import os
import requests
from fastapi import FastAPI
from urllib.parse import quote, urlencode

app = FastAPI(title="DSpace-OPDS Connector")
# --- MOC DSPACE API DATA ---
MOCK_COMMUNITIES = {
    "_embedded": {
        "communities": [
            {"uuid": "comm-1", "name": "Audiobook Library"},
            {"uuid": "comm-2", "name": "Graphic Novel Collection"}
        ]
    },
    "page": {"totalElements": 2, "totalPages": 1, "number": 0}
}

MOCK_ITEMS = {
    "comm-1": [
        {
            "uuid": "audio-1",
            "metadata": {
                "dc.title": [{"value": "The Metadata Mystery"}],
                "dc.type": [{"value": "Audiobook"}],
                "dc.contributor.author": [{"value": "English, James"}],
                "isNarratorOfPublication": [{"value": "Voice Actor, Sarah"}],
                "isPublisherOfPublication": [{"value": "OPDS Labs"}]
            }
        }
    ],
    "comm-2": [
        {
            "uuid": "comic-1",
            "metadata": {
                "dc.title": [{"value": "The Code Crusader #1"}],
                "dc.type": [{"value": "Periodical"}],
                "dc.contributor.author": [{"value": "Developer, Alex"}],
                "isIllustratorOfPublication": [{"value": "Artist, Sam"}],
                "isSeriesOfPublication": [{"value": "The Great Metadata Saga"}],
                "relation.isSeriesOfPublication.number": [{"value": "1"}]
            }
        }
    ]
}

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
    """Paginated list of Publication Entities in a collection, supporting MOCK mode."""
    
    # 1. DATA ACQUISITION LAYER
    if os.getenv("DSPACE_API") == "MOCK":
        # Pull from our local dictionary
        items = MOCK_ITEMS.get(uuid, [])
        page_info = {
            "totalElements": len(items), 
            "totalPages": 1, 
            "number": 0
        }
    else:
        # Pull from real DSpace API
        params = {'uuid': uuid, 'page': page, 'size': size, 'embed': 'metadata'}
        url = f"{DSPACE_API}/core/items/search/findByCollection?{urlencode(params)}"
        response = requests.get(url).json()
        items = response.get('_embedded', {}).get('items', [])
        page_info = response.get('page', {})

    # 2. METADATA SETUP
    current_page = page_info.get('number', 0)
    
    feed = {
        "@context": "http://opds-spec.org/opds.jsonld",
        "metadata": {
            "title": "Publications",
            "numberOfItems": page_info.get('totalElements', 0),
            "currentPage": current_page + 1
        },
        "links": [
            {"rel": "self", "href": f"{BASE_URL}/opds/v2/collection/{uuid}?page={current_page}&size={size}", "type": "application/opds+json"}
        ],
        "publications": []
    }

    # 3. PAGINATION LINKS
    if current_page < page_info.get('totalPages', 1) - 1:
        feed["links"].append({
            "rel": "next", 
            "href": f"{BASE_URL}/opds/v2/collection/{uuid}?page={current_page+1}&size={size}", 
            "type": "application/opds+json"
        })
    if current_page > 0:
        feed["links"].append({
            "rel": "previous", 
            "href": f"{BASE_URL}/opds/v2/collection/{uuid}?page={current_page-1}&size={size}", 
            "type": "application/opds+json"
        })

    # 4. PUBLICATION MAPPING
    for item in items:
        meta = item.get('metadata', {})
        
        # If in MOCK mode, bitstreams will return empty lists unless you've mocked them too
        acq_links, images = get_bitstreams(item['uuid']) if os.getenv("DSPACE_API") != "MOCK" else ([], [])
        
        pub = {
            "metadata": {
                "title": meta.get('dc.title', [{}])[0].get('value', 'Untitled'),
                "author": [{"name": a['value']} for a in meta.get('dc.contributor.author', [])],
                "publisher": {"name": meta.get('isPublisherOfPublication', [{}])[0].get('value', 'Unknown')}
            },
            "links": acq_links,
            "images": images
        }
        
        # Add Narrator if it exists (Audiobook check)
        if "isNarratorOfPublication" in meta:
            pub["metadata"]["narrator"] = [{"name": n['value']} for n in meta.get('isNarratorOfPublication', [])]
            
        feed["publications"].append(pub)
        
    return feed

# --SEARCH

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

## Test Routes

@app.get("/opds/v2/mock-preview", summary="Mock Preview for OPDS Clients")
def mock_preview():
    """Generates a mock feed to test how different entities look in e-readers."""
    return {
        "@context": "http://opds-spec.org/opds.jsonld",
        "metadata": {
            "title": "Preview: Specialized Entities"
        },
        "publications": [
            {
                "metadata": {
                    "@type": "http://schema.org/Audiobook",
                    "title": "DSpace Chronicles: The Audio Experience",
                    "author": [{"name": "English, James"}],
                    "narrator": [{"name": "Narrator Voice"}],
                    "publisher": {"name": "DSpace Labs"},
                    "description": "A mock audiobook entity to test narrator metadata."
                },
                "links": [
                    {"rel": "http://opds-spec.org/acquisition", "href": "https://www.learningcontainer.com/wp-content/uploads/2020/02/Sample-OGG-File.ogg", "type": "audio/ogg"}
                ],
                "images": [{"href": "https://placehold.co/600x400/000/fff?text=Audiobook+Cover", "type": "image/png"}]
            },
            {
                "metadata": {
                    "@type": "http://schema.org/PublicationIssue",
                    "title": "The DSpace Comic #1",
                    "author": [{"name": "Developer, Alex"}],
                    "illustrator": [{"name": "Artist, Sam"}],
                    "belongsTo": {
                        "series": {"name": "The Great Metadata Saga", "position": 1}
                    }
                },
                "links": [
                    {"rel": "http://opds-spec.org/acquisition", "href": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf", "type": "application/pdf"}
                ],
                "images": [{"href": "https://placehold.co/600x400/000/fff?text=Comic+Cover", "type": "image/png"}]
            }
        ]
    }

