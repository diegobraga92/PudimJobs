.PHONY: up down logs backend-logs frontend-logs test lint

# Start all services
up:
	docker compose up -d

# Stop all services
down:
	docker compose down

# View all logs
logs:
	docker compose logs -f

# View backend logs only
backend-logs:
	docker compose logs -f backend

# View frontend logs only
frontend-logs:
	docker compose logs -f frontend

# Run backend tests
test:
	cd backend && python -m pytest

# Lint backend
lint:
	cd backend && ruff check .

# Build everything
build:
	docker compose build