"""prikaz_plan.py — план Приказных палат (1692–93, крыльцо 1693–95) в Довмонтовом городе: общий источник для blockout
(prikaz_palaty()) и героя scripts/blender/prikaz.py (как yard_plan для построек двора, D-036).

Чистый Python без `unreal` и `bpy`. Координаты — локальные метры (D-013): x — север, y — восток. Оси здания, как
у Building: u — по азимуту yaw (вдоль длинной оси, к востоку-северо-востоку), v — вправо от него (к югу, на улицу),
z — от земли в точке base. Начало — середина основного объёма; северный фасад — v = −D/2, крыльцо — к v < −D/2.
Цифры — из docs/REFERENCES.md (раздел «Приказные палаты»): габариты и толщина стен — реестр и pleskov60, место и
ось — OSM relation 4060615, высоты и крыльцо — по фото Commons с восстановленными камерами
(build/prikaz/solve.py, measure.py); «гип.» — оценка.

krom_plan импортируется лениво, внутри функций: krom_plan.prikaz_palaty() берёт здание отсюда.

    python scripts/prikaz_plan.py     # сверка плана с контуром OSM
"""
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PrikazPlan:
    """Приказные палаты (Кремль, 4): двухэтажные каменные палаты из плитняка, обмазаны и побелены, вытянуты вдоль
    южной стены Довмонтова города; «красное крыльцо на отлёте» — к северу, в Довмонтов город. Облик — после
    реставраций 1968 (крыльцо восстановлено по проекту А. В. Воробьёва) и 1980–90-х: кровля четырёхскатная из
    оцинкованной стали. Исторические тесовые кровли с бочками, балюстрадой и шатрами над крыльцом (1693–1701)
    не строим.

    План. Габариты 31,4 × 15,3 м, стены 2,3 м (реестр S-09, pleskov60). Контур OSM (relation 4060615) больше:
    основной объём 33,1 × 18,8, крыльцо 10,4 × 15,3 — гипотеза: обвод по кровле со свесами. Его южная сторона —
    линия стены (way 654691946): по ней стоит южный фасад, западный торец — у стыка со стеной. Ось yaw — по южной
    стороне контура OSM (59,26°). Камеры фото c_09, c_14 и c_07, подобранные вместе с размерами при L = 31,4
    и D = 15,3 (build/prikaz/solve.py, невязка ≤18 пкс), дают крыльцо 8,3 × 16,1 м на u −6,15…2,15 — на обмерном
    плане pleskov60 крыльцо так же западнее середины; D при свободном подборе — 15,9 (±0,5 м).

    Высоты — от земли у северного фасада (камеры, ±0,5 м): карниз 9,0, конёк 13,55 (вальмы под 45°: конёк на
    u −7,8…7,8 по фото c_14), окна 2-го этажа 5,0–7,1, 1-го — 0,8–2,1, двери до 2,0. Крыльцо: верхний рундук
    (пол ≈4,0 — гип., парапет 4,85, арка до 7,55 и круглый столб-«бочка» по бокам), всход с косой аркой, нижний
    рундук на четырёх столбах: арки с боков 4,5 м (пята 2,75, верх 4,3), с севера 4,9 м (пята 3,1, верх 5,0).
    Кровля крыльца — одна, ступенью: над верхним рундуком карниз 8,95 и конёк 12,15, над всходом оба спускаются,
    над нижним рундуком карниз 6,1, конёк 8,7 до s 12,95 и вальма на север."""
    name: str = "Приказные палаты"
    key: str = "Prikaz"
    asset: str = "SM_PrikazPalaty"
    group: str = "Dovmont"
    relation: int = 4060615
    center: tuple = (-216.79, 72.03)    # середина основного объёма (от юго-западного угла OSM: u 15,7, v −7,65)
    yaw: float = 59.26
    length: float = 31.4               # по u (S-09, pleskov60)
    depth: float = 15.3                # по v (S-09, pleskov60; камеры — 15,9)
    wall: float = 2.3                  # толщина стен (pleskov60)
    z_eave: float = 9.0                # карниз (камеры: 9,04)
    z_ridge: float = 13.55             # конёк (камеры: 13,45–13,63)
    # крыльцо: по u, вынос от северного фасада; участки по выносу s: верхний рундук, всход, нижний рундук
    porch_u: tuple = (-6.15, 2.15)
    porch_len: float = 16.15
    s_upper: float = 5.5               # верхний рундук: s 0…5,5
    s_stair: float = 10.35             # всход: s 5,5…10,35; дальше — нижний рундук до porch_len
    porch_wall: float = 0.9            # стенки крыльца, гип.
    z_upper_floor: float = 4.0         # пол верхнего рундука ≈ 2-й этаж, гип. (парапет по фото 4,85)
    z_lower_floor: float = 0.45        # пол нижнего рундука, гип. (ступени)
    z_porch_eave: tuple = (8.95, 6.1)  # карниз крыльца: над верхним рундуком, над нижним (камеры: 8,97 / 6,12)
    z_porch_ridge: tuple = (12.15, 8.7)  # конёк: над верхним рундуком, над нижним (камеры: 12,1–12,2 / 8,7)
    s_porch_ridge: float = 12.95       # конец конька над нижним рундуком, дальше вальма (камера c_09)

    @property
    def base(self):
        """Земля у середины северного фасада — площадь Довмонтова города, откуда сняты фото."""
        return to_world(self.center, self.yaw, 0.0, -self.depth / 2)

    @property
    def hero(self):
        return f"/Game/Krom/Architecture/{self.group}/{self.asset}"

    def outline(self):
        """Контур у земли в осях здания (u, v): основной объём и крыльцо."""
        h, d = self.length / 2, self.depth / 2
        a, b = self.porch_u
        n = -d - self.porch_len
        return ((-h, d), (h, d), (h, -d), (b, -d), (b, n), (a, n), (a, -d), (-h, -d))


PRIKAZ = PrikazPlan()


def to_world(origin, yaw, u, v):
    t = math.radians(yaw)
    return origin[0] + u * math.cos(t) - v * math.sin(t), origin[1] + u * math.sin(t) + v * math.cos(t)


def to_local(origin, yaw, p):
    t = math.radians(yaw)
    dx, dy = p[0] - origin[0], p[1] - origin[1]
    return dx * math.cos(t) + dy * math.sin(t), -dx * math.sin(t) + dy * math.cos(t)


def footprint(p=PRIKAZ):
    """Контур в плане (x, y): основной объём с крыльцом — по плану, а не по OSM (тот шире на свесы кровли)."""
    return tuple(to_world(p.center, p.yaw, u, v) for u, v in p.outline())


def outline_rings(p=PRIKAZ):
    """Контуры для сверки на спутнике (build/prikaz/sat.py): стены у земли."""
    return [footprint(p)]


# ---------- blockout (пока нет героя) ----------

def prikaz_palaty():
    """Building для krom_plan: blockout-примитивы по плану; hero — SM_PrikazPalaty (scripts/blender/prikaz.py)."""
    import krom_plan as kp
    c = PRIKAZ
    L, D = c.length, c.depth
    a, b = c.porch_u
    pw, pc = b - a, (a + b) / 2
    vn = -D / 2 - c.porch_len
    vl = (vn - D / 2 - c.s_stair) / 2          # середина нижнего рундука
    parts = (kp.Part("box", (0, 0), (L, D), (0, c.z_eave), "wall"),
             kp.Part("pyr", (0, 0), (L + 0.9, D + 0.9), (c.z_eave, c.z_ridge), "tin"),
             kp.Part("box", (pc, -D / 2 - c.s_stair / 2), (pw, c.s_stair), (0, c.z_porch_eave[0]), "wall"),
             kp.Part("box", (pc, vl), (pw, c.porch_len - c.s_stair), (0, c.z_porch_eave[1]), "wall"),
             kp.Part("pyr", (pc, vl), (pw + 0.9, c.porch_len - c.s_stair + 0.9),
                     (c.z_porch_eave[1], c.z_porch_ridge[1]), "tin"))
    return kp.Building(c.name, c.group, c.center, c.yaw, parts, footprint(c),
                       "S-09, S-126…S-129, OSM relation 4060615; высоты — по камерам фото; см. prikaz_plan.PrikazPlan",
                       hero=c.hero, base=c.base)


def buildings():
    """Приказные палаты для krom_plan.buildings()."""
    return [prikaz_palaty()]


if __name__ == "__main__":
    import krom_geo as geo
    c = PRIKAZ
    els = geo.load_elements(geo.latest("krom_2*.json"))
    ways = {e["id"]: e for e in els if e["type"] == "way"}
    rel = next(e for e in els if e["type"] == "relation" and e["id"] == c.relation)
    rings = geo.assemble_rings([(ways[m["ref"]]["nodes"], geo.local_points(ways[m["ref"]]["geometry"]))
                                for m in rel["members"] if m["role"] == "outer"])
    ring = max(rings, key=lambda r: abs(geo.signed_area(r)))
    loc = [to_local(c.center, c.yaw, q) for q in ring]
    main = [(u, v) for u, v in loc if v > -11.3]          # узлы крыльца у фасада — на v −11,43
    porch = [(u, v) for u, v in loc if v < -12.0]
    us, vs = [q[0] for q in main], [q[1] for q in main]
    pu, pv = [q[0] for q in porch], [q[1] for q in porch]
    print(f"{c.name}: OSM r{c.relation} {abs(geo.signed_area(list(ring))):.0f} м²; основной объём u {min(us):+.2f}…"
          f"{max(us):+.2f}, v {min(vs):+.2f}…{max(vs):+.2f} ({max(us) - min(us):.2f} × {max(vs) - min(vs):.2f}); "
          f"крыльцо u {min(pu):+.2f}…{max(pu):+.2f}, до v {min(pv):+.2f}")
    a, b = c.porch_u
    print(f"план: {c.length} × {c.depth} (v {-c.depth / 2:+.2f}…{c.depth / 2:+.2f}), крыльцо u {a:+.2f}…{b:+.2f}, "
          f"до v {-c.depth / 2 - c.porch_len:+.2f}")
    fp = footprint(c)
    print(f"контур плана {abs(geo.signed_area(list(fp))):.0f} м²; hero {c.hero}; "
          f"base {tuple(round(x, 2) for x in c.base)}")
    assert abs(max(vs) - c.depth / 2) < 0.1, "южный фасад ушёл с линии стены OSM"
    print("ok")
