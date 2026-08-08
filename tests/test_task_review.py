"""Focused persistence and integration tests for the bounty Task Review feature."""


def test_seeded_completed_task_and_filters(client):
    response = client.get("/api/task-review/tasks")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 3
    sample = next(item for item in payload["data"] if item["id"] == "task-whatsapp-001")
    assert {key: sample["completion"][key] for key in ("complete", "total", "percent")} == {"complete": 4, "total": 4, "percent": 100}
    assert sample["ready"] is True

    filtered = client.get("/api/task-review/tasks", params={"search": "Vansh Cu", "status": "Ready"})
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["data"]] == ["task-whatsapp-001"]

    missing = client.get("/api/task-review/tasks", params={"missing_data": "true"})
    assert missing.status_code == 200
    assert all(item["missing_required"] for item in missing.json()["data"])


def test_checklist_update_persists_and_packet_uses_selected_task(client):
    detail = client.get("/api/task-review/tasks/task-instagram-002")
    assert detail.status_code == 200
    task = detail.json()
    section = next(item for item in task["sections"] if item["name"] == "Inputs & sources")

    update = client.patch(
        f"/api/task-review/tasks/task-instagram-002/sections/{section['id']}",
        json={"status": "complete", "source": "Connected test phone", "notes": "Persisted review update."},
    )
    assert update.status_code == 200
    assert update.json()["completion"]["complete"] == 2

    refreshed = client.get("/api/task-review/tasks/task-instagram-002").json()
    saved = next(item for item in refreshed["sections"] if item["id"] == section["id"])
    assert saved["status"] == "complete"
    assert saved["source"] == "Connected test phone"
    assert refreshed["ready"] is False

    note = client.patch("/api/task-review/tasks/task-instagram-002", json={"notes": "Judge note"})
    assert note.status_code == 200
    packet = client.get("/api/task-review/tasks/task-instagram-002/packet")
    assert packet.status_code == 200
    assert packet.headers["content-type"].startswith("text/markdown")
    assert "Judge note" in packet.text
    assert "Generated Steps" not in packet.text  # packet is scoped to the selected task's real sections
    assert "Like the first Instagram post" in packet.text


def test_gmail_oauth_surface_is_isolated_and_requires_connection(client):
    status = client.get("/api/gmail/status")
    assert status.status_code == 200
    assert set(status.json()) == {"configured", "connected", "email"}

    send = client.post("/api/gmail/send", json={"to": "person@example.com", "subject": "Test", "body": "Hello"})
    assert send.status_code == 401
    assert "Connect a Google account" in send.json()["detail"]


def test_task_review_filters_and_selected_packet_isolation(client):
    generated = client.get("/api/task-review/tasks", params={"search": "locate the first post"}).json()["data"]
    assert [item["id"] for item in generated] == ["task-instagram-002"]

    source = client.get("/api/task-review/tasks", params={"search": "Phone + WhatsApp contact"}).json()["data"]
    assert [item["id"] for item in source] == ["task-whatsapp-001"]

    assert {item["id"] for item in client.get("/api/task-review/tasks", params={"section": "Goal & scope"}).json()["data"]} == {
        "task-instagram-002", "task-settings-003", "task-whatsapp-001"
    }
    assert [item["id"] for item in client.get("/api/task-review/tasks", params={"owner": "Growth Ops"}).json()["data"]] == ["task-instagram-002"]
    assert [item["id"] for item in client.get("/api/task-review/tasks", params={"agent": "Settings Explorer"}).json()["data"]] == ["task-settings-003"]
    assert [item["id"] for item in client.get("/api/task-review/tasks", params={"missing_data": "false"}).json()["data"]] == ["task-whatsapp-001"]
    combined = client.get("/api/task-review/tasks", params={"search": "Instagram", "status": "In review", "owner": "Growth Ops", "agent": "Ghost Android Agent", "missing_data": "true"}).json()["data"]
    assert [item["id"] for item in combined] == ["task-instagram-002"]
    assert client.get("/api/task-review/tasks", params={"search": "does-not-exist"}).json()["data"] == []

    for task_id, note in (("task-whatsapp-001", "WhatsApp-only note"), ("task-instagram-002", "Instagram-only note")):
        response = client.patch(f"/api/task-review/tasks/{task_id}", json={"notes": note})
        assert response.status_code == 200
    whatsapp_packet = client.get("/api/task-review/tasks/task-whatsapp-001/packet").text
    instagram_packet = client.get("/api/task-review/tasks/task-instagram-002/packet").text
    assert "WhatsApp-only note" in whatsapp_packet and "Instagram-only note" not in whatsapp_packet
    assert "Instagram-only note" in instagram_packet and "WhatsApp-only note" not in instagram_packet
    assert "Generated sections: 4" in whatsapp_packet
    assert "Validation warnings: 0" in whatsapp_packet
    for packet in (whatsapp_packet, instagram_packet):
        assert "undefined" not in packet.lower()
        assert "[object object]" not in packet.lower()
