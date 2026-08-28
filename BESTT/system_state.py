import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class StatusItem:
    setting: str
    value: str
    detail: str = ""
    explanation: str = ""


def _read_text(path: str) -> Optional[str]:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _run_status_command(command: Iterable[str]) -> str:
    try:
        completed = subprocess.run(
            list(command),
            check=False,
            text=True,
            capture_output=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    output = completed.stdout.strip() or completed.stderr.strip()
    return output.splitlines()[0] if output else "unknown"


def _turbo_status() -> StatusItem:
    value = _read_text("/sys/devices/system/cpu/intel_pstate/no_turbo")
    if value == "1":
        return StatusItem("Turbo Boost", "disabled", "intel_pstate/no_turbo=1")
    if value == "0":
        return StatusItem("Turbo Boost", "enabled", "intel_pstate/no_turbo=0")
    return StatusItem("Turbo Boost", "unknown", "intel_pstate not available")


def _online_cpu_ids() -> set:
    value = _read_text("/sys/devices/system/cpu/online")
    if not value:
        return set()

    ids = set()
    for part in value.split(","):
        if "-" in part:
            start, end = part.split("-", 1)
            try:
                ids.update(range(int(start), int(end) + 1))
            except ValueError:
                continue
        elif part:
            try:
                ids.add(int(part))
            except ValueError:
                continue
    return ids


def _governor_status() -> StatusItem:
    online_cpu_ids = _online_cpu_ids()
    governors = []
    checked_cpus = []
    for path in sorted(Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/scaling_governor")):
        match = re.fullmatch(r"cpu(\d+)", path.parent.parent.name)
        if not match:
            continue
        cpu_id = int(match.group(1))
        if online_cpu_ids and cpu_id not in online_cpu_ids:
            continue
        try:
            governors.append(path.read_text(encoding="utf-8").strip())
            checked_cpus.append(cpu_id)
        except OSError:
            continue

    if not governors:
        detail = "cpufreq not available on online cores"
        if online_cpu_ids:
            detail = f"{detail}; online CPUs: {_format_cpu_ids(online_cpu_ids)}"
        return StatusItem("Scaling Governor", "unknown", detail)

    unique = sorted(set(governors))
    detail = f"checked online CPUs: {_format_cpu_ids(checked_cpus)}"
    if len(unique) == 1:
        return StatusItem("Scaling Governor", unique[0], detail)
    return StatusItem("Scaling Governor", "mixed", f"{', '.join(unique)}; {detail}")


def _format_cpu_ids(cpu_ids) -> str:
    sorted_ids = sorted(set(cpu_ids))
    if not sorted_ids:
        return "none"

    ranges = []
    start = previous = sorted_ids[0]
    for cpu_id in sorted_ids[1:]:
        if cpu_id == previous + 1:
            previous = cpu_id
            continue
        ranges.append(f"{start}-{previous}" if start != previous else str(start))
        start = previous = cpu_id
    ranges.append(f"{start}-{previous}" if start != previous else str(start))
    return ",".join(ranges)


def _online_governors() -> List[tuple]:
    online_cpu_ids = _online_cpu_ids()
    governors = []
    for path in sorted(Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/scaling_governor")):
        match = re.fullmatch(r"cpu(\d+)", path.parent.parent.name)
        if not match:
            continue
        cpu_id = int(match.group(1))
        if online_cpu_ids and cpu_id not in online_cpu_ids:
            continue
        try:
            governors.append((cpu_id, path.read_text(encoding="utf-8").strip()))
        except OSError:
            continue
    return sorted(governors, key=lambda item: item[0])


def _all_status_values() -> Dict[str, str]:
    return {item.setting: item.value for item in collect_status() if item.value}


def _smt_status() -> StatusItem:
    value = _read_text("/sys/devices/system/cpu/smt/control")
    if value == "off":
        return StatusItem("Hyper-Threading", "disabled", value)
    if value in {"on", "forceoff", "notsupported", "notimplemented"}:
        label = "enabled" if value == "on" else value
        return StatusItem("Hyper-Threading", label, value)
    return StatusItem("Hyper-Threading", "unknown", value or "not available")


def _cstate_status() -> StatusItem:
    intel_idle = _read_text("/sys/module/intel_idle/parameters/max_cstate")
    processor = _read_text("/sys/module/processor/parameters/max_cstate")
    cmdline = _read_text("/proc/cmdline") or ""

    if intel_idle == "0" or processor == "0":
        return StatusItem("C-states", "disabled", f"intel_idle={intel_idle}, processor={processor}")
    if "intel_idle.max_cstate=0" in cmdline or "processor.max_cstate=0" in cmdline:
        return StatusItem("C-states", "pending reboot", "GRUB argument present")
    if intel_idle is not None or processor is not None:
        return StatusItem("C-states", "enabled", f"intel_idle={intel_idle}, processor={processor}")
    return StatusItem("C-states", "unknown", "kernel module parameter not available")


def _aslr_status() -> StatusItem:
    value = _read_text("/proc/sys/kernel/randomize_va_space")
    if value == "0":
        return StatusItem("ASLR", "disabled", "randomize_va_space=0")
    if value in {"1", "2"}:
        return StatusItem("ASLR", "enabled", f"randomize_va_space={value}")
    return StatusItem("ASLR", "unknown", value or "not available")


def _swap_status() -> StatusItem:
    text = _read_text("/proc/swaps")
    if text is None:
        return StatusItem("Swap", "unknown", "/proc/swaps not available")
    entries = [line for line in text.splitlines()[1:] if line.strip()]
    if entries:
        return StatusItem("Swap", "enabled", f"{len(entries)} active swap entries")
    return StatusItem("Swap", "disabled", "no active swap entries")


def _ntp_status() -> StatusItem:
    candidates = [
        ("systemd-timesyncd", ["systemctl", "is-active", "systemd-timesyncd"]),
        ("chronyd", ["systemctl", "is-active", "chronyd"]),
        ("ntp", ["systemctl", "is-active", "ntp"]),
    ]
    details = []
    for name, command in candidates:
        status = _run_status_command(command)
        details.append(f"{name}={status}")
        if status == "active":
            return StatusItem("NTP Syncing", "active", ", ".join(details))
    return StatusItem("NTP Syncing", "inactive", ", ".join(details))


def _isolated_cores_status() -> StatusItem:
    value = _read_text("/sys/devices/system/cpu/isolated")
    if value:
        return StatusItem("Isolated Cores", value, "active")

    cmdline = _read_text("/proc/cmdline") or ""
    for token in cmdline.split():
        if token.startswith("isolcpus="):
            return StatusItem("Isolated Cores", "pending reboot", token)
    return StatusItem("Isolated Cores", "none", "")


def collect_status() -> List[StatusItem]:
    return [_with_explanation(item) for item in [
        StatusItem("CPU and Power", "", "", ""),
        _turbo_status(),
        _governor_status(),
        _cstate_status(),
        _smt_status(),
        StatusItem("Kernel and Memory", "", "", ""),
        _aslr_status(),
        _swap_status(),
        _ntp_status(),
        StatusItem("Isolation", "", "", ""),
        _isolated_cores_status(),
    ]]


def _with_explanation(item: StatusItem) -> StatusItem:
    if not item.value and not item.detail and not item.explanation:
        return item

    explanations = {
        "Turbo Boost": {
            "enabled": "Allows CPU cores to temporarily use turbo frequencies, which can improve speed but add run-to-run variability.",
            "disabled": "Prevents turbo frequencies, reducing one source of frequency variation during benchmarks.",
        },
        "Scaling Governor": {
            "performance": "Keeps online CPU cores at high frequency instead of dynamically scaling them.",
            "powersave": "Can dynamically change CPU frequencies based on load, which can introduce frequency variation.",
            "schedutil": "Can dynamically change CPU frequencies based on load, which can introduce frequency variation.",
            "ondemand": "Dynamically changes CPU frequency based on observed CPU utilization.",
            "mixed": "Online cores do not all use the same governor.",
        },
        "Hyper-Threading": {
            "enabled": "Allows two hardware threads to share one physical core, improving throughput but adding shared-core interference.",
            "disabled": "Prevents sibling hardware threads from sharing a core, reducing interference.",
        },
        "C-states": {
            "enabled": "Allows deeper CPU sleep states, which save power but can add wake-up latency.",
            "disabled": "Prevents deeper CPU sleep states, reducing wake-up latency variability.",
            "pending reboot": "Boot settings were changed, but the active kernel state has not changed yet.",
        },
        "ASLR": {
            "enabled": "Randomizes memory layout between runs, improving security but adding layout variation.",
            "disabled": "Keeps memory layout more stable between runs.",
        },
        "Swap": {
            "enabled": "Allows memory pages to move to disk, which can cause large timing noise.",
            "disabled": "Prevents swap activity during benchmarks.",
        },
        "NTP Syncing": {
            "active": "Time synchronization service is running and may adjust system time.",
            "inactive": "Time synchronization service is stopped during measurement.",
        },
        "Isolated Cores": {
            "none": "No CPU core is isolated for benchmark execution.",
            "pending reboot": "Core isolation was configured in boot settings but is not active yet.",
        },
    }
    explanation = explanations.get(item.setting, {}).get(item.value)
    if explanation is None and item.setting == "Isolated Cores":
        explanation = f"Core(s) {item.value} are isolated from normal scheduler activity for benchmark execution."
    if explanation is None:
        explanation = "Current value could not be interpreted by the GUI."
    return StatusItem(item.setting, item.value, item.detail, explanation)


def status_as_dict(items: Optional[List[StatusItem]] = None) -> Dict[str, Dict[str, str]]:
    source = items if items is not None else collect_status()
    return {item.setting: {"value": item.value, "explanation": item.explanation} for item in source}


def status_as_json(items: Optional[List[StatusItem]] = None) -> str:
    source = items if items is not None else collect_status()
    return json.dumps([asdict(item) for item in source], indent=2, sort_keys=True)


def export_report_text() -> str:
    values = _all_status_values()
    lines = [
        f"Turbo Boost: {values.get('Turbo Boost', 'unknown')}",
    ]

    governors = _online_governors()
    if governors:
        for cpu_id, governor in governors:
            lines.append(f"Scaling Governor core {cpu_id}: {governor}")
    else:
        lines.append("Scaling Governor: unknown")

    lines.extend([
        f"C-states: {values.get('C-states', 'unknown')}",
        f"Hyper-Threading: {values.get('Hyper-Threading', 'unknown')}",
        f"ASLR: {values.get('ASLR', 'unknown')}",
        f"Swap: {values.get('Swap', 'unknown')}",
        f"NTP Syncing: {values.get('NTP Syncing', 'unknown')}",
        f"Isolated Cores: {values.get('Isolated Cores', 'unknown')}",
    ])

    return "\n".join(lines) + "\n"


def export_report_json() -> str:
    values = _all_status_values()
    report = {
        "Turbo Boost": values.get("Turbo Boost", "unknown"),
        "Scaling Governor": {
            f"core {cpu_id}": governor for cpu_id, governor in _online_governors()
        },
        "C-states": values.get("C-states", "unknown"),
        "Hyper-Threading": values.get("Hyper-Threading", "unknown"),
        "ASLR": values.get("ASLR", "unknown"),
        "Swap": values.get("Swap", "unknown"),
        "NTP Syncing": values.get("NTP Syncing", "unknown"),
        "Isolated Cores": values.get("Isolated Cores", "unknown"),
    }
    if not report["Scaling Governor"]:
        report["Scaling Governor"] = "unknown"
    return json.dumps(report, indent=2) + "\n"
