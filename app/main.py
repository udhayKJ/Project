from app import order_logic
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from .database import engine, Base, get_db
from . import models, schemas

from .auth import hash_password, verify_password, create_access_token
from .dependencies import get_current_user, require_role
from .order_logic import is_valid_transition, get_action, is_role_allowed
from .event_logger import log_event

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="API Security Research API",
    version="0.1.0"
)


@app.get("/")
def root():
    return {
        "message": "API is running"
    }


@app.post("/tenants", response_model=schemas.TenantResponse)
def create_tenant(
    tenant: schemas.TenantCreate,
    db: Session = Depends(get_db)
):
    existing = db.query(models.Tenant).filter(
        models.Tenant.name == tenant.name
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Tenant already exists"
        )

    new_tenant = models.Tenant(
        name=tenant.name
    )

    db.add(new_tenant)
    db.commit()
    db.refresh(new_tenant)

    return new_tenant


@app.post("/users", response_model=schemas.UserResponse)
def create_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    tenant = db.query(models.Tenant).filter(
        models.Tenant.id == user.tenant_id
    ).first()

    if not tenant:
        raise HTTPException(
            status_code=404,
            detail="Tenant not found"
        )

    existing = db.query(models.User).filter(
        models.User.username == user.username
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Username already exists"
        )

    new_user = models.User(
        username=user.username,
        email=user.email,
        password_hash=hash_password(user.password),
        tenant_id=user.tenant_id,
        role="CUSTOMER"
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user

@app.post("/auth/login", response_model=schemas.TokenResponse)
def login(
    login_data: schemas.LoginRequest,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        models.User.username == login_data.username
    ).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    if not verify_password(
        login_data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    token = create_access_token(user.id)

    return {
        "access_token": token,
        "token_type": "bearer"
    }

@app.get("/users/me")
def get_me(
    current_user: models.User = Depends(get_current_user)
):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "tenant_id": current_user.tenant_id
    }

@app.post(
    "/resources",
    response_model=schemas.ResourceResponse
)
def create_resource(
    resource: schemas.ResourceCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    new_resource = models.Resource(
        name=resource.name,
        owner_id=current_user.id,
        tenant_id=current_user.tenant_id
    )

    db.add(new_resource)
    db.commit()
    db.refresh(new_resource)

    return new_resource

@app.get("/resources")
def get_resources(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    resources = db.query(models.Resource).filter(
        models.Resource.tenant_id == current_user.tenant_id
    ).all()

    return resources

@app.get("/resources/{resource_id}")
def get_resource(
    resource_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    resource = db.query(models.Resource).filter(
        models.Resource.id == resource_id
    ).first()

    if not resource:
        raise HTTPException(
            status_code=404,
            detail="Resource not found"
        )

    if resource.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied"
        )

    return resource

@app.delete("/resources/{resource_id}")
def delete_resource(
    resource_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    resource = db.query(models.Resource).filter(
        models.Resource.id == resource_id
    ).first()

    if not resource:
        raise HTTPException(
            status_code=404,
            detail="Resource not found"
        )

    if resource.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied"
        )

    if (
        resource.owner_id != current_user.id
        and current_user.role != "ADMIN"
    ):
        raise HTTPException(
            status_code=403,
            detail="Only the owner or admin can delete this resource"
        )

    db.delete(resource)
    db.commit()

    return {
        "message": "Resource deleted"
    }

@app.post(
    "/orders",
    response_model=schemas.OrderResponse
)
def create_order(
    order: schemas.OrderCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    new_order = models.Order(
        item_name=order.item_name,
        amount=order.amount,
        status="CREATED",

        # Taken from authenticated user
        owner_id=current_user.id,
        tenant_id=current_user.tenant_id
    )

    log_event(
    db=db,
    user_id=current_user.id,
    tenant_id=current_user.tenant_id,
    action="CREATE",
    resource_type="ORDER",
    resource_id=new_order.id,
    previous_state=None,
    new_state="CREATED",
    result="ALLOW"
    )

    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    return new_order

@app.get("/orders", response_model=list[schemas.OrderResponse])
def get_orders(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    orders = db.query(models.Order).filter(
        models.Order.tenant_id == current_user.tenant_id
    ).all()

    return orders

@app.get(
    "/orders/{order_id}",
    response_model=schemas.OrderResponse
)
def get_order(
    order_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    order = db.query(models.Order).filter(
        models.Order.id == order_id
    ).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    if order.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied"
        )

    return order

@app.post(
    "/orders/{order_id}/transition",
    response_model=schemas.OrderResponse
)
def transition_order(
    order_id: int,
    transition: schemas.OrderTransition,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    order = db.query(models.Order).filter(
        models.Order.id == order_id
    ).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    if order.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied"
        )

    if not is_valid_transition(
        order.status,
        transition.new_status
    ):
        log_event(
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="INVALID_TRANSITION",
        resource_type="ORDER",
        resource_id=order.id,
        previous_state=order.status,
        new_state=transition.new_status,
        result="DENY"
        )

        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition: "
                   f"{order.status} -> {transition.new_status}"
        )

    action = get_action(
        order.status,
        transition.new_status
    )

    if action is None:
        raise HTTPException(
            status_code=400,
            detail="Unknown transition"
        )

    if not is_role_allowed(
        current_user.role,
        action
    ):
        log_event(
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action=action,
        resource_type="ORDER",
        resource_id=order.id,
        previous_state=order.status,
        new_state=transition.new_status,
        result="DENY"
        )

        raise HTTPException(
            status_code=403,
            detail="Role not permitted for this action"
        )

    if (
        current_user.role == "CUSTOMER"
        and order.owner_id != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="Customer can only modify own orders"
        )

    previous_state = order.status
    order.status = transition.new_status

    db.commit()
    db.refresh(order)

    log_event(
    db=db,
    user_id=current_user.id,
    tenant_id=current_user.tenant_id,
    action=action,
    resource_type="ORDER",
    resource_id=order.id,
    previous_state=previous_state,
    new_state=order.status,
    result="ALLOW"
    )

    return order

@app.get("/events")
def get_events(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    events = db.query(models.APIEvent).filter(
        models.APIEvent.tenant_id == current_user.tenant_id
    ).all()

    return events