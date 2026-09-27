"""city_krom.py — рядовая застройка вокруг Крома в L_Krom: меши клеток из city_mesh.py (M5, D-032; фасады — D-043).

Запуск:
    .venv\\Scripts\\python scripts/city_mesh.py             # build/city/city.json
    python scripts/ue_run.py scripts/city_krom.py

Клетка city.json → StaticMesh /Game/Krom/Environment/City/SM_City_<клетка> через GeometryScript (Nanite, без
коллизии), слоты facade, glass и roof. Окна, двери, цоколь, карниз, свес кровли — геометрия city_mesh (фасадный
генератор, D-043), цвета — в цвет вершин (linear, итоговые). Материалы:
  - M_KromFacade — цвет вершин × палитра Facade ÷ её исходное значение (palette_krom.PALETTE): по умолчанию цвет
    вершин как есть, правка Facade в коллекции тонирует всю застройку;
  - M_KromCityGlass — стёкла: цвет вершин, низкая шероховатость (в окнах отражается небо);
  - M_KromCityRoof — кровли и козырьки: цвет вершин × CityRoof ÷ исходное.
Идемпотентен: удаляет свои акторы (тег generated:city_krom) и ассеты клеток, которых больше нет, пересобирает меши
в те же ассеты и сохраняет.
"""
import importlib
import json
import os
import sys
import time

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402
import palette_krom  # noqa: E402

importlib.reload(palette_krom)

LEVEL = "/Game/Krom/Maps/L_Krom"
TAG = unreal.Name("generated:city_krom")
FOLDER = "Generated/city_krom"
CITY_DIR = "/Game/Krom/Environment/City"
MAT_DIR = "/Game/Krom/Materials/City"
CITY_JSON = os.path.join(geo.REPO, "build", "city", "city.json")
PARTS = ("facade", "glass", "roof")

FACADE_ROUGHNESS, GLASS_ROUGHNESS, ROOF_ROUGHNESS = 0.85, 0.12, 0.6
TINT_HLSL = "return C.rgb * V.rgb / {ref};"     # палитра ÷ её исходное значение: по умолчанию — цвет вершин
GLASS_HLSL = "return V.rgb;"

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
mel = unreal.MaterialEditingLibrary
P = unreal.MaterialProperty
X = palette_krom.expr
GS = unreal.GeometryScript_MeshEdits


def materials(mpc):
    vec = palette_krom.hlsl_vec
    out = {}
    for key, name, color, rough in (("facade", "M_KromFacade", "Facade", FACADE_ROUGHNESS),
                                     ("glass", "M_KromCityGlass", None, GLASS_ROUGHNESS),
                                     ("roof", "M_KromCityRoof", "CityRoof", ROOF_ROUGHNESS)):
        mat = palette_krom.fresh_material(f"{MAT_DIR}/{name}")
        ins = [("V", X(mat, unreal.MaterialExpressionVertexColor, -900, -150), "")]
        if color:
            ins.append(("C", palette_krom.param(mat, mpc, color, -900, -300), ""))
            hlsl = TINT_HLSL.format(ref=vec(palette_krom.PALETTE[color]))
        else:
            hlsl = GLASS_HLSL
        base = palette_krom.custom(mat, -400, -200, hlsl, ins, description=f"KromCity{key.title()}")
        mel.connect_material_property(base, "", P.MP_BASE_COLOR)
        mel.connect_material_property(X(mat, unreal.MaterialExpressionConstant, -400, 100, r=rough), "", P.MP_ROUGHNESS)
        mat.set_editor_property("used_with_nanite", True)
        mel.recompile_material(mat)
        assets.save_loaded_asset(mat)
        out[key] = mat
    return out


def dynamic_mesh(cell):
    dm = unreal.DynamicMesh()
    for mid, key in enumerate(PARTS):
        p = cell["parts"].get(key)
        if not p:
            continue
        buf = unreal.GeometryScriptSimpleMeshBuffers()
        buf.set_editor_property("vertices", [unreal.Vector(x * 100, y * 100, z * 100) for x, y, z in p["v"]])
        buf.set_editor_property("normals", [unreal.Vector(*n) for n in p["n"]])
        buf.set_editor_property("uv0", [unreal.Vector2D(u, v) for u, v in p["uv"]])
        buf.set_editor_property("vertex_colors", [unreal.LinearColor(r, g, b, 1.0) for r, g, b in p["c"]])
        buf.set_editor_property("triangles", [unreal.IntVector(*t) for t in p["t"]])
        GS.append_buffers_to_mesh(dm, buf, material_id=mid)
    return dm


def write_asset(dm, path, mats):
    if not assets.does_asset_exist(path):
        opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
        opts.set_editor_property("enable_recompute_normals", False)
        unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, path, opts)
    sm = unreal.load_asset(path)
    opts = unreal.GeometryScriptCopyMeshToAssetOptions()
    for k, v in (("enable_recompute_normals", False), ("replace_materials", True),
                 ("new_materials", [mats[k] for k in PARTS]), ("new_material_slot_names", [unreal.Name(k) for k in PARTS])):
        opts.set_editor_property(k, v)
    unreal.GeometryScript_AssetUtils.copy_mesh_to_static_mesh(dm, sm, opts, unreal.GeometryScriptMeshWriteLOD())
    meshes.remove_collisions(sm)
    ns = sm.get_editor_property("nanite_settings")
    ns.set_editor_property("enabled", True)
    sm.set_editor_property("nanite_settings", ns)
    assets.save_loaded_asset(sm)
    return sm


def main():
    t0 = time.time()
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split(".")[0] != LEVEL:
        levels.load_level(LEVEL)
    with open(CITY_JSON, encoding="utf-8") as f:
        city = json.load(f)
    # Акторы клеток переиспользуются: ассет клетки перезаписывается на месте, а удаление всех акторов разом
    # опустошало папку Generated/city_krom, и редактор падал на ассерте ActorFolder !bIsDeleted (2026-09-27).
    names = {f"SM_City_{c['name']}" for c in city["cells"]}
    existing = {}
    for a in actors.get_all_level_actors():
        if TAG in a.tags:
            label = a.get_actor_label()
            if label.startswith("City ") and f"SM_City_{label[5:]}" in names and label[5:] not in existing:
                existing[label[5:]] = a
            else:
                actors.destroy_actor(a)
    mats = materials(palette_krom.collection())
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    for ad in reg.get_assets_by_path(CITY_DIR, recursive=False):
        if str(ad.asset_name).startswith("SM_City_") and str(ad.asset_name) not in names:
            assets.delete_asset(str(ad.package_name))
    for cell in city["cells"]:
        sm = write_asset(dynamic_mesh(cell), f"{CITY_DIR}/SM_City_{cell['name']}", mats)
        ox, oy = cell["origin"]
        a = existing.get(cell["name"])
        if a is None:
            a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(ox * 100, oy * 100, 0))
            a.set_actor_label(f"City {cell['name']}")
            a.set_folder_path(FOLDER)
            a.set_editor_property("tags", [TAG])
            a.set_editor_property("is_spatially_loaded", False)
        else:
            a.set_actor_location(unreal.Vector(ox * 100, oy * 100, 0), False, False)
        a.static_mesh_component.set_static_mesh(sm)
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    s = city["stats"]
    unreal.log(f"[city_krom] done: {s['buildings']} зданий в {len(city['cells'])} клетках, {s['triangles']} треугольников, "
               f"{time.time() - t0:.0f} с")


main()
