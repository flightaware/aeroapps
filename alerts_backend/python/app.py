"""Query alert information from AeroAPI and present it to a frontend service"""
import os
from datetime import timezone
from typing import Dict, Any, Union

import json
import requests
from flask import Flask, jsonify, Response, request
from flask_cors import CORS

from sqlalchemy import exc, create_engine, MetaData, Table, Column, Integer, String, insert

AEROAPI_BASE_URL = "https://aeroapi.flightaware.com/aeroapi"
AEROAPI_KEY = os.environ["AEROAPI_KEY"]
AEROAPI = requests.Session()
AEROAPI.headers.update({"x-apikey": AEROAPI_KEY})

# pylint: disable=invalid-name
app = Flask(__name__)
CORS(app)
UTC = timezone.utc
ISO_TIME = "%Y-%m-%dT%H:%M:%SZ"

# create the SQL engine using SQLite
engine = create_engine(
    "sqlite+pysqlite:////var/db/aeroapi_alerts/aeroapi_alerts.db", echo=False, future=True
)


def insert_into_db(data_to_insert: Dict[str, Union[str, int]]) -> int:
    """
    Insert object into the database based off of the engine.
    Assumes data_to_insert has values for all the keys:
    fa_alert_id, ident, origin, destination, aircraft_type, start_date, end_date.
    Returns 0 on success, -1 otherwise
    """
    table_name = "aeroapi_alerts_table"
    try:
        metadata_obj = MetaData()
        # create the table if it doesn't exist
        table_to_insert = Table(
            table_name,
            metadata_obj,
            Column("fa_alert_id", Integer, primary_key=True),
            Column("ident", String(30)),
            Column("origin", String(30)),
            Column("destination", String(30)),
            Column("aircraft_type", String(30)),
            Column("start_date", String(30)),
            Column("end_date", String(30)),
        )
        table_to_insert.create(engine, checkfirst=True)

        # insert the info given
        with engine.connect() as conn:
            stmt = insert(table_to_insert)
            conn.execute(stmt, data_to_insert)
            conn.commit()

    except exc.SQLAlchemyError as e:
        app.logger.error(f"SQL error occurred: {e}")
        return -1

    return 0


@app.route("/create", methods=["POST"])
def create_alert() -> Response:
    """
    Function to create an alert item via a POST request from the front-end.
    If 'max_weekly' not in payload, default value is 1000
    If 'events' not in payload, default value is all False
    Returns JSON Response in form {"Alert_id": <alert_id>, "Success": True/False}
    """
    # Process json
    content_type = request.headers.get("Content-Type")
    data: Dict[Any]
    response_frontend = {"Alert_id": None, "Success": False, "Description": None}
    if content_type == "application/json":
        data = request.json
    else:
        response_frontend["Description"] = "Invalid content sent"
        return jsonify(response_frontend)

    api_resource = "/alerts"

    # Check if max_weekly and events in data
    if "events" not in data:
        # Assume want all events to be false
        data["events"] = {
            "arrival": False,
            "departure": False,
            "cancelled": False,
            "diverted": False,
            "filed": False,
        }
    if "max_weekly" not in data:
        data["max_weekly"] = 1000

    app.logger.info(f"Making AeroAPI request to POST {api_resource}")
    result = AEROAPI.post(f"{AEROAPI_BASE_URL}{api_resource}", json=data)
    if result.status_code != 201:
        # return to front end the error, decode and clean the response
        response_frontend["Description"] = (f"""Error code {result.status_code} with 
        the following description: {json.loads(result.content.decode("utf-8"))['detail'].strip()}""")
        return jsonify(response_frontend)

    # Package created alert and put into database
    fa_alert_id = int(result.headers["Location"][8:])
    holder: Dict[str, Any] = data
    holder.pop("events")
    holder.pop("max_weekly")
    # rename dates to avoid sql keyword "end" issue
    holder["start_date"] = holder.pop("start")
    holder["end_date"] = holder.pop("end")
    database_data: Dict[str, Union[str, int]] = holder
    database_data["fa_alert_id"] = fa_alert_id

    response_frontend["Alert_id"] = fa_alert_id
    if insert_into_db(database_data) == -1:
        response_frontend["Description"] = "Database insertion error, check your database configuration"
        return jsonify(response_frontend)

    response_frontend["Success"] = True
    response_frontend["Description"] = "Request sent successfully"
    return jsonify(response_frontend)


app.run(host="0.0.0.0", port=5000, debug=True)
