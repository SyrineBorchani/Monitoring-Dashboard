# TESTING_STRATEGY

Generated on 2026-08-04 from the current codebase and test suite.

## Goal

Provide a project-specific testing approach for the Power BI monitoring service and dashboard, aligned with the actual architecture, business logic, technologies, and risk areas in this repository.

## Architecture Summary

This project is a layered FastAPI application with:

- configuration loading in `App/config.py`
- SQLAlchemy + PostgreSQL persistence in `App/database.py`, `App/models.py`, `App/storage.py`
- external Microsoft Entra / Power BI integration in `App/auth.py` and `App/powerbi_client.py`
- business logic and monitoring derivation in `App/analytics.py`
- API orchestration in `App/routes/powerbi.py`
- static dashboard UI in `App/static/*`

The two highest-risk areas are:

- analytics and incident derivation logic
- PostgreSQL-specific persistence behavior

## Dependency Boundary Matrix

This matrix focuses on external dependencies and the way the application integrates with them. It does not test third-party libraries internally.

| Dependency | Used in | Critical integration points | Automated approach | Real environment testing still needed |
| --- | --- | --- | --- | --- |
| Microsoft Entra token endpoint via `requests` | `App/auth.py` | token URL construction, client credentials form payload, timeout, token caching, force refresh, malformed token responses | mocked boundary tests in `tests/test_auth.py` | validate real tenant credentials, permission scopes, secret rotation, and tenant policy behavior |
| Power BI REST API via `requests` | `App/powerbi_client.py`, `App/routes/powerbi.py` | bearer auth header, request path formatting, query params, 401 retry, 429 propagation, timeout propagation, malformed JSON, unexpected payload shapes | mocked adapter tests in `tests/test_powerbi_client.py` and route contract tests in `tests/test_api_contract.py`/`tests/test_smoke.py` | validate real API schema drift, throttling headers, pagination behavior, tenant-specific authorization, and live workspace/dataset access |
| PostgreSQL via `pg8000` | `App/database.py`, `App/storage.py` | engine creation, schema bootstrap, session creation, upserts, constraints, query filtering, rollback after failed writes | real database integration tests in `tests/test_database_runtime.py` and `tests/test_storage_integration.py` | validate production connectivity, TLS/network settings, credentials, database privileges, and larger-volume performance |
| SQLAlchemy ORM/Core | `App/database.py`, `App/models.py`, `App/storage.py` | repository/ORM mapping, PostgreSQL JSONB writes, conflict handling, transaction semantics | exercised only through app-owned persistence tests against PostgreSQL | no separate library-internal tests; real production schema evolution would need migration tests if Alembic is introduced |
| FastAPI / Starlette framework | `App/main.py`, `App/routes/*.py` | lifespan startup, route wiring, query validation, error mapping, redirects, static mount behavior | in-process app integration tests in `tests/test_framework_integration.py`, `tests/test_smoke.py`, and `tests/test_api_contract.py` | validate process-level deployment behavior under Uvicorn/reverse proxy and any production middleware once added |
| `python-dotenv` and environment configuration | `App/config.py` | `.env` loading, required env vars, DB URL normalization, fallback DB URL assembly | configuration boundary tests in `tests/test_config.py` | validate real deployment env injection and secret management outside local `.env` files |
| Filesystem-backed dashboard assets | `App/routes/ui.py`, `App/static/*` | dashboard file existence, readability, file serving contract | route-level filesystem tests in `tests/test_framework_integration.py` and UI smoke coverage in `tests/test_smoke.py` | validate packaging/deployment paths and web-server caching/static asset hosting in production |
| Uvicorn runtime | local startup only | ASGI server startup and serving process | not directly automated; app behavior is covered in-process through FastAPI `TestClient` | run manual smoke in the deployed runtime because the repo does not contain process-level server tests |

## Not Applicable

- AI/ML dependencies: none are present in the repository as of August 4, 2026.
- Database migrations: no Alembic or other migration framework is present, so migration tests are not applicable yet.
- Middleware-specific tests: no custom middleware is currently implemented.

## Recommended Testing Pyramid

### Distribution

Recommended balance for this project:

- `60-70%` unit tests
- `25-35%` integration tests
- `5-10%` end-to-end/browser tests

### Why this split fits the project

- A large amount of core logic is pure Python and should be tested quickly at unit level.
- The storage layer is Postgres-specific and cannot be trusted with mock-only coverage.
- The UI is static and relatively thin, so browser E2E should focus on critical workflows rather than exhaustive visual testing.

## What Should Be Tested

### Unit tests

Best targets:

- `App/analytics.py`
  - timestamp parsing
  - datasource summary extraction
  - refresh normalization
  - incident derivation
  - aggregate summaries
- `App/config.py`
  - env validation
  - DB URL normalization
  - fallback DB URL construction
- `App/auth.py`
  - token caching
  - force refresh behavior
  - upstream error propagation
- `App/powerbi_client.py`
  - retry on `401`
  - query parameter forwarding
  - request exception propagation

### Integration tests

Best targets:

- `App/storage.py` against a real temporary PostgreSQL database
  - upserts
  - replacements
  - round-trip reads
  - update semantics on duplicate refresh request IDs
- `App/routes/powerbi.py` with fake Power BI client + fake storage
  - endpoint contracts
  - validation behavior
  - error mapping

### End-to-end tests

Recommended but not yet implemented:

- browser loading of `/dashboard`
- partial API failure rendering
- sync button workflow
- refresh filtering and sorting UX
- navigation via hash and sidebar buttons

## What Should Not Be Over-Tested

- Exact implementation details of helper internals when observable behavior is already covered.
- FastAPI framework behavior that is already guaranteed by the framework itself.
- CSS layout pixel details unless visual regression testing is later introduced.
- Real Microsoft Power BI or Entra live calls in the default automated suite.

## Implemented Test Layers

### Unit coverage implemented

- analytics normalization and aggregation
- configuration assembly and validation
- auth token caching, request formatting, and malformed response handling
- Power BI client request/retry behavior, malformed payload handling, and unexpected payload shapes

### Integration coverage implemented

- real PostgreSQL persistence with isolated temporary databases
- database schema bootstrap and session creation against a temporary PostgreSQL database
- API smoke tests
- API validation and error mapping
- framework lifespan and dashboard filesystem error handling

### End-to-end coverage implemented

- None yet.

This is intentional because the repository currently has no browser automation framework, frontend package manager, or UI test harness.

## Test Infrastructure

Current infrastructure added to the project:

- `pytest`
- `httpx` for FastAPI `TestClient`
- shared test support module in `tests/support.py`
- shared fixtures in `tests/conftest.py`
- isolated temporary PostgreSQL database fixture using current project credentials

## Mocking Strategy

### Appropriate mocking

- Mock external HTTP requests to Entra and Power BI.
- Use fake Power BI clients for route tests.
- Use fake in-memory storage only for controller/API tests where the storage layer is not the subject under test.

### Avoided mocking

- Storage tests do not mock PostgreSQL.
- Analytics tests do not mock their own internal transformations except for time-sensitive delayed refresh scenarios.

## Current Coverage Summary

Implemented suites:

- `tests/test_smoke.py`
- `tests/test_api_contract.py`
- `tests/test_analytics.py`
- `tests/test_config.py`
- `tests/test_auth.py`
- `tests/test_powerbi_client.py`
- `tests/test_storage_integration.py`

Current result at generation time:

- `69 passed` on August 4, 2026

## Remaining Gaps

Still recommended:

- browser E2E tests for the dashboard UI
- query and rendering tests around partial API failure in a real browser
- process-level startup tests that exercise Uvicorn or the deployed host
- performance tests for large refresh and incident histories
- live-tenant verification of Power BI throttling, auth scopes, and workspace permissions

## Operational Notes

- The integration suite creates and destroys isolated temporary PostgreSQL databases.
- These tests assume the configured PostgreSQL user can create databases.
- The default suite intentionally avoids live Microsoft network calls.
