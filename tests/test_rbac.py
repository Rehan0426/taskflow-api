"""Integration tests for RBAC hierarchy (owner > admin > member), 404 vs 403, and owner invariants."""

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, register_and_login


def test_rbac_roles_404_for_outsiders_and_403_for_insufficient_role(client: TestClient) -> None:
    owner = register_and_login(client, "owner@example.com")
    admin = register_and_login(client, "admin@example.com")
    member = register_and_login(client, "member@example.com")
    outsider = register_and_login(client, "outsider@example.com")

    owner_hdr = auth_headers(str(owner["access_token"]))
    admin_hdr = auth_headers(str(admin["access_token"]))
    member_hdr = auth_headers(str(member["access_token"]))
    outsider_hdr = auth_headers(str(outsider["access_token"]))

    # Owner creates team
    team_res = client.post("/teams", json={"name": "Platform Team"}, headers=owner_hdr)
    assert team_res.status_code == 201
    team_id = team_res.json()["id"]

    # Outsider gets 404 (never 403) when accessing team or its projects
    assert client.get(f"/teams/{team_id}", headers=outsider_hdr).status_code == 404
    assert client.get(f"/teams/{team_id}/projects", headers=outsider_hdr).status_code == 404

    # Owner adds admin and member
    add_admin = client.post(
        f"/teams/{team_id}/members",
        json={"user_id": admin["user_id"], "role": "admin"},
        headers=owner_hdr,
    )
    assert add_admin.status_code == 201

    # Admin adds regular member
    add_member = client.post(
        f"/teams/{team_id}/members",
        json={"user_id": member["user_id"], "role": "member"},
        headers=admin_hdr,
    )
    assert add_member.status_code == 201

    # Member creates a project
    proj_res = client.post(
        f"/teams/{team_id}/projects",
        json={"name": "Payments Service", "description": "Core API"},
        headers=member_hdr,
    )
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    # Outsider gets 404 on project
    assert client.get(f"/projects/{project_id}", headers=outsider_hdr).status_code == 404

    # Member gets 403 when attempting to delete project, add members, or view audit logs
    assert client.delete(f"/projects/{project_id}", headers=member_hdr).status_code == 403
    assert client.get(f"/teams/{team_id}/audit-logs", headers=member_hdr).status_code == 403

    # Admin can view audit logs (200) and delete project (204), but gets 403 trying to change roles or delete team
    audit_res = client.get(f"/teams/{team_id}/audit-logs", headers=admin_hdr)
    assert audit_res.status_code == 200
    assert audit_res.json()["total"] >= 3

    role_patch_by_admin = client.patch(
        f"/teams/{team_id}/members/{member['user_id']}",
        json={"role": "admin"},
        headers=admin_hdr,
    )
    assert role_patch_by_admin.status_code == 403
    assert client.delete(f"/teams/{team_id}", headers=admin_hdr).status_code == 403

    # Owner cannot be removed or demoted
    demote_owner = client.patch(
        f"/teams/{team_id}/members/{owner['user_id']}",
        json={"role": "admin"},
        headers=owner_hdr,
    )
    assert demote_owner.status_code == 400

    remove_owner = client.delete(
        f"/teams/{team_id}/members/{owner['user_id']}",
        headers=owner_hdr,
    )
    assert remove_owner.status_code == 400

    # Admin deletes project; Owner deletes team
    assert client.delete(f"/projects/{project_id}", headers=admin_hdr).status_code == 204
    assert client.delete(f"/teams/{team_id}", headers=owner_hdr).status_code == 204
