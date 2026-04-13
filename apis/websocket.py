from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from core.manager import manager
from core.security import get_current_user_ws

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    user=Depends(get_current_user_ws),
):
    if user is None:
        return

    await manager.connect(user.id, websocket)
    await manager.broadcast(f"Server: {user.username} is now online", user.id)

    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(f"{user.username}: {data}", user.id)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)
        await manager.broadcast(f"Server: {user.username} is now offline", user.id)