"""
Schnürt aus einem `docker export` ein Update-Paket für icom OS.

    docker export <container> | python3 deploy/pack.py --version 0.1.0 --out deploy/dist

Format übernommen aus PayPoint-60/container/pack.py (dort am MRX.neo bestätigt):

    mvt-klappenautomat_<version>.tar     unkomprimiertes tar, keine Unterordner
    ├── MANIFEST                          muss die erste Datei sein
    └── mvt-klappenautomat.tar.xz         Wurzeldateisystem unter dem Präfix rootfs/

Der Name der inneren Datei bleibt über alle Versionen gleich: icom OS erkennt
daran den Container wieder und ersetzt ihn, statt einen zweiten anzulegen – nur so
bleibt /data (Datenbank!) erhalten.

Python statt tar: BSD-tar unter macOS legt `._*`-Einträge ins Archiv, und ein
Entpacken auf dem Mac würde Eigentümer und Gerätedateien verlieren.
"""

import argparse
import hashlib
import io
import os
import sys
import tarfile
import time

CONTAINER_NAME = "mvt-klappenautomat"
ROOTFS_PREFIX = "rootfs"

# Docker hängt diese Dateien zur Laufzeit ein; im Export sind sie leer.
# resolv.conf schreibt prepare.sh beim Start neu (Nameserver = Gateway).
ERSATZ = {
    "etc/hostname": f"{CONTAINER_NAME}\n".encode(),
    "etc/hosts": f"127.0.0.1\tlocalhost\n127.0.1.1\t{CONTAINER_NAME}\n".encode(),
    "etc/resolv.conf": b"nameserver 192.168.10.1\n",
}
WEGLASSEN = {".dockerenv"}


def _ohne_vorspann(name: str) -> str:
    """'./etc/hosts' und '/etc/hosts' -> 'etc/hosts' (kein lstrip('./'), das
    schnitte auch den Punkt von '.profile' ab)."""
    while name.startswith("./"):
        name = name[2:]
    return name.lstrip("/") if name != "." else ""


def rootfs_umpacken(quelle, ziel_pfad: str) -> int:
    """Liest den Export als Strom und schreibt ihn mit Präfix rootfs/ als tar.xz."""
    with (
        tarfile.open(fileobj=quelle, mode="r|") as ein,
        tarfile.open(
            ziel_pfad, mode="w:xz", format=tarfile.GNU_FORMAT, preset=6
        ) as aus,
    ):
        wurzel = tarfile.TarInfo(ROOTFS_PREFIX)
        wurzel.type = tarfile.DIRTYPE
        wurzel.mode = 0o755
        wurzel.mtime = int(time.time())
        aus.addfile(wurzel)

        anzahl = 0
        for eintrag in ein:
            name = _ohne_vorspann(eintrag.name)
            if not name or name in WEGLASSEN:
                continue
            daten = ein.extractfile(eintrag) if eintrag.isreg() else None
            if name in ERSATZ:
                inhalt = ERSATZ[name]
                eintrag.size = len(inhalt)
                daten = io.BytesIO(inhalt)
            eintrag.name = f"{ROOTFS_PREFIX}/{name}"
            if eintrag.islnk():
                # Hardlinks verweisen auf einen Archivpfad, Symlinks nicht
                eintrag.linkname = f"{ROOTFS_PREFIX}/{_ohne_vorspann(eintrag.linkname)}"
            eintrag.pax_headers = {}
            aus.addfile(eintrag, daten)
            anzahl += 1
    return anzahl


def md5(pfad: str) -> str:
    h = hashlib.md5()
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def paket_schnueren(
    rootfs_pfad: str, version: str, beschreibung: str, ziel_pfad: str
) -> str:
    dateiname = os.path.basename(rootfs_pfad)
    # Keine Leerzeichen um '=' und keine am Zeilenende – icom OS lehnt das ab.
    # "Container ARM64" kennzeichnet aarch64; "Container" gilt für 32-Bit-Geräte.
    manifest = (
        "\n".join(
            [
                f"FILENAME={dateiname}",
                f"FILESIZE={os.path.getsize(rootfs_pfad)}",
                "FILETYPE=Container ARM64",
                f"MD5SUM={md5(rootfs_pfad)}",
                f"VERSION={version}",
                f"DESCRIPTION={beschreibung}",
            ]
        )
        + "\n"
    )

    def als_root(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        info.mode = 0o644
        return info

    with tarfile.open(ziel_pfad, mode="w", format=tarfile.GNU_FORMAT) as paket:
        kopf = tarfile.TarInfo("MANIFEST")
        kopf.size = len(manifest.encode())
        kopf.mtime = int(time.time())
        paket.addfile(als_root(kopf), io.BytesIO(manifest.encode()))
        paket.add(rootfs_pfad, arcname=dateiname, filter=als_root)
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--version", required=True)
    p.add_argument("--beschreibung", default=None)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rootfs_pfad = os.path.join(args.out, f"{CONTAINER_NAME}.tar.xz")
    paket_pfad = os.path.join(args.out, f"{CONTAINER_NAME}_{args.version}.tar")

    anzahl = rootfs_umpacken(sys.stdin.buffer, rootfs_pfad)
    beschreibung = args.beschreibung or f"MVT-Klappenautomat {args.version}"
    manifest = paket_schnueren(rootfs_pfad, args.version, beschreibung, paket_pfad)
    os.remove(rootfs_pfad)

    print(f"{anzahl} Einträge im Wurzeldateisystem")
    print(manifest, end="")
    print(f"-> {paket_pfad} ({os.path.getsize(paket_pfad) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
