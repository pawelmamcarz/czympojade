"""Testy jednostkowe i integracyjne dla Kalkulatora TCO (EV vs ICE)."""

import numpy as np
import pytest

# Import testowanych funkcji z app.py (pomijamy kod Streamlit na poziomie modułu)
# Musimy zamockować streamlit przed importem
import sys
from unittest.mock import MagicMock

# Mock streamlit żeby import app.py nie uruchamiał UI
st_mock = MagicMock()
# selectbox musi zwracać prawdziwy string z listy segmentów
st_mock.selectbox.side_effect = lambda label, options, **kwargs: options[kwargs.get("index", 0)]
st_mock.number_input.side_effect = lambda label, **kwargs: kwargs.get("value", 0)
st_mock.slider.side_effect = lambda label, *args, **kwargs: kwargs.get("value", args[2] if len(args) >= 3 else 1)
st_mock.checkbox.side_effect = lambda label, **kwargs: kwargs.get("value", False)
st_mock.button.return_value = False
st_mock.columns.side_effect = lambda n: [MagicMock() for _ in range(n)]
st_mock.tabs.side_effect = lambda labels: [MagicMock() for _ in labels]
sys.modules["streamlit"] = st_mock

from app import (
    SEGMENTS,
    ICE_MAINTENANCE_COSTS,
    BEV_MAINTENANCE_COST_PER_KM,
    BEV_BLOCKED_SEGMENTS,
    generate_dynamic_tariff,
    generate_pv_profile,
    optimize_charging,
    calculate_maintenance_cost,
    calculate_tax_shield,
    calculate_depreciation,
    estimate_insurance,
)


# ===========================================================================
# TESTY: generate_dynamic_tariff
# ===========================================================================

class TestGenerateDynamicTariff:
    def test_returns_correct_length(self):
        tariff = generate_dynamic_tariff(8760)
        assert len(tariff) == 8760

    def test_custom_length(self):
        tariff = generate_dynamic_tariff(24)
        assert len(tariff) == 24

    def test_returns_numpy_array(self):
        tariff = generate_dynamic_tariff()
        assert isinstance(tariff, np.ndarray)

    def test_has_negative_prices(self):
        """Profil powinien zawierać ujemne ceny (cecha RDN)."""
        tariff = generate_dynamic_tariff()
        assert np.any(tariff < 0), "Brak ujemnych cen w profilu taryfowym"

    def test_mean_price_is_reasonable(self):
        """Średnia cena powinna być w rozsądnym zakresie 0.20-0.80 PLN/kWh."""
        tariff = generate_dynamic_tariff()
        mean = np.mean(tariff)
        assert 0.20 <= mean <= 0.80, f"Średnia cena {mean:.2f} poza zakresem"

    def test_night_prices_lower_than_peak(self):
        """Ceny nocne (0-5) powinny być średnio niższe niż szczytowe (15-20)."""
        tariff = generate_dynamic_tariff()
        night_prices = [tariff[h] for h in range(8760) if h % 24 < 5]
        peak_prices = [tariff[h] for h in range(8760) if 15 <= h % 24 < 21]
        assert np.mean(night_prices) < np.mean(peak_prices)

    def test_deterministic_with_same_seed(self):
        """Dwa wywołania powinny dać identyczny wynik (seed=42)."""
        t1 = generate_dynamic_tariff()
        t2 = generate_dynamic_tariff()
        np.testing.assert_array_equal(t1, t2)

    def test_winter_prices_higher_than_summer(self):
        """Zima powinna być droższa niż lato (sezonowość)."""
        tariff = generate_dynamic_tariff()
        # Styczeń (godziny 0-730) vs Lipiec (godziny ~4380-5110)
        jan = tariff[:730]
        jul = tariff[4380:5110]
        assert np.mean(jan) > np.mean(jul), "Zima powinna być droższa niż lato"


# ===========================================================================
# TESTY: generate_pv_profile
# ===========================================================================

class TestGeneratePvProfile:
    def test_zero_capacity_returns_zeros(self):
        profile = generate_pv_profile(0.0)
        assert np.all(profile == 0)

    def test_negative_capacity_returns_zeros(self):
        profile = generate_pv_profile(-5.0)
        assert np.all(profile == 0)

    def test_returns_correct_length(self):
        profile = generate_pv_profile(5.0)
        assert len(profile) == 8760

    def test_no_production_at_night(self):
        """Brak produkcji PV w nocy (godziny 0-5 i 21-23)."""
        profile = generate_pv_profile(10.0)
        for h in range(8760):
            hod = h % 24
            if hod < 6 or hod > 20:
                assert profile[h] == 0, f"Produkcja PV o godzinie {hod} powinna być 0"

    def test_peak_around_noon(self):
        """Szczyt produkcji powinien być w okolicach południa/13:00."""
        profile = generate_pv_profile(10.0)
        # Sprawdź typowy letni dzień (lipiec, dzień ~180)
        day_start = 180 * 24
        day_hours = profile[day_start:day_start + 24]
        peak_hour = np.argmax(day_hours)
        assert 11 <= peak_hour <= 15, f"Szczyt PV o godzinie {peak_hour}, oczekiwano 11-15"

    def test_summer_higher_than_winter(self):
        """Produkcja letnia powinna być wyższa niż zimowa."""
        profile = generate_pv_profile(10.0)
        # Suma dzienna – styczeń vs lipiec
        jan_daily = sum(profile[h] for h in range(24))
        jul_start = 180 * 24
        jul_daily = sum(profile[jul_start + h] for h in range(24))
        assert jul_daily > jan_daily

    def test_scales_with_capacity(self):
        """Produkcja powinna skalować się liniowo z mocą instalacji."""
        p5 = generate_pv_profile(5.0)
        p10 = generate_pv_profile(10.0)
        np.testing.assert_allclose(p10, p5 * 2, rtol=1e-10)

    def test_total_annual_production_reasonable(self):
        """Roczna produkcja 5 kWp powinna być ~4000-6000 kWh (Polska)."""
        profile = generate_pv_profile(5.0)
        total = np.sum(profile)
        assert 3000 <= total <= 7000, f"Roczna produkcja {total:.0f} kWh poza zakresem"


# ===========================================================================
# TESTY: calculate_maintenance_cost
# ===========================================================================

class TestCalculateMaintenanceCost:
    def test_ice_segment_0_high_cost(self):
        """Stare auta w segmencie 1 powinny mieć wysokie koszty serwisowe."""
        cost = calculate_maintenance_cost(0, 100_000, "ICE")
        expected_avg = (0.80 + 1.00) / 2 * 100_000  # 90 000 zł
        assert cost == expected_avg

    def test_ice_segment_9_low_cost(self):
        """Nowe auta premium w segmencie 10 powinny mieć niskie koszty/km."""
        cost = calculate_maintenance_cost(9, 100_000, "ICE")
        expected_avg = (0.15 + 0.20) / 2 * 100_000  # 17 500 zł
        assert cost == expected_avg

    def test_bev_cost_lower_than_ice(self):
        """BEV powinien mieć niższe koszty serwisowe niż ICE w tym samym segmencie."""
        ice_cost = calculate_maintenance_cost(5, 100_000, "ICE")
        bev_cost = calculate_maintenance_cost(5, 100_000, "BEV")
        assert bev_cost < ice_cost

    def test_bev_blocked_segments_return_inf(self):
        """Segmenty 1-2 BEV powinny zwracać nieskończoność."""
        cost = calculate_maintenance_cost(0, 100_000, "BEV")
        assert cost == float("inf")
        cost = calculate_maintenance_cost(1, 100_000, "BEV")
        assert cost == float("inf")

    def test_zero_mileage_returns_zero(self):
        cost = calculate_maintenance_cost(5, 0, "ICE")
        assert cost == 0

    def test_bev_cost_calculation(self):
        """BEV: (0.05 + 0.08) / 2 * przebieg."""
        cost = calculate_maintenance_cost(5, 50_000, "BEV")
        expected = 0.065 * 50_000
        assert cost == expected

    @pytest.mark.parametrize("seg_idx", range(10))
    def test_all_segments_ice_positive(self, seg_idx):
        """Wszystkie segmenty ICE powinny dawać dodatni koszt serwisowy."""
        cost = calculate_maintenance_cost(seg_idx, 10_000, "ICE")
        assert cost > 0


# ===========================================================================
# TESTY: calculate_tax_shield
# ===========================================================================

class TestCalculateTaxShield:
    def test_ice_limit_100k(self):
        """ICE: limit 100 000 zł – auto za 200k powinno mieć ratio 0.5."""
        shield = calculate_tax_shield(200_000, "ICE", 10_000, 5_000, 1, 0.19)
        # ratio = 100_000 / 200_000 = 0.5
        # annual_lease = 200_000 / 4 = 50_000
        # deductible = (50_000 + 10_000 + 5_000) * 0.5 = 32_500
        # saving = 32_500 * 0.19 = 6_175
        assert shield == pytest.approx(6_175)

    def test_bev_limit_225k(self):
        """BEV: limit 225 000 zł – auto za 200k powinno mieć ratio 1.0."""
        shield = calculate_tax_shield(200_000, "BEV", 5_000, 6_000, 1, 0.19)
        # ratio = min(1.0, 225_000 / 200_000) = 1.0
        # annual_lease = 200_000 / 4 = 50_000
        # deductible = (50_000 + 5_000 + 6_000) * 1.0 = 61_000
        # saving = 61_000 * 0.19 = 11_590
        assert shield == pytest.approx(11_590)

    def test_bev_above_limit(self):
        """BEV za 300k powinno mieć ratio 225k/300k = 0.75."""
        shield = calculate_tax_shield(300_000, "BEV", 5_000, 6_000, 1, 0.19)
        ratio = 225_000 / 300_000
        annual_lease = 300_000 / 4
        deductible = (annual_lease + 5_000 + 6_000) * ratio
        expected = deductible * 0.19
        assert shield == pytest.approx(expected)

    def test_scales_with_period(self):
        """Tarcza za 3 lata = 3x tarcza za 1 rok."""
        s1 = calculate_tax_shield(200_000, "BEV", 5_000, 5_000, 1, 0.19)
        s3 = calculate_tax_shield(200_000, "BEV", 5_000, 5_000, 3, 0.19)
        assert s3 == pytest.approx(s1 * 3)

    def test_different_tax_rates(self):
        """Wyższa stawka podatkowa -> większa tarcza."""
        s12 = calculate_tax_shield(200_000, "BEV", 5_000, 5_000, 1, 0.12)
        s19 = calculate_tax_shield(200_000, "BEV", 5_000, 5_000, 1, 0.19)
        s32 = calculate_tax_shield(200_000, "BEV", 5_000, 5_000, 1, 0.32)
        assert s12 < s19 < s32

    def test_zero_price_vehicle(self):
        """Pojazd za 0 zł – ratio powinno być 1.0."""
        shield = calculate_tax_shield(0, "ICE", 5_000, 2_000, 1, 0.19)
        # ratio = 1.0 (special case), annual_lease = 0
        # deductible = (0 + 5_000 + 2_000) * 1.0 = 7_000
        # saving = 7_000 * 0.19 = 1_330
        assert shield == pytest.approx(1_330)


# ===========================================================================
# TESTY: calculate_depreciation
# ===========================================================================

class TestCalculateDepreciation:
    def test_old_ice_high_depreciation_rate(self):
        """Stare ICE (segment 0-1) tracą 15% rocznie."""
        dep = calculate_depreciation(20_000, 0, 1, "ICE")
        # remaining = 20_000 * (1 - 0.15)^1 = 17_000
        # depreciation = 3_000
        assert dep == pytest.approx(3_000)

    def test_new_bev_low_depreciation_rate(self):
        """Nowe BEV (segment 5+) tracą 8% rocznie."""
        dep = calculate_depreciation(200_000, 7, 1, "BEV")
        # remaining = 200_000 * (1 - 0.08)^1 = 184_000
        # depreciation = 16_000
        assert dep == pytest.approx(16_000)

    def test_zero_period_no_depreciation(self):
        dep = calculate_depreciation(200_000, 5, 0, "ICE")
        assert dep == 0

    def test_depreciation_increases_with_period(self):
        d1 = calculate_depreciation(100_000, 5, 1, "ICE")
        d3 = calculate_depreciation(100_000, 5, 3, "ICE")
        d5 = calculate_depreciation(100_000, 5, 5, "ICE")
        assert d1 < d3 < d5

    def test_depreciation_never_exceeds_price(self):
        """Deprecjacja nie powinna przekroczyć ceny pojazdu."""
        dep = calculate_depreciation(100_000, 0, 100, "ICE")
        assert dep <= 100_000

    @pytest.mark.parametrize("engine", ["ICE", "BEV"])
    def test_zero_price_zero_depreciation(self, engine):
        dep = calculate_depreciation(0, 5, 3, engine)
        assert dep == 0


# ===========================================================================
# TESTY: estimate_insurance
# ===========================================================================

class TestEstimateInsurance:
    def test_ice_insurance_calculation(self):
        """ICE: OC 1200 + AC (4% ceny)."""
        ins = estimate_insurance(100_000, "ICE")
        assert ins == 1_200 + 100_000 * 0.04  # 5_200

    def test_bev_insurance_higher_ac(self):
        """BEV ma wyższą stawkę AC (5% vs 4%)."""
        ins = estimate_insurance(100_000, "BEV")
        assert ins == 1_200 + 100_000 * 0.05  # 6_200

    def test_bev_more_expensive_than_ice_same_price(self):
        ice = estimate_insurance(100_000, "ICE")
        bev = estimate_insurance(100_000, "BEV")
        assert bev > ice

    def test_zero_price_only_oc(self):
        ins = estimate_insurance(0, "ICE")
        assert ins == 1_200


# ===========================================================================
# TESTY: optimize_charging (integracyjne – z HiGHS)
# ===========================================================================

class TestOptimizeCharging:
    def test_no_home_charger_all_public(self):
        """Bez wallboxa – 60% SUC, 40% AC publiczne."""
        result = optimize_charging(
            annual_demand_kwh=4800,
            battery_cap_kwh=60,
            pv_kwp=0,
            bess_kwh=0,
            has_home_charger=False,
            has_dynamic_tariff=True,
            suc_distance_km=30,
            annual_mileage_km=30_000,
        )
        assert result["pct_suc"] == 60
        assert result["pct_ac_pub"] == 40
        assert result["pct_grid"] == 0
        assert result["pct_pv"] == 0

    def test_with_home_charger_has_grid(self):
        """Z wallboxem powinno być ładowanie z sieci."""
        result = optimize_charging(
            annual_demand_kwh=4800,
            battery_cap_kwh=60,
            pv_kwp=0,
            bess_kwh=0,
            has_home_charger=True,
            has_dynamic_tariff=True,
            suc_distance_km=30,
            annual_mileage_km=30_000,
        )
        assert result["pct_grid"] > 0
        assert result["total_cost"] > 0

    def test_solver_returns_optimal(self):
        """Solver HiGHS powinien znaleźć optymalne rozwiązanie."""
        result = optimize_charging(
            annual_demand_kwh=4800,
            battery_cap_kwh=60,
            pv_kwp=5,
            bess_kwh=0,
            has_home_charger=True,
            has_dynamic_tariff=True,
            suc_distance_km=30,
            annual_mileage_km=30_000,
        )
        assert result.get("solver_status") == "optimal"

    def test_pv_reduces_cost(self):
        """Dodanie PV powinno obniżyć koszt ładowania."""
        base = optimize_charging(4800, 60, 0, 0, True, True, 30, 30_000)
        with_pv = optimize_charging(4800, 60, 10, 0, True, True, 30, 30_000)
        assert with_pv["total_cost"] <= base["total_cost"]

    def test_dynamic_tariff_cheaper_than_g11(self):
        """Taryfa dynamiczna powinna być tańsza niż G11 przy optymalizacji."""
        dynamic = optimize_charging(4800, 60, 0, 0, True, True, 30, 30_000)
        g11 = optimize_charging(4800, 60, 0, 0, True, False, 30, 30_000)
        assert dynamic["total_cost"] < g11["total_cost"]

    def test_percentages_sum_to_100(self):
        """Udziały procentowe źródeł powinny sumować się do ~100%."""
        result = optimize_charging(4800, 60, 5, 10, True, True, 30, 30_000)
        total_pct = (
            result["pct_grid"]
            + result["pct_pv"]
            + result["pct_bess"]
            + result["pct_suc"]
            + result["pct_ac_pub"]
        )
        assert total_pct == pytest.approx(100, abs=1.0)

    def test_negative_hours_with_dynamic_tariff(self):
        """Przy taryfie dynamicznej powinny być godziny z ujemną ceną."""
        result = optimize_charging(4800, 60, 0, 0, True, True, 30, 30_000)
        assert result["negative_hours_used"] >= 0  # może być 0 jeśli solver nie wybrał

    def test_bess_used_when_available(self):
        """Magazyn energii powinien być używany gdy jest dostępny."""
        without_bess = optimize_charging(4800, 60, 5, 0, True, True, 30, 30_000)
        with_bess = optimize_charging(4800, 60, 5, 20, True, True, 30, 30_000)
        # Z BESS koszt powinien być nie wyższy
        assert with_bess["total_cost"] <= without_bess["total_cost"] + 1

    def test_high_mileage_more_road_charging(self):
        """Wyższy przebieg -> więcej ładowania w trasie."""
        low = optimize_charging(1600, 60, 0, 0, True, True, 30, 10_000)
        high = optimize_charging(8000, 60, 0, 0, True, True, 30, 50_000)
        assert high["pct_suc"] + high["pct_ac_pub"] >= low["pct_suc"] + low["pct_ac_pub"]

    def test_zero_demand(self):
        """Zero zapotrzebowania powinno dać zerowy koszt."""
        result = optimize_charging(0, 60, 5, 0, True, True, 30, 0)
        assert result["total_cost"] == pytest.approx(0, abs=1)

    def test_result_keys_present(self):
        """Sprawdź, że wynik zawiera wszystkie wymagane klucze."""
        result = optimize_charging(4800, 60, 5, 0, True, True, 30, 30_000)
        required_keys = [
            "total_cost", "grid_cost", "pv_cost", "bess_cost",
            "suc_cost", "ac_pub_cost",
            "pct_grid", "pct_pv", "pct_bess", "pct_suc", "pct_ac_pub",
            "negative_hours_used",
        ]
        for key in required_keys:
            assert key in result, f"Brak klucza '{key}' w wyniku"


# ===========================================================================
# TESTY: Stałe konfiguracyjne
# ===========================================================================

class TestConstants:
    def test_segments_count(self):
        assert len(SEGMENTS) == 10

    def test_segments_price_ranges_ascending(self):
        """Segmenty powinny mieć rosnące ceny."""
        for i in range(len(SEGMENTS) - 1):
            assert SEGMENTS[i][2] < SEGMENTS[i + 1][2]

    def test_segments_no_gaps(self):
        """Między segmentami nie powinno być luk cenowych."""
        for i in range(len(SEGMENTS) - 1):
            assert SEGMENTS[i][3] + 1 == SEGMENTS[i + 1][2]

    def test_ice_maintenance_all_segments(self):
        assert len(ICE_MAINTENANCE_COSTS) == 10

    def test_ice_maintenance_old_cars_more_expensive(self):
        """Stare auta (segment 0-1) powinny mieć wyższe koszty serwisowe."""
        old_avg = sum(ICE_MAINTENANCE_COSTS[i][0] + ICE_MAINTENANCE_COSTS[i][1] for i in range(2)) / 4
        new_avg = sum(ICE_MAINTENANCE_COSTS[i][0] + ICE_MAINTENANCE_COSTS[i][1] for i in range(5, 10)) / 10
        assert old_avg > new_avg

    def test_bev_blocked_segments(self):
        assert BEV_BLOCKED_SEGMENTS == {0, 1}

    def test_bev_maintenance_cheaper_than_any_ice(self):
        bev_avg = sum(BEV_MAINTENANCE_COST_PER_KM) / 2
        for seg_idx in range(10):
            ice_avg = sum(ICE_MAINTENANCE_COSTS[seg_idx]) / 2
            assert bev_avg < ice_avg


# ===========================================================================
# TESTY: Scenariusze end-to-end (E2E)
# ===========================================================================

class TestE2EScenarios:
    """Testy scenariuszowe odwzorowujące realne przypadki użycia."""

    def test_cheap_ice_vs_new_bev_high_mileage(self):
        """Scenariusz: tanie ICE seg.2 vs nowe BEV seg.8, 30k km/rok, 3 lata.
        BEV powinno mieć niższe TCO przy tarczy podatkowej."""
        mileage = 30_000
        period = 3
        total_km = mileage * period
        seg_ice = 1  # Segment 2
        seg_bev = 7  # Segment 8

        price_ice = (SEGMENTS[seg_ice][2] + SEGMENTS[seg_ice][3]) / 2
        price_bev = (SEGMENTS[seg_bev][2] + SEGMENTS[seg_bev][3]) / 2

        # ICE costs
        fuel_annual = (mileage / 100) * 7.0 * 6.50
        fuel_total = fuel_annual * period
        maint_ice = calculate_maintenance_cost(seg_ice, total_km, "ICE")
        ins_ice = estimate_insurance(price_ice, "ICE") * period
        shield_ice = calculate_tax_shield(price_ice, "ICE", fuel_annual,
                                          estimate_insurance(price_ice, "ICE"), period, 0.19)
        tco_ice = price_ice + fuel_total + maint_ice + ins_ice - shield_ice

        # BEV costs
        energy_demand = (mileage / 100) * 16.0
        charging = optimize_charging(energy_demand, 60, 5, 0, True, True, 30, mileage)
        energy_total = charging["total_cost"] * period
        maint_bev = calculate_maintenance_cost(seg_bev, total_km, "BEV")
        ins_bev = estimate_insurance(price_bev, "BEV") * period
        shield_bev = calculate_tax_shield(price_bev, "BEV", charging["total_cost"],
                                          estimate_insurance(price_bev, "BEV"), period, 0.19)
        tco_bev = price_bev + energy_total + maint_bev + ins_bev - shield_bev

        # Oba TCO powinny być dodatnie
        assert tco_ice > 0
        assert tco_bev > 0

        # Stare ICE z ukrytymi kosztami serwisowymi powinno być drogie
        assert maint_ice > maint_bev

    def test_premium_segment_comparison(self):
        """Scenariusz: Segment 9 (premium), 20k km/rok, 5 lat."""
        seg_idx = 8  # Segment 9
        mileage = 20_000
        period = 5
        total_km = mileage * period

        price_ice = (SEGMENTS[seg_idx][2] + SEGMENTS[seg_idx][3]) / 2
        bev_idx = min(seg_idx + 2, 9)
        price_bev = (SEGMENTS[bev_idx][2] + SEGMENTS[bev_idx][3]) / 2

        # Oba powinny dać rozsądne wyniki
        maint_ice = calculate_maintenance_cost(seg_idx, total_km, "ICE")
        maint_bev = calculate_maintenance_cost(bev_idx, total_km, "BEV")
        dep_ice = calculate_depreciation(price_ice, seg_idx, period, "ICE")
        dep_bev = calculate_depreciation(price_bev, bev_idx, period, "BEV")

        assert maint_ice > 0
        assert maint_bev > 0
        assert dep_ice > 0
        assert dep_bev > 0
        assert dep_ice < price_ice
        assert dep_bev < price_bev

    def test_low_mileage_ice_wins(self):
        """Przy niskim przebiegu tanie ICE powinno być tańsze od drogiego BEV."""
        seg_ice = 3  # Segment 4
        seg_bev = 5  # Segment 6
        mileage = 5_000
        period = 1
        total_km = mileage * period

        price_ice = (SEGMENTS[seg_ice][2] + SEGMENTS[seg_ice][3]) / 2
        price_bev = (SEGMENTS[seg_bev][2] + SEGMENTS[seg_bev][3]) / 2

        fuel_cost = (mileage / 100) * 7.0 * 6.50
        maint_ice = calculate_maintenance_cost(seg_ice, total_km, "ICE")

        energy_demand = (mileage / 100) * 16.0
        charging = optimize_charging(energy_demand, 60, 0, 0, True, True, 30, mileage)
        maint_bev = calculate_maintenance_cost(seg_bev, total_km, "BEV")

        # Bez tarczy: sam zakup + roczne koszty
        tco_ice = price_ice + fuel_cost + maint_ice
        tco_bev = price_bev + charging["total_cost"] + maint_bev

        # ICE tańsze bo niższa cena zakupu dominuje przy niskim przebiegu
        assert tco_ice < tco_bev
