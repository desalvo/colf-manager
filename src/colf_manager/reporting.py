# fmt: off
from io import BytesIO
from datetime import date

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BRAND = colors.HexColor("#173f3a")
ACCENT = colors.HexColor("#287d70")
GOLD = colors.HexColor("#dfa63d")
PALE = colors.HexColor("#f3f7f5")
TEXT = colors.HexColor("#263c37")


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
    canvas.setFillColor(BRAND)
    canvas.rect(0, A4[1] - 13*mm, A4[0], 13*mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(18*mm, A4[1] - 8.5*mm, "COLF MANAGER")
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(A4[0]-18*mm, A4[1]-8.5*mm, "Documento gestionale riservato")
    canvas.setFillColor(colors.HexColor("#667873"))
    canvas.drawString(18*mm, 9*mm, "colf-manager · EUPL-1.2")
    canvas.drawRightString(A4[0]-18*mm, 9*mm, f"Pagina {doc.page}")
    canvas.restoreState()


def _doc(title):
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=17*mm, rightMargin=17*mm, topMargin=20*mm, bottomMargin=17*mm, title=title, author="colf-manager")
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




def _expense_story(expenses, styles):
    expenses = list(expenses or [])
    if not expenses:
        return []
    rows = [["Data", "Descrizione", "Sostenuta da", "Importo", "Stato"]]
    for expense in sorted(expenses, key=lambda item: item.expense_date):
        owner = "Lavoratore" if expense.direction == "worker_advance" else "Datore di lavoro"
        rows.append([
            expense.expense_date.strftime("%d/%m/%Y"),
            expense.description,
            owner,
            _money(expense.amount),
            "Regolata" if expense.reimbursed else "Da regolare",
        ])
    table = Table(rows, colWidths=[24*mm, 62*mm, 34*mm, 24*mm, 25*mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c8d8d2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.3),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    return [Paragraph("Spese e rimborsi del periodo", styles["CMSub"]), table]

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
        signers.append(("Firma lavoratore", f"{worker.first_name} {worker.last_name}"))
    if mode in {"employer", "both"}:
        employer_name = (
            f"{employer.first_name} {employer.last_name}"
            if employer
            else "Datore di lavoro non associato"
        )
        signers.append(("Firma datore di lavoro", employer_name))

    cells = []
    for label, name in signers:
        cells.append(
            Paragraph(
                f"<b>{label}</b><br/><br/><br/>"
                "________________________________________<br/>"
                f"<b>{name}</b>",
                styles["CMCenter"],
            )
        )
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

def payroll_pdf(worker, summary, year, month, employer=None, vacation=None, fiscal=None, expenses=None, title="Cedolino mensile gestionale", approval=None):
    out, doc = _doc(title)
    s = _styles()
    story = [Paragraph(title, s["CMTitle"]), Paragraph(f"Periodo {month:02d}/{year}", s["CMSub"]), _party_block(worker, employer, s), Spacer(1, 7)]
    rows = [["Voce", "Valore"], ["Ore lavorate", str(summary["worked_hours"])], ["Retribuzione ore", _money(summary["worked_pay"])], ["Assenze retribuite / ferie / malattia", _money(summary["paid_absence"])], ["Anticipi lavoratore da rimborsare", _money(summary["worker_advances"])], ["Anticipi datore da recuperare", _money(summary["employer_advances"])], ["Rettifica netta spese/anticipi", _money(summary["reimbursements"])], ["Retribuzione registrata", _money(summary["gross"])], ["Quota tredicesima maturata (stima)", _money(summary.get("thirteenth_accrual", 0))], ["Quota TFR maturata (stima)", _money(summary["tfr_accrual"])], ["Totale da corrispondere", _money(summary["payable"])]]
    story.append(_kv_table(rows))
    if vacation:
        story += [Paragraph("Ferie", s["CMSub"]), _kv_table([["Situazione ferie", "Giorni"],["Maturate alla data", str(vacation["accrued"])],["Proiezione fine anno", str(vacation["projected"])],["Godute/programmate", str(vacation["used_scheduled"])],["Disponibili secondo impostazione", str(vacation["available_usable"])]])]
    story += _expense_story(expenses, s)
    story += _fiscal_story(fiscal, s)
    story += [Spacer(1, 10), Paragraph("Il presente documento è un prospetto gestionale. Verificare sempre contratto applicato, contributi INPS, minimi retributivi e normativa vigente per il periodo considerato.", s["CMNote"])]
    story += _signature_story(worker, employer, s, approval)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    out.seek(0)
    return out


def annual_payroll_pdf(worker, employer, annual, year, vacation, fiscal=None, expenses=None, approval=None):
    out, doc = _doc("Cedolino globale annuale")
    s = _styles()
    story=[Paragraph("Cedolino globale annuale", s["CMTitle"]), Paragraph(str(year), s["CMSub"]), _party_block(worker, employer, s), Spacer(1,7)]
    rows=[["Mese","Ore","Retribuzione","Assenze","Spese nette","Da corrispondere"]]
    for i, m in enumerate(annual["months"], 1):
        rows.append([f"{i:02d}", str(m["worked_hours"]), _money(m["worked_pay"]), _money(m["paid_absence"]), _money(m["reimbursements"]), _money(m["payable"])])
    t=Table(rows,colWidths=[15*mm,25*mm,31*mm,31*mm,30*mm,32*mm],repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),BRAND),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,PALE]),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#c8d8d2")),("ALIGN",(1,1),(-1,-1),"RIGHT"),("FONTSIZE",(0,0),(-1,-1),7.2),("PADDING",(0,0),(-1,-1),4)]))
    story += [t, Paragraph("Totali annuali",s["CMSub"]), _kv_table([["Voce","Valore"],["Ore",str(annual["worked_hours"])],["Retribuzione registrata",_money(annual["gross"])],["Quota tredicesima maturata",_money(annual["thirteenth_accrual"])],["TFR maturato",_money(annual["tfr_accrual"])],["Totale corrispondibile registrato",_money(annual["payable"])]]), Paragraph("Ferie annuali",s["CMSub"]), _kv_table([["Ferie","Giorni"],["Maturate",str(vacation["accrued"])],["Maturabili entro 31/12",str(vacation["projected"])],["Godute/programmate",str(vacation["used_scheduled"])],["Disponibili",str(vacation["available_usable"])]]), Spacer(1,8), Paragraph("Prospetto gestionale annuale; non sostituisce gli adempimenti ufficiali.",s["CMNote"])]
    story += _expense_story(expenses, s)
    story += _fiscal_story(fiscal, s)
    story += _signature_story(worker, employer, s, approval)
    doc.build(story,onFirstPage=_footer,onLaterPages=_footer)
    out.seek(0)
    return out


def courtesy_cu_pdf(worker, employer, annual, year, fiscal=None, approval=None):
    out, doc = _doc("Certificazione retribuzioni / CU di cortesia")
    s=_styles()
    story=[Paragraph("Certificazione retribuzioni · CU di cortesia",s["CMTitle"]),Paragraph(f"Anno fiscale {year}",s["CMSub"]),_party_block(worker,employer,s),Spacer(1,7),_kv_table([["Dati riepilogativi","Importo"],["Retribuzione registrata",_money(annual["gross"])],["Quota tredicesima maturata",_money(annual["thirteenth_accrual"])],["Rimborsi/anticipi netti registrati",_money(annual["reimbursements"])],["TFR maturato nell'anno (informativo)",_money(annual["tfr_accrual"])]]),Spacer(1,10),Paragraph("Natura del documento",s["CMSub"]),Paragraph("Il datore di lavoro domestico privato normalmente non opera come sostituto d'imposta. Questo PDF è una certificazione di cortesia delle somme risultanti nell'applicazione e non è il modello CU telematico dell'Agenzia delle Entrate. I dati devono essere verificati prima dell'uso fiscale.",s["CMBody"]),Spacer(1,8),Paragraph(f"Generato il {date.today().strftime('%d/%m/%Y')}",s["CMNote"])]
    story += _fiscal_story(fiscal, s)
    story += _signature_story(worker, employer, s, approval)
    doc.build(story,onFirstPage=_footer,onLaterPages=_footer)
    out.seek(0)
    return out


def tfr_annual_pdf(worker, employer, tfr, year, rule_notes, fiscal=None, approval=None):
    out,doc=_doc("Prospetto TFR annuale")
    s=_styles()
    story=[Paragraph("Prospetto TFR annuale",s["CMTitle"]),Paragraph(f"Anno {year} · calcolo fino al {tfr['cutoff'].strftime('%d/%m/%Y')}",s["CMSub"]),_party_block(worker,employer,s),Spacer(1,7),_kv_table([["Calcolo quota annuale","Valore"],["Retribuzione registrata utile",_money(tfr["gross"])],["Quota tredicesima maturata",_money(tfr["thirteenth_accrual"])],["Base utile TFR stimata",_money(tfr["tfr_useful_compensation"])],["Divisore", "13,5"],["Quota TFR maturata nell'anno",_money(tfr["tfr_accrual"])]]),Paragraph("Regole applicate",s["CMSub"])]
    for note in rule_notes:
        story.append(Paragraph("• " + note, s["CMBody"]))
    story += [Spacer(1,7),Paragraph(tfr["revaluation_note"],s["CMNote"]),Spacer(1,5),Paragraph("Il prospetto calcola la quota maturata nell'anno sui dati registrati. Eventuali anticipazioni, liquidazioni pregresse, rivalutazioni di quote precedenti e trattamento fiscale devono essere riconciliati prima del pagamento.",s["CMNote"])]
    story += _fiscal_story(fiscal, s)
    story += _signature_story(worker, employer, s, approval)
    doc.build(story,onFirstPage=_footer,onLaterPages=_footer)
    out.seek(0)
    return out


def trend_pdf(worker, employer, annual, year, fiscal=None, expenses=None, approval=None):
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
    story += _expense_story(expenses, s)
    story += _fiscal_story(fiscal, s)
    story += _signature_story(worker, employer, s, approval)
    doc.build(story,onFirstPage=_footer,onLaterPages=_footer)
    out.seek(0)
    return out



def thirteenth_payroll_pdf(worker, employer, thirteenth, year, rule_notes, fiscal=None, approval=None):
    out, doc = _doc("Cedolino tredicesima")
    s = _styles()
    story = [Paragraph("Cedolino della tredicesima", s["CMTitle"]), Paragraph(f"Anno {year} · calcolo fino al {thirteenth['cutoff'].strftime('%d/%m/%Y')}", s["CMSub"]), _party_block(worker, employer, s), Spacer(1,7)]
    story += [_kv_table([["Calcolo tredicesima","Valore"],["Retribuzione utile registrata nel periodo",_money(thirteenth["gross"])],["Formula","Retribuzione utile / 12"],["Tredicesima maturata",_money(thirteenth["thirteenth"])]]), Paragraph("Metodo di calcolo", s["CMSub"]), Paragraph("La tredicesima del lavoro domestico corrisponde a un dodicesimo della retribuzione annua utile. Per un rapporto iniziato o cessato nell'anno, il valore riflette il periodo e le retribuzioni registrate nell'applicazione. La tredicesima matura anche nei periodi tutelati previsti dalla disciplina applicabile, entro i relativi limiti.", s["CMBody"])]
    for note in rule_notes:
        story.append(Paragraph("• " + note, s["CMBody"]))
    story += _fiscal_story(fiscal, s)
    story += [Spacer(1,7), Paragraph("Documento gestionale: verificare minimi contrattuali, elementi retributivi utili e disciplina vigente prima del pagamento.",s["CMNote"])]
    story += _signature_story(worker, employer, s, approval)
    doc.build(story,onFirstPage=_footer,onLaterPages=_footer)
    out.seek(0)
    return out


def combined_thirteenth_tfr_pdf(worker, employer, combined, year, rule_notes, approval=None):
    out, doc = _doc("Tredicesima + TFR")
    s = _styles()
    th = combined["thirteenth"]
    tfr = combined["tfr"]
    story=[Paragraph("Prospetto cumulativo tredicesima + TFR",s["CMTitle"]),Paragraph(f"Anno {year} · fino al {combined['cutoff'].strftime('%d/%m/%Y')}",s["CMSub"]),_party_block(worker,employer,s),Spacer(1,7),_kv_table([["Voce","Importo"],["Retribuzione utile registrata",_money(th["gross"])],["Tredicesima maturata (retribuzione / 12)",_money(th["thirteenth"])],["Base utile TFR stimata",_money(tfr["tfr_useful_compensation"])],["TFR maturato (base utile / 13,5)",_money(tfr["tfr_accrual"])],["Totale tredicesima + TFR",_money(th["thirteenth"]+tfr["tfr_accrual"])]]),Paragraph("Descrizione dei calcoli",s["CMSub"]),Paragraph(f"Tredicesima: {th['gross']} / 12 = {th['thirteenth']}. TFR: base utile {tfr['tfr_useful_compensation']} / 13,5 = {tfr['tfr_accrual']}. Il periodo termina il {combined['cutoff'].strftime('%d/%m/%Y')}.",s["CMBody"])]
    for note in rule_notes:
        story.append(Paragraph("• " + note, s["CMBody"]))
    story += _fiscal_story({"inps":combined.get("inps"),"taxes":combined.get("taxes")},s)
    story += [Paragraph(tfr["revaluation_note"],s["CMNote"]),Paragraph("Il totale non costituisce automaticamente importo netto da pagare: eventuali anticipi TFR, quote già liquidate, contribuzione e imposizione fiscale vanno riconciliati.",s["CMNote"])]
    story += _signature_story(worker, employer, s, approval)
    doc.build(story,onFirstPage=_footer,onLaterPages=_footer)
    out.seek(0)
    return out
