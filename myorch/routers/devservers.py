from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/devservers", tags=["devservers"])


@router.post("/{name}/start")
async def start(name: str, request: Request):
    memory = request.app.state.memory
    dev_mgr = request.app.state.dev_mgr
    p = memory.get_project_by_name(name)
    if p is None or not p.dev_command:
        return JSONResponse({"error": "no dev_command set"}, status_code=400)
    dev_mgr.start(project_id=p.id, command=p.dev_command, cwd=p.path)
    return {"ok": True, "project": name}


@router.post("/{name}/stop")
async def stop(name: str, request: Request):
    memory = request.app.state.memory
    p = memory.get_project_by_name(name)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    request.app.state.dev_mgr.stop(p.id)
    return {"ok": True}


@router.get("/{name}/status")
async def status(name: str, request: Request):
    memory = request.app.state.memory
    p = memory.get_project_by_name(name)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"running": request.app.state.dev_mgr.is_running(p.id)}


@router.get("/{name}/tail")
async def tail(name: str, request: Request):
    memory = request.app.state.memory
    p = memory.get_project_by_name(name)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    lines = request.app.state.dev_mgr.tail(p.id)[-100:]
    accept = request.headers.get("accept", "")
    if "text/html" in accept or request.headers.get("hx-request") == "true":
        return request.app.state.templates.TemplateResponse(
            request,
            "partials/devserver_tail.html",
            {"lines": lines},
        )
    return {"lines": lines}
