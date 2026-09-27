"""check_text.py — проверка текстовых файлов перед коммитом: управляющие символы и битый UTF-8.

Git такое пропускает молча. Пример 2026-09-25: heredoc с Python-строкой превратил `\\b` в пути `D:\\Tools\\blender`
в символ backspace (0x08) прямо в документах. Переносы строк (LF/CRLF) нормализует .gitattributes, здесь их не трогаем.

    python scripts/check_text.py          # файлы в индексе — так вызывает .githooks/pre-commit
    python scripts/check_text.py --all    # все отслеживаемые текстовые файлы

Код возврата 1 — есть нарушения: файл:строка:колонка и код символа. Проверяется версия в индексе (то, что уйдёт в коммит).
"""
import os
import re
import subprocess
import sys

TEXT_EXT = {".md", ".py", ".json", ".ini", ".txt", ".uproject", ".sh", ".toml", ".yml", ".yaml", ".cfg"}
TEXT_NAMES = {".gitignore", ".gitattributes", "pre-commit"}
BAD = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # всё управляющее, кроме \t \n \r


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def staged_text_files(everything):
    out = git("ls-files", "-z") if everything else git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    names = [n for n in out.decode("utf-8").split("\0") if n]
    return [n for n in names if os.path.splitext(n)[1].lower() in TEXT_EXT or os.path.basename(n) in TEXT_NAMES]


def problems(name):
    data = git("show", f":{name}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        line = data[:e.start].count(b"\n") + 1
        return [f"{name}:{line}: не UTF-8 (байт 0x{data[e.start]:02x})"]
    out = []
    for m in BAD.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        col = m.start() - (text.rfind("\n", 0, m.start()) + 1) + 1
        out.append(f"{name}:{line}:{col}: управляющий символ 0x{ord(m.group()):02x}")
    return out


def main():
    everything = "--all" in sys.argv
    found = [p for n in staged_text_files(everything) for p in problems(n)]
    for p in found:
        print(p, file=sys.stderr)
    if found:
        print(f"[check_text] {len(found)} нарушений — коммит остановлен. Исправить файл и снова `git add`.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
