"""pskovgu_plan.py — план зданий Псковского государственного университета (ПсковГУ) в зоне Landscape: главный корпус
на пл. Ленина, 2 и корпус исторического факультета на ул. Леона Поземского, 6. Общий источник для blockout
(buildings()) и героев scripts/blender/pskovgu.py.

Чистый Python без `unreal` и `bpy`, импортируется сам по себе (нужен только krom_geo). Координаты — локальные метры
(D-013): x — север, y — восток. Оси здания, как у krom_plan.Building: u — по азимуту yaw, v — вправо от него
(yaw + 90°), z — от земли в точке base. Цифры — из docs/REFERENCES.md (S-130…S-134): контуры OSM (S-02), история —
pleskov60 и ru.wikipedia; высоты и членения — по фото Commons (build/pskovgu_refs/manifest.json) с восстановленными
камерами (build/pskovgu/fit_*.py); «гип.» — оценка.

krom_plan импортируется лениво, внутри функций: подключение — строкой в krom_plan.buildings() (см. buildings()).

    python scripts/pskovgu_plan.py     # сверка плана с контурами OSM и проверка, что city_mesh снимет коробки
"""
import functools
import math
from dataclasses import dataclass

import krom_geo as geo


@dataclass(frozen=True)
class MainPlan:
    """Главный корпус ПсковГУ (бывший Псковский пединститут им. С. М. Кирова), пл. Ленина, 2: строился с 1955 г.
    на восточной стороне площади Ленина (до войны — перекрёсток Петропавловской и Сергиевской улиц), закончен
    в сентябре 1960 г. (S-131); в проекте 1950-х — «четырёхэтажное здание пединститута в центре» новой площади
    (S-132). Архитектор здания — не установлен (Н. С. Бутенко — архитектор памятника Ленину перед ним, S-131).

    План — контур OSM way 39012972 (S-02), вычищенный (слиты ступеньки по 5 см) и симметричный по оси портика:
    главный фасад 99,3 м на запад, к площади; портик на подиуме выступает на 3,43 м; к востоку — три крыла
    (Ш-образный план): южное и северное по 17 м шириной, среднее 16,4 м; северное крыло продолжено ещё на 34 м
    (пристройка, время — не установлено). Оси: u — вдоль главного фасада на север (yaw −8,2°), v — внутрь здания
    (на восток); фасад v = 0, портик — v < 0; начало — ось портика на линии фасада.

    Высоты — по фото c01 (S-130, камера восстановлена по углам фасада, краям портика и вершине фронтона, фокусное
    из EXIF, невязка ≤4 пкс; build/pskovgu/fit_c01b.py), проверены на c06 и c11 (оба сняты с юго-запада, на c11 —
    южный торец: пояс у угла 5,26, «тройное» окно в 3,4 м от угла, дальний угол крыла v ≈ 36,8 при OSM 36,5;
    fit_c06.py, fit_c11.py): 1-й этаж высокий, пояс над ним 4,7–5,25, этажи
    по ≈3,75 м, антаблемент 15,45–17,25, верх карниза 17,85, фронтон до 21,5. Нуль высот — земля у портика.
    Фасад: 8 осей с пилястрами по сторонам портика, торцевые части с «итальянскими» (тройными) окнами
    и фронтончиком над окном 2-го этажа; портик — 8 колонн большого ордера (крайние парные) на подиуме
    с пятью дверями. Дворовые фасады и пристройка — гипотеза (фото нет): те же этажи и шаг осей.

    Цвет — по фото 2011–2025: стены белые (в 2013 г. светло-серые) — «wall», кровля — светлая оцинковка «tin».
    Расхождение: в задаче владельца «зелёная кровля» — на фото 2011–2025 зелёного нет."""
    name: str = "ПсковГУ, главный корпус"
    key: str = "Main"
    asset: str = "SM_PskovGU_Main"
    group: str = "City"
    way: int = 39012972
    origin: tuple = (-300.77, 275.36)   # ось портика на линии главного фасада (середина между узлами OSM)
    yaw: float = -8.20                  # главный фасад, узлы OSM (два отрезка по 38 м: −8,20° и −8,20°)
    # контур (u, v) против часовой на плане, от юго-западного угла портика; выверен по OSM (≤0,25 м)
    outline: tuple = ((-11.175, -3.43), (11.175, -3.43), (11.175, 0.0), (49.65, 0.0), (49.65, 36.46),
                      (48.05, 36.46), (48.05, 70.92), (28.23, 70.92), (28.23, 39.09), (32.26, 39.09),
                      (32.26, 10.4), (12.85, 10.4), (12.85, 14.9), (7.81, 14.9), (7.81, 38.77), (1.85, 38.77),
                      (1.85, 40.25), (-1.53, 40.25), (-1.53, 38.77), (-8.56, 38.77), (-8.56, 14.9),
                      (-13.46, 14.9), (-13.46, 10.4), (-32.61, 10.4), (-32.61, 36.48), (-49.65, 36.48),
                      (-49.65, 0.0), (-11.175, 0.0))
    half: float = 49.65                 # полудлина главного фасада (OSM: −49,84 / +49,47)
    depth: float = 10.4                 # глубина главного корпуса (OSM)
    wing_s: tuple = (-49.65, -32.61, 36.48)     # южное крыло: u от, до; конец по v
    wing_n: tuple = (32.26, 49.65, 36.46)       # северное крыло
    annex: tuple = (28.23, 48.05, 36.46, 70.92)  # пристройка к северному крылу: u, v (OSM)
    wing_c: tuple = (-8.56, 7.81, 38.77)        # среднее крыло; перемычка к корпусу — u ±13 при v 10,4…14,9
    link_c: tuple = (-13.46, 12.85, 14.9)
    stair_c: tuple = (-1.53, 1.85, 40.25)       # выступ на торце среднего крыла (лестница? OSM)
    portico: tuple = (11.175, 3.43)     # полуширина и вынос подиума портика (OSM)
    columns: tuple = (1.8, 5.4, 9.0, 10.45)     # оси колонн от оси портика (фото c01), зеркально
    col_d: float = 0.95                 # диаметр колонн внизу (фото c01, гип. ±0,1)
    col_v: float = -2.85                # оси колонн по v
    z_plinth: float = 0.6               # серый цоколь, гип.
    z_belt: tuple = (4.7, 5.25)         # пояс над 1-м этажом = верх подиума портика (фото c01: 4,68…5,28 / 5,15)
    z_arch: float = 15.45               # низ антаблемента, верх колонн (c01: 15,3…15,5)
    z_frieze: float = 17.25             # низ карниза (c01: 17,27 у северного угла)
    z_eave: float = 17.85               # верх карниза (c01: 17,83)
    z_pediment: float = 21.5            # вершина фронтона портика (c01: 21,45…21,57)
    pitch: float = 22.0                 # уклон скатов, ° (гип.: по видимой части кровли на c01 и c11)
    low: tuple = (1.9, 3.7)             # окна 1-го этажа: низ, верх (c01: 1,8…3,8 у угла, 2,6…3,6 у портика)
    floors: tuple = ((5.35, 7.6), (9.05, 11.35), (12.8, 15.1))   # окна 2–4 этажей (c01)
    bay: float = 3.45                   # шаг осей крыльев главного фасада (c01: 3,45…3,6)
    bays: int = 8                       # осей между портиком и торцевой частью (c01, с обеих сторон)
    end_block: float = 38.8             # торцевая часть: u от ±38,8 до ±49,65 (водосток на c01)
    triple: float = 44.2                # ось «тройного» окна торцевой части (c01: 44,0 и −44,35)
    side_triple: float = 3.4            # торец крыла: «тройное» окно у угла (c11: v 1,3…5,4)
    side_first: float = 7.85            # торец крыла: первая ось за ним (c11: 7,8; 11,2; 14,6; 18,0; 21,5 — шаг 3,43)
    side_bays: int = 9                  # осей до конца крыла (c11 видно 5 — дальше дерево; остальные — гип.)
    doors: tuple = (0.0, 3.6, 7.2)      # двери подиума, зеркально (c01), ширина 2,0, верх 3,6
    win_w: float = 1.45                 # ширина окон (c01)

    @property
    def base(self):
        """Земля у середины передней грани портика — нуль высот (c01 и прочие фото сняты с площади)."""
        return to_world(self.origin, self.yaw, 0.0, -self.portico[1])

    @property
    def hero(self):
        return f"/Game/Krom/Architecture/{self.group}/{self.asset}"


@dataclass(frozen=True)
class Pozemskogo6Plan:
    """Дом Общества слепых, ул. Леона Поземского, 6 — корпус исторического факультета ПсковГУ (S-133, S-134).
    Построен в 1953 г. хозяйственным способом по проекту 1949 г. архитектора К. Дидрихса; двухэтажный
    с полуподвалом, кровля вальмовая; план повторяет изгиб улицы; главный фасад симметрично-осевой: неглубокий
    центральный ризалит с разорванным щипцом, парадный вход — портик с парными рустованными пилястрами, над ним три
    арочных окна; по флангам ризалита на 2-м этаже — окна с сандриками; крылья — ровный ряд прямоугольных окон,
    в 1-м этаже в лепных «архивольтах», по краям — одиночные рустованные пилястры; дворовый фасад без обрамлений
    (S-133). Высота помещений: полуподвал 2,7, этажи 3,1 м (S-133). Объект культурного наследия регионального
    значения № 6001142000 (S-134).

    План — контур OSM way 61675938 (7 узлов, S-02): уличный фасад на восток ломаный — два крыла сходятся под углом
    11,8° у ризалита (узел OSM в 1 м от середины фасада). Оси: начало — середина уличного фасада, u — по биссектрисе
    крыльев на север
    (yaw 19,4°), v — вправо, к улице; крылья отходят от оси u на ±5,9° назад (концы — на v ≈ −3). Глубина — по
    дворовым узлам OSM (10,7…13,1), принято 12,0 (гип. ±1). Членения и высоты — по фото p01 (A. Savin, 2018, FAL:
    анфас, масштаб — длина фасада по OSM, горизонт — по головам прохожих; build/pskovgu/fit_poz6_p01.py) и p02
    (AndyVolykhov, 2023: с северо-востока, масштаб — глубина торца; fit_poz6.py); расхождение высот между ними
    ≈1 м (15 %) — приняты средние. Нуль высот — земля у оси фасада. Улица под фасадом падает к югу на ≈1,6 м
    (p01: у северного угла +0,8, у южного −0,8 от нуля), в heightmap — на 2,4 м (+1,3 / −1,1).
    Цвет: стены розовые, обрамления белые — ключа «розовый» в krom_plan.COLORS нет: стены — «house» (ближайший
    из существующих; гип.), обрамления — «wall», кровля — тёмная крашеная сталь «roof»."""
    name: str = "ПсковГУ, ул. Леона Поземского, 6"
    key: str = "Pozemskogo6"
    asset: str = "SM_PskovGU_Pozemskogo6"
    group: str = "City"
    way: int = 61675938
    origin: tuple = (54.89, 230.41)     # ось симметрии на уличном фасаде: 28,45 м от обоих концов по контуру OSM
    yaw: float = 19.4                   # биссектриса крыльев (азимуты 13,5° и 25,3°)
    bend: float = 5.9                   # крылья повёрнуты на ±5,9° от оси u назад (от улицы)
    wing_n: float = 28.45               # крылья по фасаду от оси: фасад по OSM 56,9 м (27,5 + 29,4 от узла излома —
    wing_s: float = 28.45               # узел в 1 м к северу от оси; фасад симметричный, S-133)
    depth: float = 12.0                 # глубина корпуса (OSM 10,7…13,1; гип.)
    risalit: tuple = (9.3, 0.35)        # ризалит с плечами: полуширина (p01: 9,3), вынос (гип.)
    gable: float = 4.6                  # полуширина средней части под щипцом (p01: 4,6)
    z_plinth: float = 0.8               # гладкий цоколь (p01), окна полуподвала — в нём
    z_belt: tuple = (4.5, 4.75)         # межэтажная тяга (p01: 5,06, p02: 4,4 — среднее)
    z_eave: float = 7.6                 # верх карниза крыльев (низ: p01 7,7, p02 6,7; принято 7,2 + 0,4)
    z_risalit: float = 9.6              # верх карниза ризалита (p01: 10,05; гип. ±0,5)
    z_gable: float = 12.0               # вершина щипца (p01: 12,9, p02: 11,2)
    pitch: float = 28.0                 # уклон вальмы, ° (гип.)
    low: tuple = (1.8, 3.6)             # окна 1-го этажа (p01), над ними «архивольты»
    up: tuple = (4.9, 6.8)              # окна 2-го этажа — на тяге (p01)
    bay: float = 2.55                   # шаг осей крыльев: 7 осей между ризалитом и краевой пилястрой (p01: 2,1…2,4
    bays: int = 7                       # у южного конца в перспективе; гип.)
    win_w: float = 0.95                 # ширина окон (p01: 0,85 в свету)

    @property
    def hero(self):
        return f"/Game/Krom/Architecture/{self.group}/{self.asset}"


MAIN = MainPlan()
POZEMSKOGO6 = Pozemskogo6Plan()
PSKOVGU = (MAIN, POZEMSKOGO6)


def to_world(origin, yaw, u, v):
    t = math.radians(yaw)
    return origin[0] + u * math.cos(t) - v * math.sin(t), origin[1] + u * math.sin(t) + v * math.cos(t)


def to_local(origin, yaw, p):
    t = math.radians(yaw)
    dx, dy = p[0] - origin[0], p[1] - origin[1]
    return dx * math.cos(t) + dy * math.sin(t), -dx * math.sin(t) + dy * math.cos(t)


def rot(p, a):
    """Поворот точки (u, v) плана на a градусов от оси u к оси v."""
    t = math.radians(a)
    return p[0] * math.cos(t) - p[1] * math.sin(t), p[0] * math.sin(t) + p[1] * math.cos(t)


def poz_outline(p=POZEMSKOGO6):
    """Контур дома на Поземского (u, v): два крыла под углом, ризалит у излома. Против часовой на плане."""
    d = p.depth
    n1, nb = rot((p.wing_n, 0.0), -p.bend), rot((p.wing_n, -d), -p.bend)     # северное крыло: к u > 0
    s1, sb = rot((-p.wing_s, 0.0), p.bend), rot((-p.wing_s, -d), p.bend)     # южное: к u < 0
    back = (0.0, -d / math.cos(math.radians(p.bend)))    # дворовый излом — пересечение задних линий крыльев
    return (sb, back, nb, n1, (0.0, 0.0), s1)


@functools.lru_cache(maxsize=None)
def osm_ring(way):
    els = geo.load_elements(geo.latest("krom_2*.json"))
    w = next(e for e in els if e["type"] == "way" and e["id"] == way)
    return tuple(geo.open_ring(geo.local_points(w["geometry"])))


def offset(poly, d):
    """Многоугольник, раздвинутый наружу на d (стороны параллельно; углы — пересечения соседних сторон)."""
    n = len(poly)
    area = sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))
    sgn = 1.0 if area > 0 else -1.0
    lines = []
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        L = math.hypot(x1 - x0, y1 - y0)
        t = ((x1 - x0) / L, (y1 - y0) / L)
        lines.append(((x0 + t[1] * sgn * d, y0 - t[0] * sgn * d), t))
    out = []
    for i in range(n):
        (p, t), (q, s) = lines[i - 1], lines[i]
        den = t[0] * s[1] - t[1] * s[0]
        if abs(den) < 1e-6:
            out.append(q)
            continue
        a = ((q[0] - p[0]) * s[1] - (q[1] - p[1]) * s[0]) / den
        out.append((p[0] + a * t[0], p[1] + a * t[1]))
    return out


PLINTH_PROUD = 0.3   # футпринт героя — контур модели по цоколю и карнизу (раздвинут на 0,3 м)


def outline(p):
    return p.outline if hasattr(p, "outline") else poz_outline(p)


def footprint(p):
    """Контур героя в мировых метрах (x, y): контур плана, раздвинутый на PLINTH_PROUD. Им city_mesh снимает коробку
    OSM (по центру тяжести её контура — у главного корпуса он в 6 см от стены среднего крыла, во дворе; раздвижка
    на 0,3 м его накрывает — проверка в __main__)."""
    return tuple(to_world(p.origin, p.yaw, u, v) for u, v in offset(list(outline(p)), PLINTH_PROUD))


# ---------- blockout (пока нет героя) ----------

def main_building():
    import krom_plan as kp
    c = MAIN
    ze, t = c.z_eave, math.tan(math.radians(c.pitch))
    h = c.half
    parts = [kp.Part("box", (0, c.depth / 2), (2 * h, c.depth), (0, ze), "wall"),
             kp.Part("pyr", (0, c.depth / 2), (2 * h + 1, c.depth + 1), (ze, ze + c.depth / 2 * t), "tin"),
             kp.Part("box", (0, -c.portico[1] / 2), (2 * c.portico[0], c.portico[1]), (0, c.z_eave), "wall")]
    for u0, u1, v1 in (c.wing_s, c.wing_n, c.wing_c):
        du, dv = u1 - u0, v1 - c.depth
        parts += [kp.Part("box", ((u0 + u1) / 2, (c.depth + v1) / 2), (du, dv), (0, ze), "wall"),
                  kp.Part("pyr", ((u0 + u1) / 2, (c.depth + v1) / 2), (du + 1, dv + 1), (ze, ze + du / 2 * t), "tin")]
    u0, u1, v0, v1 = c.annex
    parts += [kp.Part("box", ((u0 + u1) / 2, (v0 + v1) / 2), (u1 - u0, v1 - v0), (0, ze), "wall"),
              kp.Part("pyr", ((u0 + u1) / 2, (v0 + v1) / 2), (u1 - u0 + 1, v1 - v0 + 1), (ze, ze + (u1 - u0) / 2 * t),
                      "tin")]
    return kp.Building(c.name, c.group, c.origin, c.yaw, tuple(parts), footprint(c),
                       "OSM way 39012972, S-130…S-132; высоты — по фото S-130; см. pskovgu_plan.MainPlan",
                       hero=c.hero, base=c.base)


def pozemskogo6():
    import krom_plan as kp
    c = POZEMSKOGO6
    L = c.wing_n + c.wing_s
    um = (c.wing_n - c.wing_s) / 2
    parts = (kp.Part("box", (um, -c.depth / 2 - 1.5), (L, c.depth), (0, c.z_eave), "house"),
             kp.Part("pyr", (um, -c.depth / 2 - 1.5), (L + 1, c.depth + 1),
                     (c.z_eave, c.z_eave + c.depth / 2 * math.tan(math.radians(c.pitch))), "roof"))
    return kp.Building(c.name, c.group, c.origin, c.yaw, parts, footprint(c),
                       "OSM way 61675938, S-133, S-134; см. pskovgu_plan.Pozemskogo6Plan", hero=c.hero)


def buildings():
    """Здания ПсковГУ для krom_plan.buildings() (группа City): герои scripts/blender/pskovgu.py."""
    return [main_building(), pozemskogo6()]


def point_in(p, ring):
    x, y, inside = p[0], p[1], False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _dist_seg(p, a, b):
    ax, ay = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / (ax * ax + ay * ay)))
    return math.dist(p, (a[0] + t * ax, a[1] + t * ay))


def deviation(ring, poly):
    """Наибольшее расстояние от узлов ring до сторон poly (м)."""
    return max(min(_dist_seg(q, poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))) for q in ring)


if __name__ == "__main__":
    for p in PSKOVGU:
        osm = list(osm_ring(p.way))
        plan = [to_world(p.origin, p.yaw, u, v) for u, v in outline(p)]
        fp = list(footprint(p))
        c = geo.centroid(osm)
        d1, d2 = deviation(osm, plan), deviation(plan, osm)
        inside = point_in(c, fp)
        print(f"{p.name}: OSM {len(osm)} узлов, {abs(geo.signed_area(osm)):.0f} м²; план {len(plan)} узлов, "
              f"{abs(geo.signed_area(plan)):.0f} м²; расхождение OSM→план {d1:.2f} м, план→OSM {d2:.2f} м; "
              f"центр OSM ({c[0]:.1f}, {c[1]:.1f}) в футпринте: {inside}; hero {p.hero}")
        assert inside, f"{p.name}: city_mesh не снимет коробку OSM — центр её контура вне футпринта героя"
        lim = 0.4 if p is MAIN else 2.0      # у Поземского контур OSM грубый (7 узлов), глубина — гипотеза
        assert d1 < lim and d2 < lim, f"{p.name}: контур плана разошёлся с OSM на {max(d1, d2):.2f} м"
    print("ok")
