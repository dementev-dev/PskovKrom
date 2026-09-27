"""lenina.py — герои площади Ленина (D-043, партия 3) скриптом Blender по scripts/lenina_plan.py (D-018):
библиотека им. И. И. Василева (бывший кинотеатр «Октябрь», пл. Ленина, 3) и «Центр семьи» (бывший Дом культуры
профсоюзов, пл. Ленина, 1).

    python scripts/bl_run.py scripts/blender/lenina.py                 # оба
    python scripts/bl_run.py scripts/blender/lenina.py -- Library      # один (Library, DKP)

Выгрузка — build/blender/<asset>.glb (в UE ставит scripts/heroes_krom.py после подключения плана в
krom_plan.buildings()), общий вид — build/lenina/renders/lenina_<ключ>_overview.png. Размеры, высоты и источники —
в плане.

Дом собирается из блоков плана тем же генератором, что и Запсковье (scripts/blender/zapskovye.py: тот скрипт запускает
сборку при импорте, поэтому здесь копия общих деталей — Panels, Openings, кровли, build_block). Особое у каждого
здания — в функциях extras_<ключ>: у кинотеатра — утопленный центр главного фасада между пилонами, большие лопатки
с выемками, ложные окна пилонов, ниши и окна боковых фасадов, крыльцо, западный фасад с нишами, выходами из залов,
слуховыми окнами и нишей в тимпане; у ДКП — лоджия портика, колонны, ступени. Деталь дешёвая: здания видны
с 60–250 м (≤15 тыс. треугольников на здание). Материалы — только ключи krom_plan.COLORS. Оси (u, v, z) — как в плане;
в Blender точка (u, −v, z).
"""
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402
import krom_plan  # noqa: E402
import lenina_plan as lp  # noqa: E402
import zapskovye_plan as zp  # noqa: E402 — сетка окон-плоскостей (grid)
from pskovgu_plan import offset  # noqa: E402
from bl_krom import M  # noqa: E402

RENDER_DIR = os.path.join(bk.REPO, "build", "lenina", "renders")
CHIMNEY = {"Library": "wall", "DKP": "wall"}   # вентшахты на кровлях (фото o06, a02) — белые


# ---------- общие детали (как в pskovgu.py) ----------

class Panels:
    """Плоские грани в 1–2 см от стены (стёкла, переплёты, решётки): по мешу на материал, нормаль — наружу."""

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
                if (b[1] - b[0]).cross(b[2] - b[0]).dot(Vector((n[0], -n[1], 0.0))) < 0:
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
    """Проёмы одного тела: вырезы вычитаются одной булевой операцией; стекло — плоскость у дна выреза."""

    def __init__(self, panels):
        self.cutters, self.parts, self.pan = [], [], panels

    def window(self, fr, s, w, z0, z1, depth=0.22, sill=True, cross=True, hood=None, key="wall", poly=None):
        poly = poly or bk.rect(s - w / 2, s + w / 2, z0, z1)
        self.cutters.append(bk.extrude("cut", fr, poly, -depth, 0.6, M[key]))
        self.pan.add(fr, poly, -depth + 0.01, "glass")
        if cross:
            zt = z0 + (z1 - z0) * 0.68
            self.pan.add(fr, bk.rect(s - 0.04, s + 0.04, z0, zt + 0.04), -depth + 0.03, "wall")
            self.pan.add(fr, bk.rect(s - w / 2, s + w / 2, zt - 0.04, zt + 0.04), -depth + 0.03, "wall")
        if sill:
            self.parts.append(bk.extrude("sill", fr, bk.rect(s - w / 2 - 0.1, s + w / 2 + 0.1, z0 - 0.1, z0), -0.02,
                                         0.1, M[key]))
        if hood in ("shelf", "tri"):
            self.parts.append(bk.extrude("hood", fr, bk.rect(s - w / 2 - 0.18, s + w / 2 + 0.18, z1 + 0.1, z1 + 0.24),
                                         -0.02, 0.14, M[key]))
        if hood == "tri":
            self.parts.append(bk.extrude("hood_tri", fr, [(s - w / 2 - 0.15, z1 + 0.24), (s + w / 2 + 0.15, z1 + 0.24),
                                                          (s, z1 + 0.24 + 0.25 * (w + 0.3))], -0.02, 0.1, M[key]))

    def door(self, fr, s, w, z0, z1, depth=0.35, poly=None):
        poly = poly or bk.rect(s - w / 2, s + w / 2, z0, z1)
        self.cutters.append(bk.extrude("cut", fr, poly, -depth, 0.6, M["wall"]))
        self.pan.add(fr, poly, -depth + 0.01, "dark")

    def apply(self, body):
        return [bk.cut(body, self.cutters)] + self.parts


def glass(pan, fr, s, w, z0, z1):
    """Окно-плоскость (гипотеза): стекло в 1,5 см от стены."""
    pan.add(fr, bk.rect(s - w / 2, s + w / 2, z0, z1), 0.015, "glass")


def centroid(P):
    return sum(p[0] for p in P) / len(P), sum(p[1] for p in P) / len(P)


def edge_frame(P, i):
    """Фасад по стороне i четырёхугольника P: s — от угла i, нормаль — наружу."""
    return bk.Frame.between(P[i], P[(i + 1) % len(P)], centroid(P))


def band(P, z0, z1, proud, key="wall"):
    return bk.prism("band", offset(list(P), proud), z0, z1, M[key])


def mid(a, b):
    return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2


def quad_hip(name, P, z, rise, mat, over=0.4, thick=0.15):
    """Вальмовая кровля над выпуклым четырёхугольником: конёк по оси между серединами коротких сторон."""
    P = [tuple(p) for p in P]
    L = [math.dist(P[k], P[(k + 1) % 4]) for k in range(4)]
    i = 0 if L[0] + L[2] <= L[1] + L[3] else 1
    a0, a1, c0, c1 = (P[(i + k) % 4] for k in range(4))
    ma, mc = mid(a0, a1), mid(c0, c1)
    D = math.dist(ma, mc)
    e = ((mc[0] - ma[0]) / D, (mc[1] - ma[1]) / D)
    da, dc = min(L[i] / 2, D / 2), min(L[(i + 2) % 4] / 2, D / 2)
    ra = (ma[0] + e[0] * da, ma[1] + e[1] * da, z + rise)
    rc = (mc[0] - e[0] * dc, mc[1] - e[1] * dc, z + rise)
    slope = rise / max(0.5, (L[(i + 1) % 4] + L[(i + 3) % 4]) / 4)
    Q = offset([a0, a1, c0, c1], over)
    ze = z - over * slope
    top = [(q[0], q[1], ze) for q in Q]
    bot = [(q[0], q[1], ze - thick) for q in Q]
    faces = [[0, 1, 4], [1, 2, 5, 4], [2, 3, 5], [3, 0, 4, 5], [6, 7, 8, 9]] + \
            [[k, (k + 1) % 4, 6 + (k + 1) % 4, 6 + k] for k in range(4)]
    return bk.mesh(name, top + [ra, rc] + bot, faces, mat)


def gable_quad(name, P, z, rise, roof_mat, wall_mat, over=0.4, thick=0.18):
    """Двускатная кровля над четырёхугольником P: карнизы по сторонам 0 и 2, конёк — между серединами сторон 1 и 3;
    щипцы (стенки-треугольники) на сторонах 1 и 3. Возвращает [кровля, щипец, щипец]."""
    P0, P1, P2, P3 = [tuple(p) for p in P]
    R0, R1 = mid(P3, P0), mid(P1, P2)
    e = (R1[0] - R0[0], R1[1] - R0[1])
    le = math.hypot(*e)
    e = (e[0] / le, e[1] / le)
    ext = lambda p, s: (p[0] + e[0] * s, p[1] + e[1] * s)       # noqa: E731
    half = (math.dist(P0, P3) + math.dist(P1, P2)) / 4
    slope = rise / max(half, 0.5)

    def eave(a, r):                                           # карнизная точка с выносом over по скату
        d = (a[0] - r[0], a[1] - r[1])
        ld = math.hypot(*d)
        return (a[0] + d[0] / ld * over, a[1] + d[1] / ld * over)
    zo = z - over * slope
    E0, E1 = eave(ext(P0, -over), ext(R0, -over)), eave(ext(P1, over), ext(R1, over))
    E3, E2 = eave(ext(P3, -over), ext(R0, -over)), eave(ext(P2, over), ext(R1, over))
    Ra, Rb = ext(R0, -over), ext(R1, over)
    top = [(*E0, zo), (*E1, zo), (*Rb, z + rise), (*Ra, z + rise), (*E2, zo), (*E3, zo)]
    bot = [(x, y, zz - thick) for x, y, zz in top]
    faces = [[0, 1, 2, 3], [3, 2, 4, 5], [6, 9, 8, 7], [9, 11, 10, 8],
             [0, 3, 9, 6], [3, 5, 11, 9], [1, 7, 8, 2], [2, 8, 10, 4], [0, 6, 7, 1], [5, 4, 10, 11]]
    roof = bk.mesh(name, top + bot, faces, roof_mat)
    out = [roof]
    for a, b, r in ((P1, P2, R1), (P3, P0, R0)):              # щипцы — треугольные стенки толщиной 0,3 внутрь
        c = centroid(P)
        n = (c[0] - r[0], c[1] - r[1])
        ln = math.hypot(*n)
        n = (n[0] / ln * 0.3, n[1] / ln * 0.3)
        tri = [(*a, z - 0.05), (*b, z - 0.05), (*r, z + rise - 0.05)]
        tri2 = [(x + n[0], y + n[1], zz) for x, y, zz in tri]
        faces = [[0, 1, 2], [5, 4, 3], [0, 3, 4, 1], [1, 4, 5, 2], [2, 5, 3, 0]]
        out.append(bk.mesh(f"{name}_gable", tri + tri2, faces, wall_mat))
    return out


def mansard(name, P, z, rise, inset, mat, top_rise=0.6, over=0.25):
    """Мансардная кровля: крутой нижний скат с отступом inset и подъёмом rise, сверху — пологая вальма."""
    Po = offset(list(P), over)
    Q = offset(list(P), -inset)
    verts = [(u, v, z - 0.1) for u, v in Po] + [(u, v, z + rise) for u, v in Q]
    faces = [[k, (k + 1) % 4, 4 + (k + 1) % 4, 4 + k] for k in range(4)] + [[3, 2, 1, 0], [4, 5, 6, 7]]
    return [bk.mesh(name, verts, faces, mat), quad_hip(f"{name}_top", Q, z + rise, top_rise, mat, over=0.08)]


def shed(name, P, z, rise, roof_mat, wall_mat, over=0.35, thick=0.15):
    """Односкатная кровля: сторона 0 — низ (z), сторона 2 — верх (z + rise); под скатом — клин стены."""
    P0, P1, P2, P3 = [tuple(p) for p in P]
    wedge = bk.mesh(f"{name}_wall", [(*P0, z - 0.05), (*P1, z - 0.05), (*P2, z - 0.05), (*P3, z - 0.05),
                                     (*P2, z + rise), (*P3, z + rise)],
                    [[0, 1, 2, 3], [3, 2, 4, 5], [0, 5, 4, 1], [1, 4, 2], [0, 3, 5]], wall_mat)
    Q = offset([P0, P1, P2, P3], over)
    zz = [z - 0.1, z - 0.1, z + rise + 0.1, z + rise + 0.1]
    top = [(q[0], q[1], h) for q, h in zip(Q, zz)]
    bot = [(x, y, h - thick) for x, y, h in top]
    return [wedge, bk.mesh(name, top + bot, [[0, 1, 2, 3], [7, 6, 5, 4]] +
                           [[k, 4 + k, 4 + (k + 1) % 4, (k + 1) % 4] for k in range(4)], roof_mat)]


def chevron(fr, s0, s1, z, zr, w=0.3):
    """Раскреповка щипца/фронтона — «∧» по скатам треугольника (s0, z) — (середина, zr) — (s1, z)."""
    sm = (s0 + s1) / 2
    k = (zr - z) / ((s1 - s0) / 2)
    dz = w * math.hypot(1, k)
    return [(s0 - 0.25, z - 0.02), (sm, zr + 0.2), (s1 + 0.25, z - 0.02), (s1 - 0.1, z - 0.02), (sm, zr + 0.2 - dz),
            (s0 + 0.1, z - 0.02)]


# ---------- блок ----------

def build_block(h, b, pan, parts):
    """Стены, проёмы, пояса, карниз и кровля одного блока плана."""
    P = [tuple(p) for p in b.quad]
    upper = b.z_plinth >= 5                                    # надстройка на другом блоке: без цоколя
    z0 = b.z_plinth if upper else h.base_z
    zt = b.z_eave - 0.3
    if zt > z0 + 0.1:
        split = b.low and b.z_belt > z0
        bodies = [(z0, b.z_belt, b.low), (b.z_belt, zt, b.wall)] if split else [(z0, zt, b.wall)]
        for bz0, bz1, key in bodies:
            body = bk.prism(f"walls_{b.name}", P, bz0, bz1, M[key])
            op = Openings(pan)
            for f in b.fronts:
                fr = edge_frame(P, f.edge)
                doors = {round(s, 2): (w, top) for s, w, top in f.doors}
                for r, (r0, r1, kind) in enumerate(f.rows):
                    if not (bz0 <= r0 < bz1):
                        continue
                    for k, s in enumerate(f.axes):
                        if (r, k) in f.skip:
                            continue
                        if r == 0 and round(s, 2) in doors:
                            w, top = doors[round(s, 2)]
                            op.door(fr, s, w, 0.15, top)
                            continue
                        if not f.cut:
                            glass(pan, fr, s, f.w, r0, r1)
                            continue
                        poly = bk.arch(s, f.w, r0, r1 - f.w / 2, n=8) if kind == "a" else None
                        op.window(fr, s, f.w, r0, r1, hood=dict(f.hood).get(r), key=b.trim, poly=poly,
                                  cross=kind != "a")
                        if kind == "a":
                            pan.add(fr, bk.arch_frame(s, f.w, r1 - f.w / 2, r1 - f.w / 2, 0.12, n=8), 0.015, b.trim)
            parts += op.apply(body)
        for edge, step, rows in b.backs:                      # фасады без фото — окна-плоскости (гипотеза)
            fr = edge_frame(P, edge)
            for s in zp.grid(fr.length, step):
                for r0, r1, _ in rows:
                    glass(pan, fr, s, 1.05, r0, r1)
        if not upper:
            parts.append(band(P, h.base_z, b.z_plinth, 0.05, "stone"))
        for z in b.belts:
            parts.append(band(P, z - 0.1, z + 0.12, 0.08, b.trim))
        parts.append(band(P, b.z_eave - 0.5, b.z_eave - 0.18, 0.12, b.trim))
        parts.append(band(P, b.z_eave - 0.18, b.z_eave, 0.32, b.trim))
    roof, ze = M[b.roof_key], b.z_eave
    if b.roof == "hip":
        parts.append(quad_hip(f"roof_{b.name}", P, ze, b.rise, roof))
    elif b.roof == "gable":
        parts += gable_quad(f"roof_{b.name}", P, ze, b.rise, roof, M[b.wall])
    elif b.roof == "front":                                   # щипец/фронтон — на стороне 0
        parts += gable_quad(f"roof_{b.name}", [P[3], P[0], P[1], P[2]], ze, b.rise, roof, M[b.wall])
        fr = edge_frame(P, 0)
        parts.append(bk.extrude("pediment_cornice", fr, chevron(fr, 0.0, fr.length, ze, ze + b.rise), -0.05, 0.3,
                                M[b.trim]))
    elif b.roof == "mansard":
        parts += mansard(f"roof_{b.name}", P, ze, b.rise, b.inset, roof)
    elif b.roof == "shed":
        parts += shed(f"roof_{b.name}", P, ze, b.rise, roof, M[b.wall])
    elif b.roof == "flat":
        parts.append(bk.prism(f"roof_{b.name}", offset(P, 0.3), ze - 0.2, ze, roof))
    ridge = ze + b.rise + (0.6 if b.roof == "mansard" else 0.0)
    for u, v in b.chimneys:
        parts.append(bk.box("chimney", u - 0.45, u + 0.45, v - 0.3, v + 0.3, ze, ridge + 1.2, M[CHIMNEY[h.key]]))
        parts.append(bk.box("chimney_cap", u - 0.55, u + 0.55, v - 0.4, v + 0.4, ridge + 1.2, ridge + 1.35,
                            M[CHIMNEY[h.key]]))


def front_frame(h, name, edge=0):
    b = next(b for b in h.blocks if b.name == name)
    return edge_frame([tuple(p) for p in b.quad], edge), b


def balcony(parts, pan, fr, s, z, w, depth=0.9):
    parts.append(bk.extrude("balcony", fr, bk.rect(s - w / 2, s + w / 2, z - 0.18, z), 0.0, depth, M["stone"]))
    rail = bk.Frame(fr.p(0, 0, depth)[:2], fr.t, fr.n)
    pan.add(rail, bk.rect(s - w / 2, s + w / 2, z, z + 0.95), 0.0, "dark")


# ---------- помощники фасадов площади Ленина ----------

def s_of(fr, u, v):
    """Координата s точки плана (u, v) вдоль фасада fr."""
    return (u - fr.o[0]) * fr.t[0] + (v - fr.o[1]) * fr.t[1]


def take_body(parts, name):
    """Вынуть из parts тело стен блока name (после build_block), чтобы вырезать в нём ещё проёмы."""
    body = next(o for o in parts if o.name.startswith(f"walls_{name}"))
    parts.remove(body)
    return body


def pane(pan, fr, s, w, z0, z1, d, bars=(), transom=None):
    """Остеклённый проём плоскостью на глубине d от плоскости фасада: стекло, импосты (смещения по s) и фрамуга."""
    pan.add(fr, bk.rect(s - w / 2, s + w / 2, z0, z1), d, "glass")
    for b in bars:
        pan.add(fr, bk.rect(s + b - 0.05, s + b + 0.05, z0, z1), d + 0.02, "wall")
    if transom:
        pan.add(fr, bk.rect(s - w / 2, s + w / 2, transom - 0.05, transom + 0.05), d + 0.02, "wall")


def polygon(s, z, r, n):
    return [(s + r * math.cos(2 * math.pi * k / n), z + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def cut_box(op, fr, s0, s1, z0, z1, depth):
    op.cutters.append(bk.extrude("cut", fr, bk.rect(s0, s1, z0, z1), -depth, 0.6, M["wall"]))


# ---------- пл. Ленина, 3: кинотеатр «Октябрь» ----------

def extras_library(h, pan, parts):
    """Главный фасад «триумфальной аркой» (утопленный центр, большие лопатки с выемками, пилоны с ложными окнами),
    крыльцо, боковые фасады 2-этажного объёма (ниши с окнами, лестница, большое и шестигранные окна), двухсветный
    объём: ложные окна по бокам, западный фасад с нишами и выходами из залов, слуховые окна и ниша в тимпане (S-156)."""
    front = next(b for b in h.blocks if b.name == "front")
    halls = next(b for b in h.blocks if b.name == "halls")
    P, Q = [tuple(p) for p in front.quad], [tuple(p) for p in halls.quad]
    zf, zt = lp.LIB_FLOOR, lp.LIB_TOP

    # --- главный (восточный) фасад ---
    op = Openings(pan)
    fr = edge_frame(P, 0)
    ax = s_of(fr, 0.0, 0.0)
    rd = lp.LIB_RECESS
    z0, z1, ww = lp.LIB_WIN2
    for d, w in lp.LIB_BAYS:
        for sg in ((1,) if d == 0 else (-1, 1)):
            s = ax + sg * d
            cut_box(op, fr, s - w / 2, s + w / 2, zf, zt, rd)
            pane(pan, fr, s, ww, z0, z1, -rd + 0.02, bars=(-ww / 6, ww / 6), transom=z1 - 0.7)
            pan.add(fr, bk.rect(s - ww / 2 - 0.1, s + ww / 2 + 0.1, z0 - 0.15, z0), -rd + 0.12, "wall")
            if d == 0:                                        # парадный вход и фрамуга над ним
                dw, dt = lp.LIB_DOOR
                pan.add(fr, bk.rect(s - dw / 2, s + dw / 2, zf, dt), -rd + 0.02, "dark")
                pane(pan, fr, s, dw, dt + 0.15, 4.4, -rd + 0.02, bars=(0.0,))
            else:                                             # парные окна 1-го этажа
                a, b, w1, off = lp.LIB_WIN1
                for o in (-off, off):
                    pane(pan, fr, s + o, w1, a, b, -rd + 0.02, transom=b - 0.5)
    pm = (lp.LIB_PIERS[0] + lp.LIB_PIERS[1]) / 2
    for sg in (-1, 1):
        s = ax + sg * pm                                      # выемка большой лопатки (в плане — полукруг, здесь ниша)
        cut_box(op, fr, s - 0.3, s + 0.3, zf + 0.6, zt - 0.4, 0.3)
        s = ax + sg * lp.LIB_FALSE[0]                         # ложное окно пилона с полочкой
        hw = lp.LIB_FALSE[1] / 2
        cut_box(op, fr, s - hw, s + hw, lp.LIB_FALSE[2], lp.LIB_FALSE[3], 0.3)
        parts.append(bk.extrude("shelf", fr, bk.rect(s - hw - 0.12, s + hw + 0.12, lp.LIB_FALSE[2] - 0.15,
                                                     lp.LIB_FALSE[2]), -0.3, 0.12, M["wall"]))
        for a, b in ((lp.LIB_PYLON, lp.LIB_PYLON + 1.0), (lp.LIB_W - 1.0, lp.LIB_W)):    # лопатки пилона
            s0, s1 = sorted((ax + sg * a, ax + sg * b))
            parts.append(bk.extrude("lopatka", fr, bk.rect(s0, s1, zf, zt), -0.02, 0.12, M["wall"]))

    # --- боковые фасады 2-этажного объёма (одинаковы) ---
    for i in (1, 3):
        fs = edge_frame(P, i)
        us = P[i][0]
        for v in lp.LIB_SIDE_NICHES:
            s = s_of(fs, us, v)
            cut_box(op, fs, s - 0.9, s + 0.9, zf, zt, 0.35)
            pane(pan, fs, s, 1.3, 5.2, 7.9, -0.33, bars=(0.0,), transom=7.2)
            pane(pan, fs, s, 1.3, 1.9, 3.6, -0.33, bars=(0.0,))
        s = s_of(fs, us, lp.LIB_STAIR)
        op.window(fs, s, 1.3, 4.3, 7.9)
        op.door(fs, s, 1.2, zf, 3.2)
        s = s_of(fs, us, lp.LIB_SIDE_BIG)
        op.window(fs, s, 2.6, 1.9, 3.6)
        for v in lp.LIB_HEX[:2]:
            pan.add(fs, polygon(s_of(fs, us, v), lp.LIB_HEX[2], lp.LIB_HEX[3] / 2, 6), 0.015, "glass")
    parts += op.apply(take_body(parts, "front"))
    parts.append(band(P, zt, zt + 0.3, 0.08))                 # архитрав
    parts.append(band(P, 9.35, 9.6, 0.2))                     # пояс дентикул (одной тягой)

    # --- крыльцо на три стороны ---
    depth, pw = lp.LIB_PORCH
    parts.append(bk.extrude("porch", fr, bk.rect(ax - pw, ax + pw, h.base_z + 1.0, zf), -0.05, depth, M["stone"]))
    parts.append(bk.extrude("porch_step", fr, bk.rect(ax - pw - 0.6, ax + pw + 0.6, h.base_z + 1.0, zf / 2), -0.05,
                            depth + 0.6, M["stone"]))

    # --- двухсветный объём: западный фасад ---
    op2 = Openings(pan)
    fw = edge_frame(Q, 0)
    aw = s_of(fw, 0.0, lp.LIB_L)
    corner, niche = lp.LIB_WEST
    mid_half = lp.LIB_W - corner - niche
    for sg in (-1, 1):
        s = aw + sg * (mid_half + niche / 2)
        cut_box(op2, fw, s - niche / 2, s + niche / 2, zf, 6.4, 0.45)
        parts.append(bk.extrude("frieze", fw, bk.rect(s - niche / 2, s + niche / 2, 6.55, 6.8), -0.45, 0.08,
                                M["wall"]))
        oc, dia, zc = lp.LIB_OCULI
        pan.add(fw, polygon(aw + sg * oc, zc, dia / 2, 12), 0.015, "glass")
    for d in lp.LIB_WEST_DOORS:
        s = aw + d
        op2.door(fw, s, 1.4, zf, 3.2)
        parts.append(bk.extrude("sandrik", fw, bk.rect(s - 0.95, s + 0.95, 3.35, 3.55), -0.02, 0.18, M["wall"]))
    lw, l0, ls = lp.LIB_LUNETTE
    pan.add(fw, bk.arch(aw, lw, l0, ls, n=8), 0.015, "dark")
    pan.add(fw, bk.arch_frame(aw, lw, l0, ls, 0.18, n=8), 0.04, "wall")
    # --- двухсветный объём: боковые фасады — лопатки и ложные окна ---
    for i in (1, 3):
        fs = edge_frame(Q, i)
        L = fs.length
        for k in range(lp.LIB_HALL_BAYS):
            s = L * (2 * k + 1) / (2 * lp.LIB_HALL_BAYS)
            cut_box(op2, fs, s - 1.4, s + 1.4, 1.8, 6.6, 0.25)
    parts += op2.apply(take_body(parts, "halls"))


# ---------- пл. Ленина, 1: Дом культуры профсоюзов ----------

def extras_dkp(h, pan, parts):
    """Портик на всю высоту: лоджия за колоннами (окна, двери в трёх средних пролётах), 4 колонны, пол и ступени
    (a02, d02)."""
    main = next(b for b in h.blocks if b.name == "main")
    P = [tuple(p) for p in main.quad]
    fr = edge_frame(P, 0)
    ax = s_of(fr, 0.0, 0.0)
    R, _span, anta, depth = lp.DKP_PORTICO
    dia, zb, za, cv = lp.DKP_COL
    inner = R - anta
    op = Openings(pan)
    cut_box(op, fr, ax - inner, ax + inner, zb, za, depth)
    parts += op.apply(take_body(parts, "main"))
    c0, c1 = lp.DKP_COLUMNS
    edges = (-inner, -c1, -c0, c0, c1, inner)
    for k in range(5):
        a, b = edges[k], edges[k + 1]
        n = lp.DKP_LOGGIA_AXES
        door = 1 <= k <= 3
        for j in range(n):
            s = ax + a + (b - a) * (2 * j + 1) / (2 * n)
            for r, (z0, z1, _) in enumerate(lp.DKP_ROWS):
                if r == 0 and door:
                    continue
                pane(pan, fr, s, 1.4, z0, z1, -depth + 0.02, bars=(0.0,), transom=z1 - 0.6)
        if door:
            s = ax + (a + b) / 2
            pan.add(fr, bk.rect(s - 1.1, s + 1.1, zb, 2.9), -depth + 0.02, "dark")
            pane(pan, fr, s, 2.2, 3.05, 3.7, -depth + 0.02, bars=(0.0,))
    r = dia / 2
    for d in (c0, c1):
        for sg in (-1, 1):
            u = sg * d
            parts.append(bk.box("col_base", u - r - 0.1, u + r + 0.1, cv - r - 0.1, cv + r + 0.1, zb, zb + 0.4,
                                M["wall"]))
            parts.append(bk.lathe("column", (u, cv), [(r, zb + 0.4), (r, zb + 4.0), (r * 0.88, za - 0.5),
                                                      (r * 1.12, za - 0.2), (r * 1.12, za - 0.1)], M["wall"], seg=12))
            parts.append(bk.box("col_cap", u - r - 0.14, u + r + 0.14, cv - r - 0.14, cv + r + 0.14, za - 0.12, za,
                                M["wall"]))
    parts.append(bk.extrude("portico_floor", fr, bk.rect(ax - R, ax + R, h.base_z + 0.8, zb), -depth, 1.0,
                            M["stone"]))
    parts.append(bk.extrude("steps", fr, bk.rect(ax - R + 1.0, ax + R - 1.0, h.base_z + 0.8, zb / 2), 0.9, 1.8,
                            M["stone"]))


EXTRAS = {"Library": extras_library, "DKP": extras_dkp}

# общий вид для сверки: глаз и цель (u, v, z) в осях здания
OVERVIEW = {"Library": {"overview": ((-45.0, -45.0, 22.0), (0.0, 20.0, 5.0)),
                        "west": ((40.0, 95.0, 18.0), (0.0, 30.0, 5.0))},
            "DKP": {"overview": ((-40.0, -70.0, 25.0), (0.0, 18.0, 6.0)),
                    "north": ((45.0, 110.0, 35.0), (0.0, 25.0, 5.0))}}


def build(h):
    bk.reset_scene()
    bk.use_colors(krom_plan.COLORS)
    pan, parts = Panels(), []
    for b in h.blocks:
        build_block(h, b, pan, parts)
    EXTRAS[h.key](h, pan, parts)
    objs = parts + pan.objects()
    obj = bk.join(objs, h.asset)
    bk.box_uv(obj)
    me = obj.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    print(f"[lenina] {h.name}: {len(objs)} тел → {h.asset}: {len(me.vertices)} вершин, {len(me.polygons)} граней "
          f"({tris} треугольников), слоты {[m.name for m in me.materials]}")
    bk.export_glb(obj, h.asset)
    bk.box("ground", -400, 400, -400, 400, -0.05, 0.0, bk.material("ground", (0.12, 0.16, 0.08)))
    bk.PREVIEW_DIR = RENDER_DIR
    for view, (eye, tgt) in OVERVIEW[h.key].items():
        bk.render_preview(f"lenina_{h.key}_{view}", eye=(eye[0], -eye[1], eye[2]), target=(tgt[0], -tgt[1], tgt[2]),
                          size=(1200, 700), lens=35)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    todo = [h for h in lp.HOUSES if not argv or h.key in argv]
    if not todo:
        raise SystemExit(f"[lenina] нет здания {argv}; есть: {[h.key for h in lp.HOUSES]}")
    for h in todo:
        build(h)


main()
