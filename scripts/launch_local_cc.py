"""Launch the local-Qwen Claude Code entry with the current persona appended.

Use --dry-run to generate/check the persona cache and show the command without
starting Claude. All other arguments are passed through. A leading -- separates
launcher flags from Claude flags. The .cmd entry owns endpoint/model settings.
"""

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
from persona_loader import DEFAULT_SOURCE_DIR, load_persona, render_persona


CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"


def persona_file() -> Path:
    """Generate the current local prompt, never reuse a mismatching cache."""
    content = load_persona(DEFAULT_SOURCE_DIR)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    prompt = render_persona(content, "local", DEFAULT_SOURCE_DIR) + "\n"
    path = CACHE_DIR / f"persona-local-{digest}.txt"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(prompt)
    except FileExistsError:
        if path.read_text(encoding="utf-8") != prompt:
            raise ValueError("persona cache mismatch")
    return path


def claude_executable() -> str:
    """Resolve the native CLI so Windows arguments need no shell interpolation."""
    found = shutil.which("claude")
    if not found:
        raise ValueError("Claude executable not found")
    path = Path(found)
    if os.name == "nt" and path.suffix.lower() in {".cmd", ".bat", ".ps1"}:
        native = path.parent / "node_modules/@anthropic-ai/claude-code/bin/claude.exe"
        if native.is_file():
            return str(native)
        found = shutil.which("claude.exe")
        if not found:
            raise ValueError("native Claude executable not found")
    return str(found)


def safe_command(argv: list[str]) -> str:
    """Avoid echoing credential-valued environment variables during dry runs."""
    command = subprocess.list2cmdline(argv)
    for name, value in os.environ.items():
        if re.search(r"key|token|secret|authorization|password", name, re.I) and value:
            command = command.replace(value, "[REDACTED]")
    return command


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    dry_run = False
    forwarded = []
    parsing_launcher = True
    for arg in args:
        if parsing_launcher and arg == "--":
            parsing_launcher = False
        elif parsing_launcher and arg == "--dry-run":
            dry_run = True
        else:
            forwarded.append(arg)
    try:
        prompt_path = persona_file()
        command = [claude_executable(), "--append-system-prompt-file", str(prompt_path), *forwarded]
        if dry_run:
            print("DRY RUN: " + safe_command(command))
            return 0
        return subprocess.run(command, check=False).returncode
    except (OSError, UnicodeError, ValueError):
        print("launch_local_cc: 人格、缓存或 Claude 路径无效，未启动。", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
