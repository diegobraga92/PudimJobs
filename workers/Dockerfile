FROM python:3.12-slim

WORKDIR /app

# Backend requirements cover the shared models/config; worker requirements add
# the scraping/runtime deps on top.
COPY backend/requirements.txt ./backend-requirements.txt
COPY workers/requirements.txt ./workers-requirements.txt
RUN pip install --no-cache-dir -r ./backend-requirements.txt -r ./workers-requirements.txt

# Copy both trees; the worker needs the backend's app package and its own code,
# plus the shared api/scrapers packages.
COPY backend/ ./backend/
COPY workers/ ./workers/
COPY api/ ./api/
COPY scrapers/ ./scrapers/

ENV PYTHONPATH=/app/backend:/app/workers:/app

CMD ["celery", "-A", "workers.celery_app", "worker", "--loglevel=info"]
