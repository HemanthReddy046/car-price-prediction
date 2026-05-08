from datetime import datetime
from io import BytesIO
from typing import Dict

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def generate_pdf_report(prediction_id: str, data: Dict[str, str]) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer)
    styles = getSampleStyleSheet()

    content = []
    content.append(Paragraph("Car Price Prediction Report", styles["Title"]))
    content.append(Spacer(1, 10))
    content.append(Paragraph(f"Prediction ID: {prediction_id}", styles["Normal"]))

    for key, value in data.items():
        content.append(Paragraph(f"{key}: {value}", styles["Normal"]))

    doc.build(content)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def build_prediction_report_pdf(
    user_email: str,
    input_data: Dict[str, str],
    predicted_price: float,
    recommended_price: float,
    prediction_id: str = "N/A",
    generated_at: str | None = None,
) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        textColor=colors.HexColor("#1f3b73"),
        spaceAfter=12,
    )
    section_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor("#243b55"),
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=14,
    )
    sub_section_style = ParagraphStyle(
        "SubSectionHeading",
        parent=styles["Heading4"],
        fontName="Helvetica-Bold",
        fontSize=10.8,
        textColor=colors.HexColor("#1f2937"),
        spaceAfter=4,
    )

    def format_value(key: str, value: str) -> str:
        if key == "Kilometers_Driven":
            return f"{int(float(value)):,} km"
        if key == "Mileage":
            return f"{float(value):.1f} km/l"
        if key == "Engine":
            return f"{int(float(value))} CC"
        if key == "Power":
            return f"{int(float(value))} bhp"
        if key == "Accidents":
            count = int(float(value))
            suffix = "No Accidents" if count == 0 else "Reported"
            return f"{count} ({suffix})"
        return value

    negotiation_low = predicted_price * 0.90
    negotiation_high = predicted_price * 1.05
    now_text = generated_at or datetime.now().strftime("%d %b %Y, %I:%M %p")

    story = [
        Paragraph("CAR PRICE PREDICTION REPORT", title_style),
        Spacer(1, 6),
        Paragraph(f"Prediction ID: <b>{prediction_id}</b>", body_style),
        Paragraph(f"User: <b>{user_email}</b>", body_style),
        Paragraph(f"Generated On: <b>{now_text}</b>", body_style),
        Spacer(1, 6),
        HRFlowable(width="100%", color=colors.HexColor("#cbd5e1"), thickness=0.8),
        Spacer(1, 12),
    ]

    basic_data = [
        ["Brand", format_value("Brand", input_data.get("Brand", "N/A"))],
        ["Model", format_value("Model", input_data.get("Model", "N/A"))],
        ["Fuel Type", format_value("Fuel_Type", input_data.get("Fuel_Type", "N/A"))],
        ["Transmission", format_value("Transmission", input_data.get("Transmission", "N/A"))],
    ]
    ownership_data = [
        ["Owner Type", format_value("Owner_Type", input_data.get("Owner_Type", "N/A"))],
        ["Location", format_value("Location", input_data.get("Location", "N/A"))],
        ["Accidents", format_value("Accidents", input_data.get("Accidents", "0"))],
    ]
    specs_data = [
        [
            "Manufacturing Year",
            format_value("Manufacturing_Year", input_data.get("Manufacturing_Year", "N/A")),
        ],
        [
            "Kilometers Driven",
            format_value("Kilometers_Driven", input_data.get("Kilometers_Driven", "0")),
        ],
        ["Mileage", format_value("Mileage", input_data.get("Mileage", "0"))],
        ["Engine", format_value("Engine", input_data.get("Engine", "0"))],
        ["Power", format_value("Power", input_data.get("Power", "0"))],
        ["Seats", format_value("Seats", input_data.get("Seats", "N/A"))],
    ]

    def styled_table(rows: list[list[str]]) -> Table:
        table = Table(rows, colWidths=[5.2 * cm, 10.8 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f7f9fc")]),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1f2937")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cfd8e3")),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        return table

    story.extend(
        [
            Paragraph("CAR DETAILS", section_style),
            Paragraph("Basic Information", sub_section_style),
            styled_table(basic_data),
            Spacer(1, 8),
            Paragraph("Ownership & Condition", sub_section_style),
            styled_table(ownership_data),
            Spacer(1, 8),
            Paragraph("Specifications", sub_section_style),
            styled_table(specs_data),
            Spacer(1, 10),
            HRFlowable(width="100%", color=colors.HexColor("#cbd5e1"), thickness=0.8),
            Spacer(1, 10),
        ]
    )

    price_data = [
        ["Predicted Price", f"INR {predicted_price:.2f} Lakhs"],
        ["Recommended Price", f"INR {recommended_price:.2f} Lakhs"],
        ["Negotiation Range", f"INR {negotiation_low:.2f} - INR {negotiation_high:.2f} Lakhs"],
    ]
    price_table = Table(price_data, colWidths=[5.2 * cm, 10.8 * cm])
    price_table.setStyle(
        TableStyle(
            [
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#ecfdf3"), colors.white]),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
                ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#bfdbfe")),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend(
        [
            Paragraph("PRICE SUMMARY", section_style),
            price_table,
            Spacer(1, 10),
            Paragraph("INSIGHT", section_style),
            Paragraph(
                "This price estimation is generated using trained Machine Learning models, "
                "considering market trends, vehicle condition, and specifications.",
                body_style,
            ),
            Spacer(1, 6),
            Paragraph("Thanking you User, Have a Great Day.", body_style),
        ]
    )
    document.build(story)

    buffer.seek(0)
    return buffer.read()
