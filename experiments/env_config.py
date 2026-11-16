"""Load simple dotenv assignments without running shell code or expanding values."""

import os
from pathlib import Path
import re
import shlex


def load_env(path: Path, environment=None):
    """Load KEY=value, optional export/quotes/comments; existing env takes priority."""
    target = os.environ if environment is None else environment
    if not path.is_file():
        return
    parsed = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"{path.name}:{number}: expected KEY=value")
        lexer = shlex.shlex(value, posix=True)
        lexer.whitespace_split = True
        lexer.commenters = "#"
        try:
            parts = list(lexer)
        except ValueError:
            raise ValueError(
                f"{path.name}:{number}: invalid quoting; use one line per value"
            ) from None
        if len(parts) > 1:
            raise ValueError(f"{path.name}:{number}: quote values containing spaces")
        parsed[key] = parts[0] if parts else ""
    for key, value in parsed.items():
        target.setdefault(key, value)
