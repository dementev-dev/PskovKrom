"""pskovgu.py — здания ПсковГУ героями скриптом Blender по scripts/pskovgu_plan.py (D-018): главный корпус на
пл. Ленина, 2 и корпус на ул. Леона Поземского, 6.

    python scripts/bl_run.py scripts/blender/pskovgu.py                  # оба
    python scripts/bl_run.py scripts/blender/pskovgu.py -- Main          # одно (ключ: Main, Pozemskogo6)

Выгрузка — build/blender/<asset>.glb (в UE ставит scripts/heroes_krom.py после подключения плана в
krom_plan.buildings()), превью с камер фото Commons — build/pskovgu/renders/pskovgu_<ключ>_<фото>.png; лист сверки —
build/pskovgu/compare.py → build/pskovgu_refs/compare.jpg. Габариты, высоты, оси и источники — в pskovgu_plan.py.

Здания видны с 250–1000 м, поэтому деталь дешёвая (≤15 тыс. треугольников на здание): окна фасадов с фото — вырез
и стекло-плоскость, дворовые (гипотеза) — только плоскости стекла; колонны — тела вращения на 12 граней.
Материалы — слоты по ключам krom_plan.COLORS, новых нет: стены — «wall» (главный корпус) и «house» (розовые стены
на Поземского: ключа «розовый» нет — ближайший, гип.), кровли — «tin» / «roof», цоколь — «stone», двери — «dark».
Оси здания (u, v, z) — как в плане; в Blender точка (u, −v, z).
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402
import krom_plan  # noqa: E402
import pskovgu_plan as pp  # noqa: E402
from bl_krom import M  # noqa: E402

RENDER_DIR = os.path.join(bk.REPO, "build", "pskovgu", "renders")
BASE_Z = {"Main": -1.5, "Pozemskogo6": -1.8}   # низ стен: земля под контуром ниже нуля здания (heightmap: −0,45 / −1,2)
POZ_WALL = "pink"    # розовые стены Поземского, 6: ключа «розовый» в krom_plan.COLORS нет — ближайший, гип.


# ---------- общие детали ----------

class Panels:
    """Плоские грани в 1–2 см от стены (стёкла дворовых окон, переплёты, обрамления): по мешу на материал,
    нормаль — наружу по фасаду. Многоугольник на фасаде (s, z) → одна грань."""

    def __init__(self):
        self.faces = {}

    def add(self, fr, poly, d, key):
        pts = [fr.p(s, z, d) for s, z in poly]
        self.faces.setdefault(key, []).append((pts, fr.n))

    def objects(self):
        out = []
        for key, faces in self.faces.items():
            verts, idx = [], []
            for pts, n in faces:
                b = [Vector((u, -v, z)) for u, v, z in pts]
                nb = (b[1] - b[0]).cross(b[2] - b[0])
                if nb.dot(Vector((n[0], -n[1], 0.0))) < 0:
                    b.reverse()
                idx.append(list(range(len(verts), len(verts) + len(b))))
                verts += b
            me = bpy.data.meshes.new(f"panels_{key}")
            me.from_pydata([tuple(v) for v in verts], [], idx)
            me.update()
            obj = bpy.data.objects.new(f"panels_{key}", me)
            bpy.context.scene.collection.objects.link(obj)
            out.append(bk.assign(obj, M[key]))
        return out


class Openings:
    """Проёмы одного тела: вырезы копятся и вычитаются одной булевой операцией; стекло — плоскость у дна выреза;
    переплёты, подоконники, сандрики — плоскости и простые тела."""

    def __init__(self, panels):
        self.cutters, self.parts, self.pan = [], [], panels

    def window(self, fr, s, w, z0, z1, depth=0.25, sill=True, cross=True, hood=None, key="wall", poly=None):
        """Окно: середина s, ширина w, низ z0, верх z1; poly — свой контур (арка). hood: None | "shelf" | "tri"."""
        poly = poly or bk.rect(s - w / 2, s + w / 2, z0, z1)
        self.cutters.append(bk.extrude("cut", fr, poly, -depth, 0.6, M[key]))
        self.pan.add(fr, poly, -depth + 0.01, "glass")
        if cross:                                   # стойка и фрамуга
            zt = z0 + (z1 - z0) * 0.68
            self.pan.add(fr, bk.rect(s - 0.04, s + 0.04, z0, min(z1, zt + 2)), -depth + 0.03, "wall")
            self.pan.add(fr, bk.rect(s - w / 2, s + w / 2, zt - 0.04, zt + 0.04), -depth + 0.03, "wall")
        if sill:
            self.parts.append(bk.extrude("sill", fr, bk.rect(s - w / 2 - 0.1, s + w / 2 + 0.1, z0 - 0.12, z0), -0.02,
                                         0.12, M[key]))
        self.hood(fr, s, w, z1, hood, key)

    def hood(self, fr, s, w, z, kind, key="wall"):
        if kind in ("shelf", "tri"):
            self.parts.append(bk.extrude("sandrik", fr, bk.rect(s - w / 2 - 0.2, s + w / 2 + 0.2, z + 0.12, z + 0.26),
                                         -0.02, 0.16, M[key]))
        if kind == "tri":
            self.parts.append(bk.extrude("fronton", fr, [(s - w / 2 - 0.15, z + 0.26), (s + w / 2 + 0.15, z + 0.26),
                                                         (s, z + 0.26 + 0.28 * (w + 0.3))], -0.02, 0.12, M[key]))

    def door(self, fr, s, w, z0, z1, depth=0.4, key="dark", poly=None):
        poly = poly or bk.rect(s - w / 2, s + w / 2, z0, z1)
        self.cutters.append(bk.extrude("cut", fr, poly, -depth, 0.6, M["wall"]))
        self.pan.add(fr, poly, -depth + 0.01, key)

    def apply(self, body):
        return [bk.cut(body, self.cutters)] + self.parts


def glass(pan, fr, s, w, z0, z1, frame=0.0, key="wall"):
    """Дворовое окно (гипотеза): стекло-плоскость в 1 см от стены, при frame — обрамление-плоскость вокруг."""
    if frame:
        f = frame
        pan.add(fr, bk.rect(s - w / 2 - f, s + w / 2 + f, z0 - f, z1 + f), 0.008, key)
    pan.add(fr, bk.rect(s - w / 2, s + w / 2, z0, z1), 0.015, "glass")


def face(a, b, inside):
    """Фасад по отрезку a–b: s идёт слева направо, если смотреть снаружи."""
    fr = bk.Frame.between(a, b, inside)
    right = (fr.n[1], -fr.n[0])
    if (b[0] - a[0]) * right[0] + (b[1] - a[1]) * right[1] < 0:
        fr = bk.Frame.between(b, a, inside)
    return fr


def ring_band(poly, z0, z1, proud, key="wall"):
    return bk.prism("band", pp.offset(list(poly), proud), z0, z1, M[key])


def quad_hip(name, P, z, rise, mat, over=0.5, thick=0.15):
    """Вальмовая кровля над выпуклым четырёхугольником P [(u, v)] с карнизом на z: конёк по оси между серединами двух
    коротких сторон, вальмы под тем же уклоном, что скаты; свес over — по плоскостям скатов (как в krom_yard)."""
    P = [tuple(p) for p in P]
    L = [math.dist(P[k], P[(k + 1) % 4]) for k in range(4)]
    i = 0 if L[0] + L[2] <= L[1] + L[3] else 1
    a0, a1, c0, c1 = (P[(i + k) % 4] for k in range(4))
    ma, mc = ((a0[0] + a1[0]) / 2, (a0[1] + a1[1]) / 2), ((c0[0] + c1[0]) / 2, (c0[1] + c1[1]) / 2)
    D = math.dist(ma, mc)
    e = ((mc[0] - ma[0]) / D, (mc[1] - ma[1]) / D)
    da, dc = L[i] / 2, L[(i + 2) % 4] / 2
    ra = (ma[0] + e[0] * da, ma[1] + e[1] * da, z + rise)
    rc = (mc[0] - e[0] * dc, mc[1] - e[1] * dc, z + rise)
    slope = rise / ((L[i] + L[(i + 2) % 4]) / 4)
    Q = pp.offset([a0, a1, c0, c1], over)
    ze = z - over * slope
    top = [(q[0], q[1], ze) for q in Q]
    bot = [(q[0], q[1], ze - thick) for q in Q]
    faces = [[0, 1, 4], [1, 2, 5, 4], [2, 3, 5], [3, 0, 4, 5], [6, 7, 8, 9]] + \
            [[k, (k + 1) % 4, 6 + (k + 1) % 4, 6 + k] for k in range(4)]
    return bk.mesh(name, top + [ra, rc] + bot, faces, mat)


def gable(name, fr, s0, s1, ze, zr, d0, d1, mat, over=0.35, thick=0.16):
    """Двускатная кровля: сечение в плоскости фасада fr, протянутое по нормали от d0 до d1."""
    sm, hw = (s0 + s1) / 2, (s1 - s0) / 2
    slope = (zr - ze) / hw
    zo = ze - over * slope
    th = thick * math.hypot(1, slope)
    prof = [(s0 - over, zo), (sm, zr), (s1 + over, zo), (s1 + over, zo - thick), (sm, zr - th), (s0 - over, zo - thick)]
    return bk.extrude(name, fr, prof, d0, d1, mat)


def chimney(u, v, z0, z1, a=0.7, b=0.5, key="wall"):
    return [bk.box("chimney", u - a / 2, u + a / 2, v - b / 2, v + b / 2, z0, z1, M[key])]


# ---------- главный корпус ----------

def main_building(c):
    """Корпус по контуру плана одним телом; главный фасад, торцы крыльев и портик — по фото c01, c06, c11 (S-130);
    дворовые фасады и пристройка — гипотеза: окна-плоскости с тем же шагом и этажами."""
    z = BASE_Z[c.key]
    pan = Panels()
    op = Openings(pan)
    parts = []
    body_poly = list(c.outline[3:-1])                     # без подиума портика: фасад замыкается по v = 0
    body = bk.prism("walls", body_poly, z, c.z_eave - 0.55, M["wall"])
    inside = (0.0, 5.0)
    west = bk.Frame((0.0, 0.0), (-1.0, 0.0), (0.0, -1.0))  # главный фасад: s = −u (слева направо — с севера на юг)
    (l0, l1), fl = c.low, c.floors
    W = c.win_w
    ze, zb = c.z_eave, c.z_belt
    # крылья главного фасада: 8 осей с пилястрами от портика до торцевой части
    for sg in (-1, 1):
        for k in range(c.bays):
            u = sg * (c.portico[0] + c.bay / 2 + 0.03 + c.bay * k)
            op.window(west, -u, W, l0, l1)
            for z0, z1 in fl:
                op.window(west, -u, W, z0, z1)
        for k in range(c.bays + 1):
            u = sg * (c.portico[0] + 0.03 + c.bay * k)
            parts.append(bk.extrude("pilaster", west, bk.rect(-u - 0.3, -u + 0.3, zb[1], c.z_arch), -0.02, 0.1,
                                    M["wall"]))
        # торцевая часть: «тройное» окно (середина и узкие боковые), фронтончик над окном 2-го этажа
        u = sg * c.triple
        triple(op, west, -u, fl, W)
        op.window(west, -u, W, l0, l1)
    # торцы крыльев (u = ±half), по южному на c11: «тройное» окно у угла, дальше 9 осей с пилястрами; северный —
    # так же (гип.)
    for sg in (-1, 1):
        fr = face((sg * c.half, 0.0), (sg * c.half, 36.46), inside)
        sv = (lambda v: v) if fr.t[1] > 0 else (lambda v: 36.46 - v)       # s по фасаду из v
        triple(op, fr, sv(c.side_triple), fl, W)
        op.window(fr, sv(c.side_triple), W, l0, l1)
        for k in range(c.side_bays):
            v = c.side_first + c.bay * k
            op.window(fr, sv(v), W, l0, l1, sill=False, cross=False)
            for z0, z1 in fl:
                op.window(fr, sv(v), W, z0, z1, sill=False, cross=False)
            vp = v - c.bay / 2
            parts.append(bk.extrude("pilaster", fr, bk.rect(sv(vp) - 0.3, sv(vp) + 0.3, zb[1], c.z_arch), -0.02, 0.1,
                                    M["wall"]))
    # лоджия за колоннами: 5 осей, фронтончики над окнами 2-го этажа через ось (c01)
    for u in (-2 * 3.6, -3.6, 0.0, 3.6, 2 * 3.6):
        for j, (z0, z1) in enumerate(fl):
            op.window(west, -u, W, z0, z1, hood="tri" if j == 0 and abs(u) != 3.6 else None)
    # дворовые фасады — гипотеза: плоскости стекла с шагом осей, от углов по 1,5 м
    skip = {((c.half, 0.0), (c.half, 36.46)), ((-c.half, 36.48), (-c.half, 0.0))}
    P = body_poly
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        if abs(a[1]) < 1e-6 and abs(b[1]) < 1e-6:          # главный фасад
            continue
        if (a[0] == b[0] and abs(abs(a[0]) - c.half) < 1e-6 and min(a[1], b[1]) < 1e-6):   # торцы крыльев
            continue
        L = math.dist(a, b)
        n = int((L - 3.0) // c.bay) + 1 if L >= 3.0 else 0
        if n <= 0:
            continue
        fr = face(a, b, centroid_side(P, a, b))
        s0 = (L - (n - 1) * c.bay) / 2
        for k in range(n):
            s = s0 + k * c.bay
            glass(pan, fr, s, W - 0.1, l0, l1)
            for z0, z1 in fl:
                glass(pan, fr, s, W - 0.1, z0, z1)
    parts += op.apply(body)
    # пояса и карниз по контуру тела
    parts.append(ring_band(body_poly, z, c.z_plinth, 0.06, "stone"))
    parts.append(ring_band(body_poly, zb[0], zb[1], 0.14))
    parts.append(ring_band(body_poly, c.z_arch, c.z_arch + 0.18, 0.05))
    parts.append(ring_band(body_poly, c.z_frieze - 0.55, c.z_frieze, 0.03))
    parts.append(ring_band(body_poly, c.z_frieze, ze - 0.3, 0.25))
    parts.append(ring_band(body_poly, ze - 0.3, ze, 0.6))
    parts += portico(c, pan)
    parts += main_roofs(c)
    return parts + pan.objects()


def centroid_side(P, a, b):
    """Точка внутри тела у середины стороны a–b (для нормали фасада наружу)."""
    m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    L = math.dist(a, b)
    n = (-(b[1] - a[1]) / L, (b[0] - a[0]) / L)
    for sg in (1, -1):
        q = (m[0] + sg * n[0] * 0.3, m[1] + sg * n[1] * 0.3)
        if pp.point_in(q, list(P)):
            return q
    return (0.0, 5.0)


def triple(op, fr, s, floors, W):
    """«Тройное» окно торцевой части: середина W, боковые по 0,6 м; фронтончик над окном 2-го этажа (c01, c11)."""
    for j, (z0, z1) in enumerate(floors):
        op.window(fr, s, W, z0, z1, hood="tri" if j == 0 else None)
        for sg in (-1, 1):
            op.window(fr, s + sg * (W / 2 + 0.55), 0.6, z0, z1, sill=False, cross=False)


def portico(c, pan):
    """Подиум с пятью дверями, 8 колонн большого ордера (крайние парные), антаблемент, фронтон с тимпаном."""
    R, D = c.portico
    z = BASE_Z[c.key]
    zb = c.z_belt[1]
    parts = []
    pod = bk.box("podium", -R, R, -D, 0.2, z, zb, M["wall"])
    front = bk.Frame((0.0, -D), (-1.0, 0.0), (0.0, -1.0))   # s = −u
    op = Openings(pan)
    for u in c.doors:
        for sg in ((1, -1) if u else (1,)):
            op.door(front, -sg * u, 2.0, 0.25, 3.6)
    parts += op.apply(pod)
    parts.append(bk.box("podium_cornice", -R - 0.12, R + 0.12, -D - 0.12, 0.2, zb - 0.35, zb, M["wall"]))
    parts.append(bk.box("steps", -R + 1.0, R - 1.0, -D - 1.6, -D, -0.6, 0.25, M["stone"]))
    parts.append(bk.box("steps", -R + 1.0, R - 1.0, -D - 0.8, -D, -0.6, 0.5, M["stone"]))
    r = c.col_d / 2
    for a in c.columns:
        for sg in (-1, 1):
            u = sg * a
            parts.append(bk.box("col_base", u - r - 0.1, u + r + 0.1, c.col_v - r - 0.1, c.col_v + r + 0.1, zb,
                                zb + 0.35, M["wall"]))
            parts.append(bk.lathe("column", (u, c.col_v), [(r, zb + 0.35), (r, zb + 3.5), (r * 0.86, c.z_arch - 0.55),
                                                           (r * 1.12, c.z_arch - 0.2), (r * 1.12, c.z_arch - 0.1)],
                                  M["wall"], seg=12))
            parts.append(bk.box("col_cap", u - r - 0.12, u + r + 0.12, c.col_v - r - 0.12, c.col_v + r + 0.12,
                                c.z_arch - 0.12, c.z_arch, M["wall"]))
    Re = R + 0.1
    parts.append(bk.box("architrave", -Re, Re, -D, 0.3, c.z_arch, c.z_frieze, M["wall"]))
    parts.append(bk.box("cornice", -Re - 0.3, Re + 0.3, -D - 0.45, 0.3, c.z_frieze, c.z_eave, M["wall"]))
    zp = c.z_pediment
    parts.append(bk.extrude("tympanum", front, [(-Re, c.z_eave - 0.02), (Re, c.z_eave - 0.02), (0.0, zp - 0.35)],
                            -3.0, -0.25, M["wall"]))
    parts.append(gable("roof_pediment", front, -Re - 0.2, Re + 0.2, c.z_eave, zp, -(D + 5.2), 0.55, M["tin"],
                       over=0.1, thick=0.3))
    back = bk.Frame((0.0, 5.2), (-1.0, 0.0), (0.0, 1.0))
    parts.append(bk.extrude("tympanum_back", back, [(-Re, c.z_eave), (Re, c.z_eave), (0.0, zp - 0.3)], -0.5, 0.0,
                            M["wall"]))
    return parts


def main_roofs(c):
    """Вальмы: главный корпус между крыльями (конёк вдоль фасада), крылья и среднее крыло (коньки на восток),
    пристройка; ендовы — по линии карниза (упрощение). Уклон — гип. (pitch)."""
    t = math.tan(math.radians(c.pitch))
    ze = c.z_eave
    d = c.depth
    (s0, s1, sv), (n0, n1, nv), (c0, c1, cv) = c.wing_s, c.wing_n, c.wing_c
    parts = []
    front = [(s1, 0.0), (n0, 0.0), (n0, d), (s1, d)]
    parts.append(quad_hip("roof_front", front, ze, d / 2 * t, M["tin"]))
    for q in ([(s0, 0.0), (s1, 0.0), (s1, sv), (s0, sv)], [(n0, 0.0), (n1, 0.0), (n1, nv), (n0, nv)]):
        parts.append(quad_hip("roof_wing", q, ze, (q[1][0] - q[0][0]) / 2 * t, M["tin"]))
    parts.append(quad_hip("roof_mid", [(c0, d), (c1, d), (c1, cv), (c0, cv)], ze, (c1 - c0) / 2 * t, M["tin"]))
    l0, l1, lv = c.link_c
    parts.append(quad_hip("roof_link", [(l0, d), (l1, d), (l1, lv), (l0, lv)], ze, (lv - d) / 2 * t, M["tin"]))
    a0, a1, av0, av1 = c.annex
    parts.append(quad_hip("roof_annex", [(a0, av0), (a1, av0), (a1, av1), (a0, av1)], ze, (a1 - a0) / 2 * t, M["tin"]))
    st0, st1, stv = c.stair_c
    parts.append(bk.box("stair_top", st0 - 0.2, st1 + 0.2, cv - 0.5, stv + 0.2, ze - 0.3, ze, M["tin"]))
    zr = ze + d / 2 * t
    for u in (-26.0, 26.0):                               # вытяжки на коньке (c01), гип.
        parts += chimney(u, d / 2 + 0.6, zr - 1.0, zr + 0.6, a=0.5, b=0.5)
    for u in (-44.0, 44.0):
        parts += chimney(u, 12.0, ze + 5.0, ze + 8.5 * t + 0.8)
    return parts


# ---------- ул. Леона Поземского, 6 ----------

def wing_frame(c, sg):
    """Фасад крыла: sg = +1 — северное (к u > 0), −1 — южное; s — от излома по крылу, d — наружу к улице."""
    a = -sg * c.bend
    return bk.Frame((0.0, 0.0), pp.rot((sg * 1.0, 0.0), a), pp.rot((0.0, 1.0), a))


def pozemskogo6(c):
    """Два крыла под углом по изгибу улицы, ризалит у излома: средняя часть под щипцом (вход-портик, три арочных
    окна) и плечи с аттиком; в крыльях по 7 осей: окна 1-го этажа в «архивольтах», 2-го — в наличниках; рустованные
    пилястры по краям; торцы — два ряда окон (p02); дворовый фасад — гипотеза (окна-плоскости). Нуль — земля у оси."""
    z = BASE_Z[c.key]
    d = c.depth
    pan = Panels()
    parts = []
    k = 1.0 / math.cos(math.radians(c.bend))
    R, Rd = c.risalit
    g = c.gable
    ze, zr = c.z_eave, c.z_risalit
    (l0, l1), (u0, u1) = c.low, c.up
    W = c.win_w
    for sg, L in ((1, c.wing_n), (-1, c.wing_s)):
        fr = wing_frame(c, sg)
        P = [(0.0, 0.0), fr.p(L, 0, 0.0)[:2], fr.p(L, 0, -d)[:2], (0.0, -d * k)]
        body = bk.prism("walls", P, z, ze - 0.4, M[POZ_WALL])
        op = Openings(pan)
        s_first = R + 0.3 + c.bay / 2
        for j in range(c.bays):                             # оси крыла
            s = s_first + c.bay * j
            op.window(fr, s, W, l0, l1, depth=0.2, sill=False)
            pan.add(fr, bk.arch_frame(s, W + 0.3, l1 + 0.05, l1 + 0.05, 0.16, n=6), 0.02, "wall")   # «архивольт»
            pan.add(fr, bk.rect(s - W / 2 - 0.25, s + W / 2 + 0.25, l0 - 0.55, l0 - 0.05), 0.02, "wall")  # подоконная
            op.window(fr, s, W, u0, u1, depth=0.2, sill=True)
            pan.add(fr, frame_poly(s, W, u0, u1, 0.13), 0.012, "wall")                                # наличник
            pan.add(fr, bk.rect(s - W / 2, s + W / 2, 0.15, 0.6), 0.07, "glass")                     # полуподвал
        s_end = s_first + c.bay * (c.bays - 1) + c.bay / 2 + 0.45
        parts.append(bk.extrude("rustic", fr, bk.rect(s_end - 0.4, s_end + 0.4, c.z_plinth, ze - 0.4), -0.02, 0.12,
                                M["wall"]))
        endf = face(fr.p(L, 0, 0.0)[:2], fr.p(L, 0, -d)[:2], (0.0, -d / 2))       # торец: окно у угла и пара (p02)
        for s in (d * 0.25, d * 0.62, d * 0.75):
            w = W * 0.8 if s > d * 0.5 else W
            op.window(endf, s, w, l0, l1, depth=0.2, sill=False)
            op.window(endf, s, w, u0, u1, depth=0.2, sill=True)
        backf = face((0.0, -d * k), fr.p(L, 0, -d)[:2], (0.0, -d / 2))
        for j in range(int((L - 3.0) // c.bay)):
            s = 2.0 + c.bay * j + c.bay / 2
            glass(pan, backf, s, W - 0.05, l0, l1)
            glass(pan, backf, s, W - 0.05, u0, u1)
        parts += op.apply(body)
        # плечо ризалита (s от g до R): вынос Rd, над карнизом крыльев — аттик глубиной 1,2 м до карниза ризалита
        Pr = [fr.p(g, 0, Rd)[:2], fr.p(R, 0, Rd)[:2], fr.p(R, 0, -d + 0.5)[:2], fr.p(g, 0, -d + 0.5)[:2]]
        Pa = [fr.p(g, 0, Rd)[:2], fr.p(R, 0, Rd)[:2], fr.p(R, 0, Rd - 1.2)[:2], fr.p(g, 0, Rd - 1.2)[:2]]
        rb = bk.prism("risalit", Pr, z, ze - 0.4, M[POZ_WALL])
        parts.append(bk.prism("attic", Pa, ze - 0.45, zr - 0.35, M[POZ_WALL]))
        frr = bk.Frame(fr.p(0, 0, Rd)[:2], fr.t, fr.n)
        orr = Openings(pan)
        s_fl = g + 1.7                                        # окно плеча, на 2-м этаже — с сандриком (p01)
        orr.window(frr, s_fl, W + 0.25, u0, u1, depth=0.25, hood="shelf")
        pan.add(frr, frame_poly(s_fl, W + 0.25, u0, u1, 0.14), 0.012, "wall")
        orr.window(frr, s_fl, W + 0.25, l0, l1, depth=0.25, sill=False)
        pan.add(frr, frame_poly(s_fl, W + 0.25, l0, l1, 0.14), 0.012, "wall")
        parts += orr.apply(rb)
        parts.append(bk.extrude("rustic", frr, bk.rect(R - 0.75, R - 0.05, c.z_plinth, zr - 0.35), -0.05, 0.12,
                                M["wall"]))
        parts.append(ring_band(P, z, c.z_plinth, 0.05, "stone"))
        parts.append(ring_band(Pr, z, c.z_plinth, 0.05, "stone"))
        parts.append(ring_band(P, c.z_belt[0], c.z_belt[1], 0.08))
        parts.append(ring_band(Pr, c.z_belt[0], c.z_belt[1], 0.08))
        parts.append(ring_band(P, ze - 0.4, ze, 0.35))
        parts.append(ring_band(Pa, zr - 0.35, zr, 0.35))
        parts.append(wing_roof(fr, L, d, ze, c.pitch, k))
    parts += poz_centre(c, pan, k)
    return parts + pan.objects()


def frame_poly(s, w, z0, z1, f):
    """Наличник-рамка вокруг окна (∩ с перемычкой) — одна грань."""
    a, b = s - w / 2, s + w / 2
    return [(a - f, z0 - 0.06), (a, z0 - 0.06), (a, z1), (b, z1), (b, z0 - 0.06), (b + f, z0 - 0.06), (b + f, z1 + f),
            (a - f, z1 + f)]


def wing_roof(fr, L, d, ze, pitch, k, over=0.45):
    """Кровля крыла: скаты вдоль крыла, вальма на конце, у излома — срез по оси u (стык с другим крылом)."""
    t = math.tan(math.radians(pitch))
    half = d / 2
    zo = ze - over * t
    F0, B0, R0 = (0.0, over * k), (0.0, (-d - over) * k), (0.0, -half * k)
    F1, B1, R1 = fr.p(L + over, 0, over)[:2], fr.p(L + over, 0, -d - over)[:2], fr.p(L - half, 0, -half)[:2]
    zr = ze + half * t
    verts = [(*F0, zo), (*F1, zo), (*B1, zo), (*B0, zo), (*R0, zr), (*R1, zr)]
    return bk.mesh("roof_wing", verts, [[0, 1, 5, 4], [1, 2, 5], [2, 3, 4, 5], [3, 0, 4], [0, 3, 2, 1]], M["roof"])


def poz_centre(c, pan, k):
    """Середина ризалита (u ±g): вход-портик — парные рустованные пилястры, между ними окна, в центре дверь,
    антаблемент-балкон на всю ширину; над ним три арочных окна; щипец с полукруглым окном, карниз под ним
    разорван посередине (S-133; размеры — p01)."""
    parts = []
    R, Rd = c.risalit
    g, zr = c.gable, c.z_risalit
    front = Rd * k + 0.05
    fr = bk.Frame((0.0, front), (1.0, 0.0), (0.0, 1.0))
    body = bk.box("centre", -g, g, -c.depth * 0.5, front, BASE_Z[c.key], zr, M[POZ_WALL])
    op = Openings(pan)
    ze_ent = c.z_belt[1] - 0.1                                       # антаблемент входа (p01)
    top = ze_ent + 3.4
    for s in (-2.7, 0.0, 2.7):                                        # три арочных окна над ним (p01)
        op.window(fr, s, 1.35, ze_ent + 0.65, top, depth=0.3, poly=bk.arch(s, 1.35, ze_ent + 0.65, top - 0.675, n=8))
        pan.add(fr, bk.arch_frame(s, 1.35, ze_ent + 0.65, top - 0.675, 0.14, n=8), 0.02, "wall")
    op.door(fr, 0.0, 1.7, 0.3, 3.4, depth=0.25)
    for s in (-1.75, 1.75):
        op.window(fr, s, 0.9, 2.0, 3.8, depth=0.25, sill=False)
    parts += op.apply(body)
    for a in (2.9, 4.25):                                             # парные рустованные пилястры
        for sg in (-1, 1):
            parts.append(bk.extrude("rustic", fr, bk.rect(sg * a - 0.24, sg * a + 0.24, 0.0, ze_ent), -0.02, 0.28,
                                    M["wall"]))
    parts.append(bk.extrude("entablature", fr, bk.rect(-g - 0.5, g + 0.5, ze_ent, ze_ent + 0.6), -0.02, 0.45,
                            M["wall"]))
    parts.append(bk.extrude("steps", fr, bk.rect(-1.4, 1.4, -0.8, 0.3), 0.0, 1.0, M["stone"]))
    zg0 = zr - 0.05
    parts.append(bk.extrude("gable", fr, [(-g, zg0), (g, zg0), (0.0, c.z_gable - 0.3)], -1.2, 0.0, M[POZ_WALL]))
    parts.append(gable("roof_gable", fr, -g - 0.1, g + 0.1, zg0, c.z_gable, -(c.depth * 0.55), 0.35, M["roof"],
                       over=0.25))
    zl = zg0 + 0.45
    parts.append(bk.extrude("lunette", fr, bk.arch(0.0, 1.1, zl, zl, n=8), -0.02, 0.03, M["glass"]))
    parts.append(bk.extrude("lunette_frame", fr, bk.arch_frame(0.0, 1.1, zl, zl, 0.15, n=8), -0.02, 0.06, M["wall"]))
    for sg in (-1, 1):                                                # карниз под щипцом разорван посередине
        a, b = sorted((sg * 1.3, sg * (g + 0.2)))
        parts.append(bk.extrude("cornice", fr, bk.rect(a, b, zg0 - 0.3, zg0 + 0.05), -0.02, 0.38, M["wall"]))
    return parts


# ---------- сборка и превью ----------

BUILD = {"Main": main_building, "Pozemskogo6": pozemskogo6}

# Превью с камер фото (build/pskovgu_refs/manifest.json; подбор — build/pskovgu/fit_*.py): глаз (u, v, z) в осях
# здания, азимут взгляда от оси u к оси v, наклон, крен (°), фокусное в пикселях кадра, главная точка (cx, cy)
# в пикселях (кадры обрезаны — точка не в центре), размер кадра — как у файла в build/pskovgu_refs.
VIEWS = {
    "Main": {   # c01 — GAlexandrova 2013 (IXUS 75, 5,8 мм = 35 мм экв.; кадр 2744 × 1692 обрезан из 3072 × 2304):
        # глаз на 1,6 м, фокусное из EXIF, главная точка подобрана (fit_c01b.py, невязка ≤4 пкс)
        "c01": dict(eye=(34.99, -120.60, 1.6), yaw=93.91, pitch=0.0, roll=0.51, f=2090.0, cx=422.3, cy=876.8,
                    size=(1920, 1184)),
        # c06 — User 699, 2011 (TZ4, 46 мм экв., кадр не обрезан): с юго-запада; глаз на 1,6, фокусное подобрано
        # (дисторсия у краёв кадра), невязка ≤15 пкс (fit_c06.py)
        "c06": dict(eye=(-64.64, -91.97, 1.6), yaw=57.9, pitch=4.24, roll=1.6, f=2125.0, cx=960.0, cy=720.0,
                    size=(1920, 1440)),
        # c11 — Lvovick, 2011 (A3000 IS, 35 мм экв.): с юго-запада, виден южный торец; невязка ≤12 пкс (fit_c11.py)
        "c11": dict(eye=(-88.03, -68.39, 1.6), yaw=48.96, pitch=11.99, roll=0.41, f=2026.0, cx=960.0, cy=720.0,
                    size=(1920, 1440)),
    },
    "Pozemskogo6": {   # отметки — средние по двум фото, камеры подобраны к итоговому плану (fit_poz6_views.py)
        # p01 — A. Savin, 2018, FAL (13 мм, кадр 6218 × 3109 из 7952 × 5304): анфас с улицы; горизонт по прохожим
        "p01": dict(eye=(-0.59, 26.17, 0.18), yaw=-89.42, pitch=0.0, roll=-0.52, f=886.7, cx=960.0, cy=650.0,
                    size=(1920, 960)),   # невязка ≤30 пкс
        # p02 — AndyVolykhov, 2023 (SX620 HS, 33 мм экв.): с северо-востока, северный торец
        "p02": dict(eye=(43.01, 8.02, 1.75), yaw=-150.61, pitch=11.73, roll=1.41, f=1765.3, cx=960.0, cy=714.0,
                    size=(1920, 1428)),  # невязка ≤35 пкс
    },
}


OVERVIEW = {   # общие виды для проверки формы: (глаз, цель) в осях здания
    "Main": {"overview": ((-60.0, -90.0, 45.0), (5.0, 20.0, 5.0)), "back": ((90.0, 120.0, 50.0), (0.0, 20.0, 5.0))},
    "Pozemskogo6": {"overview": ((-35.0, 55.0, 22.0), (0.0, -5.0, 4.0)),
                    "back": ((35.0, -60.0, 28.0), (0.0, -6.0, 4.0))},
}


def render_view(name, eye, yaw, pitch, roll, f, cx, cy, size, scale=0.5):
    """Превью Workbench с камерой фото: сдвиг объектива даёт главную точку (cx, cy), крен — поворот вокруг взгляда."""
    os.makedirs(RENDER_DIR, exist_ok=True)
    s = bpy.context.scene
    W, H = size
    cam = bpy.data.objects.new("PhotoCam", bpy.data.cameras.new("PhotoCam"))
    s.collection.objects.link(cam)
    cam.data.sensor_fit = "HORIZONTAL"
    cam.data.sensor_width = 36.0
    cam.data.lens = f / W * 36.0
    cam.data.shift_x = (W / 2 - cx) / W
    cam.data.shift_y = (cy - H / 2) / W
    cam.data.clip_end = 5000
    cam.location = (eye[0], -eye[1], eye[2])
    y, p = math.radians(yaw), math.radians(pitch)
    fwd = Vector((math.cos(p) * math.cos(y), -math.cos(p) * math.sin(y), math.sin(p)))
    q = fwd.to_track_quat("-Z", "Y")
    cam.rotation_euler = (Matrix.Rotation(-math.radians(roll), 4, fwd) @ q.to_matrix().to_4x4()).to_euler()
    s.camera = cam
    if s.world is None:
        s.world = bpy.data.worlds.new("Preview")
    s.world.color = (0.75, 0.8, 0.86)
    s.render.engine = "BLENDER_WORKBENCH"
    s.display.shading.light = "STUDIO"
    s.display.shading.color_type = "MATERIAL"
    s.display.shading.show_shadows = True
    s.display.shading.show_cavity = True
    s.render.resolution_x, s.render.resolution_y = round(W * scale), round(H * scale)
    s.render.filepath = os.path.join(RENDER_DIR, f"{name}.png")
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam)
    print(f"[pskovgu] preview {s.render.filepath}")


def build(c):
    name = c.asset
    bk.reset_scene()
    bk.use_colors(krom_plan.COLORS)
    objs = BUILD[c.key](c)
    obj = bk.join(objs, name)
    bk.box_uv(obj)
    me = obj.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    print(f"[pskovgu] {c.name}: {len(objs)} тел → {name}: {len(me.vertices)} вершин, {len(me.polygons)} граней "
          f"({tris} треугольников), слоты {[m.name for m in me.materials]}")
    bk.export_glb(obj, name)
    ground = bk.box("ground", -300, 300, -300, 300, -0.05, 0.0, bk.material("ground", (0.12, 0.16, 0.08)))
    ground.hide_select = True
    for view, cam in VIEWS[c.key].items():
        render_view(f"pskovgu_{c.key}_{view}", **cam)
    bk.PREVIEW_DIR = RENDER_DIR
    for view, (eye, tgt) in OVERVIEW[c.key].items():
        bk.render_preview(f"pskovgu_{c.key}_{view}", eye=(eye[0], -eye[1], eye[2]), target=(tgt[0], -tgt[1], tgt[2]),
                          size=(1200, 700), lens=35)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    todo = [c for c in pp.PSKOVGU if not argv or c.key in argv]
    if not todo:
        raise SystemExit(f"[pskovgu] нет здания {argv}; есть: {[c.key for c in pp.PSKOVGU]}")
    for c in todo:
        build(c)


main()
