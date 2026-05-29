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

**状态：设计阶段已完成，待实现。**

- [x] 设计文档 → `docs/superpowers/specs/2026-05-29-file-manager-design.md`
- [x] 实现计划 → `docs/superpowers/plans/2026-05-29-file-manager-plan.md`
- [ ] 实现代码（下一步）

实现按计划分为 5 个 Chunk：
1. 基础设施 — `config.py`、`database.py`、`models.py`
2. 业务逻辑 — `file_service.py`
3. 路由层 — `routers/files.py`
4. 模板与前端 — `base.html`、`style.css`、`index.html`、`_list.html`
5. 应用组装 — `app/main.py`、根目录 `main.py`
