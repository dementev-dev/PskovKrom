"""palette_krom.py — общая палитра: Material Parameter Collection MPC_KromPalette (M4, D-023, D-027).

Модуль для редактора, сам ничего не запускает: его импортируют landscape_krom.py, horizon_krom.py,
materials_krom.py, heroes_krom.py и walls_krom.py.
Здесь же материал воды M_KromWater — общий для Landscape и кольца, импорт текстур и узлы материалов.
Цвета поля, леса, города и воды у Landscape и у кольца горизонта — одни и те же параметры коллекции, поэтому
правка палитры не возвращает цветовой стык на краю Landscape. Цвета зданий — там же, под ключами
krom_plan.COLORS с большой буквы (Wall, Stone, Wood…): числа правятся в плане, коллекция их только несёт.
Пресеты времени суток (M4) меняют цвета коллекции на лету (unreal.MaterialLibrary.set_vector_parameter_value),
материалы не пересобираются.

collection() создаёт коллекцию или обновляет значения на месте: у существующих параметров сохраняются их GUID,
иначе материалы, которые на них ссылаются, пришлось бы пересобирать.
"""
import importlib
import json
import os

import unreal

import krom_geo
import krom_plan

importlib.reload(krom_plan)

MPC_DIR = "/Game/Krom/Materials/Terrain"
MPC_NAME = "MPC_KromPalette"
BUILDING_DIR = "/Game/Krom/Materials/Buildings"   # M_Krom<Ключ> — materials_krom.py

# linear RGB; подбирать по снимкам вьюпорта (view_krom.py)
PALETTE = {
    "Field": (0.055, 0.100, 0.036),   # трава Landscape, поля и луга кольца; холоднее прежнего — фото kutekroma_yard
    "Forest": (0.035, 0.062, 0.028),  # лес кольца
    "Built": (0.120, 0.115, 0.108),   # город кольца; пятна зданий на Landscape (дома — в M5)
    "Water": (0.015, 0.040, 0.045),   # вода: M_KromWater, реки и болота кольца
    "Earth": (0.140, 0.110, 0.070),   # грунт: тропы, откосы, полоса у уреза
    "Asphalt": (0.080, 0.080, 0.076),
    "Paved": (0.170, 0.160, 0.145),   # мощение, руины фундаментов
    "Gravel": (0.160, 0.112, 0.082),  # красно-бурый отсев троп вдоль Великой и на Стрелке (D-029): ярче травы ×1,3–1,6,
                                      # R:G ≈ 1,4 по дневным фото S-42 (на вечерних краснее)
    "Shore": (0.205, 0.170, 0.130),   # песок и галька у уреза под западной стеной Крома: вдвое ярче травы
    "Riprap": (0.165, 0.158, 0.148),  # серая каменная наброска у Плоской: как мощение, оттенок бетона
    "Foliage": (0.060, 0.120, 0.030), # листва деревьев (D-030): средний цвет атласа, породы — его строки
    "Bark": (0.100, 0.085, 0.065),    # кора деревьев
    "Facade": (0.536, 0.479, 0.413),  # застройка: базовый множитель материала; цвета зданий — facade_rules.py (D-043)
    "CityRoof": (0.160, 0.146, 0.128),  # кровли застройки: базовый множитель; цвета — facade_rules.py (D-043)
    "Concrete": (0.340, 0.330, 0.310),  # бетон мостов (D-034)
    "Railing": (0.200, 0.205, 0.210),   # крашеный металл перил и фонарей: серый (Ольгинский, покраска 2026 — S-47)
    "Screen": (0.560, 0.570, 0.580),    # серебристый ламельный экран моста 2024 (фото S-50, похоже на RAL 9006 — гип.)
    "Walkway": (0.090, 0.110, 0.130),   # серо-голубое покрытие Sika с кварцевым песком (S-49)
    "LampGlobe": (0.800, 0.800, 0.780), # белые шары фонарей Ольгинского моста (S-48)
}
WATER_ROUGHNESS = 0.06  # тёмная речная вода
# рябь (D-031): карта нормалей water_normals.py двумя слоями — второй крупнее и повёрнут, оба дрейфуют по ветру;
# издалека гаснет (мельче пикселя рябь — только мерцание), кольцо горизонта остаётся зеркальным
WATER_JSON = os.path.join(krom_geo.REPO, "refs", "textures", "water", "water.json")
WATER_TEX_DIR = "/Game/Krom/Environment/Water"
RIPPLE_SCALE2 = 2.7            # второй слой во столько раз крупнее первого
RIPPLE_SPEED = (0.05, 0.035)   # м/с по u, v первого слоя; второй — медленнее и под углом
RIPPLE_STRENGTH = 0.35          # спокойная река: отражения дробятся, но читаются (фото S-42)
RIPPLE_FADE_M = (150.0, 600.0)  # с этого расстояния рябь слабеет, к этому — гладь
WATER_HLSL = """
float2 xy = WP.xy * 0.01;
float2 uv1 = xy / {tile1} + T * float2({s1x}, {s1y});
float2 r = float2(xy.x * 0.8 - xy.y * 0.6, xy.x * 0.6 + xy.y * 0.8);
float2 uv2 = r / {tile2} - T * float2({s2x}, {s2y});
float2 a = Texture2DSample(N, NSampler, uv1).xy * 2.0 - 1.0;
float2 b = Texture2DSample(N, NSampler, uv2).xy * 2.0 - 1.0;
float fade = 1.0 - smoothstep({near}, {far}, D * 0.01);
return normalize(float3((a + b) * {strength} * fade, 1.0));
"""

assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary


def building_key(key):
    """Имя параметра коллекции и суффикс материала для ключа krom_plan.COLORS: wall → Wall."""
    return key.capitalize()


def colors():
    """Все цвета коллекции: земля (PALETTE) и здания (krom_plan.COLORS)."""
    out = dict(PALETTE)
    out.update({building_key(k): v for k, v in krom_plan.COLORS.items()})
    return out


def collection():
    """MPC_KromPalette с цветами colors() (создать или обновить на месте), сохранённая."""
    path = f"{MPC_DIR}/{MPC_NAME}"
    if assets.does_asset_exist(path):
        mpc = unreal.load_asset(path)
    else:
        mpc = tools.create_asset(MPC_NAME, MPC_DIR, unreal.MaterialParameterCollection,
                                 unreal.MaterialParameterCollectionFactoryNew())
    params = list(mpc.get_editor_property("vector_parameters"))
    by_name = {str(p.get_editor_property("parameter_name")): p for p in params}
    for name, rgb in colors().items():
        p = by_name.get(name)
        if p is None:
            p = unreal.CollectionVectorParameter()
            p.set_editor_property("parameter_name", name)
            params.append(p)
        p.set_editor_property("default_value", unreal.LinearColor(*rgb, 1.0))
    mpc.set_editor_property("vector_parameters", params)
    assets.save_loaded_asset(mpc)
    return mpc


def param(mat, mpc, name, x, y):
    """Узел материала «цвет name из коллекции» (выход float4, цвет — RGB)."""
    e = mel.create_material_expression(mat, unreal.MaterialExpressionCollectionParameter, x, y)
    e.set_editor_property("collection", mpc)
    e.set_editor_property("parameter_name", name)
    return e


def expr(mat, cls, x, y, **props):
    """Узел материала класса cls в (x, y) со свойствами props."""
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def custom(mat, x, y, code, inputs, output=unreal.CustomMaterialOutputType.CMOT_FLOAT3, description="Krom"):
    """Узел Custom с HLSL code; inputs — [(имя, узел, выход узла)], входы подключаются по порядку."""
    c = expr(mat, unreal.MaterialExpressionCustom, x, y, code=code, output_type=output, description=description)
    ins = []
    for name, _, _ in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", name)
        ins.append(ci)
    c.set_editor_property("inputs", ins)
    for name, node, out in inputs:
        mel.connect_material_expressions(node, out, c, name)
    return c


def hlsl_vec(v):
    return "float3({:.4f}, {:.4f}, {:.4f})".format(*v)


def fresh_material(path):
    """Материал по пути path: существующий — очищенный от узлов, иначе новый."""
    if assets.does_asset_exist(path):
        mat = unreal.load_asset(path)
        mel.delete_all_material_expressions(mat)
        return mat
    d, name = path.rsplit("/", 1)
    return tools.create_asset(name, d, unreal.Material, unreal.MaterialFactoryNew())


# вид текстуры → (sRGB, сжатие, повтор); сэмплер в материале — SAMPLER[вид]
TEXTURE_KINDS = {
    "color": (True, unreal.TextureCompressionSettings.TC_DEFAULT, unreal.TextureAddress.TA_WRAP),
    # маска покрытия: четыре независимых канала, у DXT5 они текут друг в друга по блокам 4 × 4; по краям — clamp
    "mask": (False, unreal.TextureCompressionSettings.TC_BC7, unreal.TextureAddress.TA_CLAMP),
    "normal": (False, unreal.TextureCompressionSettings.TC_NORMALMAP, unreal.TextureAddress.TA_WRAP),
    "linear": (False, unreal.TextureCompressionSettings.TC_MASKS, unreal.TextureAddress.TA_WRAP),  # Rough, arm
}
SAMPLER = {
    "color": unreal.MaterialSamplerType.SAMPLERTYPE_COLOR,
    "mask": unreal.MaterialSamplerType.SAMPLERTYPE_MASKS,
    "normal": unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL,
    "linear": unreal.MaterialSamplerType.SAMPLERTYPE_MASKS,
}


def import_texture(png, directory, name, kind="color"):
    """Картинка png → текстура directory/name (заменяет прежнюю), настройки по виду kind из TEXTURE_KINDS."""
    task = unreal.AssetImportTask()
    for k, v in (("filename", png), ("destination_path", directory), ("destination_name", name),
                 ("replace_existing", True), ("automated", True), ("save", False)):
        task.set_editor_property(k, v)
    tools.import_asset_tasks([task])
    tex = unreal.load_asset(f"{directory}/{name}")
    srgb, compression, address = TEXTURE_KINDS[kind]
    tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
    tex.set_editor_property("srgb", srgb)
    tex.set_editor_property("compression_settings", compression)
    tex.set_editor_property("address_x", address)
    tex.set_editor_property("address_y", address)
    assets.save_loaded_asset(tex)
    return tex


def building_material(key):
    """Материал здания M_Krom<Ключ> (materials_krom.py) для слота key; ещё не собран — None."""
    path = f"{BUILDING_DIR}/M_Krom{building_key(key)}"
    return unreal.load_asset(path) if assets.does_asset_exist(path) else None


def water_material(mpc):
    """M_KromWater — вода Landscape и кольца: цвет Water из коллекции, рябь — карта нормалей water_normals.py.
    Здесь, а не в landscape_krom, чтобы landscape_krom и horizon_krom не зависели друг от друга по кругу."""
    with open(WATER_JSON, encoding="utf-8") as f:
        w = json.load(f)
    ripples = import_texture(os.path.join(krom_geo.REPO, w["normal"]), WATER_TEX_DIR, "T_WaterRipples_N", "normal")
    mat = fresh_material(f"{MPC_DIR}/M_KromWater")
    mel.connect_material_property(param(mat, mpc, "Water", -300, 0), "", unreal.MaterialProperty.MP_BASE_COLOR)
    rough = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -300, 200)
    rough.set_editor_property("r", WATER_ROUGHNESS)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    tile1 = w["tile_m"]
    code = WATER_HLSL.format(
        tile1=tile1, tile2=tile1 * RIPPLE_SCALE2, s1x=RIPPLE_SPEED[0] / tile1, s1y=RIPPLE_SPEED[1] / tile1,
        s2x=0.6 * RIPPLE_SPEED[1] / tile1, s2y=0.6 * RIPPLE_SPEED[0] / tile1, strength=RIPPLE_STRENGTH,
        near=RIPPLE_FADE_M[0], far=RIPPLE_FADE_M[1])
    normal = custom(mat, -300, 350, code,
                    [("WP", expr(mat, unreal.MaterialExpressionWorldPosition, -700, 300), ""),
                     ("T", expr(mat, unreal.MaterialExpressionTime, -700, 400), ""),
                     ("D", expr(mat, unreal.MaterialExpressionPixelDepth, -700, 500), ""),
                     ("N", expr(mat, unreal.MaterialExpressionTextureObject, -700, 600, texture=ripples,
                                sampler_type=SAMPLER["normal"]), "")],
                    description="KromRipples")
    mel.connect_material_property(normal, "", unreal.MaterialProperty.MP_NORMAL)
    mel.recompile_material(mat)
    assets.save_loaded_asset(mat)
    return mat
