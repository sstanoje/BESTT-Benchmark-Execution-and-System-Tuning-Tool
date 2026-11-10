#!/usr/bin/env python3
"""Save original settings, or list them for the shell restoration loop."""
import json
import os
import re
import stat
from pathlib import Path
import subprocess
import sys

CPU = Path("/sys/devices/system/cpu")
ASLR = Path("/proc/sys/kernel/randomize_va_space")
SWAPS = Path("/proc/swaps")
SYSTEMD = Path("/run/systemd/system")
NTP_INIT = Path("/etc/init.d/ntp")
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
GRUB_KEYS = ("processor.max_cstate", "intel_idle.max_cstate",
             "isolcpus", "nohz_full", "rcu_nocbs", "irqaffinity")


def read_optional(path):
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return None


def command(*args):
    return subprocess.run(args, text=True, capture_output=True, timeout=10)


def capture():
    # Restore SMT first, so its CPUs are online before restoring governors.
    values = {str(path): read_optional(path) for path in (
        CPU / "smt/control", CPU / "intel_pstate/no_turbo", ASLR)}
    for part in (CPU / "online").read_text().strip().split(","):
        ends = part.split("-")
        for cpu in range(int(ends[0]), int(ends[-1]) + 1):
            path = CPU / f"cpu{cpu}/cpufreq/scaling_governor"
            values[str(path)] = read_optional(path)
    services = []
    if SYSTEMD.exists():
        for name in ("systemd-timesyncd", "chronyd", "ntp"):
            result = command("systemctl", "show", name, "-p", "LoadState", "-p", "ActiveState")
            properties = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
            if properties.get("LoadState") in ("not-found", "masked"):
                continue
            active = properties.get("ActiveState")
            if result.returncode or properties.get("LoadState") != "loaded" or active not in ("active", "inactive", "failed"):
                raise ValueError(f"Cannot read a stable state for {name}: {result.stderr.strip()}")
            services.append(["systemctl", name, "start" if active == "active" else "stop"])
    if not services and NTP_INIT.exists():
        result = command("service", "ntp", "status")
        if result.returncode not in (0, 3):
            raise ValueError("Cannot determine whether the ntp service is running")
        services.append(["service", "ntp", "start" if result.returncode == 0 else "stop"])
    return {"values": values, "swap": bool(SWAPS.read_text().splitlines()[1:]), "services": services}


def atomic_write(path, text, preserve_permissions=False):
    if preserve_permissions:
        path = path.resolve()  # Preserve a symlink to the configuration file, if present.
    metadata = path.stat() if preserve_permissions else None
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as output:
        output.write(text)
        output.flush()
        if metadata is not None:
            os.fchown(output.fileno(), metadata.st_uid, metadata.st_gid)
            os.fchmod(output.fileno(), stat.S_IMODE(metadata.st_mode))
        os.fsync(output.fileno())
    temporary.replace(path)


def grub_args(text):
    assignments = re.findall(r"(?m)^[ \t]*GRUB_CMDLINE_LINUX[ \t]*=", text)
    if len(assignments) > 1:
        raise ValueError("Duplicate GRUB_CMDLINE_LINUX assignments; keep only one before continuing")
    match = re.search(r"""(?m)^[ \t]*GRUB_CMDLINE_LINUX[ \t]*=[ \t]*(["'])(.*?)\1[ \t]*(?:#.*)?$""", text)
    if not match and assignments:
        raise ValueError("GRUB_CMDLINE_LINUX must use a quoted value")
    # Keep quoted kernel arguments intact, including unrelated arguments with spaces.
    tokens = re.findall(r"""(?:[^\s"']|"[^"]*"|'[^']*')+""", match[2]) if match else []
    return match, tokens


def update_grub(state, filename, grub, mode, additions):
    saved = state["grub"]
    if saved is None:
        raise ValueError("GRUB was unavailable when the original settings were saved")
    text = grub.read_text()
    match, current = grub_args(text)
    if mode == "restore":
        keys = saved["changed"]
        additions = [arg for arg in saved["original"] if arg.split("=", 1)[0] in keys]
    else:
        keys = GRUB_KEYS[:2] if mode == "cstates" else GRUB_KEYS[2:] if mode == "isolation" else GRUB_KEYS
    changed = [key for key in keys
               if [arg for arg in current if arg.split("=", 1)[0] == key]
               != [arg for arg in additions if arg.split("=", 1)[0] == key]]
    args = [arg for arg in current if arg.split("=", 1)[0] not in changed]
    args += [arg for arg in additions if arg.split("=", 1)[0] in changed]
    remove_assignment = (mode == "restore" and not saved.get("assignment_existed", True)
                         and saved["changed"] and match is not None and not args)
    if changed or remove_assignment:
        # Record what we may change before writing GRUB, so failed writes can be retried.
        saved["changed"] = list(dict.fromkeys(saved["changed"] + changed))
        saved.pop("restored_boot_id", None)
        atomic_write(filename, json.dumps(state, indent=2) + "\n")
        value = " ".join(args)
        if remove_assignment:
            end = match.end() + (text[match.end():match.end() + 1] == "\n")
            comment = text[match.end(2) + 1:match.end()].strip()
            text = text[:match.start()] + (comment + "\n" if comment else "") + text[end:]
        elif match:
            text = text[:match.start(2)] + value + text[match.end(2):]
        else:
            text += ("\n" if text and not text.endswith("\n") else "") + f'GRUB_CMDLINE_LINUX="{value}"\n'
        atomic_write(grub, text, preserve_permissions=True)
    # Retry regeneration even if an earlier attempt wrote the file but failed to regenerate.
    if mode == "restore" and saved.get("restored_boot_id"):
        print("reboot" if saved["restored_boot_id"] == BOOT_ID.read_text().strip() else "unchanged")
    else:
        print("regenerate" if saved["changed"] else "unchanged")


def restore_lines(state):
    lines = []
    for path, value in state["values"].items():
        if value is not None:
            lines.append(f"value\t{path}\t{value}")
    lines.append("swap\t" + ("on" if state["swap"] else "off"))
    lines.extend("\t".join(service) for service in state["services"])
    if state["grub"] and state["grub"]["changed"]:
        lines.append("grub")
    return lines


def main():
    mode, filename, grub_file, *args = sys.argv[1:]
    path, grub = Path(filename), Path(grub_file)
    os.umask(0o077)
    if mode == "save" and not path.exists():
        state = capture()
        original_grub = read_optional(grub)
        match, original_args = grub_args(original_grub) if original_grub is not None else (None, [])
        state["grub"] = None if original_grub is None else {
            "assignment_existed": match is not None,
            "original": [arg for arg in original_args if arg.split("=", 1)[0] in GRUB_KEYS],
            "changed": [],
        }
        atomic_write(path, json.dumps(state, indent=2) + "\n")
        print(f"Original settings saved in {path}")
    else:
        state = json.loads(path.read_text())
        if state["grub"] is not None and not isinstance(state["grub"], dict):
            raise ValueError("Older snapshot format: restore using the previous BESTT version before continuing")
        if mode == "grub-set":
            update_grub(state, path, grub, args[0], args[1:])
        elif mode == "grub-restore":
            update_grub(state, path, grub, "restore", [])
        elif mode == "grub-restored":
            state["grub"]["restored_boot_id"] = BOOT_ID.read_text().strip()
            atomic_write(path, json.dumps(state, indent=2) + "\n")
        elif mode == "finish-restore":
            saved = state["grub"]
            if saved and saved["changed"] and saved.get("restored_boot_id") == BOOT_ID.read_text().strip():
                print("Snapshot kept. Reboot, then run Restore Previous Settings again to finish runtime restoration.")
            else:
                path.unlink()
                print("Original settings restored; snapshot removed.")
        elif mode == "restore":
            print("\n".join(restore_lines(state)))
        else:
            restore_lines(state)  # Validate the existing snapshot before more changes.
            print(f"Keeping original settings in {path}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f"Snapshot error: {error}", file=sys.stderr)
        sys.exit(1)
