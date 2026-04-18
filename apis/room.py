from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import get_current_user
from models.room import Room, RoomMember, RoomMemberRole, RoomVisibility
from models.user import User
from schemas.room import RoomCreate, RoomOut

router = APIRouter()


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
    room = db.query(Room).filter(Room.id == room_id, Room.is_active.is_(True)).first()
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    if room.visibility == RoomVisibility.PRIVATE.value:
        is_member = (
            db.query(RoomMember)
            .filter(
                RoomMember.room_id == room.id,
                RoomMember.user_id == current_user.id,
                RoomMember.left_at.is_(None),
            )
            .first()
            is not None
        )
        if not is_member:
            raise HTTPException(status_code=403, detail="You are not allowed to access this room")

    return room
