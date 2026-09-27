"""cemetery_points.py — точки надгробий и звеньев ограды Мироносицкого кладбища на Завеличье (M5+) → build/cemetery.

Не для редактора: запускается обычным Python из .venv (numpy, scipy, matplotlib):

    PYTHONIOENCODING=utf-8 .venv/Scripts/python scripts/cemetery_points.py

Z у точек нет: землю под каждой найдёт трасса в редакторе (scripts/cemetery_krom.py). Оси и метры — D-013: x — север,
y — восток, начало — центр Троицкого собора. Всё детерминированно (SEED). Модели — scripts/blender/cemetery.py
(виды — KINDS).

Что откуда:
- контур кладбища — OSM way 99751207 (landuse=cemetery); Landscape кончается на y = −1008 (±1008 м от собора):
  западные 29 % кладбища за краем — там точек нет (до расширения Landscape);
- ограда — OSM barrier=wall: way 99751216 (восточная сторона и улица у ворот) и 49130275 (улица к западу от ворот),
  звенья SM_Cem_WallSeg по 3 м (≤ WALL_SEG_M, растягиваются по длине куска); высота 1,1 м — по фото 000, 008 (S-81),
  гипотеза. С севера и запада стены в OSM нет — там ограды не ставим (по фото не видно);
- аллеи — OSM highway внутри контура (ALLEYS, полуширина с запасом); плюс по гипотезе дорожка от главной аллеи
  к крыльцу храма (EXTRA_PATHS) и поперечные проходы через каждые AISLE_EVERY_M вдоль рядов;
- без могил: храм и его пристройки (OSM 192946557 и контур героя krom_plan.MIRONOSITSY, если он есть) + BUILD_GAP_M,
  часовня у храма, ворота с колокольней (66014994 и прямоугольник krom_plan.MIRONOSITSY_GATE), школа (164681102)
  с подъездом, газон у ограды (66668103), руины церкви Первой мировой и единоверческой часовни (CLEARINGS, по
  координатам ОКН). Братская могила военнопленных в северной части (S-84) — место неизвестно, не выделена;
- деревья — build/trees/points.json: могила не ближе TRUNK_GAP_M к стволу (углы участка) и 1,2 м (середина).

Раскладка (гипотеза по фото 005, 013 — S-81, и по обычному устройству городских кладбищ): ряды вдоль длинной оси
кладбища (азимут ROW_AZ, как восточная и западная стороны контура), могилы — поперёк рядов, длинной стороной
почти по оси запад — восток (yaw = ROW_AZ + 90 ± YAW_JITTER, памятник «в ногах», на востоке). Шаг рядов ROW_PITCH_M:
участок 2,4 м + проход ≈1 м; в ряду участки через просвет GAP_M. Заполненность — плавное поле шума (NOISE_CELL_M):
на старом кладбище много утраченных и заросших могил; у храма, ворот и главной аллеи — плотнее (FILL_NEAR),
дальше — реже (FILL_FAR). Доли видов — WEIGHTS (гипотеза по фото: у храма больше оградок и гранитных стел, в глубине —
кресты и старые надгробия).

Выход (build/cemetery, не в git): points.json — заголовок (виды, правила, счётчики) и точки по одной на строку:
kind, x, y, yaw_deg (поворот +X модели к +Y, как yaw в UE), scale_x (у звеньев ограды), source; points.png — план.
"""
import datetime
import json
import math
import os
import sys

import matplotlib
import numpy as np
from scipy.spatial import cKDTree

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.path import Path  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402

OUT_DIR = os.path.join(geo.REPO, "build", "cemetery")
OUT_JSON = os.path.join(OUT_DIR, "points.json")
OUT_PNG = os.path.join(OUT_DIR, "points.png")
TREES = os.path.join(geo.REPO, "build", "trees", "points.json")

SEED = 1546                      # год каменного храма
HALF = 1008.0                    # Landscape ±1008 м
EDGE_GAP_M = 1.5                 # от края Landscape
CEM_WAY = 99751207
WALL_WAYS = (99751216, 49130275)
WALL_SEG_M = 3.0
BORDER_GAP_M = 1.2               # от контура кладбища (внутренняя грань ограды)
ALLEYS = {                       # OSM way → полуширина с запасом, м
    66668108: 2.0,               # главная аллея от ворот на север (footway, ground)
    137590685: 1.6,              # тропа вдоль южной и восточной стороны (path)
    127019342: 1.6,              # дорожка вдоль восточной стены
    99750837: 1.6,               # дорожка на севере
    149722374: 2.0,              # проезд у северо-восточной калитки (track)
    293511304: 2.0,              # проход под колокольней
    66668104: 2.0,               # дорожка от улицы к воротам
    137591980: 2.5,              # подъезд к школе
}
EXTRA_PATHS = (                  # гипотеза: дорожка от главной аллеи к западному крыльцу храма
    (((-26.0, -961.4), (-18.8, -957.2)), 1.5),
)
BUILDINGS = {192946557: 3.5, 66014994: 4.0, 164681102: 4.0}   # OSM way → отступ, м
LAWNS = (66668103,)              # газон между улицей и оградой
CLEARINGS = (                    # без могил: руины по координатам ОКН (S-83, S-84; точность ≈10 м), радиус, м
    ((235.0, -997.3), 9.0),      # руины церкви в память Первой мировой, ≈8 × 8 м
    ((118.0, -931.4), 7.0),      # руины единоверческой часовни 1878 г.
)
GATE_GAP_M = 3.0                 # от ворот с корпусами (krom_plan.MIRONOSITSY_GATE, 18 × 5,2 м)
BUILD_GAP_M = 3.5
CHAPEL_GAP_M = 2.0
TRUNK_GAP_M = 0.7
ROW_AZ = -9.0                    # азимут рядов: западная сторона контура −9,3°, восточная стена −8,4°
YAW_JITTER = 4.0
ROW_PITCH_M = 3.4
ROW_JITTER_M = 0.25
GAP_M = (0.25, 0.75)
AISLE_EVERY_M = 36.0             # поперечные проходы (гипотеза)
AISLE_HALF_M = 1.0
NOISE_CELL_M = 14.0
FILL_NEAR, FILL_FAR = 0.9, 0.7
NEAR_CHURCH_M, NEAR_ALLEY_M = 45.0, 20.0

KINDS = {   # вид → модель (scripts/blender/cemetery.py): габарит в плане вдоль рядов (ширина) и поперёк (длина)
    "plot_stela": {"asset": "SM_Cem_PlotStela", "w": 2.1, "l": 2.7, "note": "оградка «серебрянкой», стела, скамейка"},
    "plot_cross": {"asset": "SM_Cem_PlotCross", "w": 2.1, "l": 2.7, "note": "чёрная оградка, металлический крест"},
    "plot_double": {"asset": "SM_Cem_PlotDouble", "w": 2.9, "l": 2.7, "note": "зелёная оградка, две стелы, столик"},
    "stela": {"asset": "SM_Cem_Stela", "w": 1.1, "l": 2.1, "note": "гранитная стела с цветником"},
    "cross_metal": {"asset": "SM_Cem_CrossMetal", "w": 1.2, "l": 2.2, "note": "металлический крест в цветнике"},
    "cross_wood": {"asset": "SM_Cem_CrossWood", "w": 1.1, "l": 2.2, "note": "деревянный крест с кровелькой"},
    "monument": {"asset": "SM_Cem_Monument", "w": 1.5, "l": 1.5, "note": "старое надгробие: тумба с крестом"},
    "wall": {"asset": "SM_Cem_WallSeg", "w": 0.5, "l": 3.0, "note": "звено ограды 3 м, scale_x — по длине куска"},
}
WEIGHTS = {  # доли видов у храма и аллеи / в глубине (гипотеза)
    "near": {"plot_stela": 0.30, "plot_cross": 0.20, "plot_double": 0.12, "stela": 0.16, "cross_metal": 0.10,
             "cross_wood": 0.06, "monument": 0.06},
    "far": {"plot_stela": 0.20, "plot_cross": 0.22, "plot_double": 0.06, "stela": 0.12, "cross_metal": 0.14,
            "cross_wood": 0.16, "monument": 0.10},
}
COLORS = {"plot_stela": "#9aa0a6", "plot_cross": "#202124", "plot_double": "#1e6b4a", "stela": "#5f6368",
          "cross_metal": "#8e24aa", "cross_wood": "#8d6e63", "monument": "#e37400"}


def seg_dist(p, line):
    """Расстояния от точек p (N×2) до ломаной line."""
    a = np.asarray(line[:-1], float)
    b = np.asarray(line[1:], float)
    d = b - a
    L2 = np.maximum((d ** 2).sum(1), 1e-12)
    t = np.clip(((p[:, None, :] - a[None]) * d[None]).sum(2) / L2[None], 0, 1)
    q = a[None] + t[..., None] * d[None]
    return np.sqrt(((p[:, None, :] - q) ** 2).sum(2)).min(1)


class Site:
    """Контур, препятствия и деревья кладбища в метрах проекта."""

    def __init__(self):
        els = {}
        for e in geo.load_elements(geo.latest("krom_2*.json")):
            els.setdefault((e["type"], e["id"]), e)

        def way(i):
            return [p for p in geo.local_points(els[("way", i)]["geometry"]) if p]
        self.poly = geo.open_ring(way(CEM_WAY))
        self.path = Path(self.poly)
        self.ring = self.poly + [self.poly[0]]
        self.walls = [way(i) for i in WALL_WAYS]
        self.alleys = [(way(i), w) for i, w in ALLEYS.items()] + [(list(line), w) for line, w in EXTRA_PATHS]
        self.buildings = [(geo.open_ring(way(i)), g) for i, g in BUILDINGS.items()]
        self.lawns = [Path(geo.open_ring(way(i))) for i in LAWNS]
        self.church = geo.centroid(geo.open_ring(way(192946557)))
        self.chapels = [(c, r) for c, r in CLEARINGS]
        self.gate = None
        try:                                   # контур героя, часовня и ворота — из планов krom_plan, если они есть
            import krom_plan
            g = getattr(krom_plan, "MIRONOSITSY_GATE", None)
            if g is not None:                  # ворота с корпусами: прямоугольник по size в осях ворот
                hu, hv = g.size[0] / 2, g.size[1] / 2
                self.gate = [krom_plan.to_world(g.center, g.yaw, su * hu, sv * hv)
                             for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                self.buildings.append((list(self.gate), GATE_GAP_M))
            p = getattr(krom_plan, "MIRONOSITSY", None)
            if p is not None:
                ring = [krom_plan.to_world(p.center, p.yaw, u, v) for u, v in p.outline()]
                self.buildings.append((list(ring), BUILD_GAP_M))
                for a in p.annexes:
                    if a.name.startswith("chapel"):
                        c = krom_plan.to_world(p.center, p.yaw, (a.u0 + a.u1) / 2, (a.v0 + a.v1) / 2)
                        r = math.hypot(a.u1 - a.u0, a.v1 - a.v0) / 2
                        self.chapels.append((c, r + CHAPEL_GAP_M))
        except ImportError:
            pass
        self.bpaths = [Path(r) for r, _ in self.buildings]
        with open(TREES, encoding="utf-8") as f:
            P = np.array(self.poly)
            lo, hi = P.min(0) - 5.0, P.max(0) + 5.0
            trees = [t for t in json.load(f)["points"] if lo[0] < t["x"] < hi[0] and lo[1] < t["y"] < hi[1]]
        self.trees = np.array([(t["x"], t["y"]) for t in trees]) if trees else np.zeros((0, 2))
        self.tree_kd = cKDTree(self.trees) if len(self.trees) else None
        self.main_alley = way(66668108)

    def free(self, pts, trunk_gap):
        """Можно ли ставить: все точки pts (N×2) внутри кладбища и Landscape, вне аллей, зданий, газона и стволов."""
        if np.any(np.abs(pts) > HALF - EDGE_GAP_M):
            return "edge"
        if not np.all(self.path.contains_points(pts)):
            return "outside"
        if np.any(seg_dist(pts, self.ring) < BORDER_GAP_M):
            return "border"
        for line, w in self.alleys:
            if np.any(seg_dist(pts, line) < w):
                return "alley"
        for (ring, gap), bp in zip(self.buildings, self.bpaths):
            if np.any(bp.contains_points(pts)) or np.any(seg_dist(pts, ring + [ring[0]]) < gap):
                return "building"
        for c, r in self.chapels:
            if np.any(np.hypot(pts[:, 0] - c[0], pts[:, 1] - c[1]) < r):
                return "building"
        for lp in self.lawns:
            if np.any(lp.contains_points(pts)):
                return "lawn"
        if self.tree_kd is not None:
            d, _ = self.tree_kd.query(pts)
            if np.any(d < trunk_gap) or d[0] < 1.2:
                return "tree"
        return None


def noise_field(rng, x0, y0, x1, y1, cell):
    """Плавный шум 0…1: случайные значения в узлах сетки cell, билинейно."""
    nx, ny = int((x1 - x0) / cell) + 2, int((y1 - y0) / cell) + 2
    g = rng.random((nx, ny))

    def at(x, y):
        fx, fy = (x - x0) / cell, (y - y0) / cell
        i, j = int(fx), int(fy)
        a, b = fx - i, fy - j
        i, j = min(max(i, 0), nx - 2), min(max(j, 0), ny - 2)
        return g[i, j] * (1 - a) * (1 - b) + g[i + 1, j] * a * (1 - b) + g[i, j + 1] * (1 - a) * b + \
            g[i + 1, j + 1] * a * b
    return at


def graves(site, rng, stats):
    """Могилы рядами: ряд — линия вдоль ROW_AZ, могилы поперёк; пропуски по полю заполненности."""
    ar = math.radians(ROW_AZ)
    r_hat = np.array([math.cos(ar), math.sin(ar)])              # вдоль ряда (на север-северо-запад)
    c_hat = np.array([math.cos(ar + math.pi / 2), math.sin(ar + math.pi / 2)])   # поперёк (на восток)
    P = np.array(site.poly)
    s_all, c_all = P @ r_hat, P @ c_hat
    xs, ys = P[:, 0], P[:, 1]
    fill = noise_field(rng, xs.min() - 20, ys.min() - 20, xs.max() + 20, ys.max() + 20, NOISE_CELL_M)
    church = np.array(site.church)
    out = []
    names = list(WEIGHTS["near"])
    c = c_all.min() + BORDER_GAP_M + 1.5
    row = 0
    while c < c_all.max():
        cc = c + rng.uniform(-ROW_JITTER_M, ROW_JITTER_M)
        s = s_all.min() + rng.uniform(0.0, 2.0)
        while s < s_all.max():
            base = cc * c_hat + s * r_hat
            near = (np.hypot(*(base - church)) < NEAR_CHURCH_M or
                    seg_dist(base[None], site.main_alley)[0] < NEAR_ALLEY_M)
            w = WEIGHTS["near" if near else "far"]
            kind = names[rng.choice(len(names), p=np.array([w[n] for n in names]) / sum(w.values()))]
            k = KINDS[kind]
            gap = rng.uniform(*GAP_M)
            if (s % AISLE_EVERY_M) < 2 * AISLE_HALF_M:                   # поперечный проход
                s += 2 * AISLE_HALF_M
                continue
            p_fill = (FILL_NEAR if near else FILL_FAR) * min(1.0, 0.4 + 0.9 * fill(*base))
            if rng.random() > p_fill:
                stats["vacant"] = stats.get("vacant", 0) + 1
                s += k["w"] + gap
                continue
            mid = base + (k["w"] / 2) * r_hat
            yaw = ROW_AZ + 90.0 + rng.uniform(-YAW_JITTER, YAW_JITTER)
            t = math.radians(yaw)
            e_l = np.array([math.cos(t), math.sin(t)]) * k["l"] / 2        # вдоль могилы
            e_w = np.array([-math.sin(t), math.cos(t)]) * k["w"] / 2       # поперёк
            pts = np.array([mid, mid + e_l + e_w, mid + e_l - e_w, mid - e_l + e_w, mid - e_l - e_w])
            why = site.free(pts, TRUNK_GAP_M)
            if why:
                stats[why] = stats.get(why, 0) + 1
                s += 0.6
                continue
            out.append({"kind": kind, "x": round(float(mid[0]), 2), "y": round(float(mid[1]), 2),
                        "yaw_deg": round(yaw, 1), "source": "rule", "row": row})
            s += k["w"] + gap
        c += ROW_PITCH_M
        row += 1
    return out


def wall_points(site):
    """Звенья ограды по линиям OSM: куски не длиннее WALL_SEG_M, scale_x — длина куска / WALL_SEG_M; только в
    Landscape (середина звена дальше EDGE_GAP_M от края)."""
    out = []
    for i, line in zip(WALL_WAYS, site.walls):
        for a, b in zip(line, line[1:]):
            L = math.dist(a, b)
            n = max(1, math.ceil(L / WALL_SEG_M - 1e-6))
            yaw = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            for k in range(n):
                t = (k + 0.5) / n
                x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                if max(abs(x), abs(y)) > HALF - EDGE_GAP_M:
                    continue
                if site.gate and Path(site.gate).contains_point((x, y)):    # в корпусах ворот стены нет
                    continue
                out.append({"kind": "wall", "x": round(x, 2), "y": round(y, 2), "yaw_deg": round(yaw, 1),
                            "scale_x": round(L / n / WALL_SEG_M + 0.01, 3), "source": "osm", "way": i})
    return out


def preview(site, pts, path):
    fig, ax = plt.subplots(figsize=(9, 13), dpi=110)
    P = np.array(site.ring)
    ax.plot(P[:, 1], P[:, 0], color="#c5221f", lw=1.2, label="кладбище (OSM 99751207)")
    ax.axvline(-HALF, color="#d01884", lw=1.0, ls="--", label="край Landscape")
    for line, w in site.alleys:
        L = np.array(line)
        ax.plot(L[:, 1], L[:, 0], color="#dadce0", lw=w * 2 * 2.2, solid_capstyle="round", zorder=1)
    for ring, _ in site.buildings:
        R = np.array(ring + [ring[0]])
        ax.fill(R[:, 1], R[:, 0], color="#bdc1c6", zorder=2)
    for c, r in site.chapels:
        ax.add_patch(plt.Circle((c[1], c[0]), r - CHAPEL_GAP_M, color="#bdc1c6", zorder=2))
    if len(site.trees):
        ax.scatter(site.trees[:, 1], site.trees[:, 0], s=14, facecolors="none", edgecolors="#188038", lw=0.7,
                   zorder=3, label="стволы (build/trees)")
    for q in pts:
        if q["kind"] == "wall":
            t = math.radians(q["yaw_deg"])
            h = 1.5 * q["scale_x"]
            ax.plot([q["y"] - h * math.sin(t), q["y"] + h * math.sin(t)],
                    [q["x"] - h * math.cos(t), q["x"] + h * math.cos(t)], color="#3c4043", lw=2.0, zorder=4)
            continue
        k = KINDS[q["kind"]]
        t = math.radians(q["yaw_deg"])
        el = np.array([math.cos(t), math.sin(t)]) * k["l"] / 2
        ew = np.array([-math.sin(t), math.cos(t)]) * k["w"] / 2
        c = np.array([q["x"], q["y"]])
        R = np.array([c + el + ew, c + el - ew, c - el - ew, c - el + ew])
        ax.fill(R[:, 1], R[:, 0], color=COLORS[q["kind"]], lw=0, zorder=5)
    for n, col in COLORS.items():
        ax.fill([], [], color=col, label=f"{n}: {sum(q['kind'] == n for q in pts)}")
    ax.set_aspect("equal")
    ax.set_xlabel("y, м (восток)")
    ax.set_ylabel("x, м (север)")
    ax.set_title("Мироносицкое кладбище: могилы и ограда (cemetery_points.py)")
    ax.legend(loc="lower right", fontsize=7)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rng = np.random.default_rng(SEED)
    site = Site()
    stats = {}
    pts = graves(site, rng, stats) + wall_points(site)
    counts = {}
    for q in pts:
        counts[q["kind"]] = counts.get(q["kind"], 0) + 1
    head = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "script": "scripts/cemetery_points.py",
        "seed": SEED,
        "osm": os.path.basename(geo.latest("krom_2*.json")),
        "trees": os.path.relpath(TREES, geo.REPO).replace("\\", "/"),
        "axes": "x — север, y — восток, м от центра Троицкого собора; z нет — трасса в редакторе",
        "yaw": "градусы, поворот +X модели к +Y (как yaw в UE): у могил +X — на восток, к памятнику",
        "kinds": KINDS,
        "rules": {"row_az_deg": ROW_AZ, "row_pitch_m": ROW_PITCH_M, "gap_m": GAP_M, "aisle_every_m": AISLE_EVERY_M,
                  "fill_near": FILL_NEAR, "fill_far": FILL_FAR, "noise_cell_m": NOISE_CELL_M, "weights": WEIGHTS,
                  "hypothesis": True},
        "rejected": dict(sorted(stats.items())),
        "trees_in_cemetery": int(len(site.trees)),
        "counts": dict(sorted(counts.items())),
        "total": len(pts),
    }
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        text = json.dumps(head, ensure_ascii=False, indent=2)
        f.write(text[:-2] + ',\n  "points": [\n')
        f.write(",\n".join("    " + json.dumps(q, ensure_ascii=False) for q in pts))
        f.write("\n  ]\n}\n")
    preview(site, pts, OUT_PNG)
    print(f"[cemetery_points] деревьев в контуре {len(site.trees)}, круглых исключений (часовня, руины) {len(site.chapels)}")
    for k, n in sorted(counts.items()):
        print(f"[cemetery_points] {k:12s} {n:5d}")
    print(f"[cemetery_points] отказы {head['rejected']}")
    print(f"[cemetery_points] всего {len(pts)} → {OUT_JSON}, {OUT_PNG}")


if __name__ == "__main__":
    main()
