"""
Coletor de lineup do Porto do Itaqui (Web Status)
Tipo: Scraping HTML
URL: https://www.portodoitaqui.com/porto-agora/navios/atracados
"""

import pandas as pd
from bs4 import BeautifulSoup
from loguru import logger
from datetime import datetime
import time

from src.core.fetch import fetch_url
from src.core.storage import save_raw, save_parquet
from src.core.normalize import normalize_produto, make_id, VEGETAIS

URLS = {
    "ATRACADO": "https://www.portodoitaqui.com/porto-agora/navios/atracados",
    "FUNDEADO": "https://www.portodoitaqui.com/porto-agora/navios/fundeados",
    "ESPERADO": "https://www.portodoitaqui.com/porto-agora/navios/esperados"
}

RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY_SEC = 3
RUN_MAX_PASSES = 3
RUN_RETRY_DELAY_SEC = 10

STANDARD_COLS = [
    "porto",
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
    "status",
    "fonte_url",
    "produto",
    "id_evento",
]


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=STANDARD_COLS)

def _fetch_with_retry(url: str, status: str) -> bytes:
    last_err = None
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            return fetch_url(url, retries=1)
        except Exception as e:
            last_err = e
            if attempt < RETRY_MAX_ATTEMPTS:
                delay = RETRY_BASE_DELAY_SEC * (2 ** (attempt - 1))
                time.sleep(delay)
            else:
                raise

    raise last_err

def _parse_table(html: bytes, status: str) -> pd.DataFrame:
    """Parseia a tabela de navios do Itaqui."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    
    if not table:
        logger.warning(f"Tabela não encontrada para status {status}")
        return pd.DataFrame()
        
    rows = []
    # Ignorar o cabeçalho
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all("td")
        if len(cells) < 7:
            continue
            
        # Estrutura observada:
        # Berço | Bandeira | Navio | IMO | Bordo | Comprimento | DWT | Calado | Agência | Operação | Produto | Quantidade | Previsão
        # Nota: Os índices podem variar entre as tabelas, mas tentamos um mapeamento comum.
        
        row_data = {
            "porto": "Itaqui (Web)",
            "berco": cells[0].get_text(strip=True),
            "navio": cells[2].get_text(strip=True),
            "imo": cells[3].get_text(strip=True),
            "bordo": cells[4].get_text(strip=True) if len(cells) > 4 else "",
            "comp(m)": cells[5].get_text(strip=True) if len(cells) > 5 else "",
            "dwt": cells[6].get_text(strip=True) if len(cells) > 6 else "",
            "calado(m)": cells[7].get_text(strip=True) if len(cells) > 7 else "",
            "agencia": cells[8].get_text(strip=True) if len(cells) > 8 else "",
            "operacao": cells[9].get_text(strip=True) if len(cells) > 9 else "",
            "carga": cells[10].get_text(strip=True) if len(cells) > 10 else "",
            "qtdcarga": cells[11].get_text(strip=True) if len(cells) > 11 else "",
            "prev_chegada": cells[12].get_text(strip=True) if len(cells) > 12 else "",
            "status": status,
            "ultima_atualizacao": datetime.now().isoformat(),
            "fonte_url": URLS[status]
        }
        rows.append(row_data)
        
    return pd.DataFrame(rows)

def run() -> pd.DataFrame:
    """Executa coleta Web de todos os status do Itaqui."""
    logger.info("Iniciando coleta Itaqui Web Status")
    
    all_dfs = []
    
    pending = dict(URLS)
    for pass_idx in range(1, RUN_MAX_PASSES + 1):
        if not pending:
            break
        for status, url in list(pending.items()):
            logger.info(f"Coletando Itaqui {status}: {url}")
            try:
                html = _fetch_with_retry(url, status)
                save_raw(f"itaqui_web_{status.lower()}", html, "html")
                df = _parse_table(html, status)
                if not df.empty:
                    all_dfs.append(df)
                pending.pop(status, None)
            except Exception as e:
                logger.info(
                    f"Itaqui {status}: falha no ciclo {pass_idx}/{RUN_MAX_PASSES}: {e}"
                )
        if pending and pass_idx < RUN_MAX_PASSES:
            time.sleep(RUN_RETRY_DELAY_SEC)

    if pending:
        for status in pending.keys():
            logger.error(f"Itaqui {status}: falha apos {RUN_MAX_PASSES} ciclos.")
            
    if not all_dfs:
        logger.warning("Itaqui Web: nenhum status coletado. Salvando parquet vazio.")
        empty = _empty_df()
        save_parquet("curated", "itaqui_web", empty)
        return empty
        
    df_total = pd.concat(all_dfs, ignore_index=True)

    # Sempre gerar produto/id_evento para manter schema consistente
    if "carga" in df_total.columns:
        df_total["produto"] = df_total["carga"].apply(normalize_produto)
    else:
        df_total["produto"] = ""
    df_total["id_evento"] = df_total.apply(make_id, axis=1)
    
    # Filtro de vegetais - REMOVIDO: Agora salva todos os dados sem filtrar
    logger.info(f"Itaqui Web: Salvando todos os {len(df_total)} registros (filtro de vegetais desabilitado)")
    save_parquet("curated", "itaqui_web", df_total)
    logger.success(f"Itaqui Web: {len(df_total)} registros salvos")

    return df_total

if __name__ == "__main__":
    run()
