#!/usr/bin/env python3
"""
canopy.py

Canopy — a small desktop app (no browser, no terminal typing) for creating
the weekly cohort/classroom/group git branches.

Run it with:
    python3 canopy.py

Requires:
  - Python 3 with tkinter (bundled by default on Windows and macOS Python
    installers; on Linux you may need to install it separately, e.g.
    `sudo apt install python3-tk` on Debian/Ubuntu).
  - git installed and on your PATH, with push access already working the
    normal way (SSH key or stored HTTPS credentials) for your remote.

What it does:
  - Pick the local repo folder.
  - Fill in cohort name, how many classrooms, and how many groups
    each classroom needs.
  - Click "Preview" to see the branch list and counts without touching git.
  - Click "Create & Push" to actually create the branches from your base
    branch and push them to your remote.

It's safe to re-run for the same cohort later with higher classroom or
group counts: any branch that already exists locally or on the remote is
skipped, never recreated or overwritten.
"""

import os
import string
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext


# ---------------------------------------------------------------------------
# Pure logic (no GUI, no git) — kept separate so it's easy to reason about
# ---------------------------------------------------------------------------

def num_to_letters(n: int) -> str:
    """1 -> a, 2 -> b, ..., 26 -> z, 27 -> aa, 28 -> ab, ..."""
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = string.ascii_lowercase[rem] + letters
    return letters


MAX_CLASSROOMS = 12
DEFAULT_GROUPS = 4
MAX_GROUPS = 99
PUSH_BATCH_SIZE = 100


def build_branch_list(cohort, groups_per_classroom):
    """groups_per_classroom is one group-count per classroom, in order."""
    num_classrooms = len(groups_per_classroom)
    branches = []
    for c, group_count in enumerate(groups_per_classroom, start=1):
        # A single classroom for the day doesn't need a classroom segment.
        if num_classrooms == 1:
            prefix = cohort
        else:
            prefix = f"{cohort}/classroom-{c:02d}"
        for g in range(1, group_count + 1):
            letter = num_to_letters(g)
            branches.append(f"{prefix}/group{letter}")
        branches.append(f"{prefix}/instructor")
    return branches


# ---------------------------------------------------------------------------
# Git helpers (all take an explicit cwd = the chosen repo folder)
# ---------------------------------------------------------------------------

def run_git(args, cwd, check=False):
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=check,
    )


def is_git_repo(path):
    result = run_git(["rev-parse", "--is-inside-work-tree"], cwd=path)
    return result.returncode == 0


def branch_exists_locally(branch, cwd):
    result = run_git(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=cwd)
    return result.returncode == 0


def branch_exists_on_remote(remote, branch, cwd):
    result = run_git(["show-ref", "--verify", "--quiet", f"refs/remotes/{remote}/{branch}"], cwd=cwd)
    return result.returncode == 0


def base_branch_exists(base_branch, remote, cwd):
    local = run_git(["show-ref", "--verify", "--quiet", f"refs/heads/{base_branch}"], cwd=cwd)
    remote_ref = run_git(["show-ref", "--verify", "--quiet", f"refs/remotes/{remote}/{base_branch}"], cwd=cwd)
    return local.returncode == 0 or remote_ref.returncode == 0


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class CohortBranchApp:
    def __init__(self, root):
        self.root = root
        root.title("Canopy — Cohort Branch Setup")
        root.geometry("760x780")
        root.minsize(680, 640)

        self.running = False

        # --- Header / banner ---
        header = tk.Frame(root, bg="#1F3D2E")
        header.pack(fill="x")
        tk.Label(
            header, text="🌳 Canopy", bg="#1F3D2E", fg="#F1EDE1",
            font=("Georgia", 20, "bold"), anchor="w",
        ).pack(side="left", padx=16, pady=(12, 2), anchor="s")
        tk.Label(
            header, text="  cohort branch setup", bg="#1F3D2E", fg="#A9BFB2",
            font=("Helvetica", 11), anchor="w",
        ).pack(side="left", pady=(12, 2), anchor="s")

        main = ttk.Frame(root, padding=16)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, minsize=210)
        main.columnconfigure(1, weight=1)

        row = 0

        # --- Repo path ---
        ttk.Label(main, text="Repository folder").grid(row=row, column=0, sticky="w", pady=4)
        self.repo_var = tk.StringVar(value=os.getcwd())
        repo_entry = ttk.Entry(main, textvariable=self.repo_var)
        repo_entry.grid(row=row, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(main, text="Browse…", command=self.browse_repo).grid(row=row, column=2)
        row += 1

        # --- Cohort name ---
        ttk.Label(main, text="Cohort name").grid(row=row, column=0, sticky="w", pady=4)
        self.cohort_var = tk.StringVar(value="")
        ttk.Entry(main, textvariable=self.cohort_var).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0))
        row += 1
        ttk.Label(
            main,
            text="This will be the prefix of your branch name.\nExamples: em-crashcourse-yyyymmdd or aisdlc-bc-yyyymmdd.",
            foreground="#6b6b6b",
            font=("Helvetica", 11),
            justify="left",
        ).grid(row=row, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(0, 6))
        row += 1

        # --- How many classrooms, then one group count per classroom ---
        ttk.Label(main, text="How many classrooms?").grid(row=row, column=0, sticky="w", pady=4)
        self.classrooms_var = tk.StringVar(value="1")
        self.classrooms_var.trace_add(
            "write", lambda *_args: self._restrict_number(self.classrooms_var, MAX_CLASSROOMS)
        )
        self._classroom_count_vcmd = (
            self.root.register(lambda proposed: self._allow_count(proposed, MAX_CLASSROOMS)),
            "%P",
        )
        ttk.Spinbox(
            main,
            from_=1,
            to=MAX_CLASSROOMS,
            textvariable=self.classrooms_var,
            width=6,
            validate="key",
            validatecommand=self._classroom_count_vcmd,
        ).grid(row=row, column=1, sticky="w", padx=(8, 0))
        row += 1
        self.classroom_hint = ttk.Label(
            main,
            text="",
            foreground="#6b6b6b",
            font=("Helvetica", 11),
            justify="left",
        )
        self.classroom_hint.grid(row=row, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(0, 4))
        self.classroom_hint.grid_remove()
        row += 1

        self.groups_frame = ttk.Frame(main)
        self.groups_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(2, 6))
        self.groups_frame.columnconfigure(0, minsize=210)
        self.group_vars = []
        self.group_row_widgets = []
        self._classroom_sync_job = None
        self._group_count_vcmd = (
            self.root.register(lambda proposed: self._allow_count(proposed, MAX_GROUPS)),
            "%P",
        )
        self.sync_classroom_rows()
        self.classrooms_var.trace_add("write", lambda *_: self.schedule_classroom_sync())
        row += 1

        # --- Base branch ---
        ttk.Label(main, text="Base branch").grid(row=row, column=0, sticky="w", pady=4)
        self.base_branch_var = tk.StringVar(value="main")
        ttk.Entry(main, textvariable=self.base_branch_var).grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0)
        )
        row += 1

        # --- Remote: off unless the remote is not named origin ---
        self.custom_remote_var = tk.BooleanVar(value=False)
        self.remote_var = tk.StringVar(value="")
        remote_switch = ttk.Frame(main)
        remote_switch.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(10, 2))
        self.switch = tk.Canvas(
            remote_switch, width=44, height=24, highlightthickness=0, bd=0, cursor="hand2",
        )
        self.switch.pack(side="left", padx=(0, 10), pady=2)
        self.switch.bind("<Button-1>", lambda _event: self.toggle_remote())
        ttk.Label(
            remote_switch,
            text="Leave this off unless the remote is not called origin.",
            foreground="#6b6b6b",
            font=("Helvetica", 11),
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        self.draw_switch()
        row += 1

        self.remote_entry_frame = ttk.Frame(main)
        self.remote_entry_frame.columnconfigure(1, weight=1)
        self.remote_entry_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=4)
        ttk.Label(self.remote_entry_frame, text="Remote name").grid(row=0, column=0, sticky="w")
        self.remote_entry = ttk.Entry(self.remote_entry_frame, textvariable=self.remote_var)
        self.remote_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(8, 0))
        self.remote_entry_frame.grid_remove()
        row += 1

        # --- Buttons ---
        row += 1
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=row, column=0, columnspan=3, sticky="w", pady=(4, 10))
        ttk.Button(btn_frame, text="Preview", command=self.on_preview).pack(side="left", padx=(0, 8))
        self.create_btn = ttk.Button(btn_frame, text="Create && Push", command=self.on_create_and_push)
        self.create_btn.pack(side="left")

        # --- Log output ---
        row += 1
        ttk.Label(main, text="Log").grid(row=row, column=0, sticky="w")
        row += 1
        main.rowconfigure(row, weight=1)
        self.log_widget = scrolledtext.ScrolledText(main, height=16, wrap="word", state="disabled")
        self.log_widget.grid(row=row, column=0, columnspan=3, sticky="nsew", pady=(4, 0))

    # -- helpers -------------------------------------------------------

    def browse_repo(self):
        path = filedialog.askdirectory(initialdir=self.repo_var.get() or os.getcwd())
        if path:
            self.repo_var.set(path)

    def log(self, text):
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", text + "\n")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def log_threadsafe(self, text):
        self.root.after(0, lambda: self.log(text))

    def clear_log(self):
        self.log_widget.configure(state="normal")
        self.log_widget.delete("1.0", "end")
        self.log_widget.configure(state="disabled")

    def schedule_classroom_sync(self):
        if self._classroom_sync_job is not None:
            self.root.after_cancel(self._classroom_sync_job)
        self._classroom_sync_job = self.root.after(300, self.sync_classroom_rows)

    def sync_classroom_rows(self):
        """Show one group-count row per classroom, keeping counts already typed."""
        self._classroom_sync_job = None
        raw = self.classrooms_var.get().strip()
        if not raw.isdigit():
            return
        count = int(raw)
        if count < 1 or count > MAX_CLASSROOMS:
            return

        while len(self.group_vars) < count:
            var = tk.StringVar(value=str(DEFAULT_GROUPS))
            var.trace_add("write", lambda *_args, v=var: self._restrict_number(v, MAX_GROUPS))
            self.group_vars.append(var)

        if count == 1:
            self.classroom_hint.grid_remove()
        else:
            if count == 2:
                names = "classroom-01 and classroom-02"
            else:
                names = f"classroom-01 through classroom-{count:02d}"
            self.classroom_hint.configure(
                text=f"{names} will be appended to the branch name."
            )
            self.classroom_hint.grid()

        for widget in self.group_row_widgets:
            widget.destroy()
        self.group_row_widgets = []
        for i in range(count):
            if count == 1:
                label_text = "How many groups?"
            else:
                label_text = f"Groups in classroom {i + 1}"
            label = ttk.Label(self.groups_frame, text=label_text)
            entry = ttk.Spinbox(
                self.groups_frame,
                from_=1,
                to=MAX_GROUPS,
                textvariable=self.group_vars[i],
                width=6,
                validate="key",
                validatecommand=self._group_count_vcmd,
            )
            label.grid(row=i, column=0, sticky="w", pady=4)
            entry.grid(row=i, column=1, sticky="w", padx=(8, 0), pady=4)
            self.group_row_widgets.extend([label, entry])

    def _allow_count(self, proposed, maximum):
        if proposed == "":
            return True
        if not proposed.isdigit():
            return False
        value = int(proposed)
        return 1 <= value <= maximum

    def _restrict_number(self, var, maximum):
        """Drop letters as they are typed, even if the spinner ignores key validation."""
        raw = var.get()
        digits = "".join(ch for ch in raw if ch.isdigit())
        if not digits:
            cleaned = ""
        else:
            value = min(int(digits), maximum)
            cleaned = "" if value < 1 else str(value)
        if cleaned != raw:
            var.set(cleaned)

    def draw_switch(self):
        canvas = self.switch
        canvas.delete("all")
        try:
            bg = ttk.Style().lookup("TFrame", "background") or self.root.cget("bg")
            if bg:
                canvas.configure(bg=bg)
        except tk.TclError:
            pass
        on = self.custom_remote_var.get()
        track = "#1F3D2E" if on else "#C8C8C8"
        width, height = 44, 24
        radius = height // 2
        canvas.create_oval(1, 1, height, height - 1, fill=track, outline=track)
        canvas.create_oval(width - height, 1, width - 1, height - 1, fill=track, outline=track)
        canvas.create_rectangle(radius, 1, width - radius, height - 1, fill=track, outline=track)
        knob = width - height + 3 if on else 3
        canvas.create_oval(knob, 3, knob + height - 6, height - 3, fill="#FFFFFF", outline="#FFFFFF")

    def toggle_remote(self):
        self.custom_remote_var.set(not self.custom_remote_var.get())
        self.draw_switch()
        if self.custom_remote_var.get():
            self.remote_entry_frame.grid()
            self.remote_entry.focus_set()
        else:
            self.remote_entry_frame.grid_remove()

    def read_inputs(self):
        """Validate and return the current form values, or None (and show
        an error dialog) if something is invalid."""
        cohort = self.cohort_var.get().strip()
        repo = self.repo_var.get().strip()

        def to_int(var_str, label, minimum=0):
            try:
                value = int(var_str.strip())
            except ValueError:
                raise ValueError(f"{label} must be a whole number.")
            if value < minimum:
                raise ValueError(f"{label} must be at least {minimum}.")
            return value

        if self._classroom_sync_job is not None:
            self.root.after_cancel(self._classroom_sync_job)
            self._classroom_sync_job = None

        try:
            num_classrooms = to_int(self.classrooms_var.get(), "How many classrooms", minimum=1)
            if num_classrooms > MAX_CLASSROOMS:
                raise ValueError(f"How many classrooms must be {MAX_CLASSROOMS} or fewer.")
            self.sync_classroom_rows()
            groups = [
                to_int(self.group_vars[i].get(), f"Classroom {i + 1} groups", minimum=1)
                for i in range(num_classrooms)
            ]
        except ValueError as e:
            messagebox.showerror("Invalid input", str(e))
            return None

        base_branch = self.base_branch_var.get().strip() or "main"
        if self.custom_remote_var.get():
            remote = self.remote_var.get().strip()
            if not remote:
                messagebox.showerror(
                    "Invalid input",
                    "Enter the remote name, or turn the switch off to use origin.",
                )
                return None
        else:
            remote = "origin"

        if not cohort:
            messagebox.showerror("Invalid input", "Cohort name is required.")
            return None
        if not repo:
            messagebox.showerror("Invalid input", "Repository folder is required.")
            return None

        return {
            "cohort": cohort,
            "repo": repo,
            "groups": groups,
            "base_branch": base_branch,
            "remote": remote,
        }

    # -- actions ---------------------------------------------------------

    def on_preview(self):
        values = self.read_inputs()
        if values is None:
            return

        branches = build_branch_list(values["cohort"], values["groups"])

        self.clear_log()
        self.log(f"Preview for '{values['cohort']}' — {len(branches)} branches:")
        for b in branches:
            self.log(f"  {b}")
        self.log("\n(This was a preview only — nothing was created or pushed.)")

    def on_create_and_push(self):
        if self.running:
            return

        values = self.read_inputs()
        if values is None:
            return

        repo = values["repo"]
        if not os.path.isdir(repo):
            messagebox.showerror("Invalid repository", f"'{repo}' is not a folder.")
            return
        if not is_git_repo(repo):
            messagebox.showerror("Invalid repository", f"'{repo}' is not a git repository.")
            return
        if not base_branch_exists(values["base_branch"], values["remote"], repo):
            messagebox.showerror(
                "Base branch not found",
                f"Branch '{values['base_branch']}' was not found locally or on "
                f"'{values['remote']}'. Try fetching first, or check the name.",
            )
            return

        branches = build_branch_list(values["cohort"], values["groups"])

        confirm = messagebox.askyesno(
            "Confirm",
            f"Create and push {len(branches)} branch(es) for '{values['cohort']}' "
            f"from '{values['base_branch']}' to '{values['remote']}'?\n\n"
            f"Existing branches (local or on the remote) will be skipped, not overwritten.",
        )
        if not confirm:
            return

        self.clear_log()
        self.running = True
        self.create_btn.state(["disabled"])

        thread = threading.Thread(
            target=self.worker_create_and_push,
            args=(values, branches),
            daemon=True,
        )
        thread.start()

    def worker_create_and_push(self, values, branches):
        repo = values["repo"]
        remote = values["remote"]
        base_branch = values["base_branch"]

        self.log_threadsafe(f"Fetching '{remote}'...")
        run_git(["fetch", remote], cwd=repo)

        failed = []
        to_push = []
        for branch in branches:
            if branch_exists_locally(branch, repo):
                self.log_threadsafe(f"SKIP (exists locally): {branch}")
                continue
            if branch_exists_on_remote(remote, branch, repo):
                self.log_threadsafe(f"SKIP (exists on {remote}): {branch}")
                continue

            create = run_git(["branch", branch, base_branch], cwd=repo)
            if create.returncode != 0:
                detail = create.stderr.strip() or create.stdout.strip()
                self.log_threadsafe(f"FAIL (create): {branch}")
                if detail:
                    self.log_threadsafe(f"  {detail}")
                failed.append(branch)
                continue
            to_push.append(branch)

        total = len(to_push)
        for start in range(0, total, PUSH_BATCH_SIZE):
            batch = to_push[start:start + PUSH_BATCH_SIZE]
            first = start + 1
            last = start + len(batch)
            self.log_threadsafe("")
            self.log_threadsafe(f"Pushing branches {first}–{last} of {total}:")
            push = run_git(["push", remote, *batch], cwd=repo)
            if push.returncode != 0:
                self.log_threadsafe(f"FAIL: push of branches {first}–{last}")
                detail = (push.stderr or push.stdout).strip()
                for line in detail.splitlines():
                    self.log_threadsafe(f"  {line}")
                self.log_threadsafe("  Branches in this push:")
                for branch in batch:
                    self.log_threadsafe(f"  {branch}")
                    failed.append(branch)
            else:
                for branch in batch:
                    self.log_threadsafe(f"OK:   {branch}")

        self.log_threadsafe("")
        if failed:
            self.log_threadsafe(f"Done with {len(failed)} failure(s).")
        elif not to_push:
            self.log_threadsafe("Done. Nothing new to create or push.")
        else:
            self.log_threadsafe("Done. All new branches created and pushed.")

        self.root.after(0, self.on_worker_finished)

    def on_worker_finished(self):
        self.running = False
        self.create_btn.state(["!disabled"])


def main():
    root = tk.Tk()
    app = CohortBranchApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
