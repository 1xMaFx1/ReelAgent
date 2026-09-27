"""Organize an existing checkout without deleting user files; build the Mac launcher."""

import argparse
import plistlib
from pathlib import Path


def install(folder):
    folder = folder.resolve()
    working = folder / "Рабочие файлы"
    working.mkdir(exist_ok=True)
    (folder / "Готовые ролики").mkdir(exist_ok=True)
    for item in list(folder.iterdir()):
        if item.name in {"Рабочие файлы", "Готовые ролики", "ReelAgent.app"}:
            continue
        target = working / item.name
        if target.exists():
            raise RuntimeError("Файл уже существует: " + str(target))
        item.rename(target)
    contents = folder / "ReelAgent.app/Contents"
    executable = contents / "MacOS/ReelAgent"
    executable.parent.mkdir(parents=True, exist_ok=True)
    (contents / "Resources").mkdir(exist_ok=True)
    (contents / "Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundleName": "ReelAgent",
                "CFBundleDisplayName": "ReelAgent Studio",
                "CFBundleIdentifier": "local.reelagent.studio",
                "CFBundleVersion": "2.0",
                "CFBundleShortVersionString": "2.0",
                "CFBundlePackageType": "APPL",
                "CFBundleExecutable": "ReelAgent",
                "LSUIElement": True,
            }
        )
    )
    executable.write_text("""#!/bin/zsh
APP_DIR="${0:A:h:h:h}"
cd "$APP_DIR/../Рабочие файлы" || exit 1
exec /usr/bin/python3 -m scripts.desktop
""")
    executable.chmod(0o755)
    return working


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    print(install(parser.parse_args().folder))
