"""
market_data.py — Supabase/SQLite storage + scraping danych publicznych dla CzymPojade.

Backend: Supabase (primary, persistent) → SQLite (fallback, local/ephemeral).
Gdy conn jest podany explicite (testy), zawsze SQLite.
Gdy conn=None, próbuje Supabase, potem SQLite.

Zbiera:
- Ceny paliw (e-petrol.pl) — dziennie
- Ceny prądu RDN (PSE.pl) — dziennie
- Ogłoszenia aut (OtoMoto.pl) — dziennie, max 5 modeli/sesję

Fallback do hardcoded wartości gdy DB pusty lub scraping padnie.
"""

import os
import sqlite3
import re
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_SCRAPING = True
except ImportError:
    HAS_SCRAPING = False

try:
    from sklearn.ensemble import GradientBoostingRegressor
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

try:
    from supabase import create_client
    HAS_SUPABASE_LIB = True
except ImportError:
    HAS_SUPABASE_LIB = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supabase (primary backend — persistent PostgreSQL)
# ---------------------------------------------------------------------------

_sb_client = None
_sb_checked = False


def _get_supabase():
    """Returns Supabase client singleton, or None if unavailable."""
    global _sb_client, _sb_checked
    if _sb_checked:
        return _sb_client
    _sb_checked = True

    if not HAS_SUPABASE_LIB:
        return None

    url = key = None
    try:
        import streamlit as st
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
    except Exception:
        pass

    if not url:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        return None

    try:
        _sb_client = create_client(url, key)
        logger.info("Supabase connected: %s", url[:30])
        return _sb_client
    except Exception as e:
        logger.warning("Supabase init failed: %s", e)
        return None


def _sb_already_scraped(sb, source: str, today: str) -> bool:
    """Check scrape_meta in Supabase."""
    try:
        res = sb.table("scrape_meta").select("last_run") \
            .eq("source", source).eq("last_status", "ok").execute()
        if res.data and res.data[0]["last_run"][:10] == today:
            return True
    except Exception:
        pass
    return False


def _sb_log_scrape(sb, source: str, status: str, rows: int = 0, error: str | None = None):
    """Log scrape result to Supabase."""
    try:
        sb.table("scrape_meta").upsert({
            "source": source,
            "last_run": datetime.now().isoformat(),
            "last_status": status,
            "rows_added": rows,
            "error_msg": error,
        }).execute()
    except Exception as e:
        logger.warning("Supabase log_scrape failed: %s", e)


# ---------------------------------------------------------------------------
# SQLite (fallback backend — local, ephemeral on Cloud)
# ---------------------------------------------------------------------------

DB_DIR = Path(__file__).parent / "data"
DB_PATH = DB_DIR / "czympojade.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scrape_meta (
    source      TEXT PRIMARY KEY,
    last_run    TEXT NOT NULL,
    last_status TEXT NOT NULL,
    rows_added  INTEGER DEFAULT 0,
    error_msg   TEXT
);

CREATE TABLE IF NOT EXISTS fuel_prices (
    date        TEXT NOT NULL,
    fuel_type   TEXT NOT NULL,
    price_zl    REAL NOT NULL,
    PRIMARY KEY (date, fuel_type)
);

CREATE TABLE IF NOT EXISTS electricity_prices (
    date            TEXT NOT NULL,
    price_type      TEXT NOT NULL,
    price_zl_kwh    REAL NOT NULL,
    PRIMARY KEY (date, price_type)
);

CREATE TABLE IF NOT EXISTS car_listings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scraped_date    TEXT NOT NULL,
    make            TEXT NOT NULL,
    model           TEXT NOT NULL,
    year            INTEGER NOT NULL,
    mileage_km      INTEGER,
    price_zl        INTEGER NOT NULL,
    engine_type     TEXT NOT NULL,
    original_price  INTEGER,
    age_years       REAL,
    rv_pct          REAL
);

CREATE INDEX IF NOT EXISTS idx_fuel_date ON fuel_prices(date);
CREATE INDEX IF NOT EXISTS idx_car_engine ON car_listings(engine_type);
CREATE INDEX IF NOT EXISTS idx_car_make_model ON car_listings(make, model);
"""

FUEL_DEFAULTS = {"pb95": 6.50, "on": 6.40, "lpg": 3.20, "source": "domyslne"}

_HEADERS = {
    "User-Agent": "CzymPojade-TCO-Calculator/1.0",
    "Accept-Language": "pl-PL,pl;q=0.9",
}


def get_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Returns SQLite connection, creating DB + tables if needed."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def _already_scraped(conn: sqlite3.Connection, source: str, today: str) -> bool:
    row = conn.execute(
        "SELECT last_run FROM scrape_meta WHERE source = ? AND last_status = 'ok'",
        (source,),
    ).fetchone()
    if row is None:
        return False
    return row["last_run"][:10] == today


def _log_scrape(conn, source, status, rows=0, error=None):
    conn.execute(
        "INSERT OR REPLACE INTO scrape_meta (source, last_run, last_status, rows_added, error_msg) "
        "VALUES (?, ?, ?, ?, ?)",
        (source, datetime.now().isoformat(), status, rows, error),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# 1. Fuel prices (e-petrol.pl)
# ---------------------------------------------------------------------------

def _fetch_from_epetrol() -> dict | None:
    """Scrapes e-petrol.pl. Returns {'pb95': float, 'on': float, 'lpg': float} or None."""
    if not HAS_SCRAPING:
        return None
    try:
        resp = requests.get(
            "https://www.e-petrol.pl/notowania/rynkowe/ceny-stacji-paliw",
            timeout=8,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "pl-PL,pl;q=0.9",
            },
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        prices = {}
        text = soup.get_text()
        for fuel, key in [("Pb95", "pb95"), ("Pb 95", "pb95"),
                          ("ON", "on"), ("Diesel", "on"),
                          ("LPG", "lpg")]:
            pattern = rf'{fuel}\s*[\s\-\u2013:]*\s*(\d+[,\.]\d{{2}})'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                prices[key] = float(match.group(1).replace(",", "."))
        if len(prices) < 2:
            for row in soup.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).lower()
                    for fuel, key in [("pb95", "pb95"), ("pb 95", "pb95"),
                                      ("diesel", "on"), (" on", "on"),
                                      ("lpg", "lpg")]:
                        if fuel in label:
                            try:
                                val = cells[1].get_text(strip=True).replace(",", ".").replace("zl", "").strip()
                                prices[key] = float(val)
                            except (ValueError, IndexError):
                                pass
        return prices if prices else None
    except Exception as e:
        logger.warning("e-petrol scrape failed: %s", e)
        return None


def scrape_fuel_prices(force: bool = False, conn: sqlite3.Connection | None = None) -> dict:
    """Scrapes fuel prices, stores in DB, returns current prices."""
    today = datetime.now().strftime("%Y-%m-%d")

    # --- Supabase path ---
    if conn is None:
        sb = _get_supabase()
        if sb:
            try:
                if not force and _sb_already_scraped(sb, "epetrol", today):
                    return _load_latest_fuel()

                prices = _fetch_from_epetrol()
                if prices:
                    rows = [{"date": today, "fuel_type": ft, "price_zl": p}
                            for ft, p in prices.items()]
                    sb.table("fuel_prices").upsert(rows).execute()
                    _sb_log_scrape(sb, "epetrol", "ok", len(prices))
                    return {**FUEL_DEFAULTS, **prices, "source": "e-petrol.pl"}

                _sb_log_scrape(sb, "epetrol", "error", error="no data parsed")
                stored = _load_latest_fuel()
                return stored if stored["source"] != "domyslne" else FUEL_DEFAULTS
            except Exception as e:
                logger.warning("Supabase scrape_fuel failed: %s", e)

    # --- SQLite path ---
    _conn = conn or get_db()

    if not force and _already_scraped(_conn, "epetrol", today):
        return _load_latest_fuel(_conn)

    prices = _fetch_from_epetrol()
    if prices:
        for fuel_type, price in prices.items():
            _conn.execute(
                "INSERT OR REPLACE INTO fuel_prices (date, fuel_type, price_zl) VALUES (?, ?, ?)",
                (today, fuel_type, price),
            )
        _log_scrape(_conn, "epetrol", "ok", len(prices))
        return {**FUEL_DEFAULTS, **prices, "source": "e-petrol.pl"}

    _log_scrape(_conn, "epetrol", "error", error="no data parsed")
    stored = _load_latest_fuel(_conn)
    return stored if stored["source"] != "domyslne" else FUEL_DEFAULTS


def _load_latest_fuel(conn: sqlite3.Connection | None = None) -> dict:
    """Loads most recent fuel prices from DB."""
    # --- Supabase path ---
    if conn is None:
        sb = _get_supabase()
        if sb:
            try:
                res = sb.table("fuel_prices").select("fuel_type, price_zl") \
                    .order("date", desc=True).limit(3).execute()
                if res.data:
                    result = dict(FUEL_DEFAULTS)
                    for r in res.data:
                        result[r["fuel_type"]] = r["price_zl"]
                    result["source"] = "e-petrol.pl (supabase)"
                    return result
            except Exception as e:
                logger.warning("Supabase load_latest_fuel failed: %s", e)

    # --- SQLite path ---
    _conn = conn or get_db()
    rows = _conn.execute(
        "SELECT fuel_type, price_zl FROM fuel_prices "
        "WHERE date = (SELECT MAX(date) FROM fuel_prices)"
    ).fetchall()
    if not rows:
        return dict(FUEL_DEFAULTS)
    result = dict(FUEL_DEFAULTS)
    for r in rows:
        result[r["fuel_type"]] = r["price_zl"]
    result["source"] = "e-petrol.pl (cached)"
    return result


def get_fuel_price_history(days: int = 90, conn: sqlite3.Connection | None = None) -> pd.DataFrame:
    """Returns fuel price history as pivoted DataFrame (date × fuel_type)."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # --- Supabase path ---
    if conn is None:
        sb = _get_supabase()
        if sb:
            try:
                res = sb.table("fuel_prices").select("date, fuel_type, price_zl") \
                    .gte("date", cutoff).order("date").execute()
                if res.data:
                    df = pd.DataFrame(res.data)
                    return df.pivot(index="date", columns="fuel_type", values="price_zl")
                return pd.DataFrame()
            except Exception as e:
                logger.warning("Supabase fuel_history failed: %s", e)

    # --- SQLite path ---
    _conn = conn or get_db()
    rows = _conn.execute(
        "SELECT date, fuel_type, price_zl FROM fuel_prices WHERE date >= ? ORDER BY date",
        (cutoff,),
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date", "fuel_type", "price_zl"])
    return df.pivot(index="date", columns="fuel_type", values="price_zl")


# ---------------------------------------------------------------------------
# 2. Electricity prices (PSE.pl — RDN spot)
# ---------------------------------------------------------------------------

def _fetch_pse_rdn(date_str: str | None = None) -> dict | None:
    """Fetches daily RDN spot prices from PSE.pl.

    PSE publishes fixing prices for the Day-Ahead Market (RDN).
    Returns {'rdn_avg': float, 'rdn_min': float, 'rdn_max': float} in PLN/kWh.
    """
    if not HAS_SCRAPING:
        return None
    target_date = date_str or datetime.now().strftime("%Y%m%d")
    try:
        # PSE RDN data endpoint
        url = (
            "https://www.pse.pl/dane-systemowe/funkcjonowanie-rb/"
            "raporty-dobowe-z-rb/podstawowe-wskazniki-cenowe-rb"
        )
        resp = requests.get(url, timeout=10, headers=_HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # PSE publishes prices in PLN/MWh in tables
        prices_mwh = []
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 2:
                for cell in cells:
                    txt = cell.get_text(strip=True).replace(",", ".").replace(" ", "")
                    try:
                        val = float(txt)
                        if 50 < val < 2000:  # reasonable PLN/MWh range
                            prices_mwh.append(val)
                    except ValueError:
                        pass

        if not prices_mwh:
            return None

        avg_mwh = sum(prices_mwh) / len(prices_mwh)
        return {
            "rdn_avg": round(avg_mwh / 1000, 4),  # PLN/MWh → PLN/kWh
            "rdn_min": round(min(prices_mwh) / 1000, 4),
            "rdn_max": round(max(prices_mwh) / 1000, 4),
        }
    except Exception as e:
        logger.warning("PSE scrape failed: %s", e)
        return None


def scrape_electricity_prices(force: bool = False, conn: sqlite3.Connection | None = None) -> dict | None:
    """Scrapes PSE RDN prices, stores in DB."""
    today = datetime.now().strftime("%Y-%m-%d")

    # --- Supabase path ---
    if conn is None:
        sb = _get_supabase()
        if sb:
            try:
                if not force and _sb_already_scraped(sb, "pse", today):
                    return _load_latest_electricity()

                data = _fetch_pse_rdn()
                if data:
                    rows = [{"date": today, "price_type": pt, "price_zl_kwh": v}
                            for pt, v in data.items()]
                    sb.table("electricity_prices").upsert(rows).execute()
                    _sb_log_scrape(sb, "pse", "ok", len(data))
                    return data

                _sb_log_scrape(sb, "pse", "error", error="no data parsed")
                return _load_latest_electricity()
            except Exception as e:
                logger.warning("Supabase scrape_electricity failed: %s", e)

    # --- SQLite path ---
    _conn = conn or get_db()

    if not force and _already_scraped(_conn, "pse", today):
        return _load_latest_electricity(_conn)

    data = _fetch_pse_rdn()
    if data:
        for price_type, val in data.items():
            _conn.execute(
                "INSERT OR REPLACE INTO electricity_prices (date, price_type, price_zl_kwh) "
                "VALUES (?, ?, ?)",
                (today, price_type, val),
            )
        _log_scrape(_conn, "pse", "ok", len(data))
        return data

    _log_scrape(_conn, "pse", "error", error="no data parsed")
    return _load_latest_electricity(_conn)


def _load_latest_electricity(conn: sqlite3.Connection | None = None) -> dict | None:
    """Loads most recent electricity prices from DB."""
    # --- Supabase path ---
    if conn is None:
        sb = _get_supabase()
        if sb:
            try:
                res = sb.table("electricity_prices").select("price_type, price_zl_kwh") \
                    .order("date", desc=True).limit(3).execute()
                if res.data:
                    return {r["price_type"]: r["price_zl_kwh"] for r in res.data}
            except Exception as e:
                logger.warning("Supabase load_latest_electricity failed: %s", e)

    # --- SQLite path ---
    _conn = conn or get_db()
    rows = _conn.execute(
        "SELECT price_type, price_zl_kwh FROM electricity_prices "
        "WHERE date = (SELECT MAX(date) FROM electricity_prices)"
    ).fetchall()
    if not rows:
        return None
    return {r["price_type"]: r["price_zl_kwh"] for r in rows}


def get_electricity_price_history(days: int = 90, conn: sqlite3.Connection | None = None) -> pd.DataFrame:
    """Returns electricity price history as pivoted DataFrame."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # --- Supabase path ---
    if conn is None:
        sb = _get_supabase()
        if sb:
            try:
                res = sb.table("electricity_prices").select("date, price_type, price_zl_kwh") \
                    .gte("date", cutoff).order("date").execute()
                if res.data:
                    df = pd.DataFrame(res.data)
                    return df.pivot(index="date", columns="price_type", values="price_zl_kwh")
                return pd.DataFrame()
            except Exception as e:
                logger.warning("Supabase electricity_history failed: %s", e)

    # --- SQLite path ---
    _conn = conn or get_db()
    rows = _conn.execute(
        "SELECT date, price_type, price_zl_kwh FROM electricity_prices WHERE date >= ? ORDER BY date",
        (cutoff,),
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date", "price_type", "price_zl_kwh"])
    return df.pivot(index="date", columns="price_type", values="price_zl_kwh")


# ---------------------------------------------------------------------------
# 3. Car listings (OtoMoto.pl)
# ---------------------------------------------------------------------------

# Known MSRPs from app.py presets — used to compute rv_pct
KNOWN_MSRP = {
    # BEV
    ("Tesla", "Model Y"): 189_000,
    ("Tesla", "Model 3"): 175_000,
    ("BYD", "Atto 3"): 145_000,
    ("BYD", "Seal"): 185_000,
    ("VW", "ID.4"): 195_000,
    ("VW", "ID.3"): 165_000,
    ("Hyundai", "Ioniq 5"): 215_000,
    ("Skoda", "Enyaq"): 199_000,
    ("MG", "MG4"): 125_000,
    ("Nissan", "Leaf"): 135_000,
    ("BMW", "iX1"): 220_000,
    ("Lexus", "UX 300e"): 195_000,
    ("Renault", "Zoe"): 135_000,
    # ICE
    ("Toyota", "Corolla"): 135_000,
    ("Toyota", "Yaris Cross"): 115_000,
    ("Toyota", "RAV4"): 185_000,
    ("VW", "Golf"): 145_000,
    ("Skoda", "Octavia"): 140_000,
    ("Hyundai", "Tucson"): 155_000,
    ("Kia", "Sportage"): 150_000,
    ("Dacia", "Duster"): 85_000,
    ("BMW", "320i"): 210_000,
    ("Opel", "Astra"): 115_000,
    ("Ford", "Focus"): 105_000,
}

# Models to scrape (make, model_slug for URL, engine_type)
TRACKED_MODELS = [
    {"make": "Tesla", "model": "Model Y", "slug": "tesla/model-y", "engine": "BEV"},
    {"make": "Tesla", "model": "Model 3", "slug": "tesla/model-3", "engine": "BEV"},
    {"make": "VW", "model": "ID.4", "slug": "volkswagen/id.4", "engine": "BEV"},
    {"make": "VW", "model": "ID.3", "slug": "volkswagen/id.3", "engine": "BEV"},
    {"make": "Hyundai", "model": "Ioniq 5", "slug": "hyundai/ioniq-5", "engine": "BEV"},
    {"make": "Skoda", "model": "Enyaq", "slug": "skoda/enyaq", "engine": "BEV"},
    {"make": "BMW", "model": "iX1", "slug": "bmw/ix1", "engine": "BEV"},
    {"make": "Toyota", "model": "Corolla", "slug": "toyota/corolla", "engine": "ICE"},
    {"make": "Toyota", "model": "RAV4", "slug": "toyota/rav4", "engine": "ICE"},
    {"make": "VW", "model": "Golf", "slug": "volkswagen/golf", "engine": "ICE"},
    {"make": "Skoda", "model": "Octavia", "slug": "skoda/octavia", "engine": "ICE"},
    {"make": "Hyundai", "model": "Tucson", "slug": "hyundai/tucson", "engine": "ICE"},
    {"make": "Kia", "model": "Sportage", "slug": "kia/sportage", "engine": "ICE"},
    {"make": "BMW", "model": "320i", "slug": "bmw/seria-3", "engine": "ICE"},
]


def _fetch_otomoto_listings(slug: str, engine_type: str) -> list[dict]:
    """Parses OtoMoto search results for a model. Returns list of listings."""
    if not HAS_SCRAPING:
        return []
    try:
        url = f"https://www.otomoto.pl/osobowe/{slug}"
        params = {}
        if engine_type == "BEV":
            params["search[filter_enum_fuel_type]"] = "electric"

        resp = requests.get(url, params=params, timeout=12, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "pl-PL,pl;q=0.9",
        })
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        results = []
        # OtoMoto renders listings as article elements
        for card in soup.select("article"):
            try:
                # Price
                price_el = card.select_one("[data-testid='ad-price']")
                if not price_el:
                    price_el = card.find("h3")
                if not price_el:
                    continue
                price_text = re.sub(r'[^\d]', '', price_el.get_text())
                if not price_text:
                    continue
                price = int(price_text)
                if price < 5000 or price > 2_000_000:
                    continue

                # Year + mileage from dd elements or spans
                year = None
                mileage = None
                for dd in card.find_all(["dd", "span", "li"]):
                    txt = dd.get_text(strip=True)
                    # Year: 4-digit number between 2010-2026
                    if not year:
                        yr_match = re.search(r'\b(20[12]\d)\b', txt)
                        if yr_match:
                            year = int(yr_match.group(1))
                    # Mileage: number followed by "km"
                    if not mileage:
                        km_match = re.search(r'([\d\s]+)\s*km', txt, re.IGNORECASE)
                        if km_match:
                            mileage = int(re.sub(r'\s', '', km_match.group(1)))

                if year and price:
                    results.append({
                        "year": year,
                        "mileage_km": mileage,
                        "price_zl": price,
                    })
            except (ValueError, AttributeError):
                continue

        return results[:30]  # max 30 per page
    except Exception as e:
        logger.warning("OtoMoto scrape failed for %s: %s", slug, e)
        return []


def scrape_car_listings(
    force: bool = False,
    max_models: int = 5,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Scrapes OtoMoto for tracked models. Returns count of new listings."""
    today = datetime.now().strftime("%Y-%m-%d")
    current_year = datetime.now().year
    total_added = 0

    # --- Supabase path ---
    if conn is None:
        sb = _get_supabase()
        if sb:
            try:
                for info in TRACKED_MODELS[:max_models]:
                    source_key = f"otomoto_{info['make']}_{info['model']}"
                    if not force and _sb_already_scraped(sb, source_key, today):
                        continue

                    time.sleep(2)  # rate limiting
                    listings = _fetch_otomoto_listings(info["slug"], info["engine"])
                    msrp = KNOWN_MSRP.get((info["make"], info["model"]))

                    rows = []
                    for listing in listings:
                        age = current_year - listing["year"]
                        rv = listing["price_zl"] / msrp if msrp and msrp > 0 else None
                        rows.append({
                            "scraped_date": today,
                            "make": info["make"],
                            "model": info["model"],
                            "year": listing["year"],
                            "mileage_km": listing.get("mileage_km"),
                            "price_zl": listing["price_zl"],
                            "engine_type": info["engine"],
                            "original_price": msrp,
                            "age_years": age,
                            "rv_pct": rv,
                        })

                    if rows:
                        sb.table("car_listings").insert(rows).execute()
                    _sb_log_scrape(sb, source_key, "ok", len(rows))
                    total_added += len(rows)

                return total_added
            except Exception as e:
                logger.warning("Supabase scrape_car_listings failed: %s", e)

    # --- SQLite path ---
    _conn = conn or get_db()

    for info in TRACKED_MODELS[:max_models]:
        source_key = f"otomoto_{info['make']}_{info['model']}"
        if not force and _already_scraped(_conn, source_key, today):
            continue

        time.sleep(2)  # rate limiting

        listings = _fetch_otomoto_listings(info["slug"], info["engine"])
        added = 0
        msrp = KNOWN_MSRP.get((info["make"], info["model"]))

        for listing in listings:
            age = current_year - listing["year"]
            rv = listing["price_zl"] / msrp if msrp and msrp > 0 else None

            _conn.execute(
                "INSERT INTO car_listings "
                "(scraped_date, make, model, year, mileage_km, price_zl, "
                " engine_type, original_price, age_years, rv_pct) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (today, info["make"], info["model"], listing["year"],
                 listing.get("mileage_km"), listing["price_zl"],
                 info["engine"], msrp, age, rv),
            )
            added += 1

        _log_scrape(_conn, source_key, "ok", added)
        total_added += added

    return total_added


# ---------------------------------------------------------------------------
# 4. Depreciation curve fitting from market data
# ---------------------------------------------------------------------------

def _load_car_listings_for_fitting(conn: sqlite3.Connection | None = None) -> pd.DataFrame | None:
    """Loads car listings data for curve fitting from Supabase or SQLite."""
    # --- Supabase path ---
    if conn is None:
        sb = _get_supabase()
        if sb:
            try:
                res = sb.table("car_listings") \
                    .select("engine_type, age_years, rv_pct") \
                    .gt("rv_pct", 0.05).lt("rv_pct", 1.2) \
                    .gt("age_years", 0).lte("age_years", 15) \
                    .execute()
                if res.data:
                    return pd.DataFrame(res.data)
                return None
            except Exception as e:
                logger.warning("Supabase load_car_listings failed: %s", e)

    # --- SQLite path ---
    _conn = conn or get_db()
    rows = _conn.execute("""
        SELECT engine_type, age_years, rv_pct
        FROM car_listings
        WHERE rv_pct IS NOT NULL
          AND rv_pct > 0.05 AND rv_pct < 1.2
          AND age_years > 0 AND age_years <= 15
    """).fetchall()
    if not rows:
        return None
    return pd.DataFrame(rows, columns=["engine_type", "age_years", "rv_pct"])


def fit_depreciation_curves(
    min_samples: int = 50,
    conn: sqlite3.Connection | None = None,
) -> dict | None:
    """Fits depreciation curves from car_listings. Returns dict of curves or None."""
    if not HAS_SKLEARN:
        return None

    df = _load_car_listings_for_fitting(conn)
    if df is None or len(df) < min_samples:
        return None

    curves = {}

    for engine_type in ["BEV", "ICE"]:
        subset = df[df["engine_type"] == engine_type]
        if len(subset) < min_samples // 4:
            continue

        X = subset[["age_years"]].values
        y = subset["rv_pct"].values

        model = GradientBoostingRegressor(
            n_estimators=100, max_depth=3,
            learning_rate=0.1, random_state=42,
        )
        model.fit(X, y)

        # Generate curve for years 1-10
        curve = {}
        for yr in range(1, 11):
            pred = float(model.predict([[yr]])[0])
            curve[yr] = max(0.05, min(0.95, pred))

        # Enforce monotonically decreasing
        for yr in range(2, 11):
            if curve[yr] >= curve[yr - 1]:
                curve[yr] = curve[yr - 1] - 0.02

        curves[f"NEW_{engine_type}"] = curve

        # USED variant: ~8% higher residual values
        used_curve = {}
        for yr in range(1, 11):
            used_curve[yr] = min(0.95, curve[yr] + 0.08)
        for yr in range(2, 11):
            if used_curve[yr] >= used_curve[yr - 1]:
                used_curve[yr] = used_curve[yr - 1] - 0.015
        curves[f"USED_{engine_type}"] = used_curve

    return curves if len(curves) == 4 else None


def get_depreciation_curve(engine_type: str, is_new: bool, conn: sqlite3.Connection | None = None) -> dict | None:
    """Returns fitted depreciation curve if enough data, else None."""
    fitted = fit_depreciation_curves(conn=conn)
    if fitted:
        key = f"{'NEW' if is_new else 'USED'}_{engine_type}"
        return fitted.get(key)
    return None


def get_model_depreciation(
    make: str, model: str, engine_type: str,
    min_samples: int = 20,
    conn: sqlite3.Connection | None = None,
) -> dict | None:
    """Fits depreciation curve for a specific make/model. Returns None if insufficient data."""
    # --- Supabase path ---
    if conn is None:
        sb = _get_supabase()
        if sb:
            try:
                res = sb.table("car_listings") \
                    .select("age_years, rv_pct") \
                    .eq("make", make).eq("model", model).eq("engine_type", engine_type) \
                    .gt("rv_pct", 0.05).lt("rv_pct", 1.2) \
                    .gt("age_years", 0).lte("age_years", 12) \
                    .order("age_years") \
                    .execute()
                if res.data and len(res.data) >= min_samples:
                    df = pd.DataFrame(res.data)
                    return _fit_model_curve(df, min_samples)
            except Exception as e:
                logger.warning("Supabase get_model_depreciation failed: %s", e)

    # --- SQLite path ---
    _conn = conn or get_db()
    rows = _conn.execute("""
        SELECT age_years, rv_pct
        FROM car_listings
        WHERE make = ? AND model = ? AND engine_type = ?
          AND rv_pct IS NOT NULL AND rv_pct > 0.05 AND rv_pct < 1.2
          AND age_years > 0 AND age_years <= 12
        ORDER BY age_years
    """, (make, model, engine_type)).fetchall()

    if len(rows) < min_samples:
        return None

    df = pd.DataFrame(rows, columns=["age_years", "rv_pct"])
    return _fit_model_curve(df, min_samples)


def _fit_model_curve(df: pd.DataFrame, min_samples: int = 20) -> dict | None:
    """Fits per-model depreciation curve from DataFrame of (age_years, rv_pct)."""
    curve = {}
    for yr in range(1, 11):
        bucket = df[(df["age_years"] >= yr - 0.5) & (df["age_years"] < yr + 0.5)]
        if len(bucket) >= 3:
            curve[yr] = float(bucket["rv_pct"].median())

    known = {yr: v for yr, v in curve.items() if v is not None}
    if len(known) < 3:
        return None

    # Interpolate missing years
    all_years = sorted(known.keys())
    for yr in range(1, 11):
        if yr not in known:
            lower = [y for y in all_years if y < yr]
            upper = [y for y in all_years if y > yr]
            if lower and upper:
                lo, hi = lower[-1], upper[0]
                frac = (yr - lo) / (hi - lo)
                curve[yr] = known[lo] + frac * (known[hi] - known[lo])
            elif lower:
                curve[yr] = known[lower[-1]] - 0.05
            elif upper:
                curve[yr] = min(0.95, known[upper[0]] + 0.05)

    # Enforce monotonic decrease
    for yr in range(2, 11):
        if yr in curve and yr - 1 in curve:
            if curve[yr] >= curve[yr - 1]:
                curve[yr] = curve[yr - 1] - 0.02

    return curve if len(curve) >= 5 else None


# ---------------------------------------------------------------------------
# 5. Data freshness info
# ---------------------------------------------------------------------------

def get_data_freshness(conn: sqlite3.Connection | None = None) -> dict | None:
    """Returns freshness info for sidebar display."""
    # --- Supabase path ---
    if conn is None:
        sb = _get_supabase()
        if sb:
            try:
                fuel_res = sb.table("fuel_prices").select("date") \
                    .order("date", desc=True).limit(1).execute()
                listings_res = sb.table("car_listings") \
                    .select("id", count="exact").limit(0).execute()
                elec_res = sb.table("electricity_prices").select("date") \
                    .order("date", desc=True).limit(1).execute()

                fuel_date = fuel_res.data[0]["date"] if fuel_res.data else None
                if not fuel_date:
                    return None

                return {
                    "fuel_date": fuel_date,
                    "listings_count": listings_res.count or 0,
                    "electricity_date": elec_res.data[0]["date"] if elec_res.data else None,
                    "backend": "supabase",
                }
            except Exception as e:
                logger.warning("Supabase get_data_freshness failed: %s", e)

    # --- SQLite path ---
    _conn = conn or get_db()

    fuel_date = _conn.execute("SELECT MAX(date) as d FROM fuel_prices").fetchone()
    listings_count = _conn.execute("SELECT COUNT(*) as c FROM car_listings").fetchone()
    elec_date = _conn.execute("SELECT MAX(date) as d FROM electricity_prices").fetchone()

    if not fuel_date or not fuel_date["d"]:
        return None

    return {
        "fuel_date": fuel_date["d"],
        "listings_count": listings_count["c"] if listings_count else 0,
        "electricity_date": elec_date["d"] if elec_date else None,
        "backend": "sqlite",
    }
