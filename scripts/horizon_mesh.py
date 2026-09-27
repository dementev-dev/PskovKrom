"""horizon_mesh.py — кольцо горизонта вокруг Landscape (D-022, D-023): сетка земли, вода и маска покрытия.

Не для редактора: запускается из .venv (numpy, scipy, rasterio, matplotlib, pillow):

    .venv\\Scripts\\python scripts/horizon_mesh.py

Что делает:
  1. Кропы в refs/ (если их нет — скачивает): FABDEM, тайл N57E028 (S-18) → refs/dem/fabdem_horizon.tif;
     ESA WorldCover 2021, тайл N57E027 (S-31) → refs/landcover/worldcover_horizon.tif.
  2. Земля — круг радиусом R_M без квадрата Landscape. Точки гуще у Landscape и реже к краю (BANDS),
     треугольники — Delaunay. Упрощение на экране делает Nanite, редкая сетка вдали держит ассет небольшим.
  3. Высоты — FABDEM. Суша по DEM ниже уреза поднимается на LAND_RIM_M над ним, вода DEM (< 28,9 м) остаётся
     под плоскостью воды. Под край Landscape кольцо заходит на OVERLAP_M и лежит там чуть ниже него; снаружи
     на BLEND_M переходит от края heightmap к FABDEM. Кривизна Земли: z −= r²/2R, R — радиус планеты
     SkyAtmosphere; у края Landscape её нет, на BLEND_M она нарастает.
  4. Вода — отдельная сетка на урезе с той же кривизной, от края Landscape до края круга.
  5. Маска покрытия MASK_PX² на квадрат 2R_M × 2R_M, север вверху: R — лес и кустарник, G — город и голый
     грунт, B — вода и болото; остальное (луг, пашня) — поле. Значения — доли классов в текселе.

Выход (build/horizon, не в git):
  SM_Horizon_Ground.bin, SM_Horizon_Water.bin — меши для horizon_krom.py: int32 nv, nt; float32 вершины (м,
      оси UE), нормали, UV маски; int32 треугольники в порядке GeometryScript (нормаль = −(v1 − v0) × (v2 − v0));
  T_HorizonMask.png — маска; horizon.json — параметры; превью horizon_*.png.
"""
import datetime
import json
import os
import sys
import tempfile
import time
import urllib.request

import numpy as np
import rasterio
from rasterio.windows import Window
from scipy import ndimage
from scipy.spatial import Delaunay

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402
import terrain_krom as terrain  # noqa: E402

OUT_DIR = os.path.join(geo.REPO, "build", "horizon")
DEM_CROP = os.path.join(geo.REPO, "refs", "dem", "fabdem_horizon.tif")
WC_CROP = os.path.join(geo.REPO, "refs", "landcover", "worldcover_horizon.tif")
WC_URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
          "ESA_WorldCover_10m_2021_v200_N57E027_Map.tif")
HEIGHTMAP = terrain.OUT_PNG
HEIGHTMAP_META = terrain.OUT_JSON

R_M = 18000.0         # радиус круга (D-023)
CROP_M = 19000.0      # кропы — с запасом за край круга; тайл FABDEM кончается в 19,5 км к западу
HALF = terrain.HALF   # Landscape: от −HALF до +HALF м по X и Y
BANDS = ((2500.0, 24.0), (6000.0, 48.0), (R_M, 96.0))  # до какого max(|x|, |y|) — какой шаг сетки, м
EDGE_STEP_M = 8.0     # шаг точек по краю Landscape
OVERLAP_M = 48.0      # на столько кольцо заходит под Landscape
SINK_M = 0.5          # и лежит там ниже него на столько
BLEND_M = 400.0       # переход от края heightmap к FABDEM
LAND_RIM_M = 0.3      # суша по DEM — не ниже уреза + столько
PLANET_R_M = 6360e3   # SkyAtmosphereComponent.bottom_radius по умолчанию (6360 км)
WATER_STEP_M = 250.0  # шаг сетки воды
MASK_PX = 4096        # ≈8,8 м на тексель
MASK_GROUPS = {"R": (10, 20), "G": (50, 60), "B": (80, 90, 95)}  # классы WorldCover по каналам


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ---------- данные ----------

def crop_bounds():
    lat0, lon0 = geo.to_latlon(-CROP_M, -CROP_M)
    lat1, lon1 = geo.to_latlon(CROP_M, CROP_M)
    return lon0, lat0, lon1, lat1


def write_crop(src, dst, predictor):
    """Окно src по crop_bounds() → GeoTIFF dst со сжатием deflate."""
    w, s, e, n = crop_bounds()
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(src) as ds:
            c0, r0 = ~ds.transform * (w, n)
            c1, r1 = ~ds.transform * (e, s)
            c0, r0 = int(np.floor(c0)), int(np.floor(r0))
            win = Window(c0, r0, int(np.ceil(c1)) - c0, int(np.ceil(r1)) - r0)
            if c0 < 0 or r0 < 0 or c0 + win.width > ds.width or r0 + win.height > ds.height:
                raise RuntimeError(f"{src}: круг {CROP_M:.0f} м не помещается в тайл")
            a = ds.read(1, window=win)
            prof = {"driver": "GTiff", "dtype": a.dtype, "count": 1, "width": a.shape[1], "height": a.shape[0],
                    "crs": ds.crs, "transform": ds.window_transform(win), "nodata": ds.nodata,
                    "compress": "deflate", "predictor": predictor, "tiled": True, "blockxsize": 256, "blockysize": 256}
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with rasterio.open(dst, "w", **prof) as out:
        out.write(a, 1)


def ensure_crops():
    if not os.path.exists(DEM_CROP):
        tile = os.path.join(tempfile.gettempdir(), os.path.basename(terrain.DEM_TILE_URL))
        if not os.path.exists(tile):
            print(f"downloading {terrain.DEM_TILE_URL}")
            urllib.request.urlretrieve(terrain.DEM_TILE_URL, tile)
        write_crop(tile, DEM_CROP, predictor=3)
    if not os.path.exists(WC_CROP):
        print(f"reading {WC_URL}")
        write_crop("/vsicurl/" + WC_URL, WC_CROP, predictor=2)


def raster_sampler(path, order):
    """f(x, y) → значения растра в точках плана (м), интерполяция порядка order."""
    with rasterio.open(path) as ds:
        a = ds.read(1).astype(np.float32)
        t = ds.transform

    def sample(x, y):
        lat, lon = geo.to_latlon(x, y)
        col, row = ~t * (lon, lat)
        return ndimage.map_coordinates(a, [row - 0.5, col - 0.5], order=order, mode="nearest")
    return sample


def landscape_sampler():
    """f(x, y) → высота Landscape (м, Z) по heightmap, точки за краем прижимаются к краю."""
    from PIL import Image
    hm = np.asarray(Image.open(HEIGHTMAP), dtype=np.float64)  # [Y + HALF, X + HALF]
    z = (hm - 32768) * terrain.Z_PER_UNIT_M

    def sample(x, y):
        xc, yc = np.clip(x, -HALF, HALF), np.clip(y, -HALF, HALF)
        return ndimage.map_coordinates(z, [yc + HALF, xc + HALF], order=1, mode="nearest")
    return sample


# ---------- сетки ----------

def grid_points(step, lo, hi, r_max):
    """Узлы квадратной сетки с шагом step, у которых lo ≤ max(|x|, |y|) < hi и r < r_max."""
    n = int(min(hi, r_max) // step) + 1
    v = np.arange(-n, n + 1) * step
    x, y = (a.ravel() for a in np.meshgrid(v, v, indexing="ij"))
    cheb = np.maximum(abs(x), abs(y))
    m = (cheb >= lo) & (cheb < hi) & (np.hypot(x, y) < r_max)
    return x[m], y[m]


def square_points(half, step):
    """Точки по контуру квадрата ±half с шагом step, углы включены."""
    s = np.arange(-half, half, step)
    x = np.concatenate([s, np.full_like(s, half), -s, np.full_like(s, -half)])
    y = np.concatenate([np.full_like(s, -half), s, np.full_like(s, half), -s])
    return x, y


def circle_points(r, step):
    a = np.linspace(0, 2 * np.pi, int(np.ceil(2 * np.pi * r / step)), endpoint=False)
    return r * np.cos(a), r * np.sin(a)


def triangulate(x, y, hole):
    """Delaunay по точкам; треугольники с центром внутри квадрата ±hole выбрасываются.
    Порядок вершин — как в GeometryScript: у смотрящей вверх грани (v1 − v0) × (v2 − v0) смотрит вниз."""
    tri = Delaunay(np.column_stack([x, y])).simplices
    cx, cy = x[tri].mean(1), y[tri].mean(1)
    tri = tri[np.maximum(abs(cx), abs(cy)) >= hole]
    x0, y0 = x[tri[:, 0]], y[tri[:, 0]]
    cz = (x[tri[:, 1]] - x0) * (y[tri[:, 2]] - y0) - (y[tri[:, 1]] - y0) * (x[tri[:, 2]] - x0)
    tri[cz > 0] = tri[cz > 0][:, [0, 2, 1]]
    return tri.astype(np.int32)


def vertex_normals(p, tri):
    """Нормали вершин — сумма нормалей граней (с весом площади), грань = −(v1 − v0) × (v2 − v0)."""
    a, b, c = p[tri[:, 0]], p[tri[:, 1]], p[tri[:, 2]]
    fn = -np.cross(b - a, c - a)
    n = np.zeros_like(p)
    for k in range(3):
        np.add.at(n, tri[:, k], fn)
    return n / np.linalg.norm(n, axis=1, keepdims=True)


def curvature(x, y):
    """Опускание от кривизны Земли, м; у края Landscape — 0, на BLEND_M нарастает до полного."""
    d_out = np.maximum(abs(x), abs(y)) - HALF
    return (x * x + y * y) / (2 * PLANET_R_M) * smoothstep(d_out / BLEND_M)


def mask_uv(x, y):
    return np.column_stack([(y + R_M) / (2 * R_M), (R_M - x) / (2 * R_M)])


def build_ground(meta):
    xs, ys = [], []
    lo = HALF - OVERLAP_M
    for hi, step in BANDS:
        x, y = grid_points(step, lo, hi if hi < R_M else np.inf, R_M - step / 2)
        keep = abs(np.maximum(abs(x), abs(y)) - HALF) >= EDGE_STEP_M / 2  # край Landscape — своими точками
        xs.append(x[keep])
        ys.append(y[keep])
        lo = hi
    for x, y in (square_points(HALF, EDGE_STEP_M), circle_points(R_M, BANDS[-1][1])):
        xs.append(x)
        ys.append(y)
    x, y = np.concatenate(xs), np.concatenate(ys)
    tri = triangulate(x, y, HALF - OVERLAP_M)

    z0 = meta["z0_abs_m"]
    water_abs = meta["water_level_abs_m"]
    dem = raster_sampler(DEM_CROP, order=3)(x, y)
    dem = np.where(dem >= terrain.DEM_WATER_BELOW, np.maximum(dem, water_abs + LAND_RIM_M), dem)
    d_out = np.maximum(abs(x), abs(y)) - HALF
    t = smoothstep(d_out / BLEND_M)
    sink = SINK_M * smoothstep(-d_out / OVERLAP_M)
    z = (1 - t) * landscape_sampler()(x, y) + t * (dem - z0) - sink - curvature(x, y)
    p = np.column_stack([x, y, z])
    return p, tri, dem


def build_water(meta):
    step = WATER_STEP_M
    gx, gy = grid_points(step, HALF + step / 2, np.inf, R_M - step / 2)
    sx, sy = square_points(HALF, 24.0)
    cx, cy = circle_points(R_M, step)
    x, y = np.concatenate([gx, sx, cx]), np.concatenate([gy, sy, cy])
    tri = triangulate(x, y, HALF)
    z = meta["water_level_z_m"] - curvature(x, y)
    return np.column_stack([x, y, z]), tri


def write_mesh(path, p, tri):
    nrm = vertex_normals(p, tri)
    uv = mask_uv(p[:, 0], p[:, 1])
    with open(path, "wb") as f:
        np.array([len(p), len(tri)], "<i4").tofile(f)
        for a in (p, nrm, uv):
            a.astype("<f4").tofile(f)
        tri.astype("<i4").tofile(f)


# ---------- маска ----------

def build_mask():
    """Доли групп классов WorldCover в текселях маски: строка r → x = R − (r + ½)·s, столбец c → y = −R + (c + ½)·s.
    Сетка WorldCover — широта/долгота, а широта зависит только от x, долгота — только от y: пересчёт раздельный."""
    with rasterio.open(WC_CROP) as ds:
        wc = ds.read(1)
        t = ds.transform
    s = 2 * R_M / MASK_PX
    xs = R_M - (np.arange(MASK_PX) + 0.5) * s
    ys = -R_M + (np.arange(MASK_PX) + 0.5) * s
    lat, _ = geo.to_latlon(xs, 0.0)
    _, lon = geo.to_latlon(0.0, ys)
    rows = (lat - t.f) / t.e - 0.5
    cols = (lon - t.c) / t.a - 0.5
    # тексель ≈ 8,8 м, пиксель WorldCover ≈ 9,3 м по широте и 4,9 м по долготе: по долготе усредняем по два
    r0 = np.clip(np.floor(rows).astype(int), 0, wc.shape[0] - 2)
    fr = np.clip(rows - r0, 0, 1)[:, None]
    c0 = np.clip(np.floor(cols).astype(int), 0, wc.shape[1] - 2)
    fc = np.clip(cols - c0, 0, 1)[None, :]
    out = np.zeros((MASK_PX, MASK_PX, 3), np.uint8)
    for k, classes in enumerate(MASK_GROUPS.values()):
        layer = ndimage.uniform_filter1d(np.isin(wc, classes).astype(np.float32), 2, axis=1)
        a = layer[r0] * (1 - fr) + layer[r0 + 1] * fr
        a = a[:, c0] * (1 - fc) + a[:, c0 + 1] * fc
        out[..., k] = np.rint(np.clip(a, 0, 1) * 255)
    return out


# ---------- превью ----------

def previews(ground, water_tri_count, mask, meta):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource

    p, tri = ground
    wl = meta["water_level_z_m"]
    # высоты без кривизны — на сетке 60 м
    s = 60.0
    v = np.arange(-R_M, R_M + s, s)
    gx, gy = np.meshgrid(v[::-1], v, indexing="ij")  # строки — x сверху вниз, столбцы — y
    dem = raster_sampler(DEM_CROP, order=1)(gx, gy) - meta["z0_abs_m"]
    shaded = LightSource(azdeg=315, altdeg=40).shade(dem, cmap=plt.get_cmap("terrain"), vert_exag=6,
                                                     blend_mode="soft", vmin=wl - 6, vmax=wl + 60)
    shaded[dem < wl, :3] = [0.15, 0.3, 0.6]
    shaded[np.hypot(gx, gy) > R_M, :3] = 1.0

    fig, axes = plt.subplots(1, 2, figsize=(20, 10), dpi=90)
    ext = (-R_M, R_M, -R_M, R_M)
    axes[0].imshow(shaded, extent=ext)
    axes[0].set_title(f"FABDEM, вода ниже уреза синим; сетка: {len(p)} вершин, {len(tri)} треугольников, "
                      f"вода {water_tri_count}")
    axes[1].imshow(mask, extent=ext)
    axes[1].set_title("маска: R — лес, G — город, B — вода и болото")
    for ax in axes:
        ax.plot([-HALF, HALF, HALF, -HALF, -HALF], [-HALF, -HALF, HALF, HALF, -HALF], "r-", lw=1)
        ax.set_xlabel("Y, м (восток)")
        ax.set_ylabel("X, м (север)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "horizon_top.png"))
    plt.close(fig)

    # стык с Landscape: угол и край, треугольники и высоты
    fig, axes = plt.subplots(1, 2, figsize=(20, 9), dpi=90)
    for ax, (cy, cx, w) in zip(axes, ((HALF, HALF, 300.0), (0.0, HALF, 3000.0))):
        m = (abs(p[tri, 1].mean(1) - cy) < w) & (abs(p[tri, 0].mean(1) - cx) < w)
        tp = ax.tripcolor(p[:, 1], p[:, 0], tri[m], p[:, 2], shading="gouraud", cmap="terrain")
        ax.triplot(p[:, 1], p[:, 0], tri[m], color="k", lw=0.2)
        ax.plot([-HALF, HALF, HALF], [HALF, HALF, -HALF], "r-", lw=1)
        ax.set_xlim(cy - w, cy + w)
        ax.set_ylim(cx - w, cx + w)
        ax.set_aspect("equal")
        fig.colorbar(tp, ax=ax, label="Z, м")
    axes[0].set_title("северо-восточный угол Landscape")
    axes[1].set_title("северный край Landscape")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "horizon_seam.png"))
    plt.close(fig)


def main():
    t0 = time.time()
    os.makedirs(OUT_DIR, exist_ok=True)
    ensure_crops()
    with open(HEIGHTMAP_META, encoding="utf-8") as f:
        meta = json.load(f)
    p, tri, dem = build_ground(meta)
    wp, wtri = build_water(meta)
    write_mesh(os.path.join(OUT_DIR, "SM_Horizon_Ground.bin"), p, tri)
    write_mesh(os.path.join(OUT_DIR, "SM_Horizon_Water.bin"), wp, wtri)
    mask = build_mask()
    from PIL import Image
    Image.fromarray(mask).save(os.path.join(OUT_DIR, "T_HorizonMask.png"))
    info = {
        "generated": datetime.date.today().isoformat(),
        "script": "scripts/horizon_mesh.py",
        "radius_m": R_M,
        "planet_radius_m": PLANET_R_M,
        "water_level_z_m": meta["water_level_z_m"],
        "ground": {"vertices": len(p), "triangles": len(tri), "z_range_m": [round(float(p[:, 2].min()), 2),
                                                                             round(float(p[:, 2].max()), 2)]},
        "water": {"vertices": len(wp), "triangles": len(wtri)},
        "mask": {"px": MASK_PX, "size_m": 2 * R_M, "channels": {k: list(v) for k, v in MASK_GROUPS.items()}},
        "dem_below_water_share": round(float((dem < terrain.DEM_WATER_BELOW).mean()), 3),
        "sources": ["FABDEM V1-2 (Univ. of Bristol, from Copernicus GLO-30 © ESA), CC BY-NC-SA 4.0",
                    "ESA WorldCover 10 m 2021 v200 (© ESA WorldCover project 2021 / Contains modified Copernicus "
                    "Sentinel data (2021) processed by ESA WorldCover consortium), CC BY 4.0"],
    }
    with open(os.path.join(OUT_DIR, "horizon.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
        f.write("\n")
    previews((p, tri), len(wtri), mask, meta)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    print(f"{time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
