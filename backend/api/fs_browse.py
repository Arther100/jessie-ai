"""
GET /fs/browse?path=...  — list directories on the machine running Jessie backend.
Used by Code Review folder picker (path must be readable by the backend process).
"""

from __future__ import annotations

import os
import string
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

fs_router = APIRouter(tags=["filesystem"])


def _default_roots() -> list[dict]:
    roots: list[dict] = []
    home = Path.home()
    if home.exists():
        roots.append({"name": "Home", "path": str(home)})
    cwd = Path.cwd().resolve()
    roots.append({"name": "Backend cwd", "path": str(cwd)})
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:\\")
            if drive.exists():
                roots.append({"name": f"{letter}:", "path": str(drive)})
    else:
        roots.append({"name": "/", "path": "/"})
    # de-dupe by path
    seen: set[str] = set()
    out: list[dict] = []
    for r in roots:
        key = r["path"].lower() if os.name == "nt" else r["path"]
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


@fs_router.get("/browse")
def browse(path: str = Query(default="")):
    """
    List immediate subdirectories of `path`.
    Empty path → suggested roots (home, drives, cwd).
    """
    if not path.strip():
        return {
            "path": "",
            "parent": None,
            "dirs": _default_roots(),
            "is_root_list": True,
        }

    try:
        target = Path(path).expanduser().resolve(strict=False)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid path: {exc}") from exc

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path does not exist: {target}")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {target}")

    parent = str(target.parent) if target.parent != target else None
    dirs: list[dict] = []
    try:
        entries = sorted(target.iterdir(), key=lambda p: p.name.lower())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=f"Permission denied: {target}") from exc

    for entry in entries:
        try:
            if not entry.is_dir():
                continue
            # skip hidden on unix; keep Windows system dirs visible but skip .git etc optionally
            name = entry.name
            if name.startswith(".") and name not in (".", ".."):
                continue
            dirs.append({"name": name, "path": str(entry.resolve())})
        except (PermissionError, OSError):
            continue

    return {
        "path": str(target),
        "parent": parent,
        "dirs": dirs,
        "is_root_list": False,
    }
