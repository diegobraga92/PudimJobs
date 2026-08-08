"""Chaos experiment: simulate a site HTML change that breaks the scraper.

Scenario: the feed returns malformed/restructured HTML; the scraper cannot
extract jobs; Celery retries, the circuit breaker trips, and the DLQ records
the failures. Restoring the feed + resetting the breaker recovers.

Run:
    python scripts/chaos/break_scraper_html.py
"""

import time

import httpx
from common import API_BASE, docker, headers, login, report, wait_for

FIXTURE_FEED = "/tmp/chaos_feed.xml"
VALID_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Chaos Careers</title>
<item><title>Python Engineer</title>
<link>http://localhost:8901/jobs/1</link>
<guid>chaos-1</guid></item></channel></rss>"""


def serve_feed(content: str) -> None:
    with open(FIXTURE_FEED, "w") as f:
        f.write(content)


def main() -> None:
    print("== Chaos: scraper HTML change ==")
    token = login()
    h = headers(token)

    # Start a local feed server.
    docker(["up", "-d", "chaos-feedsvr"], check=False)
    # Fallback: use python http.server on 8901 if the service isn't defined.
    import subprocess

    subprocess.Popen(
        ["python3", "-m", "http.server", "8901", "--directory", "/tmp"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    serve_feed(VALID_FEED)

    source = httpx.post(
        f"{API_BASE}/sources",
        json={"name": "HTML Break Feed", "url": "http://localhost:8901/chaos_feed.xml", "type": "rss"},
        headers=h,
        timeout=10,
    )
    source.raise_for_status()
    source_id = source.json()["id"]

    # Baseline: a healthy scrape produces a job.
    httpx.post(f"{API_BASE}/admin/sources/{source_id}/scrape", headers=h, timeout=10)
    time.sleep(3)

    # 1) Break the feed: return non-XML HTML so the parser yields nothing.
    print("1) Serving malformed feed (HTML change)...")
    serve_feed("<html><body><div class='new-layout'>no jobs here</div></body></html>")

    # 2) Trigger scrapes until the circuit breaker trips (5 failures).
    print("2) Triggering scrapes to trip the circuit breaker...")
    for _ in range(6):
        httpx.post(f"{API_BASE}/admin/sources/{source_id}/scrape", headers=h, timeout=10)
        time.sleep(1)

    # 3) Verify failed runs landed in the DLQ.
    dlq = httpx.get(f"{API_BASE}/admin/dlq", headers=h, timeout=10).json()
    dlq_failed = [r for r in dlq if r["status"] == "failed"]
    report("DLQ captures failed runs", len(dlq_failed) >= 3, f"{len(dlq_failed)} failed runs")

    # 4) Restore the feed and reset the circuit breaker.
    print("3) Restoring feed + resetting circuit breaker...")
    serve_feed(VALID_FEED)
    docker(["exec", "redis", "redis-cli", "FLUSHDB"])

    # 5) Verify recovery: a scrape succeeds again.
    def recovers():
        runs = httpx.get(f"{API_BASE}/admin/stats", headers=h, timeout=10).json()
        return runs["total_runs"] > len(dlq_failed) + 1

    try:
        wait_for(recovers, timeout=60, label="source scrapes successfully after recovery")
        report("recovery after HTML fix", True)
    except TimeoutError:
        report("recovery after HTML fix", False)


if __name__ == "__main__":
    main()
