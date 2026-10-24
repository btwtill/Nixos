"""Finds launcher apps: one folder per app with a manifest.json.

    <apps dir>/<id>/manifest.json
    {
      "id":       "hello",                  # unique, [a-z0-9-]
      "name":     "Hello",                  # shown under the icon
      "exec":     "homy-python main.py",    # run from the app folder
      "icon":     "icon.svg",               # optional, relative to the folder
      "category": "Media",                  # optional: House / Media / System / …
      "background": false                   # optional: true = keep running while
                                            # hidden (otherwise it's paused)
    }

Apps are looked up in three places (later ones win on duplicate ids):
  system      /run/current-system/sw/share/homy/apps   — declared in the Nix config
  nix-profile ~/.nix-profile/share/homy/apps            — `nix profile install …`
  sideloaded  ~/.local/share/homy/apps                  — copied in with `homy-apps install`
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass
from pathlib import Path

HOME = Path.home()
SIDELOAD_DIR = HOME / ".local" / "share" / "homy" / "apps"

SOURCES: list[tuple[str, Path]] = [
    ("system",      Path("/run/current-system/sw/share/homy/apps")),
    ("nix-profile", HOME / ".nix-profile" / "share" / "homy" / "apps"),
    ("nix-profile", HOME / ".local" / "state" / "nix" / "profile" / "share" / "homy" / "apps"),
    ("sideloaded",  SIDELOAD_DIR),
]

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class App:
    id: str
    name: str
    exec: str
    icon: str          # absolute path, "" if none
    category: str
    source: str        # system / nix-profile / sideloaded
    dir: str           # folder the app is started in
    background: bool = False   # keep running while hidden (not paused by Qtile)


def load_manifest(folder: Path, source: str) -> App | None:
    try:
        data = json.loads((folder / "manifest.json").read_text())
    except (OSError, ValueError):
        return None
    app_id, name, cmd = data.get("id", ""), data.get("name", ""), data.get("exec", "")
    if not (isinstance(app_id, str) and ID_RE.match(app_id) and name and cmd):
        return None
    icon = data.get("icon") or ""
    return App(
        id=app_id,
        name=str(name),
        exec=str(cmd),
        icon=str((folder / icon).resolve()) if icon else "",
        category=str(data.get("category") or "Other"),
        source=source,
        dir=str(folder.resolve()),
        background=data.get("background") is True,
    )


def discover() -> list[App]:
    apps: dict[str, App] = {}
    for source, root in SOURCES:
        if not root.is_dir():
            continue
        for folder in sorted(root.iterdir()):
            app = load_manifest(folder, source) if folder.is_dir() else None
            if app:
                apps[app.id] = app
    return sorted(apps.values(), key=lambda a: a.name.lower())


def watched_dirs() -> list[str]:
    """Folders worth watching for installs/removals (only those that exist)."""
    return [str(root) for _, root in SOURCES if root.is_dir()]
