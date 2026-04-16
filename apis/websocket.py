from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from core.database import get_db
from core.manager import manager
from core.security import get_current_user_ws
from models.user import User
from schemas.user import UserOut, UserPresenceStatus

router = APIRouter()


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
    await manager.broadcast(f"Server: {user.username} is now online", user.id)

    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(f"{user.username}: {data}", user.id)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)
        await manager.mark_user_offline(user.id)
        await manager.broadcast(f"Server: {user.username} is now offline", user.id)