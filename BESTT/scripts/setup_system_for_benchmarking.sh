#!/usr/bin/env bash
set -euo pipefail

if [ "${EUID}" -ne 0 ]; then
  echo "Please run as root (use sudo or pkexec)." >&2
  exit 1
fi

ISOLATED_CORE="${2:-3}"
GRUB_FILE="/etc/default/grub"
GRUB_BACKUP="/etc/default/grub.bestt.bak"

show_help() {
  cat <<'HELP'
Usage: setup_system_for_benchmarking.sh [OPTION] [CORE_NUMBER]

Options:
  -p, --performance    Set CPU governor to performance and disable Turbo Boost
      --turbo          Disable Turbo Boost
      --governor GOV   Set CPU governor to GOV
      --swap           Disable swap
      --caches         Drop filesystem caches
  -m, --memory         Disable swap and drop filesystem caches
  -s, --security       Disable ASLR
  -t, --topology       Disable Hyper-Threading
  -n, --ntp            Stop common NTP time-sync services
  -c, --cstates        Add GRUB C-state settings
  -i, --isolate        Add GRUB core-isolation settings for CORE_NUMBER
  -M, --mt-rec         Apply MTR profile
  -a, --all            Apply R profile for CORE_NUMBER
  -r, --restore        Best-effort restore of common defaults
  -h, --help           Show this help
HELP
}

available_governor() {
  local cpu="$1"
  local preferred="$2"
  local available_file="/sys/devices/system/cpu/cpu${cpu}/cpufreq/scaling_available_governors"

  if [ -f "${available_file}" ] && grep -qw "${preferred}" "${available_file}"; then
    printf '%s\n' "${preferred}"
    return 0
  fi
  return 1
}

set_governor_all() {
  local preferred="$1"
  local cpu_count
  cpu_count="$(nproc)"

  for cpu in $(seq 0 $((cpu_count - 1))); do
    local fallback=""
    local governor_file="/sys/devices/system/cpu/cpu${cpu}/cpufreq/scaling_governor"
    [ -f "${governor_file}" ] || continue

    if available_governor "${cpu}" "${preferred}" >/dev/null; then
      echo "${preferred}" > "${governor_file}"
      continue
    fi

    for candidate in schedutil ondemand powersave performance; do
      if available_governor "${cpu}" "${candidate}" >/dev/null; then
        fallback="${candidate}"
        break
      fi
    done

    if [ -n "${fallback}" ]; then
      echo "${fallback}" > "${governor_file}"
    fi
  done
}

tune_performance() {
  echo "--- Setting performance mode ---"
  disable_turbo
  set_governor_all performance
}

disable_turbo() {
  echo "--- Disabling Turbo Boost ---"
  if [ -f "/sys/devices/system/cpu/intel_pstate/no_turbo" ]; then
    echo "1" > /sys/devices/system/cpu/intel_pstate/no_turbo
  else
    echo "Turbo Boost control is not available on this machine."
  fi
}

tune_governor() {
  local governor="$1"
  echo "--- Setting scaling governors to ${governor} ---"
  set_governor_all "${governor}"
}

tune_memory() {
  echo "--- Cleaning memory state ---"
  disable_swap
  clear_caches
}

disable_swap() {
  echo "--- Disabling swap ---"
  swapoff -a || true
}

clear_caches() {
  echo "--- Clearing filesystem caches ---"
  sync
  echo "3" > /proc/sys/vm/drop_caches
}

tune_security() {
  echo "--- Disabling ASLR ---"
  echo "0" > /proc/sys/kernel/randomize_va_space
}

tune_topology() {
  echo "--- Disabling Hyper-Threading ---"
  if [ -f "/sys/devices/system/cpu/smt/control" ]; then
    echo off > /sys/devices/system/cpu/smt/control
  else
    echo "Hyper-Threading control is not available on this machine."
  fi
}

enable_topology() {
  echo "--- Enabling Hyper-Threading when supported ---"
  if [ -f "/sys/devices/system/cpu/smt/control" ]; then
    echo on > /sys/devices/system/cpu/smt/control || true
  else
    echo "Hyper-Threading control is not available on this machine."
  fi
}

tune_ntp() {
  echo "--- Stopping time synchronization services ---"
  systemctl stop systemd-timesyncd 2>/dev/null || true
  systemctl stop chronyd 2>/dev/null || true
  systemctl stop ntp 2>/dev/null || true
  service ntp stop 2>/dev/null || true
}

ensure_grub_backup() {
  [ -f "${GRUB_FILE}" ] || {
    echo "Missing ${GRUB_FILE}; cannot update GRUB." >&2
    exit 1
  }
  if [ ! -f "${GRUB_BACKUP}" ]; then
    cp "${GRUB_FILE}" "${GRUB_BACKUP}"
    echo "Created ${GRUB_BACKUP}"
  fi
}

current_grub_args() {
  sed -n 's/^GRUB_CMDLINE_LINUX="\([^"]*\)".*/\1/p' "${GRUB_FILE}" | tail -n 1
}

remove_managed_grub_args() {
  local current="$1"
  local mode="$2"
  local filtered=()

  for token in ${current}; do
    case "${token}" in
      processor.max_cstate=*|intel_idle.max_cstate=*)
        [ "${mode}" = "isolation" ] && filtered+=("${token}")
        ;;
      isolcpus=*|nohz_full=*|rcu_nocbs=*|irqaffinity=*)
        [ "${mode}" = "cstates" ] && filtered+=("${token}")
        ;;
      *)
        filtered+=("${token}")
        ;;
    esac
  done

  printf '%s\n' "${filtered[*]:-}"
}

write_grub_args() {
  local args="$1"
  python3 - "$GRUB_FILE" "$args" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
args = sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines()
written = False
out = []
for line in lines:
    if line.startswith("GRUB_CMDLINE_LINUX="):
        out.append(f'GRUB_CMDLINE_LINUX="{args}"')
        written = True
    else:
        out.append(line)
if not written:
    out.append(f'GRUB_CMDLINE_LINUX="{args}"')
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
}

regenerate_grub() {
  if command -v update-grub >/dev/null 2>&1; then
    update-grub
  elif command -v grub2-mkconfig >/dev/null 2>&1; then
    if [ -d /boot/grub2 ]; then
      grub2-mkconfig -o /boot/grub2/grub.cfg
    else
      grub2-mkconfig -o /boot/grub/grub.cfg
    fi
  else
    echo "WARNING: update-grub/grub2-mkconfig not found. Regenerate GRUB manually." >&2
  fi
}

apply_grub_args() {
  local mode="$1"
  shift
  local additions=("$@")
  ensure_grub_backup
  local current
  current="$(current_grub_args)"
  local filtered
  filtered="$(remove_managed_grub_args "${current}" "${mode}")"
  local next="${filtered}"
  for addition in "${additions[@]}"; do
    if [ -z "${next}" ]; then
      next="${addition}"
    else
      next="${next} ${addition}"
    fi
  done
  write_grub_args "${next}"
  regenerate_grub
  echo "GRUB updated. Reboot required."
}

isolation_args() {
  local target_core="$1"
  local max_idx=$(( $(nproc) - 1 ))
  local affinity

  if [ "${target_core}" -lt 0 ] || [ "${target_core}" -gt "${max_idx}" ]; then
    echo "Invalid core ${target_core}; valid range is 0-${max_idx}." >&2
    exit 1
  fi

  if [ "${target_core}" -eq 0 ]; then
    affinity="1-${max_idx}"
  elif [ "${target_core}" -eq "${max_idx}" ]; then
    affinity="0-$((max_idx - 1))"
  else
    affinity="0-$((target_core - 1)),$((target_core + 1))-${max_idx}"
  fi

  printf '%s\n' \
    "isolcpus=domain,managed_irq,${target_core}" \
    "nohz_full=${target_core}" \
    "rcu_nocbs=${target_core}" \
    "irqaffinity=${affinity}"
}

tune_cstates_only() {
  echo "--- Disabling deep C-states through GRUB ---"
  apply_grub_args cstates processor.max_cstate=0 intel_idle.max_cstate=0
}

tune_mtr_grub() {
  echo "--- Applying MTR GRUB settings ---"
  apply_grub_args all processor.max_cstate=0 intel_idle.max_cstate=0
}

tune_isolation_only() {
  local target_core="$1"
  echo "--- Isolating core ${target_core} through GRUB ---"
  mapfile -t args < <(isolation_args "${target_core}")
  apply_grub_args isolation "${args[@]}"
}

tune_full_grub() {
  local target_core="$1"
  echo "--- Applying C-state and core-isolation GRUB settings ---"
  mapfile -t args < <(isolation_args "${target_core}")
  apply_grub_args all processor.max_cstate=0 intel_idle.max_cstate=0 "${args[@]}"
}

restore_defaults() {
  echo "--- Restoring common defaults ---"
  if [ -f "/sys/devices/system/cpu/intel_pstate/no_turbo" ]; then
    echo "0" > /sys/devices/system/cpu/intel_pstate/no_turbo || true
  fi
  set_governor_all schedutil || true
  echo "2" > /proc/sys/kernel/randomize_va_space || true
  if [ -f "/sys/devices/system/cpu/smt/control" ]; then
    echo on > /sys/devices/system/cpu/smt/control || true
  fi
  swapon -a || true
  systemctl start systemd-timesyncd 2>/dev/null || true
  systemctl start chronyd 2>/dev/null || true
  systemctl start ntp 2>/dev/null || true

  if [ -f "${GRUB_FILE}" ]; then
    ensure_grub_backup
    local current
    current="$(current_grub_args)"
    local filtered
    filtered="$(remove_managed_grub_args "${current}" all)"
    write_grub_args "${filtered}"
    regenerate_grub
    echo "Managed GRUB arguments removed. Reboot required."
  fi
}

case "${1:-}" in
  -p|--performance) tune_performance ;;
  --turbo) disable_turbo ;;
  --governor) tune_governor "${2:-performance}" ;;
  --swap) disable_swap ;;
  --caches) clear_caches ;;
  -m|--memory) tune_memory ;;
  -s|--security) tune_security ;;
  -t|--topology) tune_topology ;;
  -n|--ntp) tune_ntp ;;
  -c|--cstates) tune_cstates_only ;;
  -i|--isolate) tune_isolation_only "${ISOLATED_CORE}" ;;
  -M|--mt-rec)
    tune_performance
    tune_memory
    tune_security
    enable_topology
    tune_ntp
    tune_mtr_grub
    ;;
  -a|--all)
    tune_performance
    tune_memory
    tune_security
    tune_topology
    tune_ntp
    tune_full_grub "${ISOLATED_CORE}"
    ;;
  -r|--restore) restore_defaults ;;
  -h|--help) show_help ;;
  *) show_help; exit 1 ;;
esac
