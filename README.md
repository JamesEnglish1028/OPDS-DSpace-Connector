## How to Run
1. Install dependencies: `pip install -r requirements.txt`
2. Set your DSpace API: `export DSPACE_API="https://your-repo.org/server/api"`
3. Start the connector: `uvicorn app:app --reload`
4. Access your OPDS 2.0 Root at: `http://localhost:8000/opds/v2/catalog`

## Render.com Deployment Settings
When you create the New Web Service in the Render Dashboard and link your GitHub repo, use these settings:

Runtime: Docker

Region: Choose the one closest to your DSpace instance.

## Environment Variables:

DSPACE_API: https://your-dspace-domain.edu/server/api

BASE_URL: https://your-render-app-name.onrender.com

### Running in Mock Mode
To test the UI and logic without a real DSpace server:
1. Set `DSPACE_API` to `MOCK` in Render or your terminal:
   `export DSPACE_API="MOCK"`
2. Access the specialized previews:
   - Root: `/opds/v2/catalog`
   - Pagination Test: `/opds/v2/mock-preview`
