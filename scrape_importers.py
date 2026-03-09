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
    Fallback: scrape autocentrum.pl/cenniki which aggregates all brands.

    autocentrum.pl ma strukturę:
    /cenniki/{marka}/ → lista modeli
    /cenniki/{marka}/{model}/ → wersje z cenami
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
        """Scrape cenniki from autocentrum.pl."""
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
        """Scrape all models for one brand."""
        url = f"{self.base_url}/cenniki/{slug}/"
        logger.info("Scraping %s: %s", brand_display, url)

        try:
            resp = self._get(url)
        except Exception as e:
            logger.warning("Cannot fetch %s: %s", url, e)
            return

        soup = BeautifulSoup(resp.text, "html.parser")

        # Find model links: usually <a href="/cenniki/toyota/corolla/">
        model_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if f"/cenniki/{slug}/" in href and href.count("/") >= 4:
                model_name = href.rstrip("/").split("/")[-1]
                if model_name and model_name != slug:
                    full_url = self.base_url + href if href.startswith("/") else href
                    model_links.append((model_name, full_url))

        # Deduplicate
        seen = set()
        unique_links = []
        for name, link in model_links:
            if name not in seen:
                seen.add(name)
                unique_links.append((name, link))

        for model_slug, model_url in unique_links[:15]:  # max 15 models per brand
            try:
                self._scrape_model(brand_display, model_slug, model_url)
            except Exception as e:
                logger.warning("Błąd modelu %s %s: %s", brand_display, model_slug, e)

    def _scrape_model(self, brand: str, model_slug: str, url: str):
        """Scrape variants for one model from autocentrum."""
        try:
            resp = self._get(url)
        except Exception:
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        model_display = model_slug.replace("-", " ").title()

        # Look for price tables or price entries
        # Autocentrum typically shows: Wersja | Silnik | Cena od
        rows = soup.select("table tr, .version-row, [class*='price']")

        found_any = False
        for row in rows:
            cells = row.find_all(["td", "th", "span", "div"])
            if len(cells) < 2:
                continue

            text_parts = [c.get_text(strip=True) for c in cells]
            full_text = " ".join(text_parts)

            # Try to extract price
            price = None
            for part in text_parts:
                price = self._parse_price(part)
                if price:
                    break

            if not price:
                continue

            # Determine engine type
            engine_type = "ICE"
            lower_text = full_text.lower()
            if "electric" in lower_text or "bev" in lower_text or "ev" in lower_text:
                engine_type = "BEV"
            elif "phev" in lower_text or "plug-in" in lower_text:
                engine_type = "PHEV"
            elif "hybrid" in lower_text or "hev" in lower_text:
                engine_type = "HEV"

            fuel_type = 0  # benzyna
            if "diesel" in lower_text or "tdi" in lower_text or "bluehdi" in lower_text:
                fuel_type = 1
            elif "lpg" in lower_text:
                fuel_type = 2

            # Variant name: first cell usually
            variant = text_parts[0] if text_parts else model_display

            car = CarModel(
                brand=brand,
                model=model_display,
                variant=variant,
                price_pln=price,
                engine_type=engine_type,
                fuel_type=fuel_type,
                segment=classify_segment(model_display),
                url=url,
                scraped_at=datetime.now().isoformat(),
            )
            self.models.append(car)
            found_any = True

        if not found_any:
            # Fallback: scan full page text for price patterns
            text = soup.get_text()
            price_matches = re.findall(r'od\s+([\d\s\.]+)\s*(?:zł|PLN)', text, re.IGNORECASE)
            for pm in price_matches[:1]:  # just first price
                price = self._parse_price(pm)
                if price:
                    car = CarModel(
                        brand=brand,
                        model=model_display,
                        variant="base",
                        price_pln=price,
                        engine_type="ICE",
                        segment=classify_segment(model_display),
                        url=url,
                        scraped_at=datetime.now().isoformat(),
                    )
                    self.models.append(car)


class DirectImporterScraper(BrandScraper):
    """
    Scraper bezpośrednich stron importerów.
    Każda marka ma inną strukturę → osobne metody.
    """
    brand_name = "direct"

    # Znane struktury API / cenników
    BRAND_CONFIGS = {
        "toyota": {
            "cennik_url": "https://www.toyota.pl/new-cars",
            "api_url": "https://www.toyota.pl/api/v2/vehicles",
        },
        "volkswagen": {
            "cennik_url": "https://www.volkswagen.pl/pl/modele.html",
        },
        "hyundai": {
            "cennik_url": "https://www.hyundai.com/pl/modele.html",
        },
        "kia": {
            "cennik_url": "https://www.kia.com/pl/modele/",
        },
        "skoda": {
            "cennik_url": "https://www.skoda-auto.pl/modele",
        },
        "ford": {
            "cennik_url": "https://www.ford.pl/samochody",
        },
        "bmw": {
            "cennik_url": "https://www.bmw.pl/pl/all-models.html",
        },
        "tesla": {
            "api_url": "https://www.tesla.com/pl_pl/model3",
        },
        "mg": {
            "cennik_url": "https://www.mgmotor.pl/modele",
        },
        "dacia": {
            "cennik_url": "https://www.dacia.pl/gama.html",
        },
        "renault": {
            "cennik_url": "https://www.renault.pl/samochody-osobowe.html",
        },
        "peugeot": {
            "cennik_url": "https://www.peugeot.pl/modele/samochody-osobowe.html",
        },
        "citroen": {
            "cennik_url": "https://www.citroen.pl/modele.html",
        },
        "fiat": {
            "cennik_url": "https://www.fiat.pl/modele",
        },
        "opel": {
            "cennik_url": "https://www.opel.pl/modele.html",
        },
        "mazda": {
            "cennik_url": "https://www.mazda.pl/modele/",
        },
        "nissan": {
            "cennik_url": "https://www.nissan.pl/pojazdy/nowe-samochody.html",
        },
        "honda": {
            "cennik_url": "https://www.honda.pl/cars.html",
        },
        "volvo": {
            "cennik_url": "https://www.volvocars.com/pl/modele/",
        },
        "suzuki": {
            "cennik_url": "https://www.suzuki.pl/samochody",
        },
        "byd": {
            "cennik_url": "https://www.byd.com/pl/car.html",
        },
        "cupra": {
            "cennik_url": "https://www.cupraofficial.pl/modele.html",
        },
    }

    def __init__(self, session, brands: list[str] | None = None):
        super().__init__(session)
        self.target_brands = brands

    def scrape(self) -> list[CarModel]:
        """Try to scrape direct importer sites."""
        brands = self.target_brands or list(self.BRAND_CONFIGS.keys())

        for brand in brands:
            config = self.BRAND_CONFIGS.get(brand.lower())
            if not config:
                continue

            logger.info("Próba bezpośredniego scrapowania: %s", brand)

            # Try API first
            if "api_url" in config:
                try:
                    self._try_api(brand, config["api_url"])
                    continue
                except Exception as e:
                    logger.debug("API %s failed: %s", brand, e)

            # Try HTML cennik
            if "cennik_url" in config:
                try:
                    self._try_html(brand, config["cennik_url"])
                except Exception as e:
                    logger.debug("HTML %s failed: %s", brand, e)

        return self.models

    def _try_api(self, brand: str, api_url: str):
        """Try JSON API endpoint."""
        resp = self._get(api_url, headers={"Accept": "application/json"})
        if resp.headers.get("content-type", "").startswith("application/json"):
            data = resp.json()
            logger.info("API %s returned JSON (%d bytes)", brand, len(resp.text))
            # Parsowanie zależy od struktury API danej marki
            # Na razie logujemy sukces — struktura wymaga dopasowania per-brand

    def _try_html(self, brand: str, url: str):
        """Try HTML scraping of price list page."""
        resp = self._get(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text()

        # Szukaj wzorców cenowych
        price_patterns = [
            r'od\s+([\d\s\.]+)\s*(?:zł|PLN)',
            r'cena\s+(?:od\s+)?([\d\s\.]+)\s*(?:zł|PLN)',
            r'([\d]{2,3}\s?\d{3})\s*(?:zł|PLN)',
        ]

        prices_found = []
        for pattern in price_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                price = self._parse_price(m)
                if price:
                    prices_found.append(price)

        if prices_found:
            logger.info("HTML %s: found %d prices (range %d–%d PLN)",
                        brand, len(prices_found), min(prices_found), max(prices_found))
        else:
            logger.info("HTML %s: no prices found (likely JS-rendered)", brand)


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
