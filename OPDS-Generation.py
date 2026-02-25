import requests
import json

# Configuration
DSPACE_API = "https://your-dspace-domain.edu/server/api"
COLLECTION_UUID = "your-collection-uuid-here"

def get_bitstreams(item_uuid):
    """Fetches bitstreams and separates them into Acquisition and Images."""
    links = []
    images = []
    
    # Query bundles for this specific item
    bundle_url = f"{DSPACE_API}/core/items/{item_uuid}/bundles"
    bundles = requests.get(bundle_url).json().get('_embedded', {}).get('bundles', [])
    
    for bundle in bundles:
        bundle_name = bundle.get('name')
        bitstream_url = bundle.get('_links', {}).get('bitstreams', {}).get('href')
        bitstreams = requests.get(bitstream_url).json().get('_embedded', {}).get('bitstreams', [])
        
        for bs in bitstreams:
            file_url = f"{DSPACE_API}/core/bitstreams/{bs['uuid']}/content"
            mime_type = bs.get('format', {}).get('mimetype', 'application/octet-stream')
            
            # 1. Acquisition Links (The Book/Audio file)
            if bundle_name == "ORIGINAL":
                rel = "http://opds-spec.org/acquisition/open-access"
                # If it's an Audiobook, the rel might stay the same but type changes to audio/mpeg
                links.append({"rel": rel, "href": file_url, "type": mime_type})
            
            # 2. Cover Image Links
            elif bundle_name == "THUMBNAIL" or bundle_name == "BRANDED_PREVIEW":
                images.append({"href": file_url, "type": mime_type})
                
    return links, images

def generate_opds_feed():
    # ... (previous setup code for fetching items) ...
    ds_items = fetch_dspace_items(COLLECTION_UUID)
    feed_publications = []

    for item in ds_items:
        item_uuid = item['uuid']
        metadata = item.get('metadata', {})
        
        # Get the files!
        acquisition_links, cover_images = get_bitstreams(item_uuid)
        
        pub_entry = {
            "metadata": {
                "@type": "http://schema.org/Book", # Logic from previous step
                "title": metadata.get('dc.title', [{}])[0].get('value', 'Untitled'),
                # ... other metadata ...
            },
            "links": acquisition_links,
            "images": cover_images
        }
        feed_publications.append(pub_entry)

    return {"publications": feed_publications}
