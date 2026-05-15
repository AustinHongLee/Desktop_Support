from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from launcher.core.action_model import ActionDefinition
from launcher.core.context_model import LauncherContext
from launcher.core.context_service import ContextService
from launcher.core.job_model import JobEvent, JobResult
from launcher.core.paths import plugin_root
from launcher.core.registry import ActionRegistry
from launcher.core.runner import ActionRunner


class TkLauncher:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("工程工具列")
        self.root.attributes("-topmost", True)
        self.root.geometry("520x420+80+120")
        self.root.minsize(440, 320)

        self.registry = ActionRegistry(plugin_root())
        self.registry.load()
        self.runner = ActionRunner()
        self.context = ContextService().current_context()
        self.events: queue.Queue[JobEvent | JobResult] = queue.Queue()
        self.visible_actions: list[ActionDefinition] = []

        self.context_var = tk.StringVar()
        self.filter_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")

        self._build_ui()
        self._refresh_context_label()
        self._refresh_actions()
        self.root.after(100, self._pump_events)

    def run(self) -> int:
        self.root.mainloop()
        return 0

    def _build_ui(self) -> None:
        root = self.root
        root.configure(bg="#20242a")

        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill=tk.X)

        ttk.Button(toolbar, text="使用目前目錄", command=self.use_cwd).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="選取檔案", command=self.pick_files).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="執行", command=self.run_selected).pack(side=tk.RIGHT)

        ttk.Label(root, textvariable=self.context_var, padding=(8, 0)).pack(fill=tk.X)

        filter_frame = ttk.Frame(root, padding=(8, 6))
        filter_frame.pack(fill=tk.X)
        ttk.Label(filter_frame, text="篩選").pack(side=tk.LEFT)
        filter_entry = ttk.Entry(filter_frame, textvariable=self.filter_var)
        filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        filter_entry.bind("<KeyRelease>", lambda _event: self._refresh_actions())
        filter_entry.bind("<Return>", lambda _event: self.run_selected())

        body = ttk.Frame(root, padding=(8, 0, 8, 8))
        body.pack(fill=tk.BOTH, expand=True)

        self.action_list = tk.Listbox(body, height=8, activestyle="dotbox")
        self.action_list.pack(fill=tk.BOTH, expand=True)
        self.action_list.bind("<Double-Button-1>", lambda _event: self.run_selected())

        ttk.Label(body, text="工作紀錄").pack(anchor=tk.W, pady=(8, 2))
        self.log = tk.Text(body, height=8, wrap=tk.WORD)
        self.log.pack(fill=tk.BOTH, expand=True)
        self.log.configure(state=tk.DISABLED)

        ttk.Label(root, textvariable=self.status_var, padding=(8, 0, 8, 8)).pack(fill=tk.X)
        root.bind("<Control-k>", lambda _event: filter_entry.focus_set())

    def use_cwd(self) -> None:
        self.context = LauncherContext(folder=Path.cwd(), source="manual.cwd")
        self._refresh_context_label()
        self._refresh_actions()

    def pick_files(self) -> None:
        files = filedialog.askopenfilenames(title="Select files for launcher context")
        if not files:
            return
        self.context = LauncherContext.from_paths(list(files), source="picker")
        self._refresh_context_label()
        self._refresh_actions()

    def run_selected(self) -> None:
        selection = self.action_list.curselection()
        if not selection:
            messagebox.showinfo("工程工具列", "請先選擇一個指令。")
            return
        action = self.visible_actions[selection[0]]
        self.status_var.set(f"Running {action.title}")
        self._append_log(f"\n> {action.title}\n")

        thread = threading.Thread(target=self._run_action_worker, args=(action,), daemon=True)
        thread.start()

    def _run_action_worker(self, action: ActionDefinition) -> None:
        result = self.runner.run(action, self.context, on_event=self.events.put)
        self.events.put(result)

    def _pump_events(self) -> None:
        while True:
            try:
                item = self.events.get_nowait()
            except queue.Empty:
                break

            if isinstance(item, JobResult):
                self.status_var.set("OK" if item.ok else f"Failed: {item.return_code}")
                self._append_log(f"[RESULT] {'OK' if item.ok else 'FAILED'}\n")
            else:
                self._append_log(f"[{item.type.upper()}] {item.message}\n")
        self.root.after(100, self._pump_events)

    def _refresh_actions(self) -> None:
        query = self.filter_var.get().strip().lower()
        actions = self.registry.matching_actions(self.context)
        if query:
            actions = [action for action in actions if _matches(action, query)]
        self.visible_actions = actions
        self.action_list.delete(0, tk.END)
        for action in actions:
            self.action_list.insert(tk.END, f"{action.title}    [{action.category}]")
        if actions:
            self.action_list.selection_set(0)

    def _refresh_context_label(self) -> None:
        if self.context.file_count:
            label = f"{self.context.source}: {self.context.file_count} file(s): {self.context.files[0]}"
        elif self.context.folder:
            label = f"{self.context.source}: {self.context.folder}"
        else:
            label = "No context"
        self.context_var.set(label)

    def _append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)


def _matches(action: ActionDefinition, query: str) -> bool:
    haystack = " ".join([action.id, action.title, action.category, action.description]).lower()
    return all(part in haystack for part in query.split())


def main() -> int:
    return TkLauncher().run()


if __name__ == "__main__":
    raise SystemExit(main())
