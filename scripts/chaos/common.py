"""Shared helpers for chaos experiments.

Assumes the full stack is running via ``docker compose up``. Uses the
application API + docker CLI to inject failures and verify recovery.
"""

import subprocess
import time
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api"
DOCKER_COMPOSE = ["docker", "compose"]


def docker(args: list[str], check: bool = True) -> str:
    result = subprocess.run(
        DOCKER_COMPOSE + args, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"docker compose {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def login() -> str:
    response = httpx.post(
        f"{API_BASE}/auth/login",
        json={"email": "admin@pudimjobs.dev", "password": "admin123"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def wait_for(predicate, timeout: float = 60.0, interval: float = 1.0, label: str = "condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            print(f"  ✔ {label}")
            return
        time.sleep(interval)
    raise TimeoutError(f"Timed out waiting for: {label}")


def report(name: str, ok: bool, details: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" — {details}" if details else ""))


def load_fixture(name: str) -> str:
    path = Path(__file__).parent / "fixtures" / name
    return path.read_text() if path.exists() else ""
