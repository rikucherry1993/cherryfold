"""cherryfold command-line entry.

  cherryfold                  open the current project's latest session
  cherryfold view [S] [-f]    render a session in this pane (-f / --follow tails)
  cherryfold follow [S]       split the terminal and follow the session beside you
  cherryfold list             list known sessions, newest first
  cherryfold config           print the config file path
  cherryfold clean            clear caches (__pycache__)
  cherryfold uninstall        remove the PATH symlink (--purge: also config)

S may be a .jsonl path or be omitted (then the newest session for the current
project, falling back to the newest overall, is used).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .parser import find_sessions, latest_session, load_session


def _resolve_path(arg: str | None) -> Path | None:
    if arg:
        p = Path(arg).expanduser()
        if p.is_file():
            return p
        print(f"No such session file: {p}", file=sys.stderr)
        return None
    p = latest_session(Path.cwd())
    if p is None:
        print("No session for this directory (or any parent). "
              "Run `cherryfold list --all` to see all sessions, or pass a path.",
              file=sys.stderr)
    return p


def cmd_view(args) -> int:
    path = _resolve_path(args.session)
    if path is None:
        return 1
    from .app import AgentView
    AgentView(load_session(path), follow=args.follow).run()
    return 0


def cmd_follow(args) -> int:
    from . import launcher
    path = _resolve_path(args.session)
    if path is None:
        return 1
    inner = [sys.executable, "-m", "cherryfold", "view", "--follow", str(path)]
    ok, msg = launcher.launch(inner)
    print(msg, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


def cmd_list(args) -> int:
    if args.all:
        sessions = find_sessions(all_projects=True)
    else:
        sessions = find_sessions(Path.cwd())
    if not sessions:
        if args.all:
            print("No sessions found.", file=sys.stderr)
        else:
            print("No sessions for this directory (or any parent). "
                  "Try: cherryfold list --all", file=sys.stderr)
        return 1
    for i, p in enumerate(sessions):
        print(f"{i:3}  {p}")
    return 0


def cmd_config(_args) -> int:
    from . import config
    print(config.CONFIG_FILE)
    return 0


def cmd_clean(_args) -> int:
    import shutil
    pkg = Path(__file__).resolve().parent
    removed = 0
    for pc in pkg.rglob("__pycache__"):
        shutil.rmtree(pc, ignore_errors=True)
        removed += 1
    print(f"Cleared {removed} __pycache__ dir(s).")
    return 0


def cmd_uninstall(args) -> int:
    import shutil
    from . import config
    for d in (Path.home() / ".local" / "bin", Path("/usr/local/bin")):
        link = d / "cherryfold"
        try:
            if link.is_symlink():
                link.unlink()
                print(f"Removed symlink {link}")
        except OSError:
            pass
    if args.purge:
        shutil.rmtree(config.CONFIG_DIR, ignore_errors=True)
        print(f"Removed config {config.CONFIG_DIR}")
    print("To remove the package itself: pip uninstall cherryfold")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cherryfold",
                                description="Read back Claude Code sessions.")
    sub = p.add_subparsers(dest="cmd")

    v = sub.add_parser("view", help="render a session in this pane")
    v.add_argument("session", nargs="?", help="session .jsonl (default: latest)")
    v.add_argument("-f", "--follow", action="store_true", help="tail live")
    v.set_defaults(func=cmd_view)

    fo = sub.add_parser("follow", help="split terminal and follow beside you")
    fo.add_argument("session", nargs="?", help="session .jsonl (default: latest)")
    fo.set_defaults(func=cmd_follow)

    ls = sub.add_parser("list", help="list sessions for this dir (--all: everywhere)")
    ls.add_argument("--all", action="store_true", help="list sessions across all projects")
    ls.set_defaults(func=cmd_list)
    sub.add_parser("clean", help="clear caches").set_defaults(func=cmd_clean)
    sub.add_parser("config", help="print config file path").set_defaults(func=cmd_config)
    un = sub.add_parser("uninstall", help="remove PATH symlink (--purge: config)")
    un.add_argument("--purge", action="store_true", help="also remove config")
    un.set_defaults(func=cmd_uninstall)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    known = ("view", "follow", "list", "clean", "config", "uninstall",
             "-h", "--help")
    if not argv:
        argv = ["view"]
    elif argv[0] not in known:
        argv = ["view"] + argv      # `cherryfold some.jsonl` -> view it
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
