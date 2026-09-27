"""textures_fetch.py — тайловые текстуры земли и зданий с Poly Haven (CC0) и их средние (M4).

Не для редактора: обычный Python из локального окружения (numpy, pillow):

    .venv\\Scripts\\python scripts/textures_fetch.py

Скачивает карты 2K (D-005: Landscape — не герой) в refs/textures/polyhaven/ (LFS), если их там ещё нет,
и пишет refs/textures/textures.json: файл, размер плитки в метрах (из Poly Haven), средний цвет в linear,
авторы и лицензия. Средний цвет нужен материалу: текстура делится на своё среднее и умножается на цвет
палитры (MPC_KromPalette) — рисунок от текстуры, цвет от палитры, издалека земля того же цвета, что кольцо.

Ключ "textures" — земля (его целиком читает landscape_krom.py), ключ "buildings" — стены и кровли героев,
ключ "roads" — полотно дорог и дорожек (roads_krom.py, D-038): Diffuse, nor_dx (нормали DirectX, как в UE) и Rough,
плюс rough_mean — средняя шероховатость 0..1.
Нет у ассета Rough — вместо неё maps["arm"] (AO/Rough/Metal): шероховатость в канале G (так читает materials_krom.py).
"""
import datetime
import json
import os
import sys
import urllib.request

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402

API = "https://api.polyhaven.com"
UA = {"User-Agent": "PskovKrom/0.1 (scripts/textures_fetch.py)"}  # Poly Haven отвечает 403 на User-Agent urllib
OUT_DIR = os.path.join(geo.REPO, "refs", "textures", "polyhaven")
OUT_JSON = os.path.join(geo.REPO, "refs", "textures", "textures.json")
RES = "2k"
MAPS = ("Diffuse",)  # нормали и шероховатость — когда дойдём до вида с высоты глаз: ("Diffuse", "nor_dx", "Rough")

# роль в материале → ассет Poly Haven (у ролей M5 запасной — в скобках)
TEXTURES = {
    "Grass": "leafy_grass",            # газон с листвой
    "Earth": "park_dirt",              # утоптанная земля тропинок и откосов
    "Asphalt": "asphalt_02",           # дороги, стоянки
    "Paved": "cobblestone_floor_08",   # мощение: тротуары, площади, дорожки Крома
    "Gravel": "gravelly_sand",         # отсев троп у Великой и на Стрелке: мелкое зерно с каменной крошкой (park_sand)
    "Shore": "floor_pebbles_01",       # полоса у уреза: песок с мелкой галькой 1–3 см (low_tide_rocks)
    "Riprap": "gray_rocks",            # наброска у Плоской и под набережной: угловатый серый камень (dry_river_pebbles)
}

# роль в материале зданий → ассет Poly Haven (ключ цвета krom_plan.COLORS — в комментарии; запасной — в скобках)
BUILDINGS = {
    "Stone": "rock_wall_08",              # stone, ruin: плитняк рядами, камни 10–16 × 25–40 см (rustic_stone_wall_02)
    "Whitewash": "painted_plaster_wall",  # wall, house: побелка, мягкая неровность штукатурки (plastered_stone_wall)
    "Planks": "old_planks_02",            # wood: серый тёс, доски ≈17 см вдоль вертикали картинки (weathered_planks)
}
BUILDING_MAPS = ("Diffuse", "nor_dx", "Rough")
# роль в материале дорог (roads_krom.MATS) → ассет Poly Haven; карты — как у зданий
ROADS = {
    "Asphalt": "asphalt_02",           # проезжая часть, асфальтовые дорожки (та же, что у земли)
    "Cobble": "cobblestone_floor_08",  # булыжник: дорога к Великим воротам, площадь у собора (та же, что «мощение»)
    "Tiles": "pavement_03",            # тротуарная плитка «кирпичик» серо-бурая (тротуары Пскова — гип.)
}
# листовой металл (green, roof, tin, copper, dark) — константами: фальцевой кровли в каталоге Poly Haven нет


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def download(url, path):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r, open(path, "wb") as f:
        f.write(r.read())


def mean_linear(path):
    """Средний цвет в linear: sRGB → linear попиксельно, потом среднее."""
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64) / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    return [round(float(v), 4) for v in lin.reshape(-1, 3).mean(axis=0)]


def rough_mean(path, channel=None):
    """Средняя шероховатость 0..1. Карта — данные, не цвет: без sRGB → linear. channel=1 — G из arm."""
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64) / 255.0
    return round(float(a[..., channel].mean() if channel is not None else a.mean()), 4)


def fetch_map(files, m):
    """Карта m разрешения RES: jpg, а если его нет — png. Качает, если файла нет или размер другой; путь от корня."""
    fmt = files[m][RES]
    src = fmt["jpg"] if "jpg" in fmt else fmt["png"]
    path = os.path.join(OUT_DIR, os.path.basename(src["url"]))
    if not os.path.exists(path) or os.path.getsize(path) != src["size"]:
        print(f"downloading {src['url']}")
        download(src["url"], path)
    return os.path.relpath(path, geo.REPO).replace("\\", "/")


def fetch(asset, maps):
    info = get_json(f"{API}/info/{asset}")
    files = get_json(f"{API}/files/{asset}")
    entry = {"asset": asset, "name": info["name"], "authors": sorted(info["authors"]),
             "tile_m": round(info["dimensions"][0] / 1000.0, 3), "license": "CC0",
             "page": f"https://polyhaven.com/a/{asset}", "maps": {}}
    for m in maps:
        if m == "Rough" and "Rough" not in files:
            m = "arm"  # шероховатость — канал G
        entry["maps"][m] = fetch_map(files, m)
    entry["mean_linear"] = mean_linear(os.path.join(geo.REPO, entry["maps"]["Diffuse"]))
    if "Rough" in maps:
        rough = entry["maps"].get("Rough") or entry["maps"]["arm"]
        entry["rough_mean"] = rough_mean(os.path.join(geo.REPO, rough), None if "Rough" in entry["maps"] else 1)
    return entry


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    out = {"generated": datetime.date.today().isoformat(), "script": "scripts/textures_fetch.py",
           "source": "Poly Haven (polyhaven.com), CC0", "textures": {}, "buildings": {}, "roads": {}}
    for key, table, maps in (("textures", TEXTURES, MAPS), ("buildings", BUILDINGS, BUILDING_MAPS),
                             ("roads", ROADS, BUILDING_MAPS)):
        for role, asset in table.items():
            entry = out[key][role] = fetch(asset, maps)
            rough = f", шероховатость {entry['rough_mean']}" if "rough_mean" in entry else ""
            print(f"{role:9} {asset:22} {entry['tile_m']} м, среднее {entry['mean_linear']}{rough}")
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
