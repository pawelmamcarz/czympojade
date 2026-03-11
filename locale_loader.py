"""
locale_loader.py — Ładowanie konfiguracji i stringów i18n.

Użycie:
    import os
    os.environ["APP_LANG"] = "de"   # lub "pl" (domyślnie)

    from locale_loader import cfg, t, LANG

    # Konfiguracja numeryczna:
    fuel_price = cfg("fuel.gasoline_per_liter")

    # Stringi UI:
    label = t("wizard.btn_next")
    msg   = t("analysis.road_normalization", city=0.4, rural=0.35, hwy=0.25)
"""

from __future__ import annotations

import os
import functools
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

# ---------------------------------------------------------------------------
# Ustawienie języka
# ---------------------------------------------------------------------------
LANG: str = os.environ.get("APP_LANG", "pl").lower().strip()
if LANG not in ("pl", "de"):
    LANG = "pl"

_LOCALE_DIR = Path(__file__).parent / "locale" / LANG


# ---------------------------------------------------------------------------
# Ładowanie YAML
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=None)
def _load_yaml(path: Path) -> dict:
    if not _HAS_YAML:
        raise ImportError("PyYAML nie jest zainstalowany. Uruchom: pip install pyyaml")
    if not path.exists():
        raise FileNotFoundError(f"Brak pliku locale: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _get_config() -> dict:
    return _load_yaml(_LOCALE_DIR / "config.yaml")


def _get_strings() -> dict:
    return _load_yaml(_LOCALE_DIR / "strings.yaml")


# ---------------------------------------------------------------------------
# Dostęp do konfiguracji numerycznej (cfg)
# ---------------------------------------------------------------------------
def cfg(key: str, default: Any = None) -> Any:
    """
    Pobierz wartość konfiguracyjną po kropkowej ścieżce klucza.

    Przykłady:
        cfg("fuel.gasoline_per_liter")      → 6.10 (PL) lub 1.76 (DE)
        cfg("insurance.base_annual")         → 1200 (PL) lub 480 (DE)
        cfg("pv.feed_in_rate")              → 0.52 (PL) lub 0.082 (DE)
        cfg("taxes.registration_fee_fixed") → 256 (PL) lub 27 (DE)
    """
    data = _get_config()
    parts = key.split(".")
    node = data
    for part in parts:
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return default
    return node


# ---------------------------------------------------------------------------
# Dostęp do stringów UI (t = translate)
# ---------------------------------------------------------------------------
def t(key: str, **kwargs) -> str:
    """
    Pobierz string UI po kropkowej ścieżce klucza i opcjonalnie sformatuj.

    Przykłady:
        t("app.title")
        t("wizard.progress", step=2, label="Twoje auto")
        t("analysis.road_normalization", city=0.4, rural=0.35, hwy=0.25)
    """
    strings = _get_strings()
    parts = key.split(".")
    node = strings
    for part in parts:
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return key  # Zwróć klucz jeśli nie znaleziono (bezpieczny fallback)

    if not isinstance(node, str):
        return str(node)

    try:
        return node.format(**kwargs) if kwargs else node
    except (KeyError, ValueError):
        return node


# ---------------------------------------------------------------------------
# Lista pomocnicza: pobierz listę ze strings
# ---------------------------------------------------------------------------
def tlist(key: str) -> list:
    """
    Pobierz listę stringów po kropkowej ścieżce klucza.

    Przykład:
        tlist("wizard.step_labels")  → ["Krok 0", "Krok 1", ...]
    """
    strings = _get_strings()
    parts = key.split(".")
    node = strings
    for part in parts:
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return []
    return node if isinstance(node, list) else []


# ---------------------------------------------------------------------------
# Waluta i formatowanie liczb
# ---------------------------------------------------------------------------
def fmt_currency(amount: float, decimals: int = 0) -> str:
    """Formatuje kwotę z symbolem waluty lokalnej."""
    symbol = cfg("currency_symbol", "zł")
    sep = cfg("thousands_sep", " ")
    dec = cfg("decimal_sep", ",")

    # Formatuj ze spacją tysięczną i przecinkiem dziesiętnym
    if decimals == 0:
        num_str = f"{amount:,.0f}"
    else:
        num_str = f"{amount:,.{decimals}f}"

    # Zastąp separator (Python używa . i ,)
    num_str = num_str.replace(",", "TSEP").replace(".", dec).replace("TSEP", sep)

    if LANG == "de":
        return f"{num_str} {symbol}"
    else:
        return f"{num_str} {symbol}"


def fmt_km(km: int) -> str:
    """Formatuje przebieg w km."""
    sep = cfg("thousands_sep", " ")
    s = f"{km:,}".replace(",", sep)
    return f"{s} km"


# ---------------------------------------------------------------------------
# Szybki dostęp do często używanych wartości
# ---------------------------------------------------------------------------
def fuel_gasoline() -> float:
    return cfg("fuel.gasoline_per_liter", 6.10)

def fuel_diesel() -> float:
    return cfg("fuel.diesel_per_liter", 6.30)

def fuel_lpg() -> float:
    return cfg("fuel.lpg_per_liter", 3.20)

def elec_base() -> float:
    return cfg("fuel.electricity_g11", cfg("fuel.electricity_base", 0.32))

def elec_dynamic_cap() -> float:
    return cfg("fuel.electricity_dynamic_cap", 0.42)

def vat_rate() -> float:
    return cfg("vat_rate", 0.23)

def currency_symbol() -> str:
    return cfg("currency_symbol", "zł")

def month_names() -> list:
    return tlist("month_names")
