"""web_export.py — спайк веб-версии: лёгкая сцена для three.js из данных проекта, без редактора UE.

Запуск (.venv; для упрощения рельефа и сжатия — node/npx, @gltf-transform/cli npx скачает при первом запуске):
    .venv\\Scripts\\python scripts/web_export.py              # всё → build/web/
    .venv\\Scripts\\python scripts/web_export.py --no-npx     # без упрощения и сжатия: быстро, файлы крупнее
    cd build/web && python -m http.server 8080                  # → http://localhost:8080

Что выгружается (build/web, не в git; сырьё до сжатия — build/web_tools/raw):
  terrain.glb   — рельеф Landscape: heightmap_L_Krom (1 м), плитки 8 × 8 по 252 м, упрощение meshoptimizer
                  с допуском TERRAIN_ERROR и закреплёнными краями плиток (без щелей). Цвет — запечённая 2K-текстура:
                  маски покрытия (D-025, D-029) и палитра palette_krom.PALETTE в порядке landscape_krom.LAND_HLSL,
                  у края — вид кольца горизонта. Нормали — по heightmap, дно ниже уреза срезано (воду не видно насквозь).
  horizon.glb   — кольцо горизонта build/horizon (horizon_mesh.py), цвет вершин по маске WorldCover, упрощённое.
  water.glb     — вода на урезе (D-014) над Landscape и кольцом, пруд выше плотины (build/terrain/water_pools.json).
  bridges.glb   — мосты bridge_krom.BRIDGES (его геометрия без редактора: unreal — заглушка).
  walls.glb     — стены Крома, Довмонтова и Окольного города: wall_mesh.py по okolny_plan.scene_runs(), как
                  walls_krom.py, только земля — heightmap вместо трассы UE; фундаменты Довмонтова города (blockout).
  roads.glb     — дороги build/roads/roads.json: блоки 500 м, в блоке по примитиву на материал.
  city.glb      — застройка build/city/city.json, цвет домов — цвета вершин (linear, как в city_krom.py).
  models/*.glb  — модели из build/blender и build/finpark с цветами материалов из палитры (в выгрузке Blender
                  все материалы серые 0,8: цвет слота живёт в UE, в MPC_KromPalette).
  scene.json    — расстановка моделей (как heroes_krom, landmarks_krom, finpark_krom, furniture_krom,
                  cemetery_krom), точки обзора shot_krom.VIEWS, солнце light_krom «day», материалы по ключам.
  trees.json    — деревья build/trees/points.json: место, высота, крона, порода (в браузере — инстансы).
  textures/     — Poly Haven 1K для деталей вблизи (трава, плитняк, побелка, тёс).
  credits.json  — авторы и лицензии для страницы «Источники»: фото Commons по объектам (манифесты build/*_refs и
                  refs/photos/commons), текстуры Poly Haven из textures/.
  index.html, app.js, … — просмотрщик из web/ (все файлы, кроме *.md). build/web — готовый статический сайт:
                  пути относительные, можно выкладывать как есть (web/README.md — как выложить).

Оси. Проект: X — север, Y — восток, Z — вверх, метры (левая система UE, 1 uu = 1 см; GLB из Blender — в метрах).
three.js: Y — вверх, правая система. Перевод: (x, y, z)three = (X, Z, Y) — перестановка Y и Z. Это поворот, а не
зеркало (север × верх = восток), и ровно так Blender → glTF выгружает героев: точка здания (u, v, z) → glTF (u, z, v)
(bl_krom, проверено SM_AxisTest.glb). Азимут yaw (от севера к востоку, как yaw в UE) → rotation.y = −yaw.

Скрипт идемпотентен: build/web пересобирается целиком (кроме shots/), чужого не трогает.
"""
import argparse
import ast
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from urllib.parse import unquote

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import finpark_plan as fp  # noqa: E402
import krom_geo as geo  # noqa: E402
import krom_plan as plan  # noqa: E402
import landmarks_plan  # noqa: E402
import okolny_plan as okolny  # noqa: E402
import wall_mesh as wm  # noqa: E402

REPO = geo.REPO
OUT = os.path.join(REPO, "build", "web")
WORK = os.path.join(REPO, "build", "web_tools")
RAW = os.path.join(WORK, "raw")
WEB_SRC = os.path.join(REPO, "web")
DEM = os.path.join(REPO, "refs", "dem")
BLENDER = os.path.join(REPO, "build", "blender")
FINPARK = os.path.join(REPO, "build", "finpark")
HORIZON = os.path.join(REPO, "build", "horizon")
GLTF_CLI = "@gltf-transform/cli@4"

TILES = 8                  # плиток рельефа по стороне: 2016 м / 8 = 252 м
TERRAIN_ERROR = 0.0003     # допуск упрощения, доля радиуса плитки (≈178 м): ≈5 см
HORIZON_ERROR = 0.00002    # кольцо 18 км: ≈0,4 м (у края Landscape кольцо лежит чуть ниже него — не вылезти)
HORIZON_TEX_PX = 2048      # маска кольца 4096² на 36 км → цвет 2048² (≈18 м на тексель)
BED_BELOW_M = 1.5          # дно рек ниже уреза срезается на эту глубину: под водой его не видно
TEX_PX = 2048              # текстура цвета рельефа = разрешение масок покрытия
ROAD_BLOCK_M = 500.0       # дороги — блоками (отсечение по экрану и точность квантования 16 бит ≈ 8 мм)
DETAIL_PX = 1024           # текстуры деталей для браузера
RAW_KEEP_BYTES = 50e6      # сырьё крупнее (рельеф 1 м) после сжатия удаляется

# шероховатость и металл по ключу материала — как materials_krom.SPECS (metallic, rough)
SPEC = {"stone": (0.0, 0.85), "wall": (0.0, 0.9), "house": (0.0, 0.9), "wood": (0.0, 0.8), "green": (0.0, 0.45),
        "roof": (0.0, 0.5), "dark": (0.0, 0.4), "copper": (0.0, 0.6), "gold": (1.0, 0.25), "tin": (1.0, 0.45),
        "bronze": (0.6, 0.5), "glass": (0.0, 0.08), "ruin": (0.0, 0.9)}


# ---------- константы модулей редактора (они импортируют unreal — берём литералы из исходника) ----------

def module_const(filename, name):
    """Литерал name (dict, tuple, число) из scripts/<filename> без импорта модуля."""
    with open(os.path.join(HERE, filename), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            names = [getattr(e, "id", None) for e in t.elts] if isinstance(t, ast.Tuple) else [getattr(t, "id", None)]
            if name not in names:
                continue
            try:
                value = ast.literal_eval(node.value)
            except ValueError:   # dict(...) и т. п.: только встроенные конструкторы, без имён модуля
                value = eval(compile(ast.Expression(node.value), filename, "eval"),
                             {"__builtins__": {}, "dict": dict, "tuple": tuple, "list": list})
            return value[names.index(name)] if isinstance(t, ast.Tuple) else value
    raise KeyError(f"{filename}: нет {name}")


def view_labels():
    """Подписи точек обзора — комментарии строк shot_krom.VIEWS."""
    out = {}
    with open(os.path.join(HERE, "shot_krom.py"), encoding="utf-8") as f:
        for line in f:
            m = re.match(r'\s*"(\w+)": \(.*\),\s*#\s*(.+)$', line)
            if m:
                out[m.group(1)] = m.group(2).strip()
    return out


PALETTE = module_const("palette_krom.py", "PALETTE")
ROAD_MATS = module_const("roads_krom.py", "MATS")
MARK_WHITE = module_const("roads_krom.py", "MARK_WHITE")
CONCRETE_GAIN = module_const("roads_krom.py", "CONCRETE_GAIN")
LIGHT = module_const("light_krom.py", "PRESETS")["day"]
VIEWS = module_const("shot_krom.py", "VIEWS")
STAIR_SCALE = module_const("finpark_krom.py", "STAIR_SCALE")
SLOPE_FROM_NZ, SLOPE_RANGE = module_const("landscape_krom.py", "SLOPE_FROM_NZ"), \
    module_const("landscape_krom.py", "SLOPE_RANGE")
SLOPE_EARTH = module_const("landscape_krom.py", "SLOPE_EARTH")
SHORE_M = module_const("landscape_krom.py", "SHORE_M")
EDGE_FROM_M = module_const("landscape_krom.py", "EDGE_FROM_M")
EDGE_TO_M = module_const("landscape_krom.py", "EDGE_TO_M")


def color_of(key):
    """Цвет (linear) по ключу палитры: ключ krom_plan.COLORS (wall) или palette_krom.PALETTE (Field)."""
    if key in plan.COLORS:
        return tuple(plan.COLORS[key])
    if key.lower() in plan.COLORS:
        return tuple(plan.COLORS[key.lower()])
    return tuple(PALETTE[key])


def mat_spec(key):
    """Материал модели по имени слота: цвет, металл, шероховатость, свечение."""
    k = key.lower()
    extra = {"bark": ("Bark", 0.0, 0.9), "leaves": ("Foliage", 0.0, 0.8), "metal": ("Railing", 0.5, 0.5),
             "concrete": ("Concrete", 0.0, 0.85), "glow": ("LampGlobe", 0.0, 0.5)}
    if k in extra:
        pk, metal, rough = extra[k]
        spec = dict(rgb=color_of(pk), metal=metal, rough=rough)
        if k == "glow":
            spec["emissive"] = (1.0, 0.85, 0.6)   # тёплое стекло фонарей; в «дне» почти не заметно
        return spec
    if k in plan.COLORS:
        metal, rough = SPEC.get(k, (0.0, 0.8))
        return dict(rgb=color_of(k), metal=metal, rough=rough)
    print(f"[web_export] нет цвета для слота {key!r} — серый")
    return dict(rgb=(0.5, 0.5, 0.5), metal=0.0, rough=0.8)


# ---------- рельеф ----------

META = json.load(open(os.path.join(DEM, "heightmap_L_Krom.json"), encoding="utf-8"))
HALF = -META["landscape"]["location_uu"][0] / 100.0            # 1008 м
WATER_Z = META["water_level_z_m"]
Z_STEP = 1.0 / 128                                              # terrain_krom.Z_PER_UNIT_M
H = (np.asarray(Image.open(os.path.join(DEM, "heightmap_L_Krom.png")), dtype=np.float64) - 32768) * Z_STEP
N = H.shape[0]                                                  # 2017: строки — Y (восток), столбцы — X (север)


def ground(x, y):
    """Земля Landscape в точке плана (м), билинейно по heightmap; за краем — None (как промах трассы UE)."""
    c, r = x + HALF, y + HALF
    if not (0 <= c <= N - 1 and 0 <= r <= N - 1):
        return None
    c0, r0 = min(int(c), N - 2), min(int(r), N - 2)
    fc, fr = c - c0, r - r0
    return float(H[r0, c0] * (1 - fc) * (1 - fr) + H[r0, c0 + 1] * fc * (1 - fr)
                 + H[r0 + 1, c0] * (1 - fc) * fr + H[r0 + 1, c0 + 1] * fc * fr)


def to3(p):
    """Точки плана (X, Y, Z) → three.js (X, Z, Y)."""
    p = np.asarray(p, dtype=np.float64).reshape(-1, 3)
    return p[:, [0, 2, 1]]


def orient(pos, nrm, tri):
    """Обход треугольников против часовой стрелки (как ждёт three.js), сверка по нормалям вершин: грань, чья
    геометрическая нормаль смотрит против средней нормали вершин, переворачивается. → (tri, доля перевёрнутых)."""
    tri = np.array(tri, dtype=np.int64).reshape(-1, 3)
    if not len(tri):
        return tri, 0.0
    a, b, c = pos[tri[:, 0]], pos[tri[:, 1]], pos[tri[:, 2]]
    s = (np.cross(b - a, c - a) * (nrm[tri[:, 0]] + nrm[tri[:, 1]] + nrm[tri[:, 2]])).sum(1)
    flip = s < 0
    tri[flip] = tri[flip][:, [0, 2, 1]]
    return tri, float(flip.mean())


# ---------- GLB ----------

class Glb:
    """Минимальный писатель glTF 2.0 (.glb): меши из примитивов с материалами, одна картинка JPEG на файл."""

    def __init__(self):
        self.j = {"asset": {"version": "2.0", "generator": "PskovKrom scripts/web_export.py"}, "scene": 0,
                  "scenes": [{"nodes": []}], "nodes": [], "meshes": [], "materials": [], "accessors": [],
                  "bufferViews": [], "buffers": [{"byteLength": 0}]}
        self.bin = bytearray()
        self.mats = {}

    def _view(self, data, target=None):
        while len(self.bin) % 4:
            self.bin.append(0)
        v = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)}
        if target:
            v["target"] = target
        self.bin += data
        self.j["bufferViews"].append(v)
        return len(self.j["bufferViews"]) - 1

    def _acc(self, arr, index=False):
        if index:
            a = np.ascontiguousarray(arr, dtype=np.uint32).reshape(-1)
            acc = {"bufferView": self._view(a.tobytes(), 34963), "componentType": 5125, "count": int(a.size),
                   "type": "SCALAR"}
        else:
            a = np.ascontiguousarray(arr, dtype=np.float32)
            acc = {"bufferView": self._view(a.tobytes(), 34962), "componentType": 5126, "count": int(a.shape[0]),
                   "type": {2: "VEC2", 3: "VEC3", 4: "VEC4"}[a.shape[1]],
                   "min": [float(v) for v in a.min(0)], "max": [float(v) for v in a.max(0)]}
        self.j["accessors"].append(acc)
        return len(self.j["accessors"]) - 1

    def texture(self, jpeg_bytes):
        j = self.j
        j.setdefault("images", []).append({"bufferView": self._view(jpeg_bytes), "mimeType": "image/jpeg"})
        j.setdefault("samplers", [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}])
        j.setdefault("textures", []).append({"source": len(j["images"]) - 1, "sampler": 0})
        return len(j["textures"]) - 1

    def material(self, name, rgb=(1, 1, 1), metal=0.0, rough=0.9, emissive=None, texture=None, double=False):
        if name in self.mats:
            return self.mats[name]
        pbr = {"baseColorFactor": [float(c) for c in rgb] + [1.0], "metallicFactor": metal, "roughnessFactor": rough}
        if texture is not None:
            pbr["baseColorTexture"] = {"index": texture}
        m = {"name": name, "pbrMetallicRoughness": pbr}
        if emissive:
            m["emissiveFactor"] = [float(c) for c in emissive]
        if double:
            m["doubleSided"] = True
        self.j["materials"].append(m)
        self.mats[name] = len(self.j["materials"]) - 1
        return self.mats[name]

    def mesh(self, name, prims):
        """prims: [dict(pos, nrm, idx, mat[, col][, uv])] в осях three.js; узел — в корне сцены."""
        out = []
        for p in prims:
            if not len(p["idx"]):
                continue
            attrs = {"POSITION": self._acc(p["pos"]), "NORMAL": self._acc(p["nrm"])}
            if p.get("col") is not None:
                attrs["COLOR_0"] = self._acc(p["col"])
            if p.get("uv") is not None:
                attrs["TEXCOORD_0"] = self._acc(p["uv"])
            out.append({"attributes": attrs, "indices": self._acc(p["idx"], index=True), "material": p["mat"]})
        if not out:
            return
        self.j["meshes"].append({"name": name, "primitives": out})
        self.j["nodes"].append({"name": name, "mesh": len(self.j["meshes"]) - 1})
        self.j["scenes"][0]["nodes"].append(len(self.j["nodes"]) - 1)

    def save(self, path):
        self.j["buffers"][0]["byteLength"] = len(self.bin)
        write_glb(path, self.j, bytes(self.bin))
        return path


def write_glb(path, j, binary):
    js = json.dumps(j, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    binary = binary + b"\0" * (-len(binary) % 4)
    total = 12 + 8 + len(js) + 8 + len(binary)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(binary), 0x004E4942) + binary)


def read_glb(path):
    with open(path, "rb") as f:
        b = f.read()
    jl = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + jl])
    o = 20 + jl
    bl = struct.unpack("<I", b[o:o + 4])[0]
    return j, b[o + 8:o + 8 + bl]


# ---------- рельеф: текстура и плитки ----------

def srgb8(c):
    c = np.clip(c, 0.0, 1.0)
    s = np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)
    return np.rint(s * 255).astype(np.uint8)


def value_noise(n, cell, seed):
    """Плавный шум n × n с ячейкой cell пикселей, среднее 0, размах ≈ ±1."""
    rng = np.random.default_rng(seed)
    k = n // cell + 2
    g = rng.uniform(-1, 1, (k, k)).astype(np.float32)
    img = Image.fromarray(g, mode="F").resize((k * cell, k * cell), Image.BICUBIC)
    return np.asarray(img)[:n, :n]


def terrain_color():
    """2K-текстура цвета рельефа (linear) в раскладке масок: строки — Y, столбцы — X. Порядок смешивания — как
    landscape_krom.LAND_HLSL: трава → грунт (маска, откосы, полоса у уреза) → отсев, берег, наброска, мощение,
    асфальт, дерево, застройка; от EDGE_FROM_M к EDGE_TO_M — вид кольца горизонта (маска WorldCover)."""
    n = TEX_PX
    m1 = np.asarray(Image.open(os.path.join(DEM, "ground_mask_L_Krom.png")), dtype=np.float32) / 255
    m2 = np.asarray(Image.open(os.path.join(DEM, "ground_mask2_L_Krom.png")), dtype=np.float32) / 255
    # высота и уклон в центрах текселей
    hm = np.asarray(Image.fromarray(H.astype(np.float32), mode="F").resize((n, n), Image.BILINEAR))
    gy, gx = np.gradient(H)
    nz = 1 / np.sqrt(1 + gx ** 2 + gy ** 2)
    nz = np.asarray(Image.fromarray(nz.astype(np.float32), mode="F").resize((n, n), Image.BILINEAR))
    # трава: крупные пятна и мелкая рябь вместо текстуры Grass (в браузере мелочь добавляет детальная текстура)
    grass = 1 + 0.18 * value_noise(n, 48, 1) + 0.10 * value_noise(n, 12, 2)
    c = np.array(PALETTE["Field"], np.float32) * grass[..., None]

    def mix(c, key, a, var=0.08, seed=3):
        col = np.array(color_of(key), np.float32) * (1 + var * value_noise(n, 16, seed))[..., None]
        a = np.clip(a, 0, 1)[..., None]
        return c * (1 - a) + col * a

    slope = np.clip((SLOPE_FROM_NZ - nz) / SLOPE_RANGE, 0, 1)
    shore = np.clip((WATER_Z + SHORE_M - hm) / SHORE_M, 0, 1)
    c = mix(c, "Earth", m1[..., 0] + slope * SLOPE_EARTH + shore, seed=4)
    c = mix(c, "Gravel", m2[..., 0], seed=5)
    c = mix(c, "Shore", m2[..., 1], seed=6)
    c = mix(c, "Riprap", m2[..., 2], seed=7)
    c = mix(c, "Paved", m1[..., 1], seed=8)
    c = mix(c, "Asphalt", m1[..., 2], seed=9)
    c = mix(c, "Wood", m2[..., 3], seed=10)
    c = mix(c, "Built", m1[..., 3], seed=11)
    # у края — вид кольца: та же маска WorldCover, что у horizon.glb
    hmask, R = horizon_mask()
    xs = (np.arange(n) + 0.5) / n * 2 * HALF - HALF      # столбец → X
    X, Y = np.meshgrid(xs, xs, indexing="xy")            # X по столбцам, Y по строкам
    ring = ring_color(hmask, (Y + R) / (2 * R), (R - X) / (2 * R))
    edge = np.clip((np.maximum(abs(X), abs(Y)) - EDGE_FROM_M) / (EDGE_TO_M - EDGE_FROM_M), 0, 1)
    edge = edge * edge * (3 - 2 * edge)
    c = c * (1 - edge[..., None]) + ring * edge[..., None]
    return c


def horizon_mask():
    meta = json.load(open(os.path.join(HORIZON, "horizon.json"), encoding="utf-8"))
    img = np.asarray(Image.open(os.path.join(HORIZON, "T_HorizonMask.png")).convert("RGB"), dtype=np.float32) / 255
    return img, meta["radius_m"]


def ring_color(mask, u, v):
    """Цвет кольца горизонта по маске (R — лес, G — город и голый грунт, B — вода), как ring в LAND_HLSL."""
    h, w = mask.shape[:2]
    col = np.clip((np.asarray(u) * w).astype(np.int64), 0, w - 1)
    row = np.clip((np.asarray(v) * h).astype(np.int64), 0, h - 1)
    m = mask[row, col]
    f = np.array(PALETTE["Field"], np.float32)
    return (f + (np.array(PALETTE["Forest"]) - f) * m[..., 0:1] + (np.array(PALETTE["Built"]) - f) * m[..., 1:2]
            + (np.array(PALETTE["Water"]) - f) * m[..., 2:3]).astype(np.float32)


def terrain_glb(path):
    t0 = time.time()
    color = terrain_color()
    img = Image.fromarray(srgb8(color), "RGB")
    img.save(os.path.join(WORK, "terrain_color.jpg"), quality=90)
    jpeg = open(os.path.join(WORK, "terrain_color.jpg"), "rb").read()
    g = Glb()
    mat = g.material("terrain", rgb=(1, 1, 1), rough=0.95, texture=g.texture(jpeg))
    hc = np.maximum(H, WATER_Z - BED_BELOW_M)
    gy, gx = np.gradient(H)                       # шаг 1 м: d/dY по строкам, d/dX по столбцам
    nrm = np.stack([-gx, np.ones_like(gx), -gy], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    step = (N - 1) // TILES
    k = step + 1
    ii = np.arange(k * k).reshape(k, k)
    a, b, d, e = ii[:-1, :-1], ii[:-1, 1:], ii[1:, :-1], ii[1:, 1:]   # b — следующий столбец (X), d — строка (Y)
    tri = np.concatenate([np.stack([a, d, b], -1).reshape(-1, 3), np.stack([b, d, e], -1).reshape(-1, 3)])
    flipped = 0.0
    for ty in range(TILES):
        for tx in range(TILES):
            rr, cc = np.meshgrid(np.arange(ty * step, ty * step + k), np.arange(tx * step, tx * step + k),
                                 indexing="ij")
            X, Y = cc - HALF, rr - HALF
            pos = np.stack([X, hc[rr, cc], Y], -1).reshape(-1, 3)
            n3 = nrm[rr, cc].reshape(-1, 3)
            uv = np.stack([(X + HALF) / (2 * HALF), (Y + HALF) / (2 * HALF)], -1).reshape(-1, 2)
            t, f = orient(pos, n3, tri)
            flipped = max(flipped, f)
            g.mesh(f"terrain_{ty}_{tx}", [dict(pos=pos, nrm=n3, uv=uv, idx=t, mat=mat)])
    g.save(path)
    print(f"[web_export] terrain: {TILES}×{TILES} плиток по {step} м, {len(tri) * TILES * TILES} треугольников до "
          f"упрощения, перевёрнуто {flipped:.0%}, {time.time() - t0:.0f} с")


def read_horizon_bin(path):
    with open(path, "rb") as f:
        b = f.read()
    nv, nt = struct.unpack("<ii", b[:8])
    o = 8
    v = np.frombuffer(b, np.float32, nv * 3, o).reshape(-1, 3)
    o += nv * 12
    n = np.frombuffer(b, np.float32, nv * 3, o).reshape(-1, 3)
    o += nv * 12
    uv = np.frombuffer(b, np.float32, nv * 2, o).reshape(-1, 2)
    o += nv * 8
    t = np.frombuffer(b, np.int32, nt * 3, o).reshape(-1, 3)
    return v.astype(np.float64), n.astype(np.float64), uv, t


def horizon_glb(path):
    """Кольцо горизонта: сетка horizon_mesh.py, цвет — текстура из маски WorldCover (UV маски — из сетки), чтобы
    упрощение сетки не съедало пятна леса и города."""
    v, n, uv, t = read_horizon_bin(os.path.join(HORIZON, "SM_Horizon_Ground.bin"))
    mask, _ = horizon_mask()
    k = mask.shape[0]
    rows = (np.arange(k) + 0.5) / k
    U, V = np.meshgrid(rows, rows, indexing="xy")
    img = Image.fromarray(srgb8(ring_color(mask, U, V)), "RGB").resize((HORIZON_TEX_PX,) * 2, Image.LANCZOS)
    tex = os.path.join(WORK, "horizon_color.jpg")
    img.save(tex, quality=88)
    pos, nrm = to3(v), to3(n)
    t, f = orient(pos, nrm, t)
    g = Glb()
    mat = g.material("horizon", rough=1.0, texture=g.texture(open(tex, "rb").read()))
    g.mesh("horizon", [dict(pos=pos, nrm=nrm, uv=uv, idx=t, mat=mat)])
    g.save(path)
    print(f"[web_export] horizon: {len(v)} вершин, {len(t)} треугольников, перевёрнуто {f:.0%}")


# ---------- вода ----------

def ear_clip(ring):
    """Треугольники простого многоугольника (без самопересечений) отсечением ушей."""
    pts = [tuple(p) for p in ring]
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
               for i in range(len(pts)))
    idx = list(range(len(pts))) if area > 0 else list(range(len(pts)))[::-1]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def inside(p, a, b, c):
        return cross(a, b, p) >= 0 and cross(b, c, p) >= 0 and cross(c, a, p) >= 0

    out, guard = [], 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for i in range(len(idx)):
            ia, ib, ic = idx[i - 1], idx[i], idx[(i + 1) % len(idx)]
            a, b, c = pts[ia], pts[ib], pts[ic]
            if cross(a, b, c) <= 0:
                continue
            if any(inside(pts[j], a, b, c) for j in idx if j not in (ia, ib, ic)):
                continue
            out.append((ia, ib, ic))
            idx.pop(i)
            break
    out.append(tuple(idx))
    return pts, out


def water_glb(path):
    g = Glb()
    mat = g.material("water", rgb=PALETTE["Water"], rough=0.06)
    up = lambda k: np.tile([[0.0, 1.0, 0.0]], (k, 1))  # noqa: E731
    prims = []
    h = HALF + 2.0      # плоскость чуть заходит за край Landscape — стык с водой кольца
    quad = to3([(-h, -h, WATER_Z), (h, -h, WATER_Z), (h, h, WATER_Z), (-h, h, WATER_Z)])
    t, _ = orient(quad, up(4), [(0, 1, 2), (0, 2, 3)])
    prims.append(dict(pos=quad, nrm=up(4), idx=t, mat=mat))
    v, n, _, t = read_horizon_bin(os.path.join(HORIZON, "SM_Horizon_Water.bin"))
    pos, nrm = to3(v), to3(n)
    t, _ = orient(pos, nrm, t)
    prims.append(dict(pos=pos, nrm=nrm, idx=t, mat=mat))
    pools = json.load(open(os.path.join(REPO, "build", "terrain", "water_pools.json"), encoding="utf-8"))
    for p in pools.get("pools", []):
        pts, tris = ear_clip(p["ring"])
        pos = to3([(x, y, p["z_m"]) for x, y in pts])
        t, _ = orient(pos, up(len(pts)), tris)
        prims.append(dict(pos=pos, nrm=up(len(pts)), idx=t, mat=mat))
    for rb in pools.get("ribbons", []):
        P = np.array(rb["pts"], float)
        w = rb["width_m"] / 2
        vs = []
        for i in range(len(P)):
            d = P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]
            d /= np.linalg.norm(d)
            m = np.array([-d[1], d[0]])
            vs += [(*(P[i] + m * w), rb["z_m"]), (*(P[i] - m * w), rb["z_m"])]
        tris = [(2 * i, 2 * i + 1, 2 * i + 2) for i in range(len(P) - 1)] + \
               [(2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(len(P) - 1)]
        pos = to3(vs)
        t, _ = orient(pos, up(len(vs)), tris)
        prims.append(dict(pos=pos, nrm=up(len(vs)), idx=t, mat=mat))
    g.mesh("water", prims)
    g.save(path)


# ---------- стены и фундаменты ----------

def with_foot(z, foot):
    """Как walls_krom.with_foot: земля под внешней гранью — не выше foot (подпорная стена Окольного города)."""
    k = wm.WallGeom.PROBES
    return [(foot if v is None else min(v, foot)) if i % k == 1 else v for i, v in enumerate(z)]


class Parts:
    """Сетка по ключам материалов в осях плана: parts[key] = (вершины, нормали, треугольники)."""

    def __init__(self):
        self.parts = {}

    def add(self, key, v, n, t, col=None, uv=None):
        pv, pn, pt, pc, pu = self.parts.setdefault(key, ([], [], [], [], []))
        base = sum(len(a) for a in pv)
        pv.append(np.asarray(v, float).reshape(-1, 3))
        pn.append(np.asarray(n, float).reshape(-1, 3))
        pt.append(np.asarray(t, np.int64).reshape(-1, 3) + base)
        if col is not None:
            pc.append(np.asarray(col, float).reshape(-1, 3))
        if uv is not None:
            pu.append(np.asarray(uv, float).reshape(-1, 2))

    def prims(self, g, mat_of, lift=0.0):
        """Примитивы GLB по материалам и {ключ: доля перевёрнутых треугольников} (обход сверен по нормалям)."""
        out, worst = [], {}
        for key, (pv, pn, pt, pc, pu) in self.parts.items():
            v = np.concatenate(pv)
            v[:, 2] += lift
            pos, nrm = to3(v), to3(np.concatenate(pn))
            t, f = orient(pos, nrm, np.concatenate(pt))
            worst[key] = f
            out.append(dict(pos=pos, nrm=nrm, idx=t, mat=mat_of(g, key),
                            col=np.concatenate(pc) if pc else None,
                            uv=np.concatenate(pu) if len(pu) == len(pv) else None))
        return out, worst


def flip_note(flips):
    """Сводка разворота треугольников: у wall_mesh и дорог обход — как в GeometryScript, при перестановке осей
    он становится правильным сам; переворачиваются только коробки этого скрипта."""
    bad = {k: v for k, v in flips.items() if v > 0}
    return "обход верный" if not bad else "перевёрнуто: " + ", ".join(f"{k} {v:.0%}" for k, v in bad.items())


def spec_material(g, key):
    s = mat_spec(key)
    return g.material(key, s["rgb"], s["metal"], s["rough"], s.get("emissive"))


def box(parts, key, corners, zb, zt):
    """Коробка по четырём углам плана (x, y) от zb до zt: крышка и четыре стенки (дно не нужно). UV — «кубом»
    в метрах, как wall_mesh."""
    cx, cy = sum(p[0] for p in corners) / 4, sum(p[1] for p in corners) / 4
    parts.add(key, [(x, y, zt) for x, y in corners], [(0, 0, 1)] * 4, [(0, 1, 2), (0, 2, 3)],
              uv=[(x, -y) for x, y in corners])
    for i in range(4):
        (x0, y0), (x1, y1) = corners[i], corners[(i + 1) % 4]
        mx, my = (x0 + x1) / 2 - cx, (y0 + y1) / 2 - cy
        L = math.hypot(y1 - y0, x1 - x0)
        nx, ny = (y1 - y0) / L, -(x1 - x0) / L
        if nx * mx + ny * my < 0:
            nx, ny = -nx, -ny
        parts.add(key, [(x0, y0, zb), (x1, y1, zb), (x1, y1, zt), (x0, y0, zt)], [(nx, ny, 0)] * 4,
                  [(0, 1, 2), (0, 2, 3)], uv=[(0, -zb), (L, -zb), (L, -zt), (0, -zt)])


def walls_glb(path):
    t0 = time.time()
    runs, gates = okolny.scene_runs()
    parts, misses, length = Parts(), 0, 0.0

    def gz(x, y):
        nonlocal misses
        z = ground(x, y)
        misses += z is None
        return z

    for r in runs:
        geom = wm.WallGeom(r, gates.get(r.name, ()))
        level = gz(*r.level_at) if r.level_at else None
        z = [gz(*p) for p in geom.probes()]
        foot = okolny.foot_z(r)
        mesh = geom.build(z if foot is None else with_foot(z, foot), level)
        for key, (v, n, uv, t) in mesh.parts.items():
            parts.add(key, v, n, t, uv=uv)
        length += r.length
    # фундаменты Довмонтова города и прочие blockout-здания без героя: только коробки
    blocks = 0
    for b in plan.towers() + plan.buildings():
        if b.hero:
            continue
        base = ground(*b.ground_at)
        if base is None:
            continue
        for p in b.parts:
            if p.shape != "box":
                continue
            du, dv = p.size[0] / 2, p.size[1] / 2
            corners = [plan.to_world(b.origin, b.yaw, p.uv[0] + su * du, p.uv[1] + sv * dv)
                       for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            low = min(z for z in (ground(*c) for c in corners) if z is not None)
            zb = (low - 0.3) if p.z[0] <= 0 else base + p.z[0]
            box(parts, p.mat, corners, zb, base + p.z[1])
            blocks += 1
    g = Glb()
    prims, flips = parts.prims(g, spec_material)
    g.mesh("walls", prims)
    g.save(path)
    print(f"[web_export] walls: {len(runs)} участков, {length:.0f} м, коробок blockout {blocks}, мимо heightmap "
          f"{misses}, {flip_note(flips)}, {time.time() - t0:.0f} с")


# ---------- мосты ----------

BRIDGE_MATS = {"concrete": ("Concrete", 0.85, 0.0), "road": ("Asphalt", 0.8, 0.0), "metal": ("Railing", 0.45, 0.6),
               "screen": ("Screen", 0.35, 0.8), "walk": ("Walkway", 0.7, 0.0), "globe": ("LampGlobe", 0.3, 0.0)}
# как bridge_krom.materials(): слот → (цвет палитры, шероховатость, металл)


def load_editor_module(filename):
    """Модуль редактора без редактора — ради его чистых функций геометрии: unreal подменён заглушкой, вызов main()
    в конце файла отрезан. Сам файл не меняется."""
    from unittest import mock
    saved = sys.modules.get("unreal")
    sys.modules["unreal"] = mock.MagicMock(name="unreal")
    try:
        with open(os.path.join(HERE, filename), encoding="utf-8") as f:
            src = re.sub(r"\nmain\(\)\s*$", "\n", f.read())
        ns = {"__name__": f"web_export_{filename[:-3]}", "__file__": os.path.join(HERE, filename)}
        exec(compile(src, filename, "exec"), ns)
    finally:
        if saved is None:
            sys.modules.pop("unreal", None)
        else:
            sys.modules["unreal"] = saved
    return ns


def bridges_glb(path):
    """Мосты bridge_krom.BRIDGES: ось, отметки настила и геометрия — как bridge_krom.main(), земля — heightmap."""
    bk = load_editor_module("bridge_krom.py")
    elements = {e["id"]: e for e in geo.load_elements(geo.latest("krom_2*.json"))}
    parts, names = Parts(), []
    for name, b in bk["BRIDGES"].items():
        a, e = b["ends"] if "ends" in b else bk["axis"](b, elements)
        za, ze = ground(*a), ground(*e)
        if za is None or ze is None:
            print(f"[web_export] мост {name}: конец за краем heightmap — пропущен")
            continue
        low = WATER_Z + b["deck_min"]
        if "deck_z" in b:
            fr = bk["Frame"](a, e, b["deck_z"], b["deck_z"], b["camber"])
        else:
            fr = bk["Frame"](a, e, max(za + b["deck_above"], low), max(ze + b["deck_above"], low), b["camber"])
        fr.g0, fr.g1 = za + b["deck_above"], ze + b["deck_above"]
        mesh = bk["build_mesh"](fr, b, WATER_Z)
        for key, (v, n, uv, t) in mesh.parts.items():
            parts.add(key, v, n, t, uv=uv)
        names.append(name)

    def mat(g, key):
        pal, rough, metal = BRIDGE_MATS.get(key, ("Concrete", 0.85, 0.0))
        return g.material(f"bridge_{key}", color_of(pal), metal, rough, (1.0, 0.9, 0.7) if key == "globe" else None)

    g = Glb()
    prims, flips = parts.prims(g, mat)
    g.mesh("bridges", prims)
    g.save(path)
    print(f"[web_export] bridges: {', '.join(names)}; {sum(len(p['idx']) for p in prims)} треугольников, "
          f"{flip_note(flips)}")


# ---------- дороги и город ----------

def roads_glb(path):
    t0 = time.time()
    roads = json.load(open(os.path.join(REPO, "build", "roads", "roads.json"), encoding="utf-8"))
    blocks = {}
    for cell in roads["cells"]:
        ox, oy = cell["origin"]
        key = (math.floor(ox / ROAD_BLOCK_M), math.floor(oy / ROAD_BLOCK_M))
        parts = blocks.setdefault(key, Parts())
        for slot, p in cell["parts"].items():
            if not p["t"]:
                continue
            v = np.asarray(p["v"], float) + (ox, oy, 0.0)
            parts.add(slot, v, p["n"], p["t"])

    def road_mat(g, slot):
        _tex, _tile, pal, _detail, _macro, _normal, rough = ROAD_MATS[slot]
        if slot == "marking":
            rgb = MARK_WHITE
        elif slot == "concrete":
            rgb = tuple(c * CONCRETE_GAIN for c in PALETTE[pal])
        else:
            rgb = color_of(pal)
        return g.material(f"road_{slot}", rgb, 0.0, rough)

    g, flips, tris = Glb(), {}, 0
    for (bx, by), parts in sorted(blocks.items()):
        prims, f = parts.prims(g, road_mat)
        flips.update({k: max(v, flips.get(k, 0.0)) for k, v in f.items()})
        tris += sum(len(p["idx"]) for p in prims)
        g.mesh(f"roads_{bx}_{by}", prims)
    g.save(path)
    print(f"[web_export] roads: {len(roads['cells'])} клеток → {len(blocks)} блоков, {tris} треугольников, "
          f"{flip_note(flips)}, {time.time() - t0:.0f} с")


def city_glb(path):
    city = json.load(open(os.path.join(REPO, "build", "city", "city.json"), encoding="utf-8"))
    parts = Parts()
    for cell in city["cells"]:
        ox, oy = cell["origin"]
        for key, p in cell["parts"].items():
            if p["t"]:
                parts.add(key, np.asarray(p["v"], float) + (ox, oy, 0.0), p["n"], p["t"], p["c"])
    rough = {"facade": 0.9, "roof": 0.7}
    g = Glb()
    prims, flips = parts.prims(g, lambda g, k: g.material(f"city_{k}", (1, 1, 1), 0.0, rough.get(k, 0.9)))
    g.mesh("city", prims)
    g.save(path)
    print(f"[web_export] city: {city['stats']['buildings']} домов, {sum(len(p['idx']) for p in prims)} "
          f"треугольников, {flip_note(flips)}")


# ---------- модели и расстановка ----------

def glb_source(name):
    for d in (BLENDER, FINPARK):
        p = os.path.join(d, f"{name}.glb")
        if os.path.exists(p):
            return p
    return None


def model_glb(name, path):
    """build/blender/<name>.glb → path с цветами материалов из палитры (по имени слота)."""
    j, binary = read_glb(glb_source(name))
    for m in j.get("materials", []):
        s = mat_spec(m["name"])
        m["pbrMetallicRoughness"] = {"baseColorFactor": [float(c) for c in s["rgb"]] + [1.0],
                                     "metallicFactor": s["metal"], "roughnessFactor": s["rough"]}
        if s.get("emissive"):
            m["emissiveFactor"] = list(s["emissive"])
    j["asset"]["generator"] = "PskovKrom scripts/web_export.py (" + j["asset"].get("generator", "") + ")"
    write_glb(path, j, binary)


def placements():
    """{имя модели: [(подпись, x, y, z, yaw°, sx, sy, sz)]} — места в плане, как ставят скрипты редактора."""
    out, skipped = {}, []

    def put(name, label, x, y, z, yaw, sx=1.0, sy=1.0, sz=1.0):
        if z is None:
            skipped.append(label)
            return
        if glb_source(name) is None:
            skipped.append(f"{label} (нет {name}.glb)")
            return
        out.setdefault(name, []).append((label, x, y, z, yaw, sx, sy, sz))

    heroes = [b for b in plan.towers() + plan.buildings() if b.hero]
    try:   # ПсковГУ — план в работе (не в git на момент спайка): есть выгрузка — ставим
        import pskovgu_plan
        seen = {b.hero for b in heroes}
        heroes += [b for b in pskovgu_plan.buildings() if b.hero and b.hero not in seen]
    except Exception as ex:  # noqa: BLE001
        print(f"[web_export] pskovgu_plan: {ex}")
    for b in heroes:            # heroes_krom: origin, yaw, земля в ground_at
        put(b.hero.rsplit("/", 1)[1], b.name, b.origin[0], b.origin[1], ground(*b.ground_at), b.yaw)
    for m in landmarks_plan.landmarks():   # landmarks_krom: земля в height_at + dz
        z = ground(*m.height_at)
        put(m.asset, m.name, m.xy[0], m.xy[1], None if z is None else z + m.dz, m.yaw)
    for p in fp.placements():   # finpark_krom.height()
        if not p["inside"]:
            continue
        mode, z, sz = p["z_mode"], None, 1.0
        if mode == "water":
            z = WATER_Z
        elif mode == "ground":
            z = ground(p["x"], p["y"])
        elif mode == "stairs":
            z0, z1 = ground(p["x"], p["y"]), ground(*p["end"])
            if z0 is not None and z1 is not None:
                baked, traced = p["rise"], z1 - z0
                s = traced / baked if abs(baked) > 0.2 and traced * baked > 0 else 1.0
                z, sz = z0, min(max(s, STAIR_SCALE[0]), STAIR_SCALE[1])
        elif mode == "deck":
            zs = [q for q in (ground(*e) for e in p["ends"]) if q is not None] or \
                 [q for q in (ground(p["x"], p["y"]),) if q is not None]
            if zs:
                above = fp.DECK_ABOVE_M if p["asset"] == "SM_FinPark_FlatBridge" else fp.HUMP_DECK_ABOVE_M
                z = max(zs) + above
        put(p["asset"], p["asset"], p["x"], p["y"], z, p["yaw_deg"], sz=sz)
    for src in ("furniture", "cemetery"):   # furniture_krom, cemetery_krom: вид → модель, земля в точке
        d = json.load(open(os.path.join(REPO, "build", src, "points.json"), encoding="utf-8"))
        for p in d["points"]:
            put(d["kinds"][p["kind"]]["asset"], p["kind"], p["x"], p["y"], ground(p["x"], p["y"]), p["yaw_deg"],
                sx=p.get("scale_x", 1.0))
    return out, skipped


def trees_json(path):
    d = json.load(open(os.path.join(REPO, "build", "trees", "points.json"), encoding="utf-8"))
    species = sorted({p.get("species_hint") or "maple" for p in d["points"]})
    kinds = sorted({p["kind"] for p in d["points"]})
    rows, skipped = [], 0
    for p in d["points"]:
        z = ground(p["x"], p["y"])
        if z is None:
            skipped += 1
            continue
        rows.append([round(p["x"], 1), round(z, 2), round(p["y"], 1), round(p["height_m"], 1),
                     round(p["crown_m"], 1), species.index(p.get("species_hint") or "maple"),
                     kinds.index(p["kind"]), p.get("yaw_deg", 0)])
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"source": "build/trees/points.json (trees_points.py)", "species": species, "kinds": kinds,
                   "fields": ["x", "y (земля)", "z", "высота", "крона", "порода", "вид", "yaw°"],
                   "foliage": PALETTE["Foliage"], "bark": PALETTE["Bark"], "points": rows},
                  f, ensure_ascii=False, separators=(",", ":"))
    print(f"[web_export] trees: {len(rows)} деревьев, за краем {skipped}")
    return len(rows)


def detail_textures():
    """Poly Haven 2K → 1K JPEG для деталей вблизи; плитка (м) — refs/textures/textures.json, как в materials_krom и
    landscape_krom. Среднее (linear) — по уменьшенной картинке: в браузере цвет материала = палитра / среднее."""
    info = json.load(open(os.path.join(REPO, "refs", "textures", "textures.json"), encoding="utf-8"))
    pick = {"grass": ("textures", "Grass"), "stone": ("buildings", "Stone"), "plaster": ("buildings", "Whitewash"),
            "planks": ("buildings", "Planks"), "cobble": ("roads", "Cobble"), "asphalt": ("roads", "Asphalt")}
    out = {}
    os.makedirs(os.path.join(OUT, "textures"), exist_ok=True)
    for key, (group, role) in pick.items():
        t = info.get(group, {}).get(role)
        src = t and os.path.join(REPO, "refs", "textures", "polyhaven", f"{t['asset']}_diff_2k.jpg")
        if not src or not os.path.exists(src):
            print(f"[web_export] нет текстуры {group}/{role}")
            continue
        img = Image.open(src).convert("RGB").resize((DETAIL_PX, DETAIL_PX), Image.LANCZOS)
        rel = f"textures/{key}.jpg"
        img.save(os.path.join(OUT, rel), quality=85)
        a = np.asarray(img, np.float32) / 255
        lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
        out[key] = dict(file=rel, tile_m=t["tile_m"], asset=t["asset"], name=t.get("name", t["asset"]),
                        authors=t.get("authors", []), license=t.get("license", ""),
                        mean=[round(float(v), 4) for v in lin.reshape(-1, 3).mean(0)])
    return out


# ---------- источники (страница «Источники и лицензии») ----------

# Фото Wikimedia Commons — только референсы (на сайте не показываются). Папка build/<ключ>_refs → объект;
# названия — как в docs/REFERENCES.md. «commons» — refs/photos/commons (S-25, в git).
PHOTO_OBJECTS = {   # ключ папки → (объект, запись в REFERENCES)
    "commons": ("Кром: стены, башни, двор", "S-25"),
    "yard": ("Двор Крома: Дом причта, Пороховые погреба, Консистория", "S-70"),
    "prikaz": ("Приказные палаты", "S-126"),
    "okolny": ("Стена Окольного города по Великой, Мстиславская башня", "S-74"),
    "mstislav": ("Мстиславская башня", "S-90"),
    "env": ("Окружение Крома: берега, тропы, набережные", "S-42"),
    "landmarks": ("Памятные знаки: кресты, меч Довмонта, «Россия начинается здесь»", "S-86…S-89"),
    "bridge": ("Ольгинский мост", "S-48"),
    "finpark": ("Финский парк, плотина, пешеходный мост", "S-80"),
    "chapels": ("Часовни", "S-60"),
    "paromenye": ("Церковь Успения с Пароменья и звонница", "S-54"),
    "kozmy": ("Церковь Козьмы и Дамиана с Примостья", "S-64"),
    "mironositsy": ("Церковь Жён-Мироносиц и Мироносицкое кладбище", "S-81"),
    "petrapavla": ("Церковь Петра и Павла с Буя", "S-91"),
    "varlaam": ("Церковь Варлаама Хутынского на Званице", "S-94"),
    "bogoyavlenie": ("Церковь Богоявления с Запсковья и звонница", "S-97"),
    "vasily": ("Церковь Василия на Горке", "S-100"),
    "ilya": ("Церковь Ильи Пророка с Мокрого Луга", "S-106"),
    "predtecha": ("Собор Иоанна Предтечи Ивановского монастыря", "S-109"),
    "mikhail": ("Церковь Михаила и Гавриила Архангелов с Городца", "S-115"),
    "usokha": ("Церковь Николы со Усохи", "S-120"),
    "pskovgu": ("Корпуса ПсковГУ", "S-130…S-134"),
    "lenin_square": ("Площадь Ленина", ""),
    "zapskovye": ("Запсковье: Советская набережная, ул. Леона Поземского", ""),
    "facade": ("Рядовая застройка: фасады образцов", ""),
}


def clean_author(a):
    """Автор из манифеста: у пары записей там обрывок HTML-ссылки Commons — берём имя участника из неё."""
    m = re.search(r"title=User:([^&\"]+)", a)
    if m:
        a = unquote(m.group(1)).replace("_", " ")
    a = re.sub(r"<[^>]*>?|</?$", "", a)
    return re.sub(r"\s+", " ", a).strip(" <")


def photo_credits():
    """Авторы и лицензии фото Commons по объектам: build/*_refs/manifest.json + refs/photos/commons/manifest.json.
    Форматы манифестов разные: {photos: [...]}, список, словарь «файл → запись». Берутся записи с автором и
    страницей на commons.wikimedia.org; копии (copy_of) и повторы страницы в объекте — пропускаются."""
    sources = [("commons", os.path.join(REPO, "refs", "photos", "commons", "manifest.json"))]
    bdir = os.path.join(REPO, "build")
    for fn in sorted(os.listdir(bdir)) if os.path.isdir(bdir) else []:
        if fn.endswith("_refs"):
            sources.append((fn[:-5], os.path.join(bdir, fn, "manifest.json")))
    groups, missing, warn = [], [], []
    for key, path in sources:
        if not os.path.exists(path):
            missing.append(key)
            continue
        j = json.load(open(path, encoding="utf-8"))
        if isinstance(j, list):
            items = j
        elif isinstance(j.get("photos"), list):
            items = j["photos"]
        else:
            items = [v for v in j.values() if isinstance(v, dict) and "author" in v]
        seen, by_author = set(), {}
        for p in items:
            page = p.get("page") or p.get("url") or ""
            if p.get("copy_of") or "commons.wikimedia.org" not in page or page in seen:
                continue
            if not p.get("author") or not p.get("license"):
                warn.append(f"{key}: без автора или лицензии — {page}")
                continue
            seen.add(page)
            a = by_author.setdefault(clean_author(p["author"]), {"n": 0, "licenses": []})
            a["n"] += 1
            if p["license"] not in a["licenses"]:
                a["licenses"].append(p["license"])
        if not seen:
            continue
        if key not in PHOTO_OBJECTS:
            warn.append(f"нет названия объекта для build/{key}_refs")
        label, ref = PHOTO_OBJECTS.get(key, (key, ""))
        authors = [dict(name=k, **v) for k, v in sorted(by_author.items(), key=lambda kv: (-kv[1]["n"], kv[0]))]
        groups.append(dict(key=key, object=label, ref=ref, photos=len(seen), authors=authors))
    order = list(PHOTO_OBJECTS)
    groups.sort(key=lambda g: order.index(g["key"]) if g["key"] in order else len(order))
    return groups, missing, warn


def credits_json(path, tex):
    """credits.json для страницы «Источники»: фото Commons по объектам и текстуры Poly Haven, что лежат в textures/.
    Постоянный текст (OSM, FABDEM, WorldCover, инструменты) — в web/index.html."""
    groups, missing, warn = photo_credits()
    textures, seen = [], set()
    for t in tex.values():
        if t["asset"] in seen:
            continue
        seen.add(t["asset"])
        textures.append(dict(name=t.get("name", t["asset"]), authors=t.get("authors", []), license=t.get("license", ""),
                             url=f"https://polyhaven.com/a/{t['asset']}"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dict(generated=time.strftime("%Y-%m-%d"), script="scripts/web_export.py",
                       photos_total=sum(g["photos"] for g in groups), photos=groups, textures=textures),
                  f, ensure_ascii=False, indent=1)
    print(f"[web_export] credits: фото {sum(g['photos'] for g in groups)} по {len(groups)} объектам, "
          f"текстур {len(textures)}; без манифеста: {', '.join(missing) or '—'}")
    for w in warn:
        print(f"[web_export]   ! {w}")


# ---------- сжатие ----------

def npx(*args):
    cmd = ["npx", "--yes", GLTF_CLI, *args]
    r = subprocess.run(cmd, cwd=WORK, shell=(os.name == "nt"), capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return r.stdout


def finish(raw, dst, use_npx, simplify=None, pos_bits=14, volume="mesh"):
    """Сырой GLB → build/web: упрощение (simplify — допуск) и сжатие meshopt; без npx — копия как есть."""
    if not use_npx:
        shutil.copyfile(raw, dst)
        return
    src = raw
    if simplify is not None:
        tmp = raw.replace(".glb", "_s.glb")
        npx("simplify", src, tmp, "--error", str(simplify), "--ratio", "0", "--lock-border", "true")
        src = tmp
    npx("meshopt", src, dst, "--level", "medium", "--quantize-position", str(pos_bits),
        "--quantization-volume", volume)
    if simplify is not None:   # сырой рельеф 1 м — ≈230 МБ: после сжатия не нужен
        os.remove(tmp)
        if os.path.getsize(raw) > RAW_KEEP_BYTES:
            os.remove(raw)


def glb_triangles(path):
    j, _ = read_glb(path)
    return sum(j["accessors"][p["indices"]]["count"] // 3 for m in j.get("meshes", []) for p in m["primitives"])


# ---------- сборка ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-npx", action="store_true", help="без упрощения и сжатия (gltf-transform)")
    ap.add_argument("--only", default="", help="через запятую: terrain,horizon,water,walls,bridges,roads,city,models,web")
    args = ap.parse_args()
    use_npx = not args.no_npx
    only = set(filter(None, args.only.split(",")))
    want = (lambda k: not only or k in only)
    t0 = time.time()
    os.makedirs(RAW, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    if not only:   # свои файлы пересобираются целиком; снимки shots/ остаются
        for fn in os.listdir(OUT):
            p = os.path.join(OUT, fn)
            if fn == "shots":
                continue
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)

    layers = [("terrain", terrain_glb, dict(simplify=TERRAIN_ERROR, pos_bits=16, volume="scene")),
              ("horizon", horizon_glb, dict(simplify=HORIZON_ERROR, pos_bits=16)),
              ("water", water_glb, dict(pos_bits=16)),
              ("walls", walls_glb, dict(pos_bits=16)),
              ("bridges", bridges_glb, dict(pos_bits=16)),
              ("roads", roads_glb, dict(pos_bits=16)),
              ("city", city_glb, dict(pos_bits=16))]
    for name, build, opts in layers:
        if not want(name):
            continue
        raw = os.path.join(RAW, f"{name}.glb")
        build(raw)
        finish(raw, os.path.join(OUT, f"{name}.glb"), use_npx, **opts)

    places, skipped = placements()
    models = []
    for name, items in sorted(places.items()):
        rel = f"models/{name}.glb"
        if want("models"):
            raw = os.path.join(RAW, "models", f"{name}.glb")
            model_glb(name, raw)
            os.makedirs(os.path.join(OUT, "models"), exist_ok=True)
            finish(raw, os.path.join(OUT, rel), use_npx)
        kind = "hero" if name.startswith(("SM_Trinity", "SM_Mark_")) or len(items) == 1 else "instanced"
        rows = []
        for label, x, y, z, yaw, sx, sy, sz in items:
            p = to3([(x, y, z)])[0]
            rows.append([round(float(p[0]), 3), round(float(p[1]), 3), round(float(p[2]), 3),
                         round(-math.radians(yaw), 5), round(sx, 3), round(sz, 3), round(sy, 3)])
        models.append(dict(glb=rel, kind=kind, names=[i[0] for i in items] if kind == "hero" else None,
                           items=rows, triangles=glb_triangles(glb_source(name))))
    n_trees = trees_json(os.path.join(OUT, "trees.json")) if want("models") else 0

    labels = view_labels()
    views = [dict(name=k, label=labels.get(k, k), eye=[round(float(c), 2) for c in to3([e])[0]],
                  target=[round(float(c), 2) for c in to3([t])[0]]) for k, (e, t) in VIEWS.items()]
    az, el = math.radians(LIGHT["az"]), math.radians(LIGHT["elev"])
    sun = to3([(math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))])[0]
    if want("web"):
        tex = detail_textures()
        for fn in os.listdir(WEB_SRC):   # сайт — всё, кроме документации (web/README.md — для репозитория)
            if os.path.isfile(os.path.join(WEB_SRC, fn)) and not fn.endswith(".md"):
                shutil.copyfile(os.path.join(WEB_SRC, fn), os.path.join(OUT, fn))
        credits_json(os.path.join(OUT, "credits.json"), tex)
    else:
        prev = os.path.join(OUT, "scene.json")
        tex = json.load(open(prev, encoding="utf-8")).get("textures", {}) if os.path.exists(prev) else {}
    sizes = {}
    for root, _dirs, files in os.walk(OUT):
        for fn in files:
            if fn.endswith((".glb", ".json", ".jpg", ".js", ".html")) and "shots" not in root:
                p = os.path.join(root, fn)
                sizes[os.path.relpath(p, OUT).replace(os.sep, "/")] = os.path.getsize(p)
    scene = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "script": "scripts/web_export.py",
        "axes": "three.js: x — север, y — вверх, z — восток, метры; план (X, Y, Z) → (X, Z, Y); yaw → rotation.y = −yaw",
        "half_m": HALF, "water_z": WATER_Z, "horizon_r_m": horizon_mask()[1],
        "sun": dict(az=LIGHT["az"], elev=LIGHT["elev"], dir=[round(float(c), 5) for c in sun]),
        "fog": dict(color_linear=LIGHT["fog"][2]),
        "layers": [dict(name=n, glb=f"{n}.glb") for n, _, _ in layers],
        "models": models, "trees": "trees.json", "textures": tex, "views": views,
        "materials": {k: mat_spec(k) for k in list(plan.COLORS) + ["bark", "leaves", "metal", "concrete", "glow"]},
        "skipped": skipped, "sizes": sizes,
    }
    with open(os.path.join(OUT, "scene.json"), "w", encoding="utf-8") as f:
        json.dump(scene, f, ensure_ascii=False, indent=1)
    sizes["scene.json"] = os.path.getsize(os.path.join(OUT, "scene.json"))
    total = sum(sizes.values())
    print(f"[web_export] моделей {len(models)} ({sum(len(m['items']) for m in models)} мест), деревьев {n_trees}, "
          f"пропущено {len(skipped)}: {skipped[:6]}")
    for k in sorted(sizes, key=lambda k: -sizes[k])[:12]:
        print(f"    {k:40s} {sizes[k] / 1e6:7.2f} МБ")
    print(f"[web_export] build/web: {total / 1e6:.1f} МБ, {time.time() - t0:.0f} с")


if __name__ == "__main__":
    main()
