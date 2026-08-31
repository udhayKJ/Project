from pydantic import BaseModel, EmailStr


class TenantCreate(BaseModel):
    name: str


class TenantResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    tenant_id: int


class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: str
    tenant_id: int

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str

class ResourceCreate(BaseModel):
    name: str


class ResourceResponse(BaseModel):
    id: int
    name: str
    owner_id: int
    tenant_id: int

    class Config:
        from_attributes = True

class OrderCreate(BaseModel):
    item_name: str
    amount: int


class OrderResponse(BaseModel):
    id: int
    item_name: str
    amount: int
    status: str
    owner_id: int
    tenant_id: int

    class Config:
        from_attributes = True

class OrderTransition(BaseModel):
    new_status: str