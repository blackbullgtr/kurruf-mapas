#!/usr/bin/env python3
"""
Publica el firmware del Kurruf Ride en el sitio (GitHub Pages).

    python publish_fw.py firmware/RIDE.bin site

Revisa que sea un firmware del proyecto RIDE, lee su versión y deja:
    site/fw/RIDE-<versión>.bin
    site/fw/latest.json   {"version", "file", "size", "sha256", "date", "published"}
Si no existe firmware/RIDE.bin, no hace nada.
"""
import hashlib, json, os, shutil, struct, sys, time

PROJECT = "RIDE"
MAX_SIZE = 6 * 1024 * 1024


def cstr(b):
    return b.split(b"\0", 1)[0].decode("ascii", "replace")


def main():
    src, site = sys.argv[1], sys.argv[2]
    if not os.path.exists(src):
        print(f"No hay {src}: no se publica firmware")
        return
    data = open(src, "rb").read()
    if not (1024 <= len(data) <= MAX_SIZE):
        sys.exit(f"ERROR: tamaño no válido ({len(data)} bytes)")
    if data[0] != 0xE9:
        sys.exit("ERROR: no es un firmware de ESP32 (¿subiste bootloader.bin o partition-table.bin?)")
    d = 24 + 8                                   # cabecera de imagen + cabecera del primer segmento
    magic, = struct.unpack_from("<I", data, d)
    if magic != 0xABCD5432:
        sys.exit("ERROR: no se encontró la descripción del firmware")
    version = cstr(data[d + 16:d + 48])
    project = cstr(data[d + 48:d + 80])
    ftime = cstr(data[d + 80:d + 96])
    fdate = cstr(data[d + 96:d + 112])
    if project != PROJECT:
        sys.exit(f"ERROR: es un firmware de otro proyecto ({project!r})")
    if not version or any(c in version for c in "/\\ "):
        sys.exit(f"ERROR: versión no válida ({version!r})")

    out = os.path.join(site, "fw")
    os.makedirs(out, exist_ok=True)
    name = f"RIDE-{version}.bin"
    shutil.copyfile(src, os.path.join(out, name))
    info = {
        "version": version,
        "file": name,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "date": f"{fdate} {ftime}",
        "published": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(os.path.join(out, "latest.json"), "w") as f:
        json.dump(info, f, indent=1)
    print(f"Firmware {version} publicado ({len(data)} bytes, compilado {fdate} {ftime})")


if __name__ == "__main__":
    main()
