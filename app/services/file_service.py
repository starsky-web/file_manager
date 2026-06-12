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


def upload_file(db: Session, uploaded_file, parent_id: Optional[int]) -> File:
    """上传文件，生成 UUID 存储名，写入磁盘和数据库。"""
    original_name = uploaded_file.filename or "untitled"
    safe_name = sanitize_filename(original_name)

    # 验证 parent_id 对应的记录存在且是文件夹
    if parent_id is not None:
        parent_record = get_file(db, parent_id)
        if parent_record is None or not parent_record.is_dir:
            raise ValueError("目标文件夹不存在")

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

    # 分块读取文件，同时检查大小，避免大文件撑爆内存
    chunk_size = 1024 * 1024  # 1MB
    file_size = 0
    tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    try:
        with tmp_path.open("wb") as f:
            while True:
                chunk = uploaded_file.file.read(chunk_size)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > MAX_UPLOAD_SIZE:
                    raise ValueError(f"文件大小超过限制 ({MAX_UPLOAD_SIZE // 1024 // 1024}MB)")
                f.write(chunk)
        # 先写入数据库，再确认临时文件为正式文件
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
        # DB 提交成功后再将临时文件重命名为正式文件
        tmp_path.rename(file_path)
    except Exception:
        # 清理临时文件
        if tmp_path.exists():
            tmp_path.unlink()
        raise
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

    # 如果是文件夹，同步重命名物理目录
    if file_record.is_dir:
        old_path = get_file_path(file_record)
        # 重建新路径：用新名称替换路径中当前文件夹对应的目录名
        # get_file_path 使用 stored_name or name，文件夹没有 stored_name 所以用 name
        new_path = old_path.parent / safe_name
        if old_path.exists() and old_path != new_path:
            try:
                old_path.rename(new_path)
            except OSError as e:
                logger.error(f"Failed to rename directory {old_path} -> {new_path}: {e}")

    logger.info(f"Renamed: {old_name} -> {safe_name}")
    return file_record


def delete_file(db: Session, file_id: int) -> Optional[int]:
    """删除文件记录及物理文件，返回父目录 ID。文件夹递归处理。"""
    file_record = get_file(db, file_id)
    if file_record is None:
        raise LookupError(f"文件不存在: {file_id}")

    parent_id = file_record.parent_id
    # 先收集物理文件路径，再删除 DB 记录，最后删除物理文件
    paths_to_delete = _collect_physical_paths(file_record)

    db.delete(file_record)
    db.commit()

    # DB 删除成功后再删除物理文件
    for path in paths_to_delete:
        try:
            if path.exists():
                path.unlink()
        except OSError as e:
            logger.error(f"Failed to delete physical file {path}: {e}")

    # 清理可能残留的空目录
    _cleanup_empty_dirs(file_record)

    logger.info(f"Deleted: {file_record.name} (id={file_id})")
    return parent_id


def _collect_physical_paths(file_record: File) -> list[Path]:
    """递归收集需要删除的物理文件路径。"""
    paths = []
    if not file_record.is_dir and file_record.stored_name:
        paths.append(get_file_path(file_record))
    for child in file_record.children:
        paths.extend(_collect_physical_paths(child))
    return paths


def _cleanup_empty_dirs(file_record: File) -> None:
    """从叶子向根清理空的物理目录。"""
    if file_record.is_dir:
        dir_path = get_file_path(file_record)
        try:
            if dir_path.exists() and dir_path.is_dir() and not any(dir_path.iterdir()):
                dir_path.rmdir()
        except OSError as e:
            logger.error(f"Failed to remove empty directory {dir_path}: {e}")


def format_size(size: int) -> str:
    """将字节数格式化为人类可读的大小。"""
    if size < 1024:
        return f"{size} B"
    for unit in ("KB", "MB", "GB"):
        size /= 1024
        if size < 1024:
            return f"{size:.1f} {unit}"
    size /= 1024
    return f"{size:.1f} TB"
