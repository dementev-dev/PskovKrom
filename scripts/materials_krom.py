"""materials_krom.py — материалы зданий: плитняк, побелка, тёс, металлы, стекло (M4, D-027).

Запуск:  python scripts/ue_run.py scripts/materials_krom.py
Нужно: .venv\\Scripts\\python scripts/textures_fetch.py (текстуры зданий — ключ "buildings" в textures.json),
герои и стены в /Game/Krom/Architecture (heroes_krom.py, walls_krom.py).

Материал на каждый ключ krom_plan.COLORS из MATS — M_Krom<Ключ> в /Game/Krom/Materials/Buildings, по рецепту земли
(D-025): цвет — параметр <Ключ> общей палитры MPC_KromPalette (palette_krom), рисунок — текстура Poly Haven,
делённая на свой средний цвет, рельеф — её нормали, шероховатость — её карта Rough, сдвинутая к своей цели.
Издалека здание ровно цвета палитры. Повтор плитки на длинной стене гасит та же текстура в MACRO_TILES раз крупнее.
UV героев и стен — в метрах (bl_krom.box_uv, wall_mesh), поэтому плитка текстуры = tile_m из textures.json.
Металлы, стекло и крашеные кровли — без текстур: цвет из палитры, металличность и шероховатость — константы MATS.

Потом слоты всех StaticMesh в /Game/Krom/Architecture получают материал по имени слота (= ключ цвета): геометрия
не пересобирается. heroes_krom.py и walls_krom.py при пересборке берут те же материалы
(palette_krom.building_material), пока их нет — MI_BO_*.

Идемпотентен: переимпортирует текстуры, пересобирает материалы в те же ассеты, переназначает слоты и сохраняет.
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

TEX_DIR = "/Game/Krom/Architecture/Textures"
ARCH_DIR = "/Game/Krom/Architecture"
STAGING = "/Game/Krom/Architecture/_import"   # временная папка heroes_krom
TEXTURES = os.path.join(geo.REPO, "refs", "textures", "textures.json")

MACRO_TILES = 6.7   # крупная вариация: та же текстура в 6,7 раза крупнее (не кратно, чтобы узлы не совпадали)

# ключ COLORS → роль текстуры в textures.json["buildings"] (нет — без текстуры) и константы:
#   rough — средняя шероховатость, detail — сколько цветового рисунка текстуры оставить (1 — весь),
#   macro — сила крупной вариации, normal — сила рельефа, metallic, specular
MATS = {
    "stone": dict(tex="Stone", rough=0.85, detail=1.0, macro=0.35, normal=0.65),    # открытый плитняк: швы
    # в Крому залиты раствором, а у rock_wall_08 камни «подушками» (средний наклон нормали 22°)
    "wall": dict(tex="Whitewash", rough=0.9, detail=0.7, macro=0.25, normal=0.4),   # белёный плитняк
    "wood": dict(tex="Planks", rough=0.8, detail=1.0, macro=0.3, normal=1.0),       # тёс
    "green": dict(rough=0.45),     # крашеные кровли собора и колокольни
    "roof": dict(rough=0.5),
    "dark": dict(rough=0.4),       # тёмные главы
    "copper": dict(rough=0.6),     # медь под патиной — патина не металл
    "gold": dict(metallic=1.0, rough=0.25),
    "tin": dict(metallic=1.0, rough=0.45),   # оцинковка
    "bronze": dict(metallic=0.6, rough=0.5),  # колокола, тёмные
    "glass": dict(rough=0.08),
}
DEFAULTS = dict(tex=None, rough=0.8, detail=1.0, macro=0.3, normal=1.0, metallic=0.0, specular=0.5)

BASE_HLSL = """
float3 t = D / {mean};
float m = dot(DM / {mean}, float3(0.3333, 0.3333, 0.3334));
return C.rgb * lerp(1.0, t, {detail}) * lerp(1.0, m, {macro});
"""
NORMAL_HLSL = "return normalize(float3(N.xy * {strength}, N.z));"
ROUGH_HLSL = "return saturate({rough} + R - {rough_mean});"

assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
mel = unreal.MaterialEditingLibrary
P = unreal.MaterialProperty


def const(mat, x, y, v):
    return palette_krom.expr(mat, unreal.MaterialExpressionConstant, x, y, r=v)


def sample(mat, x, y, texture, kind, uv):
    s = palette_krom.expr(mat, unreal.MaterialExpressionTextureSample, x, y, texture=texture,
                          sampler_type=palette_krom.SAMPLER[kind])
    mel.connect_material_expressions(uv, "", s, "UVs")
    return s


def import_role(role, e):
    """Карты роли из textures.json → текстуры T_Building<Роль>_{D,N,R}; Rough или arm (шероховатость — G)."""
    maps = e["maps"]
    out = {"D": palette_krom.import_texture(os.path.join(geo.REPO, maps["Diffuse"]), TEX_DIR,
                                            f"T_Building{role}_D", "color"),
           "N": palette_krom.import_texture(os.path.join(geo.REPO, maps["nor_dx"]), TEX_DIR,
                                            f"T_Building{role}_N", "normal")}
    rough = maps.get("Rough") or maps.get("arm")
    out["R"] = palette_krom.import_texture(os.path.join(geo.REPO, rough), TEX_DIR, f"T_Building{role}_R", "linear")
    out["R_channel"] = "R" if "Rough" in maps else "G"
    return out


def build(key, spec, mpc, tex, tinfo):
    """M_Krom<Ключ>: с текстурой — рисунок, рельеф и шероховатость; без — цвет палитры и константы."""
    name = palette_krom.building_key(key)
    mat = palette_krom.fresh_material(f"{palette_krom.BUILDING_DIR}/M_Krom{name}")
    color = palette_krom.param(mat, mpc, name, -700, -300)
    if spec["tex"]:
        t, e = tex[spec["tex"]], tinfo[spec["tex"]]
        inv = 1.0 / e["tile_m"]
        uv = palette_krom.expr(mat, unreal.MaterialExpressionTextureCoordinate, -1300, 0, u_tiling=inv, v_tiling=inv)
        uvm = palette_krom.expr(mat, unreal.MaterialExpressionTextureCoordinate, -1300, -300,
                                u_tiling=inv / MACRO_TILES, v_tiling=inv / MACRO_TILES)
        d = sample(mat, -1000, -150, t["D"], "color", uv)
        dm = sample(mat, -1000, -450, t["D"], "color", uvm)
        mean = palette_krom.hlsl_vec(e["mean_linear"])
        base = palette_krom.custom(mat, -400, -300, BASE_HLSL.format(mean=mean, detail=spec["detail"],
                                                                     macro=spec["macro"]),
                                   [("D", d, "RGB"), ("DM", dm, "RGB"), ("C", color, "")], description="KromBase")
        n = sample(mat, -1000, 150, t["N"], "normal", uv)
        normal = palette_krom.custom(mat, -400, 150, NORMAL_HLSL.format(strength=spec["normal"]),
                                     [("N", n, "RGB")], description="KromNormal")
        r = sample(mat, -1000, 450, t["R"], "linear", uv)
        rough = palette_krom.custom(mat, -400, 450,
                                    ROUGH_HLSL.format(rough=spec["rough"], rough_mean=e["rough_mean"]),
                                    [("R", r, t["R_channel"])],
                                    output=unreal.CustomMaterialOutputType.CMOT_FLOAT1, description="KromRough")
        mel.connect_material_property(normal, "", P.MP_NORMAL)
    else:
        base, rough = color, const(mat, -400, 450, spec["rough"])
    mel.connect_material_property(base, "", P.MP_BASE_COLOR)
    mel.connect_material_property(rough, "", P.MP_ROUGHNESS)
    mel.connect_material_property(const(mat, -400, 600, spec["metallic"]), "", P.MP_METALLIC)
    mel.connect_material_property(const(mat, -400, 700, spec["specular"]), "", P.MP_SPECULAR)
    mat.set_editor_property("used_with_nanite", True)
    mel.recompile_material(mat)
    assets.save_loaded_asset(mat)
    return mat


def assign(mats):
    """Слоты StaticMesh в ARCH_DIR → материалы по имени слота. Возвращает (изменённые меши, слоты без материала)."""
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    changed, missing = [], set()
    for ad in reg.get_assets_by_path(ARCH_DIR, recursive=True):
        if str(ad.asset_class_path.asset_name) != "StaticMesh" or str(ad.package_path).startswith(STAGING):
            continue
        sm = ad.get_asset()
        n = 0
        for i, s in enumerate(sm.get_editor_property("static_materials")):
            key = str(s.get_editor_property("material_slot_name"))
            m = mats.get(key)
            if m is None:
                missing.add(key)
            elif s.get_editor_property("material_interface") != m:
                sm.set_material(i, m)
                n += 1
        if n:
            assets.save_loaded_asset(sm)
            changed.append(f"{ad.asset_name} ({n})")
    return changed, missing


def main():
    with open(TEXTURES, encoding="utf-8") as f:
        tinfo = json.load(f).get("buildings", {})
    specs = {k: {**DEFAULTS, **v} for k, v in MATS.items()}
    roles = sorted({s["tex"] for s in specs.values() if s["tex"]})
    lost = [r for r in roles if r not in tinfo]
    if lost:
        raise RuntimeError(f"в {TEXTURES} нет текстур зданий {lost} — сначала textures_fetch.py")
    mpc = palette_krom.collection()
    tex = {r: import_role(r, tinfo[r]) for r in roles}
    mats = {k: build(k, s, mpc, tex, tinfo) for k, s in specs.items()}
    changed, missing = assign(mats)
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    unreal.log(f"[materials_krom] материалов {len(mats)}, текстур {len(roles)} × 3; слоты переназначены: "
               f"{', '.join(changed) or 'нигде'}; без материала: {sorted(missing) or 'нет'}")


main()
