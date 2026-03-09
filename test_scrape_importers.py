"""
Tests for scrape_importers.py — car importer price scraper.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from scrape_importers import (
    CarModel,
    classify_segment,
    import_from_csv,
    to_json,
    to_csv_string,
    to_presets_code,
    print_summary,
)


# ============================================================================
# CarModel tests
# ============================================================================

class TestCarModel:
    def test_ice_preset(self):
        car = CarModel(
            brand="Toyota", model="Corolla", variant="1.8 Hybrid Comfort",
            price_pln=135_000, engine_type="ICE", fuel_type=0,
            fuel_city_l=6.5, fuel_hwy_l=5.0,
        )
        preset = car.to_ice_preset()
        assert preset == {"price": 135_000, "city_l": 6.5, "hwy_l": 5.0, "fuel": 0}

    def test_bev_preset(self):
        car = CarModel(
            brand="Tesla", model="Model 3", variant="RWD",
            price_pln=175_000, engine_type="BEV",
            battery_kwh=60, consumption_city_kwh=13.5, consumption_hwy_kwh=16.0,
        )
        preset = car.to_bev_preset()
        assert preset == {"price": 175_000, "city_kwh": 13.5, "hwy_kwh": 16.0, "bat": 60}

    def test_hyb_preset_hev(self):
        car = CarModel(
            brand="Toyota", model="Corolla", variant="2.0 Hybrid",
            price_pln=145_000, engine_type="HEV", fuel_type=0,
            fuel_city_l=4.3, fuel_hwy_l=5.0,
        )
        preset = car.to_hyb_preset()
        assert preset["hybrid_type"] == "HEV"
        assert preset["price"] == 145_000
        assert preset["city_l"] == 4.3
        assert preset["bat"] == 0

    def test_hyb_preset_phev(self):
        car = CarModel(
            brand="Toyota", model="RAV4", variant="2.5 PHEV AWD",
            price_pln=235_000, engine_type="PHEV", fuel_type=0,
            fuel_city_l=1.0, fuel_hwy_l=6.0,
            battery_kwh=18.1, consumption_city_kwh=14.0,
            consumption_hwy_kwh=17.0, elec_pct=0.65,
        )
        preset = car.to_hyb_preset()
        assert preset["hybrid_type"] == "PHEV"
        assert preset["bat"] == 18.1
        assert preset["elec_pct"] == 0.65

    def test_preset_name_ice(self):
        car = CarModel(
            brand="VW", model="Golf", variant="2.0 TDI Life",
            price_pln=145_000, engine_type="ICE", fuel_type=1,
        )
        name = car.preset_name()
        assert "VW" in name
        assert "Golf" in name
        assert "2.0" in name

    def test_preset_name_bev(self):
        car = CarModel(
            brand="Tesla", model="Model Y", variant="RWD",
            price_pln=189_000, engine_type="BEV",
        )
        name = car.preset_name()
        assert "Tesla" in name
        assert "Model Y" in name

    def test_preset_name_hybrid(self):
        car = CarModel(
            brand="Toyota", model="Corolla", variant="1.8 Hybrid Comfort",
            price_pln=135_000, engine_type="HEV",
        )
        name = car.preset_name()
        assert "Hybrid" in name
        assert "1.8" in name

    def test_preset_name_diesel(self):
        car = CarModel(
            brand="Skoda", model="Octavia", variant="2.0 TDI Ambition",
            price_pln=140_000, engine_type="ICE", fuel_type=1,
        )
        name = car.preset_name()
        assert "TDI" in name

    def test_preset_name_lpg(self):
        car = CarModel(
            brand="Renault", model="Clio", variant="1.0 TCe LPG",
            price_pln=78_000, engine_type="ICE", fuel_type=2,
        )
        name = car.preset_name()
        assert "LPG" in name


# ============================================================================
# Segment classification tests
# ============================================================================

class TestClassifySegment:
    def test_mini(self):
        assert classify_segment("500") == "A – Mini"
        assert classify_segment("Panda") == "A – Mini"
        assert classify_segment("Spring") == "A – Mini"

    def test_male(self):
        assert classify_segment("Yaris") == "B – Małe"
        assert classify_segment("Polo") == "B – Małe"
        assert classify_segment("Clio") == "B – Małe"
        assert classify_segment("Yaris Cross") == "B – Małe"

    def test_kompakt(self):
        assert classify_segment("Corolla") == "C – Kompakt"
        assert classify_segment("Golf") == "C – Kompakt"
        assert classify_segment("Octavia") == "C – Kompakt"
        assert classify_segment("Model 3") == "C – Kompakt"

    def test_sredni(self):
        assert classify_segment("RAV4") == "D – Średni"
        assert classify_segment("Tucson") == "D – Średni"
        assert classify_segment("Model Y") == "D – Średni"
        assert classify_segment("ID.4") == "D – Średni"

    def test_wyzszy(self):
        assert classify_segment("Seria 3") == "E – Wyższy"
        assert classify_segment("Klasa C") == "E – Wyższy"
        assert classify_segment("Taycan") == "E – Wyższy"

    def test_van_maly(self):
        assert classify_segment("Caddy") == "Van – Mały"
        assert classify_segment("Berlingo") == "Van – Mały"
        assert classify_segment("Proace City") == "Van – Mały"
        assert classify_segment("Kangoo") == "Van – Mały"

    def test_van_duzy(self):
        assert classify_segment("Transit") == "Van – Duży"
        assert classify_segment("Transporter") == "Van – Duży"
        assert classify_segment("Proace") == "Van – Duży"
        assert classify_segment("Trafic") == "Van – Duży"

    def test_proace_city_vs_proace(self):
        """Proace City = Van Mały, Proace = Van Duży (dwuwyrazowe ma priorytet)."""
        assert classify_segment("Proace City Verso") == "Van – Mały"
        assert classify_segment("Proace") == "Van – Duży"

    def test_unknown_defaults_to_kompakt(self):
        assert classify_segment("Unknown Model XYZ") == "C – Kompakt"

    def test_case_insensitive(self):
        assert classify_segment("corolla") == "C – Kompakt"
        assert classify_segment("GOLF") == "C – Kompakt"
        assert classify_segment("Model y") == "D – Średni"


# ============================================================================
# CSV import tests
# ============================================================================

class TestCSVImport:
    def test_import_basic_csv(self):
        csv_content = (
            "brand,model,variant,price_pln,engine_type,fuel_type,"
            "fuel_city_l,fuel_hwy_l,battery_kwh,consumption_city_kwh,"
            "consumption_hwy_kwh,elec_pct,segment\n"
            "Toyota,Corolla,1.8 Hybrid,135000,HEV,0,4.5,5.5,0,0,0,0,C – Kompakt\n"
            "Tesla,Model 3,RWD,175000,BEV,0,0,0,60,13.5,16.0,0,C – Kompakt\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(csv_content)
            f.flush()
            path = f.name

        try:
            models = import_from_csv(path)
            assert len(models) == 2
            assert models[0].brand == "Toyota"
            assert models[0].price_pln == 135_000
            assert models[0].engine_type == "HEV"
            assert models[1].brand == "Tesla"
            assert models[1].engine_type == "BEV"
            assert models[1].battery_kwh == 60
        finally:
            os.unlink(path)

    def test_import_minimal_columns(self):
        """Only brand, model, price_pln, engine_type are required."""
        csv_content = (
            "brand,model,price_pln,engine_type\n"
            "VW,Golf,145000,ICE\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(csv_content)
            f.flush()
            path = f.name

        try:
            models = import_from_csv(path)
            assert len(models) == 1
            assert models[0].brand == "VW"
            assert models[0].price_pln == 145_000
            # Missing variant defaults to ""
            assert models[0].variant == ""
            # Segment auto-classified
            assert models[0].segment == "C – Kompakt"
        finally:
            os.unlink(path)

    def test_import_real_csv_file(self):
        """Test importing the bundled sample CSV."""
        csv_path = Path(__file__).parent / "data" / "cennik_importerow_2025.csv"
        if not csv_path.exists():
            pytest.skip("Sample CSV not found")

        models = import_from_csv(str(csv_path))
        assert len(models) > 50, f"Expected 50+ models, got {len(models)}"

        # Check diversity
        brands = set(m.brand for m in models)
        assert len(brands) > 15, f"Expected 15+ brands, got {len(brands)}"

        engine_types = set(m.engine_type for m in models)
        assert "ICE" in engine_types
        assert "BEV" in engine_types
        assert "HEV" in engine_types

        segments = set(m.segment for m in models)
        assert "Van – Mały" in segments
        assert "Van – Duży" in segments

        # Price sanity
        for m in models:
            assert 20_000 < m.price_pln < 1_000_000, f"Unrealistic price: {m.brand} {m.model} = {m.price_pln}"


# ============================================================================
# Output formatter tests
# ============================================================================

class TestOutputFormatters:
    @pytest.fixture
    def sample_models(self):
        return [
            CarModel(
                brand="Toyota", model="Corolla", variant="1.8 Hybrid",
                price_pln=135_000, engine_type="HEV",
                fuel_city_l=4.5, fuel_hwy_l=5.5,
                segment="C – Kompakt",
            ),
            CarModel(
                brand="Tesla", model="Model 3", variant="RWD",
                price_pln=175_000, engine_type="BEV",
                battery_kwh=60, consumption_city_kwh=13.5,
                consumption_hwy_kwh=16.0,
                segment="C – Kompakt",
            ),
            CarModel(
                brand="VW", model="Golf", variant="2.0 TDI",
                price_pln=145_000, engine_type="ICE", fuel_type=1,
                fuel_city_l=6.5, fuel_hwy_l=5.0,
                segment="C – Kompakt",
            ),
        ]

    def test_to_json(self, sample_models):
        output = to_json(sample_models)
        data = json.loads(output)
        assert len(data) == 3
        assert data[0]["brand"] == "Toyota"
        assert data[1]["engine_type"] == "BEV"
        assert data[2]["price_pln"] == 145_000

    def test_to_csv(self, sample_models):
        output = to_csv_string(sample_models)
        lines = output.strip().split("\n")
        assert len(lines) == 4  # header + 3 rows
        assert "brand" in lines[0]
        assert "Toyota" in lines[1]

    def test_to_presets_code(self, sample_models):
        code = to_presets_code(sample_models)
        assert "ICE_PRESETS_NEW" in code
        assert "BEV_PRESETS_NEW" in code
        assert "HYB_PRESETS_NEW" in code
        assert "C – Kompakt" in code
        assert "135000" in code or "135_000" in code

    def test_to_presets_valid_python(self, sample_models):
        """Generated preset code should be valid Python."""
        code = to_presets_code(sample_models)
        # Should not raise SyntaxError
        compile(code, "<presets>", "exec")

    def test_empty_models(self):
        assert to_json([]) == "[]"
        assert to_csv_string([]) == ""


# ============================================================================
# Price parser tests
# ============================================================================

class TestPriceParser:
    """Test the _parse_price method via a scraper instance."""

    @pytest.fixture
    def parser(self):
        from scrape_importers import BrandScraper
        import requests
        # Create a minimal instance for testing the parser
        class TestScraper(BrandScraper):
            def scrape(self):
                return []
        return TestScraper(requests.Session())

    def test_simple_number(self, parser):
        assert parser._parse_price("135000") == 135_000

    def test_with_spaces(self, parser):
        assert parser._parse_price("135 900 PLN") == 135_900

    def test_with_zl(self, parser):
        assert parser._parse_price("135 900 zł") == 135_900

    def test_with_dot_separator(self, parser):
        assert parser._parse_price("135.900") == 135_900

    def test_with_comma_separator(self, parser):
        assert parser._parse_price("135,900") == 135_900

    def test_too_low_returns_none(self, parser):
        assert parser._parse_price("5000") is None

    def test_too_high_returns_none(self, parser):
        assert parser._parse_price("5000000") is None

    def test_empty_returns_none(self, parser):
        assert parser._parse_price("") is None
        assert parser._parse_price(None) is None

    def test_garbage_returns_none(self, parser):
        assert parser._parse_price("abc") is None


# ============================================================================
# Consumption parser tests
# ============================================================================

class TestConsumptionParser:
    @pytest.fixture
    def parser(self):
        from scrape_importers import BrandScraper
        import requests
        class TestScraper(BrandScraper):
            def scrape(self):
                return []
        return TestScraper(requests.Session())

    def test_comma_format(self, parser):
        assert parser._parse_consumption("5,5 l/100km") == 5.5

    def test_dot_format(self, parser):
        assert parser._parse_consumption("5.5 l/100km") == 5.5

    def test_kwh_format(self, parser):
        assert parser._parse_consumption("16.0 kWh/100km") == 16.0

    def test_empty(self, parser):
        assert parser._parse_consumption("") is None
        assert parser._parse_consumption(None) is None
