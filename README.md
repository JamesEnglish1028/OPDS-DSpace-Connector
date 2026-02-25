## How to Run
1. Install dependencies: `pip install -r requirements.txt`
2. Set your DSpace API: `export DSPACE_API="https://your-repo.org/server/api"`
3. Start the connector: `uvicorn app:app --reload`
4. Access your OPDS 2.0 Root at: `http://localhost:8000/opds/v2/catalog`

## Render.com Deployment Settings
When you create the New Web Service in the Render Dashboard and link your GitHub repo, use these settings:

Runtime: Docker

Region: Choose the one closest to your DSpace instance.

Environment Variables: (Crucial for the script to talk to your DSpace)

DSPACE_API: https://your-dspace-domain.edu/server/api

BASE_URL: https://your-render-app-name.onrender.com
