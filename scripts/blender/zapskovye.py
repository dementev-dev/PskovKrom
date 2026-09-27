"""zapskovye.py — герои партии 1 (D-043) скриптом Blender по scripts/zapskovye_plan.py (D-018): Советская
набережная, 4, 6, 1/2 (дом Русакова) и ул. Леона Поземского, 5.

    python scripts/bl_run.py scripts/blender/zapskovye.py                 # все четыре
    python scripts/bl_run.py scripts/blender/zapskovye.py -- Nab4         # один (Nab4, Nab6, Rusakov, Pozemskogo5)

Выгрузка — build/blender/<asset>.glb (в UE ставит scripts/heroes_krom.py после подключения плана в
krom_plan.buildings()), превью с камер фото Commons — build/zapskovye/renders/zapskovye_<ключ>_<фото>.png; лист
сверки — build/zapskovye/compare.py → build/zapskovye_refs/compare.jpg. Размеры, высоты и источники — в плане.

Дом собирается из блоков плана одним генератором: стены-призма (1-й этаж может быть другого цвета), проёмы фасадов
с фото — вырез и стекло-плоскость, фасады без фото (гипотеза) — окна-плоскости; цоколь, тяги, карниз; кровля
вальмовая, двускатная, с фронтоном, мансардная или односкатная; трубы. Особое у каждого дома (фронтоны с люнетом,
«кокошники», люкарны, балконы, арки проездов, башня) — в функциях extras_<ключ>. Деталь дешёвая: дома видны
с 75–250 м (≤12 тыс. треугольников на дом). Материалы — только ключи krom_plan.COLORS (нужных «кирпич», «крем»,
«голубой», «охра» нет — ближайшие, см. план). Оси (u, v, z) — как в плане; в Blender точка (u, −v, z).
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402
import krom_plan  # noqa: E402
import zapskovye_plan as zp  # noqa: E402
from pskovgu_plan import offset  # noqa: E402
from bl_krom import M  # noqa: E402

RENDER_DIR = os.path.join(bk.REPO, "build", "zapskovye", "renders")
CHIMNEY = {"Nab4": "wall", "Nab6": "pink", "Rusakov": "wall", "Pozemskogo5": "pink"}   # кирпичные трубы — pink


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


# ---------- особое у каждого дома ----------

def extras_nab4(h, pan, parts):
    """«Кокошники» на мансардах крыльев розового дома, люнет во фронтоне дома Кузьменковых, дверь на балкон по оси
    фронтона, балконы связки и дома Кузьменковых (c20, c01, c03)."""
    fr, pink = front_frame(h, "pink")
    z0, ztop = zp.N4_DORMER_Z
    for u, w in zp.N4_DORMERS:
        s = pink.quad[0][0] - u
        zs = ztop - w / 2
        parts.append(bk.extrude("kokoshnik", fr, bk.arch(s, w, pink.z_eave - 0.05, zs, n=10), -2.0, 0.05, M["pink"]))
        parts.append(bk.extrude("kokoshnik_cap", fr, bk.arch_frame(s, w, pink.z_eave + 0.3, zs, 0.18, n=10), -2.1,
                                0.2, M["green"]))
        pan.add(bk.Frame(fr.p(0, 0, 0.05)[:2], fr.t, fr.n), bk.arch(s, 1.7, z0, zs, n=10), 0.01, "glass")
    fm, pmid = front_frame(h, "pink_mid")
    u, dia, zc = zp.N4_OCULUS
    s = pmid.quad[0][0] - u
    ring = [(s + dia / 2 * math.cos(math.pi * k / 6), zc + dia / 2 * math.sin(math.pi * k / 6)) for k in range(12)]
    pan.add(fm, ring, 0.06, "glass")
    fb, blue = front_frame(h, "blue")
    u, w, z = zp.N4_LUNETTE
    s = blue.quad[0][0] - u
    pan.add(fb, bk.arch(s, w, z, z, n=10), 0.03, "glass")
    pan.add(fb, bk.arch_frame(s, w, z, z, 0.14, n=10), 0.035, "wall")
    u, w, d0, d1 = zp.N4_BLUE_DOOR
    s = blue.quad[0][0] - u
    op = Openings(pan)
    op.door(fb, s, w, d0, d1)
    pan.add(fb, bk.rect(s - w / 2 - 0.2, s + w / 2 + 0.2, d1 + 0.1, d1 + 0.25), 0.1, "wall")
    parts.append(bk.extrude("door_tri", fb, [(s - w / 2 - 0.25, d1 + 0.25), (s + w / 2 + 0.25, d1 + 0.25),
                                             (s, d1 + 0.85)], -0.02, 0.12, M["wall"]))
    body = next(o for o in parts if o.name.startswith("walls_blue"))
    parts.remove(body)
    parts += op.apply(body)
    fl, link = front_frame(h, "link")
    for u, z, w in zp.N4_BALCONIES:
        if u == -12.64:
            balcony(parts, pan, fb, blue.quad[0][0] - u, z, w, depth=0.7)
        else:
            balcony(parts, pan, fl, link.quad[0][0] - u, z, w, depth=1.0)


def extras_nab6(h, pan, parts):
    """Арка проезда в низком блоке, аттик кремового блока, белая круглая башня на конце дворового крыла (гип.)."""
    fr, gate = front_frame(h, "gate")
    u, w, top = zp.N6_GATE_ARCH
    s = gate.quad[0][0] - u
    op = Openings(pan)
    op.door(fr, s, w, 0.0, top, depth=1.2, poly=bk.arch(s, w, 0.0, top - w / 2, n=8))
    body = next(o for o in parts if o.name.startswith("walls_gate"))
    parts.remove(body)
    parts += op.apply(body)
    pan.add(fr, bk.arch_frame(s, w, top - w / 2, top - w / 2, 0.25, n=8), 0.02, "wall")
    f5, s5 = front_frame(h, "s5_cream")
    z0, z1 = zp.N6_ATTIC
    pan.add(f5, bk.rect(1.2, f5.length - 1.2, z0 + 0.4, z1 - 0.5), 0.02, "tin")        # панель аттика (c20)
    (cu, cv), r, ze, rise = zp.N6_TOWER
    parts.append(bk.lathe("tower", (cu, cv), [(r, h.base_z), (r, ze - 0.4), (r + 0.25, ze - 0.4), (r + 0.25, ze)],
                          M["wall"], seg=16, smooth=False))
    parts.append(bk.lathe("tower_roof", (cu, cv), [(r + 0.4, ze), (0.0, ze + rise)], M["tin"], seg=16, smooth=False))
    for k in range(5):                                        # окна башни наружу, гип.
        a = math.radians(-40 + 20 * k) + math.atan2(-1.0, 0.0)
        frt = bk.Frame.radial((cu, cv), r, a)
        for z0, z1, _ in zp.N6_ROWS_BACK:
            glass(pan, frt, 0.0, 0.9, z0, z1)


def extras_rusakov(h, pan, parts):
    """Люкарны мансарды на реку (c07): стенка-щипец с окном и двускатной кровлей."""
    fr, front = front_frame(h, "front")
    z0, z1 = zp.RUS_DORMER_Z
    ze = front.z_eave
    for u, w in zp.RUS_DORMERS:
        s = front.quad[0][0] - u
        d_face = -0.45                                        # стенка люкарны — на нижнем скате мансарды
        prof = [(s - w / 2, ze - 0.1), (s + w / 2, ze - 0.1), (s + w / 2, z1 + 0.1), (s, z1 + 0.65),
                (s - w / 2, z1 + 0.1)]
        parts.append(bk.extrude("dormer", fr, prof, -2.2, d_face, M["wall"]))
        pan.add(fr, bk.rect(s - 0.6, s + 0.6, z0, z1), d_face + 0.01, "glass")
        parts.append(bk.extrude("dormer_roof", fr, [(s - w / 2 - 0.2, z1 + 0.02), (s, z1 + 0.78), (s + w / 2 + 0.2,
                                                     z1 + 0.02), (s + w / 2 + 0.2, z1 - 0.1), (s, z1 + 0.66),
                                                    (s - w / 2 - 0.2, z1 - 0.1)], -2.3, d_face + 0.15, M["tin"]))


def extras_pozemskogo5(h, pan, parts):
    """Сквозной проезд с балконной дверью над ним и полуфронтоном, балконы, лопатки главного фасада (S-151)."""
    fr, main = front_frame(h, "main")
    u, w, top = zp.P5_ARCH
    s = main.quad[0][0] - u
    op = Openings(pan)
    op.door(fr, s, w, 0.0, top, depth=10.0, poly=bk.arch(s, w, 0.0, top - w * 0.3, n=8))   # проезд насквозь
    op.door(fr, s, 1.2, 5.0, 7.3)                                                             # балконная дверь
    body = next(o for o in parts if o.name.startswith("walls_main"))
    parts.remove(body)
    parts += op.apply(body)
    for u, z, w in zp.P5_BALCONIES:
        balcony(parts, pan, fr, main.quad[0][0] - u, z, w, depth=0.8)
    for u in zp.P5_PILASTERS:
        s = main.quad[0][0] - u
        parts.append(bk.extrude("lopatka", fr, bk.rect(s - 0.3, s + 0.3, main.z_plinth, main.z_eave - 0.5), -0.02,
                                0.1, M["wall"]))
    a, b, rise = zp.P5_HALF_PEDIMENT
    s0, s1 = main.quad[0][0] - b, main.quad[0][0] - a
    ze = main.z_eave
    parts.append(bk.extrude("half_pediment", fr, [(s0, ze - 0.05), (s1, ze - 0.05), (s1, ze + rise)], -0.3, 0.1,
                            M["stone"]))
    parts.append(bk.extrude("half_pediment_cornice", fr, [(s0 - 0.2, ze), (s1 + 0.1, ze + rise + 0.2),
                                                          (s1 + 0.1, ze + rise), (s0, ze - 0.1)], -0.3, 0.3,
                            M["wall"]))


EXTRAS = {"Nab4": extras_nab4, "Nab6": extras_nab6, "Rusakov": extras_rusakov, "Pozemskogo5": extras_pozemskogo5}


def build_house(h):
    pan, parts = Panels(), []
    for b in h.blocks:
        build_block(h, b, pan, parts)
    EXTRAS[h.key](h, pan, parts)
    return parts + pan.objects()


# ---------- превью с камер фото ----------

# Камеры фото (build/zapskovye/fit_*.py; перевод в оси дома — fitlib.to_axes): глаз (u, v, z) в осях дома, азимут
# взгляда от оси u к оси v, наклон, крен (°), фокусное в пикселях кадра, главная точка — центр кадра, размер —
# как у файла в build/zapskovye_refs. Нуль высот камеры — нуль дома (набережная / тротуар).
VIEWS = {}   # заполняется из build/zapskovye/views.json (python build/zapskovye/views.py)


def load_views():
    import json
    path = os.path.join(bk.REPO, "build", "zapskovye", "views.json")
    if os.path.exists(path):
        VIEWS.update(json.load(open(path, encoding="utf-8")))


OVERVIEW = {"Nab4": ((-60.0, -70.0, 40.0), (0.0, 12.0, 6.0)), "Nab6": ((-70.0, -60.0, 45.0), (0.0, 20.0, 6.0)),
            "Rusakov": ((-45.0, -45.0, 30.0), (0.0, 12.0, 6.0)),
            "Pozemskogo5": ((20.0, -40.0, 30.0), (-12.0, 10.0, 3.0))}


def render_view(name, eye, yaw, pitch, roll, f, cx, cy, size, scale=0.5):
    """Превью Workbench с камерой фото: сдвиг объектива — главная точка (cx, cy), крен — поворот вокруг взгляда."""
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
    print(f"[zapskovye] preview {s.render.filepath}")


def build(h):
    bk.reset_scene()
    bk.use_colors(krom_plan.COLORS)
    objs = build_house(h)
    obj = bk.join(objs, h.asset)
    bk.box_uv(obj)
    me = obj.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    print(f"[zapskovye] {h.name}: {len(objs)} тел → {h.asset}: {len(me.vertices)} вершин, {len(me.polygons)} граней "
          f"({tris} треугольников), слоты {[m.name for m in me.materials]}")
    bk.export_glb(obj, h.asset)
    earth = bk.material("ground", (0.12, 0.16, 0.08))
    low = min([cam["eye"][2] for cam in VIEWS.get(h.key, {}).values()] + [1.0])
    if low < 0.5:        # камера на берегу ниже набережной: набережная — уступ до фасада, дальше — земля ниже глаза
        bk.box("embankment", -400, 400, -1.5, 400, low - 2.0, 0.0, earth)
        bk.box("ground", -400, 400, -400, -1.5, low - 2.0, low - 1.6, earth)
    else:
        bk.box("ground", -400, 400, -400, 400, -0.05, 0.0, earth)
    for view, cam in VIEWS.get(h.key, {}).items():
        render_view(f"zapskovye_{h.key}_{view}", **cam)
    bk.PREVIEW_DIR = RENDER_DIR
    eye, tgt = OVERVIEW[h.key]
    bk.render_preview(f"zapskovye_{h.key}_overview", eye=(eye[0], -eye[1], eye[2]), target=(tgt[0], -tgt[1], tgt[2]),
                      size=(1200, 700), lens=35)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    todo = [h for h in zp.HOUSES if not argv or h.key in argv]
    if not todo:
        raise SystemExit(f"[zapskovye] нет дома {argv}; есть: {[h.key for h in zp.HOUSES]}")
    load_views()
    for h in todo:
        build(h)


main()
