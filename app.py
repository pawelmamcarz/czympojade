# Kalkulator TCO: Auto Elektryczne (BEV) vs Spalinowe (ICE)
# z optymalizacją harmonogramu ładowania HiGHS.
# Narzędzie edukacyjne i analityczne uświadamiające ukryte koszty posiadania aut.

APP_VERSION = "0.10.0"

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

# ---------------------------------------------------------------------------
# SIDEBAR – Logo + kontakt
# ---------------------------------------------------------------------------
with st.sidebar:
    st.image("logo.png", use_container_width=True)
    st.markdown("---")
    st.markdown(
        "**Kalkulator TCO** EV vs ICE\n\n"
        "Optymalizacja kosztów z użyciem solvera **HiGHS** "
        "(programowanie liniowe). Dane rynkowe 2025/2026, "
        "bieżące ceny paliw z e-petrol.pl."
    )
    st.markdown("---")
    st.markdown(
        "[LinkedIn](https://www.linkedin.com/in/pawelmamcarz/) | "
        "[pawel@mamcarz.com](mailto:pawel@mamcarz.com) | "
        "+48 535 535 221"
    )
    st.caption(f"© 2026 Paweł Mamcarz. Wszelkie prawa zastrzeżone. v{APP_VERSION}")

st.title("Kalkulator TCO: Auto Elektryczne vs Spalinowe")
st.caption(
    "Optymalizacja z użyciem **HiGHS** (Linear Programming). "
    "Dane rynkowe 2025/2026, bieżące ceny paliw, taryfy dynamiczne RDN, "
    "tarcza podatkowa 2026 i wpływ temperatury na zużycie."
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
    dc_price: float = 1.60,
    ac_pub_price: float = 1.95,
) -> dict:
    """Optymalizuje roczny harmonogram ładowania BEV za pomocą HiGHS LP.

    Model: 288 slotów (12 miesięcy × 24h reprezentatywnego dnia).
    HiGHS minimalizuje koszt energii, NIE liczy TCO – to tylko jedna składowa.
    """
    PRICE_SUC = dc_price
    PRICE_AC_PUB = ac_pub_price
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

TESLA_WARRANTY_KM = 82_000  # Tesla: gwarancja na zawieszenie i hamulce do 82 000 km

def calculate_maintenance_cost(
    segment_idx: int, mileage_km: float, engine_type: str, is_new: bool,
    brand: str = "",
) -> dict:
    """Zwraca słownik z rozbiciem kosztów serwisowych."""
    discount = NEW_CAR_MAINTENANCE_DISCOUNT if is_new else 1.0
    is_tesla = "tesla" in brand.lower()

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

        # Tesla: gwarancja na zawieszenie i hamulce do 82 000 km
        warranty_km = min(mileage_km, TESLA_WARRANTY_KM) if (is_tesla and is_new) else 0
        post_warranty_km = max(0, mileage_km - warranty_km)

        brake_cost = post_warranty_km * 0.01 * discount if is_tesla else mileage_km * 0.01 * discount
        susp_note = ""
        if is_tesla and is_new:
            susp_cost = post_warranty_km * 0.008 * discount
            susp_note = f" (gwarancja Tesla do {TESLA_WARRANTY_KM:,} km)"
        else:
            susp_cost = 0

        breakdown = {
            "Filtry kabinowe": mileage_km * 0.01 * discount,
            "Płyn hamulcowy": mileage_km * 0.005 * discount,
            f"Hamulce (rekuperacja){' – gwarancja Tesla do ' + f'{TESLA_WARRANTY_KM:,} km' if is_tesla and is_new else ''}": brake_cost,
            "Opony (cięższe auto)": mileage_km * 0.025 * discount,
            "Przegląd / diagnostyka": mileage_km * 0.015 * discount,
        }
        if is_tesla and is_new:
            breakdown[f"Zawieszenie (po gwarancji, >{TESLA_WARRANTY_KM:,} km)"] = susp_cost

        breakdown = {k: max(0, v) for k, v in breakdown.items()}
        total = sum(breakdown.values())
        total_per_km = total / mileage_km if mileage_km > 0 else 0
        return {"total": total, "per_km": total_per_km, "breakdown": breakdown,
                "tesla_warranty": is_tesla and is_new}


# ---------------------------------------------------------------------------
# TARCZA PODATKOWA 2026
# ---------------------------------------------------------------------------

def calculate_tax_shield(
    vehicle_price: float, engine_type: str,
    annual_fuel_cost: float, insurance_annual: float,
    period_years: int, tax_rate: float = 0.19,
    usage_type: str = "firmowe",  # firmowe / mieszane / prywatne
) -> dict:
    """Szczegółowa tarcza podatkowa 2026 z rozbiciem VAT, KUP, leasingu."""
    limit = 100_000 if engine_type == "ICE" else 225_000
    is_bev = engine_type == "BEV"

    # --- Współczynniki wg użytkowania ---
    if usage_type == "firmowe":
        kup_pct = 1.0       # 100% kosztów w KUP
        vat_vehicle = 1.0   # 100% VAT od pojazdu (do limitu)
        vat_fuel = 1.0 if is_bev else 0.5   # BEV: 100% VAT od energii, ICE: 50%
        vat_ekspl = 1.0     # 100% VAT od eksploatacji
    elif usage_type == "mieszane":
        kup_pct = 0.75      # 75% kosztów w KUP
        vat_vehicle = 0.5   # 50% VAT od pojazdu
        vat_fuel = 0.5      # 50% VAT od paliwa/energii
        vat_ekspl = 0.5     # 50% VAT od eksploatacji
    else:  # prywatne
        return {"total": 0, "vat_vehicle": 0, "vat_fuel_annual": 0, "vat_ekspl_annual": 0,
                "kup_annual": 0, "pit_annual": 0, "limit": limit, "kup_pct": 0,
                "vat_fuel_pct": 0, "vat_vehicle_pct": 0, "breakdown": {}}

    # --- VAT od zakupu pojazdu (jednorazowo) ---
    price_for_vat = min(vehicle_price, limit)
    vat_vehicle_total = price_for_vat * 0.23 / 1.23 * vat_vehicle  # VAT zawarty w cenie brutto

    # --- VAT od paliwa / energii (rocznie) ---
    vat_fuel_annual = annual_fuel_cost * 0.23 / 1.23 * vat_fuel

    # --- VAT od eksploatacji: ubezpieczenie (brak VAT), serwis (est. 50% kosztów) ---
    est_maint_annual = annual_fuel_cost * 0.3  # przybliżenie serwisu
    vat_ekspl_annual = est_maint_annual * 0.23 / 1.23 * vat_ekspl

    # --- KUP: koszty w podatku dochodowym ---
    annual_lease_netto = vehicle_price / period_years  # rata leasingowa (uproszczone)
    lease_in_kup = min(annual_lease_netto, limit / period_years) * kup_pct
    fuel_in_kup = annual_fuel_cost * kup_pct
    insurance_in_kup = insurance_annual * kup_pct
    kup_annual = lease_in_kup + fuel_in_kup + insurance_in_kup
    pit_annual = kup_annual * tax_rate

    # --- Suma ---
    total_vat = vat_vehicle_total + (vat_fuel_annual + vat_ekspl_annual) * period_years
    total_pit = pit_annual * period_years
    total = total_vat + total_pit

    breakdown = {
        "VAT od zakupu (jednorazowo)": vat_vehicle_total,
        f"VAT od {'energii' if is_bev else 'paliwa'} (rocznie)": vat_fuel_annual,
        "VAT od eksploatacji (rocznie)": vat_ekspl_annual,
        "PIT/CIT – KUP rata leasingu (rocznie)": lease_in_kup * tax_rate,
        f"PIT/CIT – KUP {'energia' if is_bev else 'paliwo'} (rocznie)": fuel_in_kup * tax_rate,
        "PIT/CIT – KUP ubezpieczenie (rocznie)": insurance_in_kup * tax_rate,
    }

    return {
        "total": total,
        "vat_vehicle": vat_vehicle_total,
        "vat_fuel_annual": vat_fuel_annual,
        "vat_ekspl_annual": vat_ekspl_annual,
        "kup_annual": kup_annual,
        "pit_annual": pit_annual,
        "limit": limit,
        "kup_pct": kup_pct,
        "vat_fuel_pct": vat_fuel,
        "vat_vehicle_pct": vat_vehicle,
        "breakdown": breakdown,
    }


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


def calculate_tco_quick(
    vehicle_price, engine_type, is_new, annual_mileage, period_years, city_pct,
    fuel_price=0, city_l=0, highway_l=0,
    city_kwh=0, highway_kwh=0, battery_cap=75,
    pv_kwp=0, bess_kwh=0, has_home_charger=True,
    has_dynamic_tariff=True, has_old_pv=False, suc_distance=30,
    use_tax=True, tax_rate=0.19,
) -> dict:
    """Szybkie obliczenie TCO dla optymalizatora (HiGHS LP wewnątrz dla BEV)."""
    seg = price_to_segment(vehicle_price)
    total_km = annual_mileage * period_years
    mkm = np.array([annual_mileage * d / 365 for d in DAYS_IN_MONTH])
    if engine_type == "ICE":
        _, fa, _ = calc_annual_fuel_ice(city_l, highway_l, city_pct, mkm, fuel_price)
    else:
        dem, _ = calc_annual_consumption_bev(city_kwh, highway_kwh, city_pct, mkm)
        ch = optimize_charging(dem, battery_cap, pv_kwp, bess_kwh,
                               has_home_charger, has_dynamic_tariff, has_old_pv,
                               suc_distance, annual_mileage)
        fa = ch["total_cost"]
    et = fa * period_years
    mt = calculate_maintenance_cost(seg, total_km, engine_type, is_new)["total"]
    ins = estimate_insurance(vehicle_price, engine_type) * period_years
    tx_data = calculate_tax_shield(vehicle_price, engine_type, fa,
                                   estimate_insurance(vehicle_price, engine_type),
                                   period_years, tax_rate) if use_tax else None
    tx = tx_data["total"] if tx_data else 0
    dep = calculate_depreciation(vehicle_price, seg, period_years, engine_type, is_new)
    rv = vehicle_price - dep  # residual value
    tco = vehicle_price + et + mt + ins - tx
    tco_net = tco - rv  # TCO netto = koszt po odzyskaniu RV
    return {"tco": tco, "tco_net": tco_net, "rv": rv,
            "per_km": tco_net / total_km if total_km > 0 else 0,
            "monthly": tco_net / (period_years * 12), "energy": et,
            "maint": mt, "ins": ins, "tax": tx, "dep": dep}


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

# --- Presety popularnych modeli ---
ICE_PRESETS_NEW = {
    "Własne parametry": {"price": 140_000, "city_l": 7.5, "hwy_l": 6.0, "fuel": 0},
    "Toyota Corolla 1.8 Hybrid": {"price": 135_000, "city_l": 4.5, "hwy_l": 5.5, "fuel": 0},
    "Toyota Yaris Cross Hybrid": {"price": 115_000, "city_l": 4.8, "hwy_l": 5.2, "fuel": 0},
    "VW Golf 2.0 TDI": {"price": 145_000, "city_l": 6.5, "hwy_l": 5.0, "fuel": 1},
    "Skoda Octavia 2.0 TDI": {"price": 140_000, "city_l": 6.5, "hwy_l": 4.8, "fuel": 1},
    "Hyundai Tucson 1.6 T-GDi": {"price": 155_000, "city_l": 8.5, "hwy_l": 6.8, "fuel": 0},
    "Kia Sportage 1.6 T-GDi": {"price": 150_000, "city_l": 8.5, "hwy_l": 7.0, "fuel": 0},
    "Dacia Duster 1.0 TCe LPG": {"price": 85_000, "city_l": 10.0, "hwy_l": 8.0, "fuel": 2},
    "Toyota RAV4 2.5 Hybrid": {"price": 185_000, "city_l": 5.5, "hwy_l": 6.5, "fuel": 0},
    "BMW 320i": {"price": 210_000, "city_l": 8.5, "hwy_l": 6.5, "fuel": 0},
}
ICE_PRESETS_USED = {
    "Własne parametry": {"price": 65_000, "city_l": 7.5, "hwy_l": 6.0, "fuel": 0},
    "Toyota Corolla 1.8 Hybrid 2021": {"price": 85_000, "city_l": 4.8, "hwy_l": 5.5, "fuel": 0},
    "VW Golf VII 2.0 TDI 2019": {"price": 65_000, "city_l": 7.0, "hwy_l": 5.0, "fuel": 1},
    "Skoda Octavia III 2.0 TDI 2018": {"price": 55_000, "city_l": 7.0, "hwy_l": 5.2, "fuel": 1},
    "Opel Astra K 1.6 CDTI 2019": {"price": 48_000, "city_l": 6.8, "hwy_l": 4.8, "fuel": 1},
    "Toyota Yaris III 1.5 Hybrid 2020": {"price": 55_000, "city_l": 4.2, "hwy_l": 5.0, "fuel": 0},
    "Dacia Duster 1.5 dCi 2020": {"price": 52_000, "city_l": 7.5, "hwy_l": 6.0, "fuel": 1},
    "Hyundai Tucson 1.6 CRDi 2019": {"price": 72_000, "city_l": 8.0, "hwy_l": 6.0, "fuel": 1},
    "Ford Focus 1.5 EcoBlue 2019": {"price": 45_000, "city_l": 6.5, "hwy_l": 4.5, "fuel": 1},
    "BMW 320d F30 2018": {"price": 75_000, "city_l": 8.0, "hwy_l": 5.5, "fuel": 1},
}
BEV_PRESETS_NEW = {
    "Własne parametry": {"price": 195_000, "city_kwh": 16.5, "hwy_kwh": 19.0, "bat": 75},
    "Tesla Model Y RWD": {"price": 189_000, "city_kwh": 14.5, "hwy_kwh": 17.0, "bat": 60},
    "Tesla Model Y LR AWD": {"price": 219_000, "city_kwh": 16.0, "hwy_kwh": 19.0, "bat": 75},
    "Tesla Model 3 RWD": {"price": 175_000, "city_kwh": 13.5, "hwy_kwh": 16.0, "bat": 60},
    "BYD Atto 3": {"price": 145_000, "city_kwh": 16.0, "hwy_kwh": 19.5, "bat": 60},
    "BYD Seal": {"price": 185_000, "city_kwh": 14.5, "hwy_kwh": 17.5, "bat": 82},
    "VW ID.4 Pro": {"price": 195_000, "city_kwh": 17.0, "hwy_kwh": 20.0, "bat": 77},
    "Hyundai Ioniq 5 LR": {"price": 215_000, "city_kwh": 16.5, "hwy_kwh": 19.5, "bat": 77},
    "Skoda Enyaq iV 80": {"price": 199_000, "city_kwh": 17.5, "hwy_kwh": 20.5, "bat": 77},
    "MG4 Electric LR": {"price": 125_000, "city_kwh": 15.5, "hwy_kwh": 18.5, "bat": 64},
}
BEV_PRESETS_USED = {
    "Własne parametry": {"price": 120_000, "city_kwh": 16.5, "hwy_kwh": 19.0, "bat": 75},
    "Tesla Model 3 SR+ 2021": {"price": 105_000, "city_kwh": 14.0, "hwy_kwh": 16.5, "bat": 55},
    "Tesla Model Y LR 2022": {"price": 145_000, "city_kwh": 16.0, "hwy_kwh": 19.0, "bat": 75},
    "VW ID.3 Pro 2021": {"price": 85_000, "city_kwh": 15.5, "hwy_kwh": 18.5, "bat": 58},
    "VW ID.4 Pro 2022": {"price": 120_000, "city_kwh": 17.0, "hwy_kwh": 20.0, "bat": 77},
    "Hyundai Ioniq 5 LR 2022": {"price": 135_000, "city_kwh": 16.5, "hwy_kwh": 19.5, "bat": 77},
    "Nissan Leaf 40 kWh 2020": {"price": 65_000, "city_kwh": 16.0, "hwy_kwh": 19.0, "bat": 40},
    "Renault Zoe R135 2021": {"price": 58_000, "city_kwh": 15.0, "hwy_kwh": 18.0, "bat": 52},
    "Skoda Enyaq 80 2022": {"price": 125_000, "city_kwh": 17.5, "hwy_kwh": 20.5, "bat": 77},
    "BMW iX1 eDrive20 2023": {"price": 155_000, "city_kwh": 17.0, "hwy_kwh": 20.0, "bat": 65},
}

ice_presets = ICE_PRESETS_NEW if is_new else ICE_PRESETS_USED
bev_presets = BEV_PRESETS_NEW if is_new else BEV_PRESETS_USED

col_ice, col_bev = st.columns(2)

with col_ice:
    st.subheader("ICE (spalinowe)")
    ice_preset_name = st.selectbox(
        "Popularny model ICE",
        list(ice_presets.keys()),
        index=0,
        help="Wybierz model z listy – cena i spalanie wypełnią się automatycznie. "
             "Wybierz 'Własne parametry' aby wpisać ręcznie.",
    )
    ice_p = ice_presets[ice_preset_name]
    ice_model = st.text_input(
        "Marka i model ICE",
        value=ice_preset_name if ice_preset_name != "Własne parametry" else (
            "Toyota Corolla 2024" if is_new else "Toyota Corolla 2019"),
        help="Np. Toyota Corolla 1.8, VW Golf 2.0 TDI, Dacia Duster 1.5 dCi",
    )
    vehicle_price_ice = st.number_input(
        "Cena zakupu / leasingu ICE (zł)",
        min_value=5_000, max_value=1_000_000,
        value=ice_p["price"],
        step=5_000,
        help="Wpisz cenę swojego pojazdu – z otomoto.pl, salonu lub umowy leasingu.",
    )
    fuel_type = st.selectbox(
        "Rodzaj paliwa",
        ["Benzyna (PB95)", "Diesel (ON)", "LPG"],
        index=ice_p["fuel"],
    )

with col_bev:
    st.subheader("BEV (elektryczne)")
    bev_preset_name = st.selectbox(
        "Popularny model BEV",
        list(bev_presets.keys()),
        index=0,
        help="Wybierz model z listy – cena, zużycie i bateria wypełnią się automatycznie. "
             "Wybierz 'Własne parametry' aby wpisać ręcznie.",
    )
    bev_p = bev_presets[bev_preset_name]
    bev_model = st.text_input(
        "Marka i model BEV",
        value=bev_preset_name if bev_preset_name != "Własne parametry" else (
            "Tesla Model Y LR 2024" if is_new else "Tesla Model 3 SR+ 2021"),
        help="Np. Tesla Model Y LR, BYD Atto 3, Hyundai Ioniq 5",
    )
    vehicle_price_bev = st.number_input(
        "Cena zakupu / leasingu BEV (zł)",
        min_value=5_000, max_value=1_000_000,
        value=bev_p["price"],
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
        "Miasto (l/100 km)", min_value=3.0, max_value=25.0, value=ice_p["city_l"], step=0.5,
        help="Spalanie w cyklu miejskim.",
    )
with col_ic2:
    ice_highway_l = st.number_input(
        "Trasa (l/100 km)", min_value=3.0, max_value=20.0, value=ice_p["hwy_l"], step=0.5,
        help="Spalanie w cyklu pozamiejskim / autostrada.",
    )

st.subheader("Zużycie BEV (nominalne przy 15°C)")
col_bc1, col_bc2 = st.columns(2)
with col_bc1:
    bev_city_kwh = st.number_input(
        "Miasto (kWh/100 km)", min_value=8.0, max_value=35.0, value=bev_p["city_kwh"], step=0.5,
        help="Zużycie w cyklu miejskim przy 15°C.",
    )
with col_bc2:
    bev_highway_kwh = st.number_input(
        "Trasa (kWh/100 km)", min_value=10.0, max_value=40.0, value=bev_p["hwy_kwh"], step=0.5,
        help="Zużycie w cyklu trasowym przy 15°C.",
    )

st.subheader("Parametry BEV – bateria i ładowanie")
col3, col4 = st.columns(2)
with col3:
    battery_capacity = st.number_input(
        "Pojemność baterii BEV (kWh)", min_value=20, max_value=120, value=bev_p["bat"], step=5
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

# Ładowanie trasowe – widoczne gdy dużo trasy
highway_pct = 1.0 - city_pct
if highway_pct >= 0.3:
    st.subheader("Ładowanie trasowe (poza domem)")
    st.caption(
        f"Przy {highway_pct:.0%} jazdy trasowej część energii BEV pobierana będzie "
        "na stacjach szybkiego ładowania DC (>200 km trasy = ładowanie w trasie)."
    )
    col_ch1, col_ch2 = st.columns(2)
    with col_ch1:
        dc_charger_type = st.selectbox(
            "Preferowana sieć ładowania DC",
            [
                "Tesla Supercharger (1.49–1.69 zł/kWh)",
                "Orlen Charge (1.79–1.99 zł/kWh)",
                "GreenWay (1.69–1.89 zł/kWh)",
                "Powerdot (1.59–1.79 zł/kWh)",
                "Inne / średnia rynkowa (1.80 zł/kWh)",
            ],
            index=0,
            help="Cena zależy od abonamentu i mocy. Podane zakresy to ceny 2025/2026.",
        )
    with col_ch2:
        dc_price_map = {
            "Tesla": 1.59, "Orlen": 1.89, "GreenWay": 1.79,
            "Powerdot": 1.69, "Inne": 1.80,
        }
        dc_key = [k for k in dc_price_map if k in dc_charger_type][0]
        dc_price_default = dc_price_map[dc_key]
        dc_price_custom = st.number_input(
            "Cena ładowania DC (zł/kWh)",
            min_value=0.50, max_value=5.00, value=dc_price_default, step=0.05,
            help="Możesz wpisać własną cenę. Wartość domyślna z wybranej sieci.",
        )
        ac_pub_price = st.number_input(
            "Cena ładowania publiczne AC (zł/kWh)",
            min_value=0.50, max_value=5.00, value=1.95, step=0.05,
            help="Publiczne ładowarki AC w miastach (7-22 kW).",
        )
else:
    dc_price_custom = 1.60
    ac_pub_price = 1.95

st.subheader("Parametry podatkowe")
col7, col8, col9 = st.columns(3)
with col7:
    use_tax_shield = st.checkbox("Uwzględnij tarczę podatkową 2026", value=True)
with col8:
    tax_rate = st.selectbox("Stawka podatku", [0.12, 0.19, 0.32], index=1, format_func=lambda x: f"{x:.0%}")
with col9:
    usage_type = st.selectbox(
        "Użytkowanie pojazdu",
        ["firmowe", "mieszane", "prywatne"],
        index=0,
        format_func=lambda x: {"firmowe": "Firmowe 100%", "mieszane": "Mieszane 75%", "prywatne": "Prywatne"}[x],
        help="Firmowe: 100% VAT (BEV) / 50% VAT paliwo (ICE), 100% KUP. "
             "Mieszane: 50% VAT, 75% KUP. Prywatne: brak odliczeń.",
        disabled=not use_tax_shield,
    )
if use_tax_shield:
    with st.expander("Limity podatkowe 2026 – ICE vs BEV"):
        ct1, ct2 = st.columns(2)
        with ct1:
            st.markdown(
                "**ICE (spalinowe)**\n"
                "- Limit leasingu: **100 000 zł** netto\n"
                "- VAT od paliwa: **50%** (firmowe i mieszane)\n"
                "- VAT od zakupu: 100% firm. / 50% mieszane (do limitu)\n"
                "- KUP: 100% firmowe / 75% mieszane"
            )
        with ct2:
            st.markdown(
                "**BEV (elektryczne)**\n"
                "- Limit leasingu: **225 000 zł** netto\n"
                "- VAT od energii: **100%** (firmowe) / 50% mieszane\n"
                "- VAT od zakupu: 100% firm. / 50% mieszane (do limitu)\n"
                "- KUP: 100% firmowe / 75% mieszane"
            )

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
    tax_data_ice = None
    if use_tax_shield:
        tax_data_ice = calculate_tax_shield(
            vehicle_price_ice, "ICE", fuel_cost_annual,
            estimate_insurance(vehicle_price_ice, "ICE"), period_years, tax_rate,
            usage_type=usage_type,
        )
        tax_shield_ice = tax_data_ice["total"]

    tco_ice = vehicle_price_ice + fuel_cost_total + maint_ice + insurance_ice - tax_shield_ice
    rv_ice = vehicle_price_ice - depreciation_ice  # wartość rezydualna
    tco_net_ice = tco_ice - rv_ice  # TCO netto (po odzyskaniu RV)
    cost_per_km_ice = tco_net_ice / total_mileage if total_mileage > 0 else 0

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
            dc_price=dc_price_custom,
            ac_pub_price=ac_pub_price,
        )

    energy_cost_annual = charging_result["total_cost"]
    energy_cost_total = energy_cost_annual * period_years

    maint_bev_data = calculate_maintenance_cost(segment_idx_bev, total_mileage, "BEV", is_new, brand=bev_model)
    maint_bev = maint_bev_data["total"]
    depreciation_bev = calculate_depreciation(vehicle_price_bev, segment_idx_bev, period_years, "BEV", is_new)
    insurance_bev = estimate_insurance(vehicle_price_bev, "BEV") * period_years

    tax_shield_bev = 0.0
    tax_data_bev = None
    if use_tax_shield:
        tax_data_bev = calculate_tax_shield(
            vehicle_price_bev, "BEV", energy_cost_annual,
            estimate_insurance(vehicle_price_bev, "BEV"), period_years, tax_rate,
            usage_type=usage_type,
        )
        tax_shield_bev = tax_data_bev["total"]

    tco_bev = vehicle_price_bev + energy_cost_total + maint_bev + insurance_bev - tax_shield_bev
    rv_bev = vehicle_price_bev - depreciation_bev  # wartość rezydualna
    tco_net_bev = tco_bev - rv_bev  # TCO netto (po odzyskaniu RV)
    cost_per_km_bev = tco_net_bev / total_mileage if total_mileage > 0 else 0

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
        # RV i TCO netto
        col_rv1, col_rv2 = st.columns(2)
        with col_rv1:
            st.markdown(f"**{ice_model}**")
            c1, c2, c3 = st.columns(3)
            c1.metric("Wartość rezydualna (RV)", f"{rv_ice:,.0f} zł",
                       delta=f"-{depreciation_ice:,.0f} zł deprecjacja", delta_color="inverse")
            c2.metric("Tarcza podatkowa", f"-{tax_shield_ice:,.0f} zł")
            c3.metric("TCO netto (po sprzedaży)", f"{tco_net_ice:,.0f} zł",
                       help="TCO brutto − wartość rezydualna = realny koszt posiadania")
        with col_rv2:
            st.markdown(f"**{bev_model}**")
            c1, c2, c3 = st.columns(3)
            c1.metric("Wartość rezydualna (RV)", f"{rv_bev:,.0f} zł",
                       delta=f"-{depreciation_bev:,.0f} zł deprecjacja", delta_color="inverse")
            c2.metric("Tarcza podatkowa", f"-{tax_shield_bev:,.0f} zł")
            c3.metric("TCO netto (po sprzedaży)", f"{tco_net_bev:,.0f} zł",
                       help="TCO brutto − wartość rezydualna = realny koszt posiadania")

        # --- Rozbicie tarczy podatkowej ---
        if use_tax_shield and tax_data_ice and tax_data_bev and usage_type != "prywatne":
            with st.expander("Rozbicie tarczy podatkowej – ICE vs BEV"):
                tc1, tc2 = st.columns(2)
                with tc1:
                    st.markdown(f"**{ice_model}** (limit: **{tax_data_ice['limit']:,.0f} zł**)")
                    for label, val in tax_data_ice["breakdown"].items():
                        if val > 0:
                            st.markdown(f"- {label}: **{val:,.0f} zł**")
                    st.markdown(f"- **SUMA tarcza: {tax_shield_ice:,.0f} zł** za {period_years} lata")
                    st.caption(f"VAT paliwo: {tax_data_ice['vat_fuel_pct']:.0%} | KUP: {tax_data_ice['kup_pct']:.0%}")
                with tc2:
                    st.markdown(f"**{bev_model}** (limit: **{tax_data_bev['limit']:,.0f} zł**)")
                    for label, val in tax_data_bev["breakdown"].items():
                        if val > 0:
                            st.markdown(f"- {label}: **{val:,.0f} zł**")
                    st.markdown(f"- **SUMA tarcza: {tax_shield_bev:,.0f} zł** za {period_years} lata")
                    st.caption(f"VAT energia: {tax_data_bev['vat_fuel_pct']:.0%} | KUP: {tax_data_bev['kup_pct']:.0%}")
                adv = tax_shield_bev - tax_shield_ice
                if adv > 0:
                    st.success(f"BEV ma o **{adv:,.0f} zł** większą tarczę podatkową (wyższy limit + 100% VAT od energii)")

        st.markdown("---")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric(f"Koszt / km – {ice_model.split()[0]}", f"{cost_per_km_ice:.2f} zł",
                       help="TCO netto / km (po odliczeniu RV i tarczy)")
        with col_b:
            st.metric(f"Koszt / km – {bev_model.split()[0]}", f"{cost_per_km_bev:.2f} zł",
                       help="TCO netto / km (po odliczeniu RV i tarczy)")
        with col_c:
            diff = tco_net_ice - tco_net_bev
            st.metric(
                "Oszczędność BEV vs ICE (netto)", f"{abs(diff):,.0f} zł",
                delta=f"{'BEV tańsze' if diff > 0 else 'ICE tańsze'}",
                delta_color="normal" if diff > 0 else "inverse",
            )

        categories = ["Zakup", "Paliwo / Prąd", "Serwis", "Ubezpieczenie",
                       "Tarcza podatkowa", "Wart. rezydualna (RV)", "TCO brutto", "TCO NETTO"]
        ice_vals = [vehicle_price_ice, fuel_cost_total, maint_ice, insurance_ice,
                    -tax_shield_ice, -rv_ice, tco_ice, tco_net_ice]
        bev_vals = [vehicle_price_bev, energy_cost_total, maint_bev, insurance_bev,
                    -tax_shield_bev, -rv_bev, tco_bev, tco_net_bev]

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
            x=months_range, y=ice_cum, name=f"ICE – {ice_model} (brutto)",
            line=dict(color="#ef4444", width=3),
        ))
        fig_line.add_trace(go.Scatter(
            x=months_range, y=bev_cum, name=f"BEV – {bev_model} (brutto)",
            line=dict(color="#22c55e", width=3),
        ))
        # RV markers at end – show netto after resale
        last_mo = months_range[-1]
        fig_line.add_trace(go.Scatter(
            x=[last_mo, last_mo], y=[tco_net_ice, tco_net_bev],
            mode="markers+text", name="TCO netto (po sprzedaży)",
            marker=dict(size=14, symbol="star", color=["#ef4444", "#22c55e"],
                        line=dict(width=2, color="black")),
            text=[f"netto: {tco_net_ice:,.0f}", f"netto: {tco_net_bev:,.0f}"],
            textposition=["top right", "bottom right"],
        ))
        fig_line.update_layout(
            title="Koszt narastający w czasie (gwiazdki = TCO netto po sprzedaży auta)",
            xaxis_title="Miesiąc", yaxis_title="Koszt skumulowany (PLN)", height=450,
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
                "TCO brutto (suma wydatków)",
                "",
                "Wartość rezydualna (RV) po sprzedaży",
                "TCO NETTO (realny koszt posiadania)",
                "Koszt / km (netto)",
                "",
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
                "",
                f"{rv_ice:,.0f} zł",
                f"{tco_net_ice:,.0f} zł",
                f"{cost_per_km_ice:.2f} zł",
                "",
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
                "",
                f"{rv_bev:,.0f} zł",
                f"{tco_net_bev:,.0f} zł",
                f"{cost_per_km_bev:.2f} zł",
                "",
                f"{avg_bev_real:.1f} kWh/100km",
                f"+{bev_temp_penalty_pct:.1f}%",
            ],
        })
        # Dodaj wiersze podatkowe jeśli aktywne
        if use_tax_shield and tax_data_ice and tax_data_bev:
            tax_rows = pd.DataFrame({
                "Kategoria": [
                    "",
                    "Limit leasingu",
                    "VAT paliwo/energia",
                    "KUP (koszty uzyskania)",
                    "Użytkowanie pojazdu",
                ],
                "ICE": [
                    "",
                    f"{tax_data_ice['limit']:,.0f} zł",
                    f"{tax_data_ice['vat_fuel_pct']:.0%}",
                    f"{tax_data_ice['kup_pct']:.0%}",
                    usage_type,
                ],
                "BEV": [
                    "",
                    f"{tax_data_bev['limit']:,.0f} zł",
                    f"{tax_data_bev['vat_fuel_pct']:.0%}",
                    f"{tax_data_bev['kup_pct']:.0%}",
                    usage_type,
                ],
            })
            df_detail = pd.concat([df_detail, tax_rows], ignore_index=True)

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
                if maint_bev_data.get("tesla_warranty"):
                    st.info(f"Tesla: gwarancja na zawieszenie i hamulce do {TESLA_WARRANTY_KM:,} km – "
                            f"brak kosztów tych komponentów w okresie gwarancyjnym.")

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

# ---------------------------------------------------------------------------
# OPTYMALIZATOR HiGHS – trzy tryby zaawansowanej analizy
# ---------------------------------------------------------------------------
st.divider()
st.header("3. Optymalizator HiGHS")
st.caption(
    "Zaawansowane analizy TCO z użyciem solvera **HiGHS** (Linear Programming). "
    "Każdy scenariusz BEV uruchamia osobną optymalizację harmonogramu ładowania."
)

opt_mode = st.radio(
    "Tryb optymalizacji",
    ["A: Doradca", "B: Punkt zwrotny", "C: Porównanie floty"],
    horizontal=True,
    captions=[
        "Optymalna konfiguracja PV/BESS/taryfa",
        "Przy jakim przebiegu BEV wygrywa?",
        "Ranking wielu modeli naraz",
    ],
)

# ---- MODE A: DORADCA ----
if "Doradca" in opt_mode:
    st.subheader("Doradca – optymalna konfiguracja ładowania")
    st.markdown(
        "Dla każdej kombinacji PV / BESS / taryfy HiGHS optymalizuje koszt energii BEV, "
        "a następnie oblicza pełne TCO. Wynik: ranking od najtańszego."
    )
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        budget_monthly = st.number_input(
            "Budżet miesięczny na auto (zł)", 500, 15_000, 3_000, 250, key="adv_budget")
        has_roof = st.checkbox("Mam dach na PV", True, key="adv_roof")
    with col_d2:
        has_garage = st.checkbox("Mam garaż / wallbox", True, key="adv_garage")
        include_invest = st.checkbox(
            "Uwzględnij koszt inwestycji PV/BESS",
            True, key="adv_invest",
            help="PV: ~4 000 zł/kWp, BESS: ~3 000 zł/kWh (ceny rynkowe PL 2025/2026)",
        )

    PV_COST_PER_KWP = 4_000
    BESS_COST_PER_KWH = 3_000

    if st.button("Znajdź optymalną konfigurację (HiGHS)", key="btn_adv"):
        scenarios = []
        # ICE baseline
        r = calculate_tco_quick(
            vehicle_price_ice, "ICE", is_new, annual_mileage, period_years, city_pct,
            fuel_price=fuel_price, city_l=ice_city_l, highway_l=ice_highway_l,
            use_tax=use_tax_shield, tax_rate=tax_rate)
        scenarios.append({"Konfig.": f"ICE: {ice_model}", "PV": 0, "BESS": 0,
                          "Taryfa": "G11", "Inwestycja": 0, **r})

        pv_opts = [0] + ([3, 5, 10] if has_roof else [])
        bess_opts = [0] + ([10, 30] if has_garage else [])
        tariff_opts = [(False, "G11"), (True, "Pstryk")] if has_garage else [(False, "G11")]

        n_total = len(pv_opts) * len(bess_opts) * len(tariff_opts)
        progress = st.progress(0, text="Optymalizacja HiGHS LP...")
        done = 0

        for pv in pv_opts:
            for bess in bess_opts:
                for dyn, tname in tariff_opts:
                    r = calculate_tco_quick(
                        vehicle_price_bev, "BEV", is_new, annual_mileage,
                        period_years, city_pct,
                        city_kwh=bev_city_kwh, highway_kwh=bev_highway_kwh,
                        battery_cap=battery_capacity, pv_kwp=pv, bess_kwh=bess,
                        has_home_charger=has_garage, has_dynamic_tariff=dyn,
                        has_old_pv=has_old_pv, suc_distance=suc_distance,
                        use_tax=use_tax_shield, tax_rate=tax_rate)
                    invest = 0
                    if include_invest:
                        invest = pv * PV_COST_PER_KWP + bess * BESS_COST_PER_KWH
                    r["tco"] += invest
                    r["monthly"] = r["tco"] / (period_years * 12)
                    r["per_km"] = r["tco"] / (annual_mileage * period_years)
                    scenarios.append({
                        "Konfig.": f"BEV: {bev_model}", "PV": pv, "BESS": bess,
                        "Taryfa": tname, "Inwestycja": invest, **r,
                    })
                    done += 1
                    progress.progress(done / n_total, text=f"HiGHS LP: {done}/{n_total}")

        progress.empty()
        df_s = pd.DataFrame(scenarios).sort_values("tco")

        best = df_s.iloc[0]
        st.success(
            f"**Rekomendacja HiGHS:** {best['Konfig.']} | "
            f"PV: {best['PV']} kWp | BESS: {best['BESS']} kWh | {best['Taryfa']}\n\n"
            f"TCO: **{best['tco']:,.0f} zł** ({best['per_km']:.2f} zł/km, "
            f"{best['monthly']:,.0f} zł/mies.)"
        )

        in_budget = df_s[df_s["monthly"] <= budget_monthly]
        if len(in_budget) > 0 and in_budget.iloc[0].name != best.name:
            bb = in_budget.iloc[0]
            st.info(
                f"**Najlepsze w budżecie {budget_monthly:,} zł/mies.:** {bb['Konfig.']} | "
                f"PV: {bb['PV']} kWp | BESS: {bb['BESS']} kWh | {bb['Taryfa']}\n\n"
                f"TCO: **{bb['tco']:,.0f} zł** ({bb['monthly']:,.0f} zł/mies.)"
            )

        # Bar chart top 8
        top_n = min(8, len(df_s))
        fig_adv = go.Figure()
        fig_adv.add_trace(go.Bar(
            x=[f"{r['Konfig.'].split(':')[0]}\nPV:{r['PV']} BESS:{r['BESS']}\n{r['Taryfa']}"
               for _, r in df_s.head(top_n).iterrows()],
            y=df_s.head(top_n)["tco"],
            marker_color=["#22c55e" if "BEV" in r["Konfig."] else "#ef4444"
                          for _, r in df_s.head(top_n).iterrows()],
            text=df_s.head(top_n)["tco"].apply(lambda x: f"{x:,.0f}"),
            textposition="outside",
        ))
        fig_adv.update_layout(
            title=f"Top {top_n} konfiguracji wg TCO ({period_years} lata, HiGHS LP)",
            yaxis_title="TCO (zł)", height=450,
        )
        st.plotly_chart(fig_adv, use_container_width=True)

        # Full table
        show_df = df_s[["Konfig.", "PV", "BESS", "Taryfa", "Inwestycja",
                        "tco", "energy", "maint", "per_km", "monthly"]].copy()
        show_df.columns = ["Konfiguracja", "PV (kWp)", "BESS (kWh)", "Taryfa",
                           "Inwestycja PV+BESS", "TCO (zł)", "Energia (zł)",
                           "Serwis (zł)", "zł/km", "zł/mies."]
        for c in ["Inwestycja PV+BESS", "TCO (zł)", "Energia (zł)", "Serwis (zł)", "zł/mies."]:
            show_df[c] = show_df[c].apply(lambda x: f"{x:,.0f}")
        show_df["zł/km"] = show_df["zł/km"].apply(lambda x: f"{x:.2f}")
        st.dataframe(show_df, use_container_width=True, hide_index=True)

# ---- MODE B: BREAKEVEN ----
elif "Punkt zwrotny" in opt_mode:
    st.subheader("Punkt zwrotny – kiedy BEV wygrywa z ICE?")
    st.markdown(
        "Mapa ciepła: dla jakiego przebiegu i ceny paliwa **BEV** ma niższe TCO? "
        "Koszt energii BEV obliczony z optymalizacji HiGHS LP (jedno uruchomienie referencyjne)."
    )

    if st.button("Oblicz mapę punktu zwrotnego (HiGHS)", key="btn_breakeven"):
        with st.spinner("Optymalizacja HiGHS (referencyjne ładowanie BEV)..."):
            mkm_ref = np.array([annual_mileage * d / 365 for d in DAYS_IN_MONTH])
            maint_ice_rate = calculate_maintenance_cost(
                segment_idx_ice, 100_000, "ICE", is_new)["per_km"]
            maint_bev_rate = calculate_maintenance_cost(
                segment_idx_bev, 100_000, "BEV", is_new, brand=bev_model)["per_km"]

            dem_ref, _ = calc_annual_consumption_bev(
                bev_city_kwh, bev_highway_kwh, city_pct, mkm_ref)
            ch_ref = optimize_charging(
                dem_ref, battery_capacity, pv_kwp, bess_kwh,
                has_home_charger, has_dynamic_tariff, has_old_pv,
                suc_distance, annual_mileage)
            bev_energy_per_km = ch_ref["total_cost"] / annual_mileage if annual_mileage > 0 else 0.5

            _, ice_fuel_ref, _ = calc_annual_fuel_ice(
                ice_city_l, ice_highway_l, city_pct, mkm_ref, 1.0)
            ice_l_per_km = ice_fuel_ref / annual_mileage if annual_mileage > 0 else 0.07

            ins_ice_a = estimate_insurance(vehicle_price_ice, "ICE")
            ins_bev_a = estimate_insurance(vehicle_price_bev, "BEV")

        mileages = np.linspace(5_000, 80_000, 16)
        fuel_prices_sweep = np.linspace(4.0, 12.0, 17)
        diff_matrix = np.zeros((len(fuel_prices_sweep), len(mileages)))

        for i, fp in enumerate(fuel_prices_sweep):
            for j, mil in enumerate(mileages):
                tkm = mil * period_years
                f_ice = ice_l_per_km * fp * tkm
                m_ice = maint_ice_rate * tkm
                i_ice = ins_ice_a * period_years
                tx_ice = calculate_tax_shield(
                    vehicle_price_ice, "ICE", ice_l_per_km * fp * mil,
                    ins_ice_a, period_years, tax_rate) if use_tax_shield else 0
                tco_i = vehicle_price_ice + f_ice + m_ice + i_ice - tx_ice

                e_bev = bev_energy_per_km * tkm
                m_bev = maint_bev_rate * tkm
                i_bev = ins_bev_a * period_years
                tx_bev = calculate_tax_shield(
                    vehicle_price_bev, "BEV", bev_energy_per_km * mil,
                    ins_bev_a, period_years, tax_rate) if use_tax_shield else 0
                tco_b = vehicle_price_bev + e_bev + m_bev + i_bev - tx_bev

                diff_matrix[i, j] = tco_i - tco_b  # >0 = BEV wins

        fig_bp = go.Figure()
        fig_bp.add_trace(go.Heatmap(
            z=diff_matrix, x=mileages / 1000, y=fuel_prices_sweep,
            colorscale=[[0, "#ef4444"], [0.5, "#fef3c7"], [1, "#22c55e"]],
            zmid=0,
            colorbar=dict(title="ICE−BEV (zł)"),
            hovertemplate=(
                "Przebieg: %{x:.0f}k km/rok<br>"
                "Paliwo: %{y:.2f} zł/l<br>"
                "Różnica: %{z:,.0f} zł<extra></extra>"
            ),
        ))
        fig_bp.add_trace(go.Contour(
            z=diff_matrix, x=mileages / 1000, y=fuel_prices_sweep,
            contours=dict(start=0, end=0, size=1, showlabels=True,
                          labelfont=dict(size=14, color="black")),
            line=dict(width=3, color="black"),
            showscale=False, name="Breakeven",
        ))
        fig_bp.add_trace(go.Scatter(
            x=[annual_mileage / 1000], y=[fuel_price],
            mode="markers+text", name="Twoje parametry",
            marker=dict(size=15, color="white", symbol="diamond",
                        line=dict(width=3, color="black")),
            text=["TY"], textposition="top center",
            textfont=dict(size=14, color="black"),
        ))
        fig_bp.update_layout(
            title=(
                f"Mapa TCO: zielone = BEV tańsze "
                f"({period_years} lata, {ice_model} vs {bev_model})"
            ),
            xaxis_title="Roczny przebieg (tys. km)",
            yaxis_title="Cena paliwa (zł/l)",
            height=550,
        )
        st.plotly_chart(fig_bp, use_container_width=True)

        # Find breakeven at current fuel price
        fp_idx = np.argmin(np.abs(fuel_prices_sweep - fuel_price))
        row = diff_matrix[fp_idx, :]
        if np.all(row > 0):
            st.success(
                f"BEV wygrywa przy **każdym przebiegu** przy cenie paliwa "
                f"{fuel_price:.2f} zł/l (okres {period_years} lata)!"
            )
        elif np.all(row < 0):
            st.warning(
                f"ICE wygrywa przy **każdym przebiegu** przy cenie paliwa "
                f"{fuel_price:.2f} zł/l. Rozważ tańsze BEV lub PV."
            )
        else:
            for j in range(len(mileages) - 1):
                if row[j] <= 0 < row[j + 1]:
                    frac = -row[j] / (row[j + 1] - row[j]) if row[j + 1] != row[j] else 0.5
                    be_km = mileages[j] + frac * (mileages[j + 1] - mileages[j])
                    st.info(
                        f"Przy cenie paliwa **{fuel_price:.2f} zł/l** BEV wygrywa od "
                        f"**{be_km:,.0f} km/rok** ({period_years} lata)."
                    )
                    break

        st.caption(
            f"Koszt energii BEV: {bev_energy_per_km:.3f} zł/km (z optymalizacji HiGHS LP). "
            f"Spalanie ICE: {ice_l_per_km * 100:.1f} l/100km (z uwzględnieniem temperatury). "
            f"Dane rynkowe i podatkowe 2025/2026."
        )

# ---- MODE C: PORÓWNANIE FLOTY ----
else:
    st.subheader("Porównanie floty – ranking modeli")
    st.markdown(
        "Dodaj pojazdy do porównania. Dla **BEV** podaj zużycie w kWh/100km, "
        "dla **ICE** w l/100km. Każdy BEV przechodzi optymalizację HiGHS LP."
    )

    default_cars = pd.DataFrame([
        {"Model": ice_model, "Cena (zł)": vehicle_price_ice, "Napęd": "ICE",
         "Miasto (/100km)": ice_city_l, "Trasa (/100km)": ice_highway_l},
        {"Model": bev_model, "Cena (zł)": vehicle_price_bev, "Napęd": "BEV",
         "Miasto (/100km)": bev_city_kwh, "Trasa (/100km)": bev_highway_kwh},
        {"Model": "Dacia Spring 2025", "Cena (zł)": 85_000, "Napęd": "BEV",
         "Miasto (/100km)": 14.0, "Trasa (/100km)": 17.0},
    ])

    edited_cars = st.data_editor(
        default_cars,
        column_config={
            "Napęd": st.column_config.SelectboxColumn(options=["ICE", "BEV"]),
            "Cena (zł)": st.column_config.NumberColumn(
                min_value=5000, max_value=1_000_000, step=5000),
            "Miasto (/100km)": st.column_config.NumberColumn(
                min_value=3.0, max_value=40.0, step=0.5),
            "Trasa (/100km)": st.column_config.NumberColumn(
                min_value=3.0, max_value=40.0, step=0.5),
        },
        num_rows="dynamic",
        use_container_width=True,
        key="portfolio_editor",
    )

    if st.button("Porównaj wszystkie modele (HiGHS)", key="btn_portfolio"):
        valid_cars = edited_cars.dropna(subset=["Model", "Cena (zł)", "Napęd"])
        if len(valid_cars) < 2:
            st.warning("Dodaj co najmniej 2 pojazdy do porównania.")
        else:
            results = []
            progress = st.progress(0, text="Obliczam TCO (HiGHS LP)...")

            for idx, (_, car) in enumerate(valid_cars.iterrows()):
                etype = car["Napęd"]
                if etype == "ICE":
                    r = calculate_tco_quick(
                        car["Cena (zł)"], "ICE", is_new, annual_mileage,
                        period_years, city_pct,
                        fuel_price=fuel_price,
                        city_l=car["Miasto (/100km)"],
                        highway_l=car["Trasa (/100km)"],
                        use_tax=use_tax_shield, tax_rate=tax_rate)
                else:
                    r = calculate_tco_quick(
                        car["Cena (zł)"], "BEV", is_new, annual_mileage,
                        period_years, city_pct,
                        city_kwh=car["Miasto (/100km)"],
                        highway_kwh=car["Trasa (/100km)"],
                        battery_cap=battery_capacity, pv_kwp=pv_kwp,
                        bess_kwh=bess_kwh, has_home_charger=has_home_charger,
                        has_dynamic_tariff=has_dynamic_tariff,
                        has_old_pv=has_old_pv, suc_distance=suc_distance,
                        use_tax=use_tax_shield, tax_rate=tax_rate)
                results.append({
                    "Model": car["Model"], "Napęd": etype,
                    "Cena": car["Cena (zł)"], **r,
                })
                progress.progress((idx + 1) / len(valid_cars),
                                  text=f"HiGHS LP: {idx + 1}/{len(valid_cars)}")

            progress.empty()
            df_p = pd.DataFrame(results).sort_values("tco")

            w = df_p.iloc[0]
            st.success(
                f"**Zwycięzca (HiGHS):** {w['Model']} ({w['Napęd']}) – "
                f"TCO **{w['tco']:,.0f} zł** ({w['per_km']:.2f} zł/km, "
                f"{w['monthly']:,.0f} zł/mies.)"
            )

            # Bar chart
            colors = ["#22c55e" if r["Napęd"] == "BEV" else "#ef4444"
                      for _, r in df_p.iterrows()]
            fig_p = go.Figure()
            fig_p.add_trace(go.Bar(
                x=df_p["Model"] + " (" + df_p["Napęd"] + ")",
                y=df_p["tco"],
                marker_color=colors,
                text=df_p["tco"].apply(lambda x: f"{x:,.0f}"),
                textposition="outside",
            ))
            fig_p.update_layout(
                title=f"Ranking TCO – {period_years} lata, {annual_mileage:,} km/rok (HiGHS LP)",
                yaxis_title="TCO (zł)", height=450,
            )
            st.plotly_chart(fig_p, use_container_width=True)

            # Stacked bar – breakdown
            fig_stack = go.Figure()
            models_sorted = df_p["Model"] + " (" + df_p["Napęd"] + ")"
            fig_stack.add_trace(go.Bar(
                name="Zakup", x=models_sorted, y=df_p["Cena"], marker_color="#94a3b8"))
            fig_stack.add_trace(go.Bar(
                name="Energia/Paliwo", x=models_sorted, y=df_p["energy"], marker_color="#f59e0b"))
            fig_stack.add_trace(go.Bar(
                name="Serwis", x=models_sorted, y=df_p["maint"], marker_color="#ef4444"))
            fig_stack.add_trace(go.Bar(
                name="Ubezpieczenie", x=models_sorted, y=df_p["ins"], marker_color="#8b5cf6"))
            fig_stack.add_trace(go.Bar(
                name="Tarcza podatkowa", x=models_sorted, y=-df_p["tax"], marker_color="#22c55e"))
            fig_stack.update_layout(
                title="Struktura TCO – rozbicie kosztów",
                barmode="relative", yaxis_title="PLN", height=450,
            )
            st.plotly_chart(fig_stack, use_container_width=True)

            # Detailed table
            show_p = df_p[["Model", "Napęd", "Cena", "tco", "energy",
                           "maint", "ins", "tax", "per_km", "monthly"]].copy()
            show_p.columns = ["Model", "Napęd", "Cena zakupu", "TCO",
                              "Energia/Paliwo", "Serwis", "Ubezp.",
                              "Tarcza pod.", "zł/km", "zł/mies."]
            for c in ["Cena zakupu", "TCO", "Energia/Paliwo", "Serwis",
                       "Ubezp.", "Tarcza pod.", "zł/mies."]:
                show_p[c] = show_p[c].apply(lambda x: f"{x:,.0f}")
            show_p["zł/km"] = show_p["zł/km"].apply(lambda x: f"{x:.2f}")
            st.dataframe(show_p, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# STOPKA
# ---------------------------------------------------------------------------
st.divider()
col_f1, col_f2, col_f3 = st.columns([1, 2, 1])
with col_f2:
    st.image("logo.png", width=280)
    st.markdown(
        '<div style="text-align: center; color: #666; font-size: 0.85em;">'
        f'© 2026 <strong>Paweł Mamcarz</strong>. Wszelkie prawa zastrzeżone. v{APP_VERSION}<br>'
        'Optymalizacja z użyciem <strong>HiGHS</strong> (Linear Programming). '
        'Dane rynkowe 2025/2026, bieżące ceny paliw.<br>'
        '<a href="https://www.linkedin.com/in/pawelmamcarz/" target="_blank">LinkedIn</a>'
        ' · <a href="mailto:pawel@mamcarz.com">pawel@mamcarz.com</a>'
        ' · +48 535 535 221'
        '</div>',
        unsafe_allow_html=True,
    )
