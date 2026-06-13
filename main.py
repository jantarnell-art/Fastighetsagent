import csv
import io
import json
import os
import re
from datetime import date
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

import models
import schemas
from database import engine, get_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Fastighetsaffärsagent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.get("/", response_class=FileResponse)
def root():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))


def _apply_filters(q, municipality, property_type, buyer, seller, date_from, date_to, price_min, price_max):
    if municipality:
        q = q.filter(models.Transaction.municipality.ilike(f"%{municipality}%"))
    if property_type:
        q = q.filter(models.Transaction.property_type == property_type)
    if buyer:
        q = q.filter(models.Transaction.buyer.ilike(f"%{buyer}%"))
    if seller:
        q = q.filter(models.Transaction.seller.ilike(f"%{seller}%"))
    if date_from:
        q = q.filter(models.Transaction.transaction_date >= date_from)
    if date_to:
        q = q.filter(models.Transaction.transaction_date <= date_to)
    if price_min is not None:
        q = q.filter(models.Transaction.price_sek >= price_min)
    if price_max is not None:
        q = q.filter(models.Transaction.price_sek <= price_max)
    return q


@app.get("/api/transactions", response_model=List[schemas.Transaction])
def list_transactions(
    municipality: Optional[str] = None,
    property_type: Optional[str] = None,
    buyer: Optional[str] = None,
    seller: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Transaction)
    q = _apply_filters(q, municipality, property_type, buyer, seller, date_from, date_to, price_min, price_max)
    return q.order_by(
        models.Transaction.transaction_date.desc().nullslast(),
        models.Transaction.created_at.desc(),
    ).all()


@app.post("/api/transactions", response_model=schemas.Transaction, status_code=201)
def create_transaction(tx: schemas.TransactionCreate, db: Session = Depends(get_db)):
    obj = models.Transaction(**tx.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@app.post("/api/transactions/import", response_model=List[schemas.Transaction], status_code=201)
def import_transactions(txs: List[schemas.TransactionCreate], db: Session = Depends(get_db)):
    objs = [models.Transaction(**t.model_dump()) for t in txs]
    db.add_all(objs)
    db.commit()
    for o in objs:
        db.refresh(o)
    return objs


@app.get("/api/transactions/{tx_id}", response_model=schemas.Transaction)
def get_transaction(tx_id: int, db: Session = Depends(get_db)):
    obj = db.query(models.Transaction).filter(models.Transaction.id == tx_id).first()
    if not obj:
        raise HTTPException(404, "Affär hittades inte")
    return obj


@app.put("/api/transactions/{tx_id}", response_model=schemas.Transaction)
def update_transaction(tx_id: int, tx: schemas.TransactionCreate, db: Session = Depends(get_db)):
    obj = db.query(models.Transaction).filter(models.Transaction.id == tx_id).first()
    if not obj:
        raise HTTPException(404, "Affär hittades inte")
    for k, v in tx.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@app.delete("/api/transactions/{tx_id}", status_code=204)
def delete_transaction(tx_id: int, db: Session = Depends(get_db)):
    obj = db.query(models.Transaction).filter(models.Transaction.id == tx_id).first()
    if not obj:
        raise HTTPException(404, "Affär hittades inte")
    db.delete(obj)
    db.commit()


@app.get("/api/export/csv")
def export_csv(
    municipality: Optional[str] = None,
    property_type: Optional[str] = None,
    buyer: Optional[str] = None,
    seller: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Transaction)
    q = _apply_filters(q, municipality, property_type, buyer, seller, date_from, date_to, price_min, price_max)
    rows = q.order_by(models.Transaction.transaction_date.desc().nullslast()).all()

    buf = io.StringIO()
    buf.write("﻿")  # BOM for Excel UTF-8
    w = csv.writer(buf, delimiter=";")
    w.writerow([
        "ID", "Köpare", "Säljare", "Pris (SEK)", "Pris (text)", "Fastighetstyp",
        "Fastighetsbeteckning", "Adress", "Kommun", "Län", "Affärsdatum", "Tillträdesdatum",
        "Källnamn", "Käll-URL", "Sammanfattning", "Marknadskommentar", "Area (kvm)",
        "Antal lägenheter", "Hyresgäster", "Direktavkastning (%)", "Portfölj",
        "Tillförlitlighet", "Skapad",
    ])
    for t in rows:
        w.writerow([
            t.id, t.buyer, t.seller, t.price_sek, t.price_text, t.property_type,
            t.property_designation, t.address, t.municipality, t.county,
            t.transaction_date, t.access_date, t.source_name, t.source_url,
            t.summary, t.market_comment, t.area_sqm, t.residential_units,
            t.tenants, t.yield_percent,
            "Ja" if t.portfolio_flag else "Nej",
            t.confidence_score, t.created_at,
        ])

    content = buf.getvalue().encode("utf-8")
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=fastighetsaffarer.csv"},
    )


@app.post("/api/transactions/{tx_id}/summarize")
def summarize_transaction(tx_id: int, db: Session = Depends(get_db)):
    obj = db.query(models.Transaction).filter(models.Transaction.id == tx_id).first()
    if not obj:
        raise HTTPException(404, "Affär hittades inte")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(503, "ANTHROPIC_API_KEY saknas – konfigurera miljövariabeln för AI-analys")

    try:
        import anthropic
    except ImportError:
        raise HTTPException(503, "anthropic-paketet är inte installerat (pip install anthropic)")

    client = anthropic.Anthropic(api_key=api_key)

    info = f"""Köpare: {obj.buyer}
Säljare: {obj.seller}
Pris: {obj.price_text or (f"{obj.price_sek:,.0f} SEK" if obj.price_sek else "Okänt")}
Fastighetstyp: {obj.property_type}
Fastighetsbeteckning: {obj.property_designation or "Okänd"}
Adress: {obj.address or "Okänd"}
Kommun: {obj.municipality or "Okänd"}
Län: {obj.county or "Okänt"}
Affärsdatum: {obj.transaction_date or "Okänt"}
Area: {f"{obj.area_sqm:,.0f} kvm" if obj.area_sqm else "Okänd"}
Antal lägenheter: {obj.residential_units or "Ej tillämpligt"}
Hyresgäster: {obj.tenants or "Ej angett"}
Direktavkastning: {f"{obj.yield_percent:.2f}%" if obj.yield_percent else "Ej angett"}
Portfölj: {"Ja" if obj.portfolio_flag else "Nej"}
Råtext: {obj.raw_text or ""}"""

    msg = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": (
                "Du är expert på kommersiella fastighetsaffärer och fastighetsvärdering i Sverige. "
                "Analysera affären nedan och returnera ENBART ett JSON-objekt med:\n"
                '- "summary": faktabaserad sammanfattning på svenska, 2-3 meningar\n'
                '- "market_comment": analytisk kommentar om marknadsbetydelse och värdering på svenska, 2-3 meningar\n\n'
                f"{info}\n\n"
                "Returnera ENBART giltig JSON, inga kodblock, inga förklaringstexter."
            ),
        }],
    )

    text = msg.content[0].text.strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        result = json.loads(m.group()) if m else {"summary": text, "market_comment": ""}

    obj.summary = result.get("summary", "")
    obj.market_comment = result.get("market_comment", "")
    db.commit()
    db.refresh(obj)
    return result
