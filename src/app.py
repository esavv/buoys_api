import logging
import os

from cachetools import TTLCache
from flask import Flask, jsonify, request

from fetch_buoy import get_buoy_reading
from fetch_stations import get_stations

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Cache: max 100 entries, 15 minute TTL
buoy_cache = TTLCache(maxsize=100, ttl=900)

# Stations cache: single entry, 24 hour TTL
stations_cache = TTLCache(maxsize=1, ttl=86400)

def get_station_name(buoy_id: str) -> str | None:
    """Look up a station name from the stations cache, fetching if needed."""
    cache_key = "all"
    if cache_key not in stations_cache:
        app.logger.info("Stations cache cold — fetching for name lookup")
        result = get_stations()
        if result["status"] == "success":
            stations_cache[cache_key] = result

    cached = stations_cache.get(cache_key)
    if not cached:
        return None

    for station in cached.get("stations", []):
        if station["id"] == buoy_id:
            return station["name"]
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

    # Check cache
    if buoy_id in buoy_cache:
        app.logger.info(f"Cache HIT: buoy_id={buoy_id}")
        return jsonify(buoy_cache[buoy_id])

    # Cache miss - fetch from NOAA
    app.logger.info(f"Cache MISS: buoy_id={buoy_id}")
    response = get_buoy_reading(buoy_id)

    if response["status"] == "error":
        app.logger.warning(f"Response: buoy_id={buoy_id} status=error msg={response.get('error_msg')}")
        return jsonify(response), 502

    response["name"] = get_station_name(buoy_id)

    # Cache successful responses only
    buoy_cache[buoy_id] = response
    app.logger.info(f"Response: buoy_id={buoy_id} status=success (cached)")
    return jsonify(response)


@app.route("/stations", methods=["GET"])
def stations():
    cache_key = "all"

    if cache_key in stations_cache:
        app.logger.info("Stations cache HIT")
        return jsonify(stations_cache[cache_key])

    app.logger.info("Stations cache MISS — fetching from NOAA")
    response = get_stations()

    if response["status"] == "error":
        app.logger.warning(f"Stations fetch error: {response.get('error_msg')}")
        return jsonify(response), 502

    stations_cache[cache_key] = response
    app.logger.info(f"Stations fetched: {response['count']} stations (cached)")
    return jsonify(response)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))