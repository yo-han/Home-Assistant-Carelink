"""Carelink Token Generator - Web UI Server."""
import json
import logging
import os
import threading
from flask import Flask, render_template, jsonify, request

from carelink_auth import CarelinkAuth

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global state
auth_status = {
    "status": "idle",  # idle, running, success, error
    "message": "",
    "token_file": None
}
auth_thread = None

# Read region from options
def get_region():
    """Get region from add-on options."""
    options_file = "/data/options.json"
    if os.path.exists(options_file):
        with open(options_file) as f:
            options = json.load(f)
            return options.get("region", "eu")
    return "eu"

# Output path for logindata.json
def get_output_path():
    """Get the output path for logindata.json."""
    # Save to HA config directory
    ha_config = "/homeassistant"
    legacy_path = os.path.join(ha_config, "custom_components", "carelink")

    # Create directory if it doesn't exist
    os.makedirs(legacy_path, exist_ok=True)

    return os.path.join(legacy_path, "logindata.json")


@app.route("/")
def index():
    """Render the main page."""
    region = get_region()
    return render_template("index.html", region=region)


@app.route("/status")
def status():
    """Get current authentication status."""
    return jsonify(auth_status)


@app.route("/start", methods=["POST"])
def start_auth():
    """Start the authentication process."""
    global auth_thread, auth_status

    if auth_status["status"] == "running":
        return jsonify({"error": "Authentication already in progress"}), 400

    auth_status = {
        "status": "running",
        "message": "Starting authentication...",
        "token_file": None
    }

    region = get_region()
    output_path = get_output_path()

    def run_auth():
        global auth_status
        try:
            auth = CarelinkAuth(region=region, output_file=output_path)
            auth_status["message"] = "Opening browser for login..."

            result = auth.login()

            if result:
                auth_status = {
                    "status": "success",
                    "message": f"Login successful! Token saved to {output_path}",
                    "token_file": output_path
                }
            else:
                auth_status = {
                    "status": "error",
                    "message": "Login failed. Please try again.",
                    "token_file": None
                }
        except Exception as e:
            logger.exception("Authentication error")
            auth_status = {
                "status": "error",
                "message": "An internal error occurred during authentication. Please try again.",
                "token_file": None
            }

    auth_thread = threading.Thread(target=run_auth, daemon=True)
    auth_thread.start()

    return jsonify({"status": "started"})


@app.route("/reset", methods=["POST"])
def reset():
    """Reset the authentication status."""
    global auth_status
    auth_status = {
        "status": "idle",
        "message": "",
        "token_file": None
    }
    return jsonify({"status": "reset"})


if __name__ == "__main__":
    # Only allow connections from ingress
    app.run(host="0.0.0.0", port=8099)
