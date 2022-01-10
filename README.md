# Aero Apps - Getting started with FlightAware AeroAPI

Aero Apps is a small collection of backend sample applications to help you get
started using FlightAware's AeroAPI Flight Tracking and Flight Status API.

Aero Apps is structured into Docker containers that represent language specific
implentations of backend services. These various language example containers
are managed by Docker Compose with profiles named for each language.

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

After running the above command, you should be greeted with log output from
each container. The services will log periodically as AeroAPI requests are made
, while the sample webapps will produce some initial log output and then only
log as requests are made to them.

You can test out the FIDS sample application by visiting http://localhost in
your web browser (if not running Docker locally, use the Docker host's 
address).
