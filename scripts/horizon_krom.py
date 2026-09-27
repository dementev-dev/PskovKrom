"""horizon_krom.py — кольцо горизонта в L_Krom (D-022, D-023): земля и вода за краем Landscape, материал по маске.

Запуск:  python scripts/ue_run.py scripts/horizon_krom.py
Нужно: .venv\\Scripts\\python scripts/horizon_mesh.py (build/horizon).

Меши из build/horizon/*.bin → GeometryScript → /Game/Krom/Environment/Horizon/SM_Horizon_Ground (Nanite) и
SM_Horizon_Water. Без коллизии и без distance field (кольцо в десятки километров Lumen всё равно не разрешит).
Материал M_KromHorizon: маска T_HorizonMask по UV0 (R — лес, G — город, B — вода и болото, остальное — поле),
цвета групп — из общей палитры MPC_KromPalette (palette_krom.py), те же, что у Landscape (D-023, D-025).

Идемпотентен: переимпортирует маску, пересобирает материал, переписывает меши в те же ассеты, пересоздаёт свои
акторы (тег generated:horizon_krom) и сохраняет.
"""
import importlib
import json
import os
import sys
import time
from array import array

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402
import palette_krom  # noqa: E402

importlib.reload(palette_krom)

LEVEL = "/Game/Krom/Maps/L_Krom"
TAG = unreal.Name("generated:horizon_krom")
FOLDER = "Generated/horizon_krom"
MESH_DIR = "/Game/Krom/Environment/Horizon"
TEX_DIR = "/Game/Krom/Environment/Horizon"
MAT_DIR = "/Game/Krom/Materials/Terrain"
SRC = os.path.join(geo.REPO, "build", "horizon")

GROUPS = ("Field", "Forest", "Built", "Water")  # цвета групп — параметры MPC_KromPalette
ROUGHNESS_LAND, ROUGHNESS_WATER = 0.95, 0.1
SPECULAR_LAND, SPECULAR_WATER = 0.1, 0.5  # у суши блик неба под скользящим углом красил лес вдали в лиловый

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary


def read_mesh(name):
    """build/horizon/<name>.bin (horizon_mesh.write_mesh) → DynamicMesh в сантиметрах."""
    with open(os.path.join(SRC, f"{name}.bin"), "rb") as f:
        nv, nt = array("i", f.read(8))
        pos, nrm, uv, tri = array("f"), array("f"), array("f"), array("i")
        pos.frombytes(f.read(nv * 12))
        nrm.frombytes(f.read(nv * 12))
        uv.frombytes(f.read(nv * 8))
        tri.frombytes(f.read(nt * 12))
    buf = unreal.GeometryScriptSimpleMeshBuffers()
    buf.set_editor_property("vertices", [unreal.Vector(pos[i] * 100, pos[i + 1] * 100, pos[i + 2] * 100)
                                         for i in range(0, 3 * nv, 3)])
    buf.set_editor_property("normals", [unreal.Vector(nrm[i], nrm[i + 1], nrm[i + 2]) for i in range(0, 3 * nv, 3)])
    buf.set_editor_property("uv0", [unreal.Vector2D(uv[i], uv[i + 1]) for i in range(0, 2 * nv, 2)])
    buf.set_editor_property("triangles", [unreal.IntVector(tri[i], tri[i + 1], tri[i + 2]) for i in range(0, 3 * nt, 3)])
    dm = unreal.DynamicMesh()
    unreal.GeometryScript_MeshEdits.append_buffers_to_mesh(dm, buf, material_id=0)
    return dm, nt


def write_asset(dm, path, mat, nanite):
    """DynamicMesh → StaticMesh по пути path (создать или переписать): без коллизии и distance field."""
    if not assets.does_asset_exist(path):
        opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
        opts.set_editor_property("enable_recompute_normals", False)
        opts.set_editor_property("enable_collision", False)
        unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, path, opts)
    sm = unreal.load_asset(path)
    build = meshes.get_lod_build_settings(sm, 0)
    build.set_editor_property("distance_field_resolution_scale", 0.0)
    meshes.set_lod_build_settings(sm, 0, build)
    opts = unreal.GeometryScriptCopyMeshToAssetOptions()
    for k, v in (("enable_recompute_normals", False), ("replace_materials", True), ("new_materials", [mat]),
                 ("new_material_slot_names", [unreal.Name("ground")])):
        opts.set_editor_property(k, v)
    unreal.GeometryScript_AssetUtils.copy_mesh_to_static_mesh(dm, sm, opts, unreal.GeometryScriptMeshWriteLOD())
    meshes.remove_collisions(sm)
    sm.get_editor_property("body_setup").set_editor_property(
        "collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)  # простых форм нет — коллизии нет
    ns = sm.get_editor_property("nanite_settings")
    ns.set_editor_property("enabled", nanite)
    if nanite:  # запасной меш — по нему рисуют снимки SceneCapture (shot_krom), упрощать нечего
        ns.set_editor_property("fallback_target", unreal.NaniteFallbackTarget.PERCENT_TRIANGLES)
        ns.set_editor_property("fallback_percent_triangles", 1.0)
    sm.set_editor_property("nanite_settings", ns)
    assets.save_loaded_asset(sm)
    return sm


def import_mask():
    task = unreal.AssetImportTask()
    for k, v in (("filename", os.path.join(SRC, "T_HorizonMask.png")), ("destination_path", TEX_DIR),
                 ("destination_name", "T_HorizonMask"), ("replace_existing", True), ("automated", True),
                 ("save", False)):
        task.set_editor_property(k, v)
    tools.import_asset_tasks([task])
    tex = unreal.load_asset(f"{TEX_DIR}/T_HorizonMask")
    for k, v in (("srgb", False), ("compression_settings", unreal.TextureCompressionSettings.TC_MASKS),
                 ("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD),
                 ("address_x", unreal.TextureAddress.TA_CLAMP), ("address_y", unreal.TextureAddress.TA_CLAMP)):
        tex.set_editor_property(k, v)
    assets.save_loaded_asset(tex)
    return tex


def expr(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def horizon_material(tex, mpc):
    """Цвет = поле + (лес − поле)·R + (город − поле)·G + (вода − поле)·B; шероховатость и specular — от суши
    к воде по B."""
    mat = palette_krom.fresh_material(f"{MAT_DIR}/M_KromHorizon")
    mask = expr(mat, unreal.MaterialExpressionTextureSampleParameter2D, -900, 0, parameter_name="Mask",
                texture=tex, sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    colors = {name: palette_krom.param(mat, mpc, name, -900, 300 + 150 * i) for i, name in enumerate(GROUPS)}
    acc = colors["Field"]
    for i, (name, pin) in enumerate((("Forest", "R"), ("Built", "G"), ("Water", "B"))):
        d = expr(mat, unreal.MaterialExpressionSubtract, -600, 300 + 150 * i)
        mel.connect_material_expressions(colors[name], "", d, "A")
        mel.connect_material_expressions(colors["Field"], "", d, "B")
        m = expr(mat, unreal.MaterialExpressionMultiply, -400, 300 + 150 * i)
        mel.connect_material_expressions(d, "", m, "A")
        mel.connect_material_expressions(mask, pin, m, "B")
        s = expr(mat, unreal.MaterialExpressionAdd, -200, 300 + 150 * i)
        mel.connect_material_expressions(acc, "", s, "A")
        mel.connect_material_expressions(m, "", s, "B")
        acc = s
    mel.connect_material_property(acc, "", unreal.MaterialProperty.MP_BASE_COLOR)
    rough = expr(mat, unreal.MaterialExpressionLinearInterpolate, -200, 0, const_a=ROUGHNESS_LAND,
                 const_b=ROUGHNESS_WATER)
    mel.connect_material_expressions(mask, "B", rough, "Alpha")
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    spec = expr(mat, unreal.MaterialExpressionLinearInterpolate, -200, 150, const_a=SPECULAR_LAND,
                const_b=SPECULAR_WATER)
    mel.connect_material_expressions(mask, "B", spec, "Alpha")
    mel.connect_material_property(spec, "", unreal.MaterialProperty.MP_SPECULAR)
    mel.recompile_material(mat)
    assets.save_loaded_asset(mat)
    return mat


def spawn(label, sm, shadow):
    a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
    a.set_actor_label(label)
    a.set_folder_path(FOLDER)
    a.set_editor_property("tags", [TAG])
    a.set_editor_property("is_spatially_loaded", False)
    c = a.static_mesh_component
    c.set_static_mesh(sm)
    c.set_collision_profile_name("NoCollision")
    c.set_editor_property("cast_shadow", shadow)
    c.set_editor_property("affect_distance_field_lighting", False)
    return a


def main():
    t0 = time.time()
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split(".")[0] != LEVEL:
        levels.load_level(LEVEL)
    with open(os.path.join(SRC, "horizon.json"), encoding="utf-8") as f:
        info = json.load(f)
    for a in actors.get_all_level_actors():
        if TAG in a.tags:
            actors.destroy_actor(a)

    mpc = palette_krom.collection()
    mat = horizon_material(import_mask(), mpc)
    report = []
    for name, m, nanite, shadow in (("SM_Horizon_Ground", mat, True, True),
                                    ("SM_Horizon_Water", palette_krom.water_material(mpc), False, False)):
        dm, nt = read_mesh(name)
        sm = write_asset(dm, f"{MESH_DIR}/{name}", m, nanite)
        spawn(name.replace("SM_", "").replace("_", " "), sm, shadow)
        report.append(f"{name}: {nt} треугольников, Nanite {nanite}")

    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    for line in report:
        unreal.log(f"[horizon_krom] {line}")
    unreal.log(f"[horizon_krom] done: круг {info['radius_m'] / 1000:.0f} км от {info['generated']}, "
               f"{time.time() - t0:.0f} с")


main()
