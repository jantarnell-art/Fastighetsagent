import csv
import io
import json
import os
import re
from datetime import date

import pandas as pd
import streamlit as st

from database import Base, SessionLocal, engine
from models import Transaction

Base.metadata.create_all(bind=engine)

PROPERTY_TYPES = [
    "Handel",
    "Kontor",
    "Bostäder",
    "Industri/lager/logistik",
    "Samhällsfastigheter",
    "Hotell",
    "Mark/exploatering",
    "Blandfastigheter",
    "Övrigt",
]

TYPE_EMOJI = {
    "Handel": "🛍️", "Kontor": "🏢", "Bostäder": "🏠",
    "Industri/lager/logistik": "🏭", "Samhällsfastigheter": "🏥",
    "Hotell": "🏨", "Mark/exploatering": "🌱",
    "Blandfastigheter": "🏗️", "Övrigt": "📦",
}

SAMPLE_JSON = json.dumps([{
    "buyer": "Castellum AB",
    "seller": "Privat Fastighets AB",
    "price_sek": 285000000,
    "price_text": "285 MSEK",
    "property_type": "Kontor",
    "property_designation": "Stockholm Centrum 1:5",
    "address": "Kungsgatan 10",
    "municipality": "Stockholm",
    "county": "Stockholms län",
    "transaction_date": "2025-03-15",
    "area_sqm": 12500,
    "tenants": "Deloitte (60%), SEB (40%)",
    "yield_percent": 4.8,
    "portfolio_flag": False,
    "confidence_score": 0.9,
    "source_name": "Fastighetsnytt",
    "raw_text": "Castellum förvärvar kontorsfastighet i centrala Stockholm med långa hyreskontrakt.",
}], indent=2, ensure_ascii=False)

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Fastighetsaffärsagent",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stSidebar"] { background: #0d2137; }
[data-testid="stSidebar"] .stRadio label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] small,
[data-testid="stSidebar"] span { color: rgba(255,255,255,0.85) !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color: #fff !important; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.15); }
</style>
""", unsafe_allow_html=True)

# ── Session state ──────────────────────────────────────────────────────────────

for k, v in {
    "selected_id": None,
    "edit_id": None,
    "confirm_delete": False,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── DB helpers ─────────────────────────────────────────────────────────────────

def to_dict(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def load_transactions(filters=None):
    db = SessionLocal()
    try:
        q = db.query(Transaction)
        if filters:
            if filters.get("buyer"):
                q = q.filter(Transaction.buyer.ilike(f"%{filters['buyer']}%"))
            if filters.get("seller"):
                q = q.filter(Transaction.seller.ilike(f"%{filters['seller']}%"))
            if filters.get("property_type"):
                q = q.filter(Transaction.property_type == filters["property_type"])
            if filters.get("municipality"):
                q = q.filter(Transaction.municipality.ilike(f"%{filters['municipality']}%"))
            if filters.get("date_from"):
                q = q.filter(Transaction.transaction_date >= filters["date_from"])
            if filters.get("date_to"):
                q = q.filter(Transaction.transaction_date <= filters["date_to"])
            if filters.get("price_min") is not None:
                q = q.filter(Transaction.price_sek >= filters["price_min"])
            if filters.get("price_max") is not None:
                q = q.filter(Transaction.price_sek <= filters["price_max"])
        rows = q.order_by(
            Transaction.transaction_date.desc().nullslast(),
            Transaction.created_at.desc(),
        ).all()
        return [to_dict(r) for r in rows]
    finally:
        db.close()


def get_transaction(tx_id):
    db = SessionLocal()
    try:
        obj = db.query(Transaction).filter(Transaction.id == tx_id).first()
        return to_dict(obj) if obj else None
    finally:
        db.close()


def save_transaction(data, tx_id=None):
    db = SessionLocal()
    try:
        if tx_id:
            obj = db.query(Transaction).filter(Transaction.id == tx_id).first()
            for k, v in data.items():
                setattr(obj, k, v)
        else:
            obj = Transaction(**data)
            db.add(obj)
        db.commit()
        return obj.id
    finally:
        db.close()


def delete_tx(tx_id):
    db = SessionLocal()
    try:
        obj = db.query(Transaction).filter(Transaction.id == tx_id).first()
        if obj:
            db.delete(obj)
            db.commit()
    finally:
        db.close()


def set_ai_fields(tx_id, summary, market_comment):
    db = SessionLocal()
    try:
        obj = db.query(Transaction).filter(Transaction.id == tx_id).first()
        if obj:
            obj.summary = summary
            obj.market_comment = market_comment
            db.commit()
    finally:
        db.close()

# ── Formatting ─────────────────────────────────────────────────────────────────

def fmt_price(sek, text):
    if text:
        return text
    if not sek:
        return "–"
    if sek >= 1e9:
        v = sek / 1e9
        return f"{v:.2f} mdSEK".rstrip("0").rstrip(".") + " mdSEK" if False else f"{v:.1f} mdSEK"
    if sek >= 1e6:
        return f"{int(sek / 1e6)} MSEK"
    return f"{int(sek):,} SEK".replace(",", " ")


def fmt_area(sqm, units):
    parts = []
    if sqm:
        parts.append(f"{int(sqm):,} kvm".replace(",", " "))
    if units:
        parts.append(f"{units} lgh")
    return " / ".join(parts) or "–"


def safe_float(s):
    try:
        return float(str(s).strip().replace(",", ".").replace(" ", "")) if s and str(s).strip() else None
    except ValueError:
        return None


def safe_int(s):
    try:
        return int(str(s).strip()) if s and str(s).strip() else None
    except ValueError:
        return None


def to_dataframe(txs):
    if not txs:
        return pd.DataFrame()
    rows = [{
        "ID": t["id"],
        "Datum": str(t["transaction_date"] or ""),
        "Köpare": t["buyer"] or "",
        "Säljare": t["seller"] or "",
        "Pris": fmt_price(t.get("price_sek"), t.get("price_text")),
        "Typ": f"{TYPE_EMOJI.get(t['property_type'], '')} {t['property_type']}",
        "Kommun": t.get("municipality") or "",
        "Area / Enheter": fmt_area(t.get("area_sqm"), t.get("residential_units")),
        "Yield %": f"{t['yield_percent']:.2f}" if t.get("yield_percent") else "",
        "AI": "✓" if t.get("summary") else "",
    } for t in txs]
    return pd.DataFrame(rows)


def to_csv_bytes(txs):
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf, delimiter=";")
    w.writerow([
        "ID", "Köpare", "Säljare", "Pris (SEK)", "Pris (text)", "Fastighetstyp",
        "Fastighetsbeteckning", "Adress", "Kommun", "Län", "Affärsdatum",
        "Tillträdesdatum", "Källnamn", "Käll-URL", "Sammanfattning",
        "Marknadskommentar", "Area (kvm)", "Antal lägenheter", "Hyresgäster",
        "Direktavkastning (%)", "Portfölj", "Tillförlitlighet", "Skapad",
    ])
    for t in txs:
        w.writerow([
            t["id"], t["buyer"], t["seller"], t.get("price_sek"), t.get("price_text"),
            t["property_type"], t.get("property_designation"), t.get("address"),
            t.get("municipality"), t.get("county"), t.get("transaction_date"),
            t.get("access_date"), t.get("source_name"), t.get("source_url"),
            t.get("summary"), t.get("market_comment"), t.get("area_sqm"),
            t.get("residential_units"), t.get("tenants"), t.get("yield_percent"),
            "Ja" if t.get("portfolio_flag") else "Nej",
            t.get("confidence_score"), t.get("created_at"),
        ])
    return buf.getvalue().encode("utf-8")

# ── AI ─────────────────────────────────────────────────────────────────────────

def generate_summary(t):
    api_key = os.environ.get("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        st.error("ANTHROPIC_API_KEY saknas. Lägg till den i Streamlit Secrets eller som miljövariabel.")
        return None
    try:
        import anthropic
    except ImportError:
        st.error("anthropic-paketet saknas (pip install anthropic).")
        return None

    client = anthropic.Anthropic(api_key=api_key)
    price_str = t.get("price_text") or (
        "{:,.0f} SEK".format(t["price_sek"]).replace(",", " ") if t.get("price_sek") else "Okänt"
    )
    yield_str = "{:.2f}%".format(t["yield_percent"]) if t.get("yield_percent") else "–"
    info = "\n".join([
        "Köpare: {}, Säljare: {}".format(t["buyer"], t["seller"]),
        "Pris: {}".format(price_str),
        "Typ: {}, Beteckning: {}".format(t["property_type"], t.get("property_designation") or "–"),
        "Adress: {}, Kommun: {}, Län: {}".format(
            t.get("address") or "–", t.get("municipality") or "–", t.get("county") or "–"
        ),
        "Datum: {}".format(t.get("transaction_date") or "–"),
        "Area: {}".format(fmt_area(t.get("area_sqm"), t.get("residential_units"))),
        "Hyresgäster: {}".format(t.get("tenants") or "–"),
        "Yield: {}".format(yield_str),
        "Portfölj: {}".format("Ja" if t.get("portfolio_flag") else "Nej"),
        "Råtext: {}".format(t.get("raw_text") or ""),
    ])
    msg = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": (
                "Du är expert på kommersiella fastighetsaffärer i Sverige. "
                "Analysera affären nedan och returnera ENBART JSON med:\n"
                '"summary": faktabaserad sammanfattning på svenska, 2-3 meningar\n'
                '"market_comment": analytisk marknads- och värderingskommentar på svenska, 2-3 meningar\n\n'
                f"{info}\n\nBara JSON, inga kodblock, inga förklaringstexter."
            ),
        }],
    )
    text = msg.content[0].text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group()) if m else None

# ── Form ───────────────────────────────────────────────────────────────────────

def render_form(t=None):
    is_edit = t is not None

    def val(key, default=""):
        v = t.get(key) if t else None
        return v if v is not None else default

    with st.form("tx_form", clear_on_submit=(not is_edit)):
        st.markdown("#### Parter & Pris")
        c1, c2 = st.columns(2)
        buyer = c1.text_input("Köpare *", value=val("buyer"))
        seller = c2.text_input("Säljare *", value=val("seller"))

        c1, c2, c3 = st.columns(3)
        price_sek_str = c1.text_input("Pris (SEK)", value=str(val("price_sek", "")) if val("price_sek") else "")
        price_text = c2.text_input("Pris (text)", value=val("price_text"))
        type_idx = PROPERTY_TYPES.index(t["property_type"]) if is_edit and t.get("property_type") in PROPERTY_TYPES else 0
        prop_type = c3.selectbox("Fastighetstyp *", PROPERTY_TYPES, index=type_idx)

        st.markdown("#### Fastighet & Plats")
        c1, c2 = st.columns(2)
        designation = c1.text_input("Fastighetsbeteckning", value=val("property_designation"))
        address = c2.text_input("Adress", value=val("address"))
        c1, c2, c3 = st.columns(3)
        municipality = c1.text_input("Kommun", value=val("municipality"))
        county = c2.text_input("Län", value=val("county"))
        portfolio = c3.checkbox("Portföljaffär", value=bool(val("portfolio_flag", False)))

        st.markdown("#### Datum & Detaljer")
        c1, c2, c3, c4 = st.columns(4)
        tx_date_val = val("transaction_date")
        acc_date_val = val("access_date")
        tx_date = c1.date_input("Affärsdatum", value=tx_date_val if isinstance(tx_date_val, date) else None)
        acc_date = c2.date_input("Tillträdesdatum", value=acc_date_val if isinstance(acc_date_val, date) else None)
        area_str = c3.text_input("Area (kvm)", value=str(val("area_sqm", "")) if val("area_sqm") else "")
        units_str = c4.text_input("Antal lägenheter", value=str(val("residential_units", "")) if val("residential_units") else "")

        c1, c2 = st.columns(2)
        yield_str = c1.text_input("Direktavkastning / Yield (%)", value=str(val("yield_percent", "")) if val("yield_percent") else "")
        conf_str = c2.text_input("Tillförlitlighet (0–1)", value=str(val("confidence_score", "")) if val("confidence_score") else "")
        tenants = st.text_input("Hyresgäster", value=val("tenants"))

        st.markdown("#### Källa & Råtext")
        c1, c2 = st.columns(2)
        source_name = c1.text_input("Källnamn", value=val("source_name"))
        source_url = c2.text_input("Källlänk (URL)", value=val("source_url"))
        raw_text = st.text_area("Råtext (artikeltext, presskommuniké etc.)", value=val("raw_text"), height=120)

        submitted = st.form_submit_button("💾 Spara affär", type="primary", use_container_width=True)

    if submitted:
        if not buyer.strip() or not seller.strip():
            st.error("Köpare och säljare är obligatoriska.")
            return
        data = {
            "buyer": buyer.strip(),
            "seller": seller.strip(),
            "price_sek": safe_float(price_sek_str),
            "price_text": price_text.strip() or None,
            "property_type": prop_type,
            "property_designation": designation.strip() or None,
            "address": address.strip() or None,
            "municipality": municipality.strip() or None,
            "county": county.strip() or None,
            "transaction_date": tx_date if isinstance(tx_date, date) else None,
            "access_date": acc_date if isinstance(acc_date, date) else None,
            "source_name": source_name.strip() or None,
            "source_url": source_url.strip() or None,
            "area_sqm": safe_float(area_str),
            "residential_units": safe_int(units_str),
            "tenants": tenants.strip() or None,
            "yield_percent": safe_float(yield_str),
            "portfolio_flag": portfolio,
            "confidence_score": safe_float(conf_str),
            "raw_text": raw_text.strip() or None,
        }
        save_transaction(data, st.session_state.edit_id)
        st.session_state.edit_id = None
        st.session_state.selected_id = None
        st.success("✅ Affären sparades!")
        st.rerun()

# ── Detail view ────────────────────────────────────────────────────────────────

def render_detail(t):
    st.markdown("---")
    badge = f"{TYPE_EMOJI.get(t['property_type'], '')} {t['property_type']}"
    st.subheader(f"{t['buyer']}  ←  {t['seller']}")

    m1, m2, m3 = st.columns(3)
    m1.metric("Pris", fmt_price(t.get("price_sek"), t.get("price_text")))
    m2.metric("Typ", badge)
    m3.metric("Yield", f"{t['yield_percent']:.2f}%" if t.get("yield_percent") else "–")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Fastighet & Plats**")
        items = [
            ("Beteckning", t.get("property_designation")),
            ("Adress", t.get("address")),
            ("Kommun", t.get("municipality")),
            ("Län", t.get("county")),
            ("Portfölj", "✅ Ja" if t.get("portfolio_flag") else "Nej"),
        ]
        for label, v in items:
            st.write(f"**{label}:** {v or '–'}")
    with c2:
        st.markdown("**Datum & Detaljer**")
        url = t.get("source_url")
        name = t.get("source_name") or url
        source_str = f"[{name}]({url})" if url else (name or "–")
        items = [
            ("Affärsdatum", t.get("transaction_date")),
            ("Tillträdesdatum", t.get("access_date")),
            ("Area / Enheter", fmt_area(t.get("area_sqm"), t.get("residential_units"))),
            ("Hyresgäster", t.get("tenants")),
            ("Tillförlitlighet", f"{int(t['confidence_score']*100)}%" if t.get("confidence_score") else None),
        ]
        for label, v in items:
            st.write(f"**{label}:** {v or '–'}")
        st.markdown(f"**Källa:** {source_str}")

    if t.get("raw_text"):
        with st.expander("📝 Råtext"):
            st.text(t["raw_text"])

    st.markdown("---")
    st.markdown("#### 🤖 AI-analys")
    if t.get("summary") or t.get("market_comment"):
        ac1, ac2 = st.columns(2)
        ac1.markdown("**Sammanfattning**")
        ac1.info(t.get("summary") or "–")
        ac2.markdown("**Marknadskommentar**")
        ac2.info(t.get("market_comment") or "–")
    else:
        st.caption("Ingen AI-analys genererad ännu.")

    if st.button("✨ Generera AI-analys", key=f"ai_{t['id']}"):
        with st.spinner("Analyserar med Claude…"):
            result = generate_summary(t)
        if result:
            set_ai_fields(t["id"], result.get("summary", ""), result.get("market_comment", ""))
            st.success("AI-analys sparad!")
            st.rerun()

    st.markdown("---")
    _, ec, dc = st.columns([4, 1, 1])
    if ec.button("✏️ Redigera", key=f"edit_{t['id']}", use_container_width=True):
        st.session_state.edit_id = t["id"]
        st.rerun()
    if dc.button("🗑️ Radera", key=f"del_{t['id']}", type="secondary", use_container_width=True):
        st.session_state.confirm_delete = True
        st.rerun()

    if st.session_state.confirm_delete:
        st.warning(f"⚠️ Bekräfta radering av **{t['buyer']} ← {t['seller']}**")
        yc, nc = st.columns(2)
        if yc.button("Ja, radera permanent", type="primary", key="yes_del"):
            delete_tx(t["id"])
            st.session_state.selected_id = None
            st.session_state.confirm_delete = False
            st.rerun()
        if nc.button("Avbryt", key="no_del"):
            st.session_state.confirm_delete = False
            st.rerun()

# ── Import ─────────────────────────────────────────────────────────────────────

def render_import():
    st.subheader("📥 Importera affärer via JSON")
    st.caption("Klistra in en JSON-array. Obligatoriska fält: `buyer`, `seller`, `property_type`.")

    if st.button("📋 Visa exempelformat"):
        st.code(SAMPLE_JSON, language="json")

    json_input = st.text_area("JSON-data", height=300,
                              placeholder='[{"buyer": "...", "seller": "...", "property_type": "Kontor", ...}]')

    if st.button("📥 Importera", type="primary"):
        if not json_input.strip():
            st.error("Ange JSON-data.")
            return
        try:
            data = json.loads(json_input)
            if not isinstance(data, list):
                data = [data]
        except json.JSONDecodeError as e:
            st.error(f"Ogiltig JSON: {e}")
            return

        valid_fields = {c.name for c in Transaction.__table__.columns} - {"id", "created_at", "updated_at"}
        count, errors = 0, []
        for i, item in enumerate(data, 1):
            if not item.get("buyer") or not item.get("seller") or not item.get("property_type"):
                errors.append(f"Post {i}: saknar buyer, seller eller property_type")
                continue
            for df in ("transaction_date", "access_date"):
                if item.get(df) and isinstance(item[df], str):
                    try:
                        item[df] = date.fromisoformat(item[df])
                    except ValueError:
                        item[df] = None
            clean = {k: v for k, v in item.items() if k in valid_fields}
            save_transaction(clean)
            count += 1

        if count:
            st.success(f"✅ {count} affär{'er' if count != 1 else ''} importerades!")
        for e in errors:
            st.warning(e)
        if count:
            st.rerun()

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    with st.sidebar:
        st.markdown("## 🏢 Fastighets­affärs­agent")
        st.markdown("---")
        nav = st.radio(
            "Meny",
            ["📋 Affärer", "➕ Lägg till", "📥 Importera"],
            label_visibility="collapsed",
        )
        st.markdown("---")
        st.caption("Steg 1 · POC")

    # ── Affärer ──────────────────────────────────────────────────────────────────
    if nav == "📋 Affärer":
        st.title("📋 Fastighetsaffärer")

        if st.session_state.edit_id:
            t = get_transaction(st.session_state.edit_id)
            if t:
                render_form(t)
            if st.button("← Avbryt"):
                st.session_state.edit_id = None
                st.rerun()
            return

        with st.expander("🔍 Filter", expanded=False):
            fc1, fc2, fc3, fc4 = st.columns(4)
            f_buyer = fc1.text_input("Köpare", key="f_buyer")
            f_seller = fc2.text_input("Säljare", key="f_seller")
            f_type = fc3.selectbox("Typ", [""] + PROPERTY_TYPES, key="f_type")
            f_muni = fc4.text_input("Kommun", key="f_muni")

            fc1, fc2, fc3, fc4 = st.columns(4)
            f_date_from = fc1.date_input("Datum från", value=None, key="f_date_from")
            f_date_to = fc2.date_input("Datum till", value=None, key="f_date_to")
            f_price_min = fc3.text_input("Pris min (SEK)", key="f_price_min")
            f_price_max = fc4.text_input("Pris max (SEK)", key="f_price_max")

            if st.button("🗑️ Rensa filter"):
                for k in ["f_buyer", "f_seller", "f_type", "f_muni",
                           "f_date_from", "f_date_to", "f_price_min", "f_price_max"]:
                    st.session_state.pop(k, None)
                st.rerun()

        filters = {
            "buyer": f_buyer or None,
            "seller": f_seller or None,
            "property_type": f_type or None,
            "municipality": f_muni or None,
            "date_from": f_date_from,
            "date_to": f_date_to,
            "price_min": safe_float(f_price_min),
            "price_max": safe_float(f_price_max),
        }

        txs = load_transactions(filters)
        df = to_dataframe(txs)

        tc1, tc2 = st.columns([5, 1])
        tc1.caption(f"**{len(txs)}** affär{'er' if len(txs) != 1 else ''} visas")
        if txs:
            tc2.download_button(
                "📊 Exportera CSV",
                data=to_csv_bytes(txs),
                file_name="fastighetsaffarer.csv",
                mime="text/csv",
                use_container_width=True,
            )

        if not txs:
            st.info("Inga affärer hittades. Lägg till via '➕ Lägg till' i menyn.")
        else:
            event = st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                selection_mode="single-row",
                on_select="rerun",
                column_config={
                    "ID": st.column_config.NumberColumn(width="small"),
                    "Datum": st.column_config.TextColumn(width="small"),
                    "Pris": st.column_config.TextColumn(width="medium"),
                    "Yield %": st.column_config.TextColumn(width="small"),
                    "AI": st.column_config.TextColumn(width="small"),
                },
            )
            sel = event.selection.rows if hasattr(event, "selection") else []
            if sel and sel[0] < len(txs):
                st.session_state.selected_id = txs[sel[0]]["id"]

        if st.session_state.selected_id:
            t = get_transaction(st.session_state.selected_id)
            if t:
                render_detail(t)

    # ── Lägg till ────────────────────────────────────────────────────────────────
    elif nav == "➕ Lägg till":
        st.title("➕ Lägg till ny affär")
        render_form()

    # ── Importera ────────────────────────────────────────────────────────────────
    elif nav == "📥 Importera":
        st.title("📥 Importera via JSON")
        render_import()


main()
