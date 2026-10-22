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


def main():
    base, site = sys.argv[1].rstrip("/"), sys.argv[2]
    out = os.path.join(site, "v1")
    os.makedirs(out, exist_ok=True)
    raw = get(f"{base}/v1/regions.json")
    cat = json.loads(raw)
    for r in cat["regions"]:
        data = get(f"{base}/v1/{r['file']}")
        if hashlib.sha256(data).hexdigest() != r["sha256"]:
            sys.exit(f"ERROR: {r['file']} no coincide con el catálogo")
        with open(os.path.join(out, r["file"]), "wb") as f:
            f.write(data)
    with open(os.path.join(out, "regions.json"), "wb") as f:
        f.write(raw)
    print(f"Mapas reutilizados: {len(cat['regions'])} regiones (generados {cat.get('built')})")


if __name__ == "__main__":
    main()
