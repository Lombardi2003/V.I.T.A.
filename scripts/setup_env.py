"""Creates or completes .env, asking only for what the app needs: python scripts/setup_env.py [--update | --key FIELD]"""

import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


from pydantic_core import PydanticUndefined  # noqa: E402
from src.settings import ENV_PATH, Settings  # noqa: E402


SESSION_SECRET = "CHAINLIT_AUTH_SECRET"  # Signs the session of the app's user. Not a provider key: it is never asked for.


def _load_existing() -> dict[str, str]:
    """The values already in .env."""
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
    """A value with only its ends visible."""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _write_env(values: dict[str, str]) -> None:
    """Writes the values to .env."""
    ENV_PATH.write_text(
        "\n".join(f"{k}={v}" for k, v in values.items()) + "\n",
        encoding="utf-8",
    )


# Settings fields that hold a provider key: asked for only if a model in use needs them.
_KEY_FIELDS = {name for name in Settings.model_fields if name.endswith("_key") or "_key_" in name}


def _needed_key_fields() -> set[str]:
    """The key fields needed by the models in use (none for a local-only setup)."""
    from src.llm.factory import needed_key_fields
    return needed_key_fields()


def _relevant_fields(names: list[str], existing: dict[str, str]) -> list[str]:
    """The fields worth asking for: needed keys, and other fields with a default."""
    needed_keys = _needed_key_fields()
    relevant = []
    for name in names:
        if name in _KEY_FIELDS:
            if name in needed_keys:
                relevant.append(name)
            continue
        if Settings.model_fields[name].default is None:
            continue
        relevant.append(name)
    return relevant


def _prompt_fields(names: list[str], existing: dict[str, str]) -> dict[str, str]:
    """Asks for each field; an empty answer keeps the current value."""
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
    """Asks only for the missing values; called at startup."""
    existing = _load_existing()
    missing_fields = [name for name in Settings.model_fields if not existing.get(name.upper())]
    missing_fields = _relevant_fields(missing_fields, existing)

    if not missing_fields:
        return

    print("🔧 The .env file isn't complete yet, some values are needed:")
    updated = _prompt_fields(missing_fields, existing)
    _write_env(updated)
    print(f"✅ .env updated at {ENV_PATH}")


def ensure_session_secret() -> None:
    """Makes sure the secret that signs the user's session exists: generated once and kept in .env, so sessions survive a restart."""
    if os.environ.get(SESSION_SECRET):
        return
    values = _load_existing()
    if not values.get(SESSION_SECRET):
        values[SESSION_SECRET] = secrets.token_hex(32)
        _write_env(values)
    os.environ[SESSION_SECRET] = values[SESSION_SECRET]


def update_env() -> None:
    """Asks for every value again."""
    existing = _load_existing()
    fields = _relevant_fields(list(Settings.model_fields), existing)
    print("🔄 Updating .env: press Enter to keep a value unchanged, otherwise type a new one.")
    updated = _prompt_fields(fields, existing)
    _write_env(updated)
    print(f"✅ .env updated at {ENV_PATH}")


def set_key(name: str) -> None:
    """Asks for one provider key, even if no model in use needs it (a model of the benchmark, a second account)."""
    name = name.lower()
    if name not in _KEY_FIELDS:
        raise SystemExit(f"Unknown key '{name}'. Available: {', '.join(sorted(_KEY_FIELDS))}")
    _write_env(_prompt_fields([name], _load_existing()))
    print(f"✅ .env updated at {ENV_PATH}")


if __name__ == "__main__":
    if "--key" in sys.argv:
        following = sys.argv[sys.argv.index("--key") + 1:]
        set_key(following[0] if following else "")
    elif "--update" in sys.argv:
        update_env()
    else:
        ensure_env()
    print("✅ .env configuration complete.")
