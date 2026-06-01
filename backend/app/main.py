import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import check_db_health
from app.logging_config import configure_logging
from app.metrics import setup_metrics

# Context variable for trace_id propagation
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

# Configure structured logging at startup
configure_logging(settings.log_level)

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="PudimJobs API",
    version="0.1.0",
    description="Job Application Tracker Backend",
)

# CORS: allow frontend to call backend in development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Trace ID middleware
@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    """Ensure every request has a trace_id and add it to the response."""
    trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
    trace_id_var.set(trace_id)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(trace_id=trace_id)

    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


# Attach Prometheus metrics
setup_metrics(app)


@app.get("/health")
async def health():
    """Health check endpoint.

    Returns 200 if the service is healthy (DB connected),
    or 503 if the database is unavailable.
    """
    db_healthy = await check_db_health()
    status = "ok" if db_healthy else "degraded"
    status_code = 200 if db_healthy else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "db": "connected" if db_healthy else "disconnected",
        },
    )