from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    stars: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportOut(BaseModel):
    id: int
    title: str
    owner_id: int
    owner_email: str
    created_at: datetime
    already_downloaded: bool = False
    is_own: bool = False

    model_config = {"from_attributes": True}
