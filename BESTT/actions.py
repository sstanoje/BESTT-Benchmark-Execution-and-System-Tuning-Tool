from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from .profiles import ActionSpec, get_action


PACKAGE_DIR = Path(__file__).resolve().parent
SETUP_SCRIPT = PACKAGE_DIR / "scripts" / "setup_system_for_benchmarking.sh"
ASKPASS_SCRIPT = PACKAGE_DIR / "scripts" / "sudo_askpass.py"


@dataclass(frozen=True)
class ActionResult:
    command: Sequence[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def privilege_prefix(mode: str) -> List[str]:
    if mode == "sudo":
        return ["sudo", "-A"]
    if mode == "none":
        return []
    raise ValueError(f"Unknown privilege mode: {mode}")


def build_action_command(
    action_key: str,
    *,
    core: int = 3,
    governor: str = "performance",
    privilege: str = "sudo",
    script_path: Path = SETUP_SCRIPT,
) -> List[str]:
    action = get_action(action_key)
    if core < 0:
        raise ValueError("Core number must be non-negative")

    return [
        *privilege_prefix(privilege),
        "bash",
        str(script_path),
        *action.resolved_args(core, governor),
    ]


def build_reboot_command(*, privilege: str = "sudo") -> List[str]:
    return [
        *privilege_prefix(privilege),
        "systemctl",
        "reboot",
    ]


def command_preview(command: Sequence[str]) -> str:
    return shlex.join(str(part) for part in command)


def run_action_command(command: Sequence[str], timeout: int | None = 600, cwd: str | None = None) -> ActionResult:
    env = os.environ.copy()
    env.setdefault("SUDO_ASKPASS", str(ASKPASS_SCRIPT))
    completed = subprocess.run(
        list(command),
        check=False,
        text=True,
        capture_output=True,
        timeout=timeout,
        env=env,
        cwd=cwd,
    )
    return ActionResult(
        command=tuple(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def script_is_present(script_path: Path = SETUP_SCRIPT) -> bool:
    return script_path.exists() and os.access(script_path, os.R_OK)


def describe_action(action_key: str) -> ActionSpec:
    return get_action(action_key)
