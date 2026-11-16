# pastclimate (Python)

Official Python client for the [PastClimate API](https://developer.pastclimate.com/api/): historical daily, hourly, monthly and yearly weather, climate normals and records for places around the world.

- No dependencies. Python 3.9 or newer.
- Typed: ships `py.typed`, every response is a dataclass.
- One method per API operation, typed errors, automatic retries.

## Install

```bash
pip install pastclimate
```

## Quickstart

```python
from pastclimate import Client

client = Client()  # reads the PASTCLIMATE_API_KEY environment variable

resp = client.get_daily("gb/london", start="2024-01-01", end="2024-01-31")

for row in resp.data:
    print(row.date, row.daily_min_temp, row.daily_max_temp, row.daily_total_rain)

print("credits used:", resp.credits_used)
print("credits remaining:", resp.credits_remaining)
```

Get a key from your PastClimate account. Never put a key in source code or in a URL. Call the API from a server or a script, not from a browser: the API does not accept browser calls.

## Configuration

```python
client = Client(
    api_key="YOUR_API_KEY",            # default: the PASTCLIMATE_API_KEY environment variable
    base_url="https://api.pastclimate.com",
    timeout=30.0,                      # seconds per HTTP attempt; None waits forever
    max_retries=2,                     # see "Retries"
    max_retry_after=60.0,              # longest Retry-After (seconds) to sleep through
)
```

If no key is passed and the environment variable is not set, `Client()` raises `AuthenticationError` with code `missing_key`.

Every request sends `User-Agent: pastclimate-python/<version>` and `Authorization: Bearer <key>`.

## Choosing a place

Every data method takes the place in one of two ways:

```python
client.get_monthly("gb/london")                              # a location id
client.get_monthly(lat=51.5, lon=-0.12, country="gb")        # a point and its country
```

A point is snapped to the nearest place in that country; `resp.location.requested` shows the point you sent and the distance. Find ids with `search_locations`. Location ids and the look-up calls are free, but they still count toward your request limits.

## Responses

Every successful call returns an `ApiResponse` with:

| Attribute | Meaning |
|---|---|
| `data` | The parsed `data`: a list of rows, or one object. |
| `meta` | The parsed `meta`: `credits`, `credits_remaining`, `methodology_version`, plus fields for the call (such as `units`). |
| `location` | The place the numbers are for, or `None` for calls that are not about one place. |
| `credits_used` | Credits this call used. |
| `credits_remaining` | Credits you can still spend. |
| `rate_limit` | `limit`, `remaining`, `reset` from the `RateLimit-*` headers (`None` when absent). |
| `status_code`, `headers` | The HTTP status and the response headers (lower-case names). |
| `raw` | The whole decoded JSON body, including fields this SDK does not model yet. |

The SDK never computes or assumes credit costs. Read them from the response.

Fields are named exactly like the API's JSON fields. The API can add new fields at any time; the models ignore ones they do not know and `raw` keeps them.

## Methods

### `search_locations(q, *, country=None)`

Search places by the start of a name (at least 3 characters). Free.

```python
resp = client.search_locations("lon", country="gb")
for hit in resp.data:
    print(hit.id, hit.name, hit.population, hit.weather_available)
```

### `nearest_location(lat, lon, country)`

The place nearest a point, inside one country. Free.

```python
resp = client.nearest_location(51.5, -0.12, "gb")
print(resp.data.id, resp.data.requested.distance_km)
```

### `get_location(location_id)`

One place by id. Free.

```python
resp = client.get_location("gb/london")
print(resp.data.name, resp.data.timezone, resp.data.coverage.first_year)
```

### `get_daily(location=None, *, start, end, lat=None, lon=None, country=None, units=None, format="json")`

Daily values from `start` to `end` inclusive. Dates can be `datetime.date` objects or `"YYYY-MM-DD"` strings.

```python
resp = client.get_daily("gb/london", start="2024-01-01", end="2024-01-31", units="imperial")
print(resp.meta.units.temperature)       # "F"
print(resp.data[0].daily_max_temp)
```

### `get_hourly(location=None, *, date, days=None, lat=None, lon=None, country=None, units=None, format="json")`

Hourly values for `days` consecutive local days starting at `date`. How many days one call may ask for, and how far back it can go, depends on your plan; call `get_me()` to see your plan's limits.

```python
resp = client.get_hourly("gb/london", date="2024-01-15", days=1)
for row in resp.data:
    print(row.timestamp_utc, row.temperature, row.precipitation)
```

### `get_monthly(location=None, *, lat=None, lon=None, country=None, units=None)`

One row per calendar month on file, oldest first.

```python
resp = client.get_monthly("gb/london")
print(resp.data[-1].year, resp.data[-1].month, resp.data[-1].monthly_total_rain)
```

### `get_yearly(location=None, *, lat=None, lon=None, country=None, units=None)`

One row per calendar year on file, oldest first.

```python
resp = client.get_yearly("gb/london")
print([(r.year, r.yearly_avg_temp) for r in resp.data])
```

### `get_normals(location=None, *, month=None, lat=None, lon=None, country=None, units=None)`

Climate normals: `data.monthly` and `data.day_of_year`. `month` (1 to 12) narrows both.

```python
resp = client.get_normals("gb/london", month=7)
print(resp.data.monthly[0].avg_temp, len(resp.data.day_of_year))
```

### `get_records(location=None, *, lat=None, lon=None, country=None, units=None)`

The hottest, coldest, wettest and windiest day on file.

```python
resp = client.get_records("gb/london")
for rec in resp.data:
    print(rec.metric, rec.value, rec.unit, rec.occurred_on)
```

### `get_coverage(country=None)`

Countries served, with the first year and last published day. Free.

```python
resp = client.get_coverage("gb")
print(resp.data.countries[0].last_date)
```

### `get_me()`

Your plan, credit balance and limits. Free.

```python
resp = client.get_me()
print(resp.data.plan.id, resp.meta.credits_remaining, resp.data.rate_limit.per_minute)
```

## Units

`units="metric"` (the default) or `units="imperial"` on every data method. Field names do not change; the unit of each value is in `meta.units`.

```python
resp = client.get_records("gb/london", units="imperial")
print(resp.meta.units.temperature, resp.meta.units.wind_speed)   # F mph
```

## CSV

`get_daily` and `get_hourly` accept `format="csv"` and then return a `CsvResponse` instead:

```python
resp = client.get_daily("gb/london", start="2023-01-01", end="2023-12-31", format="csv")
with open("london-2023.csv", "w", newline="") as fh:
    fh.write(resp.text)
print(resp.credits_used, resp.credits_remaining, resp.rate_limit.remaining)
```

CSV has no `meta`, so `credits_used` and `credits_remaining` come from the `X-Credits-*` headers. Errors are still JSON and raise the usual typed errors.

## Errors

Every error is a `PastClimateError`. Errors from an HTTP answer are `ApiError` and carry `code`, `message`, `docs_url` and `status`, plus `retry_after`, `upgrade_url`, `rate_limit` and `headers`. There is one class per category:

| Class | Codes |
|---|---|
| `AuthenticationError` | `missing_key`, `invalid_key`, `key_revoked`, `email_not_verified`, `account_suspended` |
| `InvalidRequestError` | `invalid_request`, `range_too_large`, `key_in_query`, `method_not_allowed`, `cors_not_supported` |
| `NotFoundError` | `location_not_found`, `not_published`, `location_blocked`, `not_found` |
| `PlanRequiredError` | `plan_required` |
| `RateLimitError` | `rate_limited`, `daily_request_cap_reached` |
| `QuotaExceededError` | `quota_exceeded` |
| `ServerError` | `internal_error`, `api_disabled`, `metering_unavailable` |

A code the SDK does not know yet is mapped by HTTP status, or raised as plain `ApiError`, so new codes never crash your code. `NetworkError` means no answer arrived (connection failure or timeout) after the retries ran out. A request the SDK refuses before sending (for example `get_monthly()` with no place) raises `InvalidRequestError` with `status == 0`.

```python
from pastclimate import (
    Client, NotFoundError, QuotaExceededError, RateLimitError, ApiError, NetworkError,
)

client = Client()
try:
    resp = client.get_daily("gb/nowhere", start="2024-01-01", end="2024-01-31")
except NotFoundError as err:
    print("Unknown place or no data:", err.code, err.message)
except QuotaExceededError as err:
    print("Out of credits. Upgrade here:", err.upgrade_url)
except RateLimitError as err:
    print("Slow down. Try again in", err.retry_after, "seconds")
except ApiError as err:
    print(err.status, err.code, err.message, err.docs_url)
except NetworkError as err:
    print("Could not reach the API:", err)
```

Branch on `code`, not on `message`. Failed requests are not charged.

## Retries

The client retries automatically, up to `max_retries` times (default 2):

- **429 with a `Retry-After` header:** waits that many seconds, then retries.
- **5xx and network errors (including timeouts):** retries with exponential backoff and jitter.
- **Never retried:** every other 4xx, and a 429 without `Retry-After`. A 429 without `Retry-After` means waiting will not help, for example when the free credits are permanently used up.

If `Retry-After` is longer than `max_retry_after` (default 60 seconds), the error is raised straight away instead of sleeping, so a call never hangs for hours, for example until the daily limit resets. Read `err.retry_after` and decide for yourself. Set `max_retries=0` to turn retries off.

## Using your own HTTP library

The default transport uses only the standard library. To use `requests`, `httpx` or a test double, pass `transport`, a callable that takes an `HTTPRequest` and returns an `HTTPResponse` (status, lower-case header names, body bytes). It should raise `OSError` (for example `ConnectionError` or `TimeoutError`) when no answer arrives, and should not raise for non-2xx statuses.

```python
from pastclimate import Client, HTTPRequest, HTTPResponse

def transport(request: HTTPRequest) -> HTTPResponse:
    ...

client = Client("YOUR_API_KEY", transport=transport)
```

## Development

```bash
python3 -m unittest discover -s tests -t .
```

The tests use a mocked transport, plus one file that talks to a local server on 127.0.0.1. `examples/quickstart.py` calls the live API, and only when `PASTCLIMATE_API_KEY` is set.

## License

MIT. See [LICENSE](LICENSE).
