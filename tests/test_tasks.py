"""Integration tests for tasks (filtering, sorting, pagination, assignee rules) and comments."""

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, register_and_login


def test_task_lifecycle_filtering_pagination_and_comments(client: TestClient) -> None:
    owner = register_and_login(client, "lead@example.com")
    dev = register_and_login(client, "dev@example.com")
    outsider = register_and_login(client, "stranger@example.com")

    owner_hdr = auth_headers(str(owner["access_token"]))
    dev_hdr = auth_headers(str(dev["access_token"]))

    team_id = client.post("/teams", json={"name": "Backend Team"}, headers=owner_hdr).json()["id"]
    client.post(
        f"/teams/{team_id}/members",
        json={"user_id": dev["user_id"], "role": "member"},
        headers=owner_hdr,
    )
    project_id = client.post(
        f"/teams/{team_id}/projects",
        json={"name": "Q4 Roadmap"},
        headers=owner_hdr,
    ).json()["id"]

    # Assigning a task to a non-team-member must fail with 400
    bad_assign = client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Fix bug", "assignee_id": outsider["user_id"]},
        headers=owner_hdr,
    )
    assert bad_assign.status_code == 400

    # Create 3 tasks with varying status, priority, and due dates
    t1 = client.post(
        f"/projects/{project_id}/tasks",
        json={
            "title": "Setup Alembic",
            "status": "done",
            "priority": "high",
            "assignee_id": dev["user_id"],
            "due_date": "2026-11-05T10:00:00Z",
        },
        headers=owner_hdr,
    ).json()
    t2 = client.post(
        f"/projects/{project_id}/tasks",
        json={
            "title": "Write RBAC deps",
            "status": "in_progress",
            "priority": "high",
            "assignee_id": dev["user_id"],
            "due_date": "2026-11-10T10:00:00Z",
        },
        headers=dev_hdr,
    ).json()
    client.post(
        f"/projects/{project_id}/tasks",
        json={
            "title": "Polish README",
            "status": "todo",
            "priority": "low",
            "due_date": "2026-12-01T10:00:00Z",
        },
        headers=dev_hdr,
    )

    # Filter by priority=high and assignee=dev
    filtered = client.get(
        f"/projects/{project_id}/tasks",
        params={"priority": "high", "assignee": dev["user_id"], "limit": 1, "offset": 0},
        headers=dev_hdr,
    )
    assert filtered.status_code == 200
    envelope = filtered.json()
    assert envelope["total"] == 2
    assert envelope["limit"] == 1
    assert envelope["offset"] == 0
    assert len(envelope["items"]) == 1

    # Filter by due_before
    due_res = client.get(
        f"/projects/{project_id}/tasks",
        params={"due_before": "2026-11-06T00:00:00Z"},
        headers=dev_hdr,
    )
    assert due_res.json()["total"] == 1
    assert due_res.json()["items"][0]["id"] == t1["id"]

    # Comments: dev creates a comment on t2
    c_res = client.post(
        f"/tasks/{t2['id']}/comments",
        json={"text": "Working on the dependency factory now."},
        headers=dev_hdr,
    )
    assert c_res.status_code == 201
    comment_id = c_res.json()["id"]

    # Owner cannot edit dev's comment (author-only edit rule -> 403)
    edit_by_other = client.patch(
        f"/comments/{comment_id}",
        json={"text": "Edited by owner"},
        headers=owner_hdr,
    )
    assert edit_by_other.status_code == 403

    # Dev can edit their own comment
    edit_by_author = client.patch(
        f"/comments/{comment_id}",
        json={"text": "Updated: finished dependency factory."},
        headers=dev_hdr,
    )
    assert edit_by_author.status_code == 200

    # Owner (admin+) can delete dev's comment
    del_by_owner = client.delete(f"/comments/{comment_id}", headers=owner_hdr)
    assert del_by_owner.status_code == 204
