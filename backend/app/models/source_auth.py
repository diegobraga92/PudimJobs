"""Per-source authentication secrets (1:1 with ``sources``).

Credentials are stored encrypted at rest (see ``app.services.secrets``) and are
write-only through the API — responses only expose ``auth_type`` and whether a
secret is set. Supported auth types:

- ``none`` — public fetch (default)
- ``cookies`` — a raw ``Cookie`` header string pasted by the user
- ``token`` — a bearer token sent as ``Authorization: Bearer ...``
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import SourceAuthType, enum_values


class SourceAuth(Base):
    __tablename__ = "source_auth"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("sources.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    auth_type: Mapped[SourceAuthType] = mapped_column(
        Enum(SourceAuthType, native_enum=False, values_callable=enum_values),
        nullable=False,
        default=SourceAuthType.none,
    )
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
