"""roads_krom.py — дороги и дорожки у Крома в L_Krom: меши клеток из roads_mesh.py поверх Landscape (D-038).

Запуск (после terrain_krom → heights_krom, landscape_krom — маски изменились; textures_fetch.py — ключ "roads"):
    .venv\\Scripts\\python scripts/roads_mesh.py            # build/roads/roads.json
    python scripts/ue_run.py scripts/roads_krom.py

Клетка roads.json → StaticMesh /Game/Krom/Environment/Roads/SM_Roads_<клетка> через GeometryScript (Nanite, без
коллизии: ходят по Landscape, он на осадку ниже лент), слоты — материалы SLOTS (у всех клеток один список, id слота
в буферах — индекс в нём), UV в полной точности (иначе UV1 разметки в сотнях метров квантуется). Меши — весь Landscape
(roads_mesh.ZONE_M, D-038 с уточнениями 2026-09-27; roads_mesh.MESH_SCOPE = "krom" — только «дорожки у Крома»).
Материалы M_KromRoad<Слот> в /Game/Krom/Materials/Roads — рецепт земли и зданий (D-025, D-027): цвет — палитра
MPC_KromPalette, рисунок — текстура Poly Haven, делённая на свой средний цвет, и та же текстура в MACRO_TILES раз
крупнее против повтора; рельеф — её нормали, шероховатость — её карта Rough, сдвинутая к цели слота. Текстура
кладётся по мировым X, Y (узел WorldPosition), а не по UV меша: стыки клеток и лент не видны, точность UV не важна.
Нормали — в мировом пространстве (у плоских граней наклон из карты, у вертикальных — нормаль грани).
  - asphalt — asphalt_02 (textures.json["roads"]["Asphalt"]), палитра Asphalt; разметка главных улиц — по UV1
    (u — доля ширины от правого края, v — метры вдоль) и цвету вершин (R — полос / 8, G — полос по ходу / 8, B —
    осевая: 1 двойная сплошная, 0,5 прерывистая, 0 — без разметки; A — ширина / 32 м), слегка стёртая;
  - cobble — булыжник cobblestone_floor_08 («Cobble»), палитра Paved;
  - tiles — плитка «кирпичик» pavement_03 («Tiles»), палитра Paved;
  - concrete — бордюр, поребрик, лестницы: асфальт мельче и слабее, палитра Concrete (бетон мостов);
  - gravel, earth — текстуры земли (только цвет), палитры Gravel, Earth; wood — палитра Wood;
  - marking — «зебры»: белая краска × цвет вершин (жёлтые промежутки двухцветной).
Идемпотентен: удаляет свои акторы (тег generated:roads_krom) и ассеты клеток, которых больше нет, переимпортирует
текстуры, пересобирает материалы и меши в те же ассеты и сохраняет.
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
TAG = unreal.Name("generated:roads_krom")
FOLDER = "Generated/roads_krom"
ROADS_DIR = "/Game/Krom/Environment/Roads"
MAT_DIR = "/Game/Krom/Materials/Roads"
TEX_DIR = "/Game/Krom/Environment/Roads/Textures"
ROADS_JSON = os.path.join(geo.REPO, "build", "roads", "roads.json")
TEXTURES = os.path.join(geo.REPO, "refs", "textures", "textures.json")
SLOTS = ("asphalt", "cobble", "tiles", "gravel", "earth", "wood", "concrete", "marking")
MACRO_TILES = 6.7   # крупная вариация: та же текстура в 6,7 раза крупнее (не кратно — узлы не совпадают)
# слот → (группа и роль в textures.json или None, во сколько раз мельче плитка, цвет палитры, доля рисунка, сила крупной
#         вариации, сила рельефа, шероховатость)
MATS = {
    "asphalt": (("roads", "Asphalt"), 1.0, "Asphalt", 1.0, 0.3, 0.6, 0.85),
    "cobble": (("roads", "Cobble"), 1.0, "Paved", 1.0, 0.25, 0.8, 0.75),
    "tiles": (("roads", "Tiles"), 1.0, "Paved", 1.0, 0.25, 0.6, 0.8),
    "gravel": (("textures", "Gravel"), 1.0, "Gravel", 1.0, 0.3, 0.0, 0.95),
    "earth": (("textures", "Earth"), 1.0, "Earth", 1.0, 0.3, 0.0, 0.95),
    "wood": (None, 1.0, "Wood", 1.0, 0.0, 0.0, 0.8),
    "concrete": (("roads", "Asphalt"), 3.0, "Concrete", 0.25, 0.0, 0.3, 0.85),  # × CONCRETE_GAIN
    "marking": (None, 1.0, None, 0.0, 0.0, 0.0, 0.6),
}
MARK_WHITE = (0.75, 0.75, 0.72)   # краска разметки (linear)
# бордюры и поребрики темнее бетона мостов: палитра Concrete (0,34 linear) на солнце читалась белой полосой
# (владелец, снимок у Ольгинского моста); серый бортовой камень ≈0,22 linear (гип.)
CONCRETE_GAIN = 0.65
MARK_W_M, DASH_M = 0.12, (3.0, 6.0)

UV_HLSL = "return WP.xy * {k};"   # мировые см → метры → доли плитки
BASE_HLSL = """
float3 t = D / {mean};
float m = dot(DM / {mean}, float3(0.3333, 0.3333, 0.3334));
return C.rgb * {gain} * lerp(1.0, t, {detail}) * lerp(1.0, m, {macro});
"""
ASPHALT_HLSL = """
float3 t = D / {mean};
float mm = dot(DM / {mean}, float3(0.3333, 0.3333, 0.3334));
float3 c = C.rgb * lerp(1.0, t, {detail}) * lerp(1.0, mm, {macro});
float lanes = round(V.r * 8.0);
if (lanes < 2.0 || V.b <= 0.0) return c;
float w = max(VA * 32.0, 1.0);
float fwd = round(V.g * 8.0);
float m = 0.0;
for (int k = 1; k < 8; k++) {{
    if (k >= lanes) break;
    float d = abs(U1.x - k / lanes) * w;
    float dash = step(frac(U1.y / {period}), {duty});
    if (abs(k - fwd) < 0.5 && V.b > 0.75) {{
        m = max(m, step(abs(d - 0.1), {half_w}));             // двойная сплошная: две линии через 0,2 м
    }} else {{
        m = max(m, step(d, {half_w}) * dash);                  // прерывистая
    }}
}}
float wear = saturate((dot(t, float3(0.333, 0.333, 0.334)) - 0.7) * 2.0) * {wear} * 1.6;
return lerp(c, {paint}, m * (1.0 - wear));
"""
# нормаль в мировом пространстве: у горизонтальных граней — наклон из карты (u — мировой X, v — мировой Y; DirectX:
# зелёный вверх картинки = −v), у вертикальных — нормаль грани
NORMAL_HLSL = "float k = saturate(VN.z); return normalize(VN + k * {strength} * float3(N.x, -N.y, 0.0));"
ROUGH_HLSL = "return saturate({rough} + R - {rough_mean});"

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
mel = unreal.MaterialEditingLibrary
P = unreal.MaterialProperty
X = palette_krom.expr
GS = unreal.GeometryScript_MeshEdits
F2 = unreal.CustomMaterialOutputType.CMOT_FLOAT2
F1 = unreal.CustomMaterialOutputType.CMOT_FLOAT1


def textures(tinfo):
    """Карты ролей из textures.json → текстуры T_Road<Роль>_{D,N,R} (группа roads) и T_RoadGround<Роль>_D (земля)
    в TEX_DIR (есть — переимпорт)."""
    out = {}
    for spec in {m[0] for m in MATS.values() if m[0]}:
        group, role = spec
        maps = tinfo[group][role]["maps"]
        name = f"T_Road{role}" if group == "roads" else f"T_RoadGround{role}"
        t = {"D": palette_krom.import_texture(os.path.join(geo.REPO, maps["Diffuse"]), TEX_DIR, f"{name}_D", "color")}
        if "nor_dx" in maps:
            t["N"] = palette_krom.import_texture(os.path.join(geo.REPO, maps["nor_dx"]), TEX_DIR, f"{name}_N", "normal")
        rough = maps.get("Rough") or maps.get("arm")
        if rough:
            t["R"] = palette_krom.import_texture(os.path.join(geo.REPO, rough), TEX_DIR, f"{name}_R", "linear")
            t["R_channel"] = "R" if "Rough" in maps else "G"
        out[spec] = t
    return out


def sample(mat, x, y, texture, kind, uv):
    s = X(mat, unreal.MaterialExpressionTextureSample, x, y, texture=texture, sampler_type=palette_krom.SAMPLER[kind])
    mel.connect_material_expressions(uv, "", s, "UVs")
    return s


def material(slot, mpc, tinfo, tex, wear):
    spec, scale, color, detail, macro, strength, rough = MATS[slot]
    mat = palette_krom.fresh_material(f"{MAT_DIR}/M_KromRoad{slot.capitalize()}")
    vec = palette_krom.hlsl_vec
    rough_node = X(mat, unreal.MaterialExpressionConstant, -400, 300, r=rough)
    if slot == "marking":
        base = palette_krom.custom(mat, -400, -200, f"return {vec(MARK_WHITE)} * V.rgb;",
                                   [("V", X(mat, unreal.MaterialExpressionVertexColor, -900, -200), "")],
                                   description="KromMarking")
    elif spec is None:
        base = palette_krom.param(mat, mpc, color, -400, -200)
    else:
        e, t = tinfo[spec[0]][spec[1]], tex[spec]
        wp = X(mat, unreal.MaterialExpressionWorldPosition, -1700, 0)
        k = scale / e["tile_m"] / 100.0
        uv = palette_krom.custom(mat, -1400, -100, UV_HLSL.format(k=k), [("WP", wp, "")], output=F2,
                                 description="KromRoadUV")
        uvm = palette_krom.custom(mat, -1400, -400, UV_HLSL.format(k=k / MACRO_TILES), [("WP", wp, "")], output=F2,
                                  description="KromRoadUVMacro")
        d = sample(mat, -1000, -200, t["D"], "color", uv)
        dm = sample(mat, -1000, -450, t["D"], "color", uvm)
        mean = vec(e["mean_linear"])
        ins = [("C", palette_krom.param(mat, mpc, color, -1000, -650), ""), ("D", d, "RGB"), ("DM", dm, "RGB")]
        if slot == "asphalt":
            vc = X(mat, unreal.MaterialExpressionVertexColor, -1000, 0)
            # выход «» узла VertexColor — только RGB (float3): альфа (ширина полотна) идёт отдельным входом VA
            ins += [("V", vc, ""), ("VA", vc, "A"),
                    ("U1", X(mat, unreal.MaterialExpressionTextureCoordinate, -1000, 150, coordinate_index=1), "")]
            code = ASPHALT_HLSL.format(mean=mean, detail=detail, macro=macro, period=sum(DASH_M),
                                       duty=DASH_M[0] / sum(DASH_M), half_w=MARK_W_M / 2, wear=wear,
                                       paint=vec(MARK_WHITE))
        else:
            code = BASE_HLSL.format(mean=mean, detail=detail, macro=macro,
                                    gain=CONCRETE_GAIN if slot == "concrete" else 1.0)
        base = palette_krom.custom(mat, -400, -200, code, ins, description=f"KromRoad{slot.capitalize()}")
        if "N" in t and strength > 0:
            n = sample(mat, -1000, 350, t["N"], "normal", uv)
            vn = X(mat, unreal.MaterialExpressionVertexNormalWS, -1000, 550)
            normal = palette_krom.custom(mat, -400, 150, NORMAL_HLSL.format(strength=strength),
                                         [("N", n, "RGB"), ("VN", vn, "")], description="KromRoadNormal")
            mat.set_editor_property("tangent_space_normal", False)
            mel.connect_material_property(normal, "", P.MP_NORMAL)
        if "R" in t:
            r = sample(mat, -1000, 750, t["R"], "linear", uv)
            rough_node = palette_krom.custom(mat, -400, 350,
                                             ROUGH_HLSL.format(rough=rough, rough_mean=e.get("rough_mean", rough)),
                                             [("R", r, t["R_channel"])], output=F1, description="KromRoadRough")
    mel.connect_material_property(base, "", P.MP_BASE_COLOR)
    mel.connect_material_property(rough_node, "", P.MP_ROUGHNESS)
    mat.set_editor_property("used_with_nanite", True)
    mel.recompile_material(mat)
    assets.save_loaded_asset(mat)
    return mat


def dynamic_mesh(cell):
    dm = unreal.DynamicMesh()
    for mid, key in enumerate(SLOTS):
        p = cell["parts"].get(key)
        if not p:
            continue
        buf = unreal.GeometryScriptSimpleMeshBuffers()
        buf.set_editor_property("vertices", [unreal.Vector(x * 100, y * 100, z * 100) for x, y, z in p["v"]])
        buf.set_editor_property("normals", [unreal.Vector(*n) for n in p["n"]])
        buf.set_editor_property("uv0", [unreal.Vector2D(u, v) for u, v in p["uv"]])
        try:  # UV1 — для разметки; нет в этой версии буферов — разметки не будет, остальное соберётся
            buf.set_editor_property("uv1", [unreal.Vector2D(u, v) for u, v in p["uv1"]])
        except Exception as ex:  # noqa: BLE001
            unreal.log_warning(f"[roads_krom] uv1: {ex}")
        buf.set_editor_property("vertex_colors", [unreal.LinearColor(*c) for c in p["c"]])
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
                 ("new_materials", [mats[k] for k in SLOTS]),
                 ("new_material_slot_names", [unreal.Name(k) for k in SLOTS])):
        opts.set_editor_property(k, v)
    unreal.GeometryScript_AssetUtils.copy_mesh_to_static_mesh(dm, sm, opts, unreal.GeometryScriptMeshWriteLOD())
    try:  # UV в полной точности: UV1 разметки — сотни метров, в половинной точности штрихи дрожат
        bs = meshes.get_lod_build_settings(sm, 0)
        bs.set_editor_property("use_full_precision_u_vs", True)
        meshes.set_lod_build_settings(sm, 0, bs)
    except Exception as ex:  # noqa: BLE001
        unreal.log_warning(f"[roads_krom] full precision UVs: {ex}")
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
    with open(ROADS_JSON, encoding="utf-8") as f:
        roads = json.load(f)
    with open(TEXTURES, encoding="utf-8") as f:
        tinfo = json.load(f)
    if "roads" not in tinfo:
        raise RuntimeError(f"в {TEXTURES} нет ключа roads — сначала textures_fetch.py")
    for a in actors.get_all_level_actors():
        if TAG in a.tags:
            actors.destroy_actor(a)
    mpc = palette_krom.collection()
    wear = roads["params"].get("marking_wear", 0.35)
    tex = textures(tinfo)
    mats = {slot: material(slot, mpc, tinfo, tex, wear) for slot in SLOTS}
    names = {f"SM_Roads_{c['name']}" for c in roads["cells"]}
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    for ad in reg.get_assets_by_path(ROADS_DIR, recursive=False):
        if str(ad.asset_name).startswith("SM_Roads_") and str(ad.asset_name) not in names:
            assets.delete_asset(str(ad.package_name))
    tris = 0
    for cell in roads["cells"]:
        sm = write_asset(dynamic_mesh(cell), f"{ROADS_DIR}/SM_Roads_{cell['name']}", mats)
        ox, oy = cell["origin"]
        a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(ox * 100, oy * 100, 0))
        a.set_actor_label(f"Roads {cell['name']}")
        a.set_folder_path(FOLDER)
        a.set_editor_property("tags", [TAG])
        a.set_editor_property("is_spatially_loaded", False)
        a.static_mesh_component.set_static_mesh(sm)
        tris += cell["triangles"]
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    s = roads["stats"]
    unreal.log(f"[roads_krom] done: {len(roads['cells'])} клеток, {tris} треугольников (набор {s['mesh_scope']}), "
               f"{time.time() - t0:.0f} с")


main()
