"""
de_presets.py — Presety pojazdów dla rynku niemieckiego.

Dane: ceny katalogowe DE (brutto, inkl. MwSt. 19%), zużycie WLTP.
Źródła: Hersteller-Preislisten, ADAC Autokosten 2025, BAFA-Liste.

Struktura zgodna z ICE_PRESETS_NEW / BEV_PRESETS_NEW z app.py PL:
    {segment: {model_name: {price, city_l/city_kwh, hwy_l/hwy_kwh, fuel, bat?, hybrid_type?}}}

Klucze fuel: 0=benzyna/E10, 1=diesel, 2=lpg
"""

# ---------------------------------------------------------------------------
# SEGMENTY DE (odpowiedniki PL segmentów)
# ---------------------------------------------------------------------------
DE_CAR_SEGMENTS = [
    "A – Mini",
    "B – Kompakt",
    "C – Mittel",
    "D – Obere",
    "E – Oberklasse",
    "Van – Klein",
    "Van – Groß",
]

DE_SEG_EMOJI = {
    "Eigene Parameter":  "🛠️ Eigene",
    "A – Mini":          "🛵 Mini",
    "B – Kompakt":       "🚗 Kompakt",
    "C – Mittel":        "🚙 Mittelklasse",
    "D – Obere":         "🚐 Obere Mittel",
    "E – Oberklasse":    "💰 Oberklasse",
    "Van – Klein":       "🚐 Van klein",
    "Van – Groß":        "🚛 Van 3.5t",
    "Fun Car 🏎️":       "🏎️ Fun Car",
    "Pick-up 🤠":        "🤠 Pick-up",
}

# Segment Map: Wizard-Label → interner Schlüssel
WIZARD_SEGMENT_MAP_DE = {
    "Kleinstwagen (Fiat 500, VW Up, Twingo)":          "A – Mini",
    "Kompaktwagen (Golf, Astra, Focus)":                "B – Kompakt",
    "Mittelklasse (Passat, A4, 3er, C-Klasse)":        "C – Mittel",
    "SUV / Familienwagen (Tiguan, Tucson, CX-5)":      "D – Obere",
    "Oberklasse (5er, E-Klasse, A6)":                  "E – Oberklasse",
    "Kleintransporter (Caddy, Berlingo, Rifter)":      "Van – Klein",
    "Transporter bis 3.5t (Crafter, Sprinter, Transit)": "Van – Groß",
    "Pick-up / Geländewagen":                           "Pick-up 🤠",
}

WIZARD_ROAD_SPLITS_DE = {
    "Stadtverkehr":              (0.70, 0.20, 0.10),
    "Gemischt Stadt + Land":     (0.40, 0.35, 0.25),
    "Lange Strecken / Autobahn": (0.20, 0.30, 0.50),
}

WIZARD_PERIOD_YEARS_DE = 5

# ---------------------------------------------------------------------------
# VERBRENNER (ICE) — NEU
# ---------------------------------------------------------------------------
ICE_PRESETS_NEW_DE = {
    "A – Mini": {
        "VW Up! 1.0 MPI 2024":        {"price": 17_995, "city_l": 5.8, "hwy_l": 4.5, "fuel": 0},
        "Fiat 500 1.0 Hybrid 2024":   {"price": 19_490, "city_l": 5.5, "hwy_l": 4.2, "fuel": 0},
        "Renault Twingo SCe 65 2024":  {"price": 16_490, "city_l": 5.6, "hwy_l": 4.4, "fuel": 0},
        "Kia Picanto 1.0 DPI 2024":   {"price": 16_290, "city_l": 5.9, "hwy_l": 4.7, "fuel": 0},
    },
    "B – Kompakt": {
        "VW Golf 1.5 TSI 2024":        {"price": 29_995, "city_l": 6.6, "hwy_l": 5.1, "fuel": 0},
        "VW Golf 2.0 TDI 2024":        {"price": 34_995, "city_l": 5.9, "hwy_l": 4.5, "fuel": 1},
        "Toyota Corolla 1.8 HSD 2024": {"price": 30_990, "city_l": 4.5, "hwy_l": 4.8, "fuel": 0,
                                         "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0.50},
        "Opel Astra 1.2 Turbo 2024":   {"price": 25_990, "city_l": 7.0, "hwy_l": 5.3, "fuel": 0},
        "Ford Focus 1.5 EcoBoost 2024": {"price": 27_990, "city_l": 7.2, "hwy_l": 5.5, "fuel": 0},
        "Skoda Octavia 2.0 TDI 2024":  {"price": 33_490, "city_l": 5.2, "hwy_l": 4.3, "fuel": 1},
    },
    "C – Mittel": {
        "VW Passat 2.0 TDI 2024":         {"price": 42_695, "city_l": 5.8, "hwy_l": 4.8, "fuel": 1},
        "BMW 320d 2024":                   {"price": 49_800, "city_l": 5.5, "hwy_l": 4.5, "fuel": 1},
        "BMW 320i 2024":                   {"price": 46_400, "city_l": 7.0, "hwy_l": 5.5, "fuel": 0},
        "Mercedes C 200 2024":             {"price": 48_207, "city_l": 7.2, "hwy_l": 5.6, "fuel": 0},
        "Mercedes C 220d 2024":            {"price": 50_807, "city_l": 5.4, "hwy_l": 4.4, "fuel": 1},
        "Audi A4 35 TDI 2024":            {"price": 46_700, "city_l": 5.5, "hwy_l": 4.4, "fuel": 1},
        "Audi A4 35 TFSI 2024":           {"price": 43_500, "city_l": 7.3, "hwy_l": 5.8, "fuel": 0},
        "Toyota Camry 2.5 Hybrid 2024":   {"price": 39_990, "city_l": 4.2, "hwy_l": 5.0, "fuel": 0,
                                            "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0.45},
    },
    "D – Obere": {
        "BMW 520d 2024":                   {"price": 62_900, "city_l": 5.3, "hwy_l": 4.5, "fuel": 1},
        "Mercedes E 220d 2024":            {"price": 63_457, "city_l": 5.2, "hwy_l": 4.4, "fuel": 1},
        "Audi A6 40 TDI 2024":            {"price": 58_900, "city_l": 5.6, "hwy_l": 4.6, "fuel": 1},
        "Volvo S90 B4 2024":              {"price": 57_750, "city_l": 6.0, "hwy_l": 5.0, "fuel": 0},
    },
    "E – Oberklasse": {
        "BMW 750e xDrive 2024":            {"price": 133_900, "city_l": 2.1, "hwy_l": 3.5, "fuel": 0,
                                            "hybrid_type": "PHEV", "bat": 18.8, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0.70},
        "Mercedes S 500 2024":             {"price": 120_050, "city_l": 9.8, "hwy_l": 7.5, "fuel": 0},
        "Audi A8 55 TFSI 2024":           {"price": 103_900, "city_l": 10.5, "hwy_l": 8.0, "fuel": 0},
        "Porsche Panamera 2.9T 2024":     {"price": 113_700, "city_l": 9.4, "hwy_l": 7.8, "fuel": 0},
    },
    "Van – Klein": {
        "VW Caddy 2.0 TDI 2024":          {"price": 35_490, "city_l": 6.5, "hwy_l": 5.8, "fuel": 1},
        "Peugeot Rifter 1.5 BlueHDi 2024": {"price": 29_990, "city_l": 6.2, "hwy_l": 5.4, "fuel": 1},
        "Ford Tourneo Connect 2.0 TDCi 2024": {"price": 34_200, "city_l": 7.0, "hwy_l": 6.0, "fuel": 1},
        "Mercedes Citan 111 CDI 2024":    {"price": 34_800, "city_l": 6.8, "hwy_l": 5.9, "fuel": 1},
    },
    "Van – Groß": {
        "VW Crafter 2.0 TDI 2024":        {"price": 49_990, "city_l": 9.0, "hwy_l": 8.0, "fuel": 1},
        "Mercedes Sprinter 314 CDI 2024":  {"price": 52_300, "city_l": 10.0, "hwy_l": 8.5, "fuel": 1},
        "Ford Transit 2.0 EcoBlue 2024":  {"price": 44_990, "city_l": 9.5, "hwy_l": 8.2, "fuel": 1},
        "Iveco Daily 35S16 2024":          {"price": 46_900, "city_l": 9.8, "hwy_l": 8.6, "fuel": 1},
    },
}

# ---------------------------------------------------------------------------
# VERBRENNER (ICE) — GEBRAUCHT (typische Gebraucht-Listenpreise)
# ---------------------------------------------------------------------------
ICE_PRESETS_USED_DE = {
    "A – Mini": {
        "VW Up! 1.0 MPI 2020":            {"price": 9_500, "city_l": 6.2, "hwy_l": 4.8, "fuel": 0},
        "Fiat 500 1.2 8V 2019":           {"price": 8_200, "city_l": 6.0, "hwy_l": 4.5, "fuel": 0},
        "Renault Twingo SCe 70 2021":     {"price": 10_500, "city_l": 5.9, "hwy_l": 4.6, "fuel": 0},
    },
    "B – Kompakt": {
        "VW Golf 1.5 TSI 2021":           {"price": 21_500, "city_l": 7.0, "hwy_l": 5.4, "fuel": 0},
        "VW Golf 2.0 TDI 2020":           {"price": 22_900, "city_l": 6.3, "hwy_l": 4.8, "fuel": 1},
        "Toyota Corolla 1.8 HSD 2021":    {"price": 22_000, "city_l": 4.7, "hwy_l": 5.0, "fuel": 0,
                                            "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0.50},
        "Ford Focus 1.0 EcoBoost 2020":   {"price": 14_900, "city_l": 7.5, "hwy_l": 5.8, "fuel": 0},
        "Opel Astra 1.6 CDTI 2019":       {"price": 11_900, "city_l": 6.0, "hwy_l": 4.7, "fuel": 1},
        "Skoda Octavia 2.0 TDI 2021":     {"price": 24_500, "city_l": 5.5, "hwy_l": 4.5, "fuel": 1},
    },
    "C – Mittel": {
        "VW Passat 2.0 TDI 2021":         {"price": 28_500, "city_l": 6.2, "hwy_l": 5.0, "fuel": 1},
        "BMW 320d 2021":                   {"price": 34_900, "city_l": 5.8, "hwy_l": 4.7, "fuel": 1},
        "BMW 320i 2020":                   {"price": 29_500, "city_l": 7.5, "hwy_l": 5.8, "fuel": 0},
        "Mercedes C 220d 2021":            {"price": 33_900, "city_l": 5.7, "hwy_l": 4.6, "fuel": 1},
        "Audi A4 35 TDI 2020":            {"price": 29_900, "city_l": 5.8, "hwy_l": 4.6, "fuel": 1},
    },
    "D – Obere": {
        "BMW 520d 2021":                   {"price": 44_500, "city_l": 5.6, "hwy_l": 4.7, "fuel": 1},
        "Mercedes E 220d 2020":            {"price": 38_900, "city_l": 5.5, "hwy_l": 4.6, "fuel": 1},
        "Audi A6 40 TDI 2021":            {"price": 40_500, "city_l": 5.9, "hwy_l": 4.8, "fuel": 1},
    },
    "E – Oberklasse": {
        "BMW 750i 2020":                   {"price": 62_000, "city_l": 12.0, "hwy_l": 9.0, "fuel": 0},
        "Mercedes S 400d 2021":            {"price": 75_000, "city_l": 8.5, "hwy_l": 7.0, "fuel": 1},
    },
    "Van – Klein": {
        "VW Caddy 2.0 TDI 2021":          {"price": 24_900, "city_l": 7.0, "hwy_l": 6.2, "fuel": 1},
        "Peugeot Partner 1.5 BlueHDi 2020": {"price": 18_500, "city_l": 6.8, "hwy_l": 5.9, "fuel": 1},
    },
    "Van – Groß": {
        "VW Crafter 2.0 TDI 2021":        {"price": 35_000, "city_l": 9.5, "hwy_l": 8.3, "fuel": 1},
        "Mercedes Sprinter 316 CDI 2020":  {"price": 34_500, "city_l": 10.5, "hwy_l": 9.0, "fuel": 1},
        "Ford Transit 2.0 EcoBlue 2021":  {"price": 29_900, "city_l": 10.0, "hwy_l": 8.5, "fuel": 1},
    },
}

# ---------------------------------------------------------------------------
# ELEKTROAUTOS (BEV) — NEU
# ---------------------------------------------------------------------------
BEV_PRESETS_NEW_DE = {
    "A – Mini": {
        "Fiat 500e Action 2024":           {"price": 23_990, "city_kwh": 14.5, "hwy_kwh": 16.5, "bat": 23.7, "fuel": -1},
        "Citroën ë-C3 2024":              {"price": 23_300, "city_kwh": 15.0, "hwy_kwh": 17.0, "bat": 44.0, "fuel": -1},
        "Dacia Spring Comfort 2024":       {"price": 16_900, "city_kwh": 14.0, "hwy_kwh": 18.0, "bat": 26.8, "fuel": -1},
    },
    "B – Kompakt": {
        "VW ID.3 Pro 2024":                {"price": 39_995, "city_kwh": 14.5, "hwy_kwh": 17.5, "bat": 58.0, "fuel": -1},
        "VW ID.3 Pro S 2024":              {"price": 44_995, "city_kwh": 15.0, "hwy_kwh": 18.0, "bat": 77.0, "fuel": -1},
        "Renault Megane E-Tech 2024":      {"price": 35_500, "city_kwh": 14.5, "hwy_kwh": 17.5, "bat": 60.0, "fuel": -1},
        "BYD Seal U 2024":                 {"price": 39_990, "city_kwh": 15.5, "hwy_kwh": 19.5, "bat": 82.6, "fuel": -1},
        "Cupra Born 77 kWh 2024":          {"price": 44_090, "city_kwh": 14.0, "hwy_kwh": 17.0, "bat": 77.0, "fuel": -1},
        "MG 4 Extended Range 2024":        {"price": 33_990, "city_kwh": 15.0, "hwy_kwh": 18.5, "bat": 77.0, "fuel": -1},
    },
    "C – Mittel": {
        "Tesla Model 3 RWD 2024":          {"price": 42_990, "city_kwh": 13.5, "hwy_kwh": 16.5, "bat": 60.0, "fuel": -1},
        "Tesla Model 3 LR AWD 2024":       {"price": 50_990, "city_kwh": 14.0, "hwy_kwh": 16.5, "bat": 78.0, "fuel": -1},
        "BMW i4 eDrive40 2024":            {"price": 60_300, "city_kwh": 15.0, "hwy_kwh": 18.5, "bat": 83.9, "fuel": -1},
        "Mercedes EQA 250+ 2024":          {"price": 49_607, "city_kwh": 15.5, "hwy_kwh": 19.0, "bat": 70.5, "fuel": -1},
        "Hyundai Ioniq 6 AWD 2024":        {"price": 57_900, "city_kwh": 14.0, "hwy_kwh": 17.0, "bat": 77.4, "fuel": -1},
        "Kia EV6 Standard 2024":           {"price": 44_990, "city_kwh": 14.5, "hwy_kwh": 18.0, "bat": 58.0, "fuel": -1},
        "Polestar 2 Standard 2024":        {"price": 47_900, "city_kwh": 15.0, "hwy_kwh": 18.5, "bat": 69.0, "fuel": -1},
    },
    "D – Obere": {
        "Tesla Model Y RWD 2024":          {"price": 44_990, "city_kwh": 14.5, "hwy_kwh": 17.5, "bat": 60.0, "fuel": -1},
        "Tesla Model Y LR AWD 2024":       {"price": 54_990, "city_kwh": 15.0, "hwy_kwh": 18.5, "bat": 75.0, "fuel": -1},
        "BMW iX1 xDrive30 2024":           {"price": 54_500, "city_kwh": 16.0, "hwy_kwh": 19.5, "bat": 64.7, "fuel": -1},
        "Mercedes EQC 400 2024":           {"price": 63_107, "city_kwh": 20.0, "hwy_kwh": 24.0, "bat": 85.0, "fuel": -1},
        "Volkswagen ID.4 Pro 2024":        {"price": 49_995, "city_kwh": 16.0, "hwy_kwh": 19.5, "bat": 77.0, "fuel": -1},
        "Hyundai Ioniq 5 73 kWh 2024":    {"price": 52_900, "city_kwh": 16.5, "hwy_kwh": 19.5, "bat": 73.0, "fuel": -1},
        "Skoda Enyaq iV 85 2024":         {"price": 48_990, "city_kwh": 16.5, "hwy_kwh": 19.5, "bat": 82.0, "fuel": -1},
    },
    "E – Oberklasse": {
        "Tesla Model S Plaid 2024":        {"price": 124_990, "city_kwh": 18.5, "hwy_kwh": 22.0, "bat": 100.0, "fuel": -1},
        "BMW iX xDrive50 2024":            {"price": 99_400,  "city_kwh": 19.5, "hwy_kwh": 23.5, "bat": 105.2, "fuel": -1},
        "Mercedes EQS 450+ 2024":          {"price": 112_907, "city_kwh": 17.5, "hwy_kwh": 22.5, "bat": 107.8, "fuel": -1},
        "Audi e-tron GT quattro 2024":     {"price": 99_800,  "city_kwh": 19.0, "hwy_kwh": 23.0, "bat": 93.4, "fuel": -1},
        "Porsche Taycan 4S 2024":          {"price": 133_021, "city_kwh": 20.5, "hwy_kwh": 24.5, "bat": 93.4, "fuel": -1},
    },
    "Van – Klein": {
        "VW ID. Buzz 2024 (Basis)":        {"price": 54_995, "city_kwh": 18.5, "hwy_kwh": 22.0, "bat": 79.0, "fuel": -1},
        "Mercedes eVito 2024":             {"price": 55_700, "city_kwh": 26.0, "hwy_kwh": 32.0, "bat": 60.0, "fuel": -1},
        "Stellantis e-Rifter 2024":        {"price": 37_990, "city_kwh": 18.0, "hwy_kwh": 22.5, "bat": 50.0, "fuel": -1},
    },
    "Van – Groß": {
        "Mercedes eSprinter 2024":         {"price": 79_800, "city_kwh": 30.0, "hwy_kwh": 38.0, "bat": 113.0, "fuel": -1},
        "VW e-Crafter 2024":              {"price": 69_990, "city_kwh": 28.0, "hwy_kwh": 35.0, "bat": 82.0, "fuel": -1},
        "Ford E-Transit 2024":            {"price": 62_900, "city_kwh": 29.0, "hwy_kwh": 36.0, "bat": 68.0, "fuel": -1},
    },
}

# ---------------------------------------------------------------------------
# ELEKTROAUTOS (BEV) — GEBRAUCHT
# ---------------------------------------------------------------------------
BEV_PRESETS_USED_DE = {
    "B – Kompakt": {
        "VW ID.3 Pro 2021":                {"price": 22_000, "city_kwh": 15.0, "hwy_kwh": 18.0, "bat": 58.0, "fuel": -1},
        "Renault Zoe R135 2021":           {"price": 13_500, "city_kwh": 15.5, "hwy_kwh": 19.0, "bat": 52.0, "fuel": -1},
        "Nissan Leaf 40 kWh 2020":         {"price": 16_500, "city_kwh": 16.0, "hwy_kwh": 19.5, "bat": 40.0, "fuel": -1},
        "MG ZS EV 2021":                   {"price": 18_900, "city_kwh": 16.5, "hwy_kwh": 20.0, "bat": 44.5, "fuel": -1},
    },
    "C – Mittel": {
        "Tesla Model 3 RWD 2021":          {"price": 28_000, "city_kwh": 14.0, "hwy_kwh": 17.0, "bat": 60.0, "fuel": -1},
        "BMW i4 eDrive40 2022":            {"price": 44_000, "city_kwh": 15.5, "hwy_kwh": 19.0, "bat": 83.9, "fuel": -1},
        "Hyundai Ioniq 6 RWD 2023":        {"price": 38_500, "city_kwh": 14.5, "hwy_kwh": 17.5, "bat": 77.4, "fuel": -1},
        "Kia EV6 RWD 2022":               {"price": 34_900, "city_kwh": 15.0, "hwy_kwh": 18.5, "bat": 77.4, "fuel": -1},
        "Polestar 2 2022":                 {"price": 30_900, "city_kwh": 15.5, "hwy_kwh": 19.0, "bat": 78.0, "fuel": -1},
    },
    "D – Obere": {
        "Tesla Model Y RWD 2022":          {"price": 34_000, "city_kwh": 15.0, "hwy_kwh": 18.0, "bat": 60.0, "fuel": -1},
        "Tesla Model Y LR 2022":           {"price": 39_000, "city_kwh": 15.5, "hwy_kwh": 19.0, "bat": 75.0, "fuel": -1},
        "VW ID.4 Pro 2022":               {"price": 35_000, "city_kwh": 16.5, "hwy_kwh": 20.0, "bat": 77.0, "fuel": -1},
        "Hyundai Ioniq 5 73 kWh 2022":    {"price": 36_500, "city_kwh": 17.0, "hwy_kwh": 20.5, "bat": 73.0, "fuel": -1},
        "Audi Q4 e-tron 40 2022":         {"price": 36_900, "city_kwh": 17.5, "hwy_kwh": 21.0, "bat": 76.6, "fuel": -1},
    },
    "E – Oberklasse": {
        "Tesla Model S LR 2022":           {"price": 75_000, "city_kwh": 19.0, "hwy_kwh": 23.0, "bat": 100.0, "fuel": -1},
        "BMW iX xDrive40 2022":            {"price": 62_000, "city_kwh": 20.0, "hwy_kwh": 24.0, "bat": 71.0, "fuel": -1},
        "Mercedes EQS 450+ 2022":          {"price": 68_000, "city_kwh": 18.0, "hwy_kwh": 23.0, "bat": 107.8, "fuel": -1},
    },
}

# ---------------------------------------------------------------------------
# HYBRYDEN (HEV/PHEV) — NEU
# ---------------------------------------------------------------------------
HYB_PRESETS_NEW_DE = {
    "B – Kompakt": {
        "Toyota Corolla 1.8 HSD 2024":     {"price": 30_990, "city_l": 4.5, "hwy_l": 4.8, "fuel": 0,
                                             "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0.50},
        "Toyota Yaris 1.5 HSD 2024":       {"price": 24_990, "city_l": 3.8, "hwy_l": 4.5, "fuel": 0,
                                             "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0.55},
        "Honda Jazz e:HEV 2024":           {"price": 29_900, "city_l": 4.0, "hwy_l": 4.9, "fuel": 0,
                                             "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0.50},
        "Renault Clio E-Tech 145 2024":    {"price": 23_990, "city_l": 4.5, "hwy_l": 5.2, "fuel": 0,
                                             "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0.45},
        "VW Golf GTE 1.4 eHybrid 2024":   {"price": 42_680, "city_l": 1.5, "hwy_l": 5.8, "fuel": 0,
                                             "hybrid_type": "PHEV", "bat": 13.0, "city_kwh": 11.0, "hwy_kwh": 14.0, "elec_pct": 0.70},
    },
    "C – Mittel": {
        "BMW 330e 2024":                   {"price": 57_900, "city_l": 1.7, "hwy_l": 5.5, "fuel": 0,
                                             "hybrid_type": "PHEV", "bat": 18.7, "city_kwh": 12.0, "hwy_kwh": 15.5, "elec_pct": 0.65},
        "Mercedes C 300e 2024":            {"price": 59_507, "city_l": 1.6, "hwy_l": 5.4, "fuel": 0,
                                             "hybrid_type": "PHEV", "bat": 25.4, "city_kwh": 11.5, "hwy_kwh": 15.0, "elec_pct": 0.70},
        "Toyota Camry 2.5 HSD 2024":      {"price": 39_990, "city_l": 4.2, "hwy_l": 5.0, "fuel": 0,
                                             "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0.45},
        "Volvo S60 T8 Recharge 2024":     {"price": 67_050, "city_l": 1.4, "hwy_l": 5.6, "fuel": 0,
                                             "hybrid_type": "PHEV", "bat": 18.8, "city_kwh": 12.0, "hwy_kwh": 16.0, "elec_pct": 0.65},
    },
    "D – Obere": {
        "BMW 530e 2024":                   {"price": 72_500, "city_l": 1.6, "hwy_l": 5.8, "fuel": 0,
                                             "hybrid_type": "PHEV", "bat": 20.0, "city_kwh": 13.0, "hwy_kwh": 16.0, "elec_pct": 0.65},
        "Mercedes E 300e 2024":            {"price": 74_257, "city_l": 1.5, "hwy_l": 5.6, "fuel": 0,
                                             "hybrid_type": "PHEV", "bat": 25.4, "city_kwh": 12.0, "hwy_kwh": 15.5, "elec_pct": 0.70},
        "Lexus ES 300h 2024":              {"price": 60_900, "city_l": 4.8, "hwy_l": 5.5, "fuel": 0,
                                             "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0.40},
    },
    "Van – Klein": {
        "Toyota ProAce City Verso Hybrid 2024": {"price": 38_990, "city_l": 5.0, "hwy_l": 5.8, "fuel": 0,
                                                  "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0.45},
    },
}

# ---------------------------------------------------------------------------
# HYBRYDEN (HEV/PHEV) — GEBRAUCHT
# ---------------------------------------------------------------------------
HYB_PRESETS_USED_DE = {
    "B – Kompakt": {
        "Toyota Corolla 1.8 HSD 2021":     {"price": 22_000, "city_l": 4.7, "hwy_l": 5.0, "fuel": 0,
                                             "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0.50},
        "Toyota Yaris 1.5 HSD 2020":       {"price": 16_500, "city_l": 4.0, "hwy_l": 4.7, "fuel": 0,
                                             "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0.55},
        "Honda Jazz e:HEV 2022":           {"price": 22_500, "city_l": 4.2, "hwy_l": 5.1, "fuel": 0,
                                             "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0.50},
    },
    "C – Mittel": {
        "BMW 330e 2021":                   {"price": 35_000, "city_l": 2.0, "hwy_l": 5.8, "fuel": 0,
                                             "hybrid_type": "PHEV", "bat": 18.7, "city_kwh": 12.5, "hwy_kwh": 16.0, "elec_pct": 0.65},
        "Toyota Camry 2.5 HSD 2022":      {"price": 32_500, "city_l": 4.4, "hwy_l": 5.2, "fuel": 0,
                                             "hybrid_type": "HEV", "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0.45},
        "Mercedes C 300e 2022":            {"price": 38_900, "city_l": 1.8, "hwy_l": 5.6, "fuel": 0,
                                             "hybrid_type": "PHEV", "bat": 25.4, "city_kwh": 12.0, "hwy_kwh": 15.5, "elec_pct": 0.70},
    },
    "D – Obere": {
        "BMW 530e 2021":                   {"price": 45_000, "city_l": 1.8, "hwy_l": 6.0, "fuel": 0,
                                             "hybrid_type": "PHEV", "bat": 20.0, "city_kwh": 13.5, "hwy_kwh": 16.5, "elec_pct": 0.65},
        "Volvo XC60 T8 2021":             {"price": 46_000, "city_l": 1.9, "hwy_l": 6.2, "fuel": 0,
                                             "hybrid_type": "PHEV", "bat": 18.8, "city_kwh": 13.0, "hwy_kwh": 16.0, "elec_pct": 0.60},
    },
}

# ---------------------------------------------------------------------------
# WIZARD PROFILES DE (odpowiednik WIZARD_PROFILES z app.py)
# ---------------------------------------------------------------------------
WIZARD_PROFILES_DE = {
    0: {"label": "🏙️ Pendler (Stadt)",         "desc": "Täglich zur Arbeit, Kurzstrecke, Stadtverkehr"},
    1: {"label": "👨‍👩‍👧 Familie / Alltag",          "desc": "Schule, Einkauf, Wochenendausflüge"},
    2: {"label": "💼 Geschäftsreisender",        "desc": "Hohe Fahrleistung, Dienstwagen, Firmenwagen"},
    3: {"label": "☀️ PV-Besitzer / Prosument",  "desc": "Eigenheim mit PV, bewusstes Laden"},
    4: {"label": "🛣️ Vielfahrer Langstrecke",    "desc": "Vertreter, Kurier, Außendienst"},
    5: {"label": "🛒 Wenigfahrer",               "desc": "Wenig km, Wochenende, Einkaufen"},
}

# ---------------------------------------------------------------------------
# WIZARD FUEL MAP DE
# ---------------------------------------------------------------------------
WIZARD_FUEL_MAP_DE = {
    "Benzin (E5/E10)":  (0, "ICE"),
    "Diesel":            (1, "ICE"),
    "Autogas (LPG)":    (2, "ICE"),
    "Mild-Hybrid":      (0, "HEV"),
    "Vollhybrid (HEV)": (0, "HEV"),
    "Plug-in Hybrid":   (0, "PHEV"),
    "Elektro (BEV)":    (-1, "BEV"),
}

# ---------------------------------------------------------------------------
# SEGMENT THRESHOLDS DE (Fahrzeugwert-Schwellen in EUR)
# Entspricht SEGMENT_THRESHOLDS / SEGMENT_LABELS aus app.py, aber in EUR
# ---------------------------------------------------------------------------
SEGMENT_THRESHOLDS_DE = [5_000, 12_000, 20_000, 30_000, 45_000, 60_000, 80_000, 100_000, 150_000]
SEGMENT_LABELS_DE = [
    "unter 5.000 € (Altfahrzeug)",
    "5.000–12.000 € (gebraucht günstig)",
    "12.000–20.000 € (gebraucht mittel)",
    "20.000–30.000 € (gebraucht gut / Neuwagen Einstieg)",
    "30.000–45.000 € (Neuwagen Kompakt)",
    "45.000–60.000 € (Neuwagen Mittelklasse)",
    "60.000–80.000 € (Neuwagen Obere Mittelklasse)",
    "80.000–100.000 € (Neuwagen Oberklasse)",
    "100.000–150.000 € (Neuwagen Premium)",
    "über 150.000 € (Luxus)",
]

# ---------------------------------------------------------------------------
# WIZARD SEGMENT BASE PRICE DE (Referenzpreise für Fahrzeugsegmente in EUR)
# ---------------------------------------------------------------------------
WIZARD_SEGMENT_BASE_PRICE_DE = {
    # Schlüssel müssen mit WIZARD_SEGMENT_MAP_DE übereinstimmen
    "Kleinstwagen (Fiat 500, VW Up, Twingo)":              10_000,
    "Kompaktwagen (Golf, Astra, Focus)":                   22_000,
    "Mittelklasse (Passat, A4, 3er, C-Klasse)":           38_000,
    "SUV / Familienwagen (Tiguan, Tucson, CX-5)":         40_000,
    "Oberklasse (5er, E-Klasse, A6)":                     65_000,
    "Kleintransporter (Caddy, Berlingo, Rifter)":          28_000,
    "Transporter bis 3.5t (Crafter, Sprinter, Transit)":  45_000,
    "Pick-up / Geländewagen":                              55_000,
}
