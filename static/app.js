const state = {
  token: sessionStorage.getItem("horo_token") || "",
  workspace: "",
  graph: { nodes: [], edges: [] },
  events: [],
  proposals: [],
  evaluations: [],
  releases: [],
  view: "all",
};

const colors = {
  workspace: "#d7ff77", agent: "#69f0b7", human: "#ffcf88", system: "#9fb6ad",
  tool: "#ff9f72", run: "#72d7ff", event: "#79a89a", improvement: "#ba9cff",
  skill: "#ffba72", workflow: "#ffdf72", version: "#f7c76b", evaluation: "#d7ff77",
  release: "#57e3ae", knowledge: "#b7c7ff", prospect: "#ff8fa3",
  campaign: "#74e6d0", outcome: "#eaff9c", default: "#9bb3aa",
};

const $ = (selector) => document.querySelector(selector);
const authDialog = $("#auth-dialog");
const workspaceSelect = $("#workspace-select");
const mobileWorkspaceSelect = $("#workspace-select-mobile");
const canvas = $("#brain-canvas");
const ctx = canvas.getContext("2d");
let animationFrame = null;
let layoutNodes = [];
let layoutEdges = [];
let selectedNode = null;
let hoveredNode = null;
let dragNode = null;
let pan = { x: 0, y: 0 };
let zoom = 1;
let pointer = { x: 0, y: 0, down: false, lastX: 0, lastY: 0 };
let refreshTimer = null;

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401) {
    sessionStorage.removeItem("horo_token");
    state.token = "";
    authDialog.showModal();
    throw new Error("Token inválido");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Error HTTP ${response.status}`);
  return body;
}

async function initialize() {
  if (!state.token) {
    authDialog.showModal();
    return;
  }
  try {
    await loadWorkspaces();
    await loadIntegration();
    startAutoRefresh();
  } catch (error) {
    showToast(error.message, true);
  }
}

async function loadWorkspaces() {
  const workspaces = await api("/api/v1/workspaces");
  workspaceSelect.innerHTML = "";
  mobileWorkspaceSelect.innerHTML = "";
  if (!workspaces.length) {
    const id = "horo-lab";
    await api("/api/v1/workspaces", {
      method: "POST", body: JSON.stringify({ id, name: "HORO Lab" }),
    });
    return loadWorkspaces();
  }
  for (const workspace of workspaces) {
    const option = document.createElement("option");
    option.value = workspace.id;
    option.textContent = workspace.name;
    workspaceSelect.append(option);
    mobileWorkspaceSelect.append(option.cloneNode(true));
  }
  const requested = new URLSearchParams(window.location.search).get("workspace");
  const previous = localStorage.getItem("horo_workspace");
  const preferenceVersion = localStorage.getItem("horo_workspace_preference_version");
  const preferred = workspaces.find((item) => item.id === "horo-production")?.id || workspaces[0].id;
  if (workspaces.some((item) => item.id === requested)) {
    state.workspace = requested;
  } else if (preferenceVersion === "2" && workspaces.some((item) => item.id === previous)) {
    state.workspace = previous;
  } else {
    state.workspace = preferred;
  }
  localStorage.setItem("horo_workspace", state.workspace);
  localStorage.setItem("horo_workspace_preference_version", "2");
  workspaceSelect.value = state.workspace;
  mobileWorkspaceSelect.value = state.workspace;
  await refresh();
}

async function refresh() {
  if (!state.workspace) return;
  const query = encodeURIComponent(state.workspace);
  const [stats, graph, events, proposals, evaluations, releases] = await Promise.all([
    api(`/api/v1/stats?workspace_id=${query}`),
    api(`/api/v1/graph?workspace_id=${query}`),
    api(`/api/v1/events?workspace_id=${query}&limit=100`),
    api(`/api/v1/improvements?workspace_id=${query}`),
    api(`/api/v1/evaluations?workspace_id=${query}`),
    api(`/api/v1/releases?workspace_id=${query}`),
  ]);
  state.graph = graph;
  state.events = events;
  state.proposals = proposals;
  state.evaluations = evaluations;
  state.releases = releases;
  $("#stat-agents").textContent = stats.agents;
  $("#stat-runs").textContent = stats.runs;
  $("#stat-events").textContent = stats.events;
  $("#stat-proposals").textContent = stats.pending_proposals;
  renderTimeline();
  renderProposals();
  renderEvaluations();
  buildLayout();
}

function startAutoRefresh() {
  clearInterval(refreshTimer);
  refreshTimer = setInterval(() => {
    if (document.visibilityState === "visible" && state.workspace && state.token) {
      refresh().catch((error) => showToast(error.message, true));
    }
  }, 30000);
}

async function loadIntegration() {
  try {
    const status = await api("/api/v1/integrations/graphify");
    $("#graphify-dot").classList.toggle("ok", status.available && status.enabled);
    $("#graphify-status").textContent = !status.enabled
      ? "Integración desactivada"
      : status.available ? "Disponible para indexar el vault" : "Pendiente de instalación";
    $("#reindex-button").disabled = !(status.available && status.enabled);
  } catch (error) {
    $("#graphify-status").textContent = "No fue posible consultar el estado";
  }
}

function visibleKinds() {
  if (state.view === "execution") return new Set(["workspace", "agent", "human", "system", "tool", "run", "event", "prospect", "campaign", "outcome"]);
  if (state.view === "knowledge") return new Set(["workspace", "knowledge", "skill", "workflow", "campaign", "prospect"]);
  if (state.view === "evolution") return new Set(["workspace", "event", "improvement", "skill", "workflow", "version", "evaluation", "release", "outcome"]);
  return null;
}

function buildLayout() {
  const allowed = visibleKinds();
  const rawNodes = state.graph.nodes.filter((node) => !allowed || allowed.has(node.kind));
  const ids = new Set(rawNodes.map((node) => node.id));
  const oldPositions = new Map(layoutNodes.map((node) => [node.id, node]));
  const rect = canvas.getBoundingClientRect();
  layoutNodes = rawNodes.map((node, index) => {
    const old = oldPositions.get(node.id);
    const angle = index * 2.39996;
    const radius = 35 + Math.sqrt(index + 1) * 32;
    return {
      ...node,
      x: old?.x ?? rect.width / 2 + Math.cos(angle) * radius,
      y: old?.y ?? rect.height / 2 + Math.sin(angle) * radius,
      vx: old?.vx ?? 0,
      vy: old?.vy ?? 0,
      radius: node.kind === "workspace" ? 16 : node.kind === "run" ? 11 : node.kind === "event" ? 6 : 9,
    };
  });
  layoutEdges = state.graph.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));
  $("#empty-state").classList.toggle("hidden", layoutNodes.length > 1);
  renderLegend();
  startAnimation();
}

function startAnimation() {
  if (animationFrame) cancelAnimationFrame(animationFrame);
  let ticks = 0;
  const loop = () => {
    if (ticks < 280) simulate();
    draw();
    ticks += 1;
    animationFrame = requestAnimationFrame(loop);
  };
  loop();
}

function simulate() {
  const byId = new Map(layoutNodes.map((node) => [node.id, node]));
  for (let i = 0; i < layoutNodes.length; i += 1) {
    const a = layoutNodes[i];
    for (let j = i + 1; j < layoutNodes.length; j += 1) {
      const b = layoutNodes[j];
      let dx = b.x - a.x, dy = b.y - a.y;
      const distanceSquared = Math.max(80, dx * dx + dy * dy);
      const force = 1300 / distanceSquared;
      const distance = Math.sqrt(distanceSquared);
      dx /= distance; dy /= distance;
      a.vx -= dx * force; a.vy -= dy * force;
      b.vx += dx * force; b.vy += dy * force;
    }
  }
  for (const edge of layoutEdges) {
    const a = byId.get(edge.source), b = byId.get(edge.target);
    if (!a || !b) continue;
    const dx = b.x - a.x, dy = b.y - a.y;
    const distance = Math.max(1, Math.hypot(dx, dy));
    const desired = edge.source_system === "graphify" ? 90 : 105;
    const force = (distance - desired) * 0.012;
    const nx = dx / distance, ny = dy / distance;
    a.vx += nx * force; a.vy += ny * force;
    b.vx -= nx * force; b.vy -= ny * force;
  }
  const rect = canvas.getBoundingClientRect();
  for (const node of layoutNodes) {
    if (node === dragNode) continue;
    node.vx += (rect.width / 2 - node.x) * 0.0004;
    node.vy += (rect.height / 2 - node.y) * 0.0004;
    node.vx *= 0.86; node.vy *= 0.86;
    const speed = Math.hypot(node.vx, node.vy);
    if (speed > 8) { node.vx = node.vx / speed * 8; node.vy = node.vy / speed * 8; }
    node.x += node.vx; node.y += node.vy;
  }
}

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  if (canvas.width !== Math.round(rect.width * ratio) || canvas.height !== Math.round(rect.height * ratio)) {
    canvas.width = Math.round(rect.width * ratio);
    canvas.height = Math.round(rect.height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  }
}

function draw() {
  resizeCanvas();
  const rect = canvas.getBoundingClientRect();
  ctx.clearRect(0, 0, rect.width, rect.height);
  ctx.save();
  ctx.translate(pan.x, pan.y); ctx.scale(zoom, zoom);
  const byId = new Map(layoutNodes.map((node) => [node.id, node]));
  for (const edge of layoutEdges) {
    const a = byId.get(edge.source), b = byId.get(edge.target);
    if (!a || !b) continue;
    const highlighted = selectedNode && (a.id === selectedNode.id || b.id === selectedNode.id);
    ctx.strokeStyle = highlighted ? "rgba(105,240,183,.72)" : "rgba(145,190,174,.16)";
    ctx.lineWidth = highlighted ? 1.5 : 0.75;
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  }
  for (const node of layoutNodes) drawNode(node);
  ctx.restore();
}

function drawNode(node) {
  const color = colors[node.kind] || colors.default;
  const active = node === selectedNode || node === hoveredNode;
  ctx.save();
  ctx.shadowColor = color; ctx.shadowBlur = active ? 24 : node.kind === "workspace" ? 18 : 9;
  ctx.fillStyle = color;
  ctx.globalAlpha = node.kind === "event" ? .78 : .96;
  ctx.beginPath(); ctx.arc(node.x, node.y, node.radius * (active ? 1.25 : 1), 0, Math.PI * 2); ctx.fill();
  ctx.globalAlpha = 1; ctx.shadowBlur = 0;
  if (active || node.kind === "workspace" || node.kind === "run" || node.kind === "improvement") {
    const label = truncate(node.label || node.id, active ? 34 : 22);
    ctx.font = `${active ? 600 : 500} ${active ? 11 : 9}px Inter, system-ui`;
    ctx.textAlign = "center"; ctx.fillStyle = active ? "#effff8" : "#a9c1b7";
    ctx.fillText(label, node.x, node.y + node.radius + 15);
  }
  ctx.restore();
}

function worldPoint(event) {
  const rect = canvas.getBoundingClientRect();
  return { x: (event.clientX - rect.left - pan.x) / zoom, y: (event.clientY - rect.top - pan.y) / zoom };
}
function nodeAt(point) {
  return [...layoutNodes].reverse().find((node) => Math.hypot(node.x - point.x, node.y - point.y) <= node.radius + 8);
}

canvas.addEventListener("pointerdown", (event) => {
  canvas.setPointerCapture(event.pointerId);
  pointer.down = true; pointer.lastX = event.clientX; pointer.lastY = event.clientY;
  dragNode = nodeAt(worldPoint(event)) || null;
});
canvas.addEventListener("pointermove", (event) => {
  const point = worldPoint(event);
  hoveredNode = nodeAt(point) || null;
  if (!pointer.down) return;
  if (dragNode) { dragNode.x = point.x; dragNode.y = point.y; dragNode.vx = 0; dragNode.vy = 0; }
  else { pan.x += event.clientX - pointer.lastX; pan.y += event.clientY - pointer.lastY; }
  pointer.lastX = event.clientX; pointer.lastY = event.clientY;
});
canvas.addEventListener("pointerup", (event) => {
  const point = worldPoint(event); const clicked = nodeAt(point);
  if (clicked) selectNode(clicked);
  pointer.down = false; dragNode = null;
});
canvas.addEventListener("wheel", (event) => {
  event.preventDefault();
  const before = worldPoint(event); const factor = event.deltaY < 0 ? 1.1 : .9;
  zoom = Math.max(.3, Math.min(3, zoom * factor));
  const rect = canvas.getBoundingClientRect();
  pan.x = event.clientX - rect.left - before.x * zoom;
  pan.y = event.clientY - rect.top - before.y * zoom;
}, { passive: false });

function selectNode(node) {
  selectedNode = node;
  $("#inspector-placeholder").classList.add("hidden");
  $("#inspector-content").classList.remove("hidden");
  $("#node-kind").textContent = node.kind;
  $("#node-title").textContent = node.label || node.id;
  $("#node-subtitle").textContent = subtitleFor(node);
  const relations = state.graph.edges.filter((edge) => edge.source === node.id || edge.target === node.id);
  $("#node-relations").innerHTML = relations.slice(0, 20).map((edge) => {
    const otherId = edge.source === node.id ? edge.target : edge.source;
    const other = state.graph.nodes.find((item) => item.id === otherId);
    return `<div class="relation"><strong>${escapeHtml(edge.relation)}</strong><br>${escapeHtml(other?.label || otherId)}</div>`;
  }).join("") || '<div class="relation">Sin relaciones registradas</div>';
  const safeData = Object.fromEntries(Object.entries(node).filter(([key]) => !["x", "y", "vx", "vy", "radius"].includes(key)));
  $("#node-data").textContent = JSON.stringify(safeData, null, 2);
}

function subtitleFor(node) {
  if (node.kind === "run") return `${node.status || "sin estado"} · ${formatDate(node.started_at)}`;
  if (node.kind === "event") return `${node.actor_type || "actor"}: ${node.actor_id || "desconocido"} · ${formatDate(node.occurred_at)}`;
  if (node.kind === "improvement") return `${node.status || "proposed"} · confianza ${Math.round((node.confidence || 0) * 100)}%`;
  return node.source === "graphify" ? "Conocimiento indexado por Graphify" : "Memoria operacional HORO";
}

function renderLegend() {
  const kinds = [...new Set(layoutNodes.map((node) => node.kind))].slice(0, 8);
  $("#legend").innerHTML = kinds.map((kind) => `<span class="legend-item"><i class="legend-dot" style="background:${colors[kind] || colors.default}"></i>${escapeHtml(kind)}</span>`).join("");
}

function renderTimeline() {
  $("#event-count").textContent = `${state.events.length} eventos`;
  $("#timeline").innerHTML = state.events.slice(0, 30).map((event) => `
    <div class="timeline-item">
      <i class="timeline-dot"></i>
      <div class="timeline-main"><strong>${escapeHtml(event.event_type.replaceAll("_", " "))}</strong><span>${escapeHtml(event.actor_id)}${event.subject_label ? ` → ${escapeHtml(event.subject_label)}` : ""}</span></div>
      <time class="timeline-time">${formatDate(event.occurred_at, true)}</time>
    </div>`).join("") || '<p class="node-subtitle">No hay actividad registrada.</p>';
}

function renderProposals() {
  $("#proposals").innerHTML = state.proposals.map((proposal) => `
    <article class="proposal">
      <header><h3>${escapeHtml(proposal.title)}</h3><span class="proposal-status ${proposal.status}">${escapeHtml(proposal.status)}</span></header>
      <p>${escapeHtml(proposal.description)}</p>
      ${proposal.status === "proposed" ? `<div class="proposal-actions"><button data-decision="approved" data-id="${proposal.id}">Aprobar</button><button data-decision="rejected" data-id="${proposal.id}">Rechazar</button></div>` : ""}
    </article>`).join("") || '<p class="node-subtitle">Aún no existen propuestas de mejora.</p>';
  document.querySelectorAll("[data-decision]").forEach((button) => button.addEventListener("click", decideProposal));
}

function renderEvaluations() {
  $("#evaluation-count").textContent = `${state.evaluations.length} comparaciones`;
  $("#evaluations").innerHTML = state.evaluations.map((item) => {
    const baseline = item.baseline_result;
    const candidate = item.candidate_result;
    const pct = item.improvement_percent == null ? "sin evidencia suficiente" : `${item.improvement_percent >= 0 ? "+" : ""}${item.improvement_percent.toFixed(1)}% según ${item.metric}`;
    const labels = { candidate_better: "candidata mejor", baseline_better: "base mejor", inconclusive: "inconcluso" };
    const proposal = state.proposals.find((candidate) => candidate.status === "approved" && candidate.target_type === item.asset_type && candidate.target_id === item.asset_id);
    const promotion = state.releases.find((release) => release.action === "promote" && release.evaluation_id === item.id);
    const rollback = promotion && state.releases.find((release) => release.action === "rollback" && release.evaluation_id === item.id && release.created_at > promotion.created_at);
    let action = "";
    if (item.verdict === "candidate_better" && proposal && !promotion) action = `<button class="decision-button" data-promote="${item.id}" data-proposal="${proposal.id}" data-type="${item.asset_type}" data-asset="${item.asset_id}" data-version="${item.candidate_version}">Promover candidata</button>`;
    else if (promotion && !rollback) action = `<button class="decision-button rollback" data-rollback="${promotion.id}" data-type="${item.asset_type}" data-asset="${item.asset_id}">Revertir versión</button>`;
    else if (rollback) action = '<span class="release-state">Reversión registrada</span>';
    else if (item.verdict === "candidate_better") action = '<span class="release-state">Pendiente de aprobación humana</span>';
    return `<article class="evaluation">
      <header><div><p class="eyebrow">${escapeHtml(item.asset_type)} · ${escapeHtml(item.asset_id)}</p><h3>${escapeHtml(item.baseline_version)} → ${escapeHtml(item.candidate_version)}</h3></div><span class="verdict ${item.verdict}">${labels[item.verdict]}</span></header>
      <div class="comparison"><div><span>Base · n=${baseline.sample_size}</span><strong>${formatMetric(baseline.mean)}</strong></div><i>VS</i><div><span>Candidata · n=${candidate.sample_size}</span><strong>${formatMetric(candidate.mean)}</strong></div></div>
      <footer>${escapeHtml(pct)} · objetivo: ${item.direction === "minimize" ? "reducir" : "aumentar"}</footer>${action}
    </article>`;
  }).join("") || '<p class="node-subtitle">Aún no hay versiones comparadas. Las comparaciones usan métricas reales de ejecuciones.</p>';
  document.querySelectorAll("[data-promote]").forEach((button) => button.addEventListener("click", promoteVersion));
  document.querySelectorAll("[data-rollback]").forEach((button) => button.addEventListener("click", rollbackVersion));
}

function formatMetric(value) { return value == null ? "—" : Number(value).toLocaleString("es-CL", { maximumFractionDigits: 2 }); }

async function promoteVersion(event) {
  const button = event.currentTarget;
  if (!window.confirm(`¿Promover ${button.dataset.asset} ${button.dataset.version} a producción?`)) return;
  try {
    await api(`/api/v1/workspaces/${encodeURIComponent(state.workspace)}/assets/${encodeURIComponent(button.dataset.type)}/${encodeURIComponent(button.dataset.asset)}/versions/${encodeURIComponent(button.dataset.version)}/promote`, {
      method: "POST", body: JSON.stringify({ evaluation_id: button.dataset.promote, proposal_id: button.dataset.proposal, promoted_by: "dashboard-operator" }),
    });
    showToast("Nueva versión promovida con evidencia"); await refresh();
  } catch (error) { showToast(error.message, true); }
}

async function rollbackVersion(event) {
  const button = event.currentTarget;
  if (!window.confirm("¿Revertir a la versión de producción anterior? La decisión quedará auditada.")) return;
  try {
    await api(`/api/v1/workspaces/${encodeURIComponent(state.workspace)}/assets/${encodeURIComponent(button.dataset.type)}/${encodeURIComponent(button.dataset.asset)}/rollback`, {
      method: "POST", body: JSON.stringify({ release_id: button.dataset.rollback, rolled_back_by: "dashboard-operator" }),
    });
    showToast("Versión anterior restaurada"); await refresh();
  } catch (error) { showToast(error.message, true); }
}

async function decideProposal(event) {
  const button = event.currentTarget;
  const decision = button.dataset.decision;
  const id = button.dataset.id;
  const verb = decision === "approved" ? "aprobar" : "rechazar";
  if (!window.confirm(`¿Confirmas que deseas ${verb} esta propuesta?`)) return;
  try {
    await api(`/api/v1/workspaces/${encodeURIComponent(state.workspace)}/improvements/${encodeURIComponent(id)}/decision`, {
      method: "POST", body: JSON.stringify({ decision, decided_by: "dashboard-operator" }),
    });
    showToast(`Propuesta ${decision === "approved" ? "aprobada" : "rechazada"}`);
    await refresh();
  } catch (error) { showToast(error.message, true); }
}

$("#auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  state.token = $("#token-input").value.trim();
  sessionStorage.setItem("horo_token", state.token);
  try {
    await loadWorkspaces(); await loadIntegration();
    $("#auth-error").classList.add("hidden"); authDialog.close();
  } catch (error) {
    $("#auth-error").textContent = error.message; $("#auth-error").classList.remove("hidden");
  }
});
$("#change-token").addEventListener("click", () => { $("#token-input").value = ""; authDialog.showModal(); });
workspaceSelect.addEventListener("change", async () => { state.workspace = workspaceSelect.value; localStorage.setItem("horo_workspace", state.workspace); await refresh(); });
mobileWorkspaceSelect.addEventListener("change", async () => { state.workspace = mobileWorkspaceSelect.value; workspaceSelect.value = state.workspace; localStorage.setItem("horo_workspace", state.workspace); await refresh(); });
$("#refresh-button").addEventListener("click", async () => { try { await refresh(); showToast("Memoria actualizada"); } catch (error) { showToast(error.message, true); } });
$("#fit-button").addEventListener("click", () => { pan = { x: 0, y: 0 }; zoom = 1; buildLayout(); });
$("#reindex-button").addEventListener("click", async () => {
  try {
    showToast("Graphify está actualizando el índice…");
    await api(`/api/v1/workspaces/${encodeURIComponent(state.workspace)}/integrations/graphify/reindex`, { method: "POST" });
    await refresh(); showToast("Índice Graphify actualizado");
  } catch (error) { showToast(error.message, true); }
});
document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
  button.classList.add("active"); state.view = button.dataset.view;
  const titles = { all: "Mapa del cerebro", execution: "Ejecuciones observables", knowledge: "Conocimiento conectado", evolution: "Evolución y aprendizaje" };
  $("#view-title").textContent = titles[state.view]; selectedNode = null; buildLayout();
}));
window.addEventListener("resize", draw);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && state.workspace && state.token) {
    refresh().catch((error) => showToast(error.message, true));
  }
});

function formatDate(value, compact = false) {
  if (!value) return "sin fecha";
  const date = new Date(value);
  return new Intl.DateTimeFormat("es-CL", compact ? { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short" } : { dateStyle: "medium", timeStyle: "short" }).format(date);
}
function truncate(value, length) { return value.length > length ? `${value.slice(0, length - 1)}…` : value; }
function escapeHtml(value) { const div = document.createElement("div"); div.textContent = String(value ?? ""); return div.innerHTML; }
function showToast(message, error = false) { const toast = $("#toast"); toast.textContent = message; toast.style.borderColor = error ? "rgba(255,125,125,.5)" : ""; toast.classList.remove("hidden"); clearTimeout(showToast.timer); showToast.timer = setTimeout(() => toast.classList.add("hidden"), 3600); }

initialize();
