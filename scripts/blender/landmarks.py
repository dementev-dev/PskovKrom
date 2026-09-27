"""landmarks.py — памятные знаки у Крома: два креста, «Меч Довмонта», буквы «Россия начинается здесь»,
памятники Ленину и княгине Ольге, амфитеатр Детского парка (M5+, D-018).

    python scripts/bl_run.py scripts/blender/landmarks.py                 # все
    python scripts/bl_run.py scripts/blender/landmarks.py -- OlgaCross    # один (имя без SM_Mark_)

Где стоят и куда смотрят — scripts/landmarks_plan.py (там же источники и что гипотеза). Выгрузка —
build/blender/SM_Mark_<Имя>.glb (в UE ставит scripts/landmarks_krom.py), сведения — build/blender/landmarks_report.json
(треугольники, высота, слоты), превью — media/renders/blender/landmark_<Имя>_<вид>.png (с человеком 1,75 м).

Модели низкополигональные, размеры сняты с фото «на глаз» (гипотеза ±20 %):
  - BlagCross — гранитный крест на валуне в Кроме: стойка 0,36 × 0,36, крест 2,8 м над валуном, перекладина 2,0 м,
    верхняя 1,0 м, косая нижняя (поднятый конец — справа от зрителя, к северо-западу), валун ≈3,4 × 1,9 × 1,7 м,
    кольцо булыжника, бронзовая доска (фото S-86);
  - OlgaCross — Ольгин крест на Завеличье: контур креста 2,1 × 1,4 м из стальной полосы 70 мм, нижняя перекладина
    уступами, на конусе из бута ⌀1,4 × 1,15 м с доской (фото S-87);
  - DovmontSword — «Щит и меч» на Персях: консоль под верхом стены, коромысло на цепях, прапор 3,1 × 5,5 м,
    колокольцы, меч ≈7,7 м перед прапором, шесть круглых пластин (фото S-34 img4, S-42 env18, S-88). Ноль высот —
    верх лица стены, всё висит ниже (z < 0), u = 0 — внешняя грань стены;
  - RussiaLetters — 21 буква высотой 4,6 м, надпись 48 м (фото S-89), шрифт Arial Narrow Bold, сжатый по длине;
    сзади подкосы. Надпись идёт по −v: зритель смотрит на лицо (+u), его правая рука — −v.
  - Lenin — памятник на площади Ленина (1960): бронзовая фигура 4 м (кадастр 1997 г., S-135), постамент
    1,85 × 2,8 м с уступом сзади и надписью «ЛЕНИН 1870–1924», площадка с 6 ступенями, блок с серпом и молотом
    (фото S-135; ноль высот — земля у нижней ступени, тело площадки уходит под землю на 0,6 м).
  - Olga — памятник княгине Ольге на Октябрьской площади (2003, В. М. Клыков): постамент белого камня 4,2 м и фигура
    4,2 м (S-153 ✔), двенадцать святых на нижнем барабане, опорная плита, круглая площадка r 5,5 на 0,6 м с лестницей
    по дуге (фото S-154, аэрофото S-155; ноль высот — земля у нижней ступени).
  - Amphitheatre — летний амфитеатр Детского парка: 8 рядов двумя блоками по дугам r 15,3…27,4 (скамейки OSM),
    террасы +0,3 м на ряд (гип.), проходы полуступенями, мощёная площадка перед рядами (relation 3107113); ноль высот —
    земля на площадке в 8 м от центра дуг.

Оси модели — как у героев (bl_krom): u — «лицо» знака, v — вправо от u, z — вверх; всё, что стоит на земле, уходит
на SINK под землю. Материалы — слоты по ключам krom_plan.COLORS, новых нет: wall (белое: гранит креста, буквы),
ruin (валун), stone (бут, булыжник), bronze (доска, коромысло, консоль, колокольцы), copper (прапор и пластины
с патиной), tin (клинок, доска Ольгина креста), dark (сталь креста, рукоять, цепи, подкосы).
"""
import json
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402
import krom_plan  # noqa: E402
from bl_krom import M  # noqa: E402

SINK = 0.15
REPORT = os.path.join(bk.BUILD_DIR, "landmarks_report.json")
FONTS = ("C:/Windows/Fonts/ARIALNB.TTF", "C:/Windows/Fonts/DejaVuSansCondensed-Bold.ttf")  # нет — встроенный


# ---------- помощники ----------

def noise(i, k):
    """Детерминированный шум −1…1 (валуны и бут одинаковы от запуска к запуску)."""
    return ((math.sin(i * 12.9898 + k * 78.233) * 43758.5453) % 1.0) * 2.0 - 1.0


def rock(name, rings, mat, seg=14, amp=0.08, seed=0):
    """Неровное тело по кольцам (z, ru, rv) снизу вверх: эллипсы с шумом по радиусу; торцы закрыты."""
    out = []
    for j, (z, ru, rv) in enumerate(rings):
        ring = []
        for k in range(seg):
            a = 2 * math.pi * k / seg
            f = 1.0 + amp * noise(seed + j, k)
            dz = 0.0 if j in (0, len(rings) - 1) else amp * 0.5 * noise(seed + 7 * j, k + 3)
            ring.append((ru * f * math.cos(a), rv * f * math.sin(a), z + dz))
        out.append(ring)
    return bk.loft(name, out, mat)


def beam(name, p0, p1, w, mat):
    """Брус квадратного сечения w между точками p0 и p1 (u, v, z)."""
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


def slab_uz(name, u0, poly, d0, d1, mat):
    """Плоская фигура [(v, z)] в плоскости u = u0, толщиной от u0 + d0 до u0 + d1 (лицом к +u)."""
    return bk.extrude(name, bk.Frame((u0, 0.0), (0.0, 1.0), (1.0, 0.0)), poly, d0, d1, mat)


def disc(name, u0, v, z, r, thick, mat, n=16):
    return slab_uz(name, u0, [(v + r * math.cos(2 * math.pi * k / n), z + r * math.sin(2 * math.pi * k / n))
                              for k in range(n)], 0.0, thick, mat)


def tilted_plate(name, bottom, top, w, thick, mat):
    """Доска на наклонном камне: низ и верх — (u, z) середины лицевой стороны, ширина w по v."""
    (ub, zb), (ut, zt) = bottom, top
    L = math.hypot(ut - ub, zt - zb)
    n = ((zt - zb) / L, -(ut - ub) / L)          # нормаль в плоскости (u, z), наружу (+u)
    verts = []
    for du, dz in ((0.0, 0.0), (-n[0] * thick, -n[1] * thick)):
        verts += [(ub + du, -w / 2, zb + dz), (ub + du, w / 2, zb + dz), (ut + du, w / 2, zt + dz), (ut + du, -w / 2, zt + dz)]
    faces = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return bk.mesh(name, verts, faces, mat)


def slanted_bar(name, vc, zc, length, height, depth, angle, mat):
    """Косая перекладина в плоскости (v, z), наклон angle, °: поднятый конец — на −v, то есть справа от зрителя,
    который смотрит на лицо знака (стоит на +u)."""
    e = (math.cos(math.radians(angle)), -math.sin(math.radians(angle)))   # к +v — вниз
    n = (math.sin(math.radians(angle)), math.cos(math.radians(angle)))
    quad = [(vc + s * length / 2 * e[0] + t * height / 2 * n[0], zc + s * length / 2 * e[1] + t * height / 2 * n[1])
            for s, t in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    return slab_uz(name, -depth / 2, quad, 0.0, depth, mat)


# ---------- модели ----------

def blag_cross():
    """Гранитный восьмиконечный крест на валуне (Кром): доска на валуне и лицо креста — к +u."""
    boulder = [(-SINK, 1.0, 1.85), (0.5, 0.95, 1.75), (1.1, 0.75, 1.3), (1.5, 0.5, 0.8), (1.72, 0.3, 0.45)]
    parts = [rock("boulder", boulder, M["ruin"], seg=16, amp=0.07, seed=3)]
    for k in range(28):                                          # кольцо булыжника у подошвы валуна
        a = 2 * math.pi * (k + 0.3 * noise(k, 1)) / 28
        r = 0.17 + 0.05 * noise(k, 2)
        c = (1.18 * math.cos(a), 2.02 * math.sin(a))
        parts.append(bk.lathe("cobble", c, [(0.0, -0.12), (r, -0.05), (r * 0.85, 0.1), (0.0, 0.17 + 0.04 * noise(k, 5))],
                              M["stone"], seg=6, smooth=False))
    z0, w = 1.6, 0.36                                            # низ стойки — в валуне на 0,12
    h = w / 2
    parts += [bk.box("shaft", -h, h, -h, h, z0, z0 + 2.8, M["wall"]),
              bk.box("bar", -h, h, -1.0, 1.0, z0 + 1.5, z0 + 1.9, M["wall"]),
              bk.box("top_bar", -h, h, -0.49, 0.49, z0 + 2.1, z0 + 2.48, M["wall"]),
              slanted_bar("foot_bar", 0.0, z0 + 0.45, 0.75, 0.3, w, 20.0, M["wall"])]
    parts.append(tilted_plate("plaque", (1.05, 0.55), (0.86, 1.2), 0.62, 0.04, M["bronze"]))
    return parts, {"height_m": z0 + 2.8}


OLGA_OUTLINE = [(-0.12, 0.0), (-0.12, 0.72), (-0.24, 0.72), (-0.24, 0.96), (-0.15, 0.96), (-0.15, 1.26), (-0.70, 1.26),
                (-0.70, 1.56), (-0.15, 1.56), (-0.15, 1.66), (-0.29, 1.66), (-0.29, 1.98), (-0.15, 1.98), (-0.15, 2.10),
                (0.15, 2.10), (0.15, 1.98), (0.29, 1.98), (0.29, 1.66), (0.15, 1.66), (0.15, 1.56), (0.70, 1.56),
                (0.70, 1.26), (0.15, 1.26), (0.15, 0.62), (0.27, 0.62), (0.27, 0.36), (0.12, 0.36), (0.12, 0.0)]
# (s, z): s — вправо от зрителя (s = −v); уступ нижней перекладины слева выше (0,72–0,96), справа ниже (0,36–0,62)


def olga_cross():
    """Контур восьмиконечного креста из стальной полосы на конусе из бута; доска на конусе — к +u."""
    cairn = [(-SINK, 0.72, 0.72), (0.3, 0.68, 0.68), (0.75, 0.5, 0.5), (1.15, 0.33, 0.33)]
    parts = [rock("cairn", cairn, M["stone"], seg=12, amp=0.06, seed=11)]
    z0, sw, d = 1.0, 0.07, 0.03                                  # ноги креста — в конусе на 0,15
    for (s0, za), (s1, zb) in zip(OLGA_OUTLINE, OLGA_OUTLINE[1:]):
        v0, v1 = sorted((-s0, -s1))
        parts.append(bk.box("strip", -d / 2, d / 2, v0 - sw / 2, v1 + sw / 2, z0 + min(za, zb) - sw / 2,
                            z0 + max(za, zb) + sw / 2, M["dark"]))
    parts.append(tilted_plate("plaque", (0.64, 0.45), (0.55, 0.82), 0.28, 0.03, M["tin"]))
    return parts, {"height_m": z0 + 2.10 + sw / 2}


def dovmont_sword():
    """«Щит и меч» на лице Персей: u = 0 — грань стены, z = 0 — её верх (под кровлей), всё висит ниже."""
    B, D, C = "bronze", "dark", "copper"
    parts = [bk.box("beam", -0.4, 1.9, -0.13, 0.13, -1.85, -1.55, M[B]),              # консоль
             beam("strut", (0.0, 0.0, -3.0), (1.2, 0.0, -1.8), 0.1, M[B])]
    # меч перед прапором: навершие, рукоять, перекрестье, клинок
    us = 1.6
    parts += [beam("hook", (1.75, 0.0, -1.85), (us, 0.0, -2.12), 0.05, M[D]),
              bk.lathe("pommel", (us, 0.0), [(0.0, -2.38), (0.13, -2.3), (0.13, -2.18), (0.0, -2.1)], M[B], seg=10),
              bk.box("grip", us - 0.045, us + 0.045, -0.055, 0.055, -2.95, -2.36, M[D]),
              bk.box("guard", us - 0.06, us + 0.06, -0.55, 0.55, -3.1, -2.95, M["tin"]),
              slab_uz("blade", us, [(-0.14, -3.1), (0.14, -3.1), (0.12, -9.6), (0.0, -10.4), (-0.12, -9.6)],
                      -0.02, 0.02, M["tin"])]
    # коромысло с загнутыми концами на двух цепях от конца консоли
    ub = 0.55
    yoke = [(-1.5, -4.22), (-1.62, -4.35), (-1.55, -4.55), (-1.2, -4.72), (-0.6, -4.82), (0.0, -4.85), (0.6, -4.82),
            (1.2, -4.72), (1.55, -4.55), (1.62, -4.35), (1.5, -4.22)]
    parts += [beam("yoke", (ub, v0, z0), (ub, v1, z1), 0.09, M[B]) for (v0, z0), (v1, z1) in zip(yoke, yoke[1:])]
    parts += [beam("chain", (1.8, 0.0, -1.85), (ub, sv * 1.58, -4.4), 0.035, M[D]) for sv in (-1, 1)]
    parts += [beam("hanger", (ub, sv * 1.45, -4.62), (ub, sv * 1.45, -6.12), 0.03, M[D]) for sv in (-1, 1)]
    # прапор: лист с рамкой и полем (барс и план — не рельефом, а цветом материала в M4)
    top, bot, hw = -6.1, -11.6, 1.55
    parts += [bk.box("banner", 0.5, 0.56, -hw, hw, bot, top, M[C]),
              bk.box("field", 0.56, 0.58, -hw + 0.3, hw - 0.3, bot + 0.6, top - 0.6, M[C])]
    for v0, v1, z0, z1 in ((-hw, hw, top - 0.1, top), (-hw, hw, bot, bot + 0.1), (-hw, -hw + 0.1, bot, top),
                           (hw - 0.1, hw, bot, top)):
        parts.append(bk.box("frame", 0.56, 0.6, v0, v1, z0, z1, M[C]))
    # колокольцы на планке перед верхом прапора
    parts += [bk.box("bell_rail", 0.66, 0.74, -1.35, 1.35, -6.24, -6.18, M[B])]
    parts += [bk.box("bell_arm", 0.56, 0.74, sv * 1.3 - 0.03, sv * 1.3 + 0.03, -6.24, -6.18, M[B]) for sv in (-1, 1)]
    for k in range(7):
        v = -1.2 + 0.4 * k
        parts.append(bk.lathe("bell", (0.7, v), [(0.0, -6.2), (0.05, -6.26), (0.08, -6.36), (0.1, -6.5),
                                                  (0.13, -6.56), (0.0, -6.56)], M[B], seg=8))
    # пластины с гербами городов: три сверху, две по бокам и большая внизу
    plates = [(-1.0, -12.25, 0.4), (0.0, -12.25, 0.4), (1.0, -12.25, 0.4), (-0.85, -13.3, 0.4), (0.85, -13.3, 0.4),
              (0.0, -13.45, 0.55)]
    for v, z, r in plates:
        parts.append(disc("plate", 0.5, v, z, r, 0.05, M[C]))
        z_up = bot if z > -12.9 else -12.25 - 0.4
        parts.append(beam("plate_chain", (0.53, v, z_up), (0.53, v, z + r), 0.025, M[D]))
    return parts, {"height_m": 14.05, "z_min_m": -14.0, "z_max_m": -1.55}


LETTERS_TEXT = "РОССИЯ НАЧИНАЕТСЯ ЗДЕСЬ"
LETTER_H, TEXT_L, LETTER_D = 4.6, 48.0, 0.18


def text_mesh(body, fonts=FONTS):
    """Текст шрифтом из fonts → (вершины (x, y, z) в осях текста, грани). x — вдоль строки, y — вверх,
    z — толщина ±0,5."""
    cu = bpy.data.curves.new("txt", type="FONT")
    cu.body = body
    font = next((f for f in fonts if os.path.exists(f)), None)
    if font:
        cu.font = bpy.data.fonts.load(font)
    cu.size, cu.extrude, cu.resolution_u, cu.fill_mode = 1.0, 0.5, 3, "BOTH"
    ob = bpy.data.objects.new("txt", cu)
    bpy.context.scene.collection.objects.link(ob)
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    verts, faces = [tuple(v.co) for v in me.vertices], [list(p.vertices) for p in me.polygons]
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    return verts, faces, font


def russia_letters():
    """Надпись вдоль −v, лицо букв — к +u (к реке), низ — на SINK под землёй; сзади подкосы и порог."""
    cap = text_mesh("Н")[0]
    cap_h = max(v[1] for v in cap) - min(v[1] for v in cap)
    verts, faces, font = text_mesh(LETTERS_TEXT)
    x0, x1 = min(v[0] for v in verts), max(v[0] for v in verts)
    sx, sz, su = TEXT_L / (x1 - x0), LETTER_H / cap_h, LETTER_D
    xm = (x0 + x1) / 2
    # строка по −v: слева направо для зрителя с +u. Ножки «Д» ниже строки на фото не видны (все буквы стоят на одной
    # линии) — ужаты до 15 % и уходят в землю вместе с SINK
    mv = [(z * su, -(x - xm) * sx, y * sz * (0.15 if y < 0 else 1.0)) for x, y, z in verts]
    parts = [bk.mesh("letters", mv, faces, M["wall"])]
    parts.append(bk.box("sill", -0.12, 0.12, -TEXT_L / 2 - 0.2, TEXT_L / 2 + 0.2, -SINK, 0.03, M["dark"]))
    n = int(TEXT_L / 2.1)
    for k in range(n + 1):
        v = -TEXT_L / 2 + TEXT_L * k / n
        parts.append(beam("brace", (-LETTER_D / 2, v, 0.72 * LETTER_H), (-1.9, v, -SINK), 0.07, M["dark"]))
    return parts, {"height_m": LETTER_H, "length_m": TEXT_L, "font": font or "встроенный Blender",
                   "text_scale_x_of_font": round(sx / sz, 3)}


# ---------- памятник Ленину на площади Ленина ----------
# Оси: u — лицо памятника (на запад, к площади), v — вправо от него (на север), z — от земли у нижней ступени лестницы
# (landmarks_plan: ground_at); u = v = 0 — ось постамента. Размеры — гипотеза по фото (landmarks_plan), кроме высоты
# скульптуры 4 м (кадастр 1997 г., S-135).
LENIN_H = 4.0                                   # высота скульптуры
LENIN_STEPS = (6, 0.135, 0.35)                  # ступеней, подступёнок, проступь (фото l01, l09: 6 ступеней ≈0,8 м)
LENIN_PODIUM = (-5.0, 5.5, 5.0)                 # верх площадки: задняя и передняя кромки по u, полуширина по v
LENIN_BURY = 0.6                                # тело площадки под землёй: земля к задней кромке выше на ≈0,5 м
LENIN_PED = dict(w=1.85, deep=2.8, course=0.82, courses=5, deep_courses=4, slab=0.3, slab_out=0.2, plinth=0.12)
SERIF = ("C:/Windows/Fonts/timesbd.ttf", "C:/Windows/Fonts/DejaVuSerif-Bold.ttf") + FONTS


def ring3(c, t, r, n, ref=(0.0, 0.0, 1.0)):
    """Кольцо радиуса r (число или (ra, rb)) вокруг точки c, перпендикулярное направлению t (u, v, z)."""
    if abs(sum(a * b for a, b in zip(t, ref))) > 0.9:
        ref = (1.0, 0.0, 0.0)
    a = [t[1] * ref[2] - t[2] * ref[1], t[2] * ref[0] - t[0] * ref[2], t[0] * ref[1] - t[1] * ref[0]]
    la = math.sqrt(sum(x * x for x in a))
    a = [x / la for x in a]
    b = [t[1] * a[2] - t[2] * a[1], t[2] * a[0] - t[0] * a[2], t[0] * a[1] - t[1] * a[0]]
    ra, rb = r if isinstance(r, tuple) else (r, r)
    return [tuple(c[i] + ra * math.cos(2 * math.pi * k / n) * a[i] + rb * math.sin(2 * math.pi * k / n) * b[i]
                  for i in range(3)) for k in range(n)]


def tube(name, pts, radii, mat, n=10, ref=(1.0, 0.0, 0.0)):
    """Трубка переменного радиуса по точкам (u, v, z): кольца поперёк оси, торцы закрыты (руки, ноги, шея)."""
    rings = []
    for i, p in enumerate(pts):
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, len(pts) - 1)]
        d = [y - x for x, y in zip(a, b)]
        ld = math.sqrt(sum(x * x for x in d))
        rings.append(ring3(p, [x / ld for x in d], radii[i], n, ref))
    return bk.loft(name, rings, mat, smooth=True)


def ellipse(cu, cv, z, ru, rv, n=16):
    return [(cu + ru * math.cos(2 * math.pi * k / n), cv + rv * math.sin(2 * math.pi * k / n), z) for k in range(n)]


def lenin_figure(z0):
    """Фигура в рост, 4 м: костюм, распахнутый пиджак, голова непокрыта; правая рука согнута — кисть в кармане брюк,
    локоть в сторону; в опущенной левой — свёрнутая газета (кадастр 1997 г.; фото l01, l19). Лицом к +u. Размеры —
    человек 1,75 м × 4 / 1,75; z0 — верх бронзовой плиты."""
    s = LENIN_H / 1.75
    B = M["bronze"]

    def P(u, v, z):
        return (u * s, v * s, z0 + z * s)

    parts = []
    # ноги в брюках: правая (v > 0) чуть вперёд, носки врозь; ботинки
    for sv, du in ((1, 0.05), (-1, -0.03)):
        pts = [P(du, sv * 0.125, 0.07), P(du * 0.8, sv * 0.12, 0.3), P(du * 0.5, sv * 0.115, 0.5),
               P(du * 0.2, sv * 0.105, 0.72), P(0.0, sv * 0.095, 0.86)]
        parts.append(tube("leg", pts, [0.075 * s, 0.078 * s, 0.082 * s, 0.095 * s, 0.105 * s], B, n=12, ref=(1, 0, 0)))
        parts.append(bk.loft("shoe", [ellipse(du * s + 0.05 * s, sv * 0.13 * s, z0, 0.14 * s, 0.05 * s, 12),
                                      ellipse(du * s + 0.05 * s, sv * 0.13 * s, z0 + 0.07 * s, 0.13 * s, 0.045 * s, 12),
                                      ellipse(du * s + 0.01 * s, sv * 0.125 * s, z0 + 0.1 * s, 0.06 * s, 0.045 * s,
                                              12)], B, smooth=True))
    # корпус в пиджаке: от полы до плеч (эллипсы: полуоси вперёд-назад и вбок)
    torso = [(0.72, -0.01, 0.17, 0.245), (0.8, -0.005, 0.16, 0.23), (0.95, 0.0, 0.145, 0.21),
             (1.05, 0.0, 0.14, 0.2), (1.18, 0.005, 0.15, 0.215), (1.30, 0.0, 0.15, 0.225), (1.40, -0.01, 0.135, 0.235),
             (1.45, -0.015, 0.09, 0.17), (1.47, -0.015, 0.05, 0.08)]
    parts.append(bk.loft("torso", [ellipse(cu * s, 0.0, z0 + z * s, ru * s, rv * s, 18) for z, cu, ru, rv in torso],
                         B, smooth=True))
    # полы распахнутого пиджака — отвернуты от пуговиц (фото l19)
    for sv in (1, -1):
        parts.append(tube("flap", [P(0.12, sv * 0.07, 1.2), P(0.155, sv * 0.1, 0.98), P(0.16, sv * 0.13, 0.8)],
                          [(0.06 * s, 0.012 * s)] * 3, B, n=8, ref=(1, 0, 0)))
    # шея и голова (лысина, бородка клинышком)
    parts.append(tube("neck", [P(-0.01, 0.0, 1.44), P(0.0, 0.0, 1.55)], [0.055 * s, 0.05 * s], B, n=10))
    head = [(0.0, 1.53), (0.075, 1.55), (0.1, 1.6), (0.105, 1.65), (0.1, 1.7), (0.075, 1.735), (0.0, 1.75)]
    parts.append(bk.lathe("head", (0.0, 0.0), [(r * s, z0 + z * s) for r, z in head], B, seg=14))
    parts.append(tube("beard", [P(0.06, 0.0, 1.575), P(0.09, 0.0, 1.535)], [0.035 * s, 0.012 * s], B, n=8))
    # правая рука: плечо — локоть в сторону и чуть назад — кисть в кармане брюк
    parts.append(tube("arm_r", [P(-0.01, 0.21, 1.41), P(-0.05, 0.33, 1.26), P(-0.07, 0.39, 1.13), P(-0.01, 0.3, 1.0),
                                P(0.04, 0.2, 0.9)], [0.058 * s, 0.056 * s, 0.05 * s, 0.047 * s, 0.042 * s], B, n=10))
    # левая рука опущена, кисть вперёд, в ней свёрнутая газета
    parts.append(tube("arm_l", [P(-0.01, -0.2, 1.41), P(0.0, -0.235, 1.25), P(0.02, -0.25, 1.12), P(0.06, -0.24, 0.98),
                                P(0.09, -0.23, 0.88)], [0.058 * s, 0.055 * s, 0.05 * s, 0.045 * s, 0.042 * s], B, n=10))
    parts.append(bk.lathe("hand_l", (0.1 * s, -0.23 * s), [(0.0, z0 + 0.82 * s), (0.04 * s, z0 + 0.845 * s),
                                                          (0.04 * s, z0 + 0.885 * s), (0.0, z0 + 0.9 * s)], B, seg=8))
    parts.append(tube("newspaper", [P(0.16, -0.23, 0.9), P(0.07, -0.23, 0.72)], [0.028 * s, 0.028 * s], B, n=8))
    return parts


def text_block(body, cap_h, u0, vc, zc, relief, mat, fonts=SERIF, width=None):
    """Надпись на плоскости u = u0 лицом к +u, читается по −v (слева направо для зрителя на +u): высота прописной
    cap_h, центр (vc, zc); width — ужать / растянуть по длине (иначе пропорции шрифта)."""
    cap = text_mesh("Н", fonts)[0]
    k = cap_h / (max(v[1] for v in cap) - min(v[1] for v in cap))
    verts, faces, _ = text_mesh(body, fonts)
    x0, x1 = min(v[0] for v in verts), max(v[0] for v in verts)
    y0 = min(v[1] for v in cap)
    kx = width / (x1 - x0) if width else k
    xm = (x0 + x1) / 2
    mv = [(u0 + (z + 0.5) * relief, vc - (x - xm) * kx, zc - cap_h / 2 + (y - y0) * k) for x, y, z in verts]
    return bk.mesh(body, mv, faces, mat)


def hammer_sickle(u0, vc, zc, size, relief, mat):
    """Серп и молот рельефом на плоскости u = u0 (лицом к +u); size — поперечник, центр (vc, zc). Для зрителя на +u:
    молот рукоятью вниз-влево, серп — дугой справа (фото l01, l09)."""
    h = size / 2
    f = bk.Frame((u0, vc), (0.0, -1.0), (1.0, 0.0))           # s — вправо для зрителя (−v), d — к зрителю (+u)
    parts = []
    # рукоять молота: из левого нижнего угла к центру; боёк — поперёк рукояти
    a, b = (-0.75 * h, -0.8 * h), (0.25 * h, 0.35 * h)
    L = math.dist(a, b)
    t = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    n = (-t[1], t[0])

    def quad(c, half_t, half_n):
        """Прямоугольник (s, z) с центром c, полуразмерами вдоль рукояти и поперёк неё."""
        return [(c[0] + st * half_t * t[0] + sn * half_n * n[0], zc + c[1] + st * half_t * t[1] + sn * half_n * n[1])
                for st, sn in ((-1, 1), (1, 1), (1, -1), (-1, -1))]

    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    parts.append(bk.extrude("hammer", f, quad(mid, L / 2, 0.06 * size), 0.0, relief, mat))
    hw, hl = 0.13 * size, 0.42 * size
    head = (b[0] + t[0] * hw * 0.5, b[1] + t[1] * hw * 0.5)
    parts.append(bk.extrude("hammer_head", f, quad(head, hw / 2, hl / 2), 0.0, relief, mat))
    # серп: дуга от ручки внизу справа вверх и влево; ручка — короткий брусок
    outer, inner = [], []
    for k in range(13):
        ang = math.radians(-60 + 250 * k / 12)
        r_o, r_i = 0.62 * h, 0.62 * h - 0.09 * size * (1 - k / 14)
        outer.append((0.05 * h + r_o * math.cos(ang), zc + 0.05 * h + r_o * math.sin(ang)))
        inner.append((0.05 * h + r_i * math.cos(ang), zc + 0.05 * h + r_i * math.sin(ang)))
    parts.append(bk.extrude("sickle", f, outer + inner[::-1], 0.0, relief, mat))
    st = (0.05 * h + 0.62 * h * math.cos(math.radians(-60)), 0.05 * h + 0.62 * h * math.sin(math.radians(-60)))
    parts.append(bk.extrude("sickle_grip", f, [(st[0] - 0.05 * size, zc + st[1]), (st[0] + 0.03 * size, zc + st[1]),
                                               (st[0] + 0.12 * size, zc + st[1] - 0.2 * size),
                                               (st[0] + 0.04 * size, zc + st[1] - 0.2 * size)], 0.0, relief, mat))
    return parts


def lenin():
    """Памятник Ленину (1960, ск. Г. Е. Арапов, арх. П. С. (Н. С.) Бутенко): бронзовая фигура 4 м на постаменте из
    красного гранита, площадка с лестницей в шесть ступеней к площади, гранитный блок с серпом и молотом у южного края
    лестницы. Гранит — слот ruin (ключа «красный гранит» в krom_plan.COLORS нет), фигура и плита под ней — bronze,
    надпись и серп с молотом — wall."""
    G, B, W = M["ruin"], M["bronze"], M["wall"]
    n, rise, tread = LENIN_STEPS
    rear, front, hw = LENIN_PODIUM
    parts = []
    for k in range(n):                                         # ступени по фасу и бокам, сзади — отвесная стенка
        out = (n - 1 - k) * tread
        parts.append(bk.box("step", rear, front + out, -hw - out, hw + out, -LENIN_BURY, (k + 1) * rise, G))
    top = n * rise
    parts += [bk.box("parapet", rear, rear + 0.4, -hw, hw, top - 0.05, top + 0.4, G)]      # низкий бортик сзади
    parts += [bk.box("parapet_side", rear, rear + 4.0, sv * (hw - 0.4), sv * hw, top - 0.05, top + 0.4, G)
              for sv in (-1, 1)]
    p = LENIN_PED
    w2, u_face = p["w"] / 2, p["w"] / 2
    u_back = u_face - p["deep"]
    so = p["slab_out"]
    parts.append(bk.box("slab", u_back - so, u_face + so, -w2 - so, w2 + so, top - 0.06, top + p["slab"], G))
    z = top + p["slab"]
    gap, c = 0.012, p["course"]
    for k in range(p["courses"]):                              # ряды плит со швами; нижние глубже (уступ сзади)
        ub = u_back if k < p["deep_courses"] else -w2
        parts.append(bk.box("course", ub, u_face, -w2, w2, z + k * c + gap / 2, z + (k + 1) * c - gap / 2, G))
        parts.append(bk.box("joint", ub + 0.02, u_face - 0.02, -w2 + 0.02, w2 - 0.02, z + k * c - gap,
                            z + k * c + gap, G))
    z_top = z + p["courses"] * c
    zc = z + (p["deep_courses"] - 0.5) * c                     # надпись — на верхнем из глубоких рядов
    parts.append(text_block("ЛЕНИН", 0.26, u_face, 0.0, zc + 0.1, 0.015, W, width=1.2))
    parts.append(text_block("1870–1924", 0.1, u_face, 0.0, zc - 0.17, 0.012, W, width=0.62))
    parts.append(bk.box("plinth", -0.8, 0.8, -0.8, 0.8, z_top - 0.02, z_top + p["plinth"], B))
    parts += lenin_figure(z_top + p["plinth"])
    # блок с серпом и молотом у южного (−v) конца лестницы, лицом к площади
    u_b, v_b = front + (n - 1) * tread - 0.9, -(hw + (n - 1) * tread) - 1.1
    parts += [bk.box("emblem_base", u_b - 0.5, u_b + 0.45, v_b - 1.15, v_b + 1.15, -0.3, 0.3, G),
              bk.box("emblem_block", u_b - 0.4, u_b + 0.35, v_b - 1.05, v_b + 1.05, 0.28, 1.3, G)]
    parts += hammer_sickle(u_b + 0.35, v_b, 0.8, 0.75, 0.015, W)
    info = {"height_m": round(z_top + p["plinth"] + LENIN_H, 2), "figure_m": LENIN_H,
            "pedestal_m": round(p["slab"] + p["courses"] * c, 2), "podium_m": round(top, 3),
            "footprint_u_m": [rear, round(front + (n - 1) * tread, 2)], "footprint_v_m": round(hw + (n - 1) * tread, 2),
            "emblem_block_uv": [round(u_b, 2), round(v_b, 2)]}
    return parts, info


# ---------- памятник княгине Ольге на Октябрьской площади ----------
# Оси: u — лицо памятника (азимут 331°, к Троицкому собору), v — вправо от него, z — от земли у нижней ступени лестницы
# (landmarks_plan: ground_at); u = v = 0 — ось постамента. Высоты постамента и скульптуры — по 4,2 м (S-153 ✔), члены
# постамента, площадка и лестница — по фото o27, o16 (S-154) и аэрофото (S-155), гипотеза ±10 %.
OLGA_FIG_H = 4.2                         # скульптура с нимбом
OLGA_STEPS = (4, 0.15, 0.35)             # подступенков, высота, проступь (фото o16)
OLGA_PLAT_R, OLGA_STEP_ARC = 5.5, 60.0   # круглая площадка и сектор лестницы ±60° от оси u (аэрофото 2022, o16)
OLGA_BURY = 0.6                          # тело площадки под землёй
OLGA_SLAB = (5.4, 0.3)                   # опорная плита белого камня: сторона, толщина
# постамент — тело вращения (r, dz от верха плиты), сумма 4,2 м: цоколь 0,32, нижний барабан 1,83 (святые), пояс
# с подписями 0,28, конус 0,44, валик 0,12, верхний барабан 1,05, карниз 0,16
OLGA_PED = [(0.0, -0.02), (1.65, -0.02), (1.65, 0.32), (1.6, 0.32), (1.6, 2.15), (1.66, 2.15), (1.66, 2.43),
            (1.6, 2.43), (1.25, 2.87), (1.28, 2.87), (1.28, 2.99), (1.135, 2.99), (1.135, 4.04), (1.2, 4.04),
            (1.2, 4.2), (0.0, 4.2)]
OLGA_SAINTS = 12


def arc_block(name, r0, r1, z0, z1, a0, a1, mat, seg=None):
    """Сектор кольца: радиусы r0…r1, высоты z0…z1, углы a0…a1 (градусы от оси u к оси v)."""
    seg = seg or max(2, int(abs(a1 - a0) / 3))
    return bk.lathe(name, (0.0, 0.0), [(r0, z0), (r1, z0), (r1, z1), (r0, z1)], mat, seg=seg,
                    closed=True, arc=(math.radians(a0), math.radians(a1)), smooth=False)


def olga_saint(k, z0, r):
    """Святой в рост рельефом на нижнем барабане (радиус r): риза, голова, нимб; пилястра справа от него."""
    ang = 2 * math.pi * k / OLGA_SAINTS
    f = bk.Frame.radial((0.0, 0.0), r, ang)
    W = M["wall"]
    robe = [(-0.27, z0), (0.27, z0), (0.2, z0 + 1.05), (0.19, z0 + 1.28), (0.1, z0 + 1.36), (-0.1, z0 + 1.36),
            (-0.19, z0 + 1.28), (-0.2, z0 + 1.05)]
    head = [(0.1 * math.cos(2 * math.pi * i / 10), z0 + 1.47 + 0.11 * math.sin(2 * math.pi * i / 10)) for i in range(10)]
    halo = [(0.19 * math.cos(2 * math.pi * i / 14), z0 + 1.5 + 0.19 * math.sin(2 * math.pi * i / 14)) for i in range(14)]
    fp = bk.Frame.radial((0.0, 0.0), r, ang + math.pi / OLGA_SAINTS)
    return [bk.extrude("saint_robe", f, robe, -0.03, 0.08, W), bk.extrude("saint_head", f, head, -0.03, 0.09, W),
            bk.extrude("saint_halo", f, halo, -0.03, 0.04, W),
            bk.extrude("pilaster", fp, [(-0.06, z0 - 0.05), (0.06, z0 - 0.05), (0.06, z0 + 1.78), (-0.06, z0 + 1.78)],
                       -0.03, 0.06, W)]


def olga_figure(z0):
    """Бронзовая княгиня Ольга в рост с нимбом (OLGA_FIG_H от z0) и мальчик — князь Владимир — перед ней слева
    с иконой. Ольга: длинные ризы и плащ до земли, венец, нимб-кольцо; правая рука (+v) держит крест у груди, левая —
    на плече мальчика (фото o12, o27, o28). Размеры — человек 1,75 м × s; лицом к +u."""
    s = 2.22                                   # венец — 3,95 м, верх нимба — 4,2 м
    B = M["bronze"]

    def P(u, v, z):
        return (u * s, v * s, z0 + z * s)

    parts = []
    robe = [(0.0, 0.0, 0.26, 0.33), (0.25, 0.0, 0.23, 0.3), (0.6, 0.0, 0.19, 0.27), (0.95, 0.0, 0.17, 0.26),
            (1.2, 0.0, 0.16, 0.26), (1.38, -0.005, 0.15, 0.26), (1.45, -0.01, 0.1, 0.18), (1.49, -0.01, 0.05, 0.07)]
    parts.append(bk.loft("robe", [ellipse(cu * s, 0.0, z0 + z * s, ru * s, rv * s, 20) for z, cu, ru, rv in robe],
                         B, smooth=True))
    # плащ за спиной — от плеч до земли, шире риз
    cloak = [(0.02, -0.08, 0.25, 0.36), (0.6, -0.07, 0.2, 0.31), (1.2, -0.05, 0.17, 0.28), (1.42, -0.04, 0.13, 0.27)]
    parts.append(bk.loft("cloak", [ellipse(cu * s, 0.0, z0 + z * s, ru * s, rv * s, 20) for z, cu, ru, rv in cloak],
                         B, smooth=True))
    parts.append(tube("neck", [P(0.0, 0.0, 1.47), P(0.0, 0.0, 1.55)], [0.05 * s, 0.047 * s], B, n=10))
    head = [(0.0, 1.53), (0.075, 1.55), (0.098, 1.6), (0.1, 1.65), (0.094, 1.69), (0.0, 1.7)]
    parts.append(bk.lathe("head", (0.0, 0.0), [(r * s, z0 + z * s) for r, z in head], B, seg=14))
    parts.append(bk.lathe("veil", (-0.02 * s, 0.0), [(0.0, z0 + 1.46 * s), (0.13 * s, z0 + 1.47 * s),
                                                     (0.12 * s, z0 + 1.62 * s), (0.0, z0 + 1.66 * s)], B, seg=14))
    parts.append(bk.lathe("crown", (0.0, 0.0), [(0.0, z0 + 1.66 * s), (0.092 * s, z0 + 1.66 * s),
                                                (0.095 * s, z0 + 1.74 * s), (0.05 * s, z0 + 1.775 * s),
                                                (0.0, z0 + 1.78 * s)], B, seg=14))
    # нимб — кольцо в плоскости (v, z) за головой: центр 3,84 м, наружный r 0,355 (фото o27: ⌀ ≈0,6–0,7)
    zc, ro, ri = z0 + 1.73 * s, 0.16 * s, 0.14 * s
    ring_o = [(-0.06 * s, ro * math.cos(2 * math.pi * i / 24), zc + ro * math.sin(2 * math.pi * i / 24)) for i in range(24)]
    ring_i = [(-0.06 * s, ri * math.cos(2 * math.pi * i / 24), zc + ri * math.sin(2 * math.pi * i / 24)) for i in range(24)]
    verts = ring_o + ring_i + [(u - 0.02 * s, v, z) for u, v, z in ring_o] + [(u - 0.02 * s, v, z) for u, v, z in ring_i]
    faces = []
    for i in range(24):
        j = (i + 1) % 24
        faces += [[i, j, 24 + j, 24 + i], [48 + i, 72 + i, 72 + j, 48 + j], [i, 48 + i, 48 + j, j],
                  [24 + i, 24 + j, 72 + j, 72 + i]]
    parts.append(bk.mesh("halo", verts, faces, B))
    # правая рука (+v) согнута, кисть у груди держит крест; крест — стойка 1,8…3,2 м, перекладина на 2,95 (фото o27)
    parts.append(tube("arm_r", [P(-0.01, 0.2, 1.41), P(0.02, 0.29, 1.2), P(0.1, 0.27, 1.08), P(0.17, 0.22, 1.1)],
                      [0.06 * s, 0.056 * s, 0.05 * s, 0.045 * s], B, n=10))
    cu, cv = 0.2, 0.225
    parts += [bk.box("cross_shaft", (cu - 0.016) * s, (cu + 0.016) * s, (cv - 0.016) * s, (cv + 0.016) * s,
                     z0 + 0.81 * s, z0 + 1.44 * s, B),
              bk.box("cross_bar", (cu - 0.016) * s, (cu + 0.016) * s, (cv - 0.1) * s, (cv + 0.1) * s,
                     z0 + 1.31 * s, z0 + 1.345 * s, B)]
    # левая рука (−v) опущена вперёд — на плечо мальчика
    parts.append(tube("arm_l", [P(-0.01, -0.2, 1.41), P(0.03, -0.27, 1.18), P(0.1, -0.25, 0.98), P(0.16, -0.19, 0.88)],
                      [0.06 * s, 0.055 * s, 0.048 * s, 0.042 * s], B, n=10))
    # мальчик ≈2,0 м перед Ольгой слева (фото o27): рубаха до пят, голова, икона у груди лицом к +u
    bu, bv = 0.33, -0.12
    boy = [(0.0, 0.1, 0.12), (0.35, 0.085, 0.105), (0.62, 0.07, 0.1), (0.72, 0.06, 0.1), (0.76, 0.035, 0.05)]
    parts.append(bk.loft("boy", [ellipse(bu * s, bv * s, z0 + z * s, ru * s, rv * s, 16) for z, ru, rv in boy], B,
                         smooth=True))
    parts.append(bk.lathe("boy_head", (bu * s, bv * s), [(0.0, z0 + 0.75 * s), (0.05 * s, z0 + 0.77 * s),
                                                         (0.058 * s, z0 + 0.83 * s), (0.045 * s, z0 + 0.88 * s),
                                                         (0.0, z0 + 0.9 * s)], B, seg=12))
    parts.append(bk.box("icon", (bu + 0.08) * s, (bu + 0.1) * s, (bv - 0.09) * s, (bv + 0.09) * s,
                        z0 + 0.46 * s, z0 + 0.7 * s, B))
    parts += [tube("boy_arm", [P(bu, bv + sv * 0.09, 0.71), P(bu + 0.05, bv + sv * 0.1, 0.6),
                               P(bu + 0.08, bv + sv * 0.07, 0.55)], [0.03 * s, 0.028 * s, 0.026 * s], B, n=8)
              for sv in (-1, 1)]
    return parts


def olga():
    """Памятник святой равноапостольной княгине Ольге (2003, ск. В. М. Клыков, арх. С. Ю. Битный): круглая площадка
    с лестницей в 4 подступенка к площади, опорная плита, цилиндрический постамент белого камня 4,2 м с двенадцатью
    святыми на нижнем барабане и доской на верхнем, бронзовая скульптура 4,2 м. Площадка — stone (мощение), её край —
    roof (тёмный гранит), ступени — ruin (красный гранит, как у памятника Ленину), постамент и святые — wall, фигура,
    доска — bronze / dark."""
    n, rise, tread = OLGA_STEPS
    top = n * rise
    R = OLGA_PLAT_R
    parts = [bk.lathe("platform", (0.0, 0.0), [(0.0, -OLGA_BURY), (R - 0.25, -OLGA_BURY), (R - 0.25, top),
                                               (0.0, top)], M["stone"], seg=48, smooth=False),
             bk.lathe("platform_rim", (0.0, 0.0), [(R - 0.25, -OLGA_BURY), (R, -OLGA_BURY), (R, top + 0.02),
                                                   (R - 0.25, top + 0.02)], M["roof"], seg=48, closed=True,
                      smooth=False)]
    for k in range(n - 1):                                     # ступени по дуге к площади (+u), нижняя — k = 0
        r1 = R + (n - 1 - k) * tread
        parts.append(arc_block("step", R - 0.3, r1, -OLGA_BURY, (k + 1) * rise, -OLGA_STEP_ARC, OLGA_STEP_ARC,
                               M["ruin"], seg=40))
    a, t = OLGA_SLAB
    parts.append(bk.box("slab", -a / 2, a / 2, -a / 2, a / 2, top - 0.05, top + t, M["wall"]))
    zs = top + t
    parts.append(bk.lathe("pedestal", (0.0, 0.0), [(r, zs + dz) for r, dz in OLGA_PED], M["wall"], seg=48,
                          smooth=False))
    for k in range(OLGA_SAINTS):
        parts += olga_saint(k, zs + 0.38, 1.6)
    ped_top = zs + OLGA_PED[-1][1]
    zp = ped_top - 0.7                                         # доска: центр в 0,7 м под верхом (фото o27)
    parts.append(bk.lathe("plaque", (0.0, 0.0), [(1.12, zp - 0.3), (1.17, zp - 0.3), (1.17, zp + 0.3),
                                                 (1.12, zp + 0.3)], M["dark"], seg=8, closed=True,
                          arc=(-0.44, 0.44), smooth=False))
    parts.append(bk.lathe("bronze_base", (0.0, 0.0), [(0.0, ped_top - 0.02), (0.72, ped_top - 0.02),
                                                      (0.72, ped_top + 0.08), (0.0, ped_top + 0.08)], M["bronze"],
                          seg=20))
    parts += olga_figure(ped_top + 0.02)
    info = {"height_m": round(ped_top + OLGA_FIG_H, 2), "figure_m": OLGA_FIG_H, "pedestal_m": OLGA_PED[-1][1],
            "slab_m": t, "platform_m": round(top, 2), "platform_r_m": R,
            "foot_u_m": round(R + (n - 1) * tread, 2)}
    return parts, info


# ---------- амфитеатр Детского парка ----------
# Оси: u — от центра дуг к среднему проходу (азимут 168°), v — вправо от него; z — от земли на площадке перед рядами
# (landmarks_plan: ground_at, u = 8). Ряды — дуги OSM (✔ ±0,3 м), подъём и сечения — гипотеза (фото нет).
AMPH_ROWS, AMPH_R0, AMPH_PITCH = 8, 15.3, 1.73   # рядов, радиус первой скамьи, шаг (OSM 15,26…27,38)
AMPH_RISE = 0.3                                  # подъём террасы на ряд (гип.)
AMPH_EDGE = 0.6                                  # край террасы (подступенок) — на столько ближе к центру оси скамьи
AMPH_BLOCK = (3.0, 37.0)                         # блоки скамеек: углы от оси u, ° (OSM: 171–205° и 129–165°)
AMPH_SIDE = 4.0                                  # боковые лестницы за блоками, °
AMPH_BURY = 1.2                                  # тело террас под землёй (heightmap под рядами — ±0,8 м)
AMPH_SEAT = (0.45, 0.4)                          # высота сиденья, ширина доски


def amphitheatre():
    """Летний амфитеатр: мощёная площадка перед рядами (контур relation 3107113), 8 земляных террас с бетонным краем
    двумя блоками, на каждой — деревянная скамья на бетонных опорах, лестницы полуступенями в среднем проходе и по
    бокам. Террасы и площадка — stone, скамьи — wood, опоры — wall."""
    import landmarks_plan
    rows = [AMPH_R0 + AMPH_PITCH * k for k in range(AMPH_ROWS)]
    a_out = AMPH_BLOCK[1] + AMPH_SIDE
    parts = []
    stage = landmarks_plan.amph_stage_uv()               # контур площадки перед рядами — плитой
    parts.append(bk.prism("stage", stage, -0.4, 0.02, M["stone"]))
    for k, r in enumerate(rows):                          # террасы от края перед скамьёй до края следующей
        r_in = r - AMPH_EDGE
        r_out = (rows[k + 1] - AMPH_EDGE) if k + 1 < len(rows) else r + AMPH_PITCH - AMPH_EDGE
        z = AMPH_RISE * (k + 1)
        parts.append(arc_block("terrace", r_in, r_out + (0.0 if k + 1 == len(rows) else 0.05), -AMPH_BURY, z,
                               -a_out, a_out, M["stone"], seg=40))
        # полуступени в проходах: на передней половине террасы ниже (k), подъём к террасе k — в два шага
        half = AMPH_RISE * k + AMPH_RISE / 2
        for a0, a1 in ((-AMPH_BLOCK[0], AMPH_BLOCK[0]), (AMPH_BLOCK[1], a_out), (-a_out, -AMPH_BLOCK[1])):
            parts.append(arc_block("aisle_step", r_in - AMPH_PITCH / 2, r_in, -AMPH_BURY, half, a0, a1, M["stone"],
                                   seg=3))
        # скамья: доска по дуге, опоры через ≈2 м
        zt = z + AMPH_SEAT[0]
        for sgn in (1, -1):
            a0, a1 = sorted((sgn * (AMPH_BLOCK[0] + 0.5), sgn * (AMPH_BLOCK[1] - 0.5)))
            parts.append(arc_block("seat", r - AMPH_SEAT[1] / 2, r + AMPH_SEAT[1] / 2, zt - 0.06, zt, a0, a1,
                                   M["wood"], seg=16))
            n_leg = max(2, int(math.radians(a1 - a0) * r / 2.0) + 1)
            for i in range(n_leg):
                a = a0 + (a1 - a0) * i / (n_leg - 1)
                da = math.degrees(0.08 / r)
                parts.append(arc_block("seat_leg", r - 0.15, r + 0.15, z - 0.05, zt - 0.06, a - da, a + da,
                                       M["wall"], seg=1))
    top = AMPH_RISE * AMPH_ROWS
    info = {"height_m": round(top + AMPH_SEAT[0], 2), "rows": AMPH_ROWS, "row_radii_m": [round(r, 2) for r in rows],
            "rise_m": AMPH_RISE, "top_terrace_m": round(top, 2), "sector_deg": [-a_out, a_out],
            "stage_u_m": [min(u for u, _ in stage), max(u for u, _ in stage)]}
    return parts, info


MODELS = {"BlagCross": blag_cross, "OlgaCross": olga_cross, "DovmontSword": dovmont_sword,
          "RussiaLetters": russia_letters, "Lenin": lenin, "Olga": olga, "Amphitheatre": amphitheatre}

# превью: (глаз, цель, кадр, объектив) в осях модели; фото-ракурсы для листа сверки — build/landmarks_refs/work/cams_*.json
VIEWS = {"BlagCross": {"front": ((7.0, 0.8, 1.6), (0.0, 0.0, 2.3), (720, 960), 35.0),
                       "side": ((4.0, -6.0, 2.0), (0.0, 0.0, 2.2), (720, 960), 35.0)},
         "OlgaCross": {"front": ((6.0, 0.0, 1.5), (0.0, 0.0, 1.6), (720, 960), 35.0),
                       "side": ((3.5, 4.5, 1.8), (0.0, 0.0, 1.6), (720, 960), 35.0)},
         "DovmontSword": {"front": ((14.0, 0.0, -14.5), (0.0, 0.0, -8.0), (720, 1080), 24.0),
                          "oblique": ((30.0, -40.0, -12.5), (0.0, 0.0, -8.0), (720, 1080), 60.0)},
         "RussiaLetters": {"front": ((70.0, 0.0, 4.0), (0.0, 0.0, 2.3), (1600, 500), 35.0),
                           "bridge": ((137.7, -129.6, 11.0), (0.0, 0.0, 2.3), (1280, 853), 54.0)},
         "Lenin": {"front": ((45.0, 0.0, 1.7), (0.0, 0.0, 4.8), (900, 1100), 50.0),       # как l09 — с площадки
                   "oblique": ((19.0, 6.2, 1.6), (0.0, 0.0, 5.6), (900, 1200), 45.0),    # как l19 — с северо-запада
                   "side": ((3.0, 24.0, 2.5), (0.0, 0.0, 4.5), (900, 1000), 40.0)},   # как l06 — с севера
         # Ольга: o12 — с площади с северо-запада (азимут ≈314°, ≈20 м, 52 мм), o27 — с запада (≈286°, ≈45 м, 100 мм)
         "Olga": {"o12": ((19.1, -5.8, 1.6), (0.0, 0.0, 4.6), (720, 960), 52.0),
                  "o27": ((31.8, -31.8, 1.6), (0.0, 0.0, 4.9), (640, 960), 100.0),
                  "side": ((2.0, 24.0, 2.0), (0.0, 0.0, 4.5), (720, 960), 40.0)},
         "Amphitheatre": {"stage": ((4.0, 0.0, 1.7), (21.0, 0.0, 1.4), (1280, 720), 20.0),
                          "oblique": ((-10.0, -32.0, 14.0), (18.0, 0.0, 0.5), (1280, 720), 30.0)}}
HUMAN_AT = {"RussiaLetters": (3.0, 0.0), "Lenin": (8.6, 2.2), "Olga": (8.0, -2.0),
            "Amphitheatre": (10.0, 0.0)}   # человек 1,75 м на превью (u, v); иначе (2,2; 1,6)


def human(u, v, z=0.0):
    """Человек 1,75 м — только превью."""
    skin = bk.material("preview_person", (0.55, 0.35, 0.3))
    return [bk.lathe("person_body", (u, v), [(0.0, z), (0.17, z + 0.02), (0.2, z + 0.9), (0.2, z + 1.45), (0.0, z + 1.5)],
                     skin, seg=12),
            bk.lathe("person_head", (u, v), [(0.0, z + 1.5), (0.1, z + 1.56), (0.1, z + 1.68), (0.0, z + 1.75)], skin,
                     seg=12)]


def build(name):
    asset = f"SM_Mark_{name}"
    bk.reset_scene()
    bk.use_colors(krom_plan.COLORS)
    objs, info = MODELS[name]()
    obj = bk.join(objs, asset)
    bk.box_uv(obj)
    me = obj.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    slots = [m.name for m in me.materials]
    zs = [v.co.z for v in me.vertices]
    print(f"[landmarks] {asset}: {len(objs)} тел, {len(me.vertices)} вершин, {tris} треугольников, слоты {slots}, "
          f"z {min(zs):.2f}…{max(zs):.2f}")
    bk.export_glb(obj, asset)
    # превью: земля, человек, у меча — лицо стены (±10 м) и земля в 15 м под верхом (как на фото, в модели ≈17)
    g = bk.material("ground", (0.12, 0.16, 0.08))
    if name == "DovmontSword":
        bk.box("wall_face", -6.0, 0.0, -10.0, 10.0, -15.0, 0.0, bk.material("wall_preview", krom_plan.COLORS["stone"]))
        bk.box("ground", -30, 40, -40, 40, -15.3, -15.0, g)
        human(6.0, -2.5, -15.0)
    else:
        bk.box("ground", -120, 200, -150, 150, -0.3, 0.0, g)
        human(*HUMAN_AT.get(name, (2.2, 1.6)))
    for view, (eye, target, size, lens) in VIEWS[name].items():
        bk.render_preview(f"landmark_{name}_{view}", eye=(eye[0], -eye[1], eye[2]),
                          target=(target[0], -target[1], target[2]), size=size, lens=lens)
    return {"asset": asset, "tris": tris, "slots": slots, "z_min_m": round(min(zs), 3), "z_max_m": round(max(zs), 3),
            **{k: (round(v, 3) if isinstance(v, float) else v) for k, v in info.items()}}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    todo = [n for n in MODELS if not argv or n in argv]
    if not todo:
        raise SystemExit(f"[landmarks] нет модели {argv}; есть: {list(MODELS)}")
    report = {}
    if os.path.exists(REPORT):
        with open(REPORT, encoding="utf-8") as f:
            report = json.load(f)
    for n in todo:
        r = build(n)
        report[r["asset"]] = r
    os.makedirs(bk.BUILD_DIR, exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(report.items())), f, ensure_ascii=False, indent=2)
    print(f"[landmarks] report {REPORT}")


main()
