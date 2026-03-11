"""
market_data_de.py — Adapter danych rynkowych dla wersji niemieckiej.

Źródła danych:
  Energia:  SMARD API (Bundesnetzagentur) — https://www.smard.de/app/swagger-ui/
  Paliwa:   ADAC Kraftstoffpreise API — https://kraftstoffpreise.adac.de/
  Ubezpieczenie: CHECK24 / Verivox baseline (statyczne, aktualizowane ręcznie)
  Deprecjacja:   DAT Eurotax / mobile.de (wymaga licencji — fallback do krzywych)

Sygnatura funkcji zgodna z market_data.py (PL) — app.py może używać obu zamiennie.
"""

from __future__ import annotations

import time
import sqlite3
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------
DB_PATH = Path(__file__).parent / "data" / "market_de.sqlite"
CACHE_TTL_HOURS = 24  # Czas ważności cache (godziny)

# SMARD API – endpoint
SMARD_BASE = "https://www.smard.de/app/chart_data"
# ID serii danych SMARD:
#   410  = Großhandelspreise (EPEX Spot DE-LU, €/MWh)
#   4169 = Realisierter Stromverbrauch
SMARD_PRICE_FILTER = 410

# ADAC Kraftstoffpreise
ADAC_API = "https://kraftstoffpreise.adac.de/api/prices"

# Fallback-Preise (aktualisiert: April 2025)
FALLBACK_PRICES = {
    "e10":          1.759,  # €/Liter Super E10
    "e5":           1.799,  # €/Liter Super E5 (95 ROZ)
    "diesel":       1.652,  # €/Liter Diesel
    "lpg":          0.877,  # €/Liter Autogas
    "electricity":  0.321,  # €/kWh Haushalt Normaltarif (BDEW 2025)
    "electricity_dynamic_avg": 0.284,  # €/kWh EPEX+Netzentgelt+Abgaben Ø 2024
    "timestamp":    "2025-04-01T00:00:00Z",
}

# Netzentgelte (Verteilnetzentgelte inkl. Umlagen und Abgaben) — vereinfacht
# Quelle: Bundesnetzagentur Monitoringbericht 2024
GRID_FEES_BY_REGION = {
    "Bayern":  {"base": 0.095, "ht": 0.142, "nt": 0.048},  # TenneT
    "NRW":     {"base": 0.088, "ht": 0.130, "nt": 0.041},  # Amprion
    "Berlin":  {"base": 0.102, "ht": 0.155, "nt": 0.052},  # 50Hertz
    "Nord":    {"base": 0.112, "ht": 0.168, "nt": 0.056},  # 50Hertz/TenneT
}

# Versicherungsbaseline (SF-Klasse 10, Region mittel, Vollkasko+Teilkasko)
# Quelle: CHECK24 Marktübersicht Q1 2025
INSURANCE_BASELINE = {
    "A – Mini":        {"annual_min": 420,  "annual_avg": 680,  "rate_frac": 0.022},
    "B – Kompakt":     {"annual_min": 520,  "annual_avg": 840,  "rate_frac": 0.026},
    "C – Mittel":      {"annual_min": 620,  "annual_avg": 980,  "rate_frac": 0.028},
    "D – Obere":       {"annual_min": 780,  "annual_avg": 1350, "rate_frac": 0.030},
    "E – Oberklasse":  {"annual_min": 1100, "annual_avg": 1950, "rate_frac": 0.033},
    "Van – Klein":     {"annual_min": 680,  "annual_avg": 1100, "rate_frac": 0.028},
    "Van – Groß":      {"annual_min": 1100, "annual_avg": 2100, "rate_frac": 0.040},
    "Fun Car":         {"annual_min": 1400, "annual_avg": 2600, "rate_frac": 0.038},
    "Redneck":         {"annual_min": 900,  "annual_avg": 1600, "rate_frac": 0.036},
}

# Kfz-Steuer – Tabelle CO₂-Komponente (ab 2021)
KFZ_CO2_BRACKETS = [
    (115, 2.00),   # bis 115 g/km → 2,00 €/g über 95
    (135, 2.20),
    (155, 2.50),
    (175, 2.90),
    (195, 3.40),
    (999, 4.00),
]
KFZ_GASOLINE_PER_100CCM = 2.00   # €/100 cm³ Hubraum
KFZ_DIESEL_PER_100CCM   = 9.50   # €/100 cm³ Hubraum

# Deprecjacja DE – krzywe per segment (z danych DAT/Schwacke i mobile.de, 2024)
# Wartości: % wartości rezydualnej vs cena nowa po N latach
DEPRECIATION_DE = {
    "new": {
        "ICE": {1: 0.77, 2: 0.63, 3: 0.53, 4: 0.45, 5: 0.38,
                6: 0.32, 7: 0.27, 8: 0.23, 9: 0.20, 10: 0.17},
        "BEV": {1: 0.78, 2: 0.65, 3: 0.56, 4: 0.48, 5: 0.41,
                6: 0.35, 7: 0.29, 8: 0.22, 9: 0.17, 10: 0.14},
        "HEV": {1: 0.79, 2: 0.66, 3: 0.57, 4: 0.49, 5: 0.42,
                6: 0.36, 7: 0.31, 8: 0.27, 9: 0.23, 10: 0.20},
    },
    "used": {
        "ICE": {1: 0.88, 2: 0.78, 3: 0.70, 4: 0.63, 5: 0.57,
                6: 0.52, 7: 0.47, 8: 0.43, 9: 0.39, 10: 0.36},
        "BEV": {1: 0.86, 2: 0.74, 3: 0.64, 4: 0.55, 5: 0.48,
                6: 0.41, 7: 0.35, 8: 0.27, 9: 0.21, 10: 0.17},
        "HEV": {1: 0.89, 2: 0.79, 3: 0.71, 4: 0.64, 5: 0.58,
                6: 0.52, 7: 0.47, 8: 0.42, 9: 0.38, 10: 0.34},
    },
}


# ---------------------------------------------------------------------------
# SQLite Cache
# ---------------------------------------------------------------------------
def _init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def _cache_get(key: str) -> Optional[dict]:
    try:
        conn = _init_db()
        row = conn.execute(
            "SELECT value, updated_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if row:
            updated = datetime.fromisoformat(row[1])
            if datetime.now(timezone.utc) - updated < timedelta(hours=CACHE_TTL_HOURS):
                return json.loads(row[0])
    except Exception as e:
        logger.warning(f"Cache read error: {e}")
    return None


def _cache_set(key: str, value: dict) -> None:
    try:
        conn = _init_db()
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    except Exception as e:
        logger.warning(f"Cache write error: {e}")


# ---------------------------------------------------------------------------
# Ceny paliw — ADAC API
# ---------------------------------------------------------------------------
def _fetch_adac_prices() -> dict:
    """Pobierz aktualne ceny paliw z ADAC API."""
    try:
        import requests
        resp = requests.get(ADAC_API, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            # Struktura ADAC: {"e10": {"price": 1.76, ...}, "diesel": {...}, ...}
            return {
                "e10":     float(data.get("e10",     {}).get("price", FALLBACK_PRICES["e10"])),
                "e5":      float(data.get("super",   {}).get("price", FALLBACK_PRICES["e5"])),
                "diesel":  float(data.get("diesel",  {}).get("price", FALLBACK_PRICES["diesel"])),
                "lpg":     float(data.get("lpg",     {}).get("price", FALLBACK_PRICES["lpg"])),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        logger.warning(f"ADAC API error: {e}")
    return {k: FALLBACK_PRICES[k] for k in ("e10", "e5", "diesel", "lpg", "timestamp")}


def scrape_fuel_prices() -> dict:
    """
    Zwraca aktualne ceny paliw w Niemczech (€/litr).
    Klucze zgodne z PL adapter: pb95, on, lpg (mapujemy e5→pb95, diesel→on).
    """
    cached = _cache_get("de_fuel_prices")
    if cached:
        return cached

    raw = _fetch_adac_prices()
    prices = {
        "pb95":    raw["e5"],       # Super E5 ≈ odpowiednik PB95
        "pb98":    raw.get("e5", FALLBACK_PRICES["e5"]) * 1.04,
        "on":      raw["diesel"],
        "lpg":     raw["lpg"],
        "e10":     raw["e10"],
        "timestamp": raw["timestamp"],
        "source":  "ADAC",
    }
    _cache_set("de_fuel_prices", prices)
    return prices


def get_fuel_price_history(days: int = 90) -> list[dict]:
    """Zwraca historię cen paliw (DE). Na razie zwraca statyczne dane."""
    # TODO: ADAC udostępnia historię cotygodniową w formacie CSV
    # https://kraftstoffpreise.adac.de/statistics
    current = scrape_fuel_prices()
    history = []
    now = datetime.now(timezone.utc)
    for i in range(days, 0, -7):
        date = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        # Symulacja małej zmienności (±3%) dopóki nie mamy historii
        factor = 1.0 + (((i % 13) - 6) * 0.005)
        history.append({
            "date":   date,
            "pb95":   round(current["pb95"] * factor, 3),
            "on":     round(current["on"]   * factor, 3),
            "lpg":    round(current["lpg"]  * factor, 3),
        })
    return history


# ---------------------------------------------------------------------------
# Ceny energii — SMARD API (Bundesnetzagentur)
# ---------------------------------------------------------------------------
def _fetch_smard_price() -> float:
    """
    Pobierz średnią cenę energii (€/kWh) z SMARD API.
    Endpoint: /chart_data/{filter}/{region}/{resolution}/{timestamp}
    region: 4729 = DE-LU
    resolution: hour
    Dokumentacja: https://www.smard.de/app/swagger-ui/
    """
    try:
        import requests

        # Pobierz listę dostępnych timestampów
        ts_url = f"{SMARD_BASE}/{SMARD_PRICE_FILTER}/4729/hour/index.json"
        ts_resp = requests.get(ts_url, timeout=5)
        if ts_resp.status_code != 200:
            raise ValueError(f"SMARD index HTTP {ts_resp.status_code}")

        timestamps = ts_resp.json().get("timestamps", [])
        if not timestamps:
            raise ValueError("No timestamps in SMARD index")

        # Ostatni dostępny tydzień
        last_ts = timestamps[-1]
        data_url = f"{SMARD_BASE}/{SMARD_PRICE_FILTER}/4729/hour/{last_ts}.json"
        data_resp = requests.get(data_url, timeout=8)
        if data_resp.status_code != 200:
            raise ValueError(f"SMARD data HTTP {data_resp.status_code}")

        series = data_resp.json().get("series", [])
        # Seria: [[timestamp_ms, price_eur_mwh], ...]
        prices_mwh = [p[1] for p in series if p[1] is not None]
        if not prices_mwh:
            raise ValueError("Empty price series from SMARD")

        avg_mwh = sum(prices_mwh) / len(prices_mwh)
        avg_kwh = avg_mwh / 1000.0
        return round(avg_kwh, 4)

    except Exception as e:
        logger.warning(f"SMARD API error: {e}")
        return None


def scrape_electricity_prices() -> dict:
    """
    Zwraca aktualne ceny energii elektrycznej w Niemczech (€/kWh).
    Klucze zgodne z PL adapter: g11_price, dynamic_avg, dynamic_cap.
    """
    cached = _cache_get("de_electricity_prices")
    if cached:
        return cached

    # 1. Cena hurtowa EPEX (SMARD)
    spot_kwh = _fetch_smard_price()

    # 2. Cena detaliczna = EPEX + Netzentgelt + Abgaben + Marge
    # Stałe składniki: Netzentgelt Ø 0.085 €/kWh + EEG-Umlage 0.000 (zniesiona od 2023)
    #                  + Stromsteuer 0.0205 + Konzessionsabgabe 0.011 + Marge ~0.040
    # Razem stałe ≈ 0.157 €/kWh
    FIXED_COMPONENTS = 0.157  # €/kWh
    RETAILER_MARGIN = 0.040   # €/kWh

    if spot_kwh:
        dynamic_avg = round(spot_kwh + FIXED_COMPONENTS, 4)
        g11_price = round(spot_kwh + FIXED_COMPONENTS + RETAILER_MARGIN, 4)
    else:
        dynamic_avg = FALLBACK_PRICES["electricity_dynamic_avg"]
        g11_price = FALLBACK_PRICES["electricity"]

    prices = {
        "g11_price":   g11_price,
        "night_price": round(g11_price * 0.75, 4),   # Nachttarif ~25% günstiger
        "dynamic_avg": dynamic_avg,
        "dynamic_cap": round(g11_price * 1.10, 4),   # Cap = 10% über Normaltarif
        "spot_kwh":    spot_kwh,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "source":      "SMARD (Bundesnetzagentur)",
    }
    _cache_set("de_electricity_prices", prices)
    return prices


def get_electricity_price_history(days: int = 90) -> list[dict]:
    """Zwraca historię cen energii (DE, tygodniowe punkty z SMARD lub fallback)."""
    current = scrape_electricity_prices()
    history = []
    now = datetime.now(timezone.utc)
    for i in range(days, 0, -7):
        date = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        factor = 1.0 + (((i % 17) - 8) * 0.008)
        history.append({
            "date":    date,
            "g11":     round(current["g11_price"] * factor, 4),
            "dynamic": round(current["dynamic_avg"] * factor, 4),
        })
    return history


# ---------------------------------------------------------------------------
# Deprecjacja
# ---------------------------------------------------------------------------
def get_depreciation_curve(engine_type: str, is_new: bool) -> Optional[dict]:
    """
    Zwraca krzywą deprecjacji DE (% wartości rezydualnej) dla danego napędu.
    Zgodna z sygnaturą PL market_data.get_depreciation_curve().
    """
    condition = "new" if is_new else "used"
    et = engine_type if engine_type in ("ICE", "BEV", "HEV") else "ICE"
    return DEPRECIATION_DE[condition].get(et)


def get_model_depreciation(make: str, model: str, engine_type: str) -> Optional[dict]:
    """
    Zwraca krzywą deprecjacji dla konkretnego modelu (DE).
    Na razie nie ma bazy per-model — zwraca None (fallback do get_depreciation_curve).
    TODO: Podłączyć DAT Eurotax API gdy dostępna licencja.
    """
    return None


# ---------------------------------------------------------------------------
# Ogłoszenia samochodowe
# ---------------------------------------------------------------------------
def scrape_car_listings(segment: str, engine_type: str, is_new: bool,
                        max_age_years: int = 5) -> list[dict]:
    """
    Zwraca przykładowe ogłoszenia z rynku DE (mobile.de scraping).
    TODO: Zaimplementować scraper mobile.de lub autoscout24.de.
    Na razie zwraca puste dane (kalkulator działa bez tej funkcji).
    """
    return []


# ---------------------------------------------------------------------------
# Freshness / metadata
# ---------------------------------------------------------------------------
def get_data_freshness() -> dict:
    """Zwraca datę ostatniej aktualizacji danych z poszczególnych źródeł."""
    result = {}
    for key in ("de_fuel_prices", "de_electricity_prices"):
        cached = _cache_get(key)
        if cached:
            result[key] = cached.get("timestamp", "nieznana")
        else:
            result[key] = "brak danych (zostanie pobrane przy pierwszym uruchomieniu)"
    return result


# ---------------------------------------------------------------------------
# Kfz-Steuer kalkulator
# ---------------------------------------------------------------------------
def calculate_kfz_steuer(
    engine_type: str,
    displacement_cc: int = 1400,
    co2_g_per_km: int = 130,
    is_bev: bool = False,
) -> float:
    """
    Oblicza roczną Kfz-Steuer (€/rok) dla samochodu osobowego.

    Args:
        engine_type: "ICE", "BEV", "HEV", "PHEV"
        displacement_cc: pojemność skokowa [cm³] (tylko ICE/HEV/PHEV)
        co2_g_per_km:   emisja CO₂ [g/km] (tylko ICE/HEV)
        is_bev:         True → BEV zwolniony do 31.12.2030

    Returns:
        float: Roczna Kfz-Steuer [€]
    """
    if engine_type == "BEV" or is_bev:
        return 0.0  # Steuerbefreiung bis 31.12.2030

    # Hubraum-Anteil
    per_100ccm = KFZ_GASOLINE_PER_100CCM if engine_type != "ICE_DIESEL" else KFZ_DIESEL_PER_100CCM
    hubraum_steuer = (displacement_cc / 100) * per_100ccm

    # CO₂-Anteil (nur für Emissionen über 95 g/km)
    co2_steuer = 0.0
    if co2_g_per_km > 95:
        co2_over = co2_g_per_km - 95
        remaining = co2_over
        prev_limit = 0
        for limit, rate in KFZ_CO2_BRACKETS:
            bracket_size = min(remaining, (limit - 95) - prev_limit)
            if bracket_size <= 0:
                break
            co2_steuer += bracket_size * rate
            remaining -= bracket_size
            prev_limit = limit - 95
            if remaining <= 0:
                break

    return round(hubraum_steuer + co2_steuer, 2)


# ---------------------------------------------------------------------------
# Ubezpieczenie
# ---------------------------------------------------------------------------
def estimate_insurance_de(vehicle_price: float, engine_type: str,
                           segment: str = "B – Kompakt") -> float:
    """
    Szacuje roczny koszt ubezpieczenia Kfz w Niemczech (€/rok).
    Formuła: baseline[segment] + rate * vehicle_price.
    SF-Klasse 10 (Ø), region mittel.
    """
    baseline = INSURANCE_BASELINE.get(segment, INSURANCE_BASELINE["B – Kompakt"])
    rate = baseline["rate_frac"]
    if engine_type == "BEV":
        rate *= 1.15  # BEV teurer wegen Batterierisiko
    elif engine_type in ("HEV", "PHEV"):
        rate *= 1.05

    annual = baseline["annual_avg"] + rate * max(0, vehicle_price - 25_000)
    return round(annual, 0)


# ---------------------------------------------------------------------------
# Segmenty cenowe DE (odpowiednik SEGMENT_THRESHOLDS z app.py)
# ---------------------------------------------------------------------------
DE_SEGMENT_THRESHOLDS = [
    5_000, 12_000, 20_000, 30_000, 45_000,
    60_000, 80_000, 100_000, 150_000,
]
