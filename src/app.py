import os
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request

from fetch_buoy import get_buoy_reading

app = Flask(__name__)

@app.route("/buoy", methods=["GET"])
def buoy():
    buoy_id = request.args.get("id")

    if not buoy_id:
        response = {
            "status": "error",
            "error_msg": "Missing required query parameter 'id'.",
        }
        return jsonify(response), 400

    now = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"[{now}] Received buoy ID: {buoy_id}")

    response = get_buoy_reading(buoy_id)

    if response["status"] == "error":
        return jsonify(response), 502

    return jsonify(response)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))