"""
Coletor de lineup do Porto de São Francisco do Sul (Seatrade)
Tipo: Scraping HTML
URL: https://lineup.seatrade.com.br/optos/lineup/pesquisa.aspx?WCI=RELLINEUPBASE_005_4&NUM_ADMINISTRA_PORTO=2&ORDER_BY=1&VISION=1
"""

import pandas as pd
from bs4 import BeautifulSoup
from loguru import logger
from datetime import datetime

from src.core.fetch import fetch_url
from src.core.storage import save_raw, save_parquet
from src.core.normalize import normalize_produto, make_id, VEGETAIS

URL_SEATRADE = "https://lineup.seatrade.com.br/optos/lineup/pesquisa.aspx?WCI=RELLINEUPBASE_005_4&NUM_ADMINISTRA_PORTO=2&ORDER_BY=1&VISION=1"

def _parse_html(html: bytes) -> pd.DataFrame:
    """Parseia a tabela Status Vision do Seatrade SFS."""
    soup = BeautifulSoup(html, "lxml")
    
    # Tentamos encontrar a tabela com ID tabela1 (Status Vision)
    table = soup.find("table", {"id": "tabela1"})
    if not table:
        # Se não achar por ID, tentamos a primeira com classe tabela
        table = soup.find("table", class_="tabela")
        
    if not table:
        logger.error("Tabela de lineup Seatrade não encontrada no HTML")
        return pd.DataFrame()
    
    rows = []
    # O Seatrade divide por headers de status (Berthed, Awaiting, Expected)
    # Precisamos iterar pelas linhas da tabela
    
    # Primeiro identificar colunas (opcional, mas bom para robustez)
    headers = [th.get_text(strip=True) for th in table.find_all("th") if th.get("name") == "colunas"]
    if not headers:
        # Fallback se não encontrar th com name colunas
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        
    # Iterar pelas linhas do tbody
    tbody = table.find("tbody")
    if not tbody:
        logger.error("Corpo da tabela (tbody) não encontrado")
        return pd.DataFrame()
        
    current_status = ""
    for tr in tbody.find_all("tr"):
        # Verificar se é uma linha de status (ex: Berthed)
        if "header-status-lineup" in tr.get("class", []):
            current_status = tr.get_text(strip=True)
            continue
            
        cells = tr.find_all("td")
        if len(cells) < 10:
            continue
            
        # Mapeamento heurístico baseado no browser research:
        # Status | Berth | Vessel Name | LOA | Port Stay | ETA | AWB | ETB | ETC | ETS | Operation | Arrival Drafts | Agent
        
        # Como o HTML pode variar, tentamos pegar pelo índice aproximado
        # ou pela posição dependendo do status
        
        row_data = {
            "porto": "São Francisco do Sul (Seatrade)",
            "berco": cells[1].get_text(strip=True) if len(cells) > 1 else "",
            "imo": "", # Seatrade não costuma ter IMO no HTML
            "navio": cells[2].get_text(strip=True) if len(cells) > 2 else "",
            "bordo": "",
            "comp(m)": cells[3].get_text(strip=True) if len(cells) > 3 else "",
            "dwt": "",
            "carga": cells[10].get_text(strip=True) if len(cells) > 10 else "",
            "qtdcarga": "", # Quantidade costuma vir no meio do texto de Operation
            "calado(m)": cells[11].get_text(strip=True) if len(cells) > 11 else "",
            "agencia": cells[12].get_text(strip=True) if len(cells) > 12 else "",
            "ultima_atualizacao": datetime.now().isoformat(),
            "operacao": current_status + " / " + (cells[10].get_text(strip=True) if len(cells) > 10 else ""),
            "prev_chegada": cells[5].get_text(strip=True) if len(cells) > 5 else "",
            "fonte_url": URL_SEATRADE
        }
        
        # Tentar extrair qtd se possível (ex: "DISCH STEEL PRODUCTS 47.438,000")
        if row_data["carga"]:
            import re
            match = re.search(r"([\d\.,]+)$", row_data["carga"])
            if match:
                row_data["qtdcarga"] = match.group(1)
        
        rows.append(row_data)
        
    return pd.DataFrame(rows)

def _filter_vegetais(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra apenas cargas de granéis vegetais."""
    if df.empty or "carga" not in df.columns:
        return df
    
    mask = df["carga"].str.upper().str.contains("|".join(VEGETAIS), na=False)
    filtered = df.loc[mask].copy()
    
    logger.info(f"SFS Seatrade: Filtrado {len(filtered)} de {len(df)} registros (granéis vegetais)")
    return filtered

def run() -> pd.DataFrame:
    """Executa coleta do Porto de São Francisco do Sul (Seatrade)."""
    logger.info(f"Coletando SFS Seatrade: {URL_SEATRADE}")
    
    try:
        html = fetch_url(URL_SEATRADE)
    except Exception as e:
        logger.error(f"Erro ao buscar Seatrade SFS: {e}")
        return pd.DataFrame()
        
    save_raw("sfs_seatrade", html, "html")
    
    df = _parse_html(html)
    if df.empty:
        return df
        
    df = _filter_vegetais(df)
    
    if not df.empty:
        df["produto"] = df["carga"].apply(normalize_produto)
        df["id_evento"] = df.apply(make_id, axis=1)
        save_parquet("curated", "sfs_seatrade", df)
        logger.success(f"SFS Seatrade: {len(df)} registros salvos")
        
    return df

if __name__ == "__main__":
    run()
