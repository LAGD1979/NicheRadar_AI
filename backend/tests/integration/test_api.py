from fastapi.testclient import TestClient


def test_health_live_and_ready(client: TestClient) -> None:
    assert client.get("/health/live").status_code == 200
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


def test_config_public_is_demo_and_restricted(client: TestClient) -> None:
    body = client.get("/api/v1/config/public").json()
    assert body["synthetic_banner"] is True
    assert body["compliance_mode"] == "restricted"
    assert body["advanced_analytics_enabled"] is False
    assert body["target_language"] == "es"


def test_list_opportunities_paginates_and_reports_total(client: TestClient) -> None:
    body = client.get("/api/v1/opportunities", params={"page_size": 3}).json()
    assert body["total"] == 8
    assert len(body["items"]) == 3
    assert body["page"] == 1


def test_opportunity_without_evaluation_has_null_fields(client: TestClient) -> None:
    # Una oportunidad sin evaluación no se presenta como 0 ni como descartada.
    body = client.get("/api/v1/opportunities", params={"q": "Historia", "page_size": 100}).json()
    unevaluated = [i for i in body["items"] if i["id"] == "syn-opp-06"]
    assert len(unevaluated) == 1
    assert unevaluated[0]["saturation_es"] is None
    assert unevaluated[0]["confidence"] is None
    assert unevaluated[0]["data_source"] == "SIN_EVALUACION"


def test_filter_by_spanish_saturation(client: TestClient) -> None:
    body = client.get("/api/v1/opportunities", params={"saturation_es": "LOW"}).json()
    assert [i["id"] for i in body["items"]] == ["syn-opp-01"]


def test_filter_by_faceless_state(client: TestClient) -> None:
    body = client.get("/api/v1/opportunities", params={"faceless_state": "NOT_FACELESS"}).json()
    assert {i["id"] for i in body["items"]} == {"syn-opp-03", "syn-opp-05"}


def test_invalid_sort_is_problem_json(client: TestClient) -> None:
    response = client.get("/api/v1/opportunities", params={"sort": "; DROP TABLE niches"})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "INVALID_SORT"


def test_sql_metacharacters_in_search_are_plain_text(client: TestClient) -> None:
    response = client.get("/api/v1/opportunities", params={"q": "%'; DROP TABLE niches; --"})
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_detail_marks_scores_as_restricted_not_zero(client: TestClient) -> None:
    body = client.get("/api/v1/opportunities/syn-opp-01").json()
    assert body["evaluation"]["scores"]["integrated"]["value"] is None
    assert body["evaluation"]["scores"]["integrated"]["state"] == "RESTRICTED"
    assert body["evaluation"]["scores"]["integrated"]["reason"]


def test_detail_includes_expired_evidence_flagged(client: TestClient) -> None:
    body = client.get("/api/v1/opportunities/syn-opp-01").json()
    states = {e["id"]: e["availability"] for e in body["evidence"]}
    assert states["syn-ev-04"] == "EXPIRED"


def test_scores_endpoint_is_forbidden_in_restricted_mode(client: TestClient) -> None:
    # T17: sin bypass por frontend ni por variable de entorno.
    response = client.get("/api/v1/opportunities/syn-opp-01/scores")
    assert response.status_code == 403
    assert response.json()["code"] == "POLICY_RESTRICTED"


def test_missing_opportunity_is_404_problem(client: TestClient) -> None:
    response = client.get("/api/v1/opportunities/no-existe")
    assert response.status_code == 404
    assert response.json()["code"] == "OPPORTUNITY_NOT_FOUND"


def test_compare_rejects_one_item(client: TestClient) -> None:
    response = client.post("/api/v1/compare", json={"opportunity_ids": ["syn-opp-01"]})
    assert response.status_code == 422


def test_compare_rejects_nine_items(client: TestClient) -> None:
    ids = [f"syn-opp-0{i}" for i in range(1, 9)] + ["syn-opp-01"]
    response = client.post("/api/v1/compare", json={"opportunity_ids": ids})
    assert response.status_code == 422


def test_compare_rejects_duplicates(client: TestClient) -> None:
    response = client.post(
        "/api/v1/compare", json={"opportunity_ids": ["syn-opp-01", "syn-opp-01"]}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "DUPLICATE_OPPORTUNITY"


def test_compare_eight_items_keeps_nulls_and_restrictions(client: TestClient) -> None:
    # T23: ocho elementos, cada celda con estado, y nulos sin convertir en cero.
    ids = [f"syn-opp-0{i}" for i in range(1, 9)]
    body = client.post("/api/v1/compare", json={"opportunity_ids": ids}).json()
    assert len(body["items"]) == 8
    field_keys = {f["key"] for f in body["fields"]}
    for item in body["items"]:
        assert set(item["values"]) == field_keys
    no_eval = next(i for i in body["items"] if i["id"] == "syn-opp-06")
    assert no_eval["values"]["spanish.saturation_state"]["state"] == "NOT_AVAILABLE"
    assert no_eval["values"]["spanish.saturation_state"]["value"] is None
    first = body["items"][0]
    assert first["values"]["scores.integrated"]["state"] == "RESTRICTED"
    assert first["values"]["scores.integrated"]["value"] is None


def test_videos_endpoint_filters_language_conflict(client: TestClient) -> None:
    body = client.get("/api/v1/videos", params={"language_state": "UNKNOWN"}).json()
    assert [v["youtube_video_id"] for v in body["items"]] == ["SYNV17"]
    assert body["items"][0]["language_confidence"] == "CONFLICT"


def test_videos_hidden_subscribers_show_unknown_band(client: TestClient) -> None:
    body = client.get("/api/v1/videos", params={"q": "Épsilon"}).json()
    assert body["items"]
    assert all(v["subscriber_band"] == "UNKNOWN" for v in body["items"])


def test_providers_never_expose_secret_values(client: TestClient) -> None:
    text = client.get("/api/v1/providers").text + client.get("/api/v1/config/public").text
    assert "AIza" not in text
    assert "sk-" not in text
