import os
from pathlib import Path

# 基于项目根目录计算绝对路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(_PROJECT_ROOT / "uploads"))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_PROJECT_ROOT / 'data.db'}")
MAX_FILENAME_LENGTH = 255
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500MB
