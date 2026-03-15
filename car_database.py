"""Baza popularnych samochodów na polskim rynku z parametrami TCO.

Każdy model ma:
- price: cena brutto (nowe) lub rynkowa (używane)
- type: "ICE" / "BEV" / "HEV" / "PHEV"
- fuel: 0=PB95, 1=Diesel, 2=LPG (tylko ICE/HEV)
- city_l, hwy_l: spalanie l/100km (ICE/HEV/PHEV)
- city_kwh, hwy_kwh: zużycie kWh/100km (BEV/PHEV)
- bat: pojemność baterii kWh (BEV/PHEV)
- elec_pct: % jazdy na prądzie (PHEV)
- segment: klucz segmentu
- new: True = nowe, False = używane
"""

# Struktura: {nazwa_modelu: {parametry}}
# Segment keys: A–Mini, B–Małe, C–Kompakt, D–Średni, E–Wyższy, Van–Mały, Van–Duży

CAR_DB = {
    # ===== ICE — NOWE =====
    # A – Mini
    "Fiat 500 1.0 Hybrid 2025": {"price": 75_000, "type": "ICE", "fuel": 0, "city_l": 5.5, "hwy_l": 4.5, "segment": "A – Mini", "new": True},
    "Toyota Aygo X 1.0 2025": {"price": 72_000, "type": "ICE", "fuel": 0, "city_l": 5.0, "hwy_l": 4.2, "segment": "A – Mini", "new": True},
    "VW up! 1.0 2025": {"price": 62_000, "type": "ICE", "fuel": 0, "city_l": 5.5, "hwy_l": 4.5, "segment": "A – Mini", "new": True},
    # B – Małe
    "Toyota Yaris 1.5 Hybrid 2025": {"price": 95_000, "type": "ICE", "fuel": 0, "city_l": 4.0, "hwy_l": 4.8, "segment": "B – Małe", "new": True},
    "VW Polo 1.0 TSI 2025": {"price": 95_000, "type": "ICE", "fuel": 0, "city_l": 6.5, "hwy_l": 5.0, "segment": "B – Małe", "new": True},
    "Renault Clio 1.0 TCe LPG 2025": {"price": 78_000, "type": "ICE", "fuel": 2, "city_l": 9.0, "hwy_l": 7.5, "segment": "B – Małe", "new": True},
    "Opel Corsa 1.2 Turbo 2025": {"price": 88_000, "type": "ICE", "fuel": 0, "city_l": 6.5, "hwy_l": 5.0, "segment": "B – Małe", "new": True},
    "Hyundai i20 1.2 2025": {"price": 82_000, "type": "ICE", "fuel": 0, "city_l": 6.0, "hwy_l": 4.8, "segment": "B – Małe", "new": True},
    "Mazda 2 1.5 2025": {"price": 85_000, "type": "ICE", "fuel": 0, "city_l": 5.8, "hwy_l": 4.5, "segment": "B – Małe", "new": True},
    # C – Kompakt
    "Toyota Corolla 1.8 Hybrid 2025": {"price": 135_000, "type": "ICE", "fuel": 0, "city_l": 4.5, "hwy_l": 5.5, "segment": "C – Kompakt", "new": True},
    "VW Golf 2.0 TDI 2025": {"price": 145_000, "type": "ICE", "fuel": 1, "city_l": 6.5, "hwy_l": 5.0, "segment": "C – Kompakt", "new": True},
    "Hyundai i30 1.5 T-GDi 2025": {"price": 120_000, "type": "ICE", "fuel": 0, "city_l": 7.0, "hwy_l": 5.5, "segment": "C – Kompakt", "new": True},
    "Skoda Octavia 2.0 TDI 2025": {"price": 140_000, "type": "ICE", "fuel": 1, "city_l": 6.5, "hwy_l": 4.8, "segment": "C – Kompakt", "new": True},
    "Mazda 3 2.0 Hybrid 2025": {"price": 125_000, "type": "ICE", "fuel": 0, "city_l": 5.5, "hwy_l": 5.0, "segment": "C – Kompakt", "new": True},
    "Kia Ceed 1.5 T-GDi 2025": {"price": 115_000, "type": "ICE", "fuel": 0, "city_l": 7.0, "hwy_l": 5.5, "segment": "C – Kompakt", "new": True},
    "Ford Focus 1.0 EcoBoost 2025": {"price": 110_000, "type": "ICE", "fuel": 0, "city_l": 6.5, "hwy_l": 5.0, "segment": "C – Kompakt", "new": True},
    # D – Średni / SUV
    "Toyota Camry 2.5 Hybrid 2025": {"price": 175_000, "type": "ICE", "fuel": 0, "city_l": 5.0, "hwy_l": 5.5, "segment": "D – Średni", "new": True},
    "VW Passat 2.0 TDI 2025": {"price": 185_000, "type": "ICE", "fuel": 1, "city_l": 6.5, "hwy_l": 5.0, "segment": "D – Średni", "new": True},
    "Hyundai Tucson 1.6 T-GDi 2025": {"price": 155_000, "type": "ICE", "fuel": 0, "city_l": 8.5, "hwy_l": 6.8, "segment": "D – Średni", "new": True},
    "Kia Sportage 1.6 T-GDi 2025": {"price": 150_000, "type": "ICE", "fuel": 0, "city_l": 8.5, "hwy_l": 7.0, "segment": "D – Średni", "new": True},
    "Toyota RAV4 2.5 Hybrid 2025": {"price": 185_000, "type": "ICE", "fuel": 0, "city_l": 5.5, "hwy_l": 6.5, "segment": "D – Średni", "new": True},
    "Skoda Kodiaq 2.0 TDI 2025": {"price": 180_000, "type": "ICE", "fuel": 1, "city_l": 7.5, "hwy_l": 6.0, "segment": "D – Średni", "new": True},
    "Nissan Qashqai 1.3 DIG-T 2025": {"price": 140_000, "type": "ICE", "fuel": 0, "city_l": 7.5, "hwy_l": 6.0, "segment": "D – Średni", "new": True},
    # E – Wyższy / Premium
    "BMW 320i 2025": {"price": 220_000, "type": "ICE", "fuel": 0, "city_l": 8.0, "hwy_l": 5.5, "segment": "E – Wyższy", "new": True},
    "Mercedes C 200 2025": {"price": 230_000, "type": "ICE", "fuel": 0, "city_l": 8.5, "hwy_l": 6.0, "segment": "E – Wyższy", "new": True},
    "Audi A4 40 TFSI 2025": {"price": 225_000, "type": "ICE", "fuel": 0, "city_l": 8.0, "hwy_l": 5.5, "segment": "E – Wyższy", "new": True},
    "Volvo S60 B4 2025": {"price": 215_000, "type": "ICE", "fuel": 0, "city_l": 7.5, "hwy_l": 5.5, "segment": "E – Wyższy", "new": True},
    # SUV Premium
    "BMW X3 xDrive20d 2025": {"price": 280_000, "type": "ICE", "fuel": 1, "city_l": 7.5, "hwy_l": 6.0, "segment": "E – Wyższy", "new": True},
    "Mercedes GLC 220d 2025": {"price": 290_000, "type": "ICE", "fuel": 1, "city_l": 7.5, "hwy_l": 6.5, "segment": "E – Wyższy", "new": True},
    "Audi Q5 40 TDI 2025": {"price": 275_000, "type": "ICE", "fuel": 1, "city_l": 7.5, "hwy_l": 6.0, "segment": "E – Wyższy", "new": True},
    "Volvo XC60 B5 AWD 2025": {"price": 260_000, "type": "ICE", "fuel": 0, "city_l": 9.0, "hwy_l": 7.0, "segment": "E – Wyższy", "new": True},
    # Terenowe / Pickup
    "Land Rover Discovery Sport D165 2025": {"price": 250_000, "type": "ICE", "fuel": 1, "city_l": 8.5, "hwy_l": 6.5, "segment": "E – Wyższy", "new": True},
    "Land Rover Defender D250 2025": {"price": 350_000, "type": "ICE", "fuel": 1, "city_l": 10.5, "hwy_l": 8.0, "segment": "E – Wyższy", "new": True},
    "Jeep Wrangler 2.0 T-GDi 2025": {"price": 280_000, "type": "ICE", "fuel": 0, "city_l": 11.0, "hwy_l": 9.0, "segment": "E – Wyższy", "new": True},
    "Toyota Land Cruiser 2.8 D-4D 2025": {"price": 380_000, "type": "ICE", "fuel": 1, "city_l": 9.0, "hwy_l": 7.5, "segment": "E – Wyższy", "new": True},
    # Vany
    "VW Caddy 2.0 TDI 2025": {"price": 140_000, "type": "ICE", "fuel": 1, "city_l": 7.0, "hwy_l": 5.5, "segment": "Van – Mały", "new": True},
    "Renault Kangoo 1.5 dCi 2025": {"price": 120_000, "type": "ICE", "fuel": 1, "city_l": 6.5, "hwy_l": 5.0, "segment": "Van – Mały", "new": True},
    "VW Transporter T7 2.0 TDI 2025": {"price": 220_000, "type": "ICE", "fuel": 1, "city_l": 9.0, "hwy_l": 7.0, "segment": "Van – Duży", "new": True},
    "Ford Transit Custom 2.0 EcoBlue 2025": {"price": 190_000, "type": "ICE", "fuel": 1, "city_l": 8.5, "hwy_l": 6.5, "segment": "Van – Duży", "new": True},

    # ===== ICE — UŻYWANE (popularne na rynku wtórnym) =====
    "Toyota Corolla 1.6 2018": {"price": 55_000, "type": "ICE", "fuel": 0, "city_l": 8.0, "hwy_l": 5.5, "segment": "C – Kompakt", "new": False},
    "VW Golf VII 1.4 TSI 2017": {"price": 50_000, "type": "ICE", "fuel": 0, "city_l": 7.5, "hwy_l": 5.5, "segment": "C – Kompakt", "new": False},
    "Skoda Octavia III 1.6 TDI 2018": {"price": 48_000, "type": "ICE", "fuel": 1, "city_l": 6.5, "hwy_l": 4.5, "segment": "C – Kompakt", "new": False},
    "Opel Astra K 1.4 Turbo 2019": {"price": 42_000, "type": "ICE", "fuel": 0, "city_l": 7.5, "hwy_l": 5.5, "segment": "C – Kompakt", "new": False},
    "Ford Focus IV 1.0 EcoBoost 2019": {"price": 45_000, "type": "ICE", "fuel": 0, "city_l": 6.5, "hwy_l": 5.0, "segment": "C – Kompakt", "new": False},
    "Hyundai i30 1.4 T-GDi 2018": {"price": 43_000, "type": "ICE", "fuel": 0, "city_l": 7.5, "hwy_l": 5.5, "segment": "C – Kompakt", "new": False},
    "Toyota Yaris III 1.5 2019": {"price": 40_000, "type": "ICE", "fuel": 0, "city_l": 5.5, "hwy_l": 4.5, "segment": "B – Małe", "new": False},
    "VW Polo V 1.4 TDI 2017": {"price": 32_000, "type": "ICE", "fuel": 1, "city_l": 5.0, "hwy_l": 4.0, "segment": "B – Małe", "new": False},
    "VW Passat B8 2.0 TDI 2018": {"price": 75_000, "type": "ICE", "fuel": 1, "city_l": 7.0, "hwy_l": 5.0, "segment": "D – Średni", "new": False},
    "Hyundai Tucson 1.6 T-GDi 2019": {"price": 80_000, "type": "ICE", "fuel": 0, "city_l": 9.0, "hwy_l": 7.0, "segment": "D – Średni", "new": False},
    "Kia Sportage 1.6 GDi 2018": {"price": 65_000, "type": "ICE", "fuel": 0, "city_l": 9.5, "hwy_l": 7.5, "segment": "D – Średni", "new": False},
    "Toyota RAV4 2.0 2019": {"price": 95_000, "type": "ICE", "fuel": 0, "city_l": 8.5, "hwy_l": 6.5, "segment": "D – Średni", "new": False},
    "BMW 320d F30 2017": {"price": 70_000, "type": "ICE", "fuel": 1, "city_l": 7.5, "hwy_l": 5.0, "segment": "E – Wyższy", "new": False},
    "Mercedes C 220d W205 2018": {"price": 85_000, "type": "ICE", "fuel": 1, "city_l": 7.0, "hwy_l": 5.0, "segment": "E – Wyższy", "new": False},
    "Audi A4 B9 2.0 TDI 2018": {"price": 80_000, "type": "ICE", "fuel": 1, "city_l": 7.0, "hwy_l": 5.0, "segment": "E – Wyższy", "new": False},
    "Dacia Duster 1.5 dCi 2020": {"price": 55_000, "type": "ICE", "fuel": 1, "city_l": 7.0, "hwy_l": 5.5, "segment": "D – Średni", "new": False},
    "Renault Megane 1.3 TCe 2020": {"price": 48_000, "type": "ICE", "fuel": 0, "city_l": 7.0, "hwy_l": 5.5, "segment": "C – Kompakt", "new": False},
    "Land Rover Discovery Sport 2.0 TD4 2018": {"price": 110_000, "type": "ICE", "fuel": 1, "city_l": 9.0, "hwy_l": 7.0, "segment": "E – Wyższy", "new": False},
    "Land Rover Range Rover Evoque 2.0 D 2019": {"price": 130_000, "type": "ICE", "fuel": 1, "city_l": 8.5, "hwy_l": 6.5, "segment": "E – Wyższy", "new": False},
    "Jeep Compass 1.4 MultiAir 2019": {"price": 75_000, "type": "ICE", "fuel": 0, "city_l": 9.5, "hwy_l": 7.0, "segment": "D – Średni", "new": False},
    "Peugeot 308 1.5 BlueHDi 2020": {"price": 55_000, "type": "ICE", "fuel": 1, "city_l": 5.5, "hwy_l": 4.5, "segment": "C – Kompakt", "new": False},
    "Citroen C3 1.2 PureTech 2020": {"price": 38_000, "type": "ICE", "fuel": 0, "city_l": 6.0, "hwy_l": 4.5, "segment": "B – Małe", "new": False},
    "Seat Leon 1.5 TSI 2019": {"price": 52_000, "type": "ICE", "fuel": 0, "city_l": 7.0, "hwy_l": 5.5, "segment": "C – Kompakt", "new": False},

    # ===== BEV — NOWE =====
    "Tesla Model 3 SR+ 2025": {"price": 175_000, "type": "BEV", "city_kwh": 14.0, "hwy_kwh": 16.5, "bat": 60, "segment": "C – Kompakt", "new": True},
    "Tesla Model 3 LR AWD 2025": {"price": 215_000, "type": "BEV", "city_kwh": 14.5, "hwy_kwh": 17.0, "bat": 82, "segment": "C – Kompakt", "new": True},
    "Tesla Model Y LR AWD 2025": {"price": 219_000, "type": "BEV", "city_kwh": 15.5, "hwy_kwh": 18.5, "bat": 82, "segment": "D – Średni", "new": True},
    "Tesla Model Y SR 2025": {"price": 189_000, "type": "BEV", "city_kwh": 15.0, "hwy_kwh": 17.5, "bat": 60, "segment": "D – Średni", "new": True},
    "BYD Atto 3 2025": {"price": 155_000, "type": "BEV", "city_kwh": 16.0, "hwy_kwh": 19.0, "bat": 60, "segment": "C – Kompakt", "new": True},
    "BYD Seal 2025": {"price": 185_000, "type": "BEV", "city_kwh": 14.5, "hwy_kwh": 17.0, "bat": 82, "segment": "D – Średni", "new": True},
    "BYD Dolphin 2025": {"price": 120_000, "type": "BEV", "city_kwh": 13.5, "hwy_kwh": 16.0, "bat": 44, "segment": "B – Małe", "new": True},
    "Hyundai Ioniq 5 LR AWD 2025": {"price": 245_000, "type": "BEV", "city_kwh": 16.5, "hwy_kwh": 19.5, "bat": 84, "segment": "D – Średni", "new": True},
    "Hyundai Ioniq 6 LR 2025": {"price": 235_000, "type": "BEV", "city_kwh": 14.0, "hwy_kwh": 16.5, "bat": 77, "segment": "D – Średni", "new": True},
    "Kia EV6 LR AWD 2025": {"price": 255_000, "type": "BEV", "city_kwh": 17.0, "hwy_kwh": 20.0, "bat": 77, "segment": "D – Średni", "new": True},
    "Kia EV6 LR RWD 2025": {"price": 225_000, "type": "BEV", "city_kwh": 15.5, "hwy_kwh": 18.5, "bat": 77, "segment": "D – Średni", "new": True},
    "Skoda Enyaq 85 2025": {"price": 215_000, "type": "BEV", "city_kwh": 16.0, "hwy_kwh": 19.0, "bat": 82, "segment": "D – Średni", "new": True},
    "VW ID.4 Pro 2025": {"price": 210_000, "type": "BEV", "city_kwh": 16.5, "hwy_kwh": 19.5, "bat": 82, "segment": "D – Średni", "new": True},
    "VW ID.3 Pro 2025": {"price": 165_000, "type": "BEV", "city_kwh": 15.0, "hwy_kwh": 17.5, "bat": 59, "segment": "C – Kompakt", "new": True},
    "VW ID.7 Pro 2025": {"price": 265_000, "type": "BEV", "city_kwh": 15.5, "hwy_kwh": 18.0, "bat": 86, "segment": "E – Wyższy", "new": True},
    "BMW iX1 eDrive20 2025": {"price": 225_000, "type": "BEV", "city_kwh": 16.0, "hwy_kwh": 19.0, "bat": 65, "segment": "D – Średni", "new": True},
    "BMW iX3 2025": {"price": 280_000, "type": "BEV", "city_kwh": 17.5, "hwy_kwh": 20.0, "bat": 80, "segment": "E – Wyższy", "new": True},
    "Mercedes EQA 250+ 2025": {"price": 240_000, "type": "BEV", "city_kwh": 16.5, "hwy_kwh": 19.0, "bat": 70, "segment": "D – Średni", "new": True},
    "Mercedes EQB 250+ 2025": {"price": 255_000, "type": "BEV", "city_kwh": 17.0, "hwy_kwh": 20.0, "bat": 70, "segment": "D – Średni", "new": True},
    "Volvo EX30 Single Motor 2025": {"price": 165_000, "type": "BEV", "city_kwh": 15.0, "hwy_kwh": 17.5, "bat": 51, "segment": "B – Małe", "new": True},
    "Volvo EX40 Recharge 2025": {"price": 225_000, "type": "BEV", "city_kwh": 17.0, "hwy_kwh": 20.0, "bat": 82, "segment": "D – Średni", "new": True},
    "Fiat 500e 2025": {"price": 120_000, "type": "BEV", "city_kwh": 13.0, "hwy_kwh": 16.0, "bat": 42, "segment": "A – Mini", "new": True},
    "Renault Megane E-Tech 2025": {"price": 175_000, "type": "BEV", "city_kwh": 15.5, "hwy_kwh": 18.0, "bat": 60, "segment": "C – Kompakt", "new": True},
    "Peugeot e-308 2025": {"price": 185_000, "type": "BEV", "city_kwh": 15.0, "hwy_kwh": 17.5, "bat": 54, "segment": "C – Kompakt", "new": True},
    "Opel Astra Electric 2025": {"price": 180_000, "type": "BEV", "city_kwh": 15.0, "hwy_kwh": 17.5, "bat": 54, "segment": "C – Kompakt", "new": True},
    "MG4 Electric Standard 2025": {"price": 115_000, "type": "BEV", "city_kwh": 15.0, "hwy_kwh": 17.0, "bat": 51, "segment": "C – Kompakt", "new": True},
    "MG4 Electric Extended 2025": {"price": 135_000, "type": "BEV", "city_kwh": 15.5, "hwy_kwh": 18.0, "bat": 77, "segment": "C – Kompakt", "new": True},
    "Dacia Spring 2025": {"price": 85_000, "type": "BEV", "city_kwh": 13.0, "hwy_kwh": 17.0, "bat": 27, "segment": "A – Mini", "new": True},
    "Cupra Born 58 kWh 2025": {"price": 165_000, "type": "BEV", "city_kwh": 15.5, "hwy_kwh": 18.0, "bat": 58, "segment": "C – Kompakt", "new": True},
    "Nissan Ariya 63 kWh 2025": {"price": 195_000, "type": "BEV", "city_kwh": 16.5, "hwy_kwh": 19.5, "bat": 63, "segment": "D – Średni", "new": True},

    # ===== BEV — UŻYWANE =====
    "Tesla Model 3 SR+ 2021": {"price": 110_000, "type": "BEV", "city_kwh": 14.5, "hwy_kwh": 17.0, "bat": 55, "segment": "C – Kompakt", "new": False},
    "Tesla Model 3 LR 2022": {"price": 140_000, "type": "BEV", "city_kwh": 14.5, "hwy_kwh": 17.0, "bat": 82, "segment": "C – Kompakt", "new": False},
    "Tesla Model Y LR 2023": {"price": 165_000, "type": "BEV", "city_kwh": 16.0, "hwy_kwh": 19.0, "bat": 82, "segment": "D – Średni", "new": False},
    "VW ID.3 Pro 2022": {"price": 95_000, "type": "BEV", "city_kwh": 15.5, "hwy_kwh": 18.0, "bat": 58, "segment": "C – Kompakt", "new": False},
    "VW ID.4 Pro 2022": {"price": 120_000, "type": "BEV", "city_kwh": 17.0, "hwy_kwh": 20.0, "bat": 77, "segment": "D – Średni", "new": False},
    "Hyundai Ioniq 5 LR 2022": {"price": 145_000, "type": "BEV", "city_kwh": 17.0, "hwy_kwh": 20.0, "bat": 73, "segment": "D – Średni", "new": False},
    "Kia EV6 LR 2022": {"price": 150_000, "type": "BEV", "city_kwh": 17.0, "hwy_kwh": 20.0, "bat": 77, "segment": "D – Średni", "new": False},
    "BMW iX1 eDrive20 2023": {"price": 165_000, "type": "BEV", "city_kwh": 16.5, "hwy_kwh": 19.5, "bat": 65, "segment": "D – Średni", "new": False},
    "Nissan Leaf 40 kWh 2020": {"price": 60_000, "type": "BEV", "city_kwh": 15.0, "hwy_kwh": 18.0, "bat": 40, "segment": "C – Kompakt", "new": False},
    "Renault Zoe R135 2021": {"price": 65_000, "type": "BEV", "city_kwh": 14.0, "hwy_kwh": 17.5, "bat": 52, "segment": "B – Małe", "new": False},
    "Skoda Enyaq 80 2022": {"price": 130_000, "type": "BEV", "city_kwh": 16.5, "hwy_kwh": 19.5, "bat": 77, "segment": "D – Średni", "new": False},
    "Peugeot e-208 2021": {"price": 70_000, "type": "BEV", "city_kwh": 14.5, "hwy_kwh": 17.0, "bat": 50, "segment": "B – Małe", "new": False},

    # ===== HEV — NOWE =====
    "Toyota Yaris 1.5 Hybrid 2025 HEV": {"price": 95_000, "type": "HEV", "fuel": 0, "city_l": 3.8, "hwy_l": 4.8, "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0, "segment": "B – Małe", "new": True},
    "Toyota Corolla 2.0 Hybrid 2025": {"price": 145_000, "type": "HEV", "fuel": 0, "city_l": 4.5, "hwy_l": 5.5, "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0, "segment": "C – Kompakt", "new": True},
    "Toyota C-HR 2.0 Hybrid 2025": {"price": 155_000, "type": "HEV", "fuel": 0, "city_l": 4.8, "hwy_l": 5.8, "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0, "segment": "C – Kompakt", "new": True},
    "Toyota RAV4 2.5 Hybrid 2025 HEV": {"price": 195_000, "type": "HEV", "fuel": 0, "city_l": 5.0, "hwy_l": 6.5, "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0, "segment": "D – Średni", "new": True},
    "Honda Civic 2.0 e:HEV 2025": {"price": 145_000, "type": "HEV", "fuel": 0, "city_l": 4.5, "hwy_l": 5.5, "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0, "segment": "C – Kompakt", "new": True},
    "Hyundai Tucson 1.6 HEV 2025": {"price": 175_000, "type": "HEV", "fuel": 0, "city_l": 5.5, "hwy_l": 6.5, "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0, "segment": "D – Średni", "new": True},
    "Kia Sportage 1.6 HEV 2025": {"price": 170_000, "type": "HEV", "fuel": 0, "city_l": 5.5, "hwy_l": 6.5, "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0, "segment": "D – Średni", "new": True},

    # ===== PHEV — NOWE =====
    "BMW 330e 2025": {"price": 255_000, "type": "PHEV", "fuel": 0, "city_l": 1.5, "hwy_l": 5.5, "bat": 12, "city_kwh": 15.0, "hwy_kwh": 18.0, "elec_pct": 0.55, "segment": "E – Wyższy", "new": True},
    "Mercedes C 300e 2025": {"price": 285_000, "type": "PHEV", "fuel": 0, "city_l": 1.5, "hwy_l": 5.5, "bat": 25, "city_kwh": 16.0, "hwy_kwh": 19.0, "elec_pct": 0.65, "segment": "E – Wyższy", "new": True},
    "Kia Niro 1.6 PHEV 2025": {"price": 165_000, "type": "PHEV", "fuel": 0, "city_l": 1.4, "hwy_l": 5.5, "bat": 11, "city_kwh": 14.0, "hwy_kwh": 17.0, "elec_pct": 0.60, "segment": "C – Kompakt", "new": True},
    "Hyundai Tucson 1.6 PHEV 2025": {"price": 210_000, "type": "PHEV", "fuel": 0, "city_l": 1.4, "hwy_l": 5.8, "bat": 14, "city_kwh": 15.0, "hwy_kwh": 18.0, "elec_pct": 0.55, "segment": "D – Średni", "new": True},
    "Toyota RAV4 2.5 PHEV 2025": {"price": 240_000, "type": "PHEV", "fuel": 0, "city_l": 1.2, "hwy_l": 5.5, "bat": 18, "city_kwh": 15.0, "hwy_kwh": 18.0, "elec_pct": 0.60, "segment": "D – Średni", "new": True},
    "VW Golf GTE 2025": {"price": 195_000, "type": "PHEV", "fuel": 0, "city_l": 1.5, "hwy_l": 5.5, "bat": 13, "city_kwh": 14.0, "hwy_kwh": 17.0, "elec_pct": 0.55, "segment": "C – Kompakt", "new": True},
    "Volvo XC60 T6 Recharge 2025": {"price": 310_000, "type": "PHEV", "fuel": 0, "city_l": 1.8, "hwy_l": 6.0, "bat": 18, "city_kwh": 16.0, "hwy_kwh": 19.0, "elec_pct": 0.55, "segment": "E – Wyższy", "new": True},

    # ===== HEV / PHEV — UŻYWANE =====
    "Toyota Corolla 1.8 Hybrid 2019 HEV": {"price": 65_000, "type": "HEV", "fuel": 0, "city_l": 4.5, "hwy_l": 5.5, "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0, "segment": "C – Kompakt", "new": False},
    "Toyota C-HR 1.8 Hybrid 2020": {"price": 80_000, "type": "HEV", "fuel": 0, "city_l": 5.0, "hwy_l": 6.0, "bat": 0, "city_kwh": 0, "hwy_kwh": 0, "elec_pct": 0, "segment": "C – Kompakt", "new": False},
    "BMW 330e 2020": {"price": 130_000, "type": "PHEV", "fuel": 0, "city_l": 1.8, "hwy_l": 6.0, "bat": 12, "city_kwh": 16.0, "hwy_kwh": 19.0, "elec_pct": 0.50, "segment": "E – Wyższy", "new": False},
    "Kia Niro 1.6 PHEV 2021": {"price": 95_000, "type": "PHEV", "fuel": 0, "city_l": 1.5, "hwy_l": 5.8, "bat": 8.9, "city_kwh": 14.5, "hwy_kwh": 17.5, "elec_pct": 0.55, "segment": "C – Kompakt", "new": False},
}


def search_cars(query: str, car_type: str = None, max_results: int = 10) -> list:
    """Wyszukaj samochody po nazwie (fuzzy match).

    Args:
        query: tekst wpisany przez usera (np. "land rover disc")
        car_type: filtr typu ("ICE", "BEV", "HEV", "PHEV") lub None = wszystkie
        max_results: max wyników

    Returns:
        Lista tupli (nazwa, parametry_dict)
    """
    if not query or len(query) < 2:
        return []

    q = query.lower().strip()
    results = []

    for name, params in CAR_DB.items():
        # Filtr typu
        if car_type:
            if car_type == "HEV":
                if params["type"] not in ("HEV", "PHEV"):
                    continue
            elif params["type"] != car_type:
                continue

        name_lower = name.lower()
        # Exact substring match
        if q in name_lower:
            # Score: exact match at start = highest
            score = 100 if name_lower.startswith(q) else 50
            results.append((score, name, params))
        else:
            # Word-by-word match (all query words must appear)
            words = q.split()
            if all(w in name_lower for w in words):
                results.append((30, name, params))

    # Sort by score descending
    results.sort(key=lambda x: -x[0])
    return [(name, params) for _, name, params in results[:max_results]]


def get_all_names(car_type: str = None) -> list:
    """Get all car names, optionally filtered by type."""
    if car_type:
        valid_types = [car_type]
        if car_type == "HEV":
            valid_types = ["HEV", "PHEV"]
        return [n for n, p in CAR_DB.items() if p["type"] in valid_types]
    return list(CAR_DB.keys())
