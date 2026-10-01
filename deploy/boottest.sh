#!/bin/sh
# Bootprobe auf dem Mac: das Zielimage so starten, wie icom OS es startet –
# /sbin/init als PID 1, Wurzeldateisystem schreibgeschützt (findet Schreibzugriffe
# ins Image, bevor sie den Router erreichen), /tmp als 100-MB-tmpfs, /data als
# Volume, RAM-Grenze wie auf dem Gerät (~896 MB). IO-Module und Leser kommen aus
# hwsim der Entwicklungsumgebung (docker compose up hwsim).
#
#   deploy/boottest.sh          bauen + starten  ->  http://localhost:8002/
#   deploy/boottest.sh stop     anhalten (Daten bleiben im Volume)
#   deploy/boottest.sh reset    anhalten und /data löschen (wie neuer Router)

set -eu
cd "$(dirname "$0")/.."

NAME=mvt-boottest
VOLUME=mvt-boottest-data
VERSION=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)
IMAGE="mvt-klappenautomat-rootfs:$VERSION"

case "${1:-start}" in
    stop)
        docker stop -t 30 "$NAME" >/dev/null 2>&1 || true
        docker rm "$NAME" >/dev/null 2>&1 || true
        exit 0 ;;
    reset)
        "$0" stop
        docker volume rm "$VOLUME" >/dev/null 2>&1 || true
        exit 0 ;;
esac

docker compose up -d hwsim
NETZ=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' \
    "$(docker compose ps -q hwsim)")

docker buildx build --platform linux/arm64 -f deploy/Dockerfile -t "$IMAGE" --load .
"$0" stop

# Testaufbau statt Automaten-LAN: über /data/mvt/env, genau wie man es am Gerät
# für Abweichungen täte.
docker volume create "$VOLUME" >/dev/null
docker run --rm -i -v "$VOLUME:/data" "$IMAGE" sh -c 'mkdir -p /data/mvt && cat > /data/mvt/env' <<'ENV'
MVT_LESER_URL=socket://hwsim:7000
MVT_SEED_IO=hwsim:5021,hwsim:5022,hwsim:5023
MVT_SEED_TESTDATEN=1
ENV

docker run -d --name "$NAME" --platform linux/arm64 \
    --network "$NETZ" \
    --read-only --tmpfs /tmp:size=100m --tmpfs /shared:size=20m --tmpfs /devices:size=20m \
    -v "$VOLUME:/data" \
    --memory 896m \
    -p 8002:8000 \
    "$IMAGE" /sbin/init >/dev/null

echo "Container $NAME läuft – App: http://localhost:8002/  (Logs: docker exec $NAME tail -f /data/mvt/logs/app.log)"
