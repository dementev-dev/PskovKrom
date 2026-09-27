"""paromenye.py — церковь Успения с Пароменья и её звонница (Завеличье, у Ольгинского моста): модели скриптом
Blender по krom_plan.PAROMENYE и krom_plan.PAROMENYE_BELFRY (D-018, D-019).

    python scripts/bl_run.py scripts/blender/paromenye.py

Выгрузка — build/blender/SM_Paromenye.glb (храм) и build/blender/SM_ParomenyeBelfry.glb (звонница), в UE их ставит
scripts/heroes_krom.py; превью — media/renders/blender/paromenye_*.png (оба здания вместе, как стоят на месте).
Массы, высоты, главы и пролёты звона берутся из плана, источники записаны там. Здесь только детали «на глаз» по фото
S-54: лопатки и лопастные арочки четверика, окна, пояса и карнизы, профиль главы «с перехватом», утолщения столпов
звона, колокола, двери, лестница на звон.
Оси храма: u — на восток по оси храма, v — к югу, z — от земли в центре контура. Оси звонницы: u — на восток,
v — к югу, z — от земли у восточного фасада (PAROMENYE_BELFRY.base).
Материалы — слоты по ключам krom_plan.COLORS: побелка wall, кровли храма и главки приделов tin (оцинковка), глава и
кресты dark, кровля звонницы roof (на фото красно-коричневая, своего ключа нет), двери и балки wood, колокола bronze.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402
import krom_plan  # noqa: E402
from bl_krom import M, Openings, band  # noqa: E402

P = krom_plan.PAROMENYE
Z = krom_plan.PAROMENYE_BELFRY
NAME, NAME_BELFRY = "SM_Paromenye", "SM_ParomenyeBelfry"
BASE_Z = -2.0            # низ стен храма: земля под контуром от +0,7 (запад) до −1,0 м (юго-восток)
BASE_ZV = -1.5           # низ стен звонницы: к западу земля выше на 0,7 м


def rect_faces(u0, u1, v0, v1):
    """Фасады прямоугольника в плане; s — слева направо, если смотреть снаружи."""
    c = ((u0 + u1) / 2, (v0 + v1) / 2)
    return {"W": bk.Frame.between((u0, v0), (u0, v1), c), "N": bk.Frame.between((u1, v0), (u0, v0), c),
            "E": bk.Frame.between((u1, v1), (u1, v0), c), "S": bk.Frame.between((u0, v1), (u1, v1), c)}


def steps(u0, u1, v0, v1, rows, key="wall"):
    """Профилированный карниз: ступени [(z0, z1, вынос)] вокруг прямоугольника."""
    return [band(u0, u1, v0, v1, z0, z1, proud, key) for z0, z1, proud in rows]


def cross(u, v, z0, h, th=None):
    """Восьмиконечный крест: перекладины поперёк оси здания (вдоль v), нижняя — северным концом вверх (тёмный)."""
    th = th or max(0.05, 0.05 * h)
    fr = bk.Frame((u, v), (0.0, 1.0), (1.0, 0.0))
    polys = [bk.rect(-th / 2, th / 2, z0, z0 + h),
             bk.rect(-0.16 * h, 0.16 * h, z0 + 0.86 * h - th / 2, z0 + 0.86 * h + th / 2),
             bk.rect(-0.3 * h, 0.3 * h, z0 + 0.68 * h - th / 2, z0 + 0.68 * h + th / 2)]
    a, half, zf = math.radians(25), 0.18 * h, z0 + 0.3 * h
    along, perp = (math.cos(a), -math.sin(a)), (math.sin(a), math.cos(a))
    polys.append([(sa * half * along[0] + sp * th / 2 * perp[0], zf + sa * half * along[1] + sp * th / 2 * perp[1])
                  for sa, sp in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    return [bk.extrude("cross", fr, p, -th / 2, th / 2, M["dark"]) for p in polys]


def apple(u, v, z, r, key="dark"):
    return bk.lathe("apple", (u, v), [(r * math.sin(math.pi * i / 12), z + r - r * math.cos(math.pi * i / 12))
                                      for i in range(13)], M[key], seg=20)


# ---------- главы «с перехватом» ----------

# (высота над низом юбки, радиус) в диаметрах барабана — снято по фото dome (S-54, телеобъектив, почти без наклона):
# юбка шире барабана, над ней перехват уже барабана, раздутие, крутые плечи и тонкий вогнутый шпиль до яблока
ONION = ((0.0, 0.56), (0.05, 0.535), (0.106, 0.507), (0.177, 0.465), (0.23, 0.44), (0.319, 0.465), (0.39, 0.535),
         (0.46, 0.564), (0.53, 0.578), (0.6, 0.585), (0.674, 0.58), (0.745, 0.571), (0.816, 0.543), (0.887, 0.5),
         (0.957, 0.44), (1.028, 0.34), (1.099, 0.234), (1.17, 0.163), (1.24, 0.128), (1.31, 0.103), (1.38, 0.082),
         (1.45, 0.071), (1.52, 0.06), (1.6, 0.05))
R_MAX, H_APPLE = 0.585, 1.61     # наибольший радиус и яблоко: по ним профиль растягивается на onion_d и z_apple плана


def onion(c, drum_r, z_lip, onion_d, z_apple, key):
    kr, kh = onion_d / 2 / R_MAX, (z_apple - z_lip) / H_APPLE
    prof = [(drum_r * 0.9, z_lip - 0.04 * kh)] + [(r * kr, z_lip + h * kh) for h, r in bk.spline(ONION, 2)] + \
        [(0.0, z_apple + 0.02)]
    return bk.lathe("onion", c, prof, M[key], seg=48)


def main_dome():
    """Барабан с восемью щелевыми окнами под фронтончиками, двумя поясами орнамента (поребрик, бегунец — S-53) и
    карнизом под юбкой; глава с перехватом, яблоко, крест."""
    c, r = P.dome, P.drum_d / 2
    z1 = P.z_lip
    body = bk.lathe("drum", c, [(r, P.z_quad - 0.5), (r, z1 - 0.02)], M["wall"], seg=48)
    op, parts = Openings(recess=0.45), []
    for k in range(8):
        a = 2 * math.pi * (k + 0.5) / 8
        fr = bk.Frame.radial(c, r, a)
        op.slit(fr, 0.0, 0.42, z1 - 3.05, z1 - 1.95)
        parts.append(bk.extrude("sandrik", fr, [(-0.4, z1 - 1.85), (0.4, z1 - 1.85), (0.0, z1 - 1.45)], -0.05, 0.12,
                                M["wall"]))
    for z0, zt, pr in ((z1 - 1.25, z1 - 0.95, 0.07), (z1 - 0.85, z1 - 0.55, 0.07), (z1 - 0.45, z1 - 0.02, 0.2)):
        parts.append(bk.lathe("drum_band", c, [(r - 0.2, z0), (r + pr, z0), (r + pr, zt), (r - 0.2, zt)], M["wall"],
                              seg=48, closed=True, smooth=False))
    parts.append(onion(c, r, z1, P.onion_d, P.z_apple, "dark"))
    ra = 0.035 * P.onion_d
    parts.append(apple(c[0], c[1], P.z_apple, ra))
    parts += cross(c[0], c[1], P.z_apple + 2 * ra - 0.05, P.z_top - P.z_apple - 2 * ra + 0.05)
    return op.apply(body) + parts


def small_dome(d):
    """Главка придела: глухой стройный барабан с поясом, луковица с перехватом шире барабана, крест."""
    c, r = (d.u, d.v), d.drum_d / 2
    parts = [bk.lathe("sdrum", c, [(r, d.z0), (r, d.z_lip)], M["wall"], seg=24),
             bk.lathe("sdrum_band", c, [(r - 0.05, d.z_lip - 0.3), (r + 0.06, d.z_lip - 0.3), (r + 0.06, d.z_lip - 0.1),
                                        (r - 0.05, d.z_lip - 0.1)], M["wall"], seg=24, closed=True, smooth=False),
             onion(c, r, d.z_lip, d.onion_d, d.z_apple, d.mat)]
    ra = 0.04 * d.onion_d
    parts.append(apple(d.u, d.v, d.z_apple, ra))
    parts += cross(d.u, d.v, d.z_apple + 2 * ra - 0.02, d.z_top - d.z_apple - 2 * ra + 0.02)
    return parts


# ---------- четверик ----------

def lobes(fr, s0, s1, z_top, n, rising):
    """Лопастные арочки-валики в прясле s0…s1 под карнизом: n лопастей; rising — «ползучие» (к середине фасада выше,
    rising = +1 — растут вправо, −1 — влево, 0 — средняя лопасть выше крайних)."""
    w = (s1 - s0) / n
    parts = []
    for i in range(n):
        if rising:
            k = i if rising > 0 else n - 1 - i
            zs = z_top - 1.9 + 0.55 * k
        else:
            zs = z_top - 1.7 + (0.5 if i == n // 2 else 0.0)
        zs = min(zs, z_top - 0.3 - w / 2)
        parts.append(bk.extrude("lobe", fr, bk.arch_frame(s0 + (i + 0.5) * w, w - 0.3, zs, zs, 0.18, n=10),
                                -0.08, 0.1, M["wall"]))
    return parts


def keel(sc, w, z0, h):
    """Килевидная арка на фасаде (s, z): прямые бока до 0,5 h, дальше вогнутые дуги к острию."""
    side = [(0.5, 0.5), (0.42, 0.7), (0.25, 0.83), (0.08, 0.93)]
    right = [(sc + k * w, z0 + m * h) for k, m in side]
    left = [(sc - k * w, z0 + m * h) for k, m in reversed(side)]
    return [(sc - w / 2, z0), (sc + w / 2, z0)] + right + [(sc, z0 + h)] + left


def quad():
    """Четверик: три прясла на фасад между лопатками, лопастные арочки, окна, деревянный многообломный карниз,
    четырёхскатная кровля; на востоке над средней апсидой — килевидное завершение (S-24)."""
    u0, u1, v0, v1 = P.quad
    zq = P.z_quad
    faces = rect_faces(u0, u1, v0, v1)
    body = bk.box("quad", u0, u1, v0, v1, BASE_Z, zq, M["wall"])
    op, parts = Openings(recess=0.6), []
    for side, fr in faces.items():
        L = fr.length
        z_low = P.apses[0][3] - 0.5 if side == "E" else P.z_gal[1] - 0.4
        for i, s in enumerate((0.0, L / 3, 2 * L / 3, L)):                    # лопатки
            s0, s1 = (-0.2, 0.8) if i == 0 else (L - 0.8, L + 0.2) if i == 3 else (s - 0.5, s + 0.5)
            parts.append(bk.extrude("lopatka", fr, bk.rect(s0, s1, z_low, zq - 0.45), -0.1, 0.14, M["wall"]))
        if side != "E":                                   # арочки: боковые ползучие, средняя — трёхлопастная
            parts += lobes(fr, 0.8, L / 3 - 0.5, zq - 0.45, 2, +1)
            parts += lobes(fr, L / 3 + 0.5, 2 * L / 3 - 0.5, zq - 0.45, 3, 0)
            parts += lobes(fr, 2 * L / 3 + 0.5, L - 0.8, zq - 0.45, 2, -1)
    w = faces["W"]                                                              # два окошка над притвором
    for ds in (-0.8, 0.8):
        op.window(w, w.length / 2 + ds, 0.65, 8.5, 9.6, frame=False)
    for side in "NS":                                                           # по окну в среднем прясле
        fr = faces[side]
        op.window(fr, fr.length / 2, 0.95, 8.6, 10.0, frame=False)
    e = faces["E"]                                                              # окошко в килевидном завершении
    sc = v1 - (P.apses[0][0] + P.apses[0][1]) / 2
    op.window(e, sc, 0.6, 11.0, 11.9, frame=False)
    parts.append(bk.extrude("keel", e, keel(sc, P.apses[0][1] - P.apses[0][0] + 0.6, zq - 0.5, 2.4), -1.6, 0.08,
                            M["wall"]))
    parts.append(bk.extrude("keel_frame", e, keel(sc, P.apses[0][1] - P.apses[0][0] - 0.4, zq - 0.3, 1.9), 0.0, 0.14,
                            M["wall"]))
    parts += steps(u0, u1, v0, v1, ((zq - 0.5, zq - 0.25, 0.12), (zq - 0.25, zq + 0.05, 0.32)))
    parts.append(bk.hip_roof("quad_roof", u0 - 0.55, u1 + 0.55, v0 - 0.55, v1 + 0.55, zq + 0.3, P.roof_rise, 0.3,
                             M["tin"]))
    return op.apply(body) + parts


# ---------- притвор, галереи, приделы ----------

def galleries():
    """Притвор с запада и галереи с севера и юга — одно тело П-образное в плане, под односкатными кровлями к четверику."""
    (u0, u1, v0, v1), (gu, gn, gs) = P.quad, P.gal
    nu0, su0 = P.north[0], P.south[0]
    ze, zi = P.z_gal
    poly = [(gu, gn), (nu0, gn), (nu0, v0 + 0.3), (u0 + 0.3, v0 + 0.3), (u0 + 0.3, v1 - 0.3), (su0, v1 - 0.3),
            (su0, gs), (gu, gs)]
    body = bk.prism("gallery", poly, BASE_Z, ze, M["wall"])
    c = (0.0, 0.0)
    west = bk.Frame.between((gu, gn), (gu, gs), c)                      # s = v − gn
    north = bk.Frame.between((nu0, gn), (gu, gn), c)                    # s = nu0 − u
    south = bk.Frame.between((gu, gs), (su0, gs), c)                    # s = u − gu
    op, parts = Openings(recess=0.5), []
    for v in (-11.3, -7.6, 7.2, 10.6):
        op.slit(west, v - gn, 0.75, 1.2, 2.3)
    for u in (-10.0, -6.6, -3.2):
        op.slit(north, nu0 - u, 0.7, 1.6, 2.6)
        op.slit(south, u - gu, 0.7, 1.6, 2.6)
    # западный вход под крыльцом: за крыльцом стена притвора поднята до его кровли, дверь выше свеса (фото ch_west)
    _, pv0, pv1, pz, _ = P.porch
    vd = (pv0 + pv1) / 2
    door = bk.arch(vd - gn, 2.0, -0.3, 3.2)
    op.cutters.append(bk.extrude("cut", west, door, -0.55, 0.5, M["wall"]))
    parts.append(bk.extrude("door", west, door, -0.6, -0.45, M["wood"]))
    raised = bk.box("porch_wall", gu - 0.02, gu + 0.8, pv0 + 0.5, pv1 - 0.5, ze - 0.5, pz - 0.05, M["wall"])
    parts.append(bk.cut(raised, [bk.extrude("cut", west, door, -1.0, 0.5, M["wall"])]))
    parts.append(band(gu, gu + 0.5, gn, gs, ze - 0.3, ze, 0.15))       # карнизик по западной стене
    oh, zo = 0.4, ze + 0.05
    go, gvn, gvs = gu - oh, gn - oh, gs + oh
    parts.append(bk.slab("roof_w", [(u0, v0, zi), (u0, v1, zi), (go, gvs, zo), (go, gvn, zo)], 0.25, M["tin"]))
    parts.append(bk.slab("roof_n", [(u0, v0, zi), (go, gvn, zo), (nu0, gvn, zo), (nu0, v0, zi)], 0.25, M["tin"]))
    parts.append(bk.slab("roof_s", [(u0, v1, zi), (su0, v1, zi), (su0, gvs, zo), (go, gvs, zo)], 0.25, M["tin"]))
    return op.apply(body) + parts


def gable(name, u0, u1, v0, v1, z, rise, ends=(True, True), oh=0.35):
    """Двускатная кровля с коньком вдоль u над прямоугольником (карниз на z) и белёные щипцы на торцах
    ends = (западный, восточный)."""
    vm = (v0 + v1) / 2
    k = rise / (vm - v0)
    ze = z - oh * k
    parts = [bk.slab(f"{name}_n", [(u0 - oh, v0 - oh, ze), (u1 + oh, v0 - oh, ze), (u1 + oh, vm, z + rise),
                                   (u0 - oh, vm, z + rise)], 0.22, M["tin"]),
             bk.slab(f"{name}_s", [(u0 - oh, vm, z + rise), (u1 + oh, vm, z + rise), (u1 + oh, v1 + oh, ze),
                                   (u0 - oh, v1 + oh, ze)], 0.22, M["tin"])]
    c = ((u0 + u1) / 2, vm)
    for u, on in ((u0, ends[0]), (u1, ends[1])):
        if on:
            fr = bk.Frame.between((u, v1), (u, v0), c)
            tri = [(0.0, z - 0.3), (v1 - v0, z - 0.3), ((v1 - v0) / 2, z + rise - 0.15)]
            parts.append(bk.extrude(f"{name}_pediment", fr, tri, -0.4, 0.0, M["wall"]))
    return parts


def block(name, u0, u1, v0, v1, z_wall, rise, windows=(), roof=(0.4, 0.4, 0.4, 0.4), kind="hip", u_roof=None):
    """Придел или алтарный выступ: белёная коробка с окнами и кровлей. windows — [(фасад W|N|E|S, s, ширина, низ,
    пята арки)]; roof — свесы (W, E, N, S); kind — "hip" (вальма) или "gable" (конёк вдоль u, щипец на востоке);
    u_roof — вальма только до этого u (дальше — другая кровля)."""
    body = bk.box(name, u0, u1, v0, v1, BASE_Z, z_wall, M["wall"])
    faces = rect_faces(u0, u1, v0, v1)
    op = Openings(recess=0.45)
    for side, s, w, sill, spring in windows:
        op.window(faces[side], s, w, sill, spring, frame=False)
    ow, oe, on, osd = roof
    parts = [band(u0, u1, v0, v1, z_wall - 0.3, z_wall, 0.12)]
    if kind == "gable":
        parts += gable(f"{name}_roof", u0, u1, v0, v1, z_wall + 0.2, rise)
    else:
        parts.append(bk.hip_roof(f"{name}_roof", u0 - ow, u_roof or u1 + oe, v0 - on, v1 + osd, z_wall + 0.2, rise,
                                 0.25, M["tin"]))
    return op.apply(body) + parts


def chapels():
    """Приделы (S-24, S-53) по фото S-54 both_se и ch_e: северный — под вальмой, его алтарь — щипцом на восток; южный
    с притвором — под вальмой, его восточная часть с алтарём — щипцом на восток; между ней и апсидами — односкатная."""
    u0, u1, v0, v1 = P.quad
    nu0, nu1, nv0, nz, nr = P.north
    eu0, eu1, ev0, ev1, ez, er = P.ne
    su0, su1, sv1, sz, sr = P.south
    xu0, xu1, xv0, xv1, xz, xr = P.se
    out = block("north", nu0, nu1, nv0, v0 + 0.3, nz, nr,
                [("N", nu1 - 2.5, 0.8, 2.2, 3.2), ("N", nu1 - 6.0, 0.8, 2.2, 3.2)], roof=(0.4, 0.0, 0.4, -0.3))
    out += block("ne", eu0, eu1, ev0, ev1, ez, er, [("E", (ev1 - ev0) / 2, 0.8, 2.0, 3.0)], kind="gable")
    out += block("south", su0, su1, v1 - 0.3, sv1, sz, sr,
                 [("S", s - su0, 0.55, 2.7, 3.3) for s in (1.5, 4.0, 6.6)], roof=(0.4, 0.4, -0.3, 0.4), u_roof=xu0)
    out += block("se", xu0, xu1, xv0, xv1, xz, xr, [("E", (xv1 - xv0) / 2, 0.7, 2.0, 3.0), ("S", 2.0, 0.55, 2.7, 3.3),
                                                    ("S", 4.6, 0.55, 2.7, 3.3)], kind="gable")
    # между восточной частью южного придела и апсидами — односкатная кровля от четверика
    ua, ub, va, vb = xu0, su1 + 0.4, v1, xv0
    out.append(bk.slab("south_lean", [(ua, va, sz + 1.6), (ub, va, sz + 1.6), (ub, vb, sz + 0.25), (ua, vb, sz + 0.25)],
                       0.22, M["tin"]))
    # вход с юга: закрытое крыльцо на столбах — арка во всю ширину, в глубине дверь (S-24)
    pu0, pu1, pv1, pz = P.s_porch
    body = bk.box("s_porch", pu0, pu1, sv1 - 0.3, pv1, BASE_Z, pz, M["wall"])
    fr = rect_faces(pu0, pu1, sv1 - 0.3, pv1)["S"]
    sc = fr.length / 2
    bk.cut(body, [bk.extrude("cut", fr, bk.arch(sc, 1.5, -0.3, 1.85), -1.1, 0.5, M["wall"])])
    out += [body, bk.extrude("door", fr, bk.arch(sc, 1.2, -0.3, 1.7), -1.15, -1.05, M["wood"]),
            bk.hip_roof("s_porch_roof", pu0 - 0.25, pu1 + 0.25, sv1, pv1 + 0.3, pz + 0.15, 1.0, 0.2, M["tin"])]
    return out


def porch():
    """Западное крыльцо XIX в. (S-53): четыре квадратных столба с базами и капителями, обвязка, низкая вальма."""
    u_face, (pu0, pv0, pv1, pz, rise) = P.gal[0], P.porch
    parts = []
    for u in (pu0 + 0.45, u_face - 0.35):
        for v in (pv0 + 0.45, pv1 - 0.45):
            parts += [bk.box("pillar", u - 0.4, u + 0.4, v - 0.4, v + 0.4, BASE_Z, pz - 0.7, M["wall"]),
                      bk.box("pillar_base", u - 0.5, u + 0.5, v - 0.5, v + 0.5, BASE_Z, 0.5, M["wall"]),
                      bk.box("pillar_cap", u - 0.5, u + 0.5, v - 0.5, v + 0.5, pz - 1.0, pz - 0.7, M["wall"])]
    parts += [bk.box("beam", pu0, u_face, pv0, pv0 + 0.9, pz - 0.7, pz, M["wall"]),
              bk.box("beam", pu0, u_face, pv1 - 0.9, pv1, pz - 0.7, pz, M["wall"]),
              bk.box("beam", pu0, pu0 + 0.9, pv0, pv1, pz - 0.7, pz, M["wall"]),
              bk.box("step", pu0 - 0.6, u_face, pv0 + 1.2, pv1 - 1.2, BASE_Z, 0.15, M["wall"]),
              bk.hip_roof("porch_roof", pu0 - 0.35, u_face + 1.2, pv0 - 0.35, pv1 + 0.35, pz + 0.1, rise, 0.2,
                          M["tin"])]
    return parts


# ---------- апсиды ----------

def apses():
    """Три апсиды на восток (план S-53): средняя выше; стены, пояс-бегунец под карнизом, карниз, конусная кровля."""
    ue = P.quad[1]
    out = []
    for i, (v0, v1, tip, zt) in enumerate(P.apses):
        r, vc = (v1 - v0) / 2, (v0 + v1) / 2
        uc = tip - r

        def outline(g):
            return [(ue - 0.4, v0 - g), (uc, v0 - g)] + \
                [(uc + (r + g) * math.cos(a), vc + (r + g) * math.sin(a))
                 for a in (-math.pi / 2 + math.pi * k / 16 for k in range(1, 16))] + [(uc, v1 + g), (ue - 0.4, v1 + g)]
        body = bk.prism("apse", outline(0.0), BASE_Z, zt - 0.45, M["wall"])
        op = Openings(recess=0.5)
        for a, w, sill, spring in (((-0.5, 0.8, 2.6, 4.4), (0.5, 0.8, 2.6, 4.4)) if i == 0 else ((0.0, 0.6, 2.8, 4.1),)):
            op.window(bk.Frame.radial((uc, vc), r, a), 0.0, w, sill, spring, frame=False)
        parts = [bk.prism("apse_band", outline(0.08), zt - 1.6, zt - 0.95, M["wall"]),
                 bk.prism("apse_cornice", outline(0.3), zt - 0.45, zt, M["wall"]),
                 bk.loft("apse_roof", [[(u, v, zt) for u, v in outline(0.45)], [(ue, vc, zt + 0.4 + 0.12 * r)]],
                         M["tin"])]
        if i == 0:                                                          # валики средней апсиды
            for a in (-0.95, 0.0, 0.95):
                parts.append(bk.extrude("valik", bk.Frame.radial((uc, vc), r, a), bk.rect(-0.14, 0.14, 0.0, zt - 1.6),
                                        -0.1, 0.12, M["wall"]))
        out += op.apply(body) + parts
    return out


# ---------- звонница ----------

def zv_bell(u, v, top, d):
    """Колокол губой вниз: верх на top, диаметр губы d (профиль — как у колоколов belfry.py), ушко."""
    prof = ((0.0, 1.0), (0.04, 1.0), (0.12, 0.86), (0.3, 0.72), (0.55, 0.64), (0.8, 0.6), (0.92, 0.52), (1.0, 0.36),
            (1.0, 0.0))
    h = 0.95 * d
    return [bk.lathe("bell", (u, v), [(k * d / 2, top - h + t * h) for t, k in prof], M["bronze"], seg=24),
            bk.box("ushko", u - 0.04, u + 0.04, v - 0.1, v + 0.1, top, top + 0.15, M["bronze"])]


def zvonnitsa():
    """Стена звона с пятью сквозными пролётами на шести столпах (у столпов утолщение посередине пролёта, S-24),
    карниз и низкая вальма, крест; палатка к западу под односкатной кровлей, окошки, трубы; двери на восточном
    фасаде; площадка и лестница с кровли палатки к южному пролёту (фото zv_w_top)."""
    su, sv = Z.size
    E, HV = su / 2, sv / 2
    W0 = E - Z.wall
    zc0, zc1 = Z.z_cornice
    ze, zj = Z.z_chamber
    k = (zj - ze) / (W0 + E)                                             # уклон кровли палатки

    def z_roof(u):
        return ze + (u + E) * k
    c = (0.0, 0.0)
    # палатка: боковой профиль по уклону кровли, выдавлен с юга на север
    side = bk.Frame((-E, HV), (1.0, 0.0), (0.0, 1.0))
    uw = W0 + 0.3 + E                                                    # палатка заходит в стену звона на 0,3
    chamber = bk.extrude("chamber", side, [(0.0, BASE_ZV), (uw, BASE_ZV), (uw, z_roof(W0 + 0.3) - 0.1), (0.0, ze - 0.1)],
                         -sv, 0.0, M["wall"])
    op = Openings(recess=0.35)
    south = bk.Frame.between((-E, HV), (W0, HV), c)                       # s = u + E
    north = bk.Frame.between((W0, -HV), (-E, -HV), c)                     # s = W0 − u
    west = bk.Frame.between((-E, -HV), (-E, HV), c)                       # s = v + HV
    for u in (-3.3, -0.8):
        op.slit(south, u + E, 0.45, 3.0, 3.8)
        op.slit(north, W0 - u, 0.45, 3.0, 3.8)
    for v in (-2.0, 2.0):
        op.slit(west, v + HV, 0.45, 3.2, 4.0)
    parts = op.apply(chamber)
    zw = z_roof(-E - 0.35)
    parts.append(bk.slab("chamber_roof", [(W0, -HV - 0.25, zj), (W0, HV + 0.25, zj), (-E - 0.35, HV + 0.25, zw),
                                          (-E - 0.35, -HV - 0.25, zw)], 0.18, M["roof"]))
    for v in (-5.2, -3.4):                                                # две трубы у стены звона (фото zv_w_top)
        zr = z_roof(1.4)
        parts += [bk.box("chimney", 1.15, 1.65, v - 0.25, v + 0.25, zr - 0.3, zr + 1.0, M["wall"]),
                  bk.box("chimney_cap", 1.08, 1.72, v - 0.32, v + 0.32, zr + 1.0, zr + 1.12, M["roof"])]
    # стена звона
    wall = bk.box("zvon", W0, E, -HV, HV, BASE_ZV, zc0, M["wall"])
    east = bk.Frame.between((E, HV), (E, -HV), c)                         # s = HV − v, от южного конца
    westw = bk.Frame.between((W0, -HV), (W0, HV), c)                      # s = v + HV, от северного конца
    op = Openings(recess=0.3)
    for s, w, sill in Z.spans:
        spring = Z.z_arch - w / 2
        op.cutters.append(bk.extrude("cut", east, bk.arch(s, w, sill, spring), -Z.wall - 0.5, 0.5, M["wall"]))
    for s, z0, z1 in ((3.37, 7.5, 8.0), (1.31, 11.15, 11.65)):             # щели лестницы в стене (S-24), места по фото
        op.slit(east, s, 0.16, z0, z1)
    for s, w, top, niche in ((4.8, 0.9, 1.5, 0.0), (7.55, 1.2, 2.8, 1.8), (10.8, 0.9, 1.5, 0.0)):
        spring = top - w / 2
        if niche:                                                          # средняя дверь — в арочной нише
            op.cutters.append(bk.extrude("cut", east, bk.arch(s, niche, -0.3, spring + 0.15), -0.3, 0.5, M["wall"]))
            op.parts.append(bk.extrude("door", east, bk.arch(s, w, -0.3, spring), -0.34, -0.22, M["wood"]))
        else:
            op.cutters.append(bk.extrude("cut", east, bk.arch(s, w, -0.3, spring), -0.3, 0.5, M["wall"]))
            op.parts.append(bk.extrude("door", east, bk.arch(s, w, -0.3, spring), -0.35, -0.25, M["wood"]))
    parts += op.apply(wall)
    # столпы: утолщение посередине пролётов на обоих фасадах, подоконные плиты
    edges = [0.0] + [x for s, w, _ in Z.spans for x in (s - w / 2, s + w / 2)] + [sv]
    zb0, zb1 = 12.75, 13.55
    for a, b in zip(edges[::2], edges[1::2]):
        a0, b0 = max(0.0, a - 0.25), min(sv, b + 0.25)
        bulge = [(a, zb0 - 0.25), (b, zb0 - 0.25), (b0, zb0), (b0, zb1 - 0.25), (b, zb1), (a, zb1), (a0, zb1 - 0.25),
                 (a0, zb0)]
        parts.append(bk.extrude("bulge", east, bulge, -0.05, 0.25, M["wall"]))
        parts.append(bk.extrude("bulge", westw, [(sv - s, z) for s, z in bulge], -0.05, 0.25, M["wall"]))
    for s, w, sill in Z.spans:
        parts.append(bk.extrude("sill", east, bk.rect(s - w / 2 - 0.08, s + w / 2 + 0.08, sill - 0.12, sill),
                                -Z.wall - 0.12, 0.12, M["wall"]))
    parts += steps(W0, E, -HV, HV, ((zc0, zc0 + 0.25, 0.12), (zc0 + 0.25, zc0 + 0.5, 0.3), (zc0 + 0.5, zc1, 0.55)))
    parts.append(bk.hip_roof("zvon_roof", W0 - 0.85, E + 0.85, -HV - 0.85, HV + 0.85, zc1 + 0.05,
                             Z.z_ridge - zc1 - 0.05, 0.2, M["roof"]))
    um = (W0 + E) / 2
    parts += [bk.box("cross_post", um - 0.05, um + 0.05, -0.05, 0.05, Z.z_ridge - 0.2, Z.z_ridge + 0.55, M["dark"]),
              apple(um, 0.0, Z.z_ridge + 0.5, 0.2)]
    parts += cross(um, 0.0, Z.z_ridge + 0.85, Z.z_top - Z.z_ridge - 0.85, th=0.07)
    # балки и колокола в пролётах: балка поперёк пролёта в уровне пят арок
    for (s, w, sill), bells in zip(Z.spans, Z.bells):
        v = HV - s
        zb = Z.z_arch - w / 2 - 0.1
        parts.append(bk.box("beam", um - 0.1, um + 0.1, v - w / 2 - 0.25, v + w / 2 + 0.25, zb - 0.2, zb, M["wood"]))
        n = len(bells)
        for i, d in enumerate(bells):
            parts += zv_bell(um, v + (i - (n - 1) / 2) * (w / n), zb - 0.2, d)
    # площадка у южного пролёта с запада и лестница к ней по кровле палатки (фото zv_w_top, zv_w)
    s1, w1, sill1 = Z.spans[0]
    v1 = HV - s1
    zp = sill1 - 0.1
    parts.append(bk.box("platform", W0 - 1.5, W0, v1 - 0.8, v1 + 0.8, zp - 0.1, zp, M["wood"]))
    for u in (W0 - 1.45, W0 - 0.1):
        for v in (v1 - 0.75, v1 + 0.75):
            parts.append(bk.box("post", u - 0.05, u + 0.05, v - 0.05, v + 0.05, z_roof(u) - 0.1, zp + 1.0, M["wood"]))
    parts += [bk.box("rail", W0 - 1.5, W0 - 1.4, v1 - 0.8, v1 + 0.8, zp + 0.9, zp + 1.0, M["wood"]),
              bk.box("rail", W0 - 1.5, W0, v1 + 0.7, v1 + 0.8, zp + 0.9, zp + 1.0, M["wood"])]
    ua, va, vb = W0 - 0.75, v1 - 3.4, v1 - 0.8                            # марш вдоль стены: с севера вверх к площадке
    za = z_roof(ua)
    n = 9
    for i in range(n):
        v = va + (vb - va) * (i + 0.5) / n
        z = za + (zp - za) * (i + 1) / n
        parts.append(bk.box("tread", ua - 0.4, ua + 0.4, v - 0.14, v + 0.14, z - 0.05, z, M["wood"]))
    for u in (ua - 0.42, ua + 0.42):
        parts.append(bk.mesh("stringer", [(u - 0.03, va, za - 0.1), (u + 0.03, va, za - 0.1), (u + 0.03, vb, zp - 0.1),
                                          (u - 0.03, vb, zp - 0.1), (u - 0.03, va, za + 0.15), (u + 0.03, va, za + 0.15),
                                          (u + 0.03, vb, zp + 0.15), (u - 0.03, vb, zp + 0.15)],
                             [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]],
                             M["wood"]))
    return parts


# ---------- превью ----------

CHURCH_GROUND, BELFRY_GROUND = -5.28, -5.61   # земля в base героев по refs/dem/heightmap_L_Krom (только для превью)


def to_church(x, y, zw):
    """Точка мира (x — север, y — восток, z — отметка от собора) → оси храма (u, v, z)."""
    t = math.radians(P.yaw)
    dx, dy = x - P.center[0], y - P.center[1]
    return dx * math.cos(t) + dy * math.sin(t), -dx * math.sin(t) + dy * math.cos(t), zw - CHURCH_GROUND


def zv_to_church(u, v, z):
    """Точка в осях звонницы → оси храма."""
    x, y = krom_plan.to_world(Z.center, Z.yaw, u, v)
    return to_church(x, y, z + BELFRY_GROUND)


def world_view(eye, yaw, pitch):
    """Камера по точке мира и направлению (азимут и наклон, °) → (глаз, цель) в осях храма."""
    fx, fy, fz = (math.cos(math.radians(yaw)) * math.cos(math.radians(pitch)),
                  math.sin(math.radians(yaw)) * math.cos(math.radians(pitch)), math.sin(math.radians(pitch)))
    return to_church(*eye), to_church(eye[0] + 100 * fx, eye[1] + 100 * fy, eye[2] + 100 * fz)


def views():
    """Превью в осях храма: (глаз, цель, кадр, объектив мм). Ракурсы *_photo — точки съёмки фото S-54, восстановленные
    по углам звонницы (build/paromenye_refs), для сравнения «фото | модель»."""
    se = world_view((-369.7, -223.0, BELFRY_GROUND + 8.0), 314.4, 4.9)            # both_se, iPhone 11, 27 мм
    # zv_east2: 23,9 м от восточного фасада, 0,6 м от южного угла, глаз 0,92, рыск 13,7° к северу, наклон 15,5°
    su, sv = Z.size
    eu, ev = su / 2 + 23.9, sv / 2 - 0.6
    psi, th = math.radians(13.7), math.radians(15.5)
    look = (eu - 100 * math.cos(psi) * math.cos(th), ev - 100 * math.sin(psi) * math.cos(th), 0.92 + 100 * math.sin(th))
    ze = (zv_to_church(eu, ev, 0.92), zv_to_church(*look))
    krom = world_view((-205.0, -20.0, 8.0), math.degrees(math.atan2(-258.0 + 20.0, -330.0 + 205.0)), -1.2)
    return {
        "se_photo": (*se, (1280, 960), 27.0),
        "zv_east_photo": (*ze, (853, 1280), 28.0),
        "from_krom": (*krom, (1280, 720), 70.0),                                    # со стены Довмонтова города
        "west": ((-42.0, -0.5, 2.2), (0.0, -0.5, 12.5), (1280, 960), 35.0),              # как фото ch_west
        "northeast": ((38.0, -40.0, 1.6), (0.0, 0.0, 13.0), (1280, 960), 30.0),
        "east": ((36.0, 16.0, 1.6), (2.0, 1.0, 11.0), (1280, 960), 25.0),                   # как фото ch_e
        "dome": ((-85.0, 62.0, 8.0), (2.2, -0.5, 23.5), (1280, 960), 130.0),                 # как фото dome
        "zv_west": (zv_to_church(-26.0, -10.0, 1.6), zv_to_church(3.0, 0.0, 10.0), (1280, 960), 28.0),
        "high": ((55.0, -30.0, 45.0), (-2.0, 16.0, 6.0), (1280, 720), 30.0),
    }


def build(objs, name):
    obj = bk.join(objs, name)
    bk.box_uv(obj)
    me = obj.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    print(f"[paromenye] {len(objs)} тел → {name}: {len(me.vertices)} вершин, {len(me.polygons)} граней, "
          f"≈{tris} треугольников, слоты {[m.name for m in me.materials]}")
    bk.export_glb(obj, name)
    return obj


def main():
    bk.reset_scene()
    bk.use_colors(krom_plan.COLORS)
    church = build(galleries() + quad() + chapels() + porch() + apses() + main_dome() +
                   [x for d in P.domes for x in small_dome(d)], NAME)
    belfry = build(zvonnitsa(), NAME_BELFRY)
    # для превью звонница ставится на своё место в осях храма (выгрузка — уже в своих осях)
    u, v, z = zv_to_church(0.0, 0.0, 0.0)
    belfry.location = (u, -v, z)
    belfry.rotation_euler = (0.0, 0.0, -math.radians(Z.yaw - P.yaw))
    church.select_set(False)
    ground = bk.box("ground", -400, 400, -400, 400, -0.35, -0.3, bk.material("ground", (0.12, 0.16, 0.08)))
    ground.hide_select = True
    for view, (eye, target, size, lens) in views().items():
        bk.render_preview(f"paromenye_{view}", eye=(eye[0], -eye[1], eye[2]), target=(target[0], -target[1], target[2]),
                          size=size, lens=lens)


main()
