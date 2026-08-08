FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the spaCy model used by the JD parser
RUN python -m spacy download en_core_web_sm

# Copy application code
COPY . .

# Migrate + seed on startup, then run with hot reload in development
RUN chmod +x start.sh
CMD ["./start.sh"]
