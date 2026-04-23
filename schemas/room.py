from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RoomVisibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"


class RoomMemberRole(str, Enum):
    OWNER = "owner"
    MEMBER = "member"


class RoomCreate(BaseModel):
    name: str = Field(min_length=3, max_length=50)
    visibility: RoomVisibility = RoomVisibility.PUBLIC


class RoomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=50)
    visibility: RoomVisibility | None = None
    is_active: bool | None = None


class RoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    visibility: RoomVisibility
    owner_user_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RoomMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    room_id: int
    user_id: int
    role: RoomMemberRole
    joined_at: datetime
    left_at: datetime | None
    invited_by_user_id: int | None
    last_read_at: datetime | None


class RoomUserPresenceOut(BaseModel):
    user_id: int
    username: str
    is_online: bool


class RoomOnlineUsersOut(BaseModel):
    room_id: int
    online_users: list[RoomUserPresenceOut]


class RoomUserOnlineStatusOut(BaseModel):
    room_id: int
    user_id: int
    username: str
    is_online: bool


class RoomJoinRequest(BaseModel):
    pass


class RoomLeaveRequest(BaseModel):
    pass


class RoomInviteRequest(BaseModel):
    user_id: int
