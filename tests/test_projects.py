"""사업 목록 슬라이스. 접근 범위가 역할에 따라 좁혀지는지 본다."""

from tests.conftest import requires_db


@requires_db
def test_projects_requires_auth(client):
    assert client.get("/api/projects").status_code == 401


@requires_db
def test_client_sees_own_org_projects(client, client_token):
    token = client_token("r2@admin.com")
    res = client.get("/api/projects", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert set(body) >= {"content", "page", "size", "totalElements", "totalPages", "hasNext"}
    for row in body["content"]:
        # 요약 지표는 전부 SQL 집계 결과다 — 절대 규칙 1.
        assert row["requiredWorkProductTotal"] == 22
        assert row["openRiskCount"] >= 0


@requires_db
def test_admin_sees_at_least_as_many_as_client(client, client_token):
    admin = client.get(
        "/api/projects", headers={"Authorization": f"Bearer {client_token('r1@admin.com')}"}
    ).json()
    cli = client.get(
        "/api/projects", headers={"Authorization": f"Bearer {client_token('r2@admin.com')}"}
    ).json()
    assert admin["totalElements"] >= cli["totalElements"]


@requires_db
def test_project_detail_returns_metrics(client, client_token):
    token = client_token("r2@admin.com")
    listed = client.get(
        "/api/projects", headers={"Authorization": f"Bearer {token}"}
    ).json()["content"]
    assert listed, "시드 사업이 있어야 한다"
    pid = listed[0]["id"]

    res = client.get(f"/api/projects/{pid}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == pid
    assert body["metrics"]["workProductTotal"] == 22  # 29110 산출물 22종
    assert set(body["metrics"]) >= {
        "requirementTotal", "issueOpen", "riskOpen", "traceabilityCoverage", "lastSyncedAt"
    }


@requires_db
def test_project_detail_denies_foreign_project(client, client_token):
    token = client_token("r2@admin.com")
    # 존재하지 않거나 접근 불가한 사업 → 403/404
    res = client.get(
        "/api/projects/00000000-0000-4000-8000-000000000000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code in (403, 404)


@requires_db
def test_search_filters_by_name(client, client_token):
    token = client_token("r1@admin.com")
    res = client.get(
        "/api/projects", params={"q": "존재하지않는사업명zzz"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["totalElements"] == 0
