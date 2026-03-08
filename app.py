"""
Kalkulator TCO: Auto Elektryczne (BEV) vs Spalinowe (ICE)
z optymalizacją harmonogramu ładowania HiGHS.

Narzędzie edukacyjne i analityczne uświadamiające ukryte koszty posiadania aut.
"""

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import highspy

# ---------------------------------------------------------------------------
# KONFIGURACJA STRONY
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Kalkulator TCO – EV vs ICE",
    page_icon="⚡",
    layout="wide",
)

st.title("Kalkulator TCO: Auto Elektryczne vs Spalinowe")
st.caption(
    "Porównaj Całkowity Koszt Posiadania (TCO) z uwzględnieniem taryf dynamicznych, "
    "tarczy podatkowej 2026 i optymalizacji ładowania HiGHS."
)

# ---------------------------------------------------------------------------
# SEGMENTY RYNKOWE
# ---------------------------------------------------------------------------
SEGMENTS = [
    ("Segment 1: do 20 000 zł", "Stare używane: Opel, Fiat, Ford, Renault", 10_000, 20_000),
    ("Segment 2: 20 001 – 35 000 zł", "Używane: Škoda, VW, Toyota, Dacia", 20_001, 35_000),
    ("Segment 3: 35 001 – 50 000 zł", "Używane: Dacia Duster, Škoda Octavia", 35_001, 50_000),
    ("Segment 4: 50 001 – 75 000 zł", "Toyota Corolla, Hyundai, Kia", 50_001, 75_000),
    ("Segment 5: 75 001 – 100 000 zł", "Toyota C-HR, używane EV: starszy Leaf/Zoe", 75_001, 100_000),
    ("Segment 6: 100 001 – 140 000 zł", "Nowe tanie ICE / budżetowe EV: MG HS, Dacia Spring", 100_001, 140_000),
    ("Segment 7: 140 001 – 180 000 zł", "Toyota RAV4, VW Tiguan, tańsze nowe EV", 140_001, 180_000),
    ("Segment 8: 180 001 – 220 000 zł", "Tesla Model 3, BMW serii 3, nowe EV klasy średniej", 180_001, 220_000),
    ("Segment 9: 220 001 – 280 000 zł", "Tesla Model Y, BMW X3, Audi Q5", 220_001, 280_000),
    ("Segment 10: powyżej 280 000 zł", "Premium: Porsche, Mercedes GLE, Tesla Model S/X", 280_001, 400_000),
]

# ---------------------------------------------------------------------------
# WSPÓŁCZYNNIKI SERWISOWE  (zł / km)
# ---------------------------------------------------------------------------
ICE_MAINTENANCE_COSTS = {
    # (segment_index): (min_per_km, max_per_km)
    0: (0.80, 1.00),   # Segment 1
    1: (0.80, 1.00),   # Segment 2
    2: (0.30, 0.50),   # Segment 3
    3: (0.30, 0.50),   # Segment 4
    4: (0.30, 0.50),   # Segment 5
    5: (0.15, 0.20),   # Segment 6
    6: (0.15, 0.20),   # Segment 7
    7: (0.15, 0.20),   # Segment 8
    8: (0.15, 0.20),   # Segment 9
    9: (0.15, 0.20),   # Segment 10
}

BEV_MAINTENANCE_COST_PER_KM = (0.05, 0.08)  # segmenty 5+

# Blokowane segmenty BEV
BEV_BLOCKED_SEGMENTS = {0, 1}

# ---------------------------------------------------------------------------
# TARYFA DYNAMICZNA – symulacja profilu cenowego RDN (PLN/kWh)
# ---------------------------------------------------------------------------

def generate_dynamic_tariff(hours: int = 8760) -> np.ndarray:
    """Generuje roczny profil cen energii na Rynku Dnia Następnego (RDN).

    Odzwierciedla typowe polskie wzorce:
    - Noc (0-5): niskie / ujemne ceny
    - Rano (6-9): wzrost
    - Południe (10-14): spadek (nadwyżka PV)
    - Popołudnie (15-20): szczyt
    - Wieczór (21-23): spadek
    """
    rng = np.random.default_rng(42)
    prices = np.zeros(hours)
    for h in range(hours):
        hour_of_day = h % 24
        month = (h // 730) % 12  # przybliżenie

        # Bazowy profil dobowy (PLN / kWh netto)
        if hour_of_day < 5:
            base = 0.15
        elif hour_of_day < 6:
            base = 0.30
        elif hour_of_day < 10:
            base = 0.55
        elif hour_of_day < 14:
            base = 0.25  # nadwyżka PV
        elif hour_of_day < 15:
            base = 0.40
        elif hour_of_day < 21:
            base = 0.65  # szczyt
        elif hour_of_day < 23:
            base = 0.45
        else:
            base = 0.25

        # Sezonowość – zima droższa, lato w południe tańsze
        if month in (11, 0, 1):  # grudzień-luty
            base *= 1.3
        elif month in (5, 6, 7):  # czerwiec-sierpień
            if 10 <= hour_of_day <= 14:
                base *= 0.5  # dużo PV -> tanie

        # Szum + szansa na ujemne ceny nocą / w południe
        noise = rng.normal(0, 0.08)
        price = base + noise

        # W nocy i w południe latem – szansa na ujemne ceny
        if hour_of_day < 4 or (month in (5, 6, 7) and 11 <= hour_of_day <= 13):
            if rng.random() < 0.15:
                price = rng.uniform(-0.10, -0.01)

        prices[h] = price

    return prices


def generate_pv_profile(pv_kwp: float, hours: int = 8760) -> np.ndarray:
    """Generuje roczny profil produkcji PV (kWh/h)."""
    if pv_kwp <= 0:
        return np.zeros(hours)

    production = np.zeros(hours)
    for h in range(hours):
        hour_of_day = h % 24
        day_of_year = (h // 24) % 365
        month = (h // 730) % 12

        # Brak produkcji w nocy
        if hour_of_day < 6 or hour_of_day > 20:
            continue

        # Krzywa słoneczna (przybliżenie Gaussa)
        solar_peak = 13.0
        sigma = 3.0
        solar_factor = np.exp(-0.5 * ((hour_of_day - solar_peak) / sigma) ** 2)

        # Sezonowość – lato 2x więcej niż zima
        if month in (5, 6, 7):
            seasonal = 1.0
        elif month in (4, 8):
            seasonal = 0.8
        elif month in (3, 9):
            seasonal = 0.55
        elif month in (2, 10):
            seasonal = 0.35
        else:
            seasonal = 0.20

        production[h] = pv_kwp * solar_factor * seasonal * 0.85  # 85% PR

    return production


# ---------------------------------------------------------------------------
# OPTYMALIZACJA ŁADOWANIA BEV – HiGHS LP
# ---------------------------------------------------------------------------

def optimize_charging(
    annual_demand_kwh: float,
    battery_cap_kwh: float,
    pv_kwp: float,
    bess_kwh: float,
    has_home_charger: bool,
    has_dynamic_tariff: bool,
    suc_distance_km: float,
    annual_mileage_km: float,
) -> dict:
    """Optymalizuje roczny harmonogram ładowania BEV za pomocą HiGHS LP.

    Zwraca słownik z kosztami i procentowym udziałem źródeł.
    """
    HOURS = 8760
    tariff = generate_dynamic_tariff(HOURS)
    pv_profile = generate_pv_profile(pv_kwp, HOURS)

    # Ceny źródeł
    PRICE_PV = 0.0          # darmowa energia z PV
    PRICE_SUC = 1.60         # Supercharger DC
    PRICE_AC_PUBLIC = 1.95   # publiczne AC 11 kW
    PRICE_BESS_CYCLE = 0.02  # koszt cyklu magazynu

    # Bez taryfy dynamicznej – stała cena G11
    if not has_dynamic_tariff:
        tariff[:] = 0.72  # średnia G11 z dystrybucją

    # Wymagany udział ładowania poza domem (im dalej SUC, im wyższy przebieg)
    if suc_distance_km <= 0:
        suc_distance_km = 1.0
    road_fraction = np.clip(
        0.05 + 0.10 * (annual_mileage_km / 50_000) + 0.05 * (suc_distance_km / 50), 0.05, 0.50
    )

    road_demand_kwh = annual_demand_kwh * road_fraction
    home_demand_kwh = annual_demand_kwh - road_demand_kwh

    # Podział road_demand: 70% SUC, 30% AC publiczne
    suc_demand = road_demand_kwh * 0.70
    ac_pub_demand = road_demand_kwh * 0.30

    suc_cost = suc_demand * PRICE_SUC
    ac_pub_cost = ac_pub_demand * PRICE_AC_PUBLIC

    if not has_home_charger:
        # Całość na publicznych stacjach
        total_cost = annual_demand_kwh * 0.6 * PRICE_SUC + annual_demand_kwh * 0.4 * PRICE_AC_PUBLIC
        return {
            "total_cost": total_cost,
            "grid_cost": 0,
            "pv_cost": 0,
            "bess_cost": 0,
            "suc_cost": annual_demand_kwh * 0.6 * PRICE_SUC,
            "ac_pub_cost": annual_demand_kwh * 0.4 * PRICE_AC_PUBLIC,
            "pct_grid": 0,
            "pct_pv": 0,
            "pct_bess": 0,
            "pct_suc": 60,
            "pct_ac_pub": 40,
            "negative_hours_used": 0,
        }

    # ----- HiGHS LP -----
    # Zmienne: x_grid[h] – energia z sieci w godzinie h
    #          x_pv[h]   – energia z PV w godzinie h
    #          x_bess_charge[h] – ładowanie BESS z sieci
    #          x_bess_discharge[h] – rozładowanie BESS do auta

    h = highspy.Highs()
    h.silent()

    num_vars = HOURS * 4  # grid, pv, bess_charge, bess_discharge
    INF = highspy.kHighsInf

    # Indeksy zmiennych
    def idx_grid(t):
        return t

    def idx_pv(t):
        return HOURS + t

    def idx_bess_ch(t):
        return 2 * HOURS + t

    def idx_bess_dis(t):
        return 3 * HOURS + t

    # Dodaj zmienne
    costs = np.zeros(num_vars)
    lower = np.zeros(num_vars)
    upper = np.full(num_vars, INF)

    max_charge_rate = 11.0  # kW (AC domowa)

    for t in range(HOURS):
        # x_grid – koszt = cena taryfowa + opłaty dystrybucyjne (~0.30 zł/kWh)
        grid_price = tariff[t] + 0.30
        costs[idx_grid(t)] = grid_price
        upper[idx_grid(t)] = max_charge_rate  # max 11 kW/h

        # x_pv – darmowe
        costs[idx_pv(t)] = PRICE_PV
        upper[idx_pv(t)] = min(pv_profile[t], max_charge_rate)

        # x_bess_charge – koszt taryfowy (ładujemy magazyn z sieci)
        costs[idx_bess_ch(t)] = grid_price
        upper[idx_bess_ch(t)] = min(5.0, bess_kwh * 0.5) if bess_kwh > 0 else 0

        # x_bess_discharge – niewielki koszt cyklu
        costs[idx_bess_dis(t)] = PRICE_BESS_CYCLE
        upper[idx_bess_dis(t)] = min(5.0, bess_kwh * 0.5) if bess_kwh > 0 else 0

    h.addVars(num_vars, lower.tolist(), upper.tolist())

    # Ustaw funkcję celu (minimalizacja)
    h.changeColsCost(num_vars, np.arange(num_vars, dtype=np.int32), costs)
    h.changeObjectiveSense(highspy.ObjSense.kMinimize)

    # --- Ograniczenia ---

    # 1. Suma energii z domu pokrywa home_demand
    # sum(x_grid + x_pv + x_bess_dis) >= home_demand_kwh
    row_idx = list(range(HOURS)) + list(range(HOURS, 2 * HOURS)) + list(range(3 * HOURS, 4 * HOURS))
    row_vals = [1.0] * (3 * HOURS)
    h.addRow(home_demand_kwh, INF, len(row_idx), row_idx, row_vals)

    # 2. Bilans magazynu energii (BESS) – uproszczony:
    #    sum(bess_discharge) <= sum(bess_charge) * 0.90 (sprawność 90%)
    if bess_kwh > 0:
        bess_row_idx = (
            list(range(3 * HOURS, 4 * HOURS)) + list(range(2 * HOURS, 3 * HOURS))
        )
        bess_row_vals = [1.0] * HOURS + [-0.90] * HOURS
        h.addRow(-INF, 0.0, len(bess_row_idx), bess_row_idx, bess_row_vals)

        # Łączna pojemność BESS
        bess_cap_idx = list(range(2 * HOURS, 3 * HOURS))
        bess_cap_vals = [1.0] * HOURS
        h.addRow(0, bess_kwh * 365, len(bess_cap_idx), bess_cap_idx, bess_cap_vals)

    # 3. PV nie może przekroczyć produkcji w danej godzinie (już w upper bounds)
    # 4. Łączne ładowanie z sieci nie przekracza pojemności baterii / dobę
    #    (uproszczenie – per 24h blok)
    for day in range(365):
        day_start = day * 24
        day_end = min(day_start + 24, HOURS)
        day_indices = list(range(idx_grid(day_start), idx_grid(day_end)))
        day_vals = [1.0] * len(day_indices)
        h.addRow(0, battery_cap_kwh, len(day_indices), day_indices, day_vals)

    # Rozwiąż
    h.run()

    status = h.getModelStatus()
    if status != highspy.HighsModelStatus.kOptimal:
        # Fallback – prosta kalkulacja
        avg_price = float(np.mean(tariff)) + 0.30
        grid_cost_fallback = home_demand_kwh * avg_price
        return {
            "total_cost": grid_cost_fallback + suc_cost + ac_pub_cost,
            "grid_cost": grid_cost_fallback,
            "pv_cost": 0,
            "bess_cost": 0,
            "suc_cost": suc_cost,
            "ac_pub_cost": ac_pub_cost,
            "pct_grid": 100 * home_demand_kwh / annual_demand_kwh,
            "pct_pv": 0,
            "pct_bess": 0,
            "pct_suc": 100 * suc_demand / annual_demand_kwh,
            "pct_ac_pub": 100 * ac_pub_demand / annual_demand_kwh,
            "negative_hours_used": 0,
            "solver_status": str(status),
        }

    sol = h.getSolution()
    col_values = sol.col_value

    # Oblicz wyniki
    grid_energy = sum(col_values[idx_grid(t)] for t in range(HOURS))
    pv_energy = sum(col_values[idx_pv(t)] for t in range(HOURS))
    bess_discharge_energy = sum(col_values[idx_bess_dis(t)] for t in range(HOURS))

    grid_cost = sum(col_values[idx_grid(t)] * (tariff[t] + 0.30) for t in range(HOURS))
    bess_charge_cost = sum(col_values[idx_bess_ch(t)] * (tariff[t] + 0.30) for t in range(HOURS))
    bess_dis_cost = sum(col_values[idx_bess_dis(t)] * PRICE_BESS_CYCLE for t in range(HOURS))

    # Policz godziny z ujemną ceną, w których ładowano
    negative_hours = sum(
        1 for t in range(HOURS)
        if tariff[t] < 0 and col_values[idx_grid(t)] > 0.01
    )

    total_home_energy = grid_energy + pv_energy + bess_discharge_energy
    total_energy = total_home_energy + suc_demand + ac_pub_demand

    home_cost = grid_cost + bess_charge_cost + bess_dis_cost
    total_cost = home_cost + suc_cost + ac_pub_cost

    def safe_pct(part, whole):
        return 100 * part / whole if whole > 0 else 0

    return {
        "total_cost": total_cost,
        "grid_cost": home_cost,
        "pv_cost": 0,
        "bess_cost": bess_charge_cost + bess_dis_cost,
        "suc_cost": suc_cost,
        "ac_pub_cost": ac_pub_cost,
        "pct_grid": safe_pct(grid_energy, total_energy),
        "pct_pv": safe_pct(pv_energy, total_energy),
        "pct_bess": safe_pct(bess_discharge_energy, total_energy),
        "pct_suc": safe_pct(suc_demand, total_energy),
        "pct_ac_pub": safe_pct(ac_pub_demand, total_energy),
        "negative_hours_used": negative_hours,
        "solver_status": "optimal",
    }


# ---------------------------------------------------------------------------
# KOSZTY SERWISOWE
# ---------------------------------------------------------------------------

def calculate_maintenance_cost(segment_idx: int, mileage_km: float, engine_type: str) -> float:
    """Oblicza łączny koszt serwisowy na podstawie segmentu i przebiegu."""
    if engine_type == "ICE":
        min_c, max_c = ICE_MAINTENANCE_COSTS[segment_idx]
        avg = (min_c + max_c) / 2
        return avg * mileage_km
    else:  # BEV
        if segment_idx in BEV_BLOCKED_SEGMENTS:
            return float("inf")
        min_c, max_c = BEV_MAINTENANCE_COST_PER_KM
        avg = (min_c + max_c) / 2
        return avg * mileage_km


# ---------------------------------------------------------------------------
# TARCZA PODATKOWA 2026
# ---------------------------------------------------------------------------

def calculate_tax_shield(
    vehicle_price: float,
    engine_type: str,
    annual_fuel_cost: float,
    insurance_annual: float,
    period_years: int,
    tax_rate: float = 0.19,
) -> float:
    """Oblicza wartość tarczy podatkowej (oszczędności na podatku CIT/PIT).

    Od 2026:
    - ICE: limit 100 000 zł
    - BEV: limit 225 000 zł
    """
    if engine_type == "ICE":
        limit = 100_000
    else:
        limit = 225_000

    # Proporcja odliczenia kosztów pojazdu
    deduction_ratio = min(1.0, limit / vehicle_price) if vehicle_price > 0 else 1.0

    # Roczny koszt leasingu (uproszczenie: cena / 4 lata)
    annual_lease = vehicle_price / 4.0

    # Koszty odliczane: leasing * ratio + paliwo * ratio + ubezpieczenie * ratio
    annual_deductible = (annual_lease + annual_fuel_cost + insurance_annual) * deduction_ratio

    # Oszczędność podatkowa
    annual_tax_saving = annual_deductible * tax_rate

    return annual_tax_saving * period_years


# ---------------------------------------------------------------------------
# UTRATA WARTOŚCI (DEPRECIATION)
# ---------------------------------------------------------------------------

def calculate_depreciation(vehicle_price: float, segment_idx: int, period_years: int, engine_type: str) -> float:
    """Szacuje utratę wartości pojazdu w okresie analizy."""
    if engine_type == "ICE":
        if segment_idx <= 1:
            # Stare auta – tracą 30-50% w 3 lata
            annual_rate = 0.15
        elif segment_idx <= 4:
            annual_rate = 0.12
        else:
            annual_rate = 0.10  # nowe wolniej
    else:  # BEV
        if segment_idx <= 4:
            annual_rate = 0.12
        else:
            annual_rate = 0.08  # nowe EV trzymają wartość lepiej

    remaining = vehicle_price * ((1 - annual_rate) ** period_years)
    return vehicle_price - remaining


# ---------------------------------------------------------------------------
# UBEZPIECZENIE
# ---------------------------------------------------------------------------

def estimate_insurance(vehicle_price: float, engine_type: str) -> float:
    """Szacuje roczny koszt ubezpieczenia OC+AC."""
    base_rate = 0.04 if engine_type == "ICE" else 0.05  # BEV nieco droższe AC
    oc = 1200  # średnie OC
    ac = vehicle_price * base_rate
    return oc + ac


# ---------------------------------------------------------------------------
# GŁÓWNY INTERFEJS
# ---------------------------------------------------------------------------

# KROK 1: Segment
st.header("1. Wybierz segment cenowy")
segment_options = [f"{s[0]} – {s[1]}" for s in SEGMENTS]
selected_segment = st.selectbox("Segment rynkowy:", segment_options, index=5)
segment_idx = segment_options.index(selected_segment)
seg = SEGMENTS[segment_idx]
vehicle_price_ice = (seg[2] + seg[3]) / 2

st.info(f"Reprezentatywna cena ICE w tym segmencie: **{vehicle_price_ice:,.0f} zł**")

# BEV – cena zwykle wyższa o 1-2 segmenty
bev_segment_idx = min(segment_idx + 2, 9) if segment_idx >= 2 else None
if bev_segment_idx is not None:
    bev_seg = SEGMENTS[bev_segment_idx]
    vehicle_price_bev = (bev_seg[2] + bev_seg[3]) / 2
else:
    vehicle_price_bev = 0

bev_blocked = segment_idx in BEV_BLOCKED_SEGMENTS

if bev_blocked:
    st.warning(
        "W segmentach 1-2 auto elektryczne (BEV) to 15-letnie pojazdy ze "
        "zdegradowaną baterią – wymiana przewyższa wartość auta. "
        "Porównanie BEV dla tego segmentu jest zablokowane. "
        "Analiza pokaże jednak, ile naprawdę kosztuje tanie auto spalinowe "
        "i porówna z leasingiem nowego BEV z wyższego segmentu."
    )
    # Dla alertu: porównaj z Segmentem 8
    bev_segment_idx = 7
    bev_seg = SEGMENTS[7]
    vehicle_price_bev = (bev_seg[2] + bev_seg[3]) / 2

# KROK 2: Dane eksploatacyjne
st.header("2. Parametry eksploatacji")

col1, col2 = st.columns(2)
with col1:
    annual_mileage = st.number_input(
        "Roczny przebieg (km)", min_value=5000, max_value=200_000, value=30_000, step=5000
    )
    period_years = st.slider("Okres analizy (lata)", 1, 10, 3)

with col2:
    fuel_consumption = st.number_input(
        "Spalanie ICE (l/100 km)", min_value=3.0, max_value=20.0, value=7.0, step=0.5
    )
    fuel_price = st.number_input(
        "Cena paliwa (zł/l)", min_value=4.0, max_value=12.0, value=6.50, step=0.10
    )

st.subheader("Parametry BEV")
col3, col4 = st.columns(2)
with col3:
    battery_capacity = st.number_input(
        "Pojemność baterii BEV (kWh)", min_value=20, max_value=120, value=60, step=5
    )
    ev_consumption = st.number_input(
        "Zużycie BEV (kWh/100 km)", min_value=10.0, max_value=30.0, value=16.0, step=0.5
    )
with col4:
    has_home_charger = st.checkbox("Ładowarka domowa (wallbox AC 11 kW)", value=True)
    pv_kwp = st.number_input("Instalacja PV (kWp)", min_value=0.0, max_value=50.0, value=5.0, step=0.5)
    bess_kwh = st.number_input("Magazyn energii domowy (kWh)", min_value=0.0, max_value=50.0, value=0.0, step=1.0)

st.subheader("Taryfa i infrastruktura ładowania")
col5, col6 = st.columns(2)
with col5:
    has_dynamic_tariff = st.checkbox(
        "Taryfa dynamiczna (np. Pstryk)", value=True,
        help="Pozwala ładować po cenach RDN – w tym ujemnych nocą i w południe."
    )
with col6:
    suc_distance = st.number_input(
        "Odległość do Superchargera (km)", min_value=0, max_value=500, value=30, step=5
    )

st.subheader("Parametry podatkowe")
col7, col8 = st.columns(2)
with col7:
    use_tax_shield = st.checkbox("Uwzględnij tarczę podatkową 2026 (firma/leasing)", value=True)
with col8:
    tax_rate = st.selectbox("Stawka podatku", [0.12, 0.19, 0.32], index=1, format_func=lambda x: f"{x:.0%}")

# ---------------------------------------------------------------------------
# OBLICZENIA TCO
# ---------------------------------------------------------------------------

if st.button("Oblicz TCO", type="primary", use_container_width=True):
    total_mileage = annual_mileage * period_years

    # --- ICE ---
    fuel_cost_annual = (annual_mileage / 100) * fuel_consumption * fuel_price
    fuel_cost_total = fuel_cost_annual * period_years

    maint_ice = calculate_maintenance_cost(segment_idx, total_mileage, "ICE")
    depreciation_ice = calculate_depreciation(vehicle_price_ice, segment_idx, period_years, "ICE")
    insurance_ice = estimate_insurance(vehicle_price_ice, "ICE") * period_years

    tax_shield_ice = 0.0
    if use_tax_shield:
        tax_shield_ice = calculate_tax_shield(
            vehicle_price_ice, "ICE", fuel_cost_annual,
            estimate_insurance(vehicle_price_ice, "ICE"), period_years, tax_rate
        )

    tco_ice = vehicle_price_ice + fuel_cost_total + maint_ice + insurance_ice - tax_shield_ice
    cost_per_km_ice = tco_ice / total_mileage if total_mileage > 0 else 0

    # --- BEV ---
    annual_energy_demand = (annual_mileage / 100) * ev_consumption  # kWh / rok

    with st.spinner("Optymalizacja ładowania HiGHS..."):
        charging_result = optimize_charging(
            annual_demand_kwh=annual_energy_demand,
            battery_cap_kwh=battery_capacity,
            pv_kwp=pv_kwp,
            bess_kwh=bess_kwh,
            has_home_charger=has_home_charger,
            has_dynamic_tariff=has_dynamic_tariff,
            suc_distance_km=suc_distance,
            annual_mileage_km=annual_mileage,
        )

    energy_cost_annual = charging_result["total_cost"]
    energy_cost_total = energy_cost_annual * period_years

    maint_bev = calculate_maintenance_cost(bev_segment_idx, total_mileage, "BEV")
    depreciation_bev = calculate_depreciation(vehicle_price_bev, bev_segment_idx, period_years, "BEV")
    insurance_bev = estimate_insurance(vehicle_price_bev, "BEV") * period_years

    tax_shield_bev = 0.0
    if use_tax_shield:
        tax_shield_bev = calculate_tax_shield(
            vehicle_price_bev, "BEV", energy_cost_annual,
            estimate_insurance(vehicle_price_bev, "BEV"), period_years, tax_rate
        )

    tco_bev = vehicle_price_bev + energy_cost_total + maint_bev + insurance_bev - tax_shield_bev
    cost_per_km_bev = tco_bev / total_mileage if total_mileage > 0 else 0

    # ---------------------------------------------------------------------------
    # WYNIKI
    # ---------------------------------------------------------------------------
    st.divider()
    st.header("Wyniki analizy TCO")

    # SMART ALERT
    is_trap = (
        segment_idx <= 2
        and annual_mileage >= 30_000
        and tco_ice > tco_bev * 0.8
    )

    if is_trap:
        alt_seg = SEGMENTS[7]
        st.error(
            f"### UWAGA – Pułapka finansowa!\n\n"
            f"Wybór używanego auta spalinowego za **{vehicle_price_ice:,.0f} zł** "
            f"przy rocznym przebiegu **{annual_mileage:,} km** to pułapka.\n\n"
            f"TCO z powodu ukrytych kosztów napraw (rozrząd, hamulce, wtryski) "
            f"oraz kosztów paliwa wyniesie **{tco_ice:,.0f} zł** w {period_years} lata.\n\n"
            f"Za zbliżoną łączną kwotę TCO mógłbyś wziąć w **leasing na firmę** "
            f"nowe auto elektryczne z **{alt_seg[0]}** (np. Tesla Model 3 na gwarancji), "
            f"odliczyć **225 000 zł** w koszty zamiast 100 000 zł, "
            f"i ładować je inteligentnie zautomatyzowanym prądem po ujemnych cenach "
            f"z taryfy dynamicznej!\n\n"
            f"**TCO BEV (Segment 8): {tco_bev:,.0f} zł** vs **TCO ICE: {tco_ice:,.0f} zł**"
        )

    # Metryki główne
    tab1, tab2, tab3 = st.tabs(["Podsumowanie", "Struktura ładowania BEV", "Szczegółowe zestawienie"])

    with tab1:
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Koszt / km – ICE", f"{cost_per_km_ice:.2f} zł")
        with col_b:
            st.metric("Koszt / km – BEV", f"{cost_per_km_bev:.2f} zł")
        with col_c:
            diff = tco_ice - tco_bev
            st.metric(
                "Oszczędność BEV vs ICE",
                f"{abs(diff):,.0f} zł",
                delta=f"{'BEV tańsze' if diff > 0 else 'ICE tańsze'}",
                delta_color="normal" if diff > 0 else "inverse",
            )

        # Wykres TCO porównawczy
        categories = ["Zakup", "Paliwo / Prąd", "Serwis", "Ubezpieczenie", "Tarcza podatkowa", "RAZEM TCO"]
        ice_vals = [vehicle_price_ice, fuel_cost_total, maint_ice, insurance_ice, -tax_shield_ice, tco_ice]
        bev_vals = [vehicle_price_bev, energy_cost_total, maint_bev, insurance_bev, -tax_shield_bev, tco_bev]

        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(name="ICE (spalinowe)", x=categories, y=ice_vals, marker_color="#ef4444"))
        fig_bar.add_trace(go.Bar(name="BEV (elektryczne)", x=categories, y=bev_vals, marker_color="#22c55e"))
        fig_bar.update_layout(
            title=f"Porównanie TCO – {period_years} lata, {total_mileage:,} km",
            yaxis_title="PLN",
            barmode="group",
            height=500,
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        # Wykres kosztu narastającego w czasie
        months = list(range(1, period_years * 12 + 1))
        ice_cumulative = []
        bev_cumulative = []
        for m in months:
            frac = m / (period_years * 12)
            ice_cum = (
                vehicle_price_ice
                + fuel_cost_total * frac
                + maint_ice * frac
                + insurance_ice * frac
                - tax_shield_ice * frac
            )
            bev_cum = (
                vehicle_price_bev
                + energy_cost_total * frac
                + maint_bev * frac
                + insurance_bev * frac
                - tax_shield_bev * frac
            )
            ice_cumulative.append(ice_cum)
            bev_cumulative.append(bev_cum)

        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(
            x=months, y=ice_cumulative, name="ICE", line=dict(color="#ef4444", width=3)
        ))
        fig_line.add_trace(go.Scatter(
            x=months, y=bev_cumulative, name="BEV", line=dict(color="#22c55e", width=3)
        ))
        fig_line.update_layout(
            title="Koszt narastający w czasie (miesiące)",
            xaxis_title="Miesiąc",
            yaxis_title="Koszt skumulowany (PLN)",
            height=400,
        )
        st.plotly_chart(fig_line, use_container_width=True)

    with tab2:
        st.subheader("Struktura źródeł energii BEV (optymalizacja HiGHS)")

        labels_ch = []
        values_ch = []
        colors_ch = []

        source_map = [
            ("Sieć (taryfa dynamiczna)", charging_result["pct_grid"], "#3b82f6"),
            ("Fotowoltaika (PV)", charging_result["pct_pv"], "#f59e0b"),
            ("Magazyn energii (BESS)", charging_result["pct_bess"], "#8b5cf6"),
            ("Supercharger (DC)", charging_result["pct_suc"], "#ef4444"),
            ("Publiczne AC", charging_result["pct_ac_pub"], "#6b7280"),
        ]
        for label, pct, color in source_map:
            if pct > 0.1:
                labels_ch.append(label)
                values_ch.append(round(pct, 1))
                colors_ch.append(color)

        fig_pie = go.Figure(data=[go.Pie(
            labels=labels_ch,
            values=values_ch,
            marker=dict(colors=colors_ch),
            hole=0.4,
            textinfo="label+percent",
        )])
        fig_pie.update_layout(title="Udział źródeł energii w ładowaniu BEV", height=450)
        st.plotly_chart(fig_pie, use_container_width=True)

        col_e1, col_e2, col_e3 = st.columns(3)
        with col_e1:
            st.metric("Roczny koszt energii BEV", f"{energy_cost_annual:,.0f} zł")
        with col_e2:
            st.metric("Roczny koszt paliwa ICE", f"{fuel_cost_annual:,.0f} zł")
        with col_e3:
            st.metric(
                "Godziny z ujemną ceną prądu",
                f"{charging_result['negative_hours_used']}",
                help="Liczba godzin w roku, gdy prąd miał ujemną cenę i ładowano auto."
            )

        if charging_result["negative_hours_used"] > 0:
            st.success(
                f"Dzięki taryfie dynamicznej auto było ładowane przez "
                f"**{charging_result['negative_hours_used']} godzin** po ujemnych cenach – "
                f"operator energii dopłacał Ci za pobór prądu!"
            )

    with tab3:
        st.subheader("Szczegółowe zestawienie kosztów")

        df_detail = pd.DataFrame({
            "Kategoria": [
                "Cena zakupu / leasingu",
                f"Paliwo / Prąd ({period_years} lata)",
                f"Serwis i naprawy ({period_years} lata)",
                f"Ubezpieczenie OC+AC ({period_years} lata)",
                "Utrata wartości (deprecjacja)",
                "Tarcza podatkowa 2026 (oszczędność)",
                "RAZEM TCO",
                "Koszt / km",
            ],
            "ICE (zł)": [
                f"{vehicle_price_ice:,.0f}",
                f"{fuel_cost_total:,.0f}",
                f"{maint_ice:,.0f}",
                f"{insurance_ice:,.0f}",
                f"{depreciation_ice:,.0f}",
                f"-{tax_shield_ice:,.0f}",
                f"{tco_ice:,.0f}",
                f"{cost_per_km_ice:.2f}",
            ],
            "BEV (zł)": [
                f"{vehicle_price_bev:,.0f}",
                f"{energy_cost_total:,.0f}",
                f"{maint_bev:,.0f}",
                f"{insurance_bev:,.0f}",
                f"{depreciation_bev:,.0f}",
                f"-{tax_shield_bev:,.0f}",
                f"{tco_bev:,.0f}",
                f"{cost_per_km_bev:.2f}",
            ],
        })

        st.dataframe(df_detail, use_container_width=True, hide_index=True)

        st.caption(
            "Obliczenia uwzględniają limity podatkowe 2026 (ICE: 100 000 zł, BEV: 225 000 zł), "
            "optymalizację ładowania HiGHS z taryfą dynamiczną RDN, oraz współczynnik "
            "'rupiecia' dla tanich aut spalinowych."
        )
