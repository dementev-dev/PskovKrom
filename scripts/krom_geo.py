"""krom_geo.py — география проекта: широта/долгота → локальные метры, разбор выгрузок OSM.

Чистый Python без `unreal`: импортируется и скриптами редактора, и снаружи.
Оси (D-013): X — на истинный север, Y — на восток, метры; начало — центроид Троицкого собора в OSM.

    python scripts/krom_geo.py     # самопроверка: центроид собора должен лечь в (0, 0)
"""
import glob
import json
import math
import os

ORIGIN_LAT = 57.8221102  # центроид way 39012954 (Троицкий собор), D-013
ORIGIN_LON = 28.3289529
CATHEDRAL_WAY = 39012954

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OSM_DIR = os.path.join(REPO, "refs", "osm")

# Радиусы кривизны эллипсоида WGS84 в точке начала координат: меридиональный M и нормальный N.
_A, _E2 = 6378137.0, 6.69437999014e-3
_PHI = math.radians(ORIGIN_LAT)
_W = math.sqrt(1 - _E2 * math.sin(_PHI) ** 2)
_M_PER_DEG_LAT = math.radians(1) * _A * (1 - _E2) / _W ** 3
_M_PER_DEG_LON = math.radians(1) * _A / _W * math.cos(_PHI)


def to_local(lat, lon):
    """(широта, долгота) → (x, y) в метрах: x — север, y — восток."""
    return (lat - ORIGIN_LAT) * _M_PER_DEG_LAT, (lon - ORIGIN_LON) * _M_PER_DEG_LON


def to_latlon(x, y):
    return ORIGIN_LAT + x / _M_PER_DEG_LAT, ORIGIN_LON + y / _M_PER_DEG_LON


def latest(pattern):
    """Самый свежий файл в refs/osm по шаблону, например 'krom_2*.json'."""
    files = sorted(glob.glob(os.path.join(OSM_DIR, pattern)))
    if not files:
        raise FileNotFoundError(os.path.join(OSM_DIR, pattern))
    return files[-1]


def load_elements(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["elements"]


def local_points(geometry):
    """Геометрия элемента OSM → список (x, y); точки за границей выгрузки (null) → None."""
    return [to_local(p["lat"], p["lon"]) if p else None for p in geometry]


def split_on_none(points):
    """Разрезает ломаную по пропускам (None) на непрерывные куски из 2+ точек."""
    parts, cur = [], []
    for p in points:
        if p is None:
            if len(cur) > 1:
                parts.append(cur)
            cur = []
        else:
            cur.append(p)
    if len(cur) > 1:
        parts.append(cur)
    return parts


def signed_area(poly):
    """Площадь по формуле шнурования в осях (x, y); знак — ориентация обхода."""
    return 0.5 * sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]))


def centroid(poly):
    a = signed_area(poly)
    cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        c = x1 * y2 - x2 * y1
        cx += (x1 + x2) * c
        cy += (y1 + y2) * c
    return cx / (6 * a), cy / (6 * a)


def open_ring(poly):
    """Убирает повтор первой точки в конце (OSM замыкает кольца повтором)."""
    return poly[:-1] if len(poly) > 2 and poly[0] == poly[-1] else poly


def assemble_rings(ways):
    """Склеивает куски колец мультиполигона в замкнутые кольца по общим узлам.

    ways — список (node_ids, points) с полной геометрией. Возвращает список колец (x, y) без повтора точки.
    """
    pool = [(list(n), list(p)) for n, p in ways]
    rings = []
    while pool:
        nodes, pts = pool.pop(0)
        while nodes[0] != nodes[-1]:
            for i, (n2, p2) in enumerate(pool):
                if n2[0] == nodes[-1]:
                    nodes, pts = nodes + n2[1:], pts + p2[1:]
                elif n2[-1] == nodes[-1]:
                    nodes, pts = nodes + n2[-2::-1], pts + p2[-2::-1]
                else:
                    continue
                pool.pop(i)
                break
            else:
                break  # кольцо не замыкается — данные неполные, отдаём как есть
        rings.append(open_ring(pts))
    return rings


def water_rings(water_elements):
    """Кольца воды из полной геометрии: мультиполигоны (outer) и замкнутые линии."""
    ways = {e["id"]: e for e in water_elements if e["type"] == "way"}
    used, rings = set(), []
    for rel in (e for e in water_elements if e["type"] == "relation"):
        members = [ways[m["ref"]] for m in rel["members"] if m["role"] == "outer" and m["ref"] in ways]
        used |= {w["id"] for w in members} | {m["ref"] for m in rel["members"]}
        rings += assemble_rings([(w["nodes"], local_points(w["geometry"])) for w in members])
    for w in ways.values():
        if w["id"] not in used and w["nodes"][0] == w["nodes"][-1]:
            rings.append(open_ring(local_points(w["geometry"])))
            used.add(w["id"])
    return {"rings": rings, "ids": used}


def clip_to_rect(poly, xmin, xmax, ymin, ymax):
    """Обрезка многоугольника прямоугольником (Сазерленд — Ходжмен)."""
    def clip(pts, inside, cross):
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cross(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cross(prev, cur))
        return out

    def at_x(x0):
        return lambda a, b: (x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / (b[0] - a[0]))

    def at_y(y0):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (y0 - a[1]) / (b[1] - a[1]), y0)

    for inside, cross in (
        (lambda p: p[0] >= xmin, at_x(xmin)),
        (lambda p: p[0] <= xmax, at_x(xmax)),
        (lambda p: p[1] >= ymin, at_y(ymin)),
        (lambda p: p[1] <= ymax, at_y(ymax)),
    ):
        if not poly:
            break
        poly = clip(poly, inside, cross)
    return poly


def clip_line_to_rect(line, xmin, xmax, ymin, ymax):
    """Обрезка ломаной прямоугольником (Лян — Барски по отрезкам). Возвращает список кусков внутри."""
    parts, cur = [], []
    for (x1, y1), (x2, y2) in zip(line, line[1:]):
        dx, dy = x2 - x1, y2 - y1
        t0, t1 = 0.0, 1.0
        for p, q in ((-dx, x1 - xmin), (dx, xmax - x1), (-dy, y1 - ymin), (dy, ymax - y1)):
            if p == 0:
                if q < 0:
                    t0, t1 = 1.0, 0.0
                    break
            elif p < 0:
                t0 = max(t0, q / p)
            else:
                t1 = min(t1, q / p)
        if t0 > t1:
            if len(cur) > 1:
                parts.append(cur)
            cur = []
            continue
        a = (x1, y1) if t0 == 0.0 else (x1 + t0 * dx, y1 + t0 * dy)  # точные вершины, чтобы куски склеивались
        b = (x2, y2) if t1 == 1.0 else (x1 + t1 * dx, y1 + t1 * dy)
        if not cur or cur[-1] != a:
            if len(cur) > 1:
                parts.append(cur)
            cur = [a]
        cur.append(b)
        if t1 < 1.0:
            parts.append(cur)
            cur = []
    if len(cur) > 1:
        parts.append(cur)
    return parts


if __name__ == "__main__":
    els = load_elements(latest("krom_2*.json"))
    cat = next(e for e in els if e["type"] == "way" and e["id"] == CATHEDRAL_WAY)
    ring = open_ring(local_points(cat["geometry"]))
    cx, cy = centroid(ring)
    print(f"cathedral centroid: x={cx:.3f} m, y={cy:.3f} m, area={abs(signed_area(ring)):.1f} m2")
    assert abs(cx) < 0.05 and abs(cy) < 0.05, "начало координат уехало с собора"
    lat, lon = to_latlon(100.0, 200.0)
    back = to_local(lat, lon)
    assert abs(back[0] - 100) < 1e-6 and abs(back[1] - 200) < 1e-6
    assert clip_line_to_rect([(-5, 0), (5, 0), (5, 20)], -1, 10, -1, 10) == [[(-1, 0.0), (5, 0.0), (5.0, 10)]]
    assert clip_line_to_rect([(20, 20), (30, 30)], 0, 10, 0, 10) == []
    print("ok")
