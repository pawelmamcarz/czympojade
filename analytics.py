"""Analytics — logowanie anonimowych wizyt i panel admina.

Dane zbierane (bez danych osobowych):
- timestamp
- kraj (z IP, geo)
- dane z kreatora (paliwo, segment, km, miasto SCT, verdict)
- wersja aplikacji

Storage: Supabase (primary) → SQLite (fallback).
"""
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).parent / "data"
DB_PATH = DB_DIR / "czympojade.db"

_ANALYTICS_SCHEMA = """
CREATE TABLE IF NOT EXISTS visitor_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    ip          TEXT,
    country     TEXT,
    app_version TEXT,
    profile     TEXT,
    fuel        TEXT,
    segment     TEXT,
    monthly_km  INTEGER,
    has_car     INTEGER,
    car_age     INTEGER,
    sct_city    TEXT,
    work_charger TEXT,
    has_garage  INTEGER,
    has_pv      INTEGER,
    verdict     TEXT,
    savings     REAL,
    extras      TEXT
);
CREATE INDEX IF NOT EXISTS idx_vl_ts ON visitor_logs(ts);
"""


def _get_supabase():
    """Get Supabase client (singleton from market_data)."""
    try:
        from market_data import _get_sb_client
        return _get_sb_client()
    except Exception:
        return None


def _ensure_sqlite():
    """Ensure SQLite analytics table exists."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(_ANALYTICS_SCHEMA)
    conn.commit()
    return conn


def _get_client_ip():
    """Get client IP from Streamlit headers (best effort)."""
    try:
        headers = st.context.headers
        # X-Forwarded-For from reverse proxy
        xff = headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()
        return headers.get("X-Real-Ip", headers.get("Host", "unknown"))
    except Exception:
        return "unknown"


def log_visit(wdata: dict, results: dict, app_version: str):
    """Log a wizard completion event (anonymous, no personal data)."""
    ts = datetime.now(timezone.utc).isoformat()
    ip = _get_client_ip()

    row = {
        "ts": ts,
        "ip": ip,
        "country": "PL",  # TODO: geo lookup
        "app_version": app_version,
        "profile": wdata.get("profile_id", ""),
        "fuel": wdata.get("current_fuel", ""),
        "segment": wdata.get("current_segment_label", ""),
        "monthly_km": wdata.get("monthly_km", 0),
        "has_car": 1 if wdata.get("has_car") else 0,
        "car_age": wdata.get("car_age", 0),
        "sct_city": wdata.get("sct_city", ""),
        "work_charger": wdata.get("work_charger", ""),
        "has_garage": 1 if wdata.get("has_garage") else 0,
        "has_pv": 1 if wdata.get("has_pv") else 0,
        "verdict": results.get("verdict", ""),
        "savings": results.get("savings_total", 0),
        "extras": json.dumps({
            "driving_style": wdata.get("driving_style", ""),
            "pv_choice": wdata.get("pv_choice", ""),
            "car_value": wdata.get("car_value", 0),
        }, ensure_ascii=False),
    }

    # Try Supabase first
    sb = _get_supabase()
    if sb:
        try:
            sb.table("visitor_logs").insert(row).execute()
            logger.info("Analytics: logged to Supabase")
            return
        except Exception as e:
            logger.warning(f"Analytics Supabase error: {e}")

    # Fallback to SQLite
    try:
        conn = _ensure_sqlite()
        cols = list(row.keys())
        placeholders = ", ".join(["?"] * len(cols))
        conn.execute(
            f"INSERT INTO visitor_logs ({', '.join(cols)}) VALUES ({placeholders})",
            [row[c] for c in cols],
        )
        conn.commit()
        conn.close()
        logger.info("Analytics: logged to SQLite")
    except Exception as e:
        logger.warning(f"Analytics SQLite error: {e}")


def get_recent_visits(limit=100):
    """Get recent visitor logs for admin panel."""
    # Try Supabase
    sb = _get_supabase()
    if sb:
        try:
            resp = sb.table("visitor_logs").select("*").order(
                "ts", desc=True
            ).limit(limit).execute()
            return resp.data
        except Exception as e:
            logger.warning(f"Analytics read Supabase error: {e}")

    # Fallback SQLite
    try:
        conn = _ensure_sqlite()
        cur = conn.execute(
            f"SELECT * FROM visitor_logs ORDER BY ts DESC LIMIT {limit}"
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def get_visit_stats():
    """Aggregate stats for admin panel."""
    visits = get_recent_visits(1000)
    if not visits:
        return {}

    total = len(visits)
    verdicts = {}
    fuels = {}
    cities = {}
    for v in visits:
        vd = v.get("verdict", "")
        verdicts[vd] = verdicts.get(vd, 0) + 1
        fl = v.get("fuel", "")
        if fl:
            fuels[fl] = fuels.get(fl, 0) + 1
        sc = v.get("sct_city", "")
        if sc and sc != "Nie dotyczy":
            cities[sc] = cities.get(sc, 0) + 1

    return {
        "total": total,
        "verdicts": verdicts,
        "fuels": fuels,
        "sct_cities": cities,
        "has_car_pct": sum(1 for v in visits if v.get("has_car")) / max(total, 1) * 100,
        "avg_km": sum(v.get("monthly_km", 0) for v in visits) / max(total, 1),
    }


def render_admin_panel():
    """Render admin analytics panel (password-protected)."""
    st.markdown("---")
    with st.expander("🔒 Panel admina", expanded=False):
        pwd = st.text_input("Hasło", type="password", key="admin_pwd")
        if not pwd:
            return
        # Simple password check from secrets or env
        import os
        admin_pwd = os.environ.get("ADMIN_PASSWORD", "")
        try:
            admin_pwd = admin_pwd or st.secrets.get("admin", {}).get("password", "")
        except Exception:
            pass
        if not admin_pwd or pwd != admin_pwd:
            if pwd:
                st.error("Nieprawidłowe hasło")
            return

        st.success("Zalogowano jako admin")

        stats = get_visit_stats()
        if not stats:
            st.info("Brak danych analytics")
            return

        # Summary metrics
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Wizyty (last 1000)", stats["total"])
        with c2:
            st.metric("Śr. km/mies.", f'{stats["avg_km"]:.0f}')
        with c3:
            st.metric("Ma auto", f'{stats["has_car_pct"]:.0f}%')
        with c4:
            sct_total = sum(stats.get("sct_cities", {}).values())
            st.metric("W SCT", sct_total)

        # Verdict distribution
        import pandas as pd
        if stats.get("verdicts"):
            st.subheader("Werdykty")
            df_v = pd.DataFrame(
                list(stats["verdicts"].items()),
                columns=["Werdykt", "Liczba"]
            ).sort_values("Liczba", ascending=False)
            st.dataframe(df_v, hide_index=True)

        if stats.get("fuels"):
            st.subheader("Paliwa")
            df_f = pd.DataFrame(
                list(stats["fuels"].items()),
                columns=["Paliwo", "Liczba"]
            ).sort_values("Liczba", ascending=False)
            st.dataframe(df_f, hide_index=True)

        # Recent visits table
        st.subheader("Ostatnie wizyty")
        visits = get_recent_visits(50)
        if visits:
            df = pd.DataFrame(visits)
            # Select relevant columns
            show_cols = [c for c in ["ts", "ip", "fuel", "segment", "monthly_km",
                                      "sct_city", "work_charger", "verdict", "savings",
                                      "app_version"] if c in df.columns]
            st.dataframe(df[show_cols], hide_index=True, use_container_width=True)
