from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import relationship

from core.database import Base


def _utc_now():
    return datetime.now(timezone.utc)


class RoomVisibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"


class RoomMemberRole(str, Enum):
    OWNER = "owner"
    MEMBER = "member"


room_visibility_enum = SQLEnum(
    RoomVisibility,
    name="room_visibility",
    native_enum=False,
    values_callable=lambda enum_cls: [item.value for item in enum_cls],
)

room_member_role_enum = SQLEnum(
    RoomMemberRole,
    name="room_member_role",
    native_enum=False,
    values_callable=lambda enum_cls: [item.value for item in enum_cls],
)


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        Index("ix_rooms_visibility_is_active", "visibility", "is_active"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(50, collation="NOCASE"), nullable=False, unique=True)
    visibility = Column(room_visibility_enum, nullable=False, default=RoomVisibility.PUBLIC)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    owner = relationship("User", foreign_keys=[owner_user_id])
    memberships = relationship("RoomMember", back_populates="room", cascade="all, delete-orphan")


class RoomMember(Base):
    __tablename__ = "room_members"
    __table_args__ = (
        Index(
            "uq_room_members_active_room_user",
            "room_id",
            "user_id",
            unique=True,
            sqlite_where=text("left_at IS NULL"),
        ),
        Index(
            "uq_room_members_active_owner_per_room",
            "room_id",
            unique=True,
            sqlite_where=text("left_at IS NULL AND role = 'owner'"),
        ),
        Index("ix_room_members_user_left_at", "user_id", "left_at"),
        Index("ix_room_members_room_left_at", "room_id", "left_at"),
    )

    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(room_member_role_enum, nullable=False, default=RoomMemberRole.MEMBER)
    joined_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    left_at = Column(DateTime(timezone=True), nullable=True)
    invited_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    last_read_at = Column(DateTime(timezone=True), nullable=True)

    room = relationship("Room", back_populates="memberships")
    user = relationship("User", foreign_keys=[user_id])
    invited_by_user = relationship("User", foreign_keys=[invited_by_user_id])
