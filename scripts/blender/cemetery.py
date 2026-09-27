"""cemetery.py — надгробия и ограда Мироносицкого кладбища на Завеличье: низкополигональные модели для HISM (M5+).

    python scripts/bl_run.py scripts/blender/cemetery.py                 # все
    python scripts/bl_run.py scripts/blender/cemetery.py -- PlotCross    # одна (имя без SM_Cem_)

Выгрузка — build/blender/SM_Cem_<Имя>.glb (в UE ставит scripts/cemetery_krom.py по точкам
scripts/cemetery_points.py), сведения — build/blender/cemetery_report.json (габарит, треугольники, слоты), превью —
media/renders/blender/cemetery_<Имя>.png и cemetery_lineup.png (все рядом с человеком 1,75 м).

Что на кладбище по фото (build/mironositsy_refs, S-81): у храма и главной аллеи — тесные ряды участков в
металлических оградках (чёрных, «серебрянке», зелёных), в них чёрные гранитные стелы с цветниками, металлические
кресты, столики и скамейки (фото 005, 013); отдельно — гранитные стелы с цветником без оградки (013, 014),
деревянные кресты; старые надгробия XIX в. — каменные тумбы с крестом. Размеры — «на глаз» по фото и по обычным
размерам участков (гипотеза): участок 1,8 × 2,4 м, оградка 0,8 м, стела 0,5 × 1,0 м, крест 1,5–1,9 м.
Деревянный крест — восьмиконечный с двускатной «кровелькой», как принято на Псковщине (гипотеза, по фото не видно).

Оси модели: u — вдоль длинной стороны могилы на восток (к памятнику: он «в ногах», надпись смотрит на запад, ко
входу в оградку — гипотеза), v — вправо (на юг), z — от земли. Поворот yaw в points.json — азимут +u (как у
furniture). Низ всего, что стоит на земле, уходит на SINK под землю: на уклоне ничего не висит.
Нижняя перекладина крестов поднята северным концом (−v), как в pskov_church.cross8.
Материалы — слоты по ключам krom_plan.COLORS (новых нет): dark — чёрный гранит и крашеный металл, tin — оградки
«серебрянкой», green — зелёные оградки, wood — дерево крестов, скамеек и столиков, stone — серый гранит, бетон и
известняк старых надгробий, ruin — земля холмиков (тёплый бурый), wall — побелка ограды кладбища.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402
import krom_plan  # noqa: E402
from bl_krom import M  # noqa: E402

SINK = 0.15              # м под землю у всего, что стоит на земле
REPORT = os.path.join(bk.BUILD_DIR, "cemetery_report.json")

PLOT = (2.4, 1.8)        # участок в оградке: длина по u, ширина по v (гипотеза по фото 005)
FENCE_H = 0.8            # высота оградки
BAR_STEP = 0.24          # шаг прутьев оградки


def beam(name, p0, p1, w, mat, caps=True):
    """Брус квадратного сечения w между точками p0 и p1 (u, v, z); caps=False — без торцов (прутья: торцы не видны)."""
    d = [b - a for a, b in zip(p0, p1)]
    length = math.sqrt(sum(c * c for c in d))
    t = [c / length for c in d]
    up = (0.0, 0.0, 1.0) if abs(t[2]) < 0.9 else (1.0, 0.0, 0.0)
    a = [t[1] * up[2] - t[2] * up[1], t[2] * up[0] - t[0] * up[2], t[0] * up[1] - t[1] * up[0]]
    la = math.sqrt(sum(c * c for c in a))
    a = [c / la for c in a]
    b = [t[1] * a[2] - t[2] * a[1], t[2] * a[0] - t[0] * a[2], t[0] * a[1] - t[1] * a[0]]
    h = w / 2
    corners = [(-h, -h), (h, -h), (h, h), (-h, h)]
    verts = [tuple(p[i] + sa * a[i] + sb * b[i] for i in range(3)) for p in (p0, p1) for sa, sb in corners]
    faces = [[i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i] for i in range(4)]
    if caps:
        faces += [[0, 1, 2, 3], [4, 5, 6, 7]]
    return bk.mesh(name, verts, faces, mat)


def cross8(u, v, z0, h, th, mat, roof=False):
    """Восьмиконечный крест в плоскости v–z (лицом на запад, к −u): верхняя короткая перекладина (титло), средняя,
    нижняя косая — северным концом (−v) вверх. roof — двускатная «кровелька» над верхом (деревянный крест)."""
    parts = [bk.box("cross_post", u - th / 2, u + th / 2, v - th / 2, v + th / 2, z0 - SINK, z0 + h, mat)]
    for zc, half in ((0.87, 0.17), (0.70, 0.36)):
        parts.append(bk.box("cross_bar", u - th / 2, u + th / 2, v - half * h, v + half * h,
                            z0 + zc * h - th / 2, z0 + zc * h + th / 2, mat))
    a, half, zf = math.radians(24), 0.2 * h, z0 + 0.3 * h
    dv, dz = half * math.cos(a), half * math.sin(a)
    parts.append(beam("cross_foot", (u, v + dv, zf - dz), (u, v - dv, zf + dz), th, mat))
    if roof:
        zr, w, over = z0 + h + 0.02, 0.2, 0.14
        for s in (-1, 1):
            parts.append(bk.slab("cross_roof", [(u - w, v, zr + 0.12), (u + w, v, zr + 0.12),
                                                (u + w, v + s * over, zr), (u - w, v + s * over, zr)], 0.03, mat))
    return parts


def mound(u0, u1, half_w, mat="ruin", vc=0.0):
    """Холмик с серединой на v = vc: усечённая пирамида 0,15 м над землёй."""
    lo = [(u0, vc - half_w, -SINK), (u1, vc - half_w, -SINK), (u1, vc + half_w, -SINK), (u0, vc + half_w, -SINK)]
    hi = [(u0 + 0.15, vc - half_w + 0.12, 0.15), (u1 - 0.15, vc - half_w + 0.12, 0.15),
          (u1 - 0.15, vc + half_w - 0.12, 0.15), (u0 + 0.15, vc + half_w - 0.12, 0.15)]
    return bk.loft("mound", [lo, hi], M[mat])


def border(u0, u1, half_w, mat="dark", vc=0.0, h=0.12, t=0.07):
    """Цветник с серединой на v = vc: рамка из гранитных брусков вокруг могилы."""
    a, b = vc - half_w, vc + half_w
    return [bk.box("border", u0, u1, a, a + t, -SINK, h, M[mat]),
            bk.box("border", u0, u1, b - t, b, -SINK, h, M[mat]),
            bk.box("border", u0, u0 + t, a + t, b - t, -SINK, h, M[mat]),
            bk.box("border", u1 - t, u1, a + t, b - t, -SINK, h, M[mat])]


def stela(u, v, w=0.5, h=1.0, t=0.08, mat="dark", arched=False):
    """Стела на подставке у восточного края могилы, лицом на запад; arched — верх полукругом."""
    parts = [bk.box("stela_base", u - 0.14, u + 0.14, v - w / 2 - 0.06, v + w / 2 + 0.06, -SINK, 0.12, M[mat])]
    if arched:
        fr = bk.Frame((u - t / 2, v - w / 2), (0.0, 1.0), (-1.0, 0.0), w)
        prof = bk.arch(w / 2, w, 0.12, 0.12 + h - w / 2, 8)
        parts.append(bk.extrude("stela", fr, prof, -t, 0.0, M[mat]))
    else:
        parts.append(bk.box("stela", u - t / 2, u + t / 2, v - w / 2, v + w / 2, 0.12, 0.12 + h, M[mat]))
    return parts


def fence(length, width, mat, gate_w=0.7):
    """Оградка: угловые столбики с шишечками, две поперечины и прутья с шагом BAR_STEP; на западной стороне (−u)
    калитка без прутьев шириной gate_w (закрыта рамкой — сама калитка)."""
    hu, hv, H = length / 2, width / 2, FENCE_H
    parts, post = [], 0.05
    for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        u, v = su * hu, sv * hv
        parts.append(bk.box("fence_post", u - post / 2, u + post / 2, v - post / 2, v + post / 2, -SINK, H + 0.05,
                            M[mat]))
        parts.append(bk.lathe("fence_knob", (u, v), [(0.0, H + 0.05), (0.04, H + 0.08), (0.03, H + 0.12),
                                                      (0.0, H + 0.15)], M[mat], seg=6, smooth=False))
    rails = []
    for zr in (0.12, H - 0.04):
        rails += [((-hu, -hv, zr), (hu, -hv, zr)), ((hu, -hv, zr), (hu, hv, zr)), ((hu, hv, zr), (-hu, hv, zr)),
                  ((-hu, hv, zr), (-hu, -hv, zr))]
    for p0, p1 in rails:
        parts.append(beam("fence_rail", p0, p1, 0.035, M[mat]))
    sides = (((-hu, -hv), (hu, -hv)), ((hu, -hv), (hu, hv)), ((hu, hv), (-hu, hv)), ((-hu, hv), (-hu, -hv)))
    for k, (a, b) in enumerate(sides):
        L = math.dist(a, b)
        n = max(2, int(round(L / BAR_STEP)))
        for i in range(1, n):
            s = i / n
            u, v = a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s
            if k == 3 and abs(v) < gate_w / 2:          # калитка на западной стороне: рамка вместо прутьев
                continue
            parts.append(beam("fence_bar", (u, v, 0.1), (u, v, H), 0.018, M[mat], caps=False))
        if k == 3:
            for v in (-gate_w / 2, gate_w / 2):
                parts.append(beam("fence_gate", (-hu, v, 0.05), (-hu, v, H - 0.02), 0.03, M[mat]))
            for zz in (0.35, 0.55):
                parts.append(beam("fence_gate", (-hu, -gate_w / 2, zz), (-hu, gate_w / 2, zz), 0.02, M[mat]))
    return parts


def bench(u0, u1, v, mat="wood"):
    """Скамейка в оградке: доска на двух столбиках вдоль u."""
    return [bk.box("bench_seat", u0, u1, v - 0.13, v + 0.13, 0.42, 0.46, M[mat]),
            bk.box("bench_leg", u0 + 0.08, u0 + 0.14, v - 0.03, v + 0.03, -SINK, 0.42, M["dark"]),
            bk.box("bench_leg", u1 - 0.14, u1 - 0.08, v - 0.03, v + 0.03, -SINK, 0.42, M["dark"])]


def table(u, v, r=0.28):
    """Столик: квадратная столешница на одной ножке."""
    return [bk.box("table_top", u - r, u + r, v - r, v + r, 0.68, 0.72, M["wood"]),
            bk.box("table_leg", u - 0.03, u + 0.03, v - 0.03, v + 0.03, -SINK, 0.68, M["dark"])]


# ---------- модели ----------

def cross_wood():
    """Деревянный восьмиконечный крест 1,9 м с «кровелькой» на холмике, без оградки."""
    parts = cross8(0.85, 0.0, 0.0, 1.9, 0.09, M["wood"], roof=True)
    parts.append(mound(-1.0, 1.0, 0.45))
    return parts, {"size_m": [2.0, 0.9, 2.05], "footprint_m": [2.2, 1.1]}


def cross_metal():
    """Металлический крест 1,5 м (крашеная труба) с табличкой на холмике в гранитном цветнике, без оградки."""
    parts = cross8(0.85, 0.0, 0.0, 1.5, 0.05, M["dark"])
    parts.append(bk.box("plaque", 0.81, 0.83, -0.12, 0.12, 0.72, 0.9, M["stone"]))
    parts.append(mound(-0.9, 0.95, 0.4))
    parts += border(-1.0, 1.0, 0.5, "stone")
    return parts, {"size_m": [2.0, 1.0, 1.5], "footprint_m": [2.2, 1.2]}


def stela_bed():
    """Чёрная гранитная стела 0,5 × 1,0 м с цветником, без оградки (фото 013, 014)."""
    parts = stela(0.85, 0.0)
    parts += border(-0.95, 0.72, 0.42)
    parts.append(bk.box("bed", -0.9, 0.67, -0.37, 0.37, -SINK, 0.05, M["ruin"]))
    return parts, {"size_m": [1.9, 0.84, 1.12], "footprint_m": [2.1, 1.1]}


def plot_cross():
    """Участок в чёрной оградке: металлический крест и холмик."""
    L, W = PLOT
    parts = fence(L, W, "dark")
    parts += cross8(0.85, 0.0, 0.0, 1.5, 0.05, M["dark"])
    parts.append(mound(-0.95, 0.95, 0.42))
    return parts, {"size_m": [L, W, 1.5], "footprint_m": [L + 0.3, W + 0.3]}


def plot_stela():
    """Участок в оградке «серебрянкой»: гранитная стела с цветником и скамейка у северной стороны."""
    L, W = PLOT
    parts = fence(L, W, "tin")
    parts += stela(0.9, 0.2, w=0.45, h=0.95, arched=True)
    parts += border(-0.6, 0.78, 0.36, vc=0.2)
    parts.append(bk.box("bed", -0.55, 0.73, -0.11, 0.51, -SINK, 0.05, M["ruin"]))
    parts += bench(-0.9, 0.2, -0.62)
    return parts, {"size_m": [L, W, 1.07], "footprint_m": [L + 0.3, W + 0.3]}


def plot_double():
    """Семейный участок в зелёной оградке 2,4 × 2,6 м: две стелы, крест, столик и скамейка."""
    L, W = 2.4, 2.6
    parts = fence(L, W, "green")
    parts += stela(0.95, -0.55, w=0.5, h=1.0)
    parts += stela(0.95, 0.35, w=0.45, h=0.9, mat="stone")
    for vc in (-0.55, 0.35):                                  # холмик под своей стелой
        parts.append(mound(-0.5, 0.85, 0.3, vc=vc))
    parts += table(-0.75, -0.75)
    parts += bench(-1.05, -0.35, 0.95)
    return parts, {"size_m": [L, W, 1.12], "footprint_m": [L + 0.3, W + 0.3]}


def monument():
    """Старое надгробие XIX в.: ступенчатый известняковый постамент, тумба с карнизом, крест сверху (гипотеза по
    обычному виду купеческих надгробий того времени; на фото S-81 старые надгробия под деревьями не различить)."""
    parts = [bk.box("mon_step", -0.55, 0.55, -0.55, 0.55, -SINK, 0.18, M["stone"]),
             bk.box("mon_step", -0.43, 0.43, -0.43, 0.43, 0.18, 0.34, M["stone"]),
             bk.loft("mon_body", [[(-0.33, -0.33, 0.34), (0.33, -0.33, 0.34), (0.33, 0.33, 0.34), (-0.33, 0.33, 0.34)],
                                  [(-0.28, -0.28, 1.3), (0.28, -0.28, 1.3), (0.28, 0.28, 1.3), (-0.28, 0.28, 1.3)]],
                     M["stone"]),
             bk.box("mon_cornice", -0.36, 0.36, -0.36, 0.36, 1.3, 1.42, M["stone"]),
             bk.box("mon_plate", -0.335, -0.33, -0.2, 0.2, 0.6, 1.05, M["dark"])]
    parts += cross8(0.0, 0.0, 1.42, 0.85, 0.07, M["stone"])
    return parts, {"size_m": [1.1, 1.1, 2.27], "footprint_m": [1.4, 1.4]}


def wall_seg():
    """Звено ограды кладбища 3,0 м: побелённая кладка 1,1 м × 0,5 м с двускатным отливом (фото 000, 008: у ворот
    с улицы стена низкая, светлая; высота — гипотеза). Низ на 0,6 м в земле: звенья ставятся по трассе ступенями."""
    L, t, H = 3.0, 0.5, 1.1
    parts = [bk.box("wall", -L / 2, L / 2, -t / 2, t / 2, -0.6, H - 0.06, M["wall"]),
             bk.box("wall_plinth", -L / 2, L / 2, -t / 2 - 0.04, t / 2 + 0.04, -0.6, 0.25, M["wall"])]
    for s in (-1, 1):
        parts.append(bk.slab("wall_cap", [(-L / 2, 0.0, H + 0.06), (L / 2, 0.0, H + 0.06), (L / 2, s * (t / 2 + 0.06),
                                                                                           H - 0.06),
                                          (-L / 2, s * (t / 2 + 0.06), H - 0.06)], 0.03, M["tin"]))
    return parts, {"size_m": [L, t, H + 0.06], "length_m": L}


MODELS = {   # имя (SM_Cem_<имя>) → (построение, вид в points.json)
    "CrossWood": (cross_wood, "cross_wood"),
    "CrossMetal": (cross_metal, "cross_metal"),
    "Stela": (stela_bed, "stela"),
    "PlotCross": (plot_cross, "plot_cross"),
    "PlotStela": (plot_stela, "plot_stela"),
    "PlotDouble": (plot_double, "plot_double"),
    "Monument": (monument, "monument"),
    "WallSeg": (wall_seg, "wall"),
}


def human(u, v):
    """Человек 1,75 м — только превью, для масштаба."""
    skin = bk.material("preview_person", (0.55, 0.35, 0.3))
    return [bk.lathe("person_body", (u, v), [(0.0, 0.0), (0.17, 0.02), (0.2, 0.9), (0.2, 1.45), (0.0, 1.5)], skin,
                     seg=12),
            bk.lathe("person_head", (u, v), [(0.0, 1.5), (0.1, 1.56), (0.1, 1.68), (0.0, 1.75)], skin, seg=12)]


def preview_ground():
    g = bk.box("ground", -30, 30, -30, 30, -0.3, 0.0, bk.material("ground", (0.12, 0.16, 0.08)))
    g.hide_select = True
    return g


def build(name):
    fn, kind = MODELS[name]
    asset = f"SM_Cem_{name}"
    bk.reset_scene()
    bk.use_colors(krom_plan.COLORS)
    objs, info = fn()
    obj = bk.join(objs, asset)
    bk.box_uv(obj)
    me = obj.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    slots = [m.name for m in me.materials]
    print(f"[cemetery] {asset}: {len(objs)} тел, {len(me.vertices)} вершин, {tris} треугольников, слоты {slots}")
    bk.export_glb(obj, asset)
    preview_ground()
    human(-1.6, -1.3)
    d = max(info["size_m"][0], 2.2)
    bk.render_preview(f"cemetery_{name}", eye=(-1.5 * d, 1.3 * d, 1.1 * d), target=(0.0, 0.0, 0.5),
                      size=(900, 700), lens=40)
    return {"asset": asset, "kind": kind, "tris": tris, "slots": slots, **info}


def lineup():
    """Все модели в ряд с человеком — превью cemetery_lineup.png (в выгрузку не идёт)."""
    bk.reset_scene()
    bk.use_colors(krom_plan.COLORS)
    preview_ground()
    v = -10.0
    for name, (fn, _) in MODELS.items():
        objs, info = fn()
        o = bk.join(objs, name)
        w = info["size_m"][1] if name != "WallSeg" else 3.0
        if name == "WallSeg":
            o.rotation_euler = (0.0, 0.0, math.pi / 2)
        v += w / 2 + 0.9
        o.location.y = -v                 # v → Blender −y
        v += w / 2
    human(-2.0, -10.0)
    bk.render_preview("cemetery_lineup", eye=(-19.0, -2.0, 5.0), target=(0.0, -2.0, 0.4), size=(1280, 720), lens=30)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    todo = [n for n in MODELS if not argv or n in argv]
    if not todo:
        raise SystemExit(f"[cemetery] нет модели {argv}; есть: {list(MODELS)}")
    report = {}
    if os.path.exists(REPORT):
        with open(REPORT, encoding="utf-8") as f:
            report = json.load(f)
    for n in todo:
        r = build(n)
        report[r["asset"]] = r
    lineup()
    os.makedirs(bk.BUILD_DIR, exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(report.items())), f, ensure_ascii=False, indent=2)
    print(f"[cemetery] report {REPORT}")


main()
