VALID_TRANSITIONS = {
    "CREATED": ["CONFIRMED", "CANCELLED"],
    "CONFIRMED": ["PAID", "CANCELLED"],
    "PAID": ["SHIPPED"],
    "SHIPPED": ["DELIVERED"],
    "DELIVERED": [],
    "CANCELLED": []
}


def is_valid_transition(current_state: str, new_state: str) -> bool:
    allowed_states = VALID_TRANSITIONS.get(current_state, [])

    return new_state in allowed_states