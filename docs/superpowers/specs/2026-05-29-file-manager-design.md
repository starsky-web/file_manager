# 文件管理系统设计文档

## 概述

自用文件管理系统，部署在云服务器上，通过 Web 网页随时随地取用文件。基础文件操作功能，通过密码保护访问，极简设计。

## 技术选型

| 层面 | 选择 |
|------|------|
| Web 框架 | FastAPI |
| 模板引擎 | Jinja2 |
| 前端交互 | HTMX |
| 数据库 | SQLite |
| CSS | 纯 CSS（无框架） |
| Python 版本 | 3.12 |

## 项目结构

```
myTest/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用实例创建及配置
│   ├── config.py            # 配置管理
│   ├── database.py          # SQLite 连接管理
│   ├── models.py            # SQLAlchemy ORM 模型
│   ├── routers/
│   │   ├── __init__.py
│   │   └── files.py         # 文件操作路由
│   ├── services/
│   │   ├── __init__.py
│   │   └── file_service.py  # 文件业务逻辑
│   ├── templates/
│   │   ├── base.html        # 基础布局模板
│   │   ├── index.html       # 主页面（目录浏览 + 文件列表）
│   │   └── components/      # HTMX 局部刷新组件
│   └── static/
│       ├── css/
│       └── js/
├── uploads/                  # 文件存储根目录（应用启动时自动创建）
├── requirements.txt
└── main.py                   # 启动脚本，调用 uvicorn.run()
```

- `app/main.py`：创建 `FastAPI()` 实例，注册路由、挂载静态文件、配置中间件（BasicAuth）
- 根目录 `main.py`：仅包含 `uvicorn.run("app.main:app", ...)`，是唯一启动入口

## 依赖

```
# requirements.txt
fastapi==0.115.*
uvicorn[standard]==0.34.*
python-multipart==0.0.*
jinja2==3.1.*
sqlalchemy==2.0.*
```

## 数据模型

SQLite 单表设计，使用 SQLAlchemy ORM，文件和文件夹统一存储：

```python
# models.py
class File(Base):
    __tablename__ = "files"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(255), nullable=False)   # 文件名，最长 255 字符
    is_dir      = Column(Integer, default=0)
    parent_id   = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=True)
    file_size   = Column(Integer, default=0)
    stored_name = Column(String(255), nullable=True)    # 物理存储名（UUID），仅文件有值
    created_at  = Column(DateTime, default=func.now())
    updated_at  = Column(DateTime, default=func.now(), onupdate=func.now())
```

- 文件夹通过 `is_dir=1` 标识，`parent_id` 自引用形成树形结构
- 根目录无对应数据库记录，由 `parent_id IS NULL` 隐式表示
- 物理路径按需遍历 `parent_id` 拼接
- 文件上传后以 UUID 命名存储，避免原始文件名冲突和安全问题
- 数据库表在应用启动时自动创建（`Base.metadata.create_all`）
- SQLite 单写者限制在单用户场景下不影响使用

## 模块接口

### `services/file_service.py` — 核心业务逻辑

| 方法 | 功能 |
|------|------|
| `get_files(parent_id: int \| None) -> list[File]` | 获取指定目录下的文件列表，文件夹在前、按名称升序 |
| `get_file(file_id: int) -> File \| None` | 按 ID 查询文件 |
| `get_file_path(file: File) -> Path` | 根据 parent_id 链拼接文件的物理路径 |
| `upload_file(upload_file, parent_id: int \| None) -> File` | 上传文件，生成 UUID 存储名，写入磁盘和数据库 |
| `create_dir(name: str, parent_id: int \| None) -> File` | 创建文件夹记录 |
| `rename_file(file_id: int, new_name: str) -> File` | 重命名，同目录下名称冲突时抛出 `ValueError` |
| `delete_file(file_id: int) -> None` | 删除数据库记录，若是文件则同时删除物理文件（文件夹递归处理） |

### `database.py` — 数据库连接

- `get_db()`：生成器函数，返回 SQLAlchemy `Session`，用于 FastAPI `Depends()`
- `init_db()`：创建所有表

### `config.py` — 配置

```python
import os

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data.db")
ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD", "admin")
MAX_FILENAME_LENGTH = 255
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500MB
```

## 路由设计

根目录通过 `GET /` 访问（无需 dir_id），子目录通过 `GET /browse/{dir_id}` 访问。

| 方法 | 路径 | 请求参数 | 响应 | 功能 |
|------|------|----------|------|------|
| GET | `/` | 无 | HTML 页面 | 展示根目录内容 |
| GET | `/browse/{dir_id}` | 路径参数 `dir_id` | HTML 页面 | 展示指定文件夹内容 |
| POST | `/upload` | 表单字段 `file`（文件）、`parent_id`（可选，缺省为根目录） | HTML 片段（**父目录**的文件列表） | 上传文件，同名冲突返回 409 |
| GET | `/download/{file_id}` | 路径参数 `file_id` | 文件流，`Content-Type: application/octet-stream`，`Content-Disposition: attachment; filename="原始名"` | 下载文件 |
| DELETE | `/delete/{file_id}` | 路径参数 `file_id` | HTML 片段（**父目录**的文件列表） | 删除文件或文件夹，级联删除 |
| PATCH | `/rename/{file_id}` | 表单字段 `new_name` | HTML 片段（**父目录**的文件列表） | 重命名，同名冲突返回 409 |
| POST | `/mkdir` | 表单字段 `name`（文件夹名）、`parent_id`（可选，缺省为根目录） | HTML 片段（**父目录**的文件列表） | 创建文件夹 |

**HTTP 状态码约定：**
- 200：操作成功
- 404：文件/文件夹不存在
- 409：名称冲突（同目录下已存在同名文件/文件夹，包括上传和重命名）
- 500：服务端错误（磁盘满、IO 错误等）

所有路由集中在 `routers/files.py`。

## 认证

所有页面和 API 路由均受 HTTP Basic Auth 保护。用户名为 `admin`，密码通过 `ACCESS_PASSWORD` 配置。浏览器访问时自动弹出用户名密码输入框。

## 页面与交互

**页面结构：**
- 顶部导航栏：面包屑路径（从根目录到当前目录，每级可点击跳转）、上传按钮、新建文件夹按钮
- 主体：文件/文件夹列表表格（列：名称、大小、修改时间、操作）
- 列表默认按名称升序，文件夹在前、文件在后
- 空目录显示"此文件夹为空"提示
- MVP 阶段不做分页

**HTMX 交互：**
- 上传、删除、重命名、新建文件夹均局部刷新文件列表，无需整页跳转
- 删除前使用浏览器原生 `confirm()` 弹出确认对话框
- 操作失败时在页面顶部显示错误提示

**CSS：**
- 纯 CSS，无框架，响应式布局（移动端/平板/桌面适配）

## 错误处理

- 404：返回 404 页面，显示"文件不存在"
- 409：通过 HTMX 返回错误提示"同目录下已存在同名文件或文件夹"
- 500：记录完整 traceback 到日志，返回"服务器内部错误"页面
- 操作失败时，通过 HTMX 在页面显示具体错误信息

## 日志

使用 Python 标准 `logging` 模块，日志级别 INFO，输出到控制台。异常时记录完整 traceback。

## 安全

- 上传文件名和新建文件夹名均经过过滤，去除路径分隔符（`/`、`\`），防止路径穿越
- 文件名仅保留中英文、数字、下划线、点、短横线、空格
- 文件名长度限制 255 字符
- 物理存储使用 UUID 命名，隔离原始文件名
- 删除文件夹时级联删除所有子项及物理文件
- `get_file_path()` 遍历 `parent_id` 链时设置最大递归深度 50 层，防止意外循环引用
- 上传文件大小限制 500MB（`MAX_UPLOAD_SIZE` 配置项可调整）
- 删除文件时，先删数据库记录再删物理文件；若物理文件删除失败，记录错误日志（数据库记录已通过外键级联保证一致性）

## 不做的事情（MVP 范围外）

- 文件预览（图片、PDF、文本）
- 多文件批量操作
- 文件搜索
- 文件分享链接
- 拖拽上传
- 缩略图显示
- 文件哈希去重
- 分页
- 磁盘空间监控
- API 接口（JSON 响应）
