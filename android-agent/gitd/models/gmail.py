"""Server-side Gmail OAuth connection storage."""

from typing import Optional

from sqlalchemy import Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class GmailConnection(Base):
    __tablename__ = "gmail_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    token_expiry: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
