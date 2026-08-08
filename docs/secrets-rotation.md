# Secrets Rotation Practice

## Inventory

| Secret | Env var / location | Used by |
|--------|--------------------|---------|
| JWT signing key | `SECRET_KEY` | API (token signing/verification) |
| Database password | `DATABASE_URL` (embedded) | API, workers, Alembic |
| RabbitMQ password | `RABBITMQ_URL` / `CELERY_BROKER_URL` | Workers, consumer, API broker |
| Redis | `REDIS_URL` | API, workers (no auth by default in dev) |
| SMTP password | `SMTP_PASSWORD` | Email service |
| OpenAI API key (optional) | `OPENAI_API_KEY` | LLM tailoring (feature-flagged) |

## Rotation procedure (generic)

1. Generate a new value (use a password manager or `openssl rand`).
2. Update the environment variable in the deployment (`.env`, docker-compose,
   or the secret manager / Vault).
3. Restart the affected services (API, workers, consumer).
4. Verify: log in, trigger a scrape, confirm traces/metrics.
5. For the JWT key, existing tokens issued under the old key become invalid
   immediately — schedule rotation for a low-traffic window.

## Service-specific notes

### JWT secret (`SECRET_KEY`)
- HS256 uses a single shared secret; rotation invalidates all live sessions.
- Zero-downtime approach: keep the old key valid until the next token refresh
  by supporting a comma-separated list of acceptable keys
  (`SECRET_KEY=new,old`) and signing with the first. Not implemented — document
  as a future refinement.

### PostgreSQL password
- Rotate with `ALTER ROLE pudimjobs WITH PASSWORD '...'`, then update
  `DATABASE_URL` everywhere. Postgres accepts multiple concurrent credentials
  if a second role/user is created — simplest is a brief maintenance window.
- `infra/modules/rds/main.tf` holds `var.db_password`; rotate via Terraform
  and re-apply.

### RabbitMQ password
- `RABBITMQ_DEFAULT_USER`/`RABBITMQ_DEFAULT_PASS` are container env vars set at
  first boot. For rotation, add a new user via `rabbitmqctl`, update all
  consumers, then remove the old user.

### SMTP password
- Update `SMTP_PASSWORD`; the email service reconnects per message (no long-lived
  session to drain).

## Verification checklist after rotation

- [ ] `GET /health` returns `ok`
- [ ] `POST /api/auth/login` works and tokens verify
- [ ] A scrape completes (worker → RabbitMQ → DB)
- [ ] Alert matching delivers an email (Mailpit shows it)
- [ ] Grafana shows fresh metrics; Jaeger shows spans

## Hygiene practices

- `.env` is gitignored; secrets never in commit history (repo history is clean).
- Prefer a secret manager (AWS Secrets Manager / Vault) for production
  (Phase 8) — the app already reads everything from env vars, so swapping the
  source is config-only.
