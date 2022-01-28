FROM maven:3.8.4-openjdk-11-slim

LABEL org.opencontainers.image.source=https://github.com/flightaware/aero_apps

# Make AeroApps user
RUN id -u aeroapps || useradd -u 8081 aeroapps -c "AEROAPPS User" -m -s /bin/sh
USER aeroapps
WORKDIR /home/aeroapps

# Pull in dependencies and verify
COPY --chown=aeroapps backend/java/pom.xml .
COPY --chown=aeroapps backend/java/checkstyle.xml .
RUN ["mvn", "dependency:resolve", "verify"]

# Build our jar
COPY --chown=aeroapps backend/java/src src/
RUN ["mvn", "package"]

CMD ["java", "-jar", "target/aeroapps-backend-jar-with-dependencies.jar"]