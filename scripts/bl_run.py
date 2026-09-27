"""bl_run.py — запуск скрипта в Blender без окна (герои M3 делаются скриптами, D-018).

    python scripts/bl_run.py scripts/blender/hello_axes.py [-- аргументы скрипта]

Blender — портативный, путь берётся из BLENDER, по умолчанию D:/Tools/blender-5.2.2-windows-x64/blender.exe.
Запуск с --factory-startup: пользовательские настройки и аддоны не влияют на результат.
Код возврата 0 — скрипт отработал, 1 — ошибка в скрипте, 2 — Blender не найден.
"""
import os
import subprocess
import sys

BLENDER = os.environ.get("BLENDER", "D:/Tools/blender-5.2.2-windows-x64/blender.exe")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    if not os.path.exists(BLENDER):
        print(f"[bl_run] нет Blender: {BLENDER} (переменная BLENDER)", file=sys.stderr)
        return 2
    script, rest = sys.argv[1], sys.argv[2:]
    if rest and rest[0] == "--":
        rest = rest[1:]
    cmd = [BLENDER, "--background", "--factory-startup", "--python-exit-code", "1",
           "--python", os.path.abspath(script), "--", *rest]
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    sys.exit(main())
