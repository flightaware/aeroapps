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
# Two tables: one to store alert configs, other to store alerts being sent as endpoint
table_name_alert_configs = "aeroapi_alert_configs_table"
table_name_alerts = "aeroapi_alerts_table"


@app.before_first_request
def create_tables():
    """
    Check if tables exists, and if it doesn't create them.
    Returns 0 on success, -1 otherwise
    """
    try:
        metadata_obj = MetaData()
        # Create the tables if they don't exist
        # Table for storing the configurations of the alerts created
        table_to_create_alert_configs = Table(
            table_name_alert_configs,
            metadata_obj,
            Column("fa_alert_id", Integer, primary_key=True),
            Column("ident", String()),
            Column("origin", String()),
            Column("destination", String()),
            Column("aircraft_type", String()),
            Column("start_date", String()),
            Column("end_date", String()),
            Column("max_weekly", Integer),
            Column("eta", Integer),
            Column("arrival", Boolean),
            Column("cancelled", Boolean),
            Column("departure", Boolean),
            Column("diverted", Boolean),
            Column("filed", Boolean),
        )
        table_to_create_alert_configs.create(engine, checkfirst=True)
        app.logger.info(f"Table {table_name_alert_configs} successfully created / updated")
        # Table for storing the actual alerts sent from AeroAPI to this endpoint
        table_to_create_alerts = Table(
            table_name_alerts,
            metadata_obj,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("long_description", String()),
            Column("short_description", String()),
            Column("summary", String()),
            Column("event_code", String()),
            Column("alert_id", Integer),
            Column("fa_flight_id", String()),
            Column("ident", String()),
            Column("registration", String()),
            Column("aircraft_type", String()),
            Column("origin", String()),
            Column("destination", String())
        )
        table_to_create_alerts.create(engine, checkfirst=True)
        app.logger.info(f"Table {table_name_alerts} successfully created / updated")
    except exc.SQLAlchemyError as e:
        app.logger.error(f"SQL error occurred during creation of table (CRITICAL - INSERT WILL FAIL): {e}")
        return -1

    return 0


def insert_into_table(data_to_insert: Dict[str, Union[str, int, bool]], table_name: str) -> int:
    """
    Insert object into the table based off of the engine.
    Assumes data_to_insert has values for all the keys
    that are in the data_to_insert variable.
    Returns 0 on success, -1 otherwise
    """
    try:
        metadata = MetaData()
        table_to_insert = Table(table_name, metadata, autoload_with=engine)

        with engine.connect() as conn:
            stmt = insert(table_to_insert)
            conn.execute(stmt, data_to_insert)
            conn.commit()

            app.logger.info(f"Data successfully inserted into table {table_name}")

    except exc.SQLAlchemyError as e:
        app.logger.error(f"SQL error occurred during insertion into table: {e}")
        return -1

    return 0


@app.route("/post", methods=["POST"])
def handle_alert() -> Response:
    """
    Function to receive AeroAPI POST requests.
    """
    # Form response
    r_title: str
    r_reason: str
    r_detail: str
    r_status: int
    data: Dict[Any] = request.json
    # Process data by getting things needed
    # Use get() if value doesn't exist -> value is None
    processed_data: Dict[Any] = dict()
    processed_data["long_description"] = data.get("long_description", None)
    processed_data["short_description"] = data.get("short_description", None)
    processed_data["summary"] = data.get("summary", None)
    processed_data["event_code"] = data.get("event_code", None)
    processed_data["alert_id"] = data.get("alert_id", None)
    processed_data["fa_flight_id"] = data.get("flight", None).get("fa_flight_id", None)
    processed_data["ident"] = data.get("flight", None).get("ident", None)
    processed_data["registration"] = data.get("flight", None).get("registration", None)
    processed_data["aircraft_type"] = data.get("flight", None).get("aircraft_type", None)
    processed_data["origin"] = data.get("flight", None).get("origin", None)
    processed_data["destination"] = data.get("flight", None).get("destination", None)
    # Check if any values weren't processed
    if None not in processed_data.values():
        if insert_into_table(processed_data, table_name_alerts) != -1:
            r_title = "Successful request"
            r_reason = "Request processed and stored successfully"
            r_detail = "Request processed and stored successfully"
            r_status = 200
        else:
            r_title = "Error inserting into SQL Database"
            r_reason = "Inserting into the database had an error"
            r_detail = "Inserting into the database had an error"
            r_status = 500
    else:
        r_title = "Missing info in request"
        r_reason = "At least one value to insert in the database is missing in the post request"
        r_detail = "At least one value to insert in the database is missing in the post request"
        r_status = 400
    return jsonify({"title": r_title, "reason": r_reason, "detail": r_detail, "status": r_status})


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
            data.pop("max_weekly")
            # rename dates to avoid sql keyword "end" issue
            # default to None in case a user directly submits an incomplete payload
            data["start_date"] = data.pop("start", None)
            data["end_date"] = data.pop("end", None)
            data["fa_alert_id"] = fa_alert_id

            if insert_into_table(data, table_name_alert_configs) == -1:
                r_description = f"Database insertion error, check your database configuration. Alert has still been configured with alert id {r_alert_id}"
            else:
                r_success = True
                r_description = f"Request sent successfully with alert id {r_alert_id}"

    return jsonify({"Alert_id": r_alert_id, "Success": r_success, "Description": r_description})


app.run(host="0.0.0.0", port=5000, debug=True)
