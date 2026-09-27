"""leaf_atlas.py — атлас листвы и кора для деревьев M5 (листву и ветви строит scripts/blender/tree.py).

Не для редактора: обычный Python из локального окружения (numpy, pillow, scipy):

    .venv\\Scripts\\python scripts/leaf_atlas.py            # атлас и кора
    .venv\\Scripts\\python scripts/leaf_atlas.py --no-bark  # только атлас

Атлас — refs/textures/leaves/T_LeafAtlas_D.png (RGBA) и T_LeafAtlas_N.png (нормали DirectX, как в UE): 2048²,
сетка 4 × 4 ячеек по 512 px, строка — порода (ROWS), в ячейке — веточка с листьями; основание веточки — середина
нижнего края ячейки (туда tree.py ставит точку крепления карточки). Альфа — только 0 или 255 (masked-материал),
цвет под прозрачным продолжен от ближайшего листа — в мипах нет тёмных ореолов. Рисунок процедурный и
детерминированный (SEED): лопастной клён остролистный, округлая городчатая осина, округло-зубчатая лещина,
сердцевидная липа (формы — по ботаническим описаниям, «на глаз»). Лицензия — наша (сгенерирован скриптом проекта).

Кора — Poly Haven (CC0) через textures_fetch.fetch (Diffuse и nor_dx 2K в refs/textures/polyhaven/; textures.json
не трогаем): шершавая с продольными трещинами — клён и липа, гладкая — осина и лещина.

Сведения — refs/textures/trees.json: раскладка атласа (её читает tree.py), средний цвет листвы по породам
(linear, для деления «текстура / среднее × цвет палитры», как у земли), кора и какая порода с какой корой.
"""
import argparse
import colorsys
import datetime
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402

SEED = 20260926
SIZE = 2048                 # атлас, px
GRID = 4                    # ячеек по стороне
CELL = SIZE // GRID         # 512 px
SS = 4                      # суперсэмплинг рисования
W = CELL * SS               # холст ячейки
MARGIN = 10 * SS            # листья не подходят к краю ячейки ближе (соседи в мипах)
OUT_DIR = os.path.join(geo.REPO, "refs", "textures", "leaves")
OUT_JSON = os.path.join(geo.REPO, "refs", "textures", "trees.json")
ROWS = ("maple", "aspen", "hazel", "linden")  # строка атласа сверху вниз

BARK = {"rough": "bark_brown_02",            # серо-бурая, продольные трещины, 1 м — клён, липа
        "smooth": "chinese_hackberry_bark"}  # гладкая серая с пятнами лишайника, 1,8 м — осина, лещина
BARK_MAPS = ("Diffuse", "nor_dx")
SPECIES_BARK = {"maple": "rough", "linden": "rough", "aspen": "smooth", "hazel": "smooth"}

# Породы. Размеры — доли ячейки: blade — длина пластинки, petiole — черешок; leaves — листьев на главном побеге;
# color / under — верх и изнанка листа (sRGB 0..255), under_p — доля листьев изнанкой к зрителю.
# Доля blade × сторона карточки (LEAF в tree.py) = лист в метрах: клён 0,24 × 0,7 ≈ 17 см, осина 0,125 × 0,55 ≈ 7 см,
# лещина 0,19 × 0,55 ≈ 10 см, липа 0,135 × 0,55 ≈ 7 см — как у живых листьев.
SPECIES = {
    "maple": dict(name="клён остролистный", shape="maple", color=(62, 104, 34), under=(112, 142, 80), under_p=0.15,
                  blade=(0.22, 0.26), petiole=(0.07, 0.11), leaves=(7, 9), opposite=True, veins="palmate"),
    "aspen": dict(name="осина", shape="aspen", color=(74, 112, 50), under=(128, 152, 110), under_p=0.3,
                  blade=(0.11, 0.14), petiole=(0.07, 0.10), leaves=(13, 17), opposite=False, veins="pinnate"),
    "hazel": dict(name="лещина", shape="hazel", color=(76, 118, 40), under=(122, 150, 92), under_p=0.15,
                  blade=(0.17, 0.21), petiole=(0.02, 0.035), leaves=(9, 12), opposite=False, veins="pinnate"),
    "linden": dict(name="липа мелколистная", shape="linden", color=(56, 98, 34), under=(110, 138, 86), under_p=0.2,
                   blade=(0.12, 0.15), petiole=(0.05, 0.07), leaves=(13, 16), opposite=False, veins="pinnate"),
}
SIDE_SHOOTS = (1, 2, 3, 2)    # боковых побегов по вариантам ячейки (слева направо)
STEM = (92, 80, 52)           # веточка: серо-бурая
MAPLE_LOBES = (0.0, 58.0, 112.0, 158.0)  # направления главных жилок клёна, градусы от оси листа


# ---------- контуры листьев: база (0, 0), кончик (0, 1), x — поперёк ----------

def _outline(r, center_y, n=720, asym=0.0):
    """Контур по полярной функции r(|φ|) вокруг (0, center_y); φ — от оси листа к кончику, правая сторона шире на asym.
    Нормируется: точка φ = π (выемка у черешка) → (0, 0), кончик φ = 0 → (0, 1)."""
    phi = np.linspace(-math.pi, math.pi, n, endpoint=False)
    a = np.abs(phi)
    rr = r(a) * np.where(phi > 0, 1.0 + asym, 1.0 - asym)
    pts = np.stack([rr * np.sin(phi), center_y + rr * np.cos(phi)], axis=1)
    base = center_y - r(np.array([math.pi]))[0]
    tip = center_y + r(np.array([0.0]))[0]
    pts[:, 1] -= base
    return pts / (tip - base)


def _peak(a, at, amp, w, p=1.6):
    """Острый зубец/лопасть: вершина с изломом в at (радианы), плавные пазухи по бокам."""
    return amp * np.clip(1.0 - np.abs(a - at) / w, 0.0, None) ** p


def leaf_outline(shape, rng):
    d = math.radians
    asym = rng.uniform(-0.04, 0.04)
    if shape == "maple":
        # 5 лопастей (+2 маленькие у основания), на лопастях — редкие длинные зубцы, пазухи округлые
        def r(a):
            v = 0.31 + _peak(a, 0.0, 0.29, d(30), 1.8) + _peak(a, d(58), 0.28, d(30), 1.8) \
                + _peak(a, d(112), 0.17, d(26), 1.8) + _peak(a, d(158), 0.03, d(14))
            for at, amp in ((17, 0.07), (41, 0.06), (75, 0.06), (97, 0.05), (128, 0.04)):
                v = v + _peak(a, d(at), amp, d(5), 1.1)
            return v - 0.06 * np.exp(-((a - math.pi) / d(10)) ** 2)
        return _outline(r, 0.40, asym=asym)
    if shape == "aspen":
        # почти круглый, короткое остриё, основание усечённое, край городчатый
        n = rng.choice((24, 28, 32))
        def r(a):
            base = 0.47 * (1.0 + 0.03 * np.cos(a)) + _peak(a, 0.0, 0.07, 0.35, 1.5) \
                - 0.04 * np.exp(-((a - math.pi) / 0.35) ** 2)
            teeth = 0.035 * (1.0 - np.sqrt(np.abs(np.sin(n * a / 2.0)))) * np.clip((2.7 - a) / 0.4, 0.0, 1.0)
            return base * (1.0 - teeth)
        return _outline(r, 0.5, asym=asym)
    if shape == "hazel":
        # округло-обратнояйцевидный, сердцевидное основание, короткое оттянутое остриё, двоякозубчатый край
        def r(a):
            base = 0.46 + 0.05 * np.cos(a) - 0.10 * np.exp(-((a - math.pi) / 0.28) ** 2) + _peak(a, 0.0, 0.13, 0.28, 1.8)
            fade = np.clip((2.8 - a) / 0.4, 0.0, 1.0)
            saw = (a * 22 / (2 * math.pi)) % 1.0 * 0.025 + (a * 66 / (2 * math.pi)) % 1.0 * 0.012
            return base * (1.0 - saw * fade)
        return _outline(r, 0.47, asym=asym)
    if shape == "linden":
        # сердцевидный, основание неравнобокое, оттянутое остриё, мелкопильчатый край
        def r(a):
            base = 0.44 + 0.03 * np.cos(a) - 0.13 * np.exp(-((a - math.pi) / 0.32) ** 2) + _peak(a, 0.0, 0.20, 0.42, 2.0)
            fade = np.clip((2.8 - a) / 0.4, 0.0, 1.0)
            return base * (1.0 - (a * 48 / (2 * math.pi)) % 1.0 * 0.02 * fade)
        return _outline(r, 0.42, asym=asym + 0.05)
    raise ValueError(shape)


def veins(shape_veins, x, y):
    """Сила жилки 0..1 в точках (x, y) листа."""
    if shape_veins == "palmate":
        ox, oy = 0.0, 0.18
        px, py = x - ox, y - oy
        rho = np.hypot(px, py) + 1e-6
        ang = np.arctan2(px, py)
        v = np.zeros_like(x)
        for deg_ in MAPLE_LOBES:
            for s in ((1, -1) if deg_ else (1,)):
                delta = ang - s * math.radians(deg_)
                dist = rho * np.abs(np.sin(delta))
                w = 0.010 + 0.012 * np.clip(0.9 - rho, 0.0, 1.0)
                v = np.maximum(v, np.exp(-(dist / w) ** 2) * (np.cos(delta) > 0))
        return v
    mid_w = 0.010 + 0.012 * np.clip(1.0 - y, 0.0, 1.0)
    mid = np.exp(-(x / mid_w) ** 2)
    yl = y - 0.9 * np.abs(x)
    ph = yl * 7.0
    dist = np.abs(ph - np.round(ph)) / 7.0
    lat = np.exp(-(dist / 0.007) ** 2) * ((yl > 0.04) & (yl < 0.85)) * 0.75
    return np.maximum(mid, lat)


# ---------- рисование на холсте ячейки ----------

class Canvas:
    def __init__(self, rng):
        self.rng = rng
        self.col = np.zeros((W, W, 3), np.float32)
        self.alpha = np.zeros((W, W), np.float32)
        self.h = np.zeros((W, W), np.float32)
        small = rng.random((24, 24)).astype(np.float32)
        self.noise = ndimage.zoom(small, W / 24, order=3)[:W, :W] - 0.5    # низкочастотная неоднородность

    def shadow(self, mask, box):
        """Тень от нового листа на уже нарисованное (свет слева сверху): затемнить под сдвинутой размытой маской."""
        x0, y0, x1, y1 = box
        off = int(0.012 * W)
        pad = off + int(0.02 * W)
        X0, Y0, X1, Y1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(W, y1 + pad)
        big = np.zeros((Y1 - Y0, X1 - X0), np.float32)
        big[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0] = mask
        big = ndimage.shift(big, (off * 1.4, off), order=0)
        big = ndimage.gaussian_filter(big, 0.01 * W)
        self.col[Y0:Y1, X0:X1] *= (1.0 - 0.35 * big * self.alpha[Y0:Y1, X0:X1])[..., None]

    def put(self, mask, box, col, h):
        x0, y0, x1, y1 = box
        m = mask > 0.5
        self.col[y0:y1, x0:x1][m] = col[m]
        self.alpha[y0:y1, x0:x1][m] = 1.0
        self.h[y0:y1, x0:x1][m] = h[m]


def raster(poly):
    """Маска многоугольника [(x, y)] px холста: (маска, bbox) в пределах холста."""
    p = np.asarray(poly)
    x0, y0 = np.floor(p.min(axis=0)).astype(int) - 2
    x1, y1 = np.ceil(p.max(axis=0)).astype(int) + 2
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(W, y1)
    img = Image.new("L", (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(img).polygon([(float(x - x0), float(y - y0)) for x, y in p], fill=255)
    return np.asarray(img, np.float32) / 255.0, (x0, y0, x1, y1)


def stroke(cv, pts, w0, w1, rgb):
    """Стебель по ломаной pts (px холста) толщиной от w0 до w1: цвет с полутоном по «трубке», высота — валик."""
    x0 = int(max(0, min(p[0] for p in pts) - w0 - 2))
    y0 = int(max(0, min(p[1] for p in pts) - w0 - 2))
    x1 = int(min(W, max(p[0] for p in pts) + w0 + 2))
    y1 = int(min(W, max(p[1] for p in pts) + w0 + 2))
    if x1 <= x0 or y1 <= y0:
        return
    img = Image.new("L", (x1 - x0, y1 - y0), 0)
    dr = ImageDraw.Draw(img)
    n = len(pts)
    for i in range(n - 1):
        w = w0 + (w1 - w0) * i / max(1, n - 2)
        a = (pts[i][0] - x0, pts[i][1] - y0)
        b = (pts[i + 1][0] - x0, pts[i + 1][1] - y0)
        dr.line([a, b], fill=255, width=max(1, int(round(w))))
        dr.ellipse([a[0] - w / 2, a[1] - w / 2, a[0] + w / 2, a[1] + w / 2], fill=255)
    m = np.asarray(img, np.float32) / 255.0
    dist = ndimage.distance_transform_edt(m > 0.5)
    tube = np.clip(dist / max(1.0, w0 / 2), 0.0, 1.0)
    base = np.array(rgb, np.float32) / 255.0
    col = base[None, None, :] * (0.75 + 0.35 * tube)[..., None]
    cv.put(m, (x0, y0, x1, y1), col, 0.35 * np.sqrt(tube))


def leaf(cv, sp, origin, theta, length, under, rng):
    """Пластинка листа: основание в origin (px), направление theta (0 — вверх, по часовой), длина length px."""
    shape = leaf_outline(sp["shape"], rng)
    d = np.array([math.sin(theta), -math.cos(theta)])
    perp = np.array([math.cos(theta), math.sin(theta)])
    if rng.random() < 0.5:                      # лист может лечь любой стороной — зеркалим
        shape = shape * np.array([-1.0, 1.0])
    poly = origin + length * (shape[:, 1:2] * d + shape[:, 0:1] * perp)
    mask, box = raster(poly)
    if mask.sum() < 4:
        return
    x0, y0, x1, y1 = box
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32) + 0.5
    rel_x, rel_y = xx - origin[0], yy - origin[1]
    ly = (rel_x * d[0] + rel_y * d[1]) / length
    lx = (rel_x * perp[0] + rel_y * perp[1]) / length
    v = veins(sp["veins"], lx, ly)
    rgb = sp["under"] if under else sp["color"]
    hh, ss, vv = colorsys.rgb_to_hsv(*(c / 255.0 for c in rgb))
    hh = (hh + rng.uniform(-0.018, 0.018)) % 1.0
    if rng.random() < 0.08:                     # редкий лист желтее
        hh -= 0.03
    ss = min(1.0, max(0.0, ss * rng.uniform(0.88, 1.1)))
    vv = vv * rng.uniform(0.82, 1.08)
    base = np.array(colorsys.hsv_to_rgb(hh, ss, vv), np.float32)
    shade = 0.84 + 0.2 * np.clip(ly, 0.0, 1.0) + 0.25 * cv.noise[y0:y1, x0:x1]
    col = base[None, None, :] * shade[..., None]
    vein_col = np.minimum(1.0, base * (1.25 if not under else 1.35) + np.array([0.06, 0.06, 0.0], np.float32))
    k = (0.38 if not under else 0.55) * (0.7 if sp["veins"] == "palmate" else 1.0) * v
    col = col * (1.0 - k[..., None]) + vein_col[None, None, :] * k[..., None]
    edge = ndimage.distance_transform_edt(mask > 0.5) / (0.07 * length)
    h = 0.6 * np.sqrt(np.clip(edge, 0.0, 1.0)) - 0.25 * v * (1.0 if not under else -0.6)
    cv.shadow(mask, box)
    cv.put(mask, box, np.clip(col, 0.0, 1.0), h)


def bezier(p0, p1, p2, n=24):
    t = np.linspace(0.0, 1.0, n)[:, None]
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2


def fits(sp, origin, theta, length):
    """Пластинка (приближённо — эллипс по оси) целиком внутри ячейки с полем MARGIN."""
    d = np.array([math.sin(theta), -math.cos(theta)])
    perp = np.array([math.cos(theta), math.sin(theta)])
    half = 0.62 if sp["shape"] == "maple" else 0.5
    pts = [origin + length * (t * d + s * half * perp) for t in (0.0, 0.5, 1.0) for s in (-1, 0, 1)]
    return all(MARGIN <= p[0] <= W - MARGIN and MARGIN <= p[1] <= W - MARGIN for p in pts)


def shoot(cv, sp, p0, p1, p2, n_leaves, width, rng, terminal=True, t_from=0.22):
    """Побег по кривой Безье p0→p2 с листьями: очерёдными или супротивными (клён), плюс верхушечный."""
    pts = bezier(np.array(p0, float), np.array(p1, float), np.array(p2, float))
    stroke(cv, [tuple(p) for p in pts], width, width * 0.4, STEM)
    items = []
    if sp["opposite"]:
        pairs = max(1, (n_leaves - (1 if terminal else 0)) // 2)
        for i in range(pairs):
            t = t_from + (0.9 - t_from) * (i + 0.5) / pairs
            items += [(t, -1), (t, 1)]
    else:
        m = n_leaves - (1 if terminal else 0)
        side = rng.choice((-1, 1))
        for i in range(m):
            items.append((t_from + (0.92 - t_from) * (i + rng.uniform(0.2, 0.8)) / m, side))
            side = -side
    if terminal:
        items.append((1.0, 0))
    for t, side in items:
        i = min(len(pts) - 2, int(t * (len(pts) - 1)))
        at = pts[i]
        tang = pts[i + 1] - pts[i]
        stem_theta = math.atan2(tang[0], -tang[1])
        theta = stem_theta + side * math.radians(rng.uniform(38, 68)) + math.radians(rng.uniform(-8, 8))
        blade = rng.uniform(*sp["blade"]) * W
        pet = rng.uniform(*sp["petiole"]) * W
        for _ in range(6):                      # не влезает — уменьшить и повернуть к побегу
            base = at + pet * np.array([math.sin(theta), -math.cos(theta)])
            if fits(sp, base, theta, blade):
                break
            blade *= 0.88
            pet *= 0.9
            theta = stem_theta + (theta - stem_theta) * 0.85
        base = at + pet * np.array([math.sin(theta), -math.cos(theta)])
        stroke(cv, [tuple(at), tuple(base)], max(3.0, width * 0.45), max(2.0, width * 0.3),
               tuple(int(c * 0.9 + 18) for c in sp["color"]))
        leaf(cv, sp, base, theta, blade, rng.random() < sp["under_p"], rng)
    return pts


def draw_cell(sp, variant, rng):
    """Веточка породы sp: основание — середина нижнего края; variant 0..3 — от простой до ветвистой."""
    cv = Canvas(rng)
    bottom = np.array([W / 2, W - 1.0])
    top = np.array([W / 2 + rng.uniform(-0.12, 0.12) * W, rng.uniform(0.14, 0.2) * W])
    ctrl = (bottom + top) / 2 + np.array([rng.uniform(-0.14, 0.14) * W, 0.0])
    n = int(rng.integers(sp["leaves"][0], sp["leaves"][1] + 1))
    first = int(rng.integers(0, 2))
    shoots = SIDE_SHOOTS[variant]
    axis = bezier(bottom, ctrl, top)
    for k in range(shoots):                     # боковые побеги — ячейка гуще
        t = 0.25 + 0.45 * (k + rng.uniform(0.2, 0.8)) / shoots
        at = axis[int(t * (len(axis) - 1))]
        side = (-1) ** (k + first)
        end = at + np.array([side * rng.uniform(0.28, 0.36) * W, -rng.uniform(0.22, 0.34) * W])
        end = np.clip(end, MARGIN * 3, W - MARGIN * 3)
        mid = (at + end) / 2 + np.array([0.0, rng.uniform(0.02, 0.06) * W])
        shoot(cv, sp, at, mid, end, max(3, n // 2), 0.009 * W, rng)
    shoot(cv, sp, bottom, ctrl, top, n + (2 if variant == 3 else 0), 0.014 * W, rng)
    return cv


# ---------- сборка атласа ----------

def downsample(cv):
    """Суперсэмпл → ячейка: альфа по порогу 0,5 (только 0/255), цвет — средний по закрытой части пикселя;
    под прозрачным — цвет ближайшего непрозрачного пикселя. Высота → нормали DirectX."""
    a = cv.alpha.reshape(CELL, SS, CELL, SS).mean(axis=(1, 3))
    col = (cv.col * cv.alpha[..., None]).reshape(CELL, SS, CELL, SS, 3).sum(axis=(1, 3))
    col = col / np.maximum(a * SS * SS, 1e-6)[..., None]
    solid = a >= 0.5
    if solid.any():
        _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
        col = col[iy, ix]
    h = cv.h.reshape(CELL, SS, CELL, SS).mean(axis=(1, 3))
    h = ndimage.gaussian_filter(h, 0.8)
    gy, gx = np.gradient(h)
    k = 6.0
    n = np.stack([-gx * k, gy * k, np.ones_like(h)], axis=-1)  # DirectX: зелёный — вниз по картинке
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    n[~solid] = (0.0, 0.0, 1.0)
    return (np.clip(col, 0, 1) * 255 + 0.5).astype(np.uint8), (solid * 255).astype(np.uint8), \
        ((n * 0.5 + 0.5) * 255 + 0.5).astype(np.uint8)


def mean_linear(rgb, alpha):
    a = rgb[alpha > 0].astype(np.float64) / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    return [round(float(v), 4) for v in lin.mean(axis=0)]


def build_atlas():
    os.makedirs(OUT_DIR, exist_ok=True)
    rgba = np.zeros((SIZE, SIZE, 4), np.uint8)
    nrm = np.zeros((SIZE, SIZE, 3), np.uint8)
    rows = {}
    for r, key in enumerate(ROWS):
        sp = SPECIES[key]
        for c in range(GRID):
            rng = np.random.default_rng([SEED, r, c])
            rgb, a, n = downsample(draw_cell(sp, c, rng))
            ys, xs = slice(r * CELL, (r + 1) * CELL), slice(c * CELL, (c + 1) * CELL)
            rgba[ys, xs, :3], rgba[ys, xs, 3], nrm[ys, xs] = rgb, a, n
            print(f"  {key} {c}: покрытие {a.mean() / 255:.2f}")
        cell = rgba[r * CELL:(r + 1) * CELL]
        rows[key] = {"row": r, "name": sp["name"], "coverage": round(float((cell[..., 3] > 0).mean()), 3),
                     "mean_linear": mean_linear(cell[..., :3], cell[..., 3])}
    d_path = os.path.join(OUT_DIR, "T_LeafAtlas_D.png")
    n_path = os.path.join(OUT_DIR, "T_LeafAtlas_N.png")
    Image.fromarray(rgba, "RGBA").save(d_path, optimize=True)
    Image.fromarray(nrm, "RGB").save(n_path, optimize=True)
    print(f"atlas {d_path}\n      {n_path}")
    rel = lambda p: os.path.relpath(p, geo.REPO).replace("\\", "/")  # noqa: E731
    return {"diffuse": rel(d_path), "normal": rel(n_path), "size": SIZE, "grid": [GRID, GRID], "rows": rows,
            "cell": "строка — порода (row 0 — верх картинки), 4 варианта веточки слева направо: от простой до ветвистой",
            "pivot": "основание веточки — середина нижнего края ячейки",
            "alpha": "0/255, порог 0,5 при уменьшении с 4× (masked); цвет под прозрачным продолжен",
            "normal_space": "DirectX (как nor_dx Poly Haven)", "seed": SEED,
            "license": "сгенерирован scripts/leaf_atlas.py (свой, без ограничений)"}


def fetch_bark():
    import textures_fetch as tf
    os.makedirs(tf.OUT_DIR, exist_ok=True)
    out = {}
    for role, asset in BARK.items():
        out[role] = tf.fetch(asset, BARK_MAPS)
        print(f"bark {role}: {asset} {out[role]['tile_m']} м, среднее {out[role]['mean_linear']}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-bark", action="store_true", help="не трогать кору (оставить из прежнего trees.json)")
    args = ap.parse_args()
    old = {}
    if os.path.exists(OUT_JSON):
        with open(OUT_JSON, encoding="utf-8") as f:
            old = json.load(f)
    out = {"generated": datetime.date.today().isoformat(), "script": "scripts/leaf_atlas.py",
           "atlas": build_atlas(),
           "bark": old.get("bark", {}) if args.no_bark else fetch_bark(),
           "bark_source": "Poly Haven (polyhaven.com), CC0; UV коры в tree.py — в метрах (U по окружности, V вдоль ветви)",
           "species_bark": SPECIES_BARK}
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"json {OUT_JSON}")


if __name__ == "__main__":
    main()
