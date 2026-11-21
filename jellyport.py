#!/usr/bin/env python3
"""
Jellyport - move your Plex playlists to Jellyfin, with drag and drop.

Left:  your Plex playlists and movie libraries (expand to see the movies).
Right: your Jellyfin playlists.
Drag movies (or a whole playlist) from left to right, review the green
"pending" rows, then click "Copy to Jellyfin".

Run:  python jellyport.py
"""

import itertools
import json
import os
import queue
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, simpledialog, ttk

import jellyport_cli as core

APP_NAME = "Jellyport"
__version__ = core.__version__

if getattr(sys, "frozen", False):
    # Installed .exe: keep settings in %APPDATA%\Jellyport (Program Files is read-only)
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
else:
    CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "plex": {"url": "http://192.168.1.10:32400", "token": "", "verify_ssl": True},
    "jellyfin": {"url": "http://192.168.1.10:8096", "api_key": "", "user": "",
                 "verify_ssl": True},
    "path_mappings": [],
}

LARGE_DROP = 300  # ask before adding more than this many items at once


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            user = json.load(f)
        for k in ("plex", "jellyfin"):
            cfg[k].update(user.get(k, {}))
        cfg["path_mappings"] = user.get("path_mappings", [])
    return cfg


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def config_complete(cfg):
    return all([cfg["plex"].get("url"), cfg["plex"].get("token"),
                cfg["jellyfin"].get("url"), cfg["jellyfin"].get("api_key"),
                cfg["jellyfin"].get("user")])


# --------------------------------------------------------------------------- #
# Labels
# --------------------------------------------------------------------------- #
def plex_label(px):
    if px.get("type") == "episode":
        return (f'{px.get("grandparentTitle", "")} S{px.get("parentIndex", 0):02d}'
                f'E{px.get("index", 0):02d} - {px.get("title", "")}')
    return px.get("title", "?")


def jf_label(it):
    if it.get("Type") == "Episode":
        return (f'{it.get("SeriesName", "")} S{it.get("ParentIndexNumber", 0) or 0:02d}'
                f'E{it.get("IndexNumber", 0) or 0:02d} - {it.get("Name", "")}')
    return it.get("Name", "?")


# --------------------------------------------------------------------------- #
# Settings dialog
# --------------------------------------------------------------------------- #
class SettingsDialog(tk.Toplevel):
    def __init__(self, master, cfg, on_save):
        super().__init__(master)
        self.title("Settings")
        self.transient(master)
        self.resizable(True, False)
        self.cfg, self.on_save = cfg, on_save

        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)
        self.v = {}
        r = 0

        def heading(text):
            nonlocal r
            ttk.Label(frm, text=text, font=("Segoe UI", 10, "bold")).grid(
                row=r, column=0, columnspan=2, sticky="w", pady=(8 if r else 0, 4))
            r += 1

        def field(label, sect, key, secret=False):
            nonlocal r
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=2)
            var = tk.StringVar(value=str(cfg[sect].get(key, "")))
            ttk.Entry(frm, textvariable=var, width=52, show="•" if secret else "").grid(
                row=r, column=1, sticky="ew", pady=2)
            self.v[(sect, key)] = var
            r += 1

        def check(label, sect, key):
            nonlocal r
            var = tk.BooleanVar(value=bool(cfg[sect].get(key, True)))
            ttk.Checkbutton(frm, text=label, variable=var).grid(
                row=r, column=1, sticky="w", pady=2)
            self.v[(sect, key)] = var
            r += 1

        heading("Plex")
        field("Server URL", "plex", "url")
        field("Token", "plex", "token", secret=True)
        check("Verify SSL certificate", "plex", "verify_ssl")

        heading("Jellyfin")
        field("Server URL", "jellyfin", "url")
        field("API key", "jellyfin", "api_key", secret=True)
        field("User name", "jellyfin", "user")
        check("Verify SSL certificate", "jellyfin", "verify_ssl")

        heading("Path mappings (only if Plex and Jellyfin see the NAS folders differently)")
        ttk.Label(frm, text="One per line:   Plex path  =>  Jellyfin path",
                  foreground="#666").grid(row=r, column=0, columnspan=2, sticky="w")
        r += 1
        self.maps = tk.Text(frm, height=5, width=60, font=("Consolas", 9))
        self.maps.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        self.maps.insert("1.0", "\n".join(
            f'{m["plex"]}  =>  {m["jellyfin"]}' for m in cfg.get("path_mappings", [])))
        if not cfg.get("path_mappings"):
            self.maps.insert("1.0", "")
        r += 1
        ttk.Label(frm, text="e.g.  /volume1/video/Movies  =>  /media/movies",
                  foreground="#666").grid(row=r, column=0, columnspan=2, sticky="w")
        r += 1

        btns = ttk.Frame(frm)
        btns.grid(row=r, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Save & Connect", command=self.save).pack(side="right", padx=6)

        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()

    def save(self):
        cfg = self.cfg
        for (sect, key), var in self.v.items():
            val = var.get()
            cfg[sect][key] = val.strip() if isinstance(val, str) else val
        maps = []
        for line in self.maps.get("1.0", "end").splitlines():
            if "=>" in line:
                a, b = (s.strip() for s in line.split("=>", 1))
                if a and b:
                    maps.append({"plex": a, "jellyfin": b})
            elif line.strip():
                messagebox.showerror("Path mappings",
                                     f"Line is missing '=>':\n{line}", parent=self)
                return
        cfg["path_mappings"] = maps
        save_config(cfg)
        self.destroy()
        self.on_save()


# --------------------------------------------------------------------------- #
# Main window
# --------------------------------------------------------------------------- #
class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.plex = self.jf = self.matcher = None
        self.q = queue.Queue()
        self.busy = 0
        self.ids = itertools.count()

        self.left = {}        # left iid -> {"kind": group|plex_playlist|section|item, ...}
        self.plex_cache = {}  # container iid -> list of Plex items
        self.pl = {}          # right playlist iid -> state
        self.row_owner = {}   # right pending/missing row iid -> playlist iid

        self.drag = None
        self.ghost = None
        self.drop_hl = None

        self._build()
        self.root.after(100, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        if config_complete(self.cfg):
            self.root.after(200, self.connect)
        else:
            self.root.after(200, self.open_settings)

    # ------------------------------------------------------------------ UI --
    def _build(self):
        r = self.root
        r.title(f"{APP_NAME} {__version__} — Plex → Jellyfin playlists")
        r.geometry("1250x780")
        r.minsize(900, 550)

        self.bold = tkfont.nametofont("TkDefaultFont").copy()
        self.bold.configure(weight="bold")

        top = ttk.Frame(r, padding=(10, 8))
        top.pack(fill="x")
        ttk.Button(top, text="⚙ Settings…", command=self.open_settings).pack(side="left")
        ttk.Button(top, text="⟳ Connect / Refresh", command=self.connect).pack(side="left", padx=6)
        ttk.Button(top, text="🔎 Title Finder…", command=self.open_title_finder).pack(side="left")
        ttk.Button(top, text="⇄ Sync playlists…", command=self.open_sync).pack(side="left", padx=6)
        self.prog = ttk.Progressbar(top, mode="indeterminate", length=140)
        self.prog.pack(side="right")
        self.status = tk.StringVar(value="Not connected")
        ttk.Label(top, textvariable=self.status).pack(side="right", padx=10)

        body = ttk.PanedWindow(r, orient="vertical")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        panes = ttk.PanedWindow(body, orient="horizontal")
        body.add(panes, weight=5)

        # ---- left: Plex
        lf = ttk.LabelFrame(panes, text=" Plex — select movies or playlists, drag them right ",
                            padding=8)
        panes.add(lf, weight=1)
        srow = ttk.Frame(lf)
        srow.pack(fill="x")
        ttk.Label(srow, text="Filter:").pack(side="left")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *a: self._apply_filter())
        ttk.Entry(srow, textvariable=self.filter_var).pack(side="left", fill="x",
                                                           expand=True, padx=(4, 0))
        lb = ttk.Frame(lf)
        lb.pack(side="bottom", fill="x", pady=(8, 0))
        ttk.Label(lb, text="Ctrl/Shift-click to pick several", foreground="#666").pack(side="left")
        ttk.Button(lb, text="Add selected  →", command=self.add_selected).pack(side="right")
        self.ltree = self._make_tree(lf)

        # ---- right: Jellyfin
        rf = ttk.LabelFrame(panes, text=" Jellyfin playlists — drop here ", padding=8)
        panes.add(rf, weight=1)
        rtop = ttk.Frame(rf)
        rtop.pack(fill="x")
        ttk.Button(rtop, text="＋ New playlist…", command=self.new_playlist).pack(side="left")
        ttk.Button(rtop, text="✕ Remove selected pending",
                   command=self.remove_pending).pack(side="left", padx=6)
        rb = ttk.Frame(rf)
        rb.pack(side="bottom", fill="x", pady=(8, 0))
        ttk.Button(rb, text="Discard all pending", command=self.discard_pending).pack(side="left")
        self.apply_btn = ttk.Button(rb, text="Copy to Jellyfin", command=self.apply_changes)
        self.apply_btn.pack(side="right")
        legend = ttk.Frame(rb)
        legend.pack(side="right", padx=10)
        tk.Label(legend, text="■ pending", fg="#1a7f37").pack(side="left")
        tk.Label(legend, text="■ not found in Jellyfin", fg="#c62828").pack(side="left", padx=6)
        self.rtree = self._make_tree(rf)

        # ---- log
        logf = ttk.LabelFrame(body, text=" Log ", padding=4)
        body.add(logf, weight=1)
        self.logw = tk.Text(logf, height=7, state="disabled", wrap="word",
                            font=("Consolas", 9), relief="flat")
        lsb = ttk.Scrollbar(logf, command=self.logw.yview)
        self.logw.configure(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y")
        self.logw.pack(fill="both", expand=True)
        self.logw.tag_configure("err", foreground="#c62828")
        self.logw.tag_configure("ok", foreground="#1a7f37")

        # events
        self.ltree.bind("<<TreeviewOpen>>", self._on_left_open)
        self.rtree.bind("<<TreeviewOpen>>", self._on_right_open)
        self.ltree.bind("<ButtonPress-1>", self._dnd_press)
        self.ltree.bind("<B1-Motion>", self._dnd_motion)
        self.ltree.bind("<ButtonRelease-1>", self._dnd_release)
        self.ltree.bind("<Double-1>", lambda e: self.add_selected())
        self.ltree.bind("<Return>", lambda e: self.add_selected())
        self.rtree.bind("<Delete>", lambda e: self.remove_pending())
        self._update_apply_btn()

    def _make_tree(self, parent):
        fr = ttk.Frame(parent)
        fr.pack(fill="both", expand=True, pady=(6, 0))
        t = ttk.Treeview(fr, columns=("year", "info"), selectmode="extended")
        t.heading("#0", text="Title", anchor="w")
        t.heading("year", text="Year")
        t.heading("info", text="", anchor="w")
        t.column("#0", width=330)
        t.column("year", width=60, anchor="center", stretch=False)
        t.column("info", width=150, stretch=False)
        vs = ttk.Scrollbar(fr, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=vs.set)
        vs.pack(side="right", fill="y")
        t.pack(side="left", fill="both", expand=True)
        t.tag_configure("group", font=self.bold)
        t.tag_configure("container", font=self.bold)
        t.tag_configure("pending", foreground="#1a7f37")
        t.tag_configure("newpl", foreground="#1a7f37", font=self.bold)
        t.tag_configure("missing", foreground="#c62828")
        t.tag_configure("dummy", foreground="#888")
        t.tag_configure("drop", background="#cfe8ff")
        return t

    def _iid(self):
        return f"n{next(self.ids)}"

    def log(self, msg, tag=None):
        self.logw.configure(state="normal")
        self.logw.insert("end", msg + "\n", tag or ())
        self.logw.see("end")
        self.logw.configure(state="disabled")

    # ---------------------------------------------------------- background --
    def bg(self, label, fn, done=None, fail=None):
        self.busy += 1
        self.status.set(label)
        self.prog.configure(mode="indeterminate")
        self.prog.start(12)

        def run():
            try:
                self.q.put((done, fail, fn(), None))
            except Exception as e:  # noqa: BLE001 - shown to the user
                self.q.put((done, fail, None, e))

        threading.Thread(target=run, daemon=True).start()

    def _poll(self):
        try:
            while True:
                done, fail, res, err = self.q.get_nowait()
                self.busy -= 1
                if self.busy <= 0:
                    self.busy = 0
                    self.prog.stop()
                    self.prog.configure(mode="determinate", value=0)
                    self.status.set("Connected" if self.jf else "Not connected")
                try:
                    if err:
                        self.log(f"Error: {err}", "err")
                        if fail:
                            fail(err)
                    elif done:
                        done(res)
                except Exception as e:  # noqa: BLE001
                    self.log(f"Error: {e}", "err")
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    # ------------------------------------------------------------ settings --
    def open_sync(self):
        """Compare same-named playlists and copy missing entries either way."""
        if not self.jf or not self.plex:
            messagebox.showinfo("Sync playlists", "Connect to Plex and Jellyfin first.")
            return
        win = getattr(self, "_sync_win", None)
        if win is not None and win.winfo_exists():
            win.deiconify()
            win.lift()
            return
        import sync_window
        self._sync_win = tk.Toplevel(self.root)
        sync_window.SyncWindow(self._sync_win, self)

    def open_title_finder(self):
        """Search / group / export titles from either server (separate window)."""
        win = getattr(self, "_tf_win", None)
        if win is not None and win.winfo_exists():
            win.deiconify()
            win.lift()
            return
        import title_finder  # local import: title_finder imports this module
        self._tf_win = tk.Toplevel(self.root)
        title_finder.TitleFinder(self._tf_win, self.cfg)

    def open_settings(self):
        SettingsDialog(self.root, self.cfg, self.connect)

    # ------------------------------------------------------------- connect --
    def has_pending(self):
        return any(st["id"] is None or st["pending"] for st in self.pl.values())

    def connect(self):
        if not config_complete(self.cfg):
            messagebox.showinfo("Settings needed",
                                "Fill in the Plex and Jellyfin details first.")
            self.open_settings()
            return
        if self.has_pending() and not messagebox.askyesno(
                "Refresh", "Refreshing discards your pending (uncopied) changes. Continue?"):
            return
        cfg = self.cfg

        def work():
            plex = core.Plex(cfg["plex"])
            pls = plex.playlists()
            secs = [s for s in plex.sections() if s.get("type") == "movie"]
            jf = core.Jellyfin(cfg["jellyfin"])
            lib = jf.library()
            matcher = core.Matcher(lib, cfg.get("path_mappings", []))
            jpls = jf.playlists()
            return plex, pls, secs, jf, matcher, jpls, len(lib)

        self.log("Connecting to Plex and Jellyfin…")
        self.bg("Connecting…", work, self._on_connected)

    def _on_connected(self, res):
        self.plex, pls, secs, self.jf, self.matcher, jpls, nlib = res
        self.status.set("Connected")
        libs = "library" if len(secs) == 1 else "libraries"
        self.log(f"Plex: {len(pls)} playlist(s), {len(secs)} movie {libs}. "
                 f"Jellyfin: {nlib} items in library, {len(jpls)} playlist(s).", "ok")

        # left
        self.ltree.delete(*self.ltree.get_children())
        self.left.clear()
        self.plex_cache.clear()
        g = self._iid()
        self.ltree.insert("", "end", g, text="Playlists", open=True, tags=("group",))
        self.left[g] = {"kind": "group"}
        for p in sorted(pls, key=lambda p: p["title"].lower()):
            n = p.get("leafCount", "?")
            info = f"{n} items" + ("  · smart" if p.get("smart") else "")
            self._add_container(g, "plex_playlist", p["ratingKey"], p["title"], info)
        g2 = self._iid()
        self.ltree.insert("", "end", g2, text="Movie libraries", open=True, tags=("group",))
        self.left[g2] = {"kind": "group"}
        for s in secs:
            self._add_container(g2, "section", s["key"], s["title"], "library")

        # right
        self.rtree.delete(*self.rtree.get_children())
        self.pl.clear()
        self.row_owner.clear()
        for p in sorted(jpls, key=lambda p: p["Name"].lower()):
            self._add_jf_playlist(p["Name"], p["Id"], p.get("ChildCount"))
        self._update_apply_btn()

    def _add_container(self, parent, kind, key, title, info):
        iid = self._iid()
        self.ltree.insert(parent, "end", iid, text=title, values=("", info),
                          tags=("container",))
        self.ltree.insert(iid, "end", self._iid(), text="Loading…", tags=("dummy",))
        self.left[iid] = {"kind": kind, "key": key, "title": title}

    # --------------------------------------------------------- left loading --
    def _on_left_open(self, _e):
        iid = self.ltree.focus()
        d = self.left.get(iid)
        if d and d["kind"] in ("plex_playlist", "section"):
            self.load_plex(iid)

    def load_plex(self, iid, then=None):
        if iid in self.plex_cache:
            if then:
                then()
            return
        d = self.left[iid]
        if then:
            d.setdefault("waiters", []).append(then)
        if d.get("loading"):
            return
        d["loading"] = True
        plex, kind, key = self.plex, d["kind"], d["key"]

        def work():
            if kind == "plex_playlist":
                return plex.playlist_items(key)
            items = plex.section_items(key)
            return sorted(items, key=lambda x: (x.get("titleSort") or x.get("title", "")).lower())

        def done(items):
            d["loading"] = False
            if not self.ltree.exists(iid):
                return
            self.plex_cache[iid] = items
            self._fill_container(iid)
            for w in d.pop("waiters", []):
                w()

        def fail(_e):
            d["loading"] = False
            d.pop("waiters", None)

        self.bg(f'Loading "{d["title"]}" from Plex…', work, done, fail)

    def _fill_container(self, iid):
        t = self.ltree
        t.delete(*t.get_children(iid))
        flt = self.filter_var.get().strip().lower()
        shown = 0
        for px in self.plex_cache[iid]:
            label = plex_label(px)
            if flt and flt not in label.lower():
                continue
            c = self._iid()
            t.insert(iid, "end", c, text=label, values=(px.get("year", ""), ""))
            self.left[c] = {"kind": "item", "item": px}
            shown += 1
        total = len(self.plex_cache[iid])
        info = f"{total} items" if not flt else f"{shown} of {total}"
        if self.left[iid]["kind"] == "section" and not flt:
            info = f"{total} movies"
        t.set(iid, "info", info)
        return shown

    def _apply_filter(self):
        flt = self.filter_var.get().strip()
        for iid in list(self.plex_cache):
            if self.ltree.exists(iid):
                shown = self._fill_container(iid)
                if flt and shown:
                    self.ltree.item(iid, open=True)

    # ------------------------------------------------------- right loading --
    def _add_jf_playlist(self, name, pid, count=None, new=False):
        iid = self._iid()
        if new:
            self.rtree.insert("", "end", iid, text=name, values=("", "new — will be created"),
                              tags=("newpl",), open=True)
        else:
            info = f"{count} items" if count is not None else ""
            self.rtree.insert("", "end", iid, text=name, values=("", info),
                              tags=("container",))
            self.rtree.insert(iid, "end", self._iid(), text="Loading…", tags=("dummy",))
        self.pl[iid] = {"name": name, "id": pid, "loaded": new, "existing": set(),
                        "pending": [], "pending_rows": {}, "missing": set()}
        return iid

    def _on_right_open(self, _e):
        iid = self.rtree.focus()
        if iid in self.pl:
            self.load_jf(iid)

    def load_jf(self, iid, then=None):
        st = self.pl[iid]
        if st["loaded"]:
            if then:
                then()
            return
        if then:
            st.setdefault("waiters", []).append(then)
        if st.get("loading"):
            return
        st["loading"] = True
        jf, pid = self.jf, st["id"]

        def done(items):
            st["loading"] = False
            if not self.rtree.exists(iid):
                return
            t = self.rtree
            t.delete(*t.get_children(iid))
            for it in items:
                t.insert(iid, "end", self._iid(), text=jf_label(it),
                         values=(it.get("ProductionYear", ""), ""))
            st["existing"] = {it["Id"] for it in items}
            st["loaded"] = True
            t.set(iid, "info", f"{len(items)} items")
            for w in st.pop("waiters", []):
                w()

        def fail(_e):
            st["loading"] = False
            st.pop("waiters", None)

        self.bg(f'Loading Jellyfin playlist "{st["name"]}"…',
                lambda: jf.playlist_items(pid), done, fail)

    def _find_pl(self, name):
        for iid, st in self.pl.items():
            if st["name"].lower() == name.lower():
                return iid
        return None

    def _find_or_new_pl(self, name):
        return self._find_pl(name) or self._add_jf_playlist(name, None, new=True)

    def _target_pl(self, row):
        while row and row not in self.pl:
            row = self.rtree.parent(row)
        return row or None

    # --------------------------------------------------------- drag & drop --
    def _dnd_press(self, e):
        t = self.ltree
        if t.identify_region(e.x, e.y) not in ("tree", "cell"):
            self.drag = None
            return None
        if "indicator" in t.identify_element(e.x, e.y):
            self.drag = None
            return None
        row = t.identify_row(e.y)
        self.drag = {"x": e.x_root, "y": e.y_root, "row": row, "active": False, "keep": False}
        # keep a multi-selection intact when starting a drag from it
        if row and row in t.selection() and not (e.state & 0x0005):
            self.drag["keep"] = True
            return "break"
        return None

    def _dnd_motion(self, e):
        d = self.drag
        if not d or not d["row"] or not self.jf:
            return None
        if not d["active"]:
            if abs(e.x_root - d["x"]) + abs(e.y_root - d["y"]) < 8:
                return None
            if d["row"] not in self.ltree.selection():
                self.ltree.selection_set(d["row"])
            d["active"] = True
            n = len(self.ltree.selection())
            self.ghost = tk.Toplevel(self.root)
            self.ghost.overrideredirect(True)
            self.ghost.attributes("-topmost", True)
            tk.Label(self.ghost, text=f"  ➜ {n} selected  ", bg="#2b6cb0", fg="white",
                     font=self.bold, padx=4, pady=3).pack()
        self.ghost.geometry(f"+{e.x_root + 14}+{e.y_root + 10}")
        self._highlight(self._drop_target_at(e.x_root, e.y_root))
        return "break"

    def _dnd_release(self, e):
        d, self.drag = self.drag, None
        if not d:
            return None
        if d["active"]:
            if self.ghost:
                self.ghost.destroy()
                self.ghost = None
            self._highlight(None)
            w = self.root.winfo_containing(e.x_root, e.y_root)
            if w is self.rtree:
                self.drop_on(self._drop_target_at(e.x_root, e.y_root))
            return "break"
        if d["keep"]:
            self.ltree.selection_set(d["row"])
            self.ltree.focus(d["row"])
        return None

    def _drop_target_at(self, x_root, y_root):
        if self.root.winfo_containing(x_root, y_root) is not self.rtree:
            return None
        row = self.rtree.identify_row(y_root - self.rtree.winfo_rooty())
        return self._target_pl(row)

    def _highlight(self, iid):
        if self.drop_hl == iid:
            return
        for old, add in ((self.drop_hl, False), (iid, True)):
            if old and self.rtree.exists(old):
                tags = [t for t in self.rtree.item(old, "tags") if t != "drop"]
                if add:
                    tags.append("drop")
                self.rtree.item(old, tags=tags)
        self.drop_hl = iid

    # ------------------------------------------------------------- adding --
    def add_selected(self):
        sel = self.rtree.selection()
        self.drop_on(self._target_pl(sel[0]) if sel else None)

    def drop_on(self, target):
        """Add the Plex selection to Jellyfin playlist `target` (None = new playlist)."""
        if not self.jf:
            return
        sel = self.ltree.selection()
        containers = [i for i in sel
                      if self.left.get(i, {}).get("kind") in ("plex_playlist", "section")]
        items = [i for i in sel if self.left.get(i, {}).get("kind") == "item"
                 and self.ltree.parent(i) not in containers]
        if not containers and not items:
            messagebox.showinfo("Nothing selected",
                                "Select one or more movies or playlists on the Plex side.")
            return

        # make sure whole playlists/libraries are loaded first
        need = [c for c in containers if c not in self.plex_cache]
        if need:
            remaining = {"n": len(need)}

            def one_done():
                remaining["n"] -= 1
                if remaining["n"] == 0:
                    self.ltree.selection_set(sel)
                    self.drop_on(target)

            for c in need:
                self.load_plex(c, one_done)
            return

        groups = []  # (playlist name or target iid, [plex items])
        if target:
            all_items = [px for c in containers for px in self.plex_cache[c]]
            all_items += [self.left[i]["item"] for i in items]
            groups.append((target, all_items))
        else:
            for c in containers:
                groups.append((self.left[c]["title"], list(self.plex_cache[c])))
            if items:
                name = simpledialog.askstring(
                    "New Jellyfin playlist",
                    f"Add {len(items)} movie(s) to which Jellyfin playlist?\n"
                    "(Type a new name, or an existing one.)\n\n"
                    "Tip: drop onto a playlist on the right to skip this.",
                    parent=self.root)
                if not name or not name.strip():
                    return
                groups.append((name.strip(), [self.left[i]["item"] for i in items]))

        total = sum(len(g[1]) for g in groups)
        if total > LARGE_DROP and not messagebox.askyesno(
                "Lots of items", f"Add {total} items to Jellyfin playlist(s)?"):
            return

        for tgt, plex_items in groups:
            node = tgt if tgt in self.pl else self._find_or_new_pl(tgt)
            self.load_jf(node, lambda n=node, p=plex_items: self._add_items(n, p))

    def _add_items(self, node, plex_items):
        st = self.pl[node]
        t = self.rtree
        added = dup = 0
        missing = []
        pending_ids = {it["Id"] for it in st["pending"]}
        for px in plex_items:
            hit, how = self.matcher.match(px)
            if not hit:
                label = plex_label(px)
                if label not in st["missing"]:
                    st["missing"].add(label)
                    r = self._iid()
                    t.insert(node, "end", r, text=label,
                             values=(px.get("year", ""), "not in Jellyfin"),
                             tags=("missing",))
                    self.row_owner[r] = node
                missing.append(label)
                continue
            if hit["Id"] in st["existing"] or hit["Id"] in pending_ids:
                dup += 1
                continue
            pending_ids.add(hit["Id"])
            st["pending"].append(hit)
            r = self._iid()
            t.insert(node, "end", r, text=jf_label(hit),
                     values=(hit.get("ProductionYear", ""), f"+ pending ({how})"),
                     tags=("pending",))
            st["pending_rows"][r] = hit["Id"]
            self.row_owner[r] = node
            added += 1
        t.item(node, open=True)
        msg = f'"{st["name"]}": {added} added'
        if dup:
            msg += f", {dup} already there"
        if missing:
            msg += f", {len(missing)} not found in Jellyfin"
        self.log(msg, "err" if missing and not added else None)
        for m in missing[:20]:
            self.log(f"    not found: {m}", "err")
        if len(missing) > 20:
            self.log(f"    …and {len(missing) - 20} more", "err")
        self._update_apply_btn()

    def new_playlist(self):
        if not self.jf:
            return
        name = simpledialog.askstring("New Jellyfin playlist", "Playlist name:",
                                      parent=self.root)
        if not name or not name.strip():
            return
        name = name.strip()
        if self._find_pl(name):
            messagebox.showinfo("Exists", f'A playlist named "{name}" already exists.')
            return
        iid = self._add_jf_playlist(name, None, new=True)
        self.rtree.selection_set(iid)
        self.rtree.see(iid)
        self._update_apply_btn()

    # ----------------------------------------------------- removing pending --
    def remove_pending(self):
        for r in self.rtree.selection():
            if not self.rtree.exists(r):
                continue
            if r in self.pl and self.pl[r]["id"] is None:
                self._drop_pl_node(r)
            elif r in self.row_owner:
                st = self.pl[self.row_owner.pop(r)]
                jid = st["pending_rows"].pop(r, None)
                if jid:
                    st["pending"] = [it for it in st["pending"] if it["Id"] != jid]
                else:
                    st["missing"].discard(self.rtree.item(r, "text"))
                self.rtree.delete(r)
        self._update_apply_btn()

    def _drop_pl_node(self, iid):
        for r in [r for r, o in self.row_owner.items() if o == iid]:
            del self.row_owner[r]
        self.rtree.delete(iid)
        del self.pl[iid]

    def discard_pending(self):
        for iid in list(self.pl):
            st = self.pl[iid]
            if st["id"] is None:
                self._drop_pl_node(iid)
                continue
            for r in [r for r, o in self.row_owner.items() if o == iid]:
                del self.row_owner[r]
                if self.rtree.exists(r):
                    self.rtree.delete(r)
            st["pending"].clear()
            st["pending_rows"].clear()
            st["missing"].clear()
        self._update_apply_btn()

    def _update_apply_btn(self):
        n = sum(len(st["pending"]) for st in self.pl.values())
        new = sum(1 for st in self.pl.values() if st["id"] is None)
        parts = []
        if n:
            parts.append(f"{n} item(s)")
        if new:
            parts.append(f"{new} new playlist(s)")
        self.apply_btn.configure(
            text="Copy to Jellyfin" + (f"  ({', '.join(parts)})" if parts else ""),
            state="normal" if parts else "disabled")

    # --------------------------------------------------------------- apply --
    def apply_changes(self):
        plan = [(iid, st) for iid, st in self.pl.items() if st["id"] is None or st["pending"]]
        if not plan:
            return
        lines = []
        for _, st in plan:
            verb = "Create" if st["id"] is None else "Add to"
            lines.append(f'{verb} "{st["name"]}": {len(st["pending"])} item(s)')
        if not messagebox.askyesno("Copy to Jellyfin", "\n".join(lines) + "\n\nGo ahead?"):
            return
        jf = self.jf
        jobs = [(iid, st["name"], st["id"], [it["Id"] for it in st["pending"]])
                for iid, st in plan]

        def work():
            out = []
            for iid, name, pid, ids in jobs:
                try:
                    if pid is None:
                        res = jf.create_playlist(name, ids[:100])
                        pid = res["Id"]
                        if len(ids) > 100:
                            jf.add_to_playlist(pid, ids[100:])
                    elif ids:
                        jf.add_to_playlist(pid, ids)
                    out.append((iid, name, pid, len(ids), None))
                except Exception as e:  # noqa: BLE001
                    out.append((iid, name, pid, len(ids), e))
            return out

        self.apply_btn.configure(state="disabled")
        self.bg("Copying to Jellyfin…", work, self._on_applied,
                lambda e: self._update_apply_btn())

    def _on_applied(self, results):
        for iid, name, pid, n, err in results:
            if err:
                self.log(f'Failed on "{name}": {err}', "err")
                continue
            self.log(f'✔ "{name}": {n} item(s) copied', "ok")
            if iid not in self.pl:
                continue
            st = self.pl[iid]
            for r in [r for r, o in self.row_owner.items() if o == iid]:
                del self.row_owner[r]
            st.update(id=pid, loaded=False, existing=set(), pending=[],
                      pending_rows={}, missing=set())
            t = self.rtree
            t.delete(*t.get_children(iid))
            t.item(iid, tags=("container",))
            t.insert(iid, "end", self._iid(), text="Loading…", tags=("dummy",))
            self.load_jf(iid, lambda i=iid: self.rtree.item(i, open=True))
        self._update_apply_btn()

    # --------------------------------------------------------------- close --
    def _on_close(self):
        if self.has_pending() and not messagebox.askyesno(
                "Quit", "You have pending changes that were not copied. Quit anyway?"):
            return
        self.root.destroy()


def main():
    try:  # crisp text on high-DPI Windows screens
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
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
