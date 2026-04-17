from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CreateUser(BaseModel):
    username: str= Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    is_active: bool


class UserPresenceStatus(BaseModel):
    user_id: int
    is_online: bool

