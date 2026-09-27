"""trees_krom.py — деревья и кусты вокруг Крома в L_Krom: меши из Blender, материалы коры и листвы, HISM по точкам
(M5, D-030).

Запуск (сначала точки, атлас листвы и меши):
    .venv\\Scripts\\python scripts/trees_points.py            # build/trees/points.json
    .venv\\Scripts\\python scripts/leaf_atlas.py              # refs/textures/leaves, кора — refs/textures/trees.json
    python scripts/bl_run.py scripts/blender/tree.py          # build/blender/SM_Tree_*.glb + trees_report.json
    python scripts/ue_run.py scripts/trees_krom.py

Меши — build/blender/SM_Tree_<Порода>_<NN>.glb → /Game/Krom/Environment/Trees (Nanite, без коллизии), слоты `bark`
и `leaves`. Материалы:
  - листва M_KromLeaves — атлас (строка — порода), masked, двусторонняя листва (TwoSidedFoliage): свет насквозь;
    цвет — как у земли и зданий: атлас делится на свой средний цвет и умножается на цвет палитры Foliage;
  - кора M_KromBark<Rough|Smooth> — тайловая кора Poly Haven по UV в метрах, цвет — палитра Bark.
Расстановка: породы точек (species_hint) → меши SPECIES; вариант — по координатам, масштаб — высота точки к высоте
меша, поворот — yaw_deg, высота — трассой по Landscape. Один актор на меш с HierarchicalInstancedStaticMesh:
тысячи отдельных акторов — тысячи файлов World Partition.

Идемпотентен: удаляет свои акторы (тег generated:trees_krom), переимпортирует меши в те же ассеты, пересобирает
материалы и сохраняет.
"""
import importlib
import json
import os
import sys
import time
import zlib

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402
import palette_krom  # noqa: E402

importlib.reload(palette_krom)

LEVEL = "/Game/Krom/Maps/L_Krom"
TAG = unreal.Name("generated:trees_krom")
FOLDER = "Generated/trees_krom"
TREE_DIR = "/Game/Krom/Environment/Trees"
MAT_DIR = "/Game/Krom/Materials/Trees"
STAGING = f"{TREE_DIR}/_import"
GLB_DIR = os.path.join(geo.REPO, "build", "blender")
REPORT = os.path.join(GLB_DIR, "trees_report.json")
POINTS = os.path.join(geo.REPO, "build", "trees", "points.json")
TREES_JSON = os.path.join(geo.REPO, "refs", "textures", "trees.json")

# порода точки → порода меша (варианты — все SM_Tree_<Порода>_NN); породы без меша — ближайшая по облику (гип.)
SPECIES = {
    "maple": "maple", "linden": "linden",
    "birch": "aspen", "poplar": "aspen",     # берёзы и тополя — стройные, как осина
    "willow": "linden",                      # ивы у воды — широкие кроны
    "shrub": "hazel", "hedge": "hazel",
    "spruce": None, "conifer": None,         # хвойных мешей нет: 7 точек в городе пропускаются
}
LEAF_ROUGHNESS, LEAF_SUBSURFACE = 0.55, 0.6  # просвет листа — доля его цвета
BARK_ROUGHNESS = 0.85
TRACE_Z_M = 300.0

# цвет вершин из tree.py: R — случайное на карточку (оттенок), G — от центра кроны к поверхности (внутри темнее);
# через sRGB значения искажены — это порядок, а не точные числа
LEAF_HLSL = "return C.rgb * D / {mean} * lerp({tint0}, {tint1}, V.r) * lerp({inner}, 1.0, V.g);"
LEAF_TINT, LEAF_INNER = (0.85, 1.15), 0.55
BARK_HLSL = "return C.rgb * D / {mean};"

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary
P = unreal.MaterialProperty
X = palette_krom.expr


def sample(mat, x, y, texture, kind, uv=None):
    s = X(mat, unreal.MaterialExpressionTextureSample, x, y, texture=texture, sampler_type=palette_krom.SAMPLER[kind])
    if uv is not None:
        mel.connect_material_expressions(uv, "", s, "UVs")
    return s


def leaves_material(mpc, atlas, tex):
    """M_KromLeaves: атлас, masked, двусторонняя листва; цвет — Foliage из палитры."""
    mat = palette_krom.fresh_material(f"{MAT_DIR}/M_KromLeaves")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    mat.set_editor_property("two_sided", True)
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
    d = sample(mat, -900, -200, tex["D"], "color")
    n = sample(mat, -900, 150, tex["N"], "normal")
    code = LEAF_HLSL.format(mean=palette_krom.hlsl_vec(atlas["mean"]), tint0=LEAF_TINT[0], tint1=LEAF_TINT[1],
                            inner=LEAF_INNER)
    base = palette_krom.custom(mat, -450, -200, code,
                               [("D", d, "RGB"), ("C", palette_krom.param(mat, mpc, "Foliage", -900, -400), ""),
                                ("V", X(mat, unreal.MaterialExpressionVertexColor, -900, -500), "")],
                               description="KromLeaves")
    mel.connect_material_property(base, "", P.MP_BASE_COLOR)
    mel.connect_material_property(d, "A", P.MP_OPACITY_MASK)
    mel.connect_material_property(n, "RGB", P.MP_NORMAL)
    sss = X(mat, unreal.MaterialExpressionMultiply, -200, 0, const_b=LEAF_SUBSURFACE)
    mel.connect_material_expressions(base, "", sss, "A")
    mel.connect_material_property(sss, "", P.MP_SUBSURFACE_COLOR)
    mel.connect_material_property(X(mat, unreal.MaterialExpressionConstant, -200, 300, r=LEAF_ROUGHNESS), "",
                                  P.MP_ROUGHNESS)
    return finish(mat)


def bark_material(mpc, kind, info, tex):
    """M_KromBark<Kind>: кора Poly Haven по UV в метрах, цвет — Bark из палитры."""
    mat = palette_krom.fresh_material(f"{MAT_DIR}/M_KromBark{kind.capitalize()}")
    inv = 1.0 / info["tile_m"]
    uv = X(mat, unreal.MaterialExpressionTextureCoordinate, -1200, 0, u_tiling=inv, v_tiling=inv)
    d = sample(mat, -900, -200, tex["D"], "color", uv)
    n = sample(mat, -900, 150, tex["N"], "normal", uv)
    base = palette_krom.custom(mat, -450, -200, BARK_HLSL.format(mean=palette_krom.hlsl_vec(info["mean_linear"])),
                               [("D", d, "RGB"), ("C", palette_krom.param(mat, mpc, "Bark", -900, -400), "")],
                               description="KromBark")
    mel.connect_material_property(base, "", P.MP_BASE_COLOR)
    mel.connect_material_property(n, "RGB", P.MP_NORMAL)
    mel.connect_material_property(X(mat, unreal.MaterialExpressionConstant, -200, 300, r=BARK_ROUGHNESS), "",
                                  P.MP_ROUGHNESS)
    return finish(mat)


def finish(mat):
    for flag in ("used_with_nanite", "used_with_instanced_static_meshes"):
        mat.set_editor_property(flag, True)
    mel.recompile_material(mat)
    assets.save_loaded_asset(mat)
    return mat


def import_tree(name, mats):
    """build/blender/<name>.glb → StaticMesh TREE_DIR/<name> (Nanite, без коллизии); слоты по mats."""
    glb = os.path.join(GLB_DIR, f"{name}.glb")
    path = f"{TREE_DIR}/{name}"
    if assets.does_directory_exist(STAGING):
        assets.delete_directory(STAGING)
    task = unreal.AssetImportTask()
    for k, v in (("filename", glb), ("destination_path", STAGING), ("replace_existing", True),
                 ("automated", True), ("save", False)):
        task.set_editor_property(k, v)
    tools.import_asset_tasks([task])
    staged = [p for p in task.get_editor_property("imported_object_paths")
              if isinstance(unreal.load_asset(p), unreal.StaticMesh)]
    if len(staged) != 1:
        raise RuntimeError(f"импорт {glb}: ждали один StaticMesh, получили {staged}")
    src = unreal.load_asset(staged[0])
    names = [str(s.get_editor_property("material_slot_name")) for s in src.get_editor_property("static_materials")]
    lost = [n for n in names if n not in mats]
    if lost:
        raise RuntimeError(f"{name}: слоты без материала {lost}")
    if not assets.does_asset_exist(path):
        if not assets.rename_asset(staged[0].split(".")[0], path):
            raise RuntimeError(f"не удалось переместить {staged[0]} → {path}")
        sm = unreal.load_asset(path)
        for i, n in enumerate(names):
            sm.set_material(i, mats[n])
    else:  # геометрия копируется в прежний ассет — ссылки HISM на него остаются
        sm = unreal.load_asset(path)
        dm, _ = unreal.GeometryScript_AssetUtils.copy_mesh_from_static_mesh(
            src, unreal.DynamicMesh(), unreal.GeometryScriptCopyMeshFromAssetOptions(),
            unreal.GeometryScriptMeshReadLOD())
        opts = unreal.GeometryScriptCopyMeshToAssetOptions()
        for k, v in (("enable_recompute_normals", False), ("enable_recompute_tangents", False),
                     ("replace_materials", True), ("new_materials", [mats[n] for n in names]),
                     ("new_material_slot_names", [unreal.Name(n) for n in names])):
            opts.set_editor_property(k, v)
        unreal.GeometryScript_AssetUtils.copy_mesh_to_static_mesh(dm, sm, opts, unreal.GeometryScriptMeshWriteLOD())
    assets.delete_directory(STAGING)
    meshes.remove_collisions(sm)
    ns = sm.get_editor_property("nanite_settings")
    ns.set_editor_property("enabled", True)
    sm.set_editor_property("nanite_settings", ns)
    assets.save_loaded_asset(sm)
    return sm


class Ground:
    """Высота Landscape (м) трассой сверху; актор над землёй трасса проходит насквозь (как в walls_krom)."""

    def __init__(self, world):
        self.world, self.ignore, self.misses = world, [], 0

    def __call__(self, x, y):
        for _ in range(6):
            hit = unreal.SystemLibrary.line_trace_single(
                self.world, unreal.Vector(x * 100, y * 100, TRACE_Z_M * 100),
                unreal.Vector(x * 100, y * 100, -TRACE_Z_M * 100),
                unreal.TraceTypeQuery.ECC_VISIBILITY, True, self.ignore, unreal.DrawDebugTrace.NONE, True)
            if hit is None:
                break
            t = hit.to_tuple()
            if isinstance(t[9], unreal.LandscapeProxy):
                return t[5].z / 100.0
            self.ignore.append(t[9])
        self.misses += 1
        return None


def hism_actor(sm, label):
    """Актор с одним HierarchicalInstancedStaticMeshComponent для меша sm."""
    a = actors.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0))
    a.set_actor_label(label)
    a.set_folder_path(FOLDER)
    a.set_editor_property("tags", [TAG])
    a.set_editor_property("is_spatially_loaded", False)
    sub = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    root = sub.k2_gather_subobject_data_for_instance(a)[0]
    h, fail = sub.add_new_subobject(unreal.AddNewSubobjectParams(
        parent_handle=root, new_class=unreal.HierarchicalInstancedStaticMeshComponent, blueprint_context=None))
    if str(fail):
        raise RuntimeError(f"{label}: компонент не добавлен — {fail}")
    comp = unreal.SubobjectDataBlueprintFunctionLibrary.get_associated_object(
        unreal.SubobjectDataBlueprintFunctionLibrary.get_data(h))
    comp.set_static_mesh(sm)
    comp.set_collision_profile_name("NoCollision")
    return a, comp


def main():
    t0 = time.time()
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split(".")[0] != LEVEL:
        levels.load_level(LEVEL)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    with open(REPORT, encoding="utf-8") as f:
        report = json.load(f)
    if isinstance(report, list):
        report = {r["asset"]: r for r in report}
    with open(TREES_JSON, encoding="utf-8") as f:
        tinfo = json.load(f)
    with open(POINTS, encoding="utf-8") as f:
        points = json.load(f)["points"]
    for a in actors.get_all_level_actors():
        if TAG in a.tags:
            actors.destroy_actor(a)

    mpc = palette_krom.collection()
    atlas = tinfo["atlas"]
    rows = atlas["rows"].values()
    atlas["mean"] = [sum(r["mean_linear"][i] for r in rows) / len(rows) for i in range(3)]
    leaf_tex = {"D": palette_krom.import_texture(os.path.join(geo.REPO, atlas["diffuse"]), TREE_DIR,
                                                 "T_LeafAtlas_D", "color"),
                "N": palette_krom.import_texture(os.path.join(geo.REPO, atlas["normal"]), TREE_DIR,
                                                 "T_LeafAtlas_N", "normal")}
    leaf_tex["D"].set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
    leaf_tex["D"].set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    assets.save_loaded_asset(leaf_tex["D"])
    leaves = leaves_material(mpc, atlas, leaf_tex)
    barks = {}
    for kind, info in tinfo["bark"].items():
        tex = {m: palette_krom.import_texture(os.path.join(geo.REPO, info["maps"][src]), TREE_DIR,
                                              f"T_Bark{kind.capitalize()}_{m}", k)
               for m, src, k in (("D", "Diffuse", "color"), ("N", "nor_dx", "normal"))}
        barks[kind] = bark_material(mpc, kind, info, tex)

    by_species = {}
    for name, r in sorted(report.items()):
        sm = import_tree(name, {"bark": barks[tinfo["species_bark"][r["species"]]], "leaves": leaves})
        by_species.setdefault(r["species"], []).append((sm, r["height_m"]))

    ground = Ground(world)
    transforms, skipped = {}, {}
    for p in points:
        species = SPECIES.get(p["species_hint"])
        if species not in by_species:
            skipped[p["species_hint"]] = skipped.get(p["species_hint"], 0) + 1
            continue
        variants = by_species[species]
        sm, h = variants[zlib.crc32(f"{p['x']:.1f},{p['y']:.1f}".encode()) % len(variants)]
        z = ground(p["x"], p["y"])
        if z is None:
            continue
        s = p["height_m"] / h
        transforms.setdefault(sm.get_name(), (sm, []))[1].append(unreal.Transform(
            unreal.Vector(p["x"] * 100, p["y"] * 100, z * 100), unreal.Rotator(roll=0, pitch=0, yaw=p["yaw_deg"]),
            unreal.Vector(s, s, s)))
    for name, (sm, ts) in sorted(transforms.items()):
        _, comp = hism_actor(sm, f"Trees {name}")
        comp.add_instances(ts, False, True)

    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    unreal.log(f"[trees_krom] done: {sum(len(ts) for _, ts in transforms.values())} деревьев в {len(transforms)} "
               f"HISM, мимо Landscape {ground.misses}, пропущено по породам {skipped}, {time.time() - t0:.0f} с")


main()
