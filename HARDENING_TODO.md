# DSpace OPDS Connector Hardening TODO

## Phase 1: Backend Reliability (In Progress)
- [x] Add a centralized DSpace API client module.
- [x] Add configurable HTTP timeout and retry behavior for upstream DSpace calls.
- [x] Add consistent upstream error mapping (return 502 for DSpace failures instead of unhandled 500s).
- [x] Replace ad-hoc `requests.get(...).json()` calls in routes with client helpers.
- [x] Remove broad `print`-based exception handling and use structured logging.
- [x] Add unit tests for timeout/error mapping and mock mode route behavior.

## Phase 2: Performance and Observability
- [ ] Reduce N+1 requests for bitstreams (batching/caching where possible).
- [x] Add basic in-memory TTL caching for community/collection lookups.
- [ ] Add request-level latency logging and upstream status/latency metrics.
- [x] Add readiness endpoint that validates DSpace reachability with strict timeout.

## Phase 3: Render.com Deployment Hardening
- [x] Bind runtime to Render `PORT` env var instead of fixed port.
- [x] Make Gunicorn workers configurable via `WEB_CONCURRENCY`.
- [x] Pin dependency versions in `requirements.txt`.
- [x] Add `render.yaml` for reproducible service config.
- [x] Align README run/deploy instructions with actual runtime behavior.

## Phase 4: Admin UX (React.js)
- [x] Build a small React admin UI for DSpace configuration.
- [x] Add authenticated admin endpoint(s) for reading/updating effective DSpace API URL.
- [ ] Persist DSpace API URL safely (env-backed or secure config store pattern).
- [ ] Add validation + connectivity test button in UI (test `/server/api` reachability).
- [ ] Expose current effective config and last successful upstream check timestamp.

## Security and Governance
- [ ] Protect admin UI with auth (at minimum basic auth or SSO proxy on Render).
- [ ] Audit and restrict CORS for admin endpoints.
- [ ] Avoid writing secrets into git-tracked files.
