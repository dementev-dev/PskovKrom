"""prikaz.py — Приказные палаты (1692–95): герой скриптом Blender по prikaz_plan (D-018; как krom_yard, D-036).

    python scripts/bl_run.py scripts/blender/prikaz.py

Выгрузка — build/blender/SM_PrikazPalaty.glb (в UE ставит scripts/heroes_krom.py), превью с восстановленных камер
фото Commons — build/prikaz/renders/prikaz_<вид>.png (сверка — build/prikaz/compare.py → build/prikaz_refs/compare.jpg).
Габариты, высоты, крыльцо и источники — в scripts/prikaz_plan.py; здесь — детали по фото (build/prikaz/measure.py):
окна и двери с зелёными ставнями, круглые столбы верхнего рундука, косые арки всхода, арки нижнего рундука,
лестница, слуховые окна и трубы. Оси здания (u, v, z) — как в prikaz_plan; в Blender точка (u, −v, z).
Материалы — слоты по ключам krom_plan.COLORS, новых нет: стены «wall», кровли — оцинковка «tin», двери и ставни —
«green» (единственный тёмно-зелёный ключ), трубы — «stone».
Помощники face, offset, quad_hip, gable, dormer, Openings скопированы из krom_yard.py: тот при импорте сразу строит
свои здания (main() в конце модуля), поэтому импортировать его нельзя.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402
import krom_plan  # noqa: E402
import prikaz_plan  # noqa: E402
from bl_krom import M  # noqa: E402

RENDER_DIR = os.path.join(bk.REPO, "build", "prikaz", "renders")
BASE_Z = -1.0      # низ стен ниже нуля здания: земля под контуром неровная, гип.


# ---------- помощники (из krom_yard.py) ----------

def face(a, b, inside):
    """Фасад по отрезку a–b: s идёт слева направо, если смотреть снаружи (оси u, v — «левые», как x, y плана)."""
    fr = bk.Frame.between(a, b, inside)
    right = (fr.n[1], -fr.n[0])
    if (b[0] - a[0]) * right[0] + (b[1] - a[1]) * right[1] < 0:
        fr = bk.Frame.between(b, a, inside)
    return fr


def s_at(fr, p):
    """Координата s на фасаде fr для точки плана p (u, v)."""
    return (p[0] - fr.o[0]) * fr.t[0] + (p[1] - fr.o[1]) * fr.t[1]


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
    """Пояс или карниз вокруг контура poly (u, v): тело шире стен на proud."""
    return bk.prism("band", offset(poly, proud), z0, z1, M[key])


def quad_hip(name, P, z, rise, mat, over=0.45, thick=0.15):
    """Вальмовая кровля над прямоугольником P [(u, v)] с карнизом на z: конёк по длинной оси на z + rise, вальмы
    под 45° в плане; свес over — по плоскостям скатов."""
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
    Q = offset([a0, a1, c0, c1], over)
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


def dormer(u, v, n, z0, w, h, rise, depth, body="tin", roof="tin", louvre=0.5):
    """Слуховое окно: передняя стенка в точке (u, v) смотрит по n (в плане), низ z0 — в кровле; тело уходит
    в кровлю на depth, сверху двускатная крыша, спереди — жалюзи (стекло)."""
    fr = bk.Frame((u, v), (n[1], -n[0]), n)
    zl = z0 + h - louvre - 0.12
    return [bk.extrude("dormer", fr, bk.rect(-w / 2, w / 2, z0, z0 + h), -depth, 0.0, M[body]),
            gable("dormer_roof", fr, -w / 2, w / 2, z0 + h, z0 + h + rise, -depth, 0.12, M[roof], over=0.12,
                  thick=0.06),
            bk.extrude("louvre", fr, bk.rect(-louvre / 2, louvre / 2, zl, zl + louvre), -0.02, 0.02, M["glass"])]


def chimney(u, v, z0, z1, a=0.75, b=0.75, key="stone", cap="tin"):
    return [bk.box("chimney", u - a / 2, u + a / 2, v - b / 2, v + b / 2, z0, z1, M[key]),
            bk.box("chimney_cap", u - a / 2 - 0.07, u + a / 2 + 0.07, v - b / 2 - 0.07, v + b / 2 + 0.07, z1, z1 + 0.1,
                   M[cap])]


def ell_arch(sc, w, z0, zs, rise, n=16):
    """Проём с лучковым (эллиптическим) верхом: середина sc, ширина w, низ z0, пята zs, подъём арки rise."""
    top = [(sc + w / 2 * math.cos(math.pi * k / n), zs + rise * math.sin(math.pi * k / n)) for k in range(n + 1)]
    return [(sc - w / 2, z0), (sc + w / 2, z0)] + top


class Openings:
    """Проёмы одного тела: вырезы копятся и вычитаются одной булевой операцией (вырезы не пересекаются);
    стёкла, переплёты, ставни и двери — отдельные тела. Окна палат — в глубоких откосах, без наличников."""

    def __init__(self):
        self.cutters, self.parts = [], []

    def cut(self, fr, poly, depth):
        self.cutters.append(bk.extrude("cut", fr, poly, -depth, 0.6, M["wall"]))

    def window(self, fr, s, w, z0, z1, depth=0.45, arched=False, shutters=False, cross=True):
        poly = bk.arch(s, w, z0, z1 - w / 2) if arched else bk.rect(s - w / 2, s + w / 2, z0, z1)
        self.cut(fr, poly, depth)
        self.parts.append(bk.extrude("glass", fr, poly, -depth - 0.05, -depth + 0.02, M["glass"]))
        if cross:                                   # белый переплёт: стойка и фрамуга
            zt = z1 - (z1 - z0) * 0.35
            for p in (bk.rect(s - 0.03, s + 0.03, z0, z1 - (w / 2 if arched else 0)),
                      bk.rect(s - w / 2, s + w / 2, zt - 0.03, zt + 0.03)):
                self.parts.append(bk.extrude("sash", fr, p, -depth + 0.02, -depth + 0.06, M["wall"]))
        if shutters:                                # распахнутые ставни по сторонам
            for a, b in ((s - w, s - w / 2 - 0.02), (s + w / 2 + 0.02, s + w)):
                self.parts.append(bk.extrude("shutter", fr, bk.rect(a, b, z0, z1), 0.01, 0.06, M["green"]))

    def door(self, fr, s, w, z0, z1, depth=0.5, key="green"):
        poly = bk.rect(s - w / 2, s + w / 2, z0, z1)
        self.cut(fr, poly, depth)
        self.parts.append(bk.extrude("door", fr, poly, -depth - 0.04, -depth + 0.02, M[key]))

    def apply(self, body):
        return [bk.cut(body, self.cutters)] + self.parts


def steps(fr, s, w, z_top, n=2, tread=0.35, key="stone"):
    """Ступени перед проёмом: n ступеней от z_top вниз до земли."""
    rise = z_top / n
    return [bk.extrude("step", fr, bk.rect(s - w / 2, s + w / 2, -0.3, z_top - k * rise), 0.0, (k + 1) * tread, M[key])
            for k in range(n)]


# ---------- основной объём ----------

def main_block(c):
    """Беленое тело 31,4 × 15,3 до карниза 9,0 с поясом-карнизом; окна и двери по фото (measure.py): север — с
    ставнями у крыльца, двери 1-го этажа; восточный торец — два арочных и прямое окно 2-го этажа; западный — два
    малых окна и щель на чердак (лестница в толще стены); юг — малые окна 2-го и 1-го этажей (гип.: анфас юга
    на фото нет)."""
    h, d = c.length / 2, c.depth / 2
    body = bk.box("body", -h, h, -d, d, BASE_Z, c.z_eave, M["wall"])
    ctr = (0.0, 0.0)
    N, S = face((-h, -d), (h, -d), ctr), face((-h, d), (h, d), ctr)
    W, E = face((-h, -d), (-h, d), ctr), face((h, -d), (h, d), ctr)
    op = Openings()
    # север: 2-й этаж (u, ширина, низ, верх, ставни)
    for u, w, z0, z1, sh in ((-7.6, 0.85, 5.1, 7.0, True), (3.1, 0.75, 5.1, 7.0, True), (8.2, 0.6, 5.05, 6.0, True)):
        op.window(N, s_at(N, (u, -d)), w, z0, z1, shutters=sh)
    op.window(N, s_at(N, (-13.4, -d)), 0.25, 8.25, 8.75, depth=0.3, cross=False)       # щель на чердак
    for u, w, z1 in ((-10.5, 0.9, 1.55), (-7.15, 1.1, 1.75), (2.7, 0.95, 1.9), (8.9, 1.2, 2.05)):
        op.door(N, s_at(N, (u, -d)), w, 0.0, z1)
    op.window(N, s_at(N, (6.9, -d)), 0.7, 0.95, 2.1)
    op.window(N, s_at(N, (11.6, -d)), 0.8, 0.85, 2.0, arched=True, shutters=True)
    pc = sum(c.porch_u) / 2                                   # дверь с верхнего рундука в палату
    op.door(N, s_at(N, (pc, -d)), 1.3, c.z_upper_floor, c.z_upper_floor + 2.3, key="dark")
    # восточный торец: два арочных окна и прямое (2-й этаж)
    for v, arched in ((5.05, True), (0.35, True), (-4.45, False)):
        op.window(E, s_at(E, (h, v)), 0.7, 4.9, 7.3 if arched else 7.0, arched=arched)
    # западный торец: два малых окна и щель у стыка со стеной
    for v in (-3.35, -0.85):
        op.window(W, s_at(W, (-h, v)), 0.5, 5.2, 6.25)
    op.window(W, s_at(W, (-h, 2.6)), 0.25, 8.3, 8.8, depth=0.3, cross=False)
    # юг (гип.): четыре окна 2-го этажа и два малых 1-го
    for u in (-10.0, -3.5, 3.5, 10.0):
        op.window(S, s_at(S, (u, d)), 0.6, 5.2, 6.3)
    for u in (-6.0, 6.0):
        op.window(S, s_at(S, (u, d)), 0.5, 1.2, 1.9)
    parts = op.apply(body)
    outline = [(-h, -d), (h, -d), (h, d), (-h, d)]
    parts.append(ring_band(outline, c.z_eave - 0.3, c.z_eave, 0.12))
    return parts


def main_roof(c):
    """Вальма из оцинкованной стали (конёк 13,55, вальмы под 45°), слуховые окна на обеих вальмах, трубы:
    северная — по двум камерам (c_14 × c_09, верх 14,5), южная у западной вальмы — по c_07 и c_29, гип."""
    h, d = c.length / 2, c.depth / 2
    rise = c.z_ridge - c.z_eave
    parts = [quad_hip("roof", [(-h, -d), (h, -d), (h, d), (-h, d)], c.z_eave, rise, M["tin"], over=0.5)]
    k = rise / d                                              # уклон скатов и вальм
    for u, n in ((-12.4, (-1.0, 0.0)), (12.4, (1.0, 0.0))):
        z0 = c.z_eave + (h - abs(u)) * k - 0.1
        parts += dormer(u, 0.0, n, z0, 1.3, 1.0, 0.5, 2.2)
    parts += chimney(6.35, -2.9, c.z_ridge - 2.9 * k - 0.3, 14.5)
    u, v = -12.0, 4.2                                        # южная труба: по c_07 южнее оси конька, гип.
    parts += chimney(u, v, c.z_eave + min(h - abs(u), d - abs(v)) * k - 0.3, 12.6, a=0.65, b=0.65)
    return parts


# ---------- крыльцо ----------

def porch(c):
    """«Красное крыльцо на отлёте» (1693–95, восстановлено в 1968): одно беленое тело по профилю (s, z) — вынос s
    от северного фасада — с полостью рундуков и всхода; по бокам арка верхнего рундука, круглый столб-«бочка»
    и косая арка над всходом, у нижнего рундука — арки с трёх сторон; лестница, ступени, карнизы."""
    a, b = c.porch_u
    d = c.depth / 2
    Lp, t = c.porch_len, c.porch_wall
    s1, s2 = c.s_upper, c.s_stair
    zu, zl = c.z_porch_eave
    fu, fl = c.z_upper_floor, c.z_lower_floor
    side = bk.Frame((a, -d), (0.0, -1.0), (-1.0, 0.0))        # западная грань: s — от фасада на север, наружу — −u
    wdt = b - a
    outer = [(0.0, BASE_Z), (Lp, BASE_Z), (Lp, zl), (s2, zl), (s1, zu), (0.0, zu)]
    body = bk.extrude("porch", side, outer, -wdt, 0.0, M["wall"])
    z_up, z_low = 7.75, 5.2                                   # своды: верхний рундук и нижний (гип., над арками)
    cavity = [(-0.1, fu), (s1, fu), (s2, fl), (Lp - t, fl), (Lp - t, z_low), (s2 + 0.4, z_low), (s1 + 0.3, z_up),
              (-0.1, z_up)]
    body = bk.cut(body, [bk.extrude("cavity", side, cavity, -(wdt - t), -t, M["wall"])])
    # проёмы по обеим сторонам — одним резцом насквозь по u
    arcs = [bk.arch(2.45, 3.3, 4.85, 5.9),                                              # верхний рундук
            [(5.65, 4.85), (9.4, 2.75)] + bk.spline([(9.4, 2.75), (8.9, 4.1), (8.0, 5.45), (7.0, 6.35), (6.1, 6.62),
                                                     (5.65, 6.5)])[1:],                   # косая арка всхода
            ell_arch(12.8, 4.5, fl, 2.75, 1.55)]                                        # нижний рундук
    body = bk.cut(body, [bk.extrude("side_arch", side, p, -wdt - 0.5, 0.5, M["wall"]) for p in arcs])
    north = bk.Frame((a, -d - Lp), (1.0, 0.0), (0.0, -1.0))   # северная грань: s — от западного угла на восток
    op = Openings()
    op.cutters.append(bk.extrude("north_arch", north, ell_arch(4.085, 4.87, fl, 3.1, 1.9), -t - 0.3, 0.5, M["wall"]))
    east = bk.Frame((b, -d), (0.0, -1.0), (1.0, 0.0))
    for fr in (side, east):                                   # окошки палаток под рундуком и под всходом
        op.window(fr, 2.8, 0.55, 0.95, 2.05, depth=0.35, arched=True, cross=False)
        op.window(fr, 6.6, 0.45, 0.95, 1.7, depth=0.35, cross=False)
    parts = op.apply(body)
    # столбы-«бочки» между аркой верхнего рундука и косой аркой (фото c_07, c_09)
    for u in (a + t / 2, b - t / 2):
        parts.append(bk.lathe("barrel", (u, -d - 4.875), [(0.5, 4.85), (0.63, 5.15), (0.63, 5.6), (0.5, 5.9)],
                              M["wall"], seg=16))
    # лестница: от пола нижнего рундука к верхнему, во всю ширину полости
    n = 19
    rise, tread = (fu - fl) / n, (s2 - s1) / n
    for k in range(n):
        sa = s2 - (k + 1) * tread
        parts.append(bk.extrude("stair", side, bk.rect(sa, sa + tread + 0.02, fl + k * rise - 0.3, fl + (k + 1) * rise),
                                -(wdt - t) + 0.01, -t - 0.01, M["stone"]))
    # ступени у арок нижнего рундука: с севера, запада и востока
    parts += steps(north, 4.085, 4.9, fl)
    for fr in (side, east):
        parts += steps(bk.Frame(fr.p(12.8, 0.0)[:2], (0.0, -1.0) if fr is east else (0.0, 1.0), fr.n), 0.0, 4.5, fl)
    # карнизы под свесами кровли
    parts.append(bk.box("cornice", a - 0.1, b + 0.1, -d - Lp - 0.1, -d - s2, zl - 0.25, zl, M["wall"]))
    parts.append(bk.box("cornice", a - 0.1, b + 0.1, -d - s1, -d, zu - 0.25, zu, M["wall"]))
    return parts


def porch_roof(c, over=0.45, thick=0.14):
    """Кровля крыльца — одна жесть ступенью: над верхним рундуком (конёк уходит в скат палаты), наклонный участок над
    всходом, над нижним рундуком — с вальмой на север (фото c_07, c_09, c_14; отметки — measure.py)."""
    a, b = c.porch_u
    d = c.depth / 2
    pc, hw = (a + b) / 2, (b - a) / 2 + over
    zu, zl = c.z_porch_eave
    ru, rl = c.z_porch_ridge
    reach = (ru - c.z_eave) / ((c.z_ridge - c.z_eave) / d) + 0.3   # где конёк входит в скат палаты
    secs = [(-reach, zu, ru), (c.s_upper, zu, ru), (c.s_stair, zl, rl), (c.s_porch_ridge, zl, rl)]
    sn = c.porch_len + over

    def eave(e, r):
        return e - over * (r - e) / (hw - over)

    top = []
    for s, e, r in secs:
        v = -d - s
        top += [(pc - hw, v, eave(e, r)), (pc, v, r), (pc + hw, v, eave(e, r))]
    ze = eave(zl, rl)
    top += [(pc - hw, -d - sn, ze), (pc + hw, -d - sn, ze)]
    n = len(secs)
    L, T, R = (lambda i: 3 * i), (lambda i: 3 * i + 1), (lambda i: 3 * i + 2)
    NL, NR = 3 * n, 3 * n + 1
    faces = []
    for i in range(n - 1):
        faces += [[L(i), L(i + 1), T(i + 1), T(i)], [T(i), T(i + 1), R(i + 1), R(i)]]
    last = n - 1
    faces += [[L(last), NL, T(last)], [T(last), NR, R(last)], [NL, NR, T(last)], [L(0), T(0), R(0)]]
    m = len(top)
    bot = [(u, v, z - thick) for u, v, z in top]
    faces += [[m + k for k in reversed(f)] for f in faces]
    rim = [L(i) for i in range(n)] + [NL, NR] + [R(i) for i in reversed(range(n))]
    faces += [[rim[k], rim[(k + 1) % len(rim)], m + rim[(k + 1) % len(rim)], m + rim[k]] for k in range(len(rim))]
    return [bk.mesh("porch_roof", top + bot, faces, M["tin"])]


def build(c):
    bk.reset_scene()
    bk.use_colors(krom_plan.COLORS)
    objs = main_block(c) + main_roof(c) + porch(c) + porch_roof(c)
    obj = bk.join(objs, c.asset)
    bk.box_uv(obj)
    me = obj.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    print(f"[prikaz] {c.name}: {len(objs)} тел → {c.asset}: {len(me.vertices)} вершин, {len(me.polygons)} граней "
          f"({tris} треугольников), слоты {[m.name for m in me.materials]}")
    bk.export_glb(obj, c.asset)
    ground = bk.box("ground", -200, 200, -200, 200, -0.05, 0.0, bk.material("ground", (0.12, 0.16, 0.08)))  # превью
    ground.hide_select = True
    bk.PREVIEW_DIR = RENDER_DIR
    for view, (eye, look, size, lens) in VIEWS.items():
        t = target(eye, look)
        bk.render_preview(f"prikaz_{view}", eye=(eye[0], -eye[1], eye[2]), target=(t[0], -t[1], t[2]), size=size,
                          lens=lens)


# Камеры превью = камеры фото S-126, восстановленные вместе с размерами (build/prikaz/solve.py при L 31,4 и D 15,3):
# глаз (u, v, z) от середины основного объёма и земли у северного фасада, взгляд (азимут от оси u к оси v, наклон),
# кадр как у фото, фокусное — 35-мм экв.: c_09 и c_14 — по EXIF, c_07 (EXIF нет) — подобрано (28 мм; у снимка того
# же автора и камеры c_06 — 26 мм). Крен ≤0,6° превью не знает.
VIEWS = {
    "ne": ((25.2, -45.55, 3.35), (122.9, 2.9), (1280, 720), 33.0),       # c_09, A.Savin (2018): невязка ≤18 пкс
    "north": ((-13.5, -73.25, 2.22), (80.9, 4.1), (1280, 853), 56.2),    # c_14, Lion10 (2026): ≤8 пкс
    "west": ((-44.6, -12.75, 2.6), (8.2, 7.2), (1280, 852), 28.1),        # c_07, Ludvig14 (2013): ≤16 пкс
}


def target(eye, look):
    """Цель камеры: точка в 30 м по взгляду (азимут от оси u к оси v, наклон)."""
    y, p = math.radians(look[0]), math.radians(look[1])
    return (eye[0] + 30 * math.cos(p) * math.cos(y), eye[1] + 30 * math.cos(p) * math.sin(y), eye[2] + 30 * math.sin(p))


build(prikaz_plan.PRIKAZ)
