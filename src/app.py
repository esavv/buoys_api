import logging
import os

from cachetools import TTLCache
from dotenv import load_dotenv
from flask import Flask, g, jsonify, request
from posthog import Posthog

from fetch_buoy import get_buoy_history, get_buoy_reading
from fetch_stations import get_stations

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

posthog_api_key = os.environ.get("POSTHOG_API_KEY")
if posthog_api_key:
    posthog = Posthog(posthog_api_key, host="https://us.i.posthog.com")
    app.logger.info("PostHog analytics enabled")
else:
    posthog = None
    app.logger.warning("POSTHOG_API_KEY not set — analytics disabled")

# Cache: max 100 entries, 15 minute TTL
buoy_cache = TTLCache(maxsize=100, ttl=900)

# History cache: max 100 entries, 15 minute TTL
buoy_history_cache = TTLCache(maxsize=100, ttl=900)

# Stations cache: single entry, 24 hour TTL
stations_cache = TTLCache(maxsize=1, ttl=86400)

TRACKED_ENDPOINTS = {"/buoy", "/buoy/history", "/stations"}
ANALYTICS_EVENTS = {
    "app opened",
    "screen viewed",
    "favorite added by id",
    "favorite added from map",
    "favorite removed",
    "favorite reordered",
    "add buoy opened",
    "chart interacted",
}
CLIENT_SOURCES = {"ios_app", "ios_widget"}
ANALYTICS_ID_HEADER = "X-Buoys-Analytics-ID"
CLIENT_SOURCE_HEADER = "X-Buoys-Client"


def get_client_ip() -> str | None:
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()
    return client_ip


def get_client_source() -> str | None:
    source = request.headers.get(CLIENT_SOURCE_HEADER)
    return source if source in CLIENT_SOURCES else None


def get_distinct_id(client_ip: str | None) -> str:
    analytics_id = request.headers.get(ANALYTICS_ID_HEADER)
    if analytics_id:
        return analytics_id[:128]
    return client_ip or "unknown"


def sanitize_analytics_value(value):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float, str)):
        return value
    if isinstance(value, list):
        return [sanitize_analytics_value(item) for item in value[:20]]
    if isinstance(value, dict):
        return sanitize_analytics_properties(value)
    return str(value)


def sanitize_analytics_properties(properties: dict) -> dict:
    sanitized = {}
    for key, value in properties.items():
        if len(sanitized) >= 50:
            break
        if not isinstance(key, str):
            continue
        sanitized[key[:80]] = sanitize_analytics_value(value)
    return sanitized


def capture_event(event: str, distinct_id: str, properties: dict) -> None:
    if not posthog:
        return

    posthog.capture(
        distinct_id=distinct_id,
        event=event,
        properties=properties,
    )


def get_station_metadata(buoy_id: str) -> dict | None:
    """Look up station metadata from the stations cache, fetching if needed."""
    cache_key = "all"
    if cache_key not in stations_cache:
        app.logger.info("Stations cache cold — fetching for metadata lookup")
        result = get_stations()
        if result["status"] == "success":
            stations_cache[cache_key] = result

    cached = stations_cache.get(cache_key)
    if not cached:
        return None

    for station in cached.get("stations", []):
        if station["id"] == buoy_id:
            return station
    return None


@app.route("/buoy", methods=["GET"])
def buoy():
    buoy_id = request.args.get("id")

    if not buoy_id:
        app.logger.warning("Request missing 'id' parameter")
        response = {
            "status": "error",
            "error_msg": "Missing required query parameter 'id'.",
        }
        return jsonify(response), 400

    app.logger.info(f"Request: buoy_id={buoy_id}")

    if buoy_id in buoy_cache:
        app.logger.info(f"Cache HIT: buoy_id={buoy_id}")
        g.cache_hit = True
        return jsonify(buoy_cache[buoy_id])

    # Cache miss - fetch from NOAA
    app.logger.info(f"Cache MISS: buoy_id={buoy_id}")
    response = get_buoy_reading(buoy_id)

    if response["status"] == "error":
        app.logger.warning(f"Response: buoy_id={buoy_id} status=error msg={response.get('error_msg')}")
        return jsonify(response), 502

    station_metadata = get_station_metadata(buoy_id)
    if station_metadata:
        response["name"] = station_metadata.get("name")
        response["lat"] = station_metadata.get("lat")
        response["lon"] = station_metadata.get("lon")

    # Cache successful responses only
    buoy_cache[buoy_id] = response
    app.logger.info(f"Response: buoy_id={buoy_id} status=success (cached)")
    return jsonify(response)


@app.route("/buoy/history", methods=["GET"])
def buoy_history():
    buoy_id = request.args.get("id")
    hours_arg = request.args.get("hours", "24")

    if not buoy_id:
        app.logger.warning("History request missing 'id' parameter")
        response = {
            "status": "error",
            "error_msg": "Missing required query parameter 'id'.",
        }
        return jsonify(response), 400

    try:
        hours = int(hours_arg)
    except ValueError:
        app.logger.warning(f"History request invalid hours: buoy_id={buoy_id} hours={hours_arg}")
        response = {
            "status": "error",
            "error_msg": "Query parameter 'hours' must be a positive integer.",
        }
        return jsonify(response), 400

    if hours is None or hours <= 0:
        app.logger.warning(f"History request invalid hours: buoy_id={buoy_id} hours={hours_arg}")
        response = {
            "status": "error",
            "error_msg": "Query parameter 'hours' must be a positive integer.",
        }
        return jsonify(response), 400

    app.logger.info(f"History request: buoy_id={buoy_id} hours={hours}")
    cache_key = f"{buoy_id}:{hours}"

    if cache_key in buoy_history_cache:
        app.logger.info(f"History cache HIT: buoy_id={buoy_id} hours={hours}")
        g.cache_hit = True
        return jsonify(buoy_history_cache[cache_key])

    app.logger.info(f"History cache MISS: buoy_id={buoy_id} hours={hours}")
    response = get_buoy_history(buoy_id, hours)

    if response["status"] == "error":
        app.logger.warning(f"History response: buoy_id={buoy_id} status=error msg={response.get('error_msg')}")
        return jsonify(response), 502

    station_metadata = get_station_metadata(buoy_id)
    if station_metadata:
        response["name"] = station_metadata.get("name")

    buoy_history_cache[cache_key] = response
    app.logger.info(f"History response: buoy_id={buoy_id} hours={hours} status=success (cached)")
    return jsonify(response)


@app.route("/stations", methods=["GET"])
def stations():
    cache_key = "all"

    if cache_key in stations_cache:
        app.logger.info("Stations cache HIT")
        g.cache_hit = True
        return jsonify(stations_cache[cache_key])

    app.logger.info("Stations cache MISS — fetching from NOAA")
    response = get_stations()

    if response["status"] == "error":
        app.logger.warning(f"Stations fetch error: {response.get('error_msg')}")
        return jsonify(response), 502

    stations_cache[cache_key] = response
    app.logger.info(f"Stations fetched: {response['count']} stations (cached)")
    return jsonify(response)


@app.route("/analytics/events", methods=["POST"])
def analytics_events():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"status": "error", "error_msg": "Expected JSON object."}), 400

    event = payload.get("event")
    distinct_id = payload.get("distinct_id")
    source = payload.get("source")
    properties = payload.get("properties", {})

    if event not in ANALYTICS_EVENTS:
        return jsonify({"status": "error", "error_msg": "Unsupported analytics event."}), 400
    if not isinstance(distinct_id, str) or not distinct_id.strip():
        return jsonify({"status": "error", "error_msg": "Missing analytics distinct_id."}), 400
    if source not in CLIENT_SOURCES:
        return jsonify({"status": "error", "error_msg": "Unsupported analytics source."}), 400
    if not isinstance(properties, dict):
        return jsonify({"status": "error", "error_msg": "Analytics properties must be an object."}), 400

    client_ip = get_client_ip()
    event_properties = sanitize_analytics_properties(properties)
    event_properties.update({
        "source": source,
        "client_source": source,
        "ip": client_ip,
        "$ip": client_ip,
        "user_agent": request.headers.get("User-Agent"),
    })

    capture_event(event, distinct_id[:128], event_properties)
    return jsonify({"status": "success"})


@app.after_request
def track_request(response):
    if not posthog or request.path not in TRACKED_ENDPOINTS:
        return response

    client_ip = get_client_ip()
    client_source = get_client_source()
    distinct_id = get_distinct_id(client_ip)

    properties = {
        "endpoint": request.path,
        "method": request.method,
        "status_code": response.status_code,
        "cache_hit": getattr(g, "cache_hit", False),
        "ip": client_ip,
        "$ip": client_ip,
        "user_agent": request.headers.get("User-Agent"),
    }
    if client_source:
        properties["client_source"] = client_source

    if request.path in {"/buoy", "/buoy/history"}:
        properties["station_id"] = request.args.get("id")

    capture_event("api_request", distinct_id, properties)

    if client_source == "ios_widget" and request.path == "/buoy":
        capture_event("widget data fetched", distinct_id, properties)

    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))