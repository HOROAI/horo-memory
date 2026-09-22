# Arquitectura inicial

Esta arquitectura corresponde al MVP ejecutable `0.1.0`. SQLite y un token de operador permiten
una instalación privada por VPS; identidad empresarial y bases distribuidas pertenecen a HORO
Cloud y no se simulan en esta versión.

## Capas

### 1. Fuentes

- Vault de Obsidian o Markdown.
- Repositorios y skills.
- Objetivos y grafos de ejecución.
- Artefactos y resultados.
- Eventos producidos por los runtimes.

### 2. Adaptadores

- Obsidian/Markdown.
- Graphify.
- Hermes.
- Codex.
- Formato genérico de eventos para otros agentes.

Graphify será un adaptador inicial, no la fuente de verdad ni una dependencia imposible de reemplazar.

### 3. Registro de evidencia

Conserva eventos inmutables y referencias a los artefactos:

- inicio y término de nodo;
- herramienta utilizada;
- entrada y salida referenciada;
- aprobación o rechazo;
- error y recuperación;
- métrica observada;
- corrección humana;
- versión del grafo y del skill.

### 4. Grafo de conocimiento

Relaciona empresas, objetivos, grafos, nodos, skills, herramientas, decisiones, ejecuciones, resultados y aprendizajes.

### 5. Motor de mejora

- compara plan y ejecución;
- detecta fricción o desviaciones repetidas;
- genera una hipótesis;
- propone un cambio concreto;
- construye una evaluación;
- solicita aprobación antes de promover la nueva versión.

### 6. HORO Graph Studio

Tres vistas separadas:

1. conocimiento;
2. ejecución;
3. evolución entre versiones.

## Entidades mínimas

- `Tenant`
- `Agent`
- `Objective`
- `WorkflowGraph`
- `WorkflowVersion`
- `Node`
- `Skill`
- `Tool`
- `Run`
- `Event`
- `Artifact`
- `Decision`
- `MetricObservation`
- `Learning`
- `ImprovementProposal`
- `Evaluation`
- `Approval`

## Fuente de verdad

El registro de eventos y las versiones aprobadas son la fuente de verdad operacional. Obsidian es la superficie humana y Graphify es un índice derivado. Los índices se pueden reconstruir sin perder la historia.
