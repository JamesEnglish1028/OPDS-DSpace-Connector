## Local Run
1. Install dependencies: `pip install -r requirements.txt`
2. Configure DSpace API:
   - Real DSpace: `export DSPACE_API="https://your-repo.org/server/api"`
   - Mock mode: `export DSPACE_API="MOCK"`
3. Optional local feed links base URL: `export BASE_URL="http://localhost:8000"`
4. Start the connector: `uvicorn app:app --reload --port 8000`
5. Open root catalog: `http://localhost:8000/opds/v2/catalog`

## Render.com Deployment
This project is set up for Docker deployment on Render.

### Recommended setup
- Runtime: Docker
- Health Check Path: `/readyz`
- Region: choose the closest region to your DSpace instance

### Environment variables
- `DSPACE_API` (required): `https://your-dspace-domain.edu/server/api` or `MOCK`
- `BASE_URL` (required in production): `https://your-render-app-name.onrender.com`
- `DSPACE_TIMEOUT_SECONDS` (optional, default `10`)
- `DSPACE_RETRY_TOTAL` (optional, default `2`)
- `READINESS_TIMEOUT_SECONDS` (optional, default `2`)
- `LOOKUP_CACHE_TTL_SECONDS` (optional, default `60`)
- `ADMIN_TOKEN` (required to enable `/admin/api/*` endpoints)
- `WEB_CONCURRENCY` (optional, default `2`)

### Runtime behavior
- The container binds to `PORT` injected by Render.
- If `PORT` is not set, it falls back to `10000`.
- `/` is liveness and `/readyz` is strict readiness (includes upstream DSpace check).
- Lightweight in-memory TTL caching is enabled for community/collection lookups.

### Blueprint
Use the included `render.yaml` to provision the service with consistent settings.

## Admin UI (React)
- Open `/admin` to access the config UI.
- Provide `ADMIN_TOKEN` in the UI to authenticate admin API calls.
- Use it to read/update runtime `DSPACE_API` without restarting the process.
- Note: updates are in-memory per service instance and are not persisted across redeploys/restarts.

## Mock Preview Routes
- Root: `/opds/v2/catalog`
- Pagination test: `/opds/v2/mock-preview`
