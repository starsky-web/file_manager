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
