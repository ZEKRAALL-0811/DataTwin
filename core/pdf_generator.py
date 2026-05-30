import io
import re
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

def generate_pdf_report(dataset_name: str, health_score: int, insights: list, data_story: str, forecast_summary: str = None) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=50, leftMargin=50,
                            topMargin=50, bottomMargin=50)

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=colors.HexColor("#16213e"),
        spaceAfter=10,
    )
    
    subtitle_style = ParagraphStyle(
        "SubtitleStyle",
        parent=styles["Heading3"],
        fontSize=12,
        textColor=colors.HexColor("#00f5d4"),
        spaceAfter=20,
    )

    heading_style = ParagraphStyle(
        "HeadingStyle",
        parent=styles["Heading2"],
        fontSize=16,
        textColor=colors.HexColor("#16213e"),
        spaceBefore=20,
        spaceAfter=10,
    )

    body_style = ParagraphStyle(
        "BodyStyle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#333333"),
        spaceAfter=8,
        leading=16,
    )
    
    bullet_style = ParagraphStyle(
        "BulletStyle",
        parent=body_style,
        leftIndent=20,
        firstLineIndent=-10,
    )

    story_style = ParagraphStyle(
        "StoryStyle",
        parent=body_style,
        leftIndent=15,
        rightIndent=15,
        textColor=colors.HexColor("#2a2a2a"),
        backColor=colors.HexColor("#f8f9fa"),
        borderPadding=10,
    )

    elements = []

    # 1. Header
    elements.append(Paragraph("<b>DataTwin</b>", subtitle_style))
    elements.append(Paragraph("Executive Data Report", title_style))
    elements.append(Paragraph(f"<b>Dataset:</b> {dataset_name}", body_style))
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#00f5d4"), spaceAfter=20))

    # 2. Health Score
    elements.append(Paragraph("Data Health", heading_style))
    hs_color = "#00f5d4" if health_score >= 75 else ("#ffd93d" if health_score >= 50 else "#ff6b6b")
    elements.append(Paragraph(f"<b>Overall Score:</b> <font color='{hs_color}'><b>{health_score}/100</b></font>", body_style))
    elements.append(Spacer(1, 10))

    def clean_html(raw_html):
        # Remove standard HTML tags
        cleanr = re.compile('<.*?>')
        cleantext = re.sub(cleanr, '', raw_html)
        # Remove emojis which cause rendering issues in default reportlab fonts
        return cleantext.replace('📊', '').replace('✅', '').replace('⚠️', '').replace('📌', '').replace('🚨', '').replace('📈', '').replace('📉', '').replace('➡️', '').replace('💡', '').replace('🌊', '').replace('📐', '').strip()

    # 3. Insights
    if insights:
        elements.append(Paragraph("Key Insights", heading_style))
        for insight in insights:
            parts = insight.split("<br>")
            for part in parts:
                clean_part = clean_html(part)
                if clean_part:
                    elements.append(Paragraph(f"• {clean_part}", bullet_style))
        elements.append(Spacer(1, 15))

    # 4. Data Story
    if data_story:
        elements.append(Paragraph("Data Story Narrative", heading_style))
        for p in data_story.split("\n\n"):
            clean_p = clean_html(p)
            if clean_p:
                elements.append(Paragraph(clean_p, story_style))
                elements.append(Spacer(1, 5))
        elements.append(Spacer(1, 15))

    # 5. Forecast Summary
    if forecast_summary:
        elements.append(Paragraph("Forecast Summary", heading_style))
        for p in forecast_summary.split("<br>"):
            clean_p = clean_html(p)
            if clean_p:
                elements.append(Paragraph(f"• {clean_p}", bullet_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
