"""Chaos experiment: kill RabbitMQ and verify the queue survives.

Scenario: messages published while the broker is down should be buffered by
the durable queue and processed after recovery.

Requires the full ``docker compose up`` stack. Run:
    python scripts/chaos/kill_rabbitmq.py
"""

import time

import httpx
from common import API_BASE, docker, headers, login, report, wait_for


def main() -> None:
    print("== Chaos: RabbitMQ outage ==")
    token = login()
    h = headers(token)

    # Create an alert rule + feed source so a scrape emits a job.new event.
    rule = httpx.post(
        f"{API_BASE}/alert-rules",
        json={"name": "Chaos python", "keywords": ["python"], "channels": ["in_app"]},
        headers=h,
        timeout=10,
    )
    rule.raise_for_status()

    source = httpx.post(
        f"{API_BASE}/sources",
        json={"name": "Chaos Feed", "url": "http://host.docker.internal:8901/jobs.xml", "type": "rss"},
        headers=h,
        timeout=10,
    )
    source.raise_for_status()
    source_id = source.json()["id"]

    # 1) Kill RabbitMQ.
    print("1) Stopping rabbitmq...")
    docker(["stop", "rabbitmq"])

    # 2) Trigger a scrape while the broker is down.
    print("2) Triggering scrape while broker is down...")
    httpx.post(
        f"{API_BASE}/admin/sources/{source_id}/scrape", headers=h, timeout=10
    ).raise_for_status()
    time.sleep(3)

    # 3) Restore RabbitMQ.
    print("3) Restarting rabbitmq...")
    docker(["start", "rabbitmq"])

    # 4) Verify the worker eventually picks up the scrape (broker recovered).
    def scrape_done():
        resp = httpx.get(f"{API_BASE}/admin/stats", headers=h, timeout=10)
        return resp.status_code == 200 and resp.json()["total_runs"] >= 1

    try:
        wait_for(scrape_done, timeout=90, label="scrape executed after broker recovery")
        report("queue persists + worker recovers", True)
    except TimeoutError:
        report("queue persists + worker recovers", False, "scrape not processed in time")


if __name__ == "__main__":
    main()
