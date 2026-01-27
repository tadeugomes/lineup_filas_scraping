"""
Coletor de lineup do Porto de Santos - Fonte Oficial SPA
Santos Port Authority (Autoridade Portuária de Santos)

URL: https://www.portodesantos.com.br/informacoes-operacionais/operacoes-portuarias/navegacao-e-movimento-de-navios/atracacoes-programadas/
"""

import pandas as pd
from loguru import logger

from src.core.fetch import fetch_url
from src.core.storage import save_raw, save_parquet
from src.core.normalize import normalize_produto, make_id, VEGETAIS

URL = "https://www.portodesantos.com.br/informacoes-operacionais/operacoes-portuarias/navegacao-e-movimento-de-navios/atracacoes-programadas/"


def _parse_tables(html: bytes) -> pd.DataFrame:
    """Parseia todas as tabelas da página e combina em um único DataFrame."""
    try:
        tables = pd.read_html(html, flavor="lxml")
    except Exception as e:
        logger.warning(f"pd.read_html falhou: {e}")
        return pd.DataFrame()
    
    if not tables:
        logger.warning("Nenhuma tabela encontrada na página")
        return pd.DataFrame()
    
    # Combinar todas as tabelas (a página tem múltiplas tabelas por período)
    dfs = []
    for tbl in tables:
        if tbl.shape[0] > 0 and tbl.shape[1] >= 5:
            dfs.append(tbl)
    
    if not dfs:
        return pd.DataFrame()
    
    return pd.concat(dfs, ignore_index=True)


def _standardize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Padroniza colunas para o schema comum do pipeline."""
    df = df.copy()
    
    # Se for MultiIndex, achatar
    if isinstance(df.columns, pd.MultiIndex):
        new_cols = []
        for col in df.columns.values:
            levels = [str(l).strip() for l in col if "Unnamed" not in str(l)]
            if not levels:
                new_cols.append("unknown")
            else:
                # Santos costuma ter a data como primeiro nível. Se o primeiro nível parecer data/hora, ignore.
                if len(levels) > 1 and ("/" in levels[0] or ":" in levels[0]):
                    new_cols.append(levels[-1])
                else:
                    new_cols.append(' '.join(levels).strip())
        df.columns = new_cols

    # Normalizar nomes de colunas
    df.columns = [str(c).strip().lower().replace("\n", " ") for c in df.columns]
    
    # Deduplicate columns early
    df = df.loc[:, ~df.columns.duplicated()].copy()

    df["porto"] = "Santos"
    df["fonte_url"] = URL
    
    # Navio - procurar colunas candidatas
    navio_col = None
    for cand in ["navio", "navio ship burque", "ship", "embarcação", "embarcacao"]:
        if cand in df.columns:
            navio_col = cand
            break
    
    if navio_col:
        df["navio"] = df[navio_col].astype(str)
    else:
        # Fallback: tentar quinta coluna (comum no layout da SPA após data/hora)
        if df.shape[1] > 4:
            df["navio"] = df.iloc[:, 4].astype(str)
        else:
            df["navio"] = ""
    
    # prev_chegada (ETA)
    eta_col = None
    for cand in ["eta", "etadatefecha", "data", "chegada", "previsão"]:
        if cand in df.columns:
            eta_col = cand
            break
    
    if eta_col:
        df["prev_chegada"] = df[eta_col].astype(str)
    else:
        # Tentar achar algo que contenha eta nas colunas
        for c in df.columns:
            if "eta" in c:
                df["prev_chegada"] = df[c].astype(str)
                break
        else:
            df["prev_chegada"] = ""
    
    # Carga/Produto
    prod_col = None
    for cand in ["carga", "carga cargo carga", "mercadoria", "produto", "commodity"]:
        if cand in df.columns:
            prod_col = cand
            break
    
    if prod_col:
        df["carga"] = df[prod_col].astype(str)
    else:
        df["carga"] = ""
    
    # IMO (identificador único do navio)
    imo_col = None
    for cand in ["imo"]:
        if cand in df.columns:
            imo_col = cand
            break
    
    if imo_col:
        df["imo"] = df[imo_col].astype(str)
    else:
        df["imo"] = ""
    
    # Local/Terminal (berco)
    local_col = None
    for cand in ["local", "local place lugar", "terminal", "berço", "berco", "cais"]:
        if cand in df.columns:
            local_col = cand
            break
    
    if local_col:
        df["berco"] = df[local_col].astype(str)
    else:
        df["berco"] = ""

    # Missing standard columns
    standard_cols = ["berco", "imo", "navio", "bordo", "comp(m)", "dwt", "carga", 
                     "qtdcarga", "calado(m)", "agencia", "ultima_atualizacao", 
                     "operacao", "prev_chegada"]
    for col in standard_cols:
        if col not in df.columns:
            df[col] = ""
    
    return df


def _filter_vegetais(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra apenas cargas de granéis vegetais."""
    if df.empty or "carga" not in df.columns:
        return df
    
    mask = df["carga"].str.upper().str.contains("|".join(VEGETAIS), na=False)
    filtered = df.loc[mask].copy()
    
    logger.info(f"Santos: Filtrado {len(filtered)} de {len(df)} registros (granéis vegetais)")
    return filtered


def run() -> pd.DataFrame:
    """Executa coleta do Porto de Santos (SPA oficial)."""
    logger.info(f"Coletando Santos SPA: {URL}")
    
    try:
        html = fetch_url(URL)
    except Exception as e:
        logger.error(f"Erro ao buscar Santos SPA: {e}")
        return pd.DataFrame()
    
    save_raw("santos_spa", html, "html")
    
    df = _parse_tables(html)
    if df.empty:
        logger.warning("Nenhum dado extraído de Santos SPA")
        return df
    
    df = _standardize_df(df)
    df = _filter_vegetais(df)
    
    if not df.empty:
        df["produto"] = df["carga"].apply(normalize_produto)
        df["id_evento"] = df.apply(make_id, axis=1)
        
        # Final re-order
        standard_cols = ["berco", "imo", "navio", "bordo", "comp(m)", "dwt", "carga", 
                         "qtdcarga", "calado(m)", "agencia", "ultima_atualizacao", 
                         "operacao", "prev_chegada"]
        final_cols = standard_cols + ["produto", "id_evento", "porto", "fonte_url"]
        cols_to_keep = [c for c in final_cols if c in df.columns]
        df = df[cols_to_keep]
        
        save_parquet("curated", "santos_spa", df)
        logger.success(f"Santos SPA: {len(df)} registros salvos")
    
    return df


if __name__ == "__main__":
    run()
