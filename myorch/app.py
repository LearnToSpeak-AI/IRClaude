import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from myorch.config import get_settings
from myorch.db import connect, init_schema
from myorch.services.dev_server_manager import DevServerManager
from myorch.services.memory_service import MemoryService
from myorch.services.project_registry import ProjectRegistry
from myorch.services.session_manager import SessionManager


def create_app() -> FastAPI:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    from myorch.bootstrap import cleanup_orphan_images, ensure_mcp_config
    ensure_mcp_config(settings)
    cleanup_orphan_images(settings)
    conn = connect(settings.db_path)
    init_schema(conn)
    memory = MemoryService(conn)
    registry = ProjectRegistry(memory, settings.apps_root)
    session_mgr = SessionManager(memory=memory, settings=settings)
    dev_mgr = DevServerManager()

    base = Path(__file__).parent
    templates = Jinja2Templates(directory=str(base / "templates"))
    app = FastAPI(title="MyOrchestrator")
    app.mount("/static", StaticFiles(directory=str(base / "static")), name="static")

    app.state.settings = settings
    app.state.memory = memory
    app.state.registry = registry
    app.state.session_mgr = session_mgr
    app.state.dev_mgr = dev_mgr
    app.state.templates = templates

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        return templates.TemplateResponse(request, "workspace.html")

    @app.get("/health")
    async def health():
        return {
            "ok": True,
            "claude_cli": shutil.which("claude") is not None,
            "apps_root_exists": settings.apps_root.exists(),
            "db_path": str(settings.db_path),
        }

    from myorch.routers import devservers, memory as mem_router, projects, sessions
    app.include_router(projects.router)
    app.include_router(sessions.router)
    app.include_router(devservers.router)
    app.include_router(mem_router.router)

    @app.on_event("shutdown")
    async def _shutdown():
        dev_mgr.shutdown_all()

    return app
