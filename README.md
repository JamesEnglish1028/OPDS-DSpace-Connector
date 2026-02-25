## How to Run
1. Install dependencies: `pip install -r requirements.txt`
2. Set your DSpace API: `export DSPACE_API="https://your-repo.org/server/api"`
3. Start the connector: `uvicorn app:app --reload`
4. Access your OPDS 2.0 Root at: `http://localhost:8000/opds/v2/catalog`
