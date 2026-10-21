#!/usr/bin/env python3
"""
Revisa un mapa .krm: lee todas las celdas y muestra un resumen. También sirve de referencia
para probar el lector de la app.

Uso:
    python verify_krm.py salida/v1/nuble.krm
    python verify_krm.py salida/v1/nuble.krm -36.606 -72.103 2500   (calles alrededor de un punto)
"""
import math
import struct
import sys


def read_krm(path):
    data = open(path, "rb").read()
    assert data[:4] == b"KRM1", "no es un .krm"
    ver, _, lat0, lon0, nx, ny, cell, built = struct.unpack_from("<HHiiHHII", data, 4)
    index = struct.unpack_from("<" + "II" * nx * ny, data, 28)
    return data, (lat0, lon0, nx, ny, cell, built), index


def cell_ways(data, hdr, index, ix, iy):
    lat0, lon0, nx, ny, cell, _ = hdr
    off, ln = index[(iy * nx + ix) * 2], index[(iy * nx + ix) * 2 + 1]
    if ln == 0:
        return []
    pos = off

    def varint():
        nonlocal pos
        shift = v = 0
        while True:
            x = data[pos]
            pos += 1
            v |= (x & 0x7F) << shift
            if x < 0x80:
                return v
            shift += 7

    def zz():
        u = varint()
        return (u >> 1) ^ -(u & 1)

    out = []
    clat, clon = lat0 + iy * cell, lon0 + ix * cell
    for _ in range(varint()):
        cls = data[pos]
        pos += 1
        n = varint()
        pts, la, lo = [], clat, clon
        for _ in range(n):
            la += zz()
            lo += zz()
            pts.append((la, lo))
        out.append((cls, tuple(pts)))
    assert pos == off + ln, "celda con largo inconsistente"
    return out


def query(path, lat, lon, half_m):
    data, hdr, index = read_krm(path)
    lat0, lon0, nx, ny, cell, _ = hdr
    dlat = half_m / 111_195.0
    dlon = half_m / (111_195.0 * math.cos(math.radians(lat)))
    ci = lambda deg, o: math.floor((deg * 1e6 - o) / cell)
    out = []
    for iy in range(max(0, ci(lat - dlat, lat0)), min(ny - 1, ci(lat + dlat, lat0)) + 1):
        for ix in range(max(0, ci(lon - dlon, lon0)), min(nx - 1, ci(lon + dlon, lon0)) + 1):
            out += cell_ways(data, hdr, index, ix, iy)
    return out


def main():
    path = sys.argv[1]
    data, hdr, index = read_krm(path)
    lat0, lon0, nx, ny, cell, built = hdr
    if len(sys.argv) >= 5:
        ways = query(path, float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]))
        print(f"{len(ways)} tramos, {sum(len(p) for _, p in ways)} puntos alrededor del punto")
        return
    ways = pts = cells = 0
    for iy in range(ny):
        for ix in range(nx):
            w = cell_ways(data, hdr, index, ix, iy)
            if w:
                cells += 1
                ways += len(w)
                pts += sum(len(p) for _, p in w)
    print(f"{path}: {len(data) / 1e6:.2f} MB, grilla {nx}x{ny}, {cells} celdas con datos, "
          f"{ways} tramos, {pts} puntos. OK")


if __name__ == "__main__":
    main()
