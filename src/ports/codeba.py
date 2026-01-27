"""
Coletor de lineup dos portos CODEBA (Aratu, Ilhéus, Salvador)
Tipo: HTML Tables
"""

import pandas as pd
from loguru import logger
from bs4 import BeautifulSoup

from src.core.fetch import fetch_url
from src.core.storage import save_raw, save_parquet
from src.core.normalize import normalize_produto, make_id, VEGETAIS

SOURCES = {
    "aratu": {
        "porto_label": "Aratu-Candeias",
        "porto_slug": "aratu",
        "url": "https://www.codeba.gov.br/eficiente/sites/portalcodeba/pt-br/site.php?secao=tportos_aratu",
    },
    "ilheus": {
        "porto_label": "Ilhéus",
        "porto_slug": "ilheus",
        "url": "https://www.codeba.gov.br/eficiente/sites/portalcodeba/pt-br/site.php?secao=tportos_ilheus",
    },
    "salvador": {
        "porto_label": "Salvador",
        "porto_slug": "salvador",
        "url": "https://www.codeba.gov.br/eficiente/sites/portalcodeba/pt-br/site.php?secao=tportos_salvador",
    },
}

def _parse_tables(html: bytes) -> pd.DataFrame:
    """Parseia tabelas CODEBA - muitas vezes em formato 'grid' customizado."""
    try:
        # Tentar parsear manualmente via BeautifulSoup para capturar cabeçalhos reais
        soup = BeautifulSoup(html, "lxml")
        dfs = []
        for table in soup.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
                if cells:
                    rows.append(cells)

            if not rows:
                continue

            header_idx = None
            for i, row in enumerate(rows):
                row_up = [c.upper() for c in row]
                if any("NAVIO" in c for c in row_up) and any(("ETA" in c or "CHEGADA" in c or "PREV" in c) for c in row_up):
                    header_idx = i
                    break

            if header_idx is None:
                continue

            header = rows[header_idx]
            data_rows = rows[header_idx + 1:]
            norm_rows = []
            for r in data_rows:
                if not any(cell.strip() for cell in r):
                    continue
                if len(r) < len(header):
                    r = r + [""] * (len(header) - len(r))
                else:
                    r = r[:len(header)]
                norm_rows.append(r)

            if norm_rows:
                dfs.append(pd.DataFrame(norm_rows, columns=header))

        if dfs:
            return pd.concat(dfs, ignore_index=True)

        # Fallback: pd.read_html
        tables = pd.read_html(html, flavor="lxml")
        if not tables:
            return pd.DataFrame()

        dfs = [t for t in tables if t.shape[1] >= 10]
        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    except Exception as e:
        logger.warning(f"Erro ao parsear tabelas CODEBA: {e}")
        return pd.DataFrame()

def _standardize_df(df: pd.DataFrame, porto_label: str, url: str) -> pd.DataFrame:
    """Padroniza colunas CODEBA."""
    df = df.copy()
    # Limpar nomes de colunas
    df.columns = [str(c).strip().lower() for c in df.columns]
    
    df["porto"] = porto_label
    df["fonte_url"] = url
    
    # Mapeamento CODEBA:
    # 'navio' ou 'nome do navio'
    # 'chegada prevista' ou 'eta'
    # 'carga'
    
    col_map = {
        "navio": "navio",
        "nome do navio": "navio",
        "chegada prevista": "prev_chegada",
        "eta": "prev_chegada",
        "carga": "carga",
        "produto": "carga",
        "imo": "imo",
        "berço": "berco",
        "bero": "berco",
        "berco": "berco",
        "cais": "berco"
    }
    
    for old, new in col_map.items():
        if old in df.columns:
            df[new] = df[old].astype(str)
            
    # Standard columns initialization
    standard_cols = ["berco", "imo", "navio", "bordo", "comp(m)", "dwt", "carga", 
                     "qtdcarga", "calado(m)", "agencia", "ultima_atualizacao", 
                     "operacao", "prev_chegada"]

    for col in standard_cols:
        if col not in df.columns:
            df[col] = ""

    # Garantir colunas mínimas se mapeamento falhou
    if not df.empty:
        if not df["navio"].any():
            df["navio"] = df.iloc[:, 0].astype(str)
        if "navio" in df.columns:
            df = df[~df["navio"].astype(str).str.upper().str.contains("LEGENDA", na=False)].copy()

    return df

def _filter_vegetais(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra apenas cargas de granéis vegetais."""
    if df.empty or "carga" not in df.columns:
        return df
    
    mask = df["carga"].str.upper().str.contains("|".join(VEGETAIS), na=False)
    filtered = df.loc[mask].copy()
    
    if filtered.empty:
        return df # Se não achar nada, retorna original para não perder dados se o nome mudar
        
    return filtered

def run_port(key: str) -> pd.DataFrame:
    """Executa coleta para um porto específico da CODEBA."""
    cfg = SOURCES.get(key)
    if not cfg:
        return pd.DataFrame()
        
    logger.info(f"Coletando CODEBA {cfg['porto_label']}: {cfg['url']}")
    
    try:
        html = fetch_url(cfg["url"])
    except Exception as e:
        logger.error(f"Erro ao baixar {cfg['porto_label']}: {e}")
        return pd.DataFrame()
        
    save_raw(cfg["porto_slug"], html, "html")
    
    df = _parse_tables(html)
    if df.empty:
        logger.warning(f"Nenhum dado extraído de {cfg['porto_label']}")
        return df
        
    df = _standardize_df(df, cfg["porto_label"], cfg["url"])
    df = _filter_vegetais(df)
    
    if not df.empty:
        df["produto"] = df["carga"].apply(normalize_produto)
        df["id_evento"] = df.apply(make_id, axis=1)
        save_parquet("curated", cfg["porto_slug"], df)
        logger.success(f"CODEBA {cfg['porto_label']}: {len(df)} registros salvos")
        
    return df

def run_all():
    results = {}
    for key in SOURCES:
        results[key] = run_port(key)
    return results

if __name__ == "__main__":
    run_all()
