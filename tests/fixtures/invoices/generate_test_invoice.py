#!/usr/bin/env python3
"""
Generate a synthetic test invoice PDF for E2E testing.
"""

import os
from datetime import date
from decimal import Decimal

try:
    from fpdf import FPDF
except ImportError:
    import subprocess

    subprocess.check_call(["pip", "install", "fpdf2"])
    from fpdf import FPDF


class InvoicePDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, "FACTURA DE PROVEEDOR", ln=True, align="C")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5, "STAGING SUPPLIER TEST", ln=True, align="C")
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Pagina {self.page_no()}/{{nb}}", align="C")


def generate_test_invoice():
    """Generate a synthetic test invoice PDF."""
    pdf = InvoicePDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    # Supplier info
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "DATOS DEL PROVEEDOR:", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "Nombre: STAGING SUPPLIER TEST", ln=True)
    pdf.cell(0, 5, "CIF/NIF: B99999999", ln=True)
    pdf.cell(0, 5, "Direccion: Calle Test 123, 28001 Madrid", ln=True)
    pdf.ln(5)

    # Invoice info
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "DATOS DE LA FACTURA:", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "Numero: STAGING-INV-001", ln=True)
    pdf.cell(0, 5, f"Fecha: {date.today().strftime('%Y-%m-%d')}", ln=True)
    pdf.cell(0, 5, "Vencimiento: 2026-09-15", ln=True)
    pdf.ln(5)

    # Lines header
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(200, 220, 255)
    col_widths = [80, 20, 30, 30, 30]
    headers = ["Concepto", "Cant.", "Precio U.", "IVA %", "Total"]
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 7, h, border=1, fill=True, align="C")
    pdf.ln()

    # Lines
    pdf.set_font("Helvetica", "", 9)
    lines = [
        ("Servicios veterinarios consultoria", 1, Decimal("100.00"), 21),
        ("Pienso premium perro 15kg", 2, Decimal("25.00"), 21),
        ("Collar antiparasitario", 3, Decimal("12.00"), 21),
    ]

    subtotal = Decimal("0")
    vat_total = Decimal("0")

    for desc, qty, price, vat_rate in lines:
        line_total = price * qty
        vat_amount = line_total * Decimal(vat_rate) / Decimal("100")
        total_with_vat = line_total + vat_amount
        subtotal += line_total
        vat_total += vat_amount

        pdf.cell(col_widths[0], 6, desc, border=1)
        pdf.cell(col_widths[1], 6, str(qty), border=1, align="C")
        pdf.cell(col_widths[2], 6, f"{price:.2f} EUR", border=1, align="R")
        pdf.cell(col_widths[3], 6, f"{vat_rate}%", border=1, align="C")
        pdf.cell(col_widths[4], 6, f"{total_with_vat:.2f} EUR", border=1, align="R")
        pdf.ln()

    # Totals
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(sum(col_widths[:-1]), 6, "SUBTOTAL (Base imponible):", border=1, align="R")
    pdf.cell(col_widths[-1], 6, f"{subtotal:.2f} EUR", border=1, align="R")
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    pdf.cell(sum(col_widths[:-1]), 6, "IVA (21%):", border=1, align="R")
    pdf.cell(col_widths[-1], 6, f"{vat_total:.2f} EUR", border=1, align="R")
    pdf.ln()

    pdf.set_font("Helvetica", "B", 10)
    total = subtotal + vat_total
    pdf.cell(sum(col_widths[:-1]), 7, "TOTAL:", border=1, align="R", fill=True)
    pdf.cell(col_widths[-1], 7, f"{total:.2f} EUR", border=1, align="R", fill=True)
    pdf.ln(10)

    # Payment info
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "Forma de pago: Transferencia bancaria", ln=True)
    pdf.cell(0, 5, "IBAN: ES91 2100 0418 4502 0005 1332", ln=True)
    pdf.ln(5)

    # Category
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, "Categoria de gasto: veterinary", ln=True)

    # Save
    output_dir = "/home/saulo/transvega-animal/tests/fixtures/invoices"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "staging_test_invoice.pdf")
    pdf.output(output_path)

    print(f"Test invoice generated: {output_path}")
    print("Supplier: STAGING SUPPLIER TEST")
    print("CIF: B99999999")
    print("Invoice: STAGING-INV-001")
    print(f"Base: {subtotal:.2f}")
    print(f"IVA (21%): {vat_total:.2f}")
    print(f"Total: {total:.2f}")

    return output_path


if __name__ == "__main__":
    generate_test_invoice()
