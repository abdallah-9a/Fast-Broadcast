# Fast Broadcast

A real-time room-based chat application built with FastAPI, WebSockets, and Redis. Supports multi-server deployments with room-scoped messaging and presence tracking.

## Features

### Core
- **User Authentication**: JWT-based registration and login with bcrypt password hashing
- **Room Management**: Create public/private rooms with membership controls
- **Real-time Messaging**: WebSocket-based room-scoped message delivery
- **Multi-server Support**: Redis pub/sub for cross-server message routing by room ID
- **Global Presence**: Track which users are online globally
- **Room Presence**: Track which users are online within each room
- **REST API**: Full CRUD for rooms, membership, and presence queries
- **Soft-delete Membership**: Preserve membership history with `left_at` timestamps

### Access Control
- Private rooms require explicit membership
- Room owners control who can leave/access rooms
- Presence endpoints enforce membership visibility for private rooms

### Event Contract
WebSocket events use a standardized JSON envelope:
```json
{
  "event": "room.message|room.join|room.leave|room.presence_update",
  "room_id": 1,
  "sender": {"user_id": 1, "username": "alice"},
  "payload": {"message": "hello"},
  "timestamp": "2026-04-28T06:34:56.489598+00:00"
}
```

## Architecture

### Single Server
```
FastAPI WebSocket Endpoint → Local Room Connections Map → Client Sockets
```

### Multi-Server (Redis)
```
Server A (joins room 5) → Redis pub/sub (channel="broadcast")
                           ↓
Server B (listening) → Receives room_id=5 → Routes to local room subscribers only
```

Room subscription tracking keeps each server aware of which sockets are subscribed to which rooms. Redis pub/sub includes the `room_id` in the payload, so servers can route messages to the correct local audience without broadcasting globally.

## Tech Stack

- **Framework**: FastAPI 0.135.3 (async)
- **Database**: SQLAlchemy 2.0.49 ORM with SQLite
- **WebSocket**: FastAPI native with lifespan async context management
- **Authentication**: JWT (python-jose), bcrypt password hashing
- **Real-time**: Redis 7.4.0 async client (redis.asyncio) for pub/sub
- **Validation**: Pydantic v2.12.5 with ORM serialization
- **Testing**: pytest 9.0.3 with asyncio plugin

## Setup

### Prerequisites
- Python 3.12+
- Redis 7.0+ (or comment out Redis config for single-server mode)

### Installation

```bash
# Clone the repository
git clone <repo>
cd fast-broadcast

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables (optional)
export REDIS_URL=redis://localhost:6379  # Defaults to localhost:6379
export DATABASE_URL=sqlite:///./test.db

# Run the server
python -m uvicorn main:app --reload

# Run tests
pytest -q
```

## API Endpoints

### Authentication
- `POST /auth/register` - Register new user
- `POST /auth/token` - Login and get JWT token

### Global Presence
- `GET /users/{user_id}/online` - Check if user is online globally
- `GET /online-users` - List all globally online users with usernames

### Rooms
- `POST /rooms` - Create a room (public/private)
- `GET /rooms` - List rooms (public + member rooms)
- `GET /rooms/{room_id}` - Get room details
- `POST /rooms/{room_id}/join` - Join a room
- `POST /rooms/{room_id}/leave` - Leave a room
- `GET /rooms/{room_id}/members` - List room members
- `GET /rooms/{room_id}/online-users` - List online users in room with usernames
- `GET /rooms/{room_id}/users/{user_id}/online` - Check if user is online in room with username

### WebSocket
- `WS /ws` - Connect to WebSocket for real-time messaging
  - Send events: `room.join`, `room.leave`, `room.message`
  - Receive events: `room.message`, `room.join`, `room.leave`, `room.presence_update`, `error`

## WebSocket Protocol

### Connect
```bash
# Include JWT token in Authorization header
ws://localhost:8000/ws?token=<jwt_token>
# or
headers: {"Authorization": "Bearer <jwt_token>"}
```

### Send Message
```json
{
  "event": "room.message",
  "room_id": 1,
  "payload": {"message": "hello"}
}
```

### Join Room
```json
{
  "event": "room.join",
  "room_id": 1,
  "payload": {}
}
```

On join, you receive a `room.presence_update` event with all currently online users in the room:
```json
{
  "event": "room.presence_update",
  "room_id": 1,
  "sender": {...},
  "payload": {
    "online_users": [
      {"user_id": 2, "username": "bob", "is_online": true}
    ]
  }
}
```

### Leave Room
```json
{
  "event": "room.leave",
  "room_id": 1,
  "payload": {}
}
```

## Database Models

### User
- `id` (PK)
- `username` (unique, string)
- `email` (unique, email)
- `hashed_password` (string)
- `is_active` (boolean)
- `created_at`, `updated_at` (timestamps)

### Room
- `id` (PK)
- `name` (unique case-insensitive, string)
- `visibility` (enum: public/private)
- `owner_user_id` (FK → User)
- `is_active` (boolean)
- `created_at`, `updated_at` (timestamps)

### RoomMember
- `id` (PK)
- `room_id` (FK → Room, cascade delete)
- `user_id` (FK → User, cascade delete)
- `role` (enum: owner/member)
- `joined_at` (timestamp)
- `left_at` (timestamp, nullable - soft delete)
- `invited_by_user_id` (FK → User, nullable)
- `last_read_at` (timestamp, nullable)
- **Constraints**:
  - Partial unique index on (room_id, user_id) where left_at IS NULL
  - Partial unique index on (room_id) where role='owner' and left_at IS NULL (one owner per room)

## Redis Keys

### Global Presence
- `presence:online_users` - Set of online user IDs
- `presence:user:{user_id}:connections` - Connection counter per user

### Room Presence
- `presence:room:{room_id}:online_users` - Set of online user IDs in room

### Messaging
- Channel: `broadcast` - Single pub/sub channel for all room messages
  - Payload includes `room_id` for filtering

## Testing

All tests are in the `tests/` directory:
- `test_auth_endpoints.py` - Registration and login
- `test_presence_endpoints.py` - Global and room presence
- `test_room_endpoints.py` - Room CRUD and membership
- `test_websocket_endpoint.py` - WebSocket event handling

Run tests:
```bash
pytest -q              # Quick summary
pytest -v              # Verbose
pytest tests/test_auth_endpoints.py  # Single file
```

Current: **23 tests passing**

## Future Enhancements

- Message persistence and history retrieval
- Message editing/deletion
- User invitations via REST endpoint
- Room transfer ownership endpoint
- Rate limiting and message validation
- WebSocket disconnect recovery

## License

MIT
