"""
Jellyport look & feel.

apply(root, "dark") gives every window the Jellyport dark skin (purple / amber
accents to match the icon, dark Windows title bars). apply(root, "classic")
keeps the standard Windows look. Call it once, before building any widgets;
afterwards read colours from theme.C so custom tags match the active skin.
"""

import ctypes
import sys
import tkinter as tk
from tkinter import ttk

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
MONO = ("Consolas", 9)

DARK = {
    "bg": "#121018",        # window
    "surface": "#1b1823",   # lists, text areas
    "field": "#252131",     # inputs, buttons
    "hover": "#2f2a3e",
    "border": "#3a3349",
    "text": "#ece8f5",
    "muted": "#9b94ab",
    "dim": "#6f6880",
    "accent": "#8b5cf6",    # purple
    "accent_hover": "#9d74ff",
    "accent_down": "#7444e0",
    "amber": "#f2a93b",     # orange from the icon
    "on_accent": "#ffffff",
    "select": "#3d2c6b",
    "green": "#4ade80",
    "red": "#f87171",
    "drop": "#4b3790",
}

CLASSIC = {
    "bg": "SystemButtonFace", "surface": "white", "field": "white", "hover": "#e5f1fb",
    "border": "#adadad", "text": "black", "muted": "#666666", "dim": "#888888",
    "accent": "#2b6cb0", "accent_hover": "#2b6cb0", "accent_down": "#2b6cb0",
    "amber": "#b7791f", "on_accent": "white", "select": "#0078d7",
    "green": "#1a7f37", "red": "#c62828", "drop": "#cfe8ff",
}

C = dict(CLASSIC)       # current palette (filled in by apply)
MODE = "classic"


def apply(root, mode="dark"):
    global MODE
    MODE = "dark" if mode == "dark" else "classic"
    C.clear()
    C.update(DARK if MODE == "dark" else CLASSIC)
    style = ttk.Style(root)

    if MODE == "classic":
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Accent.TButton")
        style.configure("Brand.TLabel", foreground=C["accent"], font=("Segoe UI", 12, "bold"))
        return

    style.theme_use("clam")
    c = C
    root.configure(bg=c["bg"])
    style.configure(".", background=c["bg"], foreground=c["text"], fieldbackground=c["field"],
                    bordercolor=c["border"], lightcolor=c["border"], darkcolor=c["border"],
                    troughcolor=c["surface"], selectbackground=c["accent"],
                    selectforeground=c["on_accent"], insertcolor=c["text"], font=FONT,
                    focuscolor=c["accent"])
    style.map(".", foreground=[("disabled", c["dim"])])

    style.configure("TFrame", background=c["bg"])
    style.configure("TLabel", background=c["bg"], foreground=c["text"])
    style.configure("Brand.TLabel", background=c["bg"], foreground=c["amber"],
                    font=("Segoe UI", 12, "bold"))
    style.configure("TLabelframe", background=c["bg"], bordercolor=c["border"],
                    lightcolor=c["bg"], darkcolor=c["bg"], relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=c["bg"], foreground=c["amber"],
                    font=FONT_BOLD)
    style.configure("TPanedwindow", background=c["bg"])
    style.configure("Sash", sashthickness=6, background=c["bg"])

    # buttons
    style.configure("TButton", background=c["field"], foreground=c["text"],
                    bordercolor=c["border"], lightcolor=c["field"], darkcolor=c["field"],
                    focusthickness=0, padding=(12, 5), relief="flat")
    style.map("TButton",
              background=[("disabled", c["surface"]), ("pressed", c["accent_down"]),
                          ("active", c["hover"])],
              bordercolor=[("active", c["accent"])],
              foreground=[("disabled", c["dim"])])
    style.configure("Accent.TButton", background=c["accent"], foreground=c["on_accent"],
                    bordercolor=c["accent"], lightcolor=c["accent"], darkcolor=c["accent"],
                    font=FONT_BOLD)
    style.map("Accent.TButton",
              background=[("disabled", c["field"]), ("pressed", c["accent_down"]),
                          ("active", c["accent_hover"])],
              foreground=[("disabled", c["dim"])],
              bordercolor=[("disabled", c["border"])])

    # inputs
    for name in ("TEntry", "TSpinbox", "TCombobox"):
        style.configure(name, fieldbackground=c["field"], background=c["field"],
                        foreground=c["text"], bordercolor=c["border"], lightcolor=c["field"],
                        darkcolor=c["field"], arrowcolor=c["muted"], insertcolor=c["text"],
                        padding=4, selectbackground=c["accent"],
                        selectforeground=c["on_accent"])
        style.map(name, bordercolor=[("focus", c["accent"])],
                  lightcolor=[("focus", c["accent"])],
                  fieldbackground=[("readonly", c["field"]), ("disabled", c["surface"])],
                  foreground=[("readonly", c["text"]), ("disabled", c["dim"])],
                  selectbackground=[("readonly", c["field"])],
                  selectforeground=[("readonly", c["text"])],
                  arrowcolor=[("active", c["text"])])
    root.option_add("*TCombobox*Listbox.background", c["field"])
    root.option_add("*TCombobox*Listbox.foreground", c["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", c["on_accent"])
    root.option_add("*TCombobox*Listbox.font", FONT)

    for name in ("TCheckbutton", "TRadiobutton"):
        style.configure(name, background=c["bg"], foreground=c["text"],
                        indicatorbackground=c["field"], indicatorforeground=c["on_accent"],
                        indicatormargin=(0, 0, 6, 0), focusthickness=0)
        style.map(name, background=[("active", c["bg"])],
                  indicatorbackground=[("selected", c["accent"]), ("active", c["hover"])])

    # lists
    style.configure("Treeview", background=c["surface"], fieldbackground=c["surface"],
                    foreground=c["text"], bordercolor=c["border"], lightcolor=c["surface"],
                    darkcolor=c["surface"], rowheight=26, font=FONT)
    style.map("Treeview", background=[("selected", c["select"])],
              foreground=[("selected", c["on_accent"])])
    style.configure("Treeview.Heading", background=c["field"], foreground=c["muted"],
                    bordercolor=c["border"], lightcolor=c["field"], darkcolor=c["field"],
                    relief="flat", font=FONT_BOLD, padding=(6, 4))
    style.map("Treeview.Heading", background=[("active", c["hover"])],
              foreground=[("active", c["text"])])

    for orient in ("Vertical", "Horizontal"):
        style.configure(f"{orient}.TScrollbar", background=c["field"], troughcolor=c["bg"],
                        bordercolor=c["bg"], lightcolor=c["field"], darkcolor=c["field"],
                        arrowcolor=c["muted"], gripcount=0)
        style.map(f"{orient}.TScrollbar", background=[("active", c["hover"])])
    style.configure("Horizontal.TProgressbar", background=c["accent"], troughcolor=c["field"],
                    bordercolor=c["border"], lightcolor=c["accent"], darkcolor=c["accent"])

    # classic tk widgets (log, settings text boxes, dialogs)
    root.option_add("*Toplevel.background", c["bg"])
    root.option_add("*Text.background", c["surface"])
    root.option_add("*Text.foreground", c["text"])
    root.option_add("*Text.insertBackground", c["text"])
    root.option_add("*Text.selectBackground", c["accent"])
    root.option_add("*Text.selectForeground", c["on_accent"])
    root.option_add("*Text.relief", "flat")
    root.option_add("*Text.highlightThickness", 1)
    root.option_add("*Text.highlightBackground", c["border"])
    root.option_add("*Text.highlightColor", c["accent"])
    root.option_add("*Label.background", c["bg"])
    root.option_add("*Label.foreground", c["text"])
    titlebar(root)


def titlebar(win):
    """Dark Windows title bar for this window (no-op on classic or non-Windows)."""
    if MODE != "dark" or sys.platform != "win32":
        return

    def go():
        try:
            win.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
            on = ctypes.c_int(1)
            for attr in (20, 19):   # DWMWA_USE_IMMERSIVE_DARK_MODE (new / old builds)
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                    break
        except Exception:  # noqa: BLE001 - purely cosmetic
            pass

    win.after(10, go)
