"""Tests for the bulk source import API and ``scripts/import_sources.py``."""

import json

import httpx
import pytest
from scripts import import_sources
from scripts.import_sources import load_catalog

from app.main import app

CATALOG = [
    {
        "name": "Acme greenhouse",
        "url": "https://acme.example/jobs",
        "type": "discovery",
        "config": {"provider": "greenhouse", "board_token": "acme"},
    },
    {"name": "Acme feed", "url": "https://acme.example/feed.xml", "type": "rss"},
]


def test_load_catalog_accepts_an_array_or_an_object(tmp_path):
    array_file = tmp_path / "array.json"
    array_file.write_text(json.dumps(CATALOG))
    assert load_catalog(array_file) == CATALOG

    object_file = tmp_path / "object.json"
    object_file.write_text(json.dumps({"sources": CATALOG}))
    assert load_catalog(object_file) == CATALOG


def test_load_catalog_rejects_bad_input(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text("[]")
    with pytest.raises(ValueError, match="non-empty"):
        load_catalog(empty)

    incomplete = tmp_path / "incomplete.json"
    incomplete.write_text(json.dumps([{"name": "No URL", "type": "rss"}]))
    with pytest.raises(ValueError, match="missing: url"):
        load_catalog(incomplete)

    not_objects = tmp_path / "strings.json"
    not_objects.write_text(json.dumps(["nope"]))
    with pytest.raises(ValueError, match="not an object"):
        load_catalog(not_objects)


async def test_import_creates_sources_and_skips_duplicates(auth_client):
    client, _, _ = auth_client

    first = await client.post("/api/sources/import", json={"sources": CATALOG})
    assert first.status_code == 200
    body = first.json()
    assert (body["created"], body["skipped"], body["invalid"]) == (2, 0, 0)
    assert {item["status"] for item in body["results"]} == {"created"}
    assert all(item["source_id"] for item in body["results"])

    # Re-running the same catalog is a no-op (matched on url + type).
    again = await client.post("/api/sources/import", json={"sources": CATALOG})
    assert again.json()["created"] == 0
    assert again.json()["skipped"] == 2
    assert len((await client.get("/api/sources")).json()) == 2


async def test_import_dry_run_writes_nothing(auth_client):
    client, _, _ = auth_client
    response = await client.post("/api/sources/import", json={"sources": CATALOG, "dry_run": True})
    body = response.json()
    assert body["created"] == 2
    assert all(item["reason"] == "dry run" for item in body["results"])
    assert all(item["source_id"] is None for item in body["results"])
    assert (await client.get("/api/sources")).json() == []


async def test_import_reports_invalid_entries(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/sources/import",
        json={
            "sources": [
                {
                    "name": "Bad discovery",
                    "url": "https://x.example",
                    "type": "discovery",
                    "config": {},
                },
                {"name": "Fine feed", "url": "https://x.example/feed", "type": "rss"},
            ]
        },
    )
    body = response.json()
    assert (body["created"], body["invalid"]) == (1, 1)
    invalid = next(item for item in body["results"] if item["status"] == "invalid")
    assert "provider" in invalid["reason"]


async def test_import_script_works_against_the_api(auth_client, monkeypatch):
    """``scripts/import_sources.py`` posts to the real endpoint surface."""
    client, _, token = auth_client
    transport = httpx.ASGITransport(app=app)
    real_client = httpx.AsyncClient

    def _client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(import_sources.httpx, "AsyncClient", _client_factory)

    report = await import_sources.import_catalog("http://test", token, CATALOG)

    assert report["created"] == 2
    assert len((await client.get("/api/sources")).json()) == 2
