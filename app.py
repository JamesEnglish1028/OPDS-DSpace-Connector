import logging
import hmac
import os
import threading
from urllib.parse import quote
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from dspace_client import DSpaceClient, UpstreamServiceError
from ttl_cache import TTLCache


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOGGER = logging.getLogger(__name__)

app = FastAPI(title="DSpace-OPDS Connector")

# --- MOCK DSPACE API DATA ---
MOCK_COMMUNITIES = {
    "_embedded": {
        "communities": [
            {"uuid": "comm-1", "name": "Audiobook Library"},
            {"uuid": "comm-2", "name": "Graphic Novel Collection"},
        ]
    },
    "page": {"totalElements": 2, "totalPages": 1, "number": 0},
}

MOCK_ITEMS = {
    "comm-1": [
        {
            "uuid": "audio-1",
            "metadata": {
                "dc.title": [{"value": "The Metadata Mystery"}],
                "dc.type": [{"value": "Book"}],
                "dc.identifier.isbn": [{"value": "9781234567890"}],
                "dc.contributor.author": [{"value": "English, James"}],
                "isNarratorOfPublication": [{"value": "Voice Actor, Sarah"}],
                "isPublisherOfPublication": [{"value": "OPDS Labs"}],
            },
        },
        {
            "uuid": "mono-1",
            "metadata": {
                "dc.title": [{"value": "Research Monograph"}],
                "dc.type": [{"value": "Monograph"}],
                "dc.identifier.isbn": [{"value": "9782222222222"}],
                "dc.contributor.author": [{"value": "Scholar, Jane"}],
                "isPublisherOfPublication": [{"value": "Academic Press"}],
            },
        },
        {
            "uuid": "thesis-1",
            "metadata": {
                "dc.title": [{"value": "Master's Thesis"}],
                "dc.type": [{"value": "Thesis"}],
                "dc.identifier.isbn": [{"value": "9783333333333"}],
                "dc.contributor.author": [{"value": "Student, Alex"}],
                "isPublisherOfPublication": [{"value": "University"}],
            },
        },
        {
            "uuid": "report-1",
            "metadata": {
                "dc.title": [{"value": "Technical Report"}],
                "dc.type": [{"value": "TechnicalReport"}],
                "dc.identifier.isbn": [{"value": "9784444444444"}],
                "dc.contributor.author": [{"value": "Engineer, Sam"}],
                "isPublisherOfPublication": [{"value": "Tech Institute"}],
            },
        },
        {
            "uuid": "conf-1",
            "metadata": {
                "dc.title": [{"value": "Conference Paper"}],
                "dc.type": [{"value": "ConferencePaper"}],
                "dc.identifier.isbn": [{"value": "9785555555555"}],
                "dc.contributor.author": [{"value": "Researcher, Pat"}],
                "isPublisherOfPublication": [{"value": "Conference Org"}],
            },
        },
    ],
    "comm-2": [
        {
            "uuid": "comic-1",
            "metadata": {
                "dc.title": [{"value": "The Code Crusader #1"}],
                "dc.type": [{"value": "BookChapter"}],
                "dc.identifier.isbn": [{"value": "9780987654321"}],
                "dc.contributor.author": [{"value": "Developer, Alex"}],
                "isIllustratorOfPublication": [{"value": "Artist, Sam"}],
                "isSeriesOfPublication": [{"value": "The Great Metadata Saga"}],
                "relation.isSeriesOfPublication.number": [{"value": "1"}],
            },
        },
        {
            "uuid": "series-1",
            "metadata": {
                "dc.title": [{"value": "Science Series"}],
                "dc.type": [{"value": "Series"}],
                "dc.identifier.isbn": [{"value": "9786666666666"}],
                "dc.contributor.author": [{"value": "Editor, Lee"}],
            },
        },
    ],
}

MOCK_SEARCH_RESULTS = {
    "_embedded": {
        "objects": [
            {
                "_embedded": {
                    "indexableObject": {
                        "uuid": "audio-1",
                        "metadata": {
                            "dc.title": [{"value": "Mock Audiobook: The Palace Secret"}],
                            "dc.type": [{"value": "Audiobook"}],
                            "dc.identifier.isbn": [{"value": "9781111111111"}],
                            "dc.contributor.author": [{"value": "English, James"}],
                            "isNarratorOfPublication": [{"value": "Deep Voice"}],
                        },
                    }
                }
            }
        ]
    },
    "page": {"totalElements": 1, "totalPages": 1, "number": 0},
}

MOCK_COMMUNITY_INDEX = {
    "comm-1": {"name": "Audiobook Library", "subcommunities": [], "collections": [{"uuid": "comm-1", "name": "Audiobooks"}]},
    "comm-2": {"name": "Graphic Novel Collection", "subcommunities": [], "collections": [{"uuid": "comm-2", "name": "Graphic Novels"}]},
}

# --- CONFIGURATION ---
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
DSPACE_TIMEOUT_SECONDS = float(os.getenv("DSPACE_TIMEOUT_SECONDS", "10"))
DSPACE_RETRY_TOTAL = int(os.getenv("DSPACE_RETRY_TOTAL", "2"))
READINESS_TIMEOUT_SECONDS = float(os.getenv("READINESS_TIMEOUT_SECONDS", "2"))
LOOKUP_CACHE_TTL_SECONDS = float(os.getenv("LOOKUP_CACHE_TTL_SECONDS", "60"))
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()

CONFIG_LOCK = threading.Lock()
LOOKUP_CACHE = TTLCache(ttl_seconds=LOOKUP_CACHE_TTL_SECONDS)
DSPACE_API_RAW = ""
IS_MOCK = True
DSPACE_API = ""
DS_CLIENT = None


def set_runtime_dspace_api(raw_value: str):
    """Update runtime DSpace settings and rebuild the HTTP client."""
    global DSPACE_API_RAW, IS_MOCK, DSPACE_API, DS_CLIENT
    with CONFIG_LOCK:
        normalized = raw_value.strip()
        if not normalized:
            raise ValueError("dspaceApi cannot be empty")

        DSPACE_API_RAW = normalized
        IS_MOCK = normalized.upper() == "MOCK"
        DSPACE_API = "" if IS_MOCK else normalized.rstrip("/")
        DS_CLIENT = None if IS_MOCK else DSpaceClient(
            base_url=DSPACE_API,
            timeout_seconds=DSPACE_TIMEOUT_SECONDS,
            retry_total=DSPACE_RETRY_TOTAL,
        )
        LOOKUP_CACHE.clear()


set_runtime_dspace_api(os.getenv("DSPACE_API", "https://demo.dspace.org/server/api"))


class AdminConfigUpdate(BaseModel):
    dspaceApi: str


def fetch_dspace_json(
    path: str,
    params: dict | None = None,
    absolute_url: bool = False,
    timeout_seconds: float | None = None,
) -> dict:
    if IS_MOCK or DS_CLIENT is None:
        raise HTTPException(status_code=500, detail="DSpace client unavailable in mock mode")
    try:
        return DS_CLIENT.get_json(
            path=path,
            params=params,
            absolute_url=absolute_url,
            timeout_seconds=timeout_seconds,
        )
    except UpstreamServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def fetch_dspace_json_cached(path: str, params: dict | None = None) -> dict:
    if IS_MOCK:
        raise HTTPException(status_code=500, detail="Cache fetch unavailable in mock mode")

    key_parts = [path]
    if params:
        key_parts.extend(f"{k}={params[k]}" for k in sorted(params.keys()))
    cache_key = "|".join(key_parts)

    cached = LOOKUP_CACHE.get(cache_key)
    if cached is not None:
        return cached

    payload = fetch_dspace_json(path, params=params)
    LOOKUP_CACHE.set(cache_key, payload)
    return payload


def require_admin_token(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")):
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="Admin API is disabled: set ADMIN_TOKEN in environment")

    token = x_admin_token or ""
    if not hmac.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid admin token")


# --- HELPERS ---
def get_bitstreams(item_uuid: str):
    """Fetches bitstreams from DSpace bundles and maps to OPDS acquisition/images."""
    links = []
    images = []

    if IS_MOCK:
        return links, images

    try:
        bundle_resp = fetch_dspace_json(f"/core/items/{item_uuid}/bundles")
        bundles = bundle_resp.get("_embedded", {}).get("bundles", [])

        for bundle in bundles:
            bundle_name = bundle.get("name")
            bs_url = bundle.get("_links", {}).get("bitstreams", {}).get("href")
            if not bs_url:
                continue

            bs_resp = fetch_dspace_json(bs_url, absolute_url=True)
            bitstreams = bs_resp.get("_embedded", {}).get("bitstreams", [])

            for bitstream in bitstreams:
                file_url = f"{DSPACE_API}/core/bitstreams/{bitstream['uuid']}/content"
                mime_type = bitstream.get("format", {}).get("mimetype", "application/octet-stream")

                if bundle_name == "ORIGINAL":
                    links.append(
                        {
                            "rel": "http://opds-spec.org/acquisition/open-access",
                            "href": file_url,
                            "type": mime_type,
                        }
                    )
                elif bundle_name in ["THUMBNAIL", "BRANDED_PREVIEW"]:
                    images.append({"href": file_url, "type": mime_type})
    except HTTPException as exc:
        LOGGER.warning("Bitstream fetch failed for item %s: %s", item_uuid, exc.detail)

    return links, images


# --- ENDPOINTS ---
@app.get("/", summary="Health Check")
def health_check():
    return {"status": "online", "connector": "DSpace-to-OPDS2.0", "mockMode": IS_MOCK}


@app.get("/readyz", summary="Readiness Probe")
def readiness_check():
    """Strict readiness check with short timeout for Render health probes."""
    if IS_MOCK:
        return {"status": "ready", "connector": "DSpace-to-OPDS2.0", "mockMode": True}

    try:
        response = fetch_dspace_json(
            "/core/communities/search/top",
            params={"page": 0, "size": 1},
            timeout_seconds=READINESS_TIMEOUT_SECONDS,
        )
    except HTTPException as exc:
        raise HTTPException(status_code=503, detail=f"Readiness check failed: {exc.detail}") from exc

    page_info = response.get("page")
    if not isinstance(page_info, dict):
        raise HTTPException(status_code=503, detail="Readiness check failed: invalid DSpace response payload")

    return {"status": "ready", "connector": "DSpace-to-OPDS2.0", "mockMode": False}


@app.get("/admin", include_in_schema=False)
def admin_ui():
    return FileResponse("static/admin/index.html")


@app.get("/admin/api/config", summary="Admin Config Read", dependencies=[Depends(require_admin_token)])
def get_admin_config():
    return {
        "dspaceApi": "MOCK" if IS_MOCK else DSPACE_API,
        "isMock": IS_MOCK,
        "cacheTtlSeconds": LOOKUP_CACHE_TTL_SECONDS,
    }


@app.put("/admin/api/config", summary="Admin Config Update", dependencies=[Depends(require_admin_token)])
def update_admin_config(payload: AdminConfigUpdate):
    try:
        set_runtime_dspace_api(payload.dspaceApi)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": "updated",
        "dspaceApi": "MOCK" if IS_MOCK else DSPACE_API,
        "isMock": IS_MOCK,
    }


@app.get("/opds/v2/catalog", summary="Root Navigation Feed")
def root_navigation(page: int = Query(0, ge=0), size: int = Query(20, ge=1, le=200)):
    """Starts the crawl at top-level DSpace Communities with Pagination."""
    if IS_MOCK:
        response = MOCK_COMMUNITIES
    else:
        response = fetch_dspace_json_cached("/core/communities/search/top", params={"page": page, "size": size})

    page_info = response.get("page", {})
    total_pages = page_info.get("totalPages", 1)
    current_page = page_info.get("number", 0)

    feed = {
        "@context": "http://opds-spec.org/opds.jsonld",
        "metadata": {
            "title": "Main Library Catalog",
            "@type": "http://schema.org/NavigationEventsCard",
            "numberOfItems": page_info.get("totalElements", 0),
            "itemsPerPage": size,
            "currentPage": current_page + 1,
        },
        "links": [
            {
                "rel": "self",
                "href": f"{BASE_URL}/opds/v2/catalog?page={current_page}&size={size}",
                "type": "application/opds+json",
            },
            {
                "rel": "search",
                "href": f"{BASE_URL}/opds/v2/search{{?query}}",
                "type": "application/opds+json",
                "templated": True,
            },
        ],
        "navigation": [],
    }

    if current_page > 0:
        feed["links"].append(
            {
                "rel": "previous",
                "href": f"{BASE_URL}/opds/v2/catalog?page={current_page - 1}&size={size}",
                "type": "application/opds+json",
            }
        )
    if current_page < total_pages - 1:
        feed["links"].append(
            {
                "rel": "next",
                "href": f"{BASE_URL}/opds/v2/catalog?page={current_page + 1}&size={size}",
                "type": "application/opds+json",
            }
        )

    for community in response.get("_embedded", {}).get("communities", []):
        feed["navigation"].append(
            {
                "href": f"{BASE_URL}/opds/v2/community/{community['uuid']}",
                "title": community["name"],
                "type": "application/opds+json",
                "rel": "subsection",
            }
        )

    return feed


@app.get("/opds/v2/community/{uuid}", summary="Sub-Navigation Feed")
def get_community(uuid: str):
    """Lists sub-communities and collections within a community."""
    if IS_MOCK:
        comm_data = MOCK_COMMUNITY_INDEX.get(uuid)
        if comm_data is None:
            raise HTTPException(status_code=404, detail=f"Mock community '{uuid}' not found")

        feed = {
            "@context": "http://opds-spec.org/opds.jsonld",
            "metadata": {"title": comm_data.get("name", "Community")},
            "links": [{"rel": "self", "href": f"{BASE_URL}/opds/v2/community/{uuid}", "type": "application/opds+json"}],
            "navigation": [],
        }

        for subcommunity in comm_data.get("subcommunities", []):
            feed["navigation"].append(
                {
                    "href": f"{BASE_URL}/opds/v2/community/{subcommunity['uuid']}",
                    "title": subcommunity["name"],
                    "type": "application/opds+json",
                    "rel": "subsection",
                }
            )

        for collection in comm_data.get("collections", []):
            feed["navigation"].append(
                {
                    "href": f"{BASE_URL}/opds/v2/collection/{collection['uuid']}",
                    "title": collection["name"],
                    "type": "application/opds+json",
                    "rel": "http://opds-spec.org/sort/new",
                }
            )

        return feed

    comm_data = fetch_dspace_json_cached(f"/core/communities/{uuid}")

    feed = {
        "@context": "http://opds-spec.org/opds.jsonld",
        "metadata": {"title": comm_data.get("name", "Community")},
        "links": [{"rel": "self", "href": f"{BASE_URL}/opds/v2/community/{uuid}", "type": "application/opds+json"}],
        "navigation": [],
    }

    sub_resp = fetch_dspace_json_cached(f"/core/communities/{uuid}/subcommunities")
    for subcommunity in sub_resp.get("_embedded", {}).get("subcommunities", []):
        feed["navigation"].append(
            {
                "href": f"{BASE_URL}/opds/v2/community/{subcommunity['uuid']}",
                "title": subcommunity["name"],
                "type": "application/opds+json",
                "rel": "subsection",
            }
        )

    coll_resp = fetch_dspace_json_cached(f"/core/communities/{uuid}/collections")
    for collection in coll_resp.get("_embedded", {}).get("collections", []):
        feed["navigation"].append(
            {
                "href": f"{BASE_URL}/opds/v2/collection/{collection['uuid']}",
                "title": collection["name"],
                "type": "application/opds+json",
                "rel": "http://opds-spec.org/sort/new",
            }
        )

    return feed


@app.get("/opds/v2/collection/{uuid}", summary="Publication Feed")
def get_publication_feed(uuid: str, page: int = Query(0, ge=0), size: int = Query(20, ge=1, le=200)):
    """Paginated list of Publication Entities in a collection, supporting MOCK mode."""
    if IS_MOCK:
        items = MOCK_ITEMS.get(uuid, [])
        page_info = {
            "totalElements": len(items),
            "totalPages": 1,
            "number": 0,
        }
    else:
        response = fetch_dspace_json_cached(
            "/core/items/search/findByCollection",
            params={"uuid": uuid, "page": page, "size": size, "embed": "metadata"},
        )
        items = response.get("_embedded", {}).get("items", [])
        page_info = response.get("page", {})

    current_page = page_info.get("number", 0)

    feed = {
        "@context": "http://opds-spec.org/opds.jsonld",
        "metadata": {
            "title": "Publications",
            "numberOfItems": page_info.get("totalElements", 0),
            "currentPage": current_page + 1,
        },
        "links": [
            {
                "rel": "self",
                "href": f"{BASE_URL}/opds/v2/collection/{uuid}?page={current_page}&size={size}",
                "type": "application/opds+json",
            }
        ],
        "publications": [],
    }

    if current_page < page_info.get("totalPages", 1) - 1:
        feed["links"].append(
            {
                "rel": "next",
                "href": f"{BASE_URL}/opds/v2/collection/{uuid}?page={current_page + 1}&size={size}",
                "type": "application/opds+json",
            }
        )
    if current_page > 0:
        feed["links"].append(
            {
                "rel": "previous",
                "href": f"{BASE_URL}/opds/v2/collection/{uuid}?page={current_page - 1}&size={size}",
                "type": "application/opds+json",
            }
        )

    for item in items:
        metadata = item.get("metadata", {})
        acquisition_links, images = get_bitstreams(item["uuid"])

        # Add identifier and @type mapping
        isbn = metadata.get("dc.identifier.isbn", [{}])[0].get("value")
        handle = metadata.get("dc.identifier.uri", [{}])[0].get("value")
        dc_type = metadata.get("dc.type", [{}])[0].get("value", "Book")
        type_map = {
            "Book": "http://schema.org/Book",
            "BookChapter": "http://schema.org/Chapter",
            "Monograph": "http://schema.org/Book",
            "TechnicalReport": "http://schema.org/Report",
            "Thesis": "http://schema.org/Thesis",
            "ConferencePaper": "http://schema.org/ScholarlyArticle",
            "Series": "http://schema.org/Series",
            "Publication": "http://schema.org/CreativeWork",
        }
        schema_type = type_map.get(dc_type, "http://schema.org/Book")

        publication = {
            "metadata": {
                "@type": schema_type,
                "identifier": isbn or handle or f"urn:uuid:{item['uuid']}",
                "title": metadata.get("dc.title", [{}])[0].get("value", "Untitled"),
                "author": [{"name": author["value"]} for author in metadata.get("dc.contributor.author", [])],
                "publisher": {"name": metadata.get("isPublisherOfPublication", [{}])[0].get("value", "Unknown")},
                "modified": datetime.now(timezone.utc).isoformat(),
            },
            "links": acquisition_links,
            "images": images,
        }

        if "isNarratorOfPublication" in metadata:
            publication["metadata"]["narrator"] = [
                {"name": narrator["value"]} for narrator in metadata.get("isNarratorOfPublication", [])
            ]

        feed["publications"].append(publication)

    return feed


@app.get("/opds/v2/search", summary="Search Publications")
def search_publications(query: str | None = None):
    """
    Proxies search to DSpace Discovery API with support for
    Stable Identifiers (ISBN/Handle) for Palace Project ingestion.
    """
    if not query:
        return {"metadata": {"title": "No search terms"}, "publications": []}

    if IS_MOCK:
        response = MOCK_SEARCH_RESULTS
    else:
        response = fetch_dspace_json(
            "/discover/search/objects",
            params={"query": query, "dsoType": "item", "embed": "metadata"},
        )

    feed = {
        "@context": "http://opds-spec.org/opds.jsonld",
        "metadata": {
            "title": f"Results for: {query}",
            "numberOfItems": response.get("page", {}).get("totalElements", 0),
        },
        "links": [
            {
                "rel": "self",
                "href": f"{BASE_URL}/opds/v2/search?query={quote(query)}",
                "type": "application/opds+json",
            }
        ],
        "publications": [],
    }

    for result in response.get("_embedded", {}).get("objects", []):
        item = result.get("_embedded", {}).get("indexableObject", {})
        if not item:
            continue

        metadata = item.get("metadata", {})
        acquisition_links, images = get_bitstreams(item["uuid"])

        isbn = metadata.get("dc.identifier.isbn", [{}])[0].get("value")
        handle = metadata.get("dc.identifier.uri", [{}])[0].get("value")

        # Map dc.type to schema.org @type
        dc_type = metadata.get("dc.type", [{}])[0].get("value", "Book")
        type_map = {
            "Book": "http://schema.org/Book",
            "BookChapter": "http://schema.org/Chapter",
            "Monograph": "http://schema.org/Book",
            "TechnicalReport": "http://schema.org/Report",
            "Thesis": "http://schema.org/Thesis",
            "ConferencePaper": "http://schema.org/ScholarlyArticle",
            "Series": "http://schema.org/Series",
            "Publication": "http://schema.org/CreativeWork",
        }
        schema_type = type_map.get(dc_type, "http://schema.org/Book")

        feed["publications"].append(
            {
                "metadata": {
                    "@type": schema_type,
                    "identifier": isbn or handle or f"urn:uuid:{item['uuid']}",
                    "title": metadata.get("dc.title", [{}])[0].get("value", "Untitled"),
                    "author": [{"name": author["value"]} for author in metadata.get("dc.contributor.author", [])],
                    "publisher": {
                        "name": metadata.get("isPublisherOfPublication", [{}])[0].get("value", "Unknown")
                    },
                    "language": metadata.get("dc.language.iso", [{}])[0].get("value", "en"),
                    "modified": item.get("lastModified"),
                },
                "links": acquisition_links,
                "images": images,
            }
        )

    return feed


@app.get("/opds/v2/mock-preview", summary="Paginated Mock Test")
def mock_preview(page: int = Query(0, ge=0)):
    """Simulates multi-page publication feeds for e-reader testing."""
    next_page = page + 1
    has_next = page < 2

    feed = {
        "@context": "http://opds-spec.org/opds.jsonld",
        "metadata": {
            "title": f"Mock Paginated Feed - Page {page + 1}",
            "currentPage": page + 1,
            "numberOfItems": 6,
        },
        "links": [
            {
                "rel": "self",
                "href": f"{BASE_URL}/opds/v2/mock-preview?page={page}",
                "type": "application/opds+json",
            }
        ],
        "publications": [
            {
                "metadata": {"title": f"Mock Book {page * 2 + 1}", "author": [{"name": "Author A"}]},
                "links": [{"rel": "http://opds-spec.org/acquisition", "href": "#", "type": "application/pdf"}],
            },
            {
                "metadata": {"title": f"Mock Book {page * 2 + 2}", "author": [{"name": "Author B"}]},
                "links": [{"rel": "http://opds-spec.org/acquisition", "href": "#", "type": "application/pdf"}],
            },
        ],
    }

    if has_next:
        feed["links"].append(
            {
                "rel": "next",
                "href": f"{BASE_URL}/opds/v2/mock-preview?page={next_page}",
                "type": "application/opds+json",
            }
        )
    if page > 0:
        feed["links"].append(
            {
                "rel": "previous",
                "href": f"{BASE_URL}/opds/v2/mock-preview?page={page - 1}",
                "type": "application/opds+json",
            }
        )

    return feed
