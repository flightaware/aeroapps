"""Query alert information from AeroAPI and present it to a frontend service"""
import os
from datetime import timezone
from typing import Dict, Any, Union

import json
import requests
from flask import Flask, jsonify, Response, request
from flask_cors import CORS

from sqlalchemy import (exc, create_engine, MetaData, Table,
                        Column, Integer, Boolean, String, insert, delete, select)

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
table_name = "aeroapi_alerts_table"


@app.before_first_request
def create_table():
    """
    Check if table exists, and if it doesn't create it.
    Returns 0 on success, -1 otherwise
    """
    try:
        metadata_obj = MetaData()
        # create the table if it doesn't exist
        table_to_create = Table(
            table_name,
            metadata_obj,
            Column("fa_alert_id", Integer, primary_key=True),
            Column("ident", String(30), ),
            Column("origin", String(30)),
            Column("destination", String(30)),
            Column("aircraft_type", String(30)),
            Column("start_date", String(30)),
            Column("end_date", String(30)),
            Column("max_weekly", Integer),
            Column("eta", Integer),
            Column("arrival", Boolean),
            Column("cancelled", Boolean),
            Column("departure", Boolean),
            Column("diverted", Boolean),
            Column("filed", Boolean),

        )
        table_to_create.create(engine, checkfirst=True)
        app.logger.info("Table successfully created / updated")
    except exc.SQLAlchemyError as e:
        app.logger.error(f"SQL error occurred during creation of table (CRITICAL - INSERT WILL FAIL): {e}")
        return -1

    return 0


def insert_into_db(data_to_insert: Dict[str, Union[str, int, bool]]) -> int:
    """
    Insert object into the database based off of the engine.
    Assumes data_to_insert has values for all the keys:
    fa_alert_id, ident, origin, destination, aircraft_type, start_date, end_date.
    Returns 0 on success, -1 otherwise
    """
    try:
        metadata = MetaData()
        table_to_insert = Table(table_name, metadata, autoload_with=engine)

        with engine.connect() as conn:
            stmt = insert(table_to_insert)
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
            data.pop("events")
            data.pop("max_weekly")
            # rename dates to avoid sql keyword "end" issue
            # default to None in case a user directly submits an incomplete payload
            data["start_date"] = data.pop("start", None)
            data["end_date"] = data.pop("end", None)
            data["fa_alert_id"] = fa_alert_id

            if insert_into_db(data) == -1:
                r_description = f"Database insertion error, check your database configuration. Alert has still been configured with alert id {r_alert_id}"
            else:
                r_success = True
                r_description = f"Request sent successfully with alert id {r_alert_id}"

    return jsonify({"Alert_id": r_alert_id, "Success": r_success, "Description": r_description})


app.run(host="0.0.0.0", port=5000, debug=True)
