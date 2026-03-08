"""Testy jednostkowe dla kalkulatora TCO (app.py).

Uruchomienie: python -m pytest test_app.py -v
"""

import sys
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Mockujemy streamlit + plotly + highspy żeby import app.py nie odpalał UI
# ---------------------------------------------------------------------------

st_mock = MagicMock()
st_mock.cache_resource = lambda func=None, **kw: (func if func else lambda f: f)
st_mock.set_page_config = MagicMock()
st_mock.session_state = {"tco_calculated": False}

def _ctx_mgr():
    m = MagicMock()
    m.__enter__ = MagicMock(return_value=m)
    m.__exit__ = MagicMock(return_value=False)
    return m

st_mock.columns = lambda n, **kw: [_ctx_mgr() for _ in range(n if isinstance(n, int) else len(n))]
st_mock.tabs = lambda names: [_ctx_mgr() for _ in names]

def _selectbox(label, options, *a, **kw):
    if options:
        idx = kw.get("index", 0)
        opts = list(options) if not isinstance(options, list) else options
        return opts[idx] if idx < len(opts) else opts[0]
    return ""
st_mock.selectbox = _selectbox

def _radio(label, options, *a, **kw):
    if options:
        idx = kw.get("index", 0)
        opts = list(options) if not isinstance(options, list) else options
        return opts[idx] if idx < len(opts) else opts[0]
    return ""
st_mock.radio = _radio

st_mock.number_input = lambda label, *a, **kw: kw.get("value", 0)
st_mock.slider = lambda label, *a, **kw: kw.get("value", 0)
st_mock.text_input = lambda label, *a, **kw: kw.get("value", "")
st_mock.button = MagicMock(return_value=False)
st_mock.checkbox = lambda label, *a, **kw: kw.get("value", False)
st_mock.expander = lambda *a, **kw: _ctx_mgr()
st_mock.form = lambda *a, **kw: _ctx_mgr()
st_mock.form_submit_button = MagicMock(return_value=False)
st_mock.container = lambda *a, **kw: _ctx_mgr()
st_mock.empty = lambda: MagicMock()
sys.modules["streamlit"] = st_mock
sys.modules["streamlit.components"] = MagicMock()
sys.modules["streamlit.components.v1"] = MagicMock()

plotly_mock = MagicMock()
sys.modules["plotly"] = plotly_mock
sys.modules["plotly.graph_objects"] = MagicMock()
sys.modules["plotly.subplots"] = MagicMock()

sys.modules["highspy"] = MagicMock()
sys.modules["requests"] = MagicMock()
sys.modules["bs4"] = MagicMock()
sys.modules["beautifulsoup4"] = MagicMock()

import app


# ===========================================================================
# 1. Mnożniki temperaturowe
# ===========================================================================

class TestTempMultipliers:
    def test_bev_cold_higher_consumption(self):
        m = app.bev_temp_multiplier(-10, "city")
        assert m > 1.0
        assert m < 2.0

    def test_bev_optimal_temp(self):
        m = app.bev_temp_multiplier(15, "city")
        assert 0.95 <= m <= 1.05

    def test_bev_hot_ac(self):
        m = app.bev_temp_multiplier(35, "city")
        assert m > 1.0

    def test_ice_cold(self):
        m = app.ice_temp_multiplier(-10, "city")
        assert m > 1.0

    def test_ice_warm(self):
        m = app.ice_temp_multiplier(20, "highway")
        assert 0.95 <= m <= 1.05


# ===========================================================================
# 2. Zużycie roczne BEV — calc_annual_consumption_bev(city_kwh, hwy_kwh, city_pct, monthly_km)
# ===========================================================================

class TestAnnualConsumptionBEV:
    def test_basic(self):
        monthly_km = np.array([2500] * 12)
        energy, monthly_kwh = app.calc_annual_consumption_bev(18.0, 22.0, 0.5, monthly_km)
        assert energy > 0
        assert len(monthly_kwh) == 12

    def test_city_lower_than_hwy(self):
        monthly_km = np.array([2500] * 12)
        e_city, _ = app.calc_annual_consumption_bev(18, 22, 0.9, monthly_km)
        e_hwy, _ = app.calc_annual_consumption_bev(18, 22, 0.1, monthly_km)
        assert e_city < e_hwy

    def test_zero_mileage(self):
        monthly_km = np.zeros(12)
        energy, monthly_kwh = app.calc_annual_consumption_bev(18, 22, 0.5, monthly_km)
        assert energy == 0


# ===========================================================================
# 3. Zużycie roczne ICE — calc_annual_fuel_ice(city_l, hwy_l, city_pct, monthly_km, fuel_price)
# ===========================================================================

class TestAnnualFuelICE:
    def test_basic(self):
        monthly_km = np.array([2500] * 12)
        liters, cost, monthly_l = app.calc_annual_fuel_ice(8.0, 5.5, 0.4, monthly_km, 6.50)
        assert liters > 0
        assert cost > 0
        assert len(monthly_l) == 12

    def test_city_more_fuel(self):
        monthly_km = np.array([2500] * 12)
        l_city, _, _ = app.calc_annual_fuel_ice(8.0, 5.5, 0.9, monthly_km, 6.50)
        l_hwy, _, _ = app.calc_annual_fuel_ice(8.0, 5.5, 0.1, monthly_km, 6.50)
        assert l_city > l_hwy


# ===========================================================================
# 4. Segmenty cenowe — price_to_segment(price) -> int (0-9)
# ===========================================================================

class TestPriceSegment:
    def test_cheap_car(self):
        seg = app.price_to_segment(15_000)
        assert seg == 0

    def test_mid_range(self):
        seg = app.price_to_segment(100_000)
        assert seg == 4

    def test_premium(self):
        seg = app.price_to_segment(200_000)
        assert seg == 7

    def test_luxury(self):
        seg = app.price_to_segment(500_000)
        assert seg == 9  # beyond all thresholds

    def test_monotonic(self):
        """Wyższy segment = droższa cena"""
        prices = [10_000, 30_000, 60_000, 100_000, 200_000, 400_000]
        segments = [app.price_to_segment(p) for p in prices]
        assert segments == sorted(segments)


# ===========================================================================
# 5. ML: Syntetyczne profile
# ===========================================================================

class TestSyntheticProfiles:
    def test_shape(self):
        df = app.generate_synthetic_profiles(100)
        assert len(df) == 100
        assert "annual_mileage" in df.columns
        assert "city_pct" in df.columns
        assert "rw_factor_bev" in df.columns
        assert "rw_factor_ice" in df.columns

    def test_value_ranges(self):
        df = app.generate_synthetic_profiles(500)
        assert df["annual_mileage"].min() >= 5000
        assert df["annual_mileage"].max() <= 80000
        assert df["city_pct"].min() >= 0.05
        assert df["city_pct"].max() <= 1.0
        assert df["rw_factor_bev"].min() >= 1.0
        assert df["rw_factor_bev"].max() <= 1.40
        assert df["rw_factor_ice"].min() >= 1.0

    def test_reproducibility(self):
        df1 = app.generate_synthetic_profiles(50)
        df2 = app.generate_synthetic_profiles(50)
        pd.testing.assert_frame_equal(df1, df2)


# ===========================================================================
# 6. ML: Klasteryzacja
# ===========================================================================

class TestClusterModel:
    @pytest.fixture(scope="class")
    def ml(self):
        df = app.generate_synthetic_profiles(500)
        km, scaler, features, label_map = app.build_cluster_model(df)
        return {"km": km, "scaler": scaler, "cl_features": features, "label_map": label_map}

    def test_6_clusters(self, ml):
        assert ml["km"].n_clusters == 6

    def test_predict_returns_valid(self, ml):
        user = {
            "annual_mileage": 30000, "city_pct": 0.6,
            "has_home_charger": 1, "pv_kwp": 5.0,
            "has_heat_pump": 0, "usage_type": 0,
        }
        cl = app.predict_cluster(ml, user)
        assert cl["cluster_id"] in range(6)
        assert cl["name"] in [app.CLUSTER_NAMES[i][0] for i in range(6)]
        assert 0 <= cl["similarity"] <= 100
        assert "centroid" in cl

    def test_different_profiles_different_clusters(self, ml):
        city = {
            "annual_mileage": 8000, "city_pct": 0.9,
            "has_home_charger": 0, "pv_kwp": 0,
            "has_heat_pump": 0, "usage_type": 2,
        }
        fleet = {
            "annual_mileage": 60000, "city_pct": 0.2,
            "has_home_charger": 1, "pv_kwp": 0,
            "has_heat_pump": 0, "usage_type": 0,
        }
        assert app.predict_cluster(ml, city)["cluster_id"] != app.predict_cluster(ml, fleet)["cluster_id"]


# ===========================================================================
# 7. ML: Model real-world
# ===========================================================================

class TestRealWorldModel:
    @pytest.fixture(scope="class")
    def ml(self):
        df = app.generate_synthetic_profiles(500)
        rf_bev, rf_ice, features, r2_bev, r2_ice = app.build_realworld_model(df)
        return {"rf_bev": rf_bev, "rf_ice": rf_ice, "rw_features": features,
                "r2_bev": r2_bev, "r2_ice": r2_ice}

    def test_r2_positive(self, ml):
        assert ml["r2_bev"] > 0.3
        assert ml["r2_ice"] > 0.2

    def test_predict_range(self, ml):
        rw_bev, rw_ice = app.predict_realworld(ml, 0.5, 30000, 1, 5.0)
        assert 1.0 <= rw_bev <= 1.5
        assert 1.0 <= rw_ice <= 1.3

    def test_city_driver_higher_bev_correction(self, ml):
        rw_city, _ = app.predict_realworld(ml, 0.9, 10000, 0, 0)
        rw_hwy, _ = app.predict_realworld(ml, 0.1, 50000, 1, 0)
        assert rw_city > rw_hwy


# ===========================================================================
# 8. Prognoza 12-miesięczna
# ===========================================================================

class TestForecastMonthly:
    def test_12_months(self):
        df = app.forecast_monthly_costs(5000, 15000, 18, 22, 0.5, 8, 5.5, 6.50, 30000)
        assert len(df) == 12
        assert set(df.columns) >= {"Miesiąc", "BEV (zł)", "ICE (zł)", "Oszczędność (zł)"}

    def test_winter_more_expensive(self):
        df = app.forecast_monthly_costs(5000, 15000, 18, 22, 0.5, 8, 5.5, 6.50, 30000)
        jan_bev = df.loc[df["Miesiąc"] == "Sty", "BEV (zł)"].values[0]
        jul_bev = df.loc[df["Miesiąc"] == "Lip", "BEV (zł)"].values[0]
        assert jan_bev > jul_bev

    def test_bev_cheaper_overall(self):
        df = app.forecast_monthly_costs(5000, 15000, 18, 22, 0.5, 8, 5.5, 6.50, 30000)
        assert df["Oszczędność (zł)"].sum() > 0


# ===========================================================================
# 9. GreenWay — greenway_optimal_plan(annual_dc_kwh) -> dict with best, plans, best_data
# ===========================================================================

class TestGreenWay:
    def test_returns_best(self):
        plan = app.greenway_optimal_plan(1000)
        assert "best" in plan
        assert "best_data" in plan
        assert "plans" in plan

    def test_cost_positive(self):
        plan = app.greenway_optimal_plan(1000)
        assert plan["best_data"]["annual_cost"] > 0

    def test_more_kwh_higher_cost(self):
        p_low = app.greenway_optimal_plan(200)
        p_high = app.greenway_optimal_plan(5000)
        assert p_high["best_data"]["annual_cost"] >= p_low["best_data"]["annual_cost"]


# ===========================================================================
# 10. Koszty serwisu — calculate_maintenance_cost(segment_idx, mileage_km, engine_type, is_new, brand="")
# ===========================================================================

class TestMaintenance:
    def test_bev_cheaper_than_ice(self):
        bev = app.calculate_maintenance_cost(5, 90_000, "BEV", True)
        ice = app.calculate_maintenance_cost(5, 90_000, "ICE", True)
        assert bev["total"] < ice["total"]

    def test_higher_mileage_higher_cost(self):
        low = app.calculate_maintenance_cost(5, 30_000, "ICE", True)
        high = app.calculate_maintenance_cost(5, 150_000, "ICE", True)
        assert high["total"] > low["total"]

    def test_returns_breakdown(self):
        result = app.calculate_maintenance_cost(5, 90_000, "ICE", True)
        assert "total" in result
        assert "breakdown" in result


# ===========================================================================
# 11. Tarcza podatkowa — calculate_tax_shield(vehicle_price, engine_type, annual_fuel_cost, insurance_annual, period_years, tax_rate, usage_type)
# ===========================================================================

class TestTaxShield:
    def test_firmowe_positive(self):
        shield = app.calculate_tax_shield(200_000, "ICE", 15_000, 4_000, 3, 0.19, "firmowe")
        assert shield["total"] > 0

    def test_prywatne_zero(self):
        shield = app.calculate_tax_shield(200_000, "ICE", 15_000, 4_000, 3, 0.19, "prywatne")
        assert shield["total"] == 0

    def test_mieszane_between(self):
        firm = app.calculate_tax_shield(200_000, "ICE", 15_000, 4_000, 3, 0.19, "firmowe")
        mixed = app.calculate_tax_shield(200_000, "ICE", 15_000, 4_000, 3, 0.19, "mieszane")
        assert 0 < mixed["total"] < firm["total"]


# ===========================================================================
# 12. Deprecjacja
# ===========================================================================

class TestDepreciation:
    def test_new_car_depreciates(self):
        val = app.calculate_depreciation(200_000, 5, 3, "ice", True)
        assert val < 200_000
        assert val > 0

    def test_bev_more_depreciation(self):
        bev_val = app.calculate_depreciation(200_000, 5, 3, "bev", True)
        ice_val = app.calculate_depreciation(200_000, 5, 3, "ice", True)
        assert (200_000 - bev_val) >= (200_000 - ice_val)


# ===========================================================================
# 13. Ubezpieczenie
# ===========================================================================

class TestInsurance:
    def test_bev_more_expensive(self):
        assert app.estimate_insurance(200_000, "bev") >= app.estimate_insurance(200_000, "ice")

    def test_proportional_to_price(self):
        assert app.estimate_insurance(300_000, "ice") > app.estimate_insurance(80_000, "ice")


# ===========================================================================
# 14. Stałe
# ===========================================================================

class TestConstants:
    def test_6_clusters(self):
        assert len(app.CLUSTER_NAMES) == 6

    def test_cluster_names_have_desc(self):
        for i in range(6):
            name, desc = app.CLUSTER_NAMES[i]
            assert len(name) > 3
            assert len(desc) > 5

    def test_12_months(self):
        assert len(app.TEMPS_PL) == 12
        assert len(app.MONTH_NAMES_PL) == 12

    def test_version(self):
        assert app.APP_VERSION.startswith("0.")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
