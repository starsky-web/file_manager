from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.database import Base


class File(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    is_dir = Column(Integer, default=0)
    parent_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=True)
    file_size = Column(Integer, default=0)
    stored_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    children = relationship("File", backref="parent", remote_side=[id],
                            cascade="all, delete", passive_deletes=True)
