"""landscape_krom.py — Landscape в L_Krom: материал земли по маске покрытия OSM и вода на уровне уреза (M1, M4).

Запуск:  python scripts/ue_run.py scripts/landscape_krom.py
Нужно: .venv\\Scripts\\python scripts/terrain_krom.py (heightmap, маска покрытия, параметры),
.venv\\Scripts\\python scripts/textures_fetch.py (текстуры Poly Haven), horizon_krom.py (маска T_HorizonMask —
для края Landscape) и Landscape в L_Krom, импортированный из refs/dem/heightmap_L_Krom.png (scripts/README.md).

Материал M_KromLandscape (D-025):
  - покрытие — маска T_KromGroundMask из OSM по мировым XY (terrain_krom.render_mask): R — грунт, G — мощение,
    B — асфальт, A — здания, остальное — трава; вторая маска T_KromGroundMask2 (D-029): R — отсев троп, G — песок
    и галька у уреза, B — каменная наброска, A — деревянные настилы (текстура тёса зданий);
  - цвет — из общей палитры MPC_KromPalette (palette_krom), рисунок — тайловые текстуры Poly Haven, делённые на
    свой средний цвет (textures_fetch.py): издалека земля ровно цвета палитры;
  - трава — с крупными пятнами (та же текстура в MACRO_SCALE раз крупнее); на крутых откосах и у уреза — грунт;
  - край Landscape (EDGE_FROM_M → EDGE_TO_M от собора) плавно переходит в вид кольца горизонта: та же маска
    WorldCover и те же цвета, поэтому на стыке нет прямой линии.
Смешение — один узел Custom (HLSL в LAND_HLSL): граф из сотни узлов в Python не читается.

Идемпотентен: переимпортирует текстуры, пересобирает материалы, пересоздаёт свои акторы (тег
generated:landscape_krom) и сохраняет всё изменённое. Сам Landscape не пересоздаёт — только назначает материал.
"""
import importlib
import json
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402
import palette_krom  # noqa: E402

importlib.reload(palette_krom)

LEVEL = "/Game/Krom/Maps/L_Krom"
TAG = unreal.Name("generated:landscape_krom")
FOLDER = "Generated/landscape_krom"
TEX_DIR = "/Game/Krom/Environment/Terrain"
MAT_DIR = "/Game/Krom/Materials/Terrain"
HORIZON_MASK = "/Game/Krom/Environment/Horizon/T_HorizonMask"
META = os.path.join(geo.REPO, "refs", "dem", "heightmap_L_Krom.json")
TEXTURES = os.path.join(geo.REPO, "refs", "textures", "textures.json")
HORIZON = os.path.join(geo.REPO, "build", "horizon", "horizon.json")
# вода на своей отметке выше плотины Финского парка (terrain_krom.pool_water: кольцо и протока лентой; P-1, P-4)
POOLS = os.path.join(geo.REPO, "build", "terrain", "water_pools.json")
WATER_DIR = "/Game/Krom/Environment/Water"

GROUND_ROUGHNESS = 0.9
GROUND_SPECULAR = 0.25     # у кольца 0,1 (блик неба вдали), вблизи 0,1 делает землю матовой, как пластилин
MACRO_SCALE = 23.0         # крупные пятна травы: плитка × 23 (≈46 м), число не кратное, чтобы не совпадали узлы
MACRO_STRENGTH = 0.6
SLOPE_FROM_NZ, SLOPE_RANGE = 0.85, 0.25  # откос круче ≈32° начинает лысеть, к ≈53° — наполовину грунт
SLOPE_EARTH = 0.5
SHORE_M = 0.8              # полоса грунта у уреза: до SHORE_M над водой
EDGE_FROM_M, EDGE_TO_M = 880.0, 1000.0  # переход к виду кольца в последних 120 м (выгрузка OSM кончается за 50–130 м до
                                        # края); было 650…900, пока дороги геометрией шли только до 650 м (2026-09-27)
ROLES = ("Grass", "Earth", "Asphalt", "Paved", "Gravel", "Shore", "Riprap", "Wood")  # текстуры земли в материале
TILE_SCALE = {"Riprap": 3.0}  # у Gray Rocks камни 8–15 см, в натуре наброска 20–60 см (фото S-42)
WOOD_ROLE, WOOD_TEXTURE = "Planks", "/Game/Krom/Architecture/Textures/T_BuildingPlanks_D"  # настилы — тёс зданий

LAND_HLSL = """
float2 xy = WP.xy * 0.01;
float4 m = Texture2DSample(Mask, MaskSampler, xy * {inv_size} + 0.5);
float3 g = Texture2DSample(Grass, GrassSampler, xy * {inv_grass}).rgb / {mean_grass};
float3 gt = Texture2DSample(Grass, GrassSampler, xy * {inv_macro} + 0.37).rgb / {mean_grass};
float gm = (gt.r + gt.g + gt.b) / 3.0;
float3 e = Texture2DSample(Earth, EarthSampler, xy * {inv_earth}).rgb / {mean_earth};
float3 a = Texture2DSample(Asphalt, AsphaltSampler, xy * {inv_asphalt}).rgb / {mean_asphalt};
float3 p = Texture2DSample(Paved, PavedSampler, xy * {inv_paved}).rgb / {mean_paved};
float4 m2 = Texture2DSample(Mask2, Mask2Sampler, xy * {inv_size} + 0.5);
float3 gv = Texture2DSample(Gravel, GravelSampler, xy * {inv_gravel}).rgb / {mean_gravel};
float3 sh = Texture2DSample(Shore, ShoreSampler, xy * {inv_shore}).rgb / {mean_shore};
float3 rr = Texture2DSample(Riprap, RiprapSampler, xy * {inv_riprap}).rgb / {mean_riprap};
float3 wd = Texture2DSample(Wood, WoodSampler, xy * {inv_wood}).rgb / {mean_wood};
float3 c = FieldC.rgb * g * lerp(1.0, gm, {macro});
float slope = saturate(({slope_from} - N.z) / {slope_range});
float shore = saturate(({water_z} + {shore} - WP.z * 0.01) / {shore});
c = lerp(c, EarthC.rgb * e, saturate(m.r + slope * {slope_earth} + shore));
c = lerp(c, GravelC.rgb * gv, m2.r);
c = lerp(c, ShoreC.rgb * sh, m2.g);
c = lerp(c, RiprapC.rgb * rr, m2.b);
c = lerp(c, PavedC.rgb * p, m.g);
c = lerp(c, AsphaltC.rgb * a, m.b);
c = lerp(c, WoodC.rgb * wd, m2.a);
c = lerp(c, BuiltC.rgb * a, m.a);
float edge = smoothstep({edge_from}, {edge_to}, max(abs(xy.x), abs(xy.y)));
float4 h = Texture2DSample(HMask, HMaskSampler, float2(xy.y + {ring_r}, {ring_r} - xy.x) / (2.0 * {ring_r}));
float3 ring = FieldC.rgb + (ForestC.rgb - FieldC.rgb) * h.r + (BuiltC.rgb - FieldC.rgb) * h.g
            + (WaterC.rgb - FieldC.rgb) * h.b;
return lerp(c, ring, edge);
"""

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
mel = unreal.MaterialEditingLibrary


def import_texture(png, name, kind="color"):
    """Текстура в TEX_DIR (palette_krom.import_texture): цветная — sRGB, повтор; маска — linear, BC7, clamp."""
    return palette_krom.import_texture(png, TEX_DIR, name, kind)


def expr(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def hlsl_vec(v):
    return "float3({:.4f}, {:.4f}, {:.4f})".format(*v)


def landscape_material(meta, mpc, tex, tinfo, ring_r):
    """M_KromLandscape: входы узла Custom — позиция, нормаль, маски, текстуры и цвета коллекции."""
    size_m = (meta["size"] - 1) * meta["landscape"]["scale"][0] / 100.0
    t = {**tinfo["textures"], "Wood": tinfo["buildings"][WOOD_ROLE]}
    code = LAND_HLSL.format(
        inv_size=1.0 / size_m, inv_macro=1.0 / (t["Grass"]["tile_m"] * MACRO_SCALE), macro=MACRO_STRENGTH,
        **{f"inv_{k.lower()}": 1.0 / (t[k]["tile_m"] * TILE_SCALE.get(k, 1.0)) for k in ROLES},
        **{f"mean_{k.lower()}": hlsl_vec(t[k]["mean_linear"]) for k in ROLES},
        slope_from=SLOPE_FROM_NZ, slope_range=SLOPE_RANGE, slope_earth=SLOPE_EARTH,
        water_z=meta["water_level_z_m"], shore=SHORE_M, edge_from=EDGE_FROM_M, edge_to=EDGE_TO_M, ring_r=ring_r)

    mat = palette_krom.fresh_material(f"{MAT_DIR}/M_KromLandscape")
    inputs = [("WP", expr(mat, unreal.MaterialExpressionWorldPosition, -700, -300)),
              ("N", expr(mat, unreal.MaterialExpressionVertexNormalWS, -700, -200))]
    masks = unreal.MaterialSamplerType.SAMPLERTYPE_MASKS
    colors = unreal.MaterialSamplerType.SAMPLERTYPE_COLOR
    for i, (name, texture, sampler) in enumerate([("Mask", tex["Mask"], masks), ("Mask2", tex["Mask2"], masks),
                                                   ("HMask", tex["HMask"], masks)]
                                                  + [(k, tex[k], colors) for k in ROLES]):
        inputs.append((name, expr(mat, unreal.MaterialExpressionTextureObject, -700, -100 + 110 * i,
                                  texture=texture, sampler_type=sampler)))
    for i, name in enumerate(("Field", "Forest", "Built", "Water", "Earth", "Asphalt", "Paved", "Gravel", "Shore",
                              "Riprap", "Wood")):
        inputs.append((f"{name}C", palette_krom.param(mat, mpc, name, -700, 600 + 80 * i)))

    custom = expr(mat, unreal.MaterialExpressionCustom, -300, 0, code=code,
                  output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3, description="KromGround")
    ins = []
    for name, _ in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", name)
        ins.append(ci)
    custom.set_editor_property("inputs", ins)
    for name, node in inputs:
        mel.connect_material_expressions(node, "", custom, name)
    mel.connect_material_property(custom, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(expr(mat, unreal.MaterialExpressionConstant, -300, 250, r=GROUND_ROUGHNESS), "",
                                  unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(expr(mat, unreal.MaterialExpressionConstant, -300, 350, r=GROUND_SPECULAR), "",
                                  unreal.MaterialProperty.MP_SPECULAR)
    mel.recompile_material(mat)
    assets.save_loaded_asset(mat)
    return mat


def spawn_water(meta, mat):
    size_m = (meta["size"] - 1) * meta["landscape"]["scale"][0] / 100.0
    a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, meta["water_level_z_m"] * 100.0))
    a.set_actor_label("Water")
    a.set_folder_path(FOLDER)
    a.set_editor_property("tags", [TAG])
    a.set_editor_property("is_spatially_loaded", False)
    smc = a.static_mesh_component
    smc.set_static_mesh(unreal.load_asset("/Engine/BasicShapes/Plane"))
    smc.set_material(0, mat)
    smc.set_collision_profile_name("NoCollision")  # set_collision_enabled в редакторе не сохраняется
    smc.set_editor_property("cast_shadow", False)
    a.set_actor_scale3d(unreal.Vector(size_m, size_m, 1))  # Plane = 1 × 1 м
    return a


def triangulate(ring):
    """Ушная триангуляция простого многоугольника ring [(x, y)] → тройки индексов."""
    pts = list(ring)
    area = sum(pts[i - 1][0] * pts[i][1] - pts[i][0] * pts[i - 1][1] for i in range(len(pts))) / 2  # формула шнурка
    idx = list(range(len(pts))) if area < 0 else list(range(len(pts)))[::-1]  # обход по часовой в осях (x, y):
    tris = []                                                                 # у «ушей» векторное произведение < 0

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def inside(p, a, b, c):
        return cross(a, b, p) <= 0 and cross(b, c, p) <= 0 and cross(c, a, p) <= 0

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if cross(a, b, c) >= 0:
                continue
            if any(inside(pts[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


def water_surface(name, verts, tris, z_m, mat):
    """Плоский меш воды verts [(x, y)] м, tris — тройки; ассет WATER_DIR/SM_Water_<name>, актор на Z = z_m."""
    dm = unreal.DynamicMesh()
    buf = unreal.GeometryScriptSimpleMeshBuffers()
    buf.set_editor_property("vertices", [unreal.Vector(x * 100, y * 100, 0.0) for x, y in verts])
    buf.set_editor_property("normals", [unreal.Vector(0, 0, 1)] * len(verts))
    buf.set_editor_property("uv0", [unreal.Vector2D(x, y) for x, y in verts])
    def up(t):  # лицом вверх в UE: в осях плана (x, y) обход по часовой (так же Part.tri в roads_mesh)
        (ax, ay), (bx, by), (cx, cy) = (verts[i] for i in t)
        return t if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) < 0 else (t[0], t[2], t[1])
    buf.set_editor_property("triangles", [unreal.IntVector(*up(t)) for t in tris])
    unreal.GeometryScript_MeshEdits.append_buffers_to_mesh(dm, buf, material_id=0)
    path = f"{WATER_DIR}/SM_Water_{name}"
    if not assets.does_asset_exist(path):
        opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
        opts.set_editor_property("enable_recompute_normals", False)
        unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, path, opts)
    sm = unreal.load_asset(path)
    opts = unreal.GeometryScriptCopyMeshToAssetOptions()
    for k, v in (("enable_recompute_normals", False), ("replace_materials", True), ("new_materials", [mat])):
        opts.set_editor_property(k, v)
    unreal.GeometryScript_AssetUtils.copy_mesh_to_static_mesh(dm, sm, opts, unreal.GeometryScriptMeshWriteLOD())
    unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem).remove_collisions(sm)
    assets.save_loaded_asset(sm)
    a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, z_m * 100.0))
    a.set_actor_label(f"Water {name}")
    a.set_folder_path(FOLDER)
    a.set_editor_property("tags", [TAG])
    a.set_editor_property("is_spatially_loaded", False)
    smc = a.static_mesh_component
    smc.set_static_mesh(sm)
    smc.set_collision_profile_name("NoCollision")
    smc.set_editor_property("cast_shadow", False)
    return a


def spawn_pools(mat):
    """Вода выше плотины (POOLS): кольцо — многоугольником, протока — лентой; нет файла — только предупреждение."""
    if not os.path.exists(POOLS):
        unreal.log_warning(f"[landscape_krom] нет {POOLS} — сначала terrain_krom.py; вода выше плотины не построена")
        return []
    with open(POOLS, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for p in data.get("pools", []):
        ring = [tuple(v) for v in p["ring"]]
        out.append(water_surface(p["name"], ring, triangulate(ring), p["z_m"], mat))
    for r in data.get("ribbons", []):
        pts, half = r["pts"], r["width_m"] / 2
        verts, tris = [], []
        for i, (x, y) in enumerate(pts):
            a, b = pts[max(i - 1, 0)], pts[min(i + 1, len(pts) - 1)]
            dx, dy = b[0] - a[0], b[1] - a[1]
            n = (dx * dx + dy * dy) ** 0.5 or 1.0
            lx, ly = dy / n, -dx / n            # левая нормаль (ty, −tx)
            verts += [(x + lx * half, y + ly * half), (x - lx * half, y - ly * half)]
            if i:
                k = 2 * i
                tris += [(k - 2, k, k + 1), (k - 2, k + 1, k - 1)]
        out.append(water_surface(r["name"], verts, tris, r["z_m"], mat))
    return out


def main():
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split(".")[0] != LEVEL:
        levels.load_level(LEVEL)
    with open(META, encoding="utf-8") as f:
        meta = json.load(f)
    with open(TEXTURES, encoding="utf-8") as f:
        tinfo = json.load(f)
    with open(HORIZON, encoding="utf-8") as f:
        ring_r = json.load(f)["radius_m"]
    if not assets.does_asset_exist(HORIZON_MASK):
        raise RuntimeError(f"нет {HORIZON_MASK} — сначала horizon_krom.py")
    landscapes = [a for a in actors.get_all_level_actors() if isinstance(a, unreal.Landscape)]
    if len(landscapes) != 1:
        raise RuntimeError(f"в {LEVEL} ожидается ровно один Landscape, найдено {len(landscapes)} — "
                           "сначала импортируйте heightmap (scripts/README.md)")
    for a in actors.get_all_level_actors():
        if TAG in a.tags:
            actors.destroy_actor(a)

    mpc = palette_krom.collection()
    tex = {"Mask": import_texture(os.path.join(geo.REPO, meta["mask_texture"]), "T_KromGroundMask", kind="mask"),
           "Mask2": import_texture(os.path.join(geo.REPO, meta["mask2_texture"]), "T_KromGroundMask2", kind="mask"),
           "HMask": unreal.load_asset(HORIZON_MASK)}
    lost = [r for r in ROLES if r != "Wood" and r not in tinfo["textures"]]
    if lost:
        raise RuntimeError(f"в {TEXTURES} нет текстур земли {lost} — сначала textures_fetch.py")
    for role, e in tinfo["textures"].items():
        tex[role] = import_texture(os.path.join(geo.REPO, e["maps"]["Diffuse"]), f"T_Ground{role}_D")
    if not assets.does_asset_exist(WOOD_TEXTURE):
        raise RuntimeError(f"нет {WOOD_TEXTURE} — сначала materials_krom.py")
    tex["Wood"] = unreal.load_asset(WOOD_TEXTURE)
    land_mat = landscape_material(meta, mpc, tex, tinfo, ring_r)
    landscapes[0].set_editor_property("landscape_material", land_mat)
    water_mat = palette_krom.water_material(mpc)
    spawn_water(meta, water_mat)
    pools = spawn_pools(water_mat)

    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    unreal.log(f"[landscape_krom] water above the dam: {len(pools)} surfaces")
    unreal.log(f"[landscape_krom] done: water Z = {meta['water_level_z_m']} m, "
               f"Z = 0 = {meta['z0_abs_m']} m abs, mask {meta['mask_texture']}")


main()
