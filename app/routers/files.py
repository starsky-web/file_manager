import base64
import logging
import secrets

from fastapi import APIRouter, Depends, Request, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import ACCESS_PASSWORD, MAX_UPLOAD_SIZE
from app.services.file_service import (
    get_files,
    get_file,
    get_file_path,
    upload_file,
    create_dir,
    rename_file,
    delete_file,
    format_size,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def verify_auth(request: Request):
    """HTTP Basic Auth 依赖注入。"""
    authorization = request.headers.get("Authorization")
    if authorization:
        try:
            scheme, credentials = authorization.split(" ", 1)
            if scheme.lower() == "basic":
                decoded = base64.b64decode(credentials).decode("utf-8")
                username, _, password = decoded.partition(":")
                if username == "admin" and secrets.compare_digest(password, ACCESS_PASSWORD):
                    return
        except Exception:
            pass
    raise HTTPException(
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="File Manager"'},
        detail="Unauthorized",
    )


def _build_breadcrumbs(db: Session, parent_id: int | None) -> list[dict]:
    """构建面包屑列表。"""
    crumbs = [{"id": None, "name": "根目录"}]
    if parent_id is not None:
        chain = []
        current = get_file(db, parent_id)
        depth = 0
        while current is not None and depth < 50:
            chain.append({"id": current.id, "name": current.name})
            current = current.parent
            depth += 1
        chain.reverse()
        crumbs.extend(chain)
    return crumbs


@router.get("/", response_class=HTMLResponse)
def browse_root(request: Request, db: Session = Depends(get_db), _=Depends(verify_auth)):
    files = get_files(db, None)
    breadcrumbs = _build_breadcrumbs(db, None)
    return request.app.state.templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "files": files,
            "parent_id": None,
            "breadcrumbs": breadcrumbs,
            "format_size": format_size,
        },
    )


@router.get("/browse/{dir_id}", response_class=HTMLResponse)
def browse_dir(dir_id: int, request: Request, db: Session = Depends(get_db), _=Depends(verify_auth)):
    file_record = get_file(db, dir_id)
    if file_record is None or not file_record.is_dir:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    files = get_files(db, dir_id)
    breadcrumbs = _build_breadcrumbs(db, dir_id)
    return request.app.state.templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "files": files,
            "parent_id": dir_id,
            "breadcrumbs": breadcrumbs,
            "format_size": format_size,
        },
    )


@router.get("/download/{file_id}")
def download_file(file_id: int, db: Session = Depends(get_db), _=Depends(verify_auth)):
    file_record = get_file(db, file_id)
    if file_record is None or file_record.is_dir:
        raise HTTPException(status_code=404, detail="文件不存在")
    file_path = get_file_path(file_record)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        file_path,
        filename=file_record.name,
        media_type="application/octet-stream",
    )


@router.post("/upload", response_class=HTMLResponse)
async def upload(
    request: Request,
    file: UploadFile,
    parent_id: int | None = Form(None),
    db: Session = Depends(get_db),
    _=Depends(verify_auth),
):
    try:
        upload_file(db, file, parent_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _render_list_snippet(request, db, parent_id)


@router.delete("/delete/{file_id}", response_class=HTMLResponse)
def delete(file_id: int, request: Request, db: Session = Depends(get_db), _=Depends(verify_auth)):
    try:
        parent_id = delete_file(db, file_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="文件不存在")
    return _render_list_snippet(request, db, parent_id)


@router.patch("/rename/{file_id}", response_class=HTMLResponse)
async def rename(
    file_id: int,
    request: Request,
    new_name: str = Form(...),
    db: Session = Depends(get_db),
    _=Depends(verify_auth),
):
    try:
        file_record = rename_file(db, file_id, new_name)
    except LookupError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _render_list_snippet(request, db, file_record.parent_id)


@router.post("/mkdir", response_class=HTMLResponse)
async def mkdir(
    request: Request,
    name: str = Form(...),
    parent_id: int | None = Form(None),
    db: Session = Depends(get_db),
    _=Depends(verify_auth),
):
    try:
        create_dir(db, name, parent_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _render_list_snippet(request, db, parent_id)


def _render_list_snippet(request: Request, db: Session, parent_id: int | None) -> HTMLResponse:
    """渲染文件列表 HTML 片段，用于 HTMX 局部刷新。"""
    files = get_files(db, parent_id)
    breadcrumbs = _build_breadcrumbs(db, parent_id)
    html = request.app.state.templates.get_template("components/_list.html").render(
        request=request,
        files=files,
        parent_id=parent_id,
        breadcrumbs=breadcrumbs,
        format_size=format_size,
    )
    return HTMLResponse(html)
