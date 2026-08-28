from __future__ import annotations

import os
import re
import queue
import shlex
import shutil
import threading
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .actions import (
    build_action_command,
    build_reboot_command,
    command_preview,
    run_action_command,
    script_is_present,
)
from .profiles import ACTION_SPECS, actions_by_category, get_action
from .system_state import collect_status, export_report_json


class BESTT(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("BESTT")
        self.geometry("1800x1100")
        self.minsize(1500, 900)
        self._start_fullscreen()

        self.selected_action_key = tk.StringVar(value="recommended")
        self.core_var = tk.StringVar(value="3")
        self.available_cores = self._available_core_ids()
        self.available_governors = self._available_governors()
        self.governor_var = tk.StringVar(value="performance" if "performance" in self.available_governors else self.available_governors[0])
        self.available_numa_nodes = self._available_numa_nodes()
        self.available_isolated_cores = self._isolated_core_ids()
        self.available_pin_cores = self._available_pin_core_ids()
        self.status_items = []
        self.result_queue: "queue.Queue[tuple]" = queue.Queue()
        self.action_buttons = {}
        self.program_path_var = tk.StringVar()
        self.program_workdir_var = tk.StringVar(value=str(Path.home()))
        self.additional_args_var = tk.StringVar()
        self.run_program_sudo_var = tk.BooleanVar(value=False)
        self.pin_numa_var = tk.BooleanVar(value=False)
        self.numa_node_var = tk.StringVar(value=self.available_numa_nodes[0])
        self.pin_isolated_core_var = tk.BooleanVar(value=False)
        self.isolated_core_var = tk.StringVar(value=self.available_isolated_cores[0] if self.available_isolated_cores else "")
        self.elevated_priority_var = tk.BooleanVar(value=False)
        self._sudo_before_elevated_priority = None

        self._configure_style()
        self._build_widgets()
        self._select_action("recommended")
        self.refresh_status()

    def _start_fullscreen(self) -> None:
        try:
            self.state("zoomed")
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)
            except tk.TclError:
                self.attributes("-fullscreen", True)

    def _configure_style(self) -> None:
        self.default_font = tkfont.nametofont("TkDefaultFont")
        self.default_font.configure(size=11)
        self.heading_font = tkfont.nametofont("TkHeadingFont")
        self.heading_font.configure(size=12, weight="bold")
        self.status_font = tkfont.Font(family=self.default_font.actual("family"), size=13)
        self.status_heading_font = tkfont.Font(family=self.default_font.actual("family"), size=13, weight="bold")
        self.fixed_font = tkfont.Font(family="DejaVu Sans Mono", size=11)
        self.option_font = tkfont.Font(family=self.default_font.actual("family"), size=13)

        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=self.default_font)
        style.configure("TButton", padding=(12, 9))
        style.configure("Action.TButton", padding=(12, 9))
        style.configure("Run.TButton", padding=(12, 9), background="#c4c4c4")
        style.map("Run.TButton", background=[("active", "#adadad"), ("!disabled", "#c4c4c4")])
        style.configure("Refresh.TButton", padding=(12, 9), background="#d4d4d4")
        style.map("Refresh.TButton", background=[("active", "#bdbdbd"), ("!disabled", "#d4d4d4")])
        style.configure("Export.TButton", padding=(12, 9), background="#e4e4e4")
        style.map("Export.TButton", background=[("active", "#cccccc"), ("!disabled", "#e4e4e4")])
        style.configure(
            "Selected.Action.TButton",
            padding=(12, 9),
            relief="sunken",
            background="#b8bcc2",
            bordercolor="#4b5563",
            lightcolor="#d8dadd",
            darkcolor="#4b5563",
        )
        style.map(
            "Selected.Action.TButton",
            background=[("active", "#a8adb4"), ("!disabled", "#b8bcc2")],
            relief=[("pressed", "sunken"), ("!pressed", "sunken")],
        )
        style.configure("TLabel", padding=(0, 2))
        style.configure("Large.TCheckbutton", font=self.option_font, padding=(10, 9), indicatorsize=20)
        style.configure("TLabelframe.Label", font=self.heading_font)
        style.configure("Treeview", font=self.status_font, rowheight=46)
        style.configure("Treeview.Heading", font=self.status_heading_font)

    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=0, minsize=390)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left = ttk.Frame(self, padding=14)
        left.grid(row=0, column=0, sticky="nsew")
        right = ttk.Frame(self, padding=(0, 14, 14, 14))
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=3)
        right.rowconfigure(3, weight=0)
        right.rowconfigure(5, weight=2)
        right.rowconfigure(7, weight=3)

        self._build_action_panel(left)
        self._build_status_panel(right)
        self._build_program_panel(right)
        self._build_preview_panel(right)
        self._build_log_panel(right)

    def _build_action_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(7, weight=1)

        controls = ttk.LabelFrame(parent, text="Action Parameters", padding=12)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Choose core to isolate").grid(row=0, column=0, sticky="w", padx=(0, 8))
        if self.core_var.get() not in self.available_cores:
            self.core_var.set(self.available_cores[0])
        core = ttk.Combobox(
            controls,
            textvariable=self.core_var,
            values=self.available_cores,
            state="readonly",
            width=10,
        )
        core.grid(row=0, column=1, sticky="w")
        core.bind("<<ComboboxSelected>>", lambda _event: self.update_preview())

        ttk.Label(controls, text="Scaling governor").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(10, 0))
        self.governor_combo = ttk.Combobox(
            controls,
            textvariable=self.governor_var,
            values=self.available_governors,
            state="readonly",
            width=16,
        )
        self.governor_combo.grid(row=1, column=1, sticky="w", pady=(10, 0))
        self.governor_combo.bind("<<ComboboxSelected>>", lambda _event: self.update_preview())

        profiles = ttk.LabelFrame(parent, text="Setups", padding=12)
        profiles.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        profiles.columnconfigure(0, weight=1)
        for row, action in enumerate(actions_by_category("Profiles")):
            button = ttk.Button(
                profiles,
                text=action.label,
                style="Action.TButton",
                command=lambda key=action.key: self._select_action(key),
            )
            button.grid(row=row, column=0, sticky="ew", pady=4)
            self.action_buttons[action.key] = button

        advanced = ttk.LabelFrame(parent, text="Advanced Actions", padding=12)
        advanced.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        advanced.columnconfigure(0, weight=1)
        for row, action in enumerate(actions_by_category("Advanced")):
            button = ttk.Button(
                advanced,
                text=action.label,
                style="Action.TButton",
                command=lambda key=action.key: self._select_action(key),
            )
            button.grid(row=row, column=0, sticky="ew", pady=4)
            self.action_buttons[action.key] = button

        ttk.Button(parent, text="Run Selected Action", style="Run.TButton", command=self.run_selected_action).grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(28, 6),
        )
        ttk.Button(parent, text="Refresh Status", style="Refresh.TButton", command=self.refresh_status).grid(
            row=4,
            column=0,
            sticky="ew",
            pady=(0, 6),
        )
        ttk.Button(parent, text="Export Report", style="Export.TButton", command=self.export_status).grid(
            row=5,
            column=0,
            sticky="ew",
        )

    def _build_status_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Current System Status").grid(row=0, column=0, sticky="w")
        self.status_summary = ttk.Label(parent, text="", justify="left")
        self.status_summary.grid(row=0, column=0, sticky="e")

        frame = ttk.Frame(parent)
        frame.grid(row=1, column=0, sticky="nsew", pady=(6, 14))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.status_tree = ttk.Treeview(
            frame,
            columns=("value", "explanation"),
            show="tree headings",
            height=10,
        )
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=self.status_tree.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=self.status_tree.xview)
        self.status_tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.status_tree.tag_configure("group", background="#eeeeee", font=self.status_heading_font)

        self.status_tree.heading("#0", text="Setting")
        self.status_tree.heading("value", text="Value")
        self.status_tree.heading("explanation", text="Explanation")
        self.status_tree.column("#0", width=280, minwidth=200, anchor="w", stretch=True)
        self.status_tree.column("value", width=180, minwidth=140, anchor="w", stretch=True)
        self.status_tree.column("explanation", width=740, minwidth=360, anchor="w", stretch=True)
        self.status_tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.bind("<Configure>", self._resize_status_columns)

    def _build_preview_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Command Preview").grid(row=4, column=0, sticky="w")
        self.preview = self._build_scrolled_text(parent, row=5, height=7, pady=(6, 14))

    def _build_log_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Output").grid(row=6, column=0, sticky="w")
        self.log = self._build_scrolled_text(parent, row=7, height=13, pady=(6, 0))

    def _build_program_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="Run Program", padding=10)
        panel.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        panel.columnconfigure(1, weight=1)
        panel.columnconfigure(4, weight=1)

        ttk.Label(panel, text="Executable").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 6))
        ttk.Entry(panel, textvariable=self.program_path_var).grid(row=0, column=1, columnspan=4, sticky="ew", pady=(0, 6))
        ttk.Button(panel, text="Browse", command=self._browse_program).grid(row=0, column=5, sticky="ew", padx=(8, 0), pady=(0, 6))

        ttk.Label(panel, text="Working dir").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 6))
        ttk.Entry(panel, textvariable=self.program_workdir_var).grid(row=1, column=1, columnspan=4, sticky="ew", pady=(0, 6))
        ttk.Button(panel, text="Browse", command=self._browse_workdir).grid(row=1, column=5, sticky="ew", padx=(8, 0), pady=(0, 6))

        ttk.Label(panel, text="Command-line args after executable").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(4, 6))
        ttk.Entry(panel, textvariable=self.additional_args_var).grid(row=2, column=1, columnspan=5, sticky="ew", pady=(4, 6))

        options = ttk.Frame(panel)
        options.grid(row=3, column=0, columnspan=6, sticky="ew", pady=(8, 12))
        for column in range(8):
            options.columnconfigure(column, weight=1 if column in {1, 3, 5, 7} else 0)

        ttk.Checkbutton(
            options,
            text="sudo",
            variable=self.run_program_sudo_var,
            command=self._on_program_sudo_changed,
            style="Large.TCheckbutton",
        ).grid(row=0, column=0, sticky="w", padx=(0, 18))
        ttk.Checkbutton(
            options,
            text="elevated priority",
            variable=self.elevated_priority_var,
            command=self._on_elevated_priority_changed,
            style="Large.TCheckbutton",
        ).grid(row=0, column=1, sticky="w", padx=(0, 18))
        self.pin_isolated_check = ttk.Checkbutton(
            options,
            text="pin to core",
            variable=self.pin_isolated_core_var,
            command=self.update_program_preview,
            style="Large.TCheckbutton",
        )
        self.pin_isolated_check.grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.isolated_core_combo = ttk.Combobox(
            options,
            textvariable=self.isolated_core_var,
            values=self.available_pin_cores,
            state="readonly",
            width=8,
        )
        self.isolated_core_combo.grid(row=0, column=3, sticky="w", padx=(0, 12))
        self.isolated_core_combo.bind("<<ComboboxSelected>>", lambda _event: self.update_program_preview())

        ttk.Checkbutton(
            options,
            text="NUMA node",
            variable=self.pin_numa_var,
            command=self.update_program_preview,
            style="Large.TCheckbutton",
        ).grid(row=0, column=4, sticky="w", padx=(0, 8))
        self.numa_node_combo = ttk.Combobox(
            options,
            textvariable=self.numa_node_var,
            values=self.available_numa_nodes,
            state="readonly",
            width=8,
        )
        self.numa_node_combo.grid(row=0, column=5, sticky="w", padx=(0, 12))
        self.numa_node_combo.bind("<<ComboboxSelected>>", lambda _event: self.update_program_preview())

        ttk.Label(panel, text="Program command").grid(row=5, column=0, sticky="nw", padx=(0, 8))
        self.program_preview = tk.Text(
            panel,
            height=3,
            wrap="word",
            font=self.fixed_font,
            padx=8,
            pady=6,
            undo=False,
        )
        self._make_text_read_only(self.program_preview)
        self.program_preview.grid(row=5, column=1, columnspan=4, sticky="ew")
        ttk.Button(panel, text="Run Program", style="Run.TButton", command=self.run_program).grid(row=5, column=5, sticky="nsew", padx=(8, 0))

        for variable in (
            self.program_path_var,
            self.program_workdir_var,
            self.additional_args_var,
        ):
            variable.trace_add("write", lambda *_args: self.update_program_preview())
        self.update_program_preview()

    def _build_scrolled_text(
        self,
        parent: ttk.Frame,
        *,
        row: int,
        height: int,
        pady,
    ) -> tk.Text:
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="nsew", pady=pady)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        text = tk.Text(
            frame,
            height=height,
            wrap="word",
            font=self.fixed_font,
            padx=10,
            pady=8,
            undo=False,
        )
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=yscroll.set)
        self._make_text_read_only(text)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        return text

    def _resize_status_columns(self, event) -> None:
        total = max(event.width - 28, 760)
        self.status_tree.column("#0", width=int(total * 0.24))
        self.status_tree.column("value", width=int(total * 0.16))
        self.status_tree.column("explanation", width=int(total * 0.60))

    def _select_action(self, key: str) -> None:
        self.selected_action_key.set(key)
        self._update_selected_action_button(key)
        self.update_preview()

    def _update_selected_action_button(self, selected_key: str) -> None:
        for key, button in self.action_buttons.items():
            style = "Selected.Action.TButton" if key == selected_key else "Action.TButton"
            button.configure(style=style)

    def _current_core(self) -> int:
        try:
            return int(self.core_var.get())
        except (TypeError, ValueError):
            return int(self.available_cores[0])

    def _available_core_ids(self):
        online_ids = self._online_core_ids()
        cpu_ids = []
        for path in Path("/sys/devices/system/cpu").glob("cpu[0-9]*"):
            match = re.fullmatch(r"cpu(\d+)", path.name)
            if match:
                cpu_id = int(match.group(1))
                if cpu_id >= 1 and (not online_ids or cpu_id in online_ids):
                    cpu_ids.append(cpu_id)

        if not cpu_ids:
            max_core = max(1, (os.cpu_count() or 2) - 1)
            cpu_ids = list(range(1, max_core + 1))

        return [str(cpu_id) for cpu_id in sorted(cpu_ids)]

    def _available_governors(self):
        online_ids = self._online_core_ids()
        governors = set()
        for path in sorted(Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/scaling_available_governors")):
            match = re.fullmatch(r"cpu(\d+)", path.parent.parent.name)
            if match and online_ids and int(match.group(1)) not in online_ids:
                continue
            try:
                governors.update(path.read_text(encoding="utf-8").strip().split())
            except OSError:
                continue
        return sorted(governors) if governors else ["performance"]

    def _online_core_ids(self):
        online_file = Path("/sys/devices/system/cpu/online")
        try:
            text = online_file.read_text(encoding="utf-8").strip()
        except OSError:
            return set()

        ids = set()
        for part in text.split(","):
            if "-" in part:
                start, end = part.split("-", 1)
                ids.update(range(int(start), int(end) + 1))
            elif part:
                ids.add(int(part))
        return ids

    def _available_numa_nodes(self):
        nodes = []
        for path in Path("/sys/devices/system/node").glob("node[0-9]*"):
            match = re.fullmatch(r"node(\d+)", path.name)
            if match:
                nodes.append(int(match.group(1)))
        if not nodes:
            return ["0"]
        return [str(node) for node in sorted(nodes)]

    def _isolated_core_ids(self):
        isolated_file = Path("/sys/devices/system/cpu/isolated")
        try:
            text = isolated_file.read_text(encoding="utf-8").strip()
        except OSError:
            return []
        return [str(cpu_id) for cpu_id in self._parse_cpu_id_list(text)]

    def _available_pin_core_ids(self):
        core_ids = {int(core) for core in self.available_cores}
        core_ids.update(int(core) for core in self.available_isolated_cores)
        return [str(cpu_id) for cpu_id in sorted(core_ids)]

    def _parse_cpu_id_list(self, text: str):
        ids = []
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start, end = part.split("-", 1)
                try:
                    ids.extend(range(int(start), int(end) + 1))
                except ValueError:
                    continue
                continue
            try:
                ids.append(int(part))
            except ValueError:
                continue
        return sorted(set(ids))

    def update_preview(self) -> None:
        key = self.selected_action_key.get()
        try:
            command = build_action_command(
                key,
                core=self._current_core(),
                governor=self.governor_var.get(),
                privilege="sudo",
            )
            action = get_action(key)
            command_text = command_preview(command)
            description = self._format_action_description(action)
            text = (
                f"Action\n"
                f"  {action.label}\n\n"
                f"What it does\n"
                f"  {description}\n\n"
                f"Exact command\n"
                f"  {command_text}"
            )
        except Exception as exc:
            text = f"Cannot build command: {exc}"
        self._set_text(self.preview, text)

    def update_program_preview(self) -> None:
        try:
            command = self._build_program_command(validate=False)
            workdir = self._program_working_dir(validate=False) or os.getcwd()
            text = f"Working directory: {workdir}\nCommand: {command_preview(command)}"
        except Exception as exc:
            text = f"Cannot build program command: {exc}"
        self._set_text(self.program_preview, text)

    def _on_program_sudo_changed(self) -> None:
        if self.elevated_priority_var.get() and not self.run_program_sudo_var.get():
            self.run_program_sudo_var.set(True)
        self.update_program_preview()

    def _on_elevated_priority_changed(self) -> None:
        if self.elevated_priority_var.get():
            self._sudo_before_elevated_priority = self.run_program_sudo_var.get()
            self.run_program_sudo_var.set(True)
        else:
            if self._sudo_before_elevated_priority is not None:
                self.run_program_sudo_var.set(self._sudo_before_elevated_priority)
            self._sudo_before_elevated_priority = None
        self.update_program_preview()

    def _build_program_command(self, *, validate: bool) -> list[str]:
        executable = self.program_path_var.get().strip()
        if not executable:
            raise ValueError("choose an executable")

        command = []
        if self.run_program_sudo_var.get():
            command.extend(["sudo", "-A"])

        if self.pin_numa_var.get():
            node = self.numa_node_var.get().strip()
            if not node:
                raise ValueError("choose a NUMA node")
            if validate and shutil.which("numactl") is None:
                raise ValueError("numactl is required for NUMA pinning")
            command.extend(["numactl", f"--cpunodebind={node}", f"--membind={node}"])

        if self.pin_isolated_core_var.get():
            core = self.isolated_core_var.get().strip()
            if not core:
                raise ValueError("choose a core to pin")
            if validate and shutil.which("taskset") is None:
                raise ValueError("taskset is required for core pinning")
            command.extend(["taskset", "-c", core])

        if self.elevated_priority_var.get():
            if validate and shutil.which("nice") is None:
                raise ValueError("nice is required for elevated priority")
            command.extend(["nice", "-n", "-20"])

        resolved_executable = self._resolve_program_executable(executable, validate=validate)
        command.append(resolved_executable)
        command.extend(self._split_argument_field(self.additional_args_var.get(), "command-line arguments"))
        return command

    def _resolve_program_executable(self, executable: str, *, validate: bool) -> str:
        has_path = os.path.sep in executable or (os.path.altsep and os.path.altsep in executable)
        if not has_path:
            resolved = shutil.which(executable)
            if resolved:
                return resolved
            if validate:
                raise ValueError(f"executable not found on PATH: {executable}")
            return executable

        path = Path(executable).expanduser()
        if validate and not path.exists():
            raise ValueError(f"executable does not exist: {path}")
        if validate and path.exists() and not os.access(path, os.X_OK):
            raise ValueError(f"file is not executable: {path}")
        return str(path)

    def _program_working_dir(self, *, validate: bool) -> str | None:
        workdir = self.program_workdir_var.get().strip()
        if not workdir:
            return None
        path = Path(workdir).expanduser()
        if validate and not path.is_dir():
            raise ValueError(f"working directory does not exist: {path}")
        return str(path)

    def _split_argument_field(self, text: str, label: str) -> list[str]:
        try:
            return shlex.split(text)
        except ValueError as exc:
            raise ValueError(f"invalid {label}: {exc}") from exc

    def _format_action_description(self, action) -> str:
        core = self._current_core()
        return (
            action.description
            .replace("$core", str(core))
            .replace("{core}", str(core))
            .replace("{governor}", self.governor_var.get())
        )

    def refresh_status(self) -> None:
        self.status_items = collect_status()
        self._refresh_governor_options()
        for item_id in self.status_tree.get_children():
            self.status_tree.delete(item_id)
        for item in self.status_items:
            tags = ("group",) if not item.value and not item.explanation else ()
            self.status_tree.insert("", "end", text=item.setting, values=(item.value, item.explanation), tags=tags)
        self._update_status_summary()
        self._refresh_program_target_options()

    def _refresh_governor_options(self) -> None:
        self.available_governors = self._available_governors()
        if self.governor_var.get() not in self.available_governors:
            preferred = "performance" if "performance" in self.available_governors else self.available_governors[0]
            self.governor_var.set(preferred)
        if hasattr(self, "governor_combo"):
            self.governor_combo.configure(values=self.available_governors)

    def _update_status_summary(self) -> None:
        values = {item.setting: item.value for item in self.status_items}
        parts = [
            f"Turbo Boost: {values.get('Turbo Boost', 'unknown')}",
            f"Governor: {values.get('Scaling Governor', 'unknown')}",
            f"HT: {values.get('Hyper-Threading', 'unknown')}",
            f"Core isolation: {values.get('Isolated Cores', 'unknown')}",
        ]
        self.status_summary.configure(text=" | ".join(parts))

    def export_status(self) -> None:
        if not self.status_items:
            self.refresh_status()
        path = filedialog.asksaveasfilename(
            title="Export current configuration report",
            defaultextension=".json",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
            initialfile="BESTT-report.json",
        )
        if not path:
            return
        Path(path).write_text(export_report_json(), encoding="utf-8")
        self._append_log(f"Exported JSON report to {path}\n")

    def _browse_program(self) -> None:
        initial_dir = self.program_workdir_var.get().strip() or str(Path.home())
        path = self._ask_path_dialog("Choose executable", initial_dir, select_directory=False)
        if path:
            self.program_path_var.set(path)

    def _browse_workdir(self) -> None:
        initial_dir = self.program_workdir_var.get().strip() or str(Path.home())
        path = self._ask_path_dialog("Choose working directory", initial_dir, select_directory=True)
        if path:
            self.program_workdir_var.set(path)

    def _ask_path_dialog(self, title: str, initial_dir: str, *, select_directory: bool) -> str | None:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.resizable(True, True)
        width, height = self._browser_dimensions()
        dialog.geometry(f"{width}x{height}")
        dialog.minsize(min(width, 1400), min(height, 760))
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        current_dir = tk.StringVar()
        selected_text = tk.StringVar()
        item_paths = {}
        result = {"path": None}

        top = ttk.Frame(dialog, padding=(20, 18, 20, 8))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Location").grid(row=0, column=0, sticky="w", padx=(0, 10))
        location = ttk.Entry(top, textvariable=current_dir)
        location.grid(row=0, column=1, sticky="ew", padx=(0, 10))

        tree_frame = ttk.Frame(dialog, padding=(20, 0, 20, 0))
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        tree = ttk.Treeview(tree_frame, columns=("kind", "size"), show="tree headings", selectmode="browse")
        tree.heading("#0", text="Name")
        tree.heading("kind", text="Type")
        tree.heading("size", text="Size")
        tree.column("#0", width=840, minwidth=420, anchor="w", stretch=True)
        tree.column("kind", width=180, minwidth=120, anchor="w", stretch=False)
        tree.column("size", width=160, minwidth=100, anchor="e", stretch=False)
        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=yscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")

        bottom = ttk.Frame(dialog, padding=(20, 10, 20, 18))
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, textvariable=selected_text).grid(row=0, column=0, sticky="w", padx=(0, 16))

        def starting_directory(path_text: str) -> Path:
            path = Path(path_text).expanduser()
            if path.is_file():
                return path.parent
            if path.is_dir():
                return path
            return Path.home()

        def file_size(path: Path) -> str:
            try:
                size = path.stat().st_size
            except OSError:
                return ""
            if size < 1024:
                return f"{size} B"
            if size < 1024 * 1024:
                return f"{size / 1024:.1f} KB"
            return f"{size / (1024 * 1024):.1f} MB"

        def load_directory(path: Path) -> None:
            path = path.expanduser()
            if not path.is_dir():
                messagebox.showerror("Cannot Open Directory", f"Not a directory: {path}", parent=dialog)
                return

            try:
                children = sorted(path.iterdir(), key=lambda child: (not child.is_dir(), child.name.lower()))
            except OSError as exc:
                messagebox.showerror("Cannot Open Directory", str(exc), parent=dialog)
                return

            current_dir.set(str(path))
            selected_text.set(f"Selected: {path}" if select_directory else "")
            item_paths.clear()
            for item_id in tree.get_children():
                tree.delete(item_id)

            for child in children:
                try:
                    is_dir = child.is_dir()
                except OSError:
                    continue
                kind = "directory" if is_dir else "file"
                size = "" if is_dir else file_size(child)
                item_id = tree.insert("", "end", text=child.name, values=(kind, size))
                item_paths[item_id] = child

        def selected_path() -> Path | None:
            selection = tree.selection()
            if not selection:
                return Path(current_dir.get()) if select_directory else None
            return item_paths.get(selection[0])

        def refresh_selection(_event=None) -> None:
            path = selected_path()
            if path:
                selected_text.set(f"Selected: {path}")
            else:
                selected_text.set("")

        def go_to_location() -> None:
            load_directory(Path(current_dir.get()))

        def go_up() -> None:
            path = Path(current_dir.get())
            load_directory(path.parent)

        def go_home() -> None:
            load_directory(Path.home())

        def open_or_accept(_event=None) -> None:
            path = selected_path()
            if not path:
                return
            if path.is_dir():
                if select_directory:
                    result["path"] = str(path)
                    dialog.destroy()
                else:
                    load_directory(path)
                return
            if not select_directory:
                result["path"] = str(path)
                dialog.destroy()

        def accept() -> None:
            path = selected_path()
            if not path:
                messagebox.showerror("Nothing Selected", "Choose a file." if not select_directory else "Choose a directory.", parent=dialog)
                return
            if select_directory:
                result["path"] = str(path if path.is_dir() else path.parent)
                dialog.destroy()
                return
            if path.is_dir():
                load_directory(path)
                return
            result["path"] = str(path)
            dialog.destroy()

        def cancel() -> None:
            dialog.destroy()

        ttk.Button(top, text="Go", command=go_to_location).grid(row=0, column=2, sticky="ew", padx=(0, 8))
        ttk.Button(top, text="Up", command=go_up).grid(row=0, column=3, sticky="ew", padx=(0, 8))
        ttk.Button(top, text="Home", command=go_home).grid(row=0, column=4, sticky="ew")

        ttk.Button(bottom, text="Cancel", command=cancel).grid(row=0, column=1, sticky="e", padx=(0, 8))
        select_text = "Select Directory" if select_directory else "Select File"
        ttk.Button(bottom, text=select_text, command=accept).grid(row=0, column=2, sticky="e")

        tree.bind("<<TreeviewSelect>>", refresh_selection)
        tree.bind("<Double-1>", open_or_accept)
        location.bind("<Return>", lambda _event: go_to_location())
        dialog.protocol("WM_DELETE_WINDOW", cancel)

        load_directory(starting_directory(initial_dir))
        location.focus_set()
        dialog.grab_set()
        dialog.wait_window()
        return result["path"]

    def _browser_dimensions(self) -> tuple[int, int]:
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        width = min(int(screen_width * 0.96), 1700)
        height = min(int(screen_height * 0.94), 1000)
        return max(width, 1200), max(height, 760)

    def _refresh_program_target_options(self) -> None:
        if not hasattr(self, "numa_node_combo"):
            return

        self.available_numa_nodes = self._available_numa_nodes()
        if self.numa_node_var.get() not in self.available_numa_nodes:
            self.numa_node_var.set(self.available_numa_nodes[0])
        self.numa_node_combo.configure(values=self.available_numa_nodes)

        self.available_cores = self._available_core_ids()
        self.available_isolated_cores = self._isolated_core_ids()
        self.available_pin_cores = self._available_pin_core_ids()
        if self.available_isolated_cores:
            if self.isolated_core_var.get() not in self.available_pin_cores:
                self.isolated_core_var.set(self.available_isolated_cores[0])
        elif self.isolated_core_var.get() not in self.available_pin_cores:
            self.isolated_core_var.set("")
        self.isolated_core_combo.configure(values=self.available_pin_cores, state="readonly")
        self.pin_isolated_check.configure(state="normal")
        self.update_program_preview()

    def run_selected_action(self) -> None:
        if not script_is_present():
            messagebox.showerror("Missing Script", "The bundled setup script could not be found.")
            return

        action_key = self.selected_action_key.get()
        action = ACTION_SPECS[action_key]
        command = build_action_command(
            action_key,
            core=self._current_core(),
            governor=self.governor_var.get(),
            privilege="sudo",
        )
        preview = command_preview(command)

        message = f"Run this action?\n\nExact command:\n{preview}"
        if action.requires_reboot:
            message += "\n\nThis action changes boot-time settings and requires a reboot."
        if not self._ask_responsive_dialog("Confirm Action", action.label, message, "Run", "Cancel"):
            return

        self._append_log(f"$ {preview}\n")
        worker = threading.Thread(target=self._run_in_background, args=(command,), daemon=True)
        worker.start()
        self.after(150, self._poll_result_queue)

    def run_program(self) -> None:
        try:
            command = self._build_program_command(validate=True)
            workdir = self._program_working_dir(validate=True)
        except ValueError as exc:
            messagebox.showerror("Cannot Run Program", str(exc))
            return

        preview = command_preview(command)
        effective_workdir = workdir or os.getcwd()
        message = f"Run this program?\n\nWorking directory:\n{effective_workdir}\n\nExact command:\n{preview}"
        if not self._ask_responsive_dialog("Confirm Program", "Run program", message, "Run", "Cancel"):
            return

        self._append_log(f"$ {preview}\n")
        self._append_log(f"Working directory: {effective_workdir}\n")
        worker = threading.Thread(target=self._run_program_in_background, args=(command, workdir), daemon=True)
        worker.start()
        self.after(150, self._poll_result_queue)

    def _run_in_background(self, command) -> None:
        try:
            result = run_action_command(command)
            self.result_queue.put(("action_result", result))
        except Exception as exc:
            self.result_queue.put(("error", exc))

    def _run_program_in_background(self, command, workdir) -> None:
        try:
            result = run_action_command(command, timeout=None, cwd=workdir)
            self.result_queue.put(("program_result", result))
        except Exception as exc:
            self.result_queue.put(("error", exc))

    def _poll_result_queue(self) -> None:
        try:
            kind, payload = self.result_queue.get_nowait()
        except queue.Empty:
            self.after(150, self._poll_result_queue)
            return

        if kind == "error":
            self._append_log(f"ERROR: {payload}\n")
            messagebox.showerror("Action Failed", str(payload))
            return

        result = payload
        if result.stdout:
            self._append_log(result.stdout)
        if result.stderr:
            self._append_log(result.stderr)
        self._append_log(f"Exit code: {result.returncode}\n")

        if kind == "reboot_result":
            if result.ok:
                self._append_log("Reboot command accepted by systemctl.\n")
            else:
                messagebox.showerror("Reboot Failed", f"Reboot command exited with code {result.returncode}.")
            return

        if kind == "program_result":
            if result.ok:
                messagebox.showinfo("Program Complete", "Program completed.")
            else:
                messagebox.showerror("Program Failed", f"Program exited with code {result.returncode}.")
            return

        self.refresh_status()

        if result.ok:
            action = get_action(self.selected_action_key.get())
            if action.requires_reboot:
                self._offer_reboot(action.label)
            else:
                messagebox.showinfo("Action Complete", "Action completed.")
        else:
            messagebox.showerror("Action Failed", f"Action exited with code {result.returncode}.")

    def _offer_reboot(self, action_label: str) -> None:
        command = build_reboot_command(privilege="sudo")
        preview = command_preview(command)
        should_reboot = self._ask_responsive_dialog(
            "Reboot Required",
            "Reboot required",
            (
                f"{action_label} completed successfully. "
                "A reboot is required for boot-time settings to take effect.\n\n"
                f"Reboot now?\n\nExact command:\n{preview}"
            ),
            "Reboot now",
            "Later",
        )
        if not should_reboot:
            self._append_log("Reboot required, but user chose to reboot later.\n")
            return

        self._append_log(f"$ {preview}\n")
        worker = threading.Thread(target=self._run_reboot_in_background, args=(command,), daemon=True)
        worker.start()
        self.after(150, self._poll_result_queue)

    def _run_reboot_in_background(self, command) -> None:
        try:
            result = run_action_command(command, timeout=30)
            self.result_queue.put(("reboot_result", result))
        except Exception as exc:
            self.result_queue.put(("error", exc))

    def _ask_responsive_dialog(
        self,
        title: str,
        heading: str,
        message: str,
        confirm_text: str,
        cancel_text: str,
    ) -> bool:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.resizable(True, True)
        width, height = self._dialog_dimensions(message)
        dialog.geometry(f"{width}x{height}")
        dialog.minsize(min(width, 1500), min(height, 850))
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        heading_label = ttk.Label(dialog, text=heading, font=self.heading_font)
        heading_label.grid(row=0, column=0, sticky="ew", padx=32, pady=(28, 14))

        message_label = ttk.Label(dialog, text=message, justify="left", wraplength=max(900, width - 80))
        message_label.grid(row=1, column=0, sticky="nw", padx=32, pady=(0, 28))

        button_row = ttk.Frame(dialog)
        button_row.grid(row=2, column=0, sticky="e", padx=32, pady=(0, 28))

        result = {"confirmed": False}

        def finish(confirmed: bool) -> None:
            result["confirmed"] = confirmed
            dialog.destroy()

        ttk.Button(button_row, text=cancel_text, command=lambda: finish(False)).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_row, text=confirm_text, command=lambda: finish(True)).grid(row=0, column=1)

        dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))
        dialog.grab_set()
        dialog.wait_window()
        return result["confirmed"]

    def _dialog_dimensions(self, message: str) -> tuple:
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        max_width = int(screen_width * 0.96)
        max_height = int(screen_height * 0.94)
        min_width = min(1500, max_width)
        min_height = min(850, max_height)

        candidate_width = min(max_width, 1700)
        text_width = max(900, candidate_width - 80)
        wrapped_lines = self._wrapped_line_count(message, text_width)

        while wrapped_lines > 11 and candidate_width < max_width:
            candidate_width = min(max_width, candidate_width + 160)
            text_width = max(900, candidate_width - 80)
            wrapped_lines = self._wrapped_line_count(message, text_width)

        line_height = self.default_font.metrics("linespace")
        heading_height = self.heading_font.metrics("linespace")
        vertical_padding = 220
        height = heading_height + wrapped_lines * line_height + vertical_padding
        width = max(min_width, candidate_width)
        height = min(max(min_height, height), max_height)
        return width, height

    def _wrapped_line_count(self, message: str, width: int) -> int:
        line_count = 0
        space_width = self.default_font.measure(" ")
        for paragraph in message.splitlines() or [""]:
            words = paragraph.split(" ")
            if not words:
                line_count += 1
                continue

            current_width = 0
            paragraph_lines = 1
            for word in words:
                word_width = self.default_font.measure(word)
                additional = word_width if current_width == 0 else space_width + word_width
                if current_width and current_width + additional > width:
                    paragraph_lines += 1
                    current_width = word_width
                else:
                    current_width += additional
            line_count += paragraph_lines
        return max(1, line_count)

    def _set_text(self, widget: tk.Text, text: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", text)

    def _append_log(self, text: str) -> None:
        self.log.insert("end", text)
        if not text.endswith("\n"):
            self.log.insert("end", "\n")
        self.log.see("end")

    def _make_text_read_only(self, widget: tk.Text) -> None:
        def select_all(_event) -> str:
            widget.tag_add("sel", "1.0", "end-1c")
            widget.mark_set("insert", "1.0")
            widget.see("insert")
            return "break"

        def block_edit(event) -> str | None:
            if event.state & 0x4 and event.keysym.lower() == "c":
                return None
            navigation_keys = {
                "Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next",
            }
            if event.keysym in navigation_keys:
                return None
            return "break"

        widget.bind("<Control-a>", select_all)
        widget.bind("<Control-A>", select_all)
        widget.bind("<Key>", block_edit)
        widget.bind("<<Paste>>", lambda _event: "break")
        widget.bind("<<Cut>>", lambda _event: "break")
        widget.bind("<Button-2>", lambda _event: "break")


def main() -> None:
    app = BESTT()
    app.mainloop()
