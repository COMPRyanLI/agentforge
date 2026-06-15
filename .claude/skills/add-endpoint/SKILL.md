---
name: add-endpoint
description: Scaffold a new FastAPI endpoint end-to-end following the project's layered architecture. Use when adding any new HTTP route (agents, tools, runs, marketplace, auth). Produces router + service + repository + Pydantic schemas + tests.
---

# Add Endpoint

Given a description of an endpoint (method, path, purpose), implement it across every layer.
Ask for the method/path/auth requirement if not provided.

Produce, in this order (test-first):

1. **Pydantic schemas** in `app/schemas/` — request body and response models (Pydantic v2,
   fully typed). Never expose SQLAlchemy models directly.

2. **Repository method** in `app/repositories/` — the only place DB access happens. Async,
   typed, takes/returns domain models. No business logic here.

3. **Service method** in `app/services/` — business logic, validation, authorization checks,
   orchestration. Calls repositories; raises typed domain exceptions mapped to HTTP errors.

4. **Router** in `app/routers/` — thin. Declares the route, injects the auth dependency and
   DB session, validates via the Pydantic schema, calls the service, returns the response
   schema. No DB access, no business logic.

5. **Tests** in `backend/tests/`:
   - a unit test for the service (mock the repository), covering the happy path + one failure
     (e.g. not found, unauthorized);
   - an integration test hitting the route through `httpx.AsyncClient` against a real test
     Postgres, asserting status code and response shape.

Then run `/checks`. If a DB model was added/changed, generate an Alembic migration.

Constraints: respect `routers → services → repositories` layering, keep everything async and
fully typed (`mypy --strict`), and enforce ownership/auth in the service layer, not the router.
