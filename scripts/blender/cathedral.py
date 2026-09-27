"""cathedral.py — Троицкий собор, герой M3: модель скриптом Blender по krom_plan.TRINITY (D-018).

    python scripts/bl_run.py scripts/blender/cathedral.py

Выгрузка — build/blender/SM_TrinityCathedral.glb (в UE ставит scripts/heroes_krom.py), превью —
media/renders/blender/cathedral_*.png. Массы, высоты и главы берутся из TRINITY, источники записаны там. Здесь
только детали, снятые с фото S-25 «на глаз»: окна с наличниками, лопатки, пояса, аркатура, контрфорсы, профиль луковиц.
Оси здания: u — на восток по оси храма, v — к югу, z — от земли в начале координат (центроид OSM).
Материалы — слоты по ключам krom_plan.COLORS (в UE пока MI_BO_*, свои — в M4).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402
import krom_plan  # noqa: E402
from bl_krom import M, Openings, band, cornice, spline  # noqa: E402

T = krom_plan.TRINITY
NAME = "SM_TrinityCathedral"
BASE_Z = -3.0            # низ стен: Кром не плоский, здание уходит в землю
RECESS = 0.5             # глубина проёма до стекла (как у bk.Openings по умолчанию)


def arcature(fr, n, z_legs, z_top, gap=0.8, ring=0.28):
    """Аркатура: n полуциркульных арок-валиков по длине фасада, ноги до z_legs, верх арок на z_top,
    между арками — гирьки."""
    half = fr.length / n
    w = half - gap
    spring = z_top - w / 2 - ring
    parts = []
    for i in range(n):
        parts.append(bk.extrude("arch", fr, bk.arch_frame((i + 0.5) * half, w, z_legs, spring, ring), -0.1, 0.16,
                                M["wall"]))
    for i in range(1, n):
        sj = i * half
        parts.append(bk.extrude("girka", fr, bk.rect(sj - 0.17, sj + 0.17, spring - 0.55, spring + 0.1), -0.1, 0.2,
                                M["wall"]))
    return parts


# ---------- четверик ----------

def quad_faces():
    """Фасады четверика; s — слева направо, если смотреть снаружи."""
    (u0, u1), v = T.quad_u, T.quad_v
    c = ((u0 + u1) / 2, 0.0)
    return {"W": bk.Frame.between((u0, -v), (u0, v), c), "N": bk.Frame.between((u1, -v), (u0, -v), c),
            "E": bk.Frame.between((u1, v), (u1, -v), c), "S": bk.Frame.between((u0, v), (u1, v), c)}


def quad():
    (u0, u1), v = T.quad_u, T.quad_v
    op, parts = Openings(), []
    for side, fr in quad_faces().items():
        n = T.bays[0] if side in "NS" else T.bays[1]
        bay = fr.length / n
        for i in range(n):
            s = (i + 0.5) * bay
            east_bay = (side == "N" and i == 0) or (side == "S" and i == n - 1)
            if side != "E" and not east_bay:  # нижний ярус: на востоке его закрывают апсиды, в восточных пряслах — приделы
                op.window(fr, s, 2.0, 16.6, 19.8, hood=True)
            op.window(fr, s, 2.0, 25.0, 28.0, hood=True)
        for i in range(n + 1):  # лопатки: по границам прясел и на углах (угловые сходятся в «уголок»)
            s0, s1 = (-0.25, 1.1) if i == 0 else (fr.length - 1.1, fr.length + 0.25) if i == n else \
                (i * bay - 0.6, i * bay + 0.6)
            parts.append(bk.extrude("lopatka", fr, bk.rect(s0, s1, 13.0, T.z_cornice - 0.5), -0.1, 0.25, M["wall"]))
        parts += arcature(fr, 2 * n, T.z_cornice, T.z_eaves - 0.9)
    body = bk.box("quad", u0, u1, -v, v, BASE_Z, T.z_eaves, M["wall"])
    parts += band(u0, u1, -v, v, T.z_belt - 0.2, T.z_belt + 0.2, 0.3), band(u0, u1, -v, v, T.z_belt + 0.2,
                                                                          T.z_belt + 0.25, 0.33, "green")
    parts += cornice(u0, u1, -v, v, T.z_cornice, 0.5, 0.4)
    parts += cornice(u0, u1, -v, v, T.z_eaves, 0.7, 0.55, flash=False)
    parts.append(bk.hip_roof("roof", u0 - 0.7, u1 + 0.7, -v - 0.7, v + 0.7, T.z_eaves, T.roof_rise, 0.3, M["green"]))
    return op.apply(body) + parts


# ---------- гульбище, приделы, апсиды, крыльцо, контрфорсы ----------

GAL_UPPER = (1.5, 7.6, 9.2)   # окна гульбища: ширина, низ, пята арки — второй этаж
GAL_LOWER = (1.1, 1.6, 2.6)   # подклет
GAL_WINDOWS_S = (-16.9, -11.9, -6.9, 3.25, 13.85)   # u окон в промежутках между контрфорсами (13,85 — на приделе)
GAL_WINDOWS_N = (-16.9, -11.9, -6.9)                # дальше на восток — большой северный контрфорс


def gallery():
    t = T
    ue = t.prid_u[0] + 0.1          # дальше на восток — приделы
    vi = t.quad_v - 0.5
    body = bk.prism("gallery", [(t.gal_u, -t.gal_v), (ue, -t.gal_v), (ue, -vi), (t.quad_u[1] - 0.5, -vi),
                                (t.quad_u[1] - 0.5, vi), (ue, vi), (ue, t.gal_v), (t.gal_u, t.gal_v)],
                    BASE_Z, t.z_gal, M["wall"])
    op, parts = Openings(), []
    c = (0.0, 0.0)
    west = bk.Frame.between((t.gal_u, -t.gal_v), (t.gal_u, t.gal_v), c)       # s = v + gal_v
    for v in (-14.0, -8.2, 8.2, 14.0):
        for w, sill, spring in (GAL_UPPER, GAL_LOWER):
            op.window(west, v + t.gal_v, w, sill, spring)
    for sgn, us in ((-1, GAL_WINDOWS_N), (1, GAL_WINDOWS_S)):
        side = bk.Frame.between((t.gal_u, sgn * t.gal_v), (ue, sgn * t.gal_v), c)  # s = u − gal_u
        for u in us:
            for w, sill, spring in (GAL_UPPER, GAL_LOWER):
                op.window(side, u - t.gal_u, w, sill, spring)
    parts += [band(t.gal_u, ue, -t.gal_v, t.gal_v, 6.9, 7.25, 0.12),
              band(t.gal_u, ue, -t.gal_v, t.gal_v, BASE_Z, 0.6, 0.15),
              band(t.gal_u, ue, -t.gal_v, t.gal_v, t.z_gal - 0.5, t.z_gal, 0.45)]
    # кровля: три ската от стен четверика (z_gal_roof) к карнизу; углы — вальмами
    oh, zo, zi = 0.45, t.z_gal + 0.05, t.z_gal_roof
    q0, qv, go, gv = t.quad_u[0], t.quad_v, t.gal_u - oh, t.gal_v + oh
    parts.append(bk.slab("roof_w", [(q0, -qv, zi), (q0, qv, zi), (go, gv, zo), (go, -gv, zo)], 0.25, M["green"]))
    for sgn in (-1, 1):
        parts.append(bk.slab("roof_side", [(q0, sgn * qv, zi), (t.prid_u[0], sgn * qv, zi),
                                           (t.prid_u[0], sgn * gv, zo), (go, sgn * gv, zo)], 0.25, M["green"]))
    return op.apply(body) + parts


def pridel(sgn):
    """Придел в восточном конце северной (sgn = −1) или южной (+1) галереи: выше гульбища, с главкой."""
    t = T
    u0, u1 = t.prid_u
    vi, vo = t.quad_v - 0.3, t.gal_v + 0.1      # наружная стена на 10 см впереди стены гульбища
    v0, v1 = sorted((sgn * vi, sgn * vo))
    c = ((u0 + u1) / 2, sgn * (vi + vo) / 2)
    outer = bk.Frame.between((u0, sgn * vo), (u1, sgn * vo), c)     # s = u − u0
    east = bk.Frame.between((u1, sgn * t.quad_v), (u1, sgn * vo), c)  # s = |v| − quad_v
    op, parts = Openings(), []
    for u in (x for x in (GAL_WINDOWS_S if sgn > 0 else GAL_WINDOWS_N) if x > u0):
        for w, sill, spring in (GAL_UPPER, GAL_LOWER):
            op.window(outer, u - u0, w, sill, spring)
    op.window(outer, (u1 - u0) / 2, 1.5, 15.2, 17.6)
    op.window(east, east.length / 2, 1.5, 15.2, 17.6)
    body = bk.box("pridel", u0, u1, v0, v1, BASE_Z, t.z_prid - 0.6, M["wall"])
    top = t.z_prid - 0.6
    parts += arcature(outer, 2, top - 2.6, top - 0.2, gap=1.0) + arcature(east, 2, top - 2.6, top - 0.2, gap=0.8)
    pv0, pv1 = sorted((sgn * t.quad_v, sgn * vo))
    parts += cornice(u0, u1, pv0, pv1, t.z_prid, 0.6, 0.4, flash=False)
    parts.append(band(u0, u1, pv0, pv1, BASE_Z, 0.6, 0.15))
    parts.append(bk.hip_roof("roof", u0 - 0.4, u1 + 0.4, pv0 - 0.4, pv1 + 0.4, t.z_prid, 1.4, 0.25, M["green"]))
    r = t.prid_apse                             # апсида придела — полукруг на восток, ниже самого придела (фото)
    parts += apse(u1, sgn * 15.4 - r, sgn * 15.4 + r, r, 14.0, ((0.0, 1.1, 8.0, 9.6), (0.0, 0.9, 1.8, 2.7)))
    return op.apply(body) + parts


def apse(u, va, vb, p, z_top, windows):
    """Апсида от стены u (хорда va…vb) с выносом p: в плане сегмент круга, конический скат, карниз.
    windows — [(угол от оси апсиды, ширина, низ, пята)]."""
    chord = vb - va
    r = (chord * chord / 4 + p * p) / (2 * p)
    center = (u + p - r, (va + vb) / 2)

    def seg_poly(rr, n=24):
        phi = math.acos(min(1.0, (r - p) / rr))
        return [(u - 0.3, center[1] - rr * math.sin(phi))] +             [(center[0] + rr * math.cos(a), center[1] + rr * math.sin(a))
             for a in (-phi + 2 * phi * k / n for k in range(n + 1))] + [(u - 0.3, center[1] + rr * math.sin(phi))]

    body = bk.prism("apse", seg_poly(r), BASE_Z, z_top - 0.6, M["wall"])
    op = Openings()
    for a, w, sill, spring in windows:
        op.window(bk.Frame.radial(center, r, a), 0.0, w, sill, spring)
    ro = r + 0.45
    phi_r = math.acos((r - p) / ro)
    parts = [bk.prism("apse_cornice", seg_poly(r + 0.35), z_top - 0.6, z_top, M["wall"]),
             bk.prism("apse_plinth", seg_poly(r + 0.15), BASE_Z, 0.6, M["wall"]),
             bk.lathe("apse_roof", center, [(0.0, z_top), (ro, z_top), (0.0, z_top + ro * math.tan(math.radians(12)))],
                      M["green"], seg=24, closed=True, arc=(-phi_r, phi_r))]
    return op.apply(body) + parts


def apses():
    """Три апсиды четверика на всю ширину востока: центральная — полукруг ±apse_v, боковые — сегменты до углов."""
    t, u = T, T.quad_u[1]
    out = []
    for va, vb, p in ((-t.quad_v, -t.apse_v, t.apse[1]), (-t.apse_v, t.apse_v, t.apse[0]),
                      (t.apse_v, t.quad_v, t.apse[1])):
        r = ((vb - va) ** 2 / 4 + p * p) / (2 * p)
        angles = (0.0,) if p < t.apse[0] else (-math.asin(2.0 / r), math.asin(2.0 / r))
        out += apse(u, va, vb, p, t.z_prid, [(a, 1.2, 17.5, 19.6) for a in angles] +
                    [(a, 1.0, 2.4, 3.3) for a in angles])
    return out


def porch():
    """Западное крыльцо-всход (фото S-25 с дрона): крытая лестница на второй этаж гульбища. Боковые стены с косым
    верхом, кровля низкая и из-за них почти не видна. У гульбища сквозная арка с севера на юг, над ней наклонное
    окно лестницы. Посередине глухая арочная ниша с окном, у западного конца открытое крыльцо."""
    t = T
    u0, u1, va, vb = t.porch
    u1 += 0.3                                   # заходит в стену гульбища
    (w0, w1), rise = t.porch_z, 0.4             # верх стен на концах; конёк выше стен
    vm, length, width = (va + vb) / 2, u1 - u0, vb - va
    north = bk.Frame.between((u0, va), (u1, va), (u0, vm))   # s = u − u0
    south = bk.Frame.between((u0, vb), (u1, vb), (u0, vm))
    body = bk.extrude("porch", north, [(0, BASE_Z), (length, BASE_Z), (length, w1), (0, w0)], -width, 0.0, M["wall"])

    def top(s):
        return w0 + (w1 - w0) * s / length

    s_arch = length - 0.3 - 2.3                 # середина прохода: у стены гульбища остаётся столб
    cutters = [bk.extrude("cut", north, bk.arch(s_arch, 3.4, BASE_Z - 1, 2.4), -width - 0.5, 0.5, M["wall"]),
               bk.extrude("cut", north, bk.rect(0.9, 4.3, BASE_Z - 1, 3.2), -width - 0.5, 0.5, M["wall"])]
    parts = []
    s0, s1 = length - 4.6, length - 1.6         # наклонное окно лестницы над проходом
    stair = [(s0, top(s0) - 4.2), (s1, top(s1) - 4.2), (s1, top(s1) - 1.6), (s0, top(s0) - 1.6)]
    for fr in (north, south):
        cutters.append(bk.extrude("cut", fr, bk.arch(9.4, 4.4, 0.3, 1.9), -0.25, 0.5, M["wall"]))   # ниша
        cutters.append(bk.extrude("cut", fr, stair, -RECESS, 0.5, M["wall"]))
        parts.append(bk.extrude("glass", fr, stair, -RECESS - 0.05, -RECESS + 0.03, M["glass"]))
        parts.append(bk.extrude("glass", fr, bk.arch(9.4, 1.1, 1.2, 2.4), -0.3, -0.22, M["glass"]))  # окно в нише
    ua = u0 - 0.1
    ridge = [(ua, vm, w0 + rise + (w1 - w0) * (ua - u0) / length), (u1, vm, w1 + rise)]
    for v_eave in (va - 0.1, vb + 0.1):
        parts.append(bk.slab("porch_roof", ridge + [(u1, v_eave, w1 - 0.05), (ua, v_eave, w0 - 0.05)], 0.15,
                             M["roof"]))
    return [bk.cut(body, cutters)] + parts


def buttress(fr, s, w0, w1, proj, z_top, back=-0.3):
    """Контрфорс у стены fr: основание w0 × proj на BASE_Z, верх w1 у стены на z_top; скат — зелёный отлив."""
    b, head = BASE_Z, 0.6
    pts = [fr.p(s - w0 / 2, b, back), fr.p(s + w0 / 2, b, back), fr.p(s + w0 / 2, b, proj), fr.p(s - w0 / 2, b, proj),
           fr.p(s - w1 / 2, z_top, back), fr.p(s + w1 / 2, z_top, back), fr.p(s + w1 / 2, z_top, head),
           fr.p(s - w1 / 2, z_top, head)]
    body = bk.mesh("buttress", pts, [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6],
                                     [3, 0, 4, 7]], M["wall"])
    dz, dd = z_top - b, proj - head                # нормаль ската в осях (d, z): (dz, dd) / |…|
    k = 0.08 / math.hypot(dz, dd)
    slope = [(s - w0 / 2, b, proj), (s + w0 / 2, b, proj), (s + w1 / 2, z_top, head), (s - w1 / 2, z_top, head)]
    cap = [fr.p(ss, z, d) for ss, z, d in slope] + [fr.p(ss, z + k * dd, d + k * dz) for ss, z, d in slope]
    faces = [[0, 1, 2, 3], [4, 5, 6, 7]] + [[i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i] for i in range(4)]
    return [body, bk.mesh("buttress_cap", cap, faces, M["green"])]


def buttresses():
    """Контрфорсы TRINITY.buttresses: у стен гульбища (S, N) и перед апсидами (E — плоскость внутри апсид,
    тело уходит в них на 1,6 м, чтобы не было щелей между выпуклостями)."""
    t, out = T, []
    ue = t.quad_u[1] + 1.4
    frames = {"S": bk.Frame.between((t.gal_u, t.gal_v), (t.prid_u[1], t.gal_v), (0.0, 0.0)),
              "N": bk.Frame.between((t.gal_u, -t.gal_v), (t.prid_u[1], -t.gal_v), (0.0, 0.0)),
              "E": bk.Frame.between((ue, -30.0), (ue, 30.0), (0.0, 0.0))}
    for b in t.buttresses:
        s = b.at - (t.gal_u if b.side in "SN" else -30.0)
        out += buttress(frames[b.side], s, b.w, b.w - 0.6, b.proj, b.top, back=-1.6 if b.side == "E" else -0.3)
    return out


# ---------- главы ----------

# луковица: (доля высоты от барабана до яблока, радиус в долях наибольшего) — по фото S-25
ONION = ((0.00, 0.80), (0.05, 0.86), (0.12, 0.94), (0.22, 0.99), (0.32, 1.00), (0.42, 0.96), (0.52, 0.86),
         (0.62, 0.69), (0.72, 0.49), (0.81, 0.30), (0.89, 0.16), (0.95, 0.08), (1.00, 0.04))


def drum_detail(d):
    """Окна барабана относительно его верха: (число, ширина, низ, пята), пояс-база (низ, верх)."""
    top = d.drum_z[1]
    if d.drum_r > 3.3:                              # центральная
        return 8, 0.95, top - 7.5, top - 3.3, (top - 9.5, top - 8.6)
    if d.drum_r > 2.0:                              # боковые
        return 8, 0.8, top - 5.6, top - 2.4, (top - 7.4, top - 6.6)
    return 4, 0.4, top - 1.8, top - 1.0, (top - 2.4, top - 2.0)   # приделы


def cross(d, z0):
    """Восьмиконечный крест: перекладины поперёк оси храма (вдоль v), нижняя — северным концом вверх."""
    h = d.cross
    th = max(0.06, 0.045 * h)
    fr = bk.Frame((d.u, d.v), (0.0, 1.0), (1.0, 0.0))    # s — на юг, d — на восток
    polys = [bk.rect(-th / 2, th / 2, z0, z0 + h),
             bk.rect(-0.16 * h, 0.16 * h, z0 + 0.86 * h - th / 2, z0 + 0.86 * h + th / 2),
             bk.rect(-0.28 * h, 0.28 * h, z0 + 0.68 * h - th / 2, z0 + 0.68 * h + th / 2)]
    a, half, zf = math.radians(25), 0.18 * h, z0 + 0.3 * h
    along, perp = (math.cos(a), -math.sin(a)), (math.sin(a), math.cos(a))   # s < 0 (север) — выше
    polys.append([(sa * half * along[0] + sp * th / 2 * perp[0], zf + sa * half * along[1] + sp * th / 2 * perp[1])
                  for sa, sp in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    return [bk.extrude("cross", fr, p, -th / 2, th / 2, M["gold"]) for p in polys]


def dome(d):
    c, r, (z0, z1) = (d.u, d.v), d.drum_r, d.drum_z
    n, w, sill, spring, (b0, b1) = drum_detail(d)
    k = min(1.0, r / 3.0)                           # вынос карнизов у малых барабанов меньше
    body = bk.lathe("drum", c, [(r, z0), (r, z1 - 0.7 * k)], M["wall"], seg=48)
    op, parts = Openings(), []
    for i in range(n):
        a = 2 * math.pi * i / n
        op.window(bk.Frame.radial(c, r, a), 0.0, w, sill, spring, frame=r > 2.0)
        if r > 2.0:
            parts.append(bk.extrude("pilaster", bk.Frame.radial(c, r, a + math.pi / n),
                                    bk.rect(-0.2, 0.2, b1, z1 - 0.7), -0.1, 0.12, M["wall"]))
    parts.append(bk.lathe("drum_base", c, [(r - 0.2, b0), (r + 0.22 * k, b0), (r + 0.22 * k, b1), (r - 0.2, b1)],
                          M["wall"], seg=48, closed=True, smooth=False))
    parts.append(bk.lathe("drum_cornice", c, [(r - 0.2, z1 - 0.7 * k), (r + 0.3 * k, z1 - 0.7 * k),
                                              (r + 0.3 * k, z1 - 0.25 * k), (r + 0.12 * k, z1 - 0.25 * k),
                                              (r + 0.12 * k, z1), (r - 0.2, z1)],
                          M["wall"], seg=48, closed=True, smooth=False))
    rmax, ra = d.onion_d / 2, 0.05 * d.onion_d
    tip = d.apple - ra
    parts.append(bk.lathe("onion", c, [(q * rmax, z1 + t * (tip - z1)) for t, q in spline(ONION)], M[d.mat], seg=64))
    parts.append(bk.lathe("apple", c, [(ra * math.sin(math.pi * i / 12), d.apple - ra * math.cos(math.pi * i / 12))
                                       for i in range(13)], M["gold"], seg=24))
    parts += cross(d, d.apple + 0.6 * ra)
    return op.apply(body) + parts


# ---------- сборка ----------

VIEWS = {  # превью: глаз и цель в осях здания (u, v, z), размер кадра — как фото S-25 для сравнения
    "south": ((-3.0, 100.0, 30.0), (3.0, 0.0, 30.0), (1024, 1024)),        # с дрона на южный фасад
    "southwest": ((-85.0, 70.0, 14.0), (3.0, 0.0, 29.0), (1280, 720)),     # от Ольгинского моста
    "east": ((95.0, 4.0, 10.0), (14.0, 0.0, 33.0), (1024, 1024)),          # от Псковы
    "northeast_high": ((80.0, -75.0, 80.0), (3.0, 0.0, 22.0), (1280, 720)),
    "porch": ((-24.0, 42.0, 9.0), (-24.0, 0.0, 7.0), (1280, 720)),
}


def main():
    bk.reset_scene()
    bk.use_colors(krom_plan.COLORS)
    objs = quad() + gallery() + pridel(-1) + pridel(1) + apses() + porch() + buttresses()
    for d in T.domes:
        objs += dome(d)
    obj = bk.join(objs, NAME)
    bk.box_uv(obj)
    me = obj.data
    print(f"[cathedral] {len(objs)} тел → {NAME}: {len(me.vertices)} вершин, {len(me.polygons)} граней, "
          f"слоты {[m.name for m in me.materials]}")
    bk.export_glb(obj, NAME)
    ground = bk.box("ground", -150, 150, -150, 150, -0.05, 0.0, bk.material("ground", (0.12, 0.16, 0.08)))  # только превью
    ground.hide_select = True
    for name, (eye, target, size) in VIEWS.items():
        bk.render_preview(f"cathedral_{name}", eye=(eye[0], -eye[1], eye[2]), target=(target[0], -target[1], target[2]),
                          size=size, lens=35.0)


main()
