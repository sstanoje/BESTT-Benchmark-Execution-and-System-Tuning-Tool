#!/usr/bin/env bash
set -euo pipefail

read_or_unknown() {
  local path="$1"
  if [ -r "${path}" ]; then
    cat "${path}"
  else
    printf 'unknown\n'
  fi
}

online_cpus() {
  local online
  online="$(read_or_unknown /sys/devices/system/cpu/online)"
  if [ "${online}" = "unknown" ] || [ -z "${online}" ]; then
    for cpu_dir in /sys/devices/system/cpu/cpu[0-9]*; do
      [ -d "${cpu_dir}" ] || continue
      basename "${cpu_dir}" | sed 's/^cpu//'
    done
    return
  fi

  IFS=',' read -ra parts <<< "${online}"
  for part in "${parts[@]}"; do
    if [[ "${part}" == *-* ]]; then
      start="${part%-*}"
      end="${part#*-}"
      seq "${start}" "${end}"
    else
      printf '%s\n' "${part}"
    fi
  done
}

turbo_raw="$(read_or_unknown /sys/devices/system/cpu/intel_pstate/no_turbo)"
if [ "${turbo_raw}" = "1" ]; then
  turbo="disabled"
elif [ "${turbo_raw}" = "0" ]; then
  turbo="enabled"
else
  turbo="unknown"
fi

governors="$(
  for cpu in $(online_cpus); do
    governor_file="/sys/devices/system/cpu/cpu${cpu}/cpufreq/scaling_governor"
    [ -r "${governor_file}" ] && cat "${governor_file}"
  done | sort -u | paste -sd ',' -
)"
[ -n "${governors}" ] || governors="unknown"

smt_raw="$(read_or_unknown /sys/devices/system/cpu/smt/control)"
if [ "${smt_raw}" = "off" ]; then
  smt="disabled"
elif [ "${smt_raw}" = "on" ]; then
  smt="enabled"
else
  smt="${smt_raw}"
fi

aslr_raw="$(read_or_unknown /proc/sys/kernel/randomize_va_space)"
if [ "${aslr_raw}" = "0" ]; then
  aslr="disabled"
elif [ "${aslr_raw}" = "1" ] || [ "${aslr_raw}" = "2" ]; then
  aslr="enabled"
else
  aslr="unknown"
fi

if [ "$(tail -n +2 /proc/swaps 2>/dev/null | wc -l)" -gt 0 ]; then
  swap="enabled"
else
  swap="disabled"
fi

isolated="$(read_or_unknown /sys/devices/system/cpu/isolated)"
[ -n "${isolated}" ] || isolated="none"

cstate="$(read_or_unknown /sys/module/intel_idle/parameters/max_cstate)"
if [ "${cstate}" = "0" ]; then
  cstates="disabled"
elif grep -qw 'intel_idle.max_cstate=0' /proc/cmdline 2>/dev/null; then
  cstates="pending reboot"
else
  cstates="enabled"
fi

ntp="inactive"
for service in systemd-timesyncd chronyd ntp; do
  if systemctl is-active "${service}" >/dev/null 2>&1; then
    ntp="active (${service})"
    break
  fi
done

printf 'Turbo Boost: %s\n' "${turbo}"
printf 'Scaling Governor: %s (online cores only)\n' "${governors}"
printf 'C-states: %s\n' "${cstates}"
printf 'Hyper-Threading: %s\n' "${smt}"
printf 'ASLR: %s\n' "${aslr}"
printf 'Swap: %s\n' "${swap}"
printf 'NTP Syncing: %s\n' "${ntp}"
printf 'Isolated Cores: %s\n' "${isolated}"
