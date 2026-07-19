"""Create, complete, or update .env.

The list of required values isn't written here: it's read directly from
src.settings.Settings, so when a new field is added to the Settings class
in the future, this script will ask for it automatically, with no need to
keep a second file (e.g. .env.example) in sync by hand.

Usage:
    python scripts/setup_env.py            # asks only for missing values
    python scripts/setup_env.py --update   # asks for ALL values (e.g. expired key),
                                            # Enter to keep the current one unchanged
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# On Windows consoles (cp1252), printing emoji raises UnicodeEncodeError:
# force UTF-8 output when the stream allows it (e.g. not piped).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from pydantic_core import PydanticUndefined  # noqa: E402
from src.settings import ENV_PATH, Settings  # noqa: E402


def _load_existing() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    values = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _write_env(values: dict[str, str]) -> None:
    ENV_PATH.write_text(
        "\n".join(f"{k}={v}" for k, v in values.items()) + "\n",
        encoding="utf-8",
    )


def _prompt_fields(names: list[str], existing: dict[str, str]) -> dict[str, str]:
    updated = dict(existing)
    for name in names:
        env_key = name.upper()
        current = existing.get(env_key, "")
        field = Settings.model_fields[name]
        default = field.default if field.default is not PydanticUndefined else None

        if current:
            hint = f" (Enter to keep unchanged: {_mask(current)})"
        elif default is not None:
            hint = f" (Enter for default: {default})"
        else:
            hint = ""

        value = input(f"   Enter a value for {env_key}{hint}: ").strip()
        if value:
            updated[env_key] = value
        elif not current and default is not None:
            updated[env_key] = str(default)
    return updated


def ensure_env() -> None:
    """If any value required by Settings is missing, ask for it and update .env."""
    existing = _load_existing()
    missing_fields = [name for name in Settings.model_fields if not existing.get(name.upper())]

    if not missing_fields:
        return

    print("🔧 The .env file isn't complete yet, some values are needed:")
    updated = _prompt_fields(missing_fields, existing)
    _write_env(updated)
    print(f"✅ .env updated at {ENV_PATH}")


def update_env() -> None:
    """Ask for ALL values, to update existing keys (e.g. expired/revoked)."""
    existing = _load_existing()
    print("🔄 Updating .env: press Enter to keep a value unchanged, otherwise type a new one.")
    updated = _prompt_fields(list(Settings.model_fields), existing)
    _write_env(updated)
    print(f"✅ .env updated at {ENV_PATH}")


if __name__ == "__main__":
    if "--update" in sys.argv:
        update_env()
    else:
        ensure_env()
    print("✅ .env configuration complete.")
