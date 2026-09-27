"""light_krom.py — пресеты времени суток: солнце, небесный свет, дымка (M4, D-024, D-028).

Модуль для редактора: level_krom.py ставит акторы света и применяет пресет DEFAULT, а пресет переключают без
пересоздания акторов:

    python scripts/ue_run.py -c "import sys; sys.path.insert(0, 'D:/PskovKrom/scripts'); import light_krom; light_krom.apply('sunset')"

Пресет меняет только свойства акторов «Sun», «SkyLight», «HeightFog», «Post» из level_krom.py; уровень не сохраняется
(save=True — сохранить). Снимать следующей командой ue_run: Lumen, тени и автоэкспозиция догоняют сцену за
несколько кадров редактора (view_krom.py).

Солнце задаётся азимутом (от севера к востоку, как yaw в UE) и высотой над горизонтом: цвет и ослабление у низкого
солнца даёт SkyAtmosphere, яркость — одна на все пресеты. Цвет дымки у земли — в тех же единицах, что солнце
(D-024): у каждого пресета свой. Направленное рассеяние — свечение дымки вокруг солнца; объёмный туман — лучи
в дымке (дороже, только там, где он и есть картинка). Поправка экспозиции (EV) — у низкого солнца автоэкспозиция
вытягивает кадр в белёсое, минус возвращает цвет заката.
"""
import unreal

SUN_LUX = 10.0  # как в шаблоне UE, экспозиция автоматическая
EXPOSURE_DEFAULT = 1.0  # AutoExposureBias по умолчанию в UE5: с ним подобран «ясный день» D-024

# az, elev — солнце, градусы; fog — у земли (плотность, спад, цвет рассеяния linear, высота слоя, м);
# fog_high — высокий слой (плотность, спад); glow — направленное рассеяние (цвет, показатель);
# volumetric — объёмный туман (распределение рассеяния, дальность, м) или None; sky — яркость SkyLight;
# exposure — поправка автоэкспозиции (AutoExposureBias), EV; нет — EXPOSURE_DEFAULT;
# cloud_shadows — тени облаков на земле (нет — да): у низкого солнца слой облаков 5–15 км закрывает весь Кром
PRESETS = {
    # «ясный день» D-024: солнце с юго-запада, дымка растворяет край кольца горизонта в 18 км
    "day": dict(az=225.0, elev=35.0, sky=1.0,
                fog=(0.015, 0.2, (0.25, 0.32, 0.42), 0.0), fog_high=(0.0012, 0.02),
                glow=None, volumetric=None),
    # рассвет в тумане: солнце встаёт за Псковой, над водой и в низинах — туман, лучи в дымке
    "dawn": dict(az=80.0, elev=4.0, sky=1.0,
                 fog=(0.12, 1.0, (0.13, 0.13, 0.14), -13.0), fog_high=(0.004, 0.05),
                 glow=((0.5, 0.3, 0.14), 8.0), volumetric=(0.6, 1500.0), exposure=-0.5, cloud_shadows=False),
    # закат: солнце садится за Завельем, западные стены и собор в тёплом свете, дымка у горизонта тёплая
    "sunset": dict(az=280.0, elev=3.5, sky=1.0,
                   fog=(0.012, 0.2, (0.06, 0.045, 0.038), 0.0), fog_high=(0.0015, 0.02),
                   glow=((0.45, 0.25, 0.10), 6.0), volumetric=None, exposure=-0.8, cloud_shadows=False),
}
DEFAULT = "day"

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _actor(label):
    a = next((x for x in actors.get_all_level_actors() if x.get_actor_label() == label), None)
    if a is None:
        raise RuntimeError(f"нет актора {label} — сначала level_krom.py")
    return a


def apply(name=DEFAULT, save=False, **over):
    """Пресет name → солнце, SkyLight и дымка уровня; save — сохранить уровень; over — подмена полей пресета
    для подбора (apply("sunset", fog=(…)))."""
    p = {**PRESETS[name], **over}
    sun = _actor("Sun")
    sun.set_actor_rotation(unreal.Rotator(roll=0, pitch=-p["elev"], yaw=p["az"] + 180.0), False)  # светит от солнца
    sun.light_component.set_editor_property("intensity", SUN_LUX)
    sun.light_component.set_editor_property("cast_cloud_shadows", p.get("cloud_shadows", True))
    _actor("SkyLight").light_component.set_editor_property("intensity", p["sky"])

    fog_actor = _actor("HeightFog")
    density, falloff, color, z = p["fog"]
    loc = fog_actor.get_actor_location()
    fog_actor.set_actor_location(unreal.Vector(loc.x, loc.y, z * 100.0), False, False)
    fog = fog_actor.get_component_by_class(unreal.ExponentialHeightFogComponent)
    fog.set_editor_property("fog_density", density)
    fog.set_editor_property("fog_height_falloff", falloff)
    fog.set_editor_property("fog_inscattering_luminance", unreal.LinearColor(*color, 1.0))
    high = fog.get_editor_property("second_fog_data")
    high.set_editor_property("fog_density", p["fog_high"][0])
    high.set_editor_property("fog_height_falloff", p["fog_high"][1])
    high.set_editor_property("fog_height_offset", 0.0)
    fog.set_editor_property("second_fog_data", high)
    glow = p["glow"]
    fog.set_editor_property("directional_inscattering_luminance",
                            unreal.LinearColor(*(glow[0] if glow else (0.0, 0.0, 0.0)), 1.0))
    if glow:
        fog.set_editor_property("directional_inscattering_exponent", glow[1])
    vol = p["volumetric"]
    fog.set_editor_property("enable_volumetric_fog", vol is not None)
    if vol:
        fog.set_editor_property("volumetric_fog_scattering_distribution", vol[0])
        fog.set_editor_property("volumetric_fog_distance", vol[1] * 100.0)
    post = _actor("Post")
    pp = post.get_editor_property("settings")
    pp.set_editor_property("override_auto_exposure_bias", True)
    pp.set_editor_property("auto_exposure_bias", p.get("exposure", EXPOSURE_DEFAULT))
    post.set_editor_property("settings", pp)
    if save:
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    unreal.log(f"[light_krom] пресет {name}: солнце az {p['az']}°, h {p['elev']}°")
    return name
