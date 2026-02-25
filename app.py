import os
from fastapi import FastAPI
import requests

app = FastAPI()

# Render automatically provides a URL, but we'll use an Env Var if set
DSPACE_API = os.getenv("DSPACE_API", "https://demo.dspace.org/server/api")
BASE_URL = os.getenv("BASE_URL", "http://localhost:10000").rstrip('/')

@app.get("/")
def health_check():
    return {"status": "online", "connector": "DSpace-to-OPDS2.0"}

@app.get("/opds/v2/catalog", summary="Root Navigation Feed")
def root_navigation():
    """Starts the crawl at the top-level DSpace Communities."""
    url = f"{DSPACE_API}/core/communities/search/top"
    data = requests.get(url).json()
    
    feed = {
        "@context": "http://opds-spec.org/opds.jsonld",
        "metadata": {"title": "Main Library Catalog", "@type": "http://schema.org/NavigationEventsCard"},
        "links": [{"rel": "self", "href": f"{BASE_URL}/opds/v2/catalog", "type": "application/opds+json"}],
        "navigation": []
    }
    
    for comm in data.get('_embedded', {}).get('communities', []):
        feed["navigation"].append({
            "href": f"{BASE_URL}/opds/v2/community/{comm['uuid']}",
            "title": comm['name'],
            "type": "application/opds+json",
            "rel": "subsection"
        })
    return feed

@app.get("/opds/v2/community/{uuid}", summary="Sub-Navigation Feed")
def get_community(uuid: str):
    """Recursively lists sub-communities and collections."""
    comm_url = f"{DSPACE_API}/core/communities/{uuid}"
    comm_data = requests.get(comm_url).json()
    
    feed = {
        "@context": "http://opds-spec.org/opds.jsonld",
        "metadata": {"title": comm_data.get('name')},
        "navigation": []
    }
    
    # Add Sub-communities
    sub_url = f"{DSPACE_API}/core/communities/{uuid}/subcommunities"
    subs = requests.get(sub_url).json().get('_embedded', {}).get('subcommunities', [])
    for s in subs:
        feed["navigation"].append({"href": f"{BASE_URL}/opds/v2/community/{s['uuid']}", "title": s['name'], "type": "application/opds+json", "rel": "subsection"})

    # Add Collections (These point to the Publication Feed)
    coll_url = f"{DSPACE_API}/core/communities/{uuid}/collections"
    colls = requests.get(coll_url).json().get('_embedded', {}).get('collections', [])
    for c in colls:
        feed["navigation"].append({"href": f"{BASE_URL}/opds/v2/collection/{c['uuid']}", "title": c['name'], "type": "application/opds+json", "rel": "http://opds-spec.org/sort/new"})
    
    return feed

@app.get("/opds/v2/collection/{uuid}", summary="Publication Feed")
def get_publication_feed(uuid: str):
    """The 'Leaf' feed: lists all Publication Entities in a collection."""
    items_url = f"{DSPACE_API}/core/items/search/findByCollection?uuid={uuid}&embed=metadata"
    items = requests.get(items_url).json().get('_embedded', {}).get('items', [])
    
    feed = {
        "@context": "http://opds-spec.org/opds.jsonld",
        "metadata": {"title": "Publications"},
        "publications": []
    }
    
    for item in items:
        meta = item.get('metadata', {})
        
        # Mapping Virtual Metadata defined in DSpace
        pub = {
            "metadata": {
                "title": meta.get('dc.title', [{}])[0].get('value'),
                "author": [{"name": a['value']} for a in meta.get('dc.contributor.author', [])],
                "narrator": [{"name": n['value']} for n in meta.get('isNarratorOfPublication', [])],
                "publisher": meta.get('isPublisherOfPublication', [{}])[0].get('value', "Unknown")
            },
            "links": [
                {"rel": "http://opds-spec.org/acquisition/open-access", "href": f"{DSPACE_API}/core/items/{item['uuid']}/bitstreams", "type": "application/epub+zip"}
            ]
        }
        feed["publications"].append(pub)
        
    return feed
