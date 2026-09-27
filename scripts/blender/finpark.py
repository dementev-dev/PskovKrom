"""finpark.py — Финский парк (парк Куопио) и плотина на Пскове у пешеходного моста: низкополигональные модели
(M5+, D-018).

    python scripts/bl_run.py scripts/blender/finpark.py              # все
    python scripts/bl_run.py scripts/blender/finpark.py -- Weir Lamp # выборочно (имя без SM_FinPark_)

Где что стоит и откуда размеры — scripts/finpark_plan.py (там же источники); ставит в UE scripts/finpark_krom.py.
Выгрузка — build/finpark/SM_FinPark_<Имя>.glb, сведения — build/finpark/finpark_report.json (высота, треугольники,
слоты, высота света), превью — build/finpark_refs/renders/finpark_<Имя>.png, finpark_lineup.png и виды плотины
finpark_weir_dam02.png / finpark_weir_dam01.png (как на фото dam02, dam01; вода — только в превью).

Модели:
  - Weir — плотина 1974 г. (S-75, S-79): прямой бетонный водослив по гребню OSM 66838593 (49,5 м) с плавным
    («оджи») низовым скатом, белая пелена перелива и полоса пены ниже; белые устои: южный — по контуру площадки
    «Шлюз» OSM 251885747 (8,9 × 13,8 м), северный — меньше (гип.); тёмные проёмы затворов в гранях к реке (dam01),
    маячок с колпаком на южном устое (dam02) и столбик на северном. Оси — finpark_plan.WeirFrame: u — вниз по
    течению, v — к северному концу, z — от уреза ниже плотины (урез Landscape). Перепад HEAD_M и высоты — гипотеза;
  - Stairs_<way> — лестницы у южного конца пешеходного моста по линиям OSM steps: ступени 0,15 м, площадки ровные,
    бортики, перила по краям и посередине (br04: марш к ул. Воровского); handrail=no — без перил. Оси мира
    (u — север, v — восток), начало — первый узел, z — от земли в нём; подъём — по heightmap (finpark_plan.STAIR_Z),
    в редакторе растягивается по трассе;
  - FlatBridge — прямой мостик 2015 г. через устье протоки (S-77: «не горбатым, а прямым»): настил из досок
    на устоях, металлические перила (материал и ширина — гипотеза);
  - HumpBridge — мостик «для влюблённых» (S-77): горбатый деревянный, решётка перил крестом (фото fpB05, fpB06);
  - Ship — «большой корабль» детской площадки (S-77): корпус, рубка, мачта с парусом, горка — гипотеза, фото нет;
  - Lamp — фонарь аллей парка (fpA01): тонкий чёрный столб ≈3,6 м, наверху стеклянный «тюльпан»; не похож ни на
    столбик набережной (SM_Furn_LampColumn), ни на «ретро» (SM_Furn_LampRetro).
Скамейки парка — те же, что у Крома (OSM backrest=no, material=wood): SM_Furn_Bench из street_furniture.py.

Материалы — слоты по ключам krom_plan.COLORS (wall — белёный бетон устоев и пелена, wood, dark, tin, roof, ruin —
колпак маячка: красного ключа нет, ruin ближе всех по тону); concrete и metal — бетон и крашеный металл мостов
(в UE — M_KromConcrete и M_KromRailing из bridge_krom.py), glow — стекло фонаря (в UE — MI_KromLampGlow из
furniture_krom.py). Текстур новых нет. Низ всего, что стоит на земле, уходит на SINK м в землю.
"""
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402
import finpark_plan as fp  # noqa: E402
import krom_plan  # noqa: E402
from bl_krom import M  # noqa: E402

bk.BUILD_DIR = os.path.join(bk.REPO, "build", "finpark")                    # свои выгрузки — не в build/blender
bk.PREVIEW_DIR = os.path.join(bk.REPO, "build", "finpark_refs", "renders")
REPORT = os.path.join(bk.BUILD_DIR, "finpark_report.json")
SINK = 0.12
EXTRA = {   # слоты вне krom_plan.COLORS — цвета только для превью (в UE — свои материалы, см. шапку)
    "concrete": (0.34, 0.33, 0.31),   # palette_krom.PALETTE["Concrete"]
    "metal": (0.20, 0.205, 0.21),     # PALETTE["Railing"]
    "glow": (0.85, 0.84, 0.80),
}


def colors():
    bk.use_colors(krom_plan.COLORS)
    for k, rgb in EXTRA.items():
        M[k] = bk.material(k, rgb)


# ---------- помощники ----------

def hexa(name, bottom, top, mat):
    """Шестигранник: 4 точки низа и 4 точки верха [(u, v, z)] в одном порядке обхода."""
    return bk.mesh(name, list(bottom) + list(top),
                   [[0, 1, 2, 3], [4, 5, 6, 7]] + [[i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i] for i in range(4)], mat)


def profile_along_v(name, prof, v0, v1, mat):
    """Профиль [(u, z)] (замкнутый многоугольник), вытянутый вдоль v от v0 до v1."""
    n = len(prof)
    verts = [(u, v0, z) for u, z in prof] + [(u, v1, z) for u, z in prof]
    faces = [list(range(n)), list(range(n, 2 * n))] + [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    return bk.mesh(name, verts, faces, mat)


def beam(name, p0, p1, w, mat, h=None):
    """Брус сечения w × h (h = w) между точками p0 и p1 (u, v, z) — перила, стойки, рёбра."""
    h = h or w
    d = [b - a for a, b in zip(p0, p1)]
    length = math.sqrt(sum(c * c for c in d))
    t = [c / length for c in d]
    up = (0.0, 0.0, 1.0) if abs(t[2]) < 0.9 else (1.0, 0.0, 0.0)
    a = [t[1] * up[2] - t[2] * up[1], t[2] * up[0] - t[0] * up[2], t[0] * up[1] - t[1] * up[0]]
    la = math.sqrt(sum(c * c for c in a))
    a = [c / la for c in a]
    b = [t[1] * a[2] - t[2] * a[1], t[2] * a[0] - t[0] * a[2], t[0] * a[1] - t[1] * a[0]]
    corners = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    verts = [tuple(p[i] + sa * a[i] + sb * b[i] for i in range(3)) for p in (p0, p1) for sa, sb in corners]
    faces = [[0, 1, 2, 3], [4, 5, 6, 7]] + [[i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i] for i in range(4)]
    return bk.mesh(name, verts, faces, mat)


def foam_patch(name, poly):
    """Пена: тонкая плита по многоугольнику [(u, v)] на FOAM_Z."""
    n = len(poly)
    return bk.mesh(name, [(u, v, fp.FOAM_Z) for u, v in poly] + [(u, v, fp.FOAM_Z - 0.12) for u, v in poly],
                   [list(range(n)), list(range(n, 2 * n))]
                   + [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)],
                   M["wall"])


def bl(u, v, z):
    """Точка осей модели (u, v, z) → Blender (u, −v, z): для камер превью."""
    return u, -v, z


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def railing(points, mat, h=1.0, post_step=1.6, mid=True, post_w=0.05, rail_w=0.05):
    """Перила по ломаной [(u, v, z)] (z — по настилу или носкам ступеней): стойки не реже post_step, поручень на h,
    средний брус на h/2."""
    parts = []
    for a, b in zip(points, points[1:]):
        seg = math.dist(a[:2], b[:2])
        n = max(1, math.ceil(seg / post_step))
        for k in range(n + 1):
            p = [a[i] + (b[i] - a[i]) * k / n for i in range(3)]
            parts.append(beam("post", (p[0], p[1], p[2] - 0.05), (p[0], p[1], p[2] + h), post_w, mat))
        parts.append(beam("rail", (a[0], a[1], a[2] + h), (b[0], b[1], b[2] + h), rail_w, mat))
        if mid:
            parts.append(beam("rail_mid", (a[0], a[1], a[2] + h / 2), (b[0], b[1], b[2] + h / 2), 0.03, mat))
    return parts


# ---------- модели ----------

def weir():
    """Плотина в осях finpark_plan.WeirFrame (z от уреза ниже плотины)."""
    f = fp.WeirFrame()
    half, crest, bot = f.half, fp.CREST_Z, fp.BODY_BOTTOM_Z
    blocks = fp.weir_blocks()
    parts = []
    # водослив: вертикальная верховая грань, скруглённый гребень, низовой скат по smoothstep до водобоя
    top = [(-1.0, crest - 0.25), (-0.85, crest - 0.08), (-0.6, crest), (-0.2, crest)]
    slope = [(-0.2 + 3.0 * k / 8, crest - (crest + 0.3) * smoothstep(k / 8)) for k in range(1, 9)]
    prof = [(-1.0, bot)] + top + slope + [(3.6, -0.35), (8.0, -0.35), (8.0, bot)]
    parts.append(profile_along_v("weir_body", prof, -half - 0.6, half + 0.6, M["concrete"]))
    # пелена перелива — белая вода по гребню и скату (чуть над бетоном)
    sheet = [(-0.55, crest + 0.03)] + [(u, z + 0.04) for u, z in [(-0.2, crest)] + slope] + [(3.3, -0.2)]
    lo = [(u, z - 0.06) for u, z in reversed(sheet)]
    parts.append(profile_along_v("weir_sheet", sheet + lo, -half, half, M["wall"]))
    # пена ниже водослива: сплошная полоса у подошвы с рваным краем и клочья дальше по течению (dam01, Esri)
    rnd = random.Random(1974)
    n = 24
    u_mid = (fp.FOAM_U[0] + fp.FOAM_U[1]) / 2
    near = [(fp.FOAM_U[0], -half + 2 * half * k / n) for k in range(n + 1)]
    far = [(u_mid + rnd.uniform(-1.2, 1.0), half - 2 * half * k / n) for k in range(n + 1)]
    parts.append(foam_patch("foam", near + far))
    for k in range(14):
        cu, cv = rnd.uniform(u_mid + 1.0, fp.FOAM_U[1] + 3.0), rnd.uniform(-half + 3, half - 3)
        ru, rv = rnd.uniform(0.4, 1.2), rnd.uniform(1.0, 3.5)
        parts.append(foam_patch("foam_bit", [(cu + ru * math.cos(a) * rnd.uniform(0.7, 1.1),
                                              cv + rv * math.sin(a) * rnd.uniform(0.7, 1.1))
                                             for a in (2 * math.pi * j / 7 for j in range(7))]))
    # устои: белый бетон, бетонный поясок поверху, тёмный проём затвора в грани к реке
    for key, z_top, light in (("south", fp.SOUTH_TOP_Z, fp.SOUTH_LIGHT), ("north", fp.NORTH_TOP_Z, fp.NORTH_LIGHT)):
        (u0, u1), (v0, v1) = blocks[key]
        parts.append(bk.box(f"{key}_block", u0, u1, v0, v1, bot, z_top - 0.15, M["wall"]))
        parts.append(bk.box(f"{key}_coping", u0 - 0.08, u1 + 0.08, v0 - 0.08, v1 + 0.08, z_top - 0.15, z_top,
                            M["concrete"]))
        face = v1 if key == "south" else v0              # грань к реке
        side = 1 if key == "south" else -1               # наружу от устоя — к реке
        g = fp.GATE
        parts.append(bk.box(f"{key}_gate", g["u"][0], g["u"][1], min(face, face + side * 0.03),
                            max(face, face + side * 0.03), g["z"][0], g["z"][1], M["dark"]))
        # маячок у верхнего (u0) угла грани к реке
        cu, cv = u0 + light["inset"], face - side * light["inset"]
        r, h, cap = light["r"], light["h"], light["cap"]
        parts.append(bk.lathe(f"{key}_light", (cu, cv), [(r + 0.08, z_top - 0.02), (r + 0.08, z_top + 0.12),
                                                        (r, z_top + 0.16), (r, z_top + h)], M["wall"], seg=16))
        parts.append(bk.lathe(f"{key}_lamp", (cu, cv), [(r * 0.8, z_top + h), (r * 0.8, z_top + h + 0.18)],
                              M["glow"], seg=16))
        parts.append(bk.lathe(f"{key}_cap", (cu, cv), [(r + 0.06, z_top + h + 0.18), (r * 0.85, z_top + h + cap * 0.55),
                                                      (r * 0.4, z_top + h + cap * 0.9), (0.0, z_top + h + cap)],
                              M["ruin"], seg=16))
    return parts, {"height_m": fp.SOUTH_TOP_Z + fp.SOUTH_LIGHT["h"] + fp.SOUTH_LIGHT["cap"], "crest_z_m": crest,
                   "crest_len_m": round(2 * half, 2), "head_m": fp.HEAD_M, "yaw_deg": round(f.yaw, 2)}


def stairs(way):
    """Лестница по линии OSM way: оси мира от первого узла (u — север, v — восток), z — от земли в нём."""
    spec, prof = fp.STAIRS[way], fp.stair_profile(way)
    x0, y0 = prof[0][0], prof[0][1]
    pts = [(x - x0, y - y0, z) for x, y, z in prof]
    w = spec["width"]
    zmin = min(p[2] for p in pts) - 0.7
    parts, rails = [], {-1: [], 0: [], 1: []}
    for (ua, va, za), (ub, vb, zb) in zip(pts, pts[1:]):
        seg = math.hypot(ub - ua, vb - va)
        tu, tv = (ub - ua) / seg, (vb - va) / seg
        nu, nv = -tv, tu                                  # вправо по ходу

        def at(s, off, z):
            return ua + tu * s + nu * off, va + tv * s + nv * off, z

        dz = zb - za
        if abs(dz) < 1e-3:   # площадка — плита с запасом на углы
            e = w / 2
            parts.append(hexa("landing", [at(-e, -w / 2, zmin), at(seg + e, -w / 2, zmin), at(seg + e, w / 2, zmin),
                                          at(-e, w / 2, zmin)],
                              [at(-e, -w / 2, za), at(seg + e, -w / 2, za), at(seg + e, w / 2, za), at(-e, w / 2, za)],
                              M["concrete"]))
        else:
            n = max(2, round(abs(dz) / fp.STEP_RISE_M))
            run = seg / n
            for i in range(n):
                zt = za + dz * (i + 1) / n
                s0, s1 = i * run, (i + 1) * run
                parts.append(hexa("step", [at(s0, -w / 2, zmin), at(s1, -w / 2, zmin), at(s1, w / 2, zmin),
                                           at(s0, w / 2, zmin)],
                                  [at(s0, -w / 2, zt), at(s1, -w / 2, zt), at(s1, w / 2, zt), at(s0, w / 2, zt)],
                                  M["concrete"]))
            for side in (-1, 1):   # бортики по линии носков + 0,15 м
                o0, o1 = side * (w / 2), side * (w / 2 + 0.2)
                zn0, zn1 = za + (dz / n if dz > 0 else 0.0) + 0.15, zb + (0.0 if dz > 0 else -dz / n) + 0.15
                parts.append(hexa("cheek", [at(0, o0, zmin), at(seg, o0, zmin), at(seg, o1, zmin), at(0, o1, zmin)],
                                  [at(0, o0, zn0), at(seg, o0, zn1), at(seg, o1, zn1), at(0, o1, zn0)],
                                  M["concrete"]))
        for side in (-1, 0, 1):
            off = side * (w / 2 + 0.1)
            rails[side] += [at(0, off, za + 0.15 * abs(side)), at(seg, off, zb + 0.15 * abs(side))]
    lines = {3: (-1, 0, 1), 2: (-1, 1)}.get(spec["rails"], ())
    for side in lines:
        pts_r = [p for k, p in enumerate(rails[side]) if k == 0 or p != rails[side][k - 1]]
        parts += railing(pts_r, M["metal"], h=0.95, mid=side != 0)
    return parts, {"height_m": max(p[2] for p in pts) + 1.1, "rise_m": pts[-1][2], "width_m": w,
                   "osm_way": way, "origin_xy": [x0, y0], "end_xy": [prof[-1][0], prof[-1][1]]}


def flat_bridge():
    """Прямой мостик: дощатый настил на двух балках и бетонных устоях, металлические перила (гип.)."""
    L, W = fp.FLAT_BRIDGE["length"], fp.FLAT_BRIDGE["width"]
    parts = [bk.box("deck", -L / 2, L / 2, -W / 2, W / 2, -0.12, 0.0, M["wood"])]
    for s in (-1, 1):
        parts.append(bk.box("stringer", -L / 2, L / 2, s * (W / 2 - 0.45) - 0.12, s * (W / 2 - 0.45) + 0.12,
                            -0.55, -0.12, M["metal"]))
        parts.append(bk.box("abutment", s * L / 2 - 0.7 if s > 0 else -L / 2, s * L / 2 if s > 0 else -L / 2 + 0.7,
                            -W / 2 - 0.1, W / 2 + 0.1, -1.8, -0.12, M["concrete"]))
        parts += railing([(-L / 2 + 0.1, s * (W / 2 - 0.05), 0.0), (L / 2 - 0.1, s * (W / 2 - 0.05), 0.0)],
                         M["metal"], h=1.1, post_step=1.5)
    return parts, {"height_m": 1.15, "deck_above_m": fp.DECK_ABOVE_M}


def hump_bridge():
    """Горбатый деревянный мостик: настил по параболе, балки, стойки, поручень и решётка крестом (fpB05, fpB06)."""
    L, W, R = fp.HUMP_BRIDGE["length"], fp.HUMP_BRIDGE["width"], fp.HUMP_BRIDGE["rise"]
    n = 12
    us = [-L / 2 + L * k / n for k in range(n + 1)]

    def z(u):
        return R * (1 - (2 * u / L) ** 2)

    parts = []
    for k in range(n):   # настил и балки — кусками между сечениями
        ua, ub = us[k], us[k + 1]
        parts.append(hexa("deck", [(ua, -W / 2, z(ua) - 0.1), (ub, -W / 2, z(ub) - 0.1), (ub, W / 2, z(ub) - 0.1),
                                   (ua, W / 2, z(ua) - 0.1)],
                          [(ua, -W / 2, z(ua)), (ub, -W / 2, z(ub)), (ub, W / 2, z(ub)), (ua, W / 2, z(ua))],
                          M["wood"]))
        for s in (-1, 1):
            v = s * (W / 2 - 0.1)
            parts.append(beam("stringer", (ua, v, z(ua) - 0.25), (ub, v, z(ub) - 0.25), 0.12, M["wood"], h=0.28))
    posts = [-L / 2 + 0.1 + (L - 0.2) * k / 6 for k in range(7)]
    for s in (-1, 1):
        v = s * (W / 2 + 0.03)
        h = 0.95
        for k, u in enumerate(posts):
            tall = 0.15 if k in (0, 6) else 0.0
            parts.append(beam("post", (u, v, z(u) - 0.3 - SINK * (k in (0, 6))), (u, v, z(u) + h + tall), 0.1,
                              M["wood"]))
        for ua, ub in zip(posts, posts[1:]):
            parts.append(beam("handrail", (ua, v, z(ua) + h), (ub, v, z(ub) + h), 0.08, M["wood"], h=0.06))
            parts.append(beam("lattice", (ua, v, z(ua) + 0.08), (ub, v, z(ub) + h - 0.08), 0.05, M["wood"]))
            parts.append(beam("lattice", (ua, v, z(ua) + h - 0.08), (ub, v, z(ub) + 0.08), 0.05, M["wood"]))
    return parts, {"height_m": R + 1.1, "deck_above_m": fp.HUMP_DECK_ABOVE_M}


def ship():
    """«Большой корабль» детской площадки — гипотеза: корпус-лофт, рубка на корме, мачта с реей и парусом, горка."""
    L, B = fp.SHIP["length"], fp.SHIP["beam"]

    def section(u, hb, deck, keel=0.0):
        return [(u, -hb, deck), (u, -hb * 0.92, keel + 0.45), (u, -hb * 0.45, keel), (u, hb * 0.45, keel),
                (u, hb * 0.92, keel + 0.45), (u, hb, deck)]

    rings = [section(-L / 2, B * 0.42, 1.6, 0.25), section(-L / 4, B / 2, 1.45), section(L / 8, B / 2, 1.45),
             section(L * 0.33, B * 0.36, 1.65, 0.1), section(L / 2, 0.06, 2.1, 0.9)]
    rings = [[(u, v, zz - SINK) for u, v, zz in r] for r in rings]
    parts = [bk.loft("hull", rings, M["wood"])]
    parts.append(bk.box("wale", -L / 2, L * 0.33, -B / 2 - 0.04, B / 2 + 0.04, 1.2, 1.35, M["dark"]))
    parts.append(bk.box("cabin", -L / 2 + 0.3, -L / 2 + 3.0, -1.25, 1.25, 1.3, 3.1, M["wood"]))
    parts.append(bk.box("cabin_roof", -L / 2 + 0.1, -L / 2 + 3.2, -1.45, 1.45, 3.1, 3.25, M["roof"]))
    for s in (-1, 1):   # фальшборт — перила по палубе от рубки к носу
        parts += railing([(-L / 2 + 3.1, s * (B / 2 - 0.15), 1.45 - SINK), (L * 0.3, s * (B * 0.34), 1.6 - SINK)],
                         M["wood"], h=0.8, post_step=1.2)
    mast_u = 0.4
    parts.append(bk.lathe("mast", (mast_u, 0.0), [(0.13, 1.3), (0.09, 7.2)], M["wood"], seg=10))
    parts.append(beam("yard", (mast_u + 0.15, -1.7, 6.0), (mast_u + 0.15, 1.7, 6.0), 0.08, M["wood"]))
    parts.append(bk.box("sail", mast_u + 0.2, mast_u + 0.26, -1.55, 1.55, 3.4, 5.9, M["wall"]))
    parts.append(bk.lathe("nest", (mast_u, 0.0), [(0.4, 6.25), (0.45, 6.6)], M["wood"], seg=10))
    # горка с правого борта: скат из нержавейки до земли
    parts.append(hexa("slide", [(-1.4, B / 2, 1.3), (-0.8, B / 2, 1.3), (-0.8, B / 2 + 3.2, -0.05),
                                (-1.4, B / 2 + 3.2, -0.05)],
                      [(-1.4, B / 2, 1.38), (-0.8, B / 2, 1.38), (-0.8, B / 2 + 3.2, 0.03), (-1.4, B / 2 + 3.2, 0.03)],
                      M["tin"]))
    return parts, {"height_m": 7.2, "hypothesis": True}


def lamp():
    """Фонарь аллей (fpA01): чёрный столб, наверху стеклянный «тюльпан» с тёмным ободом."""
    c = (0.0, 0.0)
    z_cup, z_top = 3.62, fp.LAMP_H_M
    parts = [bk.lathe("base", c, [(0.11, -SINK), (0.11, 0.25), (0.07, 0.32)], M["dark"], seg=12, smooth=False),
             bk.lathe("pole", c, [(0.055, 0.3), (0.042, z_cup - 0.08)], M["dark"], seg=12),
             bk.lathe("collar", c, [(0.065, z_cup - 0.1), (0.07, z_cup + 0.02), (0.05, z_cup + 0.05)], M["dark"],
                      seg=12),
             bk.lathe("cup", c, [(0.05, z_cup + 0.04), (0.11, z_cup + 0.14), (0.16, z_cup + 0.3), (0.19, z_top - 0.03)],
                      M["glow"], seg=16),
             bk.lathe("rim", c, [(0.2, z_top - 0.04), (0.2, z_top)], M["dark"], seg=16, smooth=False)]
    return parts, {"height_m": z_top, "light_z_m": z_cup + 0.2}


MODELS = {name: fn for name, fn in (("Weir", weir), ("FlatBridge", flat_bridge), ("HumpBridge", hump_bridge),
                                    ("Ship", ship), ("Lamp", lamp))}
MODELS.update({f"Stairs_{w}": (lambda w=w: stairs(w)) for w in fp.STAIRS})


def human(u, v, z=0.0):
    """Человек 1,75 м — только превью, для масштаба."""
    skin = bk.material("preview_person", (0.55, 0.35, 0.3))
    return [bk.lathe("person_body", (u, v),
                     [(0.0, z), (0.17, z + 0.02), (0.2, z + 0.9), (0.2, z + 1.45), (0.0, z + 1.5)],
                     skin, seg=12),
            bk.lathe("person_head", (u, v), [(0.0, z + 1.5), (0.1, z + 1.56), (0.1, z + 1.68), (0.0, z + 1.75)], skin,
                     seg=12)]


def ground(size=30.0, z=0.0, name="ground", rgb=(0.12, 0.16, 0.08)):
    g = bk.box(name, -size, size, -size, size, z - 0.3, z, bk.material(name, rgb))
    g.hide_select = True
    return g


def build(name):
    asset = f"SM_FinPark_{name}"
    bk.reset_scene()
    colors()
    objs, info = MODELS[name]()
    obj = bk.join(objs, asset)
    bk.box_uv(obj)
    me = obj.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    slots = [m.name for m in me.materials]
    print(f"[finpark] {asset}: {len(objs)} тел, {len(me.vertices)} вершин, {tris} треугольников, слоты {slots}")
    bk.export_glb(obj, asset)
    if name == "Weir":
        return {"asset": asset, "tris": tris, "slots": slots, **info}
    if name.startswith("Stairs"):
        pts = fp.stair_profile(info["osm_way"])
        x0, y0 = pts[0][0], pts[0][1]
        rel = [(x - x0, y - y0, z) for x, y, z in pts]
        du, dv = rel[-1][0], rel[-1][1]
        ground(size=max(abs(du), abs(dv)) + 12, z=min(0.0, info["rise_m"]))
        bank = bk.material("bank", (0.13, 0.17, 0.08))
        for (ua, va, za), (ub, vb, zb) in zip(rel, rel[1:]):   # откос вокруг лестницы — только превью
            seg = math.hypot(ub - ua, vb - va)
            tu, tv = (ub - ua) / seg, (vb - va) / seg
            e, h = info["width_m"] / 2 + 2.5, min(0.0, info["rise_m"]) - 0.3
            hexa("bank", [(ua - tv * e, va + tu * e, h), (ub - tv * e, vb + tu * e, h), (ub + tv * e, vb - tu * e, h),
                          (ua + tv * e, va - tu * e, h)],
                 [(ua - tv * e, va + tu * e, za - 0.05), (ub - tv * e, vb + tu * e, zb - 0.05),
                  (ub + tv * e, vb - tu * e, zb - 0.05), (ua + tv * e, va - tu * e, za - 0.05)], bank)
        (ua, va, za), (ub, vb, _) = rel[0], rel[1]
        seg = math.hypot(ub - ua, vb - va)
        tu, tv = (ub - ua) / seg, (vb - va) / seg
        human(tu * 2.0 - tv * 0.8, tv * 2.0 + tu * 0.8, za + 0.3)
        # вид снизу вдоль первого марша — как br04 (снято в 7 м до начала лестницы 67215712)
        bk.render_preview(f"finpark_{name}", eye=bl(-tu * 7.0, -tv * 7.0, za + 2.2),
                          target=bl(tu * 10.0, tv * 10.0, za + max(info["rise_m"], 0.0) * 0.6 + 0.8),
                          size=(700, 900), lens=24)
    else:
        ground()
        human(0.0, -(fp.SHIP["beam"] / 2 + 1.0) if name == "Ship" else -1.6)
        h = max(info["height_m"], 1.8)
        d = max(h, 4.0 if "Bridge" in name else 2.8)
        bk.render_preview(f"finpark_{name}", eye=(1.6 * d, 1.3 * d, 0.6 * d), target=(0.0, 0.0, 0.45 * h),
                          size=(900, 700), lens=45 if name != "Lamp" else 60)
    return {"asset": asset, "tris": tris, "slots": slots, **{k: (round(v, 3) if isinstance(v, float) else v)
                                                             for k, v in info.items()}}


def weir_views():
    """Плотина с водой (только превью): нижний бьеф на урезе, верхний — на HEAD_M выше (предложение P-1),
    виды как на фото dam02 (с северного устоя вдоль гребня) и dam01 (с пешеходного моста вверх по течению)."""
    for pool, tag in ((fp.HEAD_M, ""), (0.0, "_now")):
        bk.reset_scene()
        colors()
        objs, _ = weir()
        bk.join(objs, "Weir")
        water = bk.material("water", (0.05, 0.085, 0.09))
        down = bk.box("water_down", 0.0, 60.0, -60.0, 60.0, -0.5, 0.0, water)
        up = bk.box("water_up", -60.0, -0.95, -60.0, 60.0, -0.5, pool, water)
        bank = bk.material("bank", (0.13, 0.17, 0.08))
        blocks = fp.weir_blocks()
        (su0, su1), (sv0, sv1) = blocks["south"]
        (nu0, nu1), (nv0, nv1) = blocks["north"]
        bk.box("bank_south", -60, 60, -70, sv1 - 0.01, -0.5, fp.SOUTH_TOP_Z - 0.02, bank)
        bk.box("bank_north", -60, 60, nv1 - 0.3, 70, -0.5, fp.NORTH_TOP_Z - 0.02, bank)
        for o in (down, up):
            o.hide_select = True
        human(nu0 + 1.5, nv0 + 2.0, fp.NORTH_TOP_Z)
        human(su1 - 1.5, sv1 - 2.0, fp.SOUTH_TOP_Z)
        if tag == "":
            bk.render_preview("finpark_weir_dam02", eye=bl(-0.3, 24.2, 4.4), target=bl(2.2, -20.0, 0.6),
                              size=(1000, 667), lens=24)
        bk.render_preview(f"finpark_weir_dam01{tag}", eye=bl(27.0, 22.0, 6.5), target=bl(0.0, 6.0, 0.5),
                          size=(1000, 750), lens=16)


def lineup():
    """Мостики, корабль и фонарь рядом с человеком — finpark_lineup.png (в выгрузку не идёт)."""
    bk.reset_scene()
    colors()
    ground(40)
    for name, v in (("HumpBridge", -9.0), ("FlatBridge", -1.0), ("Lamp", 5.0), ("Ship", 12.0)):
        o = bk.join(MODELS[name]()[0], name)
        o.location.y = -v
    human(2.0, 5.8)
    bk.render_preview("finpark_lineup", eye=(30.0, 1.0, 8.0), target=(0.0, 1.0, 2.0), size=(1280, 640), lens=28)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    todo = [n for n in MODELS if not argv or n in argv]
    if not todo:
        raise SystemExit(f"[finpark] нет модели {argv}; есть: {list(MODELS)}")
    report = {}
    if os.path.exists(REPORT):
        with open(REPORT, encoding="utf-8") as fh:
            report = json.load(fh)
    for n in todo:
        r = build(n)
        report[r["asset"]] = r
    if "Weir" in todo:
        weir_views()
    if not argv:
        lineup()
    os.makedirs(bk.BUILD_DIR, exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as fh:
        json.dump(dict(sorted(report.items())), fh, ensure_ascii=False, indent=2)
    print(f"[finpark] report {REPORT}")


main()
