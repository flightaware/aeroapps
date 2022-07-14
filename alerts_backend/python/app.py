"""Query alert information from AeroAPI and present it to a frontend service"""
import os
from datetime import datetime
from typing import Dict, Any, Tuple

import json
import requests
from flask import Flask, jsonify, Response, request
from flask.logging import create_logger
from flask_cors import CORS

from sqlalchemy import (exc, create_engine, MetaData, Table,
                        Column, Integer, Boolean, Text, insert, Date, DateTime)
from sqlalchemy.sql import func
from sqlalchemy import (
    exc,
    create_engine,
    MetaData,
    Table,
    Column,
    Integer,
    Boolean,
    Text,
    insert,
    Date,
    select,
)

AEROAPI_BASE_URL = "https://aeroapi.flightaware.com/aeroapi"
AEROAPI_KEY = os.environ["AEROAPI_KEY"]
AEROAPI = requests.Session()
AEROAPI.headers.update({"x-apikey": AEROAPI_KEY})

# pylint: disable=invalid-name
app = Flask(__name__)
logger = create_logger(app)
CORS(app)

# create the SQL engine using SQLite
engine = create_engine(
    "sqlite+pysqlite:////var/db/aeroapi_alerts/aeroapi_alerts.db", echo=False, future=True
)
# Set journal_mode to WAL to enable reading and writing concurrently
with engine.connect() as conn_wal:
    conn_wal.exec_driver_sql("PRAGMA journal_mode=WAL")
    conn_wal.commit()

# Define tables and metadata to insert and create
metadata_obj = MetaData()
# Table for alert configurations
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
# Table for POSTed alerts
aeroapi_alerts = Table(
            "aeroapi_alerts",
            metadata_obj,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("time_alert_received", DateTime(timezone=True), server_default=func.now()), # Store time in UTC that the alert was received
            Column("long_description", Text),
            Column("short_description", Text),
            Column("summary", Text),
            Column("event_code", Text),
            Column("alert_id", Integer),
            Column("fa_flight_id", Text),
            Column("ident", Text),
            Column("registration", Text),
            Column("aircraft_type", Text),
            Column("origin", Text),
            Column("destination", Text)
        )


def create_tables():
    """
    Check if the table(s) exist, and if they don't create them.
    Returns None, raises exception if error
    """
    try:
        # Create the table(s) if they don't exist
        metadata_obj.create_all(engine)
        logger.info("Table(s) successfully created (if not already created)")
    except exc.SQLAlchemyError as e:
        # Since creation of table(s) is a critical error, raise exception
        logger.error(
            f"SQL error occurred during creation of table(s) (CRITICAL - THROWING ERROR): {e}"
        )
        raise e


def insert_into_table(data_to_insert: Dict[str, Any], table: Table) -> int:
    """
    Insert object into the database based off of the table.
    Assumes data_to_insert has values for all the keys
    that are in the data_to_insert variable, and also that
    table is a valid SQLAlchemy Table variable inside the database.
    Returns 0 on success, -1 otherwise
    """
    try:
        with engine.connect() as conn:
            stmt = insert(table)
            conn.execute(stmt, data_to_insert)
            conn.commit()
            logger.info(f"Data successfully inserted into table {table.name}")
    except exc.SQLAlchemyError as e:
        logger.error(f"SQL error occurred during insertion into table {table.name}: {e}")
        return -1
    return 0


@app.rout("/delete", methods=["POST"])
def delete_alert():
    r_success: bool = False
    r_description: str
    # Process json
    content_type = request.headers.get("Content-Type")
    data: Dict[str, Any]

    if content_type != "application/json":
        r_description = "Invalid content sent"
    else:
        data = request.json
        api_resource = f"/alerts/{data['alert_id']}"
        logger.info(f"Making AeroAPI request to POST {api_resource}")
        result = AEROAPI.post(f"{AEROAPI_BASE_URL}{api_resource}", json=data)
        if result.status_code != 204:
            # return to front end the error, decode and clean the response
            try:
                processed_json = result.json()
                r_description = f"Error code {result.status_code} with the following description: {processed_json['detail']}"
            except json.decoder.JSONDecodeError:
                r_description = f"Error code {result.status_code} could not be parsed into JSON. The following is the HTML response given: {result.text}"
        else:
            r_success = True
            r_description = f"Request sent successfully, alert configuration {data['alert_id']} has been deleted"
    return jsonify({"Success": r_success, "Description": r_description})

                
@app.route("/alert_configs")
def get_alert_configs():
    """
    Function to return all the alerts that are currently configured
    via the SQL table.
    """
    data: Dict[str, Any] = {"alert_configurations": []}
    with engine.connect() as conn:
        stmt = select(aeroapi_alert_configurations)
        result = conn.execute(stmt)
        conn.commit()
        for row in result:
            data["alert_configurations"].append(dict(row))

    return jsonify(data)


@app.route("/post", methods=["POST"])
def handle_alert() -> Tuple[Response, int]:
    """
    Function to receive AeroAPI POST requests. Filters the request
    and puts the necessary data into the SQL database.
    Returns a JSON Response and also the status code in a tuple.
    """
    # Form response
    r_title: str
    r_detail: str
    r_status: int
    data: Dict[str, Any] = request.json
    # Process data by getting things needed
    processed_data: Dict[str, Any]
    try:
        processed_data = {
            "long_description": data["long_description"],
            "short_description": data["short_description"],
            "summary": data["summary"],
            "event_code": data["event_code"],
            "alert_id": data["alert_id"],
            "fa_flight_id": data["flight"]["fa_flight_id"],
            "ident": data["flight"]["ident"],
            "registration": data["flight"]["registration"],
            "aircraft_type": data["flight"]["aircraft_type"],
            "origin": data["flight"]["origin"],
            "destination": data["flight"]["destination"],
        }

        # Check if data was inserted into database properly
        if insert_into_table(processed_data, aeroapi_alerts) == -1:
            r_title = "Error inserting into SQL Database"
            r_detail = "Inserting into the database had an error"
            r_status = 500
        else:
            r_title = "Successful request"
            r_detail = "Request processed and stored successfully"
            r_status = 200
    except KeyError as e:
        # If value doesn't exist, do not insert into table and produce error
        logger.error(f"Alert POST request did not have one or more keys with data. Will process but will return 400: {e}")
        r_title = "Missing info in request"
        r_detail = "At least one value to insert in the database is missing in the post request"
        r_status = 400

    return jsonify({"title": r_title, "detail": r_detail, "status": r_status}), r_status


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
    r_description: str
    # Process json
    content_type = request.headers.get("Content-Type")
    data: Dict[str, Any]

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

        logger.info(f"Making AeroAPI request to POST {api_resource}")
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

            if insert_into_table(data, aeroapi_alert_configurations) == -1:
                r_description = f"Database insertion error, check your database configuration. Alert has still been configured with alert id {r_alert_id}"
            else:
                r_success = True
                r_description = f"Request sent successfully with alert id {r_alert_id}"

    return jsonify({"Alert_id": r_alert_id, "Success": r_success, "Description": r_description})


if __name__ == "__main__":
    # Create the table if it wasn't created before startup
    create_tables()
    app.run(host="0.0.0.0", port=5000, debug=True)
