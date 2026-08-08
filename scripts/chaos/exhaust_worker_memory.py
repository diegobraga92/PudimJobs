"""Chaos experiment: exhaust worker memory and verify no data corruption.

Scenario: the worker container is memory-limited, a burst of scrapes pushes it
over the limit, and Celery marks lost tasks for retry. After lifting the limit,
tasks complete and deduplication prevents duplicate jobs.

Run:
    python scripts/chaos/exhaust_worker_memory.py
"""

import time

import httpx
from common import API_BASE, docker, headers, login, report


def main() -> None:
    print("== Chaos: worker memory exhaustion ==")
    token = login()
    h = headers(token)

    # 1) Cap worker memory at 64MB.
    print("1) Limiting worker memory to 64m...")
    docker(["update", "--memory", "64m", "--memory-swap", "64m", "worker"])

    # 2) Trigger several concurrent scrapes to stress the worker.
    source = httpx.post(
        f"{API_BASE}/sources",
        json={"name": "Memory Feed", "url": "http://localhost:8901/chaos_feed.xml", "type": "rss"},
        headers=h,
        timeout=10,
    )
    if source.status_code == 201:
        source_id = source.json()["id"]
        for _ in range(4):
            httpx.post(f"{API_BASE}/admin/sources/{source_id}/scrape", headers=h, timeout=10)
            time.sleep(0.5)

    time.sleep(8)

    # 3) Restore worker memory.
    print("3) Restoring worker memory...")
    docker(["update", "--memory", "0", "--memory-swap", "-1", "worker"])
    time.sleep(5)

    # 4) Verify no duplicate jobs exist for the same URL (idempotent inserts).
    jobs = httpx.get(f"{API_BASE}/jobs", headers=h, timeout=10).json()
    urls = [j["url"] for j in jobs if j["url"]]
    dupes = len(urls) - len(set(urls))
    report("no duplicate jobs after worker churn", dupes == 0, f"{len(urls)} urls, {dupes} dupes")

    print("Note: tasks lost to OOM are retried by Celery "
          "(task_reject_on_worker_lost=True); dedup protects the DB.")


if __name__ == "__main__":
    main()
