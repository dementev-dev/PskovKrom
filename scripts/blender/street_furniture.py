"""street_furniture.py — малые формы вдоль прогулочных дорожек у Крома: фонари, скамейка, урна (M5, D-018).

    python scripts/bl_run.py scripts/blender/street_furniture.py              # все
    python scripts/bl_run.py scripts/blender/street_furniture.py -- Bench     # одна (имя без SM_Furn_)

Выгрузка — build/blender/SM_Furn_<Имя>.glb (в UE ставит scripts/furniture_krom.py по точкам
scripts/furniture_points.py), сведения — build/blender/furniture_report.json (высота, высота света, треугольники,
слоты), превью — media/renders/blender/furniture_<Имя>.png и furniture_lineup.png (все рядом с человеком 1,75 м).

Модели низкополигональные, размеры сняты с фото «на глаз» (гипотеза, точных чертежей нет):
  - LampColumn — фонарь-столбик набережных Псковы, Стрелки и Великой: тонкая металлическая труба ≈4,2 м, наверху
    матовый рассеиватель ≈0,5 м со скошенным торцом (фото refs/photos/commons/pskova_bank.jpg, S-42 env09, env10,
    env15). Скос смотрит вперёд (+u) — furniture_points разворачивает его к дорожке;
  - LampRetro — «ретро»-фонарь двора Крома и дороги к Великим воротам: тёмный столб с каннелированным низом,
    кронштейны, четырёхгранный фонарь с матовыми стёклами, шатрик с навершием, ≈3,85 м (build/persi/img4.jpg,
    refs/photos/commons/belfry_yard.jpg, S-34, S-25);
  - Bench — скамейка без спинки набережной Псковы: деревянное сиденье из четырёх досок на двух бетонных тумбах,
    2,0 × 0,45 м, сиденье на 0,45 м (фото env09; OSM backrest=no, material=wood, seats=4, S-41). Сидящий смотрит
    вперёд (+u);
  - Bin — бетонная урна-куб 0,45 × 0,45 × 0,65 м с тёмным проёмом сверху (env09: урны между скамейками).

Оси модели: u — вперёд (+X в UE, поворот yaw в точках), v — вправо (+Y в UE), z — от земли; низ тумб, столбов
и урн уходит на SINK м под землю, чтобы на уклоне и под будущими мешами дорожек (D-038) ничего не висело.
Материалы — слоты по ключам krom_plan.COLORS: tin (труба столбика: на фото то светлая, то графитовая — металл
с отражением неба), dark («ретро»-фонарь, кольцо под рассеивателем, проём урны), wood (сиденье — тёс, рисунок
досок), stone (бетон тумб и урн: шероховатый светло-серый рисунок ближе к бетону, чем крашеная roof). Слот glow —
матовый рассеиватель и стёкла; в UE ему свой материал M_KromLampGlow с яркостью по параметру (вечер, M6).
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402
import krom_plan  # noqa: E402
from bl_krom import M  # noqa: E402

SINK = 0.12              # м под землю у всего, что стоит на земле
GLOW_RGB = (0.85, 0.84, 0.80)  # матовое стекло днём (цвет превью; в UE — M_KromLampGlow)
REPORT = os.path.join(bk.BUILD_DIR, "furniture_report.json")


def ring(center, rx, ry, z, n=12, rot=0.0):
    """Эллипс в плане (полуоси rx по u, ry по v) на высоте z: n точек."""
    return [(center[0] + rx * math.cos(rot + 2 * math.pi * k / n), center[1] + ry * math.sin(rot + 2 * math.pi * k / n),
             z) for k in range(n)]


def star(center, r_out, r_in, z, n=8):
    """Каннелированное сечение: 2n точек, выступ r_out и желобок r_in по очереди."""
    return [(center[0] + (r_out if k % 2 == 0 else r_in) * math.cos(math.pi * k / n),
             center[1] + (r_out if k % 2 == 0 else r_in) * math.sin(math.pi * k / n), z) for k in range(2 * n)]


def beam(name, p0, p1, w, mat):
    """Брус квадратного сечения w между точками p0 и p1 (u, v, z) — кронштейны и рёбра фонаря."""
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
    faces = [[0, 1, 2, 3], [4, 5, 6, 7]] + [[i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i] for i in range(4)]
    return bk.mesh(name, verts, faces, mat)


# ---------- модели ----------

def lamp_column():
    """Фонарь-столбик: труба Ø ≈0,1 м до 3,62 м, рассеиватель-эллипс 0,13 × 0,15 м со скошенным торцом до 4,2 м."""
    c = (0.0, 0.0)
    z_head, z_top, slant = 3.62, 4.20, 0.14
    parts = [bk.lathe("foot", c, [(0.075, -SINK), (0.075, 0.03), (0.055, 0.06)], M["tin"], seg=12),
             bk.lathe("pole", c, [(0.052, 0.0), (0.045, z_head - 0.04)], M["tin"], seg=12),
             bk.lathe("collar", c, [(0.06, z_head - 0.06), (0.062, z_head + 0.01)], M["dark"], seg=12)]
    rx, ry = 0.065, 0.075
    bottom = ring(c, rx, ry, z_head)
    top = [(u, v, z_top - slant / 2 - slant / 2 * (u - c[0]) / rx)       # торец ниже спереди
           for u, v, _ in ring(c, rx, ry, z_top)]
    parts.append(bk.loft("head", [bottom, top], M["glow"]))
    return parts, {"height_m": z_top, "light_z_m": z_top - 0.25}


def lamp_retro():
    """«Ретро»-фонарь: каннелированный низ, тонкий ствол с кольцами, кронштейны, фонарь-усечённая пирамида, шатрик."""
    c = (0.0, 0.0)
    parts = [bk.lathe("plinth", c, [(0.15, -SINK), (0.15, 0.06), (0.12, 0.12), (0.11, 0.2)], M["dark"], seg=16,
                      smooth=False),
             bk.loft("flutes", [star(c, 0.095, 0.083, 0.2), star(c, 0.08, 0.07, 0.9)], M["dark"]),
             bk.lathe("collar1", c, [(0.105, 0.88), (0.105, 0.96), (0.07, 1.0)], M["dark"], seg=16, smooth=False),
             bk.lathe("shaft", c, [(0.05, 0.98), (0.042, 3.02)], M["dark"], seg=12),
             bk.lathe("ring", c, [(0.058, 2.28), (0.058, 2.34)], M["dark"], seg=12, smooth=False),
             bk.lathe("collar2", c, [(0.065, 3.0), (0.065, 3.1), (0.05, 3.14)], M["dark"], seg=12, smooth=False)]
    z0, z1 = 3.2, 3.6                      # стёкла от и до
    for k in range(4):                     # кронштейны к углам днища
        a = math.pi / 4 + k * math.pi / 2
        parts.append(beam("bracket", (0.03 * math.cos(a), 0.03 * math.sin(a), 3.02),
                          (0.17 * math.cos(a), 0.17 * math.sin(a), z0 - 0.02), 0.025, M["dark"]))
    parts.append(bk.box("floor", -0.15, 0.15, -0.15, 0.15, z0 - 0.04, z0, M["dark"]))
    lo, hi = 0.13, 0.17                    # полуширина фонаря внизу и вверху
    parts.append(bk.loft("glass", [[(su * lo, sv * lo, z0) for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))],
                                   [(su * hi, sv * hi, z1) for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]],
                         M["glow"]))
    for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):   # рёбра
        e0, e1 = lo + 0.005, hi + 0.005
        parts.append(beam("edge", (su * e0, sv * e0, z0), (su * e1, sv * e1, z1), 0.022, M["dark"]))
    parts.append(bk.box("rim", -0.2, 0.2, -0.2, 0.2, z1, z1 + 0.035, M["dark"]))
    corners = ((-1, -1), (1, -1), (1, 1), (-1, 1))
    parts.append(bk.loft("cap", [[(su * 0.2, sv * 0.2, z1 + 0.035) for su, sv in corners],
                                 [(su * 0.05, sv * 0.05, z1 + 0.16) for su, sv in corners]], M["dark"]))
    top = z1 + 0.16
    parts.append(bk.lathe("finial", c, [(0.0, top - 0.01), (0.035, top + 0.02), (0.03, top + 0.06), (0.012, top + 0.09),
                                        (0.0, top + 0.13)], M["dark"], seg=12))
    return parts, {"height_m": top + 0.13, "light_z_m": (z0 + z1) / 2}


def bench():
    """Скамейка без спинки: две бетонные тумбы 0,3 × 0,45 м заподлицо с торцами, сиденье — 4 доски по 2,0 м."""
    parts = []
    for v0 in (-1.0, 0.7):
        parts.append(bk.box("block", -0.225, 0.225, v0, v0 + 0.3, -SINK, 0.40, M["stone"]))
    w, gap, th = 0.1, 0.015, 0.045
    u = -(4 * w + 3 * gap) / 2
    for _ in range(4):
        parts.append(bk.box("board", u, u + w, -1.0, 1.0, 0.40, 0.40 + th, M["wood"]))
        u += w + gap
    return parts, {"height_m": 0.40 + th, "seat_z_m": 0.40 + th}


def bin_():
    """Урна-куб из бетона со скруглёнными (фаска) рёбрами и тёмным проёмом сверху."""
    c = (0.0, 0.0)
    h, ch = 0.225, 0.03

    def sq(half, z):   # квадрат со срезанными углами — 8 точек
        return [(c[0] + x, c[1] + y, z) for x, y in ((half, half - ch), (half - ch, half), (-half + ch, half),
                                                    (-half, half - ch), (-half, -half + ch), (-half + ch, -half),
                                                    (half - ch, -half), (half, -half + ch))]
    parts = [bk.loft("body", [sq(h, -SINK), sq(h, 0.62), sq(h - 0.02, 0.65)], M["stone"]),
             bk.box("mouth", -0.16, 0.16, -0.16, 0.16, 0.55, 0.652, M["dark"])]
    return parts, {"height_m": 0.65}


MODELS = {   # имя (SM_Furn_<имя>) → (построение, вид в points.json)
    "LampColumn": (lamp_column, "lamp_column"),
    "LampRetro": (lamp_retro, "lamp_retro"),
    "Bench": (bench, "bench"),
    "Bin": (bin_, "bin"),
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
    asset = f"SM_Furn_{name}"
    bk.reset_scene()
    bk.use_colors(krom_plan.COLORS)
    M["glow"] = bk.material("glow", GLOW_RGB)
    objs, info = fn()
    obj = bk.join(objs, asset)
    bk.box_uv(obj)
    me = obj.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    slots = [m.name for m in me.materials]
    print(f"[street_furniture] {asset}: {len(objs)} тел, {len(me.vertices)} вершин, {tris} треугольников, "
          f"слоты {slots}")
    bk.export_glb(obj, asset)
    preview_ground()
    human(0.0, -1.6 if kind == "bench" else -0.9)
    h = max(info["height_m"], 1.8)
    d = max(h, 2.8)                        # скамейка широкая, урна мала: камера не ближе
    bk.render_preview(f"furniture_{name}", eye=(1.6 * d, 1.2 * d, 0.6 * d), target=(0.0, 0.0, 0.45 * h),
                      size=(720, 900), lens=50)
    return {"asset": asset, "kind": kind, "tris": tris, "slots": slots, **{k: round(v, 3) for k, v in info.items()}}


def lineup():
    """Все модели в ряд с человеком — превью furniture_lineup.png (в выгрузку не идёт)."""
    bk.reset_scene()
    bk.use_colors(krom_plan.COLORS)
    M["glow"] = bk.material("glow", GLOW_RGB)
    preview_ground()
    for (name, (fn, _)), v in zip(MODELS.items(), (-2.6, -1.2, 0.9, 2.6)):
        objs, _ = fn()
        o = bk.join(objs, name)
        o.location.y = -v                 # v → Blender −y
    human(0.0, -0.1)
    bk.render_preview("furniture_lineup", eye=(11.0, 0.8, 2.4), target=(0.0, 0.0, 1.9), size=(1280, 720), lens=35)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    todo = [n for n in MODELS if not argv or n in argv]
    if not todo:
        raise SystemExit(f"[street_furniture] нет модели {argv}; есть: {list(MODELS)}")
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
    print(f"[street_furniture] report {REPORT}")


main()
