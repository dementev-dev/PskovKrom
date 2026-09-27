"""pozemskogo.py — герои Запсковья на переднем плане облёта (D-043, партия 2) скриптом Blender по
scripts/pozemskogo_plan.py (D-018): жилые дома ул. Леона Поземского, 8 и 10, флигель Злакомановой (6А), бывшая
канатная фабрика Мейера (24).

    python scripts/bl_run.py scripts/blender/pozemskogo.py                    # все
    python scripts/bl_run.py scripts/blender/pozemskogo.py -- Pozemskogo8     # одно (ключи — pozemskogo_plan)

Выгрузка — build/blender/<asset>.glb (в UE ставит scripts/heroes_krom.py после подключения плана в
krom_plan.buildings()). Превью с камер фото — build/pozemskogo/renders/<ключ>_<фото>.png: камеры берутся из
build/pozemskogo/views.json (его пишет build/pozemskogo/views.py; нет файла — только выгрузка и общие виды);
лист сверки — build/pozemskogo/compare.py → build/pozemskogo_refs/compare.jpg.

Здания видны с облёта с 150–500 м, деталь дешёвая (≤12 тыс. треугольников на здание): окна фасадов с фото — вырез
и стекло, остальные — плоскости стекла и наличников; кровли — вальмы и двускатные с фронтонами. Материалы — слоты по
ключам krom_plan.COLORS, новых нет (недостающие цвета — ближайшие, список в pozemskogo_plan). Общие детали (Panels,
Openings, quad_hip, gable…) — как в scripts/blender/pskovgu.py: тот скрипт запускает сборку при импорте, поэтому здесь
копия. Оси здания (u, v, z) — как в плане; в Blender точка (u, −v, z).
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402
import krom_plan  # noqa: E402
import pozemskogo_plan as zp  # noqa: E402
import pskovgu_plan as pp  # noqa: E402
from bl_krom import M  # noqa: E402

WORK = os.path.join(bk.REPO, "build", "pozemskogo")
RENDER_DIR = os.path.join(WORK, "renders")


# ---------- общие детали (как в pskovgu.py) ----------

class Panels:
    """Плоские грани у стены (стёкла, наличники, простенки): по мешу на материал, нормаль — наружу по фасаду."""

    def __init__(self):
        self.faces = {}

    def add(self, fr, poly, d, key):
        self.faces.setdefault(key, []).append(([fr.p(s, z, d) for s, z in poly], fr.n))

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
    """Проёмы одного тела: вырезы копятся и вычитаются одной булевой операцией; стекло — плоскость у дна выреза."""

    def __init__(self, panels, frame="wall"):
        self.cutters, self.parts, self.pan, self.frame = [], [], panels, frame

    def window(self, fr, s, w, z0, z1, depth=0.25, sill=True, cross=True, trim=0.0):
        poly = bk.rect(s - w / 2, s + w / 2, z0, z1)
        self.cutters.append(bk.extrude("cut", fr, poly, -depth, 0.6, M["wall"]))
        self.pan.add(fr, poly, -depth + 0.01, "glass")
        if cross:
            zt = z0 + (z1 - z0) * 0.7
            self.pan.add(fr, bk.rect(s - 0.04, s + 0.04, z0, z1), -depth + 0.03, "wall")
            self.pan.add(fr, bk.rect(s - w / 2, s + w / 2, zt - 0.04, zt + 0.04), -depth + 0.03, "wall")
        if sill:
            self.parts.append(bk.extrude("sill", fr, bk.rect(s - w / 2 - 0.08, s + w / 2 + 0.08, z0 - 0.1, z0), -0.02,
                                         0.1, M[self.frame]))
        if trim:
            self.pan.add(fr, frame_poly(s, w, z0, z1, trim), 0.012, self.frame)

    def door(self, fr, s, w, z0, z1, depth=0.35, key="dark"):
        poly = bk.rect(s - w / 2, s + w / 2, z0, z1)
        self.cutters.append(bk.extrude("cut", fr, poly, -depth, 0.6, M["wall"]))
        self.pan.add(fr, poly, -depth + 0.01, key)

    def apply(self, *bodies):
        return cut_many(bodies, self.cutters) + self.parts


def cut_many(bodies, cutters):
    """Вычесть вырезы из нескольких тел (цоколь и стены): как bk.cut, но связка вырезов удаляется в конце."""
    if not cutters:
        return list(bodies)
    c = bk.join(cutters, "cutter") if len(cutters) > 1 else cutters[0]
    for obj in bodies:
        mod = obj.modifiers.new("cut", "BOOLEAN")
        mod.operation, mod.solver, mod.object = "DIFFERENCE", "MANIFOLD", c
        me = bpy.data.meshes.new_from_object(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        obj.modifiers.remove(mod)
        old, obj.data = obj.data, me
        bpy.data.meshes.remove(old)
    bpy.data.objects.remove(c)
    return list(bodies)


def glass(pan, fr, s, w, z0, z1, trim=0.0, key="wall"):
    """Окно без выреза: стекло в 1,5 см от стены, при trim — наличник-плоскость вокруг."""
    if trim:
        pan.add(fr, frame_poly(s, w, z0, z1, trim), 0.008, key)
    pan.add(fr, bk.rect(s - w / 2, s + w / 2, z0, z1), 0.015, "glass")


def frame_poly(s, w, z0, z1, f):
    """Наличник-рамка вокруг окна (∩ с подоконной полкой) — одна грань."""
    a, b = s - w / 2, s + w / 2
    return [(a - f, z0 - 0.06), (a, z0 - 0.06), (a, z1), (b, z1), (b, z0 - 0.06), (b + f, z0 - 0.06), (b + f, z1 + f),
            (a - f, z1 + f)]


def face(a, b, inside):
    """Фасад по отрезку a–b: s идёт слева направо, если смотреть снаружи."""
    fr = bk.Frame.between(a, b, inside)
    right = (fr.n[1], -fr.n[0])
    if (b[0] - a[0]) * right[0] + (b[1] - a[1]) * right[1] < 0:
        fr = bk.Frame.between(b, a, inside)
    return fr


def s_of(fr, u, v):
    """Координата s точки плана (u, v) на фасаде fr."""
    return (u - fr.o[0]) * fr.t[0] + (v - fr.o[1]) * fr.t[1]


def inside_of(P, a, b):
    """Точка внутри многоугольника P у середины стороны a–b (для нормали фасада наружу)."""
    m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    L = math.dist(a, b)
    n = (-(b[1] - a[1]) / L, (b[0] - a[0]) / L)
    for sg in (1, -1):
        q = (m[0] + sg * n[0] * 0.3, m[1] + sg * n[1] * 0.3)
        if pp.point_in(q, list(P)):
            return q
    raise ValueError("сторона без внутренней точки")


def ring_band(poly, z0, z1, proud, key="wall"):
    return bk.prism("band", pp.offset(list(poly), proud), z0, z1, M[key])


def quad_hip(name, P, z, rise, mat, over=0.5, thick=0.15, gable_ends=False):
    """Вальмовая (или при gable_ends — двускатная) кровля над выпуклым четырёхугольником P [(u, v)] с карнизом на z:
    конёк по оси между серединами коротких сторон; свес over — по плоскостям скатов."""
    P = [tuple(p) for p in P]
    L = [math.dist(P[k], P[(k + 1) % 4]) for k in range(4)]
    i = 0 if L[0] + L[2] <= L[1] + L[3] else 1
    a0, a1, c0, c1 = (P[(i + k) % 4] for k in range(4))
    ma, mc = ((a0[0] + a1[0]) / 2, (a0[1] + a1[1]) / 2), ((c0[0] + c1[0]) / 2, (c0[1] + c1[1]) / 2)
    D = math.dist(ma, mc)
    e = ((mc[0] - ma[0]) / D, (mc[1] - ma[1]) / D)
    da, dc = (0.0, 0.0) if gable_ends else (L[i] / 2, L[(i + 2) % 4] / 2)
    if gable_ends:
        ma, mc = (ma[0] - e[0] * over, ma[1] - e[1] * over), (mc[0] + e[0] * over, mc[1] + e[1] * over)
    ra = (ma[0] + e[0] * da, ma[1] + e[1] * da, z + rise)
    rc = (mc[0] - e[0] * dc, mc[1] - e[1] * dc, z + rise)
    slope = rise / ((L[i] + L[(i + 2) % 4]) / 4)
    Q = pp.offset([a0, a1, c0, c1], over)
    ze = z - over * slope
    top = [(q[0], q[1], ze) for q in Q]
    bot = [(q[0], q[1], ze - thick) for q in Q]
    rb = [(ra[0], ra[1], ra[2] - thick), (rc[0], rc[1], rc[2] - thick)]
    if gable_ends:     # торцы скатов — вертикальные, конёк до края свеса
        faces = [[1, 2, 5, 4], [3, 0, 4, 5], [7, 8, 11, 10], [9, 6, 10, 11], [1, 2, 8, 7], [3, 0, 6, 9],
                 [0, 4, 1, 7, 10, 6], [2, 5, 3, 9, 11, 8]]
        return bk.mesh(name, top + [ra, rc] + bot + rb, faces, mat)
    faces = [[0, 1, 4], [1, 2, 5, 4], [2, 3, 5], [3, 0, 4, 5], [6, 7, 8, 9]] + \
            [[k, (k + 1) % 4, 6 + (k + 1) % 4, 6 + k] for k in range(4)]
    return bk.mesh(name, top + [ra, rc] + bot, faces, mat)


def gable_wall(name, P, z0, z, rise, mat):
    """Щипцы двускатной кровли над четырёхугольником P: треугольники стены на коротких сторонах."""
    P = [tuple(p) for p in P]
    L = [math.dist(P[k], P[(k + 1) % 4]) for k in range(4)]
    i = 0 if L[0] + L[2] <= L[1] + L[3] else 1
    out = []
    for j in (i, i + 2):
        a, b = P[j % 4], P[(j + 1) % 4]
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        out.append(bk.mesh(name, [(a[0], a[1], z), (b[0], b[1], z), (m[0], m[1], z + rise),
                                  (a[0], a[1], z0), (b[0], b[1], z0)], [[3, 4, 1, 0], [0, 1, 2]], mat))
    return out


def gable(name, fr, s0, s1, ze, zr, d0, d1, mat, over=0.35, thick=0.16):
    """Двускатная кровля: сечение в плоскости фасада fr, протянутое по нормали от d0 до d1 (фронтон к фасаду)."""
    sm, hw = (s0 + s1) / 2, (s1 - s0) / 2
    slope = (zr - ze) / hw
    zo = ze - over * slope
    th = thick * math.hypot(1, slope)
    prof = [(s0 - over, zo), (sm, zr), (s1 + over, zo), (s1 + over, zo - thick), (sm, zr - th), (s0 - over, zo - thick)]
    return bk.extrude(name, fr, prof, d0, d1, mat)


def chimney(u, v, z0, z1, a=0.8, b=0.6, key="wall"):
    return bk.box("chimney", u - a / 2, u + a / 2, v - b / 2, v + b / 2, z0, z1, M[key])


def rise_of(width, pitch):
    return width / 2 * math.tan(math.radians(pitch))


# ---------- ул. Леона Поземского, 8 ----------

def poz8(c):
    """Прямоугольник 53,1 × 13,0: цоколь, три этажа окон по 15 осей на длинных фасадах и по две на торцах, три входа
    со двора с лестничными окнами в полуэтажах и козырьками, белый карниз, вальма из оцинковки с трубами по коньку."""
    a, b = c.half
    z = c.z_foot
    pan = Panels()
    P = list(c.outline)
    zc = c.z_eave - c.cornice
    base = bk.prism("plinth", pp.offset(P, 0.06), z, c.z_plinth, M["stone"])
    body = bk.prism("walls", P, c.z_plinth, zc + 0.05, M["pink"])
    op = Openings(pan)
    W, lo, hi = c.win
    fl = [c.z_plinth + k * c.floor for k in range(c.floors)]
    west, east = face((-a, -b), (a, -b), (0, 0)), face((a, b), (-a, b), (0, 0))
    south, north = face((-a, b), (-a, -b), (0, 0)), face((a, -b), (a, b), (0, 0))
    us = [(k - (c.axes - 1) / 2) * c.bay for k in range(c.axes)]
    parts = []
    for fr, v in ((west, -b), (east, b)):
        for u in us:
            s = s_of(fr, u, v)
            if fr is west and any(abs(u - e) < 0.1 for e in c.entrances):
                op.door(fr, s, 1.4, 0.05, 2.35)
                parts.append(bk.extrude("canopy", fr, bk.rect(s - 1.3, s + 1.3, 2.6, 2.75), 0.0, 1.3, M["wall"]))
                parts.append(bk.extrude("steps", fr, bk.rect(s - 1.1, s + 1.1, z, 0.05), 0.0, 1.1, M["stone"]))
                for f0 in fl[:-1]:                      # лестничная клетка: окна на площадках между этажами
                    op.window(fr, s, 1.1, f0 + c.floor / 2 + 0.6, f0 + c.floor / 2 + 2.0, depth=0.2, cross=False)
                continue
            for f0 in fl:
                op.window(fr, s, W, f0 + lo, f0 + hi, depth=0.22, trim=0.1)
    for fr, u in ((south, -a), (north, a)):
        for v in c.ends:
            s = s_of(fr, u, v)
            for f0 in fl:
                op.window(fr, s, W, f0 + lo, f0 + hi, depth=0.22, trim=0.1)
    parts += op.apply(base, body)
    parts.append(ring_band(P, c.z_plinth, c.z_plinth + 0.15, 0.1))        # тяга над цоколем
    parts.append(ring_band(P, zc, zc + 0.2, 0.2))                        # карниз двумя уступами
    parts.append(ring_band(P, zc + 0.2, c.z_eave, 0.42))
    rise = rise_of(2 * b + 0.84, c.pitch)
    parts.append(quad_hip("roof", pp.offset(P, 0.42), c.z_eave, rise, M["tin"], over=0.12))
    zr = c.z_eave + rise
    for u in c.chimneys:
        parts.append(chimney(u, 0.0, zr - 1.5, zr + 1.1, key="wall"))
    return parts + pan.objects()


# ---------- ул. Леона Поземского, 6А ----------

def poz6a(c):
    """Трапеция по OSM: высокий юго-западный фасад (бывший брандмауэр) с двумя рядами окон и кирпичной надписью,
    односкатная кровля на северо-восток с коротким скатом к фасаду; окна двора — плоскости (гип.)."""
    A, B, C, D = c.outline
    z = c.z_foot
    r, zr = c.ridge

    def on(p, q, v):   # точка стороны p → q с координатой v
        t = (v - p[1]) / (q[1] - p[1])
        return (p[0] + t * (q[0] - p[0]), v)

    Ar, Br = on(A, D, r), on(B, C, r)
    verts = [(*A, z), (*B, z), (*C, z), (*D, z), (*A, c.z_sw), (*B, c.z_sw), (*Br, zr), (*C, c.z_ne), (*D, c.z_ne),
             (*Ar, zr)]
    faces = [[0, 3, 2, 1], [0, 1, 5, 4], [1, 2, 7, 6, 5], [2, 3, 8, 7], [3, 0, 4, 9, 8], [4, 5, 6, 9], [9, 6, 7, 8]]
    body = bk.mesh("walls", verts, faces, M["ruin"])
    pan = Panels()
    op = Openings(pan)
    sw = face(A, B, (16.0, 5.0))
    for u in c.axes:
        s = s_of(sw, u, 0.0)
        w = 1.4 if u < 5 else c.win_w
        for z0, z1 in c.rows:
            op.window(sw, s, w, z0, z1, depth=0.3, cross=u < 5, sill=True)
    parts = op.apply(body)
    su, z0, z1 = c.sign
    s = s_of(sw, su, 0.0)
    parts.append(bk.extrude("sign", sw, bk.rect(s - 1.4, s + 1.4, z0, z1), -0.01, 0.02, M["pink"]))
    ne = face(C, D, (16.0, 5.0))

    def v_ne(u):                                              # северо-восточная сторона: v при данном u
        return D[1] + (C[1] - D[1]) * (u - D[0]) / (C[0] - D[0])
    for u in c.axes[1:]:                                      # двор — гипотеза: те же оси, окна-плоскости
        s = s_of(ne, u, v_ne(u))
        if 0.8 < s < ne.length - 0.8:
            for zz0, zz1 in c.rows:
                glass(pan, ne, s, 0.9, zz0, zz1)
    parts.append(ring_band([A, B, C, D], z, c.z_plinth, 0.05, "stone"))

    def zroof(q):
        u, v = q
        if v <= r:
            return c.z_sw + (zr - c.z_sw) * max(v, 0.0) / r
        return zr - (zr - c.z_ne) * (v - r) / (v_ne(u) - r)
    Qa, Qb, Qc, Qd = pp.offset([A, B, C, D], 0.3)              # свес 0,3 на двор и торцы, у фасада — по стене
    Qa, Qb = (Qa[0], 0.0), (Qb[0], 0.0)
    Qar, Qbr = on(Qa, Qd, r), on(Qb, Qc, r)
    t = 0.14
    for poly in ([Qa, Qb, Qbr, Qar], [Qar, Qbr, Qc, Qd]):
        pts = [(q[0], q[1], zroof(q) + 0.03) for q in poly]
        parts.append(bk.mesh("roof", pts + [(u, v, zz - t) for u, v, zz in pts],
                             [[0, 1, 2, 3], [7, 6, 5, 4], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]],
                             M["green"]))
    return parts + pan.objects()


# ---------- ул. Леона Поземского, 10 ----------

def poz10(c):
    """Г-образный дом: облицованный цокольный этаж, три жилых этажа, белые тяги; западный фасад по секциям —
    розовые простенки и фронтон на севере, лоджии посередине, широкий фронтон с балконами на юге; круглый эркер на
    северо-западном углу; вальмы крыльев, слуховые окна и трубы (aer5, aer1, a06)."""
    z = c.z_foot
    P = list(c.outline)
    ze = c.z_eave
    pan = Panels()
    parts = []
    base = bk.prism("base", pp.offset(P, 0.08), z, c.z_base, M["stone"])
    body = bk.prism("walls", P, c.z_base, ze - 0.35, M["house"])
    op = Openings(pan)
    W, lo, hi = c.win
    fl = [c.z_base + k * c.floor for k in range(c.floors)]
    n = len(P)
    west = face((0.0, 0.0), (37.81, 0.0), (5.0, 5.0))
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        L = math.dist(a, b)
        if L < 3.0:
            continue
        fr = face(a, b, inside_of(P, a, b))
        is_west = abs(a[1]) < 1e-6 and abs(b[1]) < 1e-6
        is_south = abs(a[0]) < 1e-6 and abs(b[0]) < 1e-6
        k = int((L - 1.6) // c.bay)
        s0 = (L - (k - 1) * c.bay) / 2
        for j in range(k):
            s = s0 + j * c.bay
            pt = (fr.o[0] + s * fr.t[0], fr.o[1] + s * fr.t[1])
            if is_west:
                if pt[0] > 33.0:          # эркер
                    continue
                if c.loggias[0] < pt[0] < c.loggias[1]:
                    for f0 in fl:          # лоджия: глубокий проём с ограждением
                        op.window(fr, s, 2.2, f0 + 0.1, f0 + hi, depth=1.2, cross=False, sill=False)
                        pan.add(fr, bk.rect(s - 1.1, s + 1.1, f0 + 0.1, f0 + 1.05), -0.05, "wall")
                    continue
                for f0 in fl:
                    op.window(fr, s, W, f0 + lo, f0 + hi, depth=0.22, trim=0.12)
                op.window(fr, s, W + 0.3, 0.9, 2.7, depth=0.25, cross=False)    # цокольный этаж со стороны реки
            elif is_south:
                for f0 in fl:
                    op.window(fr, s, W, f0 + lo, f0 + hi, depth=0.22, trim=0.12)
                op.window(fr, s, W + 0.3, 0.9, 2.7, depth=0.25, cross=False)
            else:
                for f0 in fl:
                    glass(pan, fr, s, W, f0 + lo, f0 + hi, trim=0.1)
    parts += op.apply(base, body)
    for g0, g1, key in c.gables:                      # простенки секций фронтонов
        if key != "house":
            for f0 in fl:
                pan.add(west, bk.rect(s_of(west, g1, 0), s_of(west, g0, 0), f0, f0 + c.floor)
                        if s_of(west, g1, 0) < s_of(west, g0, 0) else
                        bk.rect(s_of(west, g0, 0), s_of(west, g1, 0), f0, f0 + c.floor), 0.004, key)
    # балконы южной секции (aer5): на двух осях у середины фронтона
    for u in (7.6, 11.0):
        s = s_of(west, u, 0.0)
        for f0 in fl:
            parts.append(bk.extrude("balcony", west, bk.rect(s - 1.3, s + 1.3, f0 - 0.15, f0), 0.0, 1.1, M["wall"]))
            parts.append(bk.extrude("rail", west, bk.rect(s - 1.3, s + 1.3, f0, f0 + 1.0), 1.05, 1.1, M["dark"]))
    parts.append(ring_band(P, c.z_base - 0.05, c.z_base + 0.25, 0.16))
    parts.append(ring_band(P, ze - 0.35, ze, 0.45))
    # эркер-башенка
    tu, tv, tr = c.tower
    parts.append(bk.lathe("tower", (tu, tv), [(tr, z), (tr, ze + 0.9), (0.0, ze + 0.9)], M["house"], seg=16,
                          smooth=False))
    parts.append(bk.lathe("tower_band", (tu, tv), [(tr + 0.08, z), (tr + 0.08, c.z_base)], M["stone"], seg=16,
                          smooth=False))
    for f0 in fl + [ze - 0.35]:
        parts.append(bk.lathe("tower_slab", (tu, tv), [(tr + 0.55, f0 - 0.15), (tr + 0.55, f0 + 0.05)], M["wall"],
                              seg=16, smooth=False))
    for k in range(5):                                # окна эркера — по кругу на запад и север
        ang = math.radians(-150 + 45 * k)
        frt = bk.Frame.radial((tu, tv), tr, ang)
        for f0 in fl:
            glass(pan, frt, 0.0, 1.0, f0 + lo, f0 + hi)
    parts.append(bk.lathe("tower_cap", (tu, tv), [(tr + 0.35, ze + 0.9), (0.0, ze + 4.6)], M["green"], seg=16,
                          smooth=False))
    # кровли крыльев: вальмы; фронтоны к реке
    r = rise_of(14.25, c.pitch)
    wq = [(0.0, 0.0), (37.8, 0.0), (37.8, 14.25), (0.0, 14.25)]
    parts.append(quad_hip("roof_w", wq, ze, r, M["green"], gable_ends=True))       # щипец южного торца (aer1)
    parts += gable_wall("gable_s", wq, ze - 0.35, ze, r, M["house"])
    bv, br = c.bay_s                                  # полукруглый эркер южного торца, два верхних этажа
    parts.append(bk.lathe("bay_s", (0.0, bv), [(br, fl[-2] - 0.2), (br, ze - 0.2)], M["house"], seg=12, smooth=False,
                          arc=(math.pi / 2, 3 * math.pi / 2)))
    parts.append(bk.lathe("bay_s_cap", (0.0, bv), [(br + 0.3, ze - 0.2), (0.0, ze + 1.2)], M["green"], seg=12,
                          smooth=False, arc=(math.pi / 2, 3 * math.pi / 2)))
    for f0 in fl[-2:]:
        for k in range(3):
            frb = bk.Frame.radial((0.0, bv), br, math.radians(135 + 45 * k))
            glass(pan, frb, 0.0, 0.8, f0 + lo, f0 + hi)
    rn = rise_of(16.03, c.pitch)
    parts.append(quad_hip("roof_n", [(37.66, 8.64), (53.69, 8.64), (53.69, 34.69), (37.66, 34.69)], ze, rn,
                          M["green"]))
    parts.append(quad_hip("roof_e1", [(42.27, 34.69), (53.69, 34.69), (53.69, 40.29), (42.27, 40.29)], ze,
                          rise_of(5.6, c.pitch), M["green"], over=0.4))
    parts.append(quad_hip("roof_e2", [(46.3, 40.29), (53.69, 40.29), (53.69, 45.73), (46.3, 45.73)], ze,
                          rise_of(5.44, c.pitch), M["green"], over=0.4))
    parts.append(bk.box("roof_step", 37.8, 46.76, 5.46 - 0.4, 8.9, ze - 0.05, ze + 0.2, M["green"]))
    for g0, g1, key in c.gables:
        s0, s1 = sorted((s_of(west, g0, 0.0), s_of(west, g1, 0.0)))
        zr = ze + rise_of(g1 - g0, c.pitch + 4)
        parts.append(gable("gable_roof", west, s0, s1, ze, zr, -7.1, 0.55, M["green"], over=0.3))
        parts.append(bk.extrude("gable_wall", west, [(s0, ze - 0.4), (s1, ze - 0.4), ((s0 + s1) / 2, zr - 0.2)],
                                -0.3, 0.0, M["house"]))
        parts.append(bk.extrude("gable_band", west, bk.rect(s0 - 0.1, s1 + 0.1, ze - 0.35, ze), -0.3, 0.45, M["wall"]))
        sm = (s0 + s1) / 2
        pan.add(west, bk.arch(sm, 1.3, ze + 0.5, ze + 1.7, n=8), 0.02, "glass")
    for u, v in c.dormers:
        zb = ze + 1.6
        parts.append(bk.box("dormer", u - 0.8, u + 0.8, v - 0.8, v + 0.8, zb - 1.5, zb + 1.3, M["house"]))
        parts.append(quad_hip("dormer_roof", [(u - 0.8, v - 0.8), (u + 0.8, v - 0.8), (u + 0.8, v + 0.8),
                                              (u - 0.8, v + 0.8)], zb + 1.3, 0.7, M["green"], over=0.15, thick=0.08))
    for u, v in c.chimneys:
        parts.append(chimney(u, v, ze + 2.0, ze + r + 1.4, key="house"))
    return parts + pan.objects()


# ---------- ул. Леона Поземского, 24 ----------

def poz24(c):
    """Юго-восточное крыло в три этажа под двускатной кровлей со щипцами; северо-западный блок — кольцо двухэтажных
    корпусов вокруг двора под стеклом (гип.), северо-западный торец кирпичный; красные кровли (aer5, спутник S-21)."""
    z = c.z_foot
    P = [tuple(p) for p in c.outline]
    wing = [tuple(p) for p in c.wing]                  # P4, P3, P2, P1
    block = [P[3], P[4], P[5], P[6], P[7], P[8], P[0]]    # остальное: P4 … P9, P1 (общая с крылом сторона P1–P4)
    pan = Panels()
    parts = []
    zb, zw = c.z_block, c.z_wing
    wb = bk.prism("wing", wing, 0.9, zw - 0.3, M["house"])
    wbase = bk.prism("wing_base", pp.offset(wing, 0.06), z, 0.9, M["stone"])
    bb = bk.prism("block", block, 0.9, zb - 0.3, M["house"])
    bbase = bk.prism("block_base", pp.offset(block, 0.06), z, 0.9, M["stone"])
    brick = bk.prism("brick", [P[5], P[6], (P[6][0] - 3.0, P[6][1] + 13.0), (P[5][0] + 13.5, P[5][1] + 1.0)], 0.9,
                     zb - 0.3, M["pink"])            # кирпичный северо-западный корпус (aer5; ширина — гип.)
    shared = {(P[0], P[3]), (P[3], P[0])}
    for poly, floors, zt, bodies, riverside in ((wing, c.floors_wing, zw, (wb, wbase), {(P[2], P[3]), (P[3], P[2])}),
                                                (block, c.floors_block, zb, (bb, bbase, brick),
                                                 {(P[4], P[5]), (P[5], P[4]), (P[3], P[4]), (P[4], P[3]),
                                                  (P[5], P[6]), (P[6], P[5])})):
        op = Openings(pan)
        z1 = c.z_wing_base if poly is wing else 0.9               # пол 1-го этажа: у крыла земля выше (P3–P4)
        fh = (zt - 0.3 - z1) / floors
        n = len(poly)
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            if (a, b) in shared:
                continue
            L = math.dist(a, b)
            if L < 4.0:
                continue
            fr = face(a, b, inside_of(poly, a, b))
            k = int((L - 2.0) // 3.6)
            s0 = (L - (k - 1) * 3.6) / 2
            for j in range(k):
                s = s0 + j * 3.6
                for f in range(floors):
                    f0 = z1 + f * fh
                    if (a, b) in riverside:
                        op.window(fr, s, 1.5, f0 + 0.9, f0 + fh - 0.8, depth=0.3)
                    else:
                        glass(pan, fr, s, 1.4, f0 + 0.9, f0 + fh - 0.8, trim=0.1)
        parts += op.apply(*bodies)
        parts.append(ring_band(poly, zt - 0.3, zt, 0.35))
    # кровли: крыло — двускатная со щипцами; кольцо — корпуса вдоль сторон P5–P6, P6–P7, P7–P8 шириной depth
    d = c.depth
    wr = rise_of(16.0, c.pitch)
    parts.append(quad_hip("roof_wing", wing, zw, wr, M["pink"], over=0.4, gable_ends=True))
    parts += gable_wall("wing_gable", wing, zw - 0.3, zw, wr, M["house"])
    br = rise_of(d, c.pitch)
    for a, b in ((P[4], P[5]), (P[5], P[6]), (P[6], P[7])):
        L = math.dist(a, b)
        t = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        m = inside_of(block, a, b)
        nn = (-t[1], t[0])
        if (m[0] - a[0]) * nn[0] + (m[1] - a[1]) * nn[1] < 0:
            nn = (-nn[0], -nn[1])
        quad = [a, b, (b[0] + nn[0] * d, b[1] + nn[1] * d), (a[0] + nn[0] * d, a[1] + nn[1] * d)]
        parts.append(quad_hip("roof_block", quad, zb, br, M["pink"], over=0.4))
    parts.append(bk.prism("atrium", block, zb - 0.9, zb - 0.5, M["glass"]))   # двор под стеклом (гип.)
    for u, v in ((10.0, -20.0), (30.0, -48.0), (48.0, -10.0)):
        parts.append(chimney(u, v, zb + br - 1.2, zb + br + 0.8, key="pink"))
    return parts + pan.objects()


# ---------- сборка и превью ----------

BUILD = {"Pozemskogo8": poz8, "Pozemskogo6A": poz6a, "Pozemskogo10": poz10, "Pozemskogo24": poz24}

OVERVIEW = {   # общие виды для проверки формы: (глаз, цель) в осях здания
    "Pozemskogo8": {"overview": ((-40.0, -60.0, 30.0), (0.0, 0.0, 5.0)), "street": ((30.0, 45.0, 20.0), (0.0, 0.0, 5.0))},
    "Pozemskogo6A": {"overview": ((-25.0, -35.0, 20.0), (16.0, 5.0, 4.0)), "yard": ((45.0, 40.0, 25.0), (16.0, 5.0, 4.0))},
    "Pozemskogo10": {"overview": ((-20.0, -60.0, 35.0), (25.0, 20.0, 6.0)), "back": ((80.0, 70.0, 40.0), (25.0, 20.0, 6.0))},
    "Pozemskogo24": {"overview": ((-50.0, -60.0, 50.0), (28.0, 0.0, 5.0)), "back": ((110.0, 60.0, 60.0), (28.0, 0.0, 5.0))},
}


def render_view(name, eye, yaw, pitch, roll, f, cx, cy, size, scale=1.0, **_):
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
    print(f"[pozemskogo] preview {s.render.filepath}")


def views():
    path = os.path.join(WORK, "views.json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def build(c, cams):
    name = c.asset
    bk.reset_scene()
    bk.use_colors(krom_plan.COLORS)
    objs = BUILD[c.key](c)
    obj = bk.join(objs, name)
    bk.box_uv(obj)
    me = obj.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    print(f"[pozemskogo] {c.name}: {len(objs)} тел → {name}: {len(me.vertices)} вершин, {len(me.polygons)} граней "
          f"({tris} треугольников), слоты {[m.name for m in me.materials]}")
    bk.export_glb(obj, name)
    ground = bk.box("ground", -400, 400, -400, 400, -0.05, 0.0, bk.material("ground", (0.12, 0.16, 0.08)))
    ground.hide_select = True
    for view, cam in cams.get(c.key, {}).items():
        render_view(f"{c.key}_{view}", **cam)
    bk.PREVIEW_DIR = RENDER_DIR
    for view, (eye, tgt) in OVERVIEW[c.key].items():
        bk.render_preview(f"{c.key}_{view}", eye=(eye[0], -eye[1], eye[2]), target=(tgt[0], -tgt[1], tgt[2]),
                          size=(1200, 700), lens=35)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    todo = [c for c in zp.POZEMSKOGO if not argv or c.key in argv]
    if not todo:
        raise SystemExit(f"[pozemskogo] нет здания {argv}; есть: {[c.key for c in zp.POZEMSKOGO]}")
    cams = views()
    for c in todo:
        build(c, cams)


main()
