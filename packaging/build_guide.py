"""Render the PDF from the editable HTML user guide."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/assets/User Guide.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)
pdfmetrics.registerFont(TTFont("Segoe", "C:/Windows/Fonts/segoeui.ttf"))
pdfmetrics.registerFont(TTFont("SegoeBold", "C:/Windows/Fonts/segoeuib.ttf"))
pdfmetrics.registerFontFamily("Segoe", normal="Segoe", bold="SegoeBold", italic="Segoe", boldItalic="SegoeBold")
INK, ORANGE, MUTED = colors.HexColor("#303030"), colors.HexColor("#db7c20"), colors.HexColor("#656565")
styles = {
    "title": ParagraphStyle("title", fontName="SegoeBold", fontSize=26, leading=31, textColor=INK, spaceAfter=14),
    "intro": ParagraphStyle("intro", fontName="Segoe", fontSize=12, leading=18, textColor=MUTED, spaceAfter=14),
    "h2": ParagraphStyle("h2", fontName="SegoeBold", fontSize=13, leading=17, textColor=INK, spaceBefore=10, spaceAfter=7),
    "body": ParagraphStyle("body", fontName="Segoe", fontSize=10.5, leading=15, textColor=INK, spaceAfter=6),
    "step": ParagraphStyle("step", fontName="Segoe", fontSize=10.5, leading=15, textColor=INK, leftIndent=18, firstLineIndent=-18, spaceAfter=7),
    "small": ParagraphStyle("small", fontName="Segoe", fontSize=9, leading=13, textColor=MUTED, spaceAfter=6),
    "cell": ParagraphStyle("cell", fontName="Segoe", fontSize=9.5, leading=14, textColor=INK),
}

SOURCE_HTML = ROOT / "docs/assets/User Guide.html"


def read_guide():
    """Use the hand-edited HTML as the source for the matching PDF."""
    import re
    from html import unescape

    source = SOURCE_HTML.read_text(encoding="utf-8")
    results = []
    for section in re.findall(r"<section>(.*?)</section>", source, re.S | re.I):
        kicker = unescape(re.search(r'<p class="kicker">(.*?)</p>', section, re.S | re.I).group(1).strip())
        title = unescape(re.search(r"<h1>(.*?)</h1>", section, re.S | re.I).group(1).strip())
        contents = []
        for match in re.finditer(r'<table>.*?</table>|<h2[^>]*>.*?</h2>|<p[^>]*>.*?</p>', section, re.S | re.I):
            tag = match.group(0)
            if tag.lower().startswith("<table"):
                rows = []
                for row in re.findall(r"<tr>(.*?)</tr>", tag, re.S | re.I):
                    rows.append([unescape(cell.strip()) for cell in re.findall(r"<td>(.*?)</td>", row, re.S | re.I)])
                contents.append(("table", rows))
            elif tag.lower().startswith("<h2"):
                contents.append(("h2", unescape(re.sub(r"^<h2[^>]*>|</h2>$", "", tag, flags=re.I).strip())))
            else:
                style = re.search(r'class="([^"]+)"', tag).group(1)
                if style == "kicker":
                    continue
                contents.append((style, unescape(re.sub(r"^<p[^>]*>|</p>$", "", tag, flags=re.I).strip())))
        results.append((title, kicker, contents))
    if len(results) != 4:
        raise ValueError("User Guide.html must contain four guide sections.")
    return results


pages = read_guide()


def page_chrome(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(ORANGE)
    canvas.rect(0, height-10, width, 10, fill=1, stroke=0)
    canvas.setFont("SegoeBold", 9)
    canvas.setFillColor(INK)
    canvas.drawString(48, height-37, "TVPAINT / LAYER EXPORTER")
    canvas.setStrokeColor(colors.HexColor("#dddddd"))
    canvas.line(48, 42, width-48, 42)
    canvas.setFont("Segoe", 9)
    canvas.setFillColor(MUTED)
    canvas.drawString(48, 27, "by Fabien Glasse")
    canvas.drawRightString(width-48, 27, f"{doc.page} / 4")
    canvas.restoreState()


story = []
for index, (title, kicker, sections) in enumerate(pages):
    if index:
        story.append(PageBreak())
    story += [Paragraph(kicker, styles["small"]), Paragraph(title, styles["title"])]
    for kind, content in sections:
        if kind == "table":
            cells = [[Paragraph(f'<b>{text}</b>' if row == 0 else text, styles['cell']) for text in values] for row, values in enumerate(content)]
            table = Table(cells, colWidths=[137, A4[0]-96-137], hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f3e5d6')),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f6f6f6'), colors.white]),
                ('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING',(0,0),(-1,-1),10),
                ('RIGHTPADDING',(0,0),(-1,-1),10), ('TOPPADDING',(0,0),(-1,-1),8),
                ('BOTTOMPADDING',(0,0),(-1,-1),8),
            ]))
            story += [table, Spacer(1, 6)]
        else:
            story.append(Paragraph(content, styles[kind]))

doc = SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=48, leftMargin=48, topMargin=61, bottomMargin=57,
                        title="TVPaint Layer Exporter - User Guide", author="Fabien Glasse")
doc.build(story, onFirstPage=page_chrome, onLaterPages=page_chrome)
print(OUT)
