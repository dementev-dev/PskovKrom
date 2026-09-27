"""furniture_points.py — точки малых форм вдоль прогулочных дорожек у Крома (M5): фонари, скамейки, урны из OSM
и правил → build/furniture/points.json.

Не для редактора: запускается обычным Python из .venv (numpy, matplotlib):

    PYTHONIOENCODING=utf-8 .venv/Scripts/python scripts/furniture_points.py

Z у точек нет: землю под каждой найдёт трасса в редакторе (scripts/furniture_krom.py) — рельеф ещё меняется
(D-037, D-038). Оси и метры — D-013: x — север, y — восток, начало — центр Троицкого собора. Всё детерминированно.
Геометрия дорожек — прямо из OSM (refs/osm/krom_2*.json), не из build/roads/roads.json: тот ещё меняется.
Вода, здания и стены — osm_layers.collect(). Только зона ZONE_R_M = 650 м от собора.

Виды (kind) и модели — KINDS; модели строит scripts/blender/street_furniture.py.

1. OSM (source "osm", узлы refs/osm/krom_env_*.json, S-41) — ровно в точке узла:
   highway=street_lamp → lamp_retro внутри контуров Крома (relation 4060616) и Довмонтова города (4060635),
   иначе lamp_column; amenity=bench → bench (все скамейки у Крома в OSM — backrest=no, material=wood, seats=4;
   7 скамеек со спинкой в парке за Советским мостом ставятся той же моделью — упрощение); amenity=waste_basket → bin.
   Поворот: фонарь — скосом к ближайшей дорожке, скамейка — сидящим от ближайшей дорожки (спиной к ней: на
   набережных — лицом к воде), урна — вдоль дорожки.
2. Правила (source "rule") — только там, где фонари и скамейки видны на фото, а в OSM их нет. Всё это гипотеза:
   места — по фото S-42 и S-34, шаг — по OSM и фото «на глаз», сторона дорожки — по фото. Список — RULES:
   - lamp_column вдоль тропы Псковы 66789566 — дыры в ряду OSM (89–111 м при шаге 25–31 м) заполняются тем же
     шагом, на той же стороне (к холму);
   - lamp_column вдоль тропы под западной стеной 66656356 (lit=yes; фонари на фото env01, env02 — со стороны откоса,
     в OSM ни одного) — шаг как у Псковы;
   - lamp_column вдоль набережной Великой под Довмонтовым городом 121919089 (pedestrian, lit=yes; env15: столбики
     по краю газона у стены и у парапета к воде) — два ряда вразбежку, у воды — только до Ольгинского моста;
   - lamp_retro вдоль дороги к Великим воротам 65775670 (img4: три «ретро»-фонаря с запада) — шаг 18 м;
   - lamp_retro во дворе Крома по дорожкам в YARD_R_M от собора (s_2022 — у собора, belfry_yard — у колокольни;
     на kutekroma_yard вдоль дорожки к Кутекроме фонарей нет) — шаг 30 м;
   - bench (+ bin рядом) вдоль тропы Псковы (env10, env11: скамейки по всей тропе, в OSM — две группы) и набережной
     Великой до Ольгинского моста (env15) со стороны воды, лицом к воде — шаг 45 м, где скамейки OSM нет ближе 30 м;
   - площадь Ленина (благоустройство 2021 г.: 53 фонаря, 108 скамеек, 26 урн — S-136; в OSM нет ни одного):
     lamp_column вдоль дорожек по мощению площади (osm_layers.squares, square — id площади) — шаг 20 м; bench + bin вдоль
     обеих кромок площадки перед памятником лицом внутрь, к клумбе 2026 г. (side="toward") — шаг 7 м;
   - Октябрьская площадь (за зоной 650 м: у правил zone_m = OLGA_ZONE_M; в OSM фонарей и скамеек нет): lamp_column по
     краю площадки у памятника княгине Ольге (изнутри, к памятнику) и вдоль аллей Детского парка от неё — в OLGA_NEAR_M
     от памятника, шаг 20 м (фото o15, o18 — S-154: высокие фонари вдоль аллей); bench + bin вдоль тех же аллей —
     шаг 25 м (гип.).
   Точка правила ставится сбоку от дорожки (полуширина + отступ) и отбрасывается: дальше zone_m, в воде или ближе
   WATER_GAP_M к урезу OSM, в здании или ближе BUILT_GAP_M, ближе к оси стены, чем WALL_WIDTH / 2 + wall_gap_m,
   на другой дорожке или дороге (полуширина + PATH_GAP_M, у скамеек — дальше: не у развилок), ближе gap_m
   к фонарю (скамейке) — своему или OSM.

Выход (build/furniture, не в git): points.json — заголовок (виды, правила, счётчики по видам и источникам, отказы)
и точки по одной на строку: kind, x, y, yaw_deg (поворот +X модели к +Y, как yaw в UE), source, osm_id / rule, way;
points.png — вся зона 650 м; points_krom.png — ±280 м у Крома.
"""
import datetime
import json
import math
import os
import sys
from dataclasses import dataclass

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.path import Path  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402
import osm_layers  # noqa: E402
import landmarks_plan  # noqa: E402

OUT_DIR = os.path.join(geo.REPO, "build", "furniture")
OUT_JSON = os.path.join(OUT_DIR, "points.json")
OUT_PNG = os.path.join(OUT_DIR, "points.png")
OUT_PNG_KROM = os.path.join(OUT_DIR, "points_krom.png")

ZONE_R_M = 650.0
KROM_REL, DOVMONT_REL = 4060616, 4060635

KINDS = {   # вид → модель (scripts/blender/street_furniture.py) и что это
    "lamp_column": {"asset": "SM_Furn_LampColumn", "note": "фонарь-столбик набережных Псковы, Стрелки и Великой"},
    "lamp_retro": {"asset": "SM_Furn_LampRetro", "note": "«ретро»-фонарь двора Крома и Довмонтова города"},
    "bench": {"asset": "SM_Furn_Bench", "note": "скамейка без спинки: доски на двух бетонных тумбах"},
    "bin": {"asset": "SM_Furn_Bin", "note": "бетонная урна-куб"},
}
FAMILY = {"lamp_column": "lamp", "lamp_retro": "lamp", "bench": "bench", "bin": "bin"}

# ---------- отступы и зазоры, м ----------
OFFSET = {"lamp": 0.6, "bench": 0.55, "bin": 0.45}  # от края дорожки до оси точки
BIN_ALONG_M = 1.6        # урна у скамейки правила — на столько вдоль дорожки от её середины
WATER_GAP_M = 1.0
BUILT_GAP_M = 0.8
PATH_GAP_M = {"lamp": 0.25, "bench": 2.5, "bin": 0.25}  # от края чужой дорожки; скамейка — не у развилки
WALL_WIDTH = osm_layers.WALL_WIDTH
YARD_CENTER, YARD_R_M = (0.0, 0.0), 70.0   # «площадь» у собора и колокольни (колокольня — в 62 м)

# ширина дорожек без тега width, м: сначала здесь (по фото), потом osm_layers.WAY_WIDTH, тег, вид highway
WIDTH = {121919089: 7.0}  # набережная Великой под Довмонтовым городом: асфальт 6–8 м (env15, research_roads §2; гип.)
PATH_KINDS = set(osm_layers.PATH_WIDTH) | {"pedestrian", "living_street"}   # «дорожки» для поворота скамеек


@dataclass
class Rule:
    """Ряд точек вдоль линий OSM ways: шаг step_m, первая точка — на phase шага от начала линии."""
    name: str
    kind: str
    ways: tuple
    step_m: float
    side: str                 # land — от воды, water — к воде, west — к западу, any — где пройдёт проверку
    note: str
    phase: float = 0.5
    gap_m: float = 0.0        # 0 — 0,6 шага
    wall_gap_m: float = 1.5
    x_min: float = -1e9       # только севернее (набережная Великой — до Ольгинского моста)
    near: tuple = None        # (центр, радиус) — только в круге
    inside: int = 0           # только внутри контура relation (двор Крома)
    with_bin: bool = False
    toward: tuple = None      # side="toward": со стороны дорожки, ближней к этой точке (площадка площади Ленина)
    square: tuple = ()        # ways=(): дорожки по мощению этих площадей (id в osm_layers.squares), ≥ 60 % длины
    zone_m: float = ZONE_R_M  # точки дальше от собора отбрасываются (Октябрьская площадь — за зоной 650 м)


LAMP_STEP_M = 28.0   # медиана шага фонарей OSM вдоль тропы Псковы 66789566 (25,9–31,2 м; считается и в сводке)
BENCH_STEP_M = 45.0
OLGINSKY_X = -345.0  # ось Ольгинского моста у набережной (way 85952978 пересекает её около x = −350)
LENIN_PLAZA = (-316.88, 203.35)   # середина площадки перед памятником Ленину (клумба 2026 г.,
                                  # osm_layers.SQUARE_REL_BEDS)
OLGA_XY = landmarks_plan.OLGA_XY  # ось памятника княгине Ольге (Октябрьская площадь, 740 м от собора)
OLGA_ZONE_M, OLGA_NEAR_M = 800.0, 100.0
OLGA_PLAZA_RING = 96334914        # контур площадки у памятника (footway по краю; osm_layers.SQUARE_WAYS)
OLGA_ALLEYS = (95196659,          # аллея вдоль Октябрьского проспекта (к Анастасиевской церкви)
               231526701,         # от памятника в глубь Детского парка
               96334923,          # на юг, к храму Василия на Горке (compacted)
               95196669)          # вдоль Советской улицы

RULES = [
    Rule("pskova_lamps", "lamp_column", (66789566,), LAMP_STEP_M, "land",
         "тропа Псковы, lit=yes: дыры в ряду OSM (89–111 м) — тем же шагом, со стороны холма, как у фонарей OSM; "
         "гипотеза — фонари там есть, но не нанесены (env10, e_holy: ряд без пропусков)"),
    Rule("velikaya_path_lamps", "lamp_column", (66656356,), LAMP_STEP_M, "land",
         "тропа под западной стеной, lit=yes: фонари со стороны откоса (env01, env02), в OSM ни одного; шаг — "
         "как у Псковы (гипотеза)"),
    Rule("velikaya_embankment_lamps", "lamp_column", (121919089,), LAMP_STEP_M, "land",
         "набережная Великой под Довмонтовым городом, lit=yes: столбики по краю газона у стены (env15); шаг — "
         "как у Псковы (гипотеза)"),
    Rule("velikaya_embankment_lamps_water", "lamp_column", (121919089,), LAMP_STEP_M, "water",
         "там же, второй ряд у парапета к воде вразбежку (env15), только до Ольгинского моста (гипотеза)",
         phase=0.0, gap_m=12.0, x_min=OLGINSKY_X),
    Rule("dovmont_road_lamps", "lamp_retro", (65775670,), 18.0, "west",
         "дорога к Великим воротам через Довмонтов город: «ретро»-фонари с западной стороны (img4, S-34); "
         "шаг на глаз (гипотеза)", wall_gap_m=1.0),
    Rule("krom_yard_lamps", "lamp_retro", (), 30.0, "any",
         "двор Крома у собора и колокольни (s_2022, belfry_yard); вдоль дорожки к Кутекроме на фото фонарей "
         "нет — только в круге YARD_R_M; шаг и сторона — гипотеза", wall_gap_m=3.0,
         near=(YARD_CENTER, YARD_R_M), inside=KROM_REL),
    Rule("pskova_benches", "bench", (66789566,), BENCH_STEP_M, "water",
         "тропа Псковы: скамейки по всей тропе (env10, env11), в OSM — две группы; со стороны воды, лицом к ней, "
         "с урной (гипотеза)", gap_m=30.0, with_bin=True),
    Rule("velikaya_embankment_benches", "bench", (121919089,), BENCH_STEP_M, "water",
         "набережная Великой под Довмонтовым городом: скамейка с урной у островка с деревом (env15); лицом к воде, "
         "до Ольгинского моста (гипотеза)", gap_m=30.0, x_min=OLGINSKY_X, with_bin=True),
    # площадь Ленина: благоустройство 2021 г. — 53 светодиодных фонаря, 108 скамеек и сидений, 26 урн (S-136); в OSM
    # на площади ни одного фонаря и скамейки. Фонари — шары на высоких столбах (фото l18 2023, l09 2026, n02 2026):
    # ближе всего столбик набережных (труба ≈4,2 м с рассеивателем); скамейки — бетонный блок с деревянным сиденьем,
    # как Bench (l18, n02)
    Rule("lenin_square_lamps", "lamp_column", (), 20.0, "any",
         "площадь Ленина: фонари-шары вдоль дорожек по мощению площади (l18, l09); шаг 20 м — чтобы на площади вышло "
         "около 50 (в 2021 г. — 53, S-136); сторона — гипотеза", phase=0.25, gap_m=10.0, square=(18345449,)),
    Rule("lenin_plaza_benches", "bench", (65775692, 65775627), 7.0, "toward",
         "площадь Ленина, площадка перед памятником: скамейки вдоль обеих кромок лицом внутрь, к клумбе 2026 г. "
         "(l18 2023, n02 2026); шаг — гипотеза", gap_m=4.0, toward=LENIN_PLAZA, with_bin=True),
    # Октябрьская площадь и Детский парк (за зоной 650 м): в OSM ни фонарей, ни скамеек; на фото o15 (2015) и o18
    # (2015) — высокие фонари-столбы вдоль края площадки у памятника и аллей парка, скамейки вдоль аллей (S-154)
    Rule("olga_plaza_lamps", "lamp_column", (OLGA_PLAZA_RING,), 20.0, "toward",
         "площадка у памятника княгине Ольге: фонари по краю изнутри (o15); шаг — гипотеза", phase=0.25,
         gap_m=10.0, toward=OLGA_XY, near=(OLGA_XY, OLGA_NEAR_M), zone_m=OLGA_ZONE_M),
    Rule("olga_alley_lamps", "lamp_column", OLGA_ALLEYS, 20.0, "any",
         "аллеи Детского парка от площадки у памятника: фонари вдоль аллей (o15, o18); шаг и сторона — гипотеза",
         gap_m=10.0, near=(OLGA_XY, OLGA_NEAR_M), zone_m=OLGA_ZONE_M),
    Rule("olga_alley_benches", "bench", OLGA_ALLEYS, 25.0, "any",
         "аллеи Детского парка у памятника: скамейки с урной (o12 — скамейка у газона); шаг — гипотеза", phase=0.3,
         gap_m=12.0, near=(OLGA_XY, OLGA_NEAR_M), zone_m=OLGA_ZONE_M, with_bin=True),
]


# ---------- геометрия ----------

class Segments:
    """Отрезки ломаных с меткой: расстояние от точки до ближайшего, точка на нём и направление."""

    def __init__(self, lines, tags=None):
        a, b, t = [], [], []
        for i, line in enumerate(lines):
            for p, q in zip(line, line[1:]):
                if p != q:
                    a.append(p)
                    b.append(q)
                    t.append(tags[i] if tags is not None else i)
        self.a, self.b = np.array(a, float).reshape(-1, 2), np.array(b, float).reshape(-1, 2)
        self.tag = t
        self.d = self.b - self.a
        self.len2 = (self.d ** 2).sum(1)

    def near(self, p):
        """(расстояние, ближайшая точка, единичное направление отрезка, метка) до всех отрезков — массивами."""
        p = np.asarray(p, float)
        t = np.clip(((p - self.a) * self.d).sum(1) / self.len2, 0.0, 1.0)
        q = self.a + t[:, None] * self.d
        return np.hypot(*(p - q).T), q, self.d / np.sqrt(self.len2)[:, None]

    def nearest(self, p, mask=None):
        dist, q, u = self.near(p)
        if mask is not None:
            dist = np.where(mask, dist, np.inf)
        i = int(np.argmin(dist))
        return float(dist[i]), q[i], u[i], self.tag[i]


class Area:
    """Многоугольники: внутри ли точка и расстояние до края."""

    def __init__(self, rings):
        rings = [r for r in rings if len(r) >= 3]
        self.paths = [Path(np.array(r, float)) for r in rings]
        self.edges = Segments([list(r) + [r[0]] for r in rings])
        lo = np.array([np.min(r, 0) for r in rings]) if rings else np.zeros((0, 2))
        hi = np.array([np.max(r, 0) for r in rings]) if rings else np.zeros((0, 2))
        self.lo, self.hi = lo, hi

    def inside(self, p):
        cand = np.nonzero((self.lo[:, 0] <= p[0]) & (p[0] <= self.hi[:, 0]) &
                          (self.lo[:, 1] <= p[1]) & (p[1] <= self.hi[:, 1]))[0]
        return any(self.paths[i].contains_point(p) for i in cand)

    def dist(self, p):
        """Расстояние до края; внутри — со знаком минус."""
        d = float(self.edges.near(p)[0].min()) if len(self.edges.tag) else math.inf
        return -d if self.inside(p) else d


def way_width(el):
    """Ширина дорожки (м): WIDTH (по фото) → osm_layers.WAY_WIDTH → тег width → вид highway."""
    tags = el.get("tags", {})
    hw = tags.get("highway")
    if el["id"] in WIDTH:
        return WIDTH[el["id"]]
    if el["id"] in getattr(osm_layers, "WAY_WIDTH", {}):
        return osm_layers.WAY_WIDTH[el["id"]]
    default = osm_layers.ROAD_WIDTH.get(hw) or osm_layers.PATH_WIDTH.get(hw) or 3.0
    return osm_layers.width_of(tags, default)


def polylines(el):
    return [part for part in geo.split_on_none(geo.local_points(el["geometry"]))]


def sample(line, s):
    """Точка и единичное направление на ломаной line на пути s от начала."""
    for p, q in zip(line, line[1:]):
        L = math.dist(p, q)
        if L == 0:
            continue
        if s <= L:
            u = ((q[0] - p[0]) / L, (q[1] - p[1]) / L)
            return (p[0] + u[0] * s, p[1] + u[1] * s), u
        s -= L
    return None, None


def length(line):
    return sum(math.dist(p, q) for p, q in zip(line, line[1:]))


def yaw_of(f):
    """Поворот модели (+X к направлению f) в градусах, как yaw в UE: x — север, y — восток."""
    return round(math.degrees(math.atan2(f[1], f[0])), 1)


# ---------- сцена ----------

class World:
    def __init__(self):
        polys, lines = osm_layers.collect()
        self.water = Area(polys["Water"])
        self.built = Area(polys["Building"] + polys["Historic"])
        self.walls = Segments([p for p, _ in lines["Wall"]])
        self.krom = Area([osm_layers.relation_ring(KROM_REL)])
        self.dovmont = Area([osm_layers.relation_ring(DOVMONT_REL)])
        main = geo.load_elements(geo.latest("krom_2*.json"))
        self.ways = {e["id"]: e for e in main if e["type"] == "way" and "geometry" in e}
        paths, tags = [], []
        for e in self.ways.values():
            t = e.get("tags", {})
            hw = t.get("highway")
            if not hw or t.get("tunnel") in ("yes", "building_passage") or t.get("area") == "yes":
                continue
            if hw not in osm_layers.ROAD_WIDTH and hw not in osm_layers.PATH_WIDTH:
                continue
            w = way_width(e)
            for line in polylines(e):
                paths.append(line)
                tags.append((e["id"], w / 2, hw in PATH_KINDS))
        self.paths = Segments(paths, tags)
        self.path_half = np.array([t[1] for t in self.paths.tag])
        self.path_id = np.array([t[0] for t in self.paths.tag])
        self.footway = np.array([t[2] for t in self.paths.tag])

    def nearest_path(self, p):
        """Ближайшая дорожка (в 15 м), иначе ближайшая дорога: (расстояние, точка, направление, id)."""
        d, q, u, tag = self.paths.nearest(p, self.footway)
        if d > 15.0:
            d, q, u, tag = self.paths.nearest(p)
        return d, q, u, tag[0]

    def reject(self, p, rule, own, fam):
        """Причина отказа точки правила (fam — семейство точки) или None."""
        if math.hypot(*p) > rule.zone_m:
            return "zone"
        if p[0] < rule.x_min:
            return "x_min"
        if rule.near and math.dist(p, rule.near[0]) > rule.near[1]:
            return "near"
        if rule.inside == KROM_REL and not self.krom.inside(p):
            return "outside"
        if self.water.dist(p) < WATER_GAP_M:
            return "water"
        if self.built.dist(p) < BUILT_GAP_M:
            return "built"
        if len(self.walls.tag) and float(self.walls.near(p)[0].min()) < WALL_WIDTH / 2 + rule.wall_gap_m:
            return "wall"
        dist = self.paths.near(p)[0]
        if np.any((dist < self.path_half + PATH_GAP_M[fam]) & (self.path_id != own)):
            return "path"
        return None


def osm_points(world):
    env = geo.load_elements(geo.latest("krom_env_*.json"))
    pts, backrest = [], 0
    for e in sorted((e for e in env if e["type"] == "node"), key=lambda e: e["id"]):
        t = e.get("tags", {})
        if t.get("highway") == "street_lamp":
            kind = "lamp"
        elif t.get("amenity") == "bench":
            kind = "bench"
        elif t.get("amenity") == "waste_basket":
            kind = "bin"
        else:
            continue
        p = geo.to_local(e["lat"], e["lon"])
        if math.hypot(*p) > ZONE_R_M:
            continue
        d, q, u, wid = world.nearest_path(p)
        n = (-u[1], u[0])
        if kind == "lamp":
            kind = "lamp_retro" if world.krom.inside(p) or world.dovmont.inside(p) else "lamp_column"
            f = (q[0] - p[0], q[1] - p[1]) if d > 0.3 else n          # скосом к дорожке
        elif kind == "bench":
            backrest += t.get("backrest") == "yes"
            if d > 0.5:
                f = (p[0] - q[0], p[1] - q[1])                          # спиной к дорожке
            else:                                                        # на оси дорожки: лицом к воде
                a, b = (p[0] + 3 * n[0], p[1] + 3 * n[1]), (p[0] - 3 * n[0], p[1] - 3 * n[1])
                f = n if world.water.dist(a) <= world.water.dist(b) else (-n[0], -n[1])
        else:
            f = tuple(u)
        pts.append({"kind": kind, "x": round(p[0], 2), "y": round(p[1], 2), "yaw_deg": yaw_of(f), "source": "osm",
                    "osm_id": e["id"], "way": int(wid)})
    return pts, backrest


def rule_lines(world, rule):
    """Линии правила: [(id, ломаная, полуширина)]. Двор Крома — дорожки внутри контура у собора."""
    out = []
    ids = rule.ways
    if not ids and rule.square:
        ids = []
        for wid, e in sorted(world.ways.items()):
            t = e.get("tags", {})
            if t.get("highway") not in osm_layers.PATH_WIDTH or t.get("footway") in ("crossing", "sidewalk"):
                continue
            mids = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for line in polylines(e) for a, b in zip(line, line[1:])]
            if mids and sum(osm_layers.in_squares(m, ids=rule.square) for m in mids) >= 0.6 * len(mids):
                ids.append(wid)
    elif not ids:
        ids = []
        for wid, e in sorted(world.ways.items()):
            t = e.get("tags", {})
            if t.get("highway") not in osm_layers.PATH_WIDTH or t.get("covered") == "yes" or "tunnel" in t:
                continue
            pts = [p for line in polylines(e) for p in line]
            if any(world.krom.inside(p) and math.dist(p, rule.near[0]) <= rule.near[1] for p in pts):
                ids.append(wid)
    for wid in ids:
        e = world.ways[wid]
        for line in polylines(e):
            out.append((wid, line, way_width(e) / 2))
    return out


def rule_points(world, pts, stats):
    """Точки всех правил по очереди; каждая следующая видит уже поставленные (и точки OSM)."""
    for rule in RULES:
        fam = FAMILY[rule.kind]
        gap = rule.gap_m or 0.6 * rule.step_m
        st = stats.setdefault(rule.name, {"placed": 0, "bins": 0, "rejected": {}})
        for wid, line, half in rule_lines(world, rule):
            L = length(line)
            k = 0
            while (rule.phase + k) * rule.step_m <= L:
                s = (rule.phase + k) * rule.step_m
                k += 1
                c, u = sample(line, s)
                n = (-u[1], u[0])
                off = half + OFFSET[fam]
                sides = [(c[0] + off * n[0], c[1] + off * n[1], n),
                         (c[0] - off * n[0], c[1] - off * n[1], (-n[0], -n[1]))]
                if rule.side in ("land", "water"):
                    sides.sort(key=lambda sd: world.water.dist(sd[:2]), reverse=rule.side == "land")
                    sides = sides[:1]
                elif rule.side == "west":
                    sides = [min(sides, key=lambda sd: sd[1])]
                elif rule.side == "toward":
                    sides = [min(sides, key=lambda sd: math.dist(sd[:2], rule.toward))]
                why = None
                for x, y, out in sides:
                    p = (x, y)
                    why = world.reject(p, rule, wid, fam)
                    if why is None and any(FAMILY[q["kind"]] == fam and math.dist(p, (q["x"], q["y"])) < gap
                                           for q in pts):
                        why = "gap"
                    if why is None:
                        break
                if why:
                    st["rejected"][why] = st["rejected"].get(why, 0) + 1
                    continue
                if fam == "lamp":
                    f = (-out[0], -out[1])                 # скосом к дорожке
                elif fam == "bench":
                    f = out                                # спиной к дорожке
                else:
                    f = u
                pts.append({"kind": rule.kind, "x": round(x, 2), "y": round(y, 2), "yaw_deg": yaw_of(f),
                            "source": "rule", "rule": rule.name, "way": wid})
                st["placed"] += 1
                if rule.with_bin:
                    boff = half + OFFSET["bin"]
                    b = (c[0] + boff * out[0] + BIN_ALONG_M * u[0], c[1] + boff * out[1] + BIN_ALONG_M * u[1])
                    if world.reject(b, rule, wid, "bin") is None:
                        pts.append({"kind": "bin", "x": round(b[0], 2), "y": round(b[1], 2), "yaw_deg": yaw_of(u),
                                    "source": "rule", "rule": rule.name, "way": wid})
                        st["bins"] += 1
    return pts


def osm_lamp_step(world, pts):
    """Шаг фонарей OSM вдоль тропы Псковы: медиана расстояний между соседями по пути (сверка LAMP_STEP_M)."""
    segs = Segments(polylines(world.ways[66789566]))
    lamps = [q for q in pts if q["source"] == "osm" and FAMILY[q["kind"]] == "lamp"]
    chain = []
    cum = np.concatenate([[0.0], np.cumsum(np.sqrt(segs.len2))])
    for q in lamps:
        dist, near, _ = segs.near((q["x"], q["y"]))
        i = int(np.argmin(dist))
        if dist[i] < 8.0:
            chain.append(cum[i] + math.dist(segs.a[i], near[i]))
    gaps = np.diff(sorted(chain))
    gaps = gaps[(gaps > 10) & (gaps < 45)]          # соседи в ряду: без дыр и без пар у развилок
    return round(float(np.median(gaps)), 1) if len(gaps) else None


# ---------- превью ----------

STYLE = {"lamp_column": ("o", "#e0b000"), "lamp_retro": ("D", "#e06000"), "bench": ("s", "#7a4a1a"),
         "bin": ("^", "#2a8a2a")}


def preview(world, pts, path, center, r, dpi, ms):
    fig, ax = plt.subplots(figsize=(14, 14))
    for ring in world.water.paths:
        v = ring.vertices
        ax.fill(v[:, 1], v[:, 0], color="#a8cbe8", zorder=0, lw=0)
    for ring in world.built.paths:
        v = ring.vertices
        ax.fill(v[:, 1], v[:, 0], color="#d4d4d4", zorder=1, lw=0)
    for a, b in zip(world.walls.a, world.walls.b):
        ax.plot([a[1], b[1]], [a[0], b[0]], color="#8a6d3b", lw=3, zorder=2, solid_capstyle="round")
    rule_ways = {w for rule in RULES for w in rule.ways}
    for a, b, (wid, half, foot) in zip(world.paths.a, world.paths.b, world.paths.tag):
        col = "#c0501a" if wid in rule_ways else ("#777" if foot else "#bbb")
        ax.plot([a[1], b[1]], [a[0], b[0]], color=col, lw=0.8 if foot else 1.6, zorder=3)
    for kind, (m, c) in STYLE.items():
        for src, face in (("osm", c), ("rule", "white")):
            sel = [q for q in pts if q["kind"] == kind and q["source"] == src]
            if sel:
                ax.scatter([q["y"] for q in sel], [q["x"] for q in sel], marker=m, s=ms, c=face, edgecolors=c if
                           src == "rule" else "k", linewidths=1.2, zorder=6, label=f"{kind} — {src} ({len(sel)})")
    t = np.linspace(0, 2 * np.pi, 200)
    ax.plot(ZONE_R_M * np.sin(t), ZONE_R_M * np.cos(t), color="#999", ls="--", lw=1, zorder=1)
    ax.plot(0, 0, "r+", ms=14, zorder=7)
    ax.set_xlim(center[1] - r, center[1] + r)
    ax.set_ylim(center[0] - r, center[0] + r)
    ax.set_aspect("equal")
    ax.set_xlabel("y, м (восток)")
    ax.set_ylabel("x, м (север)")
    ax.grid(alpha=0.25)
    ax.legend(loc="lower left", fontsize=9)
    ax.set_title("Малые формы у Крома: заливка — OSM, контур — правило (гипотеза)")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    world = World()
    pts, backrest = osm_points(world)
    stats = {}
    pts = rule_points(world, pts, stats)
    counts = {k: {"osm": 0, "rule": 0} for k in KINDS}
    for q in pts:
        counts[q["kind"]][q["source"]] += 1
    head = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "script": "scripts/furniture_points.py",
        "osm": [os.path.basename(geo.latest(p)) for p in ("krom_env_*.json", "krom_2*.json")],
        "zone_r_m": ZONE_R_M,
        "axes": "x — север, y — восток, м от центра Троицкого собора; z нет — трасса в редакторе",
        "yaw": "градусы, поворот +X модели к +Y (как yaw в UE); фонарь — скосом к дорожке, скамейка — сидящим "
               "от дорожки, урна — вдоль",
        "kinds": KINDS,
        "rules": [{"name": r.name, "kind": r.kind, "ways": list(r.ways), "step_m": r.step_m, "side": r.side,
                   "hypothesis": True, "note": r.note, **stats.get(r.name, {})} for r in RULES],
        "osm_lamp_step_m": osm_lamp_step(world, pts),
        "osm_benches_with_backrest": backrest,
        "counts": counts,
        "total": len(pts),
    }
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        text = json.dumps(head, ensure_ascii=False, indent=2)
        f.write(text[:-2] + ',\n  "points": [\n')
        f.write(",\n".join("    " + json.dumps(q, ensure_ascii=False) for q in pts))
        f.write("\n  ]\n}\n")
    preview(world, pts, OUT_PNG, (0.0, 0.0), ZONE_R_M + 20, 60, 30)
    preview(world, pts, OUT_PNG_KROM, (40.0, 0.0), 280.0, 70, 55)
    print(f"[furniture_points] шаг фонарей OSM у Псковы: {head['osm_lamp_step_m']} м (в правилах {LAMP_STEP_M})")
    for k, c in counts.items():
        print(f"[furniture_points] {k:12s} OSM {c['osm']:4d}  правило {c['rule']:4d}")
    for r in head["rules"]:
        print(f"[furniture_points] {r['name']:32s} +{r.get('placed', 0):3d} (урн {r.get('bins', 0)}), "
              f"отказы {r.get('rejected', {})}")
    print(f"[furniture_points] всего {len(pts)} → {OUT_JSON}")


if __name__ == "__main__":
    main()
