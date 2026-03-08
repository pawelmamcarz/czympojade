"""Tests for market_data.py — SQLite storage + scraping + curve fitting."""

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from market_data import (
    get_db,
    scrape_fuel_prices,
    _load_latest_fuel,
    get_fuel_price_history,
    scrape_electricity_prices,
    _load_latest_electricity,
    get_electricity_price_history,
    scrape_car_listings,
    fit_depreciation_curves,
    get_depreciation_curve,
    get_model_depreciation,
    get_data_freshness,
    FUEL_DEFAULTS,
    KNOWN_MSRP,
    TRACKED_MODELS,
)


@pytest.fixture
def db(tmp_path):
    """Create a temporary in-memory-like SQLite DB for testing."""
    db_path = tmp_path / "test.db"
    conn = get_db(db_path)
    yield conn
    conn.close()


def _insert_fuel(conn, date, pb95=6.50, on=6.40, lpg=3.20):
    for ft, price in [("pb95", pb95), ("on", on), ("lpg", lpg)]:
        conn.execute(
            "INSERT OR REPLACE INTO fuel_prices (date, fuel_type, price_zl) VALUES (?, ?, ?)",
            (date, ft, price),
        )
    conn.commit()


def _insert_listing(conn, make, model, year, price, engine_type, msrp=None, date=None):
    age = datetime.now().year - year
    rv = price / msrp if msrp else None
    conn.execute(
        "INSERT INTO car_listings "
        "(scraped_date, make, model, year, mileage_km, price_zl, "
        " engine_type, original_price, age_years, rv_pct) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (date or datetime.now().strftime("%Y-%m-%d"),
         make, model, year, 50000, price, engine_type, msrp, age, rv),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Database Init
# ---------------------------------------------------------------------------

class TestDatabaseInit:
    def test_get_db_creates_file(self, tmp_path):
        db_path = tmp_path / "subdir" / "test.db"
        conn = get_db(db_path)
        assert db_path.exists()
        conn.close()

    def test_tables_created(self, db):
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {t["name"] for t in tables}
        assert "scrape_meta" in names
        assert "fuel_prices" in names
        assert "electricity_prices" in names
        assert "car_listings" in names

    def test_idempotent(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn1 = get_db(db_path)
        conn2 = get_db(db_path)  # should not fail
        conn1.close()
        conn2.close()


# ---------------------------------------------------------------------------
# Fuel Prices
# ---------------------------------------------------------------------------

class TestFuelScraping:
    def test_store_and_retrieve(self, db):
        _insert_fuel(db, "2026-03-01", pb95=6.80, on=6.60, lpg=3.30)
        result = _load_latest_fuel(db)
        assert result["pb95"] == 6.80
        assert result["on"] == 6.60
        assert result["lpg"] == 3.30

    def test_latest_wins(self, db):
        _insert_fuel(db, "2026-03-01", pb95=6.50)
        _insert_fuel(db, "2026-03-05", pb95=6.90)
        result = _load_latest_fuel(db)
        assert result["pb95"] == 6.90

    def test_empty_db_returns_defaults(self, db):
        result = _load_latest_fuel(db)
        assert result["pb95"] == FUEL_DEFAULTS["pb95"]

    def test_history_returns_dataframe(self, db):
        _insert_fuel(db, "2026-03-01", pb95=6.50)
        _insert_fuel(db, "2026-03-02", pb95=6.55)
        _insert_fuel(db, "2026-03-03", pb95=6.60)
        hist = get_fuel_price_history(days=90, conn=db)
        assert isinstance(hist, pd.DataFrame)
        assert len(hist) == 3
        assert "pb95" in hist.columns

    def test_history_empty_db(self, db):
        hist = get_fuel_price_history(conn=db)
        assert hist.empty


# ---------------------------------------------------------------------------
# Electricity Prices
# ---------------------------------------------------------------------------

class TestElectricityScraping:
    def test_store_and_retrieve(self, db):
        db.execute(
            "INSERT INTO electricity_prices (date, price_type, price_zl_kwh) "
            "VALUES ('2026-03-01', 'rdn_avg', 0.45)"
        )
        db.commit()
        result = _load_latest_electricity(db)
        assert result is not None
        assert result["rdn_avg"] == 0.45

    def test_empty_returns_none(self, db):
        result = _load_latest_electricity(db)
        assert result is None

    def test_history(self, db):
        for i, price in enumerate([0.40, 0.42, 0.45]):
            db.execute(
                "INSERT INTO electricity_prices (date, price_type, price_zl_kwh) "
                "VALUES (?, 'rdn_avg', ?)",
                (f"2026-03-0{i+1}", price),
            )
        db.commit()
        hist = get_electricity_price_history(days=90, conn=db)
        assert len(hist) == 3


# ---------------------------------------------------------------------------
# Car Listings
# ---------------------------------------------------------------------------

class TestCarListings:
    def test_store_listing(self, db):
        _insert_listing(db, "Tesla", "Model Y", 2023, 160_000, "BEV", 189_000)
        rows = db.execute("SELECT COUNT(*) as c FROM car_listings").fetchone()
        assert rows["c"] == 1

    def test_rv_pct_computed(self, db):
        _insert_listing(db, "Tesla", "Model Y", 2023, 151_200, "BEV", 189_000)
        row = db.execute("SELECT rv_pct FROM car_listings LIMIT 1").fetchone()
        assert abs(row["rv_pct"] - 0.80) < 0.01

    def test_multiple_listings(self, db):
        for yr in range(2018, 2025):
            price = int(189_000 * (0.95 ** (2026 - yr)))
            _insert_listing(db, "Tesla", "Model Y", yr, price, "BEV", 189_000)
        rows = db.execute("SELECT COUNT(*) as c FROM car_listings").fetchone()
        assert rows["c"] == 7


# ---------------------------------------------------------------------------
# Depreciation Curve Fitting
# ---------------------------------------------------------------------------

class TestDepreciationFitting:
    def _populate_listings(self, db, n=100):
        """Insert synthetic listings for fitting."""
        np.random.seed(42)
        for i in range(n):
            engine = "BEV" if i % 2 == 0 else "ICE"
            make = "Tesla" if engine == "BEV" else "Toyota"
            model = "Model Y" if engine == "BEV" else "Corolla"
            msrp = 189_000 if engine == "BEV" else 135_000
            age = np.random.randint(1, 11)
            # Realistic depreciation: ~80% at year 1, decreasing
            rv = max(0.10, 0.90 - age * 0.08 + np.random.normal(0, 0.03))
            price = int(msrp * rv)
            _insert_listing(db, make, model, 2026 - age, price, engine, msrp)

    def test_returns_none_insufficient_data(self, db):
        _insert_listing(db, "Tesla", "Model Y", 2023, 150_000, "BEV", 189_000)
        result = fit_depreciation_curves(min_samples=50, conn=db)
        assert result is None

    def test_returns_curves_with_data(self, db):
        self._populate_listings(db, 200)
        result = fit_depreciation_curves(min_samples=50, conn=db)
        assert result is not None
        assert "NEW_BEV" in result
        assert "NEW_ICE" in result
        assert "USED_BEV" in result
        assert "USED_ICE" in result

    def test_curves_monotonically_decreasing(self, db):
        self._populate_listings(db, 200)
        result = fit_depreciation_curves(min_samples=50, conn=db)
        assert result is not None
        for key, curve in result.items():
            for yr in range(2, 11):
                assert curve[yr] < curve[yr - 1], f"{key}: year {yr} not decreasing"

    def test_values_in_range(self, db):
        self._populate_listings(db, 200)
        result = fit_depreciation_curves(min_samples=50, conn=db)
        assert result is not None
        for key, curve in result.items():
            for yr, val in curve.items():
                assert 0.05 <= val <= 0.95, f"{key} year {yr}: {val} out of range"

    def test_fallback_to_none_empty_db(self, db):
        result = get_depreciation_curve("BEV", True, conn=db)
        assert result is None


class TestModelDepreciation:
    def test_returns_none_few_samples(self, db):
        _insert_listing(db, "Tesla", "Model Y", 2023, 150_000, "BEV", 189_000)
        result = get_model_depreciation("Tesla", "Model Y", "BEV", conn=db)
        assert result is None

    def test_returns_curve_with_data(self, db):
        np.random.seed(42)
        for yr in range(2016, 2026):
            for _ in range(5):
                age = 2026 - yr
                rv = max(0.10, 0.90 - age * 0.07 + np.random.normal(0, 0.02))
                _insert_listing(db, "Tesla", "Model Y", yr, int(189_000 * rv), "BEV", 189_000)
        result = get_model_depreciation("Tesla", "Model Y", "BEV", min_samples=20, conn=db)
        assert result is not None
        assert len(result) >= 5


# ---------------------------------------------------------------------------
# Data Freshness
# ---------------------------------------------------------------------------

class TestDataFreshness:
    def test_empty_db(self, db):
        result = get_data_freshness(conn=db)
        assert result is None

    def test_with_data(self, db):
        _insert_fuel(db, "2026-03-08")
        _insert_listing(db, "Tesla", "Model Y", 2023, 150_000, "BEV", 189_000)
        result = get_data_freshness(conn=db)
        assert result is not None
        assert result["fuel_date"] == "2026-03-08"
        assert result["listings_count"] == 1


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_known_msrp_has_entries(self):
        assert len(KNOWN_MSRP) > 10

    def test_tracked_models_have_slugs(self):
        for m in TRACKED_MODELS:
            assert "slug" in m
            assert "make" in m
            assert "model" in m
            assert m["engine"] in ("BEV", "ICE")

    def test_msrp_values_positive(self):
        for key, val in KNOWN_MSRP.items():
            assert val > 0, f"{key} has non-positive MSRP"
