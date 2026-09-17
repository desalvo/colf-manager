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
from reportlab.platypus import Image as RLImage, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfgen.canvas import Canvas
from PIL import Image as PILImage

from . import __author__, __build__, __version__
from .formatting import currency

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
    styles.add(ParagraphStyle(name="CMAmountLabel", parent=styles["BodyText"], alignment=TA_CENTER, fontSize=8, textColor=MUTED, leading=10))
    styles.add(ParagraphStyle(name="CMAmountValue", parent=styles["BodyText"], alignment=TA_CENTER, fontName="Helvetica-Bold", fontSize=16, leading=19, textColor=BRAND))
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
    canvas.restoreState()


class _PageCountCanvas(Canvas):
    """Canvas che aggiunge la numerazione esatta Pagina X di Y."""

    def __init__(self, *args, **kwargs):
        Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.saveState()
            width, _ = A4
            self.setFillColor(MUTED)
            self.setFont("Helvetica", 6.6)
            self.drawRightString(width - 15*mm, 9.5*mm, f"Pagina {self._pageNumber} di {page_count}")
            self.restoreState()
            Canvas.showPage(self)
        Canvas.save(self)


def _group_sections(story):
    """Mantiene titolo di sezione e contenuto sulla stessa pagina quando possibile."""
    grouped = []
    index = 0
    while index < len(story):
        item = story[index]
        if isinstance(item, Paragraph) and getattr(item.style, "name", "") == "CMSub":
            block = [item]
            index += 1
            while index < len(story):
                nxt = story[index]
                if isinstance(nxt, Paragraph) and getattr(nxt.style, "name", "") in {"CMSub", "CMTitle"}:
                    break
                block.append(nxt)
                index += 1
            grouped.append(KeepTogether(block))
            continue
        grouped.append(item)
        index += 1
    return grouped


def _build(doc, story):
    doc.build(
        _group_sections(story),
        onFirstPage=_footer,
        onLaterPages=_footer,
        canvasmaker=_PageCountCanvas,
    )


def _report_notes_story(styles, report_kind="generic", report_year=None, extra_notes=None):
    methods = {
        "payment_receipt": "Importo dovuto, importo pagato e residuo derivano dalla posizione di pagamento registrata; il residuo e calcolato come dovuto meno pagato, con minimo zero.",
        "monthly_payroll": "I valori sono ricavati dalle registrazioni del mese: ore e tipologia delle prestazioni, tariffa valida nel periodo, assenze retribuite/non retribuite, ferie, permessi, malattia, spese/rimborsi e pagamenti. Le componenti vengono aggregate secondo le regole configurate e il residuo tiene conto dei pagamenti registrati.",
        "annual_payroll": "I valori annuali sono la somma dei risultati mensili e delle competenze maturate nel periodo, sulla base delle registrazioni di ore, tariffe, assenze, ferie, permessi, malattia, spese/rimborsi e pagamenti presenti nell'applicazione.",
        "courtesy_cu": "Il prospetto aggrega le retribuzioni e le altre componenti registrate nell'anno. E una certificazione gestionale di cortesia e non sostituisce la Certificazione Unica telematica quando questa sia prevista dalla normativa.",
        "tfr": "La quota TFR dell'anno e determinata sulla retribuzione utile registrata, comprensiva delle componenti utili, divisa per 13,5. Le quote pregresse, quando considerate, devono essere rivalutate secondo la disciplina vigente; anticipi e liquidazioni precedenti devono essere riconciliati.",
        "thirteenth": "La tredicesima maturata e calcolata in dodicesimi sulla retribuzione utile del periodo, tenendo conto dei mesi utili e delle assenze che danno diritto alla maturazione secondo la disciplina applicabile.",
        "thirteenth_tfr": "Il prospetto applica separatamente la regola della tredicesima in dodicesimi e la regola del TFR sulla retribuzione utile divisa per 13,5; il totale e la somma delle due componenti prima delle eventuali riconciliazioni fiscali/contributive o di importi gia liquidati.",
        "trend": "Il report aggrega per mese ore e importi gia calcolati dalle registrazioni del rapporto, senza introdurre valori ulteriori rispetto ai dati presenti nell'applicazione.",
        "location_trend": "Le ore retribuite sono raggruppate per luogo e mese a partire dalle registrazioni del calendario; i totali annuali sono la somma dei valori mensili per ciascun luogo.",
        "annual_payments": "Sono sommati esclusivamente i pagamenti marcati come pagati con data di pagamento compresa nell'anno indicato; i totali per categoria e il totale annuale derivano dalla somma degli importi registrati.",
        "generic": "I valori derivano dai dati registrati in Colf Manager per il periodo indicato e dalle formule documentate nel prospetto; prima dell'uso amministrativo o fiscale devono essere verificati completezza dei dati e parametri applicabili al rapporto.",
    }
    year_note = ""
    if report_year is not None:
        if report_year >= 2026:
            year_note = " Per i periodi dal 1 novembre 2025 il riferimento contrattuale corrente e il CCNL lavoro domestico sottoscritto il 28 ottobre 2025, con decorrenza 1 novembre 2025 e scadenza 31 ottobre 2028."
        elif report_year == 2025:
            year_note = " Per il 2025 occorre distinguere il regime contrattuale applicabile fino al 31 ottobre da quello del CCNL sottoscritto il 28 ottobre 2025, decorrente dal 1 novembre 2025."
        else:
            year_note = " Per periodi anteriori al 1 novembre 2025 devono essere applicati contratto collettivo, minimi, tabelle contributive e regole vigenti nel periodo, senza applicazione retroattiva del CCNL 2025."
    legal = (
        "Riferimenti essenziali: CCNL sulla disciplina del rapporto di lavoro domestico vigente nel periodo "
        "(per il CCNL 2025: art. 17 ferie, art. 39 tredicesima, art. 41 TFR); art. 2120 c.c. e legge 29 maggio 1982 n. 297 per il TFR; "
        "istruzioni e tabelle INPS dell'anno di competenza per i contributi. Minimi retributivi, valori convenzionali, aliquote e scadenze devono essere quelli vigenti nel periodo del report."
        + year_note
    )
    privacy = (
        "Il report contiene dati personali relativi al rapporto di lavoro. Deve essere conservato e condiviso solo per finalita pertinenti alla gestione del rapporto e con soggetti autorizzati, adottando misure adeguate di sicurezza e riservatezza, nel rispetto del Regolamento (UE) 2016/679 e della normativa nazionale applicabile. Questa nota non sostituisce l'eventuale informativa privacy dovuta all'interessato."
    )
    flow = [
        Spacer(1, 8),
        Paragraph("Note metodologiche, legali e privacy", styles["CMSub"]),
        Paragraph("<b>Metodo di calcolo.</b> " + methods.get(report_kind, methods["generic"]), styles["CMNote"]),
        Spacer(1, 2),
        Paragraph("<b>Riferimenti e termini legali.</b> " + legal, styles["CMNote"]),
    ]
    for note in extra_notes or []:
        flow.extend([Spacer(1, 1), Paragraph("• " + str(note), styles["CMNote"])])
    flow.extend([Spacer(1, 2), Paragraph("<b>Dati personali.</b> " + privacy, styles["CMNote"])])
    return flow


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
    return currency(v)


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
        with PILImage.open(path) as source:
            rgba = source.convert("RGBA")
            pixels = []
            # Pillow 14 removes Image.getdata(); on current Pillow versions
            # get_flattened_data() provides the same flattened pixel stream
            # without emitting a deprecation warning. Keep a compatibility
            # fallback for older supported Pillow releases.
            pixel_data = (
                rgba.get_flattened_data()
                if hasattr(rgba, "get_flattened_data")
                else rgba.getdata()
            )
            for red, green, blue, alpha in pixel_data:
                if red >= 245 and green >= 245 and blue >= 245:
                    pixels.append((255, 255, 255, 0))
                else:
                    pixels.append((red, green, blue, alpha))
            rgba.putdata(pixels)

            # Crop transparent margins before ReportLab centres the image.
            # Without this, a signature scanned with asymmetric white margins
            # is geometrically centred as a file but visibly shifted in the box.
            bbox = rgba.getchannel("A").getbbox()
            if bbox:
                rgba = rgba.crop(bbox)

            stream = BytesIO()
            rgba.save(stream, format="PNG")
            stream.seek(0)
        image = RLImage(stream)
        image._signature_stream = stream
        max_w, max_h = 38 * mm, 16 * mm
        ratio = min(max_w / image.imageWidth, max_h / image.imageHeight)
        image.drawWidth = image.imageWidth * ratio
        image.drawHeight = image.imageHeight * ratio
        image.hAlign = "CENTER"
        return image
    except Exception:
        logging.getLogger(__name__).debug("Unable to prepare signature image", exc_info=True)
        return None



def _amount_callout(due_amount, paid_amount=None, residual_amount=None, styles=None):
    """High-visibility amount summary used in payroll reports and receipts."""
    styles = styles or _styles()
    cells = [
        [
            Paragraph("IMPORTO DOVUTO", styles["CMAmountLabel"]),
            Paragraph("IMPORTO PAGATO", styles["CMAmountLabel"]),
            Paragraph("RESIDUO", styles["CMAmountLabel"]),
        ],
        [
            Paragraph(_money(due_amount), styles["CMAmountValue"]),
            Paragraph(_money(paid_amount or 0), styles["CMAmountValue"]),
            Paragraph(_money(residual_amount if residual_amount is not None else max(Decimal(due_amount) - Decimal(paid_amount or 0), Decimal("0"))), styles["CMAmountValue"]),
        ],
    ]
    table = Table(cells, colWidths=[53*mm, 53*mm, 53*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#fff3cf")),
        ("BACKGROUND", (1,0), (1,-1), colors.HexColor("#e5f6ed")),
        ("BACKGROUND", (2,0), (2,-1), colors.HexColor("#fde9e6")),
        ("BOX", (0,0), (-1,-1), 0.7, LINE),
        ("INNERGRID", (0,0), (-1,-1), 0.4, LINE),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("TOPPADDING", (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ]))
    return table


PAYMENT_METHOD_LABELS = {
    "bank_transfer": "Bonifico bancario",
    "card_deposit": "Deposito su carta",
    "cash": "Contanti",
    "other": "Altro",
}


def payment_receipt_pdf(
    payment,
    worker,
    employer,
    due_amount,
    payment_label,
    payment_method_label,
    employer_signature=None,
    worker_signature=None,
):
    """Create a professional receipt for one payment marked as paid."""
    out, doc = _doc(f"Quietanza pagamento #{payment.id}")
    styles = _styles()
    paid = Decimal(payment.amount)
    due = Decimal(due_amount if due_amount is not None else payment.amount)
    residual = max(due - paid, Decimal("0"))
    payment_date = payment.payment_date or date.today()
    period = "—"
    if payment.period_start:
        period = payment.period_start.strftime("%d/%m/%Y")
        if payment.period_end and payment.period_end != payment.period_start:
            period += " → " + payment.period_end.strftime("%d/%m/%Y")

    story = [
        Paragraph("QUIETANZA DI PAGAMENTO", styles["CMTitle"]),
        Paragraph(f"Pagamento #{payment.id} · {payment_label}", styles["CMSub"]),
        _party_block(worker, employer, styles),
        Spacer(1, 10),
        _amount_callout(due, paid, residual, styles),
        Spacer(1, 10),
        _kv_table([
            ["Dettaglio quietanza", "Valore"],
            ["Data pagamento", payment_date.strftime("%d/%m/%Y")],
            ["Periodo di riferimento", period],
            ["Categoria", payment_label],
            ["Modalità di pagamento", payment_method_label],
            ["Importo dovuto", _money(due)],
            ["Importo effettivamente pagato", _money(paid)],
            ["Residuo dopo questo pagamento", _money(residual)],
            ["Descrizione", payment.description or "—"],
        ]),
        Spacer(1, 10),
        Paragraph(
            "Il datore di lavoro attesta che l'importo indicato come effettivamente pagato è stato liquidato al lavoratore per la causale e il periodo sopra riportati. La quietanza documenta il singolo pagamento registrato nell'applicazione.",
            styles["CMBody"],
        ),
    ]
    approval = {
        "mode": "employer",
        "place": (getattr(employer, "city", None) or getattr(employer, "address", None) or "") if employer else "",
        "date": payment_date,
        "employer_signature": employer_signature,
        "worker_signature": worker_signature,
    }
    story += _signature_story(worker, employer, styles, approval, "payment_receipt", payment_date.year)
    _build(doc, story)
    out.seek(0)
    return out

def _payment_story(payments, styles, due_amount=None, title="Pagamenti registrati", due_types=None):
    payments = list(payments or [])
    if not payments and due_amount is None:
        return []
    story = [Paragraph(title, styles["CMSub"])]
    labels = {
        "salary": "Retribuzione",
        "inps_contributions": "Contributi INPS",
        "thirteenth": "Tredicesima",
        "tfr": "TFR",
        "expense_refund": "Rimborso spese",
        "other": "Altro",
    }
    paid_rows = [
        p
        for p in payments
        if getattr(p, "status", "") == "paid"
        and (not due_types or p.payment_type in due_types)
    ]
    paid_total = sum((Decimal(p.amount) for p in paid_rows), Decimal("0"))
    if paid_rows:
        by_type = {}
        for payment in paid_rows:
            by_type[payment.payment_type] = by_type.get(payment.payment_type, Decimal("0")) + Decimal(payment.amount)
        totals = [["Pagamenti effettuati per categoria", "Importo"]]
        for payment_type, amount in sorted(by_type.items(), key=lambda item: labels.get(item[0], item[0])):
            totals.append([labels.get(payment_type, payment_type), _money(amount)])
        totals.append(["Totale pagamenti effettuati", _money(paid_total)])
        story.extend([_kv_table(totals), Spacer(1, 5)])
    if due_amount is not None:
        residual = max(Decimal(due_amount) - paid_total, Decimal("0"))
        story.append(_amount_callout(Decimal(due_amount), paid_total, residual, styles))
        story.append(Spacer(1, 5))
    if payments:
        rows = [["Tipo", "Stato", "Data", "Modalità", "Importo", "Periodo"]]
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
                PAYMENT_METHOD_LABELS.get(
                    getattr(payment, "payment_method", "bank_transfer"),
                    getattr(payment, "payment_method", "bank_transfer"),
                ),
                _money(payment.amount),
                period or "—",
            ])
        table = Table(rows, colWidths=[31*mm, 22*mm, 24*mm, 31*mm, 25*mm, 39*mm], repeatRows=1)
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


def _signature_story(worker, employer, styles, approval=None, report_kind="generic", report_year=None, extra_notes=None):
    approval = approval or {}
    mode = (approval.get("mode") or "worker").strip().lower()
    if mode not in {"none", "worker", "employer", "both"}:
        mode = "worker"

    place = (approval.get("place") or "").strip() or "____________________________"
    report_date = approval.get("date") or date.today()
    if isinstance(report_date, str):
        try:
            report_date = date.fromisoformat(report_date)
        except ValueError:
            report_date = date.today()

    story = _report_notes_story(styles, report_kind, report_year, extra_notes) + [
        Spacer(1, 10),
        Paragraph("Luogo, data e firma", styles["CMSub"]),
        Paragraph(
            "La firma del lavoratore attesta la presa visione del prospetto. L'eventuale firma del datore di lavoro attesta la presa visione e, quando previsto, l'approvazione del documento.",
            styles["CMNote"],
        ),
        Spacer(1, 5),
        _kv_table([
            ["Luogo", place],
            ["Data", report_date.strftime("%d/%m/%Y")],
        ]),
        Spacer(1, 14),
    ]

    signers = [("Firma lavoratore", f"{worker.first_name} {worker.last_name}", approval.get("worker_signature"))]
    if mode in {"employer", "both"}:
        employer_name = (
            f"{employer.first_name} {employer.last_name}"
            if employer
            else "Datore di lavoro non associato"
        )
        signers.append(("Firma datore di lavoro", employer_name, approval.get("employer_signature")))

    widths = [160 * mm] if len(signers) == 1 else [80 * mm, 80 * mm]
    cells = []
    for index, (label, name, signature_path) in enumerate(signers):
        signature = _signature_image(signature_path)
        body = [Paragraph(f"<b>{label}</b>", styles["CMCenter"]), Spacer(1, 5)]
        if signature:
            # ReportLab does not reliably honour Image.hAlign when the image is
            # a flowable directly inside a Table cell. Centre it explicitly in
            # a nested one-cell table spanning the usable signature-cell width.
            signature_box = Table([[signature]], colWidths=[widths[index] - 20])
            signature_box.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            body.extend([signature_box, Spacer(1, 3)])
        else:
            # Keep the signature area structurally identical even when no
            # stored signature image is available.  The centred placeholder
            # lives in a nested one-cell table, just like an actual signature,
            # so alignment is deterministic in ReportLab and remains easy to
            # verify in regression tests.
            placeholder = Paragraph("________________________________________", styles["CMCenter"])
            signature_box = Table([[placeholder]], colWidths=[widths[index] - 20])
            signature_box.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 13*mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            body.extend([signature_box, Spacer(1, 3)])
        body.append(Paragraph(f"<b>{name}</b>", styles["CMCenter"]))
        cells.append(body)
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


def _multi_worker_signature_story(workers, styles, worker_signatures=None, place="", report_date=None, report_year=None):
    workers = list(workers or [])
    worker_signatures = worker_signatures or {}
    report_date = report_date or date.today()
    story = _report_notes_story(styles, "annual_payments", report_year) + [
        Spacer(1, 10),
        Paragraph("Luogo, data e firme dei lavoratori", styles["CMSub"]),
        Paragraph(
            "Il prospetto riepiloga pagamenti riferiti a piu lavoratori. Ogni lavoratore puo apporre la firma per presa visione; quando una firma e registrata nell'applicazione viene inserita automaticamente.",
            styles["CMNote"],
        ),
        Spacer(1, 5),
        _kv_table([["Luogo", place or "____________________________"], ["Data", report_date.strftime("%d/%m/%Y")]]),
        Spacer(1, 10),
    ]
    if not workers:
        story.append(Paragraph("Nessun lavoratore presente nel report.", styles["CMNote"]))
        return story
    rows = []
    for worker in workers:
        signature = _signature_image(worker_signatures.get(worker.id))
        body = [Paragraph("<b>Firma lavoratore</b>", styles["CMCenter"]), Spacer(1, 4)]
        if signature:
            box = Table([[signature]], colWidths=[70*mm])
            box.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
            body.extend([box, Spacer(1, 3)])
        else:
            body.extend([Spacer(1, 10*mm), Paragraph("________________________________________", styles["CMCenter"])])
        body.append(Paragraph(f"<b>{worker.first_name} {worker.last_name}</b>", styles["CMCenter"]))
        rows.append([body])
    table = Table(rows, colWidths=[160*mm])
    table.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,LINE),("INNERGRID",(0,0),(-1,-1),0.35,LINE),("BACKGROUND",(0,0),(-1,-1),PALE),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),8)]))
    story.append(table)
    return story

def _permit_story(permits, styles):
    permits = list(permits or [])
    if not permits:
        return []
    rows = [["Categoria permesso", "Retr. mese", "Retr. anno", "Miglior favore", "Non retr. anno", "Residuo"]]
    for item in permits:
        remaining = "—" if item.get("remaining") is None else f"{item['remaining']} h"
        rows.append([
            item.get("label", item.get("category", "—")),
            f"{item.get('paid_month', 0)} h",
            f"{item.get('paid_year', 0)} h",
            f"{item.get('extra_paid_year', 0)} h",
            f"{item.get('unpaid_year', 0)} h",
            remaining,
        ])
    table = Table(rows, colWidths=[46*mm, 22*mm, 22*mm, 22*mm, 22*mm, 22*mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("PADDING", (0, 0), (-1, -1), 3),
    ]))
    return [Paragraph("Permessi", styles["CMSub"]), table, Paragraph("Le categorie del monte personale ex art. 19 condividono lo stesso plafond; lutto e nascita sono diritti per evento.", styles["CMNote"])]


def _sickness_story(sickness, styles):
    if not sickness:
        return []
    if not sickness.get("known", True):
        return [Paragraph("Malattia", styles["CMSub"]), Paragraph("Regola storica non codificata per il periodo selezionato.", styles["CMNote"])]
    rows = [
        ["Malattia", "Giorni"],
        ["Totale nel mese", str(sickness.get("total_month", 0))],
        ["Retribuiti nel mese", str(sickness.get("paid_month", 0))],
        ["Totale nell’anno", str(sickness.get("total_year", 0))],
        ["Retribuiti nell’anno", str(sickness.get("paid_year", 0))],
        ["Non retribuiti", str(sickness.get("total_year", 0) - sickness.get("paid_year", 0))],
        ["Limite contrattuale retribuito", str(sickness.get("paid_days_limit", 0))],
        ["Residuo contrattuale", str(sickness.get("legal_paid_remaining", 0))],
        ["Pagati oltre limite per miglior favore", str(sickness.get("extra_paid_year", 0))],
        ["Conservazione posto - limite", str(sickness.get("job_protection_days", 0))],
        ["Conservazione posto usata negli ultimi 365 giorni", str(sickness.get("job_protection_used_365", 0))],
        ["Conservazione posto residua negli ultimi 365 giorni", str(sickness.get("job_protection_remaining_365", 0))],
    ]
    return [Paragraph("Malattia", styles["CMSub"]), _kv_table(rows), Paragraph(str(sickness.get("source", "")), styles["CMNote"])]

def payroll_pdf(worker, summary, year, month, employer=None, vacation=None, fiscal=None, expenses=None, title="Cedolino mensile gestionale", approval=None, payments=None, permits=None, sickness=None):
    out, doc = _doc(title)
    s = _styles()
    story = [Paragraph(title, s["CMTitle"]), Paragraph(f"Periodo {month:02d}/{year}", s["CMSub"]), _party_block(worker, employer, s), Spacer(1, 7)]
    rows = [["Voce", "Valore"], ["Ore totali registrate", str(summary["worked_hours"])], ["Ore ordinarie", str(summary.get("ordinary_hours", 0))], ["Ore straordinarie", str(summary.get("overtime_hours", 0))], ["Ore non retribuite", str(summary.get("unpaid_work_hours", 0))], ["Retribuzione ore", _money(summary["worked_pay"])], ["Malattia / permessi / ferie retribuiti", _money(summary["paid_absence"])], ["Anticipi lavoratore da rimborsare", _money(summary["worker_advances"])], ["Anticipi datore da recuperare", _money(summary["employer_advances"])], ["Rettifica netta spese/anticipi", _money(summary["reimbursements"])], ["Retribuzione registrata", _money(summary["gross"])], ["Quota tredicesima maturata (stima)", _money(summary.get("thirteenth_accrual", 0))], ["Quota TFR maturata (stima)", _money(summary["tfr_accrual"])], ["Totale da corrispondere", _money(summary["payable"])]]
    story.append(_kv_table(rows))
    paid_salary = sum(
        (Decimal(p.amount) for p in (payments or []) if getattr(p, "status", "") == "paid" and getattr(p, "payment_type", "") == "salary"),
        Decimal("0"),
    )
    salary_residual = max(Decimal(summary["payable"]) - paid_salary, Decimal("0"))
    story += [Spacer(1, 7), Paragraph("Importo complessivo da pagare", s["CMSub"]), _amount_callout(summary["payable"], paid_salary, salary_residual, s)]
    vacation_notes = list(summary.get("vacation_payroll_notes") or [])
    if vacation_notes:
        story += [Paragraph("Note ferie e riporto retribuzione", s["CMSub"])]
        for note in vacation_notes:
            story.append(Paragraph(note, s["CMNote"]))
        story.append(Spacer(1, 5))
    if vacation:
        story += [Paragraph("Ferie", s["CMSub"]), _kv_table([["Situazione ferie", "Giorni"],["Maturate alla data", str(vacation["accrued"])],["Proiezione fine anno", str(vacation["projected"])],["Godute/programmate", str(vacation["used_scheduled"])],["Disponibili secondo impostazione", str(vacation["available_usable"])]])]
    story += _sickness_story(sickness, s)
    story += _permit_story(permits, s)
    story += _expense_story(expenses, s, date(year, month, monthrange(year, month)[1]))
    story += _fiscal_story(fiscal, s)
    story += _payment_story(payments, s, summary.get("payable"), due_types={"salary"})
    story += [Spacer(1, 10), Paragraph("Il presente documento è un prospetto gestionale. Verificare sempre contratto applicato, contributi INPS, minimi retributivi e normativa vigente per il periodo considerato.", s["CMNote"])]
    story += _signature_story(worker, employer, s, approval, "monthly_payroll", year)
    _build(doc, story)
    out.seek(0)
    return out


def annual_payroll_pdf(worker, employer, annual, year, vacation, fiscal=None, expenses=None, approval=None, payments=None, permits=None, sickness=None):
    out, doc = _doc("Cedolino globale annuale")
    s = _styles()
    story=[Paragraph("Cedolino globale annuale", s["CMTitle"]), Paragraph(str(year), s["CMSub"]), _party_block(worker, employer, s), Spacer(1,7)]
    rows=[["Mese","Ore","Retribuzione","Malattia/permessi/ferie","Spese nette","Da corrispondere"]]
    for i, m in enumerate(annual["months"], 1):
        rows.append([f"{i:02d}", str(m["worked_hours"]), _money(m["worked_pay"]), _money(m["paid_absence"]), _money(m["reimbursements"]), _money(m["payable"])])
    t=Table(rows,colWidths=[15*mm,25*mm,31*mm,31*mm,30*mm,32*mm],repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),BRAND),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,PALE]),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#c8d8d2")),("ALIGN",(1,1),(-1,-1),"RIGHT"),("FONTSIZE",(0,0),(-1,-1),7.2),("PADDING",(0,0),(-1,-1),4)]))
    story += [t, Paragraph("Totali annuali",s["CMSub"]), _kv_table([["Voce","Valore"],["Ore",str(annual["worked_hours"])],["Retribuzione registrata",_money(annual["gross"])],["Quota tredicesima maturata",_money(annual["thirteenth_accrual"])],["TFR maturato",_money(annual["tfr_accrual"])],["Totale corrispondibile registrato",_money(annual["payable"])]]), Paragraph("Ferie annuali",s["CMSub"]), _kv_table([["Ferie","Giorni"],["Maturate",str(vacation["accrued"])],["Maturabili entro 31/12",str(vacation["projected"])],["Godute/programmate",str(vacation["used_scheduled"])],["Disponibili",str(vacation["available_usable"])]]), Spacer(1,8), Paragraph("Prospetto gestionale annuale; non sostituisce gli adempimenti ufficiali.",s["CMNote"])]
    annual_paid_salary = sum(
        (Decimal(p.amount) for p in (payments or []) if getattr(p, "status", "") == "paid" and getattr(p, "payment_type", "") == "salary"),
        Decimal("0"),
    )
    annual_salary_residual = max(Decimal(annual["payable"]) - annual_paid_salary, Decimal("0"))
    story += [Spacer(1, 7), Paragraph("Importo complessivo annuale da pagare", s["CMSub"]), _amount_callout(annual["payable"], annual_paid_salary, annual_salary_residual, s)]
    story += _sickness_story(sickness, s)
    story += _permit_story(permits, s)
    story += _expense_story(expenses, s, date(year, 12, 31))
    story += _fiscal_story(fiscal, s)
    story += _payment_story(payments, s, annual.get("payable"), due_types={"salary"})
    story += _signature_story(worker, employer, s, approval, "annual_payroll", year)
    _build(doc, story)
    out.seek(0)
    return out


def courtesy_cu_pdf(worker, employer, annual, year, fiscal=None, approval=None, payments=None):
    out, doc = _doc("Certificazione retribuzioni / CU di cortesia")
    s=_styles()
    story=[Paragraph("Certificazione retribuzioni · CU di cortesia",s["CMTitle"]),Paragraph(f"Anno fiscale {year}",s["CMSub"]),_party_block(worker,employer,s),Spacer(1,7),_kv_table([["Dati riepilogativi","Importo"],["Retribuzione registrata",_money(annual["gross"])],["Quota tredicesima maturata",_money(annual["thirteenth_accrual"])],["Rimborsi/anticipi netti registrati",_money(annual["reimbursements"])],["TFR maturato nell'anno (informativo)",_money(annual["tfr_accrual"])]]),Spacer(1,10),Paragraph("Natura del documento",s["CMSub"]),Paragraph("Il datore di lavoro domestico privato normalmente non opera come sostituto d'imposta. Questo PDF è una certificazione di cortesia delle somme risultanti nell'applicazione e non è il modello CU telematico dell'Agenzia delle Entrate. I dati devono essere verificati prima dell'uso fiscale.",s["CMBody"]),Spacer(1,8),Paragraph(f"Generato il {date.today().strftime('%d/%m/%Y')}",s["CMNote"])]
    story += _fiscal_story(fiscal, s)
    story += _payment_story(payments, s)
    story += _signature_story(worker, employer, s, approval, "courtesy_cu", year)
    _build(doc, story)
    out.seek(0)
    return out


def tfr_annual_pdf(worker, employer, tfr, year, rule_notes, fiscal=None, approval=None, payments=None):
    out,doc=_doc("Prospetto TFR annuale")
    s=_styles()
    story=[Paragraph("Prospetto TFR annuale",s["CMTitle"]),Paragraph(f"Anno {year} · calcolo fino al {tfr['cutoff'].strftime('%d/%m/%Y')}",s["CMSub"]),_party_block(worker,employer,s),Spacer(1,7),_kv_table([["Calcolo quota annuale","Valore"],["Retribuzione registrata utile",_money(tfr["gross"])],["Quota tredicesima maturata",_money(tfr["thirteenth_accrual"])],["Base utile TFR stimata",_money(tfr["tfr_useful_compensation"])],["Divisore", "13,5"],["Quota TFR maturata nell'anno",_money(tfr["tfr_accrual"])]])]
    story += [Spacer(1,7),Paragraph(tfr["revaluation_note"],s["CMNote"]),Spacer(1,5),Paragraph("Il prospetto calcola la quota maturata nell'anno sui dati registrati. Eventuali anticipazioni, liquidazioni pregresse, rivalutazioni di quote precedenti e trattamento fiscale devono essere riconciliati prima del pagamento.",s["CMNote"])]
    story += _fiscal_story(fiscal, s)
    story += _payment_story(payments, s, tfr.get("tfr_accrual"), "Liquidazioni TFR", {"tfr"})
    story += _signature_story(worker, employer, s, approval, "tfr", year, rule_notes)
    _build(doc, story)
    out.seek(0)
    return out


def trend_pdf(worker, employer, annual, year, fiscal=None, expenses=None, approval=None, payments=None, permits=None, sickness=None):
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
    story += _sickness_story(sickness, s)
    story += _permit_story(permits, s)
    story += _signature_story(worker, employer, s, approval, "trend", year)
    _build(doc, story)
    out.seek(0)
    return out




def annual_payments_pdf(payments, workers, employers, year, worker_signatures=None, place=""):
    out, doc = _doc("Pagamenti effettuati nell'anno")
    s = _styles()
    worker_map = {worker.id: worker for worker in workers}
    employer_map = {employer.id: employer for employer in employers}
    labels = {
        "salary": "Retribuzione",
        "inps_contributions": "Contributi INPS",
        "thirteenth": "Tredicesima",
        "tfr": "TFR",
        "expense_refund": "Rimborso spese",
        "other": "Altro",
    }
    paid = [
        payment
        for payment in payments
        if payment.status == "paid"
        and payment.payment_date
        and payment.payment_date.year == year
    ]
    story = [
        Paragraph("Report complessivo dei pagamenti effettuati", s["CMTitle"]),
        Paragraph(f"Anno {year}", s["CMSub"]),
        Paragraph(
            "Il prospetto comprende esclusivamente i pagamenti marcati come pagati e con data di pagamento nell'anno selezionato.",
            s["CMBody"],
        ),
        Spacer(1, 7),
    ]
    by_type = {}
    for payment in paid:
        by_type[payment.payment_type] = by_type.get(payment.payment_type, Decimal("0")) + Decimal(payment.amount)
    totals = [["Categoria", "Totale pagato"]]
    for payment_type, amount in sorted(by_type.items(), key=lambda item: labels.get(item[0], item[0])):
        totals.append([labels.get(payment_type, payment_type), _money(amount)])
    grand_total = sum((Decimal(payment.amount) for payment in paid), Decimal("0"))
    totals.append(["Totale annuale", _money(grand_total)])
    story.extend([_kv_table(totals), Spacer(1, 9), Paragraph("Dettaglio pagamenti", s["CMSub"])])
    rows = [["Data", "Lavoratore", "Datore", "Categoria", "Modalità", "Importo", "Periodo"]]
    for payment in sorted(paid, key=lambda item: (item.payment_date, item.id)):
        worker = worker_map.get(payment.worker_id)
        employer = employer_map.get(payment.employer_id)
        worker_name = f"{worker.first_name} {worker.last_name}" if worker else "-"
        employer_name = f"{employer.first_name} {employer.last_name}" if employer else "-"
        period = "-"
        if payment.period_start:
            period = payment.period_start.strftime("%d/%m/%Y")
        if payment.period_end and payment.period_end != payment.period_start:
            period += " -> " + payment.period_end.strftime("%d/%m/%Y")
        rows.append([
            payment.payment_date.strftime("%d/%m/%Y"),
            worker_name,
            employer_name,
            labels.get(payment.payment_type, payment.payment_type),
            PAYMENT_METHOD_LABELS.get(
                getattr(payment, "payment_method", "bank_transfer"),
                getattr(payment, "payment_method", "bank_transfer"),
            ),
            _money(payment.amount),
            period,
        ])
    if len(rows) == 1:
        story.append(Paragraph("Nessun pagamento effettuato nell'anno selezionato.", s["CMNote"]))
    else:
        table = Table(
            rows,
            colWidths=[18*mm, 27*mm, 27*mm, 27*mm, 28*mm, 22*mm, 31*mm],
            repeatRows=1,
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
            ("GRID", (0, 0), (-1, -1), 0.3, LINE),
            ("ALIGN", (5, 1), (5, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 6.2),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(table)
    paid_worker_ids = {payment.worker_id for payment in paid if payment.worker_id is not None}
    signing_workers = [worker for worker in workers if worker.id in paid_worker_ids]
    story += _multi_worker_signature_story(
        signing_workers, s, worker_signatures, place, date.today(), year
    )
    _build(doc, story)
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
    story += _signature_story(worker, employer, s, approval, "location_trend", year)
    _build(doc, story)
    out.seek(0)
    return out

def thirteenth_payroll_pdf(worker, employer, thirteenth, year, rule_notes, fiscal=None, approval=None, payments=None):
    out, doc = _doc("Cedolino tredicesima")
    s = _styles()
    story = [Paragraph("Cedolino della tredicesima", s["CMTitle"]), Paragraph(f"Anno {year} · calcolo fino al {thirteenth['cutoff'].strftime('%d/%m/%Y')}", s["CMSub"]), _party_block(worker, employer, s), Spacer(1,7)]
    story += [_kv_table([["Calcolo tredicesima","Valore"],["Retribuzione utile registrata nel periodo",_money(thirteenth["gross"])],["Formula","Retribuzione utile / 12"],["Tredicesima maturata",_money(thirteenth["thirteenth"])]])]
    story += _fiscal_story(fiscal, s)
    story += _payment_story(payments, s, thirteenth.get("thirteenth"), "Liquidazioni tredicesima", {"thirteenth"})
    story += [Spacer(1,7), Paragraph("Documento gestionale: verificare minimi contrattuali, elementi retributivi utili e disciplina vigente prima del pagamento.",s["CMNote"])]
    story += _signature_story(worker, employer, s, approval, "thirteenth", year, rule_notes)
    _build(doc, story)
    out.seek(0)
    return out


def combined_thirteenth_tfr_pdf(worker, employer, combined, year, rule_notes, approval=None, payments=None):
    out, doc = _doc("Tredicesima + TFR")
    s = _styles()
    th = combined["thirteenth"]
    tfr = combined["tfr"]
    story=[Paragraph("Prospetto cumulativo tredicesima + TFR",s["CMTitle"]),Paragraph(f"Anno {year} · fino al {combined['cutoff'].strftime('%d/%m/%Y')}",s["CMSub"]),_party_block(worker,employer,s),Spacer(1,7),_kv_table([["Voce","Importo"],["Retribuzione utile registrata",_money(th["gross"])],["Tredicesima maturata (retribuzione / 12)",_money(th["thirteenth"])],["Base utile TFR stimata",_money(tfr["tfr_useful_compensation"])],["TFR maturato (base utile / 13,5)",_money(tfr["tfr_accrual"])],["Totale tredicesima + TFR",_money(th["thirteenth"]+tfr["tfr_accrual"])]])]
    story += _fiscal_story({"inps":combined.get("inps"),"taxes":combined.get("taxes")},s)
    story += [Paragraph(tfr["revaluation_note"],s["CMNote"]),Paragraph("Il totale non costituisce automaticamente importo netto da pagare: eventuali anticipi TFR, quote già liquidate, contribuzione e imposizione fiscale vanno riconciliati.",s["CMNote"])]
    story += _payment_story(payments, s, combined["thirteenth"]["thirteenth"] + combined["tfr"]["tfr_accrual"], "Liquidazioni tredicesima e TFR", {"thirteenth", "tfr"})
    story += _signature_story(worker, employer, s, approval, "thirteenth_tfr", year, rule_notes)
    _build(doc, story)
    out.seek(0)
    return out
