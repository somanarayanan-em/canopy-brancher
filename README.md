# 🌳 Canopy

A small desktop app for creating the weekly cohort/classroom/group git branches — no browser, no typing git commands by hand.

## Requirements

- **Python 3** with `tkinter`
  - Windows/macOS: usually already included with Python.
  - Linux: if you get a `tkinter` import error, install it — e.g. `sudo apt install python3-tk` on Debian/Ubuntu.
- **git** installed and on your PATH, with push access to the repo already working the normal way (SSH key or saved credentials). Canopy doesn't ask for or store any credentials — it pushes as *you*.

## Running it

Open a terminal in the Canopy folder and run either of these:

```bash
python canopy.py
```

```bash
python3 canopy.py
```

A window opens. That's the whole setup.

## Optional: make your own click-and-run app

If you'd rather not open a terminal, Cursor, or VS Code each time, you can build an app and just double-click it. You only do this once, on the computer the app will run on.

**macOS** — this creates `dist/Canopy.app`

```bash
python3 -m pip install pyinstaller
python3 -m PyInstaller --windowed --name Canopy canopy.py
```

Double-click `dist/Canopy.app`.

If the build says `No module named '_tkinter'` and you installed Python with Homebrew, install the matching Tk package first (for example `brew install python-tk@3.14`) and run those commands again.

**Windows** — this creates `dist\Canopy.exe`

```bash
py -m pip install pyinstaller
py -m PyInstaller --windowed --onefile --name Canopy canopy.py
```

Double-click `dist\Canopy.exe`.

If the build fails while importing `tkinter`, reinstall Python from python.org and leave the tcl/tk option enabled.

Git still has to be installed on the computer where you open the app. Python is only needed to build it.

## What to fill in

| Field | Meaning |
|---|---|
| Repository folder | The local git clone to work in. This is what determines which repo/remote you're pushing to — Canopy doesn't ask for a repo URL directly. |
| Cohort name | Branch prefix, e.g. `em-crashcourse-20260925` (auto-filled with today's date). |
| Number of classrooms | How many classrooms to create. |
| Groups per classroom | How many group branches inside each classroom. |
| Base branch | Branch everything forks from (usually `main`). |
| Remote | Which configured remote in that repo to push to (usually `origin`). |

## Workflow

1. Pick the **Repository folder** (must already be a git clone).
2. Fill in the cohort details.
3. Click **Preview** — shows the full branch list and counts, touches nothing.
4. Check it looks right, then click **Create && Push**.
5. Confirm the dialog. Watch progress in the log pane.

Branches are created as:

```
<cohort>/classroom-01/groupa
<cohort>/classroom-01/groupb
...
<cohort>/classroom-02/groupa
...
<cohort>/instructor
```

## Re-running for the same cohort

If you need more branches later, open Canopy again, increase **Number of classrooms** or **Groups per classroom**, and click **Create && Push** again. Anything that already exists (locally or on the remote) is skipped — nothing gets recreated, overwritten, or deleted.

## Troubleshooting

- **"not a git repository"** — make sure the Repository folder is an existing git clone (has a `.git` folder), not just any folder.
- **"Base branch not found"** — check the branch name is spelled right, or run `git fetch` in that repo first so Canopy can see it.
- **Push fails for every branch** — usually a credentials/access issue with that remote. Try `git push origin main` manually in a terminal from that same folder to confirm your access works outside Canopy first.
- **Wrong repo got branches pushed** — double check which folder you picked; `git remote -v` in that folder shows the actual repo URL it's pointing at.