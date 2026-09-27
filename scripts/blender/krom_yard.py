"""krom_yard.py — Дом причта, Пороховые погреба, Консистория: простые герои скриптом Blender по yard_plan (D-018, D-036).

    python scripts/bl_run.py scripts/blender/krom_yard.py                 # все три
    python scripts/bl_run.py scripts/blender/krom_yard.py -- Pricht       # одно (ключ: Pricht, Powder, Consistory)

Выгрузка — build/blender/<asset>.glb (в UE ставит scripts/heroes_krom.py), превью с точек фото Commons (S-70) —
build/yard/renders/yard_<key>_<вид>.png. Габариты, высоты, оси и контуры — в scripts/yard_plan.py, источники там.
Здесь — детали «на глаз» по фото S-70: ритм и размер окон, наличники, сандрики, пояса, карнизы, слуховые окна, трубы,
крыльца. Оси здания (u, v, z) — как в yard_plan; в Blender точка (u, −v, z). Материалы — слоты по ключам
krom_plan.COLORS, новых нет: кирпичные трубы погребов — «stone», стены Консистории — «wall» (бледно-голубые
на фото 2013 г., белые на аэрофото). Сверка «фото / модель» — build/yard/compare.py → build/yard_refs/compare.jpg.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402
import krom_plan  # noqa: E402
import yard_plan  # noqa: E402
from bl_krom import M  # noqa: E402

RENDER_DIR = os.path.join(bk.REPO, "build", "yard", "renders")
BASE_Z = {"Pricht": -0.6, "Powder": -1.2, "Consistory": -4.0}   # низ стен: земля под контуром ниже нуля здания


# ---------- общие детали ----------

def face(a, b, inside):
    """Фасад по отрезку a–b: s идёт слева направо, если смотреть снаружи (оси u, v — «левые», как x, y плана)."""
    fr = bk.Frame.between(a, b, inside)
    right = (fr.n[1], -fr.n[0])
    if (b[0] - a[0]) * right[0] + (b[1] - a[1]) * right[1] < 0:
        fr = bk.Frame.between(b, a, inside)
    return fr


def rect_faces(u0, u1, v0, v1):
    c = ((u0 + u1) / 2, (v0 + v1) / 2)
    return {"u-": face((u0, v0), (u0, v1), c), "u+": face((u1, v0), (u1, v1), c),
            "v-": face((u0, v0), (u1, v0), c), "v+": face((u0, v1), (u1, v1), c)}


def offset(poly, d):
    """Многоугольник, раздвинутый наружу на d (стороны сдвигаются параллельно; углы — пересечения)."""
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


def ring_band(poly, z0, z1, proud, key="wall"):
    """Пояс, карниз или цоколь вокруг контура poly (u, v): тело шире стен на proud."""
    return bk.prism("band", offset(poly, proud), z0, z1, M[key])


def hexa(name, pts, mat):
    """Шестигранник по 8 точкам (u, v, z): низ 0–3, верх 4–7 в том же порядке."""
    return bk.mesh(name, pts, [[0, 1, 2, 3], [4, 5, 6, 7]] + [[i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i] for i in range(4)],
                   mat)


def quad_hip(name, P, z, rise, mat, over=0.45, thick=0.15, ridge=None):
    """Вальмовая кровля над выпуклым четырёхугольником P [(u, v)] с карнизом на z: конёк — по оси между серединами
    двух коротких сторон (вальм), на высоте z + rise; ridge — длина конька (по умолчанию вальмы под 45° в плане).
    Свес over — по плоскостям скатов."""
    P = [tuple(p) for p in P]
    L = [math.dist(P[k], P[(k + 1) % 4]) for k in range(4)]
    i = 0 if L[0] + L[2] <= L[1] + L[3] else 1
    a0, a1, c0, c1 = (P[(i + k) % 4] for k in range(4))
    ma, mc = ((a0[0] + a1[0]) / 2, (a0[1] + a1[1]) / 2), ((c0[0] + c1[0]) / 2, (c0[1] + c1[1]) / 2)
    D = math.dist(ma, mc)
    e = ((mc[0] - ma[0]) / D, (mc[1] - ma[1]) / D)
    da, dc = (L[i] / 2, L[(i + 2) % 4] / 2) if ridge is None else ((D - ridge) / 2,) * 2
    ra = (ma[0] + e[0] * da, ma[1] + e[1] * da, z + rise)
    rc = (mc[0] - e[0] * dc, mc[1] - e[1] * dc, z + rise)
    slope = rise / ((L[i] + L[(i + 2) % 4]) / 4)          # скаты вдоль конька: подъём на полуширину
    Q = offset([a0, a1, c0, c1], over)
    ze = z - over * slope
    top = [(q[0], q[1], ze) for q in Q]
    bot = [(q[0], q[1], ze - thick) for q in Q]
    verts = top + [ra, rc] + bot
    faces = [[0, 1, 4], [1, 2, 5, 4], [2, 3, 5], [3, 0, 4, 5], [6, 7, 8, 9]] + \
            [[k, (k + 1) % 4, 6 + (k + 1) % 4, 6 + k] for k in range(4)]
    return bk.mesh(name, verts, faces, mat)


def gable(name, fr, s0, s1, ze, zr, d0, d1, mat, over=0.35, thick=0.16):
    """Двускатная кровля: сечение в плоскости фасада fr (скаты от s0 и s1 к коньку на zr, карниз на ze),
    протянутое по нормали от d0 до d1 (d1 > 0 — свес над фронтоном)."""
    sm, hw = (s0 + s1) / 2, (s1 - s0) / 2
    slope = (zr - ze) / hw
    zo = ze - over * slope
    th = thick * math.hypot(1, slope)
    prof = [(s0 - over, zo), (sm, zr), (s1 + over, zo), (s1 + over, zo - thick), (sm, zr - th), (s0 - over, zo - thick)]
    return bk.extrude(name, fr, prof, d0, d1, mat)


def tympanum(fr, s0, s1, ze, zr, d0=-0.6, key="wall"):
    """Щипец (тимпан) над карнизом: треугольник в плоскости фасада, чуть ниже кровли."""
    return bk.extrude("tympanum", fr, [(s0, ze - 0.05), (s1, ze - 0.05), ((s0 + s1) / 2, zr - 0.12)], d0, 0.0, M[key])


def half_disc(sc, r, z0, n=16):
    """Полукруг над хордой на высоте z0 (люнет)."""
    return [(sc + r * math.cos(math.pi * k / n), z0 + r * math.sin(math.pi * k / n)) for k in range(n + 1)]


def chimney(u, v, z0, z1, a=0.8, b=0.6, key="wall", cap="roof"):
    return [bk.box("chimney", u - a / 2, u + a / 2, v - b / 2, v + b / 2, z0, z1, M[key]),
            bk.box("chimney_cap", u - a / 2 - 0.07, u + a / 2 + 0.07, v - b / 2 - 0.07, v + b / 2 + 0.07, z1, z1 + 0.1,
                   M[cap])]


def dormer(u, v, n, z0, w, h, rise, depth, body="wall", roof="tin", louvre=0.55):
    """Слуховое окно: передняя стенка в точке (u, v) смотрит по n (в плане), низ z0 — в кровле; тело уходит
    в кровлю на depth, сверху двускатная крыша, спереди — жалюзи (стекло)."""
    fr = bk.Frame((u, v), (n[1], -n[0]), n)
    parts = [bk.extrude("dormer", fr, bk.rect(-w / 2, w / 2, z0, z0 + h), -depth, 0.0, M[body]),
             gable("dormer_roof", fr, -w / 2, w / 2, z0 + h, z0 + h + rise, -depth, 0.12, M[roof], over=0.12, thick=0.06)]
    zl = z0 + h - louvre - 0.12
    parts.append(bk.extrude("louvre", fr, bk.rect(-louvre / 2, louvre / 2, zl, zl + louvre), -0.02, 0.02, M["glass"]))
    return parts


class Openings:
    """Проёмы одного тела: вырезы копятся и вычитаются одной булевой операцией (вырезы не пересекаются);
    стёкла, переплёты, наличники, подоконники, сандрики и двери — отдельные тела."""

    def __init__(self):
        self.cutters, self.parts = [], []

    def cut(self, fr, poly, depth):
        self.cutters.append(bk.extrude("cut", fr, poly, -depth, 0.6, M["wall"]))

    def window(self, fr, s, w, z0, z1, depth=0.25, frame=0.13, sill=True, hood=None, cross=True, blind=False):
        """Прямоугольное окно: середина s, ширина w, низ z0, верх z1. blind — глухая ниша (фальшивое окно).
        hood: None | "shelf" (сандрик-полочка) | "tri" (треугольный фронтончик)."""
        if blind:
            self.cut(fr, bk.rect(s - w / 2, s + w / 2, z0, z1), 0.06)
        else:
            self.cut(fr, bk.rect(s - w / 2, s + w / 2, z0, z1), depth)
            self.parts.append(bk.extrude("glass", fr, bk.rect(s - w / 2 + 0.02, s + w / 2 - 0.02, z0 + 0.02, z1 - 0.02),
                                         -depth - 0.05, -depth + 0.02, M["glass"]))
            if cross:                                   # белый переплёт: стойка и фрамуга
                zt = z1 - (z1 - z0) * 0.3
                for poly in (bk.rect(s - 0.03, s + 0.03, z0, z1), bk.rect(s - w / 2, s + w / 2, zt - 0.03, zt + 0.03)):
                    self.parts.append(bk.extrude("sash", fr, poly, -depth + 0.02, -depth + 0.06, M["wall"]))
        f = frame
        if f:
            for poly in (bk.rect(s - w / 2 - f, s - w / 2, z0, z1 + f), bk.rect(s + w / 2, s + w / 2 + f, z0, z1 + f),
                         bk.rect(s - w / 2 - f, s + w / 2 + f, z1, z1 + f)):
                self.parts.append(bk.extrude("nalichnik", fr, poly, -0.02, 0.05, M["wall"]))
        if sill:
            self.parts.append(bk.extrude("sill", fr, bk.rect(s - w / 2 - f - 0.05, s + w / 2 + f + 0.05, z0 - 0.1, z0),
                                         -0.02, 0.1, M["wall"]))
        self.hood(fr, s, w + 2 * f, z1 + f, hood)

    def hood(self, fr, s, w, z, kind):
        if kind in ("shelf", "tri"):
            self.parts.append(bk.extrude("sandrik", fr, bk.rect(s - w / 2 - 0.1, s + w / 2 + 0.1, z + 0.06, z + 0.18),
                                         -0.02, 0.15, M["wall"]))
        if kind == "tri":
            self.parts.append(bk.extrude("fronton", fr, [(s - w / 2 - 0.08, z + 0.18), (s + w / 2 + 0.08, z + 0.18),
                                                         (s, z + 0.62)], -0.02, 0.12, M["wall"]))

    def door(self, fr, s, w, z0, z1, depth=0.3, frame=0.13, key="dark", arch=False):
        poly = bk.arch(s, w, z0, z1 - w / 2) if arch else bk.rect(s - w / 2, s + w / 2, z0, z1)
        self.cut(fr, poly, depth)
        self.parts.append(bk.extrude("door", fr, poly, -depth - 0.04, -depth + 0.02, M[key]))
        if frame and not arch:
            for p in (bk.rect(s - w / 2 - frame, s - w / 2, z0, z1 + frame), bk.rect(s + w / 2, s + w / 2 + frame, z0, z1 + frame),
                      bk.rect(s - w / 2 - frame, s + w / 2 + frame, z1, z1 + frame)):
                self.parts.append(bk.extrude("door_frame", fr, p, -0.02, 0.05, M["wall"]))

    def pilaster(self, fr, s, z0, z1, w=0.24, proud=0.07):
        self.parts.append(bk.extrude("pilaster", fr, bk.rect(s - w / 2, s + w / 2, z0, z1), -0.02, proud, M["wall"]))

    def apply(self, body):
        return [bk.cut(body, self.cutters)] + self.parts


def steps(fr, s, w, z_top, n=3, tread=0.35, key="stone"):
    """Крыльцо-ступени перед дверью: n ступеней от z_top вниз до земли."""
    rise = z_top / n
    return [bk.extrude("step", fr, bk.rect(s - w / 2, s + w / 2, -0.3, z_top - k * rise), 0.0, (k + 1) * tread, M[key])
            for k in range(n)]


def canopy(fr, s, w, z, out=1.1, drop=0.35, key="tin"):
    """Зонт над входом на кронштейнах: наклонный лист от стены наружу."""
    pts = [fr.p(s - w / 2, z, 0.0), fr.p(s + w / 2, z, 0.0), fr.p(s + w / 2, z - drop, out), fr.p(s - w / 2, z - drop, out)]
    return [hexa("canopy", pts + [(u, v, zz + 0.07) for u, v, zz in pts], M[key])]


# ---------- Дом причта ----------

def pricht(c):
    """Два тела: главный объём и северная часть — на метр ниже (фото prich_17, prich_05). Цоколь, пояс, карниз; окна
    по фото S-70: юг — 8 осей (сандрики через одно окно), запад и восток главного объёма — 5 осей с глухими окнами,
    северная часть — 2 оси и вход; север — 7 осей, из них 5 под фронтоном."""
    h, z = c.side / 2, BASE_Z[c.key]
    v1 = c.v_split
    ze, zn = c.z_eave, c.z_eave_north
    main = bk.box("walls_main", -h, h, v1, h, z, ze, M["wall"])
    north = bk.box("walls_north", -h, h, -h, v1 + 0.3, z, zn, M["wall"])
    om, on, parts = Openings(), Openings(), []
    fr = rect_faces(-h, h, -h, h)
    (l0, l1), (u0, u1) = c.low, c.up
    dn = v1 + h                                          # глубина северной части
    W, ZD = 0.95, 0.8                                    # ширина окон (фото prich_08, px_04), порог входов (3 ступени)
    vent = dict(depth=0.15, frame=0, sill=False, cross=False)
    # юг (v+): s с запада
    p = c.side / 8
    for k in range(8):
        s = p / 2 + k * p
        om.window(fr["v+"], s, W, u0, u1, hood="shelf" if k % 2 else None)
        om.window(fr["v+"], s, W, l0, l1)
        om.window(fr["v+"], s, 0.6, 0.08, 0.4, **vent)                                 # продухи цоколя
    # запад (u−): s с севера; восток (u+): s с юга — узор главного объёма зеркален (фото prich_17, prich_05)
    bays = [dn + 1.5 + 3.0 * k for k in range(5)]
    for side, order in (("u-", bays), ("u+", [c.side - s for s in bays])):
        for k, s in enumerate(order):
            om.window(fr[side], s, W, u0, u1, blind=k in (2, 3))
            om.window(fr[side], s, W, l0, l1, blind=k >= 2)
            if k < 2:
                om.window(fr[side], s, 0.6, 0.08, 0.4, **vent)
    un = u1 - 0.3                                        # окна 2-го этажа северной части ниже (prich_17)
    w = fr["u-"]                                          # северная часть с запада: 2 окна, вход под зонтом
    for s in (2.2, 5.3):
        on.window(w, s, W, u0, un)
    on.window(w, 2.2, W, l0, l1)
    on.door(w, 7.2, 1.4, ZD, ZD + 2.3)
    parts += canopy(w, 7.2, 2.0, ZD + 2.7) + steps(w, 7.2, 2.2, ZD)
    e = fr["u+"]                                          # северная часть с востока: двери внизу и наверху, лестница
    s_door = c.side - dn + 1.25                           # у стыка с главным объёмом (s с юга)
    on.door(e, s_door, 1.3, ZD, ZD + 2.3, key="wall")
    on.door(e, s_door, 1.0, u0 - 0.35, un)
    on.window(e, c.side - 2.9, W, u0, un)
    on.window(e, c.side - 2.9, W, l0, l1)
    parts += steps(e, s_door, 1.8, ZD, n=3)
    parts += stair(c, s_door)
    # север (v−): s с востока; 7 осей: боковые части по окну, под фронтоном 5 узких; вход — вторая ось от востока
    pw, _ = c.pediment
    sp = (c.side - pw) / 2
    axes = [sp / 2] + [sp + pw / 10 + pw / 5 * k for k in range(5)] + [c.side - sp / 2]
    n = fr["v-"]
    for k, s in enumerate(axes):
        wk = 0.8 if 1 <= k <= 5 else W
        on.window(n, s, wk, u0, un)
        if k == 2:
            on.door(n, s, 1.3, ZD, ZD + 2.3)
            parts += canopy(n, s, 1.9, ZD + 2.7) + steps(n, s, 2.1, ZD)
        else:
            on.window(n, s, wk, l0, l1)
    parts += om.apply(main) + on.apply(north)
    parts.append(bk.band(-h, h, -h, h, z, c.z_plinth, 0.05, "roof"))                 # серый цоколь
    parts.append(bk.band(-h, h, -h, h, c.z_belt[0], c.z_belt[1], 0.06))              # междуэтажный пояс
    for v0, vv1, zz in ((v1, h, ze), (-h, v1, zn)):                                   # карнизы в два уступа, под свесом
        parts.append(bk.band(-h, h, v0, vv1, zz - 0.45, zz - 0.25, 0.12))
        parts.append(bk.band(-h, h, v0, vv1, zz - 0.25, zz - 0.13, 0.24))
    return parts + pricht_roofs(c, n)


def stair(c, s_door):
    """Наружная стальная лестница на 2-й этаж у восточного фасада северной части (фото prich_05, px_04)."""
    h = c.side / 2
    v_door = h - s_door                                   # восточный фасад: s = h − v
    u0, u1 = h + 0.05, h + 1.15
    vl0, vl1 = v_door - 0.75, v_door + 0.75               # площадка у верхней двери
    zl = c.up[0] - 0.35
    v_foot = vl0 - zl * 1.05                              # марш вниз к северу
    parts = [bk.box("landing", u0, u1 + 0.2, vl0, vl1, zl - 0.12, zl, M["roof"])]
    pts = [(u0, vl0, zl - 0.35), (u1, vl0, zl - 0.35), (u1, v_foot, -0.3), (u0, v_foot, -0.3)]
    parts.append(hexa("stair", pts + [(u, v, zz + 0.3) for u, v, zz in pts], M["roof"]))
    rail = [(u1 - 0.04, vl0, zl + 0.9), (u1 + 0.02, vl0, zl + 0.9), (u1 + 0.02, v_foot, 0.9), (u1 - 0.04, v_foot, 0.9)]
    parts.append(hexa("rail", rail + [(u, v, zz + 0.08) for u, v, zz in rail], M["roof"]))
    for t in (0.0, 0.5, 1.0):
        v, zz = vl0 + (v_foot - vl0) * t, zl + (0.0 - zl) * t
        parts.append(bk.box("rail_post", u1 - 0.04, u1 + 0.02, v - 0.03, v + 0.03, zz, zz + 0.95, M["roof"]))
    return parts


def pricht_roofs(c, north_face):
    """Кровли из оцинкованной жести: вальма главного объёма (конёк вдоль u, вальмы круче скатов — по аэрофото),
    ниже — вальма северной части, по оси северного фасада — фронтон с полукруглым окном и его двускатная кровля;
    слуховые окна на торцевых скатах главного объёма, трубы на коньках."""
    h, v1 = c.side / 2, c.v_split
    ze, zn = c.z_eave, c.z_eave_north
    rise = c.z_ridge - ze
    parts = [quad_hip("roof_main", [(-h, v1), (h, v1), (h, h), (-h, h)], ze, rise, M["tin"], ridge=c.ridge_len)]
    dm = (h - v1) / 2                                     # полуширина главного объёма
    slope, hip = rise / dm, rise / ((c.side - c.ridge_len) / 2)
    rn = c.rise_north                                     # вальма северной части ниже фронтона
    vn = (v1 - h) / 2
    parts.append(quad_hip("roof_north", [(-h, -h), (h, -h), (h, v1 + 0.3), (-h, v1 + 0.3)], zn, rn, M["tin"]))
    pw, zp = c.pediment
    s0, s1 = h - pw / 2, h + pw / 2                       # северный фасад: s = h − u
    v_end = v1 + (zp - ze) / slope + 0.3                  # конёк фронтона уходит в скат главного объёма
    parts.append(gable("roof_pediment", north_face, s0, s1, zn, zp, -(v_end + h), 0.35, M["tin"]))
    parts.append(tympanum(north_face, s0, s1, zn, zp))
    parts.append(bk.extrude("lunette_frame", north_face, half_disc(h, 0.62, zn + 0.22), -0.02, 0.04, M["wall"]))
    parts.append(bk.extrude("lunette", north_face, half_disc(h, 0.5, zn + 0.28), 0.0, 0.07, M["glass"]))
    vm = (v1 + h) / 2
    for sgn in (-1, 1):                                   # слуховые окна на вальмах запада и востока
        uf = sgn * (h - 2.3)
        parts += dormer(uf, vm, (sgn, 0.0), ze + 2.3 * hip - 0.25, 1.2, 0.95, 0.45, 2.0)
    zr = c.z_ridge
    for u in (-c.ridge_len / 2 + 0.4, 0.4, c.ridge_len / 2 - 1.8):
        parts += chimney(u, vm, zr - 1.0, zr + 1.2)
    for u in (-7.8, 7.8):
        parts += chimney(u, vn, zn + rn - 0.8, zn + rn + 1.0, a=0.7, b=0.55)
    return parts


# ---------- Пороховые погреба ----------

def powder(c):
    """Беленое тело на двор (восточная сторона — в крепостной стене сцены), тамбур с фронтоном, крыльцо с аркадой
    под односкатной кровлей; окошки малые, глубокие, в два ряда (фото pogr_00, pogr_04), вальма из гонта с четырьмя
    слуховыми окнами (S-23) и двумя кирпичными трубами (фото pogr_04, ключ stone)."""
    L, z = c.length / 2, BASE_Z[c.key]
    vw = c.v_west
    body = bk.box("walls", -L, L, vw, c.v_east, z, c.z_eave, M["wall"])
    fr = rect_faces(-L, L, vw, c.v_east)
    op, parts = Openings(), []
    tw, td, te, tr = c.tambour
    pl, pd, pz0, pz1 = c.porch
    small = dict(depth=0.5, frame=0, sill=False, cross=False)
    w = fr["v-"]                                          # запад: s с севера (u = L − s)
    for s in (3.0, 7.0, 10.5, 27.3):                      # тамбур — s 13,1…21,4, крыльцо — до 26,0
        op.window(w, s, 0.55, 4.3, 4.95, **small)
    for s in (5.0, 9.0, 27.3):
        op.window(w, s, 0.55, 1.6, 2.25, **small)
    nf = fr["u+"]                                         # север: s с востока
    for s in (5.5, 9.5):
        op.window(nf, s, 0.55, 4.0, 4.65, **small)
    op.window(nf, 7.5, 0.55, 1.5, 2.15, **small)
    sf = fr["u-"]                                         # юг: три окошка (фото pogr_01, pogr_03)
    for s in (3.3, 6.6, 9.9):
        op.window(sf, s, 0.55, 3.6, 4.25, **small)
    parts += op.apply(body)
    parts.append(bk.box("plinth", -L - 0.06, L + 0.06, vw - 0.06, c.v_east, z, 0.35, M["wall"]))
    parts.append(bk.box("cornice", -L - 0.15, L + 0.15, vw - 0.15, c.v_east, c.z_eave - 0.35, c.z_eave - 0.12,
                        M["wall"]))
    # тамбур
    ut = c.u_tambour
    tb = bk.box("tambour", ut - tw / 2, ut + tw / 2, vw - td, vw + 0.3, z, te, M["wall"])
    tf = rect_faces(ut - tw / 2, ut + tw / 2, vw - td, vw)
    ot = Openings()
    for s in (tw / 2 - 1.9, tw / 2 + 1.9):
        ot.window(tf["v-"], s, 0.55, 3.7, 4.35, **small)
    ot.door(tf["v-"], tw / 2, 0.95, 0.0, 1.2, depth=0.4, key="dark", arch=True)       # решётка подклета
    parts += ot.apply(tb)
    parts.append(tympanum(tf["v-"], 0.0, tw, te, tr))
    parts.append(gable("roof_tambour", tf["v-"], 0.0, tw, te, tr, -(td + 1.6), 0.35, M["wood"], thick=0.14))
    # крыльцо к югу от тамбура: аркада из двух арок на запад (за ними — тёмные двери), кровля к югу
    u0, u1 = ut - tw / 2 - pl, ut - tw / 2
    pb = bk.box("porch", u0, u1, vw - pd, vw + 0.3, z, pz1 - 0.25, M["wall"])
    pf = rect_faces(u0, u1, vw - pd, vw)
    opp = Openings()
    for s in (pl * 0.27, pl * 0.73):
        opp.cut(pf["v-"], bk.arch(s, 1.3, 0.0, 1.75), 1.2)
        opp.parts.append(bk.extrude("door", pf["v-"], bk.arch(s, 1.3, 0.0, 1.75), -1.25, -1.15, M["dark"]))
    parts += opp.apply(pb)
    parts.append(bk.slab("roof_porch", [(u1 + 0.05, vw + 0.2, pz0), (u1 + 0.05, vw - pd - 0.35, pz0),
                                        (u0 - 0.4, vw - pd - 0.35, pz1 - 0.2), (u0 - 0.4, vw + 0.2, pz1 - 0.2)],
                         0.14, M["wood"]))                  # скат от тамбура к югу (фото pogr_04)
    return parts + powder_roof(c)


def powder_roof(c):
    """Вальма из гонта над двором до внутренней грани стены сцены; слуховые окна: по одному на северном и южном
    скатах, два — на восточном (S-23); кирпичные трубы на западном скате (фото pogr_04)."""
    L = c.length / 2
    vw, vs = c.v_west, c.v_wall
    rise = c.z_ridge - c.z_eave
    parts = [quad_hip("roof", [(-L, vw), (L, vw), (L, vs), (-L, vs)], c.z_eave, rise, M["wood"], over=0.45, thick=0.18)]
    half = (vs - vw) / 2
    slope = rise / half
    vm = (vw + vs) / 2
    zd = c.z_eave + 2.2 * slope - 0.2
    for sgn in (-1, 1):
        parts += dormer(sgn * (L - 2.2), vm, (sgn, 0.0), zd, 1.1, 0.9, 0.45, 1.8, roof="wood")
        parts += dormer(sgn * 5.0, vs - 2.2, (0.0, 1.0), zd, 1.1, 0.9, 0.45, 1.8, roof="wood")
    for u in (-3.0, 2.5):
        parts += chimney(u, vm - 1.0, c.z_ridge - 1.2, c.z_ridge + 1.3, a=0.75, b=0.75, key="stone", cap="wood")
    return parts


# ---------- Консистория ----------

def consistory(c):
    """Главный корпус и крылья к двору — одним телом по контуру OSM, ретирады и лестница — своими; главный фасад
    в 5 осей с «тройным» окном, пилястры 2-го этажа, треугольные фронтончики над боковыми окнами, пояс, карниз
    (S-71, фото kons_00); северо-восточный фасад — 3 оси старой части и 2 оси пристройки 1870-х."""
    z = BASE_Z[c.key]
    P = c.outline
    x = (c.u_wings, -17.4)
    A = [P[0], P[9], P[8], P[7], P[6], P[5], x, P[2], P[1]]           # корпус и два крыла
    B = [P[2], x, P[5], (-5.79, P[5][1])]                            # ретирады
    Cst = [(-5.79, P[5][1]), P[5], P[4], P[3]]                       # лестница
    body = bk.prism("walls", A, z, c.z_eave - 0.3, M["wall"])
    op, parts = Openings(), []
    (l0, l1), (u0, u1) = c.low, c.up
    inside = (0.0, -8.0)
    se = face(P[0], P[9], inside)                                    # главный фасад: s от западного угла
    ne = face(P[9], P[8], inside)                                    # северо-восточный: s от угла с главным
    sw = face(P[1], P[0], inside)                                    # юго-западный: s от двора
    mid = c.u_axis - P[0][0]                                         # ось симметрии: на фото не посередине контура OSM
    sa, st = c.axes
    for s in (mid - sa, mid + sa):                                   # боковые оси
        op.window(se, s, 1.2, l0, l1, hood="shelf")
        op.window(se, s, 1.2, u0, u1, hood="tri")
    for s in (mid - st, mid, mid + st):                              # «тройное» окно
        op.window(se, s, 1.3, l0, l1, frame=0.1)
        op.window(se, s, 1.3, u0, u1, frame=0.1)
    for zz in (l1 + 0.1, u1 + 0.1):                                  # общий сандрик тройного окна
        op.hood(se, mid, 2 * st + 1.4, zz, "shelf")
    for s in [mid - sa, mid - st, mid, mid + st, mid + sa]:
        op.window(se, s, 0.8, 0.35, 0.55, depth=0.12, frame=0, sill=False, cross=False)   # ниши-продухи цоколя
    for s in (mid - sa - 0.95, mid - sa + 0.95, mid - st - 1.05, mid + st + 1.05, mid + sa - 0.95, mid + sa + 0.95,
              0.35, se.length - 0.35):
        op.pilaster(se, s, c.z_belt[1], c.z_eave - 0.6)                              # пилястры 2-го этажа
    for k, s in enumerate((1.8, 4.5, 7.2, 11.3, 13.9)):
        op.window(ne, s, 1.15, l0, l1, hood="shelf" if k < 3 else None)
        op.window(ne, s, 1.15, u0, u1, hood="tri" if k in (1, 3, 4) else "shelf")
    for s in (2.6, 12.8, 14.7, 16.6):                                # юго-запад: окна и дверь под общим сандриком
        op.window(sw, s, 1.1, u0, u1)
    for s in (2.6, 12.8, 16.6):
        op.window(sw, s, 1.1, l0, l1, frame=0)
    op.door(sw, 10.4, 1.4, 0.9, 3.4)
    op.hood(sw, 12.2, 7.2, l1 + 0.1, "shelf")
    op.hood(sw, 14.7, 5.0, u1 + 0.1, "shelf")
    # дворовые фасады: заднее западное крыло, северное крыло с запада и с северо-востока
    yard = [(face(P[1], P[2], inside), [2.35]), (face(P[5], P[6], inside), [2.2, 6.7]),
            (face(P[6], P[8], inside), [2.3, 5.6])]
    for fr, ss in yard:
        for s in ss:
            op.window(fr, s, 1.1, l0, l1, frame=0.1)
            op.window(fr, s, 1.1, u0, u1, frame=0.1, hood="shelf")
    parts += op.apply(body)
    parts += steps(sw, 10.4, 2.4, 0.9, n=3)
    parts += canopy(sw, 10.4, 2.2, 3.85)
    parts.append(ring_band(A, z, c.z_plinth, 0.06, "roof"))                            # гладкий цоколь
    parts.append(ring_band(A, c.z_belt[0], c.z_belt[1], 0.07))                         # пояс с филёнками
    parts.append(ring_band(A, c.z_eave - 0.6, c.z_eave - 0.38, 0.14))                  # карниз с сухариками, под свесом
    parts.append(ring_band(A, c.z_eave - 0.38, c.z_eave - 0.2, 0.3))
    # ретирады и лестница
    rb = bk.prism("retirade", B, z, c.z_back, M["wall"])
    orb = Openings()
    fb = face(P[2], (-5.79, P[5][1]), (-3.0, -20.0))
    orb.window(fb, fb.length / 2, 0.9, l0, l1, frame=0)
    orb.window(fb, fb.length / 2, 0.9, u0, u1, frame=0)
    parts += orb.apply(rb)
    parts.append(ring_band(B, c.z_back - 0.3, c.z_back, 0.25))
    zs0, zs1 = c.z_stair
    parts.append(bk.prism("stair", Cst, z, zs0, M["wall"]))
    parts.append(bk.slab("roof_stair", [(-5.99, P[5][1] + 0.1, zs0 + 0.1), (0.09, P[5][1] + 0.1, zs0 + 0.1),
                                        (0.09, P[4][1] - 0.35, zs1), (-5.99, P[3][1] - 0.35, zs1)], 0.14, M["tin"]))
    return parts + consistory_roofs(c, A, B)


def consistory_roofs(c, A, B):
    """Кровли — жесть: вальмы над главным корпусом (конёк вдоль фасада), западным и северным крыльями и ретирадами;
    над главным фасадом — слуховое окно (фото kons_00, аэрофото)."""
    P = c.outline
    pitch = math.tan(math.radians(24))                    # гип.: пологие скаты (аэрофото)
    ze = c.z_eave
    vm = c.v_main
    u_ne = P[9][0] + (P[8][0] - P[9][0]) * vm / P[8][1]   # северо-восточный фасад на глубине корпуса
    main = [P[0], P[9], (u_ne, vm), (P[0][0], vm)]
    west = [(P[0][0], vm), (c.u_wings, vm), (c.u_wings, -17.4), P[1]]
    north = [(c.u_wings, vm), (u_ne, vm), P[6], P[5]]
    parts = []
    for name, q, d in (("roof_main", main, -vm), ("roof_west", west, 8.4), ("roof_north", north, 9.3)):
        parts.append(quad_hip(name, q, ze, d / 2 * pitch, M["tin"], over=0.5))
    parts.append(quad_hip("roof_retirade", B, c.z_back, 2.8 * pitch, M["tin"], over=0.4))
    parts += dormer(0.0, -2.2, (0.0, 1.0), ze + 2.2 * pitch - 0.2, 1.0, 0.9, 0.45, 1.8)
    parts += chimney(-4.5, vm / 2, ze + 0.8, ze + (-vm / 2) * pitch + 0.9, a=0.7, b=0.5)
    parts += chimney(4.5, -13.0, ze + 0.8, ze + 4.6 * pitch + 0.9, a=0.7, b=0.5)
    return parts


# ---------- сборка ----------

BUILD = {"Pricht": pricht, "Powder": powder, "Consistory": consistory}

# Превью с точек фото S-70 (build/yard_refs/manifest.json): глаз (u, v, z) в осях здания; взгляд — цель (u, v, z) или
# (азимут от оси u к оси v, наклон), градусы; кадр — как у фото; фокусное — 35-мм экв. (кадр 36 мм по ширине): по
# EXIF или подобрано вместе с камерой.
# «камера» — восстановлена по точкам модели на фото (build/yard/fit_*.py, невязка в скобках); «гип.» — оценка по
# кадру, подогнана наложением модели на фото. Высота глаза — от нуля здания.
VIEWS = {
    "Pricht": {
        "nw": ((-40.3, -41.0, 1.31), (43.1, 6.5), (1280, 806), 40.4),       # prich_00, Ludvig14: камера (≤15 пкс)
        "east": ((32.2, -7.0, 4.1), (163.2, -0.1), (1280, 853), 28.0),      # px_04, А. Спиридонов: камера (≤15 пкс)
        "west": ((-39.8, 2.6, 6.75), (-0.4, 0.2), (1280, 960), 25.0),       # prich_17, Е. Борисова: камера (≤3 пкс),
    },                                                                      # снято с боевого хода западной стены
    "Powder": {
        "west": ((13.6, -41.1, 1.34), (118.2, 8.0), (1280, 816), 29.9),     # pogr_00, Ludvig14 (2013): камера (≤5 пкс)
        "ssw": ((-62.0, -8.0, 1.6), (-10.0, 1.0, 5.0), (1280, 864), 33.9),  # pogr_01, Ludvig14 (2013): геотег, гип.
        "sw": ((-23.2, -23.2, 5.86), (47.5, 5.2), (1280, 938), 25.7),       # pogr_04, Е. Борисова (2023): камера
    },                                                                      # (≤24 пкс, крен 5,2°; fit_cams.py)
    "Consistory": {   # kons_00: кадр выправлен по вертикалям — камера «на 6 м», без наклона (build/yard/fit_kons00.py);
        # air_09 — по кресту собора, вершине Рыбницкой и окнам (build/yard/fit_air09.py), крен −5,8° превью не знает
        "street": ((1.6, 22.3, 6.2), (-93.5, -0.2), (1280, 960), 36.0),     # kons_00, GAlexandrova (2013): камера (≤6)
        "air": ((70.1, 52.2, 65.2), (-108.7, -16.8), (2000, 1499), 25.1),   # air_09, BKDRF (без даты): камера (≤14)
    },
}


def target(eye, look):
    """Цель камеры: точка (u, v, z) или (азимут, наклон) — точка в 30 м по взгляду."""
    if len(look) == 3:
        return look
    y, p = math.radians(look[0]), math.radians(look[1])
    return (eye[0] + 30 * math.cos(p) * math.cos(y), eye[1] + 30 * math.cos(p) * math.sin(y), eye[2] + 30 * math.sin(p))


def build(c):
    name = c.asset
    bk.reset_scene()
    bk.use_colors(krom_plan.COLORS)
    objs = BUILD[c.key](c)
    obj = bk.join(objs, name)
    bk.box_uv(obj)
    me = obj.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    print(f"[krom_yard] {c.name}: {len(objs)} тел → {name}: {len(me.vertices)} вершин, {len(me.polygons)} граней "
          f"({tris} треугольников), слоты {[m.name for m in me.materials]}")
    bk.export_glb(obj, name)
    ground = bk.box("ground", -200, 200, -200, 200, -0.05, 0.0, bk.material("ground", (0.12, 0.16, 0.08)))  # превью
    ground.hide_select = True
    bk.PREVIEW_DIR = RENDER_DIR
    for view, (eye, look, size, lens) in VIEWS[c.key].items():
        t = target(eye, look)
        bk.render_preview(f"yard_{c.key}_{view}", eye=(eye[0], -eye[1], eye[2]), target=(t[0], -t[1], t[2]), size=size,
                          lens=lens)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    todo = [c for c in yard_plan.YARD if not argv or c.key in argv]
    if not todo:
        raise SystemExit(f"[krom_yard] нет здания {argv}; есть: {[c.key for c in yard_plan.YARD]}")
    for c in todo:
        build(c)


main()
