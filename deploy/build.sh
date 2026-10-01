#!/bin/sh
# Baut das Update-Paket für den MRX/MOROS.neo:
#   deploy/dist/mvt-klappenautomat_<version>.tar
#
# Braucht Docker (buildx) und python3. Auf Apple Silicon läuft der Build nativ.
# Version aus pyproject.toml; die Beschreibung im MANIFEST nennt Commit und Bauzeit,
# "+lokal" heißt: aus nicht eingecheckten Änderungen gebaut – nicht fürs Feld.
#
# Hochladen: Router-Oberfläche -> Container -> Container -> Paket wählen.
# Ein vorhandener Container gleichen Namens wird ersetzt, /data bleibt.

set -eu
cd "$(dirname "$0")/.."

VERSION=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)
IMAGE="mvt-klappenautomat-rootfs:$VERSION"
LOKAL=""
[ -z "$(git status --porcelain 2>/dev/null)" ] || LOKAL="+lokal"
COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unbekannt)$LOKAL"
STAND=$(date '+%Y-%m-%d %H:%M:%S')

# SSH ist eine Entscheidung beim Bauen (Muster PayPoint-60): liegt
# deploy/authorized_keys da, kommt der Schlüssel ins Image und das Paket heißt "+ssh".
SSH_ZIEL=deploy/rootfs/opt/mvt/authorized_keys
CID=""
aufraeumen() {
    [ -z "$CID" ] || docker rm -f "$CID" >/dev/null 2>&1 || true
    rm -f "$SSH_ZIEL"
}
trap aufraeumen EXIT
rm -f "$SSH_ZIEL"
SSH=""
if [ -s deploy/authorized_keys ]; then
    cp deploy/authorized_keys "$SSH_ZIEL"
    SSH=" +ssh"
fi

echo "== Wurzeldateisystem bauen ($IMAGE, linux/arm64)"
docker buildx build --platform linux/arm64 -f deploy/Dockerfile -t "$IMAGE" --load .

echo "== Exportieren und Paket schnüren"
CID=$(docker create --platform linux/arm64 "$IMAGE" /sbin/init)
docker export "$CID" | python3 deploy/pack.py \
    --version "$VERSION" \
    --beschreibung "MVT-Klappenautomat $VERSION (git $COMMIT$SSH), gebaut $STAND" \
    --out deploy/dist
docker run --rm --platform linux/arm64 "$IMAGE" cat /opt/mvt/requirements.lock \
    > "deploy/dist/mvt-klappenautomat_$VERSION.requirements.lock"
