import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.database import get_db
from core.manager import manager
from core.security import get_current_user_ws
from models.room import Room, RoomMember, RoomMemberRole, RoomVisibility
from models.user import User
from schemas.user import UserOut, UserPresenceStatus

router = APIRouter()
LOBBY_ROOM_ID = 0


def _build_room_event(event_type: str, room_id: int, user: User, payload: dict):
    return {
        "event": event_type,
        "room_id": room_id,
        "sender": {
            "user_id": user.id,
            "username": user.username,
        },
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _send_error(websocket: WebSocket, user: User, room_id: int, message: str):
    await websocket.send_json(
        {
            "event": "error",
            "room_id": room_id,
            "sender": {"user_id": user.id, "username": user.username},
            "payload": {"message": message},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


def _get_active_room(db: Session, room_id: int):
    return db.query(Room).filter(Room.id == room_id, Room.is_active.is_(True)).first()


def _get_active_membership(db: Session, room_id: int, user_id: int):
    return (
        db.query(RoomMember)
        .filter(
            RoomMember.room_id == room_id,
            RoomMember.user_id == user_id,
            RoomMember.left_at.is_(None),
        )
        .first()
    )


@router.get("/users/{user_id}/online", response_model=UserPresenceStatus)
async def get_user_online_status(user_id: int):
    return {
        "user_id": user_id,
        "is_online": await manager.is_user_online(user_id),
    }


@router.get("/online-users", response_model=list[UserOut])
async def get_online_users(db: Session = Depends(get_db)):
    online_user_ids = await manager.get_online_user_ids()
    if not online_user_ids:
        return []

    users = db.query(User).filter(User.id.in_(online_user_ids)).all()
    users_by_id = {user.id: user for user in users}

    return [
        {
            "id": users_by_id[user_id].id,
            "username": users_by_id[user_id].username,
            "email": users_by_id[user_id].email,
            "is_active": users_by_id[user_id].is_active,
        }
        for user_id in online_user_ids
        if user_id in users_by_id
    ]


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    user=Depends(get_current_user_ws),
):
    if user is None:
        return

    await manager.connect(user.id, websocket)
    await manager.mark_user_online(user.id)
    await manager.broadcast(
        _build_room_event(
            event_type="room.presence",
            room_id=LOBBY_ROOM_ID,
            user=user,
            payload={"status": "online"},
        ),
        user.id,
        room_id=LOBBY_ROOM_ID,
    )

    try:
        while True:
            raw_data = await websocket.receive_text()

            room_id = LOBBY_ROOM_ID
            event_type = "room.message"
            payload = {"message": raw_data}
            message_text = raw_data

            try:
                client_event = json.loads(raw_data)
                if isinstance(client_event, dict):
                    event_type = client_event.get("event", event_type)
                    room_id = int(client_event.get("room_id", room_id))

                    if event_type == "room.message":
                        message_text = str(client_event.get("payload", {}).get("message", "")).strip()
                        payload = {"message": message_text}
                    elif event_type == "room.join":
                        payload = {"action": "join"}
                    elif event_type == "room.leave":
                        payload = {"action": "leave"}
            except (json.JSONDecodeError, ValueError, TypeError):
                # Backward compatibility for plain text clients.
                event_type = "room.message"
                room_id = LOBBY_ROOM_ID
                payload = {"message": raw_data}

            if event_type not in {"room.message", "room.join", "room.leave"}:
                await _send_error(websocket, user, room_id, "Unsupported event type")
                continue

            if event_type == "room.join":
                if room_id == LOBBY_ROOM_ID:
                    await manager.join_room(room_id, websocket)
                    continue

                db = SessionLocal()
                try:
                    room = _get_active_room(db, room_id)
                    if room is None:
                        await _send_error(websocket, user, room_id, "Room not found")
                        continue

                    membership = _get_active_membership(db, room_id, user.id)
                    if membership is None:
                        if room.visibility == RoomVisibility.PRIVATE.value:
                            await _send_error(websocket, user, room_id, "Private room requires an invite")
                            continue

                        previous_membership = (
                            db.query(RoomMember)
                            .filter(RoomMember.room_id == room_id, RoomMember.user_id == user.id)
                            .order_by(RoomMember.id.desc())
                            .first()
                        )

                        if previous_membership is not None:
                            previous_membership.left_at = None
                            previous_membership.joined_at = datetime.now(timezone.utc)
                            previous_membership.role = RoomMemberRole.MEMBER.value
                        else:
                            db.add(
                                RoomMember(
                                    room_id=room_id,
                                    user_id=user.id,
                                    role=RoomMemberRole.MEMBER.value,
                                    joined_at=datetime.now(timezone.utc),
                                    left_at=None,
                                )
                            )
                        db.commit()
                finally:
                    db.close()

                await manager.join_room(room_id, websocket)
                
                # Send presence update to the joining user
                room_online_user_ids = await manager.get_room_online_user_ids(room_id)
                db = SessionLocal()
                try:
                    online_users = db.query(User).filter(User.id.in_(room_online_user_ids)).all() if room_online_user_ids else []
                    presence_payload = {
                        "online_users": [
                            {"user_id": u.id, "username": u.username}
                            for u in online_users
                        ]
                    }
                finally:
                    db.close()
                
                await websocket.send_json(
                    _build_room_event(
                        event_type="room.presence_update",
                        room_id=room_id,
                        user=user,
                        payload=presence_payload,
                    )
                )
                
                await manager.broadcast(
                    _build_room_event(
                        event_type="room.join",
                        room_id=room_id,
                        user=user,
                        payload={"action": "join"},
                    ),
                    user.id,
                    room_id=room_id,
                )
                continue

            if event_type == "room.leave":
                if room_id == LOBBY_ROOM_ID:
                    await _send_error(websocket, user, room_id, "Cannot leave lobby room")
                    continue

                db = SessionLocal()
                try:
                    room = _get_active_room(db, room_id)
                    if room is None:
                        await _send_error(websocket, user, room_id, "Room not found")
                        continue

                    membership = _get_active_membership(db, room_id, user.id)
                    if membership is None:
                        await _send_error(websocket, user, room_id, "You are not a member of this room")
                        continue

                    if membership.role == RoomMemberRole.OWNER.value:
                        await _send_error(websocket, user, room_id, "Owner cannot leave the room")
                        continue

                    membership.left_at = datetime.now(timezone.utc)
                    db.commit()
                finally:
                    db.close()

                await manager.leave_room(room_id, websocket)
                await manager.broadcast(
                    _build_room_event(
                        event_type="room.leave",
                        room_id=room_id,
                        user=user,
                        payload={"action": "leave"},
                    ),
                    user.id,
                    room_id=room_id,
                )
                continue

            if event_type == "room.message":
                normalized_message = str(message_text).strip()
                if not normalized_message:
                    await _send_error(websocket, user, room_id, "room.message requires non-empty payload.message")
                    continue

                payload = {"message": normalized_message}

                if not await manager.is_socket_in_room(room_id, websocket):
                    await _send_error(websocket, user, room_id, "Join room first")
                    continue

                if room_id != LOBBY_ROOM_ID:
                    db = SessionLocal()
                    try:
                        room = _get_active_room(db, room_id)
                        if room is None:
                            await _send_error(websocket, user, room_id, "Room not found")
                            continue

                        membership = _get_active_membership(db, room_id, user.id)
                        if membership is None:
                            await _send_error(websocket, user, room_id, "You are not a member of this room")
                            continue
                    finally:
                        db.close()

                await manager.broadcast(
                    _build_room_event(
                        event_type="room.message",
                        room_id=room_id,
                        user=user,
                        payload=payload,
                    ),
                    user.id,
                    room_id=room_id,
                )
                continue
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)
        await manager.mark_user_offline(user.id)
        await manager.broadcast(
            _build_room_event(
                event_type="room.presence",
                room_id=LOBBY_ROOM_ID,
                user=user,
                payload={"status": "offline"},
            ),
            user.id,
            room_id=LOBBY_ROOM_ID,
        )