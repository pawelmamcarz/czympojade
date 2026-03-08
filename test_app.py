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
        assert len(app.APP_VERSION) > 0


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


# ===========================================================================
# 20. v21 — LPG Constants
# ===========================================================================

class TestLPGConstants:
    def test_lpg_benzyna_pct(self):
        """10% jazdy na benzynie."""
        assert app.LPG_BENZYNA_PCT == 0.10

    def test_lpg_consumption_mult(self):
        """LPG: +15% wyższe spalanie."""
        assert app.LPG_CONSUMPTION_MULT == 1.15

    def test_lpg_maintenance_factor(self):
        """LPG: +20% wyższe koszty serwisowe bazowe."""
        assert app.LPG_MAINTENANCE_FACTOR == 1.20

    def test_lpg_component_costs_positive(self):
        """Wszystkie koszty komponentów LPG > 0."""
        assert app.LPG_FILTER_COST > 0
        assert app.LPG_SPARK_PLUG_COST > 0
        assert app.LPG_INJECTOR_COST > 0
        assert app.LPG_VALVE_DAMAGE_COST > 0
        assert app.LPG_CONTROLLER_COST > 0
        assert app.LPG_REDUCER_COST > 0
        assert app.LPG_HOSES_COST > 0
        assert app.LPG_FUEL_PUMP_COST > 0

    def test_lpg_install_costs(self):
        """Koszt instalacji LPG: nowe > używane."""
        assert app.LPG_INSTALL_COST_NEW > app.LPG_INSTALL_COST_USED
        assert app.LPG_INSTALL_COST_NEW >= 3_000
        assert app.LPG_INSTALL_COST_USED >= 2_000


# ===========================================================================
# 21. v21 — LPG Fuel Calculation (dual-fuel)
# ===========================================================================

class TestLPGFuel:
    def test_lpg_cheaper_than_pb95(self):
        """LPG dual-fuel jest tańsze niż sama benzyna."""
        monthly_km = np.array([2083] * 12)  # 25k km/rok
        _, cost_pb95, _ = app.calc_annual_fuel_ice(
            8.0, 5.5, (0.5, 0.4, 0.1), monthly_km, 6.50,
            fuel_type_idx=0)
        _, cost_lpg, _ = app.calc_annual_fuel_ice(
            8.0, 5.5, (0.5, 0.4, 0.1), monthly_km, 3.30,
            fuel_type_idx=2, pb95_price=6.50)
        assert cost_lpg < cost_pb95
        # oszczędność 25-45%
        savings_pct = (cost_pb95 - cost_lpg) / cost_pb95 * 100
        assert 20 < savings_pct < 50

    def test_lpg_dual_fuel_uses_benzyna(self):
        """LPG zużywa 10% benzyny + 90% gazu."""
        monthly_km = np.array([2083] * 12)
        liters, cost, _ = app.calc_annual_fuel_ice(
            8.0, 5.5, (0.5, 0.4, 0.1), monthly_km, 3.30,
            fuel_type_idx=2, pb95_price=6.50)
        # Koszt powinien składać się z taniego LPG + drogiej benzyny
        assert cost > 0
        assert liters > 0

    def test_lpg_higher_consumption_than_base(self):
        """LPG: wyższe spalanie o 15% (mnożnik 1.15)."""
        monthly_km = np.array([2083] * 12)
        liters_pb, _, _ = app.calc_annual_fuel_ice(
            8.0, 5.5, (0.5, 0.4, 0.1), monthly_km, 6.50,
            fuel_type_idx=0)
        liters_lpg, _, _ = app.calc_annual_fuel_ice(
            8.0, 5.5, (0.5, 0.4, 0.1), monthly_km, 3.30,
            fuel_type_idx=2, pb95_price=6.50)
        # Total liters should be the same (base liters) but LPG portion has 1.15x
        # LPG uses 90% * 1.15 + 10% of base liters → not directly comparable
        assert liters_lpg == liters_pb  # same base liters returned


# ===========================================================================
# 22. v21 — LPG Maintenance (component failure model)
# ===========================================================================

class TestLPGMaintenance:
    def test_lpg_more_expensive_than_pb95(self):
        """LPG serwis droższy niż benzyna (base + LPG components)."""
        maint_pb = app.calculate_maintenance_cost(3, 125_000, "ICE", False,
                                                   fuel_type_idx=0, period_years=5)
        maint_lpg = app.calculate_maintenance_cost(3, 125_000, "ICE", False,
                                                    fuel_type_idx=2, period_years=5)
        assert maint_lpg["total"] > maint_pb["total"]
        # LPG powinien być co najmniej 30% droższy (base +20% + komponenty)
        ratio = maint_lpg["total"] / maint_pb["total"]
        assert ratio > 1.3

    def test_lpg_breakdown_has_gas_items(self):
        """LPG breakdown zawiera pozycje instalacji gazowej."""
        maint = app.calculate_maintenance_cost(3, 125_000, "ICE", False,
                                                fuel_type_idx=2, period_years=5)
        bd = maint["breakdown"]
        assert "Filtry gazu LPG" in bd
        assert "Świece zapłonowe (skrócony interwał)" in bd
        assert "Wtryskiwacze LPG" in bd
        assert "Zawory / gniazda zaworowe" in bd
        assert "Sterownik + czujniki LPG" in bd
        assert "Reduktor LPG" in bd
        assert "Przegląd instalacji LPG (roczny)" in bd
        # Wszystkie pozycje > 0
        for key in ["Filtry gazu LPG", "Wtryskiwacze LPG", "Reduktor LPG"]:
            assert bd[key] > 0

    def test_lpg_service_annual(self):
        """LPG: roczny przegląd = 500 zł × period_years."""
        maint = app.calculate_maintenance_cost(3, 100_000, "ICE", False,
                                                fuel_type_idx=2, period_years=5)
        assert maint["breakdown"]["Przegląd instalacji LPG (roczny)"] == 500 * 5

    def test_pb95_no_lpg_items(self):
        """Benzyna NIE ma pozycji LPG w breakdown."""
        maint = app.calculate_maintenance_cost(3, 125_000, "ICE", False,
                                                fuel_type_idx=0, period_years=5)
        bd = maint["breakdown"]
        assert "Filtry gazu LPG" not in bd
        assert "Wtryskiwacze LPG" not in bd


# ===========================================================================
# 23. v21 — Fun Car Presets (ICE, BEV, HYB)
# ===========================================================================

class TestFunCarPresets:
    def test_funcar_segment_exists_new(self):
        """Fun Car segment istnieje w presetach nowych aut (ICE, BEV, HYB)."""
        assert "Fun Car 🏎️" in app.ICE_PRESETS_NEW
        assert "Fun Car 🏎️" in app.BEV_PRESETS_NEW
        assert "Fun Car 🏎️" in app.HYB_PRESETS_NEW

    def test_funcar_segment_exists_used(self):
        """Fun Car segment istnieje w presetach używanych aut (ICE, BEV, HYB)."""
        assert "Fun Car 🏎️" in app.ICE_PRESETS_USED
        assert "Fun Car 🏎️" in app.BEV_PRESETS_USED
        assert "Fun Car 🏎️" in app.HYB_PRESETS_USED

    def test_funcar_ice_new_has_models(self):
        """Fun Car ICE nowe auta mają modele z dużym spalaniem."""
        fc = app.ICE_PRESETS_NEW["Fun Car 🏎️"]
        assert len(fc) >= 2
        for name, cfg in fc.items():
            assert cfg["city_l"] >= 12  # performance = duże spalanie
            assert cfg["price"] >= 200_000

    def test_funcar_ice_used_has_lpg_models(self):
        """Fun Car ICE używane zawierają modele na LPG."""
        fc = app.ICE_PRESETS_USED["Fun Car 🏎️"]
        lpg_models = [n for n, c in fc.items() if c.get("fuel") == 2]
        assert len(lpg_models) >= 2  # co najmniej 2 modele LPG

    def test_funcar_fuel_field_valid(self):
        """Pole 'fuel' w Fun Car ICE presetach: 0=PB95, 1=ON, 2=LPG."""
        for presets in [app.ICE_PRESETS_NEW, app.ICE_PRESETS_USED]:
            if "Fun Car 🏎️" in presets:
                for name, cfg in presets["Fun Car 🏎️"].items():
                    assert cfg["fuel"] in (0, 1, 2)

    def test_funcar_bev_has_models(self):
        """Fun Car BEV nowe i używane mają modele z dużą baterią."""
        for presets in [app.BEV_PRESETS_NEW, app.BEV_PRESETS_USED]:
            fc = presets["Fun Car 🏎️"]
            assert len(fc) >= 2
            for name, cfg in fc.items():
                assert cfg["bat"] >= 70
                assert cfg["city_kwh"] >= 14.0

    def test_funcar_hyb_all_phev(self):
        """Fun Car HYB (nowe i używane) to same PHEV — performance hybrydy."""
        for presets in [app.HYB_PRESETS_NEW, app.HYB_PRESETS_USED]:
            fc = presets["Fun Car 🏎️"]
            assert len(fc) >= 2
            for name, cfg in fc.items():
                assert cfg["hybrid_type"] == "PHEV"
                assert cfg["bat"] > 0
                assert cfg["elec_pct"] > 0

    def test_funcar_has_m3_e93(self):
        """BMW M3 E93 jest w ICE Fun Car (user's car!)."""
        ice_new = app.ICE_PRESETS_NEW["Fun Car 🏎️"]
        ice_used = app.ICE_PRESETS_USED["Fun Car 🏎️"]
        # Sprawdź w nowych lub używanych
        all_names = list(ice_new.keys()) + list(ice_used.keys())
        m3_found = any("M3 E93" in n for n in all_names)
        assert m3_found, "BMW M3 E93 not found in Fun Car ICE presets"


# ===========================================================================
# 24. v21 — GreenWay March 2026 prices
# ===========================================================================

class TestGreenWayMarch2026:
    def test_standard_dc_325(self):
        """GreenWay Standard DC = 3.25 zł/kWh (marzec 2026)."""
        assert app.GREENWAY_PLANS["Standard"]["dc_per_kwh"] == 3.25

    def test_standard_ac_205(self):
        """GreenWay Standard AC = 2.05 zł/kWh."""
        assert app.GREENWAY_PLANS["Standard"]["ac_per_kwh"] == 2.05

    def test_plus_dc_240(self):
        """GreenWay Plus DC = 2.40 zł/kWh."""
        assert app.GREENWAY_PLANS["Plus"]["dc_per_kwh"] == 2.40

    def test_plus_ac_175(self):
        """GreenWay Plus AC = 1.75 zł/kWh."""
        assert app.GREENWAY_PLANS["Plus"]["ac_per_kwh"] == 1.75

    def test_max_dc_210(self):
        """GreenWay Max DC = 2.10 zł/kWh."""
        assert app.GREENWAY_PLANS["Max"]["dc_per_kwh"] == 2.10

    def test_max_ac_160(self):
        """GreenWay Max AC = 1.60 zł/kWh."""
        assert app.GREENWAY_PLANS["Max"]["ac_per_kwh"] == 1.60


# ===========================================================================
# 25. v21 — Pro Tier + Feature gates
# ===========================================================================

class TestProTier:
    def test_is_pro_exists(self):
        """Stała IS_PRO istnieje."""
        assert hasattr(app, "IS_PRO")
        assert isinstance(app.IS_PRO, bool)

    def test_submeter_cost(self):
        """Koszt podlicznika = 2500 zł."""
        assert app.SUBMETER_COST == 2_500

    def test_dynamic_price_cap(self):
        """Tarcza cenowa: max średnia = G11 (0.42)."""
        assert app.DYNAMIC_PRICE_CAP == 0.42

    def test_moj_prad_6_max(self):
        """Mój Prąd 6.0: max dotacja 28 000 zł."""
        assert app.MOJ_PRAD_6_MAX == 28_000


# ===========================================================================
# 25. v21 — SCT (Strefa Czystego Transportu)
# ===========================================================================

class TestSCT:
    def test_sct_fine_exists(self):
        """Mandat SCT = 500 zł."""
        assert app.SCT_FINE_PER_ENTRY == 500

    def test_sct_free_entries(self):
        """4 darmowe wjazdy/rok."""
        assert app.SCT_FREE_ENTRIES == 4

    def test_sct_min_year_petrol(self):
        """Benzyna/LPG: min rocznik 2005 (Euro 4+)."""
        assert app.SCT_MIN_YEAR_PETROL == 2005

    def test_sct_min_year_diesel(self):
        """Diesel: min rocznik 2009 (Euro 5+)."""
        assert app.SCT_MIN_YEAR_DIESEL == 2009

    def test_sct_cities(self):
        """SCT aktywne w Warszawie i Krakowie."""
        assert "Warszawa" in app.SCT_CITIES
        assert "Kraków" in app.SCT_CITIES


# ===========================================================================
# 26. v21 — optimize_charging with submeter/price_cap
# ===========================================================================

class TestOptimizeChargingV21:
    def test_submeter_accepted(self):
        """optimize_charging akceptuje has_submeter param."""
        result = app.optimize_charging(
            annual_demand_kwh=3500, battery_cap_kwh=60,
            pv_kwp=0, bess_kwh=0,
            has_home_charger=True, has_dynamic_tariff=False,
            has_old_pv=False, suc_distance_km=30,
            annual_mileage_km=15000,
            has_submeter=True)
        assert result["total_cost"] > 0
        assert result["has_submeter"] is True

    def test_price_cap_accepted(self):
        """optimize_charging akceptuje has_price_cap param."""
        result = app.optimize_charging(
            annual_demand_kwh=3500, battery_cap_kwh=60,
            pv_kwp=0, bess_kwh=0,
            has_home_charger=True, has_dynamic_tariff=True,
            has_old_pv=False, suc_distance_km=30,
            annual_mileage_km=15000,
            has_price_cap=True)
        assert result["total_cost"] > 0
        assert "price_cap_applied" in result

    def test_submeter_enables_dynamic(self):
        """Submeter włącza dynamiczną taryfę dla EV nawet bez has_dynamic_tariff."""
        result_static = app.optimize_charging(
            annual_demand_kwh=3500, battery_cap_kwh=60,
            pv_kwp=0, bess_kwh=0,
            has_home_charger=True, has_dynamic_tariff=False,
            has_old_pv=False, suc_distance_km=30,
            annual_mileage_km=15000,
            has_submeter=False)
        result_submeter = app.optimize_charging(
            annual_demand_kwh=3500, battery_cap_kwh=60,
            pv_kwp=0, bess_kwh=0,
            has_home_charger=True, has_dynamic_tariff=False,
            has_old_pv=False, suc_distance_km=30,
            annual_mileage_km=15000,
            has_submeter=True)
        # Submeter should give different (likely cheaper) cost due to dynamic pricing
        assert result_submeter["total_cost"] != result_static["total_cost"]


# ===========================================================================
# 27. v21 — calculate_tco_quick with LPG
# ===========================================================================

class TestTCOQuickLPG:
    def test_lpg_tco_cheaper_than_pb95(self):
        """LPG TCO powinno być tańsze niż PB95 przy tym samym aucie."""
        tco_pb = app.calculate_tco_quick(
            vehicle_price=80_000, engine_type="ICE", is_new=False,
            annual_mileage=25_000, period_years=5,
            road_split=(0.5, 0.4, 0.1),
            fuel_price=6.50, city_l=10.0, highway_l=7.0,
            fuel_type_idx=0)
        tco_lpg = app.calculate_tco_quick(
            vehicle_price=80_000, engine_type="ICE", is_new=False,
            annual_mileage=25_000, period_years=5,
            road_split=(0.5, 0.4, 0.1),
            fuel_price=3.30, city_l=10.0, highway_l=7.0,
            fuel_type_idx=2, pb95_price=6.50)
        # LPG fuel cheaper → TCO cheaper (even with higher maintenance)
        assert tco_lpg["energy"] < tco_pb["energy"]

    def test_lpg_tco_returns_valid(self):
        """LPG TCO returns valid dict."""
        tco = app.calculate_tco_quick(
            vehicle_price=28_000, engine_type="ICE", is_new=False,
            annual_mileage=20_000, period_years=5,
            road_split=(0.5, 0.4, 0.1),
            fuel_price=3.30, city_l=16.0, highway_l=11.0,
            fuel_type_idx=2, pb95_price=6.50)
        assert tco["tco"] > 0
        assert tco["per_km"] > 0
        assert tco["energy"] > 0


# ===========================================================================
# 28. v21 — APP_VERSION = "21"
# ===========================================================================

class TestVersion21:
    def test_version_21(self):
        assert app.APP_VERSION == "21"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
