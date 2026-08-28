"""
Egg Data Collector
Collects egg spawn data and sends it to the FastAPI /ingest endpoint.

Usage:
    python collector.py
    
Environment Variables:
    PREDICTOR_API_URL - URL to FastAPI server (default: http://127.0.0.1:8000)
    COLLECTOR_KEY - Secret key for authentication (must match API's COLLECTOR_KEY)
"""

import os
import json
import time
from datetime import datetime, timezone
import requests


API_URL = os.getenv("PREDICTOR_API_URL", "http://127.0.0.1:8000").rstrip("/")
COLLECTOR_KEY = os.getenv("COLLECTOR_KEY", "change-me")


def get_current_time() -> float:
    """Get current UTC timestamp"""
    return datetime.now(timezone.utc).timestamp()


def collect_eggs() -> dict:
    """
    Collect egg data from your source.
    
    This is a placeholder - replace with your actual egg collection logic.
    For example, you might:
    - Scrape a website
    - Query a game API
    - Read from a local file
    - Use OCR on screenshots
    """
    current_time = get_current_time()
    
    # Example egg data - replace with real data
    eggs = [
        {
            "uid": "egg_001",
            "egg_type": "grass",
            "area": "Route 1",
            "spawned_at": current_time
        },
        {
            "uid": "egg_002", 
            "egg_type": "water",
            "area": "Lake",
            "spawned_at": current_time + 1
        },
        {
            "uid": "egg_003",
            "egg_type": "fire",
            "area": "Volcano",
            "spawned_at": current_time + 2
        },
    ]
    
    return {
        "server_time": current_time,
        "cycle_seconds": 3600,  # 1 hour cycle
        "next_reset_at": current_time + 3600,
        "eggs": eggs
    }


def send_snapshot(snapshot: dict) -> bool:
    """Send egg snapshot to API"""
    headers = {
        "X-Collector-Key": COLLECTOR_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            f"{API_URL}/ingest",
            json=snapshot,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Snapshot sent successfully (ID: {result['id']}, {result['eggs']} eggs)")
            return True
        else:
            print(f"❌ API error: HTTP {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Connection failed: Could not reach {API_URL}")
        return False
    except requests.exceptions.Timeout:
        print(f"❌ Request timed out")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Main collector loop"""
    print(f"Egg Data Collector")
    print(f"API URL: {API_URL}")
    print(f"Collector Key: {COLLECTOR_KEY[:10]}..." if len(COLLECTOR_KEY) > 10 else f"Collector Key: {COLLECTOR_KEY}")
    print("-" * 50)
    
    # Test API connectivity
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ API is online\n")
        else:
            print(f"❌ API returned status {response.status_code}\n")
            return
    except Exception as e:
        print(f"❌ Cannot reach API: {e}\n")
        return
    
    # Collect and send in a loop
    try:
        while True:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Collecting eggs...")
            
            # Collect egg data
            snapshot = collect_eggs()
            print(f"   Found {len(snapshot['eggs'])} eggs")
            
            # Send to API
            send_snapshot(snapshot)
            
            # Wait before next collection (in production, adjust this based on your cycle)
            print("   Waiting 60 seconds before next collection...\n")
            time.sleep(60)
            
    except KeyboardInterrupt:
        print("\n\nCollector stopped.")


if __name__ == "__main__":
    main()
