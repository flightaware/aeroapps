"""Query alert information from AeroAPI and present it to a frontend service"""
import os
from datetime import timezone

import requests
from flask import Flask, jsonify, abort, Response, request
from flask_caching import Cache
from flask_cors import CORS

from sqlalchemy import exc, create_engine, text

AEROAPI_BASE_URL = "https://aeroapi.flightaware.com/aeroapi"
AEROAPI_KEY = os.environ["AEROAPI_KEY"]
CACHE_TIME = int(os.environ["CACHE_TIME"])
AEROAPI = requests.Session()
AEROAPI.headers.update({"x-apikey": AEROAPI_KEY})

# prevents excessive AeroAPI queries on page refresh
CACHE_CONFIG = {"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": CACHE_TIME}
# pylint: disable=invalid-name
app = Flask(__name__)
CORS(app)
app.config.from_mapping(CACHE_CONFIG)
CACHE = Cache(app)
UTC = timezone.utc
ISO_TIME = "%Y-%m-%dT%H:%M:%SZ"

# connect to the database
engine = create_engine("sqlite+pysqlite:///:memory:", echo=False, future=True)


def insert_into_db(data_to_insert: dict) -> int:
    """
    Insert object into the database based off of the engine
    Returns 0 on success, -1 otherwise
    """
    try:
        with engine.begin() as conn:
            stmt = text("""CREATE TABLE ex_table (fa_alert_id int, ident char(255), origin char(255), destination char(255),
             aircraft_type char(255), start char(255), end char(255))""")
            conn.execute(stmt)
            stmt = text("""INSERT INTO ex_table (fa_alert_id, ident, origin, destination, aircraft_type, start, end)
             VALUES (:fa_alert_id, :ident, :origin, :destination, :aircraft_type, :start, :end)""")
            conn.execute(stmt, data_to_insert)
    except exc.SQLAlchemyError:
        return -1

    return 0


@app.route("/create", methods=["POST"])
def create_alert() -> Response:
    """
    Function to create an alert item via a POST request from the front-end.
    If 'max_weekly' not in payload, default value is 1000
    If 'events' not in payload, default value is all True
    Returns JSON Response in form {"Alert_id": <alert_id>, "Success": True/False}
    """
    # Process json
    content_type = request.headers.get("Content-Type")
    if content_type == "application/json":
        data = request.json
    elif content_type == "application/x-www-form-urlencoded":
        data = request.get_json(force=True)
    else:
        return jsonify({"Alert_id": None, "Success": False})

    api_resource = "/alerts"

    # Check if max_weekly and events in data
    if "max_weekly" not in data:
        data["max_weekly"] = 1000
    if "events" not in data:
        # Assume want all events to be true
        data["events"] = {
            "arrival": True,
            "departure": True,
            "cancelled": True,
            "diverted": True,
            "filed": True,
        }

    app.logger.info(f"Making AeroAPI request to POST {api_resource}")
    result = AEROAPI.post(f"{AEROAPI_BASE_URL}{api_resource}", json=data)
    if result.status_code != 201:
        abort(result.status_code)

    # Package created alert and put into database
    fa_alert_id = result.headers['Location'][8:]
    database_data = data
    database_data['fa_alert_id'] = int(fa_alert_id)
    insert_into_db(database_data)

    return jsonify({"Alert_id": fa_alert_id, "Success": True})


app.run(host="0.0.0.0", port=5000, debug=True)
