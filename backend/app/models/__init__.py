"""ORM models for PudimJobs.

Importing this package registers every model on ``Base.metadata`` so that
Alembic autogenerate and ``Base.metadata.create_all`` see the full schema.
"""

from app.database import Base
from app.models.alert_rule import AlertRule
from app.models.application import Application
from app.models.audit_log import AuditLog
from app.models.enums import ApplicationStatus, SourceHealth, SourceType
from app.models.generated_cv import GeneratedCV
from app.models.job import Job
from app.models.llm_config import LLMConfig
from app.models.master_cv import MasterCV
from app.models.notification import Notification
from app.models.scrape_quality import ScrapeQuality
from app.models.scrape_run import ScrapeRun
from app.models.source import Source
from app.models.source_auth import SourceAuth
from app.models.user import User

__all__ = [
    "AlertRule",
    "Application",
    "ApplicationStatus",
    "AuditLog",
    "Base",
    "GeneratedCV",
    "Job",
    "LLMConfig",
    "MasterCV",
    "Notification",
    "ScrapeQuality",
    "ScrapeRun",
    "Source",
    "SourceAuth",
    "SourceAuthType",
    "SourceHealth",
    "SourceType",
    "User",
]
