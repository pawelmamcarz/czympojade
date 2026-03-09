#!/usr/bin/env python3
"""
scrape_importers.py — Scraper cenników nowych aut od polskich importerów.

Podprojekt CzymPojade: zbiera aktualne ceny, silniki, zużycie paliwa/prądu
ze stron importerów (toyota.pl, volkswagen.pl, hyundai.pl, …).

Wynik: JSON kompatybilny z presetami w app.py
(ICE_PRESETS_NEW, BEV_PRESETS_NEW, HYB_PRESETS_NEW).

Użycie:
    python scrape_importers.py                   # scrape all brands
    python scrape_importers.py --brands toyota vw # only specific brands
    python scrape_importers.py --output data/     # save to directory
    python scrape_importers.py --dry-run          # parse without saving
    python scrape_importers.py --format presets   # output app.py preset code

Strategia scrapingu:
    Większość importerów blokuje bezpośredni scraping (JS-rendered, Cloudflare).
    Skrypt próbuje 3 strategie w kolejności:
    1. API JSON — niektóre strony mają ukryte REST API (np. toyota.pl/api/*)
    2. HTML scraping — klasyczne parsowanie stron cennikowych
    3. Autocentrum.pl — agregator cenników jako fallback

    Dane można też wprowadzać ręcznie via --import-csv.
"""

import argparse
import json
import csv
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_SCRAPING = True
except ImportError:
    HAS_SCRAPING = False
    print("⚠️  Brak requests/beautifulsoup4. Zainstaluj: pip install requests beautifulsoup4")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================================
# Data model
# ============================================================================

@dataclass
class CarModel:
    """Pojedynczy model auta z cennika importera."""
    brand: str               # np. "Toyota"
    model: str               # np. "Corolla"
    variant: str             # np. "1.8 Hybrid Comfort"
    price_pln: int           # cena brutto PLN
    engine_type: str         # "ICE", "BEV", "HEV", "PHEV"
    fuel_type: int = 0       # 0=benzyna, 1=diesel, 2=LPG
    # ICE / HEV
    fuel_city_l: float = 0.0    # zużycie miasto l/100km
    fuel_hwy_l: float = 0.0     # zużycie trasa l/100km
    # BEV / PHEV
    battery_kwh: float = 0.0    # pojemność baterii kWh
    consumption_city_kwh: float = 0.0  # zużycie prądu miasto kWh/100km
    consumption_hwy_kwh: float = 0.0   # zużycie prądu trasa kWh/100km
    elec_pct: float = 0.0       # % jazdy na prądzie (PHEV)
    # Meta
    segment: str = ""        # "B – Małe", "C – Kompakt", etc.
    url: str = ""            # URL źródłowy
    scraped_at: str = ""     # ISO timestamp

    def preset_name(self) -> str:
        """Generuje nazwę do presetu: 'Toyota Corolla 1.8 Hybrid'."""
        # Wyciągnij silnik z variantu
        engine_part = self.variant.split()[0] if self.variant else ""
        # Szukaj wzorca x.x lub x.xL (pojemność)
        cap_match = re.search(r'(\d+\.\d+)', self.variant or "")
        capacity = cap_match.group(1) if cap_match else ""

        # Typ napędu
        drive_suffix = ""
        if self.engine_type == "BEV":
            drive_suffix = ""  # np. "Tesla Model Y"
        elif self.engine_type == "HEV":
            drive_suffix = "Hybrid"
        elif self.engine_type == "PHEV":
            drive_suffix = "PHEV"
        elif self.fuel_type == 1:
            drive_suffix = "TDI" if "vw" in self.brand.lower() or "skoda" in self.brand.lower() else "Diesel"
        elif self.fuel_type == 2:
            drive_suffix = "LPG"

        parts = [self.brand, self.model]
        if capacity:
            parts.append(capacity)
        if drive_suffix:
            parts.append(drive_suffix)

        return " ".join(parts)

    def to_ice_preset(self) -> dict:
        return {
            "price": self.price_pln,
            "city_l": self.fuel_city_l,
            "hwy_l": self.fuel_hwy_l,
            "fuel": self.fuel_type,
        }

    def to_bev_preset(self) -> dict:
        return {
            "price": self.price_pln,
            "city_kwh": self.consumption_city_kwh,
            "hwy_kwh": self.consumption_hwy_kwh,
            "bat": int(self.battery_kwh),
        }

    def to_hyb_preset(self) -> dict:
        return {
            "price": self.price_pln,
            "city_l": self.fuel_city_l,
            "hwy_l": self.fuel_hwy_l,
            "fuel": self.fuel_type,
            "hybrid_type": self.engine_type,  # "HEV" or "PHEV"
            "bat": self.battery_kwh,
            "city_kwh": self.consumption_city_kwh,
            "hwy_kwh": self.consumption_hwy_kwh,
            "elec_pct": self.elec_pct,
        }


# ============================================================================
# Segment classifier
# ============================================================================

# Mapowanie model → segment (rozbudowywane w miarę dodawania modeli)
MODEL_SEGMENT_MAP = {
    # A – Mini
    "500": "A – Mini", "panda": "A – Mini", "aygo": "A – Mini",
    "up!": "A – Mini", "spring": "A – Mini", "twingo": "A – Mini",

    # B – Małe
    "yaris": "B – Małe", "polo": "B – Małe", "i20": "B – Małe",
    "clio": "B – Małe", "corsa": "B – Małe", "fabia": "B – Małe",
    "ibiza": "B – Małe", "sandero": "B – Małe", "swift": "B – Małe",
    "jazz": "B – Małe", "micra": "B – Małe", "yaris cross": "B – Małe",
    "mg4": "B – Małe", "mg3": "B – Małe", "renault 5": "B – Małe",
    "cooper": "B – Małe", "500e": "B – Małe", "juke": "B – Małe",
    "captur": "B – Małe", "arona": "B – Małe", "puma": "B – Małe",
    "2008": "B – Małe", "c3": "B – Małe", "avenger": "B – Małe",

    # C – Kompakt
    "corolla": "C – Kompakt", "golf": "C – Kompakt", "i30": "C – Kompakt",
    "octavia": "C – Kompakt", "leon": "C – Kompakt", "megane": "C – Kompakt",
    "astra": "C – Kompakt", "focus": "C – Kompakt", "mazda3": "C – Kompakt",
    "civic": "C – Kompakt", "c-hr": "C – Kompakt", "model 3": "C – Kompakt",
    "id.3": "C – Kompakt", "duster": "C – Kompakt", "karoq": "C – Kompakt",
    "qashqai": "C – Kompakt", "3008": "C – Kompakt", "c4": "C – Kompakt",
    "tipo": "C – Kompakt", "vitara": "C – Kompakt", "seal": "C – Kompakt",
    "jogger": "C – Kompakt", "scala": "C – Kompakt",

    # D – Średni
    "camry": "D – Średni", "passat": "D – Średni", "tucson": "D – Średni",
    "sportage": "D – Średni", "rav4": "D – Średni", "tiguan": "D – Średni",
    "forester": "D – Średni", "outback": "D – Średni", "model y": "D – Średni",
    "id.4": "D – Średni", "ioniq 5": "D – Średni", "enyaq": "D – Średni",
    "ev6": "D – Średni", "5008": "D – Średni", "c5": "D – Średni",
    "cr-v": "D – Średni", "zr-v": "D – Średni", "austral": "D – Średni",
    "kodiaq": "D – Średni", "sorento": "D – Średni", "x-trail": "D – Średni",
    "cx-5": "D – Średni", "model y": "D – Średni", "xc40": "D – Średni",
    "xc60": "D – Średni",

    # E – Wyższy
    "seria 3": "E – Wyższy", "klasa c": "E – Wyższy", "a4": "E – Wyższy",
    "seria 5": "E – Wyższy", "klasa e": "E – Wyższy", "a6": "E – Wyższy",
    "model s": "E – Wyższy", "taycan": "E – Wyższy", "s90": "E – Wyższy",
    "superb": "E – Wyższy", "stinger": "E – Wyższy",

    # Van – Mały
    "caddy": "Van – Mały", "berlingo": "Van – Mały", "proace city": "Van – Mały",
    "combo": "Van – Mały", "kangoo": "Van – Mały", "partner": "Van – Mały",
    "doblo": "Van – Mały", "townstar": "Van – Mały", "rifter": "Van – Mały",
    "proace city verso": "Van – Mały",

    # Van – Duży
    "transporter": "Van – Duży", "transit": "Van – Duży", "proace": "Van – Duży",
    "trafic": "Van – Duży", "vivaro": "Van – Duży", "expert": "Van – Duży",
    "master": "Van – Duży", "movano": "Van – Duży", "sprinter": "Van – Duży",
    "crafter": "Van – Duży", "ducato": "Van – Duży",
}


def classify_segment(model_name: str) -> str:
    """Rozpoznaje segment na podstawie nazwy modelu."""
    lower = model_name.lower().strip()
    # Dopasowanie dwuwyrazowe ma priorytet (np. "yaris cross", "proace city")
    for key in sorted(MODEL_SEGMENT_MAP.keys(), key=len, reverse=True):
        if key in lower:
            return MODEL_SEGMENT_MAP[key]
    return "C – Kompakt"  # domyślny fallback


# ============================================================================
# HTTP session
# ============================================================================

def _make_session() -> "requests.Session":
    """Creates a requests session with browser-like headers."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
    })
    return s


# ============================================================================
# Brand scrapers
# ============================================================================

class BrandScraper:
    """Bazowa klasa scrapera jednej marki."""
    brand_name: str = ""
    base_url: str = ""
    price_list_urls: list = []

    def __init__(self, session: "requests.Session"):
        self.session = session
        self.models: list[CarModel] = []

    def scrape(self) -> list[CarModel]:
        """Main entry point. Override in subclass."""
        raise NotImplementedError

    def _get(self, url: str, **kwargs) -> "requests.Response":
        """GET with rate limiting and error handling."""
        time.sleep(1.5)  # rate limiting
        resp = self.session.get(url, timeout=15, **kwargs)
        resp.raise_for_status()
        return resp

    def _parse_price(self, text: str) -> Optional[int]:
        """Extract price from text like '135 900 PLN', '135.900 zł', etc."""
        if not text:
            return None
        # Remove non-numeric except space, comma, dot
        clean = re.sub(r'[^\d\s,.]', '', text.strip())
        # Handle "135 900" or "135900"
        clean = re.sub(r'\s+', '', clean)
        # Handle "135.900" (thousands separator)
        if '.' in clean and ',' not in clean and len(clean.split('.')[-1]) == 3:
            clean = clean.replace('.', '')
        # Handle "135,900"
        if ',' in clean and len(clean.split(',')[-1]) == 3:
            clean = clean.replace(',', '')
        try:
            val = int(float(clean))
            return val if 20_000 < val < 3_000_000 else None
        except (ValueError, TypeError):
            return None

    def _parse_consumption(self, text: str) -> Optional[float]:
        """Extract fuel consumption like '5,5 l/100km' → 5.5."""
        if not text:
            return None
        match = re.search(r'(\d+[,\.]\d+)', text)
        if match:
            return float(match.group(1).replace(',', '.'))
        return None


class AutocentrumScraper(BrandScraper):
    """
    Scraper autocentrum.pl/nowe/ — agregator cenników nowych aut.

    Struktura URL (potwierdzone 03/2026):
    /nowe/                     → lista marek
    /nowe/{marka}/             → lista modeli z cenami "od" + spalanie
    /nowe/{marka}/{model}/     → warianty z cenami (silnik, pakiet, skrzynia)
    """
    brand_name = "autocentrum"
    base_url = "https://www.autocentrum.pl"

    BRAND_SLUGS = {
        "toyota": "toyota", "volkswagen": "volkswagen", "hyundai": "hyundai",
        "kia": "kia", "skoda": "skoda", "ford": "ford", "bmw": "bmw",
        "mercedes": "mercedes-benz", "audi": "audi", "opel": "opel",
        "peugeot": "peugeot", "citroen": "citroen", "renault": "renault",
        "dacia": "dacia", "fiat": "fiat", "mazda": "mazda", "nissan": "nissan",
        "honda": "honda", "volvo": "volvo", "suzuki": "suzuki", "mg": "mg",
        "byd": "byd", "tesla": "tesla", "cupra": "cupra", "seat": "seat",
        "lexus": "lexus", "mini": "mini", "jeep": "jeep", "subaru": "subaru",
        "porsche": "porsche", "ds": "ds-automobiles",
    }

    def __init__(self, session, brands: list[str] | None = None):
        super().__init__(session)
        self.target_brands = brands  # None = all

    def scrape(self) -> list[CarModel]:
        """Scrape cenniki from autocentrum.pl/nowe/."""
        brands_to_scrape = self.target_brands or list(self.BRAND_SLUGS.keys())

        for brand in brands_to_scrape:
            slug = self.BRAND_SLUGS.get(brand.lower())
            if not slug:
                logger.warning("Nieznana marka dla autocentrum: %s", brand)
                continue

            try:
                self._scrape_brand(brand.title(), slug)
            except Exception as e:
                logger.error("Błąd scrapowania %s z autocentrum: %s", brand, e)

        return self.models

    def _scrape_brand(self, brand_display: str, slug: str):
        """Scrape all models from brand listing page (/nowe/{brand}/).

        HTML structure (03/2026):
          div.offer-item
            a.offer-item-info[href] → model page URL
              h2                    → "Toyota Corolla"
            div.labels.tags         → "Spalanie od: 5.0 l/100 km"
            div.price               → "106 900 PLN"
        """
        url = f"{self.base_url}/nowe/{slug}/"
        logger.info("Scraping %s: %s", brand_display, url)

        try:
            resp = self._get(url)
        except Exception as e:
            logger.warning("Cannot fetch %s: %s", url, e)
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div.offer-item")

        if not cards:
            logger.warning("No offer-item cards found for %s", brand_display)
            return

        model_links = []
        for card in cards:
            # Extract model name from h2
            h2 = card.select_one("a.offer-item-info h2")
            if not h2:
                h2 = card.select_one("h2")
            if not h2:
                continue
            model_full_name = h2.get_text(strip=True)  # "Toyota Corolla"

            # Extract model page URL
            link_el = card.select_one("a.offer-item-info")
            if not link_el:
                link_el = card.select_one("a[href*='/nowe/']")
            if not link_el:
                continue
            href = link_el.get("href", "")

            # Extract "from" price
            price_el = card.select_one("div.price")
            price_text = price_el.get_text(strip=True) if price_el else ""
            price = self._parse_price(price_text)

            # Extract fuel consumption from labels
            fuel_consumption = None
            labels = card.select(".labels div, .labels.tags div")
            for label in labels:
                label_text = label.get_text(strip=True)
                if "spalanie" in label_text.lower():
                    fuel_consumption = self._parse_consumption(label_text)
                    break

            model_links.append({
                "full_name": model_full_name,
                "href": href,
                "price": price,
                "consumption": fuel_consumption,
            })

        logger.info("Found %d models for %s on brand page", len(model_links), brand_display)

        # For each model, scrape the detail page for variants
        for info in model_links[:20]:
            model_url = info["href"]
            if model_url.startswith("/"):
                model_url = self.base_url + model_url

            # Extract model name: strip brand prefix ("Toyota Corolla" → "Corolla")
            model_name = info["full_name"]
            if model_name.lower().startswith(brand_display.lower()):
                model_name = model_name[len(brand_display):].strip()
            if not model_name:
                model_name = info["full_name"]

            try:
                self._scrape_model(brand_display, model_name, model_url,
                                   fallback_price=info["price"],
                                   fallback_consumption=info["consumption"])
            except Exception as e:
                logger.warning("Błąd modelu %s %s: %s", brand_display, model_name, e)

    def _scrape_model(self, brand: str, model_name: str, url: str,
                      fallback_price: int | None = None,
                      fallback_consumption: float | None = None):
        """Scrape variants from model page (/nowe/{brand}/{model}/).

        HTML structure:
          a.configuration-row
            div[0]      → body type: "Hatchback"
            div[1]      → engine: "1.5 Hybrid Dynamic Force 116 KM"
            div[2]      → package (span[1]): "Active"
            div[3]      → transmission (span[1]): "manualna, 6-biegowa"
            div[4]      → drive (span[1]): "na przednią oś"
            div.price   → "84 900 PLN"

        Engine type from URL href: silnik-benzynowy / silnik-hybrydowy / silnik-elektryczny
        """
        try:
            resp = self._get(url)
        except Exception:
            # Use fallback data from brand page if detail page fails
            if fallback_price:
                car = CarModel(
                    brand=brand, model=model_name, variant="base",
                    price_pln=fallback_price, engine_type="ICE",
                    fuel_city_l=fallback_consumption or 0,
                    segment=classify_segment(model_name),
                    url=url, scraped_at=datetime.now().isoformat(),
                )
                self.models.append(car)
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("a.configuration-row")

        if not rows:
            logger.debug("No configuration-row found for %s %s, using fallback", brand, model_name)
            if fallback_price:
                car = CarModel(
                    brand=brand, model=model_name, variant="base",
                    price_pln=fallback_price, engine_type="ICE",
                    fuel_city_l=fallback_consumption or 0,
                    segment=classify_segment(model_name),
                    url=url, scraped_at=datetime.now().isoformat(),
                )
                self.models.append(car)
            return

        seen_variants = set()
        for row in rows:
            cells = row.select("div")
            if len(cells) < 2:
                continue

            # Price (last cell with class 'price')
            price_el = row.select_one("div.price")
            price = self._parse_price(price_el.get_text(strip=True)) if price_el else None
            if not price:
                continue

            # Engine info (cell 1)
            engine_text = cells[1].get_text(strip=True) if len(cells) > 1 else ""

            # Package name (cell 2, second span)
            package = ""
            if len(cells) > 2:
                spans = cells[2].select("span")
                package = spans[1].get_text(strip=True) if len(spans) > 1 else cells[2].get_text(strip=True)

            # Determine engine type from href or engine text
            href = row.get("href", "")
            engine_type = "ICE"
            fuel_type = 0  # benzyna
            lower_engine = engine_text.lower()
            lower_href = href.lower()

            if "silnik-elektryczny" in lower_href or "electric" in lower_engine:
                engine_type = "BEV"
            elif "plug-in" in lower_engine or "phev" in lower_engine:
                engine_type = "PHEV"
            elif "silnik-hybrydowy" in lower_href or "hybrid" in lower_engine:
                engine_type = "HEV"

            if "diesel" in lower_engine or "tdi" in lower_engine or "bluehdi" in lower_engine or "silnik-diesla" in lower_href:
                fuel_type = 1

            # Build variant name: "1.5 Hybrid 116 KM Active"
            variant = engine_text
            if package and package.lower() not in engine_text.lower():
                variant = f"{engine_text} {package}"

            # Deduplicate: only cheapest per engine+package combo
            dedup_key = (engine_text, package)
            if dedup_key in seen_variants:
                continue
            seen_variants.add(dedup_key)

            car = CarModel(
                brand=brand,
                model=model_name,
                variant=variant,
                price_pln=price,
                engine_type=engine_type,
                fuel_type=fuel_type,
                fuel_city_l=fallback_consumption or 0,
                segment=classify_segment(model_name),
                url=url,
                scraped_at=datetime.now().isoformat(),
            )
            self.models.append(car)

        logger.info("Scraped %d variants for %s %s", len(seen_variants), brand, model_name)


class ToyotaAPIScraper(BrandScraper):
    """
    Scraper Toyota via cocadap.toyota-europe.com API.

    Publiczne JSON API — nie wymaga auth. Zwraca pełne cenniki
    z podziałem na grade → bodyType → engine → transmission → cena.
    Nie zawiera danych o spalaniu (trzeba brać z autocentrum.pl).
    """
    brand_name = "Toyota"
    API_BASE = "https://cocadap.toyota-europe.com/toyota/pl/pl/comparegradespecsv2"

    MODELS = {
        "Aygo X": "37d0214b-a347-4e4c-864f-d14df8086d90",
        "Yaris": "09a6531a-c3f1-4d2d-b4d3-eb45cbb35478",
        "Yaris Cross": "5c933238-df10-41c5-b921-a2e4d25ef931",
        "Corolla Sedan": "65bfd91d-f2a8-4cbb-bdbc-3834b400492a",
        "Corolla HB": "881ef498-b467-4895-8074-cbc4340ccc81",
        "Corolla TS": "3c8992f3-e4f9-4ae1-bb67-305780342518",
        "Corolla Cross": "aed6cffc-96a7-4068-806e-be22ce401878",
        "C-HR": "6c193d6b-514c-436f-ab43-654d97e601d8",
        "Camry": "b6866060-c84a-4a43-b968-25947907b9cc",
        "RAV4": "a68a58fb-a10e-41ae-9459-3a7c4060500f",
        "bZ4X": "7fb7f6d1-dbbc-4886-98ea-d1856e3815db",
        "Highlander": "44938d8c-6050-4bff-9173-500d1b9d76a1",
        "Land Cruiser": "60ae2897-f9e1-4ff6-bc61-974d2d0edb5f",
        "Prius Plug-in": "d27a100c-76fc-4d03-8ed4-ab4a152b09da",
        "GR86": "46bb482c-7143-42ef-ace3-90b8b6a67953",
        "Hilux": "e1610f96-e7f9-4cb1-8d64-a659fee2b768",
    }

    def __init__(self, session, models: list[str] | None = None):
        super().__init__(session)
        self.target_models = models  # None = all

    def scrape(self) -> list[CarModel]:
        """Scrape all Toyota models via cocadap API."""
        targets = self.target_models or list(self.MODELS.keys())

        for model_name in targets:
            uuid = self.MODELS.get(model_name)
            if not uuid:
                continue
            try:
                self._scrape_model(model_name, uuid)
            except Exception as e:
                logger.error("Toyota API error for %s: %s", model_name, e)

        logger.info("Toyota API: %d models scraped", len(self.models))
        return self.models

    def _scrape_model(self, model_name: str, uuid: str):
        """Fetch one model from API and extract variants."""
        url = f"{self.API_BASE}/{uuid}"
        resp = self._get(url, headers={"Accept": "application/json"})
        if not resp.headers.get("content-type", "").startswith("application/json"):
            logger.warning("Toyota API non-JSON response for %s", model_name)
            return

        data = resp.json()

        # Build engine lookup: id → {name, category_code, fuel_id}
        engine_map = {}
        for eng in data.get("engines", []):
            cat = eng.get("category", {})
            engine_map[eng["id"]] = {
                "name": eng.get("name", ""),
                "type": cat.get("code", "ICE"),  # HEV, BEV, PHEV, ICE
                "fuel": eng.get("fuel", ""),
            }

        # Build fuel lookup: id → name
        fuel_map = {}
        for f in data.get("fuels", []):
            fuel_map[f["id"]] = f.get("name", "")

        # Navigate submodels → grades → bodyTypes → engines → transmissions → wheeldrives
        for submodel in data.get("submodels", []):
            for grade in submodel.get("grades", []):
                grade_name = grade.get("name", "")
                for bt in grade.get("bodyTypes", []):
                    for eng_entry in bt.get("engines", []):
                        eng_id = eng_entry.get("id", "")
                        eng_info = engine_map.get(eng_id, {})
                        eng_name = eng_info.get("name", "")
                        eng_type = eng_info.get("type", "ICE")

                        fuel_name = fuel_map.get(eng_info.get("fuel", ""), "")
                        fuel_type = 0  # benzyna
                        if "diesel" in fuel_name.lower():
                            fuel_type = 1

                        for trans in eng_entry.get("transmissions", []):
                            for wd in trans.get("wheeldrives", []):
                                price_obj = wd.get("from") or wd.get("default")
                                if not price_obj:
                                    continue
                                price = int(price_obj.get("list", 0))
                                if price < 20_000 or price > 3_000_000:
                                    continue

                                # Deduplicate: keep cheapest per grade+engine combo
                                variant = f"{eng_name} {grade_name}".strip()

                                car = CarModel(
                                    brand="Toyota",
                                    model=model_name,
                                    variant=variant,
                                    price_pln=price,
                                    engine_type=eng_type,
                                    fuel_type=fuel_type,
                                    segment=classify_segment(model_name),
                                    url=url,
                                    scraped_at=datetime.now().isoformat(),
                                )
                                self.models.append(car)

    def _deduplicate(self):
        """Keep only cheapest variant per model+engine_type combo."""
        best = {}
        for m in self.models:
            key = (m.model, m.engine_type, m.variant)
            if key not in best or m.price_pln < best[key].price_pln:
                best[key] = m
        self.models = list(best.values())


class DirectImporterScraper(BrandScraper):
    """
    Scraper bezpośrednich stron importerów.
    Większość stron jest JS-rendered → fallback do autocentrum.pl.
    Toyota ma dedykowane API (ToyotaAPIScraper).
    """
    brand_name = "direct"

    def __init__(self, session, brands: list[str] | None = None):
        super().__init__(session)
        self.target_brands = brands

    def scrape(self) -> list[CarModel]:
        """Try Toyota API, skip other brands (JS-rendered, unreliable)."""
        brands = self.target_brands or ["toyota"]

        if "toyota" in [b.lower() for b in brands]:
            logger.info("=== Toyota API scraping ===")
            toyota = ToyotaAPIScraper(self.session)
            toyota_models = toyota.scrape()
            toyota._deduplicate()
            self.models.extend(toyota.models)
            logger.info("Toyota API: %d unique variants", len(toyota.models))

        return self.models


# ============================================================================
# CSV import (manual data entry fallback)
# ============================================================================

def import_from_csv(csv_path: str) -> list[CarModel]:
    """
    Import car data from CSV file.

    Expected columns:
        brand, model, variant, price_pln, engine_type, fuel_type,
        fuel_city_l, fuel_hwy_l, battery_kwh, consumption_city_kwh,
        consumption_hwy_kwh, elec_pct, segment

    Minimal columns: brand, model, price_pln, engine_type
    """
    models = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                car = CarModel(
                    brand=row["brand"],
                    model=row["model"],
                    variant=row.get("variant", ""),
                    price_pln=int(row["price_pln"]),
                    engine_type=row["engine_type"].upper(),
                    fuel_type=int(row.get("fuel_type", 0)),
                    fuel_city_l=float(row.get("fuel_city_l", 0)),
                    fuel_hwy_l=float(row.get("fuel_hwy_l", 0)),
                    battery_kwh=float(row.get("battery_kwh", 0)),
                    consumption_city_kwh=float(row.get("consumption_city_kwh", 0)),
                    consumption_hwy_kwh=float(row.get("consumption_hwy_kwh", 0)),
                    elec_pct=float(row.get("elec_pct", 0)),
                    segment=row.get("segment", ""),
                    scraped_at=datetime.now().isoformat(),
                )
                if not car.segment:
                    car.segment = classify_segment(car.model)
                models.append(car)
            except (KeyError, ValueError) as e:
                logger.warning("Skipping CSV row: %s — %s", row, e)

    logger.info("Imported %d models from CSV: %s", len(models), csv_path)
    return models


# ============================================================================
# Output formatters
# ============================================================================

def to_json(models: list[CarModel]) -> str:
    """Export models as JSON."""
    return json.dumps(
        [asdict(m) for m in models],
        ensure_ascii=False, indent=2,
    )


def to_csv_string(models: list[CarModel]) -> str:
    """Export models as CSV string."""
    if not models:
        return ""
    fields = [
        "brand", "model", "variant", "price_pln", "engine_type", "fuel_type",
        "fuel_city_l", "fuel_hwy_l", "battery_kwh",
        "consumption_city_kwh", "consumption_hwy_kwh", "elec_pct",
        "segment", "url", "scraped_at",
    ]
    lines = [",".join(fields)]
    for m in models:
        d = asdict(m)
        lines.append(",".join(str(d.get(f, "")) for f in fields))
    return "\n".join(lines)


def to_presets_code(models: list[CarModel]) -> str:
    """
    Generate Python code for app.py presets.

    Output: three dicts — ICE_PRESETS_NEW, BEV_PRESETS_NEW, HYB_PRESETS_NEW
    z danymi z importerów (uzupełnione o obecne segmenty).
    """
    ice: dict[str, dict] = {}
    bev: dict[str, dict] = {}
    hyb: dict[str, dict] = {}

    for m in models:
        seg = m.segment
        name = m.preset_name()

        if m.engine_type == "BEV":
            bev.setdefault(seg, {})[name] = m.to_bev_preset()
        elif m.engine_type in ("HEV", "PHEV"):
            hyb.setdefault(seg, {})[name] = m.to_hyb_preset()
        else:  # ICE
            ice.setdefault(seg, {})[name] = m.to_ice_preset()

    lines = []
    lines.append(f"# Auto-generated from scrape_importers.py — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    for var_name, data in [("ICE_PRESETS_NEW", ice), ("BEV_PRESETS_NEW", bev), ("HYB_PRESETS_NEW", hyb)]:
        lines.append(f"{var_name} = {{")
        for seg in sorted(data.keys()):
            lines.append(f'    "{seg}": {{')
            for model_name, preset in sorted(data[seg].items()):
                lines.append(f'        "{model_name}": {preset},')
            lines.append("    },")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def print_summary(models: list[CarModel]):
    """Print scraping summary to console."""
    if not models:
        print("\n❌ Brak zebranych modeli.")
        return

    brands = set(m.brand for m in models)
    segments = set(m.segment for m in models)
    engines = {}
    for m in models:
        engines[m.engine_type] = engines.get(m.engine_type, 0) + 1

    print(f"\n{'='*60}")
    print(f"📊 Scraping summary")
    print(f"{'='*60}")
    print(f"  Modeli zebranych: {len(models)}")
    print(f"  Marek:            {len(brands)}")
    print(f"  Segmentów:        {len(segments)}")
    print(f"  Typy napędów:")
    for eng, cnt in sorted(engines.items()):
        print(f"    {eng}: {cnt}")

    # Price stats per segment
    print(f"\n  Ceny wg segmentu:")
    by_seg = {}
    for m in models:
        by_seg.setdefault(m.segment, []).append(m.price_pln)

    for seg in sorted(by_seg.keys()):
        prices = by_seg[seg]
        avg = sum(prices) / len(prices)
        print(f"    {seg}: {min(prices):>10,} – {max(prices):>10,} PLN (avg {avg:,.0f}, n={len(prices)})")

    print(f"{'='*60}\n")


# ============================================================================
# Main orchestration
# ============================================================================

def scrape_all(
    brands: list[str] | None = None,
    use_autocentrum: bool = True,
    use_direct: bool = True,
) -> list[CarModel]:
    """
    Scrape all available sources.

    Strategy:
    1. Try direct importer APIs/HTML
    2. Fallback to autocentrum.pl aggregator
    3. Merge results, deduplicate
    """
    if not HAS_SCRAPING:
        logger.error("Missing requests/beautifulsoup4. Install: pip install requests beautifulsoup4")
        return []

    session = _make_session()
    all_models = []

    # 1. Direct importer scraping
    if use_direct:
        logger.info("=== Phase 1: Direct importer scraping ===")
        direct = DirectImporterScraper(session, brands)
        direct_models = direct.scrape()
        all_models.extend(direct_models)
        logger.info("Direct: %d models", len(direct_models))

    # 2. Autocentrum fallback
    if use_autocentrum:
        logger.info("=== Phase 2: Autocentrum.pl aggregator ===")
        ac = AutocentrumScraper(session, brands)
        ac_models = ac.scrape()
        all_models.extend(ac_models)
        logger.info("Autocentrum: %d models", len(ac_models))

    # Deduplicate by (brand, model, price)
    seen = set()
    unique = []
    for m in all_models:
        key = (m.brand.lower(), m.model.lower(), m.price_pln)
        if key not in seen:
            seen.add(key)
            unique.append(m)

    logger.info("Total unique models: %d (from %d raw)", len(unique), len(all_models))
    return unique


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Scraper cenników nowych aut od polskich importerów",
        epilog="Przykłady:\n"
               "  python scrape_importers.py --brands toyota vw kia\n"
               "  python scrape_importers.py --import-csv data/cennik_manual.csv\n"
               "  python scrape_importers.py --format presets --output data/presets.py\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--brands", nargs="+", default=None,
        help="Marki do scrapowania (domyślnie: wszystkie)",
    )
    parser.add_argument(
        "--import-csv", type=str, default=None,
        help="Import danych z pliku CSV (zamiast scrapowania)",
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Ścieżka do pliku wyjściowego (domyślnie: stdout)",
    )
    parser.add_argument(
        "--format", "-f", choices=["json", "csv", "presets", "summary"],
        default="json",
        help="Format wyjścia (default: json)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Pokaż co by zostało zescrapowane, bez zapisu",
    )
    parser.add_argument(
        "--no-direct", action="store_true",
        help="Pomiń bezpośrednie scrapowanie importerów",
    )
    parser.add_argument(
        "--no-autocentrum", action="store_true",
        help="Pomiń autocentrum.pl",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # --- Import from CSV ---
    if args.import_csv:
        models = import_from_csv(args.import_csv)
    else:
        # --- Scrape ---
        models = scrape_all(
            brands=args.brands,
            use_autocentrum=not args.no_autocentrum,
            use_direct=not args.no_direct,
        )

    if args.dry_run:
        print_summary(models)
        return

    # --- Output ---
    if args.format == "summary":
        print_summary(models)
        return

    if args.format == "json":
        output = to_json(models)
    elif args.format == "csv":
        output = to_csv_string(models)
    elif args.format == "presets":
        output = to_presets_code(models)
    else:
        output = to_json(models)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        logger.info("Saved to: %s", args.output)
        print_summary(models)
    else:
        print(output)


if __name__ == "__main__":
    main()
