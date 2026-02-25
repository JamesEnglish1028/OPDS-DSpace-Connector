import requests

# Change this to your Render URL after deployment
RENDER_URL = "https://your-render-app-name.onrender.com"

def test_connection():
    print(f"--- Testing OPDS Connector at: {RENDER_URL} ---")
    
    # 1. Test Health Check
    try:
        health = requests.get(f"{RENDER_URL}/").json()
        print(f"✅ Health Check: {health['status']}")
    except:
        print("❌ Health Check failed. Is the app running?")
        return

    # 2. Test Navigation (Root Catalog)
    try:
        catalog = requests.get(f"{RENDER_URL}/opds/v2/catalog").json()
        nav_count = len(catalog.get('navigation', []))
        print(f"✅ Root Catalog: Found {nav_count} communities from DSpace Demo.")
        if nav_count > 0:
            print(f"   Sample Community: {catalog['navigation'][0]['title']}")
    except:
        print("❌ Catalog Test failed.")

    # 3. Test Search
    try:
        search_term = "sample"
        search = requests.get(f"{RENDER_URL}/opds/v2/search?query={search_term}").json()
        pub_count = len(search.get('publications', []))
        print(f"✅ Search Test: Found {pub_count} publications for '{search_term}'.")
    except:
        print("❌ Search Test failed.")

if __name__ == "__main__":
    test_connection()
