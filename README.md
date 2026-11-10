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
- `flock` (util-linux), required to prevent concurrent system-configuration actions

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
2. Inspect the current machine state displayed automatically when the GUI launches.
3. Select **Setup R**, **Setup MTR**, or choose the individual action you would like to perform.
4. Review the command preview.
5. Click **Run Selected Action**.
6. If the action changed boot-time settings, confirm the reboot prompt or reboot later manually.
7. After rebooting, launch BESTT again, verify the active configuration,
   and reapply any required runtime settings.
8. In the `Run Program` panel, select the executable and working directory,
   specify any required runtime arguments, and enable any desired execution
   controls, then click `Run Program`.
9. Optionally, export the current system configuration as a JSON report.

Individual actions are available for Turbo Boost, Hyper-Threading, C-states, ASLR, swap, cache clearing, NTP, scaling governors, and core isolation. The scaling-governor action uses a dropdown populated from the governors available on the current machine.

For a complete step-by-step guide, see the [Complete Benchmarking Workflow](USER_MANUAL.md#20-complete-benchmarking-workflow)
in the User Manual.

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

### Restore Previous Settings

Before the first setup action, BESTT saves supported settings in the root-owned
`/var/lib/bestt/original-state.json`, including original managed GRUB parameters.
Later actions keep this snapshot, including across GUI restarts and reboots.
Snapshot read/write errors stop setup before any settings change. Actions are
serialized using `flock` (util-linux).

Restoration uses the saved boost state, SMT state, per-CPU governors, ASLR value,
and time-service running states. Unsupported settings are skipped. Each restore
step is attempted independently. A failed restoration keeps the snapshot for a
retry. If GRUB restoration requires a reboot, BESTT keeps the snapshot. After
rebooting, run `Restore Previous Settings` again to restore runtime settings that
may have reset during boot. The snapshot is removed only after this succeeds.
If no reboot is needed, successful restoration removes the snapshot immediately.
Without a snapshot, restoration shows a friendly warning and makes no changes.

- Cleared caches cannot be restored.
- Swap is restored only as enabled/disabled using `swapon -a` or `swapoff -a`;
  the exact original swap devices are not saved. If configured swap cannot be
  enabled, restoration reports a failure.
- GRUB restoration removes only parameters BESTT changed and reinstates their
  original values. Unrelated parameters, comments and other GRUB settings are
  preserved. Already-matching parameters are not recorded as changes. Manual
  edits to parameters BESTT changed are replaced by their original values.
  An assignment added by BESTT is removed on restoration if no unrelated
  arguments remain. Duplicate `GRUB_CMDLINE_LINUX` assignments are rejected.
  GRUB writes are atomic and preserve file permissions and ownership.
  GRUB is regenerated after changes; reboot before starting a new setup after
  restoring boot-time settings.
- The snapshot is the state before BESTT first modifies the machine, not factory
  defaults. Settings changed before this feature was installed cannot be recovered.

## Platform Compatibility

BESTT is designed for Linux systems but is not restricted to Ubuntu-based distributions. However, some controls depend on the processor, kernel, installed utilities, and system services.

- Turbo Boost control requires the Intel-specific `intel_pstate/no_turbo` interface and is unavailable on systems without it.
- C-state configuration uses the `intel_idle.max_cstate` and `processor.max_cstate` kernel parameters, which depend on the supported CPU idle drivers.
- CPU governors, SMT, ASLR, swap, and CPU-affinity controls may work on non-Intel processors where the corresponding Linux interfaces are supported.
- Boot-time settings require `/etc/default/grub` and either `update-grub` or `grub2-mkconfig`.
- Time-synchronization controls support specific services, primarily managed through systemd.

Unsupported settings or missing utilities are reported, and remaining independent operations are attempted. Complete application of the R and MTR configurations is therefore not guaranteed on unsupported systems. Users should verify the active system configuration before benchmarking. BESTT also reports whether system configuration or restoration was completed successfully or only partially.

## Safety Notes

- GRUB changes are tracked in the original-settings snapshot; no separate backup file is used.
- Boot-time changes require a reboot.
- After a successful reboot-required action, the GUI asks whether to run `sudo -A systemctl reboot`.
- Disabling ASLR reduces system security protections.
- Disabling swap may increase the risk of out-of-memory conditions.
- Stopping time synchronization may cause clock drift.
- Changing SMT, CPU governors, or core isolation may affect system performance.
- Incorrect boot configuration changes may prevent the system from booting normally.
- Review the active system configuration and restore previous settings after benchmarking.
