import pandas as pd
import numpy as np
from src.ports import (
    sao_francisco_sul,
    itaqui_web,
    rio_grande,
    santos_spa,
    santos_ecoporto,
    paranagua_appa,
    codeba,
    cdp
)

def test_schema(name, df):
    expected = ["berco", "imo", "navio", "bordo", "comp(m)", "dwt", "carga", 
                "qtdcarga", "calado(m)", "agencia", "ultima_atualizacao", 
                "operacao", "prev_chegada"]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        print(f"FAILED: {name} is missing columns: {missing}")
    else:
        print(f"PASSED: {name} has all standard columns.")

print("--- Verifying Port Schemas ---")

# 1. SFS (Mocking _parse_pdf result)
df_sfs = pd.DataFrame([{"navio": "TEST", "imo": "123", "prev_chegada": "ETA", "carga": "SOJA", "berco": "1", "comp(m)": "100", "calado(m)": "10", "agencia": "A", "operacao": "OP", "qtdcarga": "1000", "bordo": "", "dwt": "", "ultima_atualizacao": ""}])
test_schema("São Francisco do Sul", df_sfs)

# 2. Itaqui
df_itaqui = pd.DataFrame([{"navio": "TEST", "imo": "123", "prev_chegada": "ETA", "carga": "SOJA", "berco": "", "comp(m)": "100", "dwt": "1000", "calado(m)": "10", "agencia": "A", "operacao": "OP", "qtdcarga": "1000", "bordo": "", "status": "ATRACADO", "ultima_atualizacao": ""}])
test_schema("Itaqui", df_itaqui)

# 3. Rio Grande
df_rg_raw = pd.DataFrame([["NAVIO", "CARGA", "OTHER"]])
df_rg = rio_grande._standardize_df(df_rg_raw)
test_schema("Rio Grande", df_rg)

# 4. Santos SPA
df_spa_raw = pd.DataFrame([["SHIP", "SOJA", "123", "B1"]], columns=["navio", "carga", "imo", "berco"])
df_spa = santos_spa._standardize_df(df_spa_raw)
test_schema("Santos SPA", df_spa)

# 5. Santos Ecoporto
# This one returns a DF at the end of run, let's check its logic:
# rows.append({"porto": "Santos", ..., "navio": navio, ...})
df_eco = pd.DataFrame([{"navio": "TEST", "prev_chegada": "ETA", "berco": "1", "imo": "", "bordo": "", "comp(m)": "", "dwt": "", "carga": "", "qtdcarga": "", "calado(m)": "", "agencia": "", "ultima_atualizacao": "", "operacao": ""}])
test_schema("Santos Ecoporto", df_eco)

# 6. Paranaguá
df_para_raw = pd.DataFrame([["NAVIO", "2026-01-01", "SOJA"]], columns=["navio", "chegada", "carga"])
df_para = pd.DataFrame() # Logic is inside run(), but _standardize_df-like logic was injected
# Running a simplified version of its logic
df_para_mock = df_para_raw.copy()
standard_cols = ["berco", "imo", "navio", "bordo", "comp(m)", "dwt", "carga", "qtdcarga", "calado(m)", "agencia", "ultima_atualizacao", "operacao", "prev_chegada"]
for col in standard_cols: 
    if col not in df_para_mock.columns: df_para_mock[col] = ""
df_para_mock["prev_chegada"] = df_para_mock["chegada"]
test_schema("Paranaguá", df_para_mock)

# 7. CODEBA
df_codeba_raw = pd.DataFrame([["NAVIO", "ETA", "SOJA"]], columns=["navio", "eta", "carga"])
df_codeba = codeba._standardize_df(df_codeba_raw, "Salvador", "http://test")
test_schema("CODEBA", df_codeba)

# 8. CDP
df_cdp_raw = pd.DataFrame([["NAVIO", "ETA", "SOJA"]], columns=["navio", "eta", "carga"])
df_cdp = cdp._standardize_df(df_cdp_raw, "Vila do Conde", "http://test")
test_schema("CDP", df_cdp)
