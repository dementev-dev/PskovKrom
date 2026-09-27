"""belfry.py — колокольня Троицкого собора, герой M3: модель скриптом Blender по krom_plan.BELFRY (D-018, D-019).

    python scripts/bl_run.py scripts/blender/belfry.py

Выгрузка — build/blender/SM_TrinityBelfry.glb (в UE ставит scripts/heroes_krom.py), превью —
media/renders/blender/belfry_*.png. Ярусы, проёмы и пристройка берутся из BELFRY, источники записаны там. Здесь
только детали, снятые с фото S-25 «на глаз»: карнизы, парапет, руст арки, окошки, часы, колокола, профиль шпиля.
Оси здания: u — на восток, v — к югу, z — от земли двора у пристройки (BELFRY.base).
Материалы — слоты по ключам krom_plan.COLORS (в UE пока MI_BO_*, свои — в M4).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402
import krom_plan  # noqa: E402
from bl_krom import M, Openings, band  # noqa: E402

T = krom_plan.BELFRY
NAME = "SM_TrinityBelfry"
BASE_Z = -3.0            # низ стен: к Пскове земля ниже двора
HU, HV = T.size[0] / 2, T.size[1] / 2
WALL4 = 2.0              # толщина стен звона (проёмы сквозные, внутри камера с колоколами)
WALL5 = 1.9              # верхний звон: столпы между арками
Z_T4_CORNICE = 22.1      # низ карниза звона


def faces(hu, hv):
    """Фасады прямоугольника ±hu × ±hv; s — слева направо, если смотреть снаружи."""
    c = (0.0, 0.0)
    return {"W": bk.Frame.between((-hu, -hv), (-hu, hv), c), "N": bk.Frame.between((hu, -hv), (-hu, -hv), c),
            "E": bk.Frame.between((hu, hv), (hu, -hv), c), "S": bk.Frame.between((-hu, hv), (hu, hv), c)}


def steps(hu, hv, rows):
    """Профилированный карниз или пояс: ступени [(z0, z1, вынос)] вокруг прямоугольника ±hu × ±hv."""
    return [band(-hu, hu, -hv, hv, z0, z1, proud) for z0, z1, proud in rows]


def railing(fr, s0, s1, z0, h, d=0.0, step=0.16):
    """Решётка вдоль фасада fr от s0 до s1: поручень, нижняя тяга и прутья (чёрное железо, фото 2026 г.)."""
    parts = [bk.extrude("rail", fr, bk.rect(s0, s1, z0 + h - 0.06, z0 + h), d - 0.03, d + 0.03, M["dark"]),
             bk.extrude("rail", fr, bk.rect(s0, s1, z0 + 0.1, z0 + 0.15), d - 0.02, d + 0.02, M["dark"])]
    n = max(1, round((s1 - s0) / step))
    for i in range(1, n):
        s = s0 + (s1 - s0) * i / n
        parts.append(bk.extrude("bar", fr, bk.rect(s - 0.015, s + 0.015, z0 + 0.1, z0 + h), d - 0.015, d + 0.015,
                                M["dark"]))
    return parts


# колокол: (доля высоты от губы, радиус в долях радиуса губы)
BELL = ((0.0, 1.0), (0.04, 1.0), (0.12, 0.86), (0.3, 0.72), (0.55, 0.64), (0.8, 0.6), (0.92, 0.52), (1.0, 0.36),
        (1.0, 0.0))


def bell(u, v, top, d, h):
    """Колокол губой вниз: верх на top, диаметр губы d, высота h; сверху ушко."""
    prof = [(r * d / 2, top - h + t * h) for t, r in BELL]
    return [bk.lathe("bell", (u, v), prof, M["bronze"], seg=32),
            bk.box("ushko", u - 0.06, u + 0.06, v - 0.2, v + 0.2, top, top + 0.25, M["bronze"])]


# ---------- столп и звон (ярусы 1–4) ----------

def shaft():
    """Столп до площадки звона: окошки ярусов 1–3, по две сквозные арки звона на грань, камера с колоколами."""
    body = bk.box("shaft", -HU, HU, -HV, HV, BASE_Z, T.z_t4, M["wall"])
    ci, cv = HU - WALL4, HV - WALL4
    bk.cut(body, [bk.box("cut", -ci, ci, -cv, cv, T.z_sill - 0.4, T.z_arch4 + 0.7, M["wall"])])
    w, off = T.arch4
    spring = T.z_arch4 - w / 2
    op, parts = Openings(recess=0.4), []
    for side, fr in faces(HU, HV).items():
        for sgn in (-1, 1):
            s = fr.length / 2 + sgn * off
            # вырез только до камеры: глубже вырезы соседних граней пересеклись бы в её углах
            op.cutters.append(bk.extrude("cut", fr, bk.arch(s, w, T.z_sill, spring), -WALL4 - 0.2, 0.5, M["wall"]))
            parts += railing(fr, s - w / 2, s + w / 2, T.z_sill, 1.1, d=-0.3)
            parts.append(bk.extrude("sill", fr, bk.rect(s - w / 2 - 0.1, s + w / 2 + 0.1, T.z_sill - 0.18, T.z_sill),
                                    -0.3, 0.12, M["wall"]))
    # окошки столпа — по фото с Псковы (2026) на северной и восточной гранях; южная — как северная (гип.)
    for side, s_list in (("N", (3.5,)), ("S", (2 * HU - 3.5,)), ("E", (2.9, 5.9))):   # 3,5 м от восточного угла
        fr = faces(HU, HV)[side]
        for s in s_list:
            for z0 in (2.6, 8.0):
                op.slit(fr, s, 0.6, z0, z0 + 0.9)
    parts += steps(HU, HV, ((BASE_Z, -0.3, 0.2),))                                   # цоколь
    parts += steps(HU, HV, ((Z_T4_CORNICE, Z_T4_CORNICE + 0.3, 0.12),                # карниз звона
                            (Z_T4_CORNICE + 1.2, Z_T4_CORNICE + 1.5, 0.3),
                            (Z_T4_CORNICE + 1.5, T.z_t4, 0.6)))
    parts.append(band(-HU, HU, -HV, HV, T.z_t4, T.z_t4 + 0.06, 0.63, "tin"))         # площадка — жесть
    # колокола звона на двух балках в уровне пят арок (S-23), за каждым проёмом
    for v in (-off, off):
        parts.append(bk.box("beam", -ci - 0.3, ci + 0.3, v - 0.15, v + 0.15, spring - 0.3, spring, M["wood"]))
        for u in (-off, off):
            parts += bell(u, v, spring - 0.3, 1.4, 1.3)
    return op.apply(body) + parts


# ---------- верхний звон (ярус 5) ----------

def upper():
    """Квадрат меньше столпа: четыре угловых столпа, по сквозной арке на грань, руст и замковый камень, импост,
    архитрав, венчающий карниз; на площадке — парапет со столбиками и решёткой."""
    h = T.upper / 2
    w = T.arch5
    spring = T.z_arch5 - w / 2
    z_frieze = T.z_upper - 1.6
    body = bk.box("upper", -h, h, -h, h, T.z_t4, T.z_upper - 0.8, M["wall"])
    ci = h - WALL5
    bk.cut(body, [bk.box("cut", -ci, ci, -ci, ci, T.z_t4 - 0.5, T.z_arch5 + 0.6, M["wall"])])
    fr = faces(h, h)
    # сквозные арки двумя вырезами: запад — восток и север — юг пересекаются в середине
    for pair in (("W", "E"), ("N", "S")):
        f = fr[pair[0]]
        bk.cut(body, [bk.extrude("cut", f, bk.arch(f.length / 2, w, T.z_t4 - 0.5, spring), -2 * h - 0.5, 0.5,
                                 M["wall"])])
    parts = []
    for side, f in fr.items():
        sc = f.length / 2
        for s0, s1 in ((-0.12, sc - w / 2), (sc + w / 2, f.length + 0.12)):         # импост — по столпам
            parts.append(bk.extrude("impost", f, bk.rect(s0, s1, T.z_impost, T.z_impost + 0.3), -0.1, 0.12,
                                    M["wall"]))
        parts.append(bk.extrude("archivolt", f, bk.arch_frame(sc, w, spring, spring, 0.55), -0.1, 0.06, M["wall"]))
        parts.append(bk.extrude("keystone", f, [(sc - 0.22, T.z_arch5 - 0.05), (sc + 0.22, T.z_arch5 - 0.05),
                                                (sc + 0.32, T.z_arch5 + 0.75), (sc - 0.32, T.z_arch5 + 0.75)],
                                -0.1, 0.12, M["wall"]))
    parts += steps(h, h, ((z_frieze, z_frieze + 0.15, 0.08),                        # архитрав
                          (T.z_upper - 0.8, T.z_upper - 0.5, 0.35),                  # венчающий карниз
                          (T.z_upper - 0.5, T.z_upper, 0.7)))
    # парапет на площадке звона: столбики по углам и у арки, между ними решётка
    p = HU - 0.35
    pf = faces(p, p)
    for side, f in pf.items():
        posts = (0.0, p - 2.05, p + 2.05, 2 * p)
        for s in posts:
            parts.append(bk.extrude("post", f, bk.rect(s - 0.3, s + 0.3, T.z_t4, T.z_t4 + 1.35), -0.6, 0.0,
                                    M["wall"]))
        for s0, s1 in zip(posts, posts[1:]):
            parts += railing(f, s0 + 0.3, s1 - 0.3, T.z_t4, 1.15, d=-0.3)
    # большой колокол по центру (S-23: «перевешен в верхний ярус, по центру его»), над ним два малых
    parts.append(bk.box("beam", -0.15, 0.15, -ci - 0.3, ci + 0.3, T.z_impost - 1.9, T.z_impost - 1.6, M["wood"]))
    parts += bell(0.0, 0.0, T.z_impost - 1.9, 2.3, 2.0)
    parts.append(bk.box("beam", -0.15, 0.15, -ci - 0.3, ci + 0.3, T.z_impost, T.z_impost + 0.3, M["wood"]))
    for v in (-1.1, 1.1):
        parts += bell(0.0, v, T.z_impost, 0.9, 0.85)
    return [body] + parts


# ---------- венчание (ярус 6): кровля, постамент с часами, фонарик, шпиль ----------

def square(h, z):
    return [(-h, -h, z), (h, -h, z), (h, h, z), (-h, h, z)]


def crown():
    """Постамент — крутая кровля от венчающего карниза до фонарика; из скатов выходят аттики с часами."""
    h = T.upper / 2 + 0.75
    top, z_roof = T.roof
    parts = [bk.loft("roof", [square(h, T.z_upper), square(top, z_roof)], M["tin"])]
    c = (0.0, 0.0)
    d, zc, dist = T.clock
    aw, back = d + 0.6, dist - T.lantern[0]           # аттик — полукруг вокруг циферблата; назад уходит под кровлю
    r = aw / 2
    z_foot = T.z_upper + (z_roof - T.z_upper) * (h - dist) / (h - top) - 0.4   # скат под плоскостью аттика
    for k in range(4):
        a = k * math.pi / 2
        n, t = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
        fr = bk.Frame((dist * n[0] - r * t[0], dist * n[1] - r * t[1]), t, n, aw)
        attic = [(0.0, z_foot), (aw, z_foot)] + \
            [(r + r * math.cos(math.pi * i / 16), zc + r * math.sin(math.pi * i / 16)) for i in range(17)]
        parts.append(bk.extrude("attic", fr, attic, -back, 0.0, M["wall"]))
        parts.append(bk.extrude("attic_cap", fr, bk.arch_frame(r, aw, zc, zc, 0.12), -back, 0.12, M["tin"]))
        dial = [(r + d / 2 * math.cos(2 * math.pi * i / 32), zc + d / 2 * math.sin(2 * math.pi * i / 32))
                for i in range(32)]
        parts.append(bk.extrude("dial", fr, dial, -0.02, 0.06, M["dark"]))
        rim = [(r + (d / 2 + 0.08) * math.cos(2 * math.pi * i / 32), zc + (d / 2 + 0.08) * math.sin(2 * math.pi * i / 32))
               for i in range(32)]
        parts.append(bk.extrude("dial_rim", fr, rim, -0.02, 0.04, M["gold"]))
        parts.append(bk.extrude("hand", fr, bk.rect(r - 0.03, r + 0.03, zc, zc + 0.7 * d / 2), 0.06, 0.09, M["gold"]))
        parts.append(bk.extrude("hand", fr, bk.rect(r, r + 0.5 * d / 2, zc - 0.03, zc + 0.03), 0.06, 0.09, M["gold"]))
    la, z0, z1 = T.lantern
    # фонарик — восьмигранное основание шпиля с арочными окошками на всех гранях
    lantern = bk.loft("lantern", [bk.ngon(c, la, z0), bk.ngon(c, la, z1 - 0.3)], M["wall"])
    op = Openings(recess=0.25)
    for k in range(8):
        op.window(bk.Frame.radial(c, la, k * math.pi / 4), 0.0, 0.5, z0 + 0.9, z0 + 1.75, frame=False)
    parts += op.apply(lantern)
    parts.append(bk.loft("lan_cornice", [bk.ngon(c, la + 0.2, z1 - 0.3), bk.ngon(c, la + 0.2, z1)], M["wall"]))
    zs0, zs1 = T.z_spire
    parts.append(bk.loft("lan_roof", [bk.ngon(c, la + 0.3, z1), bk.ngon(c, 0.7, zs0)], M["tin"]))
    # шпиль: восемь граней, профиль чуть выпуклый (фото 2011); яблоко и крест
    prof = [(0.55, 0.0), (0.5, 0.25), (0.4, 0.5), (0.26, 0.75), (0.1, 0.95), (0.05, 1.0)]
    parts.append(bk.loft("spire_ring", [bk.ngon(c, 0.7, zs0), bk.ngon(c, 0.7, zs0 + 0.25)], M["gold"]))
    parts.append(bk.loft("spire", [bk.ngon(c, q, zs0 + t * (zs1 - zs0)) for q, t in bk.spline(prof)] +
                         [bk.ngon(c, 0.0, zs1 + 0.1)], M["gold"]))
    ra = T.apple / 2
    parts.append(bk.lathe("apple", c, [(ra * math.sin(math.pi * i / 12), zs1 + ra - ra * math.cos(math.pi * i / 12))
                                       for i in range(13)], M["gold"], seg=24))
    zc0, th = zs1 + T.apple, 0.08
    fr = bk.Frame(c, (0.0, 1.0), (1.0, 0.0))            # крест поперёк оси: s — на юг
    parts.append(bk.extrude("cross", fr, bk.rect(-th / 2, th / 2, zc0 - 0.05, T.z_top), -th / 2, th / 2, M["gold"]))
    zb = T.z_top - 0.35
    parts.append(bk.extrude("cross", fr, bk.rect(-0.3, 0.3, zb - th / 2, zb + th / 2), -th / 2, th / 2, M["gold"]))
    return parts


# ---------- пристройка с запада ----------

def annex():
    """Двухуровневая пристройка из плитняка (S-23) в линии стены: стены до z_annex, над ними деревянный свес — это
    продолжение кровли стены (фото 2011, 2026), выше зелёная вальма с коньком у грани столпа. На западном фасаде —
    дверь, внизу два окна, вверху пять окошек (фото 2011)."""
    au, av = T.annex
    ze = T.z_annex
    zr0, zr1 = T.z_annex_roof
    inner = 6.0                                         # вальма — над внутренним прямоугольником ±inner
    body = bk.box("annex", au, -HU + 0.3, -av, av, BASE_Z, ze, M["wall"])
    west = bk.Frame.between((au, -av), (au, av), (0.0, 0.0))     # s = v + av
    L = west.length
    op, parts = Openings(recess=0.3), []
    for k in range(-2, 3):
        op.slit(west, L / 2 + 2.45 * k, 0.3, 5.0, 5.55)
    for s in (1.85, L - 1.85):
        op.slit(west, s, 0.45, 1.1, 1.95)
    op.cutters.append(bk.extrude("cut", west, bk.arch(L / 2, 1.5, 0.0, 1.85), -0.35, 0.5, M["wall"]))
    parts.append(bk.extrude("door", west, bk.arch(L / 2, 1.5, 0.0, 1.85), -0.4, -0.3, M["wood"]))
    parts.append(bk.box("annex_top", au + 1.1, -HU + 0.3, -inner, inner, ze - 0.1, zr0 + 0.05, M["wall"]))
    parts.append(bk.hip_roof("annex_roof", au + 1.1, 3.0, -inner, inner, zr0, zr1 - zr0, 0.25, M["green"]))
    o, zo = 0.35, ze - 0.15                             # деревянный свес: от края стен вверх к вальме
    for quad in ([(au - o, -av - o, zo), (au - o, av + o, zo), (au + 1.1, inner, zr0), (au + 1.1, -inner, zr0)],
                 [(au - o, -av - o, zo), (-HU, -av - o, zo), (-HU, -inner, zr0), (au + 1.1, -inner, zr0)],
                 [(au - o, av + o, zo), (au + 1.1, inner, zr0), (-HU, inner, zr0), (-HU, av + o, zo)]):
        parts.append(bk.slab("skirt", [(u, v, z + 0.03) for u, v, z in quad], 0.12, M["wood"]))
    return op.apply(body) + parts


# ---------- сборка ----------

VIEWS = {  # превью: глаз и цель в осях здания (u, v, z)
    "west": ((-60.0, 0.0, 1.6), (0.0, 0.0, 26.0), (768, 1152)),              # со двора Крома, как фото 2011
    "northeast": ((40.0, -45.0, 1.6), (0.0, 0.0, 24.0), (768, 1152)),        # с набережной Псковы, как фото 2026
    "southwest_high": ((-45.0, 40.0, 40.0), (0.0, 0.0, 30.0), (1280, 720)),
    "crown": ((-22.0, 14.0, 44.0), (0.0, 0.0, 38.0), (1024, 1024)),
}


def main():
    bk.reset_scene()
    bk.use_colors(krom_plan.COLORS)
    objs = shaft() + upper() + crown() + annex()
    obj = bk.join(objs, NAME)
    bk.box_uv(obj)
    me = obj.data
    print(f"[belfry] {len(objs)} тел → {NAME}: {len(me.vertices)} вершин, {len(me.polygons)} граней, "
          f"слоты {[m.name for m in me.materials]}")
    bk.export_glb(obj, NAME)
    ground = bk.box("ground", -150, 150, -150, 150, -0.05, 0.0, bk.material("ground", (0.12, 0.16, 0.08)))  # только превью
    ground.hide_select = True
    for name, (eye, target, size) in VIEWS.items():
        bk.render_preview(f"belfry_{name}", eye=(eye[0], -eye[1], eye[2]), target=(target[0], -target[1], target[2]),
                          size=size, lens=35.0)


main()
