VALID_TRANSITIONS = {
    "CREATED": ["CONFIRMED", "CANCELLED"],
    "CONFIRMED": ["PAID", "CANCELLED"],
    "PAID": ["SHIPPED"],
    "SHIPPED": ["DELIVERED"],
    "DELIVERED": [],
    "CANCELLED": []
}


ROLE_PERMISSIONS = {
    "CUSTOMER": {
        "PAY",
        "CANCEL"
    },

    "MANAGER": {
        "CONFIRM",
        "PAY",
        "SHIP",
        "DELIVER",
        "CANCEL"
    },

    "ADMIN": {
        "CONFIRM",
        "PAY",
        "SHIP",
        "DELIVER",
        "CANCEL"
    }
}


STATE_ACTIONS = {
    ("CREATED", "CONFIRMED"): "CONFIRM",
    ("CREATED", "CANCELLED"): "CANCEL",

    ("CONFIRMED", "PAID"): "PAY",
    ("CONFIRMED", "CANCELLED"): "CANCEL",

    ("PAID", "SHIPPED"): "SHIP",
    ("SHIPPED", "DELIVERED"): "DELIVER"
}


def is_valid_transition(
    current_state: str,
    new_state: str
) -> bool:

    return new_state in VALID_TRANSITIONS.get(
        current_state,
        []
    )


def get_action(
    current_state: str,
    new_state: str
) -> str | None:

    return STATE_ACTIONS.get(
        (current_state, new_state)
    )


def is_role_allowed(
    role: str,
    action: str
) -> bool:

    return action in ROLE_PERMISSIONS.get(
        role,
        set()
    )