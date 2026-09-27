"""round_tower.py — круглые башни Крома с тёсовым шатром и сторожевой вышкой, герои M3 (D-018, D-019).

    python scripts/bl_run.py scripts/blender/round_tower.py              # все башни с планом RoundTowerPlan
    python scripts/bl_run.py scripts/blender/round_tower.py -- Кутекрома  # одна

Числа — из krom_plan (RoundTowerPlan: KUTEKROMA …), источники записаны там. Здесь только детали, снятые с фото
«на глаз»: сужение тела, подзор свеса, число досок шатра, столбы и перила вышки, флюгер.
Выгрузка — build/blender/<имя ассета>.glb (в UE ставит heroes_krom.py), превью — media/renders/blender/<имя>_*.png.
Оси башни: u — на север, v — на восток (yaw 0), z — от земли в точке base (со стороны Крома).
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
    return [p for p in vars(krom_plan).values() if isinstance(p, krom_plan.RoundTowerPlan) and p.hero]


def local(t, xy):
    """Точка (x, y) плана → оси башни (u, v)."""
    return xy[0] - t.center[0], xy[1] - t.center[1]


def radius_at(t, z):
    """Радиус тела на отметке z: сужение от d[0] у земли до d[1] у свеса (фото — ≈5 %)."""
    k = max(0.0, min(1.0, z / t.z_eave))
    return (t.d[0] + (t.d[1] - t.d[0]) * k) / 2


def body(t):
    """Тело из плитняка с бойницами ярусов; верх — под свесом шатра. Низ — z_foot: снаружи земля ниже base."""
    z1 = t.z_eave - 0.15
    shell = bk.lathe("body", C, [(radius_at(t, t.z_foot), t.z_foot), (radius_at(t, z1), z1)], M["stone"], seg=64)
    op = Openings(recess=0.8, mat="stone")
    for z0, h, w, azimuths in t.slits:
        r = radius_at(t, z0 + h / 2)
        for az in azimuths:
            op.slit(bk.Frame.radial(C, r - 0.15, math.radians(az)), 0.0, w, z0, z0 + h)
    parts = op.apply(shell)
    if t.plinth:  # откос-подошва: у земли тело шире на вынос, к верху откоса сходится с телом
        out, top = t.plinth
        r0 = radius_at(t, 0.0)
        parts.append(bk.lathe("plinth", C, [(r0 + out, t.z_foot), (r0 + out, 0.0), (radius_at(t, top) - 0.02, top)],
                              M["stone"], seg=64))
    return parts


def tent(t):
    """Шатёр: подзор по краю свеса, излом («полица») и конус до пояска вышки или до вершины; стык тёса поясом."""
    zk_r, zk = t.kick
    rb = radius_at(t, t.z_eave)
    top = [(t.tent_r, t.z_tent), (0.0, t.z_tent + 0.2)] if t.tent_r > 0 else [(0.0, t.z_tent)]
    parts = [bk.lathe("tent", C, [(rb - 0.3, t.z_eave - 0.1), (t.eave_r, t.z_eave), (zk_r, zk)] + top,
                      M["wood"], seg=32),
             # подзор: узкое кольцо по краю свеса (на фото — пропиленные концы досок)
             bk.lathe("podzor", C, [(t.eave_r - 0.06, t.z_eave - 0.3), (t.eave_r + 0.02, t.z_eave - 0.3),
                                    (t.eave_r + 0.02, t.z_eave + 0.05), (t.eave_r - 0.06, t.z_eave + 0.05)],
                      M["wood"], seg=48, closed=True, smooth=False)]
    # стык тёса на середине конуса — на фото виден поясом
    zm = (zk + t.z_tent) / 2
    rm = zk_r + (t.tent_r - zk_r) * (zm - zk) / (t.z_tent - zk)
    parts.append(bk.lathe("tes_seam", C, [(rm - 0.05, zm - 0.12), (rm + 0.06, zm - 0.12), (rm + 0.03, zm + 0.02),
                                          (rm - 0.05, zm + 0.02)], M["wood"], seg=32, closed=True, smooth=False))
    return parts


def lookout(t):
    """Сторожевая вышка по lookout_kind (bl_krom.lookout); без вышки — ничего. Венчание ставит bl_krom.finial."""
    if not t.lookout_kind:
        return []
    return bk.lookout(C, t.lookout_kind, (t.tent_r, t.z_tent), t.lookout, t.lookout_eave, t.z_top)


def views(t):
    """Превью в осях башни: (глаз, цель, размер кадра[, объектив мм]). Кутекрома — со двора (с юга), с Псковы
    (с востока), сверху с севера; остальные — с направлений фото, по которым сняты размеры (S-25)."""
    bu, bv = local(t, t.base)
    zc = t.z_top / 2
    special = {
        "Средняя": {"pskova": ((0.0, 140.0, 1.6), (0.0, 0.0, 12.0), (1280, 720), 85.0),           # как фото S-40 (04)
                    "yard": ((bu - 5.0, bv - 45.0, 1.6), (0.0, 0.0, 12.0), (768, 1152)),
                    "north_high": ((40.0, -25.0, 28.0), (0.0, 0.0, 14.0), (1280, 720))},
        "Троицкая": {"veche": ((5.4, -87.8, 1.6), (0.0, 0.0, 12.0), (1280, 853), 61.0),           # фото S-40 (13)
                     "gate_south": ((-43.5, -10.0, 1.6), (0.0, 0.0, 12.0), (1280, 853), 35.0),
                     "east_high": ((10.0, 45.0, 30.0), (0.0, 0.0, 10.0), (1280, 720))},
        "Плоская": {"zavelichye": ((3.6, -140.0, 4.0), (0.0, 0.0, 12.0), (1280, 1280), 100.0),     # как zav_north_mouth
                    "pskova_bank": ((-50.0, 84.4, 3.0), (0.0, 0.0, 11.0), (1152, 768), 52.0),    # pskova_bank
                    "yard_high": ((-45.0, 30.0, 25.0), (0.0, 0.0, 10.0), (1280, 720))},
        "Высокая": {"pskova_bank": ((-107.2, 95.1, 5.0), (0.0, 0.0, 17.0), (768, 1152), 52.0),  # pskova_bank
                    "north": ((50.0, -10.0, 1.6), (0.0, 0.0, 17.0), (768, 1152)),
                    "west_high": ((-10.0, -60.0, 35.0), (0.0, 0.0, 18.0), (1280, 720))},
    }
    if t.name in special:
        return special[t.name]
    if t.name != "Кутекрома":
        return {"yard": ((bu * 5 - 40.0, bv * 5, 1.6), (0.0, 0.0, zc), (768, 1152)),
                "east": ((5.0, 2.2 * t.z_top, 1.6), (0.0, 0.0, zc), (768, 1152)),
                "north_high": ((1.5 * t.z_top, -0.8 * t.z_top, t.z_top), (0.0, 0.0, zc), (1280, 720))}
    return {"yard": ((bu - 40.0, bv, 1.6), (0.0, 0.0, 15.0), (768, 1152)),
            "pskova": ((10.0, 70.0, 1.6), (0.0, 0.0, 16.0), (768, 1152)),
            "north_high": ((45.0, -25.0, 30.0), (0.0, 0.0, 17.0), (1280, 720))}


def build(t):
    name = t.hero.rsplit("/", 1)[1]
    bk.reset_scene()
    bk.use_colors(krom_plan.COLORS)
    objs = body(t) + tent(t) + lookout(t) + bk.finial(C, t.z_top, t.z_vane)
    obj = bk.join(objs, name)
    bk.box_uv(obj)
    # нуль высот — земля в base, а ось башни — в center: сдвигать не нужно, heroes_krom ставит актор в center
    me = obj.data
    print(f"[round_tower] {t.name}: {len(objs)} тел → {name}: {len(me.vertices)} вершин, {len(me.polygons)} граней, "
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
        raise SystemExit(f"[round_tower] нет плана для {argv}; есть: {[p.name for p in plans()]}")
    for t in todo:
        build(t)


main()
