"""yard_plan.py — план зданий XVII–XIX вв. во дворе Крома и Довмонтова города: Дом причта, Пороховые погреба,
Консистория (D-036). Общий источник для blockout (buildings()) и героев scripts/blender/krom_yard.py.

Чистый Python без `unreal` и `bpy`. Координаты — локальные метры (D-013): x — север, y — восток. Оси здания, как
у Building: u — по азимуту yaw, v — вправо от него (yaw + 90°), z — от земли в точке base (или center).
Цифры — из docs/REFERENCES.md: S-02 OSM, S-23 акт ГИКЭ 2022, S-69 реестр ОКН, S-71 pleskov60; высоты — по фото
Commons S-70 с восстановленными камерами (build/yard_refs/manifest.json, build/yard/fit_*.py); «гип.» — оценка.

krom_plan импортируется лениво, внутри функций: krom_plan.buildings() сам берёт здания отсюда.

    python scripts/yard_plan.py     # сверка чисел плана с контурами OSM
"""
import functools
import math
from dataclasses import dataclass

import krom_geo as geo


@dataclass(frozen=True)
class ClergyHousePlan:
    """Дом причта Троицкого собора (1843, арх. Ф. И. Уткин, S-71; реестр — «XIX в.», S-69) в 44 м к северу от собора.
    Двухэтажный деревянный на каменном подвале (S-71), снаружи оштукатурен, на высоком цоколе с продухами; кровля —
    оцинкованная жесть (фото S-70).

    План — контур OSM way 61675940: квадрат 23,65 × 23,65, оси по его сторонам (yaw 77°: u — на восток, v — на юг).
    Узел OSM на восточной стене делит его на северную часть (8,67 м) и главный объём (15,0 м) — так же на аэрофото
    S-70 (asv07 aerial3, aerial4). Главный объём — под вальмой, конёк вдоль u, на торцевых скатах по слуховому окну;
    северная часть ниже, под своей вальмой, по оси её фасада — фронтон с полукруглым окном (фото prich_00, px_09).
    Северная часть на метр ниже главного объёма (анфас prich_17: карнизы 8,1 и 9,0; так же prich_05, prich_19).
    Высоты — по фото S-70: prich_17 (анфас с запада, масштаб — ширина 23,65) — карнизы, окна; prich_00 (геотег, камера
    восстановлена по углам и стыку частей, фокусное из EXIF, невязка ≤12 пкс) — карниз северной части 7,8, вершина
    фронтона +1,8, конёк 12,1; по prich_17 конёк ≈13. Принято ±0,5 м."""
    name: str = "Дом причта"
    key: str = "Pricht"
    asset: str = "SM_ClergyHouse"
    group: str = "Krom"
    way: int = 61675940
    center: tuple = (71.07, -22.10)    # середина квадрата OSM; земля здесь — нуль высот
    yaw: float = 77.0
    side: float = 23.65                # сторона квадрата по фасадам
    v_split: float = -3.16             # граница северной части и главного объёма (узел OSM на восточной стене)
    z_plinth: float = 0.5              # серый цоколь
    z_belt: tuple = (4.75, 5.0)        # междуэтажный пояс
    z_eave: float = 9.0                # карниз главного объёма, по фото
    z_eave_north: float = 8.0          # карниз северной части
    z_ridge: float = 12.4              # конёк главного объёма, по фото
    ridge_len: float = 12.5            # длина конька главного объёма (аэрофото, фото prich_08)
    pediment: tuple = (12.3, 9.8)      # фронтон северного фасада: ширина (аэрофото), вершина (prich_00, px_09)
    rise_north: float = 1.2            # вальма северной части: ниже вершины фронтона (его конёк виден за ней), гип.
    low: tuple = (1.35, 2.9)           # окна 1-го этажа: низ, верх (prich_17)
    up: tuple = (5.1, 7.0)             # окна 2-го этажа (у северной части верх на 0,3 ниже)

    @property
    def hero(self):
        return f"/Game/Krom/Architecture/{self.group}/{self.asset}"


@dataclass(frozen=True)
class PowderCellarsPlan:
    """Пороховые погреба (нижний этаж — после 1636 г., верх восстановлен в 1970-х по проекту А. В. Воробьёва, S-23;
    реестр — «XVII в.», S-69) у восточной стены Крома между Средней и Кутекромой. По акту ГИКЭ 2022 (S-23):
    прямоугольная трёхчастная постройка вдоль крепостной стены, два этажа и мансарда, 29,5 × 12,8 м, высота 11,2 м;
    восточная стена — сама крепостная, толщиной 3,5 м, не белена; в центре западного фасада — двухэтажный тамбур
    8,3 × 4,0 м под двускатной кровлей, к нему с юго-запада — крыльцо под односкатной; кровля вальмовая из гонта
    со слуховыми окнами (по одному на северном и южном скатах, два — на восточном); все фасады, кроме восточного,
    побелены.

    Контур OSM relation 4060621 (31,4 × 16,4–17,1) — с крепостной стеной: восточная сторона — её наружная грань (линия
    стены «Восточная: Средняя — Кутекрома»). Оси: u — вдоль стены на север (yaw 338,1°), v — на восток к стене,
    начало — середина тела по акту (12,8 м от внутренней грани стены 3,5 м). Стена в сцене тоньше (3,0 м) и идёт
    дальше с галереей (walls_krom): тело заходит под неё до v_east, кровля — только над двором (на деле она накрывает
    и стену — отличие модели). Карниз, высоты тамбура и его место — по фото pogr_00 (S-70, 2013, геотег) с
    восстановленной камерой (ширина тамбура 8,3 — масштаб, невязка 4 пкс): карниз 7,8, тамбур 5,55 / 7,35, середина
    тамбура на 2,5 м южнее середины фасада (на аэрофото 2018 — на 1,8 м)."""
    name: str = "Пороховые погреба"
    key: str = "Powder"
    asset: str = "SM_PowderCellars"
    group: str = "Krom"
    relation: int = 4060621
    center: tuple = (110.43, 6.09)
    yaw: float = 338.08
    length: float = 29.5               # по u (S-23; OSM 31,35)
    v_west: float = -6.4               # западный фасад (12,8 м от внутренней грани стены по акту)
    v_wall: float = 6.9                # внутренняя грань стены в сцене (3,0 м от линии OSM на v = 9,9)
    v_east: float = 7.1                # тело заходит в стену
    z_eave: float = 7.8                # карниз, по фото
    z_ridge: float = 11.2              # S-23
    tambour: tuple = (8.3, 4.0, 5.55, 7.35)  # тамбур: ширина по u, вынос (S-23), карниз, конёк (по фото)
    u_tambour: float = -2.5            # середина тамбура по u (по фото и аэрофото)
    porch: tuple = (4.6, 2.6, 4.1, 3.2)      # крыльцо к югу от тамбура: по u, вынос, кровля у стены и у края (гип.)

    @property
    def base(self):
        """Земля у середины западного фасада — двор, откуда сняты фото."""
        return to_world(self.center, self.yaw, 0.0, self.v_west)

    @property
    def hero(self):
        return f"/Game/Krom/Architecture/{self.group}/{self.asset}"


@dataclass(frozen=True)
class ConsistoryPlan:
    """Консистория (Кремль, 6; 1853, проект Ф. И. Уткина 1843 г., строил И. К. Шевцов; перестроена в 1870–71 гг.
    А. И. Ранвидом — S-71; реестр: «1853 г., 1871 г.», S-69). Каменный двухэтажный дом у въезда в Довмонтов город,
    в линии его стены (S-23, акт 2026: «в южной стене Довмонтова города … здание XIX в., так называемая Духовная
    консистория»); ради него разобрали прясло стены (S-71). Главный фасад — на юго-восток, к пл. Ленина: 5 осей,
    в центре «тройное» окно, 1-й этаж рустован, пояс с филёнками, карниз с сухариками; к двору — два широких крыла
    (северное больше западного), за западным — двухэтажные ретирады и одноэтажная лестница; кровли вальмовые, над
    лестницей односкатная (S-71). Высота помещений 3,12 и 4,3 м, габариты 19,2 × 19,3 м (S-71).

    План — контур OSM relation 4060622 («Кремль, 6»), он ортогонален и шире габаритов S-71 (главный фасад 21,3 м);
    оси: u — вдоль главного фасада на северо-восток (yaw 54,8°), v — наружу, к улице; фасад на v = 0, здание — v < 0.
    Нуль высот — земля у середины главного фасада (улица); двор ниже на 1,5–3,7 м (рельеф) — цоколь уходит в землю.
    Членение на объёмы — по S-71 и аэрофото S-70 (air_09, BKDRF), границы крыльев — гип. Ось симметрии главного
    фасада на фото kons_00 — в 10,0 м от западного угла, а не посередине контура OSM (21,3 м; у S-71 — 19,2 м):
    окна ставим по фото. Стены в 2013 г. бледно-голубые (kons_00), в аэрофото — белые: цвет — «wall»."""
    name: str = "Консистория"
    key: str = "Consistory"
    asset: str = "SM_Consistory"
    group: str = "Dovmont"
    relation: int = 4060622
    center: tuple = (-201.67, 107.37)   # середина главного фасада
    yaw: float = 54.79
    # контур OSM в осях здания (u, v): P0 — западный угол главного фасада, дальше против часовой стрелки на плане
    outline: tuple = ((-10.65, 0.0), (-10.69, -17.58), (-5.98, -17.37), (-5.69, -26.55), (-0.21, -26.55),
                      (-0.21, -23.52), (8.73, -23.52), (8.73, -21.57), (8.74, -15.65), (10.65, 0.0))
    v_main: float = -9.0                # глубина главного корпуса (3 оси северо-восточного фасада, аэрофото), гип.
    v_west: float = -17.5               # задний фасад западного крыла (OSM)
    u_wings: float = -0.21              # граница западного и северного крыльев (OSM, узел P4–P5)
    u_axis: float = -0.65               # ось симметрии главного фасада: 10,0 м от западного угла (фото kons_00)
    axes: tuple = (7.0, 1.9)            # боковые оси от неё и шаг «тройного» окна (фото kons_00)
    z_plinth: float = 0.9
    z_belt: tuple = (4.45, 4.95)        # пояс: 1-й этаж 3,12 м + перекрытие (S-71; фото kons_00 — 4,4…5,0)
    z_eave: float = 9.9                 # верх карниза: 2-й этаж 4,3 м + карниз (S-71; фото kons_00 — 9,85)
    z_back: float = 8.6                 # карниз ретирад, гип.
    z_stair: tuple = (5.0, 4.2)         # односкатная кровля лестницы: у стены и у края, гип.
    low: tuple = (1.65, 3.65)           # окна 1-го этажа: низ, верх (фото kons_00)
    up: tuple = (5.75, 8.1)             # окна 2-го этажа (фото kons_00, низ — 5,76)

    @property
    def hero(self):
        return f"/Game/Krom/Architecture/{self.group}/{self.asset}"


CLERGY_HOUSE = ClergyHousePlan()
POWDER_CELLARS = PowderCellarsPlan()
CONSISTORY = ConsistoryPlan()
YARD = (CLERGY_HOUSE, POWDER_CELLARS, CONSISTORY)


def to_world(origin, yaw, u, v):
    t = math.radians(yaw)
    return origin[0] + u * math.cos(t) - v * math.sin(t), origin[1] + u * math.sin(t) + v * math.cos(t)


def to_local(origin, yaw, p):
    t = math.radians(yaw)
    dx, dy = p[0] - origin[0], p[1] - origin[1]
    return dx * math.cos(t) + dy * math.sin(t), -dx * math.sin(t) + dy * math.cos(t)


@functools.lru_cache(maxsize=None)
def osm_ring(kind, osm_id):
    """Внешнее кольцо контура OSM (x, y) без повтора точки: way — как есть, relation — склейка outer-линий по узлам."""
    els = geo.load_elements(geo.latest("krom_2*.json"))
    ways = {e["id"]: e for e in els if e["type"] == "way"}
    if kind == "way":
        return tuple(geo.open_ring(geo.local_points(ways[osm_id]["geometry"])))
    rel = next(e for e in els if e["type"] == "relation" and e["id"] == osm_id)
    rings = geo.assemble_rings([(ways[m["ref"]]["nodes"], geo.local_points(ways[m["ref"]]["geometry"]))
                                for m in rel["members"] if m["role"] == "outer"])
    return tuple(max(rings, key=lambda r: abs(geo.signed_area(r))))


def footprint(p):
    return osm_ring("way", p.way) if hasattr(p, "way") else osm_ring("relation", p.relation)


# ---------- blockout (пока нет героя) ----------

def clergy_house():
    import krom_plan as kp
    c = CLERGY_HOUSE
    s, h = c.side, c.side / 2
    dn = c.v_split + h                                   # глубина северной части
    parts = (kp.Part("box", (0, 0), (s, s), (0, c.z_eave), "wall"),
             kp.Part("pyr", (0, (c.v_split + h) / 2), (s + 1, s - dn + 1), (c.z_eave, c.z_ridge), "tin"),
             kp.Part("pyr", (0, (c.v_split - h) / 2), (s + 1, dn + 1), (c.z_eave_north, c.z_eave_north + c.rise_north),
                     "tin"))
    return kp.Building(c.name, c.group, c.center, c.yaw, parts, footprint(c),
                       "OSM way 61675940, S-69, S-71; высоты — по фото S-70; см. yard_plan.ClergyHousePlan",
                       hero=c.hero)


def powder_cellars():
    import krom_plan as kp
    c = POWDER_CELLARS
    w = c.v_east - c.v_west
    vm = (c.v_east + c.v_west) / 2
    tw, td, te, tr = c.tambour
    parts = (kp.Part("box", (0, vm), (c.length, w), (0, c.z_eave), "wall"),
             kp.Part("pyr", (0, (c.v_wall + c.v_west) / 2), (c.length + 0.8, c.v_wall - c.v_west + 0.8),
                     (c.z_eave, c.z_ridge), "wood"),
             kp.Part("box", (c.u_tambour, c.v_west - td / 2), (tw, td), (0, te), "wall"),
             kp.Part("pyr", (c.u_tambour, c.v_west - td / 2), (tw + 0.6, td + 0.6), (te, tr), "wood"))
    return kp.Building(c.name, c.group, c.center, c.yaw, parts, footprint(c),
                       "OSM relation 4060621, акт ГИКЭ 2022 (S-23); см. yard_plan.PowderCellarsPlan",
                       hero=c.hero, base=c.base)


def consistory():
    import krom_plan as kp
    c = CONSISTORY
    u0, u1 = c.outline[0][0], c.outline[-1][0]
    parts = (kp.Part("box", ((u0 + u1) / 2, c.v_main / 2), (u1 - u0, -c.v_main), (0, c.z_eave), "wall"),
             kp.Part("pyr", ((u0 + u1) / 2, c.v_main / 2), (u1 - u0 + 0.8, -c.v_main + 0.8), (c.z_eave, c.z_eave + 2.3),
                     "tin"),
             kp.Part("box", ((u0 + c.u_wings) / 2, (c.v_main + c.v_west) / 2), (c.u_wings - u0, c.v_main - c.v_west),
                     (0, c.z_eave), "wall"),
             kp.Part("box", ((c.u_wings + 8.73) / 2, (c.v_main - 23.52) / 2), (8.73 - c.u_wings, c.v_main + 23.52),
                     (0, c.z_eave), "wall"),
             kp.Part("pyr", ((u0 + 8.73) / 2, (c.v_main - 23.52) / 2), (8.73 - u0 + 0.8, c.v_main + 23.52 + 0.8),
                     (c.z_eave, c.z_eave + 2.3), "tin"))
    return kp.Building(c.name, c.group, c.center, c.yaw, parts, footprint(c),
                       "OSM relation 4060622, S-71; высоты — S-71 и фото S-70; см. yard_plan.ConsistoryPlan",
                       hero=c.hero)


def buildings():
    """Здания двора Крома и Довмонтова города для krom_plan.buildings()."""
    return [clergy_house(), powder_cellars(), consistory()]


if __name__ == "__main__":
    for p in YARD:
        ring = footprint(p)
        loc = [to_local(p.center, p.yaw, q) for q in ring]
        us, vs = [q[0] for q in loc], [q[1] for q in loc]
        print(f"{p.name}: контур OSM {len(ring)} точек, {abs(geo.signed_area(list(ring))):.0f} м², "
              f"u {min(us):+.2f}…{max(us):+.2f}, v {min(vs):+.2f}…{max(vs):+.2f}; hero {p.hero}")
    c = CONSISTORY
    loc = [to_local(c.center, c.yaw, q) for q in footprint(c)]
    err = max(min(math.dist(a, b) for b in loc) for a in c.outline)
    assert err < 0.05, f"Консистория: outline разошёлся с OSM на {err:.2f} м"
    h = CLERGY_HOUSE.side / 2
    loc = [to_local(CLERGY_HOUSE.center, CLERGY_HOUSE.yaw, q) for q in footprint(CLERGY_HOUSE)]
    assert all(abs(abs(u) - h) < 0.05 or abs(abs(v) - h) < 0.05 for u, v in loc), "Дом причта: квадрат разошёлся с OSM"
    print("ok")
