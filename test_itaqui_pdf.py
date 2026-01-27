import pdfplumber
import sys

pdf_path = r'c:\Users\tadeu\OneDrive\Documentos\GitHub\lineup_pipeline\data\raw\porto=itaqui\dt=2026-01-19\lineup.pdf'
try:
    with pdfplumber.open(pdf_path) as pdf:
        # Extract tables from the first page
        page = pdf.pages[0]
        tables = page.extract_tables()
        if tables:
            for t_idx, table in enumerate(tables):
                print(f"--- Table {t_idx} ---")
                for i in range(min(10, len(table))):
                    print(f"Row {i}: {table[i]}")
        else:
            # Fallback: extract text if no tables are detected
            print("No tables detected, extracting text:")
            print(page.extract_text()[:1000])
except Exception as e:
    print(f"Error: {e}")
