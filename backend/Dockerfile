FROM python:3.12-slim

WORKDIR /app

# System libraries for weasyprint PDF rendering (used by CV tailoring)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools && pip install --no-cache-dir -r requirements.txt

# Download the spaCy model used by the JD parser
RUN python -m spacy download en_core_web_sm

# Copy the API plus the shared packages it imports (scrapers, api/events).
# Build context must be the repository root:
#   docker build -f backend/Dockerfile -t pudimjobs-backend .
COPY backend/ ./backend/
COPY api/ ./api/
COPY scrapers/ ./scrapers/

# /app covers the shared top-level packages (scrapers, api) copied alongside backend
ENV PYTHONPATH=/app/backend:/app

# Migrate + seed on startup
RUN chmod +x /app/backend/start.sh
CMD ["/app/backend/start.sh"]
