# BESTT - Benchmark Execution and System Tuning Tool

A simple desktop utility for applying and inspecting Linux system settings used for stable short-running benchmarking and for running executables under selected process-level controls.

The tool provides a simple Python/Tkinter GUI that wraps a small set of shell-script actions. It provides two main setups:

- **R / Recommended**: high-stability setup for single-threaded benchmarks and same-program multi-threaded comparisons.
- **MTR / Multi-threaded Recommended**: stable setup that preserves multi-threaded execution for cross-benchmark comparisons.

## Scope

This tool can configure a Linux machine and record the active configuration. It can also run an executable with additional command-line arguments, elevated priority, and optional `taskset` and `numactl` settings.

## Requirements

- Linux
- Python 3.8+
- Tkinter (`python3-tk` on Debian/Ubuntu)
- `sudo` for applying setup actions

The status view works without root. Applying actions uses `sudo -A` with a bundled graphical password prompt.

## Run From Source

```bash
./run_BESTT
```

The launcher checks the required dependencies before starting the GUI. The tool can also be started directly with `python3 -m BESTT`.

## Install Editable

```bash
python3 -m pip install -e .
BESTT
```

## Usage

1. Launch the GUI.
2. Click **Refresh Status** to inspect the current machine state.
3. Select **Setup R**, **Setup MTR**, or choose the individual action you would like to perform.
4. Review the command preview.
5. Click **Run Selected Action**.
6. If the action changed boot-time settings, confirm the reboot prompt or reboot later manually.
7. Export the current configuration as JSON and attach it to benchmark results.

Individual actions are available for Turbo Boost, Hyper-Threading, C-states, ASLR, swap, cache clearing, NTP, scaling governors, and core isolation. The scaling-governor action uses a dropdown populated from the governors available on the current machine.

## Profiles

### Setup R

Applies:

- disables Turbo Boost
- sets CPU governors to `performance`
- disables swap and drops filesystem caches
- disables ASLR
- stops NTP time synchronization
- disables deep C-states through GRUB
- disables Hyper-Threading
- isolates one selected CPU core through GRUB

This action requires a reboot for GRUB settings to take effect.

### Setup MTR

Applies:

- disables Turbo Boost
- sets CPU governors to `performance`
- disables swap and drops filesystem caches
- disables ASLR
- stops NTP time synchronization
- disables deep C-states through GRUB
- enables Hyper-Threading
- removes BESTT core-isolation arguments from GRUB

This action requires a reboot for GRUB settings to take effect.

### Restore Common Defaults

Performs a best-effort restore:

- enables Turbo Boost
- sets CPU governors to `schedutil`, `ondemand`, or the first available governor
- enables ASLR
- enables Hyper-Threading
- enables swap memory
- restarts common time-sync services
- removes BESTT GRUB arguments

This is not a full machine rollback. It preserves unrelated GRUB arguments and only removes arguments managed by this tool.

## Safety Notes

- GRUB edits create `/etc/default/grub.bestt.bak` the first time the script modifies the file.
- Boot-time changes require a reboot.
- After a successful reboot-required action, the GUI asks whether to run `sudo -A systemctl reboot`.
- Review command previews before applying actions.
