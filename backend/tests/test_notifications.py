"""Tests for the notifications API."""

from app.models import Notification


async def test_list_notifications_with_unread_count(auth_client, db_session):
    client, user, _ = auth_client
    for i in range(2):
        db_session.add(
            Notification(
                user_id=user.id,
                channel="in_app",
                title=f"Match {i}",
                message="New job",
                status="sent",
            )
        )
    await db_session.commit()

    response = await client.get("/api/notifications")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["unread"] == 2
    assert len(body["items"]) == 2


async def test_mark_notification_read(auth_client, db_session):
    client, user, _ = auth_client
    notification = Notification(
        user_id=user.id, channel="in_app", title="Match", message="New job", status="sent"
    )
    db_session.add(notification)
    await db_session.commit()
    await db_session.refresh(notification)

    response = await client.post(f"/api/notifications/{notification.id}/read")
    assert response.status_code == 200
    assert response.json()["read"] is True

    listed = await client.get("/api/notifications")
    assert listed.json()["unread"] == 0


async def test_mark_all_read(auth_client, db_session):
    client, user, _ = auth_client
    for _ in range(3):
        db_session.add(
            Notification(user_id=user.id, channel="in_app", title="x", status="sent")
        )
    await db_session.commit()

    await client.post("/api/notifications/read-all")
    listed = await client.get("/api/notifications")
    assert listed.json()["unread"] == 0


async def test_notifications_require_auth(client):
    assert (await client.get("/api/notifications")).status_code == 401
