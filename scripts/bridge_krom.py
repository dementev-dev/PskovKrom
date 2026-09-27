"""bridge_krom.py — мосты через Великую и Пскову в L_Krom, упрощённо: плита, балки, опоры, перила, фонари (M5, D-034).

Запуск:  python scripts/ue_run.py scripts/bridge_krom.py

Мосты — BRIDGES: линии OSM (bridge=yes) дают ось — у моста из нескольких параллельных линий (дорога и тротуары,
пешеходная и велодорожка) ось — средняя; ширина — из контура man_made=bridge или по расстоянию между линиями
(с источником или «гип.»). Высота настила на концах — земля Landscape у устоев (трасса) + deck_above, между ними —
прямая с выпуклостью camber. Опоры — piers (м от начала оси), если схема пролётов известна, иначе поровну,
не длиннее max_span. Сечение — kind: road (асфальт, тротуары с бортиком, фонари) или foot (настил, перила).
Геометрия — коробки wall_mesh.Mesh в осях моста (s — вдоль оси, t — поперёк, z), меш — GeometryScript, Nanite,
коллизия «complex as simple» (по мосту можно пройти). Слоты: concrete, road, metal.

Идемпотентен: удаляет свои акторы (тег generated:bridge_krom), пересобирает меши в те же ассеты и сохраняет.
"""
import importlib
import json
import math
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402
import palette_krom  # noqa: E402
import wall_mesh  # noqa: E402

importlib.reload(palette_krom)
wm = importlib.reload(wall_mesh)

LEVEL = "/Game/Krom/Maps/L_Krom"
TAG = unreal.Name("generated:bridge_krom")
FOLDER = "Generated/bridge_krom"
BRIDGE_DIR = "/Game/Krom/Environment/Bridges"
MAT_DIR = "/Game/Krom/Materials/Bridges"
MATS = ("concrete", "road", "metal", "screen", "walk", "globe")

# deck_min — настил не ниже стольких метров над урезом: откос берега в heightmap местами ниже улицы у моста;
# если устой выше земли, к нему идёт пандус длиной ramp (м) до земли (с подъездами roads_mesh, прибитыми к настилу
# насыпью, — D-038, BRIDGE_DECK_MIN — пандусов у Ольгинского и Советского нет). deck_above — верх полотна (настил
# − 0,02) вровень с лентой roads_mesh у устоя: проезжая часть на ROAD_SINK_M = 0,06 над землёй, дорожка на 0,04
ROAD = dict(kind="road", sidewalk=2.6, girder=1.6, deck_above=0.08, deck_min=5.0, ramp=20.0, camber=0.6, pier_t=1.8,
            pier_inset=2.0, lamps=32.0, lamp_h=9.0, max_span=45.0, piers=None)
FOOT = dict(kind="foot", sidewalk=0.0, girder=0.8, deck_above=0.06, deck_min=2.0, ramp=10.0, camber=0.8, pier_t=0.9,
            pier_inset=0.8, lamps=0.0, lamp_h=4.5, max_span=30.0, piers=None)
BRIDGES = {
    # S-47, S-48: неразрезная ж/б балка 1970 г., 25 + 28 + 32 + 57 + 75 + 57 + 32,4 = 306,4 м (ось OSM 304,9 —
    # опоры по схеме ×0,995); в воде 2 быка с U-вырезом и 4 добавочные опоры-пары, на суше парные столбы;
    # ширина 17–18 м (контур OSM занижен), профиль прямой; балка 2,7 м в центральных пролётах, 2,0 м в боковых
    "Olginsky": dict(ROAD, label="Ольгинский мост", ways=(38938146,), width=17.5, sidewalk=2.75, camber=0.0,
                     girder=2.7, girder_side=2.0, girder_main=(85.0, 274.0),
                     piers=tuple((s * 0.995, kind) for s, kind in (
                         (25, "land"), (53, "land"), (85, "land"), (122, "twin"), (142, "bull"), (162, "twin"),
                         (197, "twin"), (217, "bull"), (237, "twin"), (274, "land"))),
                     # фонари: над каждой опорой, в серединах 57-метровых пролётов и в третях 75-метрового (S-48)
                     lamps=tuple(s * 0.995 for s in (25, 53, 85, 113.5, 142, 167, 192, 217, 245.5, 274)),
                     lamp_style="globes", lamp_h=12.0, barrier=0.75),
    "Sovetsky": dict(ROAD, label="Советский мост", ways=(31386051,),
                     width=18.6,  # тротуары OSM 293887772/3 — в 15,6 м друг от друга, + по 1,5 м
                     sidewalk=3.0, girder=1.2, camber=0.3, lamps=25.0, max_span=26.0, deck_min=6.0),  # гип.
    # акт ГИКЭ S-49: стальной однопролётный разрезной, 42,66 м, 3 двутавра h 1,22 м через 2,28 м, проход 5 м
    # (2 + 2 м), устои на шпунте, опор в русле нет, дорожка у опоры ОК1 +35,5 м БС; экран из ламелей — фото S-50
    "Pskova2024": dict(FOOT, label="Пешеходный мост через Пскову (2024)", kind="screen",
                       ends=((224.4, -11.8), (245.4, 25.3)),  # пролёт: узел OSM у Крома → 42,66 м по оси
                       width=5.0, deck_z=35.5 - 43.15, camber=0.5, girder=1.22, girders=3, girder_step=2.28,
                       screen=(-1.65, 1.35), lamella=(0.10, 0.20),  # экран от/до настила, ламель и шаг, м
                       lamella_jitter=0.04,
                       platform=(8.0, 20.0)),  # Т-площадка на Запсковье: вдоль оси × поперёк (оценка по фото)
    # опоры — по Esri через ≈21,3 м от северного конца (38,2; 635,4), ±2 м (разведка Финского парка, P-7: dam02,
    # fpA12); ширина — гип.
    "PskovaEast": dict(FOOT, label="Пешеходный мост через Пскову", ways=(66837904,), width=3.5,
                       piers=(14.3, 35.6, 57.0, 78.2, 98.8, 120.1)),
}
CURB_M, DECK_T_M, GIRDER_INSET_M = 0.2, 0.35, 0.9
PIER_BED_M = -4.5          # низ опоры — под дном у стрежня (уреза −4 м); на суше опора уходит в землю
RAIL_H_M, RAIL_STEP_M = 1.1, 2.0
TRACE_Z_M = 300.0

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
mel = unreal.MaterialEditingLibrary
GS = unreal.GeometryScript_MeshEdits


class Frame:
    """Оси моста: s — вдоль оси от a к b, t — поперёк, z — вверх; точки — метры плана."""

    def __init__(self, a, b, z0, z1, camber):
        self.a, self.len = a, math.hypot(b[0] - a[0], b[1] - a[1])
        self.u = ((b[0] - a[0]) / self.len, (b[1] - a[1]) / self.len)
        self.v = (-self.u[1], self.u[0])
        self.z0, self.z1, self.camber = z0, z1, camber

    def deck(self, s):
        """Верх настила в точке s."""
        f = min(max(s / self.len, 0.0), 1.0)
        return self.z0 + (self.z1 - self.z0) * f + self.camber * 4 * f * (1 - f)

    def p(self, s, t, z):
        return (self.a[0] + self.u[0] * s + self.v[0] * t, self.a[1] + self.u[1] * s + self.v[1] * t, z)


def box(mesh, fr, mat, s0, s1, t0, t1, zb, zt):
    """Коробка в осях моста: s0…s1, t0…t1; низ и верх — числа или функции от s (для наклонного настила)."""
    zb0, zb1 = (zb(s0), zb(s1)) if callable(zb) else (zb, zb)
    zt0, zt1 = (zt(s0), zt(s1)) if callable(zt) else (zt, zt)
    c = [fr.p(s0, t0, zb0), fr.p(s1, t0, zb1), fr.p(s1, t1, zb1), fr.p(s0, t1, zb0),
         fr.p(s0, t0, zt0), fr.p(s1, t0, zt1), fr.p(s1, t1, zt1), fr.p(s0, t1, zt0)]
    mid = tuple(sum(q[i] for q in c) / 8 for i in range(3))
    for f in ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        pts = [c[i] for i in f]
        fc = tuple(sum(q[i] for q in pts) / 4 for i in range(3))
        mesh.quad(mat, pts, tuple(fc[i] - mid[i] for i in range(3)))


def pier(mesh, fr, b, s, z_top, z_bed):
    """Опора-стенка с заострёнными торцами (ледорезы), от дна до низа балок, ригель сверху."""
    h, w = b["pier_t"] / 2, (b["width"] - 2 * b["pier_inset"]) / 2
    ring = [(-h, -w + h), (-h, w - h), (0.0, w), (h, w - h), (h, -w + h), (0.0, -w)]
    mid = fr.p(s, 0.0, (z_bed + z_top) / 2)
    for (ds0, dt0), (ds1, dt1) in zip(ring, ring[1:] + ring[:1]):
        pts = [fr.p(s + ds0, dt0, z_bed), fr.p(s + ds1, dt1, z_bed), fr.p(s + ds1, dt1, z_top), fr.p(s + ds0, dt0, z_top)]
        fc = tuple(sum(q[i] for q in pts) / 4 for i in range(3))
        mesh.quad("concrete", pts, tuple(fc[i] - mid[i] for i in range(3)))
    box(mesh, fr, "concrete", s - h - 0.3, s + h + 0.3, -w - 0.3, w + 0.3, z_top - min(0.8, b["girder"]), z_top)


def build_screen(fr, b):
    """Мост-экран (S-49, S-50): настил на двутаврах, по бокам сплошная лента вертикальных ламелей, закрывающая
    балки; устои из светлых блоков, на дальнем конце — Т-площадка с тем же экраном."""
    mesh = wm.Mesh()
    half = b["width"] / 2
    lo, hi = b["screen"]
    lw, step = b["lamella"]
    box(mesh, fr, "walk", 0.0, fr.len, -half, half, lambda s: fr.deck(s) - 0.25, fr.deck)
    for k in range(b["girders"]):
        t = (k - (b["girders"] - 1) / 2) * b["girder_step"]
        box(mesh, fr, "metal", 0.0, fr.len, t - 0.2, t + 0.2, lambda s: fr.deck(s) - 0.25 - b["girder"],
            lambda s: fr.deck(s) - 0.25)

    def lamellas(s0, s1, t, jitter_seed):
        n = int((s1 - s0) // step)
        for k in range(n + 1):
            s = s0 + k * (s1 - s0) / max(n, 1)
            top = hi + b["lamella_jitter"] * math.sin(k * 1.7 + jitter_seed)  # верхи чуть разной высоты (фото)
            box(mesh, fr, "screen", s - lw / 2, s + lw / 2, t - 0.015, t + 0.015,
                lambda x, s=s: fr.deck(s) + lo, lambda x, s=s, top=top: fr.deck(s) + top)

    for side in (-1, 1):
        t = side * (half + 0.05)
        lamellas(0.0, fr.len, t, side)
        rail = lambda s: fr.deck(s) + 0.9  # noqa: E731  поручень из нержавейки изнутри экрана
        box(mesh, fr, "metal", 0.0, fr.len, t - side * 0.12 - 0.03, t - side * 0.12 + 0.03,
            lambda s: rail(s) - 0.05, rail)
    for s in (0.0, fr.len):  # устои: оголовок 6,46 × 1,75 (S-49), облицовка светлыми блоками
        box(mesh, fr, "concrete", s - 0.9, s + 0.9, -3.3, 3.3, fr.deck(s) - 6.0, fr.deck(s) - 0.25)
    pl, pw = b["platform"]
    z = fr.deck(fr.len)
    box(mesh, fr, "walk", fr.len, fr.len + pl, -pw / 2, pw / 2, z - 0.25, z)
    box(mesh, fr, "concrete", fr.len, fr.len + pl, -pw / 2, pw / 2, z - 6.0, z - 0.25)
    for t0, t1, s_at in ((-pw / 2, -half, fr.len), (half, pw / 2, fr.len)):  # экран по краям площадки
        for k in range(int(abs(t1 - t0) // step) + 1):
            t = min(t0, t1) + k * step
            box(mesh, fr, "screen", s_at - 0.015, s_at + 0.015, t - lw / 2, t + lw / 2, z + lo + 1.2, z + hi)
    for side in (-1, 1):
        lamellas(fr.len, fr.len + pl, side * pw / 2, 3 + side)
    k = 0
    while k * step <= pw:
        t = -pw / 2 + k * step
        box(mesh, fr, "screen", fr.len + pl - 0.015, fr.len + pl + 0.015, t - lw / 2, t + lw / 2, z + lo + 1.2, z + hi)
        k += 1
    return mesh


def girder_depth(b, s):
    """Высота балки в точке s: girder в центральных пролётах girder_main, girder_side — в боковых (переход 20 м)."""
    if "girder_main" not in b:
        return b["girder"]
    s0, s1 = b["girder_main"]
    d = max(s0 - s, s - s1, 0.0)
    return b["girder"] + (b["girder_side"] - b["girder"]) * min(d / 20.0, 1.0)


def girder(mesh, fr, b, gw, taper):
    """Балка-коробка с наклонными боковыми гранями (низ уже верха на taper с каждой стороны), высота — girder_depth."""
    n = max(2, int(fr.len // 5))
    zt = lambda s: fr.deck(s) - DECK_T_M  # noqa: E731
    zb = lambda s: zt(s) - girder_depth(b, s)  # noqa: E731
    for k in range(n):
        s0, s1 = k * fr.len / n, (k + 1) * fr.len / n
        for side in (-1, 1):
            pts = [fr.p(s0, side * gw, zt(s0)), fr.p(s1, side * gw, zt(s1)),
                   fr.p(s1, side * (gw - taper), zb(s1)), fr.p(s0, side * (gw - taper), zb(s0))]
            mesh.quad("concrete", pts, (fr.v[0] * side, fr.v[1] * side, -0.3))
        pts = [fr.p(s0, -(gw - taper), zb(s0)), fr.p(s1, -(gw - taper), zb(s1)),
               fr.p(s1, gw - taper, zb(s1)), fr.p(s0, gw - taper, zb(s0))]
        mesh.quad("concrete", pts, (0.0, 0.0, -1.0))


def pier_kind(mesh, fr, b, s, kind, z_top, water_z):
    """Опоры Ольгинского (S-48): бык — стенка 4,5 × 9,5 м с U-вырезом сверху; добавочная — два столба 2 × 2 м
    на ростверке у воды со стальным оголовком; береговая — пара столбов, расширяющихся кверху."""
    bed = water_z + PIER_BED_M
    if kind == "bull":
        box(mesh, fr, "concrete", s - 2.25, s + 2.25, -4.75, 4.75, bed, z_top - 2.5)
        for t0, t1 in ((-4.75, -1.5), (1.5, 4.75)):
            box(mesh, fr, "concrete", s - 2.25, s + 2.25, t0, t1, z_top - 2.5, z_top)
        box(mesh, fr, "concrete", s - 2.8, s + 2.8, -5.3, 5.3, bed, water_z + 0.5)
    elif kind == "twin":
        box(mesh, fr, "concrete", s - 1.8, s + 1.8, -6.0, 6.0, bed, water_z + 0.8)
        for t in (-4.2, 4.2):
            box(mesh, fr, "concrete", s - 1.0, s + 1.0, t - 1.0, t + 1.0, water_z + 0.8, z_top - 1.0)
            box(mesh, fr, "metal", s - 1.3, s + 1.3, t - 1.3, t + 1.3, z_top - 1.0, z_top)
    else:  # land
        for t in (-4.5, 4.5):
            box(mesh, fr, "concrete", s - 0.7, s + 0.7, t - 0.8, t + 0.8, bed, z_top - 2.0)
            box(mesh, fr, "concrete", s - 0.9, s + 0.9, t - 1.2, t + 1.2, z_top - 2.0, z_top)


def lamp_globes(mesh, fr, s, t, z0, h):
    """Фонарь Ольгинского (S-48): серый столб h, на перекладине на 4,75 м — два белых шара."""
    box(mesh, fr, "metal", s - 0.1, s + 0.1, t - 0.1, t + 0.1, z0, z0 + h)
    box(mesh, fr, "metal", s - 0.7, s + 0.7, t - 0.05, t + 0.05, z0 + 4.65, z0 + 4.75)
    for ds in (-0.65, 0.65):
        box(mesh, fr, "globe", s + ds - 0.22, s + ds + 0.22, t - 0.22, t + 0.22, z0 + 4.75, z0 + 5.2)


def build_mesh(fr, b, water_z):
    if b["kind"] == "screen":
        return build_screen(fr, b)
    mesh = wm.Mesh()
    half = b["width"] / 2
    below = lambda s: fr.deck(s) - DECK_T_M  # noqa: E731
    walk = half - b["sidewalk"]
    box(mesh, fr, "road", 0.0, fr.len, -walk, walk, below, lambda s: fr.deck(s) - 0.02)
    edge = CURB_M if b["kind"] == "road" else 0.0
    for side in (-1, 1):
        if b["sidewalk"] > 0:
            t0, t1 = sorted((side * walk, side * half))
            box(mesh, fr, "concrete", 0.0, fr.len, t0, t1, below, lambda s: fr.deck(s) + CURB_M)
    gw = half - min(GIRDER_INSET_M, half / 3)
    if "girder_main" in b:  # коробка с наклонными гранями, тротуары — на консолях
        girder(mesh, fr, b, half - b["sidewalk"] + 0.5, 1.5)
    else:
        box(mesh, fr, "concrete", 0.0, fr.len, -gw, gw, lambda s: fr.deck(s) - DECK_T_M - b["girder"], below)
    piers = b["piers"]
    if piers is None:
        n = max(1, math.ceil(fr.len / b["max_span"]))
        piers = [k * fr.len / n for k in range(1, n)]
    for p in piers:
        s, kind = p if isinstance(p, tuple) else (p, "wall")
        z_top = fr.deck(s) - DECK_T_M - girder_depth(b, s)
        if kind == "wall":
            pier(mesh, fr, b, s, z_top, water_z + PIER_BED_M)
        else:
            pier_kind(mesh, fr, b, s, kind, z_top, water_z)
    if b.get("barrier"):  # ограждение между проезжей частью и тротуаром
        for side in (-1, 1):
            t = side * walk
            box(mesh, fr, "metal", 0.0, fr.len, t - 0.06, t + 0.06, lambda s: fr.deck(s) + CURB_M,
                lambda s: fr.deck(s) + CURB_M + b["barrier"])
    for s in (0.0, fr.len):  # устои: в землю
        box(mesh, fr, "concrete", s - 1.5, s + 1.5, -half, half, fr.deck(s) - 6.0, lambda x: fr.deck(x) - DECK_T_M)
    for s_end, g, sign in ((0.0, fr.g0, -1), (fr.len, fr.g1, 1)):  # пандусы от устоя к земле
        rise = fr.deck(s_end) - g
        if rise > 0.3:
            s0, s1 = sorted((s_end, s_end + sign * b["ramp"]))
            ramp = lambda s, s_end=s_end, rise=rise, g=g: g + rise * max(0.0, 1 - abs(s - s_end) / b["ramp"])  # noqa: E731
            box(mesh, fr, "road", s0, s1, -walk, walk, lambda s: ramp(s) - 3.0, ramp)
            if b["sidewalk"] > 0:
                for side in (-1, 1):
                    t0, t1 = sorted((side * walk, side * half))
                    box(mesh, fr, "concrete", s0, s1, t0, t1, lambda s: ramp(s) - 3.0, lambda s: ramp(s) + CURB_M)
    for side in (-1, 1):  # перила: стойки, поручень, средняя тяга
        t = side * (half - 0.08)
        n = max(1, int(fr.len // RAIL_STEP_M))
        for k in range(n + 1):
            s = k * fr.len / n
            box(mesh, fr, "metal", s - 0.04, s + 0.04, t - 0.04, t + 0.04, fr.deck(s) + edge, fr.deck(s) + edge + RAIL_H_M)
        rail = lambda s: fr.deck(s) + edge + RAIL_H_M  # noqa: E731
        box(mesh, fr, "metal", 0.0, fr.len, t - 0.05, t + 0.05, lambda s: rail(s) - 0.08, rail)
        box(mesh, fr, "metal", 0.0, fr.len, t - 0.02, t + 0.02, lambda s: rail(s) - 0.6, lambda s: rail(s) - 0.56)
        if b.get("lamp_style") == "globes":
            for s in b["lamps"]:
                lamp_globes(mesh, fr, s, side * walk, fr.deck(s) + CURB_M, b["lamp_h"])
        elif b["lamps"] > 0:  # фонари у перил, консоль к оси
            k = 0
            while 6.0 + k * b["lamps"] <= fr.len - 6.0:
                s = 6.0 + k * b["lamps"]
                lt = side * (half - 0.35)
                z0, top = fr.deck(s) + edge, fr.deck(s) + edge + b["lamp_h"]
                box(mesh, fr, "metal", s - 0.09, s + 0.09, lt - 0.09, lt + 0.09, z0, top)
                arm = lt - side * min(1.4, half / 3)
                box(mesh, fr, "metal", s - 0.06, s + 0.06, min(lt, arm), max(lt, arm), top - 0.12, top)
                box(mesh, fr, "metal", s - 0.25, s + 0.25, arm - 0.18, arm + 0.18, top - 0.3, top - 0.1)
                k += 1
    return mesh


def axis(b, elements):
    """Ось моста: средняя по линиям OSM b["ways"] (концы выровнены по первой линии)."""
    lines = [geo.local_points(elements[w]["geometry"]) for w in b["ways"]]
    a0, b0 = lines[0][0], lines[0][-1]
    starts, ends = [], []
    for ln in lines:
        p, q = ln[0], ln[-1]
        if math.hypot(p[0] - a0[0], p[1] - a0[1]) > math.hypot(q[0] - a0[0], q[1] - a0[1]):
            p, q = q, p
        starts.append(p)
        ends.append(q)
    avg = lambda pts: (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))  # noqa: E731
    return avg(starts), avg(ends)


def ground(world, x, y):
    ignore = []
    for _ in range(6):
        hit = unreal.SystemLibrary.line_trace_single(
            world, unreal.Vector(x * 100, y * 100, TRACE_Z_M * 100), unreal.Vector(x * 100, y * 100, -TRACE_Z_M * 100),
            unreal.TraceTypeQuery.ECC_VISIBILITY, True, ignore, unreal.DrawDebugTrace.NONE, True)
        if hit is None:
            return None
        t = hit.to_tuple()
        if isinstance(t[9], unreal.LandscapeProxy):
            return t[5].z / 100.0
        ignore.append(t[9])
    return None


def materials(mpc):
    out = {}
    for key, name, color, rough, metal in (("concrete", "M_KromConcrete", "Concrete", 0.85, 0.0),
                                           ("road", "M_KromBridgeRoad", "Asphalt", 0.8, 0.0),
                                           ("metal", "M_KromRailing", "Railing", 0.45, 0.6),
                                           ("screen", "M_KromScreen", "Screen", 0.35, 0.8),
                                           ("walk", "M_KromWalkway", "Walkway", 0.7, 0.0),
                                           ("globe", "M_KromLampGlobe", "LampGlobe", 0.3, 0.0)):
        mat = palette_krom.fresh_material(f"{MAT_DIR}/{name}")
        mel.connect_material_property(palette_krom.param(mat, mpc, color, -400, 0), "", unreal.MaterialProperty.MP_BASE_COLOR)
        for prop, v, y in ((unreal.MaterialProperty.MP_ROUGHNESS, rough, 200), (unreal.MaterialProperty.MP_METALLIC, metal, 300)):
            mel.connect_material_property(palette_krom.expr(mat, unreal.MaterialExpressionConstant, -400, y, r=v), "", prop)
        mat.set_editor_property("used_with_nanite", True)
        mel.recompile_material(mat)
        assets.save_loaded_asset(mat)
        out[key] = mat
    return out


def write_asset(mesh, path, origin, mats):
    dm = unreal.DynamicMesh()
    ox, oy = origin
    for mid, key in enumerate(MATS):
        if key not in mesh.parts:
            continue
        verts, norms, uvs, tris = mesh.parts[key]
        buf = unreal.GeometryScriptSimpleMeshBuffers()
        buf.set_editor_property("vertices", [unreal.Vector((x - ox) * 100, (y - oy) * 100, z * 100) for x, y, z in verts])
        buf.set_editor_property("normals", [unreal.Vector(*n) for n in norms])
        buf.set_editor_property("uv0", [unreal.Vector2D(u, v) for u, v in uvs])
        buf.set_editor_property("triangles", [unreal.IntVector(*t) for t in tris])
        GS.append_buffers_to_mesh(dm, buf, material_id=mid)
    if not assets.does_asset_exist(path):
        opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
        opts.set_editor_property("enable_recompute_normals", False)
        unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, path, opts)
    sm = unreal.load_asset(path)
    opts = unreal.GeometryScriptCopyMeshToAssetOptions()
    for k, v in (("enable_recompute_normals", False), ("replace_materials", True),
                 ("new_materials", [mats[k] for k in MATS]), ("new_material_slot_names", [unreal.Name(k) for k in MATS])):
        opts.set_editor_property(k, v)
    unreal.GeometryScript_AssetUtils.copy_mesh_to_static_mesh(dm, sm, opts, unreal.GeometryScriptMeshWriteLOD())
    meshes.remove_collisions(sm)
    sm.get_editor_property("body_setup").set_editor_property(
        "collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    ns = sm.get_editor_property("nanite_settings")
    ns.set_editor_property("enabled", True)
    sm.set_editor_property("nanite_settings", ns)
    assets.save_loaded_asset(sm)
    return sm


def main():
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split(".")[0] != LEVEL:
        levels.load_level(LEVEL)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    for a in actors.get_all_level_actors():
        if TAG in a.tags:
            actors.destroy_actor(a)
    old = f"{BRIDGE_DIR}/SM_OlginskyBridge"  # прежнее имя ассета (до BRIDGES)
    if assets.does_asset_exist(old):
        assets.delete_asset(old)
    elements = {e["id"]: e for e in geo.load_elements(geo.latest("krom_2*.json"))}
    with open(os.path.join(geo.REPO, "refs", "dem", "heightmap_L_Krom.json"), encoding="utf-8") as f:
        water_z = json.load(f)["water_level_z_m"]
    mats = materials(palette_krom.collection())
    report = []
    for name, b in BRIDGES.items():
        a, e = b["ends"] if "ends" in b else axis(b, elements)
        za, ze = ground(world, *a), ground(world, *e)
        low = water_z + b["deck_min"]
        if "deck_z" in b:  # отметка настила из проекта
            fr = Frame(a, e, b["deck_z"], b["deck_z"], b["camber"])
        else:
            fr = Frame(a, e, max(za + b["deck_above"], low), max(ze + b["deck_above"], low), b["camber"])
        fr.g0, fr.g1 = za + b["deck_above"], ze + b["deck_above"]
        mesh = build_mesh(fr, b, water_z)
        sm = write_asset(mesh, f"{BRIDGE_DIR}/SM_Bridge_{name}", a, mats)
        actor = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(a[0] * 100, a[1] * 100, 0))
        actor.set_actor_label(b["label"])
        actor.set_folder_path(FOLDER)
        actor.set_editor_property("tags", [TAG])
        actor.set_editor_property("is_spatially_loaded", False)
        actor.static_mesh_component.set_static_mesh(sm)
        mid = fr.deck(fr.len / 2)
        report.append(f"{name}: {fr.len:.0f} м × {b['width']} м, настил {fr.z0 - water_z:.1f} / {mid - water_z:.1f} / "
                      f"{fr.z1 - water_z:.1f} м над урезом, треугольников {mesh.triangles()}")
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    for line in report:
        unreal.log(f"[bridge_krom] {line}")
    unreal.log(f"[bridge_krom] done: мостов {len(BRIDGES)}")


main()
