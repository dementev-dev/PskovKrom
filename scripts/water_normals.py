"""water_normals.py — бесшовная карта нормалей ряби для материала воды M_KromWater (M5, D-031).

Не для редактора: обычный Python из локального окружения (numpy, pillow):

    .venv\\Scripts\\python scripts/water_normals.py

Рябь на реке — ветровые волны с длиной 0,1–2 м. Высоты — сумма волн со спектром Филлипса (как у океана, но короче
и мельче) через обратное FFT, поэтому карта сама по себе бесшовная. Нормали — из градиента высот, в DirectX-виде,
как нормали Poly Haven (D-027): R — X, G — минус Y. Пишет refs/textures/water/T_WaterRipples_N.png (1024², плитка
TILE_M) и water.json рядом: плитка и среднее отклонение нормали. Детерминированно (SEED).
"""
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402

OUT_DIR = os.path.join(geo.REPO, "refs", "textures", "water")
OUT_PNG = os.path.join(OUT_DIR, "T_WaterRipples_N.png")
OUT_JSON = os.path.join(OUT_DIR, "water.json")
SIZE = 1024
TILE_M = 4.0            # плитка карты, м
WIND_MS = 1.5           # ветер у воды, м/с: слабый — рябь 0,2–1 м, без барашков
WIND_DIR = (0.8, 0.6)   # направление ветра в осях карты (u, v); в материале карта ещё и поворачивается
SHORT_M = 0.025         # волны короче гасятся (мельче текселя издалека — только шум)
SLOPE = 0.12            # средний наклон поверхности (СКО градиента): спокойная река
SEED = 31


def spectrum(n, tile):
    """Амплитуды Филлипса на сетке волновых векторов n × n для плитки tile, м."""
    k1 = 2 * np.pi * np.fft.fftfreq(n, d=tile / n)
    kx, ky = np.meshgrid(k1, k1, indexing="xy")
    k = np.hypot(kx, ky)
    k[0, 0] = 1.0
    g = 9.81
    big_l = WIND_MS ** 2 / g                             # самая длинная волна при таком ветре
    w = np.array(WIND_DIR) / np.hypot(*WIND_DIR)
    align = ((kx * w[0] + ky * w[1]) / k) ** 2           # волны вдоль ветра сильнее
    p = np.exp(-1.0 / (k * big_l) ** 2) / k ** 4 * align * np.exp(-(k * SHORT_M) ** 2)
    p[0, 0] = 0.0
    return kx, ky, np.sqrt(p)


def main():
    rng = np.random.default_rng(SEED)
    kx, ky, amp = spectrum(SIZE, TILE_M)
    h_hat = amp * (rng.standard_normal(amp.shape) + 1j * rng.standard_normal(amp.shape))
    # градиент высот — в частотах: производная = i k · h
    gx = np.real(np.fft.ifft2(1j * kx * h_hat))
    gy = np.real(np.fft.ifft2(1j * ky * h_hat))
    s = SLOPE / np.sqrt((gx ** 2 + gy ** 2).mean())
    gx, gy = gx * s, gy * s
    n = np.stack([-gx, -gy, np.ones_like(gx)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    # DirectX: G хранит −Y; строки картинки идут вниз по v
    rgb = np.stack([n[..., 0], -n[..., 1], n[..., 2]], axis=-1) * 0.5 + 0.5
    os.makedirs(OUT_DIR, exist_ok=True)
    Image.fromarray(np.rint(rgb * 255).astype(np.uint8), "RGB").save(OUT_PNG)
    tilt = float(np.degrees(np.arctan(np.hypot(gx, gy))).mean())
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"script": "scripts/water_normals.py", "normal": os.path.relpath(OUT_PNG, geo.REPO).replace("\\", "/"),
                   "tile_m": TILE_M, "wind_ms": WIND_MS, "slope_rms": SLOPE, "mean_tilt_deg": round(tilt, 2)},
                  f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{OUT_PNG}: {SIZE}², плитка {TILE_M} м, средний наклон {tilt:.1f}°")


if __name__ == "__main__":
    main()
