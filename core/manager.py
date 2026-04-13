import asyncio
from collections import defaultdict
from typing import DefaultDict, Dict, Set

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # user_id -> set of sockets (supports multiple tabs/devices per user)
        self.active_connections: DefaultDict[int, Set[WebSocket]] = defaultdict(set)
        # socket object id -> user_id (allows removing exact disconnected socket)
        self.socket_to_user: Dict[int, int] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections[user_id].add(websocket)
            self.socket_to_user[id(websocket)] = user_id

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            socket_id = id(websocket)
            user_id = self.socket_to_user.pop(socket_id, None)
            if user_id is None:
                return

            sockets = self.active_connections.get(user_id)
            if not sockets:
                return

            sockets.discard(websocket)
            if not sockets:
                self.active_connections.pop(user_id, None)

    async def broadcast(self, message: str, sender_user_id: int):
        async with self._lock:
            sockets = [
                ws
                for user_id, user_sockets in self.active_connections.items()
                if user_id != sender_user_id
                for ws in user_sockets
            ]

        dead_sockets = []
        for connection in sockets:
            try:
                await connection.send_text(message)
            except Exception:
                dead_sockets.append(connection)

        for ws in dead_sockets:
            await self.disconnect(ws)


manager = ConnectionManager()