from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def payroll_pdf(worker, summary, year, month, title="Prospetto paga di supporto"):
    out = BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("COLF MANAGER", styles["Title"]),
        Paragraph(title, styles["Heading1"]),
        Paragraph(
            f"{worker.first_name} {worker.last_name} - {month:02d}/{year}", styles["Heading2"]
        ),
        Spacer(1, 8),
    ]
    rows = [
        ["Voce", "Valore"],
        ["Ore lavorate", str(summary["worked_hours"])],
        ["Retribuzione ore", f"€ {summary['worked_pay']}"],
        ["Assenze retribuite", f"€ {summary['paid_absence']}"],
        ["Rimborsi", f"€ {summary['reimbursements']}"],
        ["Lordo registrato", f"€ {summary['gross']}"],
        ["Accantonamento TFR stimato", f"€ {summary['tfr_accrual']}"],
        ["Totale da corrispondere", f"€ {summary['payable']}"],
    ]
    table = Table(rows, colWidths=[110 * mm, 50 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173f3a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d8d2")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f7f5")]),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story += [
        table,
        Spacer(1, 14),
        Paragraph(
            "Documento gestionale non sostitutivo del cedolino, delle comunicazioni o dei versamenti dovuti. Verificare CCNL, INPS e normativa applicabile alla data di pagamento.",
            styles["BodyText"],
        ),
    ]
    doc.build(story)
    out.seek(0)
    return out
