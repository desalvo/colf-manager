#!/usr/bin/env python3

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageTemplate,
    Paragraph,
    Spacer,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf"
LOGO = ROOT / "src" / "colf_manager" / "static" / "logo.png"
OUT.mkdir(parents=True, exist_ok=True)


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#173f3a"))
    canvas.rect(0, A4[1] - 23 * mm, A4[0], 23 * mm, fill=1, stroke=0)
    canvas.drawImage(
        ImageReader(str(LOGO)),
        18 * mm,
        A4[1] - 19 * mm,
        12 * mm,
        12 * mm,
        mask="auto",
    )
    canvas.setFillColor(colors.HexColor("#f7f1e8"))
    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawString(33 * mm, A4[1] - 14 * mm, "colf-manager")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(
        A4[0] - 18 * mm,
        A4[1] - 14 * mm,
        "1.0.0 · Alessandro De Salvo",
    )
    canvas.setFillColor(colors.HexColor("#667873"))
    canvas.drawRightString(A4[0] - 18 * mm, 11 * mm, str(doc.page))
    canvas.restoreState()


def build(lang):
    source = ROOT / "docs" / f"MANUAL.{lang}.md"
    target = OUT / f"colf-manager-manual-v1.0.0-{lang}.pdf"
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CMTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=29,
            textColor=colors.HexColor("#173f3a"),
            spaceAfter=4 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CMH2",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=colors.HexColor("#287d70"),
            spaceBefore=2.5 * mm,
            spaceAfter=1 * mm,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CMBody",
            parent=styles["BodyText"],
            fontSize=8.5,
            leading=10.6,
            textColor=colors.HexColor("#263c37"),
            alignment=TA_LEFT,
            spaceAfter=0.9 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CMBullet",
            parent=styles["CMBody"],
            leftIndent=5 * mm,
            firstLineIndent=-3 * mm,
            bulletIndent=0,
        )
    )
    doc = BaseDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=31 * mm,
        bottomMargin=20 * mm,
    )
    doc.addPageTemplates(
        PageTemplate(
            id="main",
            frames=[
                Frame(
                    doc.leftMargin,
                    doc.bottomMargin,
                    doc.width,
                    doc.height,
                    id="body",
                )
            ],
            onPage=header_footer,
        )
    )
    story = []
    for line in source.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            story.append(Spacer(1, 0.8 * mm))
            continue
        clean = re.sub(
            r"`([^`]+)`",
            r"<font name='Courier'>\1</font>",
            line,
        )
        if line.startswith("# "):
            img = Image(str(LOGO), width=32 * mm, height=32 * mm)
            img.hAlign = "LEFT"
            story.extend(
                [
                    img,
                    Spacer(1, 2 * mm),
                    Paragraph(clean[2:], styles["CMTitle"]),
                ]
            )
        elif line.startswith("## "):
            story.append(Paragraph(clean[3:], styles["CMH2"]))
        elif line.startswith("- "):
            story.append(Paragraph("• " + clean[2:], styles["CMBullet"]))
        else:
            story.append(Paragraph(clean, styles["CMBody"]))
    doc.build(story)
    return target


if __name__ == "__main__":
    for language in ("it", "en"):
        print(build(language))
