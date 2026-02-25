import os
import requests
from fastapi import FastAPI
from urllib.parse import quote, urlencode

app = FastAPI(title="DSpace-OPDS Connector")

# --- CONFIGURATION ---
# Render/Environment variables
DSPACE_API = os.getenv("DSPACE_API", "https://demo.dspace.org/server/api").rstrip('/')
BASE_URL = os.getenv("BASE_URL", "http://localhost:10000").rstrip('/')

# --- HELPERS ---

def get_bitstreams(item_uuid):
    """Fetches bitstreams from DSpace bundles and maps to OPDS acquisition/images."""
    links = []
    images = []
    
    try:
        # 1. Get the bundles for the item
        bundle_url = f"{DSPACE_API}/core/items/{item_uuid}/bundles"
        bundle_resp = requests.get(bundle_url).json()
        bundles = bundle_resp.get('_embedded', {}).get('bundles', [])
        
        for bundle in bundles:
            bundle_name = bundle.get('name')
            bs_url = bundle.get('_links', {}).get('bitstreams', {}).get('href')
            bs_resp = requests.get(bs_url).json()
            bitstreams = bs_resp.get('_embedded', {}).get('bitstreams', [])
            
            for bs in bitstreams:
                file_url = f"{DSPACE_API}/core/bitstreams/{bs['uuid']}/content"
                mime_type = bs.get('format', {}).get('mimetype', 'application/octet-stream')
                
                # Map to OPDS Acquisition
                if bundle_name == "ORIGINAL":
                    links.append({
                        "rel": "http://opds-spec.org/acquisition/open-access",
                        "href": file_url,
                        "type": mime_type
                    })
                # Map to OPDS Images
                elif bundle_name in ["THUMBNAIL", "BRANDED_PREVIEW"]:
                    images.append({
                        "href": file_url,
                        "type": mime_type
                    })
    except Exception as e:
        print(f"Error fetching bitstreams for {item_uuid}: {e}")
        
    return links, images

# --- ENDPOINTS ---

@app.get("/", summary="Health Check")
def health_check():
    return {"status": "online", "connector": "DSpace-to-OPDS2.0"}

@app.get("/opds/v2/catalog", summary="Root Navigation Feed")
def root_navigation(page: int = 0, size: int = 20):
    """Starts the crawl at top-level DSpace Communities with Pagination."""
    params = {'page': page, 'size': size}
    url = f"{DSPACE_API}/core/communities/search/top?{urlencode(params)}"
    response = requests.get(url).json()
    
    page_info = response.get('page', {})
    total_pages = page_info.get('totalPages', 1)
    current_page = page_info.get('number', 0)
    
    feed = {
        "@context": "http://opds-spec.org/opds.jsonld",
        "metadata": {
            "title": "Main Library Catalog",
            "@type": "http://schema.org/NavigationEventsCard",
            "numberOfItems": page_info.get('totalElements', 0),
            "itemsPerPage": size,
            "currentPage": current_page + 1
        },
        "links": [
            {"rel": "self", "href": f"{BASE_URL}/opds/v2/catalog?page={current_page}&size={size}", "type": "application/opds+json"},
            {"rel": "search", "href": f"{BASE_URL}/opds/v2/search{{?query}}", "type": "application/opds+json", "templated": True}
        ],
        "navigation": []
    }

    # Pagination Links
    if current_page > 0:
        feed["links"].append({"rel": "previous", "href": f"{BASE_URL}/opds/v2/catalog?page={current_page - 1}&size={size}", "type": "application/opds+json"})
    if current_page < total_pages - 1:
        feed["links"].append({"rel": "next", "href": f"{BASE_URL}/opds/v2/catalog?page={current_page + 1}&size={size}", "type": "application/opds+json"})

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
    """Lists sub-communities and collections within a community."""
    comm_data = requests.get(f"{DSPACE_API}/core/communities/{uuid}").json()
    
    feed = {
        "@context": "http://opds-spec.org/opds.jsonld",
        "metadata": {"title": comm_data.get('name', 'Community')},
        "links": [{"rel": "self", "href": f"{BASE_URL}/opds/v2/community/{uuid}", "type": "application/opds+json"}],
        "navigation": []
    }
    
    # Sub-communities
    sub_resp = requests.get(f"{DSPACE_API}/core/communities/{uuid}/subcommunities").json()
    for s in sub_resp.get('_embedded', {}).get('subcommunities', []):
        feed["navigation"].append({"href": f"{BASE_URL}/opds/v2/community/{s['uuid']}", "title": s['name'], "type": "application/opds+json", "rel": "subsection"})

    # Collections
    coll_resp = requests.get(f"{DSPACE_API}/core/communities/{uuid}/collections").json()
    for c in coll_resp.get('_embedded', {}).get('collections', []):
        feed["navigation"].append({"href": f"{BASE_URL}/opds/v2/collection/{c['uuid']}", "title": c['name'], "type": "application/opds+json", "rel": "http://opds-spec.org/sort/new"})
    
    return feed

@app.get("/opds/v2/collection/{uuid}", summary="Publication Feed")
def get_publication_feed(uuid: str, page: int = 0, size: int = 20):
    """Paginated list of Publication Entities in a collection."""
    params = {'uuid': uuid, 'page': page, 'size': size, 'embed': 'metadata'}
    url = f"{DSPACE_API}/core/items/search/findByCollection?{urlencode(params)}"
    response = requests.get(url).json()
    
    page_info = response.get('page', {})
    current_page = page_info.get('number', 0)
    
    feed = {
        "@context": "http://opds-spec.org/opds.jsonld",
        "metadata": {
            "title": "Publications",
            "numberOfItems": page_info.get('totalElements', 0),
            "currentPage": current_page + 1
        },
        "links": [{"rel": "self", "href": f"{BASE_URL}/opds/v2/collection/{uuid}?page={current_page}&size={size}", "type": "application/opds+json"}],
        "publications": []
    }

    # Add next/prev links
    if current_page < page_info.get('totalPages', 1) - 1:
        feed["links"].append({"rel": "next", "href": f"{BASE_URL}/opds/v2/collection/{uuid}?page={current_page+1}&size={size}", "type": "application/opds+json"})

    for item in response.get('_embedded', {}).get('items', []):
        meta = item.get('metadata', {})
        acq_links, images = get_bitstreams(item['uuid'])
        
        pub = {
            "metadata": {
                "title": meta.get('dc.title', [{}])[0].get('value', 'Untitled'),
                "author": [{"name": a['value']} for a in meta.get('dc.contributor.author', [])],
                "publisher": {"name": meta.get('isPublisherOfPublication', [{}])[0].get('value', 'Unknown')}
            },
            "links": acq_links,
            "images": images
        }
        feed["publications"].append(pub)
        
    return feed

@app.get("/opds/v2/search", summary="Search Publications")
def search_publications(query: str = None):
    """Proxies search to DSpace Discovery API."""
    if not query:
        return {"metadata": {"title": "No search terms"}, "publications": []}

    search_url = f"{DSPACE_API}/discover/search/objects?query={quote(query)}&dsoType=item&embed=metadata"
    response = requests.get(search_url).json()
    
    feed = {
        "@context": "http://opds-spec.org/opds.jsonld",
        "metadata": {"title": f"Results for: {query}"},
        "publications": []
    }

    for result in response.get('_embedded', {}).get('objects', []):
        item = result.get('_embedded', {}).get('indexableObject', {})
        if not item: continue
        meta = item.get('metadata', {})
        acq_links, images = get_bitstreams(item['uuid'])
        
        feed["publications"].append({
            "metadata": {
                "title": meta.get('dc.title', [{}])[0].get('value', 'Untitled'),
                "author": [{"name": a['value']} for a in meta.get('dc.contributor.author', [])]
            },
            "links": acq_links,
            "images": images
        })
    return feed
