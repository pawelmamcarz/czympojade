# CzymPojade.pl — Kompletny opis projektu

## Elevator Pitch

**CzymPojade.pl** to niezależny kalkulator TCO (Total Cost of Ownership), który porównuje realne koszty eksploatacji aut elektrycznych, hybrydowych i spalinowych w Polsce. Uwzględnia 150+ czynników kosztowych — od cen paliw na żywo, przez amortyzację skalibrowaną na danych z Otomoto, awaryjność z TÜV Report 2026 (9,5 mln przeglądów w DE), po optymalizację ładowania BEV solverem HiGHS LP.

**Użytkownik w 2 minuty** dostaje spersonalizowaną rekomendację: czy taniej mu jeździć obecnym autem, zmienić na elektryka, hybrydę, czy spalinówkę.

---

## Kluczowe liczby

| Metryka | Wartość |
|---------|---------|
| Modeli aut w bazie | **119** (42 BEV, 62 ICE, 9 HEV, 6 PHEV) |
| Marek | **25+** (Tesla, Toyota, VW, Kia, Hyundai, BMW, Mercedes, Volvo, Skoda, Nissan, BYD, Opel, Renault, Audi, Fiat, Dacia, MG, Cupra, Peugeot, Ford, Mazda, Honda, Jeep, Land Rover) |
| Czynników kosztowych | **150+** |
| Profile użytkowników | **6** (dojeżdżacz, rodzina, firma, prosument PV, trasa, weekend) |
| Język | **PL** (produkcja), **DE** (beta) |
| Czas analizy | **~2 min** (wizard), **~10 min** (zaawansowana) |
| Wersja | Dynamiczna: `YYYY.MM.DD` |

---

## Architektura techniczna

### Stack
- **Frontend:** Streamlit (Python)
- **Solver:** HiGHS LP (optymalizacja ładowania BEV)
- **Baza danych:** Supabase (primary) + SQLite (fallback)
- **Scraping:** e-petrol.pl (paliwa), PSE.pl (ceny prądu RDN), Otomoto (ogłoszenia)
- **Dane solarne:** PVGIS (European Commission)
- **PDF export:** FPDF2
- **Analytics:** streamlit-analytics2 + custom visitor_logs
- **CI/CD:** GitHub → Streamlit Cloud

### Pliki źródłowe

| Plik | Linie | Funkcja |
|------|-------|---------|
| `app.py` | 7 276 | Główna aplikacja — wizard, zaawansowany kalkulator, wykresy, optymalizator |
| `car_database.py` | 215 | Baza 119 modeli aut z parametrami zużycia |
| `market_data.py` | ~400 | Scraping cen paliw, prądu, ogłoszeń Otomoto → Supabase/SQLite |
| `analytics.py` | ~260 | Logowanie wizyt, panel admina |
| `app_de.py` | ~150 | Wersja niemiecka (entry point) |
| `de_presets.py` | ~400 | Presety rynku DE (ADAC, Kfz-Steuer) |
| `market_data_de.py` | ~300 | Dane rynku DE (SMARD, ADAC) |
| `locale_loader.py` | ~150 | System i18n (YAML per język) |
| `scrape_importers.py` | ~400 | Scraper stron importerów (toyota.pl, vw.pl itd.) |
| `test_app.py` | ~200 | 197 unit testów |
| `generate_og_image.py` | ~100 | Generowanie Open Graph image (SEO) |

---

## Jak działa kalkulator

### Wizard (4 kroki)

```
Krok 0: Wybierz profil → 6 kart (dojeżdżacz / rodzina / firma / PV / trasa / weekend)
Krok 1: Twoje auto     → paliwo, segment, wiek, wartość, km/mies., ryzyko awarii
                          LUB budżet + km do pracy (jeśli nie masz auta)
Krok 2: Infrastruktura → garaż, PV, BESS, ładowarka w pracy, SCT, SPP, OC/AC
Krok 3: Rekomendacja   → werdykt + porównanie + most do pełnej analizy
```

### Zaawansowany kalkulator (5 zakładek)

1. **Sankey / rozbicie kosztów** — miesięczne koszty per wariant (paliwo, serwis, ubezpieczenie, amortyzacja, tarcza podatkowa)
2. **Wpływ temperatury** — profil 12-miesięczny, kary za zimno (BEV -10% do -40%)
3. **Amortyzacja i wartość rezydualna** — krzywe deprecjacji rok po roku
4. **Optymalizacja ładowania (HiGHS LP)** — minimalizacja kosztu prądu 8 760 godzin/rok
5. **Porównanie flot** (opcjonalnie) — TCO dla wielu pojazdów

### Optymalizator ładowania BEV

Solver LP (programowanie liniowe) minimalizuje roczny koszt prądu:
- **Zmienne decyzyjne:** `charge_from_grid[h]`, `charge_from_pv[h]`, `discharge_bess[h]`, `soc[h]` × 8 760 godzin
- **Ograniczenia:** pojemność baterii, dzienny popyt energetyczny, produkcja PV (PVGIS), pojemność BESS
- **Wynik:** optymalny harmonogram ładowania, koszt roczny, % wykorzystania PV

---

## Model kosztowy — co uwzględniamy

### Energia / paliwo
| Parametr | Źródło |
|----------|--------|
| Ceny PB95, ON, LPG | e-petrol.pl (dziennie) |
| Ceny prądu (RDN) | PSE.pl (godzinowe) |
| Zużycie miasto/trasa/autostrada | car_database.py per model |
| Temperatura a zużycie BEV | Profil PL: [-2, -1, 3, 8, 14, 17, 19, 18, 14, 9, 4, 0] °C |
| Mnożnik autostrada | BEV: +18%, ICE: +12% |
| AdBlue (diesel 2018+) | 3,50 zł/l, 0,08-0,20 l/100km wg segmentu |

### Serwis i naprawy
| Parametr | Wartość |
|----------|---------|
| Serwis ICE | 1 200 – 5 000 zł wg przebiegu |
| Serwis BEV | 0,05 – 0,08 zł/km |
| Rabat nowe auto | ×0,6 (pierwsze 3 lata) |
| Awaryjność (TÜV 2026) | Rosnąca od roku 5, +10%/rok, ×1,2 powyżej 200k km |
| Baza napraw wg segmentu | 600 zł (małe) → 2 000 zł (wyższy) rocznie |
| Mnożnik Polska/Niemcy | ×0,55 |
| Suwak ryzyka | ×0,3 (optymista) → ×1,8 (pesymista) |

### Amortyzacja
| Krzywa | Rok 0 → Rok 5 → Rok 10 |
|--------|------------------------|
| Nowy ICE | 100% → 35% → 4% |
| Nowy BEV | 100% → 30% → 4% |
| Używany ICE | 60% → 20% → 4% |
| Używany BEV | 55% → 18% → 4% |
| Kalibracja | Otomoto real-world data |

### Ubezpieczenie
| Parametr | Wartość |
|----------|---------|
| OC roczne wg segmentu | 520 zł (mini) → 1 200 zł (wyższy) |
| AC | ~4% wartości auta rocznie |
| AC odpada po | 8 latach (niska wartość → nie opłaca się) |
| BEV OC | Niższe niż ICE (~552 zł śr.) |
| BEV AC | Wyższe (droższa naprawa, bateria) |

### Przegląd techniczny (SKP)
| Parametr | Wartość |
|----------|---------|
| Standard | 99 zł/rok od 4. roku |
| LPG | 162 zł/rok od 4. roku |

### Parkowanie (SPP)
| Miasto | Baza roczna | Z suwakiem 10-50% |
|--------|-------------|-------------------|
| Warszawa | 1 200 – 3 000 zł | 120 – 1 500 zł |
| Kraków | 900 – 5 300 zł | 90 – 2 650 zł |
| Abonament mieszkańca | ×0,05 (~250 zł/rok) | j.w. × suwak |
| BEV | **0 zł** (Ustawa o elektromobilności) | — |

### Strefa Czystego Transportu (SCT)
| Parametr | Wartość |
|----------|---------|
| Miasta | Warszawa, Kraków |
| Benzyna wykluczona | starsze niż 20 lat (pre-Euro 4) |
| Diesel wykluczony | starszy niż 12 lat (pre-Euro 6) |
| Kara | 500 zł/wjazd, 4 darmowe/rok |
| Roczny koszt obejścia | ~3 600 zł |
| BEV/PHEV | **Zawsze za darmo** |

### Tarcza podatkowa (firma)
| Parametr | ICE/HEV | PHEV | BEV |
|----------|---------|------|-----|
| Limit amortyzacji | 150 000 zł | 150 000 zł | **225 000 zł** |
| Odliczenie CIT | 19% | 19% | 19% |
| Efekt 5 lat (225k auto) | 28 500 zł | 28 500 zł | **42 750 zł** |

### LPG — szczegółowy model
| Parametr | Wartość |
|----------|---------|
| Udział benzyny | 10% (rozgrzewka) |
| Zużycie LPG vs benzyna | +15% |
| Instalacja (nowe/używane) | 4 500 / 3 500 zł |
| Serwis LPG roczny | 500 zł |
| Filtr (co 15k km) | 120 zł |
| Świece (co 35k km) | 300 zł |
| Wtryskiwacze (co 70k km) | 700 zł |
| Uszkodzenie zaworów (co 115k km) | 1 500 zł |
| Sterownik (co 70k km) | 1 000 zł |
| Reduktor (co 140k km) | 775 zł |

---

## Baza modeli aut

### BEV (42 modele)
**Nowe (24):** Tesla Model 3/Y (SR+, LR AWD), Hyundai Ioniq 5/6, Kia EV6 (RWD, AWD), VW ID.3/4/7, BMW iX1/iX3, Mercedes EQA/EQB, Volvo EX30/EX40, Nissan Ariya, Skoda Enyaq, Renault Megane E-Tech, MG4, BYD Atto 3/Seal, Fiat 500e, Dacia Spring, Cupra Born, Peugeot e-308, Opel Astra Electric

**Używane (9+):** Tesla Model 3 2021, Hyundai Kona 2021, VW ID.3 2022, Nissan Leaf 2020, Kia EV6 2022, BMW i3 2019 i inne

### ICE (62 modele)
**Nowe (45+):** Od VW up! (62k) po Land Cruiser (380k). Benzyna, diesel, LPG.
**Używane (17):** Popularne modele 2017-2020.

### HEV (9+ modeli)
Toyota Yaris/Corolla/RAV4/Camry Hybrid, Honda Civic e:HEV, Kia Sportage HEV

### PHEV (6+ modeli)
Kia Niro PHEV, BMW 330e, Mercedes C 300e, Volvo XC90, Jeep Grand Cherokee

---

## Integracje zewnętrzne

| Źródło | Dane | Częstotliwość |
|--------|------|---------------|
| **e-petrol.pl** | Ceny PB95, ON, LPG | Codziennie |
| **PSE.pl** | Ceny prądu RDN (godzinowe) | Codziennie |
| **Otomoto.pl** | Ceny ogłoszeń (kalibracja deprecjacji) | Codziennie (5 modeli/sesja) |
| **PVGIS** (EC) | Profil produkcji PV | Na żądanie |
| **TÜV Report 2026** | Statystyki awaryjności | Raz/rok (hardcoded) |
| **Supabase** | Persistent storage | Ciągłe |

---

## Analytics i dane dla partnerów

### Co zbieramy (anonimowo, GDPR-safe)
- Profil użytkownika (1-6)
- Rodzaj paliwa obecnego auta
- Segment auta
- Przebieg miesięczny
- Wiek auta, wartość
- Miasto SCT / SPP
- Garaż, PV, BESS
- Ładowarka w pracy
- Ubezpieczenie OC/AC
- **Werdykt** (zachowaj / zmień na BEV / HEV / ICE)
- **Oszczędność** (zł)
- **Modele porównywane** (BEV, ICE, HYB)

### Panel admina
- Statystyki wizyt (dzienne/tygodniowe)
- Rozkład werdyktów
- Popularność paliw i segmentów
- Średni przebieg użytkowników
- Eksport danych (CSV)

---

## Porównanie marek — dane do pitchów B2B

Profil: **firma CIT 19%, 25 000 km/rok, 5 lat, garaż z ładowarką**

| Marka | BEV | ICE | BEV zł/m | ICE zł/m | Oszczędność BEV (5 lat) |
|-------|-----|-----|----------|----------|------------------------|
| Volvo | EX30 (165k) | S60 B4 (215k) | 1 055 | 2 504 | **86 974 zł** |
| BMW | iX1 eDrive20 (225k) | 320i (220k) | 1 273 | 2 575 | **78 153 zł** |
| Mercedes | EQA 250+ (240k) | C 200 (230k) | 1 438 | 2 728 | **77 398 zł** |
| VW | ID.4 Pro (210k) | Kodiaq TDI (180k) | 1 222 | 2 317 | **65 672 zł** |
| Tesla/Toyota | Model Y SR (189k) | RAV4 Hybrid (185k) | 1 114 | 2 204 | **65 427 zł** |
| Skoda | Enyaq 85 (215k) | Kodiaq TDI (180k) | 1 234 | 2 317 | **64 965 zł** |
| BYD | Seal (185k) | Sportage (150k) | 1 124 | 1 973 | **50 921 zł** |
| VW | ID.3 Pro (165k) | Golf TDI (145k) | 1 055 | 1 813 | **45 506 zł** |
| Kia | EV6 LR RWD (225k) | Sportage T-GDi (150k) | 1 265 | 1 973 | **42 467 zł** |
| Nissan | Ariya 63 kWh (195k) | Qashqai DIG-T (140k) | 1 164 | 1 753 | **35 333 zł** |
| Hyundai | Ioniq 5 AWD (245k) | Tucson T-GDi (155k) | 1 494 | 2 015 | **31 255 zł** |
| Tesla/Toyota | Model 3 SR+ (175k) | Corolla Hybrid (135k) | 1 078 | 1 561 | **28 993 zł** |

**BEV wygrywa w 100% porównań** dla firm — dzięki wyższemu limitowi amortyzacji (225k vs 150k zł) i ~60% niższym kosztom energii.

---

## Wersja niemiecka (beta)

- Entry point: `app_de.py`
- Presety: `de_presets.py` (ceny z Autohaus/ADAC 2025)
- Dane rynkowe: `market_data_de.py` (SMARD — ceny prądu, ADAC — paliwa)
- Podatki: Kfz-Steuer (CO2-based), MwSt 19%
- Ubezpieczenie: ADAC baseline
- Segmenty: A–Mini → E–Oberklasse, Van–Klein, Van–Groß

---

## Deployment

```bash
# Produkcja (Streamlit Cloud)
streamlit run app.py --server.port 8501

# Development
streamlit run app.py --server.runOnSave true

# Wersja DE
APP_LANG=de streamlit run app_de.py --server.port 8502

# Testy
python -m pytest test_app.py -x -q  # 197 testów
```

### Wymagania
```
streamlit>=1.30.0, pandas>=2.0.0, numpy>=1.24.0, plotly>=5.18.0
highspy>=1.7.0, requests>=2.28.0, beautifulsoup4>=4.12.0
scikit-learn>=1.3.0, fpdf2>=2.7.0, supabase>=2.0.0
streamlit-analytics2>=0.10.0, pyyaml>=6.0.0
```

---

## Roadmap i monetyzacja

### Model biznesowy: B2B SaaS + Lead Generation

1. **Integracja danych partnera** — realne ceny (cennik dealera, stawka kWh sieci ładowania, rata leasingu) zamiast szacunkowych
2. **Lead generation** — CTA po wyniku ("Umów jazdę próbną", "Zapytaj o ofertę leasingu") z mierzalną konwersją
3. **Partner Rekomendowany** — logo, wyróżnienie w wynikach, lepsze pozycjonowanie
4. **Raporty rynkowe** — miesięczne dane o trendach: które modele porównywane, jakie werdykty, jakie profile
5. **White-label** — kalkulator z brandingiem partnera na ich stronie

### Kategorie partnerów

| Partner | Wartość dla nich | Przykład |
|---------|-----------------|---------|
| **OEM / Dealer** | Udowadnia, że ich EV jest tańszy w eksploatacji | Kia, Toyota, VW, Hyundai |
| **Sieci ładowania** | Dociera do potencjalnych kierowców EV | GreenWay, Orlen Charge, Shell Recharge |
| **Leasing / Fleet** | Optymalizacja flot, rekomendacje TCO | Arval, LeasePlan, mLeasing |
| **Ubezpieczenia** | Segmentacja klientów, cross-sell OC/AC | PZU, Warta, Ergo Hestia |
| **Energia / PV** | Prosumenci BEV — idealny target | Columbus Energy, SolarEdge |
| **Fintech / banki** | Kredyt na auto — kalkulator jako narzędzie sprzedaży | PKO, Santander |

---

## Kontakt

**Paweł Mamcarz**
- Web: [CzymPojade.pl](https://czympojade.pl)
- Email: pawel@mamcarz.com
- Tel: +48 535 535 221
- LinkedIn: [linkedin.com/in/pawelmamcarz](https://www.linkedin.com/in/pawelmamcarz/)
