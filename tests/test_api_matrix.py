import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import engine, Base
from app.config import settings

client = TestClient(app)


def reset_test_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def set_test_flags(
    test_mode=False,
    bola=False,
    bfla=False,
    workflow=False,
    contextual=False
):
    settings.TEST_MODE = test_mode
    settings.ENABLE_BOLA_TEST = bola
    settings.ENABLE_BFLA_TEST = bfla
    settings.ENABLE_WORKFLOW_TEST = workflow
    settings.ENABLE_CONTEXTUAL_TEST = contextual


@pytest.fixture(autouse=True)
def setup_database_and_flags():
    reset_test_db()
    set_test_flags(False, False, False, False, False)
    yield
    set_test_flags(False, False, False, False, False)


def create_tenant_and_users():
    """
    Sets up multi-tenant hierarchy:
    Tenant 1:
      - Alice (CUSTOMER)
      - Bob (CUSTOMER)
      - Manager1 (MANAGER)
    Tenant 2:
      - Charlie (CUSTOMER)
      - Manager2 (MANAGER)
    """
    # Create Tenant 1 & 2
    r_t1 = client.post("/tenants", json={"name": "Org 1"})
    t1_id = r_t1.json()["id"]

    r_t2 = client.post("/tenants", json={"name": "Org 2"})
    t2_id = r_t2.json()["id"]

    # Users in Tenant 1
    client.post("/users", json={
        "username": "alice",
        "email": "alice@org1.com",
        "password": "password123",
        "tenant_id": t1_id,
        "role": "CUSTOMER"
    })
    client.post("/users", json={
        "username": "bob",
        "email": "bob@org1.com",
        "password": "password123",
        "tenant_id": t1_id,
        "role": "CUSTOMER"
    })
    client.post("/users", json={
        "username": "manager1",
        "email": "manager1@org1.com",
        "password": "password123",
        "tenant_id": t1_id,
        "role": "MANAGER"
    })

    # Users in Tenant 2
    client.post("/users", json={
        "username": "charlie",
        "email": "charlie@org2.com",
        "password": "password123",
        "tenant_id": t2_id,
        "role": "CUSTOMER"
    })
    client.post("/users", json={
        "username": "manager2",
        "email": "manager2@org2.com",
        "password": "password123",
        "tenant_id": t2_id,
        "role": "MANAGER"
    })

    # Obtain JWT tokens
    def get_token(username, password="password123"):
        res = client.post("/auth/login", json={"username": username, "password": password})
        return res.json()["access_token"]

    tokens = {
        "alice": get_token("alice"),
        "bob": get_token("bob"),
        "manager1": get_token("manager1"),
        "charlie": get_token("charlie"),
        "manager2": get_token("manager2")
    }

    return {
        "t1_id": t1_id,
        "t2_id": t2_id,
        "tokens": tokens
    }


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# =========================================================================
# TEST 1: Normal Legitimate Workflow
# =========================================================================
def test_normal_legitimate_workflow():
    data = create_tenant_and_users()
    alice_tok = data["tokens"]["alice"]
    mgr1_tok = data["tokens"]["manager1"]

    # Alice creates order
    res_create = client.post(
        "/orders",
        json={"item_name": "Laptop", "amount": 1200},
        headers=auth_header(alice_tok)
    )
    assert res_create.status_code == 201
    order = res_create.json()
    order_id = order["id"]
    assert order["status"] == "CREATED"
    assert order["tenant_id"] == data["t1_id"]

    # Manager confirms order
    res_conf = client.post(
        f"/orders/{order_id}/confirm",
        headers=auth_header(mgr1_tok)
    )
    assert res_conf.status_code == 200
    assert res_conf.json()["status"] == "CONFIRMED"

    # Alice pays order
    res_pay = client.post(
        f"/orders/{order_id}/pay",
        headers=auth_header(alice_tok)
    )
    assert res_pay.status_code == 200
    assert res_pay.json()["status"] == "PAID"

    # Manager ships order
    res_ship = client.post(
        f"/orders/{order_id}/ship",
        headers=auth_header(mgr1_tok)
    )
    assert res_ship.status_code == 200
    assert res_ship.json()["status"] == "SHIPPED"

    # Manager delivers order
    res_deliv = client.post(
        f"/orders/{order_id}/deliver",
        headers=auth_header(mgr1_tok)
    )
    assert res_deliv.status_code == 200
    assert res_deliv.json()["status"] == "DELIVERED"

    # Verify event traces recorded for Alice's tenant
    events_res = client.get("/events", headers=auth_header(alice_tok))
    assert events_res.status_code == 200
    events = events_res.json()
    actions = [e["action"] for e in events]
    assert actions == ["CREATE", "CONFIRM", "PAY", "SHIP", "DELIVER"]
    for e in events:
        assert e["result"] == "ALLOW"
        assert e["tenant_id"] == data["t1_id"]
        assert e["resource_tenant_id"] == data["t1_id"]


# =========================================================================
# TEST 2: Cross-Tenant BOLA
# =========================================================================
def test_cross_tenant_bola():
    data = create_tenant_and_users()
    alice_tok = data["tokens"]["alice"]
    charlie_tok = data["tokens"]["charlie"]

    # Charlie (Tenant 2) creates an order
    r_charlie_order = client.post(
        "/orders",
        json={"item_name": "Tenant2 Secret Blueprint", "amount": 9999},
        headers=auth_header(charlie_tok)
    )
    assert r_charlie_order.status_code == 201
    t2_order_id = r_charlie_order.json()["id"]

    # --- SECURE BASELINE ---
    set_test_flags(test_mode=False, bola=False)
    res_sec = client.get(f"/orders/{t2_order_id}", headers=auth_header(alice_tok))
    assert res_sec.status_code == 403
    assert "cross-tenant" in res_sec.json()["detail"].lower()

    # --- BOLA TEST MODE ---
    set_test_flags(test_mode=True, bola=True)
    res_vuln = client.get(f"/orders/{t2_order_id}", headers=auth_header(alice_tok))
    assert res_vuln.status_code == 200
    assert res_vuln.json()["id"] == t2_order_id
    assert res_vuln.json()["tenant_id"] == data["t2_id"]

    # Verify Alice cannot see Charlie's event stream, maintaining /events isolation
    events_res = client.get("/events", headers=auth_header(alice_tok))
    assert events_res.status_code == 200
    alice_events = events_res.json()
    # Alice's tenant events should show the READ attempt with reason annotation
    bola_events = [e for e in alice_events if e["resource_id"] == t2_order_id]
    assert len(bola_events) >= 2
    assert bola_events[0]["result"] == "DENY"
    assert bola_events[0]["reason"] == "TENANT_ISOLATION_VIOLATION"
    assert bola_events[1]["result"] == "ALLOW"
    assert bola_events[1]["reason"] == "BOLA_TEST_OVERRIDE"
    assert bola_events[1]["resource_tenant_id"] == data["t2_id"]
    assert bola_events[1]["tenant_id"] == data["t1_id"]


# =========================================================================
# TEST 3: BFLA (Role Authorization Bypass)
# =========================================================================
def test_bfla_role_bypass():
    data = create_tenant_and_users()
    alice_tok = data["tokens"]["alice"]
    mgr1_tok = data["tokens"]["manager1"]

    # Alice creates order, manager confirms, alice pays
    res_create = client.post(
        "/orders",
        json={"item_name": "Phone", "amount": 800},
        headers=auth_header(alice_tok)
    )
    order_id = res_create.json()["id"]
    client.post(f"/orders/{order_id}/confirm", headers=auth_header(mgr1_tok))
    client.post(f"/orders/{order_id}/pay", headers=auth_header(alice_tok))

    # --- SECURE BASELINE: Customer tries to SHIP ---
    set_test_flags(test_mode=False, bfla=False)
    res_ship_sec = client.post(f"/orders/{order_id}/ship", headers=auth_header(alice_tok))
    assert res_ship_sec.status_code == 403
    assert "not permitted" in res_ship_sec.json()["detail"].lower()

    # --- BFLA TEST MODE: Customer tries to SHIP ---
    set_test_flags(test_mode=True, bfla=True)
    res_ship_vuln = client.post(f"/orders/{order_id}/ship", headers=auth_header(alice_tok))
    assert res_ship_vuln.status_code == 200
    assert res_ship_vuln.json()["status"] == "SHIPPED"

    # Verify event traces
    events_res = client.get("/events", headers=auth_header(alice_tok))
    events = events_res.json()
    ship_events = [e for e in events if e["action"] == "SHIP"]
    assert len(ship_events) == 2
    assert ship_events[0]["result"] == "DENY"
    assert ship_events[0]["reason"] == "ROLE_NOT_PERMITTED"
    assert ship_events[0]["role"] == "CUSTOMER"
    assert ship_events[1]["result"] == "ALLOW"
    assert ship_events[1]["reason"] == "BFLA_TEST_OVERRIDE"


# =========================================================================
# TEST 4: Workflow Violation (Invalid State Machine Transition)
# =========================================================================
def test_workflow_state_violation():
    data = create_tenant_and_users()
    alice_tok = data["tokens"]["alice"]

    # Alice creates order (status: CREATED)
    res_create = client.post(
        "/orders",
        json={"item_name": "Tablet", "amount": 500},
        headers=auth_header(alice_tok)
    )
    order_id = res_create.json()["id"]

    # --- SECURE BASELINE: Direct CREATED -> PAID bypass ---
    set_test_flags(test_mode=False, workflow=False)
    res_pay_sec = client.post(f"/orders/{order_id}/pay", headers=auth_header(alice_tok))
    assert res_pay_sec.status_code == 400
    assert "invalid transition" in res_pay_sec.json()["detail"].lower()

    # --- WORKFLOW TEST MODE: Direct CREATED -> PAID bypass ---
    set_test_flags(test_mode=True, workflow=True)
    res_pay_vuln = client.post(f"/orders/{order_id}/pay", headers=auth_header(alice_tok))
    assert res_pay_vuln.status_code == 200
    assert res_pay_vuln.json()["status"] == "PAID"

    # Verify event traces
    events_res = client.get("/events", headers=auth_header(alice_tok))
    events = events_res.json()
    wf_deny = [e for e in events if e["result"] == "DENY" and e["reason"] == "INVALID_STATE_TRANSITION"]
    wf_allow = [e for e in events if e["result"] == "ALLOW" and e["reason"] == "WORKFLOW_TEST_OVERRIDE"]
    assert len(wf_deny) == 1
    assert len(wf_allow) == 1
    assert wf_allow[0]["previous_state"] == "CREATED"
    assert wf_allow[0]["new_state"] == "PAID"


# =========================================================================
# TEST 5: Same-Tenant Contextual Ownership Violation
# =========================================================================
def test_contextual_ownership_violation():
    data = create_tenant_and_users()
    alice_tok = data["tokens"]["alice"]
    bob_tok = data["tokens"]["bob"]
    mgr1_tok = data["tokens"]["manager1"]

    # Bob creates and manager confirms Bob's order
    res_bob_order = client.post(
        "/orders",
        json={"item_name": "Bob's Watch", "amount": 300},
        headers=auth_header(bob_tok)
    )
    bob_order_id = res_bob_order.json()["id"]
    client.post(f"/orders/{bob_order_id}/confirm", headers=auth_header(mgr1_tok))

    # --- SECURE BASELINE: Alice (same tenant) attempts to pay Bob's order ---
    set_test_flags(test_mode=False, contextual=False)
    res_alice_pay_sec = client.post(f"/orders/{bob_order_id}/pay", headers=auth_header(alice_tok))
    assert res_alice_pay_sec.status_code == 403
    assert "only modify own orders" in res_alice_pay_sec.json()["detail"].lower()

    # --- CONTEXTUAL TEST MODE: Alice modifies Bob's order ---
    set_test_flags(test_mode=True, contextual=True)
    res_alice_pay_vuln = client.post(f"/orders/{bob_order_id}/pay", headers=auth_header(alice_tok))
    assert res_alice_pay_vuln.status_code == 200
    assert res_alice_pay_vuln.json()["status"] == "PAID"

    # Verify event traces demonstrate: actor tenant == resource tenant BUT actor != resource owner
    events_res = client.get("/events", headers=auth_header(alice_tok))
    events = events_res.json()
    ctx_events = [e for e in events if e["resource_id"] == bob_order_id and e["action"] == "PAY"]
    assert len(ctx_events) == 2
    assert ctx_events[0]["result"] == "DENY"
    assert ctx_events[0]["reason"] == "NOT_ORDER_OWNER"
    assert ctx_events[1]["result"] == "ALLOW"
    assert ctx_events[1]["reason"] == "CONTEXTUAL_TEST_OVERRIDE"
    # Key relational invariants
    assert ctx_events[1]["tenant_id"] == ctx_events[1]["resource_tenant_id"]
    assert ctx_events[1]["user_id"] != ctx_events[1]["resource_owner_id"]


# =========================================================================
# TEST 6: Vulnerability Isolation (Flags must not disable unrelated checks)
# =========================================================================
def test_vulnerability_isolation():
    data = create_tenant_and_users()
    alice_tok = data["tokens"]["alice"]
    mgr1_tok = data["tokens"]["manager1"]
    charlie_tok = data["tokens"]["charlie"]

    # Charlie creates order in Tenant 2
    r_c = client.post("/orders", json={"item_name": "T2 Order", "amount": 100}, headers=auth_header(charlie_tok))
    t2_order_id = r_c.json()["id"]

    # Enable BFLA test ONLY -> BOLA (cross-tenant) must STILL be blocked
    set_test_flags(test_mode=True, bfla=True, bola=False)
    r_bola_blocked = client.get(f"/orders/{t2_order_id}", headers=auth_header(alice_tok))
    assert r_bola_blocked.status_code == 403

    # Enable BOLA test ONLY -> Role authorization for SHIP must STILL be blocked on a PAID order
    r_a = client.post("/orders", json={"item_name": "T1 Order", "amount": 100}, headers=auth_header(alice_tok))
    t1_order_id = r_a.json()["id"]
    client.post(f"/orders/{t1_order_id}/confirm", headers=auth_header(mgr1_tok))
    client.post(f"/orders/{t1_order_id}/pay", headers=auth_header(alice_tok))

    set_test_flags(test_mode=True, bola=True, bfla=False)
    r_role_blocked = client.post(f"/orders/{t1_order_id}/ship", headers=auth_header(alice_tok))
    assert r_role_blocked.status_code == 403
    assert "not permitted" in r_role_blocked.json()["detail"].lower()

    # Enable Workflow test ONLY -> Tenant check must STILL be blocked
    set_test_flags(test_mode=True, workflow=True, bola=False)
    r_cross_blocked = client.post(f"/orders/{t2_order_id}/pay", headers=auth_header(alice_tok))
    assert r_cross_blocked.status_code == 403

    # Disable test mode completely -> Restores 100% secure baseline
    set_test_flags(test_mode=False)
    r_normal_blocked = client.get(f"/orders/{t2_order_id}", headers=auth_header(alice_tok))
    assert r_normal_blocked.status_code == 403
