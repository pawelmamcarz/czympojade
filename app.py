"""
Kalkulator TCO: Auto Elektryczne (BEV) vs Spalinowe (ICE)
z optymalizacją harmonogramu ładowania HiGHS.

Narzędzie edukacyjne i analityczne uświadamiające ukryte koszty posiadania aut.
"""

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import highspy

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_SCRAPING = True
except ImportError:
    HAS_SCRAPING = False

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
    "tarczy podatkowej 2026, wpływu temperatury i optymalizacji ładowania HiGHS."
)

# ---------------------------------------------------------------------------
# SEGMENTY RYNKOWE – dane CEPiK / AAA AUTO / autoDNA 2025
# Łączny rynek: ~1.74 mln transakcji (597k nowe + 1.15 mln używane)
# ---------------------------------------------------------------------------
SEGMENT_THRESHOLDS = [20_000, 35_000, 50_000, 75_000, 105_000, 145_000, 185_000, 230_000, 300_000]
SEGMENT_LABELS = [
    "do 20 tys. (stary rupieć)",
    "20-35 tys. (używany budżetowy)",
    "35-50 tys. (używany średni)",
    "50-75 tys. (używany dobry / tani nowy)",
    "75-105 tys. (nowy budżetowy)",
    "105-145 tys. (nowy kompaktowy)",
    "145-185 tys. (nowy średni)",
    "185-230 tys. (nowy wyższy średni)",
    "230-300 tys. (nowy premium)",
    "powyżej 300 tys. (premium+)",
]

# Dane rynkowe 2025 – struktura sprzedaży wg segmentu
MARKET_DATA = [
    # (transakcje_tys, nowe/uż, bev%, hev%, ice%, top_bev)
    {"vol": "162k", "mix": "0 / 162k uż.", "bev": 0.1, "hev": 0.3, "ice": 99.6,
     "top": "Tesla M3 (używana, rzadkość)"},
    {"vol": "354k", "mix": "0 / 354k uż.", "bev": 0.3, "hev": 3.0, "ice": 96.4,
     "top": "Nissan Leaf, Renault Zoe"},
    {"vol": "310k", "mix": "21k / 289k uż.", "bev": 0.9, "hev": 9.6, "ice": 89.1,
     "top": "MG 4 Standard, BYD Dolphin"},
    {"vol": "266k", "mix": "83k / 183k uż.", "bev": 1.7, "hev": 16.7, "ice": 79.7,
     "top": "MG 4, Opel Corsa-e"},
    {"vol": "251k", "mix": "145k / 106k uż.", "bev": 2.9, "hev": 41.4, "ice": 50.9,
     "top": "Tesla M3 RWD, VW ID.3"},
    {"vol": "192k", "mix": "152k / 40k uż.", "bev": 6.0, "hev": 55.0, "ice": 31.5,
     "top": "Tesla Y RWD, VW ID.4, Enyaq"},
    {"vol": "111k", "mix": "102k / 9k uż.", "bev": 12.2, "hev": 52.2, "ice": 28.1,
     "top": "Tesla Y LR, VW ID.5, BMW iX1"},
    {"vol": "61k", "mix": "58k / 3k uż.", "bev": 12.3, "hev": 30.9, "ice": 53.0,
     "top": "BMW i4, Tesla M3 LR, EQE"},
    {"vol": "29k", "mix": "28k / 2k uż.", "bev": 8.5, "hev": 15.0, "ice": 74.8,
     "top": "Audi e-tron GT, Taycan 4S"},
    {"vol": "9.5k", "mix": "9.3k / 0.2k uż.", "bev": 6.4, "hev": 0.6, "ice": 92.4,
     "top": "Taycan Turbo, EQS, BMW iX"},
]


def price_to_segment(price: float) -> int:
    """Auto-detekcja segmentu serwisowego na podstawie ceny pojazdu."""
    for i, t in enumerate(SEGMENT_THRESHOLDS):
        if price <= t:
            return i
    return 9


# ---------------------------------------------------------------------------
# WSPÓŁCZYNNIKI SERWISOWE  (zł / km)
# ---------------------------------------------------------------------------
ICE_MAINTENANCE_COSTS = {
    0: (0.80, 1.00), 1: (0.80, 1.00),  # rupiecie <35k
    2: (0.30, 0.50), 3: (0.30, 0.50),  # używane 35-75k
    4: (0.20, 0.30),                     # nowe budżetowe / dobre używane 75-105k
    5: (0.15, 0.20), 6: (0.15, 0.20),  # nowe 105-185k
    7: (0.15, 0.20), 8: (0.15, 0.20),  # nowe 185-300k
    9: (0.18, 0.25),                     # premium 300k+ (droższe części)
}

BEV_MAINTENANCE_COST_PER_KM = (0.05, 0.08)

# Nowe auta mają niższe koszty serwisowe (gwarancja, mniejsze zużycie)
NEW_CAR_MAINTENANCE_DISCOUNT = 0.6  # 60% kosztów używanego

# ---------------------------------------------------------------------------
# TEMPERATURA – średnie miesięczne w Polsce (°C) i mnożniki zużycia
# ---------------------------------------------------------------------------
MONTH_NAMES_PL = ["Sty", "Lut", "Mar", "Kwi", "Maj", "Cze",
                  "Lip", "Sie", "Wrz", "Paź", "Lis", "Gru"]
TEMPS_PL = [-2, -1, 3, 8, 14, 17, 19, 18, 14, 9, 4, 0]
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


# ---------------------------------------------------------------------------
# POBIERANIE CEN PALIW Z E-PETROL.PL
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fuel_prices() -> dict:
    """Pobiera aktualne ceny paliw z e-petrol.pl. Fallback do wartości domyślnych."""
    defaults = {"pb95": 6.50, "on": 6.40, "lpg": 3.20, "source": "domyślne"}
    if not HAS_SCRAPING:
        return defaults
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
        # e-petrol uses tables with fuel prices
        # Strategy 1: Look for specific text patterns
        text = soup.get_text()
        import re
        # Try to find patterns like "Pb95 ... 6,50" or similar
        for fuel, key in [("Pb95", "pb95"), ("Pb 95", "pb95"),
                          ("ON", "on"), ("Diesel", "on"),
                          ("LPG", "lpg")]:
            pattern = rf'{fuel}\s*[\s\-–:]*\s*(\d+[,\.]\d{{2}})'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = match.group(1).replace(",", ".")
                prices[key] = float(val)

        # Strategy 2: Look for table cells
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
                                val = cells[1].get_text(strip=True).replace(",", ".").replace("zł", "").strip()
                                prices[key] = float(val)
                            except (ValueError, IndexError):
                                pass

        if prices:
            result = {**defaults, **prices, "source": "e-petrol.pl"}
            return result
        return defaults
    except Exception:
        return defaults


# ---------------------------------------------------------------------------
# MNOŻNIKI TEMPERATUROWE
# ---------------------------------------------------------------------------

def bev_temp_multiplier(temp_c: float, driving_type: str) -> float:
    """Mnożnik zużycia BEV względem nominalnych 15°C.

    Kalibracja: Tesla Model Y LR
    - Miasto 15°C → 16.5, -15°C → 22 (×1.33)
    - Trasa  15°C → 19,   -15°C → 28 (×1.47)
    """
    if driving_type == "city":
        cold_coeff = 0.011
    else:
        cold_coeff = 0.016
    heat_coeff = 0.005
    return 1.0 + max(0, 15 - temp_c) * cold_coeff + max(0, temp_c - 25) * heat_coeff


def ice_temp_multiplier(temp_c: float, driving_type: str) -> float:
    """Mnożnik spalania ICE w zależności od temperatury."""
    if driving_type == "city":
        cold_coeff = 0.008
    else:
        cold_coeff = 0.004
    return 1.0 + max(0, 10 - temp_c) * cold_coeff


def calc_annual_consumption_bev(
    city_kwh: float, highway_kwh: float, city_pct: float,
    monthly_km: np.ndarray,
) -> tuple[float, np.ndarray]:
    """Zwraca (roczne kWh, tablica 12 miesięcznych kWh)."""
    hwy_pct = 1 - city_pct
    monthly_kwh = np.zeros(12)
    for m in range(12):
        mc = bev_temp_multiplier(TEMPS_PL[m], "city")
        mh = bev_temp_multiplier(TEMPS_PL[m], "highway")
        monthly_kwh[m] = monthly_km[m] / 100 * (
            city_pct * city_kwh * mc + hwy_pct * highway_kwh * mh
        )
    return float(monthly_kwh.sum()), monthly_kwh


def calc_annual_fuel_ice(
    city_l: float, highway_l: float, city_pct: float,
    monthly_km: np.ndarray, fuel_price: float,
) -> tuple[float, float, np.ndarray]:
    """Zwraca (roczne litry, roczny koszt PLN, tablica 12 miesięcznych litrów)."""
    hwy_pct = 1 - city_pct
    monthly_liters = np.zeros(12)
    for m in range(12):
        mc = ice_temp_multiplier(TEMPS_PL[m], "city")
        mh = ice_temp_multiplier(TEMPS_PL[m], "highway")
        monthly_liters[m] = monthly_km[m] / 100 * (
            city_pct * city_l * mc + hwy_pct * highway_l * mh
        )
    total_liters = float(monthly_liters.sum())
    return total_liters, total_liters * fuel_price, monthly_liters


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
    has_old_pv: bool,
    suc_distance_km: float,
    annual_mileage_km: float,
) -> dict:
    """Optymalizuje roczny harmonogram ładowania BEV za pomocą HiGHS LP.

    Model: 288 slotów (12 miesięcy × 24h reprezentatywnego dnia).
    HiGHS minimalizuje koszt energii, NIE liczy TCO – to tylko jedna składowa.
    """
    PRICE_SUC = 1.60
    PRICE_AC_PUB = 1.95
    PRICE_BESS_CYCLE = 0.02
    DIST_FEE = 0.30

    PV_SELF_COST = 0.0
    if has_old_pv and pv_kwp > 0:
        DIST_FEE = 0.08

    MONTHS = 12
    HPD = 24
    SLOTS = MONTHS * HPD
    DAYS = DAYS_IN_MONTH

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

    rng = np.random.default_rng(42)
    tariff = np.zeros(SLOTS)
    pv_avail = np.zeros(SLOTS)

    for s in range(SLOTS):
        m = s // HPD
        hod = s % HPD

        if hod < 5:      base = 0.15
        elif hod < 6:    base = 0.30
        elif hod < 10:   base = 0.55
        elif hod < 14:   base = 0.25
        elif hod < 15:   base = 0.40
        elif hod < 21:   base = 0.65
        elif hod < 23:   base = 0.45
        else:            base = 0.25

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
            price = 0.42

        tariff[s] = price

        if pv_kwp > 0 and 6 <= hod <= 20:
            solar = np.exp(-0.5 * ((hod - 13.0) / 3.0) ** 2)
            if m in (5, 6, 7):     season = 1.0
            elif m in (4, 8):      season = 0.8
            elif m in (3, 9):      season = 0.55
            elif m in (2, 10):     season = 0.35
            else:                  season = 0.20
            pv_avail[s] = pv_kwp * solar * season * 0.85

    solver = highspy.Highs()
    solver.silent()
    INF = highspy.kHighsInf

    max_ac = 11.0
    bess_rate = min(5.0, bess_kwh * 0.5) if bess_kwh > 0 else 0.0

    num_vars = SLOTS * 4
    costs_arr = np.zeros(num_vars)
    lower_arr = np.zeros(num_vars)
    upper_arr = np.zeros(num_vars)

    for s in range(SLOTS):
        d = DAYS[s // HPD]
        b = s * 4
        full_price = (tariff[s] + DIST_FEE) * d

        costs_arr[b] = full_price;          upper_arr[b] = max_ac
        costs_arr[b + 1] = 0.0;             upper_arr[b + 1] = min(pv_avail[s], max_ac)
        costs_arr[b + 2] = full_price;      upper_arr[b + 2] = bess_rate
        costs_arr[b + 3] = PRICE_BESS_CYCLE * d; upper_arr[b + 3] = bess_rate

    solver.addVars(num_vars, lower_arr.tolist(), upper_arr.tolist())
    for i in range(num_vars):
        solver.changeColCost(i, float(costs_arr[i]))
    solver.changeObjectiveSense(highspy.ObjSense.kMinimize)

    daily_home = home_kwh / 365.0
    for m in range(MONTHS):
        idx, vals = [], []
        for hod in range(HPD):
            b = (m * HPD + hod) * 4
            idx.extend([b, b + 1, b + 3])
            vals.extend([1.0, 1.0, 1.0])
        solver.addRow(daily_home, INF, len(idx), idx, vals)

    if bess_kwh > 0:
        idx, vals = [], []
        for s in range(SLOTS):
            d = float(DAYS[s // HPD])
            b = s * 4
            idx.extend([b + 3, b + 2])
            vals.extend([d, -0.90 * d])
        solver.addRow(-INF, 0.0, len(idx), idx, vals)

    for m in range(MONTHS):
        idx, vals = [], []
        for hod in range(HPD):
            b = (m * HPD + hod) * 4
            idx.append(b); vals.append(1.0)
        solver.addRow(0.0, float(battery_cap_kwh), len(idx), idx, vals)

    solver.run()
    status = solver.getModelStatus()

    if status != highspy.HighsModelStatus.kOptimal:
        avg_price = float(np.mean(tariff)) + DIST_FEE
        fallback = home_kwh * avg_price
        total_e = home_kwh + suc_kwh + ac_pub_kwh
        pct_fn = lambda p: 100 * p / total_e if total_e > 0 else 0
        return {
            "total_cost": fallback + suc_cost + ac_pub_cost,
            "grid_cost": fallback, "pv_cost": 0, "bess_cost": 0,
            "suc_cost": suc_cost, "ac_pub_cost": ac_pub_cost,
            "pct_grid": pct_fn(home_kwh), "pct_pv": 0, "pct_bess": 0,
            "pct_suc": pct_fn(suc_kwh), "pct_ac_pub": pct_fn(ac_pub_kwh),
            "negative_hours_used": 0, "solver_status": str(status),
        }

    sol = solver.getSolution()
    cv = list(sol.col_value)

    grid_e = pv_e = bess_dis_e = home_cost = 0.0
    neg_hours = 0

    for s in range(SLOTS):
        d = DAYS[s // HPD]
        b = s * 4
        pf = tariff[s] + DIST_FEE

        ge = cv[b] * d;     pve = cv[b+1] * d
        bce = cv[b+2] * d;  bde = cv[b+3] * d

        grid_e += ge; pv_e += pve; bess_dis_e += bde
        home_cost += ge * pf + bce * pf + bde * PRICE_BESS_CYCLE

        if tariff[s] < 0 and cv[b] > 0.01:
            neg_hours += d

    total_e = grid_e + pv_e + bess_dis_e + suc_kwh + ac_pub_kwh
    pct_fn = lambda p: 100 * p / total_e if total_e > 0 else 0

    return {
        "total_cost": home_cost + suc_cost + ac_pub_cost,
        "grid_cost": home_cost, "pv_cost": 0, "bess_cost": 0,
        "suc_cost": suc_cost, "ac_pub_cost": ac_pub_cost,
        "pct_grid": pct_fn(grid_e), "pct_pv": pct_fn(pv_e),
        "pct_bess": pct_fn(bess_dis_e),
        "pct_suc": pct_fn(suc_kwh), "pct_ac_pub": pct_fn(ac_pub_kwh),
        "negative_hours_used": int(neg_hours), "solver_status": "optimal",
    }


# ---------------------------------------------------------------------------
# KOSZTY SERWISOWE
# ---------------------------------------------------------------------------

def calculate_maintenance_cost(
    segment_idx: int, mileage_km: float, engine_type: str, is_new: bool,
) -> dict:
    """Zwraca słownik z rozbiciem kosztów serwisowych."""
    discount = NEW_CAR_MAINTENANCE_DISCOUNT if is_new else 1.0

    if engine_type == "ICE":
        min_c, max_c = ICE_MAINTENANCE_COSTS[segment_idx]
        total_per_km = (min_c + max_c) / 2 * discount
        total = total_per_km * mileage_km

        if segment_idx <= 1:
            breakdown = {
                "Przeglądy i oleje": mileage_km * 0.08 * discount,
                "Rozrząd / dwumasa": mileage_km * 0.20 * discount,
                "Hamulce (tarcze + klocki)": mileage_km * 0.10 * discount,
                "Wtryski / turbo / EGR": mileage_km * 0.18 * discount,
                "Zawieszenie / sprzęgło": mileage_km * 0.12 * discount,
                "AdBlue / filtry DPF": mileage_km * 0.05 * discount,
                "Inne awarie (po gwarancji)": max(0, total - mileage_km * 0.73 * discount),
            }
        elif segment_idx <= 4:
            breakdown = {
                "Przeglądy i oleje": mileage_km * 0.06 * discount,
                "Rozrząd / dwumasa": mileage_km * 0.08 * discount,
                "Hamulce (tarcze + klocki)": mileage_km * 0.06 * discount,
                "Wtryski / turbo / EGR": mileage_km * 0.05 * discount,
                "Zawieszenie / sprzęgło": mileage_km * 0.04 * discount,
                "AdBlue / filtry DPF": mileage_km * 0.03 * discount,
                "Inne eksploatacja": max(0, total - mileage_km * 0.32 * discount),
            }
        else:
            breakdown = {
                "Przeglądy ASO (olej, filtry)": mileage_km * 0.08 * discount,
                "Hamulce (tarcze + klocki)": mileage_km * 0.03 * discount,
                "AdBlue": mileage_km * 0.02 * discount,
                "Inne eksploatacja": max(0, total - mileage_km * 0.13 * discount),
            }
        breakdown = {k: max(0, v) for k, v in breakdown.items()}
        return {"total": total, "per_km": total_per_km, "breakdown": breakdown}
    else:  # BEV
        min_c, max_c = BEV_MAINTENANCE_COST_PER_KM
        total_per_km = (min_c + max_c) / 2 * discount
        total = total_per_km * mileage_km
        breakdown = {
            "Filtry kabinowe": mileage_km * 0.01 * discount,
            "Płyn hamulcowy": mileage_km * 0.005 * discount,
            "Hamulce (rzadsze – rekuperacja)": mileage_km * 0.01 * discount,
            "Opony (cięższe auto)": mileage_km * 0.025 * discount,
            "Przegląd / diagnostyka": mileage_km * 0.015 * discount,
        }
        breakdown = {k: max(0, v) for k, v in breakdown.items()}
        return {"total": total, "per_km": total_per_km, "breakdown": breakdown}


# ---------------------------------------------------------------------------
# TARCZA PODATKOWA 2026
# ---------------------------------------------------------------------------

def calculate_tax_shield(
    vehicle_price: float, engine_type: str,
    annual_fuel_cost: float, insurance_annual: float,
    period_years: int, tax_rate: float = 0.19,
) -> float:
    limit = 100_000 if engine_type == "ICE" else 225_000
    deduction_ratio = min(1.0, limit / vehicle_price) if vehicle_price > 0 else 1.0
    annual_lease = vehicle_price / 4.0
    annual_deductible = (annual_lease + annual_fuel_cost + insurance_annual) * deduction_ratio
    return annual_deductible * tax_rate * period_years


def calculate_depreciation(vehicle_price, segment_idx, period_years, engine_type, is_new):
    if is_new:
        # Nowe auta tracą więcej w pierwszych latach
        rate = 0.15 if engine_type == "ICE" else 0.12
    else:
        if engine_type == "ICE":
            rate = 0.15 if segment_idx <= 1 else (0.12 if segment_idx <= 4 else 0.10)
        else:
            rate = 0.12 if segment_idx <= 4 else 0.08
    return vehicle_price - vehicle_price * ((1 - rate) ** period_years)


def estimate_insurance(vehicle_price, engine_type):
    return 1200 + vehicle_price * (0.04 if engine_type == "ICE" else 0.05)


# ===========================================================================
# GŁÓWNY INTERFEJS
# ===========================================================================

# ---- Pobierz ceny paliw ----
fuel_data = fetch_fuel_prices()

# KROK 1: Dane pojazdu
st.header("1. Twoje pojazdy")

is_new = st.radio(
    "Stan pojazdu",
    ["Nowy", "Używany"],
    horizontal=True,
    help=(
        "Nowe BEV i ICE w tej samej klasie kosztują podobnie. "
        "Używane ICE są tańsze, ale mają wyższe koszty serwisowe."
    ),
) == "Nowy"

col_ice, col_bev = st.columns(2)

with col_ice:
    st.subheader("ICE (spalinowe)")
    ice_model = st.text_input(
        "Marka i model ICE",
        value="Toyota Corolla 2024" if is_new else "Toyota Corolla 2019",
        help="Np. Toyota Corolla 1.8, VW Golf 2.0 TDI, Dacia Duster 1.5 dCi",
    )
    vehicle_price_ice = st.number_input(
        "Cena zakupu / leasingu ICE (zł)",
        min_value=5_000, max_value=1_000_000,
        value=140_000 if is_new else 65_000,
        step=5_000,
        help="Wpisz cenę swojego pojazdu – z otomoto.pl, salonu lub umowy leasingu.",
    )
    fuel_type = st.selectbox(
        "Rodzaj paliwa",
        ["Benzyna (PB95)", "Diesel (ON)", "LPG"],
        index=0,
    )

with col_bev:
    st.subheader("BEV (elektryczne)")
    bev_model = st.text_input(
        "Marka i model BEV",
        value="Tesla Model Y LR 2024" if is_new else "Tesla Model 3 SR+ 2021",
        help="Np. Tesla Model Y LR, BYD Atto 3, Hyundai Ioniq 5",
    )
    vehicle_price_bev = st.number_input(
        "Cena zakupu / leasingu BEV (zł)",
        min_value=5_000, max_value=1_000_000,
        value=195_000 if is_new else 120_000,
        step=5_000,
        help="Wpisz cenę swojego pojazdu – z otomoto.pl, salonu lub umowy leasingu.",
    )

# Auto-detect segments for maintenance calculations
segment_idx_ice = price_to_segment(vehicle_price_ice)
segment_idx_bev = price_to_segment(vehicle_price_bev)

with st.expander("Kontekst rynkowy i segment serwisowy"):
    st.write(f"**ICE** ({vehicle_price_ice:,.0f} zł) → {SEGMENT_LABELS[segment_idx_ice]}")
    st.write(f"**BEV** ({vehicle_price_bev:,.0f} zł) → {SEGMENT_LABELS[segment_idx_bev]}")

    # Dane rynkowe dla wybranych segmentów
    for label, idx in [("ICE", segment_idx_ice), ("BEV", segment_idx_bev)]:
        md = MARKET_DATA[idx]
        st.markdown(
            f"**Segment {SEGMENT_LABELS[idx]}**: {md['vol']} transakcji/rok "
            f"({md['mix']}). "
            f"BEV {md['bev']}% | HEV {md['hev']}% | ICE {md['ice']}%. "
            f"Top BEV: {md['top']}"
        )

    # Tabela pełna
    st.markdown("**Struktura rynku PL 2025** (dane CEPiK / AAA AUTO / autoDNA)")
    market_rows = []
    for i, (lbl, md) in enumerate(zip(SEGMENT_LABELS, MARKET_DATA)):
        is_current = i == segment_idx_ice or i == segment_idx_bev
        market_rows.append({
            "Segment": (">> " if is_current else "") + lbl,
            "Wolumen": md["vol"],
            "Nowe/Uż.": md["mix"],
            "BEV %": f"{md['bev']:.1f}%",
            "HEV %": f"{md['hev']:.1f}%",
            "ICE %": f"{md['ice']:.1f}%",
            "Top BEV": md["top"],
        })
    st.dataframe(pd.DataFrame(market_rows), hide_index=True, use_container_width=True)
    st.caption(
        "Segment wpływa na szacowane koszty serwisowe. "
        "Tańsze auta (segmenty 1-2) mają współczynnik 'rupiecia'. "
        "Punkt zwrotny BEV: 105-185 tys. zł (6-12% udziału, HEV 50%+)."
    )

# KROK 2: Parametry eksploatacji
st.header("2. Parametry eksploatacji")

col1, col2 = st.columns(2)
with col1:
    annual_mileage = st.number_input(
        "Roczny przebieg (km)", min_value=5000, max_value=200_000, value=30_000, step=5000
    )
    period_years = st.slider("Okres analizy (lata)", 1, 10, 3)
with col2:
    city_pct = st.slider(
        "Udział jazdy miejskiej (%)", 0, 100, 60,
        help="Reszta to trasa / autostrada."
    ) / 100.0

    # Cena paliwa z e-petrol lub ręcznie
    if "Benzyna" in fuel_type:
        default_fuel = fuel_data["pb95"]
    elif "Diesel" in fuel_type:
        default_fuel = fuel_data["on"]
    else:
        default_fuel = fuel_data["lpg"]

    fuel_price = st.number_input(
        f"Cena paliwa (zł/l) – {fuel_data['source']}",
        min_value=2.0, max_value=15.0, value=default_fuel, step=0.10,
        help="Cena pobierana automatycznie z e-petrol.pl. Możesz wpisać własną.",
    )

st.subheader("Spalanie ICE (nominalne)")
col_ic1, col_ic2 = st.columns(2)
with col_ic1:
    ice_city_l = st.number_input(
        "Miasto (l/100 km)", min_value=3.0, max_value=25.0, value=8.5, step=0.5,
        help="Spalanie w cyklu miejskim.",
    )
with col_ic2:
    ice_highway_l = st.number_input(
        "Trasa (l/100 km)", min_value=3.0, max_value=20.0, value=6.0, step=0.5,
        help="Spalanie w cyklu pozamiejskim / autostrada.",
    )

st.subheader("Zużycie BEV (nominalne przy 15°C)")
col_bc1, col_bc2 = st.columns(2)
with col_bc1:
    bev_city_kwh = st.number_input(
        "Miasto (kWh/100 km)", min_value=8.0, max_value=35.0, value=16.5, step=0.5,
        help="Np. Tesla Model Y LR: ~16-17 kWh przy 15°C.",
    )
with col_bc2:
    bev_highway_kwh = st.number_input(
        "Trasa (kWh/100 km)", min_value=10.0, max_value=40.0, value=19.0, step=0.5,
        help="Np. Tesla Model Y LR: ~19 kWh przy 15°C.",
    )

st.subheader("Parametry BEV – bateria i ładowanie")
col3, col4 = st.columns(2)
with col3:
    battery_capacity = st.number_input(
        "Pojemność baterii BEV (kWh)", min_value=20, max_value=120, value=75, step=5
    )
    has_home_charger = st.checkbox("Ładowarka domowa (wallbox AC 11 kW)", value=True)
with col4:
    pv_kwp = st.number_input("Instalacja PV (kWp)", min_value=0.0, max_value=50.0, value=5.0, step=0.5)
    bess_kwh = st.number_input("Magazyn energii domowy (kWh)", min_value=0.0, max_value=150.0, value=0.0, step=5.0)

st.subheader("Taryfa energetyczna i infrastruktura ładowania")
col5, col6 = st.columns(2)
with col5:
    tariff_option = st.selectbox(
        "Model rozliczenia PV / taryfa",
        [
            "Stare zasady PV (net-metering 1:0.8)",
            "Nowe zasady PV (net-billing, taryfa G11/G12)",
            "Nowe zasady PV + taryfa dynamiczna (Pstryk)",
        ],
        index=2,
        help=(
            "Stare zasady: prosumenci przed 2022 – magazynowanie 1:0.8 w sieci.\n"
            "Nowe zasady: net-billing po cenach rynkowych.\n"
            "Pstryk: taryfa dynamiczna RDN – ceny godzinowe, czasem ujemne."
        ),
    )
    has_dynamic_tariff = "Pstryk" in tariff_option
    has_old_pv = "Stare zasady" in tariff_option
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
# PODGLĄD WPŁYWU TEMPERATURY
# ---------------------------------------------------------------------------
with st.expander("Podgląd wpływu temperatury na zużycie (miesięcznie)"):
    temp_rows = []
    for m in range(12):
        t = TEMPS_PL[m]
        bev_mc = bev_temp_multiplier(t, "city")
        bev_mh = bev_temp_multiplier(t, "highway")
        ice_mc = ice_temp_multiplier(t, "city")
        ice_mh = ice_temp_multiplier(t, "highway")
        temp_rows.append({
            "Miesiąc": MONTH_NAMES_PL[m],
            "Temp. (°C)": t,
            "BEV miasto": f"{bev_city_kwh * bev_mc:.1f} kWh",
            "BEV trasa": f"{bev_highway_kwh * bev_mh:.1f} kWh",
            "ICE miasto": f"{ice_city_l * ice_mc:.1f} l",
            "ICE trasa": f"{ice_highway_l * ice_mh:.1f} l",
            "BEV mnożnik": f"×{(city_pct * bev_mc + (1 - city_pct) * bev_mh):.2f}",
            "ICE mnożnik": f"×{(city_pct * ice_mc + (1 - city_pct) * ice_mh):.2f}",
        })
    st.dataframe(pd.DataFrame(temp_rows), use_container_width=True, hide_index=True)
    st.caption(
        "BEV: nominalne przy 15°C. Zimą pompa ciepła i ogrzewanie baterii zwiększają zużycie. "
        "ICE: nominalne przy 10°C. Zimny rozruch i paliwo zimowe zwiększają spalanie."
    )

# ===========================================================================
# OBLICZENIA TCO
# ===========================================================================

if st.button("Oblicz TCO", type="primary", use_container_width=True):
    total_mileage = annual_mileage * period_years
    monthly_km = np.array([annual_mileage * d / 365 for d in DAYS_IN_MONTH])

    # --- ICE ---
    ice_liters_annual, fuel_cost_annual, ice_monthly_liters = calc_annual_fuel_ice(
        ice_city_l, ice_highway_l, city_pct, monthly_km, fuel_price,
    )
    fuel_cost_total = fuel_cost_annual * period_years

    nominal_ice_l = city_pct * ice_city_l + (1 - city_pct) * ice_highway_l
    nominal_ice_liters = annual_mileage / 100 * nominal_ice_l
    ice_temp_penalty_pct = (ice_liters_annual / nominal_ice_liters - 1) * 100 if nominal_ice_liters > 0 else 0

    maint_ice_data = calculate_maintenance_cost(segment_idx_ice, total_mileage, "ICE", is_new)
    maint_ice = maint_ice_data["total"]
    depreciation_ice = calculate_depreciation(vehicle_price_ice, segment_idx_ice, period_years, "ICE", is_new)
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
    annual_energy_demand, bev_monthly_kwh = calc_annual_consumption_bev(
        bev_city_kwh, bev_highway_kwh, city_pct, monthly_km,
    )

    nominal_bev_kwh_100 = city_pct * bev_city_kwh + (1 - city_pct) * bev_highway_kwh
    nominal_bev_annual = annual_mileage / 100 * nominal_bev_kwh_100
    bev_temp_penalty_pct = (annual_energy_demand / nominal_bev_annual - 1) * 100 if nominal_bev_annual > 0 else 0

    with st.spinner("Optymalizacja ładowania HiGHS..."):
        charging_result = optimize_charging(
            annual_demand_kwh=annual_energy_demand,
            battery_cap_kwh=battery_capacity,
            pv_kwp=pv_kwp,
            bess_kwh=bess_kwh,
            has_home_charger=has_home_charger,
            has_dynamic_tariff=has_dynamic_tariff,
            has_old_pv=has_old_pv,
            suc_distance_km=suc_distance,
            annual_mileage_km=annual_mileage,
        )

    energy_cost_annual = charging_result["total_cost"]
    energy_cost_total = energy_cost_annual * period_years

    maint_bev_data = calculate_maintenance_cost(segment_idx_bev, total_mileage, "BEV", is_new)
    maint_bev = maint_bev_data["total"]
    depreciation_bev = calculate_depreciation(vehicle_price_bev, segment_idx_bev, period_years, "BEV", is_new)
    insurance_bev = estimate_insurance(vehicle_price_bev, "BEV") * period_years

    tax_shield_bev = 0.0
    if use_tax_shield:
        tax_shield_bev = calculate_tax_shield(
            vehicle_price_bev, "BEV", energy_cost_annual,
            estimate_insurance(vehicle_price_bev, "BEV"), period_years, tax_rate
        )

    tco_bev = vehicle_price_bev + energy_cost_total + maint_bev + insurance_bev - tax_shield_bev
    cost_per_km_bev = tco_bev / total_mileage if total_mileage > 0 else 0

    # ===================================================================
    # WYNIKI
    # ===================================================================
    st.divider()
    st.header("Wyniki analizy TCO")
    st.caption(f"**{ice_model}** vs **{bev_model}** | {total_mileage:,} km w {period_years} lata")

    # SMART ALERT
    is_cheap_ice = vehicle_price_ice <= 35_000 and not is_new
    is_trap = is_cheap_ice and annual_mileage >= 25_000 and tco_ice > tco_bev * 0.85
    if is_trap:
        st.error(
            f"### UWAGA – Pułapka taniego spalinowego!\n\n"
            f"**{ice_model}** za **{vehicle_price_ice:,.0f} zł** "
            f"przy przebiegu **{annual_mileage:,} km/rok** generuje ukryte koszty.\n\n"
            f"TCO z naprawami (rozrząd, hamulce, wtryski) i paliwem wyniesie "
            f"**{tco_ice:,.0f} zł** w {period_years} lata.\n\n"
            f"Za zbliżoną kwotę TCO mógłbyś wziąć w **leasing na firmę** "
            f"nowe BEV z limitem podatkowym **225 000 zł** (vs 100 000 zł ICE) "
            f"i ładować inteligentnie po ujemnych cenach!\n\n"
            f"**TCO BEV: {tco_bev:,.0f} zł** vs **TCO ICE: {tco_ice:,.0f} zł**"
        )

    tab1, tab2, tab3, tab4 = st.tabs([
        "Podsumowanie", "Wpływ temperatury", "Struktura ładowania BEV", "Szczegółowe zestawienie"
    ])

    with tab1:
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric(f"Koszt / km – {ice_model.split()[0]}", f"{cost_per_km_ice:.2f} zł")
        with col_b:
            st.metric(f"Koszt / km – {bev_model.split()[0]}", f"{cost_per_km_bev:.2f} zł")
        with col_c:
            diff = tco_ice - tco_bev
            st.metric(
                "Oszczędność BEV vs ICE", f"{abs(diff):,.0f} zł",
                delta=f"{'BEV tańsze' if diff > 0 else 'ICE tańsze'}",
                delta_color="normal" if diff > 0 else "inverse",
            )

        categories = ["Zakup", "Paliwo / Prąd", "Serwis", "Ubezpieczenie", "Tarcza podatkowa", "RAZEM TCO"]
        ice_vals = [vehicle_price_ice, fuel_cost_total, maint_ice, insurance_ice, -tax_shield_ice, tco_ice]
        bev_vals = [vehicle_price_bev, energy_cost_total, maint_bev, insurance_bev, -tax_shield_bev, tco_bev]

        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            name=f"ICE – {ice_model}", x=categories, y=ice_vals, marker_color="#ef4444",
        ))
        fig_bar.add_trace(go.Bar(
            name=f"BEV – {bev_model}", x=categories, y=bev_vals, marker_color="#22c55e",
        ))
        fig_bar.update_layout(
            title=f"Porównanie TCO – {period_years} lata, {total_mileage:,} km",
            yaxis_title="PLN", barmode="group", height=500,
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        months_range = list(range(1, period_years * 12 + 1))
        ice_cum, bev_cum = [], []
        for mo in months_range:
            frac = mo / (period_years * 12)
            ice_cum.append(vehicle_price_ice + (fuel_cost_total + maint_ice + insurance_ice) * frac - tax_shield_ice * frac)
            bev_cum.append(vehicle_price_bev + (energy_cost_total + maint_bev + insurance_bev) * frac - tax_shield_bev * frac)

        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(
            x=months_range, y=ice_cum, name=f"ICE – {ice_model}",
            line=dict(color="#ef4444", width=3),
        ))
        fig_line.add_trace(go.Scatter(
            x=months_range, y=bev_cum, name=f"BEV – {bev_model}",
            line=dict(color="#22c55e", width=3),
        ))
        fig_line.update_layout(
            title="Koszt narastający w czasie",
            xaxis_title="Miesiąc", yaxis_title="Koszt skumulowany (PLN)", height=400,
        )
        st.plotly_chart(fig_line, use_container_width=True)

    with tab2:
        st.subheader("Wpływ temperatury na roczne zużycie")

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.metric(
                "BEV: narzut temperaturowy (roczny)",
                f"+{bev_temp_penalty_pct:.1f}%",
                delta=f"+{annual_energy_demand - nominal_bev_annual:.0f} kWh / rok",
                delta_color="inverse",
            )
            st.metric("BEV: zużycie nominalne (15°C)", f"{nominal_bev_annual:.0f} kWh/rok")
            st.metric("BEV: zużycie rzeczywiste (z temp.)", f"{annual_energy_demand:.0f} kWh/rok")
        with col_t2:
            st.metric(
                "ICE: narzut temperaturowy (roczny)",
                f"+{ice_temp_penalty_pct:.1f}%",
                delta=f"+{ice_liters_annual - nominal_ice_liters:.0f} l / rok",
                delta_color="inverse",
            )
            st.metric("ICE: spalanie nominalne", f"{nominal_ice_liters:.0f} l/rok")
            st.metric("ICE: spalanie rzeczywiste (z temp.)", f"{ice_liters_annual:.0f} l/rok")

        fig_temp = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            subplot_titles=("BEV: zużycie miesięczne (kWh)", "ICE: spalanie miesięczne (litry)"),
            vertical_spacing=0.12,
        )

        nominal_bev_monthly = monthly_km / 100 * nominal_bev_kwh_100
        fig_temp.add_trace(go.Bar(
            x=MONTH_NAMES_PL, y=nominal_bev_monthly, name="BEV nominalne (15°C)",
            marker_color="#86efac", opacity=0.7,
        ), row=1, col=1)
        fig_temp.add_trace(go.Bar(
            x=MONTH_NAMES_PL, y=bev_monthly_kwh, name="BEV z temp.",
            marker_color="#22c55e",
        ), row=1, col=1)

        nominal_ice_monthly = monthly_km / 100 * nominal_ice_l
        fig_temp.add_trace(go.Bar(
            x=MONTH_NAMES_PL, y=nominal_ice_monthly, name="ICE nominalne",
            marker_color="#fca5a5", opacity=0.7,
        ), row=2, col=1)
        fig_temp.add_trace(go.Bar(
            x=MONTH_NAMES_PL, y=ice_monthly_liters, name="ICE z temp.",
            marker_color="#ef4444",
        ), row=2, col=1)

        fig_temp.add_trace(go.Scatter(
            x=MONTH_NAMES_PL, y=TEMPS_PL, name="Temperatura (°C)",
            line=dict(color="#3b82f6", width=2, dash="dot"),
            yaxis="y5",
        ), row=1, col=1)

        fig_temp.update_layout(height=600, barmode="overlay")
        st.plotly_chart(fig_temp, use_container_width=True)

        st.caption(
            "Przy -15°C Tesla Model Y LR zużywa ~28 kWh/100km na trasie (vs 19 przy 15°C) "
            "i ~22 w mieście (vs 16.5). ICE też pali zimą więcej: zimny silnik, gęstsze "
            "powietrze, paliwo zimowe – w mieście nawet +15-20%."
        )

    with tab3:
        st.subheader("Struktura źródeł energii BEV (optymalizacja HiGHS)")
        st.caption(
            "HiGHS LP minimalizuje roczny koszt energii BEV (sieć + PV + BESS + Supercharger). "
            "To jedna ze składowych TCO – samo TCO to proste sumowanie wszystkich kosztów."
        )

        labels_ch, values_ch, colors_ch = [], [], []
        source_map = [
            ("Sieć (taryfa)", charging_result["pct_grid"], "#3b82f6"),
            ("Fotowoltaika (PV)", charging_result["pct_pv"], "#f59e0b"),
            ("Magazyn energii (BESS)", charging_result["pct_bess"], "#8b5cf6"),
            ("Supercharger (DC)", charging_result["pct_suc"], "#ef4444"),
            ("Publiczne AC", charging_result["pct_ac_pub"], "#6b7280"),
        ]
        for label, pct_val, color in source_map:
            if pct_val > 0.1:
                labels_ch.append(label)
                values_ch.append(round(pct_val, 1))
                colors_ch.append(color)

        fig_pie = go.Figure(data=[go.Pie(
            labels=labels_ch, values=values_ch,
            marker=dict(colors=colors_ch), hole=0.4, textinfo="label+percent",
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
                help="Godziny w roku, gdy prąd miał ujemną cenę i ładowano auto."
            )

        if charging_result["negative_hours_used"] > 0:
            st.success(
                f"Dzięki taryfie dynamicznej auto było ładowane przez "
                f"**{charging_result['negative_hours_used']} godzin** po ujemnych cenach – "
                f"operator energii dopłacał Ci za pobór prądu!"
            )

    with tab4:
        st.subheader("Szczegółowe zestawienie kosztów")

        avg_bev_real = annual_energy_demand / annual_mileage * 100 if annual_mileage > 0 else 0
        avg_ice_real = ice_liters_annual / annual_mileage * 100 if annual_mileage > 0 else 0

        df_detail = pd.DataFrame({
            "Kategoria": [
                "Pojazd",
                "Stan",
                "Cena zakupu / leasingu",
                f"Paliwo / Prąd ({period_years} lata)",
                f"Serwis i naprawy ({period_years} lata)",
                f"Ubezpieczenie OC+AC ({period_years} lata)",
                "Utrata wartości (deprecjacja)",
                "Tarcza podatkowa 2026 (oszczędność)",
                "RAZEM TCO",
                "Koszt / km",
                "Śr. zużycie (z temp.)",
                "Narzut temperaturowy",
            ],
            "ICE": [
                ice_model,
                "Nowy" if is_new else "Używany",
                f"{vehicle_price_ice:,.0f} zł",
                f"{fuel_cost_total:,.0f} zł",
                f"{maint_ice:,.0f} zł",
                f"{insurance_ice:,.0f} zł",
                f"{depreciation_ice:,.0f} zł",
                f"-{tax_shield_ice:,.0f} zł",
                f"{tco_ice:,.0f} zł",
                f"{cost_per_km_ice:.2f} zł",
                f"{avg_ice_real:.1f} l/100km",
                f"+{ice_temp_penalty_pct:.1f}%",
            ],
            "BEV": [
                bev_model,
                "Nowy" if is_new else "Używany",
                f"{vehicle_price_bev:,.0f} zł",
                f"{energy_cost_total:,.0f} zł",
                f"{maint_bev:,.0f} zł",
                f"{insurance_bev:,.0f} zł",
                f"{depreciation_bev:,.0f} zł",
                f"-{tax_shield_bev:,.0f} zł",
                f"{tco_bev:,.0f} zł",
                f"{cost_per_km_bev:.2f} zł",
                f"{avg_bev_real:.1f} kWh/100km",
                f"+{bev_temp_penalty_pct:.1f}%",
            ],
        })

        st.dataframe(df_detail, use_container_width=True, hide_index=True)

        # --- ROZBICIE KOSZTÓW SERWISOWYCH ---
        st.subheader("Rozbicie kosztów serwisowych")

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.markdown(f"**{ice_model} – serwis i naprawy**")
            if maint_ice_data["breakdown"]:
                breakdown_rows = [
                    {"Kategoria": k, "Koszt (zł)": f"{v:,.0f}"}
                    for k, v in maint_ice_data["breakdown"].items()
                    if v > 0
                ]
                breakdown_rows.append({
                    "Kategoria": "RAZEM",
                    "Koszt (zł)": f"{maint_ice:,.0f}",
                })
                st.dataframe(
                    pd.DataFrame(breakdown_rows),
                    hide_index=True, use_container_width=True,
                )
                st.caption(f"Koszt serwisowy: {maint_ice_data['per_km']:.2f} zł/km")

        with col_m2:
            st.markdown(f"**{bev_model} – serwis i naprawy**")
            if maint_bev_data["breakdown"]:
                breakdown_rows = [
                    {"Kategoria": k, "Koszt (zł)": f"{v:,.0f}"}
                    for k, v in maint_bev_data["breakdown"].items()
                    if v > 0
                ]
                breakdown_rows.append({
                    "Kategoria": "RAZEM",
                    "Koszt (zł)": f"{maint_bev:,.0f}",
                })
                st.dataframe(
                    pd.DataFrame(breakdown_rows),
                    hide_index=True, use_container_width=True,
                )
                st.caption(f"Koszt serwisowy: {maint_bev_data['per_km']:.2f} zł/km")

        # Pie chart serwisowy
        fig_maint = make_subplots(
            rows=1, cols=2,
            subplot_titles=(f"ICE: {ice_model}", f"BEV: {bev_model}"),
            specs=[[{"type": "pie"}, {"type": "pie"}]],
        )
        ice_bd = {k: v for k, v in maint_ice_data["breakdown"].items() if v > 0}
        bev_bd = {k: v for k, v in maint_bev_data["breakdown"].items() if v > 0}

        if ice_bd:
            fig_maint.add_trace(go.Pie(
                labels=list(ice_bd.keys()), values=list(ice_bd.values()),
                hole=0.3, textinfo="label+percent",
            ), row=1, col=1)
        if bev_bd:
            fig_maint.add_trace(go.Pie(
                labels=list(bev_bd.keys()), values=list(bev_bd.values()),
                hole=0.3, textinfo="label+percent",
            ), row=1, col=2)
        fig_maint.update_layout(
            title="Struktura kosztów serwisowych",
            height=400, showlegend=False,
        )
        st.plotly_chart(fig_maint, use_container_width=True)

        st.caption(
            "Obliczenia uwzględniają: limity podatkowe 2026 (ICE: 100k zł, BEV: 225k zł), "
            "optymalizację ładowania HiGHS z taryfą dynamiczną RDN, wpływ temperatury "
            "na zużycie obu napędów, oraz rozbicie kosztów serwisowych. "
            "Ceny paliw aktualizowane z e-petrol.pl."
        )
