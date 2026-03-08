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

    Model: 288 slotów (12 miesięcy × 24h reprezentatywnego dnia).
    Zmienne skalowane przez liczbę dni w miesiącu.
    """
    PRICE_SUC = 1.60
    PRICE_AC_PUB = 1.95
    PRICE_BESS_CYCLE = 0.02
    DIST_FEE = 0.30

    MONTHS = 12
    HPD = 24
    SLOTS = MONTHS * HPD  # 288
    DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    # Podział: dom vs trasa
    if suc_distance_km <= 0:
        suc_distance_km = 1.0
    road_frac = np.clip(
        0.05 + 0.10 * (annual_mileage_km / 50_000) + 0.05 * (suc_distance_km / 50),
        0.05, 0.50,
    )
    road_kwh = annual_demand_kwh * road_frac
    home_kwh = annual_demand_kwh - road_kwh

    suc_kwh = road_kwh * 0.70
    ac_pub_kwh = road_kwh * 0.30
    suc_cost = suc_kwh * PRICE_SUC
    ac_pub_cost = ac_pub_kwh * PRICE_AC_PUB

    if not has_home_charger:
        total = annual_demand_kwh * 0.6 * PRICE_SUC + annual_demand_kwh * 0.4 * PRICE_AC_PUB
        return {
            "total_cost": total,
            "grid_cost": 0, "pv_cost": 0, "bess_cost": 0,
            "suc_cost": annual_demand_kwh * 0.6 * PRICE_SUC,
            "ac_pub_cost": annual_demand_kwh * 0.4 * PRICE_AC_PUB,
            "pct_grid": 0, "pct_pv": 0, "pct_bess": 0,
            "pct_suc": 60, "pct_ac_pub": 40,
            "negative_hours_used": 0,
        }

    # ---- Profile cenowe i PV (288 slotów) ----
    rng = np.random.default_rng(42)
    tariff = np.zeros(SLOTS)
    pv_avail = np.zeros(SLOTS)

    for s in range(SLOTS):
        m = s // HPD
        hod = s % HPD

        # Profil cenowy RDN (PLN/kWh netto)
        if hod < 5:
            base = 0.15
        elif hod < 6:
            base = 0.30
        elif hod < 10:
            base = 0.55
        elif hod < 14:
            base = 0.25
        elif hod < 15:
            base = 0.40
        elif hod < 21:
            base = 0.65
        elif hod < 23:
            base = 0.45
        else:
            base = 0.25

        if m in (11, 0, 1):
            base *= 1.3
        elif m in (5, 6, 7) and 10 <= hod <= 14:
            base *= 0.5

        noise = rng.normal(0, 0.05)
        price = base + noise

        if hod < 4 or (m in (5, 6, 7) and 11 <= hod <= 13):
            if rng.random() < 0.15:
                price = rng.uniform(-0.10, -0.01)

        if not has_dynamic_tariff:
            price = 0.42  # stała G11 netto

        tariff[s] = price

        # Produkcja PV
        if pv_kwp > 0 and 6 <= hod <= 20:
            solar = np.exp(-0.5 * ((hod - 13.0) / 3.0) ** 2)
            if m in (5, 6, 7):
                season = 1.0
            elif m in (4, 8):
                season = 0.8
            elif m in (3, 9):
                season = 0.55
            elif m in (2, 10):
                season = 0.35
            else:
                season = 0.20
            pv_avail[s] = pv_kwp * solar * season * 0.85

    # ---- HiGHS LP ----
    solver = highspy.Highs()
    solver.silent()
    INF = highspy.kHighsInf

    max_ac = 11.0
    bess_rate = min(5.0, bess_kwh * 0.5) if bess_kwh > 0 else 0.0

    # 4 zmienne na slot: grid(0), pv(1), bess_ch(2), bess_dis(3)
    num_vars = SLOTS * 4
    costs_arr = np.zeros(num_vars)
    lower_arr = np.zeros(num_vars)
    upper_arr = np.zeros(num_vars)

    for s in range(SLOTS):
        d = DAYS[s // HPD]
        b = s * 4
        full_price = (tariff[s] + DIST_FEE) * d

        costs_arr[b] = full_price          # grid
        upper_arr[b] = max_ac

        costs_arr[b + 1] = 0.0             # pv (darmowe)
        upper_arr[b + 1] = min(pv_avail[s], max_ac)

        costs_arr[b + 2] = full_price      # bess charge
        upper_arr[b + 2] = bess_rate

        costs_arr[b + 3] = PRICE_BESS_CYCLE * d  # bess discharge
        upper_arr[b + 3] = bess_rate

    # Dodaj zmienne i ustaw koszty
    solver.addVars(num_vars, lower_arr.tolist(), upper_arr.tolist())
    for i in range(num_vars):
        solver.changeColCost(i, float(costs_arr[i]))
    solver.changeObjectiveSense(highspy.ObjSense.kMinimize)

    # Ograniczenie 1: popyt dobowy (jedno na miesiąc)
    daily_home = home_kwh / 365.0
    for m in range(MONTHS):
        idx = []
        vals = []
        for hod in range(HPD):
            b = (m * HPD + hod) * 4
            idx.extend([b, b + 1, b + 3])  # grid + pv + bess_dis
            vals.extend([1.0, 1.0, 1.0])
        solver.addRow(daily_home, INF, len(idx), idx, vals)

    # Ograniczenie 2: bilans BESS (roczny)
    if bess_kwh > 0:
        idx = []
        vals = []
        for s in range(SLOTS):
            d = float(DAYS[s // HPD])
            b = s * 4
            idx.extend([b + 3, b + 2])
            vals.extend([d, -0.90 * d])
        solver.addRow(-INF, 0.0, len(idx), idx, vals)

    # Ograniczenie 3: pojemność baterii EV na dobę
    for m in range(MONTHS):
        idx = []
        vals = []
        for hod in range(HPD):
            b = (m * HPD + hod) * 4
            idx.append(b)
            vals.append(1.0)
        solver.addRow(0.0, float(battery_cap_kwh), len(idx), idx, vals)

    # Rozwiąż
    solver.run()
    status = solver.getModelStatus()

    if status != highspy.HighsModelStatus.kOptimal:
        avg_price = float(np.mean(tariff)) + DIST_FEE
        fallback = home_kwh * avg_price
        total_e = home_kwh + suc_kwh + ac_pub_kwh
        pct = lambda p: 100 * p / total_e if total_e > 0 else 0
        return {
            "total_cost": fallback + suc_cost + ac_pub_cost,
            "grid_cost": fallback, "pv_cost": 0, "bess_cost": 0,
            "suc_cost": suc_cost, "ac_pub_cost": ac_pub_cost,
            "pct_grid": pct(home_kwh), "pct_pv": 0, "pct_bess": 0,
            "pct_suc": pct(suc_kwh), "pct_ac_pub": pct(ac_pub_kwh),
            "negative_hours_used": 0,
            "solver_status": str(status),
        }

    # Wyciągnij wyniki
    sol = solver.getSolution()
    cv = list(sol.col_value)

    grid_e = 0.0
    pv_e = 0.0
    bess_dis_e = 0.0
    home_cost = 0.0
    neg_hours = 0

    for s in range(SLOTS):
        d = DAYS[s // HPD]
        b = s * 4
        price_full = tariff[s] + DIST_FEE

        ge = cv[b] * d
        pe = cv[b + 1] * d
        bce = cv[b + 2] * d
        bde = cv[b + 3] * d

        grid_e += ge
        pv_e += pe
        bess_dis_e += bde

        home_cost += ge * price_full
        home_cost += bce * price_full
        home_cost += bde * PRICE_BESS_CYCLE

        if tariff[s] < 0 and cv[b] > 0.01:
            neg_hours += d

    total_e = grid_e + pv_e + bess_dis_e + suc_kwh + ac_pub_kwh
    total_cost = home_cost + suc_cost + ac_pub_cost

    pct = lambda p: 100 * p / total_e if total_e > 0 else 0

    return {
        "total_cost": total_cost,
        "grid_cost": home_cost,
        "pv_cost": 0,
        "bess_cost": 0,
        "suc_cost": suc_cost,
        "ac_pub_cost": ac_pub_cost,
        "pct_grid": pct(grid_e),
        "pct_pv": pct(pv_e),
        "pct_bess": pct(bess_dis_e),
        "pct_suc": pct(suc_kwh),
        "pct_ac_pub": pct(ac_pub_kwh),
        "negative_hours_used": int(neg_hours),
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
