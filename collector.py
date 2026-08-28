import os
import time
from datetime import datetime, timezone

import requests


# --------------------------------------------------
# CONFIG
# --------------------------------------------------

API_URL = os.getenv(
    "PREDICTOR_API_URL",
    "http://127.0.0.1:8000"
).rstrip("/")

COLLECTOR_KEY = os.getenv(
    "COLLECTOR_KEY",
    "change-me"
)

COLLECTION_INTERVAL = int(
    os.getenv(
        "COLLECTION_INTERVAL",
        "60"
    )
)


# --------------------------------------------------
# TIME
# --------------------------------------------------

def get_current_time() -> float:

    return datetime.now(
        timezone.utc
    ).timestamp()


# --------------------------------------------------
# COLLECT EGGS
# --------------------------------------------------

def collect_eggs() -> dict:

    current_time = get_current_time()

    # ------------------------------------------------
    # IMPORTANT:
    # Replace this example data with your REAL
    # egg collection logic.
    # ------------------------------------------------

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
            "spawned_at": current_time
        },
        {
            "uid": "egg_003",
            "egg_type": "fire",
            "area": "Volcano",
            "spawned_at": current_time
        }
    ]

    cycle_seconds = 3600

    return {
        "server_time": current_time,
        "cycle_seconds": cycle_seconds,
        "next_reset_at": (
            current_time
            + cycle_seconds
        ),
        "eggs": eggs
    }


# --------------------------------------------------
# SEND
# --------------------------------------------------

def send_snapshot(
    snapshot: dict
) -> bool:

    headers = {
        "X-Collector-Key": COLLECTOR_KEY,
        "Content-Type": "application/json"
    }

    try:

        response = requests.post(
            f"{API_URL}/ingest",
            json=snapshot,
            headers=headers,
            timeout=30
        )

        if response.status_code == 200:

            result = response.json()

            print(
                "Snapshot sent successfully "
                f"(ID: {result.get('id')}, "
                f"{result.get('eggs')} eggs)"
            )

            return True

        print(
            f"API error: HTTP "
            f"{response.status_code}"
        )

        print(
            response.text[:500]
        )

        return False

    except requests.exceptions.ConnectionError:

        print(
            f"Connection failed: "
            f"Could not reach {API_URL}"
        )

        return False

    except requests.exceptions.Timeout:

        print(
            "Request timed out"
        )

        return False

    except Exception as error:

        print(
            f"Unexpected error: {error}"
        )

        return False


# --------------------------------------------------
# API TEST
# --------------------------------------------------

def check_api() -> bool:

    try:

        response = requests.get(
            f"{API_URL}/health",
            timeout=15
        )

        if response.status_code == 200:

            print(
                "API is online"
            )

            return True

        print(
            f"API returned HTTP "
            f"{response.status_code}"
        )

        return False

    except Exception as error:

        print(
            f"Cannot reach API: {error}"
        )

        return False


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    print(
        "Egg Data Collector"
    )

    print(
        f"API URL: {API_URL}"
    )

    print(
        f"Collection interval: "
        f"{COLLECTION_INTERVAL}s"
    )

    print(
        "-" * 50
    )

    while True:

        try:

            if not check_api():

                print(
                    "API unavailable. "
                    "Retrying in 30 seconds..."
                )

                time.sleep(30)

                continue

            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] "
                "Collecting eggs..."
            )

            snapshot = collect_eggs()

            print(
                f"Found "
                f"{len(snapshot['eggs'])} eggs"
            )

            send_snapshot(
                snapshot
            )

            print(
                f"Waiting "
                f"{COLLECTION_INTERVAL} seconds...\n"
            )

            time.sleep(
                COLLECTION_INTERVAL
            )

        except KeyboardInterrupt:

            print(
                "Collector stopped."
            )

            break

        except Exception as error:

            print(
                f"Collector error: {error}"
            )

            print(
                "Retrying in 30 seconds..."
            )

            time.sleep(30)


if __name__ == "__main__":

    main()
