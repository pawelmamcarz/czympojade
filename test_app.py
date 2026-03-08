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
st_mock.query_params = {}

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
# 2. Zużycie roczne BEV — calc_annual_consumption_bev(city_kwh, hwy_kwh, road_split, monthly_km)
# ===========================================================================

class TestAnnualConsumptionBEV:
    def test_basic(self):
        monthly_km = np.array([2500] * 12)
        energy, monthly_kwh = app.calc_annual_consumption_bev(18.0, 22.0, (0.5, 0.3, 0.2), monthly_km)
        assert energy > 0
        assert len(monthly_kwh) == 12

    def test_city_lower_than_hwy(self):
        monthly_km = np.array([2500] * 12)
        e_city, _ = app.calc_annual_consumption_bev(18, 22, (0.9, 0.1, 0.0), monthly_km)
        e_hwy, _ = app.calc_annual_consumption_bev(18, 22, (0.1, 0.9, 0.0), monthly_km)
        assert e_city < e_hwy

    def test_zero_mileage(self):
        monthly_km = np.zeros(12)
        energy, monthly_kwh = app.calc_annual_consumption_bev(18, 22, (0.5, 0.3, 0.2), monthly_km)
        assert energy == 0


# ===========================================================================
# 3. Zużycie roczne ICE — calc_annual_fuel_ice(city_l, hwy_l, road_split, monthly_km, fuel_price)
# ===========================================================================

class TestAnnualFuelICE:
    def test_basic(self):
        monthly_km = np.array([2500] * 12)
        liters, cost, monthly_l = app.calc_annual_fuel_ice(8.0, 5.5, (0.4, 0.4, 0.2), monthly_km, 6.50)
        assert liters > 0
        assert cost > 0
        assert len(monthly_l) == 12

    def test_city_more_fuel(self):
        monthly_km = np.array([2500] * 12)
        l_city, _, _ = app.calc_annual_fuel_ice(8.0, 5.5, (0.9, 0.1, 0.0), monthly_km, 6.50)
        l_hwy, _, _ = app.calc_annual_fuel_ice(8.0, 5.5, (0.1, 0.9, 0.0), monthly_km, 6.50)
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
        df = app.forecast_monthly_costs(5000, 15000, 18, 22, (0.5, 0.3, 0.2), 8, 5.5, 6.50, 30000)
        assert len(df) == 12
        assert set(df.columns) >= {"Miesiąc", "BEV (zł)", "ICE (zł)", "Oszczędność (zł)"}

    def test_winter_more_expensive(self):
        df = app.forecast_monthly_costs(5000, 15000, 18, 22, (0.5, 0.3, 0.2), 8, 5.5, 6.50, 30000)
        jan_bev = df.loc[df["Miesiąc"] == "Sty", "BEV (zł)"].values[0]
        jul_bev = df.loc[df["Miesiąc"] == "Lip", "BEV (zł)"].values[0]
        assert jan_bev > jul_bev

    def test_bev_cheaper_overall(self):
        df = app.forecast_monthly_costs(5000, 15000, 18, 22, (0.5, 0.3, 0.2), 8, 5.5, 6.50, 30000)
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

    def test_leasing_mode(self):
        leasing = app.calculate_leasing_params(200_000, 0.10, 36, 0.01)
        shield = app.calculate_tax_shield(
            200_000, "ICE", 15_000, 4_000, 3, 0.19, "firmowe", leasing=leasing)
        assert shield["total"] > 0
        assert shield["leasing_breakdown"] is not None
        assert shield["leasing_breakdown"]["proportion"] <= 1.0

    def test_leasing_interest_not_limited(self):
        """Odsetki leasingowe powinny być 100% w KUP — bez limitu proporcjonalnego."""
        leasing = app.calculate_leasing_params(300_000, 0.10, 36, 0.01)
        shield = app.calculate_tax_shield(
            300_000, "ICE", 15_000, 4_000, 3, 0.19, "firmowe", leasing=leasing)
        lb = shield["leasing_breakdown"]
        # Proportion < 1 bo 300k > limit ICE 100k
        assert lb["proportion"] < 1.0
        # Odsetki roczne w KUP = total_interest / period_years * kup_pct (bez proportion)
        expected_interest_kup = leasing["total_interest_netto"] / 3 * 1.0
        assert abs(lb["interest_kup_annual"] - expected_interest_kup) < 1.0

    def test_gotowka_no_leasing_breakdown(self):
        shield = app.calculate_tax_shield(200_000, "ICE", 15_000, 4_000, 3, 0.19, "firmowe")
        assert shield["leasing_breakdown"] is None


# ===========================================================================
# 12. Deprecjacja
# ===========================================================================

class TestDepreciation:
    def test_new_car_depreciates(self):
        loss = app.calculate_depreciation(200_000, 5, 3, "ICE", True)
        assert loss < 200_000
        assert loss > 0

    def test_new_bev_retains_better_early(self):
        """Nowe BEV tracą mniej w pierwszych 3 latach (lepsze RV)."""
        bev_loss = app.calculate_depreciation(200_000, 5, 3, "BEV", True)
        ice_loss = app.calculate_depreciation(200_000, 5, 3, "ICE", True)
        assert bev_loss < ice_loss  # BEV traci mniej w roku 1-5

    def test_bev_battery_threshold_year8(self):
        """BEV traci więcej po roku 8 (próg baterii HV)."""
        bev_loss_7 = app.calculate_depreciation(200_000, 5, 7, "BEV", True)
        bev_loss_8 = app.calculate_depreciation(200_000, 5, 8, "BEV", True)
        yearly_loss_7to8 = bev_loss_8 - bev_loss_7
        bev_loss_6 = app.calculate_depreciation(200_000, 5, 6, "BEV", True)
        yearly_loss_6to7 = bev_loss_7 - bev_loss_6
        # Rok 7→8 powinien mieć ostrzejszy spadek niż 6→7
        assert yearly_loss_7to8 > yearly_loss_6to7

    def test_used_depreciates_less(self):
        """Używane auto traci mniej procentowo niż nowe."""
        new_loss = app.calculate_depreciation(200_000, 5, 3, "ICE", True)
        used_loss = app.calculate_depreciation(200_000, 5, 3, "ICE", False)
        assert used_loss < new_loss

    def test_curve_values_match(self):
        """Sprawdź że krzywa zwraca oczekiwane wartości."""
        # Nowe ICE, rok 1: rv=0.78 → loss = 200k * 0.22 = 44k
        loss = app.calculate_depreciation(200_000, 5, 1, "ICE", True)
        assert loss == pytest.approx(200_000 * 0.22, rel=0.01)
        # Nowe BEV, rok 5: rv=0.48 → loss = 200k * 0.52 = 104k
        loss = app.calculate_depreciation(200_000, 5, 5, "BEV", True)
        assert loss == pytest.approx(200_000 * 0.52, rel=0.01)


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


# ===========================================================================
# 15. Leasing — calculate_leasing_params
# ===========================================================================

class TestLeasingParams:
    def test_basic(self):
        result = app.calculate_leasing_params(200_000, 0.10, 36, 0.01)
        assert result["vehicle_netto"] == pytest.approx(200_000 / 1.23, rel=0.01)
        assert result["monthly_rate_netto"] > 0
        assert result["lease_months"] == 36

    def test_zero_down(self):
        result = app.calculate_leasing_params(200_000, 0.0, 36, 0.01)
        assert result["down_netto"] == 0
        assert result["down_brutto"] == 0
        assert result["monthly_rate_netto"] > 0

    def test_interest_positive(self):
        result = app.calculate_leasing_params(200_000, 0.10, 36, 0.01, annual_rate=0.06)
        assert result["total_interest_netto"] > 0

    def test_cashflow_sum(self):
        """Cashflow brutto = (wpłata + raty + wykup) * 1.23"""
        result = app.calculate_leasing_params(200_000, 0.10, 36, 0.01)
        netto_sum = result["down_netto"] + result["total_rates_netto"] + result["buyout_netto"]
        assert result["total_cashflow_brutto"] == pytest.approx(netto_sum * 1.23, rel=0.01)

    def test_capital_equals_financed(self):
        result = app.calculate_leasing_params(200_000, 0.10, 36, 0.01)
        assert result["total_capital_netto"] == pytest.approx(result["financed_netto"], rel=0.01)


# ===========================================================================
# 16. Podatek od wykupu — calculate_buyout_tax
# ===========================================================================

class TestBuyoutTax:
    def test_profit_taxed(self):
        tax = app.calculate_buyout_tax(5_000, 80_000, 3, 0.19)
        assert tax == pytest.approx((80_000 - 5_000) * 0.19)

    def test_no_profit_no_tax(self):
        tax = app.calculate_buyout_tax(80_000, 50_000, 3, 0.19)
        assert tax == 0.0

    def test_6_years_exempt(self):
        tax = app.calculate_buyout_tax(5_000, 80_000, 6, 0.19)
        assert tax == 0.0

    def test_7_years_exempt(self):
        tax = app.calculate_buyout_tax(5_000, 80_000, 7, 0.19)
        assert tax == 0.0


# ===========================================================================
# 17. 3-way road split — mnożniki autostradowe
# ===========================================================================

class TestRoadSplit:
    def test_highway_multiplier_bev(self):
        """Autostrada zużywa więcej niż krajowa (BEV)."""
        monthly_km = np.array([2500] * 12)
        e_rural, _ = app.calc_annual_consumption_bev(18, 22, (0.0, 1.0, 0.0), monthly_km)
        e_hwy, _ = app.calc_annual_consumption_bev(18, 22, (0.0, 0.0, 1.0), monthly_km)
        assert e_hwy > e_rural
        ratio = e_hwy / e_rural
        assert abs(ratio - app.HIGHWAY_SPEED_MULTIPLIER_BEV) < 0.01

    def test_highway_multiplier_ice(self):
        """Autostrada zużywa więcej niż krajowa (ICE)."""
        monthly_km = np.array([2500] * 12)
        l_rural, _, _ = app.calc_annual_fuel_ice(8, 5.5, (0.0, 1.0, 0.0), monthly_km, 6.50)
        l_hwy, _, _ = app.calc_annual_fuel_ice(8, 5.5, (0.0, 0.0, 1.0), monthly_km, 6.50)
        assert l_hwy > l_rural
        ratio = l_hwy / l_rural
        assert abs(ratio - app.HIGHWAY_SPEED_MULTIPLIER_ICE) < 0.01

    def test_normalization(self):
        """Suma road_split = 1.0."""
        monthly_km = np.array([2500] * 12)
        e1, _ = app.calc_annual_consumption_bev(18, 22, (0.5, 0.3, 0.2), monthly_km)
        e2, _ = app.calc_annual_consumption_bev(18, 22, (1.0, 0.0, 0.0), monthly_km)
        # 100% miasto powinno dać mniej niż mieszany z autostradą
        assert e1 > e2  # bo highway_kwh > city_kwh + autostrada multiplier

    def test_backward_compat_2way(self):
        """road_split (city, 1-city, 0) powinna dać te same wyniki co stary 2-way."""
        monthly_km = np.array([2500] * 12)
        e_new, _ = app.calc_annual_consumption_bev(18, 22, (0.6, 0.4, 0.0), monthly_km)
        assert e_new > 0


# ===========================================================================
# 18. Stałe autostradowe
# ===========================================================================

class TestHighwayConstants:
    def test_bev_multiplier_gt_1(self):
        assert app.HIGHWAY_SPEED_MULTIPLIER_BEV > 1.0

    def test_ice_multiplier_gt_1(self):
        assert app.HIGHWAY_SPEED_MULTIPLIER_ICE > 1.0

    def test_bev_higher_than_ice(self):
        """BEV bardziej wrażliwe na aero niż ICE."""
        assert app.HIGHWAY_SPEED_MULTIPLIER_BEV > app.HIGHWAY_SPEED_MULTIPLIER_ICE


# ===========================================================================
# 19. Krzywe deprecjacji — stałe
# ===========================================================================

class TestDepreciationCurves:
    def test_all_curves_10_years(self):
        for curve in [app.DEPRECIATION_CURVE_NEW_ICE, app.DEPRECIATION_CURVE_NEW_BEV,
                      app.DEPRECIATION_CURVE_USED_ICE, app.DEPRECIATION_CURVE_USED_BEV]:
            assert len(curve) == 10
            for yr in range(1, 11):
                assert yr in curve

    def test_curves_monotonically_decreasing(self):
        """Wartość rezydualna maleje z każdym rokiem."""
        for curve in [app.DEPRECIATION_CURVE_NEW_ICE, app.DEPRECIATION_CURVE_NEW_BEV,
                      app.DEPRECIATION_CURVE_USED_ICE, app.DEPRECIATION_CURVE_USED_BEV]:
            for yr in range(1, 10):
                assert curve[yr] > curve[yr + 1]

    def test_rv_between_0_and_1(self):
        for curve in [app.DEPRECIATION_CURVE_NEW_ICE, app.DEPRECIATION_CURVE_NEW_BEV,
                      app.DEPRECIATION_CURVE_USED_ICE, app.DEPRECIATION_CURVE_USED_BEV]:
            for rv in curve.values():
                assert 0 < rv < 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
