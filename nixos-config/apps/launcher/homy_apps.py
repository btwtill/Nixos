"""homy-apps — install and remove launcher apps without a system rebuild.

    homy-apps list
    homy-apps install <folder | git URL>   copy/clone an app folder into
                                           ~/.local/share/homy/apps/<id>
    homy-apps remove <id>                  remove a sideloaded app

An app folder needs a manifest.json (see registry.py). Python apps can use
`homy-python` in their "exec" — the system's Python with PyQt6.

Apps packaged with Nix are installed with Nix's own per-user profile instead:
    nix profile install <flake>#<app>      /  nix profile remove <app>
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import registry


def _fail(msg: str):
    print(f"homy-apps: {msg}", file=sys.stderr)
    sys.exit(1)


def cmd_list():
    apps = registry.discover()
    if not apps:
        print("No apps installed.")
    for a in apps:
        print(f"{a.id:20s} {a.name:24s} {a.category:10s} {a.source}")


def cmd_install(src: str):
    with tempfile.TemporaryDirectory() as tmp:
        if src.startswith(("http://", "https://", "git@", "ssh://")):
            folder = Path(tmp) / "clone"
            r = subprocess.run(["git", "clone", "--depth", "1", src, str(folder)])
            if r.returncode != 0:
                _fail("git clone failed")
        else:
            folder = Path(src).expanduser().resolve()
            if not folder.is_dir():
                _fail(f"{src} is not a folder")

        app = registry.load_manifest(folder, "sideloaded")
        if app is None:
            _fail(f"no valid manifest.json in {src} (needs id, name, exec)")

        dest = registry.SIDELOAD_DIR / app.id
        if dest.exists():
            shutil.rmtree(dest)                      # reinstall = replace
        registry.SIDELOAD_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copytree(folder, dest, ignore=shutil.ignore_patterns(".git"))
    print(f"Installed {app.name} ({app.id}) — it appears in the app menu now.")


def cmd_remove(app_id: str):
    dest = registry.SIDELOAD_DIR / app_id
    if dest.is_dir():
        shutil.rmtree(dest)
        print(f"Removed {app_id}.")
        return
    app = next((a for a in registry.discover() if a.id == app_id), None)
    if app is None:
        _fail(f"no app with id {app_id}")
    if app.source == "nix-profile":
        _fail(f"{app_id} was installed with Nix — remove it with: nix profile remove <package>")
    _fail(f"{app_id} is part of the system config — remove it there and rebuild")


def main():
    args = sys.argv[1:]
    if args[:1] == ["list"]:
        cmd_list()
    elif len(args) == 2 and args[0] == "install":
        cmd_install(args[1])
    elif len(args) == 2 and args[0] == "remove":
        cmd_remove(args[1])
    else:
        print(__doc__)
        sys.exit(0 if args[:1] in (["-h"], ["--help"]) else 2)


if __name__ == "__main__":
    main()
