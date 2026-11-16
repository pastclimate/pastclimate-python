"""PastClimate quickstart.

Runs against the live API only when PASTCLIMATE_API_KEY is set. It spends a
small number of credits (one daily-data call); the other calls are free.

    export PASTCLIMATE_API_KEY=...       # your key, from your PastClimate account
    python examples/quickstart.py

Set PASTCLIMATE_BASE_URL to use a different API host (for example a test host).
"""

from __future__ import annotations

import os
import sys

from pastclimate import ApiError, Client, NetworkError


def main() -> int:
    if not os.environ.get("PASTCLIMATE_API_KEY"):
        print("Set PASTCLIMATE_API_KEY to run this example. Nothing was sent.")
        return 0

    base_url = os.environ.get("PASTCLIMATE_BASE_URL")
    client = Client(base_url=base_url) if base_url else Client()

    try:
        # Free: your plan and balance.
        me = client.get_me()
        print("Plan:", me.data.plan.name, "| credits remaining:", me.credits_remaining)

        # Free: find a location id.
        found = client.search_locations("lon", country="gb")
        place = found.data[0]
        print("Found:", place.id, place.name)

        # Credits are charged here. The response tells you how many.
        daily = client.get_daily(place.id, start="2024-01-01", end="2024-01-07")
        for row in daily.data:
            print(row.date, row.daily_min_temp, "to", row.daily_max_temp, "deg C", "rain" if row.rain_flag else "dry")
        print("Credits used:", daily.credits_used, "| remaining:", daily.credits_remaining)
        print("Requests left this minute:", daily.rate_limit.remaining)
    except ApiError as err:
        print("API error:", err.status, err.code, err.message, err.docs_url)
        return 1
    except NetworkError as err:
        print("Network problem:", err)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
