#!/usr/bin/env python3
"""
Kurruf Ride - conversor de mapas sin conexión.

Lee el extracto de OpenStreetMap de Chile (Geofabrik, .osm.pbf), deja solo las vías por donde
anda una moto, las simplifica y las guarda por región en un formato compacto (.krm) que la app
descarga una vez y usa sin internet para el minimapa.

Uso:
    python build_maps.py chile-latest.osm.pbf salida/

Genera:
    salida/v1/regions.json      índice: regiones, tamaño, fecha, sha256
    salida/v1/<region>.krm      un archivo por región

Formato .krm (little endian):
    "KRM1" | u16 versión | u16 reservado
    i32 lat0, i32 lon0 (microgrados, esquina suroeste de la grilla)
    u16 nx, u16 ny, u32 tamaño de celda (microgrados), u32 fecha (unix)
    índice: nx*ny entradas (u32 offset, u32 largo), fila por fila desde el sur
    celdas:  varint cantidad de calles; por calle: u8 tipo, varint puntos,
             primer punto = zigzag(lat - lat_celda), zigzag(lon - lon_celda) en microgrados,
             siguientes = zigzag de la diferencia con el anterior.
    Tipos: 0 autopista/troncal/primaria, 1 secundaria/terciaria, 2 residencial, 3 servicio/huella.
"""
import hashlib
import json
import math
import os
import struct
import sys
import time

import osmium

VERSION = 1
CELL_E6 = 50_000          # 0,05° (~5,5 km norte-sur)
PAD = 0.05                # margen alrededor de cada región (las calles del borde quedan en ambas)

# Regiones de Chile (sur, oeste, norte, este) aproximadas. Se solapan un poco a propósito.
REGIONS = [
    ("arica", "Arica y Parinacota", (-19.25, -70.45, -17.45, -68.90)),
    ("tarapaca", "Tarapacá", (-21.70, -70.35, -18.90, -68.40)),
    ("antofagasta", "Antofagasta", (-26.10, -70.75, -20.90, -67.00)),
    ("atacama", "Atacama", (-29.60, -71.65, -25.25, -68.25)),
    ("coquimbo", "Coquimbo", (-32.30, -71.80, -29.00, -69.75)),
    ("valparaiso", "Valparaíso", (-33.95, -72.00, -32.00, -69.95)),
    ("metropolitana", "Metropolitana", (-34.30, -71.75, -32.90, -69.75)),
    ("ohiggins", "O'Higgins", (-35.05, -72.10, -33.80, -70.00)),
    ("maule", "Maule", (-36.55, -72.85, -34.65, -70.30)),
    ("nuble", "Ñuble", (-37.25, -72.90, -36.00, -71.00)),
    ("biobio", "Biobío", (-38.55, -73.95, -36.40, -70.95)),
    ("araucania", "Araucanía", (-39.65, -73.55, -37.55, -70.80)),
    ("losrios", "Los Ríos", (-40.75, -73.75, -39.25, -71.55)),
    ("loslagos", "Los Lagos", (-44.10, -74.40, -40.20, -71.55)),
    ("aysen", "Aysén", (-49.20, -75.80, -43.60, -71.00)),
    ("magallanes", "Magallanes", (-56.00, -76.00, -48.50, -66.40)),
]

CLASS = {
    "motorway": 0, "trunk": 0, "primary": 0,
    "motorway_link": 0, "trunk_link": 0, "primary_link": 0,
    "secondary": 1, "tertiary": 1, "secondary_link": 1, "tertiary_link": 1,
    "unclassified": 2, "residential": 2, "living_street": 2, "road": 2,
    "service": 3, "track": 3,
}


# ------------------------------------------------------------
# Utilidades
# ------------------------------------------------------------
def varint(v: int, out: bytearray):
    while v >= 0x80:
        out.append((v & 0x7F) | 0x80)
        v >>= 7
    out.append(v)


def zigzag(v: int) -> int:
    return (v << 1) ^ (v >> 63)


def simplify(lat, lon, tol_m):
    """Douglas-Peucker en metros (plano local). Devuelve índices a conservar."""
    n = len(lat)
    if n <= 2:
        return list(range(n))
    k = math.cos(math.radians(lat[0])) * 111_195.0
    xs = [(lo - lon[0]) * k for lo in lon]
    ys = [(la - lat[0]) * 111_195.0 for la in lat]
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        bx, by = xs[b] - xs[a], ys[b] - ys[a]
        ln = math.hypot(bx, by)
        best, idx = 0.0, -1
        for i in range(a + 1, b):
            px, py = xs[i] - xs[a], ys[i] - ys[a]
            d = math.hypot(px, py) if ln == 0 else abs(px * by - py * bx) / ln
            if d > best:
                best, idx = d, i
        if idx != -1 and best > tol_m:
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))
    return [i for i in range(n) if keep[i]]


class Region:
    def __init__(self, rid, name, bbox):
        s, w, n, e = bbox
        self.id, self.name = rid, name
        self.bbox = (s - PAD, w - PAD, n + PAD, e + PAD)
        self.lat0 = int(math.floor(self.bbox[0] * 1e6 / CELL_E6)) * CELL_E6
        self.lon0 = int(math.floor(self.bbox[1] * 1e6 / CELL_E6)) * CELL_E6
        self.nx = int(math.ceil((self.bbox[3] * 1e6 - self.lon0) / CELL_E6))
        self.ny = int(math.ceil((self.bbox[2] * 1e6 - self.lat0) / CELL_E6))
        self.cells = {}        # (ix, iy) -> [cantidad, bytearray]
        self.ways = 0
        self.points = 0

    def intersects(self, s, w, n, e):
        S, W, N, E = self.bbox
        return not (n < S or s > N or e < W or w > E)

    def cell_of(self, lat_e6, lon_e6):
        return ((lon_e6 - self.lon0) // CELL_E6, (lat_e6 - self.lat0) // CELL_E6)

    def add_piece(self, cell, cls, pts):
        ix, iy = cell
        if not (0 <= ix < self.nx and 0 <= iy < self.ny) or len(pts) < 2:
            return
        entry = self.cells.get(cell)
        if entry is None:
            entry = self.cells[cell] = [0, bytearray()]
        buf = entry[1]
        clat = self.lat0 + iy * CELL_E6
        clon = self.lon0 + ix * CELL_E6
        buf.append(cls)
        varint(len(pts), buf)
        plat, plon = clat, clon
        for la, lo in pts:
            varint(zigzag(la - plat), buf)
            varint(zigzag(lo - plon), buf)
            plat, plon = la, lo
        entry[0] += 1
        self.ways += 1
        self.points += len(pts)

    def add_way(self, cls, lat_e6, lon_e6):
        """Corta la calle en pedazos por celda (cada pedazo arranca en el punto anterior para no dejar huecos)."""
        cur = self.cell_of(lat_e6[0], lon_e6[0])
        piece = [(lat_e6[0], lon_e6[0])]
        for i in range(1, len(lat_e6)):
            p = (lat_e6[i], lon_e6[i])
            c = self.cell_of(*p)
            piece.append(p)
            if c != cur:
                self.add_piece(cur, cls, piece)
                piece = [(lat_e6[i - 1], lon_e6[i - 1]), p]
                cur = c
        self.add_piece(cur, cls, piece)

    def write(self, path, built):
        header = bytearray(b"KRM1")
        header += struct.pack("<HHiiHHII", VERSION, 0, self.lat0, self.lon0, self.nx, self.ny, CELL_E6, built)
        index_size = self.nx * self.ny * 8
        offset = len(header) + index_size
        index = bytearray()
        blobs = []
        for iy in range(self.ny):
            for ix in range(self.nx):
                entry = self.cells.get((ix, iy))
                if entry is None:
                    index += struct.pack("<II", 0, 0)
                    continue
                blob = bytearray()
                varint(entry[0], blob)
                blob += entry[1]
                index += struct.pack("<II", offset, len(blob))
                blobs.append(blob)
                offset += len(blob)
        with open(path, "wb") as f:
            f.write(header)
            f.write(index)
            for b in blobs:
                f.write(b)


class Handler(osmium.SimpleHandler):
    def __init__(self, regions):
        super().__init__()
        self.regions = regions
        self.seen = 0
        self.kept = 0

    def way(self, w):
        hw = w.tags.get("highway")
        if hw is None:
            return
        self.seen += 1
        cls = CLASS.get(hw)
        if cls is None:
            return
        if hw == "service" and "service" in w.tags:     # sin estacionamientos ni accesos privados
            return
        lat, lon = [], []
        for n in w.nodes:
            if not n.location.valid():
                continue
            lat.append(n.location.lat)
            lon.append(n.location.lon)
        if len(lat) < 2:
            return
        keep = simplify(lat, lon, 4.0 if cls >= 3 else 2.5)
        la = [int(round(lat[i] * 1e6)) for i in keep]
        lo = [int(round(lon[i] * 1e6)) for i in keep]
        s, n_, w_, e = min(la) / 1e6, max(la) / 1e6, min(lo) / 1e6, max(lo) / 1e6
        hit = False
        for r in self.regions:
            if r.intersects(s, w_, n_, e):
                r.add_way(cls, la, lo)
                hit = True
        if hit:
            self.kept += 1
        if self.kept and self.kept % 100_000 == 0:
            print(f"  {self.kept} calles procesadas...", flush=True)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src, out = sys.argv[1], sys.argv[2]
    outdir = os.path.join(out, "v1")
    os.makedirs(outdir, exist_ok=True)

    regions = [Region(*r) for r in REGIONS]
    t0 = time.time()
    print(f"Leyendo {src} ...", flush=True)
    h = Handler(regions)
    # 'flex_mem' guarda las ubicaciones de los nodos en memoria de forma eficiente
    h.apply_file(src, locations=True, idx="flex_mem")
    print(f"Calles: {h.kept} usadas de {h.seen} con 'highway' ({time.time() - t0:.0f} s)")

    built = int(time.time())
    index = {
        "version": VERSION,
        "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(built)),
        "source": os.path.basename(src) + " (© OpenStreetMap contributors, ODbL)",
        "regions": [],
    }
    for r in regions:
        fname = f"{r.id}.krm"
        path = os.path.join(outdir, fname)
        r.write(path, built)
        data = open(path, "rb").read()
        index["regions"].append({
            "id": r.id, "name": r.name,
            "bbox": [round(v, 4) for v in r.bbox],
            "file": fname, "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "ways": r.ways, "points": r.points,
        })
        print(f"  {r.name:<20} {len(data) / 1e6:6.2f} MB  {r.ways:>8} tramos  {r.points:>9} puntos")
    with open(os.path.join(outdir, "regions.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    print(f"Listo en {time.time() - t0:.0f} s -> {outdir}")


if __name__ == "__main__":
    main()
