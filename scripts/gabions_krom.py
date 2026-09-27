"""gabions_krom.py — габионы на левом берегу Псковы вдоль Крома (M5, D-034).

Запуск:  python scripts/ue_run.py scripts/gabions_krom.py

Набережная Псковы от Высокой башни до Троицкого (Советского) моста реконструирована в 2014 г.: «берег укреплён
габионами» (акт ГИКЭ S-49, с. 13, 17); на фото 2013–2021 (S-51) — стенка в один ярус ≈1 м вдоль тропы со стороны
воды, ниже травяная берма и галька у уреза. У пешеходного моста 2024 г. — ступенчатые габионы в 2–3 яруса
(фото S-50). Под западной стеной у Великой габионов нет (там галька и валуны — полоса у уреза, D-029).

Стенка идёт по тропе OSM 66789566 (от Стрелки до PATH_END_X) со стороны воды: сторона — к ближайшей точке береговой
линии OSM 304637991. Это подпорная стенка, а не парапет (владелец: «как будто приделаны сбоку… висят в воздухе»; фото
env10, env11): верх — вровень с землёй у края тропы (трасса по Landscape у внутренней грани), лицо к воде ≈1 м на ярус,
низ — земля бермы за лицом (трасса) минус EMBED_M, чтобы короба не висели. Рельеф под это сечение строит
terrain_krom.pskova_terrace (D-037, D-038): внутренняя грань IN_M от оси тропы, ярус DEPTH_M × 1 м, за лицом — берма.
Короба UNIT_M по длине; у устоя моста 2024 г. — ступени в STEPS ярусов.
Меш — GeometryScript (Nanite), материал — серый камень (текстура наброски Gray Rocks, палитра Riprap) с тёмными
рёбрами коробов по UV в метрах.

Идемпотентен: удаляет свой актор (тег generated:gabions_krom), пересобирает меш в тот же ассет и сохраняет.
"""
import importlib
import json
import math
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402
import palette_krom  # noqa: E402
import wall_mesh  # noqa: E402

importlib.reload(palette_krom)
wm = importlib.reload(wall_mesh)

LEVEL = "/Game/Krom/Maps/L_Krom"
TAG = unreal.Name("generated:gabions_krom")
FOLDER = "Generated/gabions_krom"
ASSET = "/Game/Krom/Environment/Bridges/SM_Gabions_Pskova"
MAT = "/Game/Krom/Materials/Bridges/M_KromGabion"
RIPRAP_TEX = "/Game/Krom/Environment/Terrain/T_GroundRiprap_D"
TEXTURES = os.path.join(geo.REPO, "refs", "textures", "textures.json")
PATH_ID, BANK_ID = 66789566, 304637991
PATH_END_X = -62.0         # стенка до Советского моста (S-49: «до Троицкого моста»)
IN_M = 1.7                 # внутренняя грань от оси тропы: тропа 3 м (osm_layers.WAY_WIDTH) + 0,2 м газона
                           # (как terrain_krom.GABION_IN_M)
UNIT_M, DEPTH_M, TIER_M = 2.0, 1.0, 1.0  # короб: длина, толщина, высота яруса (типовой габион 2 × 1 × 1 м)
EMBED_M = 0.3              # низ короба — на столько ниже земли за лицом (не висит, если Landscape огрубил сетку)
STEPS_AT, STEPS_R_M, STEPS = (224.4, -11.8), 25.0, 3  # ступени у устоя моста 2024: центр, радиус, ярусов (S-50)
WIRE_M = 0.03              # тёмные рёбра коробов
TRACE_Z_M = 300.0

GABION_HLSL = """
float3 c = C.rgb * D / {mean};
float2 f = frac(U / float2({unit}, 1.0));
float2 e = min(f, 1.0 - f) * float2({unit}, 1.0);
float wire = 1.0 - step({wire}, min(e.x, e.y));
return lerp(c, c * 0.35, wire);
"""

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
mel = unreal.MaterialEditingLibrary
GS = unreal.GeometryScript_MeshEdits


def ground(world, x, y):
    ignore = []
    for _ in range(6):
        hit = unreal.SystemLibrary.line_trace_single(
            world, unreal.Vector(x * 100, y * 100, TRACE_Z_M * 100), unreal.Vector(x * 100, y * 100, -TRACE_Z_M * 100),
            unreal.TraceTypeQuery.ECC_VISIBILITY, True, ignore, unreal.DrawDebugTrace.NONE, True)
        if hit is None:
            return None
        t = hit.to_tuple()
        if isinstance(t[9], unreal.LandscapeProxy):
            return t[5].z / 100.0
        ignore.append(t[9])
    return None


def resample(line, step):
    """Точки ломаной через step м."""
    out, carry = [line[0]], 0.0
    for a, b in zip(line, line[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        s = step - carry
        while s <= d:
            out.append((a[0] + (b[0] - a[0]) * s / d, a[1] + (b[1] - a[1]) * s / d))
            s += step
        carry = d - (s - step)
    return out


def nearest(p, line):
    best, bd = None, 1e18
    for a, b in zip(line, line[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy or 1e-9
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
        q = (a[0] + dx * t, a[1] + dy * t)
        d = (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2
        if d < bd:
            best, bd = q, d
    return best


def unit_box(mesh, a, b, side, off0, off1, zb, zt):
    """Короб от a до b по тропе, поперёк — от off0 до off1 м в сторону side (единичный вектор к воде)."""
    c = [(a[0] + side[0] * off0, a[1] + side[1] * off0), (b[0] + side[0] * off0, b[1] + side[1] * off0),
         (b[0] + side[0] * off1, b[1] + side[1] * off1), (a[0] + side[0] * off1, a[1] + side[1] * off1)]
    pts = [(x, y, zb) for x, y in c] + [(x, y, zt) for x, y in c]
    mid = tuple(sum(q[i] for q in pts) / 8 for i in range(3))
    for f in ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        q = [pts[i] for i in f]
        fc = tuple(sum(p[i] for p in q) / 4 for i in range(3))
        mesh.quad("gabion", q, tuple(fc[i] - mid[i] for i in range(3)))


def build(world, path, bank):
    mesh = wm.Mesh()
    pts = resample(path, UNIT_M)
    units = 0
    for a, b in zip(pts, pts[1:]):
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        tx, ty = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tx, ty) or 1.0
        n = (-ty / L, tx / L)
        q = nearest(m, bank)
        if (q[0] - m[0]) * n[0] + (q[1] - m[1]) * n[1] < 0:
            n = (-n[0], -n[1])
        steps = STEPS if math.hypot(m[0] - STEPS_AT[0], m[1] - STEPS_AT[1]) <= STEPS_R_M else 1
        # верх — земля у внутренней грани (край тропы), низ последнего яруса — земля за лицом
        top = ground(world, m[0] + n[0] * (IN_M - 0.1), m[1] + n[1] * (IN_M - 0.1))
        face = IN_M + steps * DEPTH_M + 0.3
        foot = ground(world, m[0] + n[0] * face, m[1] + n[1] * face)
        if top is None:
            continue
        for k in range(steps):  # ярусы: каждый на TIER_M ниже и на DEPTH_M ближе к воде
            zt = top - k * TIER_M
            zb = zt - TIER_M
            if k == steps - 1 and foot is not None:
                zb = min(zb, foot)
            unit_box(mesh, a, b, n, IN_M + k * DEPTH_M, IN_M + (k + 1) * DEPTH_M, zb - EMBED_M, zt)
            units += 1
    return mesh, units


def material(mpc):
    with open(TEXTURES, encoding="utf-8") as f:
        info = json.load(f)["textures"]["Riprap"]
    mat = palette_krom.fresh_material(MAT)
    X = palette_krom.expr
    uv = X(mat, unreal.MaterialExpressionTextureCoordinate, -1200, 0)
    inv = 1.0 / info["tile_m"]
    uvt = X(mat, unreal.MaterialExpressionTextureCoordinate, -1200, -200, u_tiling=inv, v_tiling=inv)
    d = X(mat, unreal.MaterialExpressionTextureSample, -900, -200, texture=unreal.load_asset(RIPRAP_TEX),
          sampler_type=palette_krom.SAMPLER["color"])
    mel.connect_material_expressions(uvt, "", d, "UVs")
    code = GABION_HLSL.format(mean=palette_krom.hlsl_vec(info["mean_linear"]), unit=UNIT_M, wire=WIRE_M)
    base = palette_krom.custom(mat, -450, -200, code, [("D", d, "RGB"), ("U", uv, ""),
                                                       ("C", palette_krom.param(mat, mpc, "Riprap", -900, -400), "")],
                               description="KromGabion")
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(X(mat, unreal.MaterialExpressionConstant, -450, 100, r=0.9), "",
                                  unreal.MaterialProperty.MP_ROUGHNESS)
    mat.set_editor_property("used_with_nanite", True)
    mel.recompile_material(mat)
    assets.save_loaded_asset(mat)
    return mat


def write_asset(mesh, origin, mat):
    dm = unreal.DynamicMesh()
    ox, oy = origin
    verts, norms, uvs, tris = mesh.parts["gabion"]
    buf = unreal.GeometryScriptSimpleMeshBuffers()
    buf.set_editor_property("vertices", [unreal.Vector((x - ox) * 100, (y - oy) * 100, z * 100) for x, y, z in verts])
    buf.set_editor_property("normals", [unreal.Vector(*n) for n in norms])
    buf.set_editor_property("uv0", [unreal.Vector2D(u, v) for u, v in uvs])
    buf.set_editor_property("triangles", [unreal.IntVector(*t) for t in tris])
    GS.append_buffers_to_mesh(dm, buf, material_id=0)
    if not assets.does_asset_exist(ASSET):
        opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
        opts.set_editor_property("enable_recompute_normals", False)
        unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, ASSET, opts)
    sm = unreal.load_asset(ASSET)
    opts = unreal.GeometryScriptCopyMeshToAssetOptions()
    for k, v in (("enable_recompute_normals", False), ("replace_materials", True), ("new_materials", [mat]),
                 ("new_material_slot_names", [unreal.Name("gabion")])):
        opts.set_editor_property(k, v)
    unreal.GeometryScript_AssetUtils.copy_mesh_to_static_mesh(dm, sm, opts, unreal.GeometryScriptMeshWriteLOD())
    meshes.remove_collisions(sm)
    sm.get_editor_property("body_setup").set_editor_property(
        "collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    ns = sm.get_editor_property("nanite_settings")
    ns.set_editor_property("enabled", True)
    sm.set_editor_property("nanite_settings", ns)
    assets.save_loaded_asset(sm)
    return sm


def main():
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split(".")[0] != LEVEL:
        levels.load_level(LEVEL)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    for a in actors.get_all_level_actors():
        if TAG in a.tags:
            actors.destroy_actor(a)
    els = {e["id"]: e for e in geo.load_elements(geo.latest("krom_2*.json"))}
    path = geo.local_points(els[PATH_ID]["geometry"])
    cut = next((i for i, p in enumerate(path) if p[0] < PATH_END_X), len(path))
    path = path[:cut]
    bank = geo.local_points(els[BANK_ID]["geometry"])
    mesh, units = build(world, path, bank)
    sm = write_asset(mesh, path[0], material(palette_krom.collection()))
    a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(path[0][0] * 100, path[0][1] * 100, 0))
    a.set_actor_label("Габионы Псковы")
    a.set_folder_path(FOLDER)
    a.set_editor_property("tags", [TAG])
    a.set_editor_property("is_spatially_loaded", False)
    a.static_mesh_component.set_static_mesh(sm)
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    length = sum(math.hypot(b[0] - a_[0], b[1] - a_[1]) for a_, b in zip(path, path[1:]))
    unreal.log(f"[gabions_krom] done: {length:.0f} м по тропе, коробов {units}, треугольников {mesh.triangles()}")


main()
