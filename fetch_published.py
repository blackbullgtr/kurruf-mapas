#!/usr/bin/env python3
"""
Copia los mapas que ya están publicados en el sitio, para volver a publicar sin regenerarlos
(cuando solo cambió el firmware). Verifica el SHA-256 de cada archivo.

    python fetch_published.py https://usuario.github.io/kurruf-mapas site

Sale con error si no puede (entonces el proceso genera los mapas desde cero).
"""
import hashlib, json, os, sys, urllib.request


def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def fetch(base, site, folder):
    out = os.path.join(site, folder)
    os.makedirs(out, exist_ok=True)
    raw = get(f"{base}/{folder}/regions.json")
    cat = json.loads(raw)
    for r in cat["regions"]:
        data = get(f"{base}/{folder}/{r['file']}")
        if hashlib.sha256(data).hexdigest() != r["sha256"]:
            sys.exit(f"ERROR: {r['file']} no coincide con el catálogo")
        with open(os.path.join(out, r["file"]), "wb") as f:
            f.write(data)
    with open(os.path.join(out, "regions.json"), "wb") as f:
        f.write(raw)
    print(f"Mapas {folder} reutilizados: {len(cat['regions'])} regiones (generados {cat.get('built')})")


def main():
    base, site = sys.argv[1].rstrip("/"), sys.argv[2]
    fetch(base, site, "v1")
    fetch(base, site, "v2")      # si todavía no existe v2 publicado, falla y se generan los mapas


if __name__ == "__main__":
    main()
