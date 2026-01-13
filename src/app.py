import logging
import os

from flask import Flask, jsonify, request

from fetch_buoy import get_buoy_reading

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)

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

    response = get_buoy_reading(buoy_id)

    if response["status"] == "error":
        app.logger.warning(f"Response: buoy_id={buoy_id} status=error msg={response.get('error_msg')}")
        return jsonify(response), 502

    app.logger.info(f"Response: buoy_id={buoy_id} status=success")
    return jsonify(response)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))