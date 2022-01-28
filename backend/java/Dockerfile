FROM openjdk:8

LABEL org.opencontainers.image.source=https://github.com/flightaware/aero_apps

# Update and install Maven
RUN apt-get update && \
    apt-get install -y maven
RUN id -u aeroapps || useradd -u 8081 aeroapps -c "AEROAPPS User" -m -s /bin/sh
USER aeroapps
WORKDIR /home/aeroapps

# Pull in dependencies and verify
COPY --chown=aeroapps backend/java/pom.xml .
RUN ["mvn", "dependency:resolve", "verify"]

# Build our jar
COPY --chown=aeroapps backend/java/src src/
RUN ["mvn", "package"]

CMD ["java", "-jar", "target/aeroapps-backend-jar-with-dependencies.jar"]