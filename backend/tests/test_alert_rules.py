"""Tests for the alert rules API."""


async def test_create_and_list_rules(auth_client):
    client, _, _ = auth_client
    created = await client.post(
        "/api/alert-rules",
        json={"name": "Python jobs", "keywords": ["python", "fastapi"], "channels": ["in_app"]},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["keywords"] == ["python", "fastapi"]
    assert body["active"] is True

    listed = await client.get("/api/alert-rules")
    assert len(listed.json()) == 1


async def test_update_and_delete_rule(auth_client):
    client, _, _ = auth_client
    created = await client.post(
        "/api/alert-rules", json={"name": "AWS", "keywords": ["aws"]}
    )
    rule_id = created.json()["id"]

    updated = await client.put(
        f"/api/alert-rules/{rule_id}", json={"keywords": ["aws", "docker"], "active": False}
    )
    assert updated.status_code == 200
    assert updated.json()["keywords"] == ["aws", "docker"]
    assert updated.json()["active"] is False

    deleted = await client.delete(f"/api/alert-rules/{rule_id}")
    assert deleted.status_code == 204
    assert (await client.get("/api/alert-rules")).json() == []


async def test_alert_rules_require_auth(client):
    assert (await client.get("/api/alert-rules")).status_code == 401
