import os
from fastapi import FastAPI
import requests
from urllib.parse import quote

app = FastAPI()

# Render automatically provides a URL, but we'll use an Env Var if set
DSPACE_API = os.getenv("DSPACE_API", "https://demo.dspace.org/server/api")
BASE_URL = os.getenv("BASE_URL", "http://localhost:10000").rstrip('/')

@app.get("/")
def health_check():
    return {"status": "online", "connector": "DSpace-to-OPDS2.0"}

@app.get("/opds/v2/search", summary="Search Feed")
def search_publications(query: str = None):
    """
    Proxies a search request to DSpace and returns an OPDS 2.0 Publication Feed.
    """
    if not query:
        # Return an empty feed or a prompt if no query is provided
        return {"metadata": {"title": "Enter search terms"}, "publications": []}

    # Query DSpace Discovery API
    # We use /discover/search/objects to find items across the repo
    search_url = f"{DSPACE_API}/discover/search/objects?query={quote(query)}&dsoType=item&embed=metadata"
    response = requests.get(search_url).json()
    
    # Extract items from the Discovery search results
    search_results = response.get('_embedded', {}).get('objects', [])
    
    feed = {
        "@context": "http://opds-spec.org/opds.jsonld",
        "metadata": {
            "title": f"Search Results for: {query}",
            "numberOfItems": response.get('page', {}).get('totalElements', 0)
        },
        "publications": []
    }

    for result in search_results:
        # Discovery API wraps the item in an 'indexableObject'
        item = result.get('_embedded', {}).get('indexableObject', {})
        if not item: continue
        
        meta = item.get('metadata', {})
        # Re-use your publication mapping logic here
        feed["publications"].append({
            "metadata": {
                "title": meta.get('dc.title', [{}])[0].get('value', 'Untitled'),
                "author": [{"name": a['value']} for a in meta.get('dc.contributor.author', [])]
            },
            "links": [{"rel": "self", "href": f"{BASE_URL}/opds/v2/item/{item['uuid']}", "type": "application/opds-publication+json"}]
        })

    return feed

@app.get("/opds/v2/catalog", summary="Root Navigation Feed")
def root_navigation(page: int = 0, size: int = 20):
    """Starts the crawl at the top-level DSpace Communities with Pagination."""
    
    # Query DSpace with pagination parameters
    params = {'page': page, 'size': size}
    url = f"{DSPACE_API}/core/communities/search/top?{urlencode(params)}"
    response = requests.get(url).json()
    
    # Extract pagination info from DSpace response
    page_info = response.get('page', {})
    total_pages = page_info.get('totalPages', 1)
    current_page = page_info.get('number', 0)
    
    # Initialize the OPDS Feed
    feed = {
        "@context": "http://opds-spec.org/opds.jsonld",
        "metadata": {
            "title": "Main Library Catalog",
            "@type": "http://schema.org/NavigationEventsCard",
            "numberOfItems": page_info.get('totalElements', 0),
            "itemsPerPage": size,
            "currentPage": current_page + 1  # OPDS is usually 1-indexed for display
        },
        "links": [
            {"rel": "self", "href": f"{BASE_URL}/opds/v2/catalog?page={current_page}&size={size}", "type": "application/opds+json"},
            {"rel": "search", "href": f"{BASE_URL}/opds/v2/search{{?query}}", "type": "application/opds+json", "templated": True}
        ],
        "navigation": []
    }

    # Add Pagination Links
    if current_page > 0:
        feed["links"].append({"rel": "first", "href": f"{BASE_URL}/opds/v2/catalog?page=0&size={size}", "type": "application/opds+json"})
        feed["links"].append({"rel": "previous", "href": f"{BASE_URL}/opds/v2/catalog?page={current_page - 1}&size={size}", "type": "application/opds+json"})
    
    if current_page < total_pages - 1:
        feed["links"].append({"rel": "next", "href": f"{BASE_URL}/opds/v2/catalog?page={current_page + 1}&size={size}", "type": "application/opds+json"})
        feed["links"].append({"rel": "last", "href": f"{BASE_URL}/opds/v2/catalog?page={total_pages - 1}&size={size}", "type": "application/opds+json"})

    # Process Navigation Items
    for comm in response.get('_embedded', {}).get('communities', []):
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

@app.get("/opds/v2/collection/{uuid}", summary="Publication Feed with Pagination")
def get_publication_feed(uuid: str, page: int = 0, size: int = 20):
    """Fetches items in a collection and returns an OPDS 2.0 Publication Feed with pagination."""
    
    # Query DSpace with pagination: size and page
    params = {'uuid': uuid, 'page': page, 'size': size, 'embed': 'metadata'}
    items_url = f"{DSPACE_API}/core/items/search/findByCollection?{urlencode(params)}"
    response = requests.get(items_url).json()
    
    page_info = response.get('page', {})
    total_pages = page_info.get('totalPages', 1)
    current_page = page_info.get('number', 0)
    
    feed = {
        "@context": "http://opds-spec.org/opds.jsonld",
        "metadata": {
            "title": f"Collection Catalog - Page {current_page + 1}",
            "numberOfItems": page_info.get('totalElements', 0),
            "itemsPerPage": size,
            "currentPage": current_page + 1
        },
        "links": [
            {"rel": "self", "href": f"{BASE_URL}/opds/v2/collection/{uuid}?page={current_page}&size={size}", "type": "application/opds+json"}
        ],
        "publications": []
    }

    # Add Navigation/Pagination links to the feed
    if current_page > 0:
        feed["links"].append({"rel": "first", "href": f"{BASE_URL}/opds/v2/collection/{uuid}?page=0&size={size}", "type": "application/opds+json"})
        feed["links"].append({"rel": "previous", "href": f"{BASE_URL}/opds/v2/collection/{uuid}?page={current_page - 1}&size={size}", "type": "application/opds+json"})
    
    if current_page < total_pages - 1:
        feed["links"].append({"rel": "next", "href": f"{BASE_URL}/opds/v2/collection/{uuid}?page={current_page + 1}&size={size}", "type": "application/opds+json"})
        feed["links"].append({"rel": "last", "href": f"{BASE_URL}/opds/v2/collection/{uuid}?page={total_pages - 1}&size={size}", "type": "application/opds+json"})

    # Map Items to Publications
    items = response.get('_embedded', {}).get('items', [])
    for item in items:
        meta = item.get('metadata', {})
        
        # Acquisition and Image detection logic
        acquisition_links, cover_images = get_bitstreams(item['uuid'])
        
        pub = {
            "metadata": {
                "@type": "http://schema.org/Book",
                "title": meta.get('dc.title', [{}])[0].get('value', 'Untitled'),
                "author": [{"name": a['value']} for a in meta.get('dc.contributor.author', [])],
                "narrator": [{"name": n['value']} for n in meta.get('isNarratorOfPublication', [])],
                "publisher": {"name": meta.get('isPublisherOfPublication', [{}])[0].get('value', 'Unknown')}
            },
            "links": acquisition_links,
            "images": cover_images
        }
        feed["publications"].append(pub)
        
    return feed
