#!/usr/bin/env python3
"""
Publica en el sitio el firmware CIFRADO del Kurruf Ride.

    python publish_fw.py firmware site

Busca en la carpeta firmware/ (y subcarpetas) el latest.json y el .enc que generó
"idf.py build" (build/publicar/), los revisa y los copia a site/fw/.
Por seguridad FALLA si encuentra un firmware SIN cifrar (RIDE.bin) en la carpeta.
"""
import hashlib, json, os, shutil, struct, sys

ENC_MAGIC = 0x0788B6CF
MAX_SIZE = 6 * 1024 * 1024 + 1024


def main():
    src, site = sys.argv[1], sys.argv[2]
    if not os.path.isdir(src):
        print(f"No hay carpeta {src}: no se publica firmware")
        return
    manifests = []
    for root, _, files in os.walk(src):
        for f in files:
            p = os.path.join(root, f)
            with open(p, "rb") as fh:
                head = fh.read(4)
            if head[:1] == b"\xE9":
                sys.exit(f"ERROR DE SEGURIDAD: {p} es un firmware SIN cifrar. Bórralo del repositorio "
                         f"y sube solo los 2 archivos de build/publicar/.")
            if f == "latest.json":
                manifests.append(p)
    if not manifests:
        print("No hay latest.json en firmware/: no se publica firmware")
        return
    if len(manifests) > 1:
        sys.exit(f"ERROR: hay más de un latest.json: {manifests}. Deja solo uno.")

    man = manifests[0]
    info = json.load(open(man))
    enc_path = os.path.join(os.path.dirname(man), info["file"])
    if not os.path.exists(enc_path):
        sys.exit(f"ERROR: latest.json apunta a {info['file']}, pero no está junto a él")
    data = open(enc_path, "rb").read()
    if len(data) != info["size"] or hashlib.sha256(data).hexdigest() != info["sha256"]:
        sys.exit("ERROR: el .enc no coincide con latest.json (¿subiste archivos de compilaciones distintas?)")
    if len(data) < 1024 or len(data) > MAX_SIZE or struct.unpack_from("<I", data, 0)[0] != ENC_MAGIC:
        sys.exit("ERROR: el archivo no es un firmware cifrado de Kurruf Ride")

    out = os.path.join(site, "fw")
    os.makedirs(out, exist_ok=True)
    shutil.copyfile(enc_path, os.path.join(out, info["file"]))
    with open(os.path.join(out, "latest.json"), "w") as f:
        json.dump(info, f, indent=1)
    print(f"Firmware {info['version']} (cifrado) publicado: {info['file']}, {len(data)} bytes")


if __name__ == "__main__":
    main()
