"""Query flight information from AeroAPI and present it to a frontend service"""

from datetime import datetime, timezone
import os
import random
from typing import Optional
import requests
from flask import Flask, jsonify, abort, Response
from flask_caching import Cache

AEROAPI_BASE_URL = "https://aeroapi.flightaware.com/aeroapi"
AEROAPI_KEY = os.environ["AEROAPI_KEY"]
CACHE_TIME = os.environ["CACHE_TIME"]
AEROAPI = requests.Session()
AEROAPI.headers.update({"x-apikey": AEROAPI_KEY})

# prevents excessive AeroAPI queries on page refresh
CACHE_CONFIG = {"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": CACHE_TIME}
# pylint: disable=invalid-name
app = Flask(__name__)
app.config.from_mapping(CACHE_CONFIG)
CACHE = Cache(app)
UTC = timezone.utc
ISO_TIME = "%Y-%m-%dT%H:%M:%SZ"


def boards_request(api_resource: str, api_object_name: str) -> list:
    """Given an airport board style API resource path and the top level object name make an API
    request and format the result
    """
    flights = []

    # populate from cache when possible
    id_list = CACHE.get(api_resource)
    if id_list is not None:
        for fa_flight_id in id_list:
            entry = CACHE.get(fa_flight_id)
            if entry is not None:
                flights.append(entry)
    else:
        # Make sure this remains a list for later
        id_list = []

    # If there isn't a full "page" in the cache make a new request
    if len(flights) < 15:
        app.logger.info(f"Making AeroAPI request to GET {api_resource}")
        result = AEROAPI.get(f"{AEROAPI_BASE_URL}{api_resource}")
        if result.status_code != 200:
            abort(result.status_code)

        new_flights = format_response(result.json(), api_object_name)
        for entry in new_flights:
            CACHE.set(entry["id"], entry)
            flights.append(entry)
            id_list.append(entry["id"])
        CACHE.set(api_resource, id_list)
    else:
        app.logger.info(f"Populating {api_resource} from cache")

    return flights


def format_response(raw_payload, top_level):
    """given a json_body and a top_level key remove the key as a layer in the object reformat
    other values
    """
    missing = [
        "actual_runway_off",
        "actual_runway_on",
        "cruising_altitude",
        "filed_ground_speed",
        "hexid",
        "predicted_in",
        "predicted_off",
        "predicted_on",
        "predicted_out",
        "status",
        "true_cancel",
    ]
    orig_dest = ["destination", "origin"]
    rename = {
        "ident": "flight_number",
        "filed_airspeed": "filed_speed",
        "fa_flight_id": "id",
        "gate_origin": "actual_departure_gate",
        "gate_destination": "actual_arrival_gate",
        "terminal_origin": "actual_departure_terminal",
        "terminal_destination": "actual_arrival_terminal",
    }

    formatted_payload = []

    for entry in raw_payload[top_level]:
        # pad out missing keys to keep data structure in parity with firestarter
        for key in missing:
            entry[key] = None

        # flatten orig/dest object to a key:value
        # position-only flights will have None instead of an object
        for key in orig_dest:
            if entry[key] is not None:
                entry[key] = entry[key]["code"]

        # rename keys for parity with firestarter
        for key in rename:
            entry[rename[key]] = entry.pop(key)

        # convert iso dates to python datetime
        # jsonify in the flask return will serialize python datetime to RFC 822 standard
        for prefix in ["actual", "scheduled", "estimated"]:
            for suffix in ["out", "off", "on", "in"]:
                key = f"{prefix}_{suffix}"
                if entry[key] is not None:
                    entry[key] = datetime.strptime(entry[key], ISO_TIME)

        formatted_payload.append(entry)

    # flights should return just the object, not a list containing one object
    if top_level == "flights":
        return formatted_payload[0]

    return formatted_payload


@app.route("/positions/<fa_flight_id>")
@CACHE.cached(timeout=30)
def get_positions(fa_flight_id: str) -> Response:
    """Get positions for a specific fa_flight_id
    This route has a shorter cache time since positions are more time sensitive
    """
    api_resource = f"/flights/{fa_flight_id}/track"
    result = AEROAPI.get(f"{AEROAPI_BASE_URL}{api_resource}")
    if result.status_code != 200:
        abort(result.status_code)
    return jsonify(result.json()["positions"])


@app.route("/flights/")
@app.route("/flights/<fa_flight_id>")
def get_flight(fa_flight_id: Optional[str] = None) -> Response:
    """Get info for a specific fa_flight_id"""

    # Grab a random fa_flight_id from a broad search query if one isn't provided
    if fa_flight_id is None:
        api_resource = "/flights/search"
        flight_id_list = CACHE.get(api_resource)

        if flight_id_list is None:
            params = {"query": "-inAir 1"}
            app.logger.info(f"Making AeroAPI request to GET {api_resource}")
            result = AEROAPI.get(f"{AEROAPI_BASE_URL}{api_resource}", params=params)
            if result.status_code != 200:
                abort(result.status_code)
            flight_id_list = []
            for flight in result.json()["flights"]:
                flight_id_list.append(flight["fa_flight_id"])
            CACHE.set(api_resource, flight_id_list)
        else:
            app.logger.info(f"Populating {api_resource} from cache")

        return get_flight(random.choice(flight_id_list))

    # Otherwise look up the provided fa_flight_id
    api_resource = f"/flights/{fa_flight_id}"
    flight = CACHE.get(fa_flight_id)
    if flight is None:
        app.logger.info(f"Making AeroAPI request to GET {api_resource}")
        result = AEROAPI.get(f"{AEROAPI_BASE_URL}{api_resource}")
        if result.status_code != 200:
            abort(result.status_code)
        flight = format_response(result.json(), "flights")
        CACHE.set(flight["id"], flight)
    else:
        app.logger.info(f"Populating {api_resource} from cache")

    return jsonify(flight)


@app.route("/airports/")
def get_busiest_airports() -> Response:
    """Get the busiest airport by cancellations"""
    api_resource = "/disruption_counts/origin"
    airports = CACHE.get(api_resource)

    if airports is None:
        app.logger.info(f"Making AeroAPI request to GET {api_resource}")
        result = AEROAPI.get(f"{AEROAPI_BASE_URL}{api_resource}")
        if result.status_code != 200:
            abort(result.status_code)
        airports = []
        for entry in result.json()["entities"]:
            airports.append(entry["entity_id"])
    else:
        app.logger.info(f"Populating {api_resource} from cache")

    CACHE.set(api_resource, airports)
    return jsonify(airports)


@app.route("/airports/<airport>/arrivals")
def airport_arrivals(airport: str) -> Response:
    """Get a list of arrivals for a certain airport"""
    api_resource = f"/airports/{airport}/flights/arrivals"
    return jsonify(boards_request(api_resource, "arrivals"))


@app.route("/airports/<airport>/departures")
def airport_departures(airport: str) -> Response:
    """Get a list of departures for a certain airport"""
    api_resource = f"/airports/{airport}/flights/departures"
    return jsonify(boards_request(api_resource, "departures"))


@app.route("/airports/<airport>/enroute")
@app.route("/airports/<airport>/scheduledto")
def airport_enroute(airport: str) -> Response:
    """Get a list of flights enroute to a certain airport"""
    api_resource = f"/airports/{airport}/flights/scheduled_arrivals"
    return jsonify(boards_request(api_resource, "scheduled_arrivals"))


@app.route("/airports/<airport>/scheduled")
@app.route("/airports/<airport>/scheduledfrom")
def airport_scheduled(airport: str) -> Response:
    """Get a list of scheduled flights from a certain airport"""
    api_resource = f"/airports/{airport}/flights/scheduled_departures"
    return jsonify(boards_request(api_resource, "scheduled_departures"))


@app.route("/map/<fa_flight_id>")
def get_map(fa_flight_id: str) -> Response:
    """Get a static map image of the current flight in base64 png format
    """
    api_resource = f"/flights/{fa_flight_id}/map"
    maps_data = CACHE.get(api_resource)

    if maps_data is None:
        app.logger.info(f"Making AeroAPI request to GET {api_resource}")
        result = AEROAPI.get(f"{AEROAPI_BASE_URL}{api_resource}")
        if result.status_code != 200:
            abort(result.status_code)
        payload = result.json()
        maps_data = payload["map"]
        CACHE.set(api_resource, maps_data)
    else:
        app.logger.info(f"Populating {api_resource} from cache")

    return maps_data


app.run(host="0.0.0.0", port=5000, debug=True)
