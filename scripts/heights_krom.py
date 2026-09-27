"""heights_krom.py — обновить высоты Landscape в L_Krom из heightmap скриптом, без интерфейса (M4).

Запуск:  python scripts/ue_run.py scripts/heights_krom.py   → итог в логе: «[heights_krom] done» или «FAILED»
Нужно: .venv\\Scripts\\python scripts/terrain_krom.py (build/terrain/heightmap_L_Krom_rg.png) и Landscape того же
размера (2017 × 2017), созданный по scripts/README.md, «Landscape». Создать Landscape этот скрипт не может.

Путь: heightmap байтами R (старший) и G (младший) в 8-битном PNG → текстура без сжатия, без мипов, выборка
ближайшего → материал рисует в render target RGBA32f целое значение высоты в канал R →
Landscape.landscape_import_heightmap_from_render_target (базовый слой). Пиксель (x, y) render target — вершина
(x, y) Landscape, как в heightmap (проверено выгрузкой landscape_export_heightmap_to_render_target).

Всё асинхронно, поэтому работа идёт не в самой команде, а на тиках редактора: текстура и шейдер собираются —
ждём, пока render target станет похож на heightmap (в центре — высота у собора), и пишем высоты. Landscape
пересобирает их тоже не сразу: выгрузка сразу после записи — нули, поэтому сверка (выгрузка против render target
в PROBE точках) повторяется на следующих тиках, пока не совпадёт. Временные текстура и материал потом удаляются.
После правки высот — цепочка «После правки рельефа» в scripts/README.md (там единственный список, кого перезапускать).
"""
import os
import random
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402

LEVEL = "/Game/Krom/Maps/L_Krom"
SRC = os.path.join(geo.REPO, "build", "terrain", "heightmap_L_Krom_rg.png")
TMP_DIR = "/Game/Krom/Environment/Terrain"
TEX_PATH = f"{TMP_DIR}/T_TmpHeightRG"
MAT_PATH = f"{TMP_DIR}/M_TmpHeightToRT"
SIZE = 2017
PROBE = 400      # точек проверки
# и постоянные — там, где рельеф правят руками (D-026: Перси, Довмонтов город, захаб), м; случайные в узкую правку
# не попадают, и «до записи отличалось» показывало 0
FIXED_M = ((-126, 25), (-131, 40), (-124, 0), (-140, 30), (-150, 60), (-110, 72), (-90, 62), (-80, 52),
           (-180, 40), (-120, 90))
HALF = SIZE // 2
MAX_TICKS = 900  # ждать сборки текстуры и шейдера и пересборки Landscape не дольше (≈15 с при 60 к/с)

# +0.25: импорт берёт целую часть R ((uint16)R), а 32767.9999 от погрешности дало бы 32767
TO_RT_HLSL = """
float4 t = Texture2DSample(Tex, TexSampler, UV);
return float3(floor(t.r * 255.0 + 0.5) * 256.0 + floor(t.g * 255.0 + 0.5) + 0.25, 0.0, 0.0);
"""

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
mel = unreal.MaterialEditingLibrary
rl = unreal.RenderingLibrary


def import_rg():
    task = unreal.AssetImportTask()
    for k, v in (("filename", SRC), ("destination_path", TMP_DIR), ("destination_name", TEX_PATH.rsplit("/", 1)[1]),
                 ("replace_existing", True), ("automated", True), ("save", False)):
        task.set_editor_property(k, v)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    tex = unreal.load_asset(TEX_PATH)
    for k, v in (("srgb", False), ("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP),
                 ("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS),
                 ("filter", unreal.TextureFilter.TF_NEAREST), ("never_stream", True),
                 ("address_x", unreal.TextureAddress.TA_CLAMP), ("address_y", unreal.TextureAddress.TA_CLAMP)):
        tex.set_editor_property(k, v)
    return tex


def to_rt_material(tex):
    d, name = MAT_PATH.rsplit("/", 1)
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, d, unreal.Material, unreal.MaterialFactoryNew())
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    t = mel.create_material_expression(mat, unreal.MaterialExpressionTextureObject, -600, 0)
    t.set_editor_property("texture", tex)
    t.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    uv = mel.create_material_expression(mat, unreal.MaterialExpressionTextureCoordinate, -600, 150)
    c = mel.create_material_expression(mat, unreal.MaterialExpressionCustom, -300, 0)
    c.set_editor_property("code", TO_RT_HLSL)
    c.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    ins = []
    for n in ("Tex", "UV"):
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    c.set_editor_property("inputs", ins)
    mel.connect_material_expressions(t, "", c, "Tex")
    mel.connect_material_expressions(uv, "", c, "UV")
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(mat)
    return mat


def new_rt(world):
    return rl.create_render_target2d(world, SIZE, SIZE, unreal.TextureRenderTargetFormat.RTF_RGBA32F,
                                     unreal.LinearColor(0, 0, 0, 0), False)


def height_at(world, rt, p, rg):
    """Значение высоты (0…65535) в пикселе p: rg — выгрузка Landscape (байты в R, G), иначе целое в R."""
    c = rl.read_render_target_raw_pixel(world, rt, p[0], p[1], False)
    return round(c.r * 255) * 256 + round(c.g * 255) if rg else int(c.r)


def cleanup():
    for path in (MAT_PATH, TEX_PATH):  # сначала материал: он ссылается на текстуру
        if assets.does_asset_exist(path):
            assets.delete_asset(path)


def write(s):
    """Render target готов: запомнить ожидаемые значения и записать высоты в Landscape."""
    world, land, src = s["world"], s["land"], s["src"]
    rnd = random.Random(1)
    pts = [(0, 0), (SIZE - 1, SIZE - 1), (HALF, HALF)] + [(x + HALF, y + HALF) for x, y in FIXED_M]
    pts += [(rnd.randrange(SIZE), rnd.randrange(SIZE)) for _ in range(PROBE)]
    s["want"] = {p: height_at(world, src, p, rg=False) for p in pts}
    before = new_rt(world)
    land.landscape_export_heightmap_to_render_target(before, True, True)
    s["changed"] = sum(1 for p in pts if height_at(world, before, p, rg=True) != s["want"][p])
    if not land.landscape_import_heightmap_from_render_target(src, False, 0):
        raise RuntimeError("landscape_import_heightmap_from_render_target вернул False")


def mismatches(s):
    """Точки, где выгрузка Landscape ещё не равна записанному: [(точка, надо, есть)]."""
    after = new_rt(s["world"])
    s["land"].landscape_export_heightmap_to_render_target(after, True, True)
    got = ((p, v, height_at(s["world"], after, p, rg=True)) for p, v in s["want"].items())
    return [b for b in got if b[1] != b[2]]


def finish(s, error=None):
    unreal.unregister_slate_post_tick_callback(s["handle"])
    cleanup()
    if error:
        unreal.log_error(f"[heights_krom] FAILED: {error}")
        return
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    unreal.log(f"[heights_krom] done: {len(s['want'])} точек совпали, до записи отличалось {s['changed']}, "
               f"тиков {s['ticks']} (сверка — через {s['ticks'] - s['written_at']})")


def tick(_dt):
    s = unreal._heights_krom
    s["ticks"] += 1
    try:
        if s["phase"] == "draw":
            rl.draw_material_to_render_target(s["world"], s["src"], s["mat"])
            center = height_at(s["world"], s["src"], (SIZE // 2, SIZE // 2), rg=False)
            if 30000 < center < 35000:  # у собора Z = 0 → 32768 (±17 м)
                write(s)
                s["phase"], s["written_at"] = "verify", s["ticks"]
            elif s["ticks"] >= MAX_TICKS:
                finish(s, f"за {MAX_TICKS} тиков render target не стал heightmap: в центре {center}")
            return
        bad = mismatches(s)
        if not bad:
            finish(s)
        elif s["ticks"] >= MAX_TICKS:
            finish(s, f"после записи не совпало {len(bad)} из {len(s['want'])} точек, например {bad[:5]}")
    except Exception as e:  # noqa: BLE001 — в тике исключение потеряется, пишем в лог
        finish(s, e)


def main():
    prev = getattr(unreal, "_heights_krom", None)
    if prev and prev.get("handle") is not None:
        unreal.unregister_slate_post_tick_callback(prev["handle"])
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split(".")[0] != LEVEL:
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(LEVEL)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    land = [a for a in actors.get_all_level_actors() if isinstance(a, unreal.Landscape)]
    proxies = [a for a in actors.get_all_level_actors() if isinstance(a, unreal.LandscapeStreamingProxy)]
    if len(land) != 1:
        raise RuntimeError(f"ожидается один Landscape, найдено {len(land)}")
    if len(proxies) != 64:  # иначе запишутся только загруженные — см. level_krom.load_all
        raise RuntimeError(f"загружено {len(proxies)} прокси Landscape из 64 — сначала level_krom.py (LoadAll)")
    # Прокси — всегда загружены (D-042, уточнение 2026-09-27): в процессе рендера -game World Partition стримит их по
    # расстоянию от камеры, и дальняя земля исчезала под плоскостью воды. Флаг живёт в данных уровня; после
    # пересоздания Landscape его вернёт этот скрипт.
    streamed = [a for a in land + proxies if a.get_editor_property("is_spatially_loaded")]
    for a in streamed:
        a.set_editor_property("is_spatially_loaded", False)
    if streamed:
        unreal.log(f"[heights_krom] прокси Landscape всегда загружены: снят флаг is_spatially_loaded у {len(streamed)}")
    cleanup()
    mat = to_rt_material(import_rg())
    unreal._heights_krom = {"world": world, "land": land[0], "mat": mat, "src": new_rt(world), "ticks": 0,
                            "phase": "draw", "handle": None}
    unreal._heights_krom["handle"] = unreal.register_slate_post_tick_callback(tick)
    unreal.log("[heights_krom] запись поставлена на тики редактора")


main()
