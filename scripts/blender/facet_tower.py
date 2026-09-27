"""facet_tower.py — гранёные башни (четверики и восьмерики) с шатром, герои M3 (D-018, D-019).

    python scripts/bl_run.py scripts/blender/facet_tower.py                 # все башни с планом FacetTowerPlan
    python scripts/bl_run.py scripts/blender/facet_tower.py -- Власьевская  # одна

Числа — из krom_plan (FacetTowerPlan: SMERDYA, VLASYEVSKAYA, RYBNITSKAYA), источники записаны там. Здесь только
детали «на глаз»: подзор по краю свеса и стык тёса у тёсового шатра, рёбра по углам листового (медного), толщины
поясов, силуэт воина на прапоре Довмонтовой. Вышка и венчание — общие с круглыми башнями (bl_krom.lookout,
bl_krom.finial). Выгрузка — build/blender/<имя ассета>.glb (в UE ставит heroes_krom.py),
превью — media/renders/blender/<имя>_*.png. Оси башни: u — по азимуту yaw, v — вправо, z — от земли в точке base.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402
import krom_plan  # noqa: E402
from bl_krom import M, Openings  # noqa: E402

C = (0.0, 0.0)


def plans():
    return [p for p in vars(krom_plan).values() if isinstance(p, krom_plan.FacetTowerPlan) and p.hero]


def inset(t, z):
    """Сдвиг граней на отметке z: стены сходятся к верху на taper (ниже земли — как у земли)."""
    return -t.taper * max(0.0, min(1.0, z / t.z_eave))


def contour(t, grow=0.0):
    return krom_plan.facet_contour(t.size, t.chamfer, grow)


def ring(pts, z):
    return [(u, v, z) for u, v in pts]


def facades(t, grow):
    """Грани контура: {азимут нормали: Frame}; s — вдоль грани от её начала, нормаль наружу."""
    pts = contour(t, grow)
    n = len(pts)
    return {round(360 * i / n): bk.Frame.between(pts[i], pts[(i + 1) % n], C) for i in range(n)}


def body(t):
    """Стены из плитняка до z_eave: проезд (отдельным вырезом), бойницы и окна ярусов, пояса."""
    z1 = t.z_eave - 0.15
    rings = [ring(contour(t), t.z_foot)] + ([ring(contour(t), 0.0)] if t.taper else []) + \
        [ring(contour(t, inset(t, z1)), z1)]
    shell = bk.loft("body", rings, M[t.mat])
    if t.gate:
        w, spring, gv = t.gate
        su = t.size[0]
        fr = bk.Frame((-su / 2 - 1.0, gv), (0.0, 1.0), (1.0, 0.0))     # s — по v, d — по u насквозь
        bk.cut(shell, [bk.extrude("cut", fr, bk.arch(0.0, w, -0.3, spring), 0.0, su + 2.0, M[t.mat])])
    op = Openings(recess=0.8, mat=t.mat)
    for z0, h, w, where in t.slits:
        fr = facades(t, inset(t, z0 + h / 2) - 0.15)
        for az, s in where:
            f = fr[az]
            op.slit(f, f.length / 2 + s, w, z0, z0 + h)
    for zc, d, where in t.holes:  # круглые бойницы — тот же вырез, что у щелей, только круглый
        fr = facades(t, inset(t, zc) - 0.15)
        for az, s in where:
            f = fr[az]
            sc = f.length / 2 + s
            op.cutters.append(bk.extrude("cut", f, circle(sc, zc, d / 2), -op.recess, 0.6, M[t.mat]))
            op.parts.append(bk.extrude("glass", f, circle(sc, zc, d / 2 - 0.02), -op.recess - 0.05, -op.recess + 0.03,
                                       M["glass"]))
    leaves = []
    for az, s, w, spring in t.doors:  # дверь в арочной нише глубиной 0,6 м, створка из тёса
        f = facades(t, inset(t, spring / 2))[az]
        sc = f.length / 2 + s
        op.cutters.append(bk.extrude("cut", f, bk.arch(sc, w, -0.3, spring), -0.6, 0.6, M[t.mat]))
        leaves.append(bk.extrude("door", f, bk.arch(sc, w, 0.0, spring), -0.62, -0.52, M["wood"]))
    parts = op.apply(shell) + leaves
    for z0, h, proud in t.belts:
        parts.append(bk.loft("belt", [ring(contour(t, inset(t, z0) + proud), z0),
                                      ring(contour(t, inset(t, z0 + h) + proud), z0 + h)], M[t.mat]))
    if t.kiot:
        parts += kiot(t)
    return parts


def circle(sc, zc, r, n=12):
    """Круг на фасаде (s, z): середина (sc, zc), радиус r."""
    return [(sc + r * math.cos(2 * math.pi * k / n), zc + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def keel(sc, w, z0, h):
    """Килевидная арка на фасаде (s, z): прямые бока до 0,55 h, дальше вогнутые дуги к острию."""
    side = [(0.5, 0.55), (0.42, 0.72), (0.25, 0.83), (0.08, 0.9)]
    right = [(sc + k * w, z0 + m * h) for k, m in side]
    left = [(sc - k * w, z0 + m * h) for k, m in reversed(side)]
    return [(sc - w / 2, z0), (sc + w / 2, z0)] + right + [(sc, z0 + h)] + left


def kiot(t):
    """Киот над воротами: тёмная килевидная рамка, белое поле и образ (золото — до своих материалов M4)."""
    az, z0, w, h = t.kiot
    f = facades(t, inset(t, z0 + h / 2))[az]
    sc = f.length / 2
    return [bk.extrude("kiot", f, keel(sc, w, z0, h), -0.05, 0.18, M["dark"]),
            bk.extrude("kiot_field", f, keel(sc, w - 0.3, z0 + 0.15, h - 0.3), 0.0, 0.2, M["wall"]),
            bk.extrude("kiot_image", f, bk.rect(sc - 0.3, sc + 0.3, z0 + 0.35, z0 + 1.05), 0.0, 0.23, M["gold"])]


def lerp(a, b, f):
    return [(p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f) for p, q in zip(a, b)]


def tent(t):
    """Шатёр: софит под свесом, свес с изломом («полицей»), скаты до вершины или до вышки. Тёсовый — с подзором
    и стыком тёса; листовой (медь) — гладкий, с рёбрами-фальцами по углам."""
    ze = t.z_eave
    wall = contour(t, inset(t, ze) - 0.3)
    eave = contour(t, inset(t, ze) + t.eave)
    kick = contour(t, inset(t, ze) + t.eave - t.kick[0])
    zk = t.kick[1]
    if t.tent_r > 0:
        k = t.tent_r / max(max(abs(u), abs(v)) for u, v in kick)
        top = [(u * k, v * k) for u, v in kick]
        rings = [ring(wall, ze - 0.1), ring(eave, ze), ring(kick, zk), ring(top, t.z_tent)]
    else:
        top = [(0.0, 0.0)] * len(kick)
        rings = [ring(wall, ze - 0.1), ring(eave, ze), ring(kick, zk), [(0.0, 0.0, t.z_tent)]]
    parts = [bk.loft("tent", rings, M[t.tent_mat])]
    if t.tent_mat != "wood":
        return parts + [hip_rib(p, q, zk, t.z_tent, M[t.tent_mat]) for p, q in zip(kick, top)]
    n = len(eave)
    for i in range(n):  # подзор по краю свеса — доска на каждой грани
        fr = bk.Frame.between(eave[i], eave[(i + 1) % n], C)
        parts.append(bk.extrude("podzor", fr, bk.rect(-0.05, fr.length + 0.05, ze - 0.3, ze + 0.05), -0.08, 0.02,
                                M["wood"]))
    # стык тёса на середине скатов — на фото виден поясом
    zm = (zk + t.z_tent) / 2
    f0, f1 = (zm - 0.12 - zk) / (t.z_tent - zk), (zm + 0.02 - zk) / (t.z_tent - zk)
    parts.append(bk.loft("tes_seam", [ring(push(lerp(kick, top, f0), 0.06), zm - 0.12),
                                      ring(push(lerp(kick, top, f1), 0.03), zm + 0.02)], M["wood"]))
    return parts


def hip_rib(p, q, z0, z1, mat, w=0.05, h=0.05):
    """Фальц по углу листового шатра: трёхгранный брусок от угла p (на z0) к верху q (на z1), к верху тоньше."""
    r = math.hypot(*p)
    ru, rv = p[0] / r, p[1] / r            # наружу от оси
    tu, tv = -rv, ru                       # поперёк ребра, горизонтально
    q = (p[0] + 0.95 * (q[0] - p[0]), p[1] + 0.95 * (q[1] - p[1]))
    zq = z0 + 0.95 * (z1 - z0)

    def section(c, z, k):
        return [(c[0] - 0.03 * ru + k * w * tu, c[1] - 0.03 * rv + k * w * tv, z),
                (c[0] - 0.03 * ru - k * w * tu, c[1] - 0.03 * rv - k * w * tv, z),
                (c[0] + k * h * ru, c[1] + k * h * rv, z + k * h * 0.5)]
    return bk.mesh("rib", section(p, z0, 1.0) + section(q, zq, 0.4),
                   [[0, 1, 2], [3, 4, 5], [0, 1, 4, 3], [1, 2, 5, 4], [2, 0, 3, 5]], mat)


def push(pts, d):
    """Точки контура дальше от оси на d (накладка поверх ската)."""
    return [(u * (1 + d / math.hypot(u, v)), v * (1 + d / math.hypot(u, v))) for u, v in pts]


def lookout(t):
    """Вышка над усечённым шатром (bl_krom.lookout); поясок охватывает верх шатра по углам."""
    if not t.lookout_kind:
        return []
    if t.lookout_sides:  # гранёная вышка: радиусы до граней, поясок — по верху шатра
        return bk.lookout(C, t.lookout_kind, (t.tent_r, t.z_tent), t.lookout, t.lookout_eave, t.z_top,
                          sides=t.lookout_sides)
    corner = t.tent_r / math.cos(math.pi / t.sides) if t.sides == 8 else t.tent_r * math.sqrt(2)
    return bk.lookout(C, t.lookout_kind, (corner, t.z_tent), t.lookout, t.lookout_eave, t.z_top)


def warrior_vane(t):
    """Прапор Довмонтовой (акт ГИКЭ 2016, фото S-40: 02, 03, 16): яблоко и копьё до z_vane, флажок с косицами
    на восток, на перекладине с запада — плоская фигура воина ≈1,15 м, рукой держит копьё. Размеры по фото ±30 %."""
    parts = bk.finial(C, t.z_top, t.z_vane)[:2]           # яблоко и шпилёк-копьё, флажок свой
    zv = t.z_vane
    zb = zv - 1.45                                        # перекладина и низ флажка
    fr = bk.Frame(C, (0.0, 1.0), (1.0, 0.0))              # s — на восток, d — по u
    parts.append(bk.extrude("vane", fr, [(0.03, zb), (0.8, zb), (0.62, zb + 0.42), (0.8, zb + 0.85), (0.03, zb + 0.85)],
                            -0.015, 0.015, M["dark"]))
    parts.append(bk.extrude("vane_bar", fr, bk.rect(-0.62, 0.0, zb - 0.05, zb), -0.02, 0.02, M["dark"]))
    sc = -0.38                                            # фигура: ноги, корпус, рука к копью, голова в шлеме
    body = [(-0.13, 0.0), (-0.04, 0.0), (0.0, 0.40), (0.04, 0.0), (0.13, 0.0), (0.09, 0.52), (0.12, 0.82),
            (0.34, 0.98), (0.34, 1.04), (0.10, 0.93), (0.07, 0.95), (0.09, 1.04), (0.05, 1.12), (0.0, 1.15),
            (-0.05, 1.12), (-0.09, 1.04), (-0.07, 0.95), (-0.13, 0.88), (-0.17, 0.58), (-0.12, 0.56), (-0.10, 0.52)]
    parts.append(bk.extrude("vane_warrior", fr, [(sc + x, zb + z) for x, z in body], -0.02, 0.02, M["dark"]))
    return parts


def views(t):
    """Превью в осях башни: (глаз, цель, размер кадра[, объектив мм]) — с направлений фото S-40, по которым сняты
    размеры; для остальных — с трёх сторон и сверху."""
    zc = t.z_top / 2
    special = {
        "Довмонтова": {"yard_north": ((88.7, -7.8, 1.6), (0.0, 0.0, 9.0), (1280, 840), 60.0),         # фото 02
                       "yard_east": ((-5.1, 58.8, 1.6), (0.0, 0.0, 9.0), (1280, 719), 46.0),          # фото 01
                       "zavelichye": ((-5.0, -160.0, 3.0), (0.0, 0.0, 11.0), (960, 1280), 100.0),     # фото 07
                       "high": ((-30.0, -25.0, 25.0), (0.0, 0.0, 10.0), (1280, 720))},
        "Власьевская": {"zavelichye": ((-5.0, -140.0, 4.0), (0.0, 0.0, 22.0), (1280, 853), 100.0),   # фото 04
                        "yard": ((0.0, 52.0, 1.6), (0.0, 0.0, 14.0), (1280, 1040), 47.0),           # фото 07
                        "road": ((-31.0, -9.0, 1.6), (0.0, 0.0, 14.0), (1280, 720), 23.0)},         # фото 14
        "Рыбницкая": {"street": ((36.0, -23.4, 1.6), (0.0, 0.0, 11.0), (768, 922), 27.0),          # фото 01
                      "dovmont": ((-36.5, 10.5, 1.6), (0.0, 0.0, 9.0), (1280, 853), 28.0),         # фото 08
                      "high": ((30.0, 25.0, 25.0), (0.0, 0.0, 9.0), (1280, 720))},
    }
    if t.name in special:
        return special[t.name]
    d = 2.2 * t.z_top
    return {"front": ((d, 0.0, 1.6), (0.0, 0.0, zc), (768, 1152)),
            "side": ((0.0, d, 1.6), (0.0, 0.0, zc), (768, 1152)),
            "back_high": ((-0.8 * d, -0.6 * d, 0.8 * t.z_top), (0.0, 0.0, zc), (1280, 720))}


def build(t):
    name = t.hero.rsplit("/", 1)[1]
    bk.reset_scene()
    bk.use_colors(krom_plan.COLORS)
    objs = body(t) + tent(t) + lookout(t)   # порядок создания тел задаёт порядок слотов материалов
    objs += warrior_vane(t) if t.vane == "warrior" else bk.finial(C, t.z_top, t.z_vane)
    obj = bk.join(objs, name)
    bk.box_uv(obj)
    me = obj.data
    print(f"[facet_tower] {t.name}: {len(objs)} тел → {name}: {len(me.vertices)} вершин, {len(me.polygons)} граней, "
          f"слоты {[m.name for m in me.materials]}")
    bk.export_glb(obj, name)
    ground = bk.box("ground", -150, 150, -150, 150, -0.05, 0.0, bk.material("ground", (0.12, 0.16, 0.08)))  # превью
    ground.hide_select = True
    for view, (eye, target, size, *lens) in views(t).items():
        bk.render_preview(f"{name}_{view}", eye=(eye[0], -eye[1], eye[2]), target=(target[0], -target[1], target[2]),
                          size=size, lens=lens[0] if lens else 35.0)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    todo = [p for p in plans() if not argv or p.name in argv]
    if not todo:
        raise SystemExit(f"[facet_tower] нет плана для {argv}; есть: {[p.name for p in plans()]}")
    for t in todo:
        build(t)


main()
