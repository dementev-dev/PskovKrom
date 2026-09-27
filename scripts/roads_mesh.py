"""roads_mesh.py — дороги, тротуары, дорожки и лестницы вокруг Крома из OSM: оси с высотами, ширины, бордюры,
перекрёстки, «зебры» и разметка → элементы и меши клеток для roads_krom.py (D-038; разбор — build/research_roads.md).

Не для редактора: обычный Python из локального окружения (numpy, scipy, pillow):

    .venv\\Scripts\\python scripts/roads_mesh.py     → build/roads/roads.json + roads_top.png, roads_top_krom.png

Запускать после terrain_krom.py: тот сам вызывает corridors() и подгоняет рельеф под ленты (terrain_krom.road_bed).
  - Виды (kind): carriageway — проезжая часть (CAR; без bridge=yes — мосты строит bridge_krom, без тоннелей
    и area=yes); sidewalk — тротуар: footway=sidewalk, тротуар из тегов sidewalk=* дороги (generated) или footway
    вдоль проезжей части (inferred, гип.); footpath — дорожка вровень с землёй; trail — грунтовая тропа (mesh = false,
    остаётся в маске); steps — лестница; crossing — «зебра» по footway=crossing; junction — площадка перекрёстка;
    area — стоянки и площадки (mesh = false, пока в маске).
  - Ширина и покрытие — osm_layers.way_width, way_surface, split_surface: одни с маской покрытия (D-038); правки по фото —
    osm_layers.WAY_WIDTH, WAY_OVERRIDE, двор Крома — YARD_SURFACE. Материал (material) — по покрытию (MATERIAL).
    Площадь у собора (osm_layers.cathedral_square, булыжник) — в маске: дорожки по ней обрезаются.
    Площади OSM (osm_layers.squares: площадь Ленина, плитка с дырами газонов; Октябрьская площадь — замкнутые линии
    SQUARE_WAYS) — тоже в маске (area): ленты дорожек (footpath) по мощению не строятся, но
    в коридорах рельефа остаются (heightmap прежний). Асфальт Октябрьской площади по аэрофото (osm_layers.TRACED_AREAS)
    — только в маске (площадка без лент).
  - Высоты — сэмплер z_at: по умолчанию heightmap Landscape (refs/dem/heightmap_L_Krom.png; размер, Location, Scale —
    из его .json при запуске), билинейно по станциям не реже STEP_M, сглажены вдоль оси (SMOOTH_M), концы — точно
    по рельефу в узле: линии с общим узлом сходятся на одной высоте. Рельеф под лентой ниже её на ROAD_SINK_M /
    PATH_SINK_M (terrain_krom.road_bed), поэтому с готового heightmap лента берёт «рельеф + осадка»; terrain_krom
    вызывает corridors() со своим рельефом до подгонки, и профиль выходит тот же.
  - Перекрёстки — по общим узлам OSM: проезжая часть режется в узле, где сходятся 3+ конца, концы отступают на
    полуширину соседей + CORNER_M, площадка — выпуклая оболочка концов (веер из узла); рёбра оболочки между разными
    дорогами — бордюр угла. В узле из двух концов края лент сходятся по биссектрисе.
  - Бордюр — правилом (в OSM его почти нет): KERB_M по виду дороги, у дорожек — поребрик EDGING_M по материалу.
  - Разметка — только на главных улицах с lanes (MARKED, владелец, D-038), слегка стёртая (MARKING_WEAR); её рисует
    материал по UV1 (u — доля ширины от правого края, v — метры вдоль) и цвету вершин (R — полос / 8, G — полос по ходу
    / 8, B — осевая: 1 — двойная сплошная, 0,5 — прерывистая, 0 — без разметки; A — ширина / 32 м).
  - Лестница — число ступеней по перепаду рельефа на концах (RISE_M); где рельеф перепада не видит — dem_flat,
    геометрией пока не строится.
Меши (cells) — по всей зоне (MESH_SCOPE; в фазе 2 — только набор «дорожки у Крома», флаг set: двор, Стрелка, дорога
к Великим воротам, набережные Великой и Псковы, тропа под западной стеной и касающиеся их проезжие части). Клетки
CELL_M × CELL_M по середине элемента, как у city_mesh; слоты — материалы; UV0 — мировые X, Y в метрах (материалы
roads_krom кладут текстуру по мировой позиции). С готового heightmap высоты лент берутся как есть + осадка (рельеф
уже подогнан под профиль), и лента поднимается там, где рельеф между станциями выше неё (clear).
Геометрия — по всему Landscape (квадрат ±ZONE_M; до 2026-09-27 — круг 650 м, D-038): зона — in_zone, для рельефа —
zone_weight (terrain_krom.road_bed; у кромки Landscape гаснет). Учёт (inventory) — по всему Landscape и по зоне. Сторона: l — слева по ходу линии OSM; при X — север, Y — восток левая нормаль к направлению
(tx, ty) — (ty, −tx). Идемпотентен: build/roads/ перезаписывается целиком.
"""
import datetime
import json
import math
import os
import shutil
import sys
from collections import Counter, defaultdict

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402
import osm_layers  # noqa: E402

OUT_DIR = os.path.join(geo.REPO, "build", "roads")
OUT_JSON = os.path.join(OUT_DIR, "roads.json")
HM_META = os.path.join(geo.REPO, "refs", "dem", "heightmap_L_Krom.json")

ZONE_M = 1000.0        # геометрия — по всему Landscape: квадрат ±ZONE_M по осям (край — terrain_krom.HALF = 1008 м, за
                       # ним кольцо горизонта без дорог; выгрузка OSM кончается за 50–130 м до края). До 2026-09-27 —
                       # круг 650 м (D-038, фаза 3); владелец: «ограничение в 650 метров искусственное»
MARGIN_M = 80.0        # линии берём с запасом за зоной, чтобы перекрёстки у края считались целиком
CELL_M = 250.0
STEP_M = 2.0           # станции вдоль оси не реже
SMOOTH_M = {"carriageway": 6.0, "sidewalk": 3.0, "footpath": 3.0, "trail": 3.0, "crossing": 3.0}  # σ по длине, м
CORNER_M = 1.5         # отступ конца дороги от края соседней в перекрёстке (скругление угла — фаской оболочки)
RASTER_M = 0.5         # шаг растра расстояний до проезжей части
ROAD_SINK_M, PATH_SINK_M = 0.06, 0.04  # рельеф под проезжей частью / дорожкой ниже ленты (D-038): Landscape в LOD
                                       # огрубляет сетку и на кривизне может подняться над лентой — запас
# у мостов (bridge_krom.BRIDGES: deck_min) полотно не ниже настила: урез + столько метров; подъезд — насыпью
BRIDGE_DECK_MIN = {38938146: 5.0, 31386051: 6.0}   # Ольгинский, Советский (как в bridge_krom)
PIN_GRADE = 0.05       # уклон подъезда к мосту, не круче
EDGE_INSET_M = 0.6     # высоту края проезжей части берём на столько внутри: за краем — полоса бордюра выше
CLEAR_M = 0.03         # лента не ниже рельефа + CLEAR_M и между станциями (clear), доли ширины — CLEAR_U
CLEAR_U = (0.1, 0.3, 0.5, 0.7, 0.9)
THIN_XY_M, THIN_Z_M, THIN_MAX_M = 0.05, 0.02, 25.0  # прореживание станций лент для мешей (thin)

CAR = tuple(osm_layers.LANE_M)
# бордюр над проезжей частью, м (гип.: городской бортовой камень ≈15 см — фото c22, env17; дворовые — ниже)
KERB_M = {"primary": 0.15, "primary_link": 0.15, "secondary": 0.15, "secondary_link": 0.15, "tertiary": 0.15,
          "tertiary_link": 0.15, "residential": 0.15, "unclassified": 0.15, "living_street": 0.10, "service": 0.10,
          "pedestrian": 0.12}
KERB_MATERIALS = ("asphalt", "cobble", "tiles", "concrete")  # у грунтовых и отсыпанных дорог бордюра нет
KERB_W_LOW_M = 0.08    # ширина бордюра ≤ 10 см высотой (дворовые, service): камень БР 100.20.8; выше — KERB_W_M
                       # (БР 100.30.15), гип. — у проезда под Ольгинским мостом 15 см выглядели чрезмерно
KERB_BAND_M = 1.0      # за бордюром земля на его высоте на столько метров (terrain_krom.road_bed)
EDGING_M = {"gravel": 0.03, "tiles": 0.03}   # поребрик дорожки над её поверхностью: отсев и плитка (env04, env09);
                                              # асфальт двора — без (kutekroma_yard)
NEAR_ROAD_M = 6.0      # footway, большей частью (NEAR_SHARE) не дальше стольких метров от края проезжей части, —
NEAR_SHARE = 0.6       # тротуар (гип.)
INSIDE_M = 0.3         # станции дорожки ближе к оси, чем полуширина + INSIDE_M, лежат на проезжей части
JUNCTION_END_M = 0.5   # T-стык дорожек: конец одной на оси другой дальше стольких метров от её концов
NUDGE_GAP_M = 0.05     # тротуар, сдвинутый за бордюр (RoadField.nudge): зазор до бордюра
TOWER_RING_GAP_M, TOWER_RING_ABOVE_M = 0.3, 0.3  # отмостка вокруг башни (clear_tower): от контура, над урезом
TUCK_M = 0.2           # обрезанная проезжей частью дорожка заходит под край её ленты на столько (иначе щель до
                       # станции STEP_M: за проездом Великих ворот дорожка захаба начиналась в 3,2 м от него)
RISE_M, TREAD_M = 0.15, 0.35   # ступень лестницы; где перепад рельефа < DEM_FLAT доли от ожидаемого — dem_flat
DEM_FLAT = 0.25
MARKED = ("primary", "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link")
MARKING_WEAR = 0.35    # «слегка стёртая» (владелец): доля стёртой краски для материала (гип.)
DASH_M = (3.0, 6.0)    # прерывистая 1.5: штрих и промежуток (гип.; рисует материал, здесь — превью)
ZEBRA_W, STRIPE_M, GAP_M = 4.0, 0.5, 0.5  # «зебра»: ширина вдоль дороги, полосы и промежутки поперёк (≈ ГОСТ
                                          # Р 51256, разметка 1.14.1 — по памяти, сверить)
# сечения мешей, м: «юбка» у краёв без бордюра, бордюр (ширина, заглубление за ним), поребрик, «зебра» над полотном
SKIRT_M, KERB_W_M, KERB_BURY_M, EDGING_W_M, ZEBRA_LIFT_M = 0.3, 0.15, 0.2, 0.08, 0.005
NO_MARKING = (0.0, 0.0, 0.0, 0.0)  # цвет вершин «без разметки» (roads_krom: R — полос / 8, B — осевая)

MATERIAL = {  # тег surface → материал геометрии (слот меша)
    "asphalt": "asphalt", "chipseal": "asphalt",
    "paving_stones": "tiles", "concrete:plates": "tiles", "bricks": "tiles", "paved": "tiles",
    "concrete": "concrete", "concrete:lanes": "concrete",
    "sett": "cobble", "cobblestone": "cobble", "unhewn_cobblestone": "cobble", "stone": "cobble",
    "compacted": "gravel", "gravel": "gravel", "fine_gravel": "gravel", "pebblestone": "gravel",
    "ground": "earth", "dirt": "earth", "earth": "earth", "unpaved": "earth", "sand": "earth", "grass": "earth",
    "wood": "wood",
}
MATERIAL_BY_MASK = {"Asphalt": "asphalt", "Paved": "tiles", "Earth": "earth", "Gravel": "gravel", "Wood": "wood",
                    "Shore": "earth"}
STEPS_MATERIAL = "concrete"   # лестницы без surface (гип.)
AREAS = (("amenity", {"parking"}), ("area:highway", None), ("place", {"square"}))  # площадки: тег, значения (None — любое)

# набор «дорожки у Крома» (ответ владельца (1), D-038) — первым получает меши
MESH_SCOPE = "zone"    # "zone" — всё в зоне (владелец: «а где у нас дороги…», фаза 3 D-038); "krom" — только набор ниже
                       # и касающиеся его проезжие части (фаза 2)
SET_WAYS = (65775670,   # дорога к Великим воротам
            121919089,  # набережная Великой под Довмонтовым городом
            66789566,   # набережная Псковы от Стрелки до Советского моста (терраса, D-037)
            66656356)   # тропа из отсева под западной стеной Крома
SET_NEAR_M = 40.0      # дорожки не дальше стольких метров от контуров Крома и Довмонтова города (по суше, не за рекой)
SET_STRELKA = ((236.0, -120.0), 220.0)  # Стрелка: по суше от Кутекромы не дальше 220 м


# ---------- высоты ----------

class Heights:
    """Heightmap Landscape: размер, Location и Scale — из heightmap_L_Krom.json при каждом запуске."""

    def __init__(self, meta_path=HM_META):
        with open(meta_path, encoding="utf-8") as f:
            self.meta = json.load(f)
        ls = self.meta["landscape"]
        png = os.path.join(os.path.dirname(meta_path), os.path.basename(self.meta["heightmap"]))
        hm = np.asarray(Image.open(png)).astype(np.float64)
        # Landscape: одна ступень heightmap = Scale Z / 128 uu, 32768 — ноль; строки — Y, столбцы — X
        self.z = (hm - 32768.0) * ls["scale"][2] / 128.0 / 100.0 + ls["location_uu"][2] / 100.0
        self.x0, self.y0 = ls["location_uu"][0] / 100.0, ls["location_uu"][1] / 100.0
        self.dx, self.dy = ls["scale"][0] / 100.0, ls["scale"][1] / 100.0
        self.rect = (self.x0, self.x0 + (hm.shape[1] - 1) * self.dx, self.y0, self.y0 + (hm.shape[0] - 1) * self.dy)

    def at(self, xy):
        """Высота (м от собора) в точках (n, 2) — билинейно."""
        xy = np.asarray(xy, dtype=np.float64).reshape(-1, 2)
        rows, cols = (xy[:, 1] - self.y0) / self.dy, (xy[:, 0] - self.x0) / self.dx
        return ndimage.map_coordinates(self.z, [rows, cols], order=1, mode="nearest")


# ---------- геометрия линий ----------

def densify(pts, step=STEP_M):
    """Ломаная (x, y) → станции не реже step, вершины OSM сохраняются; (точки n × 2, длина по оси s)."""
    out = [tuple(pts[0])]
    for a, b in zip(pts, pts[1:]):
        d = math.dist(a, b)
        if d < 1e-6:
            continue
        n = max(1, math.ceil(d / step))
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(1, n + 1)]
    p = np.array(out)
    return p, np.r_[0.0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))]


def smooth(s, z, sigma):
    """Сглаживание высоты вдоль оси (гаусс σ, м) с концами, прибитыми к исходным значениям. Поправка концов — только
    у концов (гаснет за 3σ): растянутая на всю линию, она уводила профиль длинной дорожки на метр от рельефа."""
    if len(s) < 3 or s[-1] < 1e-6 or sigma <= 0:
        return z.copy()
    su = np.linspace(0.0, s[-1], max(3, int(s[-1] / 0.5) + 1))
    zs = np.interp(s, su, ndimage.gaussian_filter1d(np.interp(su, s, z), sigma / (su[1] - su[0]), mode="nearest"))
    reach = 3.0 * sigma
    if s[-1] <= 2 * reach:  # короткая линия: поправка по всей длине
        t = s / s[-1]
        return zs + (z[0] - zs[0]) * (1 - t) + (z[-1] - zs[-1]) * t
    w0 = 1 - np.clip(s / reach, 0.0, 1.0) ** 2 * (3 - 2 * np.clip(s / reach, 0.0, 1.0))
    t1 = np.clip((s[-1] - s) / reach, 0.0, 1.0)
    w1 = 1 - t1 ** 2 * (3 - 2 * t1)
    return zs + (z[0] - zs[0]) * w0 + (z[-1] - zs[-1]) * w1


def tangents(p, t0=None, t1=None):
    """Единичные касательные по станциям; t0 / t1 — заданные на концах (стык двух линий)."""
    d = np.zeros_like(p)
    d[1:-1] = p[2:] - p[:-2]
    d[0], d[-1] = p[1] - p[0], p[-1] - p[-2]
    if t0 is not None:
        d[0] = t0
    if t1 is not None:
        d[-1] = t1
    return d / np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-9)[:, None]


def left_of(t):
    return np.c_[t[:, 1], -t[:, 0]]


def cut(s, cols, s0, s1):
    """Кусок станций в [s0, s1] с точными концами: cols — массивы по станциям (n или n × k)."""
    keep = (s > s0 + 1e-6) & (s < s1 - 1e-6)
    ns = np.r_[s0, s[keep], s1]
    out = []
    for c in cols:
        c2 = c.reshape(len(s), -1)
        out.append(np.stack([np.interp(ns, s, c2[:, j]) for j in range(c2.shape[1])], axis=1).reshape(
            (len(ns),) + c.shape[1:]))
    return ns - s0, out


def runs(mask):
    """Непрерывные отрезки True: [(i0, i1)] включительно."""
    out, i0 = [], None
    for i, m in enumerate(mask):
        if m and i0 is None:
            i0 = i
        elif not m and i0 is not None:
            out.append((i0, i - 1))
            i0 = None
    if i0 is not None:
        out.append((i0, len(mask) - 1))
    return out


def hull(points):
    """Выпуклая оболочка (монотонная цепь): индексы точек против часовой в осях (x, y)."""
    idx = sorted(range(len(points)), key=lambda i: (points[i][0], points[i][1]))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for i in idx:
        while len(lower) >= 2 and cross(points[lower[-2]], points[lower[-1]], points[i]) <= 1e-9:
            lower.pop()
        lower.append(i)
    for i in reversed(idx):
        while len(upper) >= 2 and cross(points[upper[-2]], points[upper[-1]], points[i]) <= 1e-9:
            upper.pop()
        upper.append(i)
    return lower[:-1] + upper[:-1]


def tuck(p, de):
    """Станции дорожки + точки на переходах «на проезжей части» → «рядом» и обратно, где до края проезжей части
    −TUCK_M (de — от края, линейно между станциями): дорожка кончается под краем ленты, а не на станции за ним.
    Возвращает (точки, длина по оси, флаг вставленной точки)."""
    inside = de <= INSIDE_M
    out, flag = [p[0]], [False]
    for i in range(len(p) - 1):
        f, last = None, False
        if inside[i] != inside[i + 1] and de[i] != de[i + 1]:
            f = float(np.clip((-TUCK_M - de[i]) / (de[i + 1] - de[i]), 0.0, 1.0))
            if f < 0.02:        # точка перехода — сама станция i (уже в out)
                flag[-1], f = True, None
            elif f > 0.98:      # … или станция i + 1
                last, f = True, None
        if f is not None:
            out.append(p[i] + (p[i + 1] - p[i]) * f)
            flag.append(True)
        out.append(p[i + 1])
        flag.append(last)
    q = np.array(out)
    return q, np.r_[0.0, np.cumsum(np.hypot(*np.diff(q, axis=0).T))], np.array(flag)


def clear_of_tower(p, name, w):
    """Точки дорожки шириной w, попавшие в тело башни name (krom_plan.towers, контур у земли), — радиально наружу:
    край дорожки — в TOWER_RING_GAP_M от контура."""
    import krom_plan
    t = next(b for b in krom_plan.towers() if b.name == name)
    fp = np.array(t.footprint, dtype=np.float64)
    c = fp.mean(axis=0)
    r_min = float(np.hypot(*(fp - c).T).max()) + w / 2 + TOWER_RING_GAP_M
    d = p - c
    r = np.hypot(*d.T)
    k = np.where(r < r_min, r_min / np.maximum(r, 1e-6), 1.0)
    return c + d * k[:, None]


def water_z(water):
    """Урез в единицах рельефа: water (terrain_krom — абсолютный) или из heightmap_L_Krom.json (м от собора)."""
    if water is not None:
        return water
    with open(HM_META, encoding="utf-8") as f:
        return json.load(f)["water_level_z_m"]


def near_share(de):
    """Доля станций дорожки у края проезжей части (тротуар вдоль дороги)."""
    return float(((de > INSIDE_M) & (de <= NEAR_ROAD_M)).mean()) if len(de) else 0.0


def cell_of(p):
    i, j = math.floor(p[0] / CELL_M), math.floor(p[1] / CELL_M)
    return f"{i:+d}_{j:+d}".replace("+", "p").replace("-", "m")


def r2(a, nd=2):
    return np.round(np.asarray(a, dtype=np.float64), nd).tolist()


def in_zone(p):
    """Точки p (n × 2) в зоне геометрии: квадрат ±ZONE_M по осям (весь Landscape)."""
    return near_zone(p, 0.0)


def near_zone(p, margin=0.0):
    """Точки p (n × 2) не дальше margin м от зоны геометрии."""
    p = np.asarray(p, dtype=np.float64).reshape(-1, 2)
    return (np.abs(p[:, 0]) <= ZONE_M + margin) & (np.abs(p[:, 1]) <= ZONE_M + margin)


def _smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def zone_weight(x, y, fade):
    """Вес зоны 0…1 на сетке (x, y — массивы, broadcast) для terrain_krom.road_bed: 1 внутри, в последних fade м до
    края квадрата ZONE_M гаснет до 0 — высоты на кромке Landscape остаются прежними (стык с кольцом горизонта)."""
    x, y = np.broadcast_arrays(np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64))
    return 1 - _smoothstep((np.maximum(np.abs(x), np.abs(y)) - ZONE_M + fade) / fade)


def zone_bounds():
    """(x0, x1, y0, y1), м — прямоугольник растров RoadField и LandField: зона с запасом MARGIN_M."""
    r = ZONE_M + MARGIN_M
    return -r, r, -r, r


# ---------- OSM ----------

def pieces(el):
    """Линия OSM → куски без пропусков: [(id узлов, точки (x, y))]."""
    pts = geo.local_points(el["geometry"])
    out, cur_n, cur_p = [], [], []
    for n, p in zip(el.get("nodes") or [None] * len(pts), pts):
        if p is None:
            if len(cur_p) > 1:
                out.append((cur_n, cur_p))
            cur_n, cur_p = [], []
        else:
            cur_n.append(n)
            cur_p.append(p)
    if len(cur_p) > 1:
        out.append((cur_n, cur_p))
    return out


def material_of(surface, hw):
    if surface in MATERIAL:
        return MATERIAL[surface]
    if hw in CAR:
        return "asphalt"
    if hw == "steps":
        return STEPS_MATERIAL
    return MATERIAL_BY_MASK.get(osm_layers.SURFACE_DEFAULT.get(hw, "Asphalt"), "asphalt")


def classify(el, surface):
    """Линия highway с покрытием surface (osm_layers.split_surface) → описание (kind, ширина, материал, …) или None."""
    tags = el.get("tags", {})
    hw = tags.get("highway")
    if tags.get("tunnel") == "yes" or tags.get("area") == "yes" or tags.get("indoor") == "yes":
        return None  # building_passage (проезд Великих ворот, арки домов) — лента идёт насквозь
    if tags.get("bridge") not in (None, "no"):
        return None
    ov = osm_layers.WAY_OVERRIDE.get(el["id"], {})
    if ov.get("skip"):  # аудит дорожек: линии нет (боевой ход под кровлей и т. п.)
        return None
    hw_eff = ov.get("highway", hw)
    mat = material_of(surface, hw)
    width, width_src = osm_layers.way_width(el)
    if width is None:
        return None
    d = dict(osm_id=el["id"], highway=hw_eff, name=tags.get("name"), material=mat,
             mask=osm_layers.surface_class(surface, hw_eff), surface=surface, lit=tags.get("lit"),
             width=width, width_src=width_src, override="override" if ov else None, clear_tower=ov.get("clear_tower"),
             layer=int(osm_layers._num(tags.get("layer")) or 0))
    kind = ov.get("kind")
    if kind is None:
        if hw in CAR:
            kind = "carriageway"
        elif hw == "steps":
            kind = "steps"
        elif hw == "footway" and tags.get("footway") == "crossing":
            kind = "crossing"
        elif hw == "footway" and tags.get("footway") == "sidewalk":
            kind = "sidewalk"
        elif hw in ("footway", "pedestrian", "cycleway", "path", "track", "bridleway"):
            kind = "trail" if mat == "earth" else "footpath"
        else:
            return None
    d["kind"] = kind
    if kind == "carriageway":
        lanes = osm_layers._num(tags.get("lanes"))
        d["lanes"] = int(lanes) if lanes else None
        d["oneway"] = tags.get("oneway") in ("yes", "1", "-1") or tags.get("junction") == "roundabout"
        d["lanes_forward"] = osm_layers._num(tags.get("lanes:forward"))
        d["kerb"] = ov.get("kerb", KERB_M.get(hw_eff, 0.0) if mat in KERB_MATERIALS else 0.0)
        sl, sr = sidewalks_of(tags)
        sw = osm_layers.SIDEWALK_M
        d["sidewalk"] = ov.get("sidewalk", (sw if sl else 0.0, sw if sr else 0.0))
    else:
        d["kerb"] = ov.get("kerb", KERB_M["pedestrian"] if hw == "pedestrian" and mat in KERB_MATERIALS
                           else EDGING_M.get(mat, 0.0))
        d["incline"] = tags.get("incline")
        d["handrail"] = tags.get("handrail")
    return d


def sidewalks_of(tags):
    """(слева, справа) — есть ли тротуар из тегов дороги (не separate: отдельные линии footway считаются сами)."""
    both = tags.get("sidewalk:both") == "yes" or tags.get("sidewalk") in ("both", "yes")
    left = both or tags.get("sidewalk") == "left" or tags.get("sidewalk:left") == "yes"
    right = both or tags.get("sidewalk") == "right" or tags.get("sidewalk:right") == "yes"
    return left, right


# ---------- учёт (inventory) ----------

def inventory(els, rect):
    """Длины и число линий highway по видам — во всём Landscape и в зоне; покрытие тегами; площадки, узлы окружения."""
    xmin, xmax, ymin, ymax = rect
    by = defaultdict(lambda: {"n_land": 0, "km_land": 0.0, "n_zone": 0, "km_zone": 0.0})
    tagcov = defaultdict(Counter)
    COV = ("lanes", "width", "sidewalk", "kerb", "surface", "lit", "oneway", "maxspeed")
    other = Counter()
    for el in els:
        tags = el.get("tags", {})
        if el["type"] != "way":
            continue
        hw = tags.get("highway")
        if hw:
            key = hw + (f" ({tags['footway']})" if hw == "footway" and tags.get("footway") else "") + \
                (" area" if tags.get("area") == "yes" else "") + (" bridge" if tags.get("bridge") == "yes" else "")
            land = zone = 0.0
            for _, pts in pieces(el):
                p, _s = densify(pts, 1.0)
                mid = (p[1:] + p[:-1]) / 2
                seg = np.hypot(*np.diff(p, axis=0).T)
                inl = (mid[:, 0] >= xmin) & (mid[:, 0] <= xmax) & (mid[:, 1] >= ymin) & (mid[:, 1] <= ymax)
                land += float(seg[inl].sum())
                zone += float(seg[in_zone(mid)].sum())
            if land > 0:
                by[key]["n_land"] += 1
                by[key]["km_land"] += land / 1000
                for k in COV:
                    if any(t == k or t.startswith(k + ":") or t.endswith(":" + k) for t in tags):
                        tagcov[hw][k] += 1
                tagcov[hw]["ways"] += 1
                if tags.get("footway") == "crossing":
                    other["footway=crossing"] += 1
            if zone > 0:
                by[key]["n_zone"] += 1
                by[key]["km_zone"] += zone / 1000
        if el.get("nodes") and el["nodes"][0] == el["nodes"][-1] and None not in el["geometry"]:
            ring = geo.open_ring(geo.local_points(el["geometry"]))
            c = geo.centroid(ring) if len(ring) > 2 and abs(geo.signed_area(ring)) > 1e-6 else ring[0]
            if xmin <= c[0] <= xmax and ymin <= c[1] <= ymax:
                where = "зона" if in_zone(np.array([c]))[0] else "вне зоны"
                a = abs(geo.signed_area(ring)) if len(ring) > 2 else 0.0
                for k, vals in AREAS + (("highway", None),):
                    if k in tags and (vals is None or tags[k] in vals) and (k != "highway" or tags.get("area") == "yes"):
                        other[f"{k}={tags[k] if vals else '*'} ({where})"] += 1
                        other[f"{k}={tags[k] if vals else '*'} ({where}) м²"] += round(a)
        if tags.get("barrier") == "kerb":
            other["barrier=kerb (линии)"] += 1
    other["узлы в выгрузке krom_2*.json"] = sum(e["type"] == "node" for e in els)
    for pattern, label in (("krom_env_*.json", "krom_env"), ("krom_nodes_*.json", "krom_nodes")):
        try:
            nodes = geo.load_elements(geo.latest(pattern))
        except FileNotFoundError:
            continue
        for e in nodes:
            if e["type"] != "node":
                continue
            x, y = geo.to_local(e["lat"], e["lon"])
            where = "зона" if in_zone(np.array([(x, y)]))[0] else "вне зоны"
            t = e.get("tags", {})
            for k, v in (("highway", "street_lamp"), ("amenity", "bench"), ("amenity", "waste_basket"),
                         ("highway", "crossing"), ("highway", "traffic_signals"), ("barrier", "kerb")):
                if t.get(k) == v:
                    other[f"{k}={v} ({where}, {label})"] += 1
            if t.get("highway") == "crossing":
                other[f"crossing={t.get('crossing', '?')} ({where}, {label})"] += 1
            if "kerb" in t:
                other[f"kerb={t['kerb']} ({where}, {label})"] += 1
    by = {k: {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in v.items()}
          for k, v in sorted(by.items(), key=lambda kv: -kv[1]["km_land"])}
    return {"highway": by, "tag_coverage": {k: dict(v) for k, v in tagcov.items()}, "other": dict(sorted(other.items()))}


# ---------- проезжая часть ----------

class Seg:
    """Кусок проезжей части между узлами-перекрёстками."""

    def __init__(self, info, nodes, pts):
        self.info, self.nodes, self.xy = info, nodes, [tuple(p) for p in pts]
        self.hw_half = info["width"] / 2
        self.ends = [{"type": "free", "node": nodes[0]}, {"type": "free", "node": nodes[-1]}]


def carriageways(parts, z_at, bridge_nodes, lift, water=None):
    """Проезжая часть: куски между перекрёстками, высоты, обрезка у перекрёстков, площадки, бордюры углов.
    parts — [(описание, id узлов, точки)]; lift — прибавка к высоте рельефа (осадка ленты): > 0 — готовый heightmap,
    высоты берутся как есть (рельеф уже подогнан под профиль); 0 — рельеф до подгонки (terrain_krom): профиль
    сглажен, у мостов с BRIDGE_DECK_MIN конец поднят до настила (water — урез в тех же единицах)."""
    final = lift > 0
    deg = Counter()
    for info, nodes, _ in parts:
        closed = nodes[0] == nodes[-1]
        for i, n in enumerate(nodes):
            deg[n] += 2 if (0 < i < len(nodes) - 1 or closed) else 1
        if closed:
            deg[nodes[0]] -= 2  # первый и последний узел кольца — один узел степени 2
    junction = {n for n, d in deg.items() if d >= 3}
    segs = []
    for info, nodes, pts in parts:
        cuts = [0] + [i for i in range(1, len(nodes) - 1) if nodes[i] in junction] + [len(nodes) - 1]
        for a, b in zip(cuts, cuts[1:]):
            if b > a:
                segs.append(Seg(info, nodes[a:b + 1], pts[a:b + 1]))
    at_node = defaultdict(list)  # узел → [(номер куска, конец 0/1)]
    for k, s in enumerate(segs):
        at_node[s.nodes[0]].append((k, 0))
        at_node[s.nodes[-1]].append((k, 1))

    # типы концов и касательные стыков
    for k, s in enumerate(segs):
        for e in (0, 1):
            n = s.nodes[0] if e == 0 else s.nodes[-1]
            others = [(k2, e2) for k2, e2 in at_node[n] if (k2, e2) != (k, e)]
            if n in bridge_nodes:
                s.ends[e] = {"type": "bridge", "node": n, "bridge": bridge_nodes[n]}
            elif n in junction:
                s.ends[e] = {"type": "junction", "node": n,
                             "trim": max((segs[k2].hw_half for k2, _ in others), default=0.0) + CORNER_M}
            elif len(others) == 1:
                k2, e2 = others[0]
                o = segs[k2]
                q = o.xy[1] if e2 == 0 else o.xy[-2]   # соседняя точка другой линии
                node = np.array(s.xy[0] if e == 0 else s.xy[-1])
                own = np.array(s.xy[1] if e == 0 else s.xy[-2])
                t = (own - node) + (node - np.array(q)) if e == 0 else (node - own) + (np.array(q) - node)
                s.ends[e] = {"type": "join", "node": n, "t": t / max(np.hypot(*t), 1e-9)}

    for s in segs:
        p, sarc = densify(s.xy)
        L = sarc[-1]
        z = z_at(p) + lift if final else smooth(sarc, z_at(p), SMOOTH_M["carriageway"])
        s.pin = np.zeros(len(p))
        for e in (0, 1):  # у моста полотно не ниже настила: подъезд — насыпью с уклоном не круче PIN_GRADE
            end = s.ends[e]
            dmin = BRIDGE_DECK_MIN.get(end.get("bridge")) if end["type"] == "bridge" else None
            if final or water is None or dmin is None:
                continue
            dz = water + dmin - z[0 if e == 0 else -1]
            if dz <= 0:
                continue
            d_end = sarc if e == 0 else L - sarc
            reach = min(max(dz / PIN_GRADE, 20.0), 0.9 * L)
            w = 1 - np.clip(d_end / reach, 0.0, 1.0) ** 2 * (3 - 2 * np.clip(d_end / reach, 0.0, 1.0))
            z = z + dz * w
            s.pin = np.maximum(s.pin, dz * w)
        t0 = s.ends[0].get("trim", 0.0)
        t1 = s.ends[1].get("trim", 0.0)
        if t0 + t1 > 0.9 * L:  # короткий кусок между близкими перекрёстками: обрезка поровну, остаток ≥ 10 %
            f = 0.9 * L / (t0 + t1)
            t0, t1 = t0 * f, t1 * f
        s.full = (p, sarc, z)  # до обрезки: для «зебр», растра расстояний и рельефа
        ns, (pc, zc) = cut(sarc, [p, z], t0, L - t1)
        tg = tangents(pc, s.ends[0].get("t") if s.ends[0]["type"] == "join" else None,
                      s.ends[1].get("t") if s.ends[1]["type"] == "join" else None)
        off = max(s.hw_half - EDGE_INSET_M, 0.0)
        sig = 0.0 if final else SMOOTH_M["carriageway"]
        zl, zr = (edge_z(pc, ns, tg, sgn * off, sig, z_at) + lift for sgn in (1, -1))
        s.raised = 0.0
        if lift > 0:  # с готового heightmap: рельеф нигде не выше ленты
            zc, zl, zr, s.raised = clear(pc, tg, 2 * s.hw_half, zc, zl, zr, z_at)
        s.cut = (pc, ns, zc, tg, zl, zr)

    # площадки перекрёстков: оболочка обрезанных концов, высоты — концов, центр — узел
    junctions = []
    for n in sorted(junction):
        ends = at_node.get(n, [])
        if len(ends) < 2:
            continue
        pts, owner = [], []
        for k, e in ends:
            s = segs[k]
            pc, ns, zc, tg, zl, zr = s.cut
            i = 0 if e == 0 else -1
            nl = left_of(tg[[i]])[0]
            for side, ze in ((1, zl), (-1, zr)):
                c = pc[i] + side * nl * s.hw_half
                pts.append((float(c[0]), float(c[1]), float(ze[i])))
                owner.append(k)
        h = hull([(q[0], q[1]) for q in pts])
        if len(h) < 3:
            continue
        s0 = segs[ends[0][0]]
        node_xy = s0.xy[0] if ends[0][1] == 0 else s0.xy[-1]
        zj = float(z_at([node_xy])[0]) + lift
        kerbs = []
        for a, b in zip(h, h[1:] + h[:1]):
            ka, kb = segs[owner[a]].info["kerb"], segs[owner[b]].info["kerb"]
            if owner[a] != owner[b] and ka > 0 and kb > 0:
                kerbs.append({"pts": r2([pts[a], pts[b]]), "h": min(ka, kb)})
        widest = max((segs[k] for k, _ in ends), key=lambda s: s.info["width"])
        junctions.append({"kind": "junction", "node": n, "center": r2([node_xy[0], node_xy[1], zj]),
                          "ring": r2([pts[i] for i in h]), "material": widest.info["material"],
                          "osm_ids": sorted({segs[k].info["osm_id"] for k, _ in ends}), "kerbs": kerbs,
                          "segs": sorted({k for k, _ in ends}), "cell": cell_of(node_xy), "mesh": True})
    return segs, junctions


def markings(info, w):
    """Линии разметки: смещение от оси (+ — влево по ходу линии OSM) и тип; только на главных улицах (MARKED)
    с lanes ≥ 2 на асфальте (владелец, D-038)."""
    lanes = info.get("lanes")
    if not lanes or lanes < 2 or info["material"] != "asphalt" or info["highway"] not in MARKED:
        return []
    lane = w / lanes
    if info["oneway"]:
        return [{"offset": round(-w / 2 + k * lane, 2), "type": "dashed"} for k in range(1, lanes)]
    fwd = int(info.get("lanes_forward") or lanes - lanes // 2)  # по ходу — справа (правостороннее движение)
    out = []
    for k in range(1, lanes):
        typ = ("double_solid" if lanes >= 4 else "dashed") if k == fwd else "dashed"  # 1.3 при 4+ полосах (гип.)
        out.append({"offset": round(-w / 2 + k * lane, 2), "type": typ})
    return out


# ---------- растры ----------

class RoadField:
    """Расстояние до ближайшей оси проезжей части и её полуширина на растре RASTER_M вокруг зоны."""

    def __init__(self, segs):
        x0, x1, y0, y1 = zone_bounds()   # строки растра — X (север), столбцы — Y (восток)
        self.gx, self.gy = x0, y0
        self.nx, self.ny = int((x1 - x0) / RASTER_M) + 1, int((y1 - y0) / RASTER_M) + 1
        img = Image.new("I", (self.ny, self.nx), 0)
        d = ImageDraw.Draw(img)
        for k, s in enumerate(segs):
            p = s.full[0]
            d.line([((q[1] - self.gy) / RASTER_M, (q[0] - self.gx) / RASTER_M) for q in p], fill=k + 1, width=1)
        idx = np.asarray(img, dtype=np.int64)
        dist, (ii, jj) = ndimage.distance_transform_edt(idx == 0, return_indices=True)
        self.dist = dist * RASTER_M
        self.seg = idx[ii, jj] - 1
        self.half = np.array([s.hw_half for s in segs] + [0.0])
        self.grad = None

    def rc(self, p):
        r = np.clip(np.rint((p[:, 0] - self.gx) / RASTER_M).astype(int), 0, self.nx - 1)
        c = np.clip(np.rint((p[:, 1] - self.gy) / RASTER_M).astype(int), 0, self.ny - 1)
        return r, c

    def nudge(self, p, de, w):
        """Дорожка шириной w вдоль проезжей части (касательная под углом > 60° к направлению от оси), которая краем
        заходит на полотно и бордюр (тротуары OSM нарисованы местами в 0,3–1 м от края), — сдвинута от оси, чтобы край
        был за бордюром. Возвращает (точки, сдвинуто станций)."""
        if self.grad is None:
            gr, gc = np.gradient(self.dist)
            self.grad = (gr, gc)
        need = w / 2 + KERB_W_M + NUDGE_GAP_M - de
        cand = (de > INSIDE_M) & (need > 0)
        if not cand.any() or len(p) < 2:
            return p, 0
        r, c = self.rc(p)
        g = np.c_[self.grad[0][r, c], self.grad[1][r, c]]
        g /= np.maximum(np.hypot(*g.T), 1e-9)[:, None]
        tg = tangents(p)
        par = np.abs((tg * g).sum(1)) < 0.5
        move = cand & par
        if not move.any():
            return p, 0
        q = p.copy()
        q[move] += g[move] * need[move][:, None]
        return q, int(move.sum())

    def lookup(self, p):
        """(расстояние до оси, номер куска, до края проезжей части) в точках p (n × 2)."""
        r, c = self.rc(p)
        d, k = self.dist[r, c], self.seg[r, c]
        return d, k, d - self.half[k]


class LandField:
    """Вода OSM на растре 1 м вокруг зоны: «по суше ли» отрезок (набор дорожек у Крома не берёт другой берег)."""

    def __init__(self):
        x0, x1, y0, y1 = zone_bounds()
        self.gx, self.gy = x0, y0
        self.nx, self.ny = int(x1 - x0) + 1, int(y1 - y0) + 1
        img = Image.new("L", (self.ny, self.nx), 0)
        d = ImageDraw.Draw(img)
        water = geo.water_rings(geo.load_elements(geo.latest("krom_water_*.json")))
        polys, _ = osm_layers.collect((x0, x1, y0, y1))
        for ring in water["rings"] + polys["Water"]:
            if len(ring) > 2:
                d.polygon([(q[1] - self.gy, q[0] - self.gx) for q in ring], fill=1)
        self.water = np.asarray(img, dtype=bool)

    def dry(self, a, b, k=12):
        t = np.linspace(0.0, 1.0, k)
        x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        r = np.clip(np.rint(x - self.gx).astype(int), 0, self.nx - 1)
        c = np.clip(np.rint(y - self.gy).astype(int), 0, self.ny - 1)
        return not self.water[r, c].any()


def nearest_on_ring(p, ring):
    best, bd = None, 1e18
    for a, b in zip(ring, ring[1:] + ring[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy or 1e-9
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
        q = (a[0] + dx * t, a[1] + dy * t)
        d = (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2
        if d < bd:
            best, bd = q, d
    return best, math.sqrt(bd)


class KromSet:
    """Набор «дорожки у Крома» (SET_*): по ID, внутри контуров Крома и Довмонтова города, рядом с ними по суше,
    на Стрелке."""

    def __init__(self):
        self.rings = [list(osm_layers.krom_ring()), osm_layers.relation_ring(osm_layers.DOVMONT_REL)]
        self.land = LandField()

    def has(self, osm_id, p):
        if osm_id in SET_WAYS:
            return True
        m = tuple(p[len(p) // 2][:2])
        for ring in self.rings:
            if osm_layers.point_in(m, ring):
                return True
            q, d = nearest_on_ring(m, ring)
            if d <= SET_NEAR_M and self.land.dry(m, q):
                return True
        (sx, sy), sr = SET_STRELKA
        return m[0] >= sx and math.hypot(m[0] - sx, m[1] - sy) <= sr and self.land.dry(m, (sx, sy))


# ---------- сборка элементов ----------

def edge_z(p, s, tg, off, sigma, z_at):
    """Высота рельефа вдоль параллели оси на off м (+ — влево), сглаженная вдоль оси."""
    return smooth(s, z_at(p + left_of(tg) * off), sigma)


def across(zl, zc, zr, u):
    """Высота сечения ленты на доле ширины u от левого края: два отрезка — край, ось, край."""
    return zl + (zc - zl) * (u / 0.5) if u <= 0.5 else zc + (zr - zc) * ((u - 0.5) / 0.5)


def clear(p, tg, w, z, zl, zr, z_at):
    """Поднимает ленту там, где рельеф между станциями и поперёк выходит выше неё + CLEAR_M (иначе Landscape
    протыкает ленту «шахматкой» — полосы пересечения двух сеток). Возвращает (z, zl, zr) и наибольший подъём."""
    nl = left_of(tg)
    L, R = p + nl * w / 2, p - nl * w / 2
    need = np.zeros(len(p))
    for u in CLEAR_U:
        q = L + (R - L) * u
        zq = across(zl, z, zr, u)
        need = np.maximum(need, z_at(q) + CLEAR_M - zq)
        if len(p) > 1:
            qm, zm = (q[1:] + q[:-1]) / 2, (zq[1:] + zq[:-1]) / 2
            dm = z_at(qm) + CLEAR_M - zm
            need[:-1] = np.maximum(need[:-1], dm)
            need[1:] = np.maximum(need[1:], dm)
    need = np.maximum(need, 0.0)
    return z + need, zl + need, zr + need, float(need.max()) if len(need) else 0.0


def thin(el, z_at):
    """Прореживает станции ленты (с готового heightmap): станция уходит, если без неё ось и края в плане отходят
    не больше THIN_XY_M, высоты — не больше THIN_Z_M, отрезок не длиннее THIN_MAX_M; потом clear по отрезкам через
    1 м. На прямых ровных улицах вместо станций через 2 м — через 10–25 м: бордюры и «юбки» в разы легче."""
    P, L, R = (np.array(el[k], dtype=np.float64) for k in ("pts", "l", "r"))
    zl, zr = np.array(el["zl"], dtype=np.float64), np.array(el["zr"], dtype=np.float64)
    n = len(P)
    if n < 3:
        return
    s = np.r_[0, np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))]
    xy = np.hstack([P[:, :2], L, R])
    zz = np.c_[P[:, 2], zl, zr]

    def ok(i, j):
        if s[j] - s[i] > THIN_MAX_M:
            return False
        f = ((s[i + 1:j] - s[i]) / max(s[j] - s[i], 1e-9))[:, None]
        dxy = xy[i + 1:j] - (xy[i] + (xy[j] - xy[i]) * f)
        dz = zz[i + 1:j] - (zz[i] + (zz[j] - zz[i]) * f)
        return (np.hypot(dxy[:, 0::2], dxy[:, 1::2]).max() <= THIN_XY_M) and (np.abs(dz).max() <= THIN_Z_M)

    keep, i = [0], 0
    while i < n - 1:
        j = i + 1
        while j + 1 < n and ok(i, j + 1):
            j += 1
        keep.append(j)
        i = j
    k = np.array(keep)
    P, L, R, zl, zr = P[k], L[k], R[k], zl[k], zr[k]
    need = np.zeros(len(k))  # clear по отрезкам: рельеф через 1 м вдоль и по CLEAR_U поперёк
    for a in range(len(k) - 1):
        m = max(1, int(math.ceil(math.dist(P[a, :2], P[a + 1, :2]))))
        f = (np.arange(m + 1) / m)[:, None]
        la, ra = L[a] + (L[a + 1] - L[a]) * f, R[a] + (R[a + 1] - R[a]) * f
        za, zb = zl[a] + (zl[a + 1] - zl[a]) * f[:, 0], zr[a] + (zr[a + 1] - zr[a]) * f[:, 0]
        zm = P[a, 2] + (P[a + 1, 2] - P[a, 2]) * f[:, 0]
        worst = 0.0
        for u in CLEAR_U:
            worst = max(worst, float(np.max(z_at(la + (ra - la) * u) + CLEAR_M - across(za, zm, zb, u))))
        need[a] = max(need[a], worst)
        need[a + 1] = max(need[a + 1], worst)
    need = np.maximum(need, 0.0)
    P[:, 2] += need
    el.update(pts=r2(P, 3), l=r2(L), r=r2(R), zl=r2(zl + need, 3), zr=r2(zr + need, 3))
    if "s" in el:
        el["s"] = r2(np.array(el["s"])[k])


def _arc(el):
    P = np.array(el["pts"], dtype=np.float64)
    return P, (np.array(el["s"]) if "s" in el else np.r_[0, np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))])


def _nearest(P, q):
    """Ближайшая к q точка ломаной P (n × ≥2): (расстояние, длина по оси до неё, единичная касательная)."""
    a, b = P[:-1, :2], P[1:, :2]
    ab = b - a
    L2 = np.maximum((ab ** 2).sum(1), 1e-12)
    t = np.clip(((q - a) * ab).sum(1) / L2, 0.0, 1.0)
    d = np.hypot(*(a + ab * t[:, None] - q).T)
    k = int(np.argmin(d))
    seg = np.sqrt(L2)
    return float(d[k]), float(np.r_[0, np.cumsum(seg)][k] + t[k] * seg[k]), ab[k] / seg[k]


def path_junctions(elements):
    """Примыкания дорожек (T-стыки): конец дорожки J на оси другой дорожки T (не у её концов). У T поребрик / бортовой
    камень прерывается на ширину J со стороны примыкания (edge_gaps), J кончается у края T (иначе две ленты на одной
    высоте мерцают, а поребрики поперёк чужого полотна — «зебра» штрихов, как у Святых ворот). Возвращает число стыков."""
    paths = [el for el in elements if el["kind"] in ("footpath", "sidewalk") and el.get("mesh")]
    grid = defaultdict(list)
    for k, el in enumerate(paths):
        P = np.array(el["pts"])[:, :2]
        for c in {(int(x // 20), int(y // 20)) for x, y in P}:
            grid[c].append(k)
    n = 0
    for kj, J in enumerate(paths):
        for head in (0, -1):
            PJ = np.array(J["pts"], dtype=np.float64)
            if len(PJ) < 2:
                break
            q = PJ[head, :2]
            cx, cy = int(q[0] // 20), int(q[1] // 20)
            near = {k for dx in (-1, 0, 1) for dy in (-1, 0, 1) for k in grid[(cx + dx, cy + dy)] if k != kj}
            best = None
            for kt in near:
                T = paths[kt]
                PT, sT = _arc(T)
                d, sc, tg = _nearest(PT, q)
                if d <= T["width"] / 2 + 0.3 and JUNCTION_END_M < sc < sT[-1] - JUNCTION_END_M:
                    if best is None or d < best[0]:
                        best = (d, kt, sc, tg)
            if best is None:
                continue
            d, kt, sc, tg = best
            T = paths[kt]
            inward = PJ[1 if head == 0 else -2, :2] - q  # от стыка вдоль J
            side = "l" if tg[1] * inward[0] - tg[0] * inward[1] < 0 else "r"  # левая нормаль (ty, −tx)
            gap = J["width"] / 2 + 0.2
            T.setdefault("edge_gaps", {"l": [], "r": []})[side].append([round(sc - gap, 2), round(sc + gap, 2)])
            # J — до края T (5 см внахлёст)
            reach = max(T["width"] / 2 - 0.05 - d, 0.0)
            if reach > 0:
                trim_end(J, head, reach)
            n += 1
    return n


def trim_end(el, head, cut):
    """Укорачивает ленту el с конца head (0 — начало, −1 — конец) на cut метров по оси."""
    P, s = _arc(el)
    keys = ("pts", "l", "r", "zl", "zr")
    arrs = {k: np.array(el[k], dtype=np.float64) for k in keys}
    if head == -1:
        arrs = {k: v[::-1] for k, v in arrs.items()}
        s = s[-1] - s[::-1]
    if cut >= s[-1] - 0.5:
        return
    i = int(np.searchsorted(s, cut))  # первая станция дальше cut
    f = (cut - s[i - 1]) / max(s[i] - s[i - 1], 1e-9)
    for k, v in arrs.items():
        v2 = v[i - 1] + (v[i] - v[i - 1]) * f
        arrs[k] = np.concatenate([v2[None] if v.ndim > 1 else [v2], v[i:]])
    s2 = np.concatenate([[cut], s[i:]]) - cut
    if head == -1:
        arrs = {k: v[::-1] for k, v in arrs.items()}
        s2 = s2[-1] - s2[::-1]
    el.update(pts=r2(arrs["pts"], 3), l=r2(arrs["l"]), r=r2(arrs["r"]), zl=r2(arrs["zl"], 3), zr=r2(arrs["zr"], 3))
    if "s" in el:
        el["s"] = r2(s2)
    for side in el.get("edge_gaps", {}).values():  # промежутки поребрика — в новой длине по оси
        for g in side:
            if head == 0:
                g[0], g[1] = g[0] - cut, g[1] - cut


def ribbon(kind, info, p, z, tg, w, extra=None, zl=None, zr=None):
    """Лента: ось pts (x, y, z — профиль), края l, r (x, y) и их высоты zl, zr (где рельеф выровнен — как у оси,
    где нет — по рельефу, чтобы край не висел)."""
    nl = left_of(tg)
    zl = z if zl is None else zl
    zr = z if zr is None else zr
    el = {"kind": kind, "osm_id": info["osm_id"], "highway": info["highway"], "name": info.get("name"),
          "material": info["material"], "mask": info["mask"], "width": round(w, 2), "kerb": info.get("kerb", 0.0),
          "lit": info.get("lit"), "pts": r2(np.c_[p, z], 3), "l": r2(p + nl * w / 2), "r": r2(p - nl * w / 2),
          "zl": r2(zl, 3), "zr": r2(zr, 3), "cell": cell_of(p[len(p) // 2]), "mesh": kind != "trail"}
    if extra:
        el.update(extra)
    return el


def collect_ways():
    """Линии highway в зоне с запасом: [(элемент OSM, id узлов, точки, описание)] по кускам покрытия + узлы мостов."""
    els = geo.load_elements(geo.latest("krom_2*.json"))
    out, bridge_nodes = [], {}
    for el in els:
        tags = el.get("tags", {})
        if el["type"] != "way" or not tags.get("highway") or not el.get("nodes"):
            continue
        pts = [p for p in geo.local_points(el["geometry"]) if p]
        if not pts or not near_zone(np.array(pts), MARGIN_M).any():
            continue
        if tags.get("bridge") not in (None, "no"):
            for n in el["nodes"]:
                bridge_nodes[n] = el["id"]
            continue
        for nodes, piece in pieces(el):
            parts = osm_layers.split_surface(el, piece)
            if len(parts) == 1:
                info = classify(el, parts[0][1])
                if info:
                    out.append((el, nodes, piece, info))
                continue
            for sub, surface in parts:  # покрытие меняется посреди линии: узлы — только на концах исходного куска
                info = classify(el, surface)
                if info:
                    ns = [nodes[0] if sub[0] == piece[0] else None] + [None] * (len(sub) - 2) + \
                         [nodes[-1] if sub[-1] == piece[-1] else None]
                    out.append((el, ns, sub, info))
    return els, out, bridge_nodes


def build(z_at, lift=True, water=None):
    """Элементы в зоне по рельефу z_at ((n, 2) → z). lift — лента выше рельефа на осадку (с готового heightmap);
    terrain_krom зовёт с lift=False своим рельефом до подгонки. Возвращает (элементы, куски проезжей части, сводку)."""
    els, ways, bridge_nodes = collect_ways()
    car_lift, path_lift = (ROAD_SINK_M, PATH_SINK_M) if lift else (0.0, 0.0)
    car = [(info, nodes, pts) for el, nodes, pts, info in ways if info["kind"] == "carriageway"]
    segs, junctions = carriageways(car, z_at, bridge_nodes, car_lift, water)
    field = RoadField(segs)
    raised = [s.raised for s in segs]
    kset = KromSet()
    square = osm_layers.cathedral_square()
    elements, stats, diag = [], defaultdict(float), defaultdict(list)
    diag["raised_m"] += raised

    # проезжая часть, тротуары из её тегов, разметка
    for k, s in enumerate(segs):
        pc, ns, zc, tg, ezl, ezr = s.cut
        info, w = s.info, s.info["width"]
        s.set = kset.has(info["osm_id"], pc)
        nl = left_of(tg)
        zl, zr = z_at(pc + nl * w / 2), z_at(pc - nl * w / 2)
        for i0, i1 in runs(in_zone(pc)):
            if i1 - i0 < 1:
                continue
            sl = slice(i0, i1 + 1)
            ends = [s.ends[0] if i0 == 0 else {"type": "zone"}, s.ends[1] if i1 == len(pc) - 1 else {"type": "zone"}]
            ends = [{kk: (r2(v, 4) if kk == "t" else v) for kk, v in e.items()} for e in ends]
            el = ribbon("carriageway", info, pc[sl], zc[sl], tg[sl], w, {
                "width_src": info["width_src"], "lanes": info["lanes"], "oneway": info["oneway"],
                "markings": markings(info, w), "ends": ends, "s": r2(ns[sl] - ns[i0]), "seg": k,
                "sidewalk": list(info["sidewalk"])}, ezl[sl], ezr[sl])
            elements.append(el)
            diag["car_cross_pct"] += list(np.abs(zl[sl] - zr[sl]) / w * 100)
            diag["car_lift_m"] += list(np.maximum(np.abs(zl[sl] - zc[sl] + car_lift), np.abs(zr[sl] - zc[sl] + car_lift)))
            diag["car_fill_m"] += list(zc[sl] - car_lift - z_at(pc[sl]))
            diag["car_worst"].append((float(np.max(np.abs(zl[sl] - zr[sl]))), info["osm_id"], info.get("name")))
            for side, sw, ze in zip((1, -1), info["sidewalk"], (ezl, ezr)):
                if sw > 0:
                    # за бордюром: верх бордюра и тротуар на одной высоте — внахлёст они мерцали бы
                    off = side * (w / 2 + kerb_w(info["kerb"]) + sw / 2)
                    sw_info = dict(info, kerb=0.0, highway="footway", material="tiles", mask="Paved")
                    inner = ze[sl] + info["kerb"]
                    # внешний край — по рельефу, если он ниже (берег, откос): иначе тротуар висит над склоном
                    outer = np.minimum(inner, z_at(pc[sl] + nl[sl] * side * (w / 2 + sw)) + path_lift) if lift                         else inner
                    zl_, zr_ = (outer, inner) if side > 0 else (inner, outer)
                    elements.append(ribbon("sidewalk", sw_info, pc[sl] + nl[sl] * off, (inner + outer) / 2, tg[sl], sw,
                                           {"generated": "sidewalk=* дороги", "side": "l" if side > 0 else "r",
                                            "seg": k}, zl_, zr_))
    set_nodes = set()
    for el, nodes, pts, info in ways:
        if info["kind"] != "carriageway" and kset.has(el["id"], pts):
            set_nodes |= {n for n in nodes if n}
    for s in segs:  # проезжие части, которые касаются набора
        s.set = s.set or any(n in set_nodes for n in s.nodes)

    # площадки перекрёстков в зоне
    for j in junctions:
        if in_zone(np.array([j["center"][:2]]))[0]:
            j["set"] = any(segs[k].set for k in j["segs"])
            elements.append(j)

    # дорожки, тротуары, «зебры», лестницы
    car_nodes = {n for _, nodes, _ in car for n in nodes}
    # тупиковые концы проезжих частей (проезд Великих ворот → дорожка захаба): лента кончается срезом по узлу, а
    # RoadField меряет до оси «капсулой» — дорожка, продолжающая такой конец, идёт от самого узла
    ends = Counter(n for _, nodes, _ in car for n in (nodes[0], nodes[-1]))
    inner = Counter(n for _, nodes, _ in car for n in nodes[1:-1])
    dead_ends = {n for n, k in ends.items() if k == 1 and not inner[n] and n}
    possible_crossings, zebras = 0, []
    for el, nodes, pts, info in ways:
        kind = info["kind"]
        if kind == "carriageway":
            continue
        if kind == "steps":
            elements.extend(steps(info, pts, z_at))
            continue
        if kind in ("footpath", "sidewalk"):
            possible_crossings += sum(n in car_nodes for n in nodes[1:-1] if n)
        p, sarc = densify(pts)
        dc, kseg, de = field.lookup(p)
        tucked = np.zeros(len(p), bool)
        if kind != "crossing":
            p, sarc, tucked = tuck(p, de)
            dc, kseg, de = field.lookup(p)
            if kind in ("footpath", "sidewalk"):  # тротуар OSM вплотную к полотну — за бордюр
                p, moved = field.nudge(p, de, info["width"])
                if moved:
                    sarc = np.r_[0.0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))]
                    dc, kseg, de = field.lookup(p)
                    stats["footway_nudged_m"] += moved
        if info.get("clear_tower"):  # отмостка вокруг башни: вне её тела (аудит №30)
            p = clear_of_tower(p, info["clear_tower"], info["width"])
            sarc = np.r_[0.0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))]
            dc, kseg, de = field.lookup(p)
        raw = z_at(p)
        z = raw + path_lift if lift else smooth(sarc, raw, SMOOTH_M.get(kind, 3.0))
        if info.get("clear_tower"):  # и не ниже уреза + TOWER_RING_ABOVE_M
            z = np.maximum(z, water_z(water) + TOWER_RING_ABOVE_M)
        pin = np.zeros(len(p))
        if not lift and (kind == "sidewalk" or (kind == "footpath" and near_share(de) >= NEAR_SHARE)):
            # тротуар у подъезда к мосту поднимается вместе с дорогой (насыпь); набережные под мостом — нет
            for i in np.nonzero(de <= NEAR_ROAD_M)[0]:
                sg = segs[kseg[i]]
                if sg.pin.max() > 0:
                    q = sg.full[0]
                    pin[i] = sg.pin[int(np.argmin(np.hypot(*(q - p[i]).T)))]
            z = z + pin
        if kind == "crossing":
            z_on = de < INSIDE_M
            if z_on.any() and in_zone(p[z_on]).all():
                zb = zebra(info, p[z_on].mean(axis=0), segs[int(np.bincount(kseg[z_on]).argmax())])
                if not any(math.dist(zb["center"][:2], o["center"][:2]) < ZEBRA_W for o in zebras
                           if o["road_osm_id"] == zb["road_osm_id"]):  # две линии crossing на одном переходе
                    zebras.append(zb)
            continue
        near = (de > INSIDE_M) & (de <= NEAR_ROAD_M)
        inside = de <= INSIDE_M
        kind2 = kind
        if kind == "footpath" and info["highway"] == "footway" and near.mean() >= NEAR_SHARE:
            kind2 = "sidewalk"
            stats["sidewalk_inferred_km"] += sarc[-1] / 1000
            diag["sidewalk_gap_m"] += list(dc[near] - field.half[kseg[near]])
        if kind in ("footpath", "sidewalk") and inside.mean() >= NEAR_SHARE:
            stats["footway_swallowed_km"] += sarc[-1] / 1000  # тротуар целиком под проезжей частью: ширина велика
            road = segs[int(np.bincount(kseg[inside]).argmax())].info
            diag["swallowed"].append((el["id"], round(float(sarc[-1]), 1), road["osm_id"], road["width"],
                                      road["width_src"]))
        # по площади у собора — булыжник маски (osm_layers.cathedral_square): дорожки там обрезаются
        on_square = np.array([osm_layers.in_square(q) for q in p]) if math.hypot(*p[len(p) // 2]) < 80 else \
            np.zeros(len(p), bool)
        # по площадям-мультиполигонам (osm_layers.squares: площадь Ленина) — мощение маски от газона до газона: лент
        # дорожек там нет (полосы плитки с поребриком легли бы поперёк площади). Только для мешей (lift): коридоры
        # рельефа (corridors, lift=False) — прежние, heightmap от этого не меняется
        if lift and kind == "footpath":
            on_square = on_square | np.array([osm_layers.in_squares(q) for q in p])
        for head in (0, -1):  # продолжение тупика проезжей части — от узла, без обрезки
            if nodes[head] in dead_ends and kind != "crossing":
                idx = range(len(p)) if head == 0 else range(len(p) - 1, -1, -1)
                for i in idx:
                    if not inside[i]:
                        break
                    tucked[i] = True
        keep = (~inside | tucked) & ~on_square & in_zone(p)
        tg = tangents(p)
        in_set = kset.has(el["id"], pts)
        for i0, i1 in runs(keep):
            if sarc[i1] - sarc[i0] < 1.0:
                continue
            sl = slice(i0, i1 + 1)
            info2 = dict(info, kerb=0.0) if kind2 == "sidewalk" and kind == "footpath" else info
            extra = {"inferred": True} if kind2 != kind else {}
            extra["set"] = in_set
            sig = 0.0 if lift else SMOOTH_M.get(kind, 3.0)
            ezl, ezr = (edge_z(p[sl], sarc[sl] - sarc[i0], tg[sl], sgn * info["width"] / 2, sig, z_at) + path_lift
                        for sgn in (1, -1))
            zs = z[sl]
            if info.get("clear_tower"):  # края отмостки тоже не ниже уреза + TOWER_RING_ABOVE_M
                ezl, ezr = (np.maximum(e, water_z(water) + TOWER_RING_ABOVE_M) for e in (ezl, ezr))
            if lift:
                zs, ezl, ezr, up = clear(p[sl], tg[sl], info["width"], zs, ezl, ezr, z_at)
                diag["raised_m"].append(up)
            if not lift and pin[sl].any():
                extra["pin"] = r2(pin[sl], 3)
            elements.append(ribbon(kind2, info2, p[sl], zs, tg[sl], info["width"], extra, ezl, ezr))
            nl = left_of(tg[sl])
            zl, zr = z_at(p[sl] + nl * info["width"] / 2), z_at(p[sl] - nl * info["width"] / 2)
            if kind2 != "trail":
                diag["foot_cross_pct"] += list(np.abs(zl - zr) / info["width"] * 100)
                seg_len = np.r_[0, np.hypot(*np.diff(p[sl], axis=0).T)]
                steep = np.abs(zl - zr) / info["width"] > 0.15
                stats["foot_steep_m"] += float(seg_len[steep].sum())
                stats["foot_m"] += float(seg_len.sum())
    # переходы из узлов OSM (krom_nodes_*.json: highway=crossing на проезжей части); линии footway=crossing — где узла нет
    node_zebras = []
    for node in crossing_nodes():
        on = [s for s in segs if node["id"] in s.nodes]
        m = np.array(geo.to_local(node["lat"], node["lon"]))
        if not on or not in_zone(m[None]).all():
            continue
        zb = zebra({"osm_id": node["id"]}, m, max(on, key=lambda s: s.info["width"]), node.get("tags", {}))
        if zb:
            node_zebras.append(zb)
    elements += node_zebras + [z for z in zebras if not any(
        o["road_osm_id"] == z["road_osm_id"] and math.dist(o["center"][:2], z["center"][:2]) < ZEBRA_W * 2
        for o in node_zebras)]
    stats["possible_crossings_untagged"] = possible_crossings
    for el in elements:  # набор у Крома: проезжие части и их тротуары — по кускам; «зебры» и лестницы — по месту
        if el["kind"] in ("carriageway", "sidewalk") and "seg" in el:
            el["set"] = segs[el["seg"]].set
        elif el["kind"] in ("steps", "crossing") and "set" not in el:
            el["set"] = kset.has(el["osm_id"], [el.get("center") or el["pts"][len(el["pts"]) // 2]])
        el.setdefault("set", False)

    if lift:  # меши: станции прорежены там, где лента и так прямая и ровная
        for el in elements:
            if el["kind"] in ("carriageway", "sidewalk", "footpath") and el.get("mesh"):
                thin(el, z_at)
        stats["path_junctions"] = path_junctions(elements)

    # площадки (стоянки, area:highway) — в маске; кольцо с высотами
    for el in els:
        tags = el.get("tags", {})
        if el["type"] != "way" or not el.get("nodes") or el["nodes"][0] != el["nodes"][-1] or None in el["geometry"]:
            continue
        hit = next((k for k, vals in AREAS if k in tags and (vals is None or tags[k] in vals)), None)
        if not hit and not (tags.get("highway") and tags.get("area") == "yes"):
            continue
        if el["id"] in osm_layers.SQUARE_WAYS:   # площадь-линия: элемент — ниже, из osm_layers.squares
            continue
        ring = geo.open_ring(geo.local_points(el["geometry"]))
        if len(ring) < 3 or not in_zone(np.array([geo.centroid(ring)]))[0]:
            continue
        mat = MATERIAL.get(tags.get("surface"), "asphalt" if tags.get("amenity") == "parking" else "tiles")
        elements.append({"kind": "area", "osm_id": el["id"], "tag": f"{hit or 'highway'}={tags.get(hit or 'highway')}",
                         "material": mat, "area_m2": round(abs(geo.signed_area(ring))),
                         "ring": r2(np.c_[np.array(ring), z_at(ring)]), "cell": cell_of(geo.centroid(ring)),
                         "mesh": False, "set": False})
    outer, holes, r = square
    elements.append({"kind": "area", "osm_id": osm_layers.SQUARE_WAY, "tag": "площадь у собора (cathedral_square)",
                     "material": MATERIAL[osm_layers.SQUARE_SURFACE], "ring": r2(np.c_[np.array(outer), z_at(outer)]),
                     "holes": [r2(h) for h in holes], "radius_m": r, "cell": cell_of((0.0, 0.0)), "mesh": False,
                     "set": True})
    for sid, name, outers, holes, surface, _ in osm_layers.squares():   # площади-мультиполигоны: мощение в маске
        ring = list(max(outers, key=len))
        c = geo.centroid(ring)
        if not in_zone(np.array([c]))[0]:
            continue
        area = sum(abs(geo.signed_area(list(o))) for o in outers) - sum(abs(geo.signed_area(list(h))) for h in holes)
        elements.append({"kind": "area", "osm_id": sid, "tag": f"площадь «{name}» (osm_layers.squares)" if name else
                         "площадь-мультиполигон (osm_layers.squares)", "material": MATERIAL.get(surface, "tiles"),
                         "area_m2": round(area), "ring": r2(np.c_[np.array(ring), z_at(ring)]),
                         "holes": [r2(h) for h in holes], "cell": cell_of(c), "mesh": False, "set": False})
    return els, elements, segs, {"stats": stats, "diag": diag}


def steps(info, pts, z_at):
    p, sarc = densify(pts)
    L = float(sarc[-1])
    if L < 0.5 or not (in_zone(np.array([pts[0]])) | in_zone(np.array([pts[-1]]))).any():
        return []
    z0, z1 = (float(v) for v in z_at([pts[0], pts[-1]]))
    dz = z1 - z0
    n = max(2, round(abs(dz) / RISE_M))
    flat = abs(dz) < DEM_FLAT * L * RISE_M / TREAD_M
    agree = None
    if info.get("incline") in ("up", "down") and abs(dz) > 0.3:
        agree = (dz > 0) == (info["incline"] == "up")
    z = z0 + (z1 - z0) * sarc / L
    el = ribbon("steps", info, p, z, tangents(p), info["width"], {
        "n": n, "rise": round(abs(dz) / n, 3), "tread": round(L / n, 3), "up_end": 1 if dz > 0 else 0,
        "dem_flat": bool(flat), "incline": info.get("incline"), "incline_agrees": agree,
        "handrail": info.get("handrail")})
    el["mesh"] = not flat  # лестницу, которой рельеф не видит, геометрией пока не строим (висела бы над склоном)
    return [el]


UNMARKED = {"unmarked", "no"}   # crossing / crossing:markings без разметки
BICOLOUR = "zebra:bicolour"     # белые полосы с жёлтыми промежутками (обычная «зебра» Пскова в OSM)


def crossing_nodes():
    """Узлы highway=crossing из самой свежей выгрузки refs/osm/krom_nodes_*.json (нет её — пусто)."""
    try:
        nodes = geo.load_elements(geo.latest("krom_nodes_*.json"))
    except FileNotFoundError:
        return []
    return [e for e in nodes if e["type"] == "node" and e.get("tags", {}).get("highway") == "crossing"]


def zebra(info, m, seg, tags=None):
    """«Зебра» поперёк проезжей части seg у точки m: полосы вдоль оси дороги (1.14.1); у zebra:bicolour промежутки —
    жёлтые (yellow). Узел без разметки — None."""
    tags = tags or {}
    if tags.get("crossing") in UNMARKED or tags.get("crossing:markings") in UNMARKED:
        return None
    p, sarc, z = seg.full
    tg = tangents(p)
    i = int(np.argmin(np.hypot(*(p - m).T)))
    t = tg[i]
    c = p[i] + t * float(np.dot(m - p[i], t))
    nl = left_of(t[None])[0]
    w = seg.info["width"]
    n = max(1, int((w + GAP_M) // (STRIPE_M + GAP_M)))
    span = n * STRIPE_M + (n - 1) * GAP_M
    bicolour = tags.get("crossing:markings") == BICOLOUR
    stripes, yellow = [], []

    def quad(u0, u1):
        q = [c + nl * u0 - t * ZEBRA_W / 2, c + nl * u0 + t * ZEBRA_W / 2, c + nl * u1 + t * ZEBRA_W / 2,
             c + nl * u1 - t * ZEBRA_W / 2]
        return r2([[v[0], v[1], float(z[i])] for v in q], 3)

    for k in range(n):
        u0 = -span / 2 + k * (STRIPE_M + GAP_M)
        stripes.append(quad(u0, u0 + STRIPE_M))
        if bicolour and k < n - 1:
            yellow.append(quad(u0 + STRIPE_M, u0 + STRIPE_M + GAP_M))
    return {"kind": "crossing", "osm_id": info["osm_id"], "road_osm_id": seg.info["osm_id"],
            "crossing": tags.get("crossing"), "markings": tags.get("crossing:markings"),
            "center": r2([c[0], c[1], float(z[i])], 3), "dir": r2(t, 4), "road_width": round(w, 2),
            "zebra_width": ZEBRA_W, "stripes": stripes, "yellow": yellow, "cell": cell_of(c), "mesh": True}


# ---------- коридоры для рельефа (terrain_krom.road_bed) ----------

def corridors(z_at, exclude=(), water=None):
    """Коридоры лент для подгонки рельефа: [{group: car | path, pts (n × 2, станции ≤ 0,5 м), z (n) — профиль оси
    без осадки, allow (n) — на сколько сверх обычного предела можно поднять землю (подъезды к мостам), half —
    полуширина, м, kerb, band — полоса за бордюром на его высоте, id}]; water — урез в единицах z_at. Проезжая часть — целые куски
    до обрезки у перекрёстков (площадки перекрёстков внутри них); дорожки и тротуары — как в build (без грунтовых троп,
    лестниц и линий из exclude)."""
    _, elements, segs, _ = build(z_at, lift=False, water=water)
    out = []
    for s in segs:
        p, sarc, z = s.full
        if not in_zone(p).any():
            continue
        q, qs = densify([tuple(v) for v in p], 0.5)
        band = max([KERB_BAND_M] + [w for w in s.info["sidewalk"] if w > 0]) if s.info["kerb"] > 0 else 0.0
        out.append({"group": "car", "pts": q, "z": np.interp(qs, sarc, z), "allow": np.interp(qs, sarc, s.pin),
                    "half": s.hw_half,
                    "kerb": s.info["kerb"], "band": band, "id": s.info["osm_id"]})
    for el in elements:
        if (el["kind"] not in ("footpath", "sidewalk") or el.get("generated") or el["osm_id"] in exclude
                or el.get("layer", 0) < 0):  # под мостом или улицей (layer < 0) — рельеф не трогаем
            continue
        P = np.array(el["pts"])
        q, qs = densify([tuple(v) for v in P[:, :2]], 0.5)
        s0 = np.r_[0, np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))]
        allow = np.interp(qs, s0, el["pin"]) if "pin" in el else np.zeros(len(q))
        out.append({"group": "path", "pts": q, "z": np.interp(qs, s0, P[:, 2]), "allow": allow,
                    "half": el["width"] / 2,
                    "kerb": 0.0, "band": 0.0, "id": el["osm_id"]})
    return out


# ---------- меши клеток ----------

class Part:
    """Сетка одного материала клетки: вершины (м от начала клетки), нормали, UV0 (мировые X, Y), UV1, цвет, треугольники.
    Порядок вершин — как в GeometryScript: нормаль грани = −(v1 − v0) × (v2 − v0) (wall_mesh.Mesh)."""

    def __init__(self):
        self.v, self.n, self.uv, self.uv1, self.c, self.t = [], [], [], [], [], []

    def tri(self, pts, out, uv1=None, color=(1.0, 1.0, 1.0, 1.0), origin=(0.0, 0.0), uv=None):
        a, b, c = (np.asarray(q, dtype=np.float64) for q in pts)
        cr = np.cross(b - a, c - a)
        k = float(np.linalg.norm(cr))
        if k < 1e-9:
            return
        order = (0, 2, 1) if float(np.dot(cr, out)) > 0 else (0, 1, 2)
        nrm = np.asarray(out, dtype=np.float64)
        nrm = nrm / (np.linalg.norm(nrm) or 1.0)
        i = len(self.v)
        for j in order:
            q = pts[j]
            self.v.append([round(q[0] - origin[0], 3), round(q[1] - origin[1], 3), round(q[2], 3)])
            self.n.append([round(float(v), 4) for v in nrm])
            self.uv.append([round(float(v), 3) for v in (uv[j] if uv else (q[0], q[1]))])
            self.uv1.append([round(float(v), 3) for v in (uv1[j] if uv1 else (0.0, 0.0))])
            self.c.append([round(float(v), 3) for v in color])
        self.t.append([i, i + 1, i + 2])

    def quad(self, pts, out, uv1=None, color=(1.0, 1.0, 1.0, 1.0), origin=(0.0, 0.0), uv=None):
        a, b, c, d = pts
        u = uv1 or [None] * 4
        w = uv or [None] * 4
        self.tri([a, b, c], out, [u[0], u[1], u[2]] if uv1 else None, color, origin, [w[0], w[1], w[2]] if uv else None)
        self.tri([a, c, d], out, [u[0], u[2], u[3]] if uv1 else None, color, origin, [w[0], w[2], w[3]] if uv else None)


UP = (0.0, 0.0, 1.0)


def wall_uv(a, b):
    """UV вертикальной грани a → b (точки (x, y, z)): u — вдоль ребра в метрах от мирового нуля, v — высота."""
    t = np.array(b[:2], dtype=np.float64) - np.array(a[:2], dtype=np.float64)
    t = t / (np.linalg.norm(t) or 1.0)
    return lambda q: (float(q[0] * t[0] + q[1] * t[1]), float(q[2]))


def vertical(part, a, b, z_top_a, z_top_b, z_bot_a, z_bot_b, out, o):
    pts = [(a[0], a[1], z_bot_a), (b[0], b[1], z_bot_b), (b[0], b[1], z_top_b), (a[0], a[1], z_top_a)]
    f = wall_uv(a, b)
    part.quad(pts, (out[0], out[1], 0.0), origin=o, uv=[f(q) for q in pts], color=NO_MARKING)


def cut_edge(edge, out, z, s, gaps):
    """Край ленты с промежутками gaps ([s0, s1] по оси): станции на границах вставлены; возвращает (край, наружу,
    высоты, пропуск отрезка i → i + 1) или None, если пропущено всё."""
    cuts = [v for g in gaps for v in g if s[0] < v < s[-1]]
    s2 = np.unique(np.concatenate([s, cuts]))
    e2 = np.c_[np.interp(s2, s, edge[:, 0]), np.interp(s2, s, edge[:, 1])]
    o2 = np.c_[np.interp(s2, s, out[:, 0]), np.interp(s2, s, out[:, 1])]
    mid = (s2[:-1] + s2[1:]) / 2
    hole = np.zeros(len(mid), bool)
    for a, b in gaps:
        hole |= (mid > a) & (mid < b)
    if hole.all():
        return None
    return e2, o2, np.interp(s2, s, z), hole


def kerb_w(h):
    """Ширина бортового камня высотой h над полотном."""
    return KERB_W_LOW_M if h <= 0.10 + 1e-6 else KERB_W_M


def edge_strip(parts, mat, edge, z, outward, width, h, bury, o, faces=("in", "top", "out"), hole=None):
    """Бордюр / поребрик вдоль края edge (n × 2) с высотой полотна z: полоса шириной width наружу (outward, n × 2),
    верх на h над полотном, внутренняя грань от полотна, внешняя — вниз на bury; hole[i] — отрезок i → i + 1 пропустить."""
    p = parts[mat]
    e2 = edge + outward * width
    for i in range(len(edge) - 1):
        if hole is not None and hole[i]:
            continue
        a, b, a2, b2 = edge[i], edge[i + 1], e2[i], e2[i + 1]
        za, zb = z[i] + h, z[i + 1] + h
        on = tuple(-(outward[i] + outward[i + 1]) / 2)
        if "in" in faces and h > 0:
            vertical(p, a, b, za, zb, z[i], z[i + 1], on, o)
        if "top" in faces:
            p.quad([(a[0], a[1], za), (b[0], b[1], zb), (b2[0], b2[1], zb), (a2[0], a2[1], za)], UP, origin=o)
        if "out" in faces:
            vertical(p, a2, b2, za, zb, za - bury, zb - bury, tuple(-np.array(on)), o)


def mesh_element(parts, el, o):
    """Треугольники элемента в части клетки parts (материал → Part); o — начало клетки."""
    kind = el["kind"]
    if kind in ("carriageway", "footpath", "sidewalk"):
        P = np.array(el["pts"])
        L, R = np.array(el["l"]), np.array(el["r"])
        zl, zr = np.array(el["zl"]), np.array(el["zr"])
        mat = el["material"]
        p = parts[mat]
        car = kind == "carriageway"
        w = el["width"]
        color = NO_MARKING  # дорожки и тротуары: без разметки (белый цвет вершин материал асфальта читал бы как 8 полос)
        if car:
            mk = el.get("markings") or []
            lanes = el.get("lanes") or 0
            center = next((m["type"] for m in mk if m["type"] == "double_solid"), "dashed" if mk else None)
            fwd = int(round((next((m["offset"] for m in mk if m["type"] == "double_solid"), -w / 2) + w / 2)
                            / (w / lanes))) if mk and lanes else 0
            color = (lanes / 8.0 if mk else 0.0, fwd / 8.0, {"double_solid": 1.0, "dashed": 0.5}.get(center, 0.0),
                     min(w / 32.0, 1.0))
        s = np.array(el["s"]) if "s" in el else np.r_[0, np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))]
        for i in range(len(P) - 1):  # два квада поперёк: край — ось — край (ось по рельефу, если он не выровнен)
            c0, c1 = (P[i, 0], P[i, 1], P[i, 2]), (P[i + 1, 0], P[i + 1, 1], P[i + 1, 2])
            q = [(L[i][0], L[i][1], zl[i]), (L[i + 1][0], L[i + 1][1], zl[i + 1]), c1, c0]
            p.quad(q, UP, uv1=[(1.0, s[i]), (1.0, s[i + 1]), (0.5, s[i + 1]), (0.5, s[i])], color=color, origin=o)
            q = [c0, c1, (R[i + 1][0], R[i + 1][1], zr[i + 1]), (R[i][0], R[i][1], zr[i])]
            p.quad(q, UP, uv1=[(0.5, s[i]), (0.5, s[i + 1]), (0.0, s[i + 1]), (0.0, s[i])], color=color, origin=o)
        nl = (L - R) / np.maximum(np.linalg.norm(L - R, axis=1, keepdims=True), 1e-9)
        kerb = el.get("kerb", 0.0)
        gaps = el.get("edge_gaps", {})
        for side, edge, out, z in (("l", L, nl, zl), ("r", R, -nl, zr)):
            hole = None
            if gaps.get(side) and not car:  # примыкание дорожки: поребрик и «юбка» прерываются
                cut = cut_edge(edge, out, z, s, gaps[side])
                if cut is None:
                    continue
                edge, out, z, hole = cut
            if car and kerb > 0:  # за бордюром земля на его высоте (terrain_krom.road_bed) — задней грани не нужно
                edge_strip(parts, "concrete", edge, z, out, kerb_w(kerb), kerb, KERB_BURY_M, o, faces=("in", "top"))
            elif kerb > 0.05:   # бортовой камень у дорожки (набережная Великой)
                edge_strip(parts, "concrete", edge, z, out, KERB_W_M, kerb, KERB_BURY_M, o, hole=hole)
            elif kerb > 0:      # поребрик вровень с газоном: верх и внешняя грань (3 см внутренней не видно)
                edge_strip(parts, "concrete", edge, z, out, EDGING_W_M, kerb, KERB_BURY_M, o, faces=("top", "out"),
                           hole=hole)
            else:               # «юбка» вниз — прячет расхождение с Landscape
                for i in range(len(edge) - 1):
                    if hole is not None and hole[i]:
                        continue
                    vertical(p, edge[i], edge[i + 1], z[i], z[i + 1], z[i] - SKIRT_M, z[i + 1] - SKIRT_M,
                             tuple((out[i] + out[i + 1]) / 2), o)
    elif kind == "junction":
        c = el["center"]
        ring = el["ring"]
        p = parts[el["material"]]
        for a, b in zip(ring, ring[1:] + ring[:1]):
            p.tri([c, a, b], UP, uv1=[(0.5, 0.0)] * 3, color=(0.0, 0.0, 0.0, 0.0), origin=o)
        for kb in el["kerbs"]:
            a, b = np.array(kb["pts"])
            mid = (a[:2] + b[:2]) / 2
            t = b[:2] - a[:2]
            nrm = np.array([t[1], -t[0]]) / (np.linalg.norm(t) or 1.0)
            if np.dot(nrm, mid - np.array(c[:2])) < 0:
                nrm = -nrm
            edge_strip(parts, "concrete", np.array([a[:2], b[:2]]), np.array([a[2], b[2]]), np.array([nrm, nrm]),
                       kerb_w(kb["h"]), kb["h"], KERB_BURY_M, o)
    elif kind == "steps" and el.get("mesh"):
        P = np.array(el["pts"])
        L, R = np.array(el["l"]), np.array(el["r"])
        s = np.r_[0, np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))]
        z0, z1 = P[0, 2], P[-1, 2]
        n = el["n"]
        p = parts[el["material"]]
        lo, hi = min(z0, z1), max(z0, z1)
        up_dir = 1 if z1 >= z0 else -1

        def at(arr, sj):
            return np.array([np.interp(sj, s, arr[:, 0]), np.interp(sj, s, arr[:, 1])])

        for k in range(n):  # проступь k: от ступени к ступени вверх; низ — от нижнего конца
            sa = s[-1] * k / n if up_dir > 0 else s[-1] * (n - k) / n
            sb = s[-1] * (k + 1) / n if up_dir > 0 else s[-1] * (n - k - 1) / n
            zt = lo + (k + 1) * (hi - lo) / n
            la, lb, ra, rb = at(L, sa), at(L, sb), at(R, sa), at(R, sb)
            p.quad([(la[0], la[1], zt), (lb[0], lb[1], zt), (rb[0], rb[1], zt), (ra[0], ra[1], zt)], UP, origin=o)
            fwd = (at(P[:, :2], sb) - at(P[:, :2], sa))
            vertical(p, ra, la, zt, zt, zt - (hi - lo) / n - 0.05, zt - (hi - lo) / n - 0.05,
                     tuple(-fwd / (np.linalg.norm(fwd) or 1.0)), o)
            for e0, e1, sgn in ((la, lb, 1), (ra, rb, -1)):  # щёки: от проступи до земли на склоне
                side = (L[0] - R[0]) * sgn
                zg0 = lo + (hi - lo) * k / n - 0.3
                vertical(p, e0, e1, zt, zt, zg0, zg0, tuple(side / (np.linalg.norm(side) or 1.0)), o)
    elif kind == "crossing":
        for q in el["stripes"]:
            parts["marking"].quad([(v[0], v[1], v[2] + ZEBRA_LIFT_M) for v in q], UP, origin=o)
        for q in el.get("yellow", []):  # цвет вершин: жёлтые промежутки двухцветной «зебры»
            parts["marking"].quad([(v[0], v[1], v[2] + ZEBRA_LIFT_M) for v in q], UP, origin=o,
                                  color=(1.0, 0.78, 0.08, 1.0))


def cells(elements):
    """Меши по клеткам для элементов набора (MESH_SCOPE): [{name, origin, parts: {материал: буферы}}]."""
    out = {}
    for el in elements:
        if not el.get("mesh") or el["kind"] in ("trail", "area"):
            continue
        if MESH_SCOPE == "krom" and not el.get("set"):
            continue
        name = el["cell"]
        if name not in out:
            i, j = (int(v) for v in name.replace("p", "+").replace("m", "-").split("_"))
            out[name] = {"origin": (i * CELL_M, j * CELL_M), "parts": defaultdict(Part)}
        mesh_element(out[name]["parts"], el, out[name]["origin"])
    res = []
    for name, cell in sorted(out.items()):
        parts = {k: {"v": p.v, "n": p.n, "uv": p.uv, "uv1": p.uv1, "c": p.c, "t": p.t}
                 for k, p in sorted(cell["parts"].items()) if p.t}
        res.append({"name": name, "origin": list(cell["origin"]), "parts": parts,
                    "triangles": sum(len(v["t"]) for v in parts.values())})
    return res


# ---------- сводка ----------

def pct(v, qs=(50, 90, 99)):
    v = np.asarray(v, dtype=np.float64)
    if not len(v):
        return None
    return {f"p{q}": round(float(np.percentile(v, q)), 3) for q in qs} | {"max": round(float(v.max()), 3),
                                                                           "n": int(len(v))}


def summarize(elements, meta, mesh_cells):
    stats, diag = meta["stats"], meta["diag"]
    kinds = defaultdict(lambda: {"n": 0, "km": 0.0, "set": 0})
    mats = Counter()
    for el in elements:
        k = el["kind"] + (" (inferred)" if el.get("inferred") else "") + (" (generated)" if el.get("generated") else "")
        kinds[k]["n"] += 1
        kinds[k]["set"] += bool(el.get("set"))
        if "pts" in el:
            L = float(np.sum(np.hypot(*np.diff(np.array(el["pts"])[:, :2], axis=0).T)))
            kinds[k]["km"] += L / 1000
            if el.get("mesh"):
                mats[el["material"]] += L / 1000
    st = sorted(diag["car_worst"], key=lambda t: -t[0])[:8]
    steps_ = [el for el in elements if el["kind"] == "steps"]
    agree = [el["incline_agrees"] for el in steps_ if el["incline_agrees"] is not None]
    tri_mat = Counter()
    for c in mesh_cells:
        for k, v in c["parts"].items():
            tri_mat[k] += len(v["t"])
    return {
        "kinds": {k: {"n": v["n"], "km": round(v["km"], 2), "set": v["set"]} for k, v in sorted(kinds.items())},
        "km_by_material": {k: round(v, 2) for k, v in mats.most_common()},
        "mesh_scope": MESH_SCOPE, "mesh_cells": len(mesh_cells), "mesh_triangles": sum(tri_mat.values()),
        "mesh_triangles_by_material": dict(tri_mat.most_common()),
        "car_cross_slope_pct": pct(diag["car_cross_pct"]),
        "car_cross_steeper_4pct_share": round(float(np.mean(np.asarray(diag["car_cross_pct"]) > 4)), 3)
        if diag["car_cross_pct"] else None,
        "car_edge_lift_m": pct(diag["car_lift_m"]),
        "car_profile_minus_heightmap_m": pct(diag["car_fill_m"], (1, 50, 99)),
        "car_worst_cross_dz_m": [{"dz": round(a, 2), "osm_id": b, "name": c} for a, b, c in st],
        "foot_cross_slope_pct": pct(diag["foot_cross_pct"]),
        "foot_steeper_15pct_m": round(stats["foot_steep_m"]), "foot_m": round(stats["foot_m"]),
        "sidewalk_inferred_km": round(stats["sidewalk_inferred_km"], 2),
        "sidewalk_centre_from_carriageway_edge_m": pct(diag["sidewalk_gap_m"], (10, 50, 90)),
        "footway_swallowed_km": round(stats["footway_swallowed_km"], 2),
        "footway_nudged_stations": int(stats["footway_nudged_m"]),
        "path_junctions": int(stats["path_junctions"]),
        "footway_swallowed_ids": diag["swallowed"][:20],
        "steps": {"n": len(steps_), "dem_flat": sum(el["dem_flat"] for el in steps_),
                  "incline_checked": len(agree), "incline_agrees": sum(agree)},
        "zebras": sum(el["kind"] == "crossing" for el in elements),
        "clear_raised_m": pct(diag["raised_m"], (50, 90, 99)),
        "possible_crossings_untagged": int(stats["possible_crossings_untagged"]),
    }


# ---------- превью ----------

MASK_RGB = {"Earth": (150, 120, 85), "Paved": (175, 170, 160), "Asphalt": (75, 75, 78), "Built": (190, 120, 110),
            "Gravel": (180, 115, 90), "Shore": (215, 200, 160), "Riprap": (130, 130, 130), "Wood": (140, 100, 60)}
GRASS_RGB, WATER_RGB = (112, 138, 88), (80, 112, 150)
MAT_RGB = {"asphalt": (48, 48, 54), "cobble": (120, 104, 88), "tiles": (214, 204, 186), "concrete": (188, 188, 182),
           "gravel": (196, 104, 72), "earth": (140, 100, 62), "wood": (160, 112, 60)}
KERB_RGB, MARK_RGB, STEPS_RGB, AREA_RGB, SET_RGB = (245, 245, 240), (255, 255, 255), (205, 70, 170), (240, 200, 40), \
    (20, 120, 255)


def base_map(hts, rect, k):
    """Маска покрытия (обе) и вода по heightmap, север вверху, k пикселей на метр в прямоугольнике rect."""
    meta = hts.meta
    m1 = np.asarray(Image.open(os.path.join(geo.REPO, meta["mask_texture"]))).astype(np.float64) / 255
    m2 = np.asarray(Image.open(os.path.join(geo.REPO, meta["mask2_texture"]))).astype(np.float64) / 255
    shares = np.concatenate([m1, m2], axis=-1)
    names = list(meta["mask_channels"].values()) + list(meta["mask2_channels"].values())
    cols = np.array([MASK_RGB[n] for n in names], dtype=np.float64)
    rgb = np.array(GRASS_RGB) * (1 - shares.sum(-1, keepdims=True)) + shares @ cols   # [Y, X], как heightmap
    lx0, lx1, ly0, ly1 = hts.rect
    xmin, xmax, ymin, ymax = rect
    w, h = int(round((ymax - ymin) * k)), int(round((xmax - xmin) * k))
    ys = ymin + (np.arange(w) + 0.5) / k
    xs = xmax - (np.arange(h) + 0.5) / k
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    npx = rgb.shape[0]
    rr = np.clip(((Y - ly0) / (ly1 - ly0) * npx).astype(int), 0, npx - 1)
    cc = np.clip(((X - lx0) / (lx1 - lx0) * npx).astype(int), 0, npx - 1)
    img = rgb[rr, cc]
    z = ndimage.map_coordinates(hts.z, [(Y - hts.y0) / hts.dy, (X - hts.x0) / hts.dx], order=1, mode="nearest")
    img[z < meta["water_level_z_m"] + 0.05] = WATER_RGB
    img = 0.55 * img + 0.45 * 200  # бледнее, чтобы геометрия читалась
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


def preview(hts, elements, rect, k, path, detail):
    img = base_map(hts, rect, k)
    d = ImageDraw.Draw(img)
    xmin, xmax, ymin, ymax = rect

    def px(p):
        return ((p[1] - ymin) * k, (xmax - p[0]) * k)

    def strip(el, col):
        L, R = el["l"], el["r"]
        for i in range(len(L) - 1):
            d.polygon([px(L[i]), px(L[i + 1]), px(R[i + 1]), px(R[i])], fill=col)

    order = ("area", "trail", "footpath", "sidewalk", "carriageway", "junction", "steps", "crossing")
    for kind in order:
        for el in (e for e in elements if e["kind"] == kind):
            if kind == "area":
                d.polygon([px(q) for q in el["ring"]], outline=AREA_RGB)
            elif kind == "trail":
                pts = [px(q) for q in el["pts"]]
                for i in range(0, len(pts) - 1, 2):
                    d.line(pts[i:i + 2], fill=MAT_RGB["earth"], width=max(1, round(el["width"] * k)))
            elif kind in ("footpath", "sidewalk", "carriageway"):
                col = MAT_RGB[el["material"]]
                if kind == "sidewalk":
                    col = tuple(min(255, c + 18) for c in col)
                strip(el, col)
                if detail and el.get("set"):
                    for side in ("l", "r"):
                        d.line([px(q) for q in el[side]], fill=SET_RGB, width=1)
                elif el["kerb"] > 0 and detail:
                    for side in ("l", "r"):
                        d.line([px(q) for q in el[side]], fill=KERB_RGB, width=1)
                if kind == "carriageway" and detail:
                    P = np.array(el["pts"])[:, :2]
                    nl = left_of(tangents(P))
                    s = np.array(el["s"])
                    for mk in el["markings"]:
                        line = P + nl * mk["offset"]
                        if mk["type"] == "double_solid":
                            for o in (-0.12, 0.12):
                                d.line([px(q) for q in line + nl * o], fill=MARK_RGB, width=1)
                        else:
                            on = (s % sum(DASH_M)) < DASH_M[0]
                            for i0, i1 in runs(on):
                                if i1 > i0:
                                    d.line([px(q) for q in line[i0:i1 + 1]], fill=MARK_RGB, width=1)
            elif kind == "junction":
                d.polygon([px(q) for q in el["ring"]], fill=MAT_RGB[el["material"]],
                          outline=SET_RGB if detail and el.get("set") else None)
                if detail:
                    for kb in el["kerbs"]:
                        d.line([px(q) for q in kb["pts"]], fill=KERB_RGB, width=1)
            elif kind == "steps":
                strip(el, STEPS_RGB if el.get("mesh") else (230, 170, 215))
                if detail and el.get("mesh"):
                    P, L, R = np.array(el["pts"])[:, :2], np.array(el["l"]), np.array(el["r"])
                    s = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
                    for j in range(1, el["n"]):
                        sj = s[-1] * j / el["n"]
                        a = [np.interp(sj, s, L[:, c]) for c in (0, 1)]
                        b = [np.interp(sj, s, R[:, c]) for c in (0, 1)]
                        d.line([px(a), px(b)], fill=(90, 20, 70), width=1)
            elif kind == "crossing":
                for q in el["stripes"]:
                    d.polygon([px(v) for v in q], fill=MARK_RGB)
                for q in el.get("yellow", []):
                    d.polygon([px(v) for v in q], fill=(250, 205, 40))
    d.rectangle([px((ZONE_M, -ZONE_M)), px((-ZONE_M, ZONE_M))], outline=(200, 40, 40), width=2)
    try:
        font = ImageFont.truetype("arial.ttf", 18 if detail else 14)
    except OSError:
        font = ImageFont.load_default()
    legend = [("проезжая часть (асфальт)", MAT_RGB["asphalt"]), ("булыжник", MAT_RGB["cobble"]),
              ("тротуар / плитка", MAT_RGB["tiles"]), ("отсев", MAT_RGB["gravel"]), ("грунт (маска)", MAT_RGB["earth"]),
              ("лестница", STEPS_RGB), ("стоянки, площадь (маска)", AREA_RGB), ("меши: дорожки у Крома", SET_RGB),
              (f"зона: квадрат ±{ZONE_M:.0f} м", (200, 40, 40))]
    y = 10
    d.rectangle([6, 6, 300, 14 + 24 * len(legend)], fill=(255, 255, 255))
    for text, col in legend:
        d.rectangle([12, y + 2, 36, y + 18], fill=col, outline=(0, 0, 0))
        d.text((44, y), text, fill=(0, 0, 0), font=font)
        y += 24
    img.save(path)


def main():
    hts = Heights()
    els, elements, segs, meta = build(hts.at)
    inv = inventory(els, hts.rect)
    mesh_cells = cells(elements)
    summary = summarize(elements, meta, mesh_cells)
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR)
    out = {
        "script": "scripts/roads_mesh.py", "generated": datetime.date.today().isoformat(),
        "units": "м; X — север, Y — восток, Z — от земли у собора (D-013); l — слева по ходу линии OSM",
        "sources": {"osm": os.path.relpath(geo.latest("krom_2*.json"), geo.REPO).replace("\\", "/"),
                    "heightmap": hts.meta["heightmap"], "heightmap_generated": hts.meta.get("generated")},
        "params": {"zone_m": ZONE_M, "cell_m": CELL_M, "step_m": STEP_M, "smooth_m": SMOOTH_M, "corner_m": CORNER_M,
                   "sink_m": {"road": ROAD_SINK_M, "path": PATH_SINK_M}, "lane_m": osm_layers.LANE_M,
                   "kerb_m": KERB_M, "edging_m": EDGING_M, "sidewalk_m": osm_layers.SIDEWALK_M,
                   "near_road_m": NEAR_ROAD_M, "rise_m": RISE_M, "dash_m": DASH_M, "marking_wear": MARKING_WEAR,
                   "marked": MARKED, "zebra": [ZEBRA_W, STRIPE_M, GAP_M], "mesh_scope": MESH_SCOPE,
                   "set_ways": SET_WAYS},
        "inventory": inv, "stats": summary, "elements": elements, "cells": mesh_cells,
    }
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    ext = hts.rect
    preview(hts, elements, ext, 2048 / (ext[1] - ext[0]), os.path.join(OUT_DIR, "roads_top.png"), detail=False)
    preview(hts, elements, (-400.0, 480.0, -380.0, 380.0), 2.5, os.path.join(OUT_DIR, "roads_top_krom.png"),
            detail=True)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
