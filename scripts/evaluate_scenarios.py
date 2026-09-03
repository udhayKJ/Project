"""
Scenario Evaluation & Ground Truth Demonstration Script for API Security Research Testbed.

Demonstrates:
1. Ground truth separation (NONE, BOLA, BFLA, WORKFLOW, CONTEXTUAL)
2. Execution across secure mode and vulnerability test modes
3. Comparison of HTTP outcomes and contextual event traces generated in PostgreSQL
"""
import sys
import os
import json

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.database import engine, Base
from app.config import settings

client = TestClient(app)


def reset_environment():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    settings.TEST_MODE = False
    settings.ENABLE_BOLA_TEST = False
    settings.ENABLE_BFLA_TEST = False
    settings.ENABLE_WORKFLOW_TEST = False
    settings.ENABLE_CONTEXTUAL_TEST = False


def setup_fixtures():
    # Tenants
    r_t1 = client.post("/tenants", json={"name": "Org 1"}).json()
    r_t2 = client.post("/tenants", json={"name": "Org 2"}).json()
    t1_id, t2_id = r_t1["id"], r_t2["id"]

    # Users
    client.post("/users", json={"username": "alice", "email": "alice@org1.com", "password": "password123", "tenant_id": t1_id, "role": "CUSTOMER"})
    client.post("/users", json={"username": "bob", "email": "bob@org1.com", "password": "password123", "tenant_id": t1_id, "role": "CUSTOMER"})
    client.post("/users", json={"username": "manager1", "email": "mgr1@org1.com", "password": "password123", "tenant_id": t1_id, "role": "MANAGER"})
    client.post("/users", json={"username": "charlie", "email": "charlie@org2.com", "password": "password123", "tenant_id": t2_id, "role": "CUSTOMER"})

    # Tokens
    def tok(u):
        return client.post("/auth/login", json={"username": u, "password": "password123"}).json()["access_token"]

    tokens = {u: tok(u) for u in ["alice", "bob", "manager1", "charlie"]}
    return {"t1_id": t1_id, "t2_id": t2_id, "tokens": tokens}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def run_evaluation():
    print("=" * 80)
    print("API SECURITY RESEARCH TESTBED: EXPERIMENTAL SCENARIO EVALUATION")
    print("=" * 80)

    reset_environment()
    fixtures = setup_fixtures()
    alice_tok = fixtures["tokens"]["alice"]
    bob_tok = fixtures["tokens"]["bob"]
    mgr1_tok = fixtures["tokens"]["manager1"]
    charlie_tok = fixtures["tokens"]["charlie"]

    scenarios = [
        {
            "id": 1,
            "name": "Normal Legitimate Behavior (Alice pays own confirmed order)",
            "ground_truth": "NONE",
            "setup": lambda: _setup_scenario_1(alice_tok, mgr1_tok),
            "test_flag": ("NONE", None),
        },
        {
            "id": 2,
            "name": "Cross-Tenant BOLA (Alice accesses Charlie's Tenant 2 order)",
            "ground_truth": "BOLA",
            "setup": lambda: _setup_scenario_2(charlie_tok),
            "test_flag": ("ENABLE_BOLA_TEST", "bola"),
        },
        {
            "id": 3,
            "name": "BFLA - Broken Function Level Authorization (Customer Alice attempts SHIP)",
            "ground_truth": "BFLA",
            "setup": lambda: _setup_scenario_3(alice_tok, mgr1_tok),
            "test_flag": ("ENABLE_BFLA_TEST", "bfla"),
        },
        {
            "id": 4,
            "name": "Workflow State Machine Violation (Direct CREATED -> PAID bypass)",
            "ground_truth": "WORKFLOW",
            "setup": lambda: _setup_scenario_4(alice_tok),
            "test_flag": ("ENABLE_WORKFLOW_TEST", "workflow"),
        },
        {
            "id": 5,
            "name": "Same-Tenant Contextual Ownership Violation (Alice modifies Bob's order)",
            "ground_truth": "CONTEXTUAL",
            "setup": lambda: _setup_scenario_5(bob_tok, mgr1_tok),
            "test_flag": ("ENABLE_CONTEXTUAL_TEST", "contextual"),
        }
    ]

    for sc in scenarios:
        print(f"\n--- Scenario {sc['id']}: {sc['name']} ---")
        print(f"Experimental Ground Truth: [ {sc['ground_truth']} ] (Note: Separate from analyzer event stream)")
        
        target_info = sc["setup"]()
        action_fn = target_info["action_fn"]

        # Run in Secure Baseline Mode
        settings.TEST_MODE = False
        settings.ENABLE_BOLA_TEST = False
        settings.ENABLE_BFLA_TEST = False
        settings.ENABLE_WORKFLOW_TEST = False
        settings.ENABLE_CONTEXTUAL_TEST = False

        sec_status, sec_body = action_fn()
        print(f"  [Secure Mode]  HTTP Status: {sec_status} | Response: {sec_body.get('status') or sec_body.get('detail')}")

        # Run in Vulnerability Test Mode (if applicable)
        flag_name, flag_key = sc["test_flag"]
        if flag_key:
            settings.TEST_MODE = True
            setattr(settings, f"ENABLE_{flag_key.upper()}_TEST", True)
            test_status, test_body = action_fn()
            print(f"  [Test Mode ({flag_name}=true)] HTTP Status: {test_status} | Response: {test_body.get('status') or test_body.get('detail')}")
            # Reset flags
            setattr(settings, f"ENABLE_{flag_key.upper()}_TEST", False)
            settings.TEST_MODE = False

    # Inspect generated events from Alice's Tenant
    print("\n" + "=" * 80)
    print("CONTEXTUAL EVENT STREAM SAMPLE (TENANT 1 - What the research analyzer receives):")
    print("=" * 80)
    res_events = client.get("/events", headers=auth(alice_tok)).json()
    for ev in res_events[-6:]:
        print(json.dumps({
            "event_id": ev["id"],
            "timestamp": ev["timestamp"],
            "actor": {"user_id": ev["user_id"], "role": ev["role"], "tenant_id": ev["tenant_id"]},
            "action": ev["action"],
            "resource": {"type": ev["resource_type"], "id": ev["resource_id"], "owner_id": ev["resource_owner_id"], "tenant_id": ev["resource_tenant_id"]},
            "state_transition": f"{ev['previous_state']} -> {ev['new_state']}",
            "result": ev["result"],
            "reason": ev["reason"]
        }, indent=2))

    print("\nEvaluation complete. Ground truth is isolated from analyzer stream.")


def _setup_scenario_1(alice_tok, mgr1_tok):
    order = client.post("/orders", json={"item_name": "Item1", "amount": 100}, headers=auth(alice_tok)).json()
    client.post(f"/orders/{order['id']}/confirm", headers=auth(mgr1_tok))
    return {
        "action_fn": lambda: (
            lambda r: (r.status_code, r.json())
        )(client.post(f"/orders/{order['id']}/pay", headers=auth(alice_tok)))
    }


def _setup_scenario_2(charlie_tok):
    order = client.post("/orders", json={"item_name": "T2 Confidential Item", "amount": 500}, headers=auth(charlie_tok)).json()
    return {
        "action_fn": lambda: (
            lambda r: (r.status_code, r.json())
        )(client.get(f"/orders/{order['id']}", headers=auth(client.post("/auth/login", json={"username": "alice", "password": "password123"}).json()["access_token"])))
    }


def _setup_scenario_3(alice_tok, mgr1_tok):
    order = client.post("/orders", json={"item_name": "Item3", "amount": 300}, headers=auth(alice_tok)).json()
    client.post(f"/orders/{order['id']}/confirm", headers=auth(mgr1_tok))
    client.post(f"/orders/{order['id']}/pay", headers=auth(alice_tok))
    return {
        "action_fn": lambda: (
            lambda r: (r.status_code, r.json())
        )(client.post(f"/orders/{order['id']}/ship", headers=auth(alice_tok)))
    }


def _setup_scenario_4(alice_tok):
    order = client.post("/orders", json={"item_name": "Item4", "amount": 400}, headers=auth(alice_tok)).json()
    # Order is in CREATED state, attempt immediate transition to PAID
    return {
        "action_fn": lambda: (
            lambda r: (r.status_code, r.json())
        )(client.post(f"/orders/{order['id']}/pay", headers=auth(alice_tok)))
    }


def _setup_scenario_5(bob_tok, mgr1_tok):
    order = client.post("/orders", json={"item_name": "Bob's Personal Item", "amount": 700}, headers=auth(bob_tok)).json()
    client.post(f"/orders/{order['id']}/confirm", headers=auth(mgr1_tok))
    alice_tok = client.post("/auth/login", json={"username": "alice", "password": "password123"}).json()["access_token"]
    return {
        "action_fn": lambda: (
            lambda r: (r.status_code, r.json())
        )(client.post(f"/orders/{order['id']}/pay", headers=auth(alice_tok)))
    }


if __name__ == "__main__":
    run_evaluation()
