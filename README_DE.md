# Womit fahre ich 2026? — Deutsche Version

TCO-Rechner für den deutschen Automobilmarkt.

## Schnellstart

```bash
# Deutsche Version starten
streamlit run app_de.py

# Oder mit explizitem Port (wenn PL-Version auf 8501 läuft)
APP_LANG=de streamlit run app_de.py --server.port 8502
```

## Architektur

```
czympojade/
├── app.py                    # Haupt-App (PL) — Berechnungslogik bleibt sprachunabhängig
├── app_de.py                 # Einstiegspunkt DE — patcht Konstanten, startet app.py
│
├── locale_loader.py          # i18n-Wrapper: cfg(), t(), tlist(), fmt_currency()
├── market_data_de.py         # DE Marktdaten: SMARD-API, ADAC, Kfz-Steuer, Versicherung
├── de_presets.py             # DE Fahrzeugpresets (ICE/BEV/HYB neu+gebraucht)
│
└── locale/
    ├── de/
    │   ├── config.yaml       # Numerische Konfiguration (€, MwSt 19%, SMARD-Preise, ...)
    │   └── strings.yaml      # UI-Strings (Deutsch)
    └── pl/
        ├── config.yaml       # Numerische Konfiguration (zł, MwSt 23%, ...)
        └── strings.yaml      # UI-Strings (Polnisch)
```

## Was wird überschrieben?

`app_de.py` patcht diese Konstanten aus `app.py` auf deutsche Werte:

| Konstante | PL-Wert | DE-Wert |
|-----------|---------|---------|
| `CURRENCY_SYMBOL` | `zł` | `€` |
| `FUEL_GASOLINE_DEFAULT` | `6.10 zł/l` | `1.76 €/l` |
| `FUEL_DIESEL_DEFAULT` | `6.30 zł/l` | `1.65 €/l` |
| `ELEC_G11_DEFAULT` | `0.78 zł/kWh` | `0.32 €/kWh` |
| `VAT_RATE` | `23%` | `19%` |
| `TAX_LIMIT_BEV` | `225 000 zł` | `95 000 €` |
| `SEGMENT_THRESHOLDS` | in PLN | in EUR |
| `ICE_PRESETS_NEW` | PL-Modelle | DE-Modelle |
| `WIZARD_PROFILES` | PL-Profile | DE-Profile |

## Datenquellen

| Quelle | Daten | Update |
|--------|-------|--------|
| **ADAC** | Kraftstoffpreise E5/E10/Diesel/LPG | Wöchentlich |
| **SMARD** (Bundesnetzagentur) | EPEX-Spot-Preis DE-LU | Stündlich |
| **Kfz-Steuer** | CO₂-basierte Formel ab 2021 | Jährlich |
| **EEG 2024** | Einspeisevergütung 8,2 ct/kWh | Jährlich |
| **DAT/Schwacke** | Restwert-Kurven (approximiert) | Laufend |

## Deutsche Besonderheiten vs. PL-Version

- **Kfz-Steuer** statt polnische PCC/Zulassungsgebühren
- **Dienstwagen-Besteuerung** (0,25%-Regelung BEV vs. 1% ICE)
- **EEG Einspeisung** (8,2 ct/kWh) statt PL net-billing
- **BAFA-Subvention**: Eingestellt 2023 (in PL: MP7 bis 16k zł)
- **Deutschlandticket** (49 €/Monat) als ÖPNV-Referenz
- **IONITY/EnBW** als Schnelllade-Referenz (statt PL-Netzwerke)
- **Wallbox-Subvention**: Regional verschieden (KfW 442 für Firmen)

## Deployment (Streamlit Cloud)

Erstelle eine separate Streamlit-App mit:
- **Main file**: `app_de.py`
- **Environment variable**: `APP_LANG=de`

Oder setze in `.streamlit/secrets.toml`:
```toml
APP_LANG = "de"
```
