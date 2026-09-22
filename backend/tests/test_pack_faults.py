"""装袋失败响应的统一形状：{"fault", "detail", "at"}，at ∈ {route, stop, pack}。

钉住三类 fault 及其 at：
- route_not_found → at=route（路线找不到）
- invalid_stop    → at=stop（订户点字段不合法）
- pack_rejected   → at=pack（装袋过程业务拒绝）
同类失败连续两次，fault 与 at 必须相同；成功写袋/拒收的路径语义不变。
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import DeliveryRoute, PackBag, RejectRecord, SubscriberStop

FAULT_KEYS = {"fault", "detail", "at"}


@pytest.fixture()
def env():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        # 不作为上下文管理器使用：不触发 lifespan（避免连真实库/种子数据）
        yield TestClient(app), Session
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def seed_route(Session, stops, max_weight=8.0, max_volume=18.0, name="测试线"):
    with Session() as db:
        route = DeliveryRoute(name=name, max_weight_kg=max_weight, max_volume_l=max_volume)
        db.add(route)
        db.flush()
        for seq, (stop_name, weight, volume) in enumerate(stops, start=1):
            db.add(
                SubscriberStop(
                    route_id=route.id, seq=seq, name=stop_name,
                    weight_kg=weight, volume_l=volume,
                )
            )
        db.commit()
        return route.id


def test_route_not_found_fault(env):
    client, _ = env
    r1 = client.post("/api/pack", json={"route_id": 999})
    assert r1.status_code == 404
    body = r1.json()
    assert set(body) == FAULT_KEYS
    assert body["fault"] == "route_not_found"
    assert body["at"] == "route"
    assert body["detail"]

    r2 = client.post("/api/pack", json={"route_id": 999})
    assert r2.status_code == 404
    assert set(r2.json()) == FAULT_KEYS
    assert r2.json()["fault"] == body["fault"]
    assert r2.json()["at"] == body["at"]


def test_invalid_stop_fault(env):
    client, Session = env
    rid = seed_route(Session, stops=[("坏点", -1.0, 2.0), ("好点", 1.0, 1.0)])
    r1 = client.post("/api/pack", json={"route_id": rid})
    assert r1.status_code == 422
    body = r1.json()
    assert set(body) == FAULT_KEYS
    assert body["fault"] == "invalid_stop"
    assert body["at"] == "stop"
    assert "坏点" in body["detail"]

    r2 = client.post("/api/pack", json={"route_id": rid})
    assert r2.status_code == 422
    assert r2.json()["fault"] == body["fault"]
    assert r2.json()["at"] == body["at"]

    # 失败不得产生任何袋/拒收残留
    with Session() as db:
        assert db.scalars(select(PackBag)).all() == []
        assert db.scalars(select(RejectRecord)).all() == []


def test_pack_rejected_fault(env):
    client, Session = env
    rid = seed_route(Session, stops=[("正常点", 1.0, 1.0)], max_weight=0.0)
    r1 = client.post("/api/pack", json={"route_id": rid})
    assert r1.status_code == 409
    body = r1.json()
    assert set(body) == FAULT_KEYS
    assert body["fault"] == "pack_rejected"
    assert body["at"] == "pack"

    r2 = client.post("/api/pack", json={"route_id": rid})
    assert r2.status_code == 409
    assert r2.json()["fault"] == body["fault"]
    assert r2.json()["at"] == body["at"]

    with Session() as db:
        assert db.scalars(select(PackBag)).all() == []
        assert db.scalars(select(RejectRecord)).all() == []


def test_success_still_writes_bags_and_rejects(env):
    client, Session = env
    rid = seed_route(Session, stops=[("小件", 2.0, 3.0), ("超大件", 9.5, 6.0)])
    r = client.post("/api/pack", json={"route_id": rid})
    assert r.status_code == 200
    bags = r.json()
    assert len(bags) == 1
    assert [i["stop_name"] for i in bags[0]["items"]] == ["小件"]

    with Session() as db:
        bag_rows = db.scalars(select(PackBag).where(PackBag.route_id == rid)).all()
        assert len(bag_rows) == 1
        rejects = db.scalars(select(RejectRecord).where(RejectRecord.route_id == rid)).all()
        assert [x.stop_name for x in rejects] == ["超大件"]
        assert "超重" in rejects[0].reason
