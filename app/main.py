import logging
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from .database import engine, Base, get_db
from . import models, schemas
from .config import (
    settings,
    is_bola_test_active,
    is_bfla_test_active,
    is_workflow_test_active,
    is_contextual_test_active
)
from .auth import hash_password, verify_password, create_access_token
from .dependencies import get_current_user
from .order_logic import is_valid_transition, get_action, is_role_allowed
from .event_logger import log_event

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("api_security.main")

# Create tables if not exist
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="API Security Research Testbed",
    version="1.0.0",
    description="A single configuration-driven API testbed for generating contextual event traces."
)


@app.get("/")
def root():
    return {
        "message": "API Security Research Testbed is running",
        "version": "1.0.0"
    }


# ==========================================
# Tenant & User Management
# ==========================================

@app.post("/tenants", response_model=schemas.TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(
    tenant: schemas.TenantCreate,
    db: Session = Depends(get_db)
):
    existing = db.query(models.Tenant).filter(models.Tenant.name == tenant.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant already exists"
        )

    new_tenant = models.Tenant(name=tenant.name)
    db.add(new_tenant)
    db.commit()
    db.refresh(new_tenant)
    return new_tenant


@app.post("/users", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == user.tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    existing = db.query(models.User).filter(models.User.username == user.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )

    role = (user.role or "CUSTOMER").upper()
    if role not in ("CUSTOMER", "MANAGER", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role. Must be CUSTOMER, MANAGER, or ADMIN"
        )

    new_user = models.User(
        username=user.username,
        email=user.email,
        password_hash=hash_password(user.password),
        tenant_id=user.tenant_id,
        role=role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


# ==========================================
# Authentication & User Profile
# ==========================================

@app.post("/auth/login", response_model=schemas.TokenResponse)
def login(
    login_data: schemas.LoginRequest,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.username == login_data.username).first()
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    token = create_access_token(user.id)
    return {
        "access_token": token,
        "token_type": "bearer"
    }


@app.get("/users/me", response_model=schemas.UserResponse)
def get_me(
    current_user: models.User = Depends(get_current_user)
):
    return current_user


# ==========================================
# Resources Management (Generic)
# ==========================================

@app.post("/resources", response_model=schemas.ResourceResponse, status_code=status.HTTP_201_CREATED)
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


@app.get("/resources", response_model=List[schemas.ResourceResponse])
def get_resources(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(models.Resource).filter(
        models.Resource.tenant_id == current_user.tenant_id
    ).all()


@app.get("/resources/{resource_id}", response_model=schemas.ResourceResponse)
def get_resource(
    resource_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    resource = db.query(models.Resource).filter(models.Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    if resource.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: cross-tenant access prohibited"
        )

    return resource


@app.delete("/resources/{resource_id}")
def delete_resource(
    resource_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    resource = db.query(models.Resource).filter(models.Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    if resource.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    if resource.owner_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner or admin can delete this resource"
        )

    db.delete(resource)
    db.commit()
    return {"message": "Resource deleted"}


# ==========================================
# Orders Management & State Machine
# ==========================================

@app.post("/orders", response_model=schemas.OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    order: schemas.OrderCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    new_order = models.Order(
        item_name=order.item_name,
        amount=order.amount,
        status="CREATED",
        owner_id=current_user.id,
        tenant_id=current_user.tenant_id
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    # Log successful order creation
    log_event(
        db=db,
        action="CREATE",
        resource_type="ORDER",
        user_id=current_user.id,
        role=current_user.role,
        tenant_id=current_user.tenant_id,
        resource_id=new_order.id,
        resource_owner_id=current_user.id,
        resource_tenant_id=current_user.tenant_id,
        previous_state=None,
        new_state="CREATED",
        result="ALLOW",
        reason="SUCCESS"
    )

    return new_order


@app.get("/orders", response_model=List[schemas.OrderResponse])
def get_orders(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(models.Order).filter(
        models.Order.tenant_id == current_user.tenant_id
    ).all()


@app.get("/orders/{order_id}", response_model=schemas.OrderResponse)
def get_order(
    order_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    # Cross-tenant BOLA Evaluation
    is_cross_tenant = (order.tenant_id != current_user.tenant_id)
    if is_cross_tenant:
        if not is_bola_test_active():
            log_event(
                db=db,
                action="READ",
                resource_type="ORDER",
                user_id=current_user.id,
                role=current_user.role,
                tenant_id=current_user.tenant_id,
                resource_id=order.id,
                resource_owner_id=order.owner_id,
                resource_tenant_id=order.tenant_id,
                previous_state=order.status,
                new_state=order.status,
                result="DENY",
                reason="TENANT_ISOLATION_VIOLATION"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: cross-tenant access prohibited"
            )

    # Log authorized (or BOLA-bypassed) read
    log_event(
        db=db,
        action="READ",
        resource_type="ORDER",
        user_id=current_user.id,
        role=current_user.role,
        tenant_id=current_user.tenant_id,
        resource_id=order.id,
        resource_owner_id=order.owner_id,
        resource_tenant_id=order.tenant_id,
        previous_state=order.status,
        new_state=order.status,
        result="ALLOW",
        reason="BOLA_TEST_OVERRIDE" if is_cross_tenant else "SUCCESS"
    )

    return order


def _execute_order_transition(
    order_id: int,
    target_status: str,
    current_user: models.User,
    db: Session
) -> models.Order:
    """
    Unified transition handler evaluating Tenant (BOLA), Workflow, Role (BFLA),
    and Contextual Ownership checks with configuration-driven overrides.
    """
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    target_status = target_status.upper()
    action = get_action(order.status, target_status)

    # 1. Multi-Tenant Isolation Check (BOLA)
    is_cross_tenant = (order.tenant_id != current_user.tenant_id)
    if is_cross_tenant and not is_bola_test_active():
        log_event(
            db=db,
            action=action,
            resource_type="ORDER",
            user_id=current_user.id,
            role=current_user.role,
            tenant_id=current_user.tenant_id,
            resource_id=order.id,
            resource_owner_id=order.owner_id,
            resource_tenant_id=order.tenant_id,
            previous_state=order.status,
            new_state=target_status,
            result="DENY",
            reason="TENANT_ISOLATION_VIOLATION"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: cross-tenant operation prohibited"
        )

    # 2. Workflow Validation Check (State Machine)
    valid_transition = is_valid_transition(order.status, target_status)
    if not valid_transition and not is_workflow_test_active():
        log_event(
            db=db,
            action="INVALID_TRANSITION",
            resource_type="ORDER",
            user_id=current_user.id,
            role=current_user.role,
            tenant_id=current_user.tenant_id,
            resource_id=order.id,
            resource_owner_id=order.owner_id,
            resource_tenant_id=order.tenant_id,
            previous_state=order.status,
            new_state=target_status,
            result="DENY",
            reason="INVALID_STATE_TRANSITION"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid transition: {order.status} -> {target_status}"
        )

    # 3. Role-Based Authorization Check (BFLA)
    role_allowed = is_role_allowed(current_user.role, action)
    if not role_allowed and not is_bfla_test_active():
        log_event(
            db=db,
            action=action,
            resource_type="ORDER",
            user_id=current_user.id,
            role=current_user.role,
            tenant_id=current_user.tenant_id,
            resource_id=order.id,
            resource_owner_id=order.owner_id,
            resource_tenant_id=order.tenant_id,
            previous_state=order.status,
            new_state=target_status,
            result="DENY",
            reason="ROLE_NOT_PERMITTED"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role {current_user.role} is not permitted to perform action {action}"
        )

    # 4. Contextual Resource Ownership Check (Same-Tenant Ownership)
    is_ownership_violation = (current_user.role == "CUSTOMER" and order.owner_id != current_user.id)
    if is_ownership_violation and not is_contextual_test_active():
        log_event(
            db=db,
            action=action,
            resource_type="ORDER",
            user_id=current_user.id,
            role=current_user.role,
            tenant_id=current_user.tenant_id,
            resource_id=order.id,
            resource_owner_id=order.owner_id,
            resource_tenant_id=order.tenant_id,
            previous_state=order.status,
            new_state=target_status,
            result="DENY",
            reason="NOT_ORDER_OWNER"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer can only modify own orders"
        )

    # Execute state change
    previous_state = order.status
    order.status = target_status
    db.commit()
    db.refresh(order)

    # Determine reason annotation for research logging
    reason = "SUCCESS"
    if is_cross_tenant:
        reason = "BOLA_TEST_OVERRIDE"
    elif not valid_transition:
        reason = "WORKFLOW_TEST_OVERRIDE"
    elif not role_allowed:
        reason = "BFLA_TEST_OVERRIDE"
    elif is_ownership_violation:
        reason = "CONTEXTUAL_TEST_OVERRIDE"

    log_event(
        db=db,
        action=action,
        resource_type="ORDER",
        user_id=current_user.id,
        role=current_user.role,
        tenant_id=current_user.tenant_id,
        resource_id=order.id,
        resource_owner_id=order.owner_id,
        resource_tenant_id=order.tenant_id,
        previous_state=previous_state,
        new_state=order.status,
        result="ALLOW",
        reason=reason
    )

    return order


@app.post("/orders/{order_id}/transition", response_model=schemas.OrderResponse)
def transition_order(
    order_id: int,
    transition: schemas.OrderTransition,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return _execute_order_transition(
        order_id=order_id,
        target_status=transition.new_status,
        current_user=current_user,
        db=db
    )


@app.post("/orders/{order_id}/confirm", response_model=schemas.OrderResponse)
def confirm_order(
    order_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return _execute_order_transition(order_id, "CONFIRMED", current_user, db)


@app.post("/orders/{order_id}/pay", response_model=schemas.OrderResponse)
def pay_order(
    order_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return _execute_order_transition(order_id, "PAID", current_user, db)


@app.post("/orders/{order_id}/ship", response_model=schemas.OrderResponse)
def ship_order(
    order_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return _execute_order_transition(order_id, "SHIPPED", current_user, db)


@app.post("/orders/{order_id}/deliver", response_model=schemas.OrderResponse)
def deliver_order(
    order_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return _execute_order_transition(order_id, "DELIVERED", current_user, db)


@app.post("/orders/{order_id}/cancel", response_model=schemas.OrderResponse)
def cancel_order(
    order_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return _execute_order_transition(order_id, "CANCELLED", current_user, db)


# ==========================================
# Event Logging & Research Inspection
# ==========================================

@app.get("/events", response_model=List[schemas.EventResponse])
def get_events(
    action: Optional[str] = Query(None, description="Filter by action name"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    result: Optional[str] = Query(None, description="Filter by result (ALLOW/DENY)"),
    user_id: Optional[int] = Query(None, description="Filter by user id"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve contextual event traces.
    Enforces tenant isolation: users can only inspect event traces from their own tenant.
    """
    query = db.query(models.APIEvent).filter(
        models.APIEvent.tenant_id == current_user.tenant_id
    )

    if action:
        query = query.filter(models.APIEvent.action == action.upper())
    if resource_type:
        query = query.filter(models.APIEvent.resource_type == resource_type.upper())
    if result:
        query = query.filter(models.APIEvent.result == result.upper())
    if user_id:
        query = query.filter(models.APIEvent.user_id == user_id)

    events = query.order_by(models.APIEvent.id.asc()).all()
    return events