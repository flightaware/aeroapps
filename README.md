# Aero Apps - Getting started with FlightAware AeroAPI

Aero Apps is a small collection of backend sample applications to help you get
started using FlightAware's AeroAPI Flight Tracking and Flight Status API.

Aero Apps is structured into Docker containers that represent language specific
implentations of backend services. These various language example containers
are managed by Docker Compose with profiles named for each language.

Furthermore, there is also a Docker container for just Python for the Alerts
Frontend application in particular for alert creation showcasing.

## Quickstart

You must set the following variable (in your environment or a .env file) before
you can start using Aero Apps.

* AEROAPI_KEY - Your FlightAware AeroAPI access key

The usual Docker Compose incantation run in the root of this repo will get you
up and running:

```
docker-compose --profile python pull && docker-compose --profile python up
```

Different profile options are documented in
[docker-compose.yml](./docker-compose.yml).

`docker-compose pull` pulls prebuilt images from the Github Container Registry,
and `docker-compose up` creates containers from those images and launches them.
If you'd like to build the images yourself, you can instead run
`docker-compose up --build`.

*For alert creation, the commands will all be the same except add `-f
docker-compose-alerts.yml` to utilize the alerts docker compose file. For
example, instead of `docker-compose --profile python up`, you should have
`docker-compose -f docker-compose-alerts.yml --profile python up`*.

After running the above command, you should be greeted with log output from
each container. The services will log periodically as AeroAPI requests are made
, while the sample webapps will produce some initial log output and then only
log as requests are made to them.

You can test out the FIDS/Alerts sample application by visiting http://localhost:8080 in
your web browser (if not running Docker locally, use the Docker host's
address).

## Alerts Backend Note:

Whenever an event is triggered for an  alert, AeroAPI will send a POST request to your 
configured endpoint. In order to configure your endpoint, you need to publicly expose its
address/port (specified using the POST_PORT environment variable, NOT the WEB_SERVER_PORT variable).
Furthermore, as noted in the docker-compose-alerts.yml file, we encourage the service for
accepting POSTed triggered alerts to be isolated, and thus will be sent to a different Docker
container. This means that you will have to set the endpoint URL using /post, instead of /api/post.
In order to get send your alerts to this webapp, you should configure this webapp 
(http://localhost:8081/post for example) to receive alerts using a REST client like cURL,
like the following command:
```
curl --location --request PUT 'https://aeroapi.flightaware.com/aeroapi/alerts/endpoint' \
--header 'Content-Type: application/json; charset=UTF-8' \
--header 'x-apikey: <YOUR API KEY>' \
--data-raw '{
  "url": "<YOUR IP>"
}'
```
(see the [documentation](https://flightaware.com/aeroapi/portal/documentation#put-/alerts/endpoint)
for more information). NOTE: if you previously configured a different production endpoint to receive alerts,
**you will change the same URL!** This means that ALL of your configured alerts
will all be sent to the newly configured endpoint.

You can see this newly configured URL by going to FlightAware's
[push notification testing page](https://flightaware.com/commercial/aeroapi/send.rvt)
or by going to the alert creation page on the webapp. On this push notification testing
page, you can also do two things: test your configured endpoint on the backend to see if it
receives a test triggered alert properly, and also see the success/failure of triggered alerts
that were sent up to 24 hours in the past. If there was an error it will display the
full error message.
