# API Security Research Testbed

A lightweight, configuration-driven FastAPI + PostgreSQL API testbed designed as a controlled research environment for studying **API authorization, multi-tenancy, workflow/state violations, and contextual API behavioral analysis**.

> **Project Framing:** This system is **a controlled API testbed for generating contextual API behavior traces for research into behavioral/state-model-based API security analysis**. The API itself is not the final research contribution; it serves as the baseline environment that produces rich, multi-dimensional event traces for downstream learning and automated compliance analysis.

---

## 1. Project Objective

The objective of this project is to provide a single, realistic API with a secure baseline and configuration-driven controlled vulnerabilities.

Instead of building multiple disparate APIs or exposing separate `/vulnerable/...` endpoints, this testbed allows researchers to toggle specific behavioral weaknesses (BOLA, BFLA, Workflow state bypasses, Contextual ownership violations) on the **exact same normal endpoints** via server-side configuration.

Key principles:
- **Single Unified API**: The same endpoint structure is used across secure and test scenarios.
- **Secure by Default**: Without explicit test flags, the API strictly enforces tenant isolation, role authorization, resource ownership, and workflow state transitions.
- **Rich Contextual Event Stream**: Captures actor context, resource ownership, state changes, and decision outcomes (both `ALLOW` and `DENY`).
- **Ground-Truth Decoupling**: Vulnerability configurations serve as experimental ground truth and are kept completely separate from the event stream consumed by future behavioral analyzers.

---

## 2. Architecture

```
                          ┌───────────────────────────┐
                          │    Single FastAPI App     │
                          │   (Standard Endpoints)    │
                          └─────────────┬─────────────┘
                                        │
                          ┌─────────────▼─────────────┐
                          │    JWT Authentication     │
                          │ (User ID, Role, Tenant ID)│
                          └─────────────┬─────────────┘
                                        │
                          ┌─────────────▼─────────────┐
                          │   Business & Auth Logic   │
                          │ ┌───────────────────────┐ │
                          │ │ 1. Tenant Check       │ │
                          │ │ 2. Workflow Check     │ │
                          │ │ 3. Role (RBAC) Check  │ │
                          │ │ 4. Ownership Check    │ │
                          │ └───────────────────────┘ │
                          └─────────────┬─────────────┘
                                        │
                   ┌────────────────────┴────────────────────┐
                   ▼                                         ▼
   ┌───────────────────────────────┐         ┌───────────────────────────────┐
   │         Secure Mode           │         │     Test Mode Overrides       │
   │      (TEST_MODE=false)        │         │      (TEST_MODE=true)         │
   │  - Strict Tenant Isolation    │         │  - ENABLE_BOLA_TEST           │
   │  - Strict Workflow Logic      │         │  - ENABLE_BFLA_TEST           │
   │  - Strict Role Permissions    │         │  - ENABLE_WORKFLOW_TEST       │
   │  - Strict Ownership Rules     │         │  - ENABLE_CONTEXTUAL_TEST     │
   └───────────────┬───────────────┘         └───────────────┬───────────────┘
                   │                                         │
                   └────────────────────┬────────────────────┘
                                        │
                          ┌─────────────▼─────────────┐
                          │   Contextual Event Logger │
                          │(Actor, Resource, States,  │
                          │ Result: ALLOW/DENY)       │
                          └─────────────┬─────────────┘
                                        │
                          ┌─────────────▼─────────────┐
                          │   PostgreSQL Database     │
                          │ (api_events, orders, etc.)│
                          └─────────────┬─────────────┘
                                        │
                                        ▼
                         /events Endpoint (Per Tenant)
                                        │
                                        ▼
                          Future Research Analyzer
```

---

## 3. Technology Stack

| Technology | Purpose |
| :--- | :--- |
| **Python 3.10+** | Core runtime environment |
| **FastAPI** | High-performance asynchronous REST API framework |
| **PostgreSQL** | Relational database for persistent storage and event logging |
| **SQLAlchemy 2.0** | ORM and relational mapping |
| **Pydantic V2** | Request/response data validation and schema serialization |
| **PyJWT & pwdlib** | Cryptographic token issuance (JWT) and secure password hashing (Argon2) |
| **Uvicorn** | Production-ready ASGI web server |
| **Pytest & HTTPX** | Automated test matrix and evaluation harness |

---

## 4. Authentication

Authentication is handled via industry-standard JSON Web Tokens (JWT):

1. **Login Endpoint**: `POST /auth/login` accepts `{"username": "...", "password": "..."}` and returns a signed bearer token.
2. **Token Content**: Encodes subject (`sub` = user ID) and expiration timestamp.
3. **Security Context**: Resolves into an authenticated user context exposing:
   - `user_id` (Integer)
   - `role` (`CUSTOMER`, `MANAGER`, `ADMIN`)
   - `tenant_id` (Integer)
4. **Current User Endpoint**: `GET /users/me` returns the authenticated identity and tenant binding.

---

## 5. Multi-Tenancy

The API enforces strict multi-tenant isolation:
- A **Tenant** represents an organization or isolated security boundary.
- Multiple users with different roles can belong to the same tenant.
- All primary business resources (`Order`, `Resource`) and operational logs (`APIEvent`) are tagged with `tenant_id`.

Example hierarchy:
```text
Tenant 1 (Org 1)
 ├── Alice (CUSTOMER)
 ├── Bob   (CUSTOMER)
 └── Manager1 (MANAGER)

Tenant 2 (Org 2)
 ├── Charlie (CUSTOMER)
 └── Manager2 (MANAGER)
```

In baseline secure mode, users cannot read, modify, or list resources belonging to another tenant under any circumstances.

---

## 6. Role-Based Access Control (RBAC)

The system supports three distinct hierarchical roles:

| Action | CUSTOMER | MANAGER | ADMIN | Description |
| :--- | :---: | :---: | :---: | :--- |
| **CREATE** | Yes | Yes | Yes | Create a new order |
| **CONFIRM** | No | Yes | Yes | Confirm an order from `CREATED` state |
| **PAY** | Yes (Own) | Yes | Yes | Pay for a confirmed order |
| **SHIP** | No | Yes | Yes | Ship a paid order |
| **DELIVER** | No | Yes | Yes | Mark a shipped order as delivered |
| **CANCEL** | Yes (Own) | Yes | Yes | Cancel an order before shipment |

---

## 7. Resource Ownership

Ownership introduces a contextual dimension beyond coarse-grained role permissions:
- Each order tracks `owner_id` (the customer who created the order) and `tenant_id`.
- Even within the same tenant, a `CUSTOMER` is only permitted to operate on orders they own:
  ```text
  Alice (CUSTOMER, Tenant 1) -> Alice's Order (Tenant 1) => ALLOW
  Alice (CUSTOMER, Tenant 1) -> Bob's Order   (Tenant 1) => DENY (403 Forbidden)
  ```
- Managers and Admins possess organizational authority across their tenant's orders.

---

## 8. Order State Machine

The lifecycle of an order adheres to a strict finite-state workflow:

```text
CREATED
  ├──> CONFIRMED ──> PAID ──> SHIPPED ──> DELIVERED (Terminal)
  └──> CANCELLED (Terminal)
```

### Transition & Action Mapping
```python
VALID_TRANSITIONS = {
    "CREATED": ["CONFIRMED", "CANCELLED"],
    "CONFIRMED": ["PAID", "CANCELLED"],
    "PAID": ["SHIPPED"],
    "SHIPPED": ["DELIVERED"],
    "DELIVERED": [],
    "CANCELLED": []
}

STATE_ACTIONS = {
    ("CREATED", "CONFIRMED"): "CONFIRM",
    ("CREATED", "CANCELLED"): "CANCEL",
    ("CONFIRMED", "PAID"): "PAY",
    ("CONFIRMED", "CANCELLED"): "CANCEL",
    ("PAID", "SHIPPED"): "SHIP",
    ("SHIPPED", "DELIVERED"): "DELIVER"
}
```

Any attempt to skip steps (e.g., `CREATED -> PAID` or `PAID -> DELIVERED`) is rejected in secure mode with `400 Bad Request`.

---

## 9. Event Logging & Contextual Event Schema

Every API interaction is recorded in the `api_events` table to supply high-fidelity behavioral data for research.

### Contextual Fields Logged
- `id`: Event ID
- `timestamp`: UTC ISO timestamp
- `user_id`: Acting user ID
- `role`: Acting user role (`CUSTOMER`, `MANAGER`, `ADMIN`)
- `tenant_id`: Acting user organization ID
- `action`: API action name (`CREATE`, `READ`, `CONFIRM`, `PAY`, `SHIP`, `DELIVER`, `CANCEL`)
- `resource_type`: Resource type (`ORDER`, `RESOURCE`)
- `resource_id`: Identifier of targeted resource
- `resource_owner_id`: User ID of the resource owner
- `resource_tenant_id`: Tenant ID of the resource
- `previous_state`: Prior state before transition (or `null`)
- `new_state`: Resulting state after transition (or target state attempted)
- `result`: Outcome (`ALLOW` or `DENY`)
- `reason`: Machine-readable reason tag (`SUCCESS`, `TENANT_ISOLATION_VIOLATION`, `ROLE_NOT_PERMITTED`, `NOT_ORDER_OWNER`, `INVALID_STATE_TRANSITION`, `BOLA_TEST_OVERRIDE`, etc.)

### Logging Denied Attempts
Denied attempts are logged prior to raising HTTP errors. This allows downstream research models to observe attack attempts, brute-force probes, and policy violations.

---

## 10. Configuration-Driven Test Mode

Vulnerabilities are controlled entirely through local configuration / environment variables. No bypass query parameters (`?bypass_auth=true`) or backdoor endpoints exist.

```env
# Master switch
TEST_MODE=false

# Specific vulnerability flags (Active only when TEST_MODE=true)
ENABLE_BOLA_TEST=false
ENABLE_BFLA_TEST=false
ENABLE_WORKFLOW_TEST=false
ENABLE_CONTEXTUAL_TEST=false
```

When `TEST_MODE=false`, all flags are ignored and the system operates in full secure baseline mode.

---

## 11. Controlled Vulnerability #1 — BOLA (Broken Object Level Authorization)

- **Target**: Cross-tenant resource access (`GET /orders/{id}`, `POST /orders/{id}/transition`).
- **Secure Mode**: User from Tenant 1 attempting to access an order from Tenant 2 is rejected (`403 Forbidden`).
- **Test Mode (`ENABLE_BOLA_TEST=true`)**: Tenant isolation check is bypassed on the target order. Request succeeds (`200 OK`).
- **Contextual Evidence**: Event stream shows `actor.tenant_id != resource.resource_tenant_id` with `result="ALLOW"`.

---

## 12. Controlled Vulnerability #2 — BFLA (Broken Function Level Authorization)

- **Target**: Restricted administrative/managerial actions (e.g. `POST /orders/{id}/ship`).
- **Secure Mode**: `CUSTOMER` attempting to execute `SHIP` is rejected (`403 Forbidden`).
- **Test Mode (`ENABLE_BFLA_TEST=true`)**: Role authorization check is bypassed. Request succeeds (`200 OK`).
- **Contextual Evidence**: Event stream shows `actor.role="CUSTOMER"` performing `action="SHIP"` with `result="ALLOW"`.

---

## 13. Controlled Vulnerability #3 — Workflow Violation

- **Target**: Finite state machine transitions (`POST /orders/{id}/transition`).
- **Secure Mode**: Attempting an illegal skip transition (e.g. `CREATED -> PAID` or `CREATED -> SHIPPED`) is rejected (`400 Bad Request`).
- **Test Mode (`ENABLE_WORKFLOW_TEST=true`)**: State machine transition validation is bypassed. Order status transitions directly.
- **Contextual Evidence**: Event stream shows invalid `previous_state` to `new_state` transition with `result="ALLOW"`.

---

## 14. Controlled Vulnerability #4 — Contextual Authorization Violation

- **Target**: Same-tenant resource ownership (`POST /orders/{id}/pay` or `/transition`).
- **Secure Mode**: Alice (`CUSTOMER`, Tenant 1) attempting to pay Bob's order (`CUSTOMER`, Tenant 1) is rejected (`403 Forbidden`).
- **Test Mode (`ENABLE_CONTEXTUAL_TEST=true`)**: Ownership check is bypassed while tenant check remains active. Request succeeds (`200 OK`).
- **Contextual Evidence**: Event stream shows `actor.tenant_id == resource.resource_tenant_id` but `actor.user_id != resource.resource_owner_id` with `result="ALLOW"`.

---

## 15. Test Matrix

| Scenario | Actor & Action | Secure Mode | Vulnerability Test Mode | Ground Truth |
| :--- | :--- | :---: | :---: | :---: |
| **1. Normal Legitimate** | Alice pays own confirmed order | `200 ALLOW` | `200 ALLOW` | `NONE` |
| **2. Cross-Tenant BOLA** | Alice accesses Tenant 2 order | `403 DENY` | `200 ALLOW` | `BOLA` |
| **3. BFLA** | Customer Alice executes SHIP | `403 DENY` | `200 ALLOW` | `BFLA` |
| **4. Workflow Bypass** | Alice transitions `CREATED -> PAID` | `400 DENY` | `200 ALLOW` | `WORKFLOW` |
| **5. Contextual Ownership** | Alice modifies same-tenant Bob's order | `403 DENY` | `200 ALLOW` | `CONTEXTUAL` |

---

## 16. Ground-Truth Separation

Experimental ground truth (`NONE`, `BOLA`, `BFLA`, `WORKFLOW`, `CONTEXTUAL`) is strictly separated from the data given to future behavioral analyzers:
- Test configuration flags are never returned in HTTP responses.
- Ground-truth labels are not stored in the `api_events` table consumed by the analyzer.
- The downstream research system must independently infer anomalies solely from observed event streams and relational metadata.

---

## 17. How to Run in Secure Mode

1. Ensure `.env` is configured for secure defaults:
   ```env
   TEST_MODE=false
   ENABLE_BOLA_TEST=false
   ENABLE_BFLA_TEST=false
   ENABLE_WORKFLOW_TEST=false
   ENABLE_CONTEXTUAL_TEST=false
   ```
2. Start the API server:
   ```powershell
   .\venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

---

## 18. How to Run Each Experiment

To run a specific controlled experiment, modify `.env` or set environment variables before starting the server:

### Experiment 1: Cross-Tenant BOLA
```env
TEST_MODE=true
ENABLE_BOLA_TEST=true
ENABLE_BFLA_TEST=false
ENABLE_WORKFLOW_TEST=false
ENABLE_CONTEXTUAL_TEST=false
```

### Experiment 2: BFLA (Privilege Escalation)
```env
TEST_MODE=true
ENABLE_BOLA_TEST=false
ENABLE_BFLA_TEST=true
ENABLE_WORKFLOW_TEST=false
ENABLE_CONTEXTUAL_TEST=false
```

### Experiment 3: Workflow Bypass
```env
TEST_MODE=true
ENABLE_BOLA_TEST=false
ENABLE_BFLA_TEST=false
ENABLE_WORKFLOW_TEST=true
ENABLE_CONTEXTUAL_TEST=false
```

### Experiment 4: Same-Tenant Ownership Violation
```env
TEST_MODE=true
ENABLE_BOLA_TEST=false
ENABLE_BFLA_TEST=false
ENABLE_WORKFLOW_TEST=false
ENABLE_CONTEXTUAL_TEST=true
```

---

## 19. How to Inspect Events

Inspect logged events via `GET /events` with an authenticated Bearer token:

```http
GET /events HTTP/1.1
Host: localhost:8000
Authorization: Bearer <JWT_TOKEN>
```

### Optional Query Filters:
- `action`: Filter by action (e.g. `?action=SHIP`)
- `resource_type`: Filter by resource (e.g. `?resource_type=ORDER`)
- `result`: Filter by outcome (e.g. `?result=DENY`)
- `user_id`: Filter by actor (e.g. `?user_id=1`)

---

## 20. What the API Provides to the Later Research Layer

The event logs produced by this testbed provide the relational and temporal foundation for the subsequent research stage:

```text
Actor (Who?) ───────► user_id, role, tenant_id
Target (What?) ─────► resource_type, resource_id, owner_id, resource_tenant_id
Operation (How?) ───► action, previous_state -> new_state
Decision (Outcome) ─► ALLOW / DENY, reason
Timing (When?) ─────► timestamp
```

This rich contextual stream will enable downstream automaton learning, probabilistic relational modeling, and contextual anomaly detectors to discover complex vulnerabilities that cannot be detected by syntax or static inspection alone.

---

## Verification & Automated Test Suite

Run the full automated test matrix suite:
```powershell
.\venv\Scripts\python -m pytest tests/test_api_matrix.py -v
```

Run the scenario evaluation and ground-truth demonstration:
```powershell
.\venv\Scripts\python scripts/evaluate_scenarios.py
```

Reset the database schema:
```powershell
.\venv\Scripts\python scripts/reset_db.py
```
