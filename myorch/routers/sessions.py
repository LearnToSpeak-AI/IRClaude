import asyncio
import json
import uuid

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/sessions", tags=["sessions"])

MAX_IMAGE_BYTES = 5 * 1024 * 1024


class OpenSessionRequest(BaseModel):
    project: str


@router.get("/workspace/{name}", response_class=HTMLResponse)
async def workspace(name: str, request: Request):
    memory = request.app.state.memory
    templates = request.app.state.templates
    project = memory.get_project_by_name(name)
    if project is None:
        return HTMLResponse("not found", status_code=404)
    return templates.TemplateResponse(
        request,
        "partials/workspace_panel.html",
        {"project": project},
    )


@router.post("/open")
async def open_session(req: OpenSessionRequest, request: Request):
    memory = request.app.state.memory
    project = memory.get_project_by_name(req.project)
    if project is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    handle = request.app.state.session_mgr.open(project_id=project.id)
    return JSONResponse({"session_id": handle.session_id, "project": project.name})


@router.post("/{session_id}/close")
async def close_session(session_id: int, request: Request):
    request.app.state.session_mgr.request_summary_and_close(session_id)
    return {"ok": True}


@router.post("/{session_id}/upload-image")
async def upload_image(session_id: int, request: Request, file: UploadFile = File(...)):
    settings = request.app.state.settings
    data = await file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="image > 5MB")
    sess_dir = settings.tmp_dir / str(session_id)
    sess_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".png" if (file.content_type or "").endswith("png") else ".bin"
    fname = f"{uuid.uuid4().hex}{suffix}"
    path = sess_dir / fname
    path.write_bytes(data)
    return {"path": str(path)}


@router.websocket("/ws/{session_id}")
async def ws_session(ws: WebSocket, session_id: int):
    await ws.accept()
    mgr = ws.app.state.session_mgr
    handle = mgr.get(session_id)
    if handle is None:
        await ws.send_text(json.dumps({"error": "session not found"}))
        await ws.close()
        return

    async def pump_pty_to_ws():
        while True:
            chunk = await asyncio.to_thread(handle.pty.read_nonblocking, 0.1)
            if chunk:
                await ws.send_text(chunk)
            else:
                await asyncio.sleep(0.05)
            if not handle.pty.is_alive():
                await ws.send_text("\n[session ended]\n")
                break

    pump_task = asyncio.create_task(pump_pty_to_ws())
    try:
        while True:
            data = await ws.receive_text()
            handle.pty.write(data)
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()
