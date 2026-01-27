"""
Coletor de navios atracados do Porto do Rio Grande (Praticos da Barra)
URL: https://www.rgpilots.com.br/atracados
Tipo: HTML
"""

import pandas as pd
from loguru import logger

from src.core.fetch import fetch_url
from src.core.storage import save_raw, save_parquet
from src.core.normalize import make_id

URL = "https://www.rgpilots.com.br/atracados"


def _parse_html(html: bytes) -> pd.DataFrame:
    try:
        from io import StringIO
        tables = pd.read_html(StringIO(html.decode("utf-8", errors="ignore")))
    except ValueError:
        return pd.DataFrame()

    if not tables:
        return pd.DataFrame()

    df = None
    for t in tables:
        cols = [str(c).lower() for c in t.columns]
        if any("navio" in c for c in cols):
            df = t
            break

    if df is None:
        df = max(tables, key=lambda t: t.shape[0])

    df.columns = [str(c).strip().lower().replace("\n", " ") for c in df.columns]
    df = df.loc[:, ~df.columns.duplicated()].copy()

    # Mapear colunas conhecidas
    if "navio" in df.columns:
        df["navio"] = df["navio"].astype(str)

    if "data" in df.columns:
        df["prev_chegada"] = df["data"].astype(str)

    if "agência" in df.columns:
        df["agencia"] = df["agência"].astype(str)
    elif "agencia" in df.columns:
        df["agencia"] = df["agencia"].astype(str)

    # "De Para" pode conter berco/destino
    for cand in ["de para", "para", "berco", "berço"]:
        if cand in df.columns:
            df["berco"] = df[cand].astype(str)
            break

    df["porto"] = "Rio Grande (Pilots)"
    df["fonte_url"] = URL
    df["operacao"] = "ATRACADO"

    # Garantir colunas padrao
    standard_cols = [
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
    ]
    for col in standard_cols:
        if col not in df.columns:
            df[col] = ""

    df["id_evento"] = df.apply(make_id, axis=1)

    final_cols = standard_cols + ["id_evento", "porto", "fonte_url"]
    cols_to_keep = [c for c in final_cols if c in df.columns]
    return df[cols_to_keep]


def run() -> pd.DataFrame:
    logger.info(f"Coletando Rio Grande (Pilots): {URL}")
    try:
        html = fetch_url(URL)
    except Exception as e:
        logger.error(f"Erro ao buscar Pilots Rio Grande: {e}")
        return pd.DataFrame()

    save_raw("rio_grande_pilots", html, "html")
    df = _parse_html(html)
    if df.empty:
        return df

    save_parquet("curated", "rio_grande_pilots", df)
    logger.success(f"Rio Grande (Pilots): {len(df)} registros extraidos")
    return df


if __name__ == "__main__":
    run()
