import pytest
from fastapi.testclient import TestClient

from app.core.security import get_current_principal, permissions_for_roles
from app.main import app
from app.tools.contracts import ProfitInput, calculate_profit


def principal_override():
    from app.core.security import Principal

    roles = frozenset({"operator", "approver"})
    return Principal(
        tenant_id="demo",
        user_id="operator-001",
        username="operator-001",
        roles=roles,
        permissions=permissions_for_roles(roles),
    )


@pytest.fixture(autouse=True)
def authenticated_principal():
    app.dependency_overrides[get_current_principal] = principal_override
    yield
    app.dependency_overrides.pop(get_current_principal, None)


def test_market_entry_completes_with_evidence() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/agent/tasks",
        json={
            "tenant_id": "demo",
            "user_id": "operator-001",
            "user_query": "分析便携咖啡机在 US 市场是否值得进入",
            "intent": "market_entry",
            "constraints": {"minimum_margin": 0.3},
        },
    )
    assert response.status_code == 201
    task = response.json()
    assert task["status"] == "COMPLETED"
    assert task["result"]["evidence_refs"][0]["grade"] == "D"
    assert "supervisor:routed_to:market_intelligence" in task["events"]


def test_listing_requires_approval_before_completion() -> None:
    client = TestClient(app)
    created = client.post(
        "/api/v1/agent/tasks",
        json={
            "tenant_id": "demo",
            "user_query": "为便携咖啡机生成 Amazon US Listing",
            "intent": "listing_generation",
            "business_context": {"sku": "COFFEE-001", "platform": "amazon"},
        },
    )
    assert created.status_code == 201
    task = created.json()
    assert task["status"] == "WAITING_APPROVAL"
    assert task["approval_status"] == "WAITING_APPROVAL"
    approved = client.post(f"/api/v1/approvals/{task['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "COMPLETED"
    assert approved.json()["approval_status"] == "APPROVED"


def test_task_events_are_sse() -> None:
    client = TestClient(app)
    created = client.post(
        "/api/v1/agent/tasks",
        json={
            "tenant_id": "demo",
            "user_query": "诊断本周店铺转化率下降原因",
            "intent": "operations_diagnosis",
        },
    ).json()
    response = client.get(f"/api/v1/agent/tasks/{created['id']}/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: task-update" in response.text


def test_profit_calculator_is_deterministic() -> None:
    result = calculate_profit(
        ProfitInput(
            price=100,
            product_cost=35,
            platform_fee=15,
            logistics_cost=10,
            advertising_cost=10,
        )
    )
    assert result == {"revenue": 100, "total_cost": 70, "profit": 30, "margin": 0.3}


def test_openapi_contains_prd_contracts() -> None:
    paths = TestClient(app).get("/openapi.json").json()["paths"]
    expected = {
        "/api/v1/agent/tasks",
        "/api/v1/agent/tasks/{task_id}",
        "/api/v1/agent/tasks/{task_id}/events",
        "/api/v1/agent/tasks/{task_id}/cancel",
        "/api/v1/approvals/{task_id}/approve",
        "/api/v1/approvals/{task_id}/reject",
        "/api/v1/products",
        "/api/v1/analytics/market",
        "/api/v1/analytics/operations",
        "/api/v1/knowledge/search",
    }
    assert expected <= set(paths)
