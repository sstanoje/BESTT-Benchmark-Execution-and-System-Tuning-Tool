# BESTT - User Manual

## 1. Purpose

BESTT is a simple Linux desktop application for preparing a machine for stable short-running benchmarking and controlled benchmark execution. It provides buttons for applying predefined benchmarking setups, individual system-tuning actions, inspecting the current machine state, previewing commands before execution, running a selected executable, and exporting a JSON report of the active configuration.

The application is intended for benchmarking experiments where the system configuration must be controlled and documented.

## 2. Requirements

- Linux
- Python 3.8 or newer
- Tkinter, usually available as `python3-tk`
- `sudo`
- Permission to change system settings

Optional tools are used only by specific features:

- `taskset` for program core pinning
- `numactl` for NUMA pinning
- `systemctl` for time-service status/actions and reboot
- `update-grub` or `grub2-mkconfig` for automatic GRUB regeneration

Install Tkinter on Debian/Ubuntu systems with:

```bash
sudo apt install python3-tk
```

## 3. Starting the Application

From the repository root:

```bash
./run_BESTT
```

or

```bash
python3 -m BESTT
```

The launcher checks the required dependencies before starting the GUI. The application opens maximized by default.

## 4. Administrator Password Prompt

System-changing actions are executed through:

```bash
sudo -A
```

The application includes a small graphical askpass helper, so the administrator password is requested in a GUI dialog instead of the terminal.

The password is not written to the output panel or the exported report.

## 5. Window Layout

The window has two main areas:

- Left panel: run settings, profile buttons, advanced action buttons, and bottom control buttons.
- Right panel: current system status, program runner, setup-action command preview, and command output.

The currently selected action button is shown with a darker grey shaded style.

## 6. Action Parameters

These controls provide values used by selected setup actions. They are not global application settings.

### Core

A dropdown menu containing currently online CPU cores, starting from core `1`.

Core `0` is intentionally excluded from the dropdown. The selected core is used by actions that isolate a CPU core:

- `Setup R`
- `Isolate Core`

Example:

```text
Core: 3
```

When `Setup R` is selected, the generated command uses that core:

```bash
sudo -A bash BESTT/scripts/setup_system_for_benchmarking.sh --all 3
```

### Scaling governor

A dropdown menu containing CPU scaling governors available on currently online CPU cores.

The selected governor is used by the `Set Scaling Governor` advanced action.

Example:

```text
Scaling governor: performance
```

Generated command pattern:

```bash
sudo -A bash BESTT/scripts/setup_system_for_benchmarking.sh --governor <governor>
```

## 7. Profile Buttons

Profile buttons apply complete benchmarking configurations.

### Setup R

Applies the recommended benchmarking configuration for high-stability measurements.

It performs the following actions:

- disables Turbo Boost
- sets CPU scaling governors to `performance`
- disables deeper C-states
- disables Hyper-Threading
- isolates the selected CPU core
- disables ASLR
- stops NTP time synchronization
- disables swap memory
- clears system caches

Uses the selected core from the `Core` dropdown.

Command pattern:

```bash
sudo -A bash BESTT/scripts/setup_system_for_benchmarking.sh --all <core>
```

This action changes boot-time settings and requires a reboot.

### Setup MTR

Applies the recommended benchmarking configuration for multi-threaded benchmarks.

It performs the following actions:

- disables Turbo Boost
- sets CPU scaling governors to `performance`
- disables deeper C-states
- enables Hyper-Threading
- does not isolate a core
- disables ASLR
- stops NTP time synchronization
- disables swap memory
- clears system caches

Command:

```bash
sudo -A bash BESTT/scripts/setup_system_for_benchmarking.sh --mt-rec
```

This action changes boot-time settings and requires a reboot.

### Restore Common Defaults

Restores common default system behavior as a best-effort operation.

It performs the following actions:

- enables Turbo Boost
- restores a common CPU governor such as `schedutil`, `ondemand`, or the first available governor
- enables ASLR
- enables Hyper-Threading
- enables swap memory
- restarts common time synchronization services (NTP)
- removes BESTT GRUB arguments

Command:

```bash
sudo -A bash BESTT/scripts/setup_system_for_benchmarking.sh --restore
```

This action can require a reboot when boot-time settings are changed.

## 8. Advanced Action Buttons

Advanced actions apply individual settings. They are useful for testing one factor at a time.

### Disable Turbo Boost

Disables Turbo Boost.

Command:

```bash
sudo -A bash BESTT/scripts/setup_system_for_benchmarking.sh --turbo
```

### Disable Hyper-Threading

Disables Hyper-Threading.

Command:

```bash
sudo -A bash BESTT/scripts/setup_system_for_benchmarking.sh --topology
```

### Disable C-states

Configures the system to disable deeper C-states by changing GRUB kernel arguments.

Command:

```bash
sudo -A bash BESTT/scripts/setup_system_for_benchmarking.sh --cstates
```

This action requires a reboot.

### Disable ASLR

Disables address-space layout randomization.

Command:

```bash
sudo -A bash BESTT/scripts/setup_system_for_benchmarking.sh --security
```

### Disable Swap

Disables swap memory.

Command:

```bash
sudo -A bash BESTT/scripts/setup_system_for_benchmarking.sh --swap
```

### Clear Caches

Synchronizes disks and drops filesystem caches.

Command:

```bash
sudo -A bash BESTT/scripts/setup_system_for_benchmarking.sh --caches
```

### Stop NTP

Stops common time synchronization services.

Command:

```bash
sudo -A bash BESTT/scripts/setup_system_for_benchmarking.sh --ntp
```

### Set Scaling Governor

Sets online CPU scaling governors to the value selected in the `Scaling governor` dropdown.

Command pattern:

```bash
sudo -A bash BESTT/scripts/setup_system_for_benchmarking.sh --governor <governor>
```

### Isolate Core

Adds GRUB kernel arguments for isolating the selected core from normal scheduler activity.

Command pattern:

```bash
sudo -A bash BESTT/scripts/setup_system_for_benchmarking.sh --isolate <core>
```

This action requires a reboot.

## 9. Bottom Control Buttons

### Run Selected Action

Runs the currently selected profile or advanced action.

Before execution, the application opens a confirmation popup showing the exact command that will be executed.

For actions that require a reboot, the confirmation popup also states that boot-time settings are changed.

### Refresh Status

Reloads the current system state and updates the status table.

Use this after applying an action, rebooting, or manually changing system settings outside the GUI.

### Export Report

Exports the current system configuration as a JSON file.

Default file name:

```text
BESTT-report.json
```

## 10. Current System Status

The status table has three columns:

- `Setting`: name of the system setting.
- `Value`: current value detected by the GUI.
- `Explanation`: practical meaning of the current value.

The table is divided into groups:

- `CPU and Power`
- `Kernel and Memory`
- `Isolation`

## 11. Status Settings and Explanations

### Turbo Boost

Possible values:

- `enabled`
- `disabled`
- `unknown`

Meaning:

- `enabled`: CPU cores may temporarily use turbo frequencies. This can improve speed but can also add run-to-run variability.
- `disabled`: turbo frequencies are prevented, reducing one source of frequency variation during benchmarks.
- `unknown`: the GUI could not read the Turbo Boost status.

### Scaling Governor

Possible values include:

- `performance`
- `powersave`
- `schedutil`
- `ondemand`
- `mixed`
- `unknown`

Meaning:

- `performance`: keeps online CPU cores at high frequency instead of dynamically scaling them.
- `powersave`: can dynamically change CPU frequencies based on load, which can introduce frequency variation.
- `schedutil`: can dynamically change CPU frequencies based on load, which can introduce frequency variation.
- `ondemand`: dynamically changes CPU frequency based on observed CPU utilization.
- `mixed`: online cores do not all use the same governor.
- `unknown`: the GUI could not determine the governor on online cores.

Only online CPU cores are checked.

### C-states

Possible values:

- `enabled`
- `disabled`
- `pending reboot`
- `unknown`

Meaning:

- `enabled`: deeper CPU sleep states are allowed. They save power but can add wake-up latency.
- `disabled`: deeper CPU sleep states are prevented, reducing wake-up latency variability.
- `pending reboot`: boot settings were changed, but the active kernel state has not changed yet.
- `unknown`: the GUI could not determine the C-state status.

### Hyper-Threading

Possible values:

- `enabled`
- `disabled`
- `unknown`

Meaning:

- `enabled`: two hardware threads may share one physical core. This can improve throughput but adds shared-core interference.
- `disabled`: sibling hardware threads do not share a core, reducing interference.
- `unknown`: the GUI could not determine the Hyper-Threading state.

### ASLR

Possible values:

- `enabled`
- `disabled`
- `unknown`

Meaning:

- `enabled`: randomizes memory layout between runs. This improves security but can add layout variation.
- `disabled`: keeps memory layout more stable between runs.
- `unknown`: the GUI could not read the ASLR setting.

### Swap

Possible values:

- `enabled`
- `disabled`
- `unknown`

Meaning:

- `enabled`: memory pages may move to disk, which can cause large timing noise.
- `disabled`: swap activity is prevented during benchmarks.
- `unknown`: the GUI could not read swap status.

### NTP Syncing

Possible values:

- `active`
- `inactive`

Meaning:

- `active`: a time synchronization service is running and may adjust system time.
- `inactive`: common time synchronization services are stopped.

### Isolated Cores

Possible values:

- `none`
- a core list, for example `3`
- `pending reboot`

Meaning:

- `none`: no CPU core is isolated for benchmark execution.
- a core list: listed core or cores are isolated from normal scheduler activity.
- `pending reboot`: core isolation was configured in boot settings but is not active yet.

## 12. Run Program Panel

The `Run Program` panel starts a selected benchmark executable from the GUI.

This panel is separate from the setup actions. Setup actions configure the system; the program runner starts the benchmark or other executable after the system has been configured.

### Executable

Path to the executable that should be run.

The `Browse` button opens a large in-application file browser. Select a file and click `Select File`, or double-click a directory to enter it.

### Working dir

Working directory used when starting the program.

The `Browse` button opens a large in-application directory browser. Select a directory and click `Select Directory`.

### Browser Controls

The file and directory browser popups contain:

- `Location`: current directory path.
- `Go`: opens the path typed in `Location`.
- `Up`: moves to the parent directory.
- `Home`: moves to the user's home directory.
- `Cancel`: closes the popup without selecting anything.
- `Select File` or `Select Directory`: confirms the selected item.

### Command-line args after executable

Additional command-line arguments appended after the executable.

Example:

```text
--warmup 10 --iterations 50 --input "data file.txt"
```

If the executable is `/home/user/bench`, the command preview will place these arguments after the executable:

```bash
/home/user/bench --warmup 10 --iterations 50 --input 'data file.txt'
```

Arguments are parsed as command-line arguments, so quotes can be used for values that contain spaces.

### sudo

Runs the selected program through:

```bash
sudo -A
```

The same graphical password prompt is used.

### elevated priority

Runs the selected program with elevated process priority:

```bash
nice -n -20
```

This usually requires administrator privileges. When `elevated priority` is selected, `sudo` is checked automatically. When `elevated priority` is cleared, `sudo` is restored to the state it had before elevated priority was selected.

### pin to core

Runs the selected program on a selected CPU core using:

```bash
taskset -c <core>
```

If an isolated core is currently active, it is selected by default. If no isolated core is active, the field starts empty and the user can choose a currently available core from the dropdown.

### NUMA node

Runs the selected program bound to the selected NUMA node using:

```bash
numactl --cpunodebind=<node> --membind=<node>
```

This option requires `numactl`.

### Program command

Shows the complete command that will be executed for the selected program. This preview updates automatically when fields or checkboxes change.

The command is built in this order:

```text
sudo -A  numactl ...  taskset -c <core>  nice -n -20  <executable>  <command-line args>
```

Parts are included only when the corresponding option is selected.

### Run Program

Opens a confirmation popup showing:

- working directory
- exact command
- `Run` button
- `Cancel` button

When confirmed, the program runs in the background. Standard output, standard error, and the exit code are appended to the output panel after the program finishes.

## 13. Command Preview

The command preview shows:

- the selected action name
- what the selected action does
- the exact command that will be executed

Example:

```text
Action
  Disable Turbo Boost

What it does
  Disable Turbo Boost.

Exact command
  sudo -A bash .../setup_system_for_benchmarking.sh --turbo
```

The command preview is read-only.

## 14. Confirmation Popups

When `Run Selected Action` or `Run Program` is clicked, a confirmation popup appears.

The popup contains:

- action name or program run heading
- exact command
- reboot warning when relevant
- `Run` button
- `Cancel` button

The popup size is calculated from the text using Tk font measurements. It is also resizable.

## 15. Reboot Prompt

After a successful action that requires a reboot, the GUI asks whether to reboot immediately.

If confirmed, the application runs:

```bash
sudo -A systemctl reboot
```

If declined, the system remains running and the user must reboot manually later.

After rebooting, click `Refresh Status` to check the active system state. Some runtime-controlled settings may return to the state defined by the system firmware or BIOS after reboot. If any such setting is not in the desired state, run the selected setup profile again, or apply the required changes individually through the tool GUI, before collecting benchmark measurements. If the boot-time settings are already shown as applied after the reboot, no additional reboot is needed, even if the selected profile includes actions that normally require a reboot.

## 16. Output Panel

The output panel shows:

- commands executed by the GUI
- standard output from setup scripts
- standard error from setup scripts
- standard output from programs started through `Run Program`
- standard error from programs started through `Run Program`
- exit code
- reboot-related messages

The output panel is read-only.

## 17. JSON Report Format

The report is exported as JSON.

Example:

```json
{
  "Turbo Boost": "enabled",
  "Scaling Governor": {
    "core 0": "powersave",
    "core 1": "powersave",
    "core 2": "powersave"
  },
  "C-states": "disabled",
  "Hyper-Threading": "enabled",
  "ASLR": "enabled",
  "Swap": "enabled",
  "NTP Syncing": "active",
  "Isolated Cores": "3"
}
```

The report order matches the GUI status order.

The `Scaling Governor` field is an object because each online CPU core can have its own governor.

## 18. Reboot-Requiring Actions

The following actions can require a reboot:

- `Setup R`
- `Setup MTR`
- `Restore Common Defaults`
- `Disable C-states`
- `Isolate Core`

The GUI prompts for reboot after successful execution of these actions.

## 19. Notes and Limitations

- The application is intended for Linux systems.
- Some settings depend on CPU, kernel, and distribution support.
- C-state and core-isolation settings are applied through GRUB and require reboot.
- The status table reflects the currently active system state. Boot-time changes may appear as `pending reboot`.
- Setup actions use fixed predefined commands.
- The program runner executes a selected executable as an argument list, not through a shell command string.
- The exported report records system state, not benchmark results.
