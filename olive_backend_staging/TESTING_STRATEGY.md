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
- auth token caching and error propagation
- Power BI client request/retry behavior

### Integration coverage implemented

- real PostgreSQL persistence with isolated temporary databases
- API smoke tests
- API validation and error mapping

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

- `55 passed`

## Remaining Gaps

Still recommended:

- browser E2E tests for the dashboard UI
- query and rendering tests around partial API failure in a real browser
- startup tests that exercise `App.main` with real env variations
- resilience tests for malformed upstream Power BI payloads
- transaction failure / rollback behavior in `App/storage.py`
- performance tests for large refresh and incident histories

## Operational Notes

- The integration suite creates and destroys isolated temporary PostgreSQL databases.
- These tests assume the configured PostgreSQL user can create databases.
- The default suite intentionally avoids live Microsoft network calls.

