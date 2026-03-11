"""
app_de.py — Deutsches Einstiegspunkt für den TCO-Rechner "Womit fahre ich 2026?"

Verwendung:
    streamlit run app_de.py

Oder mit explizitem Port:
    APP_LANG=de streamlit run app_de.py --server.port 8502

Dieses Modul setzt APP_LANG=de, lädt locale_loader, überschreibt
polnische Konstanten mit deutschen Äquivalenten und startet dann app.py.
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# 1. Setze Locale BEVOR andere Module importiert werden
# ---------------------------------------------------------------------------
os.environ["APP_LANG"] = "de"

# ---------------------------------------------------------------------------
# 2. locale_loader importieren (liest locale/de/config.yaml + strings.yaml)
# ---------------------------------------------------------------------------
from locale_loader import cfg, t, tlist, fmt_currency, fmt_km, LANG  # noqa: E402

assert LANG == "de", "locale_loader hat nicht auf 'de' umgeschaltet"

# ---------------------------------------------------------------------------
# 3. market_data_de importieren (SMARD, ADAC, Kfz-Steuer)
# ---------------------------------------------------------------------------
try:
    from market_data_de import (
        scrape_fuel_prices as db_fuel_prices_de,
        scrape_electricity_prices as scrape_electricity_prices_de,
        get_fuel_price_history as get_fuel_price_history_de,
        get_electricity_price_history as get_electricity_price_history_de,
        get_depreciation_curve as market_depreciation_curve_de,
        calculate_kfz_steuer,
        estimate_insurance_de,
        DEPRECIATION_DE,
        INSURANCE_BASELINE,
    )
    HAS_MARKET_DE = True
except ImportError as _e:
    HAS_MARKET_DE = False
    print(f"[app_de] Warnung: market_data_de nicht geladen: {_e}", file=sys.stderr)

# ---------------------------------------------------------------------------
# 4. Deutsche Auto-Presets importieren
# ---------------------------------------------------------------------------
from de_presets import (
    DE_CAR_SEGMENTS,
    DE_SEG_EMOJI,
    WIZARD_SEGMENT_MAP_DE,
    WIZARD_ROAD_SPLITS_DE,
    WIZARD_PROFILES_DE,
    WIZARD_SEGMENT_BASE_PRICE_DE,
    WIZARD_FUEL_MAP_DE,
    SEGMENT_THRESHOLDS_DE,
    SEGMENT_LABELS_DE,
    ICE_PRESETS_NEW_DE,
    ICE_PRESETS_USED_DE,
    BEV_PRESETS_NEW_DE,
    BEV_PRESETS_USED_DE,
    HYB_PRESETS_NEW_DE,
    HYB_PRESETS_USED_DE,
)

# ---------------------------------------------------------------------------
# 5. Streamlit page config (must run before any st.* calls)
# ---------------------------------------------------------------------------
import streamlit as st  # noqa: E402

st.set_page_config(
    page_title=t("app.title"),
    page_icon="⚡",
    layout="wide",
)

# ---------------------------------------------------------------------------
# 6. Monkey-patch: ersetze polnische Konstanten mit deutschen Äquivalenten
#    Dieses Modul wird BEVOR app.py importiert ausgeführt,
#    daher werden die Patches über sys.modules sichtbar gemacht.
# ---------------------------------------------------------------------------

# Wir patchen die globalen Variablen NACH dem Import von app.py
# (app.py darf set_page_config NICHT ein zweites Mal aufrufen)

# Trick: app.py beginnt mit st.set_page_config() — das schlägt fehl,
# wenn es zweimal aufgerufen wird. Wir unterdrücken den zweiten Aufruf,
# indem wir st.set_page_config mit einem No-Op ersetzen.

_original_set_page_config = st.set_page_config

def _noop_set_page_config(*args, **kwargs):
    """No-op: Seitenconfig wurde bereits in app_de.py gesetzt."""
    pass

st.set_page_config = _noop_set_page_config

# ---------------------------------------------------------------------------
# 7. Importiere app.py als Modul (exec in eigenem Namespace)
#    Wir nutzen importlib um app.py zu laden, dann patchen wir seine globals.
# ---------------------------------------------------------------------------
import importlib.util  # noqa: E402
import pathlib         # noqa: E402

_APP_PATH = pathlib.Path(__file__).parent / "app.py"

_spec = importlib.util.spec_from_file_location("_czympojade_app", _APP_PATH)
_app_mod = importlib.util.module_from_spec(_spec)

# ---------------------------------------------------------------------------
# 8. Vor dem Ausführen von app.py: Konstanten in dessen Namespace setzen
#    Wir registrieren das Modul und setzen Variablen vor _spec.loader.exec_module
# ---------------------------------------------------------------------------
sys.modules["_czympojade_app"] = _app_mod

# Deutsche Basiskonstanten in den zukünftigen Namespace injizieren
_app_mod.APP_LANG = "de"
_app_mod.CURRENCY_SYMBOL = cfg("currency_symbol", "€")
_app_mod.CURRENCY_SEP_THOUSANDS = cfg("thousands_sep", ".")
_app_mod.CURRENCY_SEP_DECIMAL = cfg("decimal_sep", ",")

# Kraftstoffpreise (€/l)
_app_mod.FUEL_GASOLINE_DEFAULT = cfg("fuel.gasoline_per_liter", 1.76)
_app_mod.FUEL_DIESEL_DEFAULT   = cfg("fuel.diesel_per_liter",   1.65)
_app_mod.FUEL_LPG_DEFAULT      = cfg("fuel.lpg_per_liter",      0.88)

# Strompreise (€/kWh)
_app_mod.ELEC_G11_DEFAULT      = cfg("fuel.electricity_base",   0.32)
_app_mod.DYNAMIC_PRICE_CAP     = cfg("fuel.electricity_dynamic_cap", 0.35)

# MwSt.
_app_mod.VAT_RATE              = cfg("vat_rate", 0.19)

# Fahrzeug-Segmentgrenzen
_app_mod.SEGMENT_THRESHOLDS    = SEGMENT_THRESHOLDS_DE
_app_mod.SEGMENT_LABELS        = SEGMENT_LABELS_DE

# Fahrzeugsegmente (Strings)
_app_mod.CAR_SEGMENTS          = DE_CAR_SEGMENTS
_app_mod._SEG_EMOJI            = DE_SEG_EMOJI

# Wizard-Daten
_app_mod.WIZARD_PROFILES       = WIZARD_PROFILES_DE
_app_mod.WIZARD_SEGMENT_MAP    = WIZARD_SEGMENT_MAP_DE
_app_mod.WIZARD_ROAD_SPLITS    = WIZARD_ROAD_SPLITS_DE
_app_mod.WIZARD_SEGMENT_BASE_PRICE = WIZARD_SEGMENT_BASE_PRICE_DE
_app_mod.WIZARD_FUEL_MAP       = WIZARD_FUEL_MAP_DE

# Presets
_app_mod.ICE_PRESETS_NEW       = ICE_PRESETS_NEW_DE
_app_mod.ICE_PRESETS_USED      = ICE_PRESETS_USED_DE
_app_mod.BEV_PRESETS_NEW       = BEV_PRESETS_NEW_DE
_app_mod.BEV_PRESETS_USED      = BEV_PRESETS_USED_DE
_app_mod.HYB_PRESETS_NEW       = HYB_PRESETS_NEW_DE
_app_mod.HYB_PRESETS_USED      = HYB_PRESETS_USED_DE

# Steuerliche Limits (Deutschland — Dienstwagen-Besteuerung)
# BEV: 0,25%-Regelung (statt 1%) bis 31.12.2030, max. 95.000 € Listenpreis
_app_mod.TAX_LIMIT_ICE         = cfg("taxes.company_car_tax_limit_ice", 70_000)
_app_mod.TAX_LIMIT_PHEV        = cfg("taxes.company_car_tax_limit_phev", 70_000)
_app_mod.TAX_LIMIT_BEV         = cfg("taxes.company_car_tax_limit_bev", 95_000)

# Zulassungskosten DE (Kfz-Zulassung ~27 €, Kennzeichen ~30 €, gesamt ~57 €)
_app_mod.REGISTRATION_FEE_ICE  = cfg("taxes.registration_fee_fixed", 57)
_app_mod.REGISTRATION_FEE_BEV  = cfg("taxes.registration_fee_fixed", 57)

# PV – Einspeisevergütung DE (EEG 2024)
_app_mod.PV_FEED_IN_RATE       = cfg("pv.feed_in_rate", 0.082)

# Submeter (Wallbox-Unterverteilung)
_app_mod.SUBMETER_COST         = cfg("pv.submeter_cost", 800)

# Marktdaten-Adapter überschreiben (falls market_data_de verfügbar)
if HAS_MARKET_DE:
    _app_mod.HAS_MARKET_DB = True
    _app_mod.db_fuel_prices        = db_fuel_prices_de
    _app_mod.scrape_electricity_prices = scrape_electricity_prices_de
    _app_mod.get_fuel_price_history    = get_fuel_price_history_de
    _app_mod.get_electricity_price_history = get_electricity_price_history_de
    _app_mod.market_depreciation_curve = market_depreciation_curve_de
else:
    _app_mod.HAS_MARKET_DB = False

# Sprachspezifische Strings als Modul-Globals
_app_mod.APP_TITLE             = t("app.title")
_app_mod.APP_SUBTITLE          = t("app.subtitle")
_app_mod.BTN_HOME              = t("app.btn_home")
_app_mod.BTN_NEXT              = t("wizard.btn_next")
_app_mod.BTN_BACK              = t("wizard.btn_back")
_app_mod.BTN_FULL_ANALYSIS     = t("wizard.btn_full_analysis")
_app_mod.BTN_BACK_TO_WIZARD    = t("wizard.btn_back_to_wizard")
_app_mod.FOOTER_DATA_SOURCE    = t("footer.data_source")
_app_mod.FOOTER_DISCLAIMER     = t("footer.disclaimer")

# LPG-Strings auf Deutsch
_app_mod.WIZARD_PARKING_OPTS   = tlist("wizard.parking_opts")

# Alternative Verkehrsmittel (DE-Preise anpassen)
# ÖPNV Monatskarte DE (Deutschlandticket 49 €)
_ALT_TRANSPORT_DE = {
    "🚌 ÖPNV": {
        "monthly_pass": 49,   # Deutschlandticket 2025
        "per_km": 0,
        "fixed_monthly": 49,
        "max_km_month": 1500,
        "emoji": "🚌",
        "desc": "Deutschlandticket (49 €/Monat)",
    },
    "🚗 Uber / FREENOW": {
        "monthly_pass": 0,
        "per_km": 1.80,       # Durchschnitt DE-Großstädte
        "fixed_monthly": 0,
        "min_per_ride": 5,
        "avg_ride_km": 8,
        "emoji": "🚗",
        "desc": "Fahrten auf Abruf (Uber, FREENOW, Bolt)",
    },
    "🚲 Leihfahrrad (TIER/NextBike)": {
        "monthly_pass": 15,
        "per_km": 0.10,
        "fixed_monthly": 15,
        "max_km_month": 200,
        "emoji": "🚲",
        "desc": "E-Bike/Rad-Sharing (TIER, Nextbike, Lime)",
    },
    "🚆 Fernzug (ICE)": {
        "monthly_pass": 0,
        "per_km": 0.22,       # BahnCard 50 Durchschnitt
        "fixed_monthly": 0,
        "avg_ride_km": 300,
        "emoji": "🚆",
        "desc": "Fernverkehr ICE/IC (BahnCard 50)",
    },
}
_app_mod.ALT_TRANSPORT = _ALT_TRANSPORT_DE

# ---------------------------------------------------------------------------
# 9. Führe app.py aus (Streamlit-App startet hier)
# ---------------------------------------------------------------------------
_spec.loader.exec_module(_app_mod)
