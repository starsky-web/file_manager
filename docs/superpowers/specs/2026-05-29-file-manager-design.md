# 文件管理系统设计文档

## 概述

自用文件管理系统，部署在云服务器上，通过 Web 网页随时随地取用文件。基础文件操作功能，单用户模式，极简设计。

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
│   ├── main.py              # FastAPI 应用入口
│   ├── config.py            # 配置管理
│   ├── database.py          # SQLite 连接管理
│   ├── models.py            # 数据模型
│   ├── routers/
│   │   ├── __init__.py
│   │   └── files.py         # 文件操作路由
│   ├── services/
│   │   ├── __init__.py
│   │   └── file_service.py  # 文件业务逻辑
│   ├── templates/
│   │   ├── base.html        # 基础布局模板
│   │   ├── index.html       # 主页面（目录浏览）
│   │   └── components/      # HTMX 局部刷新组件
│   └── static/
│       ├── css/
│       └── js/
├── uploads/                  # 文件存储根目录
├── requirements.txt
└── main.py                   # 启动入口
```

## 数据模型

SQLite 单表设计，文件和文件夹统一存储：

```sql
CREATE TABLE files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,           -- 文件名（显示名）
    is_dir      INTEGER DEFAULT 0,       -- 是否为文件夹
    parent_id   INTEGER,                 -- 父文件夹 ID（NULL 表示根目录）
    file_size   INTEGER DEFAULT 0,       -- 文件大小（字节），文件夹为 0
    stored_name TEXT,                    -- 物理存储名（上传时生成，仅文件有值）
    file_hash   TEXT,                    -- SHA256 哈希，预留去重
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_id) REFERENCES files(id) ON DELETE CASCADE
);
```

- 文件夹通过 `is_dir=1` 标识，`parent_id` 自引用形成树形结构
- 物理路径按需遍历 `parent_id` 拼接
- 文件上传后以 UUID 命名存储，避免原始文件名冲突和安全问题

## 路由设计

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/` | 主页面，展示根目录内容 |
| GET | `/browse/{dir_id}` | 浏览指定文件夹 |
| POST | `/upload` | 上传文件到当前目录 |
| GET | `/download/{file_id}` | 下载指定文件 |
| DELETE | `/delete/{file_id}` | 删除文件或文件夹（级联删除物理文件） |
| PATCH | `/rename/{file_id}` | 重命名文件或文件夹 |
| POST | `/mkdir` | 在当前目录下创建文件夹 |

所有路由集中在 `routers/files.py`。

## 页面与交互

**页面结构：**
- 顶部导航栏：面包屑路径、上传按钮、新建文件夹按钮
- 主体：文件/文件夹列表表格（名称、大小、修改时间、操作）
- 文件夹可点击进入子目录

**HTMX 交互：**
- 上传、删除、重命名、新建文件夹均局部刷新列表，无需整页跳转
- 删除前弹出确认对话框

**CSS：**
- 纯 CSS，无框架，响应式布局适配多端

## 配置

```python
# config.py
UPLOAD_DIR = "uploads"
DATABASE_URL = "sqlite:///./data.db"
```

## 错误处理

- 404：文件不存在时返回友好提示
- 500：服务端异常记录日志，返回错误页面
- 操作失败（磁盘满等）：通过 HTMX 在页面显示错误提示

## 安全

- 上传文件名过滤路径分隔符，防止路径穿越
- 文件名仅保留中英文、数字、下划线、点、短横线
- 物理存储使用 UUID 命名，隔离原始文件名
- 删除文件夹时级联删除所有子项及物理文件
