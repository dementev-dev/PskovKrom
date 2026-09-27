"""facade_rules.py — таблица стилей рядовой застройки для фасадного генератора city_mesh.py (M5+, D-043).

Не для редактора: данные и выбор стиля, без bpy/unreal. Цвета — linear RGB, как krom_plan.COLORS и
palette_krom.PALETTE.

Класс здания — по тегам OSM (building, building:material, building:levels, start_date, addr:street); тегов
цвета и материала в зоне почти нет (1 building:colour, 1 building:material на 970 зданий), поэтому эпоха
выводится из этажности, типа и улицы — это гипотеза (гип.), а не данные. Цвет стен — building:colour, иначе
детерминированный выбор по id из палитры класса; кровли — roof:colour, иначе палитра кровель класса.

Палитра сверена с фото улиц Пскова (Commons, S-138…S-140): жёлтая охра и кремовый у сталинских домов Октябрьского
и Рижского проспектов, бежевый у улицы Горького, 14, красный кирпич без штукатурки у дореволюционных
домов Советской и Леона Поземского, серая штукатурка модерна (Октябрьский, 18), белый (Некрасова), бурый
крашеный тёс (Олега Кошевого, 5); цоколь и рустованный первый этаж — тёмно-серые; кровли — оцинковка (светло-
и тёмно-серая), местами ржаво-бурая. Числа — среднее k-средних по освещённой стене × 0,7–0,85 (экспозиция фото
выше альбедо) — гип.
"""
import re
import zlib

# ---------- цвета (linear) ----------

COLORS = {
    # штукатурка
    "ochre": (0.60, 0.485, 0.25),     # жёлтая охра: Октябрьский, 50 (S-138)
    "cream": (0.56, 0.49, 0.33),      # кремовый: Рижский, 5; Ольгинская наб., 3
    "beige": (0.47, 0.42, 0.33),      # бежевый: Горького, 14
    "pink": (0.58, 0.39, 0.32),       # розовый (гип.: фото в выборке нет)
    "white": (0.66, 0.65, 0.61),      # белый: Некрасова, 26
    "grey": (0.45, 0.44, 0.41),       # серая штукатурка: Октябрьский, 18
    "bluegrey": (0.42, 0.46, 0.48),   # серо-голубой (гип.)
    # кирпич, панели, дерево
    "brick": (0.33, 0.17, 0.10),      # красный кирпич: Леона Поземского, 3
    "brick_pale": (0.38, 0.25, 0.20), # выцветший розоватый кирпич: Советская, 31
    "silicate": (0.55, 0.54, 0.50),   # белый силикатный кирпич пятиэтажек (гип.)
    "panel": (0.40, 0.40, 0.38),      # серые панели (гип.)
    "wood_brown": (0.16, 0.085, 0.05),  # бурый крашеный тёс: Олега Кошевого, 5
    "wood_red": (0.22, 0.09, 0.06),   # красно-коричневый тёс (гип.)
    "wood_grey": (0.20, 0.17, 0.13),  # некрашеный старый тёс (гип.)
    # детали
    "trim_white": (0.70, 0.69, 0.65), # тяги, карнизы, откосы у крашеных домов
    "plinth": (0.085, 0.09, 0.09),    # тёмно-серый цоколь и руст: Октябрьский, 18; Рижский, 5
    "plinth_stone": (0.16, 0.15, 0.14),  # серый камень цоколя у кирпичных домов (гип.)
    "sill": (0.33, 0.33, 0.32),       # оцинкованный отлив подоконника
    "concrete": (0.46, 0.46, 0.44),   # балконы, козырьки подъездов
    "door_wood": (0.09, 0.05, 0.03),
    "door_metal": (0.07, 0.07, 0.065),
    "gate": (0.10, 0.12, 0.10),       # ворота гаражей
    "greenhouse": (0.55, 0.58, 0.58),
    # кровли
    "galv_light": (0.40, 0.41, 0.39), # светлая оцинковка: Ольгинская наб., 3
    "galv": (0.27, 0.27, 0.26),       # потемневшая оцинковка (с высоты — основной тон, S-140)
    "rusty": (0.25, 0.19, 0.15),      # ржаво-бурая жесть: Леона Поземского, 3
    "roof_red": (0.20, 0.07, 0.05),   # крашенная суриком (гип.)
    "roof_green": (0.07, 0.12, 0.08), # крашенная зелёным (гип.)
    "shifer": (0.36, 0.39, 0.40),     # асбестоцементный шифер: Олега Кошевого, 5
    "bitumen": (0.075, 0.075, 0.07),  # плоская мягкая кровля
    "bitumen_light": (0.13, 0.13, 0.125),
}
GLASS = [(0.018, 0.022, 0.028), (0.025, 0.030, 0.036), (0.030, 0.032, 0.034), (0.09, 0.085, 0.075)]  # последнее — шторы

# ---------- классы: геометрия ----------
# plinth — цоколь, м; first — первый этаж в долях типового; win — окно (ширина, высота), м; step — шаг окон;
# corner — простенок у угла; cornice — (высота, вынос), м, 0 — без карниза; overhang — свес скатной кровли;
# door — (ширина, высота) и door_every — шаг дверей (подъезды) по уличной стене, None — одна;
# rustic — доля домов с тёмным первым этажом; balconies — где балконы: None, "street", "yard"
BASE = dict(windows=True, plinth=0.8, first=1.15, win=(1.1, 1.7), step=3.0, corner=1.0, cornice=(0.35, 0.2),
            overhang=0.45, door=(1.3, 2.4), door_every=None, door_color="door_wood", canopy=True, rustic=0.0,
            balconies=None, chimneys=True, vitrine=False, gates=False)
STYLES = {
    "historic": dict(),                                                          # 1–3 этажа до 1917 г. (гип.)
    "stalin": dict(plinth=1.0, first=1.25, win=(1.3, 1.9), step=3.2, corner=1.2, cornice=(0.5, 0.3),
                   overhang=0.5, door=(1.4, 2.5), door_every=20.0, rustic=0.4, balconies="street",
                   chimneys=False),                                              # 4–5 этажей 1940–50-х (гип.)
    "soviet": dict(plinth=0.6, first=1.0, win=(1.45, 1.45), step=3.0, corner=0.9, cornice=(0.25, 0.1),
                   overhang=0.3, door=(1.2, 2.2), door_every=16.0, door_color="door_metal", balconies="yard",
                   chimneys=False),                                             # 5–9 этажей 1960–80-х (гип.)
    "modern": dict(plinth=0.6, first=1.1, win=(1.5, 1.6), step=3.2, corner=1.0, cornice=(0.3, 0.12),
                   overhang=0.4, door=(1.6, 2.4), door_every=25.0, door_color="door_metal", chimneys=False),
    "public": dict(plinth=0.9, first=1.2, win=(1.4, 2.0), step=3.4, corner=1.2, cornice=(0.45, 0.25),
                   door=(1.8, 2.6), chimneys=False),
    "shop": dict(plinth=0.5, first=1.3, win=(1.4, 1.8), step=3.4, corner=1.0, cornice=(0.35, 0.2),
                 door=(1.6, 2.4), door_color="door_metal", chimneys=False, vitrine=True),
    "wood": dict(plinth=0.5, first=1.0, win=(1.0, 1.3), step=2.7, corner=0.8, cornice=(0.0, 0.0), overhang=0.5,
                 door=(1.0, 2.1), canopy=False),                                 # деревянные дома частного сектора
    "industrial": dict(plinth=0.4, first=1.0, win=(2.2, 1.8), step=4.5, corner=1.5, cornice=(0.3, 0.1),
                       overhang=0.3, door=None, chimneys=False, gates=True),
    "utility": dict(windows=False, plinth=0.3, cornice=(0.0, 0.0), overhang=0.3, door=None, chimneys=False),
    "garage": dict(windows=False, plinth=0.0, cornice=(0.0, 0.0), overhang=0.2, door=None, chimneys=False,
                   gates=True),
    "church": dict(windows=False, plinth=0.9, cornice=(0.45, 0.25), door=None, chimneys=False),
}
for _k, _v in STYLES.items():
    STYLES[_k] = dict(BASE, **_v)

# ---------- классы: цвет (вес, ключ COLORS) ----------
PLASTER = [(3, "ochre"), (3, "cream"), (2, "beige"), (2, "pink"), (2, "white"), (1, "grey"), (1, "bluegrey")]
WALLS = {
    "historic": PLASTER + [(5, "brick"), (2, "brick_pale")],   # кирпич без штукатурки ≈ треть (фото S-139, гип.)
    "stalin": [(4, "ochre"), (3, "cream"), (2, "beige"), (1, "pink"), (1, "grey")],
    "soviet": [(4, "silicate"), (3, "panel"), (2, "brick"), (1, "beige")],
    "modern": [(2, "beige"), (2, "white"), (1, "grey"), (1, "cream"), (1, "brick_pale")],
    "public": PLASTER + [(2, "brick")],
    "shop": PLASTER + [(2, "grey"), (1, "silicate")],
    "wood": [(4, "wood_brown"), (2, "wood_red"), (2, "wood_grey"), (1, "cream"), (1, "bluegrey")],
    "industrial": [(3, "brick"), (2, "panel"), (1, "silicate")],
    "utility": [(3, "panel"), (2, "wood_grey"), (2, "brick_pale"), (1, "silicate")],
    "garage": [(3, "panel"), (2, "silicate"), (1, "brick_pale")],
    "church": [(1, "white")],
}
ROOFS_PITCHED = {
    "default": [(4, "galv"), (3, "galv_light"), (1, "rusty"), (1, "roof_red"), (1, "roof_green")],
    "wood": [(3, "shifer"), (3, "galv"), (2, "rusty"), (1, "roof_green")],
    "utility": [(3, "shifer"), (2, "rusty"), (2, "galv")],
}
ROOFS_FLAT = [(3, "bitumen"), (2, "bitumen_light"), (1, "galv")]

# улица → класс для жилых 2–5 этажей без тегов эпохи (гип.: по фото S-138, S-139 — отдельные дома, не вся улица)
STREETS = {
    "Октябрьский проспект": "stalin",
    "Рижский проспект": "stalin",
    "улица Максима Горького": "stalin",
    "улица Труда": "stalin",
    "Советская улица": "historic",
    "улица Леона Поземского": "historic",
    "улица Некрасова": "historic",
    "Ольгинская набережная": "historic",
}

RELIGIOUS = {"church", "chapel", "cathedral", "temple", "monastery", "religious"}
UTILITY = {"shed", "service", "greenhouse", "kiosk", "roof", "hut", "carport", "transformer_tower", "toilets",
           "bunker", "cabin", "barn", "farm_auxiliary", "construction", "storage_tank"}
GARAGES = {"garage", "garages", "parking"}
PUBLIC = {"school", "university", "college", "kindergarten", "hospital", "office", "public", "government",
          "civic", "museum", "hotel", "train_station", "transportation", "sports_centre", "theatre", "bank"}
SHOPS = {"retail", "commercial", "supermarket"}
HOUSES = {"house", "detached", "semidetached_house", "bungalow", "terrace", "cottage"}
INDUSTRIAL = {"industrial", "warehouse", "manufacture", "factory"}


def pick(h, table):
    """Взвешенный выбор из [(вес, значение)] по хешу h."""
    total = sum(w for w, _ in table)
    r = h % total
    for w, v in table:
        if r < w:
            return v
        r -= w
    return table[-1][1]


def year(tags):
    m = re.search(r"(1[5-9]\d\d|20\d\d)", tags.get("start_date", ""))
    return int(m.group(1)) if m else None


def classify(h, tags, levels, area):
    """Класс здания по тегам, этажности и улице (гип.: эпоха по этажности и улице)."""
    b = tags.get("building", "yes")
    mat = tags.get("building:material", "")
    if b in RELIGIOUS:
        return "church"
    if b in GARAGES:
        return "garage"
    if b in UTILITY or levels < 1:
        return "utility"
    if mat == "wood":
        return "wood"
    if b in INDUSTRIAL:
        return "industrial"
    y = year(tags)
    if y and y >= 1995:
        return "modern"
    if b in PUBLIC:
        return "public"
    if b in SHOPS or tags.get("shop"):
        return "shop"
    street = STREETS.get(tags.get("addr:street"))
    if street and 2 <= levels <= 5 and h % 10 < 8:
        return street
    if levels >= 5:
        return "soviet"
    if b in HOUSES or (levels <= 1.5 and area < 160):
        return pick(h >> 4, [(11, "wood"), (6, "historic")])
    if levels >= 4:
        return pick(h >> 4, [(1, "stalin"), (1, "soviet")])
    return "historic"


# ---------- цвет из тегов ----------

CSS = {  # sRGB 0–255 для частых значений building:colour / roof:colour
    "white": (245, 245, 240), "whitesmoke": (245, 245, 245), "ivory": (255, 255, 240), "beige": (225, 210, 175),
    "wheat": (245, 222, 179), "cream": (240, 225, 185), "yellow": (235, 205, 110), "khaki": (215, 200, 130),
    "gold": (225, 185, 80), "orange": (225, 150, 80), "pink": (235, 180, 170), "salmon": (230, 150, 120),
    "red": (170, 60, 45), "darkred": (120, 35, 30), "maroon": (110, 40, 30), "brown": (120, 75, 45),
    "sienna": (150, 85, 50), "tan": (205, 175, 135), "grey": (150, 150, 145), "gray": (150, 150, 145),
    "silver": (190, 190, 190), "lightgrey": (205, 205, 200), "lightgray": (205, 205, 200),
    "darkgrey": (95, 95, 92), "darkgray": (95, 95, 92), "dimgray": (90, 90, 90), "black": (35, 35, 35),
    "green": (70, 110, 70), "darkgreen": (40, 70, 45), "olive": (120, 120, 70), "lightgreen": (160, 200, 150),
    "blue": (80, 110, 160), "lightblue": (165, 195, 215), "skyblue": (150, 190, 220), "teal": (60, 120, 120),
    "purple": (120, 80, 120),
}


def srgb_to_linear(c):
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def parse_colour(s):
    """Значение building:colour / roof:colour → linear RGB (× 0,8: тег — «цвет краски», не альбедо) или None."""
    if not s:
        return None
    s = s.strip().lower().split(";")[0]
    if re.fullmatch(r"#?[0-9a-f]{6}", s):
        s = s.lstrip("#")
        rgb = tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    elif re.fullmatch(r"#[0-9a-f]{3}", s):
        rgb = tuple(int(ch * 2, 16) for ch in s[1:])
    else:
        rgb = CSS.get(s.replace(" ", "").replace("_", ""))
    if rgb is None:
        return None
    return tuple(round(0.8 * x, 3) for x in srgb_to_linear([v / 255.0 for v in rgb]))


def scale(c, k):
    return tuple(min(1.0, x * k) for x in c)


# ---------- стиль здания ----------

def style(bid, tags, levels, area, flat_roof):
    """Параметры фасада и цвета для здания: словарь STYLES класса + wall, trim, plinth_c, roof, glass (linear)."""
    h = zlib.crc32(str(bid).encode())
    cls = classify(h, tags, levels, area)
    s = dict(STYLES[cls], cls=cls)
    mat = tags.get("building:material", "")
    key = pick(h, WALLS[cls])
    if mat == "brick" and cls not in ("wood",):
        key = pick(h, [(3, "brick"), (1, "brick_pale")])
    wall = parse_colour(tags.get("building:colour")) or COLORS[key]
    brick = key.startswith("brick") and not tags.get("building:colour")
    if cls in ("soviet", "industrial", "utility", "garage", "wood") or brick:
        trim = scale(wall, 1.12)          # кирпич, панели, тёс: тяги в цвет стены
    else:
        trim = COLORS["trim_white"] if (h >> 8) % 4 else scale(wall, 1.15)  # белые тяги у крашеных — чаще
    s["wall"], s["trim"] = wall, trim
    s["plinth_c"] = COLORS["plinth_stone"] if brick or cls in ("wood", "utility") else COLORS["plinth"]
    s["rustic"] = (h >> 12) % 100 < s["rustic"] * 100
    s["roof"] = parse_colour(tags.get("roof:colour")) or COLORS[pick(h >> 16, ROOFS_FLAT if flat_roof else
                                                                     ROOFS_PITCHED.get(cls, ROOFS_PITCHED["default"]))]
    s["glass_h"] = h
    s["door_c"] = COLORS[s["door_color"]]
    if tags.get("building") == "greenhouse":
        s["wall"] = COLORS["greenhouse"]
    return s


def glass(h):
    """Цвет стекла окна по хешу: тёмные оттенки, каждое шестое — со шторами."""
    h = zlib.crc32(str(h).encode())
    return GLASS[-1] if h % 6 == 0 else GLASS[h % (len(GLASS) - 1)]
