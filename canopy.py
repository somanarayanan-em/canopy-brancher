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
  - Fill in cohort name, number of classrooms, and groups per classroom.
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


def build_branch_list(cohort, num_classrooms, groups_per_classroom):
    branches = []
    for c in range(1, num_classrooms + 1):
        classroom = f"classroom-{c:02d}"
        for g in range(1, groups_per_classroom + 1):
            letter = num_to_letters(g)
            branches.append(f"{cohort}/{classroom}/group{letter}")
    branches.append(f"{cohort}/instructor")
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
        root.geometry("760x720")
        root.minsize(640, 580)

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
        self.cohort_var = tk.StringVar(value=self.default_cohort_name())
        ttk.Entry(main, textvariable=self.cohort_var).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0))
        row += 1

        # --- Branch counts ---
        ttk.Label(main, text="Number of classrooms").grid(row=row, column=0, sticky="w", pady=4)
        self.classrooms_var = tk.StringVar(value="2")
        ttk.Entry(main, textvariable=self.classrooms_var).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0))
        row += 1

        ttk.Label(main, text="Groups per classroom").grid(row=row, column=0, sticky="w", pady=4)
        self.groups_var = tk.StringVar(value="4")
        ttk.Entry(main, textvariable=self.groups_var).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0))
        row += 1

        # --- Base branch / remote ---
        ttk.Label(main, text="Base branch").grid(row=row, column=0, sticky="w", pady=4)
        self.base_branch_var = tk.StringVar(value="main")
        ttk.Entry(main, textvariable=self.base_branch_var).grid(row=row, column=1, sticky="ew", padx=(8, 8))
        ttk.Label(main, text="Remote").grid(row=row, column=2, sticky="w")
        row += 1
        self.remote_var = tk.StringVar(value="origin")
        ttk.Entry(main, textvariable=self.remote_var, width=8).grid(row=row - 1, column=2, sticky="e")

        # --- Tally ---
        row += 1
        self.tally_var = tk.StringVar(value="Fill in the fields above, then click Preview.")
        ttk.Label(main, textvariable=self.tally_var, foreground="#4a4a4a").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(10, 4)
        )

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

    @staticmethod
    def default_cohort_name():
        import datetime
        today = datetime.date.today()
        return f"em-crashcourse-{today.strftime('%Y%m%d')}"

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

        try:
            num_classrooms = to_int(self.classrooms_var.get(), "Number of classrooms", minimum=1)
            groups_per_classroom = to_int(self.groups_var.get(), "Groups per classroom", minimum=1)
        except ValueError as e:
            messagebox.showerror("Invalid input", str(e))
            return None

        base_branch = self.base_branch_var.get().strip() or "main"
        remote = self.remote_var.get().strip() or "origin"

        if not cohort:
            messagebox.showerror("Invalid input", "Cohort name is required.")
            return None
        if not repo:
            messagebox.showerror("Invalid input", "Repository folder is required.")
            return None

        return {
            "cohort": cohort,
            "repo": repo,
            "num_classrooms": num_classrooms,
            "groups_per_classroom": groups_per_classroom,
            "base_branch": base_branch,
            "remote": remote,
        }

    # -- actions ---------------------------------------------------------

    def on_preview(self):
        values = self.read_inputs()
        if values is None:
            return

        num_classrooms = values["num_classrooms"]
        groups_per_classroom = values["groups_per_classroom"]
        branches = build_branch_list(values["cohort"], num_classrooms, groups_per_classroom)

        self.tally_var.set(
            f"{num_classrooms} classroom(s) x {groups_per_classroom} group(s) "
            f"= {len(branches)} branch(es) total (incl. instructor)"
        )

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

        branches = build_branch_list(
            values["cohort"], values["num_classrooms"], values["groups_per_classroom"],
        )

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
        for branch in branches:
            if branch_exists_locally(branch, repo):
                self.log_threadsafe(f"SKIP (exists locally): {branch}")
                continue
            if branch_exists_on_remote(remote, branch, repo):
                self.log_threadsafe(f"SKIP (exists on {remote}): {branch}")
                continue

            create = run_git(["branch", branch, base_branch], cwd=repo)
            if create.returncode != 0:
                self.log_threadsafe(f"FAIL (create): {branch} — {create.stderr.strip()}")
                failed.append(branch)
                continue

            push = run_git(["push", remote, branch], cwd=repo)
            if push.returncode != 0:
                self.log_threadsafe(f"FAIL (push): {branch} — {push.stderr.strip()}")
                failed.append(branch)
            else:
                self.log_threadsafe(f"OK:   {branch}")

        if failed:
            self.log_threadsafe(f"\nDone with {len(failed)} failure(s).")
        else:
            self.log_threadsafe("\nDone. All branches created and pushed successfully.")

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
