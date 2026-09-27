"""Install a login LaunchAgent for this project; no administrator privileges."""

import os
import plistlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABEL = "com.reelagent.download"


def main() -> None:
    local = ROOT / ".local"
    local.mkdir(exist_ok=True)
    target = Path.home() / "Library/LaunchAgents" / (LABEL + ".plist")
    target.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-m", "scripts.auto_download"],
        "WorkingDirectory": str(ROOT),
        "RunAtLoad": True,
        "StartInterval": 300,
        "ProcessType": "Background",
        "StandardOutPath": str(local / "receiver.log"),
        "StandardErrorPath": str(local / "receiver-error.log"),
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"},
    }
    target.write_bytes(plistlib.dumps(config))
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domain + "/" + LABEL], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", domain, str(target)], check=True)
    print("Автоскачивание установлено. Проверка облака каждые 5 минут при входе в Mac.")


if __name__ == "__main__":
    main()
