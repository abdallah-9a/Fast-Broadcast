from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import get_current_user
from models.room import Room, RoomMember, RoomMemberRole, RoomVisibility
from models.user import User
from schemas.room import RoomCreate, RoomMemberOut, RoomOut

router = APIRouter()


def _utc_now():
    return datetime.now(timezone.utc)


def _get_active_room(db: Session, room_id: int):
    room = db.query(Room).filter(Room.id == room_id, Room.is_active.is_(True)).first()
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


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


@router.post("", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
def create_room(
    room_in: RoomCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room_name = room_in.name.strip()
    if not room_name:
        raise HTTPException(status_code=400, detail="Room name cannot be empty")

    room = Room(
        name=room_name,
        visibility=room_in.visibility.value,
        owner_user_id=current_user.id,
    )
    db.add(room)
    db.flush()

    owner_membership = RoomMember(
        room_id=room.id,
        user_id=current_user.id,
        role=RoomMemberRole.OWNER.value,
    )
    db.add(owner_membership)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Room with this name already exists",
        )

    db.refresh(room)
    return room


@router.get("", response_model=list[RoomOut])
def list_rooms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    membership_query = and_(
        RoomMember.room_id == Room.id,
        RoomMember.user_id == current_user.id,
        RoomMember.left_at.is_(None),
    )

    rooms = (
        db.query(Room)
        .outerjoin(RoomMember, membership_query)
        .filter(Room.is_active.is_(True))
        .filter(
            or_(
                Room.visibility == RoomVisibility.PUBLIC.value,
                RoomMember.id.isnot(None),
            )
        )
        .order_by(Room.created_at.desc())
        .all()
    )

    return rooms


@router.get("/{room_id}", response_model=RoomOut)
def get_room_details(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = _get_active_room(db, room_id)

    if room.visibility == RoomVisibility.PRIVATE.value:
        is_member = _get_active_membership(db, room.id, current_user.id) is not None
        if not is_member:
            raise HTTPException(status_code=403, detail="You are not allowed to access this room")

    return room


@router.post("/{room_id}/join", response_model=RoomMemberOut)
def join_room(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = _get_active_room(db, room_id)

    active_membership = _get_active_membership(db, room.id, current_user.id)
    if active_membership is not None:
        return active_membership

    if room.visibility == RoomVisibility.PRIVATE.value:
        raise HTTPException(status_code=403, detail="Private room requires an invite")

    previous_membership = (
        db.query(RoomMember)
        .filter(RoomMember.room_id == room.id, RoomMember.user_id == current_user.id)
        .order_by(RoomMember.id.desc())
        .first()
    )

    if previous_membership is not None:
        previous_membership.left_at = None
        previous_membership.joined_at = _utc_now()
        previous_membership.role = RoomMemberRole.MEMBER.value
        membership = previous_membership
    else:
        membership = RoomMember(
            room_id=room.id,
            user_id=current_user.id,
            role=RoomMemberRole.MEMBER.value,
            joined_at=_utc_now(),
            left_at=None,
        )
        db.add(membership)

    db.commit()
    db.refresh(membership)
    return membership


@router.post("/{room_id}/leave", response_model=RoomMemberOut)
def leave_room(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = _get_active_room(db, room_id)

    membership = _get_active_membership(db, room.id, current_user.id)
    if membership is None:
        raise HTTPException(status_code=404, detail="You are not a member of this room")

    if membership.role == RoomMemberRole.OWNER.value:
        raise HTTPException(status_code=400, detail="Owner cannot leave the room")

    membership.left_at = _utc_now()
    db.commit()
    db.refresh(membership)
    return membership


@router.get("/{room_id}/members", response_model=list[RoomMemberOut])
def list_room_members(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = _get_active_room(db, room_id)

    if room.visibility == RoomVisibility.PRIVATE.value:
        membership = _get_active_membership(db, room.id, current_user.id)
        if membership is None:
            raise HTTPException(status_code=403, detail="You are not allowed to access this room")

    members = (
        db.query(RoomMember)
        .filter(RoomMember.room_id == room.id, RoomMember.left_at.is_(None))
        .order_by(RoomMember.joined_at.asc())
        .all()
    )
    return members
