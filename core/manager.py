import asyncio
import json
from collections import defaultdict
from typing import DefaultDict, Dict, Set
import redis.asyncio as redis
from fastapi import WebSocket
from core.config import REDIS_CHANNEL, REDIS_URL


class ConnectionManager:
    def __init__(self):
        # user_id -> set of sockets (supports multiple tabs/devices per user)
        self.active_connections: DefaultDict[int, Set[WebSocket]] = defaultdict(set)
        # socket object id -> user_id (allows removing exact disconnected socket)
        self.socket_to_user: Dict[int, int] = {}
        self._lock = asyncio.Lock()

        # Redis Settings
        self.redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        self.pubsub = self.redis_client.pubsub() # -> Publisher Subscriber
        self.channel = REDIS_CHANNEL

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

    async def _local_broadcast(self, message: str, sender_user_id: int = None):
        async with self._lock:
            sockets = [
                ws
                for user_id, user_sockets in self.active_connections.items()
                if user_id != sender_user_id
                for ws in user_sockets
            ]

        for connection in sockets:
            try:
                await connection.send_text(message)
            except Exception:
                asyncio.create_task(self.disconnect(connection))

    async def broadcast(self, message: str, sender_id: int = None):
        payload = {
            "message": message,
            "sender_id": sender_id
        }
        await self.redis_client.publish(self.channel, json.dumps(payload))

    async def listen_to_redis(self):
        await self.pubsub.subscribe(self.channel)
        try:
            async for message in self.pubsub.listen():
                if message['type'] == 'message':
                    data = json.loads(message['data'])
                    await self._local_broadcast(
                        message=data['message'],
                        sender_user_id=data.get('sender_id')
                    )
        except Exception as e:
            print(f"Redis Listen Error: {e}")

manager = ConnectionManager()