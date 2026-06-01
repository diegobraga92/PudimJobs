# Service Level Objectives (SLOs)

## API Availability

| Metric | Target |
|--------|--------|
| **SLI** | `successful_health_checks / total_health_checks` over rolling 7-day window |
| **SLO** | **99.5%** availability |
| **Measurement** | Prometheus `up` metric, scraped every 30s |
| **Error Budget** | 0.5% (~ 5 hours of downtime per year) |

### Error Budget Policy

- **Burn rate alert**: If >2% of the error budget is consumed in 1 hour → page on-call
- **Remediation**: Downtime must be investigated, root cause documented via postmortem
- **Overspend**: If error budget is exhausted, freeze feature deploys until budget is restored

## Phase 0 SLOs (Not Measured Yet)

Phase 0 is development-only. SLO monitoring will be activated when:
1. Prometheus/Grafana stack is deployed to production
2. At least 7 days of production traffic data exists
3. Alerting channels (email/PagerDuty) are configured

## Planned Future SLOs

| Service | SLO Target | Notes |
|---------|-----------|-------|
| API availability | 99.5% | Core API endpoints |
| Scraping freshness | 95% of sources scraped within 1h | Per-source SLO |
| Search latency | p99 < 500ms | FTS query performance |
| Notification delivery | 99% delivered within 5min | Email + in-app |