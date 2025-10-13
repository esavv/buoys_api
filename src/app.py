import os
from flask import Flask, jsonify, request

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

    print(f"Received buoy ID: {buoy_id}")

    response = {
        "status": "success",
        "last_updated": "10:26 am EDT",
        "sig_wave_height": "14.8 ft",
        "swell_height": "7.5 ft",
        "swell_period": "11.8 s",
        "swell_direction": "SE",
    }
    return jsonify(response)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))