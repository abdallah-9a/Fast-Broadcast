import asyncio
import json
from collections import defaultdict
from typing import Any
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
        # room_id -> sockets currently subscribed to this room on this instance.
        self.room_connections: DefaultDict[int, Set[WebSocket]] = defaultdict(set)
        # socket object id -> subscribed room_ids.
        self.socket_rooms: Dict[int, Set[int]] = {}
        self._lock = asyncio.Lock()

        # Redis Settings
        self.redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        self.pubsub = self.redis_client.pubsub() # -> Publisher Subscriber
        self.channel = REDIS_CHANNEL
        self.online_users_key = "presence:online_users"
        self.lobby_room_id = 0

    def _user_connections_key(self, user_id: int) -> str:
        return f"presence:user:{user_id}:connections"

    def _room_online_users_key(self, room_id: int) -> str:
        return f"presence:room:{room_id}:online_users"

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections[user_id].add(websocket)
            socket_id = id(websocket)
            self.socket_to_user[socket_id] = user_id
            self.socket_rooms[socket_id] = set()

        # Every connection starts in lobby room for backward compatibility.
        await self.join_room(self.lobby_room_id, websocket)

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

            subscribed_rooms = self.socket_rooms.pop(socket_id, set())
            for room_id in subscribed_rooms:
                room_sockets = self.room_connections.get(room_id)
                if room_sockets is None:
                    continue
                room_sockets.discard(websocket)
                if not room_sockets:
                    self.room_connections.pop(room_id, None)
                    # Remove user from room presence when last socket leaves
                    room_online_key = self._room_online_users_key(room_id)
                    await self.redis_client.srem(room_online_key, user_id)

    async def join_room(self, room_id: int, websocket: WebSocket):
        async with self._lock:
            socket_id = id(websocket)
            if socket_id not in self.socket_to_user:
                return

            user_id = self.socket_to_user[socket_id]
            was_in_room = socket_id in self.socket_rooms and room_id in self.socket_rooms[socket_id]
            
            self.room_connections[room_id].add(websocket)
            self.socket_rooms.setdefault(socket_id, set()).add(room_id)
            
            # Add user to room presence only on first join from this socket
            if not was_in_room:
                room_online_key = self._room_online_users_key(room_id)
                await self.redis_client.sadd(room_online_key, user_id)

    async def leave_room(self, room_id: int, websocket: WebSocket):
        async with self._lock:
            socket_id = id(websocket)
            subscribed_rooms = self.socket_rooms.get(socket_id)
            if not subscribed_rooms or room_id not in subscribed_rooms:
                return

            subscribed_rooms.discard(room_id)
            room_sockets = self.room_connections.get(room_id)
            if room_sockets is not None:
                room_sockets.discard(websocket)
                if not room_sockets:
                    # Remove user from room presence when last socket leaves
                    user_id = self.socket_to_user.get(socket_id)
                    if user_id is not None:
                        room_online_key = self._room_online_users_key(room_id)
                        await self.redis_client.srem(room_online_key, user_id)
                    self.room_connections.pop(room_id, None)

    async def is_socket_in_room(self, room_id: int, websocket: WebSocket) -> bool:
        async with self._lock:
            return websocket in self.room_connections.get(room_id, set())

    async def _local_broadcast(self, event: Dict[str, Any], room_id: int, sender_user_id: int = None):
        async with self._lock:
            sockets = [
                ws
                for ws in self.room_connections.get(room_id, set())
                for user_id in [self.socket_to_user.get(id(ws))]
                if user_id is not None
                if user_id != sender_user_id
            ]

        for connection in sockets:
            try:
                await connection.send_json(event)
            except Exception:
                asyncio.create_task(self.disconnect(connection))

    async def broadcast(self, event: Dict[str, Any], sender_id: int = None, room_id: int | None = None):
        resolved_room_id = room_id if room_id is not None else int(event.get("room_id", self.lobby_room_id))
        payload = {
            "event": event,
            "sender_id": sender_id,
            "room_id": resolved_room_id,
        }
        await self.redis_client.publish(self.channel, json.dumps(payload))

    async def mark_user_online(self, user_id: int):
        connections_key = self._user_connections_key(user_id)
        await self.redis_client.incr(connections_key)
        await self.redis_client.sadd(self.online_users_key, user_id)

    async def mark_user_offline(self, user_id: int):
        connections_key = self._user_connections_key(user_id)
        count = await self.redis_client.decr(connections_key)
        if count <= 0:
            await self.redis_client.delete(connections_key)
            await self.redis_client.srem(self.online_users_key, user_id)

    async def is_user_online(self, user_id: int) -> bool:
        return await self.redis_client.sismember(self.online_users_key, user_id)

    async def get_online_user_ids(self) -> list[int]:
        raw_user_ids = await self.redis_client.smembers(self.online_users_key)
        valid_user_ids = []
        for raw_id in raw_user_ids:
            try:
                valid_user_ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue
        return sorted(valid_user_ids)

    async def get_room_online_user_ids(self, room_id: int) -> list[int]:
        """Get sorted list of user IDs currently online in a specific room."""
        room_online_key = self._room_online_users_key(room_id)
        raw_user_ids = await self.redis_client.smembers(room_online_key)
        valid_user_ids = []
        for raw_id in raw_user_ids:
            try:
                valid_user_ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue
        return sorted(valid_user_ids)

    async def listen_to_redis(self):
        await self.pubsub.subscribe(self.channel)
        try:
            async for message in self.pubsub.listen():
                if message['type'] == 'message':
                    data = json.loads(message['data'])
                    room_id = int(data.get("room_id", self.lobby_room_id))
                    await self._local_broadcast(
                        event=data['event'],
                        room_id=room_id,
                        sender_user_id=data.get('sender_id')
                    )
        except Exception as e:
            print(f"Redis Listen Error: {e}")

manager = ConnectionManager()