"""Concurrent load test for the PudimJobs API.

Simulates concurrent scrape triggers and search requests, reporting
p50/p95/p99 latency, throughput, and error rate. Usage::

    python scripts/load_test.py --base-url http://localhost:8000 \\
        --token <JWT> --search-concurrency 50 --search-requests 500
"""

import argparse
import asyncio
import statistics
import time

import httpx


async def _timed_request(client: httpx.AsyncClient, method: str, url: str, **kwargs):
    start = time.perf_counter()
    try:
        response = await client.request(method, url, **kwargs)
        status = response.status_code
    except httpx.HTTPError:
        status = 0
    return status, time.perf_counter() - start


async def _worker(client, queue: asyncio.Queue, results: list, counter: dict):
    while True:
        try:
            method, url, kwargs = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        status, elapsed = await _timed_request(client, method, url, **kwargs)
        results.append(elapsed)
        counter["requests"] += 1
        if status and 200 <= status < 300:
            counter["ok"] += 1
        else:
            counter["errors"] += 1
        queue.task_done()


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = min(len(values) - 1, int(len(values) * p))
    return values[index]


async def _run(base_url: str, token: str, search_concurrency: int, search_requests: int, scrape_concurrency: int):
    headers = {"Authorization": f"Bearer {token}"}
    counter = {"requests": 0, "ok": 0, "errors": 0}
    queue: asyncio.Queue = asyncio.Queue()
    results: list[float] = []

    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30) as client:
        # Seed search requests.
        for _ in range(search_requests):
            queue.put_nowait(("GET", "/api/jobs", {"params": {"q": "python backend", "limit": "20"}}))

        # Seed scrape triggers (only if a source id is reachable; we just enqueue).
        scrape_ok = await client.get("/api/admin/sources")
        if scrape_ok.status_code == 200:
            sources = scrape_ok.json()
            for source in sources[:scrape_concurrency]:
                queue.put_nowait(("POST", f"/api/admin/sources/{source['id']}/scrape", {}))

        start = time.perf_counter()
        workers = [
            asyncio.create_task(_worker(client, queue, results, counter))
            for _ in range(search_concurrency)
        ]
        await queue.join()
        for worker in workers:
            worker.cancel()
        elapsed = time.perf_counter() - start

    print("=" * 60)
    print("Load test results")
    print("=" * 60)
    print(f"requests:      {counter['requests']}")
    print(f"ok:            {counter['ok']}  errors: {counter['errors']}")
    print(f"throughput:    {counter['requests'] / elapsed:.1f} req/s")
    print(f"p50:           {_percentile(results, 0.50) * 1000:.1f} ms")
    print(f"p95:           {_percentile(results, 0.95) * 1000:.1f} ms")
    print(f"p99:           {_percentile(results, 0.99) * 1000:.1f} ms")
    print(f"mean:          {statistics.mean(results) * 1000:.1f} ms" if results else "mean: n/a")


def main() -> None:
    parser = argparse.ArgumentParser(description="PudimJobs load test")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", required=True, help="JWT access token")
    parser.add_argument("--search-concurrency", type=int, default=20)
    parser.add_argument("--search-requests", type=int, default=200)
    parser.add_argument("--scrape-concurrency", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(
        _run(
            args.base_url,
            args.token,
            args.search_concurrency,
            args.search_requests,
            args.scrape_concurrency,
        )
    )


if __name__ == "__main__":
    main()
