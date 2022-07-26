"""Query alert information from AeroAPI and present it to a frontend service"""
import os
from datetime import datetime
from typing import Dict, Any, Tuple, Set

import copy
import json
import requests
from flask import Flask, jsonify, Response, request
from flask.logging import create_logger
from flask_cors import CORS

from sqlalchemy import (exc, create_engine, MetaData, Table,
                        Column, Integer, Boolean, Text, insert,
                        Date, DateTime, delete, update)
from sqlalchemy.sql import func, and_
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
    exists
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
    Column("time_alert_received", DateTime(timezone=True), server_default=func.now()),
    # Store time in UTC that the alert was received
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


def delete_from_table(fa_alert_id: int):
    """
    Delete alert config from SQL Alert Configurations table based on FA Alert ID.
    Returns 0 on success, -1 otherwise.
    """
    try:
        with engine.connect() as conn:
            stmt = delete(aeroapi_alert_configurations).where(aeroapi_alert_configurations.c.fa_alert_id == fa_alert_id)
            conn.execute(stmt)
            conn.commit()
            logger.info(f"Data successfully deleted from {aeroapi_alert_configurations.name}")
    except exc.SQLAlchemyError as e:
        logger.error(f"SQL error occurred during deletion from table {aeroapi_alert_configurations.name}: {e}")
        return -1
    return 0


def modify_from_table(fa_alert_id: int, modified_data: Dict[str, Any]):
    """
    Updates alert config from SQL Alert Configurations table based on FA Alert ID.
    Returns 0 on success, -1 otherwise.
    """
    try:
        with engine.connect() as conn:
            stmt = (update(aeroapi_alert_configurations).
                    where(aeroapi_alert_configurations.c.fa_alert_id == fa_alert_id))
            conn.execute(stmt, modified_data)
            conn.commit()
            logger.info(f"Data successfully updated in table {aeroapi_alert_configurations.name}")
    except exc.SQLAlchemyError as e:
        logger.error(f"SQL error occurred during updating in table {aeroapi_alert_configurations.name}: {e}")
        return -1
    return 0


def get_alerts_not_from_app(existing_alert_ids: Set[int]):
    """
    Function to get all alert configurations that were not configured
    inside the webapp. Follows exact same format as SQL table, with extra
    "is_from_app" column set to False. Takes in existing_alerts parameter
    as a list to compare with configured alerts to ensure no overlap.
    Returns a dictionary of all the alerts. If no alerts exist, return None.
    """
    api_resource = "/alerts"
    logger.info(f"Making AeroAPI request to GET {api_resource}")
    result = AEROAPI.get(f"{AEROAPI_BASE_URL}{api_resource}")
    if not result:
        return []
    all_alerts = result.json()["alerts"]
    if not all_alerts:
        return []
    alerts_not_from_app = []
    for alert in all_alerts:
        if int(alert["id"]) not in existing_alert_ids:
            # Don't have to catch key doesn't exist as AeroAPI guarantees
            # Keys will exist (just might be null)
            holder = {
                "fa_alert_id": alert["id"],
                "ident": alert["ident"],
                "origin": alert["origin"],
                "destination": alert["destination"],
                "aircraft_type": alert["aircraft_type"],
                "start_date": alert["start"],
                "end_date": alert["end"],
                "max_weekly": 1000,
                "eta": alert["eta"],
                "arrival": alert["events"]["arrival"],
                "cancelled": alert["events"]["cancelled"],
                "departure": alert["events"]["departure"],
                "diverted": alert["events"]["diverted"],
                "filed": alert["events"]["filed"],
                "is_from_app": False
            }
            alerts_not_from_app.append(holder)
    return alerts_not_from_app


def check_if_dup(alert_data) -> bool:
    """
    Check if given alert is a duplicate alert configured. Do this by checking the
    SQLite database. Return True if duplicate, False if not.
    """
    try:
        with engine.connect() as conn:
            stmt = select(aeroapi_alert_configurations).where(and_(
                aeroapi_alert_configurations.c.ident == alert_data["ident"],
                aeroapi_alert_configurations.c.destination == alert_data["destination"],
                aeroapi_alert_configurations.c.origin == alert_data["origin"],
                aeroapi_alert_configurations.c.aircraft_type == alert_data["aircraft_type"],
            ))
            result = conn.execute(stmt)
            conn.commit()
            return result.all()
    except exc.SQLAlchemyError as e:
        logger.error(f"SQL error occurred in checking for duplicate alert in table {aeroapi_alert_configurations.name}: {e}")
        raise e


@app.route("/modify", methods=["POST"])
def modify_alert():
    """
    Function to modify the alert given (with key "fa_alert_id" in the payload).
    Modifies the given alert via AeroAPI PUT call and also modifies the respective
    alert in the SQLite database. Returns JSON Response in form {"Success": True/False,
    "Description": <A detailed description of the response>}
    """
    r_success: bool = False
    r_description: str
    # Process json
    content_type = request.headers.get("Content-Type")
    data: Dict[str, Any]

    if content_type != "application/json":
        r_description = "Invalid content sent"
    else:
        data = request.json

        fa_alert_id = data.pop('fa_alert_id')

        # Make deep copy to send to AeroAPI - needs events in nested dictionary
        aeroapi_adjusted_data = copy.deepcopy(data)
        aeroapi_adjusted_data["events"] = {
            "arrival": aeroapi_adjusted_data.pop('arrival'),
            "departure": aeroapi_adjusted_data.pop('departure'),
            "cancelled": aeroapi_adjusted_data.pop('cancelled'),
            "diverted": aeroapi_adjusted_data.pop('diverted'),
            "filed": aeroapi_adjusted_data.pop('filed'),
        }
        # Rename start and end again
        aeroapi_adjusted_data["start"] = aeroapi_adjusted_data.pop("start_date")
        aeroapi_adjusted_data["end"] = aeroapi_adjusted_data.pop("end_date")

        api_resource = f"/alerts/{fa_alert_id}"
        logger.info(f"Making AeroAPI request to PUT {api_resource}")
        result = AEROAPI.put(f"{AEROAPI_BASE_URL}{api_resource}", json=aeroapi_adjusted_data)
        if result.status_code != 204:
            # return to front end the error, decode and clean the response
            try:
                processed_json = result.json()
                r_description = f"Error code {result.status_code} with the following description for alert configuration {fa_alert_id}: {processed_json['detail']}"
            except json.decoder.JSONDecodeError:
                r_description = f"Error code {result.status_code} for the alert configuration {fa_alert_id} could not be parsed into JSON. The following is the HTML response given: {result.text}"
        else:
            # Parse into datetime to update in SQLite table
            if data["start_date"]:
                data["start_date"] = datetime.strptime(data["start_date"], "%Y-%m-%d")
            if data["end_date"]:
                data["end_date"] = datetime.strptime(data["end_date"], "%Y-%m-%d")

            # Check if data was inserted into database properly
            if modify_from_table(fa_alert_id, data) == -1:
                r_description = (
                    "Error modifying the alert configuration from the SQL Database - since it was modified "
                    "on AeroAPI but not SQL, this means the alert will still be the original alert on the table - in "
                    "order to properly modify the alert please look in your SQL database."
                )
            else:
                r_success = True
                r_description = f"Request sent successfully, alert configuration {fa_alert_id} has been updated"

    return jsonify({"Success": r_success, "Description": r_description})


@app.route("/delete", methods=["POST"])
def delete_alert():
    """
    Function to delete the alert given (with key "fa_alert_id" in the payload).
    Deletes the given alert via AeroAPI DELETE call and then deletes it from the
    SQLite database. Returns JSON Response in form {"Success": True/False,
    "Description": <A detailed description of the response>}
    """
    r_success: bool = False
    r_description: str
    # Process json
    content_type = request.headers.get("Content-Type")
    data: Dict[str, Any]

    if content_type != "application/json":
        r_description = "Invalid content sent"
    else:
        data = request.json
        fa_alert_id = data['fa_alert_id']
        api_resource = f"/alerts/{fa_alert_id}"
        logger.info(f"Making AeroAPI request to DELETE {api_resource}")
        result = AEROAPI.delete(f"{AEROAPI_BASE_URL}{api_resource}", json=data)
        if result.status_code != 204:
            # return to front end the error, decode and clean the response
            try:
                processed_json = result.json()
                r_description = f"Error code {result.status_code} with the following description for alert configuration {fa_alert_id}: {processed_json['detail']}"
            except json.decoder.JSONDecodeError:
                r_description = f"Error code {result.status_code} for the alert configuration {fa_alert_id} could not be parsed into JSON. The following is the HTML response given: {result.text}"
        else:
            # Check if data was inserted into database properly
            if delete_from_table(fa_alert_id) == -1:
                r_description = "Error deleting the alert configuration from the SQL Database - since it was deleted \
                on AeroAPI but not SQL, this means the alert will still be shown on the table - in order to properly \
                delete the alert please look in your SQL database."
            else:
                r_success = True
                r_description = f"Request sent successfully, alert configuration {fa_alert_id} has been deleted"

    return jsonify({"Success": r_success, "Description": r_description})


@app.route("/posted_alerts")
def get_posted_alerts():
    """
    Function to return all the alerts that are currently configured
    via the SQL table.
    """
    data: Dict[str, Any] = {"posted_alerts": []}
    with engine.connect() as conn:
        stmt = select(aeroapi_alerts)
        result = conn.execute(stmt)
        conn.commit()
        for row in result:
            data["posted_alerts"].append(dict(row))

    return jsonify(data)


@app.route("/alert_configs")
def get_alert_configs():
    """
    Function to return all the alerts that are currently configured
    via the SQL table.
    """
    data: Dict[str, Any] = {"alert_configurations": []}
    existing_alert_ids = set()
    with engine.connect() as conn:
        stmt = select(aeroapi_alert_configurations)
        result = conn.execute(stmt)
        conn.commit()
        for row in result:
            row_holder = dict(row)
            row_holder["is_from_app"] = True
            data["alert_configurations"].append(row_holder)
            existing_alert_ids.add(row_holder["fa_alert_id"])

    # Append alerts not created from app
    alerts_not_from_app = get_alerts_not_from_app(existing_alert_ids)
    data["alert_configurations"].extend(alerts_not_from_app)

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
        logger.error(
            f"Alert POST request did not have one or more keys with data. Will process but will return 400: {e}")
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

        # Check if alert is duplicate
        if check_if_dup(data):
            r_description = f"Ticket error: alert has already been configured. Ticket has not been created"
        else:
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
                # Allow empty strings
                if data["start_date"] == "":
                    data["start_date"] = None
                if data["end_date"] == "":
                    data["end_date"] = None
                # Handle if dates are None - accept them but don't parse time
                if data["start_date"]:
                    data["start_date"] = datetime.strptime(data["start_date"], "%Y-%m-%d")
                if data["end_date"]:
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
