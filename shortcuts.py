"""
Resolves a Windows .lnk shortcut to the real file/executable it points to.

Desktop icons are almost always .lnk shortcuts, not the actual .exe — this
lets "Add Application" work by dragging in a shortcut and still store the
real target path underneath.

Needs pywin32 (pip install pywin32). If it isn't installed, resolving a
.lnk raises a clear error; picking a plain .exe still works either way.
"""

import os

try:
    import win32com.client
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False


def resolve_shortcut(path: str) -> str:
    """If `path` is a .lnk shortcut, return the target it points to.
    Otherwise return `path` unchanged."""
    if not path.lower().endswith(".lnk"):
        return path
    if not PYWIN32_AVAILABLE:
        raise RuntimeError(
            "Reading .lnk shortcuts needs the 'pywin32' package. "
            "Run: pip install pywin32"
        )
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(path)
    target = shortcut.Targetpath
    return target if target else path


def display_name_for(path: str) -> str:
    """A friendly label for the list widget: just the file's base name."""
    base = os.path.basename(path)
    name, _ext = os.path.splitext(base)
    if name.casefold() == "msedge":
        return "Microsoft Edge"
    return name or base
