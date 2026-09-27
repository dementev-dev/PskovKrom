"""zapskovye_plan.py — герои партии 1 (D-043): первый ряд Запсковья напротив Крома через Пскову — Советская
набережная, 6, 4 (дом Кузьменковых и розовый дом рядом), 1/2 (доходный дом Русакова) и ул. Леона Поземского, 5.
Общий источник для blockout (buildings()) и героев scripts/blender/zapskovye.py.

Чистый Python без `unreal` и `bpy` (нужны krom_geo и помощники pskovgu_plan). Координаты — локальные метры (D-013):
x — север, y — восток. Оси дома, как у krom_plan.Building: u — по азимуту yaw, v — вправо от него (yaw + 90°),
z — от нуля дома (набережная или тротуар у главного фасада). Дом собран из блоков: четырёхугольник в плане (u, v),
высота карниза, кровля, цвета по ключам krom_plan.COLORS и фасады с осями окон. Цифры — docs/REFERENCES.md
(S-148…S-152): контуры OSM (S-02), история — pleskov60 и реестр ОКН; высоты и оси — по фото Commons
(build/zapskovye_refs/manifest.json) с восстановленными камерами (build/zapskovye/fit_*.py). «гип.» — оценка.

Набережная (дома 1/2, 4, 6) построена заново в 2000-е по старым открыткам (реконструкция 2003 г., S-149):
«Золотая набережная».

krom_plan импортируется лениво, внутри функций: подключение — строкой в krom_plan.buildings() (см. buildings()).

    python scripts/zapskovye_plan.py     # сверка планов с контурами OSM и проверка, что city_mesh снимет коробки
"""
from dataclasses import dataclass

import krom_geo as geo
from pskovgu_plan import deviation, offset, osm_ring, point_in, to_world


@dataclass(frozen=True)
class Facade:
    """Фасад по стороне edge четырёхугольника блока (от угла edge к углу edge + 1). axes — оси проёмов, метры от
    начала стороны; rows — ряды (z0, z1, вид): "r" прямоугольный, "a" с полуциркульным верхом; cut — вырез и стекло
    (фасад с фото) или окна-плоскости (гипотеза); hood — {номер ряда: "shelf" | "tri"} сандрики; skip — (ряд, ось)
    без проёма; doors — (ось, ширина, верх) двери 1-го этажа вместо окна."""
    edge: int
    axes: tuple
    rows: tuple
    w: float = 1.2
    cut: bool = True
    hood: tuple = ()
    skip: tuple = ()
    doors: tuple = ()


@dataclass(frozen=True)
class Block:
    """Объём: четырёхугольник quad [(u, v)] (выпуклый), стены от низа до z_eave (верх карниза), кровля roof:
    "hip" — вальмовая, "gable" — двускатная с коньком вдоль сторон 0 и 2 (щипцы — стороны 1 и 3), "front" —
    двускатная с щипцом (фронтоном) на стороне 0, "mansard" — мансардная (нижний скат rise, отступ inset, верх —
    пологая вальма 0,6 м), "shed" — односкатная (выше сторона 2); low — цвет 1-го этажа до z_belt."""
    name: str
    quad: tuple
    z_eave: float
    roof: str
    rise: float
    wall: str = "wall"
    trim: str = "wall"
    roof_key: str = "tin"
    low: str = ""
    z_belt: float = 0.0
    z_plinth: float = 0.6
    belts: tuple = ()
    fronts: tuple = ()
    backs: tuple = ()
    chimneys: tuple = ()
    inset: float = 1.2


def rq(u0, u1, v0, v1):
    """Прямоугольник: сторона 0 — фасад v = v0 от u0 к u1, дальше против хода к v1."""
    return ((u0, v0), (u1, v0), (u1, v1), (u0, v1))


def along(u0, us):
    """Оси окон по координате u → метры от начала стороны u0."""
    return tuple(round(abs(u - u0), 3) for u in us)


def grid(length, step, margin=1.5):
    """Оси окон-плоскостей (гипотеза): через step, от краёв не ближе margin."""
    n = int((length - 2 * margin) // step) + 1 if length > 2 * margin else 0
    s0 = (length - (n - 1) * step) / 2
    return tuple(round(s0 + k * step, 3) for k in range(n))


@dataclass(frozen=True)
class House:
    name: str
    key: str
    asset: str
    way: int
    origin: tuple            # начало осей (x, y)
    yaw: float
    outline: tuple           # контур дома (u, v) — OSM, приведённый к осям (для футпринта)
    base: tuple              # (u, v): земля heightmap здесь — нуль дома
    base_z: float            # низ стен: земля под контуром ниже нуля (heightmap)
    blocks: tuple
    note: str = ""
    group: str = "City"

    @property
    def hero(self):
        return f"/Game/Krom/Architecture/{self.group}/{self.asset}"

    @property
    def base_xy(self):
        return to_world(self.origin, self.yaw, *self.base)


# ---------- Советская наб., 4: розовый дом и дом Кузьменковых ----------
# Оси: начало — середина речного фасада OSM w61675937 (узлы A (20,30; 141,38) и B (58,25; 124,85)), u — вдоль фасада
# на северо-запад (yaw −23,54°), v — внутрь, от реки. Высоты и оси — фото c20 (karel291, 2015) и c01 (AndyVolykhov,
# 2023), камеры и отметки подобраны совместно (build/zapskovye/fit_nab4.py, невязка ≤9 пкс на кадре 3840).

N4_ROWS = ((1.70, 3.45, "r"), (5.12, 6.84, "r"), (8.46, 10.22, "r"))      # розовый дом, c20
N4_PINK_AXES = (18.13, 16.07, 12.26, 9.45, 6.77, 2.94, 1.00)
N4_BLUE_AXES = (-7.03, -9.05, -12.64, -16.22, -18.18)

NAB4 = House(
    name="Советская наб., 4 (дом Кузьменковых и розовый дом)", key="Nab4", asset="SM_Zapskovye_Nab4", way=61675937,
    origin=(39.275, 133.115), yaw=-23.54,
    outline=((20.70, 0.0), (20.42, 16.16), (-6.69, 16.71), (-6.76, 23.81), (-2.36, 23.79), (-1.94, 35.74),
             (-18.16, 36.44), (-18.50, 22.90), (-20.25, 20.80), (-20.42, 13.0), (-20.69, 0.0)),
    base=(10.0, 16.2), base_z=-6.4,
    blocks=(
        # розовый дом: 3 этажа (1-й серо-белый), крылья под зелёной мансардой с «кокошниками», средняя часть —
        # 4-й этаж под фронтоном (центр 9,4; фронтон — отдельный блок pink_mid)
        Block("pink", rq(20.67, -1.55, 0.0, 16.2), 11.72, "flat", 0.0, wall="pink", low="wall", z_belt=3.84,
              roof_key="green", z_plinth=0.5,
              fronts=(Facade(0, along(20.67, N4_PINK_AXES), N4_ROWS, w=1.05, hood=((1, "shelf"),),
                             doors=((round(20.67 - 9.45, 3), 1.5, 3.3),)),),
              backs=((2, 2.8, N4_ROWS),)),
        Block("pink_mid", rq(14.13, 4.63, 0.0, 16.2), 14.95, "front", 17.33 - 14.95, wall="pink", roof_key="green",
              z_plinth=11.72,
              fronts=(Facade(0, along(14.13, (12.26, 9.45, 6.77)), ((11.95, 13.37, "a"),), w=1.05),)),
        Block("pink_wing_nw", rq(20.67, 14.13, 0.0, 16.2), 11.72, "mansard", 3.26, roof_key="green", z_plinth=11.72,
              inset=1.3, chimneys=((19.2, 3.5), (15.5, 3.0))),
        Block("pink_wing_se", rq(4.63, -1.55, 0.0, 16.2), 11.72, "mansard", 3.26, roof_key="green", z_plinth=11.72,
              inset=1.3, chimneys=((3.2, 3.0), (-0.2, 3.5))),
        # связка с балконами (утоплена, гип. 1 м)
        Block("link", rq(-1.55, -4.59, 1.0, 16.2), 11.24, "hip", 1.9, z_plinth=0.5,
              fronts=(Facade(0, (1.52,), ((5.12, 7.2, "r"), (8.46, 10.6, "r")), w=1.3),)),
        # дом Кузьменковых (голубой; ключа нет — wall): 3 этажа, фронтон на всю ширину с люнетом
        Block("blue", rq(-4.59, -20.67, 0.0, 16.2), 11.48, "front", 15.76 - 11.48, z_plinth=0.5,
              belts=(3.84, 7.30),
              fronts=(Facade(0, along(-4.59, N4_BLUE_AXES), ((1.70, 3.45, "r"), (5.12, 6.84, "r"), (8.46, 10.10, "a")),
                             w=1.05, hood=((1, "shelf"),), skip=((1, 2),)),),
              backs=((2, 2.8, N4_ROWS),), chimneys=((-8.0, 9.0), (-17.0, 9.0))),
        # дворовый корпус за домом Кузьменковых (фото нет — гип.)
        Block("rear", ((-6.7, 16.2), (-18.4, 16.2), (-18.2, 36.4), (-2.0, 35.7)), 11.0, "hip", 3.0, z_plinth=0.5,
              backs=((1, 3.0, N4_ROWS), (2, 3.0, N4_ROWS), (3, 3.0, N4_ROWS))),
    ),
    note="OSM way 61675937; S-148…S-150; высоты — фото c20, c01 (fit_nab4.py)")

N4_BLUE_DOOR = (-12.64, 1.3, 4.5, 6.84)     # дверь на балкон 2-го этажа по оси фронтона (c03), гип. ширина
N4_LUNETTE = (-12.64, 1.72, 12.0)           # люнет во фронтоне: ось, ширина, низ (c20: 12,0…12,86)
N4_OCULUS = (9.54, 0.8, 15.9)               # круглое окно во фронтоне розового дома: ось, диаметр, центр (c20, гип.)
N4_DORMERS = ((17.83, 2.96), (1.29, 2.96))  # «кокошники» крыльев: ось, ширина (c20: 19,31…16,35; второй — зеркально)
N4_DORMER_Z = (12.18, 14.98)                # низ окна, верх полукружия (c20)
N4_BALCONIES = ((-3.07, 4.3, 2.6), (-3.07, 7.54, 2.6), (-12.64, 4.35, 2.2))   # ось, отметка плиты, ширина (c20, c03)

# ---------- Советская наб., 6 ----------
# Оси: начало — середина речного фасада OSM w96360303 (узлы (82,03; 114,94) и (120,67; 99,21)), u — на северо-запад
# (yaw −22,15°), v — внутрь. Фото: c20 (юго-восточный конец: карниз кремового блока 16,1, окна 3–4 этажей, низ
# кирпичного блока с аркой 8,6; fit_nab4.py + px2plane) и аэрофото a01 (A.Savin, 2018: доли секций вдоль фасада;
# fit_a01.py). Секции с северо-запада: кирпичная угловая, кремовая со щипцом, кремовая с фронтоном, лососёвая
# кирпичная, кремовый блок с аттиком, низкий кирпичный блок с аркой; дворовое крыло на северо-восток (4 этажа)
# с белой круглой башней на конце. По c20 юго-восточный конец дома — на 5–6 м северо-западнее узла OSM (контур
# OSM оставлен как есть). Дворовые фасады, крыло и башня — гипотеза (аэрофото, окна-плоскости). Юго-восточная
# стена дворового крыла сдвинута во двор на 0,4–0,8 м против OSM: центр контура OSM (внутренний угол «Г»,
# u 4,76, v 20,39) должен попасть в футпринт, иначе city_mesh оставит коробку.

N6_ROWS = ((1.2, 3.3, "a"), (5.4, 7.3, "r"), (8.73, 10.29, "r"), (11.93, 13.35, "r"))   # 3–4 — c20, 1–2 — гип.
N6_ROWS_BACK = ((1.4, 3.2, "r"), (5.4, 7.3, "r"), (8.73, 10.29, "r"), (11.93, 13.35, "r"))


def _n6_front(u0, u1, n, rows=N6_ROWS):
    L = abs(u1 - u0)
    return (Facade(0, tuple(round(L * (2 * k + 1) / (2 * n), 3) for k in range(n)), rows, w=1.1),)


NAB6 = House(
    name="Советская наб., 6", key="Nab6", asset="SM_Zapskovye_Nab6", way=96360303,
    origin=(101.35, 107.075), yaw=-22.15,
    outline=((-20.86, 0.0), (20.87, 0.0), (20.30, 55.65), (4.60, 51.27), (4.60, 14.38), (-5.66, 13.93),
             (-8.46, 17.90), (-8.41, 22.82), (-21.10, 22.23)),
    base=(0.0, 14.2), base_z=-3.0,
    blocks=(
        Block("s1_brick", rq(20.87, 12.2, 0.0, 14.2), 15.4, "hip", 2.6, wall="pink", low="wall", z_belt=4.3,
              belts=(4.3, 8.6), fronts=_n6_front(20.87, 12.2, 3), backs=((1, 3.2, N6_ROWS_BACK),),
              chimneys=((17.5, 7.0), (14.0, 11.0))),
        Block("s2_gable", rq(12.2, 6.4, 0.0, 14.2), 15.4, "front", 3.0, low="wall", z_belt=4.3, belts=(4.3, 8.6),
              fronts=_n6_front(12.2, 6.4, 2), chimneys=((9.3, 10.0),)),
        Block("s3_pediment", rq(6.4, 1.3, 0.0, 14.2), 14.9, "front", 2.9, low="wall", z_belt=4.3, belts=(4.3, 8.6),
              fronts=_n6_front(6.4, 1.3, 2), chimneys=((3.9, 9.0),)),
        Block("s4_salmon", rq(1.3, -7.6, 0.0, 14.2), 14.4, "hip", 2.8, wall="pink", belts=(4.3, 8.6),
              fronts=_n6_front(1.3, -7.6, 3), chimneys=((-2.0, 6.0), (-5.5, 10.0))),
        Block("s5_cream", rq(-7.6, -15.0, 0.0, 14.2), 16.1, "hip", 1.6, low="pink", z_belt=8.6, belts=(8.6, 14.4),
              fronts=_n6_front(-7.6, -15.0, 2), chimneys=((-9.5, 8.0), (-13.0, 8.0))),
        Block("gate", rq(-15.0, -20.86, 0.0, 14.2), 8.6, "hip", 1.8, wall="pink", belts=(4.3,),
              fronts=(Facade(0, (2.9,), ((5.2, 7.2, "r"),), w=1.1),),
              backs=((1, 3.2, ((1.4, 3.2, "r"), (5.2, 7.2, "r"))),)),
        Block("wing", ((20.87, 14.2), (4.60, 14.2), (4.60, 51.27), (20.30, 55.65)), 14.4, "hip", 2.5, wall="pink",
              belts=(4.3, 8.6), backs=((1, 3.2, N6_ROWS_BACK), (3, 3.2, N6_ROWS_BACK)),
              chimneys=((13.0, 25.0), (13.0, 35.0), (13.0, 45.0))),
        Block("rear_se", ((-5.66, 14.2), (-21.0, 14.2), (-21.1, 22.23), (-8.41, 22.82)), 11.0, "hip", 2.5,
              backs=((2, 3.2, N6_ROWS_BACK[:3]),)),
    ),
    note="OSM way 96360303; S-148, S-149; высоты — фото c20, доли секций — аэрофото a01 (гип. ±1–2 м)")

N6_GATE_ARCH = (-17.9, 2.6, 3.4)            # арка проезда в низком блоке: ось, ширина, верх (c20 — арочная дверь)
N6_TOWER = ((8.8, 49.0), 3.8, 17.6, 1.6)    # белая круглая башня: центр (u, v), радиус, карниз, подъём шатра (гип.)
N6_ATTIC = (14.4, 16.1)                     # аттик-фриз кремового блока (c20: 14,4…16,1)
N6_TOP_GLASS = (14.4, 17.2, 1.6)            # остеклённый верхний этаж дворового крыла: низ, верх, отступ (гип.)

# ---------- Советская наб., 1/2 (ул. Л. Поземского, 2): доходный дом Русакова ----------
# Оси: начало — середина речного фасада OSM w61675941 (узлы (−11,47; 196,35) — угол с ул. Л. Поземского и (−2,03;
# 177,95)), u — на северо-запад (yaw −62,84°), v — внутрь (на северо-восток). Фасад на реку — фото c07
# (Е. Борисова, 2023, анфас; fit_rus.py, невязка ≤4,5 пкс): 3 этажа и мансарда с четырьмя люкарнами, 7 осей.
# Уличный фасад и дворовые корпуса — гипотеза (тот же шаг осей; корпуса во дворе ниже, 3 этажа).

RUS_ROWS = ((1.0, 3.2, "r"), (4.47, 6.51, "r"), (9.24, 11.68, "r"))    # 1-й этаж под верандой — гип.
RUS_AXES = (6.97, 4.27, 1.56, -0.59, -2.74, -5.23, -7.72)

RUSAKOV = House(
    name="Доходный дом Русакова, Советская наб., 1/2", key="Rusakov", asset="SM_Zapskovye_Rusakov", way=61675941,
    origin=(-6.750, 187.150), yaw=-62.84,
    outline=((10.34, 0.0), (10.33, 7.08), (5.92, 7.06), (5.79, 15.79), (0.65, 15.79), (0.63, 26.67), (7.82, 26.67),
             (7.80, 34.83), (-10.41, 34.83), (-10.35, 0.0)),
    base=(-10.35, 0.0), base_z=-3.2,
    blocks=(
        Block("front", rq(10.34, -10.35, 0.0, 7.07), 13.78, "mansard", 2.2, z_plinth=0.5, belts=(4.37, 8.34),
              inset=1.0,
              fronts=(Facade(0, along(10.34, RUS_AXES), RUS_ROWS, w=1.2, hood=((1, "shelf"), (2, "shelf")),
                             skip=((1, 3),)),
                      Facade(1, (3.5,), RUS_ROWS, w=1.2, hood=((1, "shelf"), (2, "shelf")))),
              chimneys=((3.0, 4.5), (-4.0, 4.5))),
        Block("street", rq(5.85, -10.36, 7.07, 15.79), 13.78, "hip", 2.6, z_plinth=0.5, belts=(4.37, 8.34),
              fronts=(Facade(1, (1.6, 4.3, 7.0), RUS_ROWS, w=1.2, hood=((1, "shelf"), (2, "shelf"))),),
              backs=((2, 2.7, RUS_ROWS),), chimneys=((-7.5, 12.0),)),
        Block("yard1", ((0.65, 15.79), (-10.38, 15.79), (-10.38, 26.67), (0.63, 26.67)), 11.0, "hip", 2.5,
              z_plinth=0.5, backs=((1, 2.7, RUS_ROWS[:2] + ((7.8, 9.8, "r"),)), (2, 2.7, RUS_ROWS[:2]),
                                   (3, 2.7, RUS_ROWS[:2]))),
        Block("yard2", ((7.82, 26.67), (-10.38, 26.67), (-10.41, 34.83), (7.80, 34.83)), 11.0, "hip", 2.5,
              z_plinth=0.5, backs=((1, 2.7, RUS_ROWS[:2] + ((7.8, 9.8, "r"),)), (2, 2.7, RUS_ROWS[:2]),
                                   (3, 2.7, RUS_ROWS[:2]), (0, 2.7, RUS_ROWS[:2]))),
    ),
    note="OSM way 61675941; S-148…S-150; высоты — фото c07 (fit_rus.py)")

RUS_DORMERS = ((4.53, 2.05), (1.45, 2.05), (-1.98, 2.05), (-4.90, 2.05))   # люкарны на реку: ось, ширина (c07)
RUS_DORMER_Z = (13.94, 15.90)              # низ, верх окна люкарны (c07); щипец люкарны — до 16,4 (гип.)

# ---------- ул. Леона Поземского, 5 ----------
# Оси: начало — северный угол N (71,68; 275,84) у ул. Труда, u — вдоль главного северо-западного фасада на северо-
# восток (yaw 29,91°; фасад — u от −35,01 до 0), v — внутрь. Три корпуса (S-151): главный 1949 г. по ул. Поземского,
# северный 1958 г. по ул. Труда (под углом 121°), дворовый 1958 г. с односкатной кровлей. Высоты: северный корпус —
# фото p02 (Я. Игошин, 2013; fit_poz5.py, карниз по высоте помещений S-151), главный — p01 (грубо) и S-151.
# Главный фасад (S-151): от угла — две части по три окна с балконом в середине каждой, лопатки; сквозной проезд
# с балконом над ним и полуфронтоном; правая часть на три окна у соседнего дома. Цвет — выцветшая охристая
# штукатурка (2013): ключа «охра» нет — stone (ближайший), тяги и сандрики — wall.

P5_MAIN_ROWS = ((1.4, 3.3, "r"), (5.1, 7.2, "r"))           # гип. по S-151 (1-й этаж 3,20, 2-й 3,10)
P5_NORTH_ROWS = ((1.3, 2.9, "r"), (4.45, 6.39, "r"))        # p02 (2-й этаж), 1-й — гип.
P5_AXES = (-1.6, -4.8, -8.0, -11.3, -14.6, -17.9, -26.9, -30.0, -33.1)
P5_PILASTERS = (-0.3, -9.6, -19.6, -24.8)                   # лопатки главного фасада (S-151), места — гип.

POZ5 = House(
    name="Жилой дом, ул. Леона Поземского, 5", key="Pozemskogo5", asset="SM_Zapskovye_Pozemskogo5", way=61675936,
    origin=(71.68, 275.84), yaw=29.91,
    outline=((0.0, 0.0), (11.93, 19.51), (3.31, 24.73), (-5.01, 10.36), (-26.25, 10.70), (-25.93, 23.99),
             (-34.41, 24.13), (-34.51, 17.15), (-35.01, 0.0)),
    base=(0.0, 0.0), base_z=-1.4,
    blocks=(
        Block("main", ((0.0, 0.0), (-35.01, 0.0), (-35.0, 10.6), (-5.01, 10.36)), 8.35, "gable", 2.9, wall="stone",
              roof_key="roof", z_plinth=0.85, belts=(4.9,),
              fronts=(Facade(0, along(0.0, P5_AXES), P5_MAIN_ROWS, w=1.15, hood=((1, "shelf"),)),),
              backs=((2, 3.2, P5_MAIN_ROWS),), chimneys=((-8.0, 5.0), (-16.0, 5.0), (-30.0, 5.0))),
        Block("north", ((0.0, 0.0), (11.93, 19.51), (3.31, 24.73), (-5.01, 10.36)), 7.28, "gable", 2.6, wall="stone",
              roof_key="roof", z_plinth=0.6, belts=(4.33,),
              fronts=(Facade(0, tuple(round(1.154 + 3.174 * k, 3) for k in range(7)), P5_NORTH_ROWS, w=1.1,
                             hood=((1, "shelf"),)),
                      Facade(1, (2.4,), P5_NORTH_ROWS, w=1.0, cut=False)),
              backs=((2, 3.2, P5_NORTH_ROWS),), chimneys=((3.0, 13.0), (7.0, 19.0))),
        Block("yard", ((-26.25, 10.70), (-35.0, 10.6), (-34.41, 24.13), (-25.93, 23.99)), 6.8, "shed", 1.4,
              wall="stone", roof_key="roof", z_plinth=0.5, backs=((0, 3.0, ((1.2, 2.8, "r"), (4.0, 5.8, "r"))),
                                                  (1, 3.0, ((1.2, 2.8, "r"), (4.0, 5.8, "r"))),
                                                  (2, 3.0, ((1.2, 2.8, "r"), (4.0, 5.8, "r"))))),
    ),
    note="OSM way 61675936; S-150…S-152; высоты — p02 (fit_poz5.py) и S-151, главный фасад — гип. по S-151")

P5_ARCH = (-22.2, 3.0, 3.6)                 # сквозной проезд: ось, ширина, верх (p01 — ось 22,2 м от угла, грубо)
P5_BALCONIES = ((-4.8, 4.9, 2.4), (-14.6, 4.9, 2.4), (-22.2, 4.9, 2.8))   # балконы 2-го этажа (S-151; места — гип.)
P5_HALF_PEDIMENT = (-24.8, -19.6, 1.3)      # полуфронтон над проездом: от, до, подъём (гип.)

HOUSES = (NAB4, NAB6, RUSAKOV, POZ5)

PLINTH_PROUD = 0.3   # футпринт героя — контур дома, раздвинутый на 0,3 м (цоколь, карниз)


def outline(h):
    return h.outline


def footprint(h):
    """Контур героя в мировых метрах (x, y): им city_mesh снимает коробку OSM по её центру тяжести."""
    return tuple(to_world(h.origin, h.yaw, u, v) for u, v in offset(list(h.outline), PLINTH_PROUD))


# ---------- blockout (пока нет героя) ----------

def _block_parts(b, kp):
    us, vs = [p[0] for p in b.quad], [p[1] for p in b.quad]
    c = ((min(us) + max(us)) / 2, (min(vs) + max(vs)) / 2)
    size = (max(us) - min(us), max(vs) - min(vs))
    z0 = 0.0 if b.z_plinth < 5 else b.z_plinth
    parts = [kp.Part("box", c, size, (z0, b.z_eave), b.wall)] if b.z_eave - z0 > 0.1 else []   # мансарды — без стен
    if b.rise > 0:
        parts.append(kp.Part("pyr", c, (size[0] + 0.6, size[1] + 0.6), (b.z_eave, b.z_eave + b.rise), b.roof_key))
    return parts


def building(h):
    import krom_plan as kp
    parts = tuple(p for b in h.blocks for p in _block_parts(b, kp))
    return kp.Building(h.name, h.group, h.origin, h.yaw, parts, footprint(h),
                       f"{h.note}; см. zapskovye_plan", hero=h.hero, base=h.base_xy)


def buildings():
    """Герои партии 1 для krom_plan.buildings() (группа City): scripts/blender/zapskovye.py."""
    return [building(h) for h in HOUSES]


if __name__ == "__main__":
    els = geo.load_elements(geo.latest("krom_2*.json"))
    rings = {e["id"]: geo.open_ring(geo.local_points(e["geometry"])) for e in els
             if e["type"] == "way" and "building" in e.get("tags", {}) and None not in e["geometry"]}
    for h in HOUSES:
        osm = list(osm_ring(h.way))
        plan = [to_world(h.origin, h.yaw, u, v) for u, v in h.outline]
        fp = list(footprint(h))
        c = geo.centroid(osm)
        d1, d2 = deviation(osm, plan), deviation(plan, osm)
        inside = point_in(c, fp)
        print(f"{h.name}: OSM {len(osm)} узлов, {abs(geo.signed_area(osm)):.0f} м²; план {len(plan)} узлов, "
              f"{abs(geo.signed_area(plan)):.0f} м²; расхождение OSM→план {d1:.2f} м, план→OSM {d2:.2f} м; "
              f"центр OSM ({c[0]:.1f}, {c[1]:.1f}) в футпринте: {inside}; база {tuple(round(v, 2) for v in h.base_xy)}")
        assert inside, f"{h.name}: city_mesh не снимет коробку OSM — центр её контура вне футпринта героя"
        lim = 0.8 if h is NAB6 else 0.3           # у наб., 6 стена крыла сдвинута ради центра контура
        assert d1 < lim and d2 < lim, f"{h.name}: контур плана разошёлся с OSM на {max(d1, d2):.2f} м"
        for w, ring in rings.items():            # соседи (наб., 2, 3, 5, сарай во дворе наб., 6 и др.) остаются
            if w != h.way and len(ring) > 2:
                assert not point_in(geo.centroid(ring), fp), f"{h.name}: футпринт накрыл центр соседа w{w}"
        for b in h.blocks:                       # блоки не выходят за контур больше чем на 1,5 м (гип. упрощения)
            for u, v in b.quad:
                p = to_world(h.origin, h.yaw, u, v)
                if not point_in(p, fp):
                    dd = deviation([p], plan)
                    assert dd < 1.5, f"{h.name}/{b.name}: угол ({u}, {v}) вне контура на {dd:.1f} м"
    print("ok")
