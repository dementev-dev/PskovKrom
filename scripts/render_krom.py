"""render_krom.py — рендер облёта SEQ_Flyover через Movie Render Queue в MP4 (M6).

Модуль для редактора, в две команды ue_run. Два режима (D-042): separate=False — рендер в PIE на тиках редактора
(status() видит его); separate=True — отдельный процесс UnrealEditor-Cmd -game из сохранённых пакетов (перед запуском
light_krom.apply(preset, save=True) и view_krom.clouds(True); ждать выхода процесса, status() его не видит).
preview() — 720p, один сэмпл, без Game Override, отдельным процессом (≈14 кадров/с); финал — render(..., separate=True).

    python scripts/ue_run.py -c "import sys; sys.path.insert(0, 'D:/PskovKrom/scripts'); import render_krom; render_krom.render('flyover_test', 20, 32)"
    python scripts/ue_run.py -c "import sys; sys.path.insert(0, 'D:/PskovKrom/scripts'); import render_krom; print(render_krom.status())"

render ставит пресет света (light_krom) и облака (view_krom.clouds), собирает задание очереди MRQ — отрезок
[start_s, end_s) последовательности, разрешение, временные сэмплы (сглаживание и размытие движения), прогрев
(облака и Lumen сходятся за десятки кадров — без прогрева первые кадры шахматят) — и запускает PIE-исполнитель.
status — идёт ли рендер; когда кончился, возвращает свет «day» и выключает облака в редакторе (PIE работает
с копией уровня, в редакторе меняются только несохранённые свойства — уровень не сохраняется).
Выход — media/renders/movies/<name>/<name>.mp4 (вне git; отобранное — в media/progress).
"""
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import light_krom  # noqa: E402
import view_krom  # noqa: E402

from shot_krom import REPO  # noqa: E402

SEQ = "/Game/Krom/Cinematics/SEQ_Flyover.SEQ_Flyover"
LEVEL = "/Game/Krom/Maps/L_Krom.L_Krom"
OUT_DIR = os.path.join(REPO, "media", "renders", "movies")
FPS = 24


def render(name="flyover_test", start_s=0.0, end_s=10.0, preset="sunset", res=(1920, 1080), temporal=4,
           warmup=64, clouds=True, overrides=True, separate=False):
    """Отрезок облёта [start_s, end_s) → MP4. Возвращает путь к папке вывода."""
    light_krom.apply(preset)
    view_krom.clouds(clouds)
    sub = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    if sub.is_rendering():
        raise RuntimeError("MRQ уже рендерит")
    queue = sub.get_queue()
    for j in list(queue.get_jobs()):
        queue.delete_job(j)
    job = queue.allocate_new_job(unreal.MoviePipelineExecutorJob)
    job.set_editor_property("job_name", name)
    job.set_editor_property("sequence", unreal.SoftObjectPath(SEQ))
    job.set_editor_property("map", unreal.SoftObjectPath(LEVEL))
    cfg = job.get_configuration()

    out_dir = os.path.join(OUT_DIR, name)
    os.makedirs(out_dir, exist_ok=True)
    out = cfg.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
    out.set_editor_property("output_directory", unreal.DirectoryPath(out_dir.replace("\\", "/")))
    out.set_editor_property("output_resolution", unreal.IntPoint(*res))
    out.set_editor_property("file_name_format", name)
    out.set_editor_property("override_existing_output", True)
    out.set_editor_property("use_custom_playback_range", True)
    out.set_editor_property("custom_start_frame", int(round(start_s * FPS)))
    out.set_editor_property("custom_end_frame", int(round(end_s * FPS)))

    cfg.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)
    cfg.find_or_add_setting_by_class(unreal.MoviePipelineMP4EncoderOutput)
    aa = cfg.find_or_add_setting_by_class(unreal.MoviePipelineAntiAliasingSetting)
    aa.set_editor_property("temporal_sample_count", temporal)
    aa.set_editor_property("engine_warm_up_count", warmup)
    aa.set_editor_property("render_warm_up_count", warmup)
    if overrides:  # кинематографические cvar (Lumen, тени, Nanite на максимум): секунды на кадр — только для финала
        cfg.find_or_add_setting_by_class(unreal.MoviePipelineGameOverrideSetting)

    # PIE — рендер внутри редактора; separate — отдельный процесс UnrealEditor-Cmd -game (без накладных расходов
    # редактора, для превью D-042)
    sub.render_queue_with_executor(unreal.MoviePipelineNewProcessExecutor if separate else unreal.MoviePipelinePIEExecutor)
    unreal.log(f"[render_krom] {name}: {start_s}–{end_s} с, {res[0]}×{res[1]}, пресет {preset}, "
               f"сэмплов {temporal}, прогрев {warmup} → {out_dir}")
    return out_dir


def preview(name="flyover_preview", start_s=0.0, end_s=90.0, preset="day"):
    """Превью в качестве реального времени (D-042): 720p, один сэмпл, короткий прогрев, без Game Override."""
    return render(name, start_s, end_s, preset=preset, res=(1280, 720), temporal=1, warmup=8, overrides=False,
                  separate=True)


def status(restore=True):
    """'rendering' или 'idle'; в idle возвращает редактору свет day и выключает облака (restore)."""
    sub = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    if sub.is_rendering():
        return "rendering"
    if restore:
        light_krom.apply("day")
        view_krom.clouds(False)
    return "idle"
