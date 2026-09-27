"""osm_layers.py — слои подложки из выгрузки OSM: вода, дороги, тропы, здания, исторические здания, стены (D-012).

Чистый Python без `unreal`. Раньше жил внутри underlay_osm.py (плоские меши на Z = 0), потом подложка стала
текстурой на Landscape (terrain_krom.py рисует). С M4 материал Landscape берёт не подложку, а покрытие земли —
ground() (D-025). Ширина и покрытие линий highway — way_width() и way_surface(): одни и те же для маски покрытия
и для геометрии дорог roads_mesh.py (D-038); правки по фото — WAY_WIDTH, WAY_OVERRIDE, двор Крома — YARD_SURFACE,
площадь у собора — cathedral_square(), площади OSM (мультиполигоны — площадь Ленина, замкнутые линии SQUARE_WAYS —
Октябрьская площадь) — squares(), площадки по аэрофото (асфальт Октябрьской площади) — TRACED_AREAS.
"""
import functools
import math

import krom_geo as geo

BBOX = (57.8140, 28.3120, 57.8300, 28.3450)  # как в выгрузке Overpass (D-012)

# слой → цвет (linear RGB); порядок = порядок отрисовки
LAYERS = {
    "Water":    (0.03, 0.12, 0.35),
    "Path":     (0.30, 0.27, 0.22),
    "Road":     (0.05, 0.05, 0.05),
    "Building": (0.55, 0.55, 0.55),
    "Historic": (0.85, 0.55, 0.12),
    "Wall":     (0.75, 0.05, 0.03),
}
GROUND_COLOR = (0.20, 0.24, 0.16)

ROAD_WIDTH = {  # м, если нет тега width
    "primary": 9, "secondary": 8, "tertiary": 7, "residential": 5, "unclassified": 5,
    "living_street": 4, "pedestrian": 4, "service": 3,
}
PATH_WIDTH = {"footway": 1.5, "path": 1.2, "steps": 1.5, "cycleway": 1.5, "track": 2.5, "bridleway": 1.5}
WALL_WIDTH = 4.0
HISTORIC_BUILDINGS = {"cathedral", "church", "chapel", "temple", "tower", "monastery"}


# вода на своей отметке — не река: рельеф режет «Water» до уреза Великой (terrain_krom), и фонтан-брызгальник
# в сквере на Завеличье (way 1284115091) стал котлованом 60 м глубиной 8 м (владелец: «яма, в реальности нет»)
STANDING_WATER = {"pond", "basin", "reflecting_pool", "fountain", "pool", "wastewater", "reservoir"}


def standing_water(tags):
    return (tags.get("amenity") == "fountain" or tags.get("leisure") == "swimming_pool"
            or tags.get("water") in STANDING_WATER)


def is_closed(el):
    return el.get("nodes") and el["nodes"][0] == el["nodes"][-1] and None not in el["geometry"]


def width_of(tags, default):
    try:
        return float(tags.get("width", "").split()[0])
    except (ValueError, IndexError):
        return default


def bbox_rect():
    """Прямоугольник выгрузки в локальных метрах: (xmin, xmax, ymin, ymax)."""
    (xmin, ymin), (xmax, ymax) = geo.to_local(BBOX[0], BBOX[1]), geo.to_local(BBOX[2], BBOX[3])
    return xmin, xmax, ymin, ymax


def collect(rect=None):
    """Слои из самых свежих refs/osm/krom_*.json и krom_water_*.json.

    Возвращает (polys, lines): слой → список колец (x, y) и слой → список (ломаная, ширина, м).
    Всё обрезано по прямоугольнику rect (по умолчанию — bbox выгрузки).
    """
    rect = rect or bbox_rect()
    main = geo.load_elements(geo.latest("krom_2*.json"))
    water = geo.water_rings(geo.load_elements(geo.latest("krom_water_*.json")))
    polys = {k: [] for k in LAYERS}
    lines = {k: [] for k in LAYERS}

    def pieces(pts):  # куски ломаной внутри подложки (Overpass отдаёт и первую точку за границей)
        return [c for part in geo.split_on_none(pts) for c in geo.clip_line_to_rect(part, *rect)]

    for el in main:
        tags = el.get("tags", {})
        if el["type"] == "way":
            pts = geo.local_points(el["geometry"])
            b, hw = tags.get("building"), tags.get("highway")
            if b and b != "no" and is_closed(el):
                historic = "historic" in tags or b in HISTORIC_BUILDINGS or tags.get("man_made") == "tower"
                polys["Historic" if historic else "Building"].append(pts)
            elif tags.get("barrier") == "city_wall":
                lines["Wall"] += [(part, WALL_WIDTH) for part in pieces(pts)]
            elif hw and tags.get("tunnel") != "yes" and not WAY_OVERRIDE.get(el["id"], {}).get("skip"):
                if tags.get("area") == "yes" and is_closed(el):
                    polys["Road"].append(pts)
                elif hw in ROAD_WIDTH:
                    lines["Road"] += [(part, width_of(tags, ROAD_WIDTH[hw])) for part in pieces(pts)]
                elif hw in PATH_WIDTH:
                    lines["Path"] += [(part, width_of(tags, PATH_WIDTH[hw])) for part in pieces(pts)]
            elif (tags.get("natural") == "water" and is_closed(el) and el["id"] not in water["ids"]
                  and not standing_water(tags)):
                polys["Water"].append(pts)
        elif el["type"] == "relation" and tags.get("building") and tags.get("building") != "no":
            outers = [m for m in el["members"] if m["role"] == "outer" and m.get("geometry") and None not in m["geometry"]]
            ways = [([(p["lat"], p["lon"]) for p in m["geometry"]], geo.local_points(m["geometry"])) for m in outers]
            polys["Historic" if "historic" in tags else "Building"] += geo.assemble_rings(ways)

    polys["Water"] += water["rings"]
    # всё обрезаем по подложке: здания на границе Overpass отдаёт целиком (с соседней внешней точкой)
    polys = {k: [c for c in (geo.clip_to_rect(geo.open_ring(r), *rect) for r in v) if c] for k, v in polys.items()}
    return polys, lines


def relation_ring(rel_id):
    """Самое длинное внешнее кольцо мультиполигона OSM rel_id в локальных метрах (x, y) — например, контур
    Довмонтова города (4060635) или Крома (4060616)."""
    main = geo.load_elements(geo.latest("krom_2*.json"))
    rel = next(e for e in main if e["type"] == "relation" and e["id"] == rel_id)
    outers = [m for m in rel["members"] if m["role"] == "outer" and m.get("geometry") and None not in m["geometry"]]
    ways = [([(p["lat"], p["lon"]) for p in m["geometry"]], geo.local_points(m["geometry"])) for m in outers]
    return max(geo.assemble_rings(ways), key=len)


# ---------- покрытие земли для материала Landscape (M4) ----------

# классы покрытия; всё, что не попало ни в один, — трава. Две маски RGBA: GROUND — первая, GROUND2 — вторая (D-029)
GROUND = ("Earth", "Paved", "Asphalt", "Built")
GROUND2 = ("Gravel", "Shore", "Riprap", "Wood")  # отсев троп, песок и галька у уреза, каменная наброска, настилы
# порядок отрисовки (поздний перекрывает): полоса у уреза и наброска (terrain_krom) ложатся после площадок, до линий
PAINT = ("Shore", "Earth", "Gravel", "Riprap", "Paved", "Asphalt", "Wood", "Built")
SURFACE = {  # тег surface → класс
    "asphalt": "Asphalt", "chipseal": "Asphalt",
    "paving_stones": "Paved", "sett": "Paved", "stone": "Paved", "cobblestone": "Paved", "paved": "Paved",
    "unhewn_cobblestone": "Paved", "concrete": "Paved", "concrete:plates": "Paved", "bricks": "Paved",
    "ground": "Earth", "dirt": "Earth", "earth": "Earth", "unpaved": "Earth",
    "compacted": "Gravel", "gravel": "Gravel", "fine_gravel": "Gravel", "pebblestone": "Gravel",
    "sand": "Shore", "wood": "Wood",
}
SURFACE_DEFAULT = {  # highway без surface → класс (тротуары в центре Пскова чаще плитка, чем асфальт)
    "footway": "Paved", "steps": "Paved", "pedestrian": "Paved", "living_street": "Paved",
    "path": "Earth", "track": "Earth", "bridleway": "Earth",
}
AREA_CLASS = (  # (тег, значения) замкнутого контура → класс
    ("amenity", {"parking"}, "Asphalt"),
    ("amenity", {"marketplace"}, "Paved"),
    ("place", {"square"}, "Paved"),
    ("landuse", {"construction", "brownfield"}, "Earth"),
    ("natural", {"beach", "sand", "shingle"}, "Shore"),
    ("natural", {"bare_rock"}, "Riprap"),
    ("leisure", {"playground"}, "Earth"),
)


# ---------- ширина и покрытие линий highway: одни для маски покрытия и геометрии дорог (D-038) ----------

KROM_REL, DOVMONT_REL = 4060616, 4060635  # контуры OSM: Псковский кром, Довмонтов город
LANE_M = {  # м на полосу, если у проезжей части есть lanes (гип.: 3,5 м — магистрали, 3,0–3,25 — улицы)
    "primary": 3.5, "primary_link": 3.5, "secondary": 3.5, "secondary_link": 3.5, "tertiary": 3.25,
    "tertiary_link": 3.25, "residential": 3.0, "unclassified": 3.0, "living_street": 3.0, "service": 3.0,
}
SIDEWALK_M = 2.5  # тротуар footway=sidewalk и тротуар из тегов дороги без width (гип.; фото img4 — ≈2,5 м)
WAY_WIDTH = {  # м, ширина троп без тега width — по фото (S-42); иначе — по виду
    66656356: 4.0,   # тропа из отсева вдоль Великой под западной стеной Крома
    66789566: 3.0,   # набережная Псковы от Стрелки до Советского моста: ≈3 м (env11 — люди с коляской, S-42)
}
WAY_OVERRIDE = {  # правки по фото там, где тегов OSM не хватает (гип.; D-038)
    # дорога к Великим воротам — в OSM footway без surface; на фото булыжник ≈5,5 м, справа по ходу к воротам
    # (к востоку) тротуар ≈2,5 м за бордюром, слева низкий парапет к газону (img4 — S-34, env16; оценка по людям)
    65775670: dict(kind="carriageway", highway="pedestrian", surface="sett", width=5.5, kerb=0.15,
                   sidewalk=(0.0, 2.5)),
    # проезд Великих ворот сквозь Перси (в OSM footway, tunnel=building_passage): та же дорога, проём 4 м (D-026),
    # без бордюров; за ним во дворе — асфальтовая дорожка 68666634
    68666636: dict(kind="carriageway", highway="pedestrian", surface="sett", width=3.8, kerb=0.0, sidewalk=(0.0, 0.0)),
    # набережная Великой у Довмонтова города: асфальт, бортовой камень к газонному откосу (env15 — S-42); ширина — гип.
    121919089: dict(width=6.0, kerb=0.12),
    # набережная Псковы: в OSM вся — gravel; на фото — серый асфальт с бортовым камнем вдоль Псковы от Стрелки до
    # Советского моста (env08 — Стрелка, 2021; env10, env11 — 2018); отсев — только петли Стрелки (env04, env05)
    66789566: dict(surface="asphalt", kerb=0.08),
    # аудит дорожек (build/paths_audit/paths_audit.md, номера — оттуда; подтверждено координатором 2026-09-26):
    # skip — линии нет ни в маске, ни геометрией; kind="steps" — лестница вместо ленты (связки круче 30 %)
    312786289: dict(skip=True),         # №33: боевой ход стены Стрелки под кровлей (covered, layer=1), не по земле
    312786290: dict(skip=True),         # №39: лестница с площадки у калитки на боевой ход (covered, layer=1)
    955445423: dict(clear_tower="Плоская"),  # №30: отмостка вокруг Плоской — вне тела башни, не ниже уреза + 0,3
    156627272: dict(kind="steps"),      # №257: 38 м, перепад 8,75 м
    904435787: dict(kind="steps"),      # №265: 20 м, перепад 5,35 м
    69178357: dict(kind="steps"),       # №92: продолжение лестницы 69178365, 15 м, перепад 4,3 м
    308580500: dict(kind="steps"),      # №205: 22 м, перепад 5,1 м
    304533773: dict(kind="steps"),      # №182: 21 м, перепад 5,8 м
    96360318: dict(kind="steps"),       # №255: 15 м, перепад 5,2 м
    361786765: dict(surface="ground", width=1.0),  # №122: тупик на газоне у Ольгинского моста — еле заметная тропа
    299833215: dict(width=6.0),         # №72: нижний причал у воды под Довмонтовым городом — широкая мощёная полоса
    69178361: dict(width=6.0),          # №81: нижний причал у Власьевской (продолжение №72)
    304533805: dict(skip=True),         # №190: деревянный настил 2014 г. там, где в 2024 г. встал конец моста
    # ширины дорожек двора Крома и Стрелки — по аэрофото А3 2018 и фото S-42 (оценки аудита, гип.; решение 2026-09-27)
    65775689: dict(width=3.0),          # №4: диагональ от Кутекромы и вдоль северной части двора
    65775608: dict(width=2.5),          # №5: диагональ через газон
    65775711: dict(width=3.0),          # №6: главная дорожка двора вдоль западной стены
    1226677027: dict(width=2.0),        # №8: «V» к западной стене
    259354617: dict(width=4.0),         # №10: проезд вдоль здания и стоянки к собору
    65775622: dict(width=3.0),          # №11: к Средней башне и вдоль Восточной стены к собору
    69178352: dict(width=2.0),          # №12: диагональ к западной стороне собора
    68666638: dict(width=2.0),          # №26: вдоль Персей по краю газона (положение в OSM ±5 м — не правим)
    259326830: dict(width=2.5),         # №32: по газону Стрелки к Плоской
    259326828: dict(width=2.5),         # №34: от круглой площадки к стене
    66789562: dict(width=3.0),          # №37: вдоль стены Стрелки от набережной Псковы к Кутекроме
}
YARD_SURFACE = "asphalt"  # дорожки двора Крома без surface: асфальт вровень с газоном (kutekroma_yard, env17; гип.)
# площадь у собора — булыжник (владелец, D-038; belfry_yard, аэрофото env16, env17): территория храма OSM (landuse=
# religious) без газонов и зданий, не дальше SQUARE_R_M от собора (гип.: отдельного контура площади в OSM нет)
SQUARE_WAY, SQUARE_SURFACE, SQUARE_R_M = 1338866919, "sett", 60.0
# площади-мультиполигоны OSM (relation с place=square или area:highway): ground() берёт только замкнутые линии,
# и площадь Ленина (relation 18345449) была травой с полосками дорожек (владелец: «площадь перед ПсковГУ не такая»).
# Покрытие — тег surface, без него — SQUARE_REL_SURFACE, иначе — как у пешеходной улицы; внутренние кольца
# (газоны) — трава маски
SQUARE_REL_TAGS = (("place", {"square"}), ("area:highway", {"pedestrian", "footway"}))
SQUARE_REL_SURFACE = {18345449: "paving_stones"}  # площадь Ленина: плитка благоустройства 2021 г. (S-136; l18, l09)
# клумбы, которых нет в OSM, — дыры в мощении (трава маски: класса «цветник» нет). Прямоугольник: центр, азимут длинной
# стороны, длина × ширина, м. Площадь Ленина: «историческая клумба», возвращённая в июне 2026 г. на месте плитки
# площадки перед памятником (S-137): вытянута вдоль оси площадки к памятнику (фото n01, n02 — S-137, l09 — S-135),
# центр — на оси площадки между дорожками 65775692 и 65775627 в 27 м к западу от постамента; размеры и место — гип. ±3 м
SQUARE_REL_BEDS = {18345449: (((-316.88, 203.35), 261.8, 16.0, 8.0),)}
# площади — замкнутые линии OSM (не мультиполигоны), только по списку: Октябрьская площадь (владелец: «площадь у ЦУМа —
# где круг и большой памятник?»). Площадка у памятника княгине Ольге (way 96334914: highway=footway +
# area:highway=footway без area=yes) рисовалась линией 1,5 м по контуру, внутри была трава; круг посреди перекрёстка
# (way 363118183: area:highway=footway, barrier=kerb, без highway) не рисовался вовсе. Весь список замкнутых
# area:highway не берём: там настил 2014 г. (304533805, снят), тартан площадки 376526073 и т. п.
# Значение: имя; beds — газоны (дыры, прямоугольники как в SQUARE_REL_BEDS); extra — добавочные внешние кольца.
# Площадка у памятника: мощение на аэрофото Esri Wayback 2022-06 (S-21, S-155; build/oktyabrskaya_refs) доходит на севере до
# x ≈ −627, контур OSM — до −629…−633 (extra, гип. ±1,5 м); в круге OSM (r ≈ 11,5) — площадка памятника с лестницей
# (модель SM_Mark_Olga), газоны с деревьями к юго-западу и востоку от неё (фото o12, o16, o27 — S-154; аэрофото S-155) и
# аллея на юг, к храму Василия на Горке. Газоны — прямоугольники 12 × 5 м в осях памятника (азимут 331°), в 8,5 м
# в стороны от оси (гип. ±2 м)
SQUARE_WAYS = {
    96334914: dict(name="Октябрьская площадь: площадка у памятника княгине Ольге",
                   beds=(((-657.05, 351.22), 331.0, 12.0, 5.0), ((-648.80, 366.09), 331.0, 12.0, 5.0)),
                   extra=(((-627.0, 331.5), (-626.5, 360.0), (-629.6, 360.0), (-633.3, 332.4)),)),
    363118183: dict(name="Октябрьская площадь: круг посреди перекрёстка (островок ⌀12 м, плитка, бортовой камень)"),
}
# площадки, которых нет контуром в OSM, — по аэрофото (гип. ±2 м): класс по surface, в ground() — среди площадок
# (площади squares() и линии дорог ложатся поверх). Октябрьская площадь — один асфальт от тротуара до тротуара (Esri
# Wayback 2022-06, S-21, S-155), а ленты проезжих частей OSM (way_width) оставляли между собой травяные клинья
TRACED_AREAS = (
    ("Октябрьская площадь: проезжая часть перекрёстка", "asphalt",
     ((-546.5, 298.0), (-536.0, 330.0), (-528.0, 350.0), (-530.0, 357.0), (-545.0, 362.0), (-576.0, 368.0),
      (-588.0, 375.0), (-600.0, 381.0), (-617.5, 385.0), (-626.7, 358.3), (-627.1, 331.2), (-640.0, 331.2),
      (-640.0, 317.0), (-628.3, 316.7), (-620.0, 314.2), (-610.8, 310.0), (-601.7, 304.0), (-596.7, 307.5),
      (-590.0, 309.6), (-582.5, 309.2), (-570.0, 305.0), (-560.0, 300.0))),
)


@functools.lru_cache(maxsize=None)
def _elements():
    return tuple(geo.load_elements(geo.latest("krom_2*.json")))


@functools.lru_cache(maxsize=None)
def krom_ring():
    return tuple(relation_ring(KROM_REL))


def point_in(p, ring):
    x, y, inside = p[0], p[1], False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _num(s):
    try:
        return float(str(s).split(";")[0].replace(",", ".").split()[0])
    except (ValueError, IndexError, TypeError):
        return None


LANE_MIN_M = 2.75       # ужимая проезжую часть по тротуарам, не уже стольких метров на полосу
FIT_BAND = (0.35, 3.0)  # точки тротуара от 0,35 полуширины до полуширины + 3 м от оси считаются «у самого края»
FIT_MIN_POINTS = 5      # линия footway участвует, если в этой полосе у неё столько точек через 2 м (≈10 м вдоль)
FIT_GAP_M = 0.25        # от края тротуара до края проезжей части — бордюр и зазор


@functools.lru_cache(maxsize=None)
def _sidewalk_fit():
    """Ширина проезжей части с lanes, ужатая по отдельно нарисованным тротуарам OSM: {id линии: ширина, м}.

    lanes × LANE_M местами шире улицы: тротуары OSM ложатся под полотно (Леона Поземского на севере — 240 м,
    build/research_roads.md). Для каждой проезжей части с lanes: точки линий footway (не crossing) через 2 м в полосе
    FIT_BAND от оси, у линий с ≥ FIT_MIN_POINTS таких точек; полуширина — 30-й процентиль расстояния до оси минус
    половина ширины тротуара и FIT_GAP_M. Ширина — только если она меньше lanes × LANE_M."""
    import numpy as np
    els = [e for e in _elements() if e["type"] == "way" and e.get("tags", {}).get("highway")]
    feet = []
    for e in els:
        t = e["tags"]
        if t["highway"] != "footway" or t.get("footway") == "crossing" or t.get("bridge") or t.get("tunnel"):
            continue
        fw = SIDEWALK_M if t.get("footway") == "sidewalk" else (_num(t.get("width")) or PATH_WIDTH["footway"])
        for part in geo.split_on_none(geo.local_points(e["geometry"])):
            pts = []
            for a, b in zip(part, part[1:]):
                n = max(1, int(math.dist(a, b) // 2.0))
                pts += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
            if pts:
                feet.append((np.array(pts), fw))
    out = {}
    for e in els:
        t = e["tags"]
        hw, lanes = t["highway"], _num(t.get("lanes"))
        if hw not in LANE_M or not lanes or t.get("width") or t.get("bridge") or t.get("area") == "yes":
            continue
        w0 = lanes * LANE_M[hw]
        line = np.array([p for p in geo.local_points(e["geometry"]) if p])
        if len(line) < 2:
            continue
        lo, hi = line.min(axis=0) - (w0 / 2 + 4), line.max(axis=0) + (w0 / 2 + 4)
        a, b = line[:-1], line[1:]
        ab = b - a
        L2 = np.maximum((ab ** 2).sum(1), 1e-9)
        vals = []
        for pts, fw in feet:
            m = (pts[:, 0] >= lo[0]) & (pts[:, 0] <= hi[0]) & (pts[:, 1] >= lo[1]) & (pts[:, 1] <= hi[1])
            if m.sum() < FIT_MIN_POINTS:
                continue
            q = pts[m]
            tt = np.clip(((q[:, None, :] - a[None]) * ab[None]).sum(2) / L2[None], 0.0, 1.0)
            d = np.hypot(*(q[:, None, :] - a[None] - tt[..., None] * ab[None]).transpose(2, 0, 1)).min(1)
            band = (d >= FIT_BAND[0] * w0 / 2) & (d <= w0 / 2 + FIT_BAND[1])
            if band.sum() >= FIT_MIN_POINTS:
                vals += list(d[band] - fw / 2 - FIT_GAP_M)
        if len(vals) >= FIT_MIN_POINTS:
            out[e["id"]] = round(2 * float(np.percentile(vals, 30)), 2)
    return out


def way_width(el):
    """(ширина, м; откуда) линии highway: WAY_OVERRIDE, WAY_WIDTH, тег width, lanes × LANE_M у проезжих частей,
    SIDEWALK_M у тротуаров, иначе ROAD_WIDTH / PATH_WIDTH по виду; вида без ширины — (None, None)."""
    tags = el.get("tags", {})
    hw = tags.get("highway") or ""
    ov = WAY_OVERRIDE.get(el["id"], {})
    if "width" in ov:
        return float(ov["width"]), "фото (гип.)"
    if el["id"] in WAY_WIDTH:
        return WAY_WIDTH[el["id"]], "WAY_WIDTH (фото)"
    w = _num(tags.get("width"))
    if w:
        return w, "width"
    lanes = _num(tags.get("lanes"))
    if hw in LANE_M and lanes:
        fit = _sidewalk_fit().get(el["id"])
        if fit and fit < lanes * LANE_M[hw]:
            return max(fit, lanes * LANE_MIN_M), "lanes, ужата по тротуарам OSM (гип.)"
        return lanes * LANE_M[hw], "lanes × LANE_M (гип.)"
    if hw == "footway" and tags.get("footway") == "sidewalk":
        return SIDEWALK_M, "SIDEWALK_M (гип.)"
    w = ROAD_WIDTH.get(hw) or ROAD_WIDTH.get(hw.replace("_link", "")) or PATH_WIDTH.get(hw)
    return (float(w), "ROAD_WIDTH / PATH_WIDTH") if w else (None, None)


def way_surface(el, pts=None):
    """Покрытие (значение тега surface) линии highway с правками: WAY_OVERRIDE, дорожки двора Крома без surface —
    YARD_SURFACE (pts — точки линии, по середине решается «во дворе»). Без покрытия — None."""
    tags = el.get("tags", {})
    ov = WAY_OVERRIDE.get(el["id"], {})
    if "surface" in ov:
        return ov["surface"]
    if tags.get("surface"):
        return tags["surface"]
    ok = [p for p in pts or [] if p]
    if tags.get("highway") in ("footway", "path") and ok and point_in(ok[len(ok) // 2], list(krom_ring())):
        return YARD_SURFACE
    return None


def split_surface(el, line):
    """Куски ломаной line (x, y) с покрытием: [(кусок, surface)] — по surface_split из WAY_OVERRIDE (к северу от X —
    первое покрытие) или целиком way_surface."""
    ov = WAY_OVERRIDE.get(el["id"], {})
    if "surface_split" not in ov:
        return [(line, way_surface(el, line))]
    x0, north, south = ov["surface_split"]
    out, cur, side = [], [line[0]], line[0][0] >= x0
    for a, b in zip(line, line[1:]):
        if (b[0] >= x0) != side:
            c = (x0, a[1] + (x0 - a[0]) / (b[0] - a[0]) * (b[1] - a[1]))
            out.append((cur + [c], north if side else south))
            cur, side = [c], not side
        cur.append(b)
    out.append((cur, north if side else south))
    return [(c, s) for c, s in out if len(c) > 1]


def surface_class(surface, hw):
    """Класс покрытия маски: по surface, без него — по виду highway (SURFACE_DEFAULT, остальные дороги — асфальт)."""
    return SURFACE.get(surface, SURFACE_DEFAULT.get(hw, "Asphalt"))


@functools.lru_cache(maxsize=None)
def cathedral_square():
    """Площадь у собора (гип., SQUARE_*): (внешнее кольцо, дыры — газоны и здания, радиус от собора, м)."""
    els = _elements()
    outer = geo.open_ring(geo.local_points(next(e for e in els if e["type"] == "way" and e["id"] == SQUARE_WAY)
                                           ["geometry"]))
    holes = []
    for e in els:
        tags = e.get("tags", {})
        if e["type"] != "way" or not is_closed(e) or e["id"] == SQUARE_WAY:
            continue
        if tags.get("landuse") == "grass" or tags.get("leisure") in ("park", "garden") or (
                tags.get("building") and tags.get("building") != "no"):
            ring = geo.open_ring(geo.local_points(e["geometry"]))
            if any(point_in(p, outer) for p in ring) or point_in(outer[0], ring):
                holes.append(tuple(ring))
    return tuple(outer), tuple(holes), SQUARE_R_M


def in_square(p):
    outer, holes, r = cathedral_square()
    return math.hypot(p[0], p[1]) <= r and point_in(p, list(outer)) and not any(point_in(p, list(h)) for h in holes)


def _rel_rings(rel, role):
    ms = [m for m in rel["members"] if m["role"] == role and m.get("geometry") and None not in m["geometry"]]
    ways = [([(p["lat"], p["lon"]) for p in m["geometry"]], geo.local_points(m["geometry"])) for m in ms]
    return [tuple(r) for r in geo.assemble_rings(ways) if len(r) > 2]


def bed_ring(center, az, length, width):
    """Прямоугольник клумбы: центр (x, y), азимут длинной стороны, °, длина × ширина, м → кольцо (x, y)."""
    t = math.radians(az)
    u, v = (math.cos(t), math.sin(t)), (-math.sin(t), math.cos(t))
    return tuple((center[0] + su * length / 2 * u[0] + sv * width / 2 * v[0],
                  center[1] + su * length / 2 * u[1] + sv * width / 2 * v[1])
                 for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)))


@functools.lru_cache(maxsize=None)
def squares():
    """Площади: мультиполигоны OSM (SQUARE_REL_TAGS), затем замкнутые линии SQUARE_WAYS (в порядке списка) —
    ((id, имя, внешние кольца, дыры, surface, класс маски), …). Дыры — внутренние кольца (газоны) и клумбы
    SQUARE_REL_BEDS / beds; кольца — (x, y) без повтора точки. Порядок важен: маска (terrain_krom.render_mask) рисует
    площади по очереди, поздняя перекрывает раннюю."""
    out, ways = [], {}
    for e in _elements():
        tags = e.get("tags", {})
        if e["type"] == "way" and e["id"] in SQUARE_WAYS and is_closed(e):
            ways[e["id"]] = e
        if e["type"] != "relation" or tags.get("type") != "multipolygon":
            continue
        if not any(tags.get(k) in vals for k, vals in SQUARE_REL_TAGS):
            continue
        outer = _rel_rings(e, "outer")
        if not outer:
            continue
        holes = _rel_rings(e, "inner") + [bed_ring(*b) for b in SQUARE_REL_BEDS.get(e["id"], ())]
        surface = tags.get("surface") or SQUARE_REL_SURFACE.get(e["id"])
        out.append((e["id"], tags.get("name"), tuple(outer), tuple(holes), surface,
                    surface_class(surface, "pedestrian")))
    for wid, cfg in SQUARE_WAYS.items():
        e = ways.get(wid)
        if e is None:
            continue
        tags = e.get("tags", {})
        outer = (tuple(geo.open_ring(geo.local_points(e["geometry"]))),) + tuple(cfg.get("extra", ()))
        holes = tuple(bed_ring(*b) for b in cfg.get("beds", ()))
        surface = tags.get("surface")
        out.append((wid, cfg.get("name") or tags.get("name"), outer, holes, surface,
                    surface_class(surface, "pedestrian")))
    return tuple(out)


def traced_areas():
    """Площадки по аэрофото (TRACED_AREAS): [(имя, класс маски, кольцо (x, y))]."""
    return [(name, surface_class(surface, None), ring) for name, surface, ring in TRACED_AREAS]


def in_squares(p, ids=None):
    """Точка p (x, y) — на мощении площади (squares): внутри внешнего кольца и не в газоне / клумбе; ids — только
    эти площади (id OSM), иначе любая."""
    for (sid, _, outer, holes, _, _), (x0, x1, y0, y1) in zip(squares(), _square_boxes()):
        if ids is not None and sid not in ids:
            continue
        if not (x0 <= p[0] <= x1 and y0 <= p[1] <= y1):
            continue
        if any(point_in(p, list(r)) for r in outer) and not any(point_in(p, list(h)) for h in holes):
            return True
    return False


@functools.lru_cache(maxsize=None)
def _square_boxes():
    return tuple((min(q[0] for r in s[2] for q in r), max(q[0] for r in s[2] for q in r),
                  min(q[1] for r in s[2] for q in r), max(q[1] for r in s[2] for q in r)) for s in squares())


def ground(rect):
    """Покрытие земли из самых свежих refs/osm/krom_*.json: класс (GROUND + GROUND2) → (кольца, [(ломаная, ширина, м)]).

    Дороги и дорожки — по way_surface (тег surface и правки), без него — по виду highway (SURFACE_DEFAULT, остальные
    дороги — асфальт); ширина — way_width, одна с геометрией дорог (D-038). Площадки — по AREA_CLASS и highway
    с area=yes, площадки по аэрофото — TRACED_AREAS. Здания — «Built» (под ними встанут дома M5), руины (фундаменты
    храмов Довмонтова города) — «Paved», городские стены (в OSM это ещё и building) пропускаются: под ними меши стен.
    Площадь у собора (cathedral_square) рисует terrain_krom.render_mask поверх линий, площади squares() — после
    площадок, до линий. Обрезано по rect.
    """
    main = geo.load_elements(geo.latest("krom_2*.json"))
    polys = {k: [] for k in GROUND + GROUND2}
    lines = {k: [] for k in GROUND + GROUND2}

    def pieces(pts):
        return [c for part in geo.split_on_none(pts) for c in geo.clip_line_to_rect(part, *rect)]

    def building(tags):  # класс здания или None
        b = tags.get("building")
        if not b or b == "no" or tags.get("barrier") == "city_wall":
            return None
        return "Paved" if b == "ruins" else "Built"

    for el in main:
        tags = el.get("tags", {})
        if el["type"] == "way":
            pts = geo.local_points(el["geometry"])
            b, hw = tags.get("building"), tags.get("highway")
            if b and b != "no" and is_closed(el):
                if building(tags):
                    polys[building(tags)].append(pts)
            elif hw and tags.get("tunnel") != "yes" and not WAY_OVERRIDE.get(el["id"], {}).get("skip"):
                if tags.get("area") == "yes" and is_closed(el):
                    polys[surface_class(way_surface(el, pts), hw)].append(pts)
                    continue
                w, _ = way_width(el)
                if w is None:
                    continue
                hw_eff = WAY_OVERRIDE.get(el["id"], {}).get("highway", hw)
                for part in pieces(pts):
                    for piece, surface in split_surface(el, part):
                        lines[surface_class(surface, hw_eff)].append((piece, w))
            elif is_closed(el):
                cls = next((c for k, vals, c in AREA_CLASS if tags.get(k) in vals), None)
                if cls:
                    polys[cls].append(pts)
        elif el["type"] == "relation" and building(tags):
            outers = [m for m in el["members"] if m["role"] == "outer" and m.get("geometry") and None not in m["geometry"]]
            ways = [([(p["lat"], p["lon"]) for p in m["geometry"]], geo.local_points(m["geometry"])) for m in outers]
            polys[building(tags)] += geo.assemble_rings(ways)
    for _, cls, ring in traced_areas():   # площадки по аэрофото (Октябрьская площадь — асфальт перекрёстка)
        polys[cls].append(list(ring))

    polys = {k: [c for c in (geo.clip_to_rect(geo.open_ring(r), *rect) for r in v) if c] for k, v in polys.items()}
    return polys, lines
