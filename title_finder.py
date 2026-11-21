#!/usr/bin/env python3
"""
Title Finder - search and export titles from your Plex or Jellyfin libraries.

- Pick a server (Plex or Jellyfin) and a library, then click Load.
- Find titles that start with / contain / end with some text, or use a regex.
- "Group by prefix" lists every first-N-characters prefix (e.g. ABC, XYZ) with
  a count; click one to see its titles.
- Export the results to CSV (opens in Excel) or copy them to the clipboard.

Uses the same settings as Jellyport (config.json / %APPDATA%\\Jellyport).
Read-only: it never changes anything on your servers.

Run:  python title_finder.py
"""

import csv
import os
import queue
import re
import sys
import threading
import tkinter as tk
from collections import Counter
from tkinter import filedialog, messagebox, ttk

import jellyport as jp
import jellyport_cli as core

ALL = "All libraries"
CODE = "Code (ABC-123)"
MODES = ["Starts with", CODE, "Contains", "Ends with", "Regex"]
ARTICLES = re.compile(r"^(the|a|an)\s+", re.I)


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def plex_libraries(plex):
    """[(name, loader)] for every Plex movie / TV library."""
    out = []
    for s in plex.sections():
        kind = {"movie": 1, "show": 2}.get(s.get("type"))
        if kind:
            out.append((s["title"], lambda k=s["key"], t=kind, n=s["title"]:
                        [plex_record(x, n) for x in plex.section_items(k, t)]))
    return out


def plex_record(x, lib):
    f = ""
    for m in x.get("Media", []) or []:
        for p in m.get("Part", []) or []:
            f = f or p.get("file", "")
    return {"title": x.get("title", ""), "sort": x.get("titleSort") or x.get("title", ""),
            "year": x.get("year", ""), "type": x.get("type", ""), "library": lib, "file": f}


def jf_libraries(jf):
    out = []
    for v in jf.views():
        if v.get("CollectionType") in ("playlists", "boxsets", "music", "books", "livetv"):
            continue
        out.append((v["Name"], lambda i=v["Id"], n=v["Name"]:
                    [jf_record(x, n) for x in jf.view_items(i)]))
    return out


def jf_record(x, lib):
    return {"title": x.get("Name", ""), "sort": x.get("SortName") or x.get("Name", ""),
            "year": x.get("ProductionYear", ""), "type": (x.get("Type") or "").lower(),
            "library": lib, "file": x.get("Path", "")}


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
class TitleFinder:
    def __init__(self, root, cfg=None):
        self.root = root
        self.cfg = cfg if cfg is not None else jp.load_config()
        self.q = queue.Queue()
        self.busy = 0
        self.libs = {}       # server -> [(name, loader)]
        self.items = []      # loaded records
        self.shown = []      # filtered records
        self._after = None
        self._build()
        root.after(100, self._poll)
        if jp.config_complete(self.cfg):
            root.after(200, self.connect)
        else:
            root.after(200, self.open_settings)

    # ------------------------------------------------------------------ UI --
    def _build(self):
        r = self.root
        r.title(f"Title Finder — {jp.APP_NAME} {jp.__version__}")
        r.geometry("1150x720")
        r.minsize(850, 500)

        top = ttk.Frame(r, padding=(10, 8))
        top.pack(fill="x")
        ttk.Button(top, text="⚙ Settings…", command=self.open_settings).pack(side="left")
        ttk.Label(top, text="Server:").pack(side="left", padx=(14, 4))
        self.server = tk.StringVar(value="Plex")
        sv = ttk.Combobox(top, textvariable=self.server, values=["Plex", "Jellyfin"],
                          width=9, state="readonly")
        sv.pack(side="left")
        sv.bind("<<ComboboxSelected>>", lambda e: self._fill_libraries())
        ttk.Label(top, text="Library:").pack(side="left", padx=(12, 4))
        self.library = tk.StringVar()
        self.lib_box = ttk.Combobox(top, textvariable=self.library, width=28, state="readonly")
        self.lib_box.pack(side="left")
        self.lib_box.bind("<<ComboboxSelected>>", lambda e: self.load())
        ttk.Button(top, text="⟳ Reload", command=self.load).pack(side="left", padx=8)
        self.prog = ttk.Progressbar(top, mode="determinate", length=120)
        self.prog.pack(side="right")
        self.status = tk.StringVar(value="Not connected")
        ttk.Label(top, textvariable=self.status).pack(side="right", padx=8)

        find = ttk.LabelFrame(r, text=" Find ", padding=8)
        find.pack(fill="x", padx=10)
        self.mode = tk.StringVar(value="Starts with")
        ttk.Combobox(find, textvariable=self.mode, values=MODES, width=11,
                     state="readonly").pack(side="left")
        self.text = tk.StringVar()
        ent = ttk.Entry(find, textvariable=self.text, width=30)
        ent.pack(side="left", padx=6)
        ttk.Label(find, text="in").pack(side="left")
        self.field = tk.StringVar(value="Title")
        ttk.Combobox(find, textvariable=self.field, values=["Title", "File name"], width=9,
                     state="readonly").pack(side="left", padx=6)
        self.case = tk.BooleanVar(value=False)
        ttk.Checkbutton(find, text="Match case", variable=self.case).pack(side="left", padx=6)
        self.skip_articles = tk.BooleanVar(value=False)
        ttk.Checkbutton(find, text='Ignore "The / A / An"',
                        variable=self.skip_articles).pack(side="left", padx=6)
        for v in (self.mode, self.text, self.field, self.case, self.skip_articles):
            v.trace_add("write", lambda *a: self._schedule_filter())

        body = ttk.PanedWindow(r, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=8)

        # prefix groups
        gf = ttk.LabelFrame(body, text=" Group by prefix ", padding=6)
        body.add(gf, weight=0)
        row = ttk.Frame(gf)
        row.pack(fill="x")
        ttk.Label(row, text="First").pack(side="left")
        self.plen = tk.IntVar(value=3)
        ttk.Spinbox(row, from_=1, to=10, width=3, textvariable=self.plen).pack(side="left", padx=4)
        ttk.Label(row, text="chars").pack(side="left")
        self.letters_only = tk.BooleanVar(value=True)
        ttk.Checkbutton(gf, text="Letters only (skip 123, -, spaces)",
                        variable=self.letters_only).pack(anchor="w", pady=(4, 0))
        ttk.Button(gf, text="Group", command=self.group).pack(fill="x", pady=4)
        self.groups = ttk.Treeview(gf, columns=("prefix", "n"), show="headings", height=12,
                                   selectmode="browse")
        self.groups.heading("prefix", text="Prefix")
        self.groups.heading("n", text="Titles")
        self.groups.column("prefix", width=90)
        self.groups.column("n", width=60, anchor="e")
        self.groups.pack(fill="both", expand=True)
        self.groups.bind("<<TreeviewSelect>>", self._on_group)

        # results
        rf = ttk.Frame(body)
        body.add(rf, weight=1)
        bar = ttk.Frame(rf)
        bar.pack(side="bottom", fill="x", pady=(6, 0))
        self.count = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.count).pack(side="left")
        ttk.Button(bar, text="Export CSV…", command=self.export).pack(side="right")
        ttk.Button(bar, text="Copy titles", command=self.copy).pack(side="right", padx=6)
        cols = ("title", "year", "type", "library", "file")
        t = ttk.Treeview(rf, columns=cols, show="headings", selectmode="extended")
        for c, w, txt in (("title", 330, "Title"), ("year", 55, "Year"), ("type", 70, "Type"),
                          ("library", 140, "Library"), ("file", 360, "File")):
            t.heading(c, text=txt, command=lambda c=c: self.sort_by(c))
            t.column(c, width=w, stretch=c in ("title", "file"),
                     anchor="center" if c == "year" else "w")
        vs = ttk.Scrollbar(rf, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=vs.set)
        vs.pack(side="right", fill="y")
        t.pack(fill="both", expand=True)
        self.tree = t
        self._sort = ("title", False)

    # ---------------------------------------------------------- background --
    def bg(self, label, fn, done):
        self.busy += 1
        self.status.set(label)
        self.prog.configure(mode="indeterminate")
        self.prog.start(12)

        def run():
            try:
                self.q.put((done, fn(), None))
            except Exception as e:  # noqa: BLE001 - shown to the user
                self.q.put((done, None, e))
        threading.Thread(target=run, daemon=True).start()

    def _poll(self):
        if not self.root.winfo_exists():   # window closed (opened from Jellyport)
            return
        try:
            while True:
                done, res, err = self.q.get_nowait()
                self.busy = max(0, self.busy - 1)
                if not self.busy:
                    self.prog.stop()
                    self.prog.configure(mode="determinate", value=0)
                if err:
                    self.status.set("Error")
                    messagebox.showerror("Title Finder", str(err), parent=self.root)
                else:
                    done(res)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    # ------------------------------------------------------------- connect --
    def open_settings(self):
        jp.SettingsDialog(self.root, self.cfg, self.connect)

    def connect(self):
        cfg = self.cfg

        def work():
            libs = {}
            errors = []
            try:
                libs["Plex"] = plex_libraries(core.Plex(cfg["plex"]))
            except Exception as e:  # noqa: BLE001
                errors.append(f"Plex: {e}")
            try:
                libs["Jellyfin"] = jf_libraries(core.Jellyfin(cfg["jellyfin"]))
            except Exception as e:  # noqa: BLE001
                errors.append(f"Jellyfin: {e}")
            return libs, errors

        def done(res):
            self.libs, errors = res
            parts = [f"{k}: {len(v)} {'library' if len(v) == 1 else 'libraries'}"
                     for k, v in self.libs.items()]
            self.status.set("  ·  ".join(parts) or "Not connected")
            if errors:
                messagebox.showwarning("Title Finder", "\n".join(errors), parent=self.root)
            if self.server.get() not in self.libs and self.libs:
                self.server.set(next(iter(self.libs)))
            self._fill_libraries()

        self.bg("Connecting…", work, done)

    def _fill_libraries(self):
        names = [n for n, _ in self.libs.get(self.server.get(), [])]
        self.lib_box["values"] = [ALL] + names if names else []
        self.library.set(ALL if names else "")
        if names:
            self.load()            # load straight away - no extra click needed
        else:
            self.items, self.shown = [], []
            self._render()

    # ---------------------------------------------------------------- load --
    def load(self):
        libs = self.libs.get(self.server.get(), [])
        if not libs:
            messagebox.showinfo("Title Finder", f"Not connected to {self.server.get()}.", parent=self.root)
            return
        pick = self.library.get()
        chosen = libs if pick == ALL else [l for l in libs if l[0] == pick]
        server = self.server.get()
        self._load_id = getattr(self, "_load_id", 0) + 1
        token = self._load_id
        self.items, self.shown = [], []
        self.tree.delete(*self.tree.get_children())
        self.groups.delete(*self.groups.get_children())
        self.count.set(f"Loading titles from {server}…")

        def work():
            out = []
            for _, loader in chosen:
                out.extend(loader())
            return out

        def done(items):
            if token != self._load_id:     # a newer load was started meanwhile
                return
            self.items = items
            self.status.set(f"{server} · {pick}: {len(items):,} titles loaded")
            self.group()
            self.apply_filter()

        self.bg(f"Loading {pick} from {server}…", work, done)

    # -------------------------------------------------------------- filter --
    def _subject(self, rec):
        if self.field.get() == "File name":
            return core.basename(rec["file"]) if rec["file"] else ""
        s = rec["title"]
        if self.skip_articles.get():
            s = ARTICLES.sub("", s)
        return s

    def _schedule_filter(self):
        if self._after:
            self.root.after_cancel(self._after)
        self._after = self.root.after(250, self.apply_filter)

    def apply_filter(self):
        self._after = None
        text, mode, case = self.text.get(), self.mode.get(), self.case.get()
        if mode in ("Regex", CODE):
            pattern = text if mode == "Regex" else rf"^{re.escape(text)}[\s\-_.]*\d"
            try:
                rx = re.compile(pattern, 0 if case else re.I)
            except re.error as e:
                self.count.set(f"Regex error: {e}")
                return
            test = lambda s: bool(rx.search(s))
        else:
            needle = text if case else text.lower()
            fn = {"Starts with": str.startswith, "Contains": str.__contains__,
                  "Ends with": str.endswith}[mode]
            test = lambda s: fn(s if case else s.lower(), needle)
        self.shown = [r for r in self.items if not text or test(self._subject(r))]
        self._render()

    def sort_by(self, col):
        rev = self._sort == (col, False)
        self._sort = (col, rev)
        self._render()

    def _render(self):
        col, rev = self._sort
        key = (lambda r: str(r["sort"]).lower()) if col == "title" else \
              (lambda r: str(r[col]).lower())
        rows = sorted(self.shown, key=key, reverse=rev)
        t = self.tree
        t.delete(*t.get_children())
        for r in rows[:20000]:
            t.insert("", "end", values=(r["title"], r["year"], r["type"], r["library"], r["file"]))
        more = f" (showing first 20,000)" if len(rows) > 20000 else ""
        if not self.items:
            self.count.set("No titles loaded yet. Pick a server and library; titles load automatically.")
        elif not rows:
            self.count.set(f"No matches among {len(self.items):,} titles")
        else:
            self.count.set(f"{len(rows):,} of {len(self.items):,} titles{more}")

    # -------------------------------------------------------------- groups --
    def prefix_of(self, rec):
        s = self._subject(rec)
        if self.letters_only.get():
            s = "".join(ch for ch in s if ch.isalpha())
        n = max(1, int(self.plen.get() or 3))
        p = s[:n]
        return p if self.case.get() else p.upper()

    def group(self):
        counts = Counter(self.prefix_of(r) for r in self.items)
        g = self.groups
        g.delete(*g.get_children())
        for p, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            g.insert("", "end", iid=f"p:{p}", values=(p or "(none)", n))

    def _on_group(self, _e):
        sel = self.groups.selection()
        if not sel:
            return
        p = sel[0][2:]
        self.shown = [r for r in self.items if self.prefix_of(r) == p]
        self._render()

    # -------------------------------------------------------------- output --
    def _selected_or_shown(self):
        cols = ("title", "year", "type", "library", "file")
        ids = self.tree.selection() or self.tree.get_children()
        return [dict(zip(cols, self.tree.item(i, "values"))) for i in ids]

    def copy(self):
        rows = self._selected_or_shown()
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(r["title"] for r in rows))
        self.count.set(f"Copied {len(rows):,} titles to the clipboard")

    def export(self):
        rows = self._selected_or_shown()
        if not rows:
            messagebox.showinfo("Title Finder", "Nothing to export.", parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"{self.server.get()} titles.csv")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["title", "year", "type", "library", "file"])
            w.writeheader()
            w.writerows(rows)
        self.count.set(f"Exported {len(rows):,} titles to {path}")


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        pass
    root = tk.Tk()
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for ico in (os.path.join(base, "icon.ico"), os.path.join(base, "installer", "icon.ico")):
        if os.path.exists(ico):
            try:
                root.iconbitmap(default=ico)
            except tk.TclError:
                pass
            break
    try:
        ttk.Style(root).theme_use("vista")
    except tk.TclError:
        pass
    TitleFinder(root)
    root.mainloop()


if __name__ == "__main__":
    main()
