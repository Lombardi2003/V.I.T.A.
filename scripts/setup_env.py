"""Crea, completa o aggiorna .env.

L'elenco dei valori richiesti non e' scritto qui: viene letto direttamente
da src.settings.Settings, cosi' quando in futuro si aggiunge un nuovo campo
alla classe Settings, questo script lo chiedera' in automatico senza bisogno
di mantenere un secondo file (es. .env.example) allineato a mano.

Uso:
    python scripts/setup_env.py            # chiede solo i valori mancanti
    python scripts/setup_env.py --update   # richiede TUTTI i valori (es. chiave scaduta),
                                            # Invio per lasciare invariato quello attuale
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Su console Windows (cp1252) le stampe con emoji vanno in UnicodeEncodeError:
# forziamo l'output UTF-8 quando lo stream lo consente (es. non in pipe).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

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
        hint = f" (Invio per lasciare invariato: {_mask(current)})" if current else ""
        value = input(f"   Inserisci un valore per {env_key}{hint}: ").strip()
        if value:
            updated[env_key] = value
    return updated


def ensure_env() -> None:
    """Se manca qualche valore richiesto da Settings, lo chiede e aggiorna .env."""
    existing = _load_existing()
    missing_fields = [name for name in Settings.model_fields if not existing.get(name.upper())]

    if not missing_fields:
        return

    print("🔧 Il file .env non e' ancora completo, servono alcuni valori:")
    updated = _prompt_fields(missing_fields, existing)
    _write_env(updated)
    print(f"✅ .env aggiornato in {ENV_PATH}")


def update_env() -> None:
    """Richiede TUTTI i valori, per aggiornare chiavi esistenti (es. scadute/revocate)."""
    existing = _load_existing()
    print("🔄 Aggiornamento .env: premi Invio per lasciare invariato un valore, altrimenti scrivine uno nuovo.")
    updated = _prompt_fields(list(Settings.model_fields), existing)
    _write_env(updated)
    print(f"✅ .env aggiornato in {ENV_PATH}")


if __name__ == "__main__":
    if "--update" in sys.argv:
        update_env()
    else:
        ensure_env()
    print("✅ Configurazione .env completa.")
