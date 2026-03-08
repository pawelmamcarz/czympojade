# Kalkulator kosztów: Auto Elektryczne (BEV) vs Spalinowe (ICE)
# z optymalizacją harmonogramu ładowania HiGHS.
# Narzędzie edukacyjne i analityczne uświadamiające ukryte koszty posiadania aut.

APP_VERSION = "0.17.0"

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import highspy
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_SCRAPING = True
except ImportError:
    HAS_SCRAPING = False

try:
    from market_data import (
        scrape_fuel_prices as db_fuel_prices,
        get_fuel_price_history,
        get_depreciation_curve as market_depreciation_curve,
        get_model_depreciation,
        scrape_car_listings,
        scrape_electricity_prices,
        get_data_freshness,
        get_electricity_price_history,
    )
    HAS_MARKET_DB = True
except ImportError:
    HAS_MARKET_DB = False

# ---------------------------------------------------------------------------
# KONFIGURACJA STRONY
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Czym pojadę w 2026 — jakie auto mi się opłaca kupić?",
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
        "**Kalkulator kosztów** EV vs ICE\n\n"
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
    st.markdown("---")
    st.markdown(
        "**Solver:** [HiGHS](https://highs.dev/) MILP\n\n"
        "Mixed-Integer Linear Programming do optymalizacji "
        "harmonogramu ładowania BEV."
    )
    if HAS_MARKET_DB:
        try:
            _freshness = get_data_freshness()
            if _freshness:
                st.markdown("---")
                st.caption(
                    f"Dane rynkowe: {_freshness['fuel_date']}\n\n"
                    f"Ogłoszenia w bazie: {_freshness['listings_count']:,}"
                )
        except Exception:
            pass
    st.caption(f"© 2026 Paweł Mamcarz. Wszelkie prawa zastrzeżone. v{APP_VERSION}")

st.title("Czym pojadę w 2026 — jakie auto mi się opłaca kupić?")
st.caption(
    "Porównanie pełnych kosztów posiadania auta elektrycznego i spalinowego. "
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

# Mnożniki prędkościowe: autostrada (130-140 km/h) vs droga krajowa (90 km/h)
# Wyższe zużycie z powodu oporu aerodynamicznego
HIGHWAY_SPEED_MULTIPLIER_BEV = 1.18  # +18% BEV na autostradzie vs krajowa
HIGHWAY_SPEED_MULTIPLIER_ICE = 1.12  # +12% ICE na autostradzie vs krajowa

# ---------------------------------------------------------------------------
# G14dynamic – opłata dystrybucyjna wg pory dnia (zł/kWh)
# ---------------------------------------------------------------------------
G14_DIST_BY_HOUR = (
    [0.0118] * 6 +   # 00-06: dark green (noc)
    [0.0470] * 4 +   # 06-10: light green (poranek)
    [0.3528] * 4 +   # 10-14: yellow (szczyt dzienny)
    [0.0470] * 3 +   # 14-17: light green (popołudnie)
    [2.3521] * 4 +   # 17-21: red (szczyt wieczorny)
    [0.0470] * 3     # 21-24: light green (wieczór)
)

# ---------------------------------------------------------------------------
# GreenWay 2026 – plany abonamentowe DC
# ---------------------------------------------------------------------------
GREENWAY_PLANS = {
    "Standard": {"monthly_fee": 0.00, "dc_per_kwh": 3.15},
    "Plus":     {"monthly_fee": 29.99, "dc_per_kwh": 2.40},
    "Max":      {"monthly_fee": 79.99, "dc_per_kwh": 2.10},
}

# ---------------------------------------------------------------------------
# Ionity 2026 – plany abonamentowe DC
# ---------------------------------------------------------------------------
IONITY_PLANS = {
    "Direct":  {"monthly_fee": 0.00,  "dc_per_kwh": 3.50},
    "Motion":  {"monthly_fee": 28.50, "dc_per_kwh": 2.50},
    "Power":   {"monthly_fee": 51.50, "dc_per_kwh": 2.05},
}

# ---------------------------------------------------------------------------
# Pompa ciepła (PC) – szacunkowe roczne zużycie prądu
# ---------------------------------------------------------------------------
HEAT_PUMP_ANNUAL_KWH = 4500  # typowa PC w domu 100-140 m², COP ~3.5


# ---------------------------------------------------------------------------
# POBIERANIE CEN PALIW Z E-PETROL.PL
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fuel_prices() -> dict:
    """Pobiera aktualne ceny paliw. Próbuje market_data DB, fallback do live scrape."""
    defaults = {"pb95": 6.50, "on": 6.40, "lpg": 3.20, "source": "domyślne"}
    if HAS_MARKET_DB:
        try:
            return db_fuel_prices()
        except Exception:
            pass
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
    city_kwh: float, highway_kwh: float, road_split: tuple,
    monthly_km: np.ndarray,
) -> tuple[float, np.ndarray]:
    """Zwraca (roczne kWh, tablica 12 miesięcznych kWh).

    road_split: (miasto%, krajowa%, autostrada%) — znormalizowane do 1.0
    Krajowa używa highway_kwh (WLTP), autostrada dodaje mnożnik prędkościowy.
    """
    pct_c, pct_r, pct_h = road_split
    monthly_kwh = np.zeros(12)
    for m in range(12):
        mc = bev_temp_multiplier(TEMPS_PL[m], "city")
        mh = bev_temp_multiplier(TEMPS_PL[m], "highway")
        monthly_kwh[m] = monthly_km[m] / 100 * (
            pct_c * city_kwh * mc
            + pct_r * highway_kwh * mh
            + pct_h * highway_kwh * mh * HIGHWAY_SPEED_MULTIPLIER_BEV
        )
    return float(monthly_kwh.sum()), monthly_kwh


def calc_annual_fuel_ice(
    city_l: float, highway_l: float, road_split: tuple,
    monthly_km: np.ndarray, fuel_price: float,
) -> tuple[float, float, np.ndarray]:
    """Zwraca (roczne litry, roczny koszt PLN, tablica 12 miesięcznych litrów).

    road_split: (miasto%, krajowa%, autostrada%) — znormalizowane do 1.0
    """
    pct_c, pct_r, pct_h = road_split
    monthly_liters = np.zeros(12)
    for m in range(12):
        mc = ice_temp_multiplier(TEMPS_PL[m], "city")
        mh = ice_temp_multiplier(TEMPS_PL[m], "highway")
        monthly_liters[m] = monthly_km[m] / 100 * (
            pct_c * city_l * mc
            + pct_r * highway_l * mh
            + pct_h * highway_l * mh * HIGHWAY_SPEED_MULTIPLIER_ICE
        )
    total_liters = float(monthly_liters.sum())
    return total_liters, total_liters * fuel_price, monthly_liters


# ---------------------------------------------------------------------------
# GreenWay – optymalizator planu abonamentowego
# ---------------------------------------------------------------------------

def greenway_optimal_plan(annual_dc_kwh: float) -> dict:
    """Wybiera optymalny plan GreenWay na podstawie rocznego zużycia DC."""
    results = {}
    for name, plan in GREENWAY_PLANS.items():
        annual_cost = plan["monthly_fee"] * 12 + plan["dc_per_kwh"] * annual_dc_kwh
        eff_per_kwh = annual_cost / annual_dc_kwh if annual_dc_kwh > 0 else plan["dc_per_kwh"]
        results[name] = {
            "annual_cost": annual_cost,
            "monthly_total": annual_cost / 12,
            "effective_per_kwh": eff_per_kwh,
            "subscription": plan["monthly_fee"],
            "rate": plan["dc_per_kwh"],
        }
    best = min(results, key=lambda k: results[k]["annual_cost"])
    return {"plans": results, "best": best, "best_data": results[best]}


def ionity_optimal_plan(annual_dc_kwh: float) -> dict:
    """Wybiera optymalny plan Ionity na podstawie rocznego zużycia DC."""
    results = {}
    for name, plan in IONITY_PLANS.items():
        annual_cost = plan["monthly_fee"] * 12 + plan["dc_per_kwh"] * annual_dc_kwh
        eff_per_kwh = annual_cost / annual_dc_kwh if annual_dc_kwh > 0 else plan["dc_per_kwh"]
        results[name] = {
            "annual_cost": annual_cost,
            "monthly_total": annual_cost / 12,
            "effective_per_kwh": eff_per_kwh,
            "subscription": plan["monthly_fee"],
            "rate": plan["dc_per_kwh"],
        }
    best = min(results, key=lambda k: results[k]["annual_cost"])
    return {"plans": results, "best": best, "best_data": results[best]}


# ---------------------------------------------------------------------------
# ML – SYNTETYCZNE DANE, KLASTERYZACJA, PROGNOZA
# ---------------------------------------------------------------------------

CLUSTER_NAMES = {
    0: ("Miejski Commuter", "Krótkie trasy miejskie, bez PV, prywatne użytkowanie"),
    1: ("Rodzinny Podmiejski", "Średni przebieg, mieszana jazda miasto/trasa"),
    2: ("Firmowy Flota", "Duży przebieg, trasa, użytkowanie firmowe"),
    3: ("Eco-Prosument", "PV + magazyn energii, świadomy energetycznie"),
    4: ("Long-Distance Traveler", "Bardzo duży przebieg, dominuje trasa"),
    5: ("Weekend Driver", "Mały przebieg, głównie miasto, rekreacyjnie"),
}


def generate_synthetic_profiles(n: int = 1000) -> pd.DataFrame:
    rng = np.random.RandomState(42)
    mileage = np.exp(rng.normal(np.log(15000), 0.6, n)).clip(5000, 80000).astype(int)
    city = rng.beta(3, 2, n).clip(0.10, 0.95)
    home_charger = rng.binomial(1, 0.60, n)
    pv = np.where(rng.random(n) < 0.30, rng.uniform(3, 20, n).round(1), 0.0)
    bess = np.where(pv > 0, np.where(rng.random(n) < 0.35, rng.uniform(5, 30, n).round(0), 0.0), 0.0)
    heat_pump = np.where(pv > 0, rng.binomial(1, 0.40, n), rng.binomial(1, 0.08, n))
    tax = rng.choice([0.12, 0.19, 0.32], n, p=[0.35, 0.45, 0.20])
    usage = rng.choice([0, 1, 2], n, p=[0.30, 0.25, 0.45])
    # Real-world factor: zależy od city%, przebiegu, stylu
    base_bev = 1.08 + 0.15 * city + 0.05 * (mileage < 10000) + rng.normal(0, 0.03, n)
    rw_bev = base_bev.clip(1.05, 1.35)
    base_ice = 1.04 + 0.10 * city + rng.normal(0, 0.02, n)
    rw_ice = base_ice.clip(1.02, 1.20)
    return pd.DataFrame({
        "annual_mileage": mileage, "city_pct": city,
        "has_home_charger": home_charger, "pv_kwp": pv,
        "bess_kwh": bess, "has_heat_pump": heat_pump,
        "tax_rate": tax, "usage_type": usage,
        "rw_factor_bev": rw_bev, "rw_factor_ice": rw_ice,
    })


def build_cluster_model(df: pd.DataFrame):
    features = ["annual_mileage", "city_pct", "has_home_charger", "pv_kwp", "has_heat_pump", "usage_type"]
    X = df[features].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    km = KMeans(n_clusters=6, random_state=42, n_init=10)
    km.fit(X_scaled)
    # Posortuj klastry wg centroidów dla stabilnych nazw
    centroids = scaler.inverse_transform(km.cluster_centers_)
    order = np.argsort(centroids[:, 0])  # sortuj po annual_mileage
    label_map = {old: new for new, old in enumerate(order)}
    return km, scaler, features, label_map


def build_realworld_model(df: pd.DataFrame):
    features = ["city_pct", "annual_mileage", "has_home_charger", "pv_kwp"]
    X = df[features].values
    y_bev = df["rw_factor_bev"].values
    y_ice = df["rw_factor_ice"].values
    rf_bev = RandomForestRegressor(n_estimators=50, max_depth=6, random_state=42)
    rf_bev.fit(X, y_bev)
    rf_ice = RandomForestRegressor(n_estimators=50, max_depth=6, random_state=42)
    rf_ice.fit(X, y_ice)
    r2_bev = rf_bev.score(X, y_bev)
    r2_ice = rf_ice.score(X, y_ice)
    return rf_bev, rf_ice, features, r2_bev, r2_ice


@st.cache_resource
def get_ml_models():
    profiles = generate_synthetic_profiles(1000)
    km, scaler, cl_features, label_map = build_cluster_model(profiles)
    rf_bev, rf_ice, rw_features, r2_bev, r2_ice = build_realworld_model(profiles)
    return {
        "km": km, "scaler": scaler, "cl_features": cl_features, "label_map": label_map,
        "rf_bev": rf_bev, "rf_ice": rf_ice, "rw_features": rw_features,
        "r2_bev": r2_bev, "r2_ice": r2_ice, "profiles": profiles,
    }


def predict_cluster(ml, user_vals: dict) -> dict:
    X = np.array([[user_vals[f] for f in ml["cl_features"]]])
    X_scaled = ml["scaler"].transform(X)
    raw_label = ml["km"].predict(X_scaled)[0]
    cluster_id = ml["label_map"][raw_label]
    name, desc = CLUSTER_NAMES[cluster_id]
    # Odległość do centroidu (podobieństwo)
    centroid = ml["km"].cluster_centers_[raw_label]
    dist = np.linalg.norm(X_scaled[0] - centroid)
    similarity = max(0, 100 - dist * 15)  # skalowanie do 0-100%
    # Centroid w oryginalnej skali
    centroid_orig = ml["scaler"].inverse_transform(centroid.reshape(1, -1))[0]
    return {
        "cluster_id": cluster_id, "name": name, "desc": desc,
        "similarity": similarity,
        "centroid": dict(zip(ml["cl_features"], centroid_orig)),
        "user": user_vals,
    }


def predict_realworld(ml, city_pct, annual_mileage, has_home_charger, pv_kwp):
    X = np.array([[city_pct, annual_mileage, int(has_home_charger), pv_kwp]])
    return ml["rf_bev"].predict(X)[0], ml["rf_ice"].predict(X)[0]


def forecast_monthly_costs(
    annual_energy_cost: float, fuel_cost_annual: float,
    bev_city_kwh: float, bev_highway_kwh: float, road_split: tuple,
    ice_city_l: float, ice_highway_l: float, fuel_price: float,
    annual_mileage: float,
) -> pd.DataFrame:
    pct_c, pct_r, pct_h = road_split
    monthly_km = np.array([annual_mileage * d / 365 for d in DAYS_IN_MONTH])
    months = MONTH_NAMES_PL
    bev_costs, ice_costs = [], []
    nominal_bev = pct_c * bev_city_kwh + pct_r * bev_highway_kwh + pct_h * bev_highway_kwh * HIGHWAY_SPEED_MULTIPLIER_BEV
    nominal_ice = pct_c * ice_city_l + pct_r * ice_highway_l + pct_h * ice_highway_l * HIGHWAY_SPEED_MULTIPLIER_ICE
    for m in range(12):
        t = TEMPS_PL[m]
        bev_mult = bev_temp_multiplier(t, "city") * pct_c + bev_temp_multiplier(t, "highway") * (pct_r + pct_h)
        ice_mult = ice_temp_multiplier(t, "city") * pct_c + ice_temp_multiplier(t, "highway") * (pct_r + pct_h)
        bev_base = monthly_km[m] / 100 * nominal_bev
        bev_real = bev_base * bev_mult
        bev_cost = bev_real / (annual_mileage / 100 * nominal_bev) * annual_energy_cost if annual_energy_cost > 0 else 0
        ice_liters = monthly_km[m] / 100 * nominal_ice * ice_mult
        ice_cost = ice_liters * fuel_price
        bev_costs.append(round(bev_cost, 0))
        ice_costs.append(round(ice_cost, 0))
    savings = [int(ic - bc) for ic, bc in zip(ice_costs, bev_costs)]
    return pd.DataFrame({
        "Miesiąc": months,
        "BEV (zł)": bev_costs,
        "ICE (zł)": ice_costs,
        "Oszczędność (zł)": savings,
    })


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
    PV_SELF_COST = 0.0

    # Opłata dystrybucyjna wg pory dnia (G14dynamic lub stała)
    if has_old_pv and pv_kwp > 0:
        dist_fees_24 = [0.08] * 24
    elif has_dynamic_tariff:
        dist_fees_24 = list(G14_DIST_BY_HOUR)
    else:
        dist_fees_24 = [0.30] * 24

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
    solver.setOptionValue('time_limit', 5.0)
    solver.setOptionValue('mip_rel_gap', 0.05)
    INF = highspy.kHighsInf

    max_ac = 11.0
    bess_rate = min(5.0, bess_kwh * 0.5) if bess_kwh > 0 else 0.0

    num_vars = SLOTS * 4
    costs_arr = np.zeros(num_vars)
    lower_arr = np.zeros(num_vars)
    upper_arr = np.zeros(num_vars)

    for s in range(SLOTS):
        d = DAYS[s // HPD]
        hod = s % HPD
        b = s * 4
        full_price = (tariff[s] + dist_fees_24[hod]) * d

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
        avg_dist = sum(dist_fees_24) / 24
        avg_price = float(np.mean(tariff)) + avg_dist
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
        pf = tariff[s] + dist_fees_24[s % HPD]

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

    if engine_type in ("ICE", "HEV", "PHEV"):
        min_c, max_c = ICE_MAINTENANCE_COSTS[segment_idx]
        base_per_km = (min_c + max_c) / 2 * discount
        if engine_type == "HEV":
            base_per_km *= HEV_MAINTENANCE_FACTOR
        elif engine_type == "PHEV":
            base_per_km *= PHEV_MAINTENANCE_FACTOR
        total_per_km = base_per_km
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
# LEASING / FINANSOWANIE
# ---------------------------------------------------------------------------

def calculate_leasing_params(vehicle_brutto, down_pct=0.10, lease_months=36,
                              buyout_pct=0.01, annual_rate=0.04):
    """Oblicz rozbicie leasingu operacyjnego: kapitał, odsetki, wpłata, wykup."""
    netto = vehicle_brutto / 1.23
    down_netto = netto * down_pct
    buyout_netto = netto * buyout_pct
    financed = netto - down_netto - buyout_netto
    # PMT formula
    r = annual_rate / 12
    if r > 0 and lease_months > 0:
        monthly_rate = financed * (r * (1 + r) ** lease_months) / ((1 + r) ** lease_months - 1)
    else:
        monthly_rate = financed / max(lease_months, 1)
    total_rates = monthly_rate * lease_months
    total_interest = max(0, total_rates - financed)
    total_capital = financed
    return {
        "vehicle_netto": netto,
        "down_netto": down_netto, "down_brutto": down_netto * 1.23,
        "monthly_rate_netto": monthly_rate,
        "total_rates_netto": total_rates, "total_rates_brutto": total_rates * 1.23,
        "total_capital_netto": total_capital,
        "total_interest_netto": total_interest,
        "buyout_netto": buyout_netto, "buyout_brutto": buyout_netto * 1.23,
        "total_cashflow_brutto": (down_netto + total_rates + buyout_netto) * 1.23,
        "financed_netto": financed,
        "lease_months": lease_months,
    }


def calculate_buyout_tax(buyout_value, resale_value, years_owned, tax_rate=0.19):
    """Podatek od sprzedaży auta wykupionego prywatnie (< 6 lat od wykupu)."""
    if years_owned >= 6 or resale_value <= buyout_value:
        return 0.0
    return (resale_value - buyout_value) * tax_rate


# ---------------------------------------------------------------------------
# TARCZA PODATKOWA 2026
# ---------------------------------------------------------------------------

def calculate_tax_shield(
    vehicle_price: float, engine_type: str,
    annual_fuel_cost: float, insurance_annual: float,
    period_years: int, tax_rate: float = 0.19,
    usage_type: str = "firmowe",  # firmowe / mieszane / prywatne
    leasing: dict = None,  # dict from calculate_leasing_params() or None for gotówka
) -> dict:
    """Szczegółowa tarcza podatkowa 2026 z rozbiciem VAT, KUP, leasingu."""
    # PHEV: limit BEV (225k) od 2025, HEV: limit ICE (100k)
    if engine_type in ("BEV", "PHEV"):
        limit = 225_000
    else:
        limit = 100_000
    is_bev = engine_type == "BEV"
    is_phev = engine_type == "PHEV"

    # --- Współczynniki wg użytkowania ---
    if usage_type == "firmowe":
        kup_pct = 1.0       # 100% kosztów w KUP
        vat_vehicle = 1.0   # 100% VAT od pojazdu (do limitu)
        # BEV/PHEV: 100% VAT od energii, ICE/HEV: 50% paliwo
        vat_fuel = 1.0 if (is_bev or is_phev) else 0.5
        vat_ekspl = 1.0     # 100% VAT od eksploatacji
    elif usage_type == "mieszane":
        kup_pct = 0.75      # 75% kosztów w KUP
        vat_vehicle = 0.5   # 50% VAT od pojazdu
        vat_fuel = 0.5      # 50% VAT od paliwa/energii
        vat_ekspl = 0.5     # 50% VAT od eksploatacji
    else:  # prywatne
        return {"total": 0, "vat_vehicle": 0, "vat_fuel_annual": 0, "vat_ekspl_annual": 0,
                "kup_annual": 0, "pit_annual": 0, "limit": limit, "kup_pct": 0,
                "vat_fuel_pct": 0, "vat_vehicle_pct": 0, "breakdown": {},
                "leasing_breakdown": None}

    # --- VAT od paliwa / energii (rocznie) ---
    vat_fuel_annual = annual_fuel_cost * 0.23 / 1.23 * vat_fuel

    # --- VAT od eksploatacji: ubezpieczenie (brak VAT), serwis (est. 50% kosztów) ---
    est_maint_annual = annual_fuel_cost * 0.3  # przybliżenie serwisu
    vat_ekspl_annual = est_maint_annual * 0.23 / 1.23 * vat_ekspl

    fuel_in_kup = annual_fuel_cost * kup_pct
    insurance_in_kup = insurance_annual * kup_pct

    if leasing is not None:
        # --- LEASING: proporcjonalny limit ---
        vehicle_netto = leasing["vehicle_netto"]
        proportion = min(limit, vehicle_netto) / vehicle_netto if vehicle_netto > 0 else 1.0

        # VAT od rat leasingowych + wpłaty (proporcjonalnie do limitu)
        vat_base = (leasing["down_netto"] + leasing["total_rates_netto"] + leasing["buyout_netto"])
        vat_vehicle_total = vat_base * 0.23 * proportion * vat_vehicle

        # KUP: wpłata własna (jednorazowa)
        down_kup = leasing["down_netto"] * proportion * kup_pct
        # KUP: raty kapitałowe (limitowane, rozłożone na okres)
        capital_kup_annual = (leasing["total_capital_netto"] * proportion / period_years) * kup_pct
        # KUP: odsetki — 100% w KUP, BEZ limitu proporcjonalnego
        interest_kup_annual = (leasing["total_interest_netto"] / period_years) * kup_pct
        # KUP: wykup (jednorazowy, limitowany)
        buyout_kup = leasing["buyout_netto"] * proportion * kup_pct

        lease_in_kup_annual = capital_kup_annual + interest_kup_annual
        kup_annual = lease_in_kup_annual + fuel_in_kup + insurance_in_kup
        # Jednorazowe KUP (wpłata + wykup) rozłożone na okres analizy
        kup_oneoff = (down_kup + buyout_kup) / period_years
        kup_annual += kup_oneoff
        pit_annual = kup_annual * tax_rate

        # --- Suma ---
        total_vat = vat_vehicle_total + (vat_fuel_annual + vat_ekspl_annual) * period_years
        total_pit = pit_annual * period_years
        total = total_vat + total_pit

        breakdown = {
            "VAT od leasingu (wpłata+raty+wykup)": vat_vehicle_total,
            f"VAT od {'energii' if is_bev else 'paliwa'} (rocznie)": vat_fuel_annual,
            "VAT od eksploatacji (rocznie)": vat_ekspl_annual,
            "PIT/CIT – wpłata własna w KUP": down_kup * tax_rate,
            "PIT/CIT – raty kapitałowe w KUP (rocznie)": capital_kup_annual * tax_rate,
            "PIT/CIT – odsetki w KUP (rocznie, bez limitu)": interest_kup_annual * tax_rate,
            "PIT/CIT – wykup w KUP": buyout_kup * tax_rate,
            f"PIT/CIT – KUP {'energia' if is_bev else 'paliwo'} (rocznie)": fuel_in_kup * tax_rate,
            "PIT/CIT – KUP ubezpieczenie (rocznie)": insurance_in_kup * tax_rate,
        }

        leasing_breakdown = {
            "proportion": proportion,
            "down_kup": down_kup,
            "capital_kup_annual": capital_kup_annual,
            "interest_kup_annual": interest_kup_annual,
            "buyout_kup": buyout_kup,
        }

    else:
        # --- GOTÓWKA: uproszczona amortyzacja ---
        price_for_vat = min(vehicle_price, limit)
        vat_vehicle_total = price_for_vat * 0.23 / 1.23 * vat_vehicle

        annual_lease_netto = vehicle_price / period_years  # amortyzacja (uproszczone)
        lease_in_kup = min(annual_lease_netto, limit / period_years) * kup_pct
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
            "PIT/CIT – KUP amortyzacja (rocznie)": lease_in_kup * tax_rate,
            f"PIT/CIT – KUP {'energia' if is_bev else 'paliwo'} (rocznie)": fuel_in_kup * tax_rate,
            "PIT/CIT – KUP ubezpieczenie (rocznie)": insurance_in_kup * tax_rate,
        }

        leasing_breakdown = None

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
        "leasing_breakdown": leasing_breakdown,
    }


# ---------------------------------------------------------------------------
# KRZYWE DEPRECJACJI – wartość rezydualna jako % ceny po N latach
# Kalibracja: dane AAA AUTO / autoDNA 2025, raporty DAT/Schwacke
# BEV: próg roku 8 = koniec gwarancji baterii HV → ostrzejszy spadek
# ---------------------------------------------------------------------------
DEPRECIATION_CURVE_NEW_ICE = {
    1: 0.78, 2: 0.65, 3: 0.55, 4: 0.47, 5: 0.40,
    6: 0.35, 7: 0.30, 8: 0.26, 9: 0.23, 10: 0.20,
}
DEPRECIATION_CURVE_NEW_BEV = {
    1: 0.82, 2: 0.70, 3: 0.62, 4: 0.55, 5: 0.48,
    6: 0.42, 7: 0.37, 8: 0.30, 9: 0.24, 10: 0.19,
}
DEPRECIATION_CURVE_USED_ICE = {
    1: 0.88, 2: 0.78, 3: 0.70, 4: 0.63, 5: 0.57,
    6: 0.52, 7: 0.47, 8: 0.43, 9: 0.39, 10: 0.36,
}
DEPRECIATION_CURVE_USED_BEV = {
    1: 0.87, 2: 0.76, 3: 0.67, 4: 0.59, 5: 0.52,
    6: 0.46, 7: 0.40, 8: 0.32, 9: 0.26, 10: 0.21,
}
# Hybrydy: między ICE a BEV — popularne marki (Toyota, Hyundai) trzymają wartość dobrze
DEPRECIATION_CURVE_NEW_HYB = {
    1: 0.80, 2: 0.67, 3: 0.58, 4: 0.50, 5: 0.43,
    6: 0.37, 7: 0.32, 8: 0.28, 9: 0.24, 10: 0.21,
}
DEPRECIATION_CURVE_USED_HYB = {
    1: 0.88, 2: 0.77, 3: 0.68, 4: 0.61, 5: 0.55,
    6: 0.49, 7: 0.44, 8: 0.39, 9: 0.35, 10: 0.31,
}

# Maintenance factors vs ICE base cost
HEV_MAINTENANCE_FACTOR = 0.85   # 85% kosztów ICE (hamowanie rekuperacyjne, mniej wymiany olejów)
PHEV_MAINTENANCE_FACTOR = 0.95  # 95% kosztów ICE (serwis spalinowy + bateria HV)


def calculate_depreciation(vehicle_price, segment_idx, period_years, engine_type, is_new,
                           make=None, model=None):
    """Deprecjacja nieliniowa z krzywą piecewise per rok.

    Priorytet: krzywa per model (market data) > krzywa per engine (market data) > hardcoded.
    BEV ma ostrzejszy spadek w roku 8 (koniec gwarancji baterii HV).
    Interpolacja liniowa dla wartości niecałkowitych i > 10 lat.
    """
    curve = None
    # Spróbuj krzywą z danych rynkowych
    if HAS_MARKET_DB:
        try:
            if make and model:
                curve = get_model_depreciation(make, model, engine_type)
            if curve is None:
                curve = market_depreciation_curve(engine_type, is_new)
        except Exception:
            pass
    # Fallback do hardcoded
    if curve is None:
        if is_new:
            if engine_type == "BEV":
                curve = DEPRECIATION_CURVE_NEW_BEV
            elif engine_type in ("HEV", "PHEV"):
                curve = DEPRECIATION_CURVE_NEW_HYB
            else:
                curve = DEPRECIATION_CURVE_NEW_ICE
        else:
            if engine_type == "BEV":
                curve = DEPRECIATION_CURVE_USED_BEV
            elif engine_type in ("HEV", "PHEV"):
                curve = DEPRECIATION_CURVE_USED_HYB
            else:
                curve = DEPRECIATION_CURVE_USED_ICE

    years = min(period_years, 10)
    if years <= 0:
        return 0.0

    # Interpolacja dla niecałkowitych lat
    if years in curve:
        rv_pct = curve[years]
    else:
        lower = max(k for k in curve if k <= years)
        upper = min(k for k in curve if k >= years)
        if lower == upper:
            rv_pct = curve[lower]
        else:
            frac = (years - lower) / (upper - lower)
            rv_pct = curve[lower] + frac * (curve[upper] - curve[lower])

    return vehicle_price * (1.0 - rv_pct)


def estimate_insurance(vehicle_price, engine_type):
    if engine_type == "BEV":
        rate = 0.05
    elif engine_type in ("HEV", "PHEV"):
        rate = 0.042
    else:
        rate = 0.04
    return 1200 + vehicle_price * rate


def calculate_tco_quick(
    vehicle_price, engine_type, is_new, annual_mileage, period_years, road_split,
    fuel_price=0, city_l=0, highway_l=0,
    city_kwh=0, highway_kwh=0, battery_cap=75,
    pv_kwp=0, bess_kwh=0, has_home_charger=True,
    has_dynamic_tariff=True, has_old_pv=False, suc_distance=30,
    use_tax=True, tax_rate=0.19, leasing=None,
) -> dict:
    """Szybkie obliczenie TCO dla optymalizatora (HiGHS LP wewnątrz dla BEV)."""
    seg = price_to_segment(vehicle_price)
    total_km = annual_mileage * period_years
    mkm = np.array([annual_mileage * d / 365 for d in DAYS_IN_MONTH])
    if engine_type == "ICE":
        _, fa, _ = calc_annual_fuel_ice(city_l, highway_l, road_split, mkm, fuel_price)
    else:
        dem, _ = calc_annual_consumption_bev(city_kwh, highway_kwh, road_split, mkm)
        ch = optimize_charging(dem, battery_cap, pv_kwp, bess_kwh,
                               has_home_charger, has_dynamic_tariff, has_old_pv,
                               suc_distance, annual_mileage)
        fa = ch["total_cost"]
    et = fa * period_years
    mt = calculate_maintenance_cost(seg, total_km, engine_type, is_new)["total"]
    ins = estimate_insurance(vehicle_price, engine_type) * period_years
    tx_data = calculate_tax_shield(vehicle_price, engine_type, fa,
                                   estimate_insurance(vehicle_price, engine_type),
                                   period_years, tax_rate,
                                   leasing=leasing) if use_tax else None
    tx = tx_data["total"] if tx_data else 0
    dep = calculate_depreciation(vehicle_price, seg, period_years, engine_type, is_new)
    rv = vehicle_price - dep  # residual value
    acquisition = leasing["total_cashflow_brutto"] if leasing else vehicle_price
    tco = acquisition + et + mt + ins - tx
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

# Codzienny scraping danych rynkowych (w tle, max raz/dzień)
if HAS_MARKET_DB:
    @st.cache_data(ttl=86400, show_spinner=False)
    def _daily_market_scrape():
        try:
            scrape_car_listings(max_models=5)
        except Exception:
            pass
        try:
            scrape_electricity_prices()
        except Exception:
            pass
        return True
    _daily_market_scrape()

# KROK 1: Dane pojazdu
st.header("1. Twoje pojazdy")

# --- Presety popularnych modeli (pogrupowane wg segmentu A–E) ---
_CUSTOM_ICE_NEW = {"price": 140_000, "city_l": 7.5, "hwy_l": 6.0, "fuel": 0}
_CUSTOM_ICE_USED = {"price": 65_000, "city_l": 7.5, "hwy_l": 6.0, "fuel": 0}
_CUSTOM_BEV_NEW = {"price": 195_000, "city_kwh": 16.5, "hwy_kwh": 19.0, "bat": 75}
_CUSTOM_BEV_USED = {"price": 120_000, "city_kwh": 16.5, "hwy_kwh": 19.0, "bat": 75}

ICE_PRESETS_NEW = {
    "A – Mini": {
        "Fiat 500 1.0 Hybrid": {"price": 75_000, "city_l": 5.5, "hwy_l": 4.5, "fuel": 0},
        "Toyota Aygo X 1.0": {"price": 72_000, "city_l": 5.0, "hwy_l": 4.2, "fuel": 0},
        "VW up! 1.0": {"price": 62_000, "city_l": 5.5, "hwy_l": 4.5, "fuel": 0},
    },
    "B – Małe": {
        "Toyota Yaris 1.5 Hybrid": {"price": 95_000, "city_l": 4.0, "hwy_l": 4.8, "fuel": 0},
        "VW Polo 1.0 TSI": {"price": 95_000, "city_l": 6.5, "hwy_l": 5.0, "fuel": 0},
        "Renault Clio 1.0 TCe LPG": {"price": 78_000, "city_l": 9.0, "hwy_l": 7.5, "fuel": 2},
        "Opel Corsa 1.2 Turbo": {"price": 88_000, "city_l": 6.5, "hwy_l": 5.0, "fuel": 0},
    },
    "C – Kompakt": {
        "Toyota Corolla 1.8 Hybrid": {"price": 135_000, "city_l": 4.5, "hwy_l": 5.5, "fuel": 0},
        "VW Golf 2.0 TDI": {"price": 145_000, "city_l": 6.5, "hwy_l": 5.0, "fuel": 1},
        "Hyundai i30 1.5 T-GDi": {"price": 120_000, "city_l": 7.0, "hwy_l": 5.5, "fuel": 0},
        "Skoda Octavia 2.0 TDI": {"price": 140_000, "city_l": 6.5, "hwy_l": 4.8, "fuel": 1},
        "Mazda 3 2.0 Hybrid": {"price": 125_000, "city_l": 5.5, "hwy_l": 5.0, "fuel": 0},
    },
    "D – Średni": {
        "Toyota Camry 2.5 Hybrid": {"price": 175_000, "city_l": 5.0, "hwy_l": 5.5, "fuel": 0},
        "VW Passat 2.0 TDI": {"price": 185_000, "city_l": 6.5, "hwy_l": 5.0, "fuel": 1},
        "Hyundai Tucson 1.6 T-GDi": {"price": 155_000, "city_l": 8.5, "hwy_l": 6.8, "fuel": 0},
        "Kia Sportage 1.6 T-GDi": {"price": 150_000, "city_l": 8.5, "hwy_l": 7.0, "fuel": 0},
        "Toyota RAV4 2.5 Hybrid": {"price": 185_000, "city_l": 5.5, "hwy_l": 6.5, "fuel": 0},
    },
    "E – Wyższy": {
        "BMW 320i": {"price": 210_000, "city_l": 8.5, "hwy_l": 6.5, "fuel": 0},
        "Mercedes C 200": {"price": 225_000, "city_l": 8.0, "hwy_l": 6.0, "fuel": 0},
        "Audi A4 40 TFSI": {"price": 215_000, "city_l": 8.0, "hwy_l": 6.0, "fuel": 0},
        "Volvo S60 B4": {"price": 210_000, "city_l": 7.5, "hwy_l": 6.0, "fuel": 0},
    },
}
ICE_PRESETS_USED = {
    "A – Mini": {
        "Fiat 500 1.2 2019": {"price": 35_000, "city_l": 6.0, "hwy_l": 5.0, "fuel": 0},
        "Toyota Aygo 1.0 2020": {"price": 38_000, "city_l": 5.0, "hwy_l": 4.2, "fuel": 0},
        "VW up! 1.0 2019": {"price": 30_000, "city_l": 5.5, "hwy_l": 4.5, "fuel": 0},
    },
    "B – Małe": {
        "Toyota Yaris III 1.5 Hybrid 2020": {"price": 55_000, "city_l": 4.2, "hwy_l": 5.0, "fuel": 0},
        "VW Polo VI 1.0 TSI 2020": {"price": 52_000, "city_l": 6.5, "hwy_l": 5.0, "fuel": 0},
        "Opel Corsa F 1.2 2020": {"price": 45_000, "city_l": 6.5, "hwy_l": 5.0, "fuel": 0},
        "Renault Clio V 1.0 TCe 2021": {"price": 48_000, "city_l": 6.5, "hwy_l": 5.2, "fuel": 0},
    },
    "C – Kompakt": {
        "Toyota Corolla 1.8 Hybrid 2021": {"price": 85_000, "city_l": 4.8, "hwy_l": 5.5, "fuel": 0},
        "VW Golf VII 2.0 TDI 2019": {"price": 65_000, "city_l": 7.0, "hwy_l": 5.0, "fuel": 1},
        "Skoda Octavia III 2.0 TDI 2018": {"price": 55_000, "city_l": 7.0, "hwy_l": 5.2, "fuel": 1},
        "Opel Astra K 1.6 CDTI 2019": {"price": 48_000, "city_l": 6.8, "hwy_l": 4.8, "fuel": 1},
        "Ford Focus 1.5 EcoBlue 2019": {"price": 45_000, "city_l": 6.5, "hwy_l": 4.5, "fuel": 1},
    },
    "D – Średni": {
        "Hyundai Tucson 1.6 CRDi 2019": {"price": 72_000, "city_l": 8.0, "hwy_l": 6.0, "fuel": 1},
        "Dacia Duster 1.5 dCi 2020": {"price": 52_000, "city_l": 7.5, "hwy_l": 6.0, "fuel": 1},
        "Kia Sportage 1.6 T-GDi 2020": {"price": 78_000, "city_l": 8.5, "hwy_l": 7.0, "fuel": 0},
        "Toyota RAV4 2.5 Hybrid 2020": {"price": 115_000, "city_l": 5.8, "hwy_l": 6.5, "fuel": 0},
    },
    "E – Wyższy": {
        "BMW 320d F30 2018": {"price": 75_000, "city_l": 8.0, "hwy_l": 5.5, "fuel": 1},
        "Mercedes C 220d W205 2019": {"price": 95_000, "city_l": 7.5, "hwy_l": 5.5, "fuel": 1},
        "Audi A4 2.0 TDI B9 2019": {"price": 85_000, "city_l": 7.5, "hwy_l": 5.5, "fuel": 1},
    },
}
BEV_PRESETS_NEW = {
    "A – Mini": {
        "Fiat 500e": {"price": 120_000, "city_kwh": 13.0, "hwy_kwh": 16.0, "bat": 42},
        "Dacia Spring": {"price": 85_000, "city_kwh": 14.0, "hwy_kwh": 17.0, "bat": 27},
    },
    "B – Małe": {
        "Renault 5 E-Tech": {"price": 125_000, "city_kwh": 14.5, "hwy_kwh": 17.0, "bat": 52},
        "MG4 Electric LR": {"price": 125_000, "city_kwh": 15.5, "hwy_kwh": 18.5, "bat": 64},
        "Opel Corsa-e": {"price": 135_000, "city_kwh": 15.0, "hwy_kwh": 17.5, "bat": 51},
    },
    "C – Kompakt": {
        "Tesla Model 3 RWD": {"price": 175_000, "city_kwh": 13.5, "hwy_kwh": 16.0, "bat": 60},
        "VW ID.3 Pro": {"price": 165_000, "city_kwh": 15.5, "hwy_kwh": 18.5, "bat": 58},
        "BYD Seal": {"price": 185_000, "city_kwh": 14.5, "hwy_kwh": 17.5, "bat": 82},
        "Hyundai Ioniq 6 LR": {"price": 205_000, "city_kwh": 13.5, "hwy_kwh": 15.5, "bat": 77},
    },
    "D – Średni": {
        "Tesla Model Y RWD": {"price": 189_000, "city_kwh": 14.5, "hwy_kwh": 17.0, "bat": 60},
        "VW ID.4 Pro": {"price": 195_000, "city_kwh": 17.0, "hwy_kwh": 20.0, "bat": 77},
        "Hyundai Ioniq 5 LR": {"price": 215_000, "city_kwh": 16.5, "hwy_kwh": 19.5, "bat": 77},
        "Skoda Enyaq iV 80": {"price": 199_000, "city_kwh": 17.5, "hwy_kwh": 20.5, "bat": 77},
        "BYD Atto 3": {"price": 145_000, "city_kwh": 16.0, "hwy_kwh": 19.5, "bat": 60},
    },
    "E – Wyższy": {
        "Tesla Model Y LR AWD": {"price": 219_000, "city_kwh": 16.0, "hwy_kwh": 19.0, "bat": 75},
        "BMW iX xDrive40": {"price": 310_000, "city_kwh": 18.0, "hwy_kwh": 21.0, "bat": 77},
        "Mercedes EQE 300": {"price": 350_000, "city_kwh": 16.0, "hwy_kwh": 18.5, "bat": 90},
    },
}
BEV_PRESETS_USED = {
    "A – Mini": {
        "Fiat 500e 2022": {"price": 72_000, "city_kwh": 13.5, "hwy_kwh": 16.5, "bat": 42},
        "Dacia Spring 2022": {"price": 48_000, "city_kwh": 14.5, "hwy_kwh": 17.5, "bat": 27},
    },
    "B – Małe": {
        "Renault Zoe R135 2021": {"price": 58_000, "city_kwh": 15.0, "hwy_kwh": 18.0, "bat": 52},
        "MG4 Electric 2023": {"price": 85_000, "city_kwh": 15.5, "hwy_kwh": 18.5, "bat": 64},
        "Nissan Leaf 40 kWh 2020": {"price": 65_000, "city_kwh": 16.0, "hwy_kwh": 19.0, "bat": 40},
    },
    "C – Kompakt": {
        "Tesla Model 3 SR+ 2021": {"price": 105_000, "city_kwh": 14.0, "hwy_kwh": 16.5, "bat": 55},
        "VW ID.3 Pro 2021": {"price": 85_000, "city_kwh": 15.5, "hwy_kwh": 18.5, "bat": 58},
        "BYD Seal 2023": {"price": 135_000, "city_kwh": 14.5, "hwy_kwh": 17.5, "bat": 82},
    },
    "D – Średni": {
        "Tesla Model Y LR 2022": {"price": 145_000, "city_kwh": 16.0, "hwy_kwh": 19.0, "bat": 75},
        "VW ID.4 Pro 2022": {"price": 120_000, "city_kwh": 17.0, "hwy_kwh": 20.0, "bat": 77},
        "Hyundai Ioniq 5 LR 2022": {"price": 135_000, "city_kwh": 16.5, "hwy_kwh": 19.5, "bat": 77},
        "Skoda Enyaq 80 2022": {"price": 125_000, "city_kwh": 17.5, "hwy_kwh": 20.5, "bat": 77},
    },
    "E – Wyższy": {
        "BMW iX1 eDrive20 2023": {"price": 155_000, "city_kwh": 17.0, "hwy_kwh": 20.0, "bat": 65},
        "Lexus UX 300e 2022": {"price": 135_000, "city_kwh": 17.0, "hwy_kwh": 20.0, "bat": 54},
        "Tesla Model Y LR AWD 2022": {"price": 175_000, "city_kwh": 16.0, "hwy_kwh": 19.0, "bat": 75},
    },
}

# ---------------------------------------------------------------------------
# HYBRYDY – presety HEV i PHEV pogrupowane wg segmentów
# hybrid_type: "HEV" (pełna hybryda, bez ładowania) / "PHEV" (plug-in, z baterią)
# elec_pct: szacowany % jazdy na prądzie (0 dla HEV, 40-80% dla PHEV przy ładowaniu w domu)
# city_l / hwy_l: spalanie w trybie hybrydowym (PHEV: gdy bateria wyczerpana = charge-sustaining)
# city_kwh / hwy_kwh: zużycie prądu w trybie elektrycznym PHEV
# ---------------------------------------------------------------------------
_CUSTOM_HYB_NEW = {"price": 150_000, "city_l": 5.0, "hwy_l": 5.5, "fuel": 0,
                   "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0}
_CUSTOM_HYB_USED = {"price": 80_000, "city_l": 5.0, "hwy_l": 5.5, "fuel": 0,
                    "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0}

HYB_PRESETS_NEW = {
    "A – Mini": {
        "Toyota Yaris 1.5 Hybrid": {"price": 95_000, "city_l": 3.8, "hwy_l": 4.8, "fuel": 0,
                                     "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0},
    },
    "B – Małe": {
        "Toyota Yaris Cross 1.5 Hybrid": {"price": 120_000, "city_l": 4.8, "hwy_l": 5.5, "fuel": 0,
                                           "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0},
        "Renault Clio E-Tech Hybrid": {"price": 98_000, "city_l": 4.2, "hwy_l": 5.0, "fuel": 0,
                                        "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0},
    },
    "C – Kompakt": {
        "Toyota Corolla 2.0 Hybrid": {"price": 145_000, "city_l": 4.3, "hwy_l": 5.0, "fuel": 0,
                                       "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0},
        "Toyota C-HR 2.0 Hybrid": {"price": 150_000, "city_l": 4.8, "hwy_l": 5.5, "fuel": 0,
                                    "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0},
        "Kia Niro 1.6 PHEV": {"price": 165_000, "city_l": 1.4, "hwy_l": 5.5, "fuel": 0,
                               "hybrid_type": "PHEV", "bat": 11.1, "city_kwh": 14.0, "hwy_kwh": 17.0, "elec_pct": 0.60},
    },
    "D – Średni": {
        "Toyota RAV4 2.5 Hybrid": {"price": 185_000, "city_l": 5.2, "hwy_l": 6.0, "fuel": 0,
                                    "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0},
        "Hyundai Tucson 1.6 HEV": {"price": 158_000, "city_l": 6.0, "hwy_l": 6.5, "fuel": 0,
                                    "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0},
        "Toyota RAV4 2.5 PHEV": {"price": 235_000, "city_l": 1.0, "hwy_l": 6.0, "fuel": 0,
                                  "hybrid_type": "PHEV", "bat": 18.1, "city_kwh": 16.0, "hwy_kwh": 19.0, "elec_pct": 0.65},
        "Hyundai Tucson 1.6 PHEV": {"price": 205_000, "city_l": 1.4, "hwy_l": 6.5, "fuel": 0,
                                     "hybrid_type": "PHEV", "bat": 13.8, "city_kwh": 15.5, "hwy_kwh": 18.5, "elec_pct": 0.55},
        "Mitsubishi Outlander PHEV": {"price": 215_000, "city_l": 1.8, "hwy_l": 7.0, "fuel": 0,
                                      "hybrid_type": "PHEV", "bat": 20.0, "city_kwh": 17.0, "hwy_kwh": 20.0, "elec_pct": 0.60},
    },
    "E – Wyższy": {
        "BMW 330e": {"price": 255_000, "city_l": 1.5, "hwy_l": 6.5, "fuel": 0,
                     "hybrid_type": "PHEV", "bat": 12.0, "city_kwh": 15.0, "hwy_kwh": 18.0, "elec_pct": 0.50},
        "Mercedes C 300 e": {"price": 280_000, "city_l": 1.2, "hwy_l": 6.0, "fuel": 0,
                              "hybrid_type": "PHEV", "bat": 25.4, "city_kwh": 16.0, "hwy_kwh": 19.0, "elec_pct": 0.60},
        "Volvo S60 T8 PHEV": {"price": 270_000, "city_l": 1.5, "hwy_l": 7.0, "fuel": 0,
                               "hybrid_type": "PHEV", "bat": 18.8, "city_kwh": 16.0, "hwy_kwh": 19.5, "elec_pct": 0.55},
    },
}

HYB_PRESETS_USED = {
    "A – Mini": {
        "Toyota Yaris 1.5 Hybrid 2021": {"price": 55_000, "city_l": 4.0, "hwy_l": 5.0, "fuel": 0,
                                          "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0},
    },
    "B – Małe": {
        "Toyota Yaris Cross 1.5 HEV 2022": {"price": 80_000, "city_l": 5.0, "hwy_l": 5.5, "fuel": 0,
                                              "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0},
        "Renault Clio E-Tech 2022": {"price": 58_000, "city_l": 4.5, "hwy_l": 5.0, "fuel": 0,
                                      "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0},
    },
    "C – Kompakt": {
        "Toyota Corolla 2.0 Hybrid 2021": {"price": 85_000, "city_l": 4.5, "hwy_l": 5.2, "fuel": 0,
                                            "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0},
        "Toyota C-HR 2.0 Hybrid 2022": {"price": 95_000, "city_l": 5.0, "hwy_l": 5.5, "fuel": 0,
                                         "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0},
    },
    "D – Średni": {
        "Toyota RAV4 2.5 HEV 2021": {"price": 115_000, "city_l": 5.5, "hwy_l": 6.2, "fuel": 0,
                                       "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0},
        "Mitsubishi Outlander PHEV 2021": {"price": 105_000, "city_l": 2.0, "hwy_l": 7.5, "fuel": 0,
                                            "hybrid_type": "PHEV", "bat": 13.8, "city_kwh": 17.0, "hwy_kwh": 20.0, "elec_pct": 0.50},
        "Hyundai Tucson HEV 2022": {"price": 105_000, "city_l": 6.2, "hwy_l": 6.8, "fuel": 0,
                                     "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0},
    },
    "E – Wyższy": {
        "BMW 330e 2021": {"price": 140_000, "city_l": 1.8, "hwy_l": 7.0, "fuel": 0,
                          "hybrid_type": "PHEV", "bat": 12.0, "city_kwh": 15.0, "hwy_kwh": 18.0, "elec_pct": 0.45},
        "Volvo XC60 T8 PHEV 2021": {"price": 165_000, "city_l": 2.0, "hwy_l": 8.0, "fuel": 0,
                                     "hybrid_type": "PHEV", "bat": 11.6, "city_kwh": 17.0, "hwy_kwh": 20.5, "elec_pct": 0.45},
    },
}

CAR_SEGMENTS = ["A – Mini", "B – Małe", "C – Kompakt", "D – Średni", "E – Wyższy"]

# ---------------------------------------------------------------------------
# ODCZYT PARAMETRÓW Z URL (query_params) — umożliwia udostępnianie linku
# ---------------------------------------------------------------------------
_qp = st.query_params
_qp_v_ice = int(_qp.get("v_ice", 0))
_qp_v_bev = int(_qp.get("v_bev", 0))
_qp_km = int(_qp.get("km", 0))
_qp_yrs = int(_qp.get("yrs", 0))
_qp_city = int(_qp.get("city", 0))
_qp_rural = int(_qp.get("rural", 0))
_qp_hwy = int(_qp.get("hwy", 0))

col_ice, col_hyb, col_bev = st.columns(3)

with col_ice:
    st.subheader("ICE (spalinowe)")
    is_new_ice = st.radio(
        "Stan ICE", ["Nowy", "Używany"], horizontal=True, key="is_new_ice",
        help="Nowy = auto z salonu. Używany = z rynku wtórnego (wyższe koszty serwisowe).",
    ) == "Nowy"
    ice_presets_all = ICE_PRESETS_NEW if is_new_ice else ICE_PRESETS_USED
    ice_segment_opts = ["Własne parametry"] + CAR_SEGMENTS
    ice_segment = st.selectbox(
        "Segment ICE", ice_segment_opts, index=3, key="seg_ice",
        help="A=mini, B=małe, C=kompakt, D=średni/SUV, E=wyższy. "
             "Własne parametry = wpisz ręcznie.",
    )
    if ice_segment == "Własne parametry":
        ice_p = _CUSTOM_ICE_NEW if is_new_ice else _CUSTOM_ICE_USED
        ice_preset_name = "Własne parametry"
    else:
        ice_models = ice_presets_all.get(ice_segment, {})
        ice_preset_name = st.selectbox(
            "Model ICE", list(ice_models.keys()), index=0,
            help="Wybierz model – cena i spalanie wypełnią się automatycznie.",
        )
        ice_p = ice_models[ice_preset_name]
    ice_model = st.text_input(
        "Marka i model ICE",
        value=ice_preset_name if ice_preset_name != "Własne parametry" else (
            "Toyota Corolla 2024" if is_new_ice else "Toyota Corolla 2019"),
        help="Np. Toyota Corolla 1.8, VW Golf 2.0 TDI, Dacia Duster 1.5 dCi",
    )
    vehicle_value_ice = st.number_input(
        "Wartość auta ICE – brutto (zł)",
        min_value=5_000, max_value=1_000_000,
        value=_qp_v_ice if _qp_v_ice > 0 else ice_p["price"],
        step=5_000,
        help="Cena katalogowa / rynkowa brutto (z VAT).",
    )
    financing_mode_ice = st.radio(
        "Forma finansowania ICE",
        ["Leasing", "Gotówka"],
        horizontal=True, index=0,
        help="Leasing: wpłata + raty + wykup. Gotówka: jednorazowy zakup.",
    )
    leasing_ice = None
    if financing_mode_ice == "Leasing":
        lc1, lc2 = st.columns(2)
        with lc1:
            down_pct_ice = st.slider(
                "Wpłata własna ICE (%)", 0, 50, 10,
                help="Typowo 0-30% wartości auta.",
            ) / 100.0
            lease_months_ice = st.selectbox(
                "Okres leasingu ICE (mies.)", [24, 36, 48, 60], index=1,
            )
        with lc2:
            buyout_pct_ice = st.slider(
                "Wykup ICE (%)", 0, 30, 1,
                help="Wartość wykupu jako % wartości auta. 1% = symboliczny wykup.",
            ) / 100.0
        leasing_ice = calculate_leasing_params(
            vehicle_value_ice, down_pct_ice, lease_months_ice, buyout_pct_ice,
        )
        st.caption(
            f"Rata netto: **{leasing_ice['monthly_rate_netto']:,.0f} zł** | "
            f"Suma wpłat brutto: {leasing_ice['total_cashflow_brutto']:,.0f} zł | "
            f"Odsetki: {leasing_ice['total_interest_netto']:,.0f} zł netto | "
            f"Wykup: {leasing_ice['buyout_brutto']:,.0f} zł brutto"
        )
        total_acquisition_ice = leasing_ice["total_cashflow_brutto"]
    else:
        total_acquisition_ice = vehicle_value_ice
    # Backward compat alias
    vehicle_price_ice = vehicle_value_ice
    fuel_type = st.selectbox(
        "Rodzaj paliwa",
        ["Benzyna (PB95)", "Diesel (ON)", "LPG"],
        index=ice_p["fuel"],
    )

with col_hyb:
    st.subheader("Hybryda (HEV / PHEV)")
    is_new_hyb = st.radio(
        "Stan HYB", ["Nowy", "Używany"], horizontal=True, key="is_new_hyb",
        help="Nowy = auto z salonu. Używany = z rynku wtórnego.",
    ) == "Nowy"
    hyb_presets_all = HYB_PRESETS_NEW if is_new_hyb else HYB_PRESETS_USED
    hyb_segment_opts = ["Własne parametry"] + CAR_SEGMENTS
    hyb_segment = st.selectbox(
        "Segment Hybryda", hyb_segment_opts, index=4, key="seg_hyb",
        help="A=mini, B=małe, C=kompakt, D=średni/SUV, E=wyższy.",
    )
    if hyb_segment == "Własne parametry":
        hyb_p = _CUSTOM_HYB_NEW if is_new_hyb else _CUSTOM_HYB_USED
        hyb_preset_name = "Własne parametry"
    else:
        hyb_models = hyb_presets_all.get(hyb_segment, {})
        hyb_preset_name = st.selectbox(
            "Model Hybryda", list(hyb_models.keys()), index=0,
            help="Wybierz model — cena i spalanie wypełnią się automatycznie.",
        )
        hyb_p = hyb_models[hyb_preset_name]
    hyb_model = st.text_input(
        "Marka i model Hybryda",
        value=hyb_preset_name if hyb_preset_name != "Własne parametry" else (
            "Toyota Corolla 2.0 Hybrid 2024" if is_new_hyb else "Toyota Corolla 2.0 Hybrid 2021"),
        help="Np. Toyota Corolla Hybrid, RAV4 PHEV, BMW 330e",
    )
    hyb_type = hyb_p.get("hybrid_type", "HEV")
    st.caption(f"Typ: **{hyb_type}** {'(ładowanie z gniazdka + paliwo)' if hyb_type == 'PHEV' else '(paliwo, bez ładowania z gniazdka)'}")
    vehicle_value_hyb = st.number_input(
        "Wartość auta HYB – brutto (zł)",
        min_value=5_000, max_value=1_000_000,
        value=hyb_p["price"],
        step=5_000,
        help="Cena katalogowa / rynkowa brutto (z VAT).",
    )
    financing_mode_hyb = st.radio(
        "Forma finansowania HYB",
        ["Leasing", "Gotówka"],
        horizontal=True, index=0,
        help="Leasing: wpłata + raty + wykup. Gotówka: jednorazowy zakup.",
    )
    leasing_hyb = None
    if financing_mode_hyb == "Leasing":
        lc1h, lc2h = st.columns(2)
        with lc1h:
            down_pct_hyb = st.slider(
                "Wpłata własna HYB (%)", 0, 50, 10,
                help="Typowo 0-30% wartości auta.",
            ) / 100.0
            lease_months_hyb = st.selectbox(
                "Okres leasingu HYB (mies.)", [24, 36, 48, 60], index=1,
            )
        with lc2h:
            buyout_pct_hyb = st.slider(
                "Wykup HYB (%)", 0, 30, 1,
                help="Wartość wykupu jako % wartości auta. 1% = symboliczny wykup.",
            ) / 100.0
        leasing_hyb = calculate_leasing_params(
            vehicle_value_hyb, down_pct_hyb, lease_months_hyb, buyout_pct_hyb,
        )
        st.caption(
            f"Rata netto: **{leasing_hyb['monthly_rate_netto']:,.0f} zł** | "
            f"Suma wpłat brutto: {leasing_hyb['total_cashflow_brutto']:,.0f} zł | "
            f"Odsetki: {leasing_hyb['total_interest_netto']:,.0f} zł netto | "
            f"Wykup: {leasing_hyb['buyout_brutto']:,.0f} zł brutto"
        )
        total_acquisition_hyb = leasing_hyb["total_cashflow_brutto"]
    else:
        total_acquisition_hyb = vehicle_value_hyb
    vehicle_price_hyb = vehicle_value_hyb
    hyb_fuel_type_idx = hyb_p.get("fuel", 0)
    hyb_fuel_type = ["Benzyna (PB95)", "Diesel (ON)", "LPG"][hyb_fuel_type_idx]
    if hyb_type == "PHEV":
        hyb_elec_pct = st.slider(
            "% jazdy na prądzie (PHEV)",
            10, 95,
            int(hyb_p.get("elec_pct", 0.6) * 100),
            step=5,
            help="Szacowany udział jazdy na silniku elektrycznym. "
                 "Zależy od tras, ładowania w domu i pojemności baterii.",
        ) / 100.0
    else:
        hyb_elec_pct = 0.0

with col_bev:
    st.subheader("BEV (elektryczne)")
    is_new_bev = st.radio(
        "Stan BEV", ["Nowy", "Używany"], horizontal=True, key="is_new_bev",
        help="Nowy = auto z salonu. Używany = z rynku wtórnego (wyższe koszty serwisowe).",
    ) == "Nowy"
    bev_presets_all = BEV_PRESETS_NEW if is_new_bev else BEV_PRESETS_USED
    bev_segment_opts = ["Własne parametry"] + CAR_SEGMENTS
    bev_segment = st.selectbox(
        "Segment BEV", bev_segment_opts, index=4, key="seg_bev",
        help="A=mini, B=małe, C=kompakt, D=średni/SUV, E=wyższy. "
             "Własne parametry = wpisz ręcznie.",
    )
    if bev_segment == "Własne parametry":
        bev_p = _CUSTOM_BEV_NEW if is_new_bev else _CUSTOM_BEV_USED
        bev_preset_name = "Własne parametry"
    else:
        bev_models = bev_presets_all.get(bev_segment, {})
        bev_preset_name = st.selectbox(
            "Model BEV", list(bev_models.keys()), index=0,
            help="Wybierz model – cena, zużycie i bateria wypełnią się automatycznie.",
        )
        bev_p = bev_models[bev_preset_name]
    bev_model = st.text_input(
        "Marka i model BEV",
        value=bev_preset_name if bev_preset_name != "Własne parametry" else (
            "Tesla Model Y LR 2024" if is_new_bev else "Tesla Model 3 SR+ 2021"),
        help="Np. Tesla Model Y LR, BYD Atto 3, Hyundai Ioniq 5",
    )
    vehicle_value_bev = st.number_input(
        "Wartość auta BEV – brutto (zł)",
        min_value=5_000, max_value=1_000_000,
        value=_qp_v_bev if _qp_v_bev > 0 else bev_p["price"],
        step=5_000,
        help="Cena katalogowa / rynkowa brutto (z VAT).",
    )
    financing_mode_bev = st.radio(
        "Forma finansowania BEV",
        ["Leasing", "Gotówka"],
        horizontal=True, index=0,
        help="Leasing: wpłata + raty + wykup. Gotówka: jednorazowy zakup.",
    )
    leasing_bev = None
    if financing_mode_bev == "Leasing":
        lc1b, lc2b = st.columns(2)
        with lc1b:
            down_pct_bev = st.slider(
                "Wpłata własna BEV (%)", 0, 50, 10,
                help="Typowo 0-30% wartości auta.",
            ) / 100.0
            lease_months_bev = st.selectbox(
                "Okres leasingu BEV (mies.)", [24, 36, 48, 60], index=1,
            )
        with lc2b:
            buyout_pct_bev = st.slider(
                "Wykup BEV (%)", 0, 30, 1,
                help="Wartość wykupu jako % wartości auta. 1% = symboliczny wykup.",
            ) / 100.0
        leasing_bev = calculate_leasing_params(
            vehicle_value_bev, down_pct_bev, lease_months_bev, buyout_pct_bev,
        )
        st.caption(
            f"Rata netto: **{leasing_bev['monthly_rate_netto']:,.0f} zł** | "
            f"Suma wpłat brutto: {leasing_bev['total_cashflow_brutto']:,.0f} zł | "
            f"Odsetki: {leasing_bev['total_interest_netto']:,.0f} zł netto | "
            f"Wykup: {leasing_bev['buyout_brutto']:,.0f} zł brutto"
        )
        total_acquisition_bev = leasing_bev["total_cashflow_brutto"]
    else:
        total_acquisition_bev = vehicle_value_bev
    # Backward compat alias
    vehicle_price_bev = vehicle_value_bev

# Auto-detect segments for maintenance calculations
segment_idx_ice = price_to_segment(vehicle_value_ice)
segment_idx_bev = price_to_segment(vehicle_value_bev)

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
        "Roczny przebieg (km)", min_value=5000, max_value=200_000,
        value=_qp_km if _qp_km >= 5000 else 30_000, step=5000,
    )
    # Domyślny okres = max okres leasingu (jeśli aktywny)
    _default_period = 3
    if leasing_ice is not None or leasing_bev is not None:
        _lm = max(
            leasing_ice["lease_months"] if leasing_ice else 0,
            leasing_bev["lease_months"] if leasing_bev else 0,
        )
        _default_period = max(1, min(10, -(-_lm // 12)))  # ceil division, clamp 1-10
    period_years = st.slider("Okres analizy (lata)", 1, 10,
                             _qp_yrs if 1 <= _qp_yrs <= 10 else _default_period)
with col2:
    st.markdown("**Profil tras**")
    _rs1, _rs2, _rs3 = st.columns(3)
    with _rs1:
        pct_city = st.slider("Miasto (%)", 0, 100,
                             _qp_city if 0 < _qp_city <= 100 else 50, key="pct_city")
    with _rs2:
        pct_rural = st.slider("Krajowa (%)", 0, 100,
                              _qp_rural if 0 < _qp_rural <= 100 else 30, key="pct_rural")
    with _rs3:
        pct_highway = st.slider("Autostrada (%)", 0, 100,
                                _qp_hwy if 0 < _qp_hwy <= 100 else 20, key="pct_highway")
    _total = pct_city + pct_rural + pct_highway
    if _total == 0:
        _total = 1
    pct_city_n = pct_city / _total
    pct_rural_n = pct_rural / _total
    pct_highway_n = pct_highway / _total
    road_split = (pct_city_n, pct_rural_n, pct_highway_n)
    city_pct = pct_city_n  # backward compat dla ML/klasteryzacji
    st.caption(
        f"Normalizacja: Miasto {pct_city_n:.0%} · Krajowa {pct_rural_n:.0%} "
        f"· Autostrada {pct_highway_n:.0%}"
    )

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

if HAS_MARKET_DB:
    with st.expander("Trend cen paliw (ostatnie 90 dni)"):
        _fuel_hist = get_fuel_price_history(90)
        if not _fuel_hist.empty:
            _fig_fh = go.Figure()
            _fuel_names = {"pb95": "PB95", "on": "ON (Diesel)", "lpg": "LPG"}
            for col in _fuel_hist.columns:
                _fig_fh.add_trace(go.Scatter(
                    x=_fuel_hist.index, y=_fuel_hist[col],
                    name=_fuel_names.get(col, col.upper()), mode="lines+markers",
                ))
            _fig_fh.update_layout(
                yaxis_title="zl/l", height=300, margin=dict(t=20, b=30),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(_fig_fh, use_container_width=True)
        else:
            st.caption("Brak danych historycznych. Trend pojawi sie po kilku dniach zbierania danych.")

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

st.subheader("Spalanie Hybryda (nominalne)")
col_hc1, col_hc2 = st.columns(2)
with col_hc1:
    hyb_city_l = st.number_input(
        "Hybryda: miasto (l/100 km)", min_value=0.5, max_value=20.0,
        value=hyb_p["city_l"], step=0.5,
        help="Spalanie w cyklu miejskim. PHEV: w trybie charge-sustaining (bat wyczerpana)." if hyb_type == "PHEV"
        else "Spalanie w cyklu miejskim (tryb hybrydowy).",
    )
with col_hc2:
    hyb_highway_l = st.number_input(
        "Hybryda: trasa (l/100 km)", min_value=3.0, max_value=20.0,
        value=hyb_p["hwy_l"], step=0.5,
        help="Spalanie w cyklu trasowym.",
    )
if hyb_type == "PHEV":
    col_hce1, col_hce2 = st.columns(2)
    with col_hce1:
        hyb_city_kwh = st.number_input(
            "PHEV: miasto (kWh/100 km)", min_value=8.0, max_value=30.0,
            value=float(hyb_p.get("city_kwh", 15.0)), step=0.5,
            help="Zużycie prądu w trybie elektrycznym (EV mode).",
        )
    with col_hce2:
        hyb_highway_kwh = st.number_input(
            "PHEV: trasa (kWh/100 km)", min_value=10.0, max_value=35.0,
            value=float(hyb_p.get("hwy_kwh", 18.0)), step=0.5,
            help="Zużycie prądu w trasie (EV mode).",
        )
    hyb_bat_cap = st.number_input(
        "Bateria PHEV (kWh)", min_value=5, max_value=30,
        value=int(hyb_p.get("bat", 12)), step=1,
        help="Pojemność baterii HV plug-in.",
    )
else:
    hyb_city_kwh = 0.0
    hyb_highway_kwh = 0.0
    hyb_bat_cap = 0

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
    pv_kwp = st.number_input(
        "Instalacja PV (kWp)", min_value=0.0, max_value=50.0, value=5.0, step=0.5,
        help="Moc instalacji fotowoltaicznej w kWp. W Polsce ~1 000 kWh/kWp rocznie. "
             "Np. 5 kWp → ~5 000 kWh/rok (~417 kWh/mies.). "
             "Sprawdź na fakturze z instalatora lub w aplikacji inwertera.",
    )
    if pv_kwp > 0:
        _pv_yr = pv_kwp * 1000
        st.caption(f"Szacowana produkcja: **~{_pv_yr:,.0f} kWh/rok** (~{_pv_yr / 12:.0f} kWh/mies.)")
    bess_kwh = st.number_input("Magazyn energii domowy (kWh)", min_value=0.0, max_value=150.0, value=0.0, step=5.0)
    has_heat_pump = st.checkbox(
        "Pompa ciepła (PC) w domu", value=False,
        help=f"Typowe zużycie PC: ~{HEAT_PUMP_ANNUAL_KWH:,} kWh/rok (dom 100-140 m², COP ~3.5). "
             "Zmienia optymalne proporcje PV:BESS.",
    )

# BESS Smart Advisor
if pv_kwp > 0:
    bess_ratio = 2.0 if has_heat_pump else 1.5
    recommended_bess = pv_kwp / bess_ratio
    st.info(
        f"**BESS Advisor:** PV {pv_kwp:.1f} kWp "
        f"{'+ pompa ciepła' if has_heat_pump else '(bez PC)'} → "
        f"ratio PV:BESS = {bess_ratio}:1 → "
        f"zalecany BESS: **{recommended_bess:.0f} kWh**"
        + (f" (masz: {bess_kwh:.0f} kWh)" if bess_kwh > 0 else "")
    )

# Szacunkowe zużycie prądu w domu (PC + BEV)
if has_heat_pump:
    pct_c, pct_r, pct_h = road_split
    est_bev_annual = annual_mileage / 100 * (
        pct_c * bev_city_kwh + pct_r * bev_highway_kwh
        + pct_h * bev_highway_kwh * HIGHWAY_SPEED_MULTIPLIER_BEV
    )
    est_home_base = 3500  # typowe zużycie domu bez PC i BEV
    total_home_kwh = est_home_base + HEAT_PUMP_ANNUAL_KWH + est_bev_annual
    with st.expander("Szacunkowe zużycie prądu w domu"):
        st.markdown(
            f"| Źródło | kWh/rok | kWh/mies. |\n"
            f"| --- | ---: | ---: |\n"
            f"| Dom (AGD, oświetlenie) | {est_home_base:,.0f} | {est_home_base / 12:.0f} |\n"
            f"| **Pompa ciepła (PC)** | **{HEAT_PUMP_ANNUAL_KWH:,}** | **{HEAT_PUMP_ANNUAL_KWH / 12:.0f}** |\n"
            f"| **BEV ładowanie** | **{est_bev_annual:,.0f}** | **{est_bev_annual / 12:.0f}** |\n"
            f"| **RAZEM** | **{total_home_kwh:,.0f}** | **{total_home_kwh / 12:.0f}** |"
        )
        if pv_kwp > 0:
            pv_annual_est = pv_kwp * 1000  # ~1000 kWh/kWp w Polsce
            coverage = pv_annual_est / total_home_kwh * 100
            st.caption(
                f"PV {pv_kwp} kWp → ~{pv_annual_est:,.0f} kWh/rok → "
                f"pokrycie: **{coverage:.0f}%** zapotrzebowania domu."
            )

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
            "Pstryk + G14dynamic: taryfa dynamiczna RDN + opłata dystrybucyjna "
            "wg pory dnia (dark green 0.01, light green 0.05, yellow 0.35, red 2.35 zł/kWh)."
        ),
    )
    has_dynamic_tariff = "Pstryk" in tariff_option
    has_old_pv = "Stare zasady" in tariff_option
with col6:
    suc_distance = st.number_input(
        "Odległość do Superchargera (km)", min_value=0, max_value=500, value=30, step=5
    )

# Ładowanie trasowe – widoczne gdy dużo trasy
highway_pct = pct_rural_n + pct_highway_n
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
                "Tesla Supercharger (0.70–1.90 zł/kWh, dynamiczne)",
                "GreenWay (2.10–3.15 zł/kWh, zależy od abo)",
                "Orlen Charge (2.02–2.39 zł/kWh)",
                "Ionity (2.05–3.50 zł/kWh, zależy od abo)",
                "Powerdot (2.48–2.68 zł/kWh)",
                "Shell Recharge (2.99–3.59 zł/kWh)",
                "Elocity (2.00–2.30 zł/kWh)",
                "Inne / średnia rynkowa (2.30 zł/kWh)",
            ],
            index=0,
            help=(
                "Ceny 2025/2026 — zakresy uwzględniają abonamenty i moc ładowarki. "
                "Tesla SC: ceny dynamiczne wg lokalizacji/pory. "
                "GreenWay: Standard 3.15, Plus (29.99 zł/m) 2.40, Max (79.99 zł/m) 2.10. "
                "Ionity: Direct 3.50, Motion (28.50 zł/m) 2.50, Power (51.50 zł/m) 2.05. "
                "Orlen Charge: zależy od mocy — ≤50 kW: 2.02, 50–125 kW: 2.17, >125 kW: 2.39."
            ),
        )
    with col_ch2:
        dc_price_map = {
            "Tesla": 1.20, "GreenWay": 2.40, "Orlen": 2.17,
            "Ionity": 2.50, "Powerdot": 2.58, "Shell": 3.19,
            "Elocity": 2.15, "Inne": 2.30,
        }
        dc_key = [k for k in dc_price_map if k in dc_charger_type][0]
        dc_price_default = dc_price_map[dc_key]
        dc_price_custom = st.number_input(
            "Cena ładowania DC (zł/kWh)",
            min_value=0.50, max_value=5.00, value=dc_price_default, step=0.05,
            help="Możesz wpisać własną cenę. Wartość domyślna to typowa cena wybranej sieci (z uwzgl. abonamentu).",
        )
        ac_pub_price = st.number_input(
            "Cena ładowania publiczne AC (zł/kWh)",
            min_value=0.50, max_value=5.00, value=1.95, step=0.05,
            help="Publiczne ładowarki AC w miastach (7-22 kW).",
        )
else:
    dc_price_custom = 2.30
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
            "BEV mnożnik": f"×{(pct_city_n * bev_mc + (pct_rural_n + pct_highway_n) * bev_mh):.2f}",
            "ICE mnożnik": f"×{(pct_city_n * ice_mc + (pct_rural_n + pct_highway_n) * ice_mh):.2f}",
        })
    st.dataframe(pd.DataFrame(temp_rows), use_container_width=True, hide_index=True)
    st.caption(
        "BEV: nominalne przy 15°C. Zimą pompa ciepła i ogrzewanie baterii zwiększają zużycie. "
        "ICE: nominalne przy 10°C. Zimny rozruch i paliwo zimowe zwiększają spalanie."
    )

# ===========================================================================
# OBLICZENIA TCO
# ===========================================================================

if st.button("Oblicz koszty", type="primary", use_container_width=True):
    st.session_state["tco_calculated"] = True

if st.session_state.get("tco_calculated", False):
    total_mileage = annual_mileage * period_years
    monthly_km = np.array([annual_mileage * d / 365 for d in DAYS_IN_MONTH])

    # --- ICE ---
    ice_liters_annual, fuel_cost_annual, ice_monthly_liters = calc_annual_fuel_ice(
        ice_city_l, ice_highway_l, road_split, monthly_km, fuel_price,
    )
    fuel_cost_total = fuel_cost_annual * period_years

    _pc, _pr, _ph = road_split
    nominal_ice_l = _pc * ice_city_l + _pr * ice_highway_l + _ph * ice_highway_l * HIGHWAY_SPEED_MULTIPLIER_ICE
    nominal_ice_liters = annual_mileage / 100 * nominal_ice_l
    ice_temp_penalty_pct = (ice_liters_annual / nominal_ice_liters - 1) * 100 if nominal_ice_liters > 0 else 0

    maint_ice_data = calculate_maintenance_cost(segment_idx_ice, total_mileage, "ICE", is_new_ice)
    maint_ice = maint_ice_data["total"]
    depreciation_ice = calculate_depreciation(vehicle_price_ice, segment_idx_ice, period_years, "ICE", is_new_ice)
    insurance_ice = estimate_insurance(vehicle_price_ice, "ICE") * period_years

    tax_shield_ice = 0.0
    tax_data_ice = None
    if use_tax_shield:
        tax_data_ice = calculate_tax_shield(
            vehicle_price_ice, "ICE", fuel_cost_annual,
            estimate_insurance(vehicle_price_ice, "ICE"), period_years, tax_rate,
            usage_type=usage_type, leasing=leasing_ice,
        )
        tax_shield_ice = tax_data_ice["total"]

    tco_ice = total_acquisition_ice + fuel_cost_total + maint_ice + insurance_ice - tax_shield_ice
    rv_ice = vehicle_value_ice - depreciation_ice  # wartość rezydualna (wg wartości auta)
    buyout_tax_ice = 0.0
    if leasing_ice and usage_type == "prywatne":
        buyout_tax_ice = calculate_buyout_tax(
            leasing_ice["buyout_brutto"], rv_ice, period_years, tax_rate)
    tco_net_ice = tco_ice - rv_ice + buyout_tax_ice
    cost_per_km_ice = tco_net_ice / total_mileage if total_mileage > 0 else 0

    # --- BEV ---
    annual_energy_demand, bev_monthly_kwh = calc_annual_consumption_bev(
        bev_city_kwh, bev_highway_kwh, road_split, monthly_km,
    )

    nominal_bev_kwh_100 = _pc * bev_city_kwh + _pr * bev_highway_kwh + _ph * bev_highway_kwh * HIGHWAY_SPEED_MULTIPLIER_BEV
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

    maint_bev_data = calculate_maintenance_cost(segment_idx_bev, total_mileage, "BEV", is_new_bev, brand=bev_model)
    maint_bev = maint_bev_data["total"]
    depreciation_bev = calculate_depreciation(vehicle_price_bev, segment_idx_bev, period_years, "BEV", is_new_bev)
    insurance_bev = estimate_insurance(vehicle_price_bev, "BEV") * period_years

    tax_shield_bev = 0.0
    tax_data_bev = None
    if use_tax_shield:
        tax_data_bev = calculate_tax_shield(
            vehicle_price_bev, "BEV", energy_cost_annual,
            estimate_insurance(vehicle_price_bev, "BEV"), period_years, tax_rate,
            usage_type=usage_type, leasing=leasing_bev,
        )
        tax_shield_bev = tax_data_bev["total"]

    tco_bev = total_acquisition_bev + energy_cost_total + maint_bev + insurance_bev - tax_shield_bev
    rv_bev = vehicle_value_bev - depreciation_bev  # wartość rezydualna (wg wartości auta)
    buyout_tax_bev = 0.0
    if leasing_bev and usage_type == "prywatne":
        buyout_tax_bev = calculate_buyout_tax(
            leasing_bev["buyout_brutto"], rv_bev, period_years, tax_rate)
    tco_net_bev = tco_bev - rv_bev + buyout_tax_bev
    cost_per_km_bev = tco_net_bev / total_mileage if total_mileage > 0 else 0

    # --- HYBRYDA ---
    segment_idx_hyb = price_to_segment(vehicle_price_hyb)
    hyb_engine_type = hyb_type  # "HEV" or "PHEV"

    if hyb_type == "PHEV" and hyb_elec_pct > 0:
        # PHEV: split mileage into fuel + electric portions
        fuel_monthly_km = monthly_km * (1 - hyb_elec_pct)
        elec_monthly_km = monthly_km * hyb_elec_pct

        # Fuel portion
        hyb_liters_annual, hyb_fuel_cost_annual, hyb_monthly_liters = calc_annual_fuel_ice(
            hyb_city_l, hyb_highway_l, road_split, fuel_monthly_km, fuel_price,
        )
        # Electric portion
        hyb_elec_demand, hyb_monthly_kwh = calc_annual_consumption_bev(
            hyb_city_kwh, hyb_highway_kwh, road_split, elec_monthly_km,
        )
        hyb_charging_result = optimize_charging(
            annual_demand_kwh=hyb_elec_demand,
            battery_cap_kwh=hyb_bat_cap,
            pv_kwp=pv_kwp,
            bess_kwh=bess_kwh,
            has_home_charger=has_home_charger,
            has_dynamic_tariff=has_dynamic_tariff,
            has_old_pv=has_old_pv,
            suc_distance_km=suc_distance,
            annual_mileage_km=annual_mileage * hyb_elec_pct,
            dc_price=dc_price_custom,
            ac_pub_price=ac_pub_price,
        )
        hyb_energy_cost_annual = hyb_fuel_cost_annual + hyb_charging_result["total_cost"]
    else:
        # HEV: only fuel, no electricity
        hyb_liters_annual, hyb_fuel_cost_annual, hyb_monthly_liters = calc_annual_fuel_ice(
            hyb_city_l, hyb_highway_l, road_split, monthly_km, fuel_price,
        )
        hyb_energy_cost_annual = hyb_fuel_cost_annual
        hyb_elec_demand = 0.0
        hyb_monthly_kwh = None
        hyb_charging_result = None

    hyb_energy_cost_total = hyb_energy_cost_annual * period_years

    # Hybrid nominal consumption & temperature penalty
    if hyb_type == "PHEV" and hyb_elec_pct > 0:
        _nominal_hyb_l = _pc * hyb_city_l + _pr * hyb_highway_l + _ph * hyb_highway_l * HIGHWAY_SPEED_MULTIPLIER_ICE
        nominal_hyb_liters = (annual_mileage * (1 - hyb_elec_pct)) / 100 * _nominal_hyb_l
        hyb_temp_penalty_pct = (hyb_liters_annual / nominal_hyb_liters - 1) * 100 if nominal_hyb_liters > 0 else 0
    else:
        _nominal_hyb_l = _pc * hyb_city_l + _pr * hyb_highway_l + _ph * hyb_highway_l * HIGHWAY_SPEED_MULTIPLIER_ICE
        nominal_hyb_liters = annual_mileage / 100 * _nominal_hyb_l
        hyb_temp_penalty_pct = (hyb_liters_annual / nominal_hyb_liters - 1) * 100 if nominal_hyb_liters > 0 else 0

    maint_hyb_data = calculate_maintenance_cost(segment_idx_hyb, total_mileage, hyb_engine_type, is_new_hyb)
    maint_hyb = maint_hyb_data["total"]
    depreciation_hyb = calculate_depreciation(vehicle_price_hyb, segment_idx_hyb, period_years, hyb_engine_type, is_new_hyb)
    insurance_hyb = estimate_insurance(vehicle_price_hyb, hyb_engine_type) * period_years

    tax_shield_hyb = 0.0
    tax_data_hyb = None
    if use_tax_shield:
        tax_data_hyb = calculate_tax_shield(
            vehicle_price_hyb, hyb_engine_type, hyb_energy_cost_annual,
            estimate_insurance(vehicle_price_hyb, hyb_engine_type), period_years, tax_rate,
            usage_type=usage_type, leasing=leasing_hyb,
        )
        tax_shield_hyb = tax_data_hyb["total"]

    tco_hyb = total_acquisition_hyb + hyb_energy_cost_total + maint_hyb + insurance_hyb - tax_shield_hyb
    rv_hyb = vehicle_value_hyb - depreciation_hyb
    buyout_tax_hyb = 0.0
    if leasing_hyb and usage_type == "prywatne":
        buyout_tax_hyb = calculate_buyout_tax(
            leasing_hyb["buyout_brutto"], rv_hyb, period_years, tax_rate)
    tco_net_hyb = tco_hyb - rv_hyb + buyout_tax_hyb
    cost_per_km_hyb = tco_net_hyb / total_mileage if total_mileage > 0 else 0

    # ===================================================================
    # WYNIKI
    # ===================================================================
    st.divider()
    st.header("Wyniki analizy kosztów")
    st.caption(
        f"**{ice_model}** vs **{hyb_model}** vs **{bev_model}** | {total_mileage:,} km w {period_years} lata | "
        "Wszystkie kwoty **brutto** (cashflow z VAT). Tarcza podatkowa odliczona osobno."
    )

    # SMART ALERT
    is_cheap_ice = vehicle_price_ice <= 35_000 and not is_new_ice
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

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Podsumowanie", "Wpływ temperatury", "Struktura ładowania BEV",
        "Szczegółowe zestawienie", "ML Insights",
    ])

    with tab1:
        # RV i TCO netto
        col_rv1, col_rv2, col_rv3 = st.columns(3)
        with col_rv1:
            st.markdown(f"**🔴 {ice_model}**")
            c1, c2, c3 = st.columns(3)
            c1.metric("RV", f"{rv_ice:,.0f} zł",
                       delta=f"-{depreciation_ice:,.0f}", delta_color="inverse")
            c2.metric("Tarcza", f"-{tax_shield_ice:,.0f}")
            c3.metric("TCO netto", f"{tco_net_ice:,.0f} zł")
        with col_rv2:
            st.markdown(f"**🟠 {hyb_model}**")
            c1, c2, c3 = st.columns(3)
            c1.metric("RV", f"{rv_hyb:,.0f} zł",
                       delta=f"-{depreciation_hyb:,.0f}", delta_color="inverse")
            c2.metric("Tarcza", f"-{tax_shield_hyb:,.0f}")
            c3.metric("TCO netto", f"{tco_net_hyb:,.0f} zł")
        with col_rv3:
            st.markdown(f"**🟢 {bev_model}**")
            c1, c2, c3 = st.columns(3)
            c1.metric("RV", f"{rv_bev:,.0f} zł",
                       delta=f"-{depreciation_bev:,.0f}", delta_color="inverse")
            c2.metric("Tarcza", f"-{tax_shield_bev:,.0f}")
            c3.metric("TCO netto", f"{tco_net_bev:,.0f} zł")

        if period_years >= 8 and (not is_new_bev or not is_new_ice):
            pass  # używane — próg baterii może nie mieć zastosowania
        elif period_years >= 8:
            st.info(
                "Po 8. roku eksploatacji gwarancja baterii HV wygasa — "
                "uwzględniono przyspieszoną utratę wartości BEV w krzywej deprecjacji."
            )

        # --- Rozbicie tarczy podatkowej ---
        if use_tax_shield and tax_data_ice and tax_data_bev and usage_type != "prywatne":
            with st.expander("Rozbicie tarczy podatkowej – ICE vs HYB vs BEV"):
                tc1, tc2, tc3 = st.columns(3)
                for _tc, _name, _td, _ts in [
                    (tc1, ice_model, tax_data_ice, tax_shield_ice),
                    (tc2, hyb_model, tax_data_hyb, tax_shield_hyb),
                    (tc3, bev_model, tax_data_bev, tax_shield_bev),
                ]:
                    with _tc:
                        if _td:
                            st.markdown(f"**{_name}** (limit: **{_td['limit']:,.0f} zł**)")
                            for label, val in _td["breakdown"].items():
                                if val > 0:
                                    st.markdown(f"- {label}: **{val:,.0f} zł**")
                            st.markdown(f"- **SUMA: {_ts:,.0f} zł** / {period_years} lata")
                best_tax = max(tax_shield_ice, tax_shield_hyb, tax_shield_bev)
                if best_tax > min(tax_shield_ice, tax_shield_hyb, tax_shield_bev):
                    winner = "BEV" if best_tax == tax_shield_bev else ("HYB" if best_tax == tax_shield_hyb else "ICE")
                    st.success(f"{winner} ma największą tarczę podatkową: **{best_tax:,.0f} zł**")

        st.markdown("---")
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            st.metric(f"Koszt / km – {ice_model.split()[0]}", f"{cost_per_km_ice:.2f} zł",
                       help="TCO netto / km (po odliczeniu RV i tarczy)")
        with col_b:
            st.metric(f"Koszt / km – {hyb_model.split()[0]}", f"{cost_per_km_hyb:.2f} zł",
                       help="TCO netto / km (po odliczeniu RV i tarczy)")
        with col_c:
            st.metric(f"Koszt / km – {bev_model.split()[0]}", f"{cost_per_km_bev:.2f} zł",
                       help="TCO netto / km (po odliczeniu RV i tarczy)")
        with col_d:
            best_tco = min(tco_net_ice, tco_net_hyb, tco_net_bev)
            best_name = "ICE" if best_tco == tco_net_ice else ("HYB" if best_tco == tco_net_hyb else "BEV")
            worst_tco = max(tco_net_ice, tco_net_hyb, tco_net_bev)
            savings = worst_tco - best_tco
            st.metric(
                f"Najtańszy: {best_name}", f"{savings:,.0f} zł",
                delta=f"oszczędność vs najdroższy",
                delta_color="normal",
            )

        categories = ["Finansowanie", "Paliwo / Prąd", "Serwis", "Ubezpieczenie",
                       "Tarcza podatkowa", "Wart. rezydualna (RV)", "TCO brutto", "TCO NETTO"]
        ice_vals = [total_acquisition_ice, fuel_cost_total, maint_ice, insurance_ice,
                    -tax_shield_ice, -rv_ice, tco_ice, tco_net_ice]
        hyb_vals = [total_acquisition_hyb, hyb_energy_cost_total, maint_hyb, insurance_hyb,
                    -tax_shield_hyb, -rv_hyb, tco_hyb, tco_net_hyb]
        bev_vals = [total_acquisition_bev, energy_cost_total, maint_bev, insurance_bev,
                    -tax_shield_bev, -rv_bev, tco_bev, tco_net_bev]

        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            name=f"ICE – {ice_model}", x=categories, y=ice_vals, marker_color="#ef4444",
        ))
        fig_bar.add_trace(go.Bar(
            name=f"HYB – {hyb_model}", x=categories, y=hyb_vals, marker_color="#f59e0b",
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
        ice_cum, hyb_cum, bev_cum = [], [], []
        for mo in months_range:
            frac = mo / (period_years * 12)
            ice_cum.append(total_acquisition_ice + (fuel_cost_total + maint_ice + insurance_ice) * frac - tax_shield_ice * frac)
            hyb_cum.append(total_acquisition_hyb + (hyb_energy_cost_total + maint_hyb + insurance_hyb) * frac - tax_shield_hyb * frac)
            bev_cum.append(total_acquisition_bev + (energy_cost_total + maint_bev + insurance_bev) * frac - tax_shield_bev * frac)

        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(
            x=months_range, y=ice_cum, name=f"ICE – {ice_model} (brutto)",
            line=dict(color="#ef4444", width=3),
        ))
        fig_line.add_trace(go.Scatter(
            x=months_range, y=hyb_cum, name=f"HYB – {hyb_model} (brutto)",
            line=dict(color="#f59e0b", width=3),
        ))
        fig_line.add_trace(go.Scatter(
            x=months_range, y=bev_cum, name=f"BEV – {bev_model} (brutto)",
            line=dict(color="#22c55e", width=3),
        ))
        # RV markers at end – show netto after resale
        last_mo = months_range[-1]
        fig_line.add_trace(go.Scatter(
            x=[last_mo, last_mo, last_mo],
            y=[tco_net_ice, tco_net_hyb, tco_net_bev],
            mode="markers+text", name="TCO netto (po sprzedaży)",
            marker=dict(size=14, symbol="star",
                        color=["#ef4444", "#f59e0b", "#22c55e"],
                        line=dict(width=2, color="black")),
            text=[f"netto: {tco_net_ice:,.0f}", f"netto: {tco_net_hyb:,.0f}",
                  f"netto: {tco_net_bev:,.0f}"],
            textposition=["top right", "middle right", "bottom right"],
        ))

        # Breakeven detection – punkt przecięcia dla każdej pary
        def _find_breakeven(cum_a, cum_b, months):
            """Find first crossover between two cumulative cost arrays."""
            for i in range(1, len(months)):
                if (cum_a[i - 1] - cum_b[i - 1]) * (cum_a[i] - cum_b[i]) < 0:
                    d0 = cum_a[i - 1] - cum_b[i - 1]
                    d1 = cum_a[i] - cum_b[i]
                    frac_be = d0 / (d0 - d1)
                    be_month = months[i - 1] + frac_be
                    be_cost = cum_a[i - 1] + frac_be * (cum_a[i] - cum_a[i - 1])
                    return be_month, be_cost
            return None, None

        breakeven_pairs = [
            ("ICE↔BEV", ice_cum, bev_cum, "#7c3aed", -40),
            ("ICE↔HYB", ice_cum, hyb_cum, "#dc2626", -70),
            ("HYB↔BEV", hyb_cum, bev_cum, "#059669", -100),
        ]
        breakeven_messages = []
        for pair_name, cum_a, cum_b, color, ay_offset in breakeven_pairs:
            be_month, be_cost = _find_breakeven(cum_a, cum_b, months_range)
            if be_month is not None:
                cheaper = pair_name.split("↔")[1] if cum_b[-1] < cum_a[-1] else pair_name.split("↔")[0]
                fig_line.add_annotation(
                    x=be_month, y=be_cost,
                    text=f"{pair_name}: {be_month:.0f}. mies.",
                    showarrow=True, arrowhead=2, ax=50, ay=ay_offset,
                    font=dict(size=11, color=color, weight="bold"),
                    bgcolor="white", bordercolor=color, borderwidth=2, borderpad=3,
                )
                fig_line.add_trace(go.Scatter(
                    x=[be_month], y=[be_cost],
                    mode="markers", name=f"BE {pair_name}",
                    marker=dict(size=10, color=color, symbol="diamond",
                                line=dict(width=2, color="black")),
                    showlegend=False,
                ))
                breakeven_messages.append(
                    f"**{pair_name}**: breakeven w **{be_month:.0f}. miesiącu** → {cheaper} tańszy"
                )

        fig_line.update_layout(
            title="Koszt narastający w czasie (gwiazdki = TCO netto po sprzedaży auta)",
            xaxis_title="Miesiąc", yaxis_title="Koszt skumulowany (PLN)", height=500,
        )
        st.plotly_chart(fig_line, use_container_width=True)

        # Breakeven info messages
        if breakeven_messages:
            st.info("📊 **Punkty breakeven:**\n\n" + "\n\n".join(breakeven_messages))
        else:
            ordered = sorted(
                [("ICE", ice_cum[-1]), ("HYB", hyb_cum[-1]), ("BEV", bev_cum[-1])],
                key=lambda x: x[1],
            )
            st.info(
                f"📊 **Brak punktów breakeven** — kolejność od najtańszego przez cały okres: "
                f"{ordered[0][0]} → {ordered[1][0]} → {ordered[2][0]}"
            )

    with tab2:
        st.subheader("Wpływ temperatury na roczne zużycie")

        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1:
            st.markdown("**🟢 BEV**")
            st.metric(
                "Narzut temperaturowy",
                f"+{bev_temp_penalty_pct:.1f}%",
                delta=f"+{annual_energy_demand - nominal_bev_annual:.0f} kWh / rok",
                delta_color="inverse",
            )
            st.metric("Nominalne (15°C)", f"{nominal_bev_annual:.0f} kWh/rok")
            st.metric("Rzeczywiste (z temp.)", f"{annual_energy_demand:.0f} kWh/rok")
        with col_t2:
            st.markdown("**🟠 Hybryda (paliwo)**")
            st.metric(
                "Narzut temperaturowy",
                f"+{hyb_temp_penalty_pct:.1f}%",
                delta=f"+{hyb_liters_annual - nominal_hyb_liters:.0f} l / rok",
                delta_color="inverse",
            )
            st.metric("Nominalne", f"{nominal_hyb_liters:.0f} l/rok")
            st.metric("Rzeczywiste (z temp.)", f"{hyb_liters_annual:.0f} l/rok")
            if hyb_type == "PHEV" and hyb_elec_demand > 0:
                st.caption(f"PHEV: {hyb_elec_pct*100:.0f}% jazdy na prądzie → {hyb_elec_demand:.0f} kWh/rok")
        with col_t3:
            st.markdown("**🔴 ICE**")
            st.metric(
                "Narzut temperaturowy",
                f"+{ice_temp_penalty_pct:.1f}%",
                delta=f"+{ice_liters_annual - nominal_ice_liters:.0f} l / rok",
                delta_color="inverse",
            )
            st.metric("Nominalne", f"{nominal_ice_liters:.0f} l/rok")
            st.metric("Rzeczywiste (z temp.)", f"{ice_liters_annual:.0f} l/rok")

        fig_temp = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            subplot_titles=("BEV: zużycie miesięczne (kWh)", "ICE / HYB: spalanie miesięczne (litry)"),
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
        # Hybrid fuel monthly line
        fig_temp.add_trace(go.Scatter(
            x=MONTH_NAMES_PL, y=hyb_monthly_liters, name="HYB z temp.",
            line=dict(color="#f59e0b", width=2, dash="dash"),
            mode="lines+markers",
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

        col_e1, col_e2, col_e3, col_e4 = st.columns(4)
        with col_e1:
            st.metric("Roczny koszt energii BEV", f"{energy_cost_annual:,.0f} zł")
        with col_e2:
            st.metric("Roczny koszt energii HYB", f"{hyb_energy_cost_annual:,.0f} zł",
                       help="PHEV: paliwo + prąd; HEV: tylko paliwo")
        with col_e3:
            st.metric("Roczny koszt paliwa ICE", f"{fuel_cost_annual:,.0f} zł")
        with col_e4:
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

        # GreenWay subscription optimizer
        dc_kwh_annual = annual_energy_demand * charging_result["pct_suc"] / 100
        if dc_kwh_annual > 0:
            gw = greenway_optimal_plan(dc_kwh_annual)
            with st.expander("GreenWay 2026 – optymalny plan abonamentowy"):
                gw_rows = []
                for name, data in gw["plans"].items():
                    marker = " **najlepszy**" if name == gw["best"] else ""
                    gw_rows.append({
                        "Plan": f"{name}{marker}",
                        "Abonament": f"{data['subscription']:.2f} zł/mies.",
                        "Stawka DC": f"{data['rate']:.2f} zł/kWh",
                        "Koszt roczny": f"{data['annual_cost']:,.0f} zł",
                        "Efektywna cena": f"{data['effective_per_kwh']:.2f} zł/kWh",
                    })
                st.dataframe(pd.DataFrame(gw_rows), hide_index=True, use_container_width=True)
                st.caption(
                    f"Przy {dc_kwh_annual:,.0f} kWh DC/rok optymalny plan to "
                    f"**GreenWay {gw['best']}** "
                    f"({gw['best_data']['effective_per_kwh']:.2f} zł/kWh efektywnie)."
                )

            # Ionity subscription optimizer
            ion = ionity_optimal_plan(dc_kwh_annual)
            with st.expander("Ionity 2026 – optymalny plan abonamentowy"):
                ion_rows = []
                for name, data in ion["plans"].items():
                    marker = " **najlepszy**" if name == ion["best"] else ""
                    ion_rows.append({
                        "Plan": f"{name}{marker}",
                        "Abonament": f"{data['subscription']:.2f} zł/mies.",
                        "Stawka DC": f"{data['rate']:.2f} zł/kWh",
                        "Koszt roczny": f"{data['annual_cost']:,.0f} zł",
                        "Efektywna cena": f"{data['effective_per_kwh']:.2f} zł/kWh",
                    })
                st.dataframe(pd.DataFrame(ion_rows), hide_index=True, use_container_width=True)
                st.caption(
                    f"Przy {dc_kwh_annual:,.0f} kWh DC/rok optymalny plan to "
                    f"**Ionity {ion['best']}** "
                    f"({ion['best_data']['effective_per_kwh']:.2f} zł/kWh efektywnie)."
                )

        # G14dynamic distribution tariff info
        if has_dynamic_tariff:
            with st.expander("G14dynamic – opłata dystrybucyjna wg pory dnia"):
                st.markdown(
                    "| Strefa | Godziny | Opłata dystr. (zł/kWh) | Kolor |\n"
                    "| --- | --- | ---: | --- |\n"
                    "| Noc | 00:00–06:00 | 0.0118 | dark green |\n"
                    "| Poranek | 06:00–10:00 | 0.0470 | light green |\n"
                    "| Dzień | 10:00–14:00 | 0.3528 | yellow |\n"
                    "| Popołudnie | 14:00–17:00 | 0.0470 | light green |\n"
                    "| Szczyt | 17:00–21:00 | 2.3521 | red |\n"
                    "| Wieczór | 21:00–24:00 | 0.0470 | light green |"
                )
                st.caption(
                    "G14dynamic: opłata dystrybucyjna zmienia się wg pory dnia. "
                    "HiGHS automatycznie ładuje auto w najtańszych godzinach (noc/poranek)."
                )

    with tab4:
        st.subheader("Szczegółowe zestawienie kosztów (brutto / cashflow)")

        avg_bev_real = annual_energy_demand / annual_mileage * 100 if annual_mileage > 0 else 0
        avg_ice_real = ice_liters_annual / annual_mileage * 100 if annual_mileage > 0 else 0
        avg_hyb_fuel_real = hyb_liters_annual / (annual_mileage * (1 - hyb_elec_pct if hyb_type == "PHEV" else 0) or annual_mileage) * 100 if annual_mileage > 0 else 0

        # Build detail rows
        detail_cats = [
            "Pojazd",
            "Typ napędu",
            "Stan",
            "Forma finansowania",
            "Wartość auta (brutto)",
            "Finansowanie – suma wpłat (brutto)",
        ]
        ice_detail = [
            ice_model,
            "ICE (spalinowy)",
            "Nowy" if is_new_ice else "Używany",
            financing_mode_ice,
            f"{vehicle_value_ice:,.0f} zł",
            f"{total_acquisition_ice:,.0f} zł",
        ]
        hyb_detail = [
            hyb_model,
            f"{hyb_type} ({'pełna hybryda' if hyb_type == 'HEV' else 'plug-in'})",
            "Nowy" if is_new_hyb else "Używany",
            financing_mode_hyb,
            f"{vehicle_value_hyb:,.0f} zł",
            f"{total_acquisition_hyb:,.0f} zł",
        ]
        bev_detail = [
            bev_model,
            "BEV (elektryczny)",
            "Nowy" if is_new_bev else "Używany",
            financing_mode_bev,
            f"{vehicle_value_bev:,.0f} zł",
            f"{total_acquisition_bev:,.0f} zł",
        ]

        # Leasing breakdown rows
        if leasing_ice or leasing_hyb or leasing_bev:
            detail_cats += [
                "  Wpłata własna (brutto)",
                "  Raty łącznie (brutto)",
                "  w tym kapitał (netto)",
                "  w tym odsetki (netto)",
                "  Wykup (brutto)",
                "  Rata miesięczna (netto)",
            ]
            for ldata, vals in [(leasing_ice, ice_detail), (leasing_hyb, hyb_detail), (leasing_bev, bev_detail)]:
                if ldata:
                    vals += [
                        f"{ldata['down_brutto']:,.0f} zł",
                        f"{ldata['total_rates_brutto']:,.0f} zł",
                        f"{ldata['total_capital_netto']:,.0f} zł",
                        f"{ldata['total_interest_netto']:,.0f} zł",
                        f"{ldata['buyout_brutto']:,.0f} zł",
                        f"{ldata['monthly_rate_netto']:,.0f} zł",
                    ]
                else:
                    vals += ["—"] * 6

        detail_cats += [
            f"Paliwo / Prąd ({period_years} lata)",
            f"Serwis i naprawy ({period_years} lata)",
            f"Ubezpieczenie OC+AC ({period_years} lata)",
            "Utrata wartości (deprecjacja)",
            "Tarcza podatkowa 2026 (oszczędność)",
            "TCO brutto (suma wydatków)",
            "",
            "Wartość rezydualna (RV) po sprzedaży",
        ]
        ice_detail += [
            f"{fuel_cost_total:,.0f} zł",
            f"{maint_ice:,.0f} zł",
            f"{insurance_ice:,.0f} zł",
            f"{depreciation_ice:,.0f} zł",
            f"-{tax_shield_ice:,.0f} zł",
            f"{tco_ice:,.0f} zł",
            "",
            f"{rv_ice:,.0f} zł",
        ]
        hyb_detail += [
            f"{hyb_energy_cost_total:,.0f} zł",
            f"{maint_hyb:,.0f} zł",
            f"{insurance_hyb:,.0f} zł",
            f"{depreciation_hyb:,.0f} zł",
            f"-{tax_shield_hyb:,.0f} zł",
            f"{tco_hyb:,.0f} zł",
            "",
            f"{rv_hyb:,.0f} zł",
        ]
        bev_detail += [
            f"{energy_cost_total:,.0f} zł",
            f"{maint_bev:,.0f} zł",
            f"{insurance_bev:,.0f} zł",
            f"{depreciation_bev:,.0f} zł",
            f"-{tax_shield_bev:,.0f} zł",
            f"{tco_bev:,.0f} zł",
            "",
            f"{rv_bev:,.0f} zł",
        ]

        # Buyout tax row if applicable
        if buyout_tax_ice > 0 or buyout_tax_hyb > 0 or buyout_tax_bev > 0:
            detail_cats.append("Podatek od sprzedaży (wykup prywatny)")
            ice_detail.append(f"{buyout_tax_ice:,.0f} zł" if buyout_tax_ice > 0 else "—")
            hyb_detail.append(f"{buyout_tax_hyb:,.0f} zł" if buyout_tax_hyb > 0 else "—")
            bev_detail.append(f"{buyout_tax_bev:,.0f} zł" if buyout_tax_bev > 0 else "—")

        hyb_consumption_str = f"{avg_hyb_fuel_real:.1f} l/100km"
        if hyb_type == "PHEV" and hyb_elec_pct > 0:
            hyb_consumption_str += f" + {hyb_elec_pct*100:.0f}% prąd"

        detail_cats += [
            "TCO NETTO (realny koszt posiadania)",
            "Koszt / km (netto)",
            "",
            "Śr. zużycie (z temp.)",
            "Narzut temperaturowy",
        ]
        ice_detail += [
            f"{tco_net_ice:,.0f} zł",
            f"{cost_per_km_ice:.2f} zł",
            "",
            f"{avg_ice_real:.1f} l/100km",
            f"+{ice_temp_penalty_pct:.1f}%",
        ]
        hyb_detail += [
            f"{tco_net_hyb:,.0f} zł",
            f"{cost_per_km_hyb:.2f} zł",
            "",
            hyb_consumption_str,
            f"+{hyb_temp_penalty_pct:.1f}%",
        ]
        bev_detail += [
            f"{tco_net_bev:,.0f} zł",
            f"{cost_per_km_bev:.2f} zł",
            "",
            f"{avg_bev_real:.1f} kWh/100km",
            f"+{bev_temp_penalty_pct:.1f}%",
        ]

        df_detail = pd.DataFrame({
            "Kategoria": detail_cats,
            "🔴 ICE": ice_detail,
            "🟠 HYB": hyb_detail,
            "🟢 BEV": bev_detail,
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
                "🔴 ICE": [
                    "",
                    f"{tax_data_ice['limit']:,.0f} zł",
                    f"{tax_data_ice['vat_fuel_pct']:.0%}",
                    f"{tax_data_ice['kup_pct']:.0%}",
                    usage_type,
                ],
                "🟠 HYB": [
                    "",
                    f"{tax_data_hyb['limit']:,.0f} zł" if tax_data_hyb else "—",
                    f"{tax_data_hyb['vat_fuel_pct']:.0%}" if tax_data_hyb else "—",
                    f"{tax_data_hyb['kup_pct']:.0%}" if tax_data_hyb else "—",
                    usage_type,
                ],
                "🟢 BEV": [
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

        col_m1, col_m2, col_m3 = st.columns(3)
        for _col, _name, _data, _total in [
            (col_m1, ice_model, maint_ice_data, maint_ice),
            (col_m2, hyb_model, maint_hyb_data, maint_hyb),
            (col_m3, bev_model, maint_bev_data, maint_bev),
        ]:
            with _col:
                st.markdown(f"**{_name} – serwis**")
                if _data["breakdown"]:
                    breakdown_rows = [
                        {"Kategoria": k, "Koszt (zł)": f"{v:,.0f}"}
                        for k, v in _data["breakdown"].items()
                        if v > 0
                    ]
                    breakdown_rows.append({
                        "Kategoria": "RAZEM",
                        "Koszt (zł)": f"{_total:,.0f}",
                    })
                    st.dataframe(
                        pd.DataFrame(breakdown_rows),
                        hide_index=True, use_container_width=True,
                    )
                    st.caption(f"Koszt serwisowy: {_data['per_km']:.2f} zł/km")
                    if _data.get("tesla_warranty"):
                        st.info(f"Tesla: gwarancja do {TESLA_WARRANTY_KM:,} km")

        # Pie chart serwisowy
        fig_maint = make_subplots(
            rows=1, cols=3,
            subplot_titles=(f"ICE: {ice_model}", f"HYB: {hyb_model}", f"BEV: {bev_model}"),
            specs=[[{"type": "pie"}, {"type": "pie"}, {"type": "pie"}]],
        )
        ice_bd = {k: v for k, v in maint_ice_data["breakdown"].items() if v > 0}
        hyb_bd = {k: v for k, v in maint_hyb_data["breakdown"].items() if v > 0}
        bev_bd = {k: v for k, v in maint_bev_data["breakdown"].items() if v > 0}

        if ice_bd:
            fig_maint.add_trace(go.Pie(
                labels=list(ice_bd.keys()), values=list(ice_bd.values()),
                hole=0.3, textinfo="label+percent",
            ), row=1, col=1)
        if hyb_bd:
            fig_maint.add_trace(go.Pie(
                labels=list(hyb_bd.keys()), values=list(hyb_bd.values()),
                hole=0.3, textinfo="label+percent",
            ), row=1, col=2)
        if bev_bd:
            fig_maint.add_trace(go.Pie(
                labels=list(bev_bd.keys()), values=list(bev_bd.values()),
                hole=0.3, textinfo="label+percent",
            ), row=1, col=3)
        fig_maint.update_layout(
            title="Struktura kosztów serwisowych",
            height=400, showlegend=False,
        )
        st.plotly_chart(fig_maint, use_container_width=True)

        st.caption(
            "Obliczenia uwzględniają: limity podatkowe 2026 (ICE/HEV: 100k zł, PHEV/BEV: 225k zł), "
            "optymalizację ładowania HiGHS z taryfą dynamiczną RDN, wpływ temperatury "
            "na zużycie wszystkich napędów, oraz rozbicie kosztów serwisowych. "
            "Ceny paliw aktualizowane z e-petrol.pl."
        )

    # ===================================================================
    # TAB 5 – ML INSIGHTS
    # ===================================================================
    with tab5:
        ml = get_ml_models()

        # --- Klasteryzacja profilu ---
        st.subheader("Twój profil kierowcy")
        user_features = {
            "annual_mileage": annual_mileage,
            "city_pct": city_pct,
            "has_home_charger": int(has_home_charger),
            "pv_kwp": pv_kwp,
            "has_heat_pump": int(has_heat_pump),
            "usage_type": {"firmowe": 0, "mieszane": 1, "prywatne": 2}.get(usage_type, 2),
        }
        cl_auto = predict_cluster(ml, user_features)

        # Selectbox do zmiany klastra
        cluster_options = [f"Auto: {cl_auto['name']} ({cl_auto['similarity']:.0f}%)"]
        cluster_options += [f"{CLUSTER_NAMES[i][0]}" for i in range(6)]
        selected_cluster = st.selectbox(
            "Klaster kierowcy",
            cluster_options,
            index=0,
            help="Model ML automatycznie przypisał Ci klaster na podstawie parametrów. "
                 "Możesz wybrać inny klaster, żeby zobaczyć jak zmienią się wyniki.",
        )
        if selected_cluster.startswith("Auto:"):
            cl = cl_auto
        else:
            # Ręcznie wybrany klaster — pobierz centroid
            override_id = next(i for i in range(6) if CLUSTER_NAMES[i][0] == selected_cluster)
            # Znajdź surowy label odpowiadający temu cluster_id
            inv_map = {v: k for k, v in ml["label_map"].items()}
            raw_label = inv_map[override_id]
            centroid_scaled = ml["km"].cluster_centers_[raw_label]
            centroid_orig = ml["scaler"].inverse_transform(centroid_scaled.reshape(1, -1))[0]
            X = np.array([[user_features[f] for f in ml["cl_features"]]])
            X_scaled = ml["scaler"].transform(X)
            dist = np.linalg.norm(X_scaled[0] - centroid_scaled)
            similarity = max(0, 100 - dist * 15)
            name, desc = CLUSTER_NAMES[override_id]
            cl = {
                "cluster_id": override_id, "name": name, "desc": desc,
                "similarity": similarity,
                "centroid": dict(zip(ml["cl_features"], centroid_orig)),
                "user": user_features,
            }

        st.info(f"**Klaster: {cl['name']}**\n\n{cl['desc']}")

        col_cl1, col_cl2 = st.columns(2)
        with col_cl1:
            st.metric("Podobieństwo do klastra", f"{cl['similarity']:.0f}%")
        with col_cl2:
            st.metric("Klaster nr", f"{cl['cluster_id'] + 1} / 6")

        # Radar chart: user vs centroid
        radar_labels = ["Przebieg (tys. km)", "Miasto (%)", "Ładow. domowa",
                        "PV (kWp)", "Pompa ciepła", "Użytkowanie"]
        user_vals_norm = [
            annual_mileage / 80000,
            city_pct,
            int(has_home_charger),
            pv_kwp / 20,
            int(has_heat_pump),
            user_features["usage_type"] / 2,
        ]
        centroid_norm = [
            cl["centroid"]["annual_mileage"] / 80000,
            cl["centroid"]["city_pct"],
            cl["centroid"]["has_home_charger"],
            cl["centroid"]["pv_kwp"] / 20,
            cl["centroid"]["has_heat_pump"],
            cl["centroid"]["usage_type"] / 2,
        ]
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=user_vals_norm + [user_vals_norm[0]],
            theta=radar_labels + [radar_labels[0]],
            fill="toself", name="Twój profil",
            fillcolor="rgba(59, 130, 246, 0.2)", line_color="#3b82f6",
        ))
        fig_radar.add_trace(go.Scatterpolar(
            r=centroid_norm + [centroid_norm[0]],
            theta=radar_labels + [radar_labels[0]],
            fill="toself", name=f"Centroid: {cl['name']}",
            fillcolor="rgba(239, 68, 68, 0.15)", line_color="#ef4444",
        ))
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
            title="Profil vs centroid klastra",
            height=420, showlegend=True,
        )
        st.plotly_chart(fig_radar, use_container_width=True)

        # --- Korekta real-world ---
        st.subheader("Korekta real-world (ML)")
        rw_bev, rw_ice = predict_realworld(ml, city_pct, annual_mileage, has_home_charger, pv_kwp)
        col_rw1, col_rw2, col_rw3 = st.columns(3)
        with col_rw1:
            nominal_bev = pct_city_n * bev_city_kwh + pct_rural_n * bev_highway_kwh + pct_highway_n * bev_highway_kwh * HIGHWAY_SPEED_MULTIPLIER_BEV
            corrected_bev = nominal_bev * rw_bev
            st.metric(
                f"BEV: mnożnik ×{rw_bev:.2f}",
                f"{corrected_bev:.1f} kWh/100km",
                delta=f"+{(rw_bev - 1) * 100:.0f}% vs katalog ({nominal_bev:.1f})",
                delta_color="inverse",
            )
        with col_rw2:
            # Hybrid uses ICE-like correction with slightly lower factor (better efficiency)
            rw_hyb = 1 + (rw_ice - 1) * 0.8  # HYB runs more efficiently due to recuperation
            nominal_hyb = pct_city_n * hyb_city_l + pct_rural_n * hyb_highway_l + pct_highway_n * hyb_highway_l * HIGHWAY_SPEED_MULTIPLIER_ICE
            corrected_hyb = nominal_hyb * rw_hyb
            st.metric(
                f"HYB: mnożnik ×{rw_hyb:.2f}",
                f"{corrected_hyb:.1f} L/100km",
                delta=f"+{(rw_hyb - 1) * 100:.0f}% vs katalog ({nominal_hyb:.1f})",
                delta_color="inverse",
            )
        with col_rw3:
            nominal_ice = pct_city_n * ice_city_l + pct_rural_n * ice_highway_l + pct_highway_n * ice_highway_l * HIGHWAY_SPEED_MULTIPLIER_ICE
            corrected_ice = nominal_ice * rw_ice
            st.metric(
                f"ICE: mnożnik ×{rw_ice:.2f}",
                f"{corrected_ice:.1f} L/100km",
                delta=f"+{(rw_ice - 1) * 100:.0f}% vs katalog ({nominal_ice:.1f})",
                delta_color="inverse",
            )
        st.caption(
            f"Model: RandomForest (n=1000 syntetycznych profili, "
            f"R² BEV={ml['r2_bev']:.3f}, R² ICE={ml['r2_ice']:.3f})"
        )

        # --- Prognoza 12-miesięczna ---
        st.subheader("Prognoza kosztów energii – 12 miesięcy")
        df_forecast = forecast_monthly_costs(
            energy_cost_annual, fuel_cost_annual,
            bev_city_kwh, bev_highway_kwh, road_split,
            ice_city_l, ice_highway_l, fuel_price,
            annual_mileage,
        )
        # Approximate hybrid monthly costs using seasonal pattern from ICE/BEV
        hyb_monthly_fc = []
        for i, row in df_forecast.iterrows():
            if hyb_type == "PHEV" and hyb_elec_pct > 0:
                # PHEV: weighted mix of BEV and ICE seasonal patterns
                ice_ratio = row["ICE (zł)"] / (total_ice_fc_raw := sum(df_forecast["ICE (zł)"])) if sum(df_forecast["ICE (zł)"]) > 0 else 1/12
                bev_ratio = row["BEV (zł)"] / (total_bev_fc_raw := sum(df_forecast["BEV (zł)"])) if sum(df_forecast["BEV (zł)"]) > 0 else 1/12
                fuel_part = hyb_fuel_cost_annual * ice_ratio
                elec_part = (hyb_energy_cost_annual - hyb_fuel_cost_annual) * bev_ratio
                hyb_monthly_fc.append(round(fuel_part + elec_part, 0))
            else:
                # HEV: same seasonal pattern as ICE
                ice_ratio = row["ICE (zł)"] / sum(df_forecast["ICE (zł)"]) if sum(df_forecast["ICE (zł)"]) > 0 else 1/12
                hyb_monthly_fc.append(round(hyb_energy_cost_annual * ice_ratio, 0))
        df_forecast["HYB (zł)"] = hyb_monthly_fc

        fig_fc = go.Figure()
        fig_fc.add_trace(go.Bar(
            x=df_forecast["Miesiąc"], y=df_forecast["ICE (zł)"],
            name="ICE", marker_color="#ef4444",
        ))
        fig_fc.add_trace(go.Bar(
            x=df_forecast["Miesiąc"], y=df_forecast["HYB (zł)"],
            name="HYB", marker_color="#f59e0b",
        ))
        fig_fc.add_trace(go.Bar(
            x=df_forecast["Miesiąc"], y=df_forecast["BEV (zł)"],
            name="BEV", marker_color="#22c55e",
        ))
        fig_fc.update_layout(
            title="Miesięczne koszty energii/paliwa (z sezonowością)",
            yaxis_title="Koszt (zł)", barmode="group", height=400,
        )
        st.plotly_chart(fig_fc, use_container_width=True)

        total_bev_fc = sum(df_forecast["BEV (zł)"])
        total_hyb_fc = sum(df_forecast["HYB (zł)"])
        total_ice_fc = sum(df_forecast["ICE (zł)"])
        col_fc1, col_fc2, col_fc3, col_fc4 = st.columns(4)
        with col_fc1:
            st.metric("ICE roczny", f"{total_ice_fc:,.0f} zł")
        with col_fc2:
            st.metric("HYB roczny", f"{total_hyb_fc:,.0f} zł")
        with col_fc3:
            st.metric("BEV roczny", f"{total_bev_fc:,.0f} zł")
        with col_fc4:
            best_fc = min(total_ice_fc, total_hyb_fc, total_bev_fc)
            worst_fc = max(total_ice_fc, total_hyb_fc, total_bev_fc)
            st.metric("Max oszczędność", f"{worst_fc - best_fc:,.0f} zł/rok")

        st.dataframe(df_forecast, use_container_width=True, hide_index=True)

        # --- Metodologia ---
        with st.expander("Metodologia ML"):
            st.markdown(
                "**Dane treningowe:** 1000 syntetycznych profili kierowców (rozkłady "
                "zbliżone do polskiego rynku: przebieg log-normalny, mediana ~15 tys. km/rok, "
                "30% z PV, 15% z pompą ciepła).\n\n"
                "**Klasteryzacja:** KMeans (k=6) na 6 cechach po standaryzacji (StandardScaler). "
                "Klastry nazwane post-hoc wg centroidów.\n\n"
                "**Korekta real-world:** RandomForest (50 drzew, max_depth=6) przewiduje "
                "mnożnik korekcyjny zużycia vs dane katalogowe. Wyższy city% i niski przebieg "
                "= wyższy mnożnik (częstsze rozgrzewanie, korki).\n\n"
                "**Prognoza 12-mies.:** rozkład kosztów z uwzględnieniem sezonowości temperaturowej "
                "(średnie miesięczne temperatury w Polsce) i mnożników zużycia BEV/ICE.\n\n"
                "**Disclaimer:** Dane syntetyczne – wyniki mają charakter orientacyjny i edukacyjny."
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
        has_roof = st.checkbox("Mogę zamontować panele fotowoltaiczne", True, key="adv_roof")
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
            vehicle_price_ice, "ICE", is_new_ice, annual_mileage, period_years, road_split,
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
                        vehicle_price_bev, "BEV", is_new_bev, annual_mileage,
                        period_years, road_split,
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
                segment_idx_ice, 100_000, "ICE", is_new_ice)["per_km"]
            maint_bev_rate = calculate_maintenance_cost(
                segment_idx_bev, 100_000, "BEV", is_new_bev, brand=bev_model)["per_km"]

            dem_ref, _ = calc_annual_consumption_bev(
                bev_city_kwh, bev_highway_kwh, road_split, mkm_ref)
            ch_ref = optimize_charging(
                dem_ref, battery_capacity, pv_kwp, bess_kwh,
                has_home_charger, has_dynamic_tariff, has_old_pv,
                suc_distance, annual_mileage)
            bev_energy_per_km = ch_ref["total_cost"] / annual_mileage if annual_mileage > 0 else 0.5

            _, ice_fuel_ref, _ = calc_annual_fuel_ice(
                ice_city_l, ice_highway_l, road_split, mkm_ref, 1.0)
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
                    ins_ice_a, period_years, tax_rate)["total"] if use_tax_shield else 0
                tco_i = vehicle_price_ice + f_ice + m_ice + i_ice - tx_ice

                e_bev = bev_energy_per_km * tkm
                m_bev = maint_bev_rate * tkm
                i_bev = ins_bev_a * period_years
                tx_bev = calculate_tax_shield(
                    vehicle_price_bev, "BEV", bev_energy_per_km * mil,
                    ins_bev_a, period_years, tax_rate)["total"] if use_tax_shield else 0
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

    # Konkurenci segmentowi — po 2 auta (ICE + BEV) na segment cenowy
    _FLEET_COMPETITORS = {
        0: [  # do 20k
            {"Model": "Fiat Panda 2015", "Cena (zł)": 18_000, "Napęd": "ICE", "Miasto (/100km)": 7.0, "Trasa (/100km)": 5.5},
            {"Model": "Renault Zoe 2017", "Cena (zł)": 19_000, "Napęd": "BEV", "Miasto (/100km)": 16.0, "Trasa (/100km)": 19.0},
        ],
        1: [  # 20-35k
            {"Model": "Toyota Yaris 2019", "Cena (zł)": 32_000, "Napęd": "ICE", "Miasto (/100km)": 6.5, "Trasa (/100km)": 5.0},
            {"Model": "Nissan Leaf 24kWh 2017", "Cena (zł)": 30_000, "Napęd": "BEV", "Miasto (/100km)": 15.5, "Trasa (/100km)": 18.5},
        ],
        2: [  # 35-50k
            {"Model": "Opel Corsa 2021", "Cena (zł)": 45_000, "Napęd": "ICE", "Miasto (/100km)": 7.0, "Trasa (/100km)": 5.5},
            {"Model": "Renault Zoe R135 2021", "Cena (zł)": 48_000, "Napęd": "BEV", "Miasto (/100km)": 15.0, "Trasa (/100km)": 18.0},
        ],
        3: [  # 50-75k
            {"Model": "VW Golf 1.5 TSI 2022", "Cena (zł)": 68_000, "Napęd": "ICE", "Miasto (/100km)": 7.5, "Trasa (/100km)": 5.5},
            {"Model": "Nissan Leaf 40kWh 2020", "Cena (zł)": 65_000, "Napęd": "BEV", "Miasto (/100km)": 16.0, "Trasa (/100km)": 19.0},
        ],
        4: [  # 75-105k
            {"Model": "Toyota Corolla 1.8 HEV", "Cena (zł)": 98_000, "Napęd": "ICE", "Miasto (/100km)": 5.5, "Trasa (/100km)": 5.0},
            {"Model": "MG4 Electric Standard", "Cena (zł)": 95_000, "Napęd": "BEV", "Miasto (/100km)": 15.5, "Trasa (/100km)": 18.5},
        ],
        5: [  # 105-145k
            {"Model": "VW Golf 2.0 TDI", "Cena (zł)": 135_000, "Napęd": "ICE", "Miasto (/100km)": 6.5, "Trasa (/100km)": 4.8},
            {"Model": "BYD Atto 3", "Cena (zł)": 130_000, "Napęd": "BEV", "Miasto (/100km)": 16.0, "Trasa (/100km)": 19.5},
        ],
        6: [  # 145-185k
            {"Model": "Toyota Camry 2.5 HEV", "Cena (zł)": 165_000, "Napęd": "ICE", "Miasto (/100km)": 6.0, "Trasa (/100km)": 5.5},
            {"Model": "Tesla Model 3 RWD", "Cena (zł)": 175_000, "Napęd": "BEV", "Miasto (/100km)": 13.5, "Trasa (/100km)": 16.0},
        ],
        7: [  # 185-230k
            {"Model": "BMW 320i 2024", "Cena (zł)": 210_000, "Napęd": "ICE", "Miasto (/100km)": 8.0, "Trasa (/100km)": 6.0},
            {"Model": "Tesla Model Y LR AWD", "Cena (zł)": 219_000, "Napęd": "BEV", "Miasto (/100km)": 16.0, "Trasa (/100km)": 19.0},
        ],
        8: [  # 230-300k
            {"Model": "Mercedes C300 AMG", "Cena (zł)": 265_000, "Napęd": "ICE", "Miasto (/100km)": 9.5, "Trasa (/100km)": 7.0},
            {"Model": "BMW i4 eDrive40", "Cena (zł)": 260_000, "Napęd": "BEV", "Miasto (/100km)": 16.5, "Trasa (/100km)": 19.5},
        ],
        9: [  # 300k+
            {"Model": "BMW M340i xDrive", "Cena (zł)": 340_000, "Napęd": "ICE", "Miasto (/100km)": 10.5, "Trasa (/100km)": 7.5},
            {"Model": "Tesla Model S LR", "Cena (zł)": 380_000, "Napęd": "BEV", "Miasto (/100km)": 18.0, "Trasa (/100km)": 21.0},
        ],
    }

    # Dobierz konkurentów z segmentu wybranego auta (wg droższego z pary ICE/BEV)
    _ref_seg = max(segment_idx_ice, segment_idx_bev)
    _competitors = _FLEET_COMPETITORS.get(_ref_seg, _FLEET_COMPETITORS[5])
    # Filtruj: nie dodawaj konkurenta jeśli to ten sam model co wybrany
    _extra = [c for c in _competitors
              if c["Model"] != ice_model and c["Model"] != bev_model]

    default_cars = pd.DataFrame([
        {"Model": ice_model, "Cena (zł)": vehicle_price_ice, "Napęd": "ICE",
         "Miasto (/100km)": ice_city_l, "Trasa (/100km)": ice_highway_l},
        {"Model": bev_model, "Cena (zł)": vehicle_price_bev, "Napęd": "BEV",
         "Miasto (/100km)": bev_city_kwh, "Trasa (/100km)": bev_highway_kwh},
    ] + _extra)

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
                        car["Cena (zł)"], "ICE", is_new_ice, annual_mileage,
                        period_years, road_split,
                        fuel_price=fuel_price,
                        city_l=car["Miasto (/100km)"],
                        highway_l=car["Trasa (/100km)"],
                        use_tax=use_tax_shield, tax_rate=tax_rate)
                else:
                    r = calculate_tco_quick(
                        car["Cena (zł)"], "BEV", is_new_bev, annual_mileage,
                        period_years, road_split,
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
# EKSPORT WYNIKÓW — PDF / CSV / URL
# ---------------------------------------------------------------------------
if st.session_state.get("tco_calculated"):
    st.divider()
    st.subheader("Eksport wyników")
    exp_c1, exp_c2, exp_c3 = st.columns(3)

    with exp_c1:
        # PDF download
        from fpdf import FPDF
        import unicodedata
        def _strip_pl(text: str) -> str:
            """Strip Polish diacritics for PDF (Helvetica has no Unicode)."""
            _map = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
            return text.translate(_map)
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "Czym Pojade 2026 - Raport TCO", ln=True, align="C")
        pdf.ln(4)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, _strip_pl(f"ICE: {ice_model} ({vehicle_value_ice:,.0f} zl)"), ln=True)
        pdf.cell(0, 7, _strip_pl(f"BEV: {bev_model} ({vehicle_value_bev:,.0f} zl)"), ln=True)
        pdf.cell(0, 7, f"Przebieg: {annual_mileage:,} km/rok | Okres: {period_years} lat", ln=True)
        _pc_d, _pr_d, _ph_d = road_split
        pdf.cell(0, 7, f"Profil tras: Miasto {_pc_d:.0%} | Krajowa {_pr_d:.0%} | Autostrada {_ph_d:.0%}", ln=True)
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Wyniki", ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, f"TCO netto ICE: {tco_net_ice:,.0f} zl | BEV: {tco_net_bev:,.0f} zl", ln=True)
        pdf.cell(0, 7, f"Koszt/km ICE: {cost_per_km_ice:.2f} zl | BEV: {cost_per_km_bev:.2f} zl", ln=True)
        pdf.cell(0, 7, _strip_pl(f"Roznica: {abs(tco_net_ice - tco_net_bev):,.0f} zl na korzysc {'BEV' if tco_net_bev < tco_net_ice else 'ICE'}"), ln=True)
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, _strip_pl("Rozbicie kosztow"), ln=True)
        pdf.set_font("Helvetica", "", 9)
        # Table header
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(80, 6, "Kategoria", border=1)
        pdf.cell(50, 6, "ICE", border=1, align="R")
        pdf.cell(50, 6, "BEV", border=1, align="R", ln=True)
        pdf.set_font("Helvetica", "", 9)
        for cat, iv, bv in zip(detail_cats, ice_detail, bev_detail):
            if cat == "":
                continue
            pdf.cell(80, 5, _strip_pl(cat[:40]), border=1)
            pdf.cell(50, 5, _strip_pl(str(iv)[:25]), border=1, align="R")
            pdf.cell(50, 5, _strip_pl(str(bv)[:25]), border=1, align="R", ln=True)
        pdf.ln(6)
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(0, 5, f"Wygenerowano: czympojade.pl v{APP_VERSION}", ln=True)
        pdf_bytes = pdf.output()
        st.download_button(
            "Pobierz raport PDF", pdf_bytes,
            "czympojade_raport.pdf", "application/pdf",
        )

    with exp_c2:
        # CSV download
        import io, csv
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Kategoria", "ICE", "BEV"])
        for cat, iv, bv in zip(detail_cats, ice_detail, bev_detail):
            w.writerow([cat, iv, bv])
        st.download_button(
            "Pobierz CSV", buf.getvalue(),
            "czympojade_raport.csv", "text/csv",
        )

    with exp_c3:
        # URL sharing
        if st.button("Udostepnij link do obliczen"):
            params = {
                "v_ice": int(vehicle_value_ice),
                "v_bev": int(vehicle_value_bev),
                "new_ice": int(is_new_ice),
                "new_bev": int(is_new_bev),
                "km": annual_mileage,
                "yrs": period_years,
                "city": pct_city,
                "rural": pct_rural,
                "hwy": pct_highway,
            }
            st.query_params.update(params)
            st.success("Link zaktualizowany — skopiuj URL z paska przegladarki.")

# ---------------------------------------------------------------------------
# SŁOWNIK SKRÓTÓW
# ---------------------------------------------------------------------------
with st.expander("Słownik skrótów"):
    st.markdown(
        "| Skrót | Pełna nazwa | Opis |\n"
        "| --- | --- | --- |\n"
        "| **TCO** | Total Cost of Ownership | Całkowity koszt posiadania pojazdu |\n"
        "| **BEV** | Battery Electric Vehicle | Samochód w pełni elektryczny |\n"
        "| **ICE** | Internal Combustion Engine | Samochód spalinowy |\n"
        "| **HEV** | Hybrid Electric Vehicle | Samochód hybrydowy |\n"
        "| **PV** | Photovoltaic | Fotowoltaika – panele słoneczne |\n"
        "| **BESS** | Battery Energy Storage System | Magazyn energii domowy |\n"
        "| **PC** | Pompa Ciepła | Heat pump – ogrzewanie/chłodzenie domu |\n"
        "| **RV** | Residual Value | Wartość rezydualna pojazdu po sprzedaży |\n"
        "| **KUP** | Koszty Uzyskania Przychodu | Koszty podatkowe w firmie |\n"
        "| **VAT** | Value Added Tax | Podatek od towarów i usług (23%) |\n"
        "| **RDN** | Rynek Dnia Następnego | Giełda energii – ceny godzinowe |\n"
        "| **G11** | Taryfa G11 | Taryfa jednostrefowa – jedna cena całą dobę |\n"
        "| **G12** | Taryfa G12 | Taryfa dwustrefowa – dzień/noc |\n"
        "| **G12w** | Taryfa G12w | Taryfa weekendowa – tańszy prąd w weekendy |\n"
        "| **G14** | Taryfa G14dynamic | Dynamiczna taryfa dystrybucyjna (4 strefy cenowe) |\n"
        "| **LP/MILP** | (Mixed-Integer) Linear Programming | Programowanie liniowe – metoda optymalizacji |\n"
        "| **HiGHS** | High-performance Solver | Solver optymalizacyjny open-source |\n"
        "| **DC** | Direct Current | Szybkie ładowanie (>50 kW, Supercharger) |\n"
        "| **AC** | Alternating Current | Wolne ładowanie (3–22 kW, wallbox) |\n"
        "| **SUC** | Supercharger | Stacja szybkiego ładowania Tesla |\n"
        "| **COP** | Coefficient of Performance | Współczynnik wydajności pompy ciepła |\n"
        "| **ML** | Machine Learning | Uczenie maszynowe – predykcja i klasteryzacja |\n"
        "| **KMeans** | K-Means Clustering | Algorytm klasteryzacji (podział na grupy) |\n"
        "| **RF** | Random Forest | Las losowy – model predykcyjny (regresja) |"
    )

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
        'Optymalizacja z użyciem <strong><a href="https://highs.dev/" target="_blank">HiGHS</a></strong> (Linear Programming). '
        'Dane rynkowe 2025/2026, bieżące ceny paliw.<br>'
        '<a href="https://www.linkedin.com/in/pawelmamcarz/" target="_blank">LinkedIn</a>'
        ' · <a href="mailto:pawel@mamcarz.com">pawel@mamcarz.com</a>'
        ' · +48 535 535 221'
        '</div>',
        unsafe_allow_html=True,
    )
