"""trees_points.py — точки посадки деревьев и кустов на Landscape L_Krom (M5): OSM + WorldCover → build/trees/points.json.

Не для редактора: запускается обычным Python из .venv (numpy, scipy, rasterio, pillow, matplotlib):

    .venv\\Scripts\\python scripts/trees_points.py

Z у точек нет: землю под каждой найдёт трасса в редакторе. Оси и метры — D-013: x — север, y — восток, начало — центр
Троицкого собора. Всё детерминированно (SEED, элементы OSM по id): те же данные — те же точки.

Данные: OSM — рощи и дороги из refs/osm/krom_2*.json, natural=tree, tree_row и живые изгороди из refs/osm/krom_env_*.json;
ESA WorldCover 2021 (класс 10 — деревья; кроп и привязка — как в horizon_mesh.py); рельеф и маски покрытия terrain_krom.py
(refs/dem); стены, башни и здания krom_plan.py. Доли крон WorldCover по зонам — разведка build/research_env.md, §5.2.

Правила:
  1. natural=tree → kind tree_osm ровно в точке OSM, «как есть»: исключения из п. 8 на них не действуют, нарушения —
     предупреждением в сводке. Высота — тег height, иначе 12–22 м (одно дерево Довмонтова города — 22 м, OSM_HEIGHT).
  2. natural=tree_row → kind row: по линии с шагом 6–8 м, 10–18 м. Точка в воде или ближе 2 м к урезу, ближе 4 м
     к стене или башне, в контуре здания — пропускается (дороги рядам не мешают: ряд и есть посадка вдоль дороги).
  3. barrier=hedge → kind shrub, species hedge: шаг ≈2 м (вдали — реже, п. 9), 1,2–2 м. Пропуск — как у рядов.
  4. Рощи → kind grove: полигоны natural=wood / landuse=forest и пиксели WorldCover «деревья». «Дротики» по перемешанным
     кандидатам (пуассоновский диск): кандидат принимается, если ближе r нет уже поставленного дерева; r = 5–7 м растёт
     с высотой (14–25 м), крона ≈ 0,4–0,75 высоты по виду (у клёна и липы 0,5–0,6: 7–15 м). В пикселях WorldCover полог
     почти смыкается, поэтому доля крон в зоне близка к доле WorldCover (сверка — в сводке).
  5. Двор Крома — OSM-деревья и редкие по WorldCover (r = 11 м, не ближе 12 м к собору и колокольне), 12–22 м.
     Довмонтов город — только OSM (одно большое дерево на газоне, фото aerial7, env16).
  6. Откос к Великой под западной стеной Крома (участки Плоская — Кутекрома — Довмонтова, VELIKAYA_BAND_M наружу,
     севернее x = −105): деревьев нет, кусты на уклоне — до ≈1 % площади (WorldCover и фото S-45: откос открытый).
  7. Кусты → kind shrub, 2–4 м, редко: по краю рощ (кольцо 3–5 м вокруг рощ) и на крутых берегах (уклон > 20°,
     до воды < 60 м) вне дворов Крома и Довмонтова города.
  8. Нельзя (для п. 2–7): вода (рельеф ниже уреза) и 2 м от уреза; мощение, асфальт, грунт, отсев, песок у уреза,
     наброска, настилы и здания по маскам покрытия (здания + 2 м, остальное + 1 м); тело стен (от внешней грани
     до двора; Кром и стена Окольного города по Великой из okolny_plan) и контуры башен и зданий krom_plan, линии
     city_wall OSM — + 4 м; дороги и тропы OSM — полуширина + 1 м (ширина троп у Крома — по фото, WAY_WIDTH).
     У стен крона не заходит за 0,5 м до стены: высота уменьшается вместе с кроной.
  9. Бюджет (6 ГБ VRAM, ориентир ≤ 5–8 тыс. точек): рощи и кусты ближе R_FULL_M к Крому и Довмонтову городу — полной
     густоты, дальше r растёт до ×EDGE_MULT к R_EDGE_M. Сколько точек было бы без прорежения — в сводке и в JSON.

species_hint — закрытый список SPECIES. Из OSM только spruce и conifer (hint_src "osm"); остальное — гипотеза по фото
(разведка §5.3, hint_src "guess"): у воды ива и тополь, во дворе Крома, в Довмонтовом городе, в рядах и у одиночных
деревьев — клён и липа, на Завеличье больше берёзы. Кусты — «shrub» (лещина, сирень, шиповник — гип.), изгороди — «hedge».

Выход (build/trees, не в git): points.json — заголовок (правила, словари, счётчики, сверка долей) и точки по одной
на строку; points.png — весь Landscape; points_krom.png — ±450 м у Крома с кронами в масштабе.
"""
import datetime
import json
import math
import os
import sys

import numpy as np
import rasterio
from PIL import Image
from rasterio import features
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import horizon_mesh  # noqa: E402
import krom_geo as geo  # noqa: E402
import krom_plan  # noqa: E402
import okolny_plan  # noqa: E402
import osm_layers  # noqa: E402
import terrain_krom as terrain  # noqa: E402

OUT_DIR = os.path.join(geo.REPO, "build", "trees")
OUT_JSON = os.path.join(OUT_DIR, "points.json")
OUT_PNG = os.path.join(OUT_DIR, "points.png")
OUT_PNG_KROM = os.path.join(OUT_DIR, "points_krom.png")
SEED = 20260926

HALF, N, MAP_T = terrain.HALF, terrain.N, terrain.MAP_T  # сетка 1 м, «север вверху»: строка r → x = HALF − r, столбец c → y = c − HALF
KROM_REL, DOVMONT_REL = 4060616, 4060635  # контуры OSM: Псковский кром, Довмонтов город

# ---------- исключения (п. 8) ----------
WATER_LAND_M = 0.1      # суша — рельеф выше уреза на столько (у кромки terrain_krom держит +0,2)
WATER_GAP_M = 2.0
SURFACE_MIN = 0.3       # доля класса в пикселе маски, с которой пиксель — не трава
SURFACE_GAP_M = 1.0
BUILT_GAP_M = 2.0
WALL_GAP_M = 4.0
ROAD_GAP_M = 1.0
CROWN_WALL_GAP_M = 0.5  # крона не ближе стольких метров к стене
CROWN_MIN_M = 3.0       # но у OSM-деревьев — не меньше этого
WAY_WIDTH = {66656356: 4.0, 66789566: 2.5}  # ширина троп по фото (S-42), если в osm_layers её ещё нет

# ---------- виды точек ----------
KINDS = {
    "tree_osm": "одиночное дерево OSM natural=tree — ровно в точке",
    "row": "дерево ряда OSM natural=tree_row",
    "grove": "дерево рощи: OSM natural=wood / landuse=forest или пиксель WorldCover «деревья»",
    "shrub": "куст: край рощи, крутой берег, откос к Великой; живая изгородь OSM (species hedge)",
}
HEIGHT = {"tree_osm": (12.0, 22.0), "row": (10.0, 18.0), "grove": (14.0, 25.0), "yard": (12.0, 22.0),
          "shrub": (2.0, 4.0), "hedge": (1.2, 2.0)}
OSM_HEIGHT = {9739978471: 22.0}  # Довмонтов город: «одно очень большое дерево на газоне» (фото aerial7, env16; гип.)
ROW_STEP_M = (6.0, 8.0)
HEDGE_STEP_M = (1.8, 2.4)
GROVE_R_M = (5.0, 7.0)  # минимальное расстояние в роще: у 14-метрового дерева — 5, у 25-метрового — 7
YARD_R_M = 11.0
CHURCH_GAP_M = 12.0     # от собора и колокольни
HERO_GAP_M = 10.0       # от храмов-героев за стенами (Пароменье, часовни, храмы генератора D-036): газон, как на фото
EDGE_RING_M = (3.0, 5.0)
EDGE_R_M = 15.0
SLOPE_DEG = 20.0
SLOPE_WATER_M = 60.0
SLOPE_R_M = 12.0
VELIKAYA_BAND_M = 70.0
VELIKAYA_X_MIN = -105.0  # южнее — набережная Довмонтова города: там ряд 1059312182, правило не действует
VELIKAYA_SHARE = 0.01
VELIKAYA_SLOPE_DEG = 12.0
VELIKAYA_R_M = 8.0
CANDIDATES_PER_M2 = 0.1

# ---------- бюджет (п. 9) ----------
R_FULL_M = 350.0
R_EDGE_M = 800.0
EDGE_MULT = 3.0

# ---------- породы ----------
SPECIES = {
    "maple": "клён остролистный (гип.)",
    "linden": "липа (гип.)",
    "birch": "берёза (гип.)",
    "willow": "ива (гип.)",
    "poplar": "тополь (гип.)",
    "spruce": "ель (OSM genus=Picea)",
    "conifer": "хвойное без уточнения (OSM leaf_type=needleleaved)",
    "shrub": "куст: лещина, сирень, шиповник (гип.)",
    "hedge": "живая изгородь, стриженая (OSM barrier=hedge)",
}
MIX = {  # доли пород по месту (гипотеза по фото, разведка §5.3)
    "water": {"willow": 0.7, "poplar": 0.2, "birch": 0.1},
    "town": {"maple": 0.5, "linden": 0.5},
    "zavelichye": {"birch": 0.35, "maple": 0.25, "linden": 0.2, "poplar": 0.2},
    "other": {"maple": 0.35, "linden": 0.3, "birch": 0.2, "poplar": 0.15},
}
WATER_SPECIES_M = 12.0  # ближе к воде — ивы и тополя
CROWN = {"maple": (0.5, 0.6), "linden": (0.5, 0.6), "birch": (0.45, 0.55), "willow": (0.6, 0.75), "poplar": (0.4, 0.5),
         "spruce": (0.3, 0.4), "conifer": (0.3, 0.4), "shrub": (0.8, 1.1), "hedge": (0.8, 1.0)}  # крона / высота

# зона точки (по приоритету) — пригодится редактору для LOD и пород
ZONES = ("krom_yard", "dovmont", "velikaya_slope", "krom_band", "zavelichye", "zapskovye", "city")
BAND_M = 60.0          # полоса вокруг Крома и Довмонтова города (как в разведке)
BAND_SPLIT_Y = -40.0   # к Великой — y < −40, к Пскове — y ≥ −40 (так посчитаны 1 % и 39 %)
BANK_M, BANK_BOX_M = 40.0, 500.0
PROBES = {"city": (0.0, 0.0), "zavelichye": (-213.0, -271.0), "zapskovye": (395.0, -169.0)}  # точки в компонентах суши
RESEARCH = {  # доли крон WorldCover из разведки, %
    "суша Landscape": 32, "двор Крома": 15, "Довмонтов город": 1, "полоса 60 м у Великой": 1,
    "полоса 60 м у Псковы": 39, "берега ±500 м, Завеличье": 63, "берега ±500 м, Запсковье": 68,
}
KIND_COLORS = {"tree_osm": "#8e24aa", "row": "#1565c0", "grove": "#1b5e20", "shrub": "#ef6c00"}


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def cell(x, y):
    """(x, y), м → (строка, столбец) сетки, прижатые к краю."""
    r = np.clip(np.rint(HALF - np.asarray(x)).astype(int), 0, N - 1)
    c = np.clip(np.rint(np.asarray(y) + HALF).astype(int), 0, N - 1)
    return r, c


def inside(x, y, margin=0.5):
    return abs(x) <= HALF - margin and abs(y) <= HALF - margin


def edt(mask):
    """Расстояние до ближайшей клетки mask, м (в самой mask — 0)."""
    return ndimage.distance_transform_edt(~mask)


def rasterize_polys(rings, all_touched=False):
    geoms = [{"type": "Polygon", "coordinates": [[(y, x) for x, y in r] + [(r[0][1], r[0][0])]]}
             for r in rings if len(r) > 2]
    if not geoms:
        return np.zeros((N, N), bool)
    return features.rasterize(geoms, out_shape=(N, N), transform=MAP_T, fill=0, default_value=1,
                              all_touched=all_touched).astype(bool)


def rasterize_lines(lines):
    geoms = [{"type": "LineString", "coordinates": [(y, x) for x, y in line]} for line in lines if len(line) > 1]
    if not geoms:
        return np.zeros((N, N), bool)
    return features.rasterize(geoms, out_shape=(N, N), transform=MAP_T, fill=0, default_value=1,
                              all_touched=True).astype(bool)


# ---------- данные ----------

def load_mask(path):
    """Маска покрытия terrain_krom (2048², строки — y, столбцы — x) → доли каналов на сетке узлов, север вверху."""
    ue = np.asarray(Image.open(path).convert("RGBA"))
    m = ue.transpose(1, 0, 2)[::-1]  # обратное к render_mask: строка → x сверху вниз, столбец → y
    s = 2 * HALF / m.shape[0]
    idx = np.clip(np.floor(np.arange(N) / s).astype(int), 0, m.shape[0] - 1)
    return m[idx[:, None], idx[None, :]].astype(np.float32) / 255.0


def load_terrain():
    with open(terrain.OUT_JSON, encoding="utf-8") as f:
        meta = json.load(f)
    hm = np.asarray(Image.open(terrain.OUT_PNG), dtype=np.float64)   # [y + HALF, x + HALF]
    z = ((hm - 32768) * terrain.Z_PER_UNIT_M).T[::-1, :]
    masks = [load_mask(terrain.OUT_MASK)]
    mask2 = meta.get("mask2_texture")
    if mask2 and os.path.exists(os.path.join(geo.REPO, mask2)):
        masks.append(load_mask(os.path.join(geo.REPO, mask2)))
    return meta, z, masks


def worldcover_trees():
    """Пиксели WorldCover «деревья» (класс 10) в узлах сетки — ближайший пиксель, привязка как в horizon_mesh."""
    if not os.path.exists(horizon_mesh.WC_CROP):
        raise FileNotFoundError(f"{horizon_mesh.WC_CROP}: запусти scripts/horizon_mesh.py")
    with rasterio.open(horizon_mesh.WC_CROP) as ds:
        wc = ds.read(1)
        t = ds.transform
    xs = HALF - np.arange(N, dtype=np.float64)
    ys = np.arange(N, dtype=np.float64) - HALF
    lat, _ = geo.to_latlon(xs, 0.0)
    _, lon = geo.to_latlon(0.0, ys)
    rows = np.floor((lat - t.f) / t.e).astype(int)
    cols = np.floor((lon - t.c) / t.a).astype(int)
    return wc[rows[:, None], cols[None, :]] == 10


def osm_data():
    """Элементы OSM, отсортированные по (тип, id): основная выгрузка и выгрузка узлов окружения."""
    key = lambda e: (e["type"], e["id"])  # noqa: E731
    main = sorted(geo.load_elements(geo.latest("krom_2*.json")), key=key)
    env = sorted(geo.load_elements(geo.latest("krom_env_*.json")), key=key)
    return main, env


def rings_of(el):
    """Кольца замкнутой линии или внешние кольца мультиполигона (полная геометрия) в локальных метрах."""
    if el["type"] == "way":
        return [geo.open_ring(geo.local_points(el["geometry"]))] if osm_layers.is_closed(el) else []
    outers = [m for m in el.get("members", []) if m["role"] == "outer" and m.get("geometry")
              and None not in m["geometry"]]
    ways = [([(p["lat"], p["lon"]) for p in m["geometry"]], geo.local_points(m["geometry"])) for m in outers]
    return geo.assemble_rings(ways)


def line_pieces(el, rect):
    pts = geo.local_points(el["geometry"])
    return [c for part in geo.split_on_none(pts) for c in geo.clip_line_to_rect(part, *rect)]


# ---------- растры правил ----------

def roads_mask(main):
    """Дороги и тропы OSM: полуширина + ROAD_GAP_M (площадки highway area=yes — целиком)."""
    widths = {**WAY_WIDTH, **getattr(osm_layers, "WAY_WIDTH", {})}
    rect = (-HALF - 20, HALF + 20, -HALF - 20, HALF + 20)
    groups, areas = {}, []
    for el in main:
        tags = el.get("tags", {})
        hw = tags.get("highway")
        if el["type"] != "way" or not hw or tags.get("tunnel") == "yes":
            continue
        if tags.get("area") == "yes" and osm_layers.is_closed(el):
            areas += rings_of(el)
            continue
        w0 = osm_layers.ROAD_WIDTH.get(hw) or osm_layers.PATH_WIDTH.get(hw)
        if not w0:
            continue
        w = widths.get(el["id"]) or osm_layers.width_of(tags, w0)
        buf = math.ceil((w / 2 + ROAD_GAP_M) * 2) / 2
        groups.setdefault(buf, []).extend(line_pieces(el, rect))
    out = rasterize_polys(areas)
    for buf, lines in sorted(groups.items()):
        out |= edt(rasterize_lines(lines)) <= buf
    return out


def structures(main):
    """Тела стен (от внешней грани до двора; Кром и стена Окольного города по Великой — okolny_plan), контуры башен
    и зданий krom_plan, линии city_wall OSM. Возвращает (расстояние до них, расстояние до собора и колокольни, участки
    стен)."""
    runs = krom_plan.wall_runs() + okolny_plan.wall_runs()
    quads = []
    for r in runs:
        for (ax, ay), (bx, by) in zip(r.points, r.points[1:]):
            L = math.hypot(bx - ax, by - ay)
            if L < 1e-9:
                continue
            mx, my = -(by - ay) / L * r.yard, (bx - ax) / L * r.yard
            t = r.profile.t
            quads.append([(ax, ay), (bx, by), (bx + mx * t, by + my * t), (ax + mx * t, ay + my * t)])
    feet = [list(b.footprint) for b in krom_plan.towers() + krom_plan.buildings()]
    rect = (-HALF - 20, HALF + 20, -HALF - 20, HALF + 20)
    city_walls = [p for el in main if el["type"] == "way" and el.get("tags", {}).get("barrier") == "city_wall"
                  for p in line_pieces(el, rect)]
    body = rasterize_polys(quads + feet, all_touched=True) | rasterize_lines(city_walls)
    church = rasterize_polys([list(krom_plan.cathedral().footprint), list(krom_plan.belfry().footprint)],
                             all_touched=True)
    heroes = [list(b.footprint) for b in krom_plan.buildings()
              if b.hero and b.group in ("Zavelichye", "Churches") and b.footprint]
    d_hero = edt(rasterize_polys(heroes, all_touched=True)) if heroes else np.full((N, N), 1e9)
    return edt(body), edt(church), runs, city_walls, d_hero


def woods_mask(main):
    rings = [r for el in main
             if el.get("tags", {}).get("natural") == "wood" or el.get("tags", {}).get("landuse") == "forest"
             for r in rings_of(el)]
    return rasterize_polys(rings)


def velikaya_slope(runs, krom):
    """Откос к Великой под западной стеной Крома: снаружи участков Плоская — Кутекрома — Довмонтова, до VELIKAYA_BAND_M."""
    near = {"Плоская", "Кутекрома", "Довмонтова"}
    segs = [(a, b, r.yard) for r in runs if r.wall == "Западная" and {r.a, r.b} <= near
            for a, b in zip(r.points, r.points[1:]) if math.dist(a, b) > 1e-9]
    xs = [p[0] for a, b, _ in segs for p in (a, b)]
    ys = [p[1] for a, b, _ in segs for p in (a, b)]
    m = VELIKAYA_BAND_M + 2
    r0, c0 = cell(max(xs) + m, min(ys) - m)
    r1, c1 = cell(min(xs) - m, max(ys) + m)
    X = (HALF - np.arange(r0, r1 + 1, dtype=np.float64))[:, None]
    Y = (np.arange(c0, c1 + 1, dtype=np.float64) - HALF)[None, :]
    best = np.full((r1 - r0 + 1, c1 - c0 + 1), np.inf)
    outer = np.zeros_like(best, bool)
    for (ax, ay), (bx, by), yard in segs:
        ex, ey = bx - ax, by - ay
        t = np.clip(((X - ax) * ex + (Y - ay) * ey) / (ex * ex + ey * ey), 0.0, 1.0)
        d = np.hypot(X - ax - t * ex, Y - ay - t * ey)
        side = (ex * (Y - ay) - ey * (X - ax)) * yard < 0   # не со стороны двора
        closer = d < best
        best = np.where(closer, d, best)
        outer = np.where(closer, side, outer)
    zone = np.zeros((N, N), bool)
    zone[r0:r1 + 1, c0:c1 + 1] = (best <= VELIKAYA_BAND_M) & outer & (X > VELIKAYA_X_MIN)
    return zone & ~krom


def build_grids():
    meta, z, masks = load_terrain()
    main, env = osm_data()
    g = {"meta": meta, "main": main, "env": env, "z": z}
    wl = meta["water_level_z_m"]
    land = z >= wl + WATER_LAND_M
    g["land"] = land
    g["d_water"] = edt(~land)
    gy, gx = np.gradient(z)
    g["slope"] = np.degrees(np.arctan(np.hypot(gx, gy)))
    built = masks[0][..., 3] >= SURFACE_MIN
    other = np.zeros((N, N), bool)
    for k, m in enumerate(masks):
        for ch in range(4):
            if not (k == 0 and ch == 3):
                other |= m[..., ch] >= SURFACE_MIN
    g["built"] = built
    g["surface"] = (edt(built) <= BUILT_GAP_M) | (edt(other) <= SURFACE_GAP_M)
    g["roads"] = roads_mask(main)
    g["d_struct"], g["d_church"], g["runs"], g["city_walls"], g["d_hero"] = structures(main)
    g["wc"] = worldcover_trees()
    g["wood"] = woods_mask(main)
    g["allowed"] = (land & (g["d_water"] >= WATER_GAP_M) & ~g["surface"] & ~g["roads"] & (g["d_struct"] > WALL_GAP_M)
                    & (g["d_hero"] >= HERO_GAP_M))

    # зоны
    krom = rasterize_polys([osm_layers.relation_ring(KROM_REL)])
    dov = rasterize_polys([osm_layers.relation_ring(DOVMONT_REL)])
    d_ring = edt(krom | dov)
    X = (HALF - np.arange(N, dtype=np.float64))[:, None] * np.ones((1, N))
    Y = (np.arange(N, dtype=np.float64) - HALF)[None, :] * np.ones((N, 1))
    band = (d_ring > 0) & (d_ring <= BAND_M)
    lab, _ = ndimage.label(land)
    comp = {k: lab[cell(*p)] for k, p in PROBES.items()}
    zav, zap = lab == comp["zavelichye"], lab == comp["zapskovye"]
    bank = (g["d_water"] <= BANK_M) & (abs(X) <= BANK_BOX_M) & (abs(Y) <= BANK_BOX_M)
    vel = velikaya_slope(g["runs"], krom) & land
    zone = np.full((N, N), ZONES.index("city"), np.int8)
    for name, m in (("zapskovye", zap), ("zavelichye", zav), ("krom_band", band), ("velikaya_slope", vel),
                    ("dovmont", dov), ("krom_yard", krom)):
        zone[m] = ZONES.index(name)
    g["zone"] = zone
    g["d_krom"] = d_ring
    g["mult"] = 1 + (EDGE_MULT - 1) * smoothstep((d_ring - R_FULL_M) / (R_EDGE_M - R_FULL_M))
    g["summary_zones"] = [
        ("суша Landscape", land),
        ("двор Крома", krom & land),
        ("Довмонтов город", dov & land),
        ("полоса 60 м у Великой", band & (Y < BAND_SPLIT_Y) & land),
        ("полоса 60 м у Псковы", band & (Y >= BAND_SPLIT_Y) & land),
        ("откос к Великой (правило 6)", vel),
        ("берега ±500 м, Завеличье", bank & zav),
        ("берега ±500 м, Запсковье", bank & zap),
        ("Завеличье, вся суша", zav),
        ("Запсковье, вся суша", zap),
        ("остальное", land & ~krom & ~dov & ~band & ~bank),
        (f"дальше {R_FULL_M:.0f} м от Крома", land & (d_ring > R_FULL_M)),
    ]
    return g


# ---------- расстановка ----------

class Grid:
    """Пространственный хэш поставленных точек: проверка «нет соседа ближе r»."""

    def __init__(self, size=4.0):
        self.size = size
        self.cells = {}

    def add(self, x, y):
        self.cells.setdefault((int(x // self.size), int(y // self.size)), []).append((x, y))

    def free(self, x, y, r):
        s, r2 = self.size, r * r
        for i in range(int((x - r) // s), int((x + r) // s) + 1):
            for j in range(int((y - r) // s), int((y + r) // s) + 1):
                for px, py in self.cells.get((i, j), ()):
                    if (px - x) ** 2 + (py - y) ** 2 < r2:
                        return False
        return True


def pick_species(rng, mix):
    names = list(MIX[mix])
    return names[rng.choice(len(names), p=[MIX[mix][n] for n in names])]


def crown_of(rng, species, h):
    lo, hi = CROWN[species]
    return h * rng.uniform(lo, hi)


def limit_crown(g, x, y, h, crown, floor=0.0):
    """Крона не ближе CROWN_WALL_GAP_M к стенам и башням; высота — в той же пропорции."""
    lim = max(floor, 2 * (g["d_struct"][cell(x, y)] - CROWN_WALL_GAP_M))
    if crown > lim:
        k = lim / crown
        return h * k, crown * k
    return h, crown


def point(x, y, kind, h, crown, species, hint_src, source, g, rng, osm_id=None):
    p = {"x": round(float(x), 1), "y": round(float(y), 1), "kind": kind, "height_m": round(float(h), 1),
         "crown_m": round(float(crown), 1), "yaw_deg": int(rng.integers(0, 360)), "species_hint": species,
         "hint_src": hint_src, "source": source, "zone": ZONES[g["zone"][cell(x, y)]]}
    if osm_id is not None:
        p["osm_id"] = osm_id
    return p


def mix_for(g, x, y, town=False):
    rc = cell(x, y)
    if g["d_water"][rc] <= WATER_SPECIES_M and not town:
        return "water"
    if town:
        return "town"
    return "zavelichye" if ZONES[g["zone"][rc]] == "zavelichye" else "other"


def osm_trees(g, rng, trees, warn):
    for el in g["env"]:
        tags = el.get("tags", {})
        if el["type"] != "node" or tags.get("natural") != "tree":
            continue
        x, y = geo.to_local(el["lat"], el["lon"])
        if not inside(x, y):
            continue
        if tags.get("genus") == "Picea":
            species, src = "spruce", "osm"
        elif tags.get("leaf_type") == "needleleaved":
            species, src = "conifer", "osm"
        else:
            species, src = pick_species(rng, mix_for(g, x, y, town=g["d_water"][cell(x, y)] > WATER_SPECIES_M)), "guess"
        try:
            h = float(tags["height"])
        except (KeyError, ValueError):
            h = OSM_HEIGHT.get(el["id"]) or rng.uniform(*HEIGHT["tree_osm"])
        h, crown = limit_crown(g, x, y, h, crown_of(rng, species, h), floor=CROWN_MIN_M)
        rc = cell(x, y)
        why = [w for bad, w in ((not g["land"][rc], "в воде"), (g["d_struct"][rc] <= 1.0, "в стене или башне"),
                                (g["built"][rc], "в контуре здания"),
                                (g["roads"][rc], "у дороги или тропы (ближе полуширины + 1 м)"),
                                (g["surface"][rc] and not g["built"][rc], "на мощении или площадке или ближе 1 м"))
               if bad]
        if why:
            warn.append(f"tree_osm {el['id']} ({x:.1f}, {y:.1f}): {'; '.join(why)} — оставлено как есть")
        trees.append(point(x, y, "tree_osm", h, crown, species, src, "osm_tree", g, rng, el["id"]))


def hard_blocked(g, x, y):
    rc = cell(x, y)
    return not g["land"][rc] or g["d_water"][rc] < WATER_GAP_M or g["d_struct"][rc] <= WALL_GAP_M or g["built"][rc]


def along(line, step, rng):
    """Точки по ломаной: первая — на случайном полушаге от начала, дальше шаг — случайный из диапазона step."""
    out, s = [], rng.uniform(0.2, 0.6) * step[0]
    for (ax, ay), (bx, by) in zip(line, line[1:]):
        L = math.hypot(bx - ax, by - ay)
        while s <= L:
            out.append((ax + (bx - ax) * s / L, ay + (by - ay) * s / L))
            s += rng.uniform(*step)
        s -= L
    return out


def osm_lines(g, rng, trees, shrubs, warn):
    rect = (-HALF + 0.5, HALF - 0.5, -HALF + 0.5, HALF - 0.5)
    for el in g["env"]:
        tags = el.get("tags", {})
        if el["type"] != "way":
            continue
        row, hedge = tags.get("natural") == "tree_row", tags.get("barrier") == "hedge"
        if not (row or hedge):
            continue
        skipped = 0
        for piece in line_pieces(el, rect):
            for x, y in along(piece, ROW_STEP_M if row else HEDGE_STEP_M, rng):
                if hard_blocked(g, x, y):
                    skipped += 1
                    continue
                if row:
                    species = "conifer" if tags.get("leaf_type") == "needleleaved" else pick_species(rng, "town")
                    h = rng.uniform(*HEIGHT["row"])
                    h, crown = limit_crown(g, x, y, h, crown_of(rng, species, h))
                    trees.append(point(x, y, "row", h, crown, species, "osm" if species == "conifer" else "guess",
                                       "osm_tree_row", g, rng, el["id"]))
                elif rng.random() < 1 / g["mult"][cell(x, y)]:   # вдали изгородь редеет, как рощи (п. 9)
                    h = rng.uniform(*HEIGHT["hedge"])
                    shrubs.append(point(x, y, "shrub", h, crown_of(rng, "hedge", h), "hedge", "osm", "osm_hedge",
                                        g, rng, el["id"]))
        if skipped and row:
            warn.append(f"row {el['id']}: пропущено {skipped} точек (вода, стена, здание)")


def candidates(domain, rng, density=CANDIDATES_PER_M2):
    """Случайные точки в клетках domain (≈density на м²) в случайном порядке."""
    r, c = np.nonzero(domain)
    keep = rng.random(len(r)) < density
    r, c = r[keep], c[keep]
    x = HALF - r + rng.uniform(-0.5, 0.5, len(r))
    y = c - HALF + rng.uniform(-0.5, 0.5, len(r))
    order = rng.permutation(len(x))
    return x[order], y[order]


def darts(xs, ys, radii, grid, limit=None):
    """Индексы принятых кандидатов: ближе radius нет ни одной точки grid (grid пополняется)."""
    out = []
    for i, (x, y, r) in enumerate(zip(xs, ys, radii)):
        if grid.free(x, y, r):
            grid.add(x, y)
            out.append(i)
            if limit is not None and len(out) >= limit:
                break
    return out


def seeded(points):
    grid = Grid()
    for p in points:
        grid.add(p["x"], p["y"])
    return grid


def zone_is(g, *names):
    return np.isin(g["zone"], [ZONES.index(n) for n in names])


def fill(g, rng, fixed_trees, fixed_all, thin=True):
    """Двор Крома, рощи, кусты. thin=False — без прорежения (только для счёта). Возвращает (деревья, кусты)."""
    mult = g["mult"] if thin else np.ones((N, N))
    trees, shrubs = [], []
    tgrid = seeded(fixed_trees)

    # двор Крома: редкие по WorldCover
    dom = g["allowed"] & g["wc"] & zone_is(g, "krom_yard") & (g["d_church"] >= CHURCH_GAP_M)
    xs, ys = candidates(dom, rng)
    for i in darts(xs, ys, np.full(len(xs), YARD_R_M), tgrid):
        x, y = xs[i], ys[i]
        species = pick_species(rng, "town")
        h = rng.uniform(*HEIGHT["yard"])
        h, crown = limit_crown(g, x, y, h, crown_of(rng, species, h))
        trees.append(point(x, y, "grove", h, crown, species, "guess", "worldcover", g, rng))

    # рощи
    dom = g["allowed"] & (g["wc"] | g["wood"]) & ~zone_is(g, "krom_yard", "dovmont", "velikaya_slope")
    xs, ys = candidates(dom, rng)
    hs = rng.uniform(*HEIGHT["grove"], len(xs))
    lo, hi = HEIGHT["grove"]
    radii = (GROVE_R_M[0] + (GROVE_R_M[1] - GROVE_R_M[0]) * (hs - lo) / (hi - lo)) * mult[cell(xs, ys)]
    for i in darts(xs, ys, radii, tgrid):
        x, y = xs[i], ys[i]
        species = pick_species(rng, mix_for(g, x, y))
        h, crown = limit_crown(g, x, y, hs[i], crown_of(rng, species, hs[i]))
        source = "osm_wood" if g["wood"][cell(x, y)] else "worldcover"
        trees.append(point(x, y, "grove", h, crown, species, "guess", source, g, rng))

    agrid = seeded(fixed_all + trees)

    def shrub_pass(dom, r, source, limit=None, m=True):
        xs, ys = candidates(dom, rng)
        radii = r * (mult[cell(xs, ys)] if m else np.ones(len(xs)))
        for i in darts(xs, ys, radii, agrid, limit):
            h = rng.uniform(*HEIGHT["shrub"])
            h, crown = limit_crown(g, xs[i], ys[i], h, crown_of(rng, "shrub", h))
            shrubs.append(point(xs[i], ys[i], "shrub", h, crown, "shrub", "guess", source, g, rng))

    free_zone = ~zone_is(g, "krom_yard", "dovmont", "velikaya_slope")
    # откос к Великой: до ≈1 % площади — кусты на уклоне
    vel = zone_is(g, "velikaya_slope")
    area = float((vel & g["land"]).sum())
    mean_crown = np.mean(HEIGHT["shrub"]) * np.mean(CROWN["shrub"])
    n_vel = int(round(VELIKAYA_SHARE * area / (math.pi * mean_crown ** 2 / 4)))
    shrub_pass(g["allowed"] & vel & (g["slope"] >= VELIKAYA_SLOPE_DEG), VELIKAYA_R_M, "rule_velikaya", n_vel, m=False)
    # край рощ
    d_grove = edt(g["wc"] | g["wood"])
    ring = (d_grove >= EDGE_RING_M[0]) & (d_grove <= EDGE_RING_M[1])
    shrub_pass(g["allowed"] & ring & free_zone, EDGE_R_M, "rule_edge")
    # крутые берега
    steep = (g["slope"] > SLOPE_DEG) & (g["d_water"] < SLOPE_WATER_M) & ~(g["wc"] | g["wood"])
    shrub_pass(g["allowed"] & steep & free_zone, SLOPE_R_M, "rule_slope")
    return trees, shrubs


# ---------- сверка ----------

def crown_cover(points):
    """Проекция крон (круги crown_m) на сетку 1 м."""
    cov = np.zeros((N, N), bool)
    by_r = {}
    for p in points:
        by_r.setdefault(round(p["crown_m"] / 2 * 2) / 2, []).append(p)   # радиус с шагом 0,5 м
    for r, ps in by_r.items():
        m = np.zeros((N, N), bool)
        m[cell([p["x"] for p in ps], [p["y"] for p in ps])] = True
        cov |= edt(m) <= r
    return cov


def coverage_table(g, pts, pts_full):
    trees = [p for p in pts if p["kind"] != "shrub"]
    cov = crown_cover(trees)
    cov_full = crown_cover([p for p in pts_full if p["kind"] != "shrub"])
    rows = []
    for name, m in g["summary_zones"]:
        area = int(m.sum())
        if not area:
            continue
        ref = next((v for k, v in RESEARCH.items() if name.startswith(k)), None)
        n = sum(1 for p in trees if m[cell(p["x"], p["y"])])
        rows.append({"zone": name, "land_m2": area, "worldcover_pct": round(float(g["wc"][m].mean()) * 100, 1),
                     "research_pct": ref, "crowns_pct": round(float(cov[m].mean()) * 100, 1),
                     "crowns_full_pct": round(float(cov_full[m].mean()) * 100, 1), "trees": n})
    return rows


def count(points, key="kind"):
    out = {}
    for p in points:
        out[p[key]] = out.get(p[key], 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


# ---------- превью ----------

def previews(g, pts):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import EllipseCollection

    bg = np.asarray(Image.open(terrain.OUT_MAP).convert("RGB")).transpose(1, 0, 2)[::-1]   # север вверху
    ext = (-HALF, HALF, -HALF, HALF)
    wc = np.ma.masked_where(~g["wc"], np.ones((N, N)))
    vel = np.ma.masked_where(~zone_is(g, "velikaya_slope"), np.ones((N, N)))
    for path, (cx, cy, lim), crowns in ((OUT_PNG, (0.0, 0.0, HALF), False), (OUT_PNG_KROM, (40.0, -40.0, 450.0), True)):
        fig, ax = plt.subplots(figsize=(15, 15), dpi=110)
        ax.imshow(bg, extent=ext, origin="upper", alpha=0.55, interpolation="bilinear")
        ax.imshow(wc, extent=(-HALF - 0.5, HALF + 0.5, -HALF - 0.5, HALF + 0.5), origin="upper", cmap="Greens",
                  vmin=0, vmax=3, alpha=0.35, interpolation="nearest")
        ax.imshow(vel, extent=(-HALF - 0.5, HALF + 0.5, -HALF - 0.5, HALF + 0.5), origin="upper", cmap="Oranges",
                  vmin=0, vmax=4, alpha=0.3, interpolation="nearest")
        ax.contour(np.arange(N) - HALF, HALF - np.arange(N), g["d_krom"], levels=[R_FULL_M], colors="k",
                   linewidths=0.8, linestyles="--")
        for line in g["city_walls"]:
            ax.plot([p[1] for p in line], [p[0] for p in line], color="red", lw=1.0 if not crowns else 0.8)
        for r in g["runs"]:
            ax.plot([p[1] for p in r.points], [p[0] for p in r.points], color="red", lw=1.8 if crowns else 1.0)
        for kind, color in KIND_COLORS.items():
            ps = [p for p in pts if p["kind"] == kind]
            if not ps:
                continue
            y = np.array([p["y"] for p in ps])
            x = np.array([p["x"] for p in ps])
            if crowns:
                d = np.array([p["crown_m"] for p in ps])
                ax.add_collection(EllipseCollection(d, d, 0, units="xy", offsets=np.column_stack([y, x]),
                                                    offset_transform=ax.transData, facecolors=color, alpha=0.45,
                                                    edgecolors=color, linewidths=0.3))
                ax.plot(y, x, ".", color=color, ms=1.5)
            else:
                ax.plot(y, x, ".", color=color, ms=3.0 if kind != "grove" else 2.0, label=f"{kind}: {len(ps)}")
        if crowns:
            for kind, color in KIND_COLORS.items():
                ax.plot([], [], "o", color=color, label=f"{kind}: {sum(1 for p in pts if p['kind'] == kind)}")
        ax.plot(0, 0, "k+", ms=12)
        ax.set_xlim(cy - lim, cy + lim)
        ax.set_ylim(cx - lim, cx + lim)
        ax.set_aspect("equal")
        ax.set_xlabel("Y, м (восток)")
        ax.set_ylabel("X, м (север)")
        ax.legend(loc="upper right", fontsize=10)
        ax.set_title(f"trees_points: {len(pts)} точек; зелёная заливка — WorldCover «деревья», оранжевая — откос к "
                     f"Великой (правило 6), пунктир — {R_FULL_M:.0f} м от Крома (дальше прорежено)")
        fig.tight_layout()
        fig.savefig(path)
        plt.close(fig)


# ---------- main ----------

def main():
    rng_seed = np.random.SeedSequence(SEED)
    g = build_grids()
    warn = []
    rng = np.random.default_rng(rng_seed.spawn(1)[0])
    trees_fixed, shrubs_fixed = [], []
    osm_trees(g, rng, trees_fixed, warn)
    osm_lines(g, rng, trees_fixed, shrubs_fixed, warn)
    # одна и та же последовательность кандидатов — с прорежением и без (для счёта)
    fill_seed = rng_seed.spawn(2)[1]
    trees, shrubs = fill(g, np.random.default_rng(fill_seed), trees_fixed, trees_fixed + shrubs_fixed, thin=True)
    trees_full, shrubs_full = fill(g, np.random.default_rng(fill_seed), trees_fixed, trees_fixed + shrubs_fixed,
                                   thin=False)
    pts = trees_fixed + trees + shrubs_fixed + shrubs
    pts_full = trees_fixed + trees_full + shrubs_fixed + shrubs_full
    table = coverage_table(g, pts, pts_full)

    os.makedirs(OUT_DIR, exist_ok=True)
    species = count(pts, "species_hint")
    head = {
        "generated": datetime.date.today().isoformat(),
        "script": "scripts/trees_points.py",
        "seed": SEED,
        "axes": "x — север, y — восток, метры; начало — центр Троицкого собора (D-013). Z нет: землю ищет трасса "
                "в редакторе",
        "landscape_half_m": HALF,
        "rules": "докстринг scripts/trees_points.py",
        "fields": {"x, y": "м, 0,1", "kind": "см. kinds", "height_m": "высота дерева или куста", "crown_m":
                   "диаметр кроны", "yaw_deg": "поворот вокруг Z", "species_hint": "см. species", "hint_src":
                   "osm — из тегов OSM, guess — гипотеза по фото", "source": "osm_tree | osm_tree_row | osm_hedge | "
                   "osm_wood | worldcover | rule_edge | rule_slope | rule_velikaya", "zone": "см. zones",
                   "osm_id": "id узла или линии OSM, если есть"},
        "kinds": KINDS,
        "species": {k: {"note": v, "points": species.get(k, 0)} for k, v in SPECIES.items()},
        "zones": list(ZONES),
        "counts": count(pts),
        "counts_by_source": count(pts, "source"),
        "counts_full_density": count(pts_full),
        "total": len(pts),
        "total_full_density": len(pts_full),
        "budget": {"full_within_m": R_FULL_M, "edge_mult": EDGE_MULT, "edge_at_m": R_EDGE_M},
        "coverage": table,
        "warnings": warn,
        "sources": ["OpenStreetMap © участники OSM, ODbL (refs/osm)",
                    "ESA WorldCover 10 m 2021 v200 (© ESA WorldCover project 2021 / Contains modified Copernicus "
                    "Sentinel data (2021) processed by ESA WorldCover consortium), CC BY 4.0"],
    }
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        text = json.dumps(head, ensure_ascii=False, indent=2)
        f.write(text[:-2] + ',\n  "points": [\n')
        f.write(",\n".join("    " + json.dumps(p, ensure_ascii=False) for p in pts))
        f.write("\n  ]\n}\n")
    previews(g, pts)

    print(f"точек: {len(pts)} (без прорежения было бы {len(pts_full)})")
    print("по kind:", head["counts"], "  без прорежения:", head["counts_full_density"])
    print("по source:", head["counts_by_source"])
    print("species_hint:", species)
    print(f"{'зона':34} {'суша, м²':>10} {'WC %':>6} {'разв.':>6} {'кроны %':>8} {'без прор.':>9} {'деревьев':>9}")
    for r in table:
        ref = "" if r["research_pct"] is None else r["research_pct"]
        print(f"{r['zone']:34} {r['land_m2']:>10} {r['worldcover_pct']:>6} {ref:>6} {r['crowns_pct']:>8} "
              f"{r['crowns_full_pct']:>9} {r['trees']:>9}")
    for w in warn:
        print("!", w)
    print(OUT_JSON)


if __name__ == "__main__":
    main()
