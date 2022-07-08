"""Query alert information from AeroAPI and present it to a frontend service"""
import os
from datetime import datetime
from typing import Dict, Any, Union

import json
import requests
from flask import Flask, jsonify, Response, request
from flask_cors import CORS

from sqlalchemy import (exc, create_engine, MetaData, Table,
                        Column, Integer, Boolean, Text, insert, Date)

AEROAPI_BASE_URL = "https://aeroapi.flightaware.com/aeroapi"
AEROAPI_KEY = os.environ["AEROAPI_KEY"]
AEROAPI = requests.Session()
AEROAPI.headers.update({"x-apikey": AEROAPI_KEY})

# pylint: disable=invalid-name
app = Flask(__name__)
CORS(app)

# create the SQL engine using SQLite
engine = create_engine(
    "sqlite+pysqlite:////var/db/aeroapi_alerts/aeroapi_alerts.db", echo=False, future=True
)

# Define table and metadata to insert and create
metadata_obj = MetaData()
aeroapi_alert_configurations = Table(
            "aeroapi_alert_configurations",
            metadata_obj,
            Column("fa_alert_id", Integer, primary_key=True),
            Column("ident", Text),
            Column("origin", Text),
            Column("destination", Text),
            Column("aircraft_type", Text),
            Column("start_date", Date),
            Column("end_date", Date),
            Column("max_weekly", Integer),
            Column("eta", Integer),
            Column("arrival", Boolean),
            Column("cancelled", Boolean),
            Column("departure", Boolean),
            Column("diverted", Boolean),
            Column("filed", Boolean),
        )


def create_table():
    """
    Check if the tables exist, and if they don't create them.
    Returns None, raises exception if error
    """
    try:
        # Create the table if it doesn't exist
        metadata_obj.create_all(engine)
        app.logger.info("Table successfully created (if not already created)")
    except exc.SQLAlchemyError as e:
        # Since creation of table is a critical error, raise exception
        app.logger.error(f"SQL error occurred during creation of table (CRITICAL - THROWING ERROR): {e}")
        raise e


def insert_into_db(data_to_insert: Dict[str, Union[str, int, bool]]) -> int:
    """
    Insert object into the database based off of the engine.
    Assumes data_to_insert has values for all the keys:
    fa_alert_id, ident, origin, destination, aircraft_type, start_date, end_date.
    Returns 0 on success, -1 otherwise
    """
    try:
        with engine.connect() as conn:
            stmt = insert(aeroapi_alert_configurations)
            conn.execute(stmt, data_to_insert)
            conn.commit()

            app.logger.info("Data successfully inserted into table")

    except exc.SQLAlchemyError as e:
        app.logger.error(f"SQL error occurred during insertion into table: {e}")
        return -1

    return 0


@app.route("/create", methods=["POST"])
def create_alert() -> Response:
    """
    Function to create an alert item via a POST request from the front-end.
    If 'max_weekly' not in payload, default value is 1000
    If 'events' not in payload, default value is all False
    Returns JSON Response in form {"Alert_id": <alert_id, -1 if no alert id produced>,
    "Success": True/False, "Description": <A detailed description of the response>}
    """
    # initialize response headers
    r_alert_id: int = -1
    r_success: bool = False
    r_description: str = ''
    # Process json
    content_type = request.headers.get("Content-Type")
    data: Dict[Any]

    if content_type != "application/json":
        r_description = "Invalid content sent"
    else:
        data = request.json
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
            try:
                processed_json = result.json()
                r_description = f"Error code {result.status_code} with the following description: {processed_json['detail']}"
            except json.decoder.JSONDecodeError:
                r_description = f"Error code {result.status_code} could not be parsed into JSON. The following is the HTML response given: {result.text}"
        else:
            # Package created alert and put into database
            fa_alert_id = int(result.headers["Location"][8:])
            r_alert_id = fa_alert_id
            # Flatten events to insert into database
            data["arrival"] = data["events"]["arrival"]
            data["departure"] = data["events"]["departure"]
            data["cancelled"] = data["events"]["cancelled"]
            data["diverted"] = data["events"]["diverted"]
            data["filed"] = data["events"]["filed"]
            data.pop("events")
            # Rename dates to avoid sql keyword "end" issue, and also change to Python datetime.datetime()
            # Default to None in case a user directly submits an incomplete payload
            data["start_date"] = data.pop("start", None)
            data["end_date"] = data.pop("end", None)
            data["start_date"] = datetime.strptime(data["start_date"], "%Y-%m-%d")
            data["end_date"] = datetime.strptime(data["end_date"], "%Y-%m-%d")
            data["fa_alert_id"] = fa_alert_id

            if insert_into_db(data) == -1:
                r_description = f"Database insertion error, check your database configuration. Alert has still been configured with alert id {r_alert_id}"
            else:
                r_success = True
                r_description = f"Request sent successfully with alert id {r_alert_id}"

    return jsonify({"Alert_id": r_alert_id, "Success": r_success, "Description": r_description})


if __name__ == "__main__":
    # Create the table if it wasn't created before startup
    create_table()
    app.run(host="0.0.0.0", port=5000, debug=True)
