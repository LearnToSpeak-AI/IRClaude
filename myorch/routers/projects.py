from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_class=HTMLResponse)
async def list_projects(request: Request):
    memory = request.app.state.memory
    templates = request.app.state.templates
    projects = memory.list_projects()
    return templates.TemplateResponse(
        request,
        "partials/project_list.html",
        {"projects": projects},
    )


@router.post("/scan", response_class=HTMLResponse)
async def scan(request: Request):
    request.app.state.registry.scan()
    return await list_projects(request)


@router.get("/{name}")
async def get_project(name: str, request: Request):
    p = request.app.state.memory.get_project_by_name(name)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(p.model_dump(mode="json"))


@router.patch("/{name}")
async def update_project(
    name: str, request: Request,
    dev_command: str | None = Form(None),
    dev_port: int | None = Form(None),
    description: str | None = Form(None),
):
    memory = request.app.state.memory
    p = memory.get_project_by_name(name)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    fields = {k: v for k, v in {"dev_command": dev_command,
                                "dev_port": dev_port,
                                "description": description}.items() if v is not None}
    if fields:
        memory.update_project(p.id, **fields)
    return JSONResponse(memory.get_project_by_name(name).model_dump(mode="json"))
