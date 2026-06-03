import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import init_db
from app.config import UPLOAD_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="文件管理系统")

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
