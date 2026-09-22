"""POST /api/pack 失败响应的统一形状：{"fault", "detail", "at"}。

钉住三类 fault 与对应 at：
- 路线找不到        -> route_not_found / route / 404
- 订户点字段不合法  -> stop_invalid     / stop  / 422
- 装袋过程业务拒绝  -> pack_rejected    / pack  / 409
同类失败连续两次，fault 与 at 必须相同。
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
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app), TestingSession
    finally:
        app.dependency_overrides.clear()


def make_route(db, **kw) -> DeliveryRoute:
    route = DeliveryRoute(
        name=kw.get("name", "测试线"),
        max_weight_kg=kw.get("max_weight_kg", 8.0),
        max_volume_l=kw.get("max_volume_l", 20.0),
    )
    db.add(route)
    db.flush()
    return route


def add_stop(db, route_id, seq, name, weight_kg, volume_l) -> SubscriberStop:
    stop = SubscriberStop(
        route_id=route_id, seq=seq, name=name, weight_kg=weight_kg, volume_l=volume_l
    )
    db.add(stop)
    db.flush()
    return stop


def test_route_not_found_fault_shape_and_repeat(env):
    client, _ = env
    r1 = client.post("/api/pack", json={"route_id": 999})
    assert r1.status_code == 404
    body = r1.json()
    assert set(body) == FAULT_KEYS
    assert body["fault"] == "route_not_found"
    assert body["at"] == "route"
    assert body["detail"]

    r2 = client.post("/api/pack", json={"route_id": 999})
    again = r2.json()
    assert again["fault"] == body["fault"]
    assert again["at"] == body["at"]


@pytest.mark.parametrize(
    "weight_kg,volume_l",
    [(-1.0, 4.0), (2.0, 0.0)],
    ids=["weight_not_positive", "volume_not_positive"],
)
def test_stop_field_invalid_fault_shape_and_repeat(env, weight_kg, volume_l):
    client, Session = env
    db = Session()
    route = make_route(db)
    add_stop(db, route.id, 1, "坏字段点", weight_kg, volume_l)
    route_id = route.id
    db.commit()
    db.close()

    r1 = client.post("/api/pack", json={"route_id": route_id})
    assert r1.status_code == 422
    body = r1.json()
    assert set(body) == FAULT_KEYS
    assert body["fault"] == "stop_invalid"
    assert body["at"] == "stop"
    assert body["detail"]

    r2 = client.post("/api/pack", json={"route_id": route_id})
    again = r2.json()
    assert again["fault"] == body["fault"]
    assert again["at"] == body["at"]


def test_pack_rejected_when_route_has_no_stops(env):
    client, Session = env
    db = Session()
    route = make_route(db)
    route_id = route.id
    db.commit()
    db.close()

    r1 = client.post("/api/pack", json={"route_id": route_id})
    assert r1.status_code == 409
    body = r1.json()
    assert set(body) == FAULT_KEYS
    assert body["fault"] == "pack_rejected"
    assert body["at"] == "pack"
    assert body["detail"]

    r2 = client.post("/api/pack", json={"route_id": route_id})
    again = r2.json()
    assert again["fault"] == body["fault"]
    assert again["at"] == body["at"]


def test_success_path_still_writes_bags_and_rejects(env):
    client, Session = env
    db = Session()
    route = make_route(db, max_weight_kg=4.0, max_volume_l=10.0)
    add_stop(db, route.id, 1, "甲", 2.0, 3.0)
    add_stop(db, route.id, 2, "乙", 2.5, 3.0)
    add_stop(db, route.id, 3, "超大件", 9.0, 1.0)  # 单件超限 -> 拒收
    route_id = route.id
    db.commit()
    db.close()

    r = client.post("/api/pack", json={"route_id": route_id})
    assert r.status_code == 200
    bags = r.json()
    assert isinstance(bags, list)
    assert len(bags) == 2
    assert bags[0]["items"][0]["stop_name"] == "甲"

    db = Session()
    assert len(db.scalars(select(PackBag).where(PackBag.route_id == route_id)).all()) == 2
    rejects = db.scalars(select(RejectRecord).where(RejectRecord.route_id == route_id)).all()
    assert len(rejects) == 1
    assert rejects[0].stop_name == "超大件"
    assert "超重" in rejects[0].reason

    # 再跑一次：清旧重写，袋数与拒收数不变（现网语义）
    r2 = client.post("/api/pack", json={"route_id": route_id})
    assert r2.status_code == 200
    assert len(r2.json()) == 2
    assert len(db.scalars(select(PackBag).where(PackBag.route_id == route_id)).all()) == 2
    assert len(db.scalars(select(RejectRecord).where(RejectRecord.route_id == route_id)).all()) == 1
    db.close()
