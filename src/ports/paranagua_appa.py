import os
import pandas as pd
import httpx
import urllib3
from loguru import logger

from src.core.storage import save_raw, save_parquet
from src.core.normalize import normalize_produto, make_id, VEGETAIS

URL = "https://www.appaweb.appa.pr.gov.br/appaweb/pesquisa.aspx?WCI=relLineUpRetroativo"
LOGIN_URL = "https://www.appaweb.appa.pr.gov.br/appaweb/default.aspx?WCI=Default&Mv=Ok"

# Suprimir avisos de SSL não verificado (padrão no projeto)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def _is_login_page(html: str) -> bool:
    return "APPA Web" in html and 'name="User"' in html and 'name="Pass"' in html

STANDARD_COLS = [
    "berco",
    "imo",
    "navio",
    "bordo",
    "comp(m)",
    "dwt",
    "carga",
    "qtdcarga",
    "calado(m)",
    "agencia",
    "ultima_atualizacao",
    "operacao",
    "prev_chegada",
    "produto",
    "id_evento",
    "porto",
    "fonte_url",
]


def _empty_df() -> pd.DataFrame:
    df = pd.DataFrame(columns=STANDARD_COLS)
    df["porto"] = "Paranagua/Antonina"
    df["fonte_url"] = URL
    return df

def _fetch_html() -> bytes:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    cookie = os.getenv("APPAWEB_COOKIE", "").strip()
    user = os.getenv("APPAWEB_USER", "").strip()
    password = os.getenv("APPAWEB_PASS", "").strip()

    with httpx.Client(timeout=60, verify=False, headers=headers, follow_redirects=True) as client:
        if cookie:
            client.headers["Cookie"] = cookie

        r = client.get(URL)
        r.raise_for_status()
        if not _is_login_page(r.text):
            return r.content

        if not user or not password:
            logger.warning(
                "APPA Web exige login. Defina APPAWEB_USER/APPAWEB_PASS ou APPAWEB_COOKIE para acesso."
            )
            return r.content

        # Tenta login com credenciais fornecidas (captcha é apenas client-side)
        payload = {"User": user, "Pass": password, "valuecaptcha": ""}
        client.post(LOGIN_URL, data=payload)

        r2 = client.get(URL)
        r2.raise_for_status()
        if _is_login_page(r2.text):
            logger.error("Login APPA falhou ou sessão não autorizada para o relatório.")
        return r2.content

def run():
    html = _fetch_html()
    save_raw("paranagua_appa", html, "html")

    try:
        tables = pd.read_html(html, flavor="lxml")
    except ValueError:
        logger.warning("Paranagua/Antonina: nenhuma tabela encontrada (provavel pagina de login).")
        empty = _empty_df()
        save_parquet("curated", "paranagua_appa", empty)
        return empty
    if not tables:
        empty = _empty_df()
        save_parquet("curated", "paranagua_appa", empty)
        return empty

    # Heuristic: largest table is usually the report body
    df = max(tables, key=lambda t: t.shape[0])

    # Se for MultiIndex, achatar. Priorizamos o último nível se ele for informativo.
    if isinstance(df.columns, pd.MultiIndex):
        new_cols = []
        for col in df.columns.values:
            levels = [str(l).strip() for l in col if "Unnamed" not in str(l)]
            if not levels:
                new_cols.append("unknown")
            else:
                new_cols.append(levels[-1])
        df.columns = new_cols

    # Normalize columns
    df.columns = [str(c).strip().lower().replace("\n", " ") for c in df.columns]
    
    # Deduplicate columns early
    df = df.loc[:, ~df.columns.duplicated()].copy()

    df["porto"] = "Paranagua/Antonina"
    df["fonte_url"] = URL

    # Mapping columns
    standard_cols = ["berco", "imo", "navio", "bordo", "comp(m)", "dwt", "carga", 
                     "qtdcarga", "calado(m)", "agencia", "ultima_atualizacao", 
                     "operacao", "prev_chegada"]

    # Ship name
    for cand in ["embarcação", "embarcacao", "navio", "nome", "embarcacao / vgm"]:
        if cand in df.columns:
            df["navio"] = df[cand].astype(str)
            break

    # ETA / chegada
    for cand in ["chegada", "eta", "data progr.", "prev. chegada", "data/hora"]:
        if cand in df.columns:
            df["prev_chegada"] = df[cand].astype(str)
            break

    # IMO
    if "imo" in df.columns:
        df["imo"] = df["imo"].astype(str)

    # Produto/carga
    for cand in ["produtos", "produto", "carga", "mercadoria", "mercadoria/operação"]:
        if cand in df.columns:
            df["carga"] = df[cand].astype(str)
            break

    # Berço
    for cand in ["berço", "berco", "local", "cais", "berço / vgm"]:
        if cand in df.columns:
            df["berco"] = df[cand].astype(str)
            break

    # Filter for vegetal
    mask = df["carga"].str.upper().str.contains("|".join(VEGETAIS), na=False)
    df = df.loc[mask].copy()

    if df.empty:
        empty = _empty_df()
        save_parquet("curated", "paranagua_appa", empty)
        return empty

    # Final cleanup: ensure all standard cols exist
    for col in standard_cols:
        if col not in df.columns:
            df[col] = ""

    df["produto"] = df["carga"].apply(normalize_produto)
    df["id_evento"] = df.apply(make_id, axis=1)

    # Re-order and keep only needed
    final_cols = standard_cols + ["produto", "id_evento", "porto", "fonte_url"]
    cols_to_keep = [c for c in final_cols if c in df.columns]
    df = df[cols_to_keep]

    save_parquet("curated", "paranagua_appa", df)
    return df

if __name__ == "__main__":
    run()
