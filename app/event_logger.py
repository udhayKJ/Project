from sqlalchemy.orm import Session

from .models import APIEvent


def log_event(
    db: Session,
    user_id: int | None,
    tenant_id: int | None,
    action: str,
    resource_type: str,
    resource_id: int | None,
    previous_state: str | None,
    new_state: str | None,
    result: str
):
    event = APIEvent(
        user_id=user_id,
        tenant_id=tenant_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        previous_state=previous_state,
        new_state=new_state,
        result=result
    )

    db.add(event)
    db.commit()