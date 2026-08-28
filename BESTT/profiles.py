from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class ActionSpec:
    key: str
    label: str
    description: str
    script_args: Tuple[str, ...]
    category: str
    requires_core: bool = False
    requires_governor: bool = False
    requires_reboot: bool = False

    def resolved_args(self, core: int, governor: str = "performance") -> Tuple[str, ...]:
        return tuple(arg.format(core=core, governor=governor) for arg in self.script_args)


ACTION_SPECS: Dict[str, ActionSpec] = {
    "recommended": ActionSpec(
        key="recommended",
        label="Setup R",
        category="Profiles",
        script_args=("--all", "{core}"),
        requires_core=True,
        requires_reboot=True,
        description=(
            "Apply the recommended benchmarking configuration: Disable Turbo Boost, set scaling governors "
            "to performance, disable deeper C-states, disable Hyper-Threading, isolate selected core ($core), "
            "disable ASLR, stop NTP, disable swap memory, and clear system caches."
        ),
    ),
    "mt_recommended": ActionSpec(
        key="mt_recommended",
        label="Setup MTR",
        category="Profiles",
        script_args=("--mt-rec",),
        requires_reboot=True,
        description=(
            "Apply the recommended benchmarking configuration for multi-threaded benchmarks: Disable Turbo Boost, "
            "set scaling governors to performance, disable deeper C-states, enable Hyper-Threading, do not isolate a core, disable ASLR, stop NTP, "
            "disable swap memory, and clear system caches."
        ),
    ),
    "restore_defaults": ActionSpec(
        key="restore_defaults",
        label="Restore Common Defaults",
        category="Profiles",
        script_args=("--restore",),
        requires_reboot=True,
        description=(
            "Restore system to its default state."
        ),
    ),
    "turbo": ActionSpec(
        key="turbo",
        label="Disable Turbo Boost",
        category="Advanced",
        script_args=("--turbo",),
        description="Disable Turbo Boost.",
    ),
    "topology": ActionSpec(
        key="topology",
        label="Disable Hyper-Threading",
        category="Advanced",
        script_args=("--topology",),
        description="Disable Hyper-Threading.",
    ),
    "cstates": ActionSpec(
        key="cstates",
        label="Disable C-states",
        category="Advanced",
        script_args=("--cstates",),
        requires_reboot=True,
        description="Disables deeper C-states (sets C-states to 0).",
    ),
    "security": ActionSpec(
        key="security",
        label="Disable ASLR",
        category="Advanced",
        script_args=("--security",),
        description="Disable address-space layout randomization.",
    ),
    "swap": ActionSpec(
        key="swap",
        label="Disable Swap",
        category="Advanced",
        script_args=("--swap",),
        description="Disable swap memory.",
    ),
    "caches": ActionSpec(
        key="caches",
        label="Clear Caches",
        category="Advanced",
        script_args=("--caches",),
        description="Sync disks and drop filesystem caches.",
    ),
    "ntp": ActionSpec(
        key="ntp",
        label="Stop NTP",
        category="Advanced",
        script_args=("--ntp",),
        description="Stop common network time synchronization services (NTP).",
    ),
    "governor": ActionSpec(
        key="governor",
        label="Set Scaling Governor",
        category="Advanced",
        script_args=("--governor", "{governor}"),
        requires_governor=True,
        description="Set online CPU scaling governors to {governor}.",
    ),
    "isolate": ActionSpec(
        key="isolate",
        label="Isolate Core",
        category="Advanced",
        script_args=("--isolate", "{core}"),
        requires_core=True,
        requires_reboot=True,
        description="Isolate selected core (core $core).",
    ),
}


def get_action(key: str) -> ActionSpec:
    try:
        return ACTION_SPECS[key]
    except KeyError as exc:
        raise ValueError(f"Unknown setup action: {key}") from exc


def actions_by_category(category: str) -> Tuple[ActionSpec, ...]:
    return tuple(action for action in ACTION_SPECS.values() if action.category == category)
