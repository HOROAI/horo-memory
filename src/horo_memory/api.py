from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings
from .models import (
    AgentCreate,
    ContextSearch,
    EventCreate,
    ImprovementCreate,
    ImprovementDecision,
    NoteCreate,
    RunComplete,
    RunCreate,
    WorkspaceCreate,
)
from .runtime import build_service
from .security import verify_token
from .service import ConflictError, NotFoundError


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    service = build_service(settings)
    app = FastAPI(
        title="HORO Memory",
        version="0.1.0",
        description="Self-hosted operational memory and observable learning for AI agents.",
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.service = service

    def authorize(authorization: str | None = Header(default=None)) -> None:
        verify_token(settings, authorization)

    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > settings.max_request_bytes:
                    return JSONResponse({"detail": "Request body too large"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(NotFoundError)
    async def not_found_handler(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(ConflictError)
    async def conflict_handler(_: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {key: value for key, value in error.items() if key != "ctx"}
            for error in exc.errors()
        ]
        return JSONResponse({"detail": errors}, status_code=422)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": "0.1.0",
            "graphify": service.graphify.status(),
        }

    @app.get("/api/v1/workspaces", dependencies=[Depends(authorize)])
    def list_workspaces() -> list[dict[str, Any]]:
        return service.list_workspaces()

    @app.post("/api/v1/workspaces", dependencies=[Depends(authorize)], status_code=201)
    def create_workspace(request: WorkspaceCreate) -> dict[str, Any]:
        return service.create_workspace(request)

    @app.get("/api/v1/agents", dependencies=[Depends(authorize)])
    def list_agents(workspace_id: str) -> list[dict[str, Any]]:
        return service.list_agents(workspace_id)

    @app.post("/api/v1/agents", dependencies=[Depends(authorize)], status_code=201)
    def create_agent(request: AgentCreate) -> dict[str, Any]:
        return service.create_agent(request)

    @app.get("/api/v1/runs", dependencies=[Depends(authorize)])
    def list_runs(workspace_id: str, limit: int = Query(default=100, ge=1, le=500)):
        return service.list_runs(workspace_id, limit)

    @app.post("/api/v1/runs", dependencies=[Depends(authorize)], status_code=201)
    def start_run(request: RunCreate) -> dict[str, Any]:
        return service.start_run(request)

    @app.post(
        "/api/v1/workspaces/{workspace_id}/runs/{run_id}/complete",
        dependencies=[Depends(authorize)],
    )
    def complete_run(workspace_id: str, run_id: str, request: RunComplete) -> dict[str, Any]:
        return service.complete_run(workspace_id, run_id, request)

    @app.get("/api/v1/events", dependencies=[Depends(authorize)])
    def list_events(workspace_id: str, limit: int = Query(default=200, ge=1, le=2000)):
        return service.list_events(workspace_id, limit)

    @app.post("/api/v1/events", dependencies=[Depends(authorize)], status_code=201)
    def record_event(request: EventCreate) -> dict[str, Any]:
        return service.record_event(request)

    @app.post("/api/v1/vault/notes", dependencies=[Depends(authorize)])
    def write_note(request: NoteCreate) -> dict[str, Any]:
        return service.write_note(request)

    @app.post("/api/v1/context/search", dependencies=[Depends(authorize)])
    def search_context(request: ContextSearch) -> list[dict[str, Any]]:
        return service.search_context(request)

    @app.get("/api/v1/improvements", dependencies=[Depends(authorize)])
    def list_improvements(workspace_id: str) -> list[dict[str, Any]]:
        return service.list_improvements(workspace_id)

    @app.post("/api/v1/improvements", dependencies=[Depends(authorize)], status_code=201)
    def create_improvement(request: ImprovementCreate) -> dict[str, Any]:
        return service.create_improvement(request)

    @app.post(
        "/api/v1/workspaces/{workspace_id}/improvements/{proposal_id}/decision",
        dependencies=[Depends(authorize)],
    )
    def decide_improvement(
        workspace_id: str,
        proposal_id: str,
        request: ImprovementDecision,
    ) -> dict[str, Any]:
        return service.decide_improvement(workspace_id, proposal_id, request)

    @app.get("/api/v1/graph", dependencies=[Depends(authorize)])
    def graph(workspace_id: str, include_graphify: bool = True) -> dict[str, Any]:
        return service.graph(workspace_id, include_graphify)

    @app.get("/api/v1/stats", dependencies=[Depends(authorize)])
    def stats(workspace_id: str) -> dict[str, Any]:
        return service.stats(workspace_id)

    @app.get("/api/v1/integrations/graphify", dependencies=[Depends(authorize)])
    def graphify_status() -> dict[str, Any]:
        return service.graphify.status()

    @app.post(
        "/api/v1/workspaces/{workspace_id}/integrations/graphify/reindex",
        dependencies=[Depends(authorize)],
    )
    def graphify_reindex(workspace_id: str) -> dict[str, Any]:
        service._require_workspace(workspace_id)
        return service.graphify.reindex(workspace_id)

    static_dir = Path(__file__).parent / "static"
    if not static_dir.exists():
        static_dir = Path(__file__).parents[2] / "static"
    app.mount("/assets", StaticFiles(directory=static_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    return app


app = create_app()
