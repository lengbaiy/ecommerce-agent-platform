from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.security import Principal, decode_jwt_principal
from app.db.models import Base
from app.db.session import build_engine
from app.domain import AgentTask, TaskCreate
from app.main import app
from app.repositories import InMemoryTaskRepository, SQLAlchemyTaskRepository
from app.services import TaskService


def login(
    client: TestClient,
    username: str = "admin",
    password: str = "TestAdmin@123456",
) -> dict[str, str]:
    captcha = client.post("/api/v1/auth/captcha").json()
    assert captcha["provider"] == "local_puzzle"
    assert captcha["canvas_width"] == 350
    response = client.post(
        "/api/v1/auth/login",
        json={
            "tenant_id": "local",
            "username": username,
            "password": password,
            "captcha_id": captcha["captcha_id"],
            "slider_position": captcha["puzzle_offset"],
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_login_requires_verified_slider_captcha() -> None:
    client = TestClient(app)
    with client:
        captcha = client.post("/api/v1/auth/captcha").json()
        denied = client.post(
            "/api/v1/auth/login",
            json={
                "tenant_id": "local",
                "username": "admin",
                "password": "TestAdmin@123456",
                "captcha_id": captcha["captcha_id"],
            },
        )
        assert denied.status_code == 401

        failed = client.post(
            "/api/v1/auth/login",
            json={
                "tenant_id": "local",
                "username": "admin",
                "password": "TestAdmin@123456",
                "captcha_id": captcha["captcha_id"],
                "slider_position": captcha["puzzle_offset"] + 5,
            },
        )
        assert failed.status_code == 401


def test_login_session_permissions_and_logout() -> None:
    client = TestClient(app)
    with client:
        headers = login(client)
        me = client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200
        assert "user:write" in me.json()["permissions"]

        created = client.post(
            "/api/v1/agent/tasks",
            headers=headers,
            json={
                "tenant_id": "spoofed-tenant",
                "user_id": "spoofed-user",
                "user_query": "验证任务身份只能来自登录会话",
            },
        )
        assert created.status_code == 201
        assert created.json()["request"]["tenant_id"] == "local"
        assert created.json()["request"]["user_id"] == me.json()["user_id"]

        logout = client.post("/api/v1/auth/logout", headers=headers)
        assert logout.status_code == 204
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_user_management_is_tenant_scoped_and_role_validated() -> None:
    client = TestClient(app)
    with client:
        headers = login(client)
        created = client.post(
            "/api/v1/auth/users",
            headers=headers,
            json={
                "username": "operator-a",
                "display_name": "运营人员 A",
                "password": "Operator@123456",
                "roles": ["operator"],
            },
        )
        assert created.status_code == 201
        assert created.json()["tenant_id"] == "local"
        assert "task:create" in created.json()["permissions"]

        invalid = client.post(
            "/api/v1/auth/users",
            headers=headers,
            json={
                "username": "bad-role",
                "display_name": "错误角色",
                "password": "Operator@123456",
                "roles": ["superuser"],
            },
        )
        assert invalid.status_code == 409

        operator_headers = login(client, "operator-a", "Operator@123456")
        assert client.get("/api/v1/auth/me", headers=operator_headers).status_code == 200
        assert client.get("/api/v1/auth/users", headers=operator_headers).status_code == 403

        updated = client.patch(
            f"/api/v1/auth/users/{created.json()['id']}",
            headers=headers,
            json={"roles": ["approver"]},
        )
        assert updated.status_code == 200
        assert "approval:decide" in updated.json()["permissions"]
        assert client.get("/api/v1/auth/me", headers=operator_headers).status_code == 401

        admin_id = client.get("/api/v1/auth/me", headers=headers).json()["user_id"]
        self_disable = client.patch(
            f"/api/v1/auth/users/{admin_id}",
            headers=headers,
            json={"enabled": False},
        )
        assert self_disable.status_code == 422


def test_api_requires_an_authenticated_session() -> None:
    response = TestClient(app).get("/api/v1/agent/tasks")
    assert response.status_code == 401


def test_sql_repository_persists_and_is_tenant_scoped(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'tasks.db').as_posix()}"
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    principal = Principal(tenant_id="persistent-tenant", user_id="operator-001")
    task = AgentTask(
        request=TaskCreate(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            user_query="验证 SQL 仓库持久化",
        )
    )
    repository = SQLAlchemyTaskRepository(factory)
    repository.add(task)

    assert SQLAlchemyTaskRepository(factory).get(str(task.id), principal.tenant_id).id == task.id
    with pytest.raises(KeyError):
        repository.get(str(task.id), "another-tenant")
    engine.dispose()


def test_approval_rejects_result_changed_after_snapshot() -> None:
    repository = InMemoryTaskRepository()
    service = TaskService(repository=repository)
    operator = Principal(tenant_id="snapshot-tenant", user_id="operator-001")
    approver = Principal(tenant_id="snapshot-tenant", user_id="approver-001")
    task = service.create(
        TaskCreate(user_query="生成必须经过审批的 Listing", intent="listing_generation"),
        operator,
    )
    stored = repository.get(str(task.id), operator.tenant_id)
    assert stored.result is not None
    stored.result.summary = "tampered after snapshot"
    repository.save(stored)

    with pytest.raises(ValueError, match="approved result hash mismatch"):
        service.approve(str(task.id), approver)


def test_worker_execution_mode_leaves_a_claimable_task() -> None:
    repository = InMemoryTaskRepository()
    service = TaskService(repository=repository, execution_mode="worker")
    principal = Principal(tenant_id="worker-tenant", user_id="operator-001")
    created = service.create(TaskCreate(user_query="验证异步任务执行器边界"), principal)
    completed = service.run_next()

    assert created.status == "PENDING"
    assert completed is not None
    assert completed.status == "COMPLETED"


def test_jwt_identity_uses_signed_tenant_and_role_claims() -> None:
    configuration = Settings(
        auth_mode="jwt",
        jwt_secret="test-only-secret-with-at-least-32-bytes",
        jwt_issuer="https://identity.test/",
        jwt_audience="ecommerce-agent-api",
    )
    token = jwt.encode(
        {
            "sub": "approver-007",
            "tenant_id": "tenant-jwt",
            "roles": ["approver"],
            "jti": "session-001",
            "iss": configuration.jwt_issuer,
            "aud": configuration.jwt_audience,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        configuration.jwt_secret,
        algorithm=configuration.jwt_algorithm,
    )
    principal = decode_jwt_principal(token, configuration)
    assert principal.tenant_id == "tenant-jwt"
    assert principal.has_permission("approval:decide")


def test_production_rejects_default_credentials() -> None:
    configuration = Settings(
        environment="production",
        auto_create_schema=False,
        jwt_secret="local-development-session-secret-change-before-production",
        bootstrap_admin_password="Admin@123456",
    )
    with pytest.raises(RuntimeError, match="development JWT secret"):
        configuration.validate()
