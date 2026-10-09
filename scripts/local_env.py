"""Load local model credentials without shell evaluation or dependencies."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_local_env(path=None):
    source = Path(path) if path else ROOT / ".env.local"
    if not source.exists():
        return
    for line_number, raw in enumerate(source.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not separator or not re.fullmatch(r"[A-Z_][A-Z_0-9]*", name):
            raise ValueError("Invalid environment entry at line %d" % line_number)
        if value[:1] in ("'", '"'):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError("Unclosed environment value at line %d" % line_number)
            value = value[1:-1]
        # Preserve explicit shell overrides; do not expand variables or commands.
        os.environ.setdefault(name, value)


def model_key():
    return os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
