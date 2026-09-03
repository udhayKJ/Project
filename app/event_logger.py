import logging
from sqlalchemy.orm import Session

from .models import APIEvent

logger = logging.getLogger("api_security.event_logger")


def log_event(
    db: Session,
    action: str,
    resource_type: str,
    user_id: int | None = None,
    role: str | None = None,
    tenant_id: int | None = None,
    resource_id: int | None = None,
    resource_owner_id: int | None = None,
    resource_tenant_id: int | None = None,
    previous_state: str | None = None,
    new_state: str | None = None,
    result: str = "ALLOW",
    reason: str | None = None
) -> APIEvent:
    """
    Records an API action into the api_events table.
    Preserves rich contextual information (actor, resource ownership, states, result, reason)
    for downstream behavioral analysis.
    """
    event = APIEvent(
        user_id=user_id,
        role=role,
        tenant_id=tenant_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_owner_id=resource_owner_id,
        resource_tenant_id=resource_tenant_id,
        previous_state=previous_state,
        new_state=new_state,
        result=result,
        reason=reason
    )

    try:
        db.add(event)
        db.commit()
        db.refresh(event)
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to log API event: {e}")
        raise

    return event