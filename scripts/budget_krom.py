"""budget_krom.py — замер бюджета кадра и видеопамяти в редакторе: CSV-профайлер UE (M4, пункт «Бюджет VRAM»).

Модуль для редактора, в две команды ue_run (профайлер пишет кадры на тиках редактора, внутри одной команды тиков нет):

    python scripts/ue_run.py -c "import sys; sys.path.insert(0, 'D:/PskovKrom/scripts'); import budget_krom; budget_krom.start('oblique')"
    python scripts/ue_run.py -c "import sys; sys.path.insert(0, 'D:/PskovKrom/scripts'); import budget_krom; print(budget_krom.report())"

start ставит камеру вьюпорта в ракурс (VIEWS из shot_krom) и запускает `csvprofile frames=N`; report читает
последний CSV из Krom/Saved/Profiling/CSV (дождаться, пока файл допишется) и возвращает медианы.
Время кадра (FrameTime) в фоне не показательно: редактор без фокуса сам сбавляет частоту до ≈3 кадров/с.
Смотреть на GPUTime — работа видеокарты за кадр, её фон не трогает. Память: GPUMem/LocalUsedMB против
LocalBudgetMB (≈5,2 ГБ на RTX 3060 Laptop 6 ГБ) и TextureStreaming: WantedMips не больше StreamingPool —
значит, «over budget» нет.
"""
import csv
import glob
import os
import statistics

import unreal

from shot_krom import REPO, VIEWS, look_at

CSV_DIR = os.path.join(REPO, "Krom", "Saved", "Profiling", "CSV")
FRAMES = 120
COLUMNS = ("GPUTime", "FrameTime", "GPUMem/LocalUsedMB", "GPUMem/LocalBudgetMB", "GPUMem/SystemUsedMB",
           "TextureStreaming/StreamingPool", "TextureStreaming/WantedMips", "TextureStreaming/NonStreamingMips",
           "RenderTargetPoolSize", "RHI/DrawCalls", "RHI/PrimitivesDrawn")


def start(view=None, frames=FRAMES):
    """Камера вьюпорта — в ракурс view (если задан), затем csvprofile на frames кадров."""
    if view:
        eye, target = VIEWS[view]
        unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(
            unreal.Vector(*(v * 100 for v in eye)), look_at(eye, target))
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    unreal.SystemLibrary.execute_console_command(world, f"csvprofile frames={frames}")
    return f"csvprofile {frames} кадров{' из ' + view if view else ''}"


def report(path=None):
    """Медианы COLUMNS по последнему (или заданному) CSV: {столбец: (медиана, максимум)}."""
    path = path or max(glob.glob(os.path.join(CSV_DIR, "*.csv")), key=os.path.getmtime)
    with open(path, encoding="utf-8", errors="replace") as f:
        rows = list(csv.reader(f))
    head = rows[0]
    data = [r for r in rows[1:] if len(r) >= len(head) - 1 and r[1][:1].isdigit()]
    if not data:
        raise RuntimeError(f"{path}: кадров нет — профайлер ещё пишет?")
    out = {"file": os.path.basename(path), "frames": len(data)}
    for c in COLUMNS:
        i = head.index(c)
        v = [float(r[i]) for r in data if i < len(r) and r[i]]
        out[c] = (round(statistics.median(v), 2), round(max(v), 2))
    return out
