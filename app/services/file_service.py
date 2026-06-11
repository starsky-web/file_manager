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
    path = Path(UPLOAD_DIR).joinpath(*parts)
    # 向后兼容：如果拼接路径不存在，尝试旧版扁平路径
    if not path.exists() and file.stored_name:
        flat_path = Path(UPLOAD_DIR) / file.stored_name
        if flat_path.exists():
            return flat_path
    return path


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

    # 根据 parent 链构建物理路径，与 get_file_path 保持一致
    parts = [stored_name]
    current_id = parent_id
    depth = 0
    while current_id is not None and depth < 50:
        parent = get_file(db, current_id)
        if parent is None:
            break
        parts.append(parent.stored_name or parent.name)
        current_id = parent.parent_id
        depth += 1
    parts.reverse()
    file_path = Path(UPLOAD_DIR).joinpath(*parts)

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
