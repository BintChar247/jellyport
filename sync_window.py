"""
Sync playlists window for Jellyport.

Pairs playlists by name on Plex and Jellyfin, shows what each side is missing,
and copies the missing entries (Jellyfin -> Plex, Plex -> Jellyfin, or both).
Missing playlists are created. Nothing is ever removed.
"""

import tkinter as tk
from tkinter import messagebox, ttk

import jellyport_cli as core

DIRECTIONS = [("Jellyfin → Plex", "to_plex"), ("Plex → Jellyfin", "to_jf"), ("Both ways", "both")]


class SyncWindow:
    def __init__(self, win, app):
        self.win, self.app = win, app
        self.plans = {}       # row iid -> plan
        self.checked = set()
        win.title("Sync playlists — Jellyport")
        win.geometry("980x560")
        win.transient(app.root)

        top = ttk.Frame(win, padding=(10, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Copy missing entries:").pack(side="left")
        self.direction = tk.StringVar(value="to_plex")
        for label, val in DIRECTIONS:
            ttk.Radiobutton(top, text=label, value=val, variable=self.direction,
                            command=self.compare).pack(side="left", padx=6)
        ttk.Button(top, text="⟳ Compare", command=self.compare).pack(side="left", padx=10)

        ttk.Label(win, text="Playlists are paired by name. Missing playlists are created. "
                            "Nothing is ever removed. Click a row to tick or untick it; "
                            "double-click to see entries that can't be matched.",
                  foreground="#666", padding=(10, 0)).pack(fill="x")

        bottom = ttk.Frame(win, padding=(10, 8))
        bottom.pack(side="bottom", fill="x")
        self.summary = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.summary).pack(side="left")
        self.go = ttk.Button(bottom, text="Sync ticked playlists", command=self.apply,
                             state="disabled")
        self.go.pack(side="right")

        cols = ("tick", "plex", "jf", "add_plex", "add_jf", "missing", "note")
        fr = ttk.Frame(win, padding=(10, 6, 10, 0))
        fr.pack(fill="both", expand=True)
        t = ttk.Treeview(fr, columns=cols, selectmode="browse")
        t.heading("#0", text="Playlist", anchor="w")
        t.column("#0", width=230)
        for c, txt, w in (("tick", "Sync", 50), ("plex", "In Plex", 70),
                          ("jf", "In Jellyfin", 80), ("add_plex", "+ to Plex", 75),
                          ("add_jf", "+ to Jellyfin", 90), ("missing", "Not found", 75),
                          ("note", "", 260)):
            t.heading(c, text=txt)
            t.column(c, width=w, anchor="w" if c == "note" else "center", stretch=c == "note")
        vs = ttk.Scrollbar(fr, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=vs.set)
        vs.pack(side="right", fill="y")
        t.pack(fill="both", expand=True)
        t.tag_configure("work", foreground="#1a7f37")
        t.tag_configure("idle", foreground="#888")
        t.bind("<ButtonRelease-1>", self._toggle)
        t.bind("<Double-1>", self._show_missing)
        self.tree = t
        self.compare()

    # ------------------------------------------------------------- compare --
    def compare(self):
        app, direction = self.app, self.direction.get()
        mappings = app.cfg.get("path_mappings", [])
        self.tree.delete(*self.tree.get_children())
        self.plans.clear()
        self.checked.clear()
        self.go.configure(state="disabled")
        self.summary.set("Comparing…")

        def work():
            if direction in ("to_plex", "both") and getattr(app, "_plex_matcher", None) is None:
                app._plex_matcher = core.PlexMatcher(app.plex.library_index(), mappings)
            p_pls = {p["title"].lower(): p for p in app.plex.playlists()}
            j_pls = {p["Name"].lower(): p for p in app.jf.playlists()}
            names = {"to_plex": set(j_pls), "to_jf": set(p_pls)}.get(direction,
                                                                     set(p_pls) | set(j_pls))
            out = []
            for n in sorted(names):
                pp, jpl = p_pls.get(n), j_pls.get(n)
                name = (jpl or {}).get("Name") or (pp or {}).get("title")
                d, note = direction, ""
                if pp and pp.get("smart") and d in ("to_plex", "both"):
                    note = "Plex smart playlist: can't add to it"
                    d = "to_jf" if d == "both" else None
                if d:
                    plan = core.plan_sync(app.plex, app.jf, app.matcher,
                                          getattr(app, "_plex_matcher", None),
                                          name, pp, jpl, d)
                else:
                    plan = {"name": name, "plex_pl": pp, "jf_pl": jpl, "add_plex": [],
                            "add_jf": [], "missing": [],
                            "plex_count": pp.get("leafCount", "") if pp else "",
                            "jf_count": jpl.get("ChildCount", "") if jpl else ""}
                if not pp and plan["add_plex"]:
                    note = note or "will be created in Plex"
                if not jpl and plan["add_jf"]:
                    note = note or "will be created in Jellyfin"
                plan["note"] = note
                out.append(plan)
            return out

        app.bg("Comparing playlists…", work, self._show,
               lambda e: self.summary.set(f"Compare failed: {e}"))

    def _show(self, plans):
        if not self.win.winfo_exists():
            return
        t = self.tree
        for plan in plans:
            work = len(plan["add_plex"]) + len(plan["add_jf"])
            if work:
                note = plan["note"]
            else:
                note = plan["note"] or "up to date"
            iid = t.insert("", "end", text=plan["name"], tags=("work" if work else "idle",),
                           values=("☑" if work else "",
                                   plan["plex_count"] if plan["plex_pl"] else "—",
                                   plan["jf_count"] if plan["jf_pl"] else "—",
                                   len(plan["add_plex"]) or "", len(plan["add_jf"]) or "",
                                   len(plan["missing"]) or "", note))
            self.plans[iid] = plan
            if work:
                self.checked.add(iid)
        self._update()

    def _update(self):
        n_p = sum(len(self.plans[i]["add_plex"]) for i in self.checked)
        n_j = sum(len(self.plans[i]["add_jf"]) for i in self.checked)
        if not self.plans:
            self.summary.set("No playlists to compare.")
        else:
            self.summary.set(f"{len(self.checked)} playlist(s) ticked: {n_p} entries to Plex, "
                             f"{n_j} to Jellyfin")
        self.go.configure(state="normal" if self.checked else "disabled")

    def _toggle(self, e):
        iid = self.tree.identify_row(e.y)
        plan = self.plans.get(iid)
        if not plan or not (plan["add_plex"] or plan["add_jf"]):
            return
        if iid in self.checked:
            self.checked.discard(iid)
            self.tree.set(iid, "tick", "☐")
        else:
            self.checked.add(iid)
            self.tree.set(iid, "tick", "☑")
        self._update()

    def _show_missing(self, e):
        plan = self.plans.get(self.tree.identify_row(e.y))
        if not plan or not plan["missing"]:
            return
        lines = [f"not in {where}: {what}" for where, what in plan["missing"][:40]]
        if len(plan["missing"]) > 40:
            lines.append(f"…and {len(plan['missing']) - 40} more")
        messagebox.showinfo(f'Not found — {plan["name"]}', "\n".join(lines), parent=self.win)

    # --------------------------------------------------------------- apply --
    def apply(self):
        plans = [self.plans[i] for i in self.checked]
        n_p = sum(len(p["add_plex"]) for p in plans)
        n_j = sum(len(p["add_jf"]) for p in plans)
        if not messagebox.askyesno(
                "Sync playlists",
                f"Add {n_p} entries to Plex and {n_j} to Jellyfin across "
                f"{len(plans)} playlist(s)?\n\nNothing will be removed.", parent=self.win):
            return
        app = self.app
        self.go.configure(state="disabled")

        def work():
            out = []
            for plan in plans:
                try:
                    out.append((plan["name"], *core.apply_sync(app.plex, app.jf, plan), None))
                except Exception as e:  # noqa: BLE001
                    out.append((plan["name"], 0, 0, e))
            return out

        def done(results):
            for name, a, b, err in results:
                if err:
                    app.log(f'Sync "{name}" failed: {err}', "err")
                else:
                    app.log(f'⇄ "{name}": +{a} to Plex, +{b} to Jellyfin', "ok")
            if self.win.winfo_exists():
                self.compare()
            if not app.has_pending():
                app.connect()

        app.bg("Syncing playlists…", work, done, lambda e: self._update())
