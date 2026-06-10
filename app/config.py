import os

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data.db")
MAX_FILENAME_LENGTH = 255
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500MB
