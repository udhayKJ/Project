from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict


class TenantCreate(BaseModel):
    name: str


class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    tenant_id: int
    role: Optional[str] = "CUSTOMER"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    role: str
    tenant_id: int


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class ResourceCreate(BaseModel):
    name: str


class ResourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    owner_id: int
    tenant_id: int


class OrderCreate(BaseModel):
    item_name: str
    amount: int


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_name: str
    amount: int
    status: str
    owner_id: int
    tenant_id: int


class OrderTransition(BaseModel):
    new_status: str


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    user_id: Optional[int] = None
    role: Optional[str] = None
    tenant_id: Optional[int] = None
    action: str
    resource_type: str
    resource_id: Optional[int] = None
    resource_owner_id: Optional[int] = None
    resource_tenant_id: Optional[int] = None
    previous_state: Optional[str] = None
    new_state: Optional[str] = None
    result: str
    reason: Optional[str] = None