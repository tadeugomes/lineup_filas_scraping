import pdfplumber
import sys

pdf_path = r'c:\Users\tadeu\OneDrive\Documentos\GitHub\lineup_pipeline\data\raw\porto=sao_francisco_sul\dt=2026-01-19\lineup.pdf'
try:
    with pdfplumber.open(pdf_path) as pdf:
        table = pdf.pages[0].extract_table()
        if table:
            for i in range(min(5, len(table))):
                print(f"Row {i}: {table[i]}")
        else:
            print("No table found")
except Exception as e:
    print(f"Error: {e}")
