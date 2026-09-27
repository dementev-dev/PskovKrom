"""finpark_plan.py — Финский парк (парк Куопио) и плотина на Пскове у пешеходного моста: что и где ставит
scripts/finpark_krom.py и какие модели строит scripts/blender/finpark.py (M5+).

Чистый Python без bpy, unreal и numpy — импортируется редактором UE, Blender и обычным Python:

    PYTHONIOENCODING=utf-8 .venv/Scripts/python scripts/finpark_plan.py   # сводка, plan.png, pool_ring.json

Что это (источники — docs/REFERENCES.md, S-75…S-80):
  - Парк Куопио, он же Финский парк (OSM way 38938144, alt_name) — пейзажный парк на левом берегу Псковы
    от пешеходного моста в Бродах вверх по реке к Кузнецкому мосту, на «Милицейском островке». Заложен
    в начале 1990-х по проекту архитекторов из Куопио, города-побратима (S-76); реконструкция 2015 г. (проект
    2012 г.): дорожки и велодорожки, прямой мостик через протоку, два мостика «для влюблённых», детская площадка —
    «большой корабль» на резиновом покрытии, лабиринт из кустарника, фонари, скамейки и «диваны» (S-77, S-78).
  - Плотина на Пскове (OSM waterway=weir 66838593, у южного конца — площадка «Шлюз» 251885747, tourism=viewpoint)
    построена в 1974 г. для поддержания уровня воды: к середине XX в. Пскова обмелела до 20–30 см (S-75);
    водослив с большой пропускной способностью, без неё упала бы глубина на всём подпоре и «нарушится ландшафт
    Финского парка» (S-79). Прямой бетонный водослив ≈49 м поперёк реки в ≈30 м выше пешеходного моста
    (OSM 66837904), по краям — белые бетонные устои; на южном — маячок с красным колпаком (фото S-80: dam01,
    dam02, fpA11, fpA13). Перепад, высоты устоев и маячка — гипотеза по фото (ниже, HEAD_M и др.).
  - Большая часть парка (Y > 1008 м: площадка у Кузнецкого моста, клумбы, лодочная станция, второй мостик
    «для влюблённых», скамейки у площади) — за краем Landscape (terrain_krom.HALF), на кольце горизонта: там
    не ставим ничего (трасса мимо Landscape), см. build/finpark_refs/proposals.md.

Оси (D-013): x — север, y — восток, метры от центра Троицкого собора; координаты OSM — срез Overpass 2026-05-06
(build/finpark_refs/osm_finpark.json; © участники OSM, ODbL, как S-02), округлены до 0,1 м и вписаны сюда
литералами: в refs/osm части
путей парка нет (выгрузка у Крома их не берёт), а расстановка не должна зависеть от сети.

Как ставится (finpark_krom.py): модель — StaticMesh SM_FinPark_<Имя> (build/finpark/*.glb). Высота — z_mode:
  "water"  — от уреза Landscape (refs/dem/heightmap_L_Krom.json: water_level_z_m): плотина стоит в воде, трасса
             там попала бы в дно русла;
  "ground" — трассой по Landscape в точке при каждом запуске (рельеф ещё меняют terrain_krom и дороги);
  "stairs" — трассой в первом и последнем узле лестницы: меш сдвигается на землю в первом узле и растягивается
             по Z, чтобы подъём совпал с трассой (в модели — подъём по heightmap на 2026-09-26, STAIR_Z);
  "deck"   — мостик: трассой в концах, настил на выше из концов + DECK_ABOVE_M.
Модель без трассы (за краем Landscape) пропускается.
"""
import json
import math
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANDSCAPE_HALF_M = 1008.0   # terrain_krom.HALF: Landscape от −HALF до +HALF по X и Y
EDGE_MARGIN_M = 1.0         # ближе к краю Landscape точки не ставим (мостик 380961441 — в 1,1 м)

# ---------- OSM (срез 2026-05-06), локальные метры ----------
WAYS = {
    38938144: [(-156.6, 1248.4), (-155.1, 1172.9), (-127.8, 1053.6), (-94.7, 986.8), (-89.6, 976.8), (-49.5, 997.1),
               (-23.2, 955.0), (10.0, 943.3), (15.2, 917.4), (2.7, 899.6), (-16.8, 818.2), (-47.2, 769.5),
               (-91.8, 795.8), (-99.5, 769.1), (-77.1, 749.7), (-77.8, 735.2), (-22.0, 688.3), (-19.6, 702.2),
               (-14.2, 707.3), (-10.6, 711.6), (-8.4, 714.1), (28.7, 728.9), (48.0, 765.7), (58.2, 790.3),
               (58.4, 817.8), (48.6, 883.8), (30.2, 967.2), (27.5, 1023.4), (35.6, 1062.8), (64.2, 1123.7),
               (82.1, 1163.4), (88.6, 1202.3), (87.3, 1228.1), (81.1, 1251.5), (68.2, 1277.0), (52.6, 1305.6),
               (37.8, 1326.4), (17.7, 1347.9), (6.2, 1353.8), (-18.7, 1358.9), (-39.6, 1361.5), (-57.3, 1361.4),
               (-64.6, 1349.9), (-84.6, 1349.6), (-114.9, 1355.5), (-143.5, 1362.6), (-167.0, 1324.6),
               (-152.6, 1311.1), (-143.0, 1296.5), (-139.6, 1263.8), (-156.6, 1248.4)],  # leisure=park «парк Куопио»
    66838593: [(27.5, 680.0), (-10.6, 711.6)],  # waterway=weir: гребень плотины, с севера на юг
    251885747: [(-14.2, 707.3), (-24.7, 716.2), (-22.0, 719.3), (-18.9, 723.0), (-8.4, 714.1), (-10.6, 711.6),
                (-14.2, 707.3)],  # «Шлюз»: footway, place=square, surface=concrete, viewpoint, waterway=lock_gate
    66837904: [(38.2, 635.4), (-59.9, 717.4)],  # пешеходный мост (bridge_krom: PskovaEast)
    67215711: [(-59.9, 717.4), (-75.9, 730.7)],  # footway, lit=yes: от моста к лестнице
    67215712: [(-75.9, 730.7), (-86.9, 739.4), (-84.1, 743.4), (-89.4, 747.7)],  # steps, lit=yes: к ул. Воровского
    67215717: [(-86.9, 739.4), (-90.2, 734.9), (-96.0, 738.7)],  # steps, lit=yes: вторая ветвь с площадки
    371099803: [(-62.8, 713.7), (-52.8, 705.3)],  # steps, handrail=no: от моста вниз, к реке
    371099804: [(-57.2, 720.8), (-46.2, 711.8)],  # steps, handrail=no, ramp:wheelchair=yes
    371099802: [(-62.8, 713.7), (-59.9, 717.4), (-57.2, 720.8)],  # footway у головы моста
    305954019: [(-75.9, 730.7), (-67.5, 740.6), (-60.4, 749.2), (-34.9, 782.6), (-18.5, 810.1), (-7.8, 835.6),
                (-7.7, 835.1), (-3.9, 861.2), (1.7, 887.4), (3.1, 891.0), (16.2, 907.6), (21.8, 914.8),
                (24.8, 915.0)],  # pedestrian «Милицейская улица» — главная аллея, asphalt
    119210646: [(15.5, 953.8), (13.6, 959.9), (7.5, 986.1), (4.5, 1005.7), (6.8, 1026.7), (8.1, 1035.0),
                (13.8, 1073.4), (21.5, 1098.0), (-45.7, 1085.8), (-56.3, 1084.0), (-54.5, 1057.6), (-51.8, 1046.2),
                (-47.0, 1035.5), (-43.6, 1028.6), (-39.2, 1018.3), (-38.7, 1017.3), (-21.5, 991.2), (-10.2, 978.0),
                (13.6, 959.9)],  # footway, paving_stones: аллея вокруг детской зоны
    376238051: [(12.5, 953.6), (-16.2, 975.9), (-34.1, 993.6), (-47.4, 1012.1), (-55.0, 1026.7), (-63.0, 1050.3),
                (-65.4, 1072.5), (-64.8, 1090.4)],  # cycleway, lit=yes (дальше — за краем Landscape)
    119210575: [(24.8, 915.0), (26.9, 905.1), (27.8, 900.6), (37.8, 852.4), (37.9, 845.0), (38.1, 841.2),
                (38.1, 837.2), (36.4, 821.3), (32.7, 808.5), (27.1, 798.0), (26.2, 796.1), (20.8, 788.7),
                (-2.5, 756.2), (-30.2, 726.9), (-56.2, 699.8), (-59.5, 699.5), (-62.4, 702.0), (-65.5, 704.7),
                (-83.5, 719.3)],  # footway, asphalt: береговая дорожка
    364661758: [(-16.7, 797.2), (-10.1, 800.5), (-3.2, 799.5), (0.7, 796.6), (5.6, 794.2), (11.0, 794.1),
                (15.9, 795.9), (22.2, 801.0), (27.6, 809.4), (29.4, 816.8), (30.9, 824.5), (27.7, 835.0),
                (25.8, 841.1), (20.9, 846.1), (17.1, 853.8), (18.0, 865.1), (22.5, 878.2), (23.0, 887.2),
                (19.8, 898.5)],  # cycleway
    364661769: [(1.6, 820.2), (-1.8, 817.3), (-4.0, 813.3), (-4.8, 808.9), (-4.1, 804.5), (-1.9, 800.5),
                (1.4, 797.5), (5.4, 795.8), (9.7, 795.4), (13.9, 796.5), (17.5, 798.8), (20.2, 802.2),
                (21.7, 806.2), (21.9, 810.5), (20.7, 814.7), (18.2, 818.2), (14.5, 820.8), (10.2, 822.1),
                (5.7, 821.9), (1.6, 820.2)],  # footway, paved: кольцо Ø ≈27 м
    371686050: [(-24.1, 762.1), (-24.9, 768.7), (-25.2, 776.5), (-24.1, 782.3), (-20.7, 789.3), (-16.7, 797.2),
                (-3.5, 829.6), (-2.1, 832.9), (1.9, 843.4), (3.4, 858.4), (4.8, 870.8), (7.5, 885.5),
                (10.3, 891.3), (15.6, 896.4), (19.8, 898.5), (21.1, 906.4), (21.8, 914.8)],  # cycleway
    370889390: [(-36.1, 763.0), (-36.7, 760.9), (-36.5, 758.7), (-35.7, 756.7), (-34.1, 755.1), (-32.2, 754.1),
                (-30.0, 753.8), (-27.9, 754.3), (-26.0, 755.4), (-24.6, 757.2), (-24.0, 758.7), (-23.8, 760.4),
                (-24.1, 762.1), (-25.1, 764.0), (-26.7, 765.6), (-28.7, 766.5), (-30.9, 766.7), (-33.0, 766.1),
                (-34.8, 764.8), (-36.1, 763.0)],  # cycleway: кольцо Ø ≈13 м
    364661730: [(-42.2, 717.4), (-40.0, 721.0), (-35.6, 731.6), (-29.5, 746.5), (-24.6, 757.2)],  # cycleway
    368877904: [(-113.6, 683.7), (-107.7, 693.1), (-93.7, 709.2), (-90.5, 710.0), (-87.0, 710.7), (-83.7, 711.0),
                (-80.5, 710.4), (-76.1, 708.4), (-66.3, 702.7), (-64.2, 702.4), (-62.4, 702.0), (-59.7, 702.1),
                (-57.3, 702.7), (-52.8, 705.3), (-50.9, 707.1), (-46.2, 711.8), (-42.2, 717.4)],  # cycleway
    371099800: [(-7.7, 835.1), (-2.1, 832.9), (0.6, 831.7), (13.4, 826.5), (21.4, 831.3), (27.7, 835.0),
                (38.1, 841.2)],  # footway
    371099801: [(29.4, 816.8), (27.3, 822.0), (24.5, 828.2), (21.4, 831.3), (17.3, 834.4), (9.9, 835.5),
                (0.6, 831.7), (-3.5, 829.6)],  # cycleway
    370889392: [(3.1, 891.0), (7.5, 885.5), (18.0, 865.1), (37.9, 845.0)],  # footway
    119210582: [(24.8, 915.0), (17.2, 946.6)],  # footway
    380959871: [(21.8, 914.8), (14.2, 946.3)],  # cycleway
    373362116: [(-54.7, 730.0), (-47.6, 738.5), (-60.4, 749.2), (-62.0, 750.2), (-69.1, 741.9), (-67.5, 740.6),
                (-54.7, 730.0)],  # footway, area: мощёная площадка у моста со скамейками
    1018873053: [(-30.2, 726.9), (-22.0, 719.3)],  # footway к «Шлюзу»
    371101281: [(-86.2, 754.0), (-89.4, 747.7), (-96.0, 738.7), (-101.4, 736.1), (-107.4, 735.5), (-104.5, 742.1),
                (-101.2, 761.4), (-100.5, 766.0), (-86.2, 754.0)],  # footway, area, lit=yes: площадка у улицы
    380961441: [(-57.7, 1005.2), (-51.7, 1008.6)],  # bridge, footway, wood: мостик «для влюблённых» (1-й)
    343869565: [(-59.7, 1022.0), (-65.1, 1019.2)],  # bridge, footway, wood: мостик «для влюблённых» (2-й)
    119210609: [(17.2, 946.6), (15.5, 953.8)],  # bridge, footway: через устье протоки
    380959870: [(14.2, 946.3), (12.5, 953.6)],  # bridge, cycleway: рядом, в 3 м
    380959873: [(7.5, 986.1), (4.5, 1005.7), (-9.9, 1011.8), (-33.6, 1022.5), (-39.2, 1018.3), (-21.5, 991.2),
                (-10.2, 978.0), (0.6, 980.0), (7.5, 986.1)],  # leisure=playground, surface=tartan
    119210602: [(-64.4, 1023.4), (-53.8, 1004.6), (-45.1, 993.0), (-12.4, 960.1), (1.8, 952.1), (31.4, 945.8),
                (66.8, 943.8)],  # waterway=stream: протока, впадает в Пскову
    638140184: [(-124.2, 1150.3), (-123.2, 1131.4), (-119.6, 1117.2), (-111.6, 1080.3), (-86.4, 1020.0),
                (-78.9, 975.6), (-78.9, 948.9), (-65.4, 917.5), (-57.2, 897.7), (-65.2, 868.2), (-72.3, 838.7),
                (-66.1, 818.6), (-68.2, 804.0), (-83.7, 764.4), (-86.4, 760.5)],  # man_made=embankment: бровка откоса
}
BENCH_NODES = {   # amenity=bench в парке на Landscape: у моста и у ул. Воровского backrest=no, material=wood (S-41)
    3820124432: (-55.3, 733.9), 3820124433: (-63.0, 740.1), 3820124434: (-51.0, 738.5),
    6014764315: (-76.2, 813.1), 6014764316: (-76.0, 818.4),
    11038048592: (3.5, 989.2), 11038048593: (2.6, 984.9),
}
PHOTO_VIEWPOINT = (-16.2, 675.7)  # OSM tourism=viewpoint 3768409093 на пешеходном мосту: вид на плотину
PATH_HALF_W = {"pedestrian": 1.5, "footway": 1.0, "cycleway": 1.25, "steps": 1.5}   # гип., как osm_layers
PATH_KIND = {305954019: "pedestrian", 376238051: "cycleway", 364661758: "cycleway", 371686050: "cycleway",
             370889390: "cycleway", 364661730: "cycleway", 368877904: "cycleway", 371099801: "cycleway",
             380959871: "cycleway", 67215712: "steps", 67215717: "steps", 371099803: "steps", 371099804: "steps"}
PATHS = (67215711, 67215712, 67215717, 371099803, 371099804, 371099802, 305954019, 119210646, 376238051, 119210575,
         364661758, 364661769, 371686050, 370889390, 364661730, 368877904, 371099800, 371099801, 370889392, 119210582,
         380959871, 1018873053)

# ---------- плотина ----------
# Высоты — от уреза ниже плотины (урез Landscape: Пскова ниже плотины в подпоре Великой, 30,0 м БС — S-14…S-16,
# terrain_krom).
HEAD_M = 1.5            # перепад верхний − нижний бьеф, гипотеза 1–2 м: dam01 (июль), dam02, fpA13; br01–br03 (март,
                        # половодье) — ≈0,8 м над пеной; OSM ele=31 у нижней Псковы — грубая отметка
OVERFLOW_M = 0.15       # слой перелива над гребнем в межень (гип.)
CREST_Z = HEAD_M - OVERFLOW_M
SOUTH_TOP_Z = 4.0       # верх южного устоя («Шлюз»): на dam02 грань к реке 8,9 м (OSM) ≈ 2,2 × высоты — гип.
NORTH_TOP_Z = 3.0       # верх северного устоя: dam01 — ниже южного (гип.)
BODY_BOTTOM_Z = -2.5    # тело водослива уходит под дно (дно русла terrain_krom — до −4 м у стрежня)
FOAM_Z = 0.04           # пена ниже водослива — белая плита чуть над урезом (гип., на Esri полоса пены ≈8 м)
FOAM_U = (2.6, 9.0)     # от и до по течению (м от гребня)
NORTH_BLOCK_UV = ((-2.5, 5.5), (0.0, 4.5))   # устой у Запсковья: по течению и в берег от конца гребня (гип., dam01,
                                             # Esri — белый короб у северного конца)
SOUTH_LIGHT = dict(inset=0.7, r=0.4, h=2.0, cap=0.55)   # маячок: у верхнего угла южного устоя (dam02) — Ø0,8 × 2,0 м
NORTH_LIGHT = dict(inset=0.6, r=0.22, h=1.3, cap=0.3)   # столбик у верхнего угла северного устоя (dam01, гип.)
GATE = dict(u=(2.4, 4.2), z=(0.1, 1.4), depth=0.35)     # тёмный проём затвора в грани устоя к реке (dam01, гип.)


def _unit(dx, dy):
    n = math.hypot(dx, dy)
    return dx / n, dy / n


class WeirFrame:
    """Оси плотины: u — вниз по течению (к пешеходному мосту), v — вдоль гребня к северному концу (правее u,
    как Y правее X в UE), начало — середина гребня OSM на урезе. yaw — поворот +X модели к +Y (как в UE)."""

    def __init__(self):
        (xa, ya), (xb, yb) = WAYS[66838593]          # северный и южный концы гребня
        self.origin = ((xa + xb) / 2, (ya + yb) / 2)
        self.v = _unit(xa - xb, ya - yb)             # к северному концу
        self.u = (self.v[1], -self.v[0])             # левее v на 90°: вниз по течению
        self.half = math.hypot(xa - xb, ya - yb) / 2
        self.yaw = math.degrees(math.atan2(self.u[1], self.u[0]))

    def to_uv(self, x, y):
        dx, dy = x - self.origin[0], y - self.origin[1]
        return dx * self.u[0] + dy * self.u[1], dx * self.v[0] + dy * self.v[1]

    def to_xy(self, u, v):
        return (self.origin[0] + u * self.u[0] + v * self.v[0], self.origin[1] + u * self.u[1] + v * self.v[1])


def weir_blocks():
    """Устои в осях плотины: {"south": ((u0, u1), (v0, v1)), "north": ...}. Южный — рамка площадки «Шлюз» OSM
    (грань к реке 8,9 м по течению, 13,8 м в берег), северный — NORTH_BLOCK_UV от конца гребня."""
    f = WeirFrame()
    uv = [f.to_uv(x, y) for x, y in WAYS[251885747][:-1]]
    us, vs = [p[0] for p in uv], [p[1] for p in uv]
    (nu0, nu1), (nv0, nv1) = NORTH_BLOCK_UV
    return {"south": ((round(min(us), 2), round(max(us), 2)), (round(min(vs), 2), round(-f.half, 2))),
            "north": ((nu0, nu1), (round(f.half + nv0, 2), round(f.half + nv1, 2)))}


# ---------- лестницы ----------
# Подъём по узлам — heightmap_L_Krom.png на 2026-09-26 (м от первого узла); сегмент с |dz| < LANDING_DZ — площадка.
# Финально подъём подгоняет трасса в редакторе (z_mode "stairs").
STAIR_Z = {67215712: [0.0, 2.12, 2.3, 3.1], 67215717: [0.0, -0.13, 0.74], 371099803: [0.0, -1.38],
           371099804: [0.0, -2.07]}
STAIRS = {   # ширина (гип.) и перила: br04 — широкий марш с перилами по краям и посередине; handrail=no — без
    67215712: dict(width=3.6, rails=3, note="к ул. Воровского от моста (br04)"),
    67215717: dict(width=2.4, rails=2, note="вторая ветвь с площадки (гип.)"),
    371099803: dict(width=2.4, rails=0, note="от моста к реке, handrail=no"),
    371099804: dict(width=2.4, rails=0, note="от моста к реке, handrail=no, пандус"),
}
LANDING_DZ = 0.3
STEP_RISE_M = 0.15


def stair_profile(way):
    """Узлы лестницы [(x, y, z)] — z от первого узла; площадка (|dz| < LANDING_DZ) ровная на высоте верхнего из двух
    узлов, чтобы не уходить под рельеф."""
    pts, zs = WAYS[way], list(STAIR_Z[way])
    for k in range(len(zs) - 1):
        if abs(zs[k + 1] - zs[k]) < LANDING_DZ:
            zs[k] = zs[k + 1] = max(zs[k], zs[k + 1])
    return [(x, y, round(z - zs[0], 3)) for (x, y), z in zip(pts, zs)]


# ---------- мостики, корабль, фонари ----------
DECK_ABOVE_M = 0.3       # настил над землёй у концов (как bridge_krom.FOOT["deck_above"])
FLAT_BRIDGE = dict(length=9.0, width=5.5)     # прямой мостик 2015 г. через устье протоки: пеший и велосипедный путь
HUMP_BRIDGE = dict(length=7.0, width=1.6, rise=0.9)   # мостики «для влюблённых» (fpB05, fpB06)
HUMP_DECK_ABOVE_M = 0.05  # горбатый мостик концами лежит на земле
SHIP = dict(length=11.0, beam=3.6)            # «большой корабль» детской площадки — гипотеза, фото нет
LAMP_WAYS = (305954019, 119210646, 376238051, 67215711)  # аллеи с фонарями (fpA01; lit=yes у 376238051, 67215711)
LAMP_STEP_M = 25.0       # гип.: на fpA01 соседние фонари — через ≈20–30 м
LAMP_SIDE_GAP_M = 0.8    # от края аллеи
LAMP_H_M = 4.1           # см. finpark.py: lamp()


def _seg_dist(p, a, b):
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy), (ax + t * dx, ay + t * dy)


def dist_to_way(p, way):
    """(расстояние, ближайшая точка) от p до ломаной way."""
    return min((_seg_dist(p, a, b) for a, b in zip(WAYS[way], WAYS[way][1:])), key=lambda r: r[0])


def inside_landscape(x, y, margin=EDGE_MARGIN_M):
    return abs(x) <= LANDSCAPE_HALF_M - margin and abs(y) <= LANDSCAPE_HALF_M - margin


def along(way, step, start):
    """Точки через step м по ломаной way, первая — в start м от начала: [(x, y, tx, ty)] с касательной."""
    out, s_next, s0 = [], start, 0.0
    for a, b in zip(WAYS[way], WAYS[way][1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if seg < 1e-6:
            continue
        t = ((b[0] - a[0]) / seg, (b[1] - a[1]) / seg)
        while s_next <= s0 + seg:
            k = s_next - s0
            out.append((a[0] + t[0] * k, a[1] + t[1] * k, t[0], t[1]))
            s_next += step
        s0 += seg
    return out


def half_w(way):
    return PATH_HALF_W[PATH_KIND.get(way, "footway")]


def lamp_points():
    """Фонари парка вдоль LAMP_WAYS через LAMP_STEP_M справа по ходу (к бровке откоса — как у Псковы «со стороны
    холма»), отступ — полуширина + LAMP_SIDE_GAP_M; отказ, если ближе к другой дорожке, чем её полуширина + зазор,
    или за краем Landscape. Гипотеза: в OSM фонарей парка нет, есть только lit=yes и фото fpA01."""
    out, rejected = [], {"edge": 0, "path": 0}
    for way in LAMP_WAYS:
        off = half_w(way) + LAMP_SIDE_GAP_M
        for x, y, tx, ty in along(way, LAMP_STEP_M, LAMP_STEP_M / 2):
            px, py = x - ty * off, y + tx * off          # справа по ходу: (−ty, tx)
            if not inside_landscape(px, py):
                rejected["edge"] += 1
                continue
            if any(dist_to_way((px, py), w)[0] < half_w(w) + LAMP_SIDE_GAP_M - 0.05 for w in PATHS if w != way):
                rejected["path"] += 1
                continue
            yaw = math.degrees(math.atan2(ty, tx))
            out.append(dict(x=round(px, 2), y=round(py, 2), yaw_deg=round(yaw, 1), way=way))
    return out, rejected


def bench_points():
    """Скамейки OSM: сидящий лицом к ближайшей дорожке или площадке (в парке скамейки стоят вдоль аллей)."""
    out = []
    for nid, (x, y) in BENCH_NODES.items():
        d, q = min((dist_to_way((x, y), w) for w in PATHS + (373362116, 371101281)), key=lambda r: r[0])
        yaw = math.degrees(math.atan2(q[1] - y, q[0] - x)) if d > 0.05 else 0.0
        out.append(dict(x=x, y=y, yaw_deg=round(yaw, 1), osm_id=nid))
    return out


def _mid(way):
    (xa, ya), (xb, yb) = WAYS[way][0], WAYS[way][-1]
    return (xa + xb) / 2, (ya + yb) / 2, math.degrees(math.atan2(yb - ya, xb - xa))


def placements():
    """Всё, что ставит finpark_krom.py: [dict(asset, x, y, yaw_deg, z_mode, ...)] — порядок не важен."""
    f = WeirFrame()
    out = [dict(asset="SM_FinPark_Weir", x=round(f.origin[0], 2), y=round(f.origin[1], 2), yaw_deg=round(f.yaw, 2),
                z_mode="water", src="OSM 66838593, 251885747; фото dam01, dam02 (S-80)")]
    for way in STAIRS:
        prof = stair_profile(way)
        out.append(dict(asset=f"SM_FinPark_Stairs_{way}", x=prof[0][0], y=prof[0][1], yaw_deg=0.0, z_mode="stairs",
                        end=(prof[-1][0], prof[-1][1]), rise=prof[-1][2], src=f"OSM {way}"))
    # прямой мостик — посередине между пешей и велосипедной линиями OSM (одна плита на обе, гип.)
    xs = [p for w in (119210609, 380959870) for p in WAYS[w]]
    cx, cy = sum(p[0] for p in xs) / 4, sum(p[1] for p in xs) / 4
    _, _, yaw = _mid(119210609)
    out.append(dict(asset="SM_FinPark_FlatBridge", x=round(cx, 2), y=round(cy, 2), yaw_deg=round(yaw, 1), z_mode="deck",
                    ends=[WAYS[119210609][0], WAYS[119210609][1]], src="OSM 119210609 + 380959870; S-77"))
    for way in (380961441, 343869565):
        x, y, yaw = _mid(way)
        out.append(dict(asset="SM_FinPark_HumpBridge", x=round(x, 2), y=round(y, 2), yaw_deg=round(yaw, 1),
                        z_mode="deck", ends=[WAYS[way][0], WAYS[way][-1]], src=f"OSM {way}; фото fpB05, fpB06"))
    # корабль — в середине площадки 380959873 по её длинной оси, носом к реке (гипотеза: фото нет)
    out.append(dict(asset="SM_FinPark_Ship", x=-12.0, y=999.5, yaw_deg=-36.9, z_mode="ground",
                    src="OSM 380959873 (tartan); S-77 «большой корабль» — форма и место гипотеза"))
    lamps, _ = lamp_points()
    out += [dict(asset="SM_FinPark_Lamp", x=p["x"], y=p["y"], yaw_deg=p["yaw_deg"], z_mode="ground",
                 src=f"правило вдоль {p['way']} (гип.)") for p in lamps]
    out += [dict(asset="SM_Furn_Bench", x=p["x"], y=p["y"], yaw_deg=p["yaw_deg"], z_mode="ground",
                 src=f"OSM {p['osm_id']}") for p in bench_points()]
    for p in out:
        p["inside"] = inside_landscape(p["x"], p["y"])
    return out


# ---------- сводка и картинки (только .venv) ----------

def pool_ring():
    """Кольцо воды OSM выше плотины (refs/osm/krom_water_*.json: начинается на линии гребня), обрезанное по
    Landscape, — для предложения о верхнем бьефе (build/finpark_refs/pool_ring.json)."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import krom_geo as geo
    rings = geo.water_rings(geo.load_elements(geo.latest("krom_water_*.json")))["rings"]
    up = [r for r in rings if min(p[1] for p in r) > 670 and min(p[1] for p in r) < 690]
    h = LANDSCAPE_HALF_M
    return [[(round(x, 1), round(y, 1)) for x, y in geo.clip_to_rect(geo.open_ring(r), -h, h, -h, h)] for r in up]


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image

    out_dir = os.path.join(REPO, "build", "finpark_refs")
    items = placements()
    lamps, rejected = lamp_points()
    counts = {}
    for p in items:
        key = p["asset"] + ("" if p["inside"] else " (за краем)")
        counts[key] = counts.get(key, 0) + 1
    f = WeirFrame()
    print(f"[finpark_plan] плотина: середина ({f.origin[0]:.2f}, {f.origin[1]:.2f}), гребень {2 * f.half:.1f} м, "
          f"yaw {f.yaw:.2f}°, перепад {HEAD_M} м (гип.), устои {weir_blocks()}")
    print(f"[finpark_plan] {counts}; фонари — отказы {rejected}")
    rings = pool_ring()
    with open(os.path.join(out_dir, "pool_ring.json"), "w", encoding="utf-8") as fh:
        json.dump({"note": "вода OSM выше плотины (krom_water), обрезана по Landscape; x — север, y — восток, м",
                   "level_above_water_m": HEAD_M, "weir": WAYS[66838593], "rings": rings}, fh, ensure_ascii=False)

    # план: Esri (S-21, только сверка) + OSM + что ставим + точки съёмки фото
    X0, X1, Y0, Y1 = -130.0, 90.0, 630.0, 1040.0
    fig, ax = plt.subplots(figsize=(16, 16 * (X1 - X0) / (Y1 - Y0) + 0.6), dpi=90)
    sat = os.path.join(out_dir, "work", "sat.png")
    if os.path.exists(sat):   # окно esri.py: X [−200, 200], Y [600, 1300]
        ax.imshow(Image.open(sat), extent=(600, 1300, -200, 200), alpha=0.75)
    for w, pts in WAYS.items():
        c, lw = ("yellow", 1.4) if w == 38938144 else ("orange", 1.0) if w == 638140184 else \
            ("deepskyblue", 1.2) if w == 119210602 else ("red", 2.5) if w == 66838593 else \
            ("white", 2.0) if w == 66837904 else ("magenta", 1.2) if w in STAIRS else ("cyan", 0.8)
        ax.plot([p[1] for p in pts], [p[0] for p in pts], color=c, lw=lw, alpha=0.8)
    for r in rings:
        ax.fill([p[1] for p in r], [p[0] for p in r], color="blue", alpha=0.18, lw=0)
    style = {"SM_FinPark_Weir": ("s", "red", 9), "SM_FinPark_Lamp": ("o", "gold", 5),
             "SM_Furn_Bench": ("s", "white", 5),
             "SM_FinPark_FlatBridge": ("D", "sienna", 8), "SM_FinPark_HumpBridge": ("D", "chocolate", 8),
             "SM_FinPark_Ship": ("^", "tomato", 11)}
    for p in items:
        m, c, s = style.get(p["asset"], ("v", "magenta", 8))
        ax.plot(p["y"], p["x"], m, color=c, ms=s, mec="black", mew=0.6, alpha=1.0 if p["inside"] else 0.35)
    for nm, (u0, u1), (v0, v1) in ((k, *b) for k, b in weir_blocks().items()):
        ring = [f.to_xy(u, v) for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1), (u0, v0))]
        ax.plot([q[1] for q in ring], [q[0] for q in ring], color="red", lw=1.5)
    foam = [f.to_xy(u, v) for u, v in ((FOAM_U[0], -f.half), (FOAM_U[1], -f.half), (FOAM_U[1], f.half),
                                       (FOAM_U[0], f.half))]
    ax.fill([q[1] for q in foam], [q[0] for q in foam], color="white", alpha=0.5)
    man = os.path.join(out_dir, "manifest.json")
    if os.path.exists(man):
        with open(man, encoding="utf-8") as fh:
            for ph in json.load(fh)["photos"]:
                g = (ph.get("geotag") or {}).get("local_m")
                if g and X0 < g[0] < X1 and Y0 < g[1] < Y1:
                    ax.plot(g[1], g[0], "*", color="lime", ms=9, mec="black")
                    ax.text(g[1] + 2, g[0] + 2, os.path.basename(ph["file"]).split("_")[0], color="lime", fontsize=7)
    ax.axvline(LANDSCAPE_HALF_M, color="red", ls="--", lw=1.2)
    ax.text(LANDSCAPE_HALF_M - 3, X1 - 8, "край Landscape Y = 1008", color="red", ha="right", fontsize=9)
    ax.set_xlim(Y0, Y1)
    ax.set_ylim(X0, X1)
    ax.set_aspect("equal")
    ax.set_xlabel("Y, м (восток)")
    ax.set_ylabel("X, м (север)")
    ax.set_title("Финский парк и плотина: жёлтый — парк OSM, красный — гребень и устои, белое — пена; ■ белые — "
                 "скамейки, ● — фонари (гип.), ◆ — мостики, ▲ — корабль (гип.), ▼ — лестницы; ★ — фото; "
                 "бледные — за краем Landscape", fontsize=8)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    path = os.path.join(out_dir, "plan.png")
    fig.savefig(path)
    print(f"[finpark_plan] {path}, pool_ring.json: {len(rings)} кольцо, {sum(len(r) for r in rings)} точек")


if __name__ == "__main__":
    main()
