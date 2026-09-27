"""chapels.py — часовни у Ольгинского моста на Завеличье: модели скриптом Blender по krom_plan.CHAPELS (D-018, D-019).

    python scripts/bl_run.py scripts/blender/chapels.py                # обе
    python scripts/bl_run.py scripts/blender/chapels.py -- Anastasia   # одна (ChapelPlan.key: Anastasia, Olga)

Выгрузка — build/blender/SM_Chapel_<key>.glb (в UE ставит scripts/heroes_krom.py), превью —
media/renders/blender/chapel_<key>_*.png. Размеры, проёмы и отметки берутся из ChapelPlan, источники записаны там.
Здесь только детали, снятые с фото S-60 «на глаз»: пилястры, пояс треугольников, киот, пята закомар, ниши, горельеф,
аркатура и профили глав. Оси часовни: u — на восток (азимут yaw), v — к югу, z — от земли в центре.
Материалы — слоты по ключам krom_plan.COLORS.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402
import krom_plan  # noqa: E402
from bl_krom import M, Openings  # noqa: E402

C = (0.0, 0.0)
BASE_Z = -0.3            # низ стен: часовни стоят на неровной земле, тело уходит в неё


def faces(h, a=None):
    """Фасады квадрата ±h (у крестового — торцы рукавов шириной 2a): {сторона: Frame}; s — слева направо снаружи."""
    a = h if a is None else a
    return {"W": bk.Frame.between((-h, -a), (-h, a), C), "N": bk.Frame.between((a, -h), (-a, -h), C),
            "E": bk.Frame.between((h, a), (h, -a), C), "S": bk.Frame.between((-a, h), (a, h), C)}


def inward(fr, depth):
    """Та же плоскость фасада, сдвинутая внутрь на depth (дно ниши)."""
    return bk.Frame((fr.o[0] - depth * fr.n[0], fr.o[1] - depth * fr.n[1]), fr.t, fr.n, fr.length)


def ball(z0, r):
    """Яблоко под крестом: низ на z0."""
    return bk.lathe("apple", C, [(r * math.sin(math.pi * i / 12), z0 + r - r * math.cos(math.pi * i / 12))
                                 for i in range(13)], M["gold"], seg=24)


def cross8(z0, h, th=0.05):
    """Восьмиконечный крест (как у собора): перекладины поперёк оси (вдоль v), нижняя — северным концом вверх."""
    fr = bk.Frame(C, (0.0, 1.0), (1.0, 0.0))
    polys = [bk.rect(-th / 2, th / 2, z0, z0 + h),
             bk.rect(-0.16 * h, 0.16 * h, z0 + 0.86 * h - th / 2, z0 + 0.86 * h + th / 2),
             bk.rect(-0.34 * h, 0.34 * h, z0 + 0.68 * h - th / 2, z0 + 0.68 * h + th / 2)]
    a, half, zf = math.radians(25), 0.2 * h, z0 + 0.3 * h
    along, perp = (math.cos(a), -math.sin(a)), (math.sin(a), math.cos(a))
    polys.append([(sa * half * along[0] + sp * th / 2 * perp[0], zf + sa * half * along[1] + sp * th / 2 * perp[1])
                  for sa, sp in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    return [bk.extrude("cross", fr, p, -th / 2, th / 2, M["gold"]) for p in polys]


def cross4(z0, h, th=0.07):
    """Четырёхконечный крест с расширенными концами (Ольгинская, фото S-60): перекладина вдоль v на 0,68 высоты."""
    fr = bk.Frame(C, (0.0, 1.0), (1.0, 0.0))
    w, zb = 0.33 * h, z0 + 0.68 * h
    polys = [bk.rect(-th / 2, th / 2, z0, z0 + h), bk.rect(-w, w, zb - th / 2, zb + th / 2),
             bk.rect(-th, th, z0 + h - 0.1, z0 + h), bk.rect(-w, -w + 0.1, zb - th, zb + th),
             bk.rect(w - 0.1, w, zb - th, zb + th)]
    return [bk.extrude("cross", fr, p, -th / 2, th / 2, M["gold"]) for p in polys]


# ---------- часовня св. Анастасии (Щусев, 1911) ----------

A_RIDGE = 0.75           # подъём коньков от щипца к барабану (фото ana_13, ana_35: барабан выходит из кровли выше щипцов)
A_OVER = 0.3             # вынос кровли за стены (фото ana_35: щипцы и углы кровли далеко выступают)
A_PIL = ((-0.06, 0.44), (0.54, 0.98))   # угловая пара пилястр: s от угла (фото ana_13, ana_14; S-58 «угловые пары»)
# луковица: (доля высоты от юбки до острия, радиус в долях наибольшего) — вытянутая, с долгим острием (фото ana_13)
ONION_A = ((0.0, 0.66), (0.06, 0.8), (0.14, 0.93), (0.23, 0.995), (0.3, 1.0), (0.38, 0.96), (0.47, 0.84),
           (0.56, 0.64), (0.65, 0.43), (0.74, 0.27), (0.83, 0.16), (0.92, 0.09), (1.0, 0.05))


def a_roof_z(c, u, v):
    """Кровля по четырём щипцам: вершины щипцов на z_gable, углы — на z_eave, коньки поднимаются к центру на A_RIDGE."""
    h = c.side / 2
    lo, hi = min(abs(u), abs(v)), max(abs(u), abs(v))
    return c.z_eave + (c.z_gable - c.z_eave) * (1 - lo / h) + A_RIDGE * (1 - hi / h)


def a_ring(c, h, dz=0.0):
    """Кольцо кровли над квадратом ±h: углы и вершины щипцов через одну, против часовой (u — восток, v — юг)."""
    pts = [(h, -h), (h, 0.0), (h, h), (0.0, h), (-h, h), (-h, 0.0), (-h, -h), (0.0, -h)]
    return [(u, v, a_roof_z(c, u, v) + dz) for u, v in pts]


def a_body(c):
    """Стены до кровли: четверик с щипцами, верх — по плоскостям кровли (восемь треугольников к центру)."""
    h = c.side / 2
    top = a_ring(c, h)
    verts = top + [(0.0, 0.0, a_roof_z(c, 0.0, 0.0))] + [(u, v, BASE_Z) for u, v in ((h, -h), (h, h), (-h, h), (-h, -h))]
    fs = [[i, (i + 1) % 8, 8] for i in range(8)]
    fs += [[9, 10, 2, 1, 0], [10, 11, 4, 3, 2], [11, 12, 6, 5, 4], [12, 9, 0, 7, 6], [9, 10, 11, 12]]
    return bk.mesh("walls", verts, fs, M["wall"])


def a_frieze(op, fr, s0, z0):
    """Пояс «бегунца и поребрика» (S-57) под щипцом: ряд квадратиков, треугольники вниз и вверх, ряд квадратиков
    (фото ana_13, ana_15). s0 — середина, z0 — низ пояса; глубина 5 см."""
    def cut(poly):
        op.cutters.append(bk.extrude("cut", fr, poly, -0.05, 0.3, M["wall"]))
    for i in range(10):
        s = s0 + 0.145 * (i - 4.5)
        cut(bk.rect(s - 0.04, s + 0.04, z0 + 0.45, z0 + 0.54))
    for i in range(7):
        s = s0 + 0.2 * (i - 3)
        cut([(s - 0.085, z0 + 0.39), (s + 0.085, z0 + 0.39), (s, z0 + 0.26)])
        cut(bk.rect(s - 0.035, s + 0.035, z0, z0 + 0.08))
    for i in range(6):
        s = s0 + 0.2 * (i - 2.5)
        cut([(s - 0.085, z0 + 0.12), (s + 0.085, z0 + 0.12), (s, z0 + 0.245)])


def a_walls(c):
    """Стены, цоколь, угловые пары пилястр; проёмы по S-58: дверь с запада, окна со ставнями с юга и севера;
    на востоке — доска 1911 г. в нише; под щипцами юга, севера и востока — пояс треугольников; киот над дверью."""
    h, e = c.side / 2, c.z_eave
    body = a_body(c)
    op, parts = Openings(recess=0.25), []
    fr = faces(h)
    for side, f in fr.items():
        L = f.length
        for s0, s1 in A_PIL:                          # пары пилястр у обоих углов, вынос 6 см
            for a0, a1 in ((s0, s1), (L - s1, L - s0)):
                top = e + (c.z_gable - e) * min(a0, L - a1) / h - 0.07
                parts.append(bk.extrude("pilaster", f, [(a0, 0.1), (a1, 0.1), (a1, top), (a0, top)], -0.1, 0.06,
                                        M["wall"]))
        for a0, a1 in ((A_PIL[0][1], A_PIL[1][0]), (L - A_PIL[1][0], L - A_PIL[0][1])):   # перемычки паза
            for z0, z1 in ((0.1, 0.35), (e - 0.3, e - 0.07)):
                parts.append(bk.extrude("pilaster", f, bk.rect(a0, a1, z0, z1), -0.1, 0.06, M["wall"]))
        if side != "W":
            a_frieze(op, f, L / 2, 2.95)
    # запад: двустворчатая дверь с полуциркульным верхом, над ней киот со ступенчатым верхом (фото ana_14, ana_43)
    w = fr["W"]
    op.cutters.append(bk.extrude("cut", w, bk.arch(h, 1.2, 0.12, 1.62), -0.25, 0.3, M["wall"]))
    parts.append(bk.extrude("door", w, bk.arch(h, 1.2, 0.12, 1.62), -0.26, -0.2, M["green"]))
    parts.append(bk.extrude("door_frame", w, bk.arch_frame(h, 1.2, 0.12, 1.62, 0.07), -0.05, 0.03, M["wall"]))
    kiot = [(-0.26, 2.85), (0.26, 2.85), (0.26, 3.42), (0.17, 3.42), (0.17, 3.54), (0.08, 3.54), (0.08, 3.64),
            (-0.08, 3.64), (-0.08, 3.54), (-0.17, 3.54), (-0.17, 3.42), (-0.26, 3.42)]
    op.cutters.append(bk.extrude("cut", w, [(h + s, z) for s, z in kiot], -0.1, 0.3, M["wall"]))
    for s in (-0.34, 0.34):
        parts.append(bk.extrude("kiot_post", w, bk.rect(h + s - 0.035, h + s + 0.035, 2.85, 3.42), -0.05, 0.03,
                                M["wall"]))
    # юг и север: окно со ставнями, продух под поясом и у земли (фото ana_15, ana_44)
    for side in ("S", "N"):
        f = fr[side]
        op.cutters.append(bk.extrude("cut", f, bk.rect(h - 0.45, h + 0.45, 1.27, 2.37), -0.25, 0.3, M["wall"]))
        parts.append(bk.extrude("shutters", f, bk.rect(h - 0.44, h + 0.44, 1.28, 2.36), -0.06, -0.01, M["green"]))
        for poly in (bk.arch(h, 0.12, 2.7, 2.8), bk.rect(h - 0.085, h + 0.085, 0.35, 0.52)):
            op.cutters.append(bk.extrude("cut", f, poly, -0.2, 0.3, M["wall"]))
            parts.append(bk.extrude("vent", f, poly, -0.22, -0.18, M["glass"]))
    # восток: памятная доска 1911 г. в нише с полуциркульным верхом (фото ana_13, S-58)
    op.cutters.append(bk.extrude("cut", fr["E"], bk.arch(h, 0.62, 0.9, 1.6), -0.06, 0.3, M["wall"]))
    parts.append(bk.extrude("plaque", fr["E"], bk.arch(h, 0.54, 0.95, 1.6), -0.07, -0.03, M["stone"]))
    parts.append(bk.band(-h, h, -h, h, BASE_Z, 0.12, 0.09))                     # цоколь (1971, S-58)
    return op.apply(body) + parts


def a_top(c):
    """Кровля по щипцам (зелёная жесть), барабан с поясом треугольничков (S-58), юбка, луковица, яблоко, крест."""
    h = c.side / 2
    ho = h + A_OVER
    zc = a_roof_z(c, 0.0, 0.0)
    t = 0.07
    # плита толщиной t по тем же плоскостям; на выносе края опускаются по формуле a_roof_z — как свес на фото
    parts = [bk.loft("roof", [[(0.0, 0.0, zc - 0.02)], a_ring(c, ho, -0.02), a_ring(c, ho, t), [(0.0, 0.0, zc + t)]],
                     M["green"])]
    dd, z_drum = c.drum
    r = dd / 2
    drum = bk.lathe("drum", C, [(r, zc - 0.4), (r, z_drum)], M["wall"], seg=40)
    op = Openings()
    for k in range(10):                                  # пояс треугольников остриём вниз (фото ana_13, ana_44)
        fr = bk.Frame.radial(C, r, 2 * math.pi * (k + 0.5) / 10)
        op.cutters.append(bk.extrude("cut", fr, [(-0.075, z_drum - 0.11), (0.075, z_drum - 0.11), (0.0, z_drum - 0.25)],
                                     -0.05, 0.3, M["wall"]))
    parts += op.apply(drum)
    od, z0, z1 = c.dome
    parts.append(bk.lathe("collar", C, [(r - 0.06, z_drum - 0.03), (od / 2 + 0.05, z_drum), (od / 2 + 0.05, z_drum + 0.05),
                                        (r + 0.06, z_drum + 0.09), (r - 0.06, z_drum + 0.09)],
                          M["green"], seg=48, closed=True, smooth=False))
    parts.append(bk.lathe("onion", C, [(q * od / 2, z0 + t_ * (z1 - z0)) for t_, q in bk.spline(ONION_A)] + [(0.0, z1)],
                          M["green"], seg=48))
    parts.append(ball(z1 - 0.02, 0.065))
    parts += cross8(z1 + 0.1, c.z_top - z1 - 0.1)
    return parts


def anastasia(c):
    return a_walls(c) + a_top(c)


# ---------- Ольгинская часовня (Красильников, 2000) ----------

O_FILL = 0.2             # угловые части отступают от торцов рукавов (план — крест, S-61; величина — гип.)
O_NICHE = (1.85, 6.0, 0.12)   # ниша-портал в закомаре: ширина, верх арки, глубина (фото olg_61, olg_60)
O_HOOD = (1.5, 6.5)      # кровли угловых частей: от карниза поднимаются к барабану до отметки 6,5 на «апофеме» 1,5
# шлем: (доля высоты главы, радиус в долях наибольшего) — невысокий, чуть заострённый (фото olg_60)
HELMET = ((0.0, 1.0), (0.1, 0.995), (0.2, 0.975), (0.3, 0.94), (0.4, 0.885), (0.5, 0.81), (0.6, 0.71), (0.7, 0.58),
          (0.8, 0.43), (0.88, 0.28), (0.94, 0.15), (0.98, 0.06), (1.0, 0.0))


def o_bars(c):
    """Два рукава креста насквозь (запад — восток и север — юг): сечение — закомара (полуциркуль на стенах)."""
    H, a = c.side / 2, c.arm / 2
    zs = c.z_gable - a
    ew = bk.Frame((-H, 0.0), (0.0, 1.0), (1.0, 0.0))   # s — по v, d — по u
    ns = bk.Frame((0.0, -H), (1.0, 0.0), (0.0, 1.0))   # s — по u, d — по v
    prof = bk.arch(0.0, 2 * a, BASE_Z, zs, n=24)
    return [bk.extrude("arm_ew", ew, prof, 0.0, 2 * H, M["wall"]), bk.extrude("arm_ns", ns, prof, 0.0, 2 * H, M["wall"])]


def o_walls(c):
    """Рукава с нишами-порталами в закомарах: запад — дверь и окно над ней, юг и север — высокое окно и плита
    с надписью, восток — горельеф св. Ольги (S-61, фото olg_60, olg_61); угловые части ниже рукавов; цоколь из
    чёрного камня."""
    H, a = c.side / 2, c.arm / 2
    ew, ns = o_bars(c)
    fr = faces(H, a)
    wn, top, dn = O_NICHE
    niche_spring = top - wn / 2
    parts = []
    for body, sides in ((ew, ("W", "E")), (ns, ("S", "N"))):
        bk.cut(body, [bk.extrude("cut", fr[s], bk.arch(a, wn, 0.25, niche_spring), -dn, 0.5, M["wall"]) for s in sides])
        op = Openings(recess=0.3)
        for side in sides:
            f, n = fr[side], inward(fr[side], dn)
            if side == "W":
                op.cutters.append(bk.extrude("cut", n, bk.arch(a, 1.0, 0.25, 2.5), -0.3, 0.6, M["wall"]))
                op.parts.append(bk.extrude("door", n, bk.arch(a, 1.0, 0.25, 2.5), -0.32, -0.26, M["dark"]))
                op.parts.append(bk.extrude("door_frame", n, bk.arch_frame(a, 1.0, 0.25, 2.5, 0.08), -0.05, 0.04,
                                           M["wall"]))
                op.window(n, a, 0.42, 3.95, 5.16, frame=False)
            elif side == "E":                             # горельеф в нише с полуциркульным верхом и полочка под ним
                op.cutters.append(bk.extrude("cut", n, bk.arch(a, 0.8, 1.85, 4.75), -0.08, 0.6, M["wall"]))
                op.parts.append(bk.extrude("relief", n, [(a + s, z) for s, z in olga_figure(1.95, 4.95)], -0.1, 0.05,
                                           M["wall"]))
                op.parts.append(bk.extrude("console", n, bk.rect(a - 0.38, a + 0.38, 1.6, 1.8), -0.05, 0.12, M["wall"]))
            else:
                op.window(n, a, 0.38, 3.1, 5.35, frame=False)
                op.parts.append(bk.extrude("plaque", n, bk.rect(a - 0.3, a + 0.3, 1.5, 2.3), -0.02, 0.03, M["stone"]))
        parts += op.apply(body)
    zf = c.z_eave
    q = H - O_FILL
    for su in (-1, 1):                                    # угловые части и цоколь
        for sv in (-1, 1):
            u0, u1 = sorted((su * (a - 0.1), su * q))
            v0, v1 = sorted((sv * (a - 0.1), sv * q))
            parts.append(bk.box("corner", u0, u1, v0, v1, BASE_Z, zf, M["wall"]))
            parts.append(bk.band(u0, u1, v0, v1, BASE_Z, 0.25, 0.05, "dark"))
    parts.append(bk.band(-H, H, -a, a, BASE_Z, 0.25, 0.05, "dark"))
    parts.append(bk.band(-a, a, -H, H, BASE_Z, 0.25, 0.05, "dark"))
    return parts


def olga_figure(z0, z1):
    """Силуэт горельефа: святая в рост в длинных одеждах, голова в нимбе; s — от оси ниши."""
    hgt = z1 - z0
    k = [(0.2, 0.0), (0.24, 0.05), (0.22, 0.45), (0.2, 0.68), (0.18, 0.78), (0.08, 0.82)]
    right = [(s, z0 + t * hgt) for s, t in k]
    rc, zc = 0.17, z0 + 0.9 * hgt
    halo = [(rc * math.cos(a), zc + rc * math.sin(a)) for a in [math.radians(-60 + 300 * i / 16) for i in range(17)]]
    return right + halo + [(-s, z) for s, z in reversed(right)]


def o_roofs(c):
    """Кровли тёмной жестью: своды рукавов по закомарам со свесом, кровли угловых частей — от карниза вверх к барабану
    (сомкнутый свод, вырезанный рукавами), желоба и водомёты у пят закомар, фартук у барабана."""
    H, a = c.side / 2, c.arm / 2
    zs = c.z_gable - a
    parts = []
    for fr in (bk.Frame((-H - 0.06, 0.0), (0.0, 1.0), (1.0, 0.0)), bk.Frame((0.0, -H - 0.06), (1.0, 0.0), (0.0, 1.0))):
        parts.append(bk.extrude("vault_roof", fr, bk.arch_frame(0.0, 2 * a, zs - 0.25, zs, 0.07, n=24), 0.0,
                                2 * H + 0.12, M["dark"]))
    # угловые кровли: четверть эллипса от карниза (апофема H − O_FILL + 0,02) вверх до O_HOOD
    q_e, (q_top, z_top) = H - O_FILL + 0.02, O_HOOD
    prof = [(0.0, c.z_eave - 0.02)]
    for i in range(13):
        th = math.pi / 2 * (1 - i / 12)
        prof.append((q_top + (q_e - q_top) * math.sin(th), c.z_eave + (z_top - c.z_eave) * math.cos(th)))
    prof.append((0.0, z_top))
    hood = bk.nlathe("corner_roof", C, prof, M["dark"], 4)
    for bar in o_bars(c):                                 # убрать внутри рукавов — остаются угловые части и полосы
        bk.cut(hood, [bar])                                # над сводами у барабана
    parts.append(hood)
    q = H - O_FILL
    for su in (-1, 1):
        for sv in (-1, 1):                                # желоба по карнизам угловых частей
            for (u0, u1, v0, v1) in ((q, q + 0.12, a, q + 0.12), (a, q + 0.12, q, q + 0.12)):
                us = sorted((su * u0, su * u1))
                vs = sorted((sv * v0, sv * v1))
                parts.append(bk.box("gutter", *us, *vs, c.z_eave - 0.06, c.z_eave + 0.05, M["dark"]))
            for along_u in (True, False):                 # водомёты у пят закомар — вбок вдоль фасада
                if along_u:
                    us, vs = sorted((su * (H - 0.05), su * (H + 0.08))), sorted((sv * a, sv * (a + 0.4)))
                else:
                    us, vs = sorted((su * a, su * (a + 0.4))), sorted((sv * (H - 0.05), sv * (H + 0.08)))
                parts.append(bk.box("spout", *us, *vs, zs - 0.3, zs - 0.2, M["dark"]))
    r = c.drum[0] / 2
    parts.append(bk.lathe("drum_apron", C, [(r - 0.1, 5.8), (2.3, 6.42), (r, 6.68), (0.0, 6.68)], M["dark"], seg=48,
                          smooth=False))
    return parts


def o_drum(c):
    """Световой барабан: четыре узких окна по осям, аркатура под карнизом (12 арочек, фото olg_60, olg_61),
    карниз, шлемовидная глава (S-61), яблоко и крест."""
    dd, z1 = c.drum
    r = dd / 2
    drum = bk.lathe("drum", C, [(r, 6.2), (r, z1 - 0.2)], M["wall"], seg=64)
    op = Openings(recess=0.3)
    for k in range(4):
        op.window(bk.Frame.radial(C, r, k * math.pi / 2), 0.0, 0.36, z1 - 1.95, z1 - 0.98, frame=False)
    parts = op.apply(drum)
    band = bk.lathe("arcature", C, [(r - 0.06, z1 - 0.62), (r + 0.06, z1 - 0.62), (r + 0.06, z1 - 0.18),
                                    (r - 0.06, z1 - 0.18)], M["wall"], seg=72, closed=True, smooth=False)
    bk.cut(band, [bk.extrude("cut", bk.Frame.radial(C, r + 0.06, 2 * math.pi * k / 12),
                             bk.arch(0.0, 0.56, z1 - 0.7, z1 - 0.58), -0.13, 0.3, M["wall"]) for k in range(12)])
    parts.append(band)
    parts.append(bk.lathe("drum_cornice", C, [(r - 0.1, z1 - 0.2), (r + 0.1, z1 - 0.2), (r + 0.1, z1 - 0.09),
                                              (r + 0.16, z1 - 0.09), (r + 0.16, z1), (r - 0.1, z1)],
                          M["wall"], seg=64, closed=True, smooth=False))
    od, z0, zt = c.dome
    parts.append(bk.lathe("helmet", C, [(0.0, z0 - 0.02)] + [(q * od / 2, z0 + t * (zt - z0)) for t, q in bk.spline(HELMET)],
                          M["dark"], seg=64))
    parts.append(bk.lathe("spire", C, [(0.05, zt - 0.05), (0.03, zt + 0.1), (0.0, zt + 0.1)], M["dark"], seg=12))
    parts.append(ball(zt + 0.02, 0.1))
    parts += cross4(zt + 0.2, c.z_top - zt - 0.2)
    return parts


def olga(c):
    return o_walls(c) + o_roofs(c) + o_drum(c)


# ---------- сборка ----------

BUILD = {"Anastasia": anastasia, "Olga": olga}

VIEWS = {  # превью: глаз, цель (u, v, z), кадр, фокус — с тех же сторон, что фото S-60 для сравнения
    "Anastasia": {
        "west": ((-12.0, 0.0, 1.4), (0.0, 0.0, 4.6), (960, 1280), 35.0),          # ana_14, ana_43: дверь
        "east": ((12.0, 0.0, 1.4), (0.0, 0.0, 4.6), (960, 1280), 35.0),           # ana_13: доска и пояс
        "south": ((1.5, 11.0, 1.4), (0.0, 0.0, 4.4), (960, 1280), 35.0),          # ana_15, ana_44: окно
        "southwest_high": ((-8.0, 7.5, 9.0), (0.0, 0.0, 4.0), (960, 1280), 35.0),  # ana_35: с лестницы моста
    },
    "Olga": {
        "west": ((-14.0, 0.0, 1.5), (0.0, 0.0, 5.8), (960, 1280), 35.0),           # olg_61: дверь
        "northeast_far": ((95.0, -95.0, 3.0), (0.0, 0.0, 6.0), (960, 1280), 200.0),  # olg_60: из-под Крома через реку
        "southwest": ((-8.0, 9.0, 1.5), (0.0, 0.0, 5.5), (960, 1280), 35.0),       # olg_56
        "high": ((-18.0, 14.0, 14.0), (0.0, 0.0, 5.5), (1280, 960), 35.0),
    },
}


def build(c):
    name = c.hero.rsplit("/", 1)[1]
    bk.reset_scene()
    bk.use_colors(krom_plan.COLORS)
    objs = BUILD[c.key](c)
    obj = bk.join(objs, name)
    bk.box_uv(obj)
    me = obj.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    print(f"[chapels] {c.name}: {len(objs)} тел → {name}: {len(me.vertices)} вершин, {len(me.polygons)} граней "
          f"({tris} треугольников), слоты {[m.name for m in me.materials]}")
    bk.export_glb(obj, name)
    ground = bk.box("ground", -60, 60, -60, 60, -0.05, 0.0, bk.material("ground", (0.12, 0.16, 0.08)))  # только превью
    ground.hide_select = True
    for view, (eye, target, size, lens) in VIEWS[c.key].items():
        bk.render_preview(f"chapel_{c.key}_{view}", eye=(eye[0], -eye[1], eye[2]),
                          target=(target[0], -target[1], target[2]), size=size, lens=lens)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    todo = [c for c in krom_plan.CHAPELS if not argv or c.key in argv]
    if not todo:
        raise SystemExit(f"[chapels] нет часовни {argv}; есть: {[c.key for c in krom_plan.CHAPELS]}")
    for c in todo:
        build(c)


main()
