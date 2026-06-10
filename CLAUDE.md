# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

自用文件管理系统，挂载在云服务器上，通过 Web 网页随时随地取用文件。

- **Python 3.12**，使用虚拟环境（`.venv`）
- **FastAPI** 后端 + **Jinja2** 模板渲染 + **HTMX** 前端交互
- **SQLite** 存储文件元数据，文件直接存磁盘
- 单用户模式，无需登录

## 常用命令

```bash
# 激活虚拟环境
source .venv/Scripts/activate

# 安装依赖
pip install -r requirements.txt

# 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 运行主程序
python main.py
```

## 项目结构

```
myTest/
├── main.py                   # 开发启动入口，调用 uvicorn 运行 app.main:app
├── requirements.txt          # 项目依赖声明
├── test_e2e.py               # 端到端冒烟测试脚本（手动运行）
├── app/
│   ├── __init__.py           # 包标记（空文件）
│   ├── main.py               # FastAPI 应用实例化、模板/静态文件挂载、路由注册
│   ├── config.py             # 全局配置常量（上传目录、数据库 URL、文件大小限制）
│   ├── database.py           # SQLAlchemy 引擎、会话工厂、Base 基类、init_db()
│   ├── models.py             # File 数据模型（自引用树形结构，支持文件和文件夹）
│   ├── routers/
│   │   ├── __init__.py       # 包标记（空文件）
│   │   └── files.py          # HTTP 路由层：浏览、下载、上传、删除、重命名、创建文件夹
│   ├── services/
│   │   ├── __init__.py       # 包标记（空文件）
│   │   └── file_service.py   # 核心业务逻辑：文件 CRUD、路径拼接、名称清洗、大小格式化
│   ├── templates/
│   │   ├── base.html         # HTML5 骨架模板（引入 HTMX CDN + style.css）
│   │   ├── index.html        # 主页面模板（上传/新建文件夹按钮 + JS 交互 + 列表组件）
│   │   └── components/
│   │       └── _list.html    # 文件列表组件（面包屑导航 + 文件表格，HTMX 局部刷新目标）
│   └── static/
│       └── css/
│           └── style.css     # 全局样式（响应式布局、导航栏、文件表格、按钮等）
├── uploads/                  # 文件物理存储目录（运行时创建）
└── docs/
    └── superpowers/
        ├── specs/
        │   └── 2026-05-29-file-manager-design.md   # 设计文档
        └── plans/
            └── 2026-05-29-file-manager-plan.md     # 实现计划
```

## 文件详细说明

### 入口与配置

| 文件 | 职责 |
|------|------|
| `main.py` | 开发环境启动脚本。使用 `uvicorn.run()` 启动 FastAPI 应用，监听 `0.0.0.0:8000`，开启热重载。等价于 `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` |
| `app/config.py` | 全局配置常量。`UPLOAD_DIR`（上传目录，默认 `uploads`）、`DATABASE_URL`（SQLite 路径，默认 `sqlite:///./data.db`）、`MAX_FILENAME_LENGTH`（255 字符）、`MAX_UPLOAD_SIZE`（500MB）。均支持环境变量覆盖 |
| `requirements.txt` | 5 个依赖：`fastapi`、`uvicorn[standard]`、`python-multipart`（文件上传解析）、`jinja2`（模板引擎）、`sqlalchemy`（ORM） |

### 数据层

| 文件 | 职责 |
|------|------|
| `app/database.py` | SQLAlchemy 核心配置。创建引擎（SQLite，关闭 same-thread 检查以支持多线程）、会话工厂 `SessionLocal`、声明式基类 `Base`。提供 `get_db()` 生成器（FastAPI 依赖注入用）和 `init_db()` 建表函数 |
| `app/models.py` | 定义 `File` 模型，映射 `files` 表。自引用树形结构：`parent_id` 外键指向自身，`parent`/`children` 关系实现文件夹层级。字段包括 `name`（显示名）、`is_dir`（0=文件/1=文件夹）、`stored_name`（UUID 物理文件名）、`file_size`、`created_at`、`updated_at`。级联删除通过 SQLAlchemy cascade + 数据库外键 ondelete 双重保障 |

### 业务逻辑层

| 文件 | 职责 |
|------|------|
| `app/services/file_service.py` | 所有文件操作的核心业务逻辑，不依赖 HTTP 层。包含：`sanitize_filename()`（过滤危险字符，保留中英文/数字/下划线/点/空格）、`get_files()`（按目录查询，文件夹在前按名称排序）、`get_file()`（按 ID 单条查询）、`get_file_path()`（沿 parent 链拼接完整物理路径，最大深度 50 层）、`check_name_conflict()`（同目录同名检测）、`upload_file()`（生成 UUID 存储名，写入磁盘 + 数据库记录）、`create_dir()`（创建文件夹记录）、`rename_file()`（重命名并检查冲突）、`delete_file()`（删除数据库记录 + 递归删除物理文件）、`format_size()`（字节数转可读大小 B/KB/MB/GB/TB） |

### 路由层

| 文件 | 职责 |
|------|------|
| `app/routers/files.py` | HTTP API 路由，挂载在根路径。包含 6 个端点：`GET /`（浏览根目录）、`GET /browse/{dir_id}`（浏览子目录）、`GET /download/{file_id}`（下载文件，返回 FileResponse）、`POST /upload`（上传文件，multipart 表单）、`DELETE /delete/{file_id}`（删除，HTMX 局部刷新）、`PATCH /rename/{file_id}`（重命名）、`POST /mkdir`（创建文件夹）。内部函数 `_build_breadcrumbs()` 沿 parent 链构建面包屑，`_render_list_snippet()` 渲染 `_list.html` 片段用于 HTMX 响应 |

### 前端模板

| 文件 | 职责 |
|------|------|
| `app/templates/base.html` | HTML5 骨架。设置 `lang="zh-CN"`、viewport、引入 `style.css` 和 HTMX 2.0.4 CDN。定义 `{% block content %}` 供子模板填充 |
| `app/templates/index.html` | 主页面模板，继承 `base.html`。顶部导航栏包含隐藏的 HTMX 上传表单（选择文件自动提交）和新建文件夹按钮。底部内联 JS 处理：新建文件夹（prompt + fetch POST）、重命名（事件委托 + prompt + fetch PATCH）、HTMX 错误响应捕获和 toast 提示。`showError()` 函数在页面顶部显示 5 秒自动消失的错误消息 |
| `app/templates/components/_list.html` | 文件列表组件，HTMX 局部刷新的核心目标（`#file-list`）。包含：面包屑导航（支持 HTMX 点击跳转，根目录/中间目录/当前目录三级渲染）、空目录提示、文件表格（名称含文件夹/文件图标、大小、修改时间、操作按钮）。文件夹名称可点击进入子目录，文件提供下载/重命名/删除按钮。删除按钮使用 `hx-confirm` 弹出确认对话框 |

### 静态资源

| 文件 | 职责 |
|------|------|
| `app/static/css/style.css` | 全局样式表。定义 CSS 变量（颜色、阴影）、容器居中布局、导航栏、面包屑导航、文件表格（斑马纹 + hover 高亮）、按钮样式（主要/危险/小尺寸变体）、空状态提示、错误 toast 动画、响应式断点（移动端适配） |

### 测试

| 文件 | 职责 |
|------|------|
| `test_e2e.py` | 手动端到端测试脚本。使用 `requests` 库对本地 `localhost:8000` 发送 HTTP 请求，覆盖 8 个场景：首页访问、创建文件夹、上传文件、下载文件、重命名、删除、404 不存在、409 冲突。统计通过/失败数，全部通过则退出码 0 |

### 应用入口

| 文件 | 职责 |
|------|------|
| `app/main.py` | FastAPI 应用工厂。创建 `FastAPI` 实例（title="文件管理系统"），配置 Jinja2 模板引擎并挂载到 `app.state`，注册 `files` 路由，挂载 `/static` 静态文件服务。`startup` 事件中自动创建上传目录并初始化数据库表。配置全局 logging 格式 |

## 技术选型

| 层面 | 选择 |
|------|------|
| Web 框架 | FastAPI |
| 模板引擎 | Jinja2 |
| 前端交互 | HTMX |
| 数据库 | SQLite |
| CSS | 纯 CSS（无框架） |

## 核心功能

- 文件/文件夹的上传、下载、删除、重命名
- 目录浏览与导航
- HTTP Basic Auth 密码保护
- 上传文件大小限制 500MB

## 当前进度

**状态：MVP 实现已完成，已合并到 master。**

- [x] 设计文档 → `docs/superpowers/specs/2026-05-29-file-manager-design.md`
- [x] 实现计划 → `docs/superpowers/plans/2026-05-29-file-manager-plan.md`
- [x] 5 个 Chunk 全部实现（11 commits）
- [x] E2E 测试 → `test_e2e.py`（12 项全部通过）
- [x] 合并到 master 分支

### 实现文件清单

| Chunk | 文件 | 状态 |
|-------|------|------|
| 1. 基础设施 | `config.py`, `database.py`, `models.py` | ✓ |
| 2. 业务逻辑 | `file_service.py` | ✓ |
| 3. 路由层 | `routers/files.py` | ✓ |
| 4. 模板与前端 | `base.html`, `style.css`, `index.html`, `_list.html` | ✓ |
| 5. 应用组装 | `app/main.py`, `main.py` | ✓ |
| 测试 | `test_e2e.py` | ✓ |

### 后续可做

- 部署到云服务器
- 添加文件预览功能
- 添加拖拽上传

## 部署方案（Ubuntu 22.04）

### 架构

```
互联网 → 服务器IP:8000 → uvicorn (0.0.0.0:8000) → FastAPI 应用
                                              ↓
                                    SQLite (data.db) + uploads/
```

- uvicorn 监听 `0.0.0.0:8000`，直接对外服务
- systemd 守护进程，崩溃自动重启，开机自启
- UFW 防火墙仅开放必要端口

### 服务器目录规划

```
/opt/file-manager/          # 项目根目录
├── app/                    # 应用代码
├── main.py                 # 开发入口（部署不用）
├── requirements.txt
├── .venv/                  # Python 虚拟环境
├── data.db                 # SQLite 数据库（运行时自动生成）
├── uploads/                # 上传文件存储（运行时自动生成）
└── deploy/
    └── file-manager.service  # systemd 服务配置文件
```

### 部署步骤

#### 1. 服务器环境准备

```bash
# 更新系统包
sudo apt update && sudo apt upgrade -y

# 安装 Python 3.12
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt install python3.12 python3.12-venv git -y

# 安装并配置防火墙
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 8000/tcp    # 文件管理系统
sudo ufw enable
```

#### 2. 拉取代码

```bash
sudo mkdir -p /opt/file-manager
sudo chown $USER:$USER /opt/file-manager
git clone <仓库地址> /opt/file-manager
cd /opt/file-manager
```

#### 3. 创建虚拟环境并安装依赖

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### 4. 创建 systemd 服务

创建服务文件 `deploy/file-manager.service`（已在仓库中）：

```ini
[Unit]
Description=文件管理系统
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/file-manager
ExecStart=/opt/file-manager/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

安装并启动服务：

```bash
# 复制服务文件
sudo cp /opt/file-manager/deploy/file-manager.service /etc/systemd/system/

# 重载 systemd 配置
sudo systemctl daemon-reload

# 设置目录权限
sudo chown -R www-data:www-data /opt/file-manager

# 启动服务
sudo systemctl start file-manager

# 设置开机自启
sudo systemctl enable file-manager

# 查看运行状态
sudo systemctl status file-manager
```

#### 5. 验证部署

```bash
# 检查服务状态
sudo systemctl status file-manager

# 查看日志
sudo journalctl -u file-manager -f

# 访问测试
curl http://localhost:8000
```

浏览器访问 `http://<服务器IP>:8000` 即可使用。

### 日常运维命令

```bash
# 查看服务状态
sudo systemctl status file-manager

# 重启服务（代码更新后）
sudo systemctl restart file-manager

# 查看实时日志
sudo journalctl -u file-manager -f

# 查看最近 50 条日志
sudo journalctl -u file-manager -n 50

# 停止服务
sudo systemctl stop file-manager

# 禁用开机自启
sudo systemctl disable file-manager
```

### 更新部署流程

```bash
cd /opt/file-manager
sudo systemctl stop file-manager
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl start file-manager
```

### 备份建议

定期备份以下两个目录/文件：

- `/opt/file-manager/uploads/` — 所有上传的文件
- `/opt/file-manager/data.db` — 文件元数据库

```bash
# 示例备份脚本
tar -czf backup-$(date +%Y%m%d).tar.gz -C /opt/file-manager uploads data.db
```
