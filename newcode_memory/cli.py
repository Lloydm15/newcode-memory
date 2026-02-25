"""
CLI installer for newcode-memory.

Usage:
    pip install newcode-memory
    newcode-memory install                          # defaults to localhost:4000
    newcode-memory install --server http://192.168.2.100:4000  # remote server
    newcode-memory uninstall                        # removes hooks and MCP config
"""

import argparse
import json
import os
import stat
import sys
from importlib.resources import files as pkg_files
from pathlib import Path
from shutil import copy2


def _claude_dir() -> Path:
    """~/.claude — Claude Code's config directory."""
    return Path.home() / ".claude"


def _hooks_dir() -> Path:
    """Where we install hook scripts."""
    d = _claude_dir() / "newcode-memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _package_hooks_dir() -> Path:
    """Path to hook scripts bundled in this package."""
    return Path(__file__).parent / "hooks"


def _mcp_server_path() -> str:
    """Absolute path to the MCP server script in this package."""
    return str(Path(__file__).parent / "mcp_server.py")


def _python_path() -> str:
    """Path to the Python interpreter running this package."""
    return sys.executable


def _merge_json(filepath: Path, patch: dict) -> dict:
    """Deep-merge patch into existing JSON file. Returns merged result."""
    existing = {}
    if filepath.exists():
        try:
            existing = json.loads(filepath.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}

    def _deep_merge(base, override):
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                _deep_merge(base[k], v)
            else:
                base[k] = v
        return base

    return _deep_merge(existing, patch)


def install(server_url: str):
    """Install hooks and MCP config into Claude Code."""
    hooks_dir = _hooks_dir()
    pkg_hooks = _package_hooks_dir()

    # Copy hook scripts
    for script_name in ["capture-prompt.sh", "auto-ingest.sh"]:
        src = pkg_hooks / script_name
        dst = hooks_dir / script_name
        copy2(src, dst)
        # Make executable
        dst.chmod(dst.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    capture_path = str(hooks_dir / "capture-prompt.sh")
    ingest_path = str(hooks_dir / "auto-ingest.sh")

    # -- Wire hooks into ~/.claude/settings.json --
    settings_path = _claude_dir() / "settings.json"
    hooks_config = {
        "hooks": {
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": capture_path,
                            "timeout": 5,
                        }
                    ]
                }
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"NEWCODE_SERVER_URL={server_url} {ingest_path}",
                            "timeout": 30,
                        }
                    ]
                }
            ],
        }
    }
    merged = _merge_json(settings_path, hooks_config)
    settings_path.write_text(json.dumps(merged, indent=2) + "\n")

    # -- Wire MCP server into ~/.claude/.mcp.json --
    mcp_path = _claude_dir() / ".mcp.json"
    mcp_config = {
        "mcpServers": {
            "newcode-memory": {
                "type": "stdio",
                "command": _python_path(),
                "args": [_mcp_server_path()],
                "env": {
                    "NEWCODE_SERVER_URL": server_url,
                },
            }
        }
    }
    merged_mcp = _merge_json(mcp_path, mcp_config)
    mcp_path.write_text(json.dumps(merged_mcp, indent=2) + "\n")

    print(f"newcode-memory installed.")
    print(f"  Server:  {server_url}")
    print(f"  Hooks:   {hooks_dir}")
    print(f"  MCP:     {mcp_path}")
    print(f"  Settings:{settings_path}")
    print()
    print("Restart Claude Code for changes to take effect.")


def uninstall():
    """Remove hooks and MCP config from Claude Code."""
    # Remove from settings.json
    settings_path = _claude_dir() / "settings.json"
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text())
            hooks = data.get("hooks", {})
            # Remove our hooks (check by path containing "newcode-memory")
            for event in ["UserPromptSubmit", "Stop"]:
                if event in hooks:
                    hooks[event] = [
                        h for h in hooks[event]
                        if not any(
                            "newcode-memory" in hook.get("command", "")
                            for hook in h.get("hooks", [])
                        )
                    ]
                    if not hooks[event]:
                        del hooks[event]
            if not hooks:
                data.pop("hooks", None)
            settings_path.write_text(json.dumps(data, indent=2) + "\n")
        except (json.JSONDecodeError, OSError):
            pass

    # Remove from .mcp.json
    mcp_path = _claude_dir() / ".mcp.json"
    if mcp_path.exists():
        try:
            data = json.loads(mcp_path.read_text())
            data.get("mcpServers", {}).pop("newcode-memory", None)
            mcp_path.write_text(json.dumps(data, indent=2) + "\n")
        except (json.JSONDecodeError, OSError):
            pass

    # Remove hook scripts
    hooks_dir = _claude_dir() / "newcode-memory"
    if hooks_dir.exists():
        for f in hooks_dir.iterdir():
            f.unlink()
        hooks_dir.rmdir()

    print("newcode-memory uninstalled.")
    print("Restart Claude Code for changes to take effect.")


def main():
    parser = argparse.ArgumentParser(
        prog="newcode-memory",
        description="Memory system for Claude Code",
    )
    sub = parser.add_subparsers(dest="command")

    install_cmd = sub.add_parser("install", help="Install hooks and MCP into Claude Code")
    install_cmd.add_argument(
        "--server",
        default="http://localhost:4000",
        help="URL of the newcode server (default: http://localhost:4000)",
    )

    sub.add_parser("uninstall", help="Remove hooks and MCP from Claude Code")

    args = parser.parse_args()

    if args.command == "install":
        install(args.server)
    elif args.command == "uninstall":
        uninstall()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
