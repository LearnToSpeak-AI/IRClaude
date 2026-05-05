from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from myorch.models import Decision, Recall

router = APIRouter(prefix="/memory", tags=["memory"])


def _project_or_404(request: Request, name: str):
    return request.app.state.memory.get_project_by_name(name)


@router.get("/{name}/decisions", response_class=HTMLResponse)
async def list_decisions(name: str, request: Request):
    p = _project_or_404(request, name)
    if p is None:
        return HTMLResponse("not found", status_code=404)
    decisions = request.app.state.memory.list_decisions(p.id)
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/decisions_list.html",
        {"decisions": decisions},
    )


@router.get("/{name}/recalls", response_class=HTMLResponse)
async def list_recalls(name: str, request: Request):
    p = _project_or_404(request, name)
    if p is None:
        return HTMLResponse("not found", status_code=404)
    recalls = request.app.state.memory.list_recalls(p.id)
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/recalls_list.html",
        {"recalls": recalls},
    )


@router.get("/{name}/search")
async def search(name: str, q: str, request: Request, limit: int = 10):
    p = _project_or_404(request, name)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    hits = request.app.state.memory.recall(p.id, q, limit=limit)
    accept = request.headers.get("accept", "")
    if "text/html" in accept or request.headers.get("hx-request") == "true":
        return request.app.state.templates.TemplateResponse(
            request,
            "partials/search_results.html",
            {"hits": hits},
        )
    return JSONResponse({"hits": [h.model_dump() for h in hits]})


@router.post("/{name}/decisions")
async def create_decision(
    name: str, request: Request,
    title: str = Form(...), body: str = Form(...), tags: str = Form(""),
):
    p = _project_or_404(request, name)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    d = request.app.state.memory.save_decision(
        p.id,
        Decision(project_id=p.id, title=title, body=body,
                 tags=[t.strip() for t in tags.split(",") if t.strip()]),
    )
    return JSONResponse(d.model_dump(mode="json"))


@router.post("/{name}/recalls")
async def create_recall(
    name: str, request: Request,
    text: str = Form(...), tags: str = Form(""),
):
    p = _project_or_404(request, name)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    r = request.app.state.memory.save_recall(
        p.id,
        Recall(project_id=p.id, text=text,
               tags=[t.strip() for t in tags.split(",") if t.strip()]),
    )
    return JSONResponse(r.model_dump(mode="json"))
