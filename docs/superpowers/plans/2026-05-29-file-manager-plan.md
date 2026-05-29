# 文件管理系统实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个自用 Web 文件管理系统，支持文件/文件夹的浏览、上传、下载、删除和重命名。

**Architecture:** FastAPI 单体应用，Jinja2 服务端渲染 HTML，HTMX 处理无刷新交互，SQLAlchemy + SQLite 存储元数据，文件以 UUID 命名存磁盘。

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Jinja2, HTMX 2.0, SQLite

---

## Chunk 1: 基础设施 — 配置、数据库、数据模型

> **注意:** `app/__init__.py`、`app/routers/__init__.py`、`app/services/__init__.py`、`requirements.txt` 已存在，无需重复创建。

### Task 1.1: 编写 config.py

**Files:**
- Create: `app/config.py`

- [ ] **Step 1: 写入配置模块**

```python
import os

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data.db")
ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD", "admin")
MAX_FILENAME_LENGTH = 255
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500MB
```

- [ ] **Step 2: 验证** — 运行 `python -c "from app.config import UPLOAD_DIR; print(UPLOAD_DIR)"`，应输出 `uploads`

- [ ] **Step 3: 提交**

```bash
git add app/config.py
git commit -m "feat: add config module"
```

---

### Task 1.2: 编写 database.py

**Files:**
- Create: `app/database.py`

- [ ] **Step 1: 写入数据库连接模块**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app.models import File  # noqa: F401
    Base.metadata.create_all(bind=engine)
```

- [ ] **Step 2: 验证** — 运行 `python -c "from app.database import engine; print(engine.url)"`，应输出 SQLite URL

- [ ] **Step 3: 提交**

```bash
git add app/database.py
git commit -m "feat: add database connection module"
```

---

### Task 1.3: 编写 models.py

**Files:**
- Create: `app/models.py`

- [ ] **Step 1: 写入 ORM 模型**

```python
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.database import Base


class File(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    is_dir = Column(Integer, default=0)
    parent_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=True)
    file_size = Column(Integer, default=0)
    stored_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    children = relationship("File", backref="parent", remote_side=[id],
                            cascade="all, delete", passive_deletes=True)
```

- [ ] **Step 2: 验证** — 运行 `python -c "from app.models import File; print(File.__tablename__)"`，应输出 `files`

- [ ] **Step 3: 提交**

```bash
git add app/models.py
git commit -m "feat: add File ORM model"
```

---

## Chunk 2: 业务逻辑 — file_service

### Task 2.1: 编写 sanitize_filename 和基础查询函数

**Files:**
- Create: `app/services/file_service.py`

- [ ] **Step 1: 写入完整的 file_service.py**

```python
import re
import uuid
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR, MAX_FILENAME_LENGTH, MAX_UPLOAD_SIZE
from app.models import File

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """过滤文件名中的危险字符，只保留安全字符。"""
    # 去除路径分隔符
    name = name.replace("/", "").replace("\\", "")
    # 只保留中英文、数字、下划线、点、短横线、空格
    name = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9_. \-]", "", name)
    # 去除首尾空格和点
    name = name.strip(". ")
    # 截断到最大长度
    if len(name) > MAX_FILENAME_LENGTH:
        name = name[:MAX_FILENAME_LENGTH]
    # 如果过滤后为空，使用默认名
    if not name:
        name = "untitled"
    return name


def get_files(db: Session, parent_id: Optional[int]) -> list[File]:
    """获取指定目录下的文件列表，文件夹在前、按名称升序。"""
    return (
        db.query(File)
        .filter(File.parent_id == parent_id)
        .order_by(File.is_dir.desc(), File.name.asc())
        .all()
    )


def get_file(db: Session, file_id: int) -> Optional[File]:
    """按 ID 查询文件。"""
    return db.query(File).filter(File.id == file_id).first()


def get_file_path(file: File) -> Path:
    """根据 parent_id 链拼接文件的物理路径，最大深度 50 层。"""
    parts = []
    current = file
    depth = 0
    while current is not None and depth < 50:
        parts.append(current.stored_name or current.name)
        current = current.parent
        depth += 1
    parts.reverse()
    return Path(UPLOAD_DIR).joinpath(*parts)


def check_name_conflict(db: Session, name: str, parent_id: Optional[int],
                        exclude_id: Optional[int] = None) -> bool:
    """检查同目录下是否存在同名文件/文件夹。"""
    query = db.query(File).filter(
        File.parent_id == parent_id,
        File.name == name,
    )
    if exclude_id is not None:
        query = query.filter(File.id != exclude_id)
    return query.first() is not None


def upload_file(db: Session, upload_file, parent_id: Optional[int]) -> File:
    """上传文件，生成 UUID 存储名，写入磁盘和数据库。"""
    original_name = upload_file.filename or "untitled"
    safe_name = sanitize_filename(original_name)

    if check_name_conflict(db, safe_name, parent_id):
        raise ValueError(f"同名文件已存在: {safe_name}")

    stored_name = uuid.uuid4().hex
    file_path = Path(UPLOAD_DIR) / stored_name
    file_path.parent.mkdir(parents=True, exist_ok=True)

    content = upload_file.file.read()
    file_size = len(content)

    if file_size > MAX_UPLOAD_SIZE:
        raise ValueError(f"文件大小超过限制 ({MAX_UPLOAD_SIZE // 1024 // 1024}MB)")

    file_path.write_bytes(content)

    file_record = File(
        name=safe_name,
        is_dir=0,
        parent_id=parent_id,
        file_size=file_size,
        stored_name=stored_name,
    )
    db.add(file_record)
    db.commit()
    db.refresh(file_record)
    logger.info(f"Uploaded file: {safe_name} -> {stored_name} ({file_size} bytes)")
    return file_record


def create_dir(db: Session, name: str, parent_id: Optional[int]) -> File:
    """创建文件夹记录。"""
    safe_name = sanitize_filename(name)

    if check_name_conflict(db, safe_name, parent_id):
        raise ValueError(f"同名文件或文件夹已存在: {safe_name}")

    dir_record = File(
        name=safe_name,
        is_dir=1,
        parent_id=parent_id,
    )
    db.add(dir_record)
    db.commit()
    db.refresh(dir_record)
    logger.info(f"Created directory: {safe_name}")
    return dir_record


def rename_file(db: Session, file_id: int, new_name: str) -> File:
    """重命名文件或文件夹。"""
    file_record = get_file(db, file_id)
    if file_record is None:
        raise LookupError(f"文件不存在: {file_id}")

    safe_name = sanitize_filename(new_name)

    if check_name_conflict(db, safe_name, file_record.parent_id, exclude_id=file_id):
        raise ValueError(f"同名文件或文件夹已存在: {safe_name}")

    old_name = file_record.name
    file_record.name = safe_name
    db.commit()
    db.refresh(file_record)
    logger.info(f"Renamed: {old_name} -> {safe_name}")
    return file_record


def delete_file(db: Session, file_id: int) -> Optional[int]:
    """删除文件记录及物理文件，返回父目录 ID。文件夹递归处理。"""
    file_record = get_file(db, file_id)
    if file_record is None:
        raise LookupError(f"文件不存在: {file_id}")

    parent_id = file_record.parent_id
    _delete_physical_files(file_record)

    db.delete(file_record)
    db.commit()
    logger.info(f"Deleted: {file_record.name} (id={file_id})")
    return parent_id


def _delete_physical_files(file_record: File) -> None:
    """递归删除物理文件。"""
    if not file_record.is_dir and file_record.stored_name:
        file_path = get_file_path(file_record)
        try:
            if file_path.exists():
                file_path.unlink()
        except OSError as e:
            logger.error(f"Failed to delete physical file {file_path}: {e}")

    for child in file_record.children:
        _delete_physical_files(child)


def format_size(size: int) -> str:
    """将字节数格式化为人类可读的大小。"""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size} {unit}"
        size //= 1024
    return f"{size} TB"
```

- [ ] **Step 2: 验证** — 运行 `python -c "from app.services.file_service import sanitize_filename, format_size; print(sanitize_filename('../etc/passwd'), format_size(2048))"`，应输出 `etcpasswd 2 KB`

- [ ] **Step 3: 提交**

```bash
git add app/services/file_service.py
git commit -m "feat: add file_service with all business logic functions"
```

---

## Chunk 3: 路由层 — HTTP 端点

### Task 3.1: 编写完整的路由文件

**Files:**
- Create: `app/routers/files.py`

- [ ] **Step 1: 写入路由文件**

```python
import logging

from fastapi import APIRouter, Depends, Request, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import MAX_UPLOAD_SIZE
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
def browse_root(request: Request, db: Session = Depends(get_db)):
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
def browse_dir(dir_id: int, request: Request, db: Session = Depends(get_db)):
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
def download_file(file_id: int, db: Session = Depends(get_db)):
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
):
    try:
        upload_file(db, file, parent_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _render_list_snippet(request, db, parent_id)


@router.delete("/delete/{file_id}", response_class=HTMLResponse)
def delete(file_id: int, request: Request, db: Session = Depends(get_db)):
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
```

- [ ] **Step 2: 验证** — 运行 `python -c "from app.routers.files import router; print(len(router.routes))"`，应输出 `7`

- [ ] **Step 3: 提交**

```bash
git add app/routers/files.py
git commit -m "feat: add all file operation routes"
```

---

## Chunk 4: 模板与前端

> **注意:** 确保以下目录已存在：`app/templates/`、`app/templates/components/`、`app/static/css/`（可在写入文件前手动创建或由编辑器自动创建）。

### Task 4.1: 编写 base.html 和 CSS

**Files:**
- Create: `app/templates/base.html`
- Create: `app/static/css/style.css`

- [ ] **Step 1: 写入 base.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>文件管理系统</title>
    <link rel="stylesheet" href="/static/css/style.css">
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
</head>
<body>
    <div class="container">
        {% block content %}{% endblock %}
    </div>
</body>
</html>
```

- [ ] **Step 2: 写入 style.css**

```css
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: #f5f5f5;
    color: #333;
    line-height: 1.6;
}

.container {
    max-width: 960px;
    margin: 0 auto;
    padding: 20px;
}

/* 导航栏 */
.navbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    padding: 16px 0;
    border-bottom: 1px solid #e0e0e0;
    margin-bottom: 20px;
}

.breadcrumbs {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 16px;
    flex-wrap: wrap;
}

.breadcrumbs a {
    color: #1a73e8;
    text-decoration: none;
}

.breadcrumbs a:hover {
    text-decoration: underline;
}

.breadcrumbs .sep {
    color: #999;
    margin: 0 4px;
}

.breadcrumbs .current {
    color: #333;
    font-weight: 500;
}

.nav-actions {
    display: flex;
    gap: 8px;
    align-items: center;
}

/* 按钮 */
.btn {
    display: inline-block;
    padding: 8px 16px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    text-decoration: none;
    color: #fff;
    background: #1a73e8;
    transition: background 0.2s;
}

.btn:hover {
    background: #1557b0;
}

.btn-danger {
    background: #dc3545;
}

.btn-danger:hover {
    background: #b02a37;
}

.btn-sm {
    padding: 4px 10px;
    font-size: 13px;
}

/* 文件列表表格 */
.file-table {
    width: 100%;
    border-collapse: collapse;
    background: #fff;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.file-table th,
.file-table td {
    padding: 12px 16px;
    text-align: left;
    border-bottom: 1px solid #eee;
}

.file-table th {
    background: #fafafa;
    font-weight: 500;
    font-size: 13px;
    color: #666;
}

.file-table tr:last-child td {
    border-bottom: none;
}

.file-table tr:hover {
    background: #f8f9ff;
}

.file-table .col-name { width: 45%; }
.file-table .col-size { width: 15%; }
.file-table .col-time { width: 20%; }
.file-table .col-actions { width: 20%; text-align: right; }

.file-icon {
    margin-right: 8px;
}

.file-link {
    color: #1a73e8;
    text-decoration: none;
    font-weight: 500;
}

.file-link:hover {
    text-decoration: underline;
}

.dir-link {
    color: #333;
    text-decoration: none;
    font-weight: 500;
    cursor: pointer;
}

.dir-link:hover {
    color: #1a73e8;
}

.file-size, .file-time {
    color: #888;
    font-size: 13px;
}

.actions {
    display: flex;
    gap: 6px;
    justify-content: flex-end;
}

/* 空状态 */
.empty-state {
    text-align: center;
    padding: 60px 20px;
    color: #999;
    font-size: 16px;
}

/* 上传表单 */
.upload-form {
    display: inline;
}

/* 错误提示 */
.error-toast {
    background: #fde7e9;
    color: #c62828;
    padding: 12px 16px;
    border-radius: 6px;
    margin-bottom: 16px;
    font-size: 14px;
}

/* 响应式 */
@media (max-width: 768px) {
    .container { padding: 12px; }
    .navbar { flex-direction: column; align-items: flex-start; }
    .file-table th.col-size,
    .file-table td.col-size,
    .file-table th.col-time,
    .file-table td.col-time { display: none; }
    .file-table .col-name { width: 60%; }
    .file-table .col-actions { width: 40%; }
}

@media (max-width: 480px) {
    .nav-actions { flex-direction: column; width: 100%; }
    .nav-actions .btn { width: 100%; text-align: center; }
}
```

- [ ] **Step 3: 提交**

```bash
git add app/templates/base.html app/static/css/style.css
git commit -m "feat: add base template and CSS styles"
```

---

### Task 4.2: 编写 index.html（完整页面模板）

**Files:**
- Create: `app/templates/index.html`

- [ ] **Step 1: 写入 index.html**

```html
{% extends "base.html" %}
{% block content %}

<nav class="navbar">
    <div class="nav-actions">
        <form class="upload-form"
              hx-post="/upload"
              hx-target="#file-list"
              hx-encoding="multipart/form-data"
              hx-on::after-request="document.getElementById('file-input').value = ''">
            <input type="hidden" name="parent_id" value="{{ parent_id or '' }}">
            <input type="file" name="file" id="file-input" required
                   style="display:none"
                   onchange="this.form.dispatchEvent(new Event('submit', {bubbles: true}))">
            <button type="button" class="btn" onclick="document.getElementById('file-input').click()">
                上传文件
            </button>
        </form>
        <button class="btn" id="mkdir-btn">新建文件夹</button>
    </div>
</nav>

<div id="error-area"></div>

{% include "components/_list.html" %}

<script>
document.getElementById('mkdir-btn').addEventListener('click', function() {
    var name = prompt('请输入文件夹名称:');
    if (!name || !name.trim()) return;
    var formData = new FormData();
    formData.append('name', name.trim());
    formData.append('parent_id', '{{ parent_id or '' }}');
    fetch('/mkdir', { method: 'POST', body: formData,
        headers: { 'HX-Request': 'true', 'HX-Target': 'file-list' }
    }).then(function(r) {
        if (r.ok) return r.text();
        return r.text().then(function(t) { throw new Error(t); });
    }).then(function(html) {
        document.getElementById('file-list').outerHTML = html;
        htmx.process(document.getElementById('file-list'));
    }).catch(function(e) {
        showError('创建文件夹失败: ' + e.message);
    });
});

document.addEventListener('click', function(e) {
    if (!e.target.matches('.rename-btn')) return;
    var btn = e.target;
    var fileId = btn.dataset.fileId;
    var oldName = btn.dataset.fileName;
    var newName = prompt('请输入新名称:', oldName);
    if (!newName || !newName.trim()) return;
    var formData = new FormData();
    formData.append('new_name', newName.trim());
    fetch('/rename/' + fileId, { method: 'PATCH', body: formData,
        headers: { 'HX-Request': 'true', 'HX-Target': 'file-list' }
    }).then(function(r) {
        if (r.ok) return r.text();
        return r.text().then(function(t) { throw new Error(t); });
    }).then(function(html) {
        document.getElementById('file-list').outerHTML = html;
        htmx.process(document.getElementById('file-list'));
    }).catch(function(e) {
        showError('重命名失败: ' + e.message);
    });
});

document.body.addEventListener('htmx:responseError', function(evt) {
    var message = '操作失败';
    try {
        var detail = JSON.parse(evt.detail.xhr.responseText);
        if (detail.detail) message = detail.detail;
    } catch(_) {}
    showError(message);
});

function showError(msg) {
    var area = document.getElementById('error-area');
    area.innerHTML = '<div class="error-toast">' + msg + '</div>';
    setTimeout(function() { area.innerHTML = ''; }, 5000);
}
</script>

{% endblock %}
```

- [ ] **Step 2: 验证** — 运行 `python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('app/templates')); t = env.get_template('index.html'); print('OK')"`，应输出 `OK`

- [ ] **Step 3: 提交**

```bash
git add app/templates/index.html
git commit -m "feat: add main page template with HTMX interactions"
```

---

### Task 4.3: 编写 _list.html（文件列表组件模板）

**Files:**
- Create: `app/templates/components/_list.html`

- [ ] **Step 1: 写入 _list.html**

```html
<div id="file-list">
    <!-- 面包屑导航 — 在 #file-list 内确保 HTMX 刷新时同步更新 -->
    <div class="breadcrumbs">
        {% for crumb in breadcrumbs %}
            {% if not loop.first %}
                <span class="sep">/</span>
            {% endif %}
            {% if loop.last %}
                <span class="current">{{ crumb.name }}</span>
            {% elif crumb.id is none %}
                <a href="/" hx-get="/" hx-target="#file-list" hx-push-url="true">根目录</a>
            {% else %}
                <a href="/browse/{{ crumb.id }}" hx-get="/browse/{{ crumb.id }}" hx-target="#file-list" hx-push-url="true">{{ crumb.name }}</a>
            {% endif %}
        {% endfor %}
    </div>

    {% if not files %}
        <div class="empty-state">此文件夹为空</div>
    {% else %}
        <table class="file-table">
            <thead>
                <tr>
                    <th class="col-name">名称</th>
                    <th class="col-size">大小</th>
                    <th class="col-time">修改时间</th>
                    <th class="col-actions">操作</th>
                </tr>
            </thead>
            <tbody>
                {% for f in files %}
                <tr>
                    <td class="col-name">
                        {% if f.is_dir %}
                            <span class="file-icon">&#128193;</span>
                            <a href="/browse/{{ f.id }}"
                               hx-get="/browse/{{ f.id }}"
                               hx-target="#file-list"
                               hx-push-url="true"
                               class="dir-link">{{ f.name }}</a>
                        {% else %}
                            <span class="file-icon">&#128196;</span>
                            <span class="file-link">{{ f.name }}</span>
                        {% endif %}
                    </td>
                    <td class="col-size">
                        {% if not f.is_dir %}
                            <span class="file-size">{{ format_size(f.file_size) }}</span>
                        {% endif %}
                    </td>
                    <td class="col-time">
                        <span class="file-time">{{ f.updated_at.strftime('%Y-%m-%d %H:%M') }}</span>
                    </td>
                    <td class="col-actions">
                        <div class="actions">
                            {% if not f.is_dir %}
                                <a href="/download/{{ f.id }}" class="btn btn-sm">下载</a>
                            {% endif %}
                            <button class="btn btn-sm rename-btn"
                                    data-file-id="{{ f.id }}"
                                    data-file-name="{{ f.name }}">重命名</button>
                            <button class="btn btn-sm btn-danger"
                                    hx-delete="/delete/{{ f.id }}"
                                    hx-target="#file-list"
                                    hx-confirm="确定要删除「{{ f.name }}」吗？{% if f.is_dir %}文件夹内所有内容将被一起删除。{% endif %}">删除</button>
                        </div>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    {% endif %}
</div>
```

- [ ] **Step 2: 验证** — 运行 `python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('app/templates')); t = env.get_template('components/_list.html'); print('OK')"`，应输出 `OK`

- [ ] **Step 3: 提交**

```bash
git add app/templates/components/_list.html
git commit -m "feat: add file list component template"
```

---

## Chunk 5: 应用组装与启动

### Task 5.1: 编写 app/main.py

**Files:**
- Create: `app/main.py`

- [ ] **Step 1: 写入 FastAPI 应用实例**

```python
import logging
import secrets
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import ACCESS_PASSWORD, UPLOAD_DIR
from app.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """HTTP Basic Auth 中间件，保护所有路由。"""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/static"):
            return await call_next(request)

        authorization = request.headers.get("Authorization")
        if authorization:
            try:
                scheme, credentials = authorization.split(" ", 1)
                if scheme.lower() == "basic":
                    import base64
                    decoded = base64.b64decode(credentials).decode("utf-8")
                    username, _, password = decoded.partition(":")
                    if username == "admin" and secrets.compare_digest(password, ACCESS_PASSWORD):
                        return await call_next(request)
            except Exception:
                pass

        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="File Manager"'},
            content="Unauthorized",
        )


app = FastAPI(title="文件管理系统")

# 注册中间件（在路由之前）
app.add_middleware(BasicAuthMiddleware)

# 配置 Jinja2 模板引擎
templates = Jinja2Templates(directory="app/templates")
app.state.templates = templates

# 注册路由
from app.routers import files  # noqa: E402
app.include_router(files.router)

# 挂载静态文件（在路由之后）
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
def startup():
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    init_db()
    logger.info(f"File manager started. Upload dir: {UPLOAD_DIR}")
```

- [ ] **Step 2: 验证** — 运行 `python -c "from app.main import app; print(app.title)"`，应输出 `文件管理系统`

- [ ] **Step 3: 提交**

```bash
git add app/main.py
git commit -m "feat: add FastAPI application with BasicAuth and templates"
```

---

### Task 5.2: 更新根目录 main.py 为启动脚本

**Files:**
- Modify: `main.py`

- [ ] **Step 1: 重写 main.py**

```python
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
```

- [ ] **Step 2: 验证** — 运行 `python main.py`，访问 `http://localhost:8000`，应弹出密码输入框

- [ ] **Step 3: 提交**

```bash
git add main.py
git commit -m "feat: update main.py as uvicorn startup script"
```

---

## 最终验证

### Task 6.1: 端到端功能测试

- [ ] **Step 1: 启动服务器** — `python main.py`

- [ ] **Step 2: 浏览器访问 `http://localhost:8000`**，输入用户名 `admin`，密码 `admin`（默认）

- [ ] **Step 3: 测试上传** — 点击"上传文件"，选择一个测试文件，验证文件出现在列表中

- [ ] **Step 4: 测试新建文件夹** — 点击"新建文件夹"，输入名称，验证文件夹出现且可点击进入

- [ ] **Step 5: 测试下载** — 点击文件的"下载"按钮，验证文件正确下载

- [ ] **Step 6: 测试重命名** — 点击"重命名"，输入新名称，验证名称更新

- [ ] **Step 7: 测试删除** — 点击"删除"，确认弹窗后验证文件/文件夹被删除

- [ ] **Step 8: 测试错误处理** — 上传同名文件，验证 409 错误提示；访问 `/browse/99999`，验证 404

- [ ] **Step 9: 提交**

```bash
git add app/ main.py requirements.txt
git commit -m "feat: file manager MVP complete"
```
