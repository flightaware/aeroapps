FROM python:3.8-slim-buster

LABEL org.opencontainers.image.source=https://github.com/flightaware/aero_apps

RUN apt-get update && \
	apt-get install -y make
RUN id -u aeroapps || useradd -u 8081 aeroapps -c "AEROAPPS User" -m -s /bin/sh
USER aeroapps
WORKDIR /home/aeroapps

COPY --chown=aeroapps backend/python/requirements ./requirements
COPY --chown=aeroapps backend/python/Makefile .

ENV FLASK_APP=app.py
ENV FLASK_ENV=development

RUN make docker-setup
ENV VIRTUAL_ENV=./venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY --chown=aeroapps backend/python/app.py .

CMD ["python3", "app.py"]