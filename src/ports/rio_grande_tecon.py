"""
Coletor de lineup do Porto do Rio Grande (Tecon)
Tipo: API JSON
URL: https://api.teconline.com.br/API/ProgNavio
"""

import pandas as pd
import json
from datetime import datetime, timedelta
from loguru import logger

from src.core.fetch import fetch_url
from src.core.storage import save_raw, save_parquet
from src.core.normalize import normalize_produto, make_id

URL_API = "https://api.teconline.com.br/API/ProgNavio"

def _fetch_tecon_data() -> dict:
    """Busca dados da API do Tecon Rio Grande."""
    data_inicial = datetime.now().strftime("%Y-%m-%d")
    data_final = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    
    url = f"{URL_API}?dataInicial={data_inicial}&dataFinal={data_final}&tamanhoPagina=10000"
    
    # Adicionar cabeçalhos completos para evitar 403
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://teconline.com.br/programacao-navios",
        "Origin": "https://teconline.com.br",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Authorization": "null",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site"
    }
    
    logger.info(f"Buscando API Tecon: {url}")
    try:
        import httpx
        with httpx.Client(timeout=60, verify=False) as client:
            r = client.get(url, headers=headers, follow_redirects=True)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.error(f"Erro ao buscar API Tecon Rio Grande: {e}")
        return {}

def _standardize_df(data: dict) -> pd.DataFrame:
    """Transforma JSON da Tecon em DataFrame padronizado."""
    if not data or "Data" not in data or not data["Data"]:
        return pd.DataFrame()
    
    rows = []
    for item in data["Data"]:
        row = {
            "porto": "Rio Grande (Tecon)",
            "berco": item.get("Berco", ""),
            "imo": item.get("LloydsId", ""),
            "navio": item.get("NavioNome", ""),
            "bordo": "",
            "comp(m)": item.get("Comprimento", ""),
            "dwt": "",
            "carga": item.get("ServicoNome", ""), # Tecon é contêiner, aqui usamos Servico como carga/contexto
            "qtdcarga": item.get("Movs", ""),
            "calado(m)": "",
            "agencia": item.get("Armador", ""),
            "ultima_atualizacao": datetime.now().isoformat(),
            "operacao": item.get("Situacao", ""),
            "prev_chegada": item.get("EtaFormat", ""),
            "fonte_url": URL_API
        }
        rows.append(row)
    
    return pd.DataFrame(rows)

def run() -> pd.DataFrame:
    """Executa coleta do Porto do Rio Grande (Tecon)."""
    logger.info("Iniciando coleta Rio Grande (Tecon)")
    
    raw_data = _fetch_tecon_data()
    if not raw_data:
        return pd.DataFrame()
    
    save_raw("rio_grande_tecon", json.dumps(raw_data).encode("utf-8"), "json")
    
    df = _standardize_df(raw_data)
    
    if not df.empty:
        # Nota: Tecon é terminal de contêineres, normalize_produto pode não encontrar vegetais
        df["produto"] = df["carga"].apply(normalize_produto)
        df["id_evento"] = df.apply(make_id, axis=1)
        save_parquet("curated", "rio_grande_tecon", df)
        logger.success(f"Rio Grande (Tecon): {len(df)} registros extraídos")
    
    return df

if __name__ == "__main__":
    run()
