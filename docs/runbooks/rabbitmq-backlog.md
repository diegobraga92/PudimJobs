# Runbook: RabbitMQ Queue Backlog

**Symptoms:** `matching.job.new` or `celery` queues grow (check
`http://localhost:15672` → Queues); new-job alert notifications lag or don't
arrive; worker latency rises.

## Investigation

1. Inspect queue depth in the RabbitMQ management UI (`pudimjobs` /
   `pudimjobs_dev` at `:15672`) or via API:
   ```bash
   curl -s -u pudimjobs:pudimjobs_dev \
     "http://localhost:15672/api/queues/%2F" | jq '.[] | {name, messages}'
   ```
2. Check the consumer is running:
   ```bash
   docker compose ps event-consumer
   docker compose logs event-consumer --tail=20
   ```
3. Check worker saturation:
   ```bash
   docker compose logs worker --tail=50
   ```

## Resolution

1. **Consumer down** → restart it (durable queues buffer events until it
   returns; no data loss):
   ```bash
   docker compose up -d event-consumer
   ```
2. **Worker pool saturated** → scale the worker:
   ```bash
   docker compose up -d --scale worker=4
   ```
3. **Poison messages** (a task that always fails): if `celery` queue is full of
   failing tasks, purge it only after confirming no legitimate work is queued:
   ```bash
   docker exec <rabbitmq-container> rabbitmqctl purge_queue celery
   ```
4. Monitor recovery: Grafana **PudimJobs Overview** → worker scrape dashboard →
   queue gauges should drain.

## Verification

- [ ] Queue depths return to ~0.
- [ ] Alert notifications arrive (check Mailpit inbox / Notifications page).
- [ ] Grafana shows no backlog and normal worker throughput.
