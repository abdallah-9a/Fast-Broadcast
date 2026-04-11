from pydantic import BaseModel, EmailStr, Field


class CreateUser(BaseModel):
    username: str= Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8)


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    is_active: bool

