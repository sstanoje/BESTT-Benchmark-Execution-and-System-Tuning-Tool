#!/usr/bin/env bash
set -uo pipefail

if [ "${EUID}" -ne 0 ]; then
  echo "Please run as root (use sudo or pkexec)." >&2
  exit 1
fi

ISOLATED_CORE="${2:-3}"
GRUB_FILE="/etc/default/grub"
STATE_FILE="/var/lib/bestt/original-state.json"
STATE_HELPER="$(dirname "${BASH_SOURCE[0]}")/original_state.py"

failures=0

# Each independent step reports its result and lets the next step run.
run_step() {
  local label="$1"
  shift
  if "$@"; then
    echo "[OK] ${label}"
  else
    failures=$((failures + 1))
    if [[ "${label}" == GRUB* ]]; then
      echo "[CRITICAL] ${label} failed; boot settings were not fully applied."
    else
      echo "[WARN] ${label} failed or is unsupported; continuing."
    fi
  fi
}

write_value() {
  echo "$1" > "$2"
}

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
  -r, --restore        Restore saved previous settings
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

# Expand the kernel's online CPU list (for example, 0-2,6,8).
online_cpus() {
  local online part
  local parts=()
  online="$(cat /sys/devices/system/cpu/online)" || return 1
  [ -n "${online}" ] || return 1
  IFS=',' read -ra parts <<< "${online}"
  for part in "${parts[@]}"; do
    if [[ "${part}" == *-* ]]; then
      seq "${part%-*}" "${part#*-}" || return 1
    else
      printf '%s\n' "${part}"
    fi
  done
}

set_governor_all() {
  local preferred="$1"
  local failed=0
  local cpus cpu
  cpus="$(online_cpus)" || return 1

  for cpu in ${cpus}; do
    local fallback=""
    local governor_file="/sys/devices/system/cpu/cpu${cpu}/cpufreq/scaling_governor"
    if [ ! -f "${governor_file}" ]; then
      echo "[WARN] CPU ${cpu}: governor control unavailable."
      failed=1
      continue
    fi

    if available_governor "${cpu}" "${preferred}" >/dev/null; then
      echo "${preferred}" > "${governor_file}" || failed=1
      continue
    fi

    for candidate in schedutil ondemand powersave performance; do
      if available_governor "${cpu}" "${candidate}" >/dev/null; then
        fallback="${candidate}"
        break
      fi
    done

    echo "[WARN] CPU ${cpu}: ${preferred} unavailable; fallback: ${fallback:-none}."
    failed=1
    if [ -n "${fallback}" ]; then
      echo "${fallback}" > "${governor_file}" || failed=1
    fi
  done
  return "${failed}"
}

tune_performance() {
  echo "--- Setting performance mode ---"
  run_step "Disable Turbo Boost" disable_turbo
  run_step "CPU governors" set_governor_all performance
}

disable_turbo() {
  echo "--- Disabling Turbo Boost ---"
  if [ -f "/sys/devices/system/cpu/intel_pstate/no_turbo" ]; then
    echo "1" > /sys/devices/system/cpu/intel_pstate/no_turbo
  else
    echo "Turbo Boost control is not available on this machine."
    return 1
  fi
}

tune_governor() {
  local governor="$1"
  echo "--- Setting scaling governors to ${governor} ---"
  run_step "CPU governors" set_governor_all "${governor}"
}

tune_memory() {
  echo "--- Cleaning memory state ---"
  run_step "Disable swap" disable_swap
  run_step "Clear caches" clear_caches
}

disable_swap() {
  echo "--- Disabling swap ---"
  swapoff -a
}

clear_caches() {
  echo "--- Clearing filesystem caches ---"
  sync || return 1
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
    return 1
  fi
}

enable_topology() {
  echo "--- Enabling Hyper-Threading when supported ---"
  if [ -f "/sys/devices/system/cpu/smt/control" ]; then
    echo on > /sys/devices/system/cpu/smt/control
  else
    echo "Hyper-Threading control is not available on this machine."
    return 1
  fi
}

tune_ntp() {
  local operation="${1:-stop}"
  local found=0
  local name
  for name in systemd-timesyncd chronyd ntp; do
    if [ "$(systemctl show "$name" -p LoadState --value 2>/dev/null)" = "loaded" ]; then
      found=1
      run_step "${operation} ${name}" systemctl "$operation" "$name"
    fi
  done
  if [ "$found" -eq 0 ]; then
    if [ -x /etc/init.d/ntp ]; then
      run_step "${operation} ntp" service ntp "$operation"
    else
      echo "[WARN] No supported time-sync service found; no service changed."
      failures=$((failures + 1))
    fi
  fi
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
    echo "update-grub/grub2-mkconfig not found. Regenerate GRUB manually." >&2
    return 1
  fi
}

apply_grub_args() {
  local result
  result="$(python3 "${STATE_HELPER}" grub-set "${STATE_FILE}" "${GRUB_FILE}" "$@")" || return 1
  if [ "${result}" = unchanged ]; then
    echo "GRUB parameters already match; no changes needed."
    return 0
  fi
  regenerate_grub || {
    echo "GRUB regeneration failed. Fix the error and regenerate GRUB before rebooting." >&2
    return 1
  }
  echo "GRUB updated. Reboot required."
}

isolation_args() {
  local target_core="$1"
  local cpus cpu
  local found=0
  local affinity=""
  cpus="$(online_cpus)" || return 1

  for cpu in ${cpus}; do
    if [ "${cpu}" = "${target_core}" ]; then
      found=1
    else
      affinity="${affinity:+${affinity},}${cpu}"
    fi
  done
  if [ "${found}" -eq 0 ] || [ -z "${affinity}" ]; then
    echo "Invalid core ${target_core}; select an online CPU and leave another CPU available." >&2
    return 1
  fi

  printf '%s\n' \
    "isolcpus=domain,managed_irq,${target_core}" \
    "nohz_full=${target_core}" \
    "rcu_nocbs=${target_core}" \
    "irqaffinity=${affinity}"
}

tune_cstates_only() {
  echo "--- Disabling deep C-states through GRUB ---"
  run_step "GRUB C-states" apply_grub_args cstates processor.max_cstate=0 intel_idle.max_cstate=0
}

tune_mtr_grub() {
  echo "--- Applying MTR GRUB settings ---"
  run_step "GRUB MTR settings" apply_grub_args all processor.max_cstate=0 intel_idle.max_cstate=0
}

tune_isolation_only() {
  local target_core="$1"
  echo "--- Isolating core ${target_core} through GRUB ---"
  local output
  output="$(isolation_args "${target_core}")" || return 1
  local args=()
  mapfile -t args <<< "${output}"
  apply_grub_args isolation "${args[@]}"
}

tune_full_grub() {
  tune_cstates_only
  run_step "GRUB core isolation" tune_isolation_only "$1"
}

restore_value() {
  local current
  current="$(cat "$1")" || return 1
  [ "${current}" = "$2" ] && return 0
  write_value "$2" "$1" || return 1
  [ "$(cat "$1")" = "$2" ]
}

restore_swap() {
  if [ "$1" = on ]; then
    swapon -a || return 1
    # A manually activated swap device may not be configured in fstab.
    [ "$(tail -n +2 /proc/swaps | wc -l)" -gt 0 ]
  else
    swapoff -a
  fi
}

restore_grub() {
  local result
  result="$(python3 "${STATE_HELPER}" grub-restore "${STATE_FILE}" "${GRUB_FILE}")" || return 1
  [ "${result}" = unchanged ] && return 0
  if [ "${result}" != reboot ]; then
    regenerate_grub || return 1
    python3 "${STATE_HELPER}" grub-restored "${STATE_FILE}" "${GRUB_FILE}" || return 1
  fi
  echo "GRUB updated. Reboot required."
}

restore_defaults() {
  if [ ! -f "${STATE_FILE}" ]; then
    echo "[WARN] Nothing to restore. BESTT has no saved settings to restore. Apply a setup action first."
    return 1
  fi
  local saved kind target value
  saved="$(python3 "${STATE_HELPER}" restore "${STATE_FILE}" "${GRUB_FILE}")" || return 1
  while IFS=$'\t' read -r kind target value; do
    case "${kind}" in
      value) run_step "Restore ${target}" restore_value "${target}" "${value}" ;;
      swap) run_step "Restore swap" restore_swap "${target}" ;;
      systemctl) run_step "Restore ${target}" systemctl "${value}" "${target}" ;;
      service) run_step "Restore ${target}" service "${target}" "${value}" ;;
      grub) run_step "GRUB restoration" restore_grub ;;
    esac
  done <<< "${saved}"
  if [ "${failures}" -eq 0 ]; then
    python3 "${STATE_HELPER}" finish-restore "${STATE_FILE}" "${GRUB_FILE}" || return 1
  else
    echo "Snapshot kept for retrying restoration."
  fi
}

# Validate the action before creating a snapshot. Help never changes state.
case "${1:-}" in
  -h|--help) show_help; exit 0 ;;
  -r|--restore|-p|--performance|--turbo|--governor|--swap|--caches|-m|--memory|-s|--security|-t|--topology|-n|--ntp|-c|--cstates|-i|--isolate|-M|--mt-rec|-a|--all) ;;
  *) show_help; exit 1 ;;
esac

# Keep concurrent GUI/CLI actions from overwriting or restoring the same snapshot.
install -d -m 700 /var/lib/bestt || exit 1
exec 9>/var/lib/bestt/lock || exit 1
flock -n 9 || { echo "Another BESTT action is running (or flock is unavailable)." >&2; exit 1; }
if [[ "${1}" != "-r" && "${1}" != "--restore" ]]; then
  python3 "${STATE_HELPER}" save "${STATE_FILE}" "${GRUB_FILE}" || exit 1
fi

case "${1:-}" in
  -p|--performance) tune_performance ;;
  --turbo) run_step "Disable Turbo Boost" disable_turbo ;;
  --governor) tune_governor "${2:-performance}" ;;
  --swap) run_step "Disable swap" disable_swap ;;
  --caches) run_step "Clear caches" clear_caches ;;
  -m|--memory) tune_memory ;;
  -s|--security) run_step "Disable ASLR" tune_security ;;
  -t|--topology) run_step "Disable SMT" tune_topology ;;
  -n|--ntp) tune_ntp ;;
  -c|--cstates) tune_cstates_only ;;
  -i|--isolate) run_step "GRUB core isolation" tune_isolation_only "${ISOLATED_CORE}" ;;
  -M|--mt-rec)
    tune_performance
    tune_memory
    run_step "Disable ASLR" tune_security
    run_step "Enable SMT" enable_topology
    tune_ntp
    tune_mtr_grub
    ;;
  -a|--all)
    tune_performance
    tune_memory
    run_step "Disable ASLR" tune_security
    run_step "Disable SMT" tune_topology
    tune_ntp
    tune_full_grub "${ISOLATED_CORE}"
    ;;
  -r|--restore) restore_defaults || exit 1 ;;
  -h|--help) show_help; exit 0 ;;
  *) show_help; exit 1 ;;
esac

if [ "${failures}" -gt 0 ]; then
  if [[ "${1:-}" == "-r" || "${1:-}" == "--restore" ]]; then
    echo "Result: PARTIALLY RESTORED (${failures} failed or unsupported steps)."
  else
    echo "Result: PARTIALLY APPLIED (${failures} failed or unsupported steps)."
  fi
  echo "Verify the system configuration before benchmarking."
  exit 1
fi
echo "Result: SUCCESS."
