"""photo_refs.py — фото-референсы с Wikimedia Commons и сравнение «фото / модель» (S-25).

Не для редактора. Берём только свободные лицензии Commons: автор и лицензия — в манифесте, ссылка на страницу
файла обязательна при любом показе. Точка съёмки — «camera location» Commons; направление там почти всегда
не указано, поэтому цель камеры задаётся в списке PHOTOS руками (по умолчанию — собор).

    python scripts/photo_refs.py fetch      # скачать PHOTOS в refs/photos/commons + manifest.json
    python scripts/ue_run.py -c "import sys; sys.path.insert(0, 'D:/PskovKrom/scripts'); \
        import shot_krom; shot_krom.shot_photos()"                     # модель с тех же точек (в редакторе)
    .venv\\Scripts\\python scripts/photo_refs.py compare               # пары фото | модель в media/renders/compare
"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402

API = "https://commons.wikimedia.org/w/api.php"
UA = "PskovKrom/0.1 (hobby non-commercial 3D model of Pskov Krom; reference photos)"
OUT_DIR = os.path.join(geo.REPO, "refs", "photos", "commons")
MANIFEST = os.path.join(OUT_DIR, "manifest.json")
COMPARE_DIR = os.path.join(geo.REPO, "media", "renders", "compare")
WIDTH = 1600

CATHEDRAL = (0.0, 0.0, 30.0)
# id → файл на Commons и поправки: target — цель камеры (x, y, z), по умолчанию собор; eye_z — отметка глаза,
# по умолчанию земля или вода + 1,7 м; focal35 — если в EXIF нет пересчёта на 35 мм. Точки съёмки — из Commons,
# цели подобраны по кадру; eye_z на мосту и у дрона — гип.
PHOTOS = {
    "zav_olga_chapel": {"title": "Часовня Святой Ольги. Вид на Кремль с Завеличья. Псков.jpg"},
    "zav_olga_chapel_2": {"title": "Троицкий собор и кремль от Ольгинской часовни - panoramio.jpg"},
    "zav_view4": {"title": "Ансамбль Псковского Кремля. Вид 4.jpg"},
    "zav_river_2014": {"title": "Вид на Псковский Кром с реки Великой, 2014..jpg",  # с воды; Canon 550D, 35 мм × 1,6
                       "eye_z": -11.4, "focal35": 56, "target": (-20.0, 10.0, 25.0)},
    "zav_north": {"title": "Кром с Завеличья - panoramio.jpg", "target": (290.0, -125.0, 10.0)},
    "zav_north_mouth": {"title": "Плоская башня и Кутекрома - panoramio.jpg", "target": (288.0, -113.0, 8.0)},
    "olginsky_1": {"title": "Троицкий собор с Ольгинского моста - panoramio.jpg", "eye_z": -4.0},
    "olginsky_2016": {"title": "Kremlin of Pskov (2016).jpg", "eye_z": -4.0},
    "pskova_bank": {"title": "Стены и башни Псковского кремля на берегу реки Псковы.jpg", "target": (365.0, -163.0, 5.0)},
    "pskova_sunrise": {"title": "Псковский Кремль со стороны реки Псковы на восходе 01.jpg",
                       "target": (170.0, -30.0, 5.0)},
    "aerial_velikaya": {"title": "Pskov asv07-2018 Kremlin aerial5.jpg", "eye_z": 100.0},
    # колокольня (M3): со двора Крома с запада и с Запсковья через Пскову
    "belfry_west": {"title": "Pskov KremlinBT1.jpg", "target": (-35.5, 50.7, 22.0),  # кадр обрезан, EXIF нет:
                    "focal35": 27},                                                    # по ширине грани и геотегу
    "belfry_yard": {"title": "Колокольня - panoramio (26).jpg", "target": (-35.5, 50.7, 22.0)},
    "belfry_pskova": {"title": "Колокольня и собор - panoramio.jpg", "target": (-20.0, 25.0, 28.0)},
    # Кутекрома (M3): со двора Крома; с Завеличья она же — в zav_north_mouth
    "kutekroma_yard": {"title": "Pskov Kremlin KutekromaTower1.jpg", "target": (235.0, -120.5, 8.0)},
}


def api(params):
    q = urllib.parse.urlencode(dict(params, format="json", formatversion="2"))
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
    for attempt in range(6):  # Commons режет частые запросы (429) на десятки секунд
        try:
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        except OSError:
            time.sleep(15 * (attempt + 1))
    raise RuntimeError(f"Commons API не ответил: {params}")


def plain(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def fetch():
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest = []
    for pid, spec in PHOTOS.items():
        title = spec["title"]
        d = api({"action": "query", "titles": f"File:{title}", "prop": "imageinfo|coordinates",
                 "iiprop": "url|extmetadata|commonmetadata", "iiurlwidth": str(WIDTH), "coprimary": "primary"})
        page = d["query"]["pages"][0]
        ii = page["imageinfo"][0]
        em = ii["extmetadata"]
        exif = {m["name"]: m["value"] for m in ii.get("commonmetadata", []) if not isinstance(m["value"], list)}
        lat, lon = page["coordinates"][0]["lat"], page["coordinates"][0]["lon"]
        x, y = geo.to_local(lat, lon)
        path = os.path.join(OUT_DIR, f"{pid}.jpg")
        if not os.path.exists(path):
            req = urllib.request.Request(ii["thumburl"], headers={"User-Agent": UA})
            with open(path, "wb") as f:
                f.write(urllib.request.urlopen(req, timeout=120).read())
            time.sleep(1)
        manifest.append({
            "id": pid, "title": title, "page": ii["descriptionurl"],
            "file": os.path.relpath(path, geo.REPO).replace("\\", "/"),
            "author": plain(em.get("Artist", {}).get("value")), "license": plain(em.get("LicenseShortName", {}).get("value")),
            "date": exif.get("DateTimeOriginal"), "camera_latlon": [lat, lon], "camera_xy": [round(x, 1), round(y, 1)],
            "target": list(spec.get("target", CATHEDRAL)), "eye_z": spec.get("eye_z"),
            "focal35": spec.get("focal35") or exif.get("FocalLengthIn35mmFilm"),
            "size": [ii["thumbwidth"], ii["thumbheight"]],
        })
        print(f"{pid:18} ({x:6.0f}, {y:6.0f})  f35={exif.get('FocalLengthIn35mmFilm')}  {manifest[-1]['license']}")
        time.sleep(1)
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f"{len(manifest)} фото → {MANIFEST}")


def compare(wait_s=180):
    """Фото слева, модель справа; подпись — автор и лицензия (атрибуция обязательна).

    Снимки модели shot_krom снимает в тиках редактора, поэтому недостающие ждём до wait_s секунд."""
    from PIL import Image, ImageDraw, ImageFont
    os.makedirs(COMPARE_DIR, exist_ok=True)
    font = ImageFont.truetype("arial.ttf", 16)
    photos = json.load(open(MANIFEST, encoding="utf-8"))
    models = {m["id"]: os.path.join(COMPARE_DIR, f"{m['id']}_model.png") for m in photos}
    deadline = time.time() + wait_s
    while not all(os.path.exists(p) for p in models.values()) and time.time() < deadline:
        time.sleep(2)
    time.sleep(1)  # последний файл мог ещё дописываться
    for m in photos:
        model = models[m["id"]]
        if not os.path.exists(model):
            print(f"нет {model} — сначала shot_krom.shot_photos()")
            continue
        a = Image.open(os.path.join(geo.REPO, m["file"])).convert("RGB")
        b = Image.open(model).convert("RGB").resize(a.size)
        pair = Image.new("RGB", (a.width * 2, a.height + 28), (20, 20, 20))
        pair.paste(a, (0, 0))
        pair.paste(b, (a.width, 0))
        ImageDraw.Draw(pair).text((8, a.height + 5), f"{m['title']} — {m['author']}, {m['license']} (Wikimedia Commons)"
                                  f"   |   модель, та же точка", fill=(220, 220, 220), font=font)
        out = os.path.join(COMPARE_DIR, f"{m['id']}.jpg")
        pair.save(out, quality=88)
        print(out)


if __name__ == "__main__":
    {"fetch": fetch, "compare": compare}[sys.argv[1] if len(sys.argv) > 1 else "fetch"]()
