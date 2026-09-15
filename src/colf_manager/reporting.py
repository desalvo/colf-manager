# fmt: off
from io import BytesIO
import logging
from calendar import monthrange
from datetime import date
from decimal import Decimal
from pathlib import Path

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import __author__, __build__, __version__

BRAND = colors.HexColor("#173f3a")
ACCENT = colors.HexColor("#287d70")
GOLD = colors.HexColor("#dfa63d")
PALE = colors.HexColor("#f3f7f5")
TEXT = colors.HexColor("#263c37")
MUTED = colors.HexColor("#6b7d77")
LINE = colors.HexColor("#c8d8d2")
LOGO_PATH = Path(__file__).resolve().parent / "static" / "logo.png"


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CMTitle", parent=styles["Title"], textColor=BRAND, fontName="Helvetica-Bold", fontSize=22, leading=26, spaceAfter=8))
    styles.add(ParagraphStyle(name="CMSub", parent=styles["Heading2"], textColor=ACCENT, fontSize=12, leading=15, spaceBefore=7, spaceAfter=5, keepWithNext=True))
    styles.add(ParagraphStyle(name="CMBody", parent=styles["BodyText"], textColor=TEXT, fontSize=8.7, leading=12))
    styles.add(ParagraphStyle(name="CMNote", parent=styles["BodyText"], textColor=colors.HexColor("#5f6d69"), fontSize=7.5, leading=10))
    styles.add(ParagraphStyle(name="CMRight", parent=styles["BodyText"], alignment=TA_RIGHT, fontSize=8))
    styles.add(ParagraphStyle(name="CMCenter", parent=styles["BodyText"], alignment=TA_CENTER, fontSize=8))
    return styles


def _footer(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(BRAND)
    canvas.rect(0, height - 16*mm, width, 16*mm, fill=1, stroke=0)
    if LOGO_PATH.is_file():
        try:
            canvas.drawImage(str(LOGO_PATH), 15*mm, height - 13.2*mm, width=9*mm, height=9*mm, preserveAspectRatio=True, mask="auto")
        except Exception:
            logging.getLogger(__name__).debug("Unable to draw report logo", exc_info=True)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10.5)
    canvas.drawString(27*mm, height - 8.2*mm, "COLF MANAGER")
    canvas.setFont("Helvetica", 6.8)
    canvas.drawString(27*mm, height - 12.2*mm, f"v{__version__} · {__build__} · {__author__}")
    canvas.drawRightString(width - 15*mm, height - 10.3*mm, "Documento gestionale riservato")
    canvas.setStrokeColor(LINE)
    canvas.line(15*mm, 14*mm, width - 15*mm, 14*mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 6.6)
    canvas.drawString(15*mm, 9.5*mm, f"colf-manager · v{__version__} · {__author__} · EUPL-1.2")
    canvas.drawRightString(width - 15*mm, 9.5*mm, f"Pagina {doc.page}")
    canvas.restoreState()


def _doc(title):
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=17*mm, rightMargin=17*mm, topMargin=23*mm, bottomMargin=18*mm, title=title, author="colf-manager")
    return out, doc


def _party_block(worker, employer, styles):
    e = employer
    emp = f"{e.first_name} {e.last_name}" if e else "Datore di lavoro non associato"
    emp_details = []
    if e:
        if e.fiscal_code:
            emp_details.append(f"CF {e.fiscal_code}")
        if e.address:
            emp_details.append(e.address)
        if e.email:
            emp_details.append(e.email)
        if e.phone:
            emp_details.append(e.phone)
    worker_details = [f"{worker.first_name} {worker.last_name}"]
    if worker.fiscal_code:
        worker_details.append(f"CF {worker.fiscal_code}")
    if worker.inps_number:
        worker_details.append(f"Rapporto INPS {worker.inps_number}")
    if getattr(worker, "contract_number", None):
        worker_details.append(f"Contratto {worker.contract_number}")
    rows = [
        [Paragraph("<b>Datore di lavoro</b>", styles["CMBody"]), Paragraph("<b>Lavoratore</b>", styles["CMBody"])],
        [Paragraph(emp + ("<br/>" + "<br/>".join(emp_details) if emp_details else ""), styles["CMBody"]), Paragraph("<br/>".join(worker_details), styles["CMBody"])],
    ]
    t = Table(rows, colWidths=[80*mm, 80*mm])
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),PALE),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#c8d8d2")),("INNERGRID",(0,0),(-1,-1),0.3,colors.HexColor("#dbe5e1")),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),7)]))
    return t


def _kv_table(rows):
    t = Table(rows, colWidths=[112*mm, 48*mm])
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),BRAND),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,PALE]),("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#c8d8d2")),("ALIGN",(1,1),(1,-1),"RIGHT"),("PADDING",(0,0),(-1,-1),6)]))
    return t


def _money(v):
    return f"€ {v}"


def _fiscal_story(fiscal, styles):
    if not fiscal:
        return []
    story = [Paragraph("Contributi e fiscalità", styles["CMSub"])]
    inps = fiscal.get("inps") if isinstance(fiscal, dict) else None
    taxes = fiscal.get("taxes") if isinstance(fiscal, dict) else None
    if inps:
        if inps.get("unavailable"):
            story.append(Paragraph(f"Calcolo contributivo automatico non disponibile: {inps.get('source','')}", styles["CMNote"]))
        else:
            story.append(_kv_table([["Contributi INPS (stima)","Importo"],["Totale da versare all'INPS",_money(inps["total"])],["Quota ordinariamente a carico del datore",_money(inps["employer_share"])],["Quota ordinariamente a carico del lavoratore",_money(inps["worker_share"])],["Quota residua stimata a carico lavoratore",_money(inps["worker_due"])],["Costo contributivo stimato datore",_money(inps["employer_cost"])]]))
            story.append(Paragraph(f"Fonte/tabella: {inps.get('source','INPS')}. Il datore versa materialmente l'intero contributo; la ripartizione economica della quota lavoratore dipende dalle impostazioni del contratto registrate nell'app.", styles["CMNote"]))
    if taxes:
        story.append(_kv_table([["Stima fiscale IRPEF","Importo"],["Reddito del rapporto considerato",_money(taxes["taxable_income_estimate"])],["IRPEF lorda nazionale stimata",_money(taxes["gross_irpef_estimate"])],["Stima residua a carico lavoratore",_money(taxes["worker_due_estimate"])],["Stima assunta economicamente dal datore",_money(taxes["employer_assumed_tax_cost"])]]))
        story.append(Paragraph(taxes["note"] + " Il datore domestico privato non opera normalmente come sostituto d'imposta: questa sezione non costituisce liquidazione fiscale definitiva.", styles["CMNote"]))
    return story




def _expense_story(expenses, styles, as_of=None):
    expenses = list(expenses or [])
    if not expenses:
        return []
    rows = [["Data", "Descrizione", "Sostenuta da", "Originaria", "Compensata", "Residuo"]]
    for expense in sorted(expenses, key=lambda item: item.expense_date):
        owner = "Lavoratore" if expense.direction == "worker_advance" else "Datore di lavoro"
        settlements = [
            item
            for item in (getattr(expense, "settlements", []) or [])
            if as_of is None or item.settlement_date <= as_of
        ]
        allocations = [
            item
            for item in (getattr(expense, "recovery_allocations", []) or [])
            if as_of is None or item.due_month <= as_of
        ]
        if expense.reimbursed and not settlements and not allocations:
            settled = Decimal(expense.amount)
            payroll_allocated = Decimal("0")
        else:
            settled = sum((Decimal(item.amount) for item in settlements), Decimal("0"))
            payroll_allocated = sum(
                (Decimal(item.amount) for item in allocations if item.locked_at), Decimal("0")
            )
        residual = max(
            Decimal("0"), Decimal(expense.amount) - settled - payroll_allocated
        )
        rows.append([
            expense.expense_date.strftime("%d/%m/%Y"),
            expense.description,
            owner,
            _money(expense.amount),
            _money(settled + payroll_allocated),
            _money(residual),
        ])
    table = Table(rows, colWidths=[20*mm, 54*mm, 29*mm, 22*mm, 23*mm, 22*mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c8d8d2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.0),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    detail = []
    for expense in sorted(expenses, key=lambda item: item.expense_date):
        for settlement in getattr(expense, "settlements", []) or []:
            if as_of is not None and settlement.settlement_date > as_of:
                continue
            methods = {
                "cash": "contanti",
                "bank_transfer": "bonifico",
                "card": "carta",
                "electronic": "elettronico",
                "other": "altro",
            }
            doc = settlement.filename or "senza documento"
            detail.append(Paragraph(
                f"• {settlement.settlement_date.strftime('%d/%m/%Y')} — {expense.description}: "
                f"{_money(settlement.amount)} ({methods.get(settlement.method, settlement.method)}; {doc})",
                styles["CMNote"],
            ))
    story = [Paragraph("Spese, compensazioni e residui del periodo", styles["CMSub"]), table]
    if detail:
        story.append(Paragraph("Compensazioni manuali registrate", styles["CMSub"]))
        story.extend(detail)
    return story

def _signature_image(path):
    if not path or not Path(path).is_file():
        return None
    try:
        image = RLImage(path)
        max_w, max_h = 38 * mm, 16 * mm
        ratio = min(max_w / image.imageWidth, max_h / image.imageHeight)
        image.drawWidth = image.imageWidth * ratio
        image.drawHeight = image.imageHeight * ratio
        return image
    except Exception:
        return None


def _payment_story(payments, styles, due_amount=None, title="Pagamenti registrati", due_types=None):
    payments = list(payments or [])
    if not payments and due_amount is None:
        return []
    story = [Paragraph(title, styles["CMSub"])]
    paid_total = sum((p.amount for p in payments if getattr(p, "status", "") == "paid" and (not due_types or p.payment_type in due_types)), 0)
    if due_amount is not None:
        residual = max(due_amount - paid_total, 0)
        story.append(_kv_table([
            ["Situazione liquidazione", "Importo"],
            ["Dovuto / maturato nel prospetto", _money(due_amount)],
            ["Quota già liquidata registrata", _money(paid_total)],
            ["Residuo da liquidare", _money(residual)],
        ]))
        story.append(Spacer(1, 5))
    if payments:
        labels = {
            "salary": "Retribuzione",
            "inps_contributions": "Contributi INPS",
            "thirteenth": "Tredicesima",
            "tfr": "TFR",
            "expense_refund": "Rimborso spese",
            "other": "Altro",
        }
        rows = [["Tipo", "Stato", "Data", "Importo", "Periodo"]]
        for payment in payments:
            period = ""
            if payment.period_start:
                period = payment.period_start.strftime("%d/%m/%Y")
            if payment.period_end and payment.period_end != payment.period_start:
                period += " → " + payment.period_end.strftime("%d/%m/%Y")
            rows.append([
                labels.get(payment.payment_type, payment.payment_type),
                "Pagato" if payment.status == "paid" else "Da pagare",
                payment.payment_date.strftime("%d/%m/%Y") if payment.payment_date else "—",
                _money(payment.amount),
                period or "—",
            ])
        table = Table(rows, colWidths=[36*mm, 25*mm, 28*mm, 30*mm, 45*mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
            ("GRID", (0, 0), (-1, -1), 0.35, LINE),
            ("FONTSIZE", (0, 0), (-1, -1), 7.1),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
    return story


def _signature_story(worker, employer, styles, approval=None):
    approval = approval or {}
    mode = (approval.get("mode") or "none").strip().lower()
    if mode not in {"worker", "employer", "both"}:
        return []

    place = (approval.get("place") or "").strip() or "____________________________"
    report_date = approval.get("date") or date.today()
    if isinstance(report_date, str):
        try:
            report_date = date.fromisoformat(report_date)
        except ValueError:
            report_date = date.today()

    story = [
        Spacer(1, 10),
        Paragraph("Approvazione e firme", styles["CMSub"]),
        Paragraph(
            "La sottoscrizione attesta la presa visione e, quando previsto, l'approvazione "
            "del presente prospetto gestionale.",
            styles["CMNote"],
        ),
        Spacer(1, 5),
        _kv_table([
            ["Luogo", place],
            ["Data", report_date.strftime("%d/%m/%Y")],
        ]),
        Spacer(1, 14),
    ]

    signers = []
    if mode in {"worker", "both"}:
        signers.append(("Firma lavoratore", f"{worker.first_name} {worker.last_name}", approval.get("worker_signature")))
    if mode in {"employer", "both"}:
        employer_name = (
            f"{employer.first_name} {employer.last_name}"
            if employer
            else "Datore di lavoro non associato"
        )
        signers.append(("Firma datore di lavoro", employer_name, approval.get("employer_signature")))

    cells = []
    for label, name, signature_path in signers:
        signature = _signature_image(signature_path)
        body = [Paragraph(f"<b>{label}</b>", styles["CMCenter"]), Spacer(1, 5)]
        if signature:
            body.extend([signature, Spacer(1, 3)])
        else:
            body.extend([Spacer(1, 13*mm), Paragraph("________________________________________", styles["CMCenter"])])
        body.append(Paragraph(f"<b>{name}</b>", styles["CMCenter"]))
        cells.append(body)
    widths = [160 * mm] if len(cells) == 1 else [80 * mm, 80 * mm]
    table = Table([cells], colWidths=widths)
    table.setStyle(
        TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#c8d8d2")),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dbe5e1")),
            ("BACKGROUND", (0, 0), (-1, -1), PALE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 10),
        ])
    )
    story.append(table)
    return story

def payroll_pdf(worker, summary, year, month, employer=None, vacation=None, fiscal=None, expenses=None, title="Cedolino mensile gestionale", approval=None, payments=None):
    out, doc = _doc(title)
    s = _styles()
    story = [Paragraph(title, s["CMTitle"]), Paragraph(f"Periodo {month:02d}/{year}", s["CMSub"]), _party_block(worker, employer, s), Spacer(1, 7)]
    rows = [["Voce", "Valore"], ["Ore lavorate", str(summary["worked_hours"])], ["Retribuzione ore", _money(summary["worked_pay"])], ["Assenze retribuite / ferie / malattia", _money(summary["paid_absence"])], ["Anticipi lavoratore da rimborsare", _money(summary["worker_advances"])], ["Anticipi datore da recuperare", _money(summary["employer_advances"])], ["Rettifica netta spese/anticipi", _money(summary["reimbursements"])], ["Retribuzione registrata", _money(summary["gross"])], ["Quota tredicesima maturata (stima)", _money(summary.get("thirteenth_accrual", 0))], ["Quota TFR maturata (stima)", _money(summary["tfr_accrual"])], ["Totale da corrispondere", _money(summary["payable"])]]
    story.append(_kv_table(rows))
    if vacation:
        story += [Paragraph("Ferie", s["CMSub"]), _kv_table([["Situazione ferie", "Giorni"],["Maturate alla data", str(vacation["accrued"])],["Proiezione fine anno", str(vacation["projected"])],["Godute/programmate", str(vacation["used_scheduled"])],["Disponibili secondo impostazione", str(vacation["available_usable"])]])]
    story += _expense_story(expenses, s, date(year, month, monthrange(year, month)[1]))
    story += _fiscal_story(fiscal, s)
    story += _payment_story(payments, s, summary.get("payable"), due_types={"salary"})
    story += [Spacer(1, 10), Paragraph("Il presente documento è un prospetto gestionale. Verificare sempre contratto applicato, contributi INPS, minimi retributivi e normativa vigente per il periodo considerato.", s["CMNote"])]
    story += _signature_story(worker, employer, s, approval)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    out.seek(0)
    return out


def annual_payroll_pdf(worker, employer, annual, year, vacation, fiscal=None, expenses=None, approval=None, payments=None):
    out, doc = _doc("Cedolino globale annuale")
    s = _styles()
    story=[Paragraph("Cedolino globale annuale", s["CMTitle"]), Paragraph(str(year), s["CMSub"]), _party_block(worker, employer, s), Spacer(1,7)]
    rows=[["Mese","Ore","Retribuzione","Assenze","Spese nette","Da corrispondere"]]
    for i, m in enumerate(annual["months"], 1):
        rows.append([f"{i:02d}", str(m["worked_hours"]), _money(m["worked_pay"]), _money(m["paid_absence"]), _money(m["reimbursements"]), _money(m["payable"])])
    t=Table(rows,colWidths=[15*mm,25*mm,31*mm,31*mm,30*mm,32*mm],repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),BRAND),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,PALE]),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#c8d8d2")),("ALIGN",(1,1),(-1,-1),"RIGHT"),("FONTSIZE",(0,0),(-1,-1),7.2),("PADDING",(0,0),(-1,-1),4)]))
    story += [t, Paragraph("Totali annuali",s["CMSub"]), _kv_table([["Voce","Valore"],["Ore",str(annual["worked_hours"])],["Retribuzione registrata",_money(annual["gross"])],["Quota tredicesima maturata",_money(annual["thirteenth_accrual"])],["TFR maturato",_money(annual["tfr_accrual"])],["Totale corrispondibile registrato",_money(annual["payable"])]]), Paragraph("Ferie annuali",s["CMSub"]), _kv_table([["Ferie","Giorni"],["Maturate",str(vacation["accrued"])],["Maturabili entro 31/12",str(vacation["projected"])],["Godute/programmate",str(vacation["used_scheduled"])],["Disponibili",str(vacation["available_usable"])]]), Spacer(1,8), Paragraph("Prospetto gestionale annuale; non sostituisce gli adempimenti ufficiali.",s["CMNote"])]
    story += _expense_story(expenses, s, date(year, 12, 31))
    story += _fiscal_story(fiscal, s)
    story += _payment_story(payments, s, annual.get("payable"), due_types={"salary"})
    story += _signature_story(worker, employer, s, approval)
    doc.build(story,onFirstPage=_footer,onLaterPages=_footer)
    out.seek(0)
    return out


def courtesy_cu_pdf(worker, employer, annual, year, fiscal=None, approval=None, payments=None):
    out, doc = _doc("Certificazione retribuzioni / CU di cortesia")
    s=_styles()
    story=[Paragraph("Certificazione retribuzioni · CU di cortesia",s["CMTitle"]),Paragraph(f"Anno fiscale {year}",s["CMSub"]),_party_block(worker,employer,s),Spacer(1,7),_kv_table([["Dati riepilogativi","Importo"],["Retribuzione registrata",_money(annual["gross"])],["Quota tredicesima maturata",_money(annual["thirteenth_accrual"])],["Rimborsi/anticipi netti registrati",_money(annual["reimbursements"])],["TFR maturato nell'anno (informativo)",_money(annual["tfr_accrual"])]]),Spacer(1,10),Paragraph("Natura del documento",s["CMSub"]),Paragraph("Il datore di lavoro domestico privato normalmente non opera come sostituto d'imposta. Questo PDF è una certificazione di cortesia delle somme risultanti nell'applicazione e non è il modello CU telematico dell'Agenzia delle Entrate. I dati devono essere verificati prima dell'uso fiscale.",s["CMBody"]),Spacer(1,8),Paragraph(f"Generato il {date.today().strftime('%d/%m/%Y')}",s["CMNote"])]
    story += _fiscal_story(fiscal, s)
    story += _payment_story(payments, s)
    story += _signature_story(worker, employer, s, approval)
    doc.build(story,onFirstPage=_footer,onLaterPages=_footer)
    out.seek(0)
    return out


def tfr_annual_pdf(worker, employer, tfr, year, rule_notes, fiscal=None, approval=None, payments=None):
    out,doc=_doc("Prospetto TFR annuale")
    s=_styles()
    story=[Paragraph("Prospetto TFR annuale",s["CMTitle"]),Paragraph(f"Anno {year} · calcolo fino al {tfr['cutoff'].strftime('%d/%m/%Y')}",s["CMSub"]),_party_block(worker,employer,s),Spacer(1,7),_kv_table([["Calcolo quota annuale","Valore"],["Retribuzione registrata utile",_money(tfr["gross"])],["Quota tredicesima maturata",_money(tfr["thirteenth_accrual"])],["Base utile TFR stimata",_money(tfr["tfr_useful_compensation"])],["Divisore", "13,5"],["Quota TFR maturata nell'anno",_money(tfr["tfr_accrual"])]]),Paragraph("Regole applicate",s["CMSub"])]
    for note in rule_notes:
        story.append(Paragraph("• " + note, s["CMBody"]))
    story += [Spacer(1,7),Paragraph(tfr["revaluation_note"],s["CMNote"]),Spacer(1,5),Paragraph("Il prospetto calcola la quota maturata nell'anno sui dati registrati. Eventuali anticipazioni, liquidazioni pregresse, rivalutazioni di quote precedenti e trattamento fiscale devono essere riconciliati prima del pagamento.",s["CMNote"])]
    story += _fiscal_story(fiscal, s)
    story += _payment_story(payments, s, tfr.get("tfr_accrual"), "Liquidazioni TFR", {"tfr"})
    story += _signature_story(worker, employer, s, approval)
    doc.build(story,onFirstPage=_footer,onLaterPages=_footer)
    out.seek(0)
    return out


def trend_pdf(worker, employer, annual, year, fiscal=None, expenses=None, approval=None, payments=None):
    out,doc=_doc("Andamento ore e retribuzioni")
    s=_styles()
    story=[Paragraph("Andamento ore e retribuzioni",s["CMTitle"]),Paragraph(str(year),s["CMSub"]),_party_block(worker,employer,s),Spacer(1,8)]
    hours=[float(m["worked_hours"]) for m in annual["months"]]
    drawing=Drawing(480,230)
    chart=VerticalBarChart()
    chart.x=42
    chart.y=42
    chart.height=145
    chart.width=395
    chart.data=[hours]
    chart.categoryAxis.categoryNames=["G","F","M","A","M","G","L","A","S","O","N","D"]
    chart.valueAxis.valueMin=0
    chart.bars[0].fillColor=ACCENT
    chart.bars[0].strokeColor=ACCENT
    drawing.add(chart)
    drawing.add(String(42,205,"Ore lavorate per mese",fontName="Helvetica-Bold",fontSize=10,fillColor=BRAND))
    story += [drawing,Spacer(1,4)]
    rows=[["Mese","Ore","Retribuzione","Da corrispondere"]]
    for i, m in enumerate(annual["months"], 1):
        rows.append([f"{i:02d}/{year}", str(m["worked_hours"]), _money(m["gross"]), _money(m["payable"])])
    t=Table(rows,colWidths=[35*mm,35*mm,45*mm,45*mm],repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),BRAND),("TEXTCOLOR",(0,0),(-1,0),colors.white),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,PALE]),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#c8d8d2")),("ALIGN",(1,1),(-1,-1),"RIGHT"),("FONTSIZE",(0,0),(-1,-1),7.5),("PADDING",(0,0),(-1,-1),4)]))
    story += [t,Spacer(1,8),Paragraph(f"Totale ore: {annual['worked_hours']} · Retribuzione registrata: {_money(annual['gross'])}",s["CMBody"])]
    story += _expense_story(expenses, s, date(year, 12, 31))
    story += _fiscal_story(fiscal, s)
    story += _payment_story(payments, s)
    story += _signature_story(worker, employer, s, approval)
    doc.build(story,onFirstPage=_footer,onLaterPages=_footer)
    out.seek(0)
    return out




def location_trend_pdf(worker, employer, location_data, year, approval=None, payments=None):
    out, doc = _doc("Andamento ore per luogo")
    s = _styles()
    story = [
        Paragraph("Andamento delle ore per luogo", s["CMTitle"]),
        Paragraph(str(year), s["CMSub"]),
        _party_block(worker, employer, s),
        Spacer(1, 8),
        Paragraph("Il prospetto distingue le ore retribuite registrate in base al luogo di lavoro memorizzato per ciascun inserimento.", s["CMBody"]),
        Spacer(1, 7),
    ]
    if not location_data:
        story.append(Paragraph("Nessuna ora retribuita registrata per l'anno selezionato.", s["CMNote"]))
    else:
        totals = [["Luogo", "Ore annuali"]]
        for item in location_data:
            totals.append([item["location"], f'{item["total"]:.2f}'])
        table = Table(totals, colWidths=[125*mm, 35*mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c8d8d2")),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.8),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story += [table, Spacer(1, 9), Paragraph("Dettaglio mensile", s["CMSub"])]
        month_headers = ["Luogo"] + [f"{m:02d}" for m in range(1, 13)] + ["Tot."]
        rows = [month_headers]
        for item in location_data:
            rows.append([item["location"]] + [f"{value:.2f}" for value in item["months"]] + [f'{item["total"]:.2f}'])
        detail = Table(rows, colWidths=[48*mm] + [8.4*mm] * 12 + [12*mm], repeatRows=1)
        detail.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c8d8d2")),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 5.8),
            ("PADDING", (0, 0), (-1, -1), 2.2),
        ]))
        story.append(detail)
    story += _payment_story(payments, s)
    story += _signature_story(worker, employer, s, approval)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    out.seek(0)
    return out

def thirteenth_payroll_pdf(worker, employer, thirteenth, year, rule_notes, fiscal=None, approval=None, payments=None):
    out, doc = _doc("Cedolino tredicesima")
    s = _styles()
    story = [Paragraph("Cedolino della tredicesima", s["CMTitle"]), Paragraph(f"Anno {year} · calcolo fino al {thirteenth['cutoff'].strftime('%d/%m/%Y')}", s["CMSub"]), _party_block(worker, employer, s), Spacer(1,7)]
    story += [_kv_table([["Calcolo tredicesima","Valore"],["Retribuzione utile registrata nel periodo",_money(thirteenth["gross"])],["Formula","Retribuzione utile / 12"],["Tredicesima maturata",_money(thirteenth["thirteenth"])]]), Paragraph("Metodo di calcolo", s["CMSub"]), Paragraph("La tredicesima del lavoro domestico corrisponde a un dodicesimo della retribuzione annua utile. Per un rapporto iniziato o cessato nell'anno, il valore riflette il periodo e le retribuzioni registrate nell'applicazione. La tredicesima matura anche nei periodi tutelati previsti dalla disciplina applicabile, entro i relativi limiti.", s["CMBody"])]
    for note in rule_notes:
        story.append(Paragraph("• " + note, s["CMBody"]))
    story += _fiscal_story(fiscal, s)
    story += _payment_story(payments, s, thirteenth.get("thirteenth"), "Liquidazioni tredicesima", {"thirteenth"})
    story += [Spacer(1,7), Paragraph("Documento gestionale: verificare minimi contrattuali, elementi retributivi utili e disciplina vigente prima del pagamento.",s["CMNote"])]
    story += _signature_story(worker, employer, s, approval)
    doc.build(story,onFirstPage=_footer,onLaterPages=_footer)
    out.seek(0)
    return out


def combined_thirteenth_tfr_pdf(worker, employer, combined, year, rule_notes, approval=None, payments=None):
    out, doc = _doc("Tredicesima + TFR")
    s = _styles()
    th = combined["thirteenth"]
    tfr = combined["tfr"]
    story=[Paragraph("Prospetto cumulativo tredicesima + TFR",s["CMTitle"]),Paragraph(f"Anno {year} · fino al {combined['cutoff'].strftime('%d/%m/%Y')}",s["CMSub"]),_party_block(worker,employer,s),Spacer(1,7),_kv_table([["Voce","Importo"],["Retribuzione utile registrata",_money(th["gross"])],["Tredicesima maturata (retribuzione / 12)",_money(th["thirteenth"])],["Base utile TFR stimata",_money(tfr["tfr_useful_compensation"])],["TFR maturato (base utile / 13,5)",_money(tfr["tfr_accrual"])],["Totale tredicesima + TFR",_money(th["thirteenth"]+tfr["tfr_accrual"])]]),Paragraph("Descrizione dei calcoli",s["CMSub"]),Paragraph(f"Tredicesima: {th['gross']} / 12 = {th['thirteenth']}. TFR: base utile {tfr['tfr_useful_compensation']} / 13,5 = {tfr['tfr_accrual']}. Il periodo termina il {combined['cutoff'].strftime('%d/%m/%Y')}.",s["CMBody"])]
    for note in rule_notes:
        story.append(Paragraph("• " + note, s["CMBody"]))
    story += _fiscal_story({"inps":combined.get("inps"),"taxes":combined.get("taxes")},s)
    story += [Paragraph(tfr["revaluation_note"],s["CMNote"]),Paragraph("Il totale non costituisce automaticamente importo netto da pagare: eventuali anticipi TFR, quote già liquidate, contribuzione e imposizione fiscale vanno riconciliati.",s["CMNote"])]
    story += _payment_story(payments, s, combined["thirteenth"]["thirteenth"] + combined["tfr"]["tfr_accrual"], "Liquidazioni tredicesima e TFR", {"thirteenth", "tfr"})
    story += _signature_story(worker, employer, s, approval)
    doc.build(story,onFirstPage=_footer,onLaterPages=_footer)
    out.seek(0)
    return out
