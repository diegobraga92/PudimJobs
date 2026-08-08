"""Chaos experiment: break a normalization rule and verify the dashboard sees it.

Scenario: the company-map mapping is removed, so company normalization stops
working; completeness scores dip; the data-quality dashboard reflects the
drop. Restoring the mapping + re-assessing recovers.

Run:
    python scripts/chaos/drop_data_quality.py
"""

import time

import httpx
from common import API_BASE, headers, login, report, wait_for

MAPPING_FILE = "../../backend/app/data/company_map.json"


def main() -> None:
    print("== Chaos: data-quality normalization failure ==")
    token = login()
    h = headers(token)

    # 1) Break the mapping: point the normalizer at an empty map.
    print("1) Removing company mappings...")
    with open(MAPPING_FILE) as f:
        original = f.read()
    with open(MAPPING_FILE, "w") as f:
        f.write("{}")

    # 2) Create a job with a mapped company and assess it.
    job = httpx.post(
        f"{API_BASE}/jobs",
        json={"title": "Python Engineer", "company": "Google LLC", "description": "x" * 250, "tags": ["python"]},
        headers=h,
        timeout=10,
    )
    if job.status_code == 201:
        job_id = job.json()["id"]
        httpx.post(f"{API_BASE}/jobs/{job_id}/parse", headers=h, timeout=10)
        time.sleep(5)

    # 3) Verify quality recorded the (failed) normalization.
    jobs = httpx.get(f"{API_BASE}/admin/quality/jobs", headers=h, timeout=10).json()
    assessed = [j for j in jobs if j["normalized_company"]]
    report(
        "normalization degrades when mapping removed",
        not assessed,
        f"{len(jobs)} assessed jobs",
    )

    # 4) Restore the mapping and re-assess.
    print("2) Restoring mappings...")
    with open(MAPPING_FILE, "w") as f:
        f.write(original)

    def recovers():
        jobs_now = httpx.get(f"{API_BASE}/admin/quality/jobs", headers=h, timeout=10).json()
        return any(j["normalized_company"] == "Google" for j in jobs_now)

    try:
        wait_for(recovers, timeout=60, label="normalization recovers after mapping restore")
        report("recovery after mapping restore", True)
    except TimeoutError:
        report("recovery after mapping restore", False)


if __name__ == "__main__":
    main()
