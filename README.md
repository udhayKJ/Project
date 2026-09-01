# API Security Research Testbed

A lightweight FastAPI-based API prototype designed as a controlled research environment for studying **API authorization, multi-tenancy, workflow/state violations, and contextual API behavior**.

The API provides both a secure baseline and deliberately vulnerable variants. These controlled variants will later be used to generate API behavioral traces for the project's **compliance analysis and behavioral modeling research**.

> **Project Status:** API Prototype Complete
> **Purpose:** Research / Paper / Proof of Concept
> **Production Use:** Not intended

---

## 1. Project Objective

The purpose of this API is not to build a complete production application.

Instead, it acts as a **controlled API security testbed** where known-good and known-vulnerable behaviors can be generated and compared.

The API provides:

* Authentication
* Role-based authorization
* Multi-tenant isolation
* Resource ownership
* Order management
* Order workflow/state transitions
* API event logging
* Controlled vulnerable API variants

The generated API events will later serve as input to the project's compliance analysis system.

---

## 2. High-Level Architecture

```text
                         FastAPI
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
   Authentication     Authorization        Orders
          |                 |                 |
          |          +------+------+          |
          |          |      |      |          |
          |         Role   Tenant Ownership   |
          |                 |                 |
          +-----------------+-----------------+
                            |
                            v
                     Order State Machine
                            |
                            v
                       Event Logger
                            |
                            v
                       PostgreSQL
                            |
                            v
                       /events API
                            |
                            v
                  Research Analyzer
```

---

## 3. Technology Stack

| Technology        | Purpose                         |
| ----------------- | ------------------------------- |
| Python            | Primary programming language    |
| FastAPI           | REST API framework              |
| PostgreSQL        | Relational database             |
| SQLAlchemy        | ORM / database interaction      |
| Pydantic          | Request and response validation |
| JWT               | Authentication                  |
| Uvicorn           | ASGI server                     |
| Swagger / OpenAPI | API testing and documentation   |

The implementation is intentionally lightweight because the API is a **research prototype rather than the final research contribution**.

---

## 4. Project Structure

```text
app/
│
├── main.py
├── models.py
├── schemas.py
├── database.py
├── dependencies.py
├── order_logic.py
├── event_logger.py
```

### Main Components

#### `main.py`

Contains the FastAPI application and API routes.

#### `models.py`

Contains SQLAlchemy database models such as:

* User
* Tenant
* Resource
* Order
* APIEvent

#### `schemas.py`

Contains Pydantic request/response models.

#### `database.py`

Handles PostgreSQL connection and SQLAlchemy session management.

#### `dependencies.py`

Contains shared FastAPI dependencies such as:

* Database session
* Current authenticated user
* Authentication-related dependencies

#### `order_logic.py`

Contains the order state machine and authorization logic.

#### `event_logger.py`

Records API actions into the `api_events` table.

#### `vulnerabilities/`

Contains deliberately vulnerable implementations used for controlled security experiments.

---

# 5. Authentication

The API uses JWT-based authentication.

The basic flow is:

```text
User
 |
 | Login
 v
/auth/login
 |
 v
JWT
 |
 v
Authenticated API requests
```

The JWT identifies the authenticated user.

The user's database record provides additional security context such as:

```text
User ID
Role
Tenant ID
```

---

# 6. Multi-Tenancy

Each user belongs to a tenant.

Example:

```text
Tenant 1
├── Alice
└── Bob

Tenant 2
├── Charlie
└── David
```

Resources and orders are associated with a tenant.

The secure API prevents users from accessing resources belonging to another tenant.

For example:

```text
Alice
Tenant 1
   |
   X
   |
Order 42
Tenant 2

       ↓

    DENIED
```

This provides the foundation for testing **cross-tenant authorization violations**.

---

# 7. Role-Based Authorization

The prototype uses roles such as:

```text
CUSTOMER
MANAGER
ADMIN
```

Different roles have different permissions.

Example:

| Action        | CUSTOMER | MANAGER | ADMIN |
| ------------- | -------: | ------: | ----: |
| Create Order  |      Yes |     Yes |   Yes |
| Confirm Order |       No |     Yes |   Yes |
| Pay Order     |      Yes |     Yes |   Yes |
| Ship Order    |       No |     Yes |   Yes |
| Deliver Order |       No |     Yes |   Yes |
| Cancel Order  |      Own |     Yes |   Yes |

The exact authorization rules are configurable and primarily exist to generate controlled behavioral scenarios.

---

# 8. Resource Ownership

Orders contain an owner:

```text
Order
├── owner_id
└── tenant_id
```

For customers, ownership is part of the authorization decision.

For example:

```text
Alice
CUSTOMER
Tenant 1
       |
       v
Alice's Order
       |
       v
    ALLOW
```

but:

```text
Alice
CUSTOMER
Tenant 1
       |
       v
Bob's Order
       |
       v
    DENY
```

This allows the prototype to test authorization decisions that depend on more than a user's role.

---

# 9. Order Management

The API provides the following order endpoints.

### Create Order

```http
POST /orders
```

Example:

```json
{
  "item_name": "Laptop",
  "amount": 50000
}
```

Security-sensitive fields such as:

```text
owner_id
tenant_id
status
```

are determined by the server rather than supplied by the client.

---

### List Orders

```http
GET /orders
```

Returns orders belonging to the authenticated user's tenant.

---

### Get Order

```http
GET /orders/{order_id}
```

The secure implementation checks tenant isolation before returning the order.

---

# 10. Order State Machine

Orders follow a predefined workflow.

```text
CREATED
   |
   +----> CONFIRMED
   |          |
   |          +----> PAID
   |                   |
   |                   +----> SHIPPED
   |                              |
   |                              +----> DELIVERED
   |
   +----> CANCELLED
```

Valid transitions include:

```text
CREATED    → CONFIRMED
CREATED    → CANCELLED

CONFIRMED  → PAID
CONFIRMED  → CANCELLED

PAID       → SHIPPED

SHIPPED    → DELIVERED
```

Invalid transitions are rejected.

For example:

```text
CREATED → PAID
CREATED → SHIPPED
PAID → CREATED
DELIVERED → PAID
```

These state constraints allow the system to generate **workflow-level behavioral traces**.

---

# 11. State Transition API

```http
POST /orders/{order_id}/transition
```

Example:

```json
{
  "new_status": "CONFIRMED"
}
```

The secure implementation evaluates:

```text
Authenticated User
        |
        +-- Tenant?
        |
        +-- Role?
        |
        +-- Ownership?
        |
        +-- Current State?
        |
        +-- Valid Transition?
        |
        v
     Decision
```

This is an important part of the research testbed because authorization and workflow state can influence the same API action.

---

# 12. API Event Logging

The API records important interactions in the `api_events` table.

A conceptual event contains:

```text
User
Tenant
Action
Resource Type
Resource ID
Previous State
New State
Result
```

Example:

```json
{
  "user_id": 1,
  "tenant_id": 1,
  "action": "PAY",
  "resource_type": "ORDER",
  "resource_id": 10,
  "previous_state": "CONFIRMED",
  "new_state": "PAID",
  "result": "ALLOW"
}
```

Denied operations are also recorded.

Example:

```json
{
  "user_id": 1,
  "tenant_id": 1,
  "action": "INVALID_TRANSITION",
  "resource_type": "ORDER",
  "resource_id": 10,
  "previous_state": "CREATED",
  "new_state": "PAID",
  "result": "DENY"
}
```

---

# 13. Event Inspection

Events can be inspected through:

```http
GET /events
```

The endpoint is primarily intended for research and debugging.

The resulting event stream will eventually be used by the compliance analysis component.

Conceptually:

```text
API Requests
     |
     v
API Events
     |
     v
Contextual Representation
     |
     v
Behavioral Analysis
```

---
# 14. Experimental Test Matrix

| Scenario                               | Secure API | Vulnerable API | Expected Finding     |
| -------------------------------------- | ---------- | -------------- | -------------------- |
| User accesses own order                | Allow      | Allow          | Normal               |
| Cross-tenant order access              | Deny       | Allow          | BOLA                 |
| Customer performs restricted function  | Deny       | Allow          | BFLA                 |
| Invalid state transition               | Deny       | Allow          | Workflow violation   |
| Customer modifies another user's order | Deny       | Allow          | Contextual violation |

---

# 17. Research Purpose

The API itself is **not the primary research contribution**.

It exists to generate realistic behavioral traces containing information such as:

```text
Actor
Role
Tenant
Resource
Ownership
Action
Previous State
New State
Result
```

These traces will later be transformed into a contextual behavioral representation.

The planned research pipeline is:

```text
                 FastAPI
                    |
                    v
              API Interaction
                    |
                    v
              Event Logging
                    |
                    v
          Contextual Event Model
                    |
                    v
          Behavioral/State Model
                    |
                    v
          Compliance Analyzer
                    |
                    v
           Violation Detection
```

---

# 18. Current Scope

The API prototype intentionally focuses on:

* Authentication
* Authorization
* Multi-tenancy
* Ownership
* Stateful resources
* Workflow validation
* Event generation
* Controlled vulnerabilities

The following are outside the current API scope:

* Frontend application
* Production deployment
* Distributed architecture
* Advanced monitoring
* Cloud infrastructure
* LLM-based security analysis
* High-scale performance optimization

---

# 20. Next Stage

The next stage is **not to add more API functionality**.

The next stage is to build the research layer:

```text
API Events
     |
     v
Event Normalization
     |
     v
Contextual Representation
     |
     v
Behavioral Model
     |
     v
Compliance Analysis
     |
     v
Violation Classification
     |
     v
Experimental Evaluation
```

The main research questions will be:

1. Can contextual API events represent meaningful API behavior?
2. Can expected API behavior be modeled from these events?
3. Can deviations from the model identify security/compliance violations?
4. Can the system distinguish different types of violations?
5. Can the approach detect violations that are difficult to identify from individual requests alone?

The results from these experiments will form the primary technical basis of the research paper and help determine which aspects, if any, provide a sufficiently novel basis for future patent claims.
