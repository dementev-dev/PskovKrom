"""city_mesh.py — рядовая застройка вокруг Крома из OSM: коробки по этажности, простые крыши и фасадный генератор
(M5, D-032; фасады — D-043).

Не для редактора: обычный Python из локального окружения (numpy, pillow):

    .venv\\Scripts\\python scripts/city_mesh.py        → build/city/city.json + build/city/city_top.png
    .venv\\Scripts\\python scripts/city_mesh.py --glb build/facade_refs p0_m1 p1_m2
                                                      → ещё и клетки p0_m1, p1_m2 в GLB (превью в Blender)

Это не реконструкция: здания OSM (≈1000) выдавливаются на высоту, фасады собираются по правилам; порядок в сцене
собирает city_krom.py.
  - Контуры — замкнутые линии и мультиполигоны building (внешние кольца). Пропускаются руины, городские стены,
    всё внутри контуров Крома и Довмонтова города (там герои и blockout) и здания, центр которых внутри контура
    героя krom_plan (Пароменье, часовни, ПсковГУ — heroes_krom.py), чтобы не было коробки-двойника.
  - Высота стен — тег height, иначе building:levels × FLOOR_M + PLINTH_M, иначе по типу здания (LEVELS_BY_TYPE, гип.).
  - Крыша — roof:shape (flat, hipped, gabled, pyramidal и родственные), без тега — плоская у многоэтажных и крупных,
    вальмовая у малых (гип.). Скатная крыша строится по описанному прямоугольнику контура и только если контур
    близок к нему (RECT_MIN), иначе — плоская. Высота конька — ROOF_PITCH от короткой стороны, не выше ROOF_MAX_M.
  - Низ — земля heightmap под контуром (минимум) минус BURY_M, чтобы на склоне не было щели.
  - Фасад (D-043) — по классу и цветам facade_rules.style(): этажи — building:levels (иначе по типу), первый этаж
    выше у старых домов; окна — ряды по этажам с шагом стиля, утоплены на RECESS_M (стекло, откосы, отлив; без
    сквозных дыр); на стенах вплотную к соседу (ближе PARTY_M) окон нет; двери с козырьком — на стене к улице
    (ближайшая улица OSM не дальше STREET_M, иначе длинная стена); цоколь, карниз, свес и торец кровли, трубы,
    балконы, ворота гаражей. Детали по удалённости от собора (LOD_M): до 650 м — всё; до 900 м — окна плоскими
    стёклами без цоколя и карниза; дальше — коробка, стена чуть темнее (средний тон стены с окнами).
  - Цвет — в цвет вершин, linear (материалы city_krom.py умножают его на оттенок палитры).
  - UV стен — в метрах: u — вдоль периметра, v — высота над низом; у горизонтальных граней — x, y.
Меши режутся по клеткам CELL_M × CELL_M (по центру здания): у каждой клетки начало и части facade (стены и
детали), glass (стёкла) и roof (кровли, козырьки).
"""
import json
import math
import os
import struct
import sys
import zlib

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import facade_rules as fr  # noqa: E402
import krom_geo as geo  # noqa: E402
import krom_plan  # noqa: E402

OUT_DIR = os.path.join(geo.REPO, "build", "city")
OUT_JSON = os.path.join(OUT_DIR, "city.json")
HEIGHTMAP = os.path.join(geo.REPO, "refs", "dem", "heightmap_L_Krom.png")
HM_META = os.path.join(geo.REPO, "refs", "dem", "heightmap_L_Krom.json")
HALF = 1008
CELL_M = 250.0
FLOOR_M, PLINTH_M = 3.0, 0.6
BURY_M = 1.0
ROOF_PITCH = 0.55      # высота конька ÷ половина короткой стороны: ≈29°
ROOF_MAX_M = 6.0
RECT_MIN = 0.82        # площадь контура ÷ площадь описанного прямоугольника — для скатной крыши
MIN_AREA_M2 = 6.0
EXCLUDE_RELS = (4060616, 4060635)  # Псковский кром, Довмонтов город (terrain_krom.KROM_REL, DOVMONT_REL)
EXCLUDE_WAYS = (96260903, 95192411, 96333727)  # куски стены Окольного города под кровлей — их строит okolny_plan (D-040)
# этажей по типу здания без тегов (гип.: типовая застройка центра Пскова); None — по умолчанию
LEVELS_BY_TYPE = {
    "apartments": 5, "residential": 3, "dormitory": 4, "hotel": 4, "office": 3, "university": 3, "school": 3,
    "hospital": 4, "public": 2, "commercial": 2, "retail": 1, "industrial": 2, "warehouse": 1, "house": 1.5,
    "detached": 1.5, "semidetached_house": 1.5, "shed": 1, "garage": 1, "garages": 1, "service": 1, "greenhouse": 1,
    "kiosk": 1, "roof": 1, "church": 4, "chapel": 2, "cathedral": 5,
}
DEFAULT_LEVELS = 2
PITCHED = {"hipped", "gabled", "pyramidal", "side_hipped", "half-hipped", "quadruple_saltbox", "mansard",
           "gambrel", "saltbox"}

# фасадный генератор (D-043)
LOD_M = (650.0, 900.0)   # до — все детали; до второго — окна плоскими стёклами; дальше — коробки
RECESS_M = 0.15          # глубина окна в стене
FLAT_GLASS_M = 0.03      # стекло поверх стены во второй зоне
PLINTH_PROUD = 0.05      # вынос цоколя
DOOR_PROUD = 0.07        # дверь поверх стены и цоколя
ROOF_THICK = 0.12        # толщина кровли со свесом (торец и подшивка)
PARTY_M = 0.5            # стена ближе к соседнему контуру — глухая
SAMPLE_M = 0.5           # шаг проверки глухой стены вдоль ребра
STREET_M = 35.0          # дальше — дверь на длинной стене
STREET_CLASSES = {"primary", "secondary", "tertiary", "residential", "living_street", "pedestrian", "unclassified",
                  "primary_link", "secondary_link", "tertiary_link"}
MIN_FLOOR_M = 2.3


# ---------- геометрия в плане ----------

def ccw(ring):
    return ring if geo.signed_area(ring) > 0 else ring[::-1]


def point_in(p, ring):
    x, y, inside = p[0], p[1], False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def points_in(pts, ring):
    """Точки pts (n × 2) внутри кольца — массив bool (чётность пересечений)."""
    r = np.asarray(ring, float)
    x1, y1 = r[:, 0], r[:, 1]
    x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
    px, py = pts[:, :1], pts[:, 1:2]
    cond = (y1 > py) != (y2 > py)
    with np.errstate(divide="ignore", invalid="ignore"):
        xc = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
    return (cond & (px < xc)).sum(1) % 2 == 1


def earcut(ring):
    """Треугольники многоугольника без дыр (обход против часовой): индексы в ring."""
    idx = list(range(len(ring)))
    tris = []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = ring[i0], ring[i1], ring[i2]
            if cross(a, b, c) <= 1e-9:
                continue
            if any(cross(a, b, ring[j]) >= 0 and cross(b, c, ring[j]) >= 0 and cross(c, a, ring[j]) >= 0
                   for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            break  # вырожденный остаток: срезаем веером
    for k in range(1, len(idx) - 1):
        tris.append((idx[0], idx[k], idx[k + 1]))
    return tris


def min_rect(ring):
    """Описанный прямоугольник минимальной площади: (центр, ось длинной стороны, длина, ширина)."""
    best = None
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        d = math.hypot(x2 - x1, y2 - y1)
        if d < 1e-6:
            continue
        u = ((x2 - x1) / d, (y2 - y1) / d)
        v = (-u[1], u[0])
        us = [p[0] * u[0] + p[1] * u[1] for p in ring]
        vs = [p[0] * v[0] + p[1] * v[1] for p in ring]
        area = (max(us) - min(us)) * (max(vs) - min(vs))
        if best is None or area < best[0]:
            cu, cv = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
            best = (area, (cu * u[0] + cv * v[0], cu * u[1] + cv * v[1]), u, max(us) - min(us), max(vs) - min(vs))
    _, c, u, a, b = best
    if b > a:
        u, a, b = (-u[1], u[0]), b, a
    return c, u, a, b


def seg_dist(px, py, ax, ay, bx, by):
    """Расстояния от точек (px, py) до отрезков (ax, ay)–(bx, by) (numpy, широковещание) и ближайшие точки."""
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.clip(np.where(ll > 1e-12, ((px - ax) * dx + (py - ay) * dy) / ll, 0.0), 0.0, 1.0)
    qx, qy = ax + t * dx, ay + t * dy
    return np.hypot(px - qx, py - qy), qx, qy


# ---------- данные ----------

class Heights:
    def __init__(self):
        hm = np.asarray(Image.open(HEIGHTMAP)).astype(np.float64)
        self.z = (hm - 32768) / 128.0          # ue[y + HALF, x + HALF], метры от собора

    def min_under(self, ring):
        vals = [self.at(*p) for p in ring]
        c = geo.centroid(ring)
        vals.append(self.at(*c))
        return min(vals)

    def at(self, x, y):
        i = min(max(int(round(y + HALF)), 0), 2 * HALF)
        j = min(max(int(round(x + HALF)), 0), 2 * HALF)
        return float(self.z[i, j])


class SegGrid:
    """Отрезки в сетке CELL × CELL: ключ владельца, концы; ближайшие — по клеткам рамки."""

    def __init__(self, cell):
        self.cell, self.g = cell, {}

    def add(self, key, a, b):
        c = self.cell
        for i in range(math.floor(min(a[0], b[0]) / c), math.floor(max(a[0], b[0]) / c) + 1):
            for j in range(math.floor(min(a[1], b[1]) / c), math.floor(max(a[1], b[1]) / c) + 1):
                self.g.setdefault((i, j), []).append((key, a[0], a[1], b[0], b[1]))

    def near(self, x0, y0, x1, y1):
        c, seen, out = self.cell, set(), []
        for i in range(math.floor(x0 / c), math.floor(x1 / c) + 1):
            for j in range(math.floor(y0 / c), math.floor(y1 / c) + 1):
                for s in self.g.get((i, j), ()):
                    if id(s) not in seen:
                        seen.add(id(s))
                        out.append(s)
        return out


class Context:
    """Соседи (глухие стены), улицы (сторона дверей) и рельеф — в мировых метрах."""

    def __init__(self, rings, streets, heights):
        self.rings = rings                       # ключ → кольцо
        self.walls = SegGrid(10.0)
        for key, ring in rings.items():
            for a, b in zip(ring, ring[1:] + ring[:1]):
                self.walls.add(key, a, b)
        self.streets = SegGrid(50.0)
        for k, line in enumerate(streets):
            for a, b in zip(line, line[1:]):
                self.streets.add(k, a, b)
        self.hts = heights

    def blocked(self, key, pts):
        """Точки pts (n × 2) у стены здания key: True — рядом чужой контур (ближе PARTY_M) или внутри него."""
        x0, y0 = pts.min(0) - PARTY_M
        x1, y1 = pts.max(0) + PARTY_M
        segs = [s for s in self.walls.near(x0, y0, x1, y1) if s[0] != key]
        out = np.zeros(len(pts), bool)
        if not segs:
            return out
        a = np.asarray([s[1:] for s in segs], float)
        d, _, _ = seg_dist(pts[:, :1], pts[:, 1:2], a[:, 0], a[:, 1], a[:, 2], a[:, 3])
        out |= d.min(1) < PARTY_M
        for k in {s[0] for s in segs}:
            if not out.all():
                out |= points_in(pts, self.rings[k])
        return out

    def street_dist(self, m, n):
        """Расстояние от середины стены m до ближайшей улицы перед ней (по нормали n), иначе None."""
        segs = self.streets.near(m[0] - STREET_M, m[1] - STREET_M, m[0] + STREET_M, m[1] + STREET_M)
        if not segs:
            return None
        a = np.asarray([s[1:] for s in segs], float)
        d, qx, qy = seg_dist(m[0], m[1], a[:, 0], a[:, 1], a[:, 2], a[:, 3])
        ok = ((qx - m[0]) * n[0] + (qy - m[1]) * n[1] > 0.5) & (d < STREET_M)
        return float(d[ok].min()) if ok.any() else None


def buildings():
    """([(id, tags, кольцо в метрах, ключ)] — внешние кольца зданий OSM без исключённых;
    {ключ: кольцо} — все контуры зданий и героев (соседи для глухих стен); [линии улиц])."""
    els = geo.load_elements(geo.latest("krom_2*.json"))
    excl = []
    for e in els:
        if e["type"] == "relation" and e["id"] in EXCLUDE_RELS:
            outers = [m for m in e["members"] if m["role"] == "outer" and m.get("geometry") and None not in m["geometry"]]
            ways = [([(p["lat"], p["lon"]) for p in m["geometry"]], geo.local_points(m["geometry"])) for m in outers]
            excl += geo.assemble_rings(ways)
    heroes = [list(b.footprint) for b in krom_plan.towers() + krom_plan.buildings() if b.hero and b.footprint]
    excl += heroes
    out, rings, streets = [], {}, []
    for k, f in enumerate(heroes):
        rings[("hero", k)] = [tuple(p) for p in f]
    for e in els:
        tags = e.get("tags", {})
        if e["type"] == "way" and tags.get("highway") in STREET_CLASSES and e.get("geometry") \
                and None not in e["geometry"]:
            streets.append(geo.local_points(e["geometry"]))
        b = tags.get("building")
        if not b or b in ("no", "ruins") or tags.get("barrier") == "city_wall" or tags.get("historic") == "city_gate":
            continue
        rs = []
        if e["type"] == "way" and e.get("nodes") and e["nodes"][0] == e["nodes"][-1] and None not in e["geometry"]:
            rs = [geo.open_ring(geo.local_points(e["geometry"]))]
        elif e["type"] == "relation":
            outers = [m for m in e["members"] if m["role"] == "outer" and m.get("geometry") and None not in m["geometry"]]
            ways = [([(p["lat"], p["lon"]) for p in m["geometry"]], geo.local_points(m["geometry"])) for m in outers]
            rs = [geo.open_ring(r) for r in geo.assemble_rings(ways)]
        for n, ring in enumerate(rs):
            if len(ring) < 3 or abs(geo.signed_area(ring)) < MIN_AREA_M2:
                continue
            key = (e["type"], e["id"], n)
            rings[key] = ccw(ring)
            if e["type"] == "way" and e["id"] in EXCLUDE_WAYS:
                continue
            c = geo.centroid(ring)
            if max(abs(c[0]), abs(c[1])) > HALF - 5 or any(point_in(c, r) for r in excl):
                continue
            out.append((e["id"], tags, ccw(ring), key))
    return out, rings, streets


def num(s):
    try:
        return float(str(s).split(";")[0].replace(",", ".").split()[0])
    except (ValueError, IndexError):
        return None


def shape_of(bid, tags, ring):
    """(высота стен, форма крыши, этажей) — по тегам или по типу (гип.)."""
    b = tags.get("building")
    levels = num(tags.get("building:levels"))
    h = num(tags.get("height"))
    roof = tags.get("roof:shape")
    tagged = levels is not None
    if levels is None:
        levels = LEVELS_BY_TYPE.get(b, DEFAULT_LEVELS)
    wall = h if h else levels * FLOOR_M + PLINTH_M
    area = abs(geo.signed_area(ring))
    if roof is None:
        roof = "pyramidal" if b in ("church", "chapel", "cathedral") else \
            ("flat" if levels >= 3 or area > 600 or b in ("garages", "industrial", "warehouse", "retail") else "hipped")
    if h and roof in PITCHED:
        wall = h * 0.75  # height — до конька
    if h and not tagged:   # этажи для окон — по высоте
        levels = max(1.0, round((wall - PLINTH_M) / FLOOR_M))
    return wall, roof, levels


def pitched_rect(ring, shape):
    """Описанный прямоугольник для скатной крыши или None — крыша плоская."""
    area = abs(geo.signed_area(ring))
    c, u, la, lb = min_rect(ring)
    if shape in PITCHED and area / max(la * lb, 1e-6) >= RECT_MIN and lb >= 3.0:
        return c, u, la, lb
    return None


# ---------- сетка ----------

def _cross(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    return uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx


def normal(a, b, c):
    n = _cross(a, b, c)
    k = math.sqrt(sum(x * x for x in n)) or 1.0
    return tuple(x / k for x in n)


class Part:
    def __init__(self):
        self.v, self.n, self.uv, self.c, self.t = [], [], [], [], []

    def face(self, pts, nrm, uvs, color):
        """Треугольник или четырёхугольник (вершины общие); обход выправляется по нормали nrm (наружу)."""
        cr = _cross(pts[0], pts[1], pts[2])
        if len(pts) == 4:
            c2 = _cross(pts[0], pts[2], pts[3])
            cr = (cr[0] + c2[0], cr[1] + c2[1], cr[2] + c2[2])
        dot = cr[0] * nrm[0] + cr[1] * nrm[1] + cr[2] * nrm[2]
        if abs(dot) < 1e-7:
            return            # вырожденная грань
        if dot < 0:
            pts, uvs = pts[::-1], uvs[::-1]
        i = len(self.v)
        col = [round(x, 3) for x in color]
        nn = [round(nrm[0], 4), round(nrm[1], 4), round(nrm[2], 4)]
        for p, uv in zip(pts, uvs):
            self.v.append([round(p[0], 3), round(p[1], 3), round(p[2], 3)])
            self.n.append(nn)
            self.uv.append([round(uv[0], 2), round(uv[1], 2)])
            self.c.append(col)
        # порядок вершин GeometryScript: нормаль = −(v1 − v0) × (v2 − v0) (wall_mesh.Mesh) — обходим по часовой
        self.t.append([i, i + 2, i + 1])
        if len(pts) == 4:
            self.t.append([i, i + 3, i + 2])

    def tri(self, pts, nrm, uvs, color):
        self.face(list(pts), nrm, list(uvs), color)


class Edge:
    """Ребро контура: u — вдоль ребра от a, w — наружу по нормали, z — высота; s — периметр до a (для UV)."""

    def __init__(self, a, b, s):
        self.a, self.b, self.s = a, b, s
        self.d = math.hypot(b[0] - a[0], b[1] - a[1])
        self.t = ((b[0] - a[0]) / self.d, (b[1] - a[1]) / self.d)
        self.n = (self.t[1], -self.t[0])     # наружу у обхода против часовой (X — север, Y — восток)

    def P(self, u, w, z):
        return (self.a[0] + self.t[0] * u + self.n[0] * w, self.a[1] + self.t[1] * u + self.n[1] * w, z)

    def rect(self, part, u0, u1, z0, z1, w, col, zb):
        """Вертикальный прямоугольник в плоскости стены, вынесенный на w, лицом наружу."""
        if u1 - u0 < 1e-3 or z1 - z0 < 1e-3:
            return
        pts = [self.P(u0, w, z0), self.P(u1, w, z0), self.P(u1, w, z1), self.P(u0, w, z1)]
        uvs = [(self.s + u0, z0 - zb), (self.s + u1, z0 - zb), (self.s + u1, z1 - zb), (self.s + u0, z1 - zb)]
        part.face(pts, (self.n[0], self.n[1], 0.0), uvs, col)

    def hface(self, part, u0, u1, w0, w1, z, up, col):
        """Горизонтальная полоса у стены (полка цоколя, низ карниза, откос): up — лицом вверх."""
        if u1 - u0 < 1e-3 or abs(w1 - w0) < 1e-3:
            return
        pts = [self.P(u0, w0, z), self.P(u1, w0, z), self.P(u1, w1, z), self.P(u0, w1, z)]
        part.face(pts, (0.0, 0.0, 1.0 if up else -1.0), [(p[0], p[1]) for p in pts], col)

    def side(self, part, u, w0, w1, z0, z1, sgn, col, zb):
        """Торец поперёк стены на отметке u: sgn = +1 — лицом по ходу ребра, −1 — против."""
        if abs(w1 - w0) < 1e-3 or z1 - z0 < 1e-3:
            return
        pts = [self.P(u, w0, z0), self.P(u, w1, z0), self.P(u, w1, z1), self.P(u, w0, z1)]
        uvs = [(self.s + u + w0, z0 - zb), (self.s + u + w1, z0 - zb), (self.s + u + w1, z1 - zb),
               (self.s + u + w0, z1 - zb)]
        part.face(pts, (sgn * self.t[0], sgn * self.t[1], 0.0), uvs, col)

    def box(self, part, u0, u1, w0, w1, z0, z1, col, zb):
        """Короб у стены (козырёк, балкон): лицо, бока, верх, низ; задняя грань — в стене, её нет."""
        self.rect(part, u0, u1, z0, z1, w1, col, zb)
        self.side(part, u0, w0, w1, z0, z1, -1, col, zb)
        self.side(part, u1, w0, w1, z0, z1, 1, col, zb)
        self.hface(part, u0, u1, w0, w1, z1, True, col)
        self.hface(part, u0, u1, w0, w1, z0, False, col)


def mix(a, b, k):
    return tuple(x + (y - x) * k for x, y in zip(a, b))


def shade(c, k):
    return tuple(x * k for x in c)


# ---------- фасад ----------

class Layout:
    """Вертикальная раскладка здания: отметки цоколя, этажей и карниза (одна на все стены)."""

    def __init__(self, st, zg, top, levels, roof_thick):
        self.zg, self.top = zg, top
        hc = st["cornice"][0]
        self.zc1 = top - roof_thick                 # верх карниза: под подшивкой свеса или у плоской кровли
        self.zc0 = self.zc1 - hc
        self.zp = zg + st["plinth"]
        n = max(0, int(levels + 1e-6)) if st["windows"] else 0
        n = min(n, int((self.zc0 - self.zp) / MIN_FLOOR_M))
        self.floors = []                            # (низ этажа, высота этажа)
        if n > 0:
            wts = [st["first"]] + [1.0] * (n - 1)
            unit = (self.zc0 - self.zp) / sum(wts)
            z = self.zp
            for w in wts:
                self.floors.append((z, unit * w))
                z += unit * w

    def window(self, st, i):
        """(ширина, низ, верх) окна этажа i."""
        base, fh = self.floors[i]
        if i == 0 and st["vitrine"]:
            wh = min(fh * 0.72, 2.6)
            return 2.4, base + 0.35, base + 0.35 + wh
        ww, wh = st["win"]
        wh = min(wh, fh * 0.62)
        sill = base + (fh - wh) * 0.62
        return ww, sill, sill + wh


class Facade:
    """Сборка одного здания в части клетки: стены, окна, двери, цоколь, карниз, кровля."""

    def __init__(self, parts, ctx, origin, key):
        self.f, self.g, self.r = parts["facade"], parts["glass"], parts["roof"]
        self.ctx, self.o, self.key = ctx, origin, key

    def world(self, p):
        return p[0] + self.o[0], p[1] + self.o[1]

    def edges(self, ring):
        out, s = [], 0.0
        for a, b in zip(ring, ring[1:] + ring[:1]):
            if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-3:
                continue
            e = Edge(a, b, s)
            out.append(e)
            s += e.d
        return out

    def free_mask(self, e):
        """Отметки проб вдоль ребра и маска «не глухая» (нет соседа ближе PARTY_M)."""
        k = max(2, int(math.ceil(e.d / SAMPLE_M)) + 1)
        us = np.linspace(0.0, e.d, k)
        pts = np.asarray([self.world(e.P(u, 0.1, 0.0)) for u in us], float)
        return us, ~self.ctx.blocked(self.key, pts)

    @staticmethod
    def is_free(us, ok, u0, u1):
        sel = (us >= u0 - 0.25) & (us <= u1 + 0.25)
        return bool(ok[sel].all()) if sel.any() else True

    def columns(self, e, st, ww, us, ok):
        """Оси окон по ребру: равный шаг от середины, простенки у углов, только на свободных участках."""
        avail = e.d - 2 * st["corner"]
        if avail < ww:
            return []
        m = 1 + int((avail - ww) / st["step"])
        span = (m - 1) * st["step"] + ww
        c0 = (e.d - span) / 2 + ww / 2
        cs = [c0 + k * st["step"] for k in range(m)]
        return [c for c in cs if self.is_free(us, ok, c - ww / 2, c + ww / 2)]

    def ground(self, e, u):
        return self.ctx.hts.at(*self.world(e.P(u, 0.6, 0.0)))

    def build(self, ring, z0, wall_h, shape, levels, st, lod, h):
        zg = z0 + BURY_M
        top = zg + wall_h
        rect = pitched_rect(ring, shape)
        detail = lod == 0
        roof_thick = ROOF_THICK if (detail and rect) else 0.0
        if not detail:
            st = dict(st, plinth=0.0, cornice=(0.0, 0.0))
        lay = Layout(st, zg, top, levels, roof_thick)
        edges = self.edges(ring)
        wall = st["wall"]
        if lod == 2:
            cover = 0.0
            if lay.floors:
                ww, s0, s1 = lay.window(st, min(1, len(lay.floors) - 1))
                cover = min(0.35, ww * (s1 - s0) / (st["step"] * lay.floors[-1][1]))
            wall = mix(wall, fr.GLASS[0], cover)          # средний тон стены с окнами, как было у шейдера
            for e in edges:
                e.rect(self.f, 0.0, e.d, z0, top, 0.0, wall, z0)
            self.roof(ring, top, shape, rect, st, 0.0, detail=False)
            return
        masks = [self.free_mask(e) for e in edges] if lay.floors or detail else [None] * len(edges)
        street = self.street_edge(edges, masks) if detail else None
        yard = self.yard_edge(edges, masks, street) if detail and st["balconies"] == "yard" else None
        for k, e in enumerate(edges):
            us, ok = masks[k] if masks[k] is not None else (np.zeros(0), np.zeros(0, bool))
            rows = []
            for i in range(len(lay.floors)):
                ww, s0, s1 = lay.window(st, i)
                if s1 > lay.zc0 - 0.15:
                    continue
                cols = [c for c in self.columns(e, st, ww, us, ok) if s0 > self.ground(e, c) + 0.25]
                rows.append([i, ww, s0, s1, cols])
            doors = self.doors(e, st, lay, rows, us, ok) if detail and k == street else []
            if not detail:
                e.rect(self.f, 0.0, e.d, z0, top, 0.0, wall, z0)
                for i, ww, s0, s1, cols in rows:
                    for c in cols:
                        e.rect(self.g, c - ww / 2, c + ww / 2, s0, s1, FLAT_GLASS_M, fr.glass(h + k * 31 + i * 7 + int(c)),
                               z0)
                continue
            self.wall_detail(e, st, lay, rows, z0, h + k * 31)
            for u, dw, dz0, dz1 in doors:
                e.rect(self.f, u - dw / 2, u + dw / 2, dz0, dz1, DOOR_PROUD, st["door_c"], z0)
                if st["canopy"]:
                    cc = fr.COLORS["concrete"] if st["cls"] in ("soviet", "modern") else st["roof"]
                    e.box(self.r, u - dw / 2 - 0.3, u + dw / 2 + 0.3, 0.0, 0.8, dz1 + 0.05, dz1 + 0.17, cc, z0)
            if st["gates"] and k == street:
                self.gates(e, st, lay, us, ok, z0)
            if st["balconies"] and len(lay.floors) >= 3 and ((st["balconies"] == "street" and k == street) or
                                                             (st["balconies"] == "yard" and k == yard)):
                self.balconies(e, st, lay, rows, z0)
        self.roof(ring, top, shape, rect, st, st["overhang"] if detail else 0.0, detail=detail)
        if detail and rect and st["chimneys"]:
            self.chimneys(rect, top, shape, st, h)

    def street_edge(self, edges, masks):
        """Индекс стены к улице: ближайшая улица перед стеной (≤ STREET_M), иначе самая длинная свободная."""
        best, cand = None, []
        for k, e in enumerate(edges):
            us, ok = masks[k]
            if e.d < 3.0 or ok.mean() < 0.6:
                continue
            cand.append(k)
            m = self.world(e.P(e.d / 2, 0.0, 0.0))
            d = self.ctx.street_dist(m, e.n)
            if d is not None and (best is None or d < best[0] - 1.0 or (abs(d - best[0]) <= 1.0 and e.d > edges[best[1]].d)):
                best = (d, k)
        if best:
            return best[1]
        return max(cand, key=lambda k: edges[k].d) if cand else None

    @staticmethod
    def yard_edge(edges, masks, street):
        cand = [k for k, e in enumerate(edges) if k != street and e.d >= 10.0 and masks[k][1].mean() > 0.8]
        if street is not None:   # не параллельную улице стену рядом — ту, что смотрит от улицы
            sn = edges[street].n
            cand = [k for k in cand if edges[k].n[0] * sn[0] + edges[k].n[1] * sn[1] < -0.5] or cand
        return max(cand, key=lambda k: edges[k].d) if cand else None

    def doors(self, e, st, lay, rows, us, ok):
        """Двери на уличной стене: подъезды с шагом door_every или одна посередине; окна первого этажа — прочь."""
        if not st["door"] or e.d < st["door"][0] + 1.0:
            return []
        dw, dh = st["door"]
        n = 1 if not st["door_every"] else max(1, int(round(e.d / st["door_every"])))
        row0 = rows[0] if rows and rows[0][0] == 0 else None
        out = []
        for j in range(n):
            u = e.d * (j + 0.5) / n
            if row0 and row0[4]:
                u = min(row0[4], key=lambda c: abs(c - u))      # по оси окна: ритм простенков сохраняется
            if not self.is_free(us, ok, u - dw / 2, u + dw / 2) or any(abs(u - d[0]) < dw + 1.0 for d in out):
                continue
            z0 = max(lay.zg, min(self.ground(e, u), lay.zp + 1.0))
            out.append((u, dw, z0, z0 + dh))
        if row0:
            row0[4] = [c for c in row0[4] if all(abs(c - d[0]) > (row0[1] + d[1]) / 2 + 0.3 for d in out)]
        return out

    def wall_detail(self, e, st, lay, rows, zb, h):
        """Стена первой зоны: цоколь, пояса и простенки вокруг утопленных окон, откосы, стёкла, карниз."""
        f, g, d = self.f, self.g, e.d
        wall, trim, plc = st["wall"], st["trim"], st["plinth_c"]
        pp = PLINTH_PROUD
        if st["plinth"] > 0:
            e.rect(f, -pp, d + pp, zb, lay.zp, pp, plc, zb)
            e.hface(f, -pp, d + pp, 0.0, pp, lay.zp, True, plc)
        rustic_top = lay.floors[1][0] if st["rustic"] and len(lay.floors) > 1 else None

        def col_at(z0, z1):
            return plc if rustic_top is not None and z1 <= rustic_top + 1e-6 else wall

        rows = [r for r in rows if r[4]]
        levels = [lay.zp]
        for _, _, s0, s1, _ in rows:
            levels += [s0, s1]
        levels.append(lay.zc0)
        # пояса между рядами окон (во всю длину ребра); у руста — разрез по верху первого этажа
        for j in range(0, len(levels), 2):
            z0, z1 = levels[j], levels[j + 1]
            cuts = [z0] + ([rustic_top] if rustic_top is not None and z0 < rustic_top < z1 else []) + [z1]
            for a, b in zip(cuts, cuts[1:]):
                e.rect(f, 0.0, d, a, b, 0.0, col_at(a, b), zb)
        sill_c, rev_top, rev_side = fr.COLORS["sill"], shade(trim, 0.55), shade(trim, 0.85)
        for i, ww, s0, s1, cols in rows:
            cw = col_at(s0, s1)
            edges_u = [0.0]
            for c in cols:
                edges_u += [c - ww / 2, c + ww / 2]
            edges_u.append(d)
            for j in range(0, len(edges_u), 2):          # простенки
                e.rect(f, edges_u[j], edges_u[j + 1], s0, s1, 0.0, cw, zb)
            u0, u1 = cols[0] - ww / 2, cols[-1] + ww / 2
            e.hface(f, u0, u1, 0.0, -RECESS_M, s1, False, rev_top)   # верхний откос (от стены внутрь)
            e.hface(f, u0, u1, 0.0, -RECESS_M, s0, True, sill_c)     # отлив
            for c in cols:
                a, b = c - ww / 2, c + ww / 2
                e.side(f, a, -RECESS_M, 0.0, s0, s1, 1, rev_side, zb)
                e.side(f, b, -RECESS_M, 0.0, s0, s1, -1, rev_side, zb)
                e.rect(g, a, b, s0, s1, -RECESS_M, fr.glass(h + i * 7 + int(c)), zb)
        hc, pc = st["cornice"]
        if hc > 0:
            e.rect(f, -pc, d + pc, lay.zc0, lay.zc1, pc, trim, zb)
            e.hface(f, -pc, d + pc, 0.0, pc, lay.zc0, False, shade(trim, 0.7))
            e.hface(f, -pc, d + pc, 0.0, pc, lay.zc1, True, trim)
        if lay.top - lay.zc1 > 1e-3:   # стена под кровлей со свесом (в торце — фронтон, сама стена скрыта)
            e.rect(f, 0.0, d, lay.zc1, lay.top, 0.0, trim if hc > 0 else wall, zb)

    def gates(self, e, st, lay, us, ok, zb):
        gh = min(2.3 if st["cls"] == "garage" else 3.5, lay.top - lay.zg - 0.4)
        gw, step = (2.6, 3.2) if st["cls"] == "garage" else (3.5, max(e.d, 1.0))
        if gh < 1.5 or e.d < gw + 0.4:
            return
        m = max(1, int((e.d - 0.4) / step))
        for j in range(m):
            u = e.d * (j + 0.5) / m
            if self.is_free(us, ok, u - gw / 2, u + gw / 2):
                z0 = max(lay.zg, self.ground(e, u))
                e.rect(self.f, u - gw / 2, u + gw / 2, z0, z0 + gh, FLAT_GLASS_M, fr.COLORS["gate"], zb)

    def balconies(self, e, st, lay, rows, zb):
        """Балконы: у пятиэтажек — через окно на всех этажах, кроме первого; у сталинок — средние оси."""
        conc = fr.COLORS["concrete"] if st["cls"] == "soviet" else fr.COLORS["trim_white"]
        for i, ww, s0, s1, cols in rows:
            if i == 0 or not cols or (st["cls"] == "stalin" and i >= len(lay.floors) - 1):
                continue
            if st["cls"] == "stalin":
                mid = len(cols) // 2
                sel = cols[max(0, mid - 1):mid + 1] if len(cols) >= 6 else cols[mid:mid + 1]
            else:
                sel = cols[::2]
            fb = lay.floors[i][0]
            bw = ww + 1.0
            for c in sel:
                e.box(self.f, c - bw / 2, c + bw / 2, 0.0, 1.0 if st["cls"] == "soviet" else 0.8, fb - 0.15, fb + 1.0,
                      conc, zb)

    def chimneys(self, rect, top, shape, st, h):
        c, u, la, lb = rect
        v = (-u[1], u[0])
        rh = min(ROOF_PITCH * lb / 2, ROOF_MAX_M)
        ridge = top + rh
        half = (la / 2 if shape == "gabled" else max(la / 2 - lb / 2, 0.0))
        pos = [0.0] if half < 3.0 or shape == "pyramidal" else [-0.45 * half, 0.45 * half][:1 + (la > 14)]
        col = fr.COLORS["brick"] if (h >> 20) % 3 else st["trim"]
        for du in pos:
            dv = 0.25 * lb / 2 * (1 if (h >> 22) % 2 else -1)
            z1 = ridge + 0.8
            z0 = ridge - rh * abs(dv) / (lb / 2) - 0.3          # низ — под скатом
            cx, cy = c[0] + u[0] * du + v[0] * dv, c[1] + u[1] * du + v[1] * dv
            a = (cx - u[0] * 0.4 - v[0] * 0.28, cy - u[1] * 0.4 - v[1] * 0.28)
            e = Edge(a, (a[0] + u[0] * 0.8, a[1] + u[1] * 0.8), 0.0)   # труба 0,8 × 0,56: от ребра a–b по нормали
            e.rect(self.f, 0.0, 0.8, z0, z1, 0.56, col, z0)
            e.side(self.f, 0.0, 0.0, 0.56, z0, z1, -1, col, z0)
            e.side(self.f, 0.8, 0.0, 0.56, z0, z1, 1, col, z0)
            e.hface(self.f, 0.0, 0.8, 0.0, 0.56, z1, True, shade(col, 0.4))
            self.f.face([e.P(0.0, 0.0, z0), e.P(0.8, 0.0, z0), e.P(0.8, 0.0, z1), e.P(0.0, 0.0, z1)],
                        (-e.n[0], -e.n[1], 0.0), [(0, 0), (0.8, 0), (0.8, z1 - z0), (0, z1 - z0)], col)

    def roof(self, ring, top, shape, rect, st, ov, detail):
        """Кровля: плоская — по контуру; скатная — по описанному прямоугольнику, со свесом ov и толщиной."""
        roof, rcol = self.r, st["roof"]
        if not rect:
            for i0, i1, i2 in earcut(ring):
                pts = [(ring[i][0], ring[i][1], top) for i in (i0, i1, i2)]
                roof.face(pts, (0, 0, 1), [(p[0], p[1]) for p in pts], rcol)
            return
        c, u, la, lb = rect
        v = (-u[1], u[0])
        rh = min(ROOF_PITCH * lb / 2, ROOF_MAX_M)
        ha, hb = la / 2, lb / 2
        slope = rh / hb
        ea, eb = ha + ov, hb + ov
        ze = top - ov * slope

        def P(du, dv, z):
            return (c[0] + u[0] * du + v[0] * dv, c[1] + u[1] * du + v[1] * dv, z)

        corners = [P(-ea, -eb, ze), P(ea, -eb, ze), P(ea, eb, ze), P(-ea, eb, ze)]
        if shape == "pyramidal":
            apex = P(0, 0, top + rh)
            faces = [(corners[i], corners[(i + 1) % 4], apex) for i in range(4)]
            rim = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
        elif shape == "gabled":
            r0, r1 = P(-ea, 0, top + rh), P(ea, 0, top + rh)
            faces = [(corners[0], corners[1], r1, r0), (corners[2], corners[3], r0, r1)]
            rim = [(corners[0], corners[1]), (corners[2], corners[3]), (corners[1], r1), (r1, corners[2]),
                   (corners[3], r0), (r0, corners[0])]
            for tri in ((P(ha, -hb, top), P(ha, hb, top), P(ha, 0, top + rh)),
                        (P(-ha, hb, top), P(-ha, -hb, top), P(-ha, 0, top + rh))):   # фронтоны — стены
                self.f.face(list(tri), normal(*tri), [(0, 0), (lb, 0), (lb / 2, rh)], st["wall"])
        else:  # вальмовая и прочие скатные
            k = max(ha - hb, 0.0)
            r0, r1 = P(-k, 0, top + rh), P(k, 0, top + rh)
            faces = [(corners[0], corners[1], r1, r0), (corners[2], corners[3], r0, r1),
                     (corners[1], corners[2], r1), (corners[3], corners[0], r0)]
            rim = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
        for fpts in faces:
            nrm = normal(fpts[0], fpts[1], fpts[2])
            if nrm[2] < 0:
                nrm = tuple(-x for x in nrm)
            roof.face(list(fpts), nrm, [(p[0], p[1]) for p in fpts], rcol)
            if detail:   # подшивка свеса снизу — та же грань ниже на толщину, лицом вниз
                low = [(p[0], p[1], p[2] - ROOF_THICK) for p in fpts]
                roof.face(low, tuple(-x for x in nrm), [(p[0], p[1]) for p in low], shade(rcol, 0.6))
        if detail:       # торцы кровли по краю
            cx, cy = c
            for a, b in rim:
                mx, my = (a[0] + b[0]) / 2 - cx, (a[1] + b[1]) / 2 - cy
                ex, ey = b[0] - a[0], b[1] - a[1]
                nx, ny = ey, -ex
                if nx * mx + ny * my < 0:
                    nx, ny = -nx, -ny
                k = math.hypot(nx, ny) or 1.0
                pts = [a, b, (b[0], b[1], b[2] - ROOF_THICK), (a[0], a[1], a[2] - ROOF_THICK)]
                roof.face(pts, (nx / k, ny / k, 0.0), [(0, 0), (1, 0), (1, 0.1), (0, 0.1)], shade(rcol, 0.8))


# ---------- сборка ----------

def main(glb_dir=None, glb_cells=()):
    hts = Heights()
    blds, rings, streets = buildings()
    ctx = Context(rings, streets, hts)
    cells = {}
    stats = {"buildings": 0, "pitched": 0, "flat": 0, "tagged_levels": 0, "lod": [0, 0, 0],
             "lod_triangles": [0, 0, 0], "classes": {}}
    for bid, tags, ring, key in blds:
        wall_h, shape, levels = shape_of(bid, tags, ring)
        z0 = hts.min_under(ring) - BURY_M
        cx, cy = geo.centroid(ring)
        lod = 0 if math.hypot(cx, cy) < LOD_M[0] else (1 if math.hypot(cx, cy) < LOD_M[1] else 2)
        ck = (math.floor(cx / CELL_M), math.floor(cy / CELL_M))
        ox, oy = ck[0] * CELL_M, ck[1] * CELL_M
        cell = cells.setdefault(ck, {"origin": [ox, oy], "parts": {k: Part() for k in ("facade", "glass", "roof")},
                                     "count": 0})
        local = [(p[0] - ox, p[1] - oy) for p in ring]
        rect = pitched_rect(local, shape)
        st = fr.style(bid, tags, levels, abs(geo.signed_area(ring)), flat_roof=rect is None)
        n0 = sum(len(p.t) for p in cell["parts"].values())
        Facade(cell["parts"], ctx, (ox, oy), key).build(local, z0, wall_h, shape, levels, st, lod,
                                                        zlib.crc32(str(bid).encode()))
        stats["lod_triangles"][lod] += sum(len(p.t) for p in cell["parts"].values()) - n0
        stats["lod"][lod] += 1
        stats["classes"][st["cls"]] = stats["classes"].get(st["cls"], 0) + 1
        cell["count"] += 1
        stats["buildings"] += 1
        stats["tagged_levels"] += "building:levels" in tags
        stats["pitched" if shape in PITCHED else "flat"] += 1   # по форме; скатная без прямоугольника — плоская
    out = {"script": "scripts/city_mesh.py", "cell_m": CELL_M, "units": "м, начало клетки — origin",
           "colors": "linear RGB в цвет вершин, итоговые (материал умножает на палитру ÷ её исходное значение)",
           "lod_m": list(LOD_M), "stats": stats, "cells": []}
    tris = 0
    for (i, j), cell in sorted(cells.items()):
        entry = {"name": f"{i:+d}_{j:+d}".replace("+", "p").replace("-", "m"), "origin": cell["origin"],
                 "count": cell["count"], "parts": {}}
        for k, p in cell["parts"].items():
            if p.t:
                entry["parts"][k] = {"v": p.v, "n": p.n, "uv": p.uv, "c": p.c, "t": p.t}
                tris += len(p.t)
        out["cells"].append(entry)
    stats["cells"], stats["triangles"] = len(out["cells"]), tris
    means = {}
    for k in ("facade", "roof"):
        cs = [c for cell in out["cells"] if k in cell["parts"] for c in cell["parts"][k]["c"]]
        means[k] = [round(float(x), 4) for x in np.mean(np.asarray(cs), 0)] if cs else [0.5, 0.5, 0.5]
    out["facade_mean"], out["roof_mean"] = means["facade"], means["roof"]  # справка: средние по вершинам
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    preview(out)
    if glb_dir:
        for name in glb_cells:
            cell = next((c for c in out["cells"] if c["name"] == name), None)
            if cell is None:
                print(f"[city_mesh] нет клетки {name}")
                continue
            path = os.path.join(glb_dir, f"city_{name}.glb")
            write_glb(cell, path)
            print(f"[city_mesh] {path}")
    print(json.dumps(stats, ensure_ascii=False))


def preview(out):
    n, k = 2048, 2048 / (2 * HALF)
    img = Image.new("RGB", (n, n), (40, 50, 40))
    d = ImageDraw.Draw(img)
    for cell in out["cells"]:
        ox, oy = cell["origin"]
        p = cell["parts"].get("roof")
        if not p:
            continue
        for a, b, c in p["t"]:
            if p["n"][a][2] < 0.1:
                continue
            pts = [((p["v"][i][1] + oy + HALF) * k, (HALF - p["v"][i][0] - ox) * k) for i in (a, b, c)]
            d.polygon(pts, fill=(200, 90, 60))
    img.save(os.path.join(OUT_DIR, "city_top.png"))


def write_glb(cell, path):
    """Клетка → GLB (glTF 2.0) с цветами вершин COLOR_0: оси glTF = (X, Z, Y) от UE (Y-вверх, зеркало),
    Blender при импорте возвращает (X, −Y, Z) — как у bl_krom. Порядок индексов GeometryScript в зеркале — прямой."""
    ox, oy = cell["origin"]
    bins, views, accs, prims = bytearray(), [], [], []

    def add(arr, target, comp, typ):
        off = len(bins)
        bins.extend(arr.tobytes())
        while len(bins) % 4:
            bins.append(0)
        views.append({"buffer": 0, "byteOffset": off, "byteLength": arr.nbytes, **({"target": target} if target else {})})
        acc = {"bufferView": len(views) - 1, "componentType": comp, "count": int(arr.shape[0]), "type": typ}
        if typ == "VEC3" and comp == 5126:
            acc["min"], acc["max"] = arr.min(0).tolist(), arr.max(0).tolist()
        accs.append(acc)
        return len(accs) - 1

    mats = []
    for k, p in cell["parts"].items():
        v = np.asarray(p["v"], np.float32) + np.asarray([ox, oy, 0.0], np.float32)
        pos = np.ascontiguousarray(v[:, [0, 2, 1]])
        nrm = np.ascontiguousarray(np.asarray(p["n"], np.float32)[:, [0, 2, 1]])
        col = np.ascontiguousarray(np.asarray(p["c"], np.float32))
        idx = np.asarray(p["t"], np.uint32).reshape(-1)
        attrs = {"POSITION": add(pos, 34962, 5126, "VEC3"), "NORMAL": add(nrm, 34962, 5126, "VEC3"),
                 "COLOR_0": add(col, 34962, 5126, "VEC3")}
        mats.append({"name": f"city_{k}", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1],
                     "metallicFactor": 0.0, "roughnessFactor": 0.2 if k == "glass" else 0.85}})
        prims.append({"attributes": attrs, "indices": add(idx, 34963, 5125, "SCALAR"), "material": len(mats) - 1})
    gl = {"asset": {"version": "2.0", "generator": "PskovKrom scripts/city_mesh.py"}, "scene": 0,
          "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": f"city_{cell['name']}"}],
          "meshes": [{"primitives": prims, "name": f"city_{cell['name']}"}], "materials": mats,
          "buffers": [{"byteLength": len(bins)}], "bufferViews": views, "accessors": accs}
    js = json.dumps(gl, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(bins)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(bins), 0x004E4942) + bytes(bins))


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--glb"]:
        main(os.path.abspath(args[1]), args[2:])
    else:
        main()
