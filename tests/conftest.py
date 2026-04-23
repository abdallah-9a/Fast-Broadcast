import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.database import Base, get_db
from core.manager import manager
import core.security as security
import apis.websocket as websocket_api
from main import app


@pytest.fixture()
def testing_session_local():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    try:
        yield SessionLocal
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, testing_session_local):
    online_user_ids: set[int] = set()
    room_online_users: dict[int, set[int]] = {}  # room_id -> set of online user_ids

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    async def fake_listen_to_redis():
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return

    async def fake_broadcast(event: dict, sender_id: int = None, room_id: int | None = None):
        return None

    async def fake_mark_user_online(user_id: int):
        online_user_ids.add(user_id)

    async def fake_mark_user_offline(user_id: int):
        online_user_ids.discard(user_id)

    async def fake_is_user_online(user_id: int) -> bool:
        return user_id in online_user_ids

    async def fake_get_online_user_ids() -> list[int]:
        return sorted(online_user_ids)

    async def fake_get_room_online_user_ids(room_id: int) -> list[int]:
        return sorted(room_online_users.get(room_id, set()))

    # Mock redis_client.sadd and srem for room presence tracking
    async def fake_redis_sadd(key: str, *values):
        if key.startswith("presence:room:"):
            room_id = int(key.split(":")[2])
            if room_id not in room_online_users:
                room_online_users[room_id] = set()
            for val in values:
                room_online_users[room_id].add(int(val))
        return len(values)

    async def fake_redis_srem(key: str, *values):
        if key.startswith("presence:room:"):
            room_id = int(key.split(":")[2])
            if room_id in room_online_users:
                for val in values:
                    room_online_users[room_id].discard(int(val))
        return len(values)

    async def fake_redis_smembers(key: str):
        if key.startswith("presence:room:"):
            room_id = int(key.split(":")[2])
            return list(str(uid) for uid in room_online_users.get(room_id, set()))
        return []

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(security, "SessionLocal", testing_session_local)
    monkeypatch.setattr(websocket_api, "SessionLocal", testing_session_local)
    monkeypatch.setattr(manager, "listen_to_redis", fake_listen_to_redis)
    monkeypatch.setattr(manager, "broadcast", fake_broadcast)
    monkeypatch.setattr(manager, "mark_user_online", fake_mark_user_online)
    monkeypatch.setattr(manager, "mark_user_offline", fake_mark_user_offline)
    monkeypatch.setattr(manager, "is_user_online", fake_is_user_online)
    monkeypatch.setattr(manager, "get_online_user_ids", fake_get_online_user_ids)
    monkeypatch.setattr(manager, "get_room_online_user_ids", fake_get_room_online_user_ids)
    monkeypatch.setattr(manager.redis_client, "sadd", fake_redis_sadd)
    monkeypatch.setattr(manager.redis_client, "srem", fake_redis_srem)
    monkeypatch.setattr(manager.redis_client, "smembers", fake_redis_smembers)

    manager.active_connections.clear()
    manager.socket_to_user.clear()
    manager.room_connections.clear()
    manager.socket_rooms.clear()
    online_user_ids.clear()
    room_online_users.clear()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    manager.active_connections.clear()
    manager.socket_to_user.clear()
    manager.room_connections.clear()
    manager.socket_rooms.clear()
    online_user_ids.clear()
    room_online_users.clear()
