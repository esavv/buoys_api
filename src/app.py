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


TRACKED_ENDPOINTS = {"/buoy", "/buoy/history", "/stations"}


@app.after_request
def track_request(response):
    if not posthog or request.path not in TRACKED_ENDPOINTS:
        return response

    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    properties = {
        "endpoint": request.path,
        "method": request.method,
        "status_code": response.status_code,
        "cache_hit": getattr(g, "cache_hit", False),
        "ip": client_ip,
        "$ip": client_ip,
        "user_agent": request.headers.get("User-Agent"),
    }

    if request.path in {"/buoy", "/buoy/history"}:
        properties["station_id"] = request.args.get("id")

    posthog.capture(
        distinct_id=client_ip or "unknown",
        event="api_request",
        properties=properties,
    )

    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))