"""ORM models for PudimJobs.

Importing this package registers every model on ``Base.metadata`` so that
Alembic autogenerate and ``Base.metadata.create_all`` see the full schema.
"""

from app.database import Base
from app.models.application import Application
from app.models.audit_log import AuditLog
from app.models.enums import ApplicationStatus, SourceHealth, SourceType
from app.models.job import Job
from app.models.master_cv import MasterCV
from app.models.source import Source
from app.models.user import User

__all__ = [
    "Application",
    "ApplicationStatus",
    "AuditLog",
    "Base",
    "Job",
    "MasterCV",
    "Source",
    "SourceHealth",
    "SourceType",
    "User",
]
