"""
Coletor de lineup do Porto do Itaqui (EMAP)

URL: https://www.portodoitaqui.com/_files/arquivos/mapa-de-atracacao.pdf
Tipo: PDF
"""

import pandas as pd
import re
from bs4 import BeautifulSoup
from loguru import logger

from src.core.fetch import fetch_url
from src.core.storage import save_raw, save_parquet
from src.core.normalize import normalize_produto, make_id, VEGETAIS

# Link fallback sugerido pelo usuário para emergência/intermitência
URL_FALLBACK = "https://www.portodoitaqui.com/public/_files/arquivos/MAPA%20DE%20ATRACA%C3%87%C3%83O%20-%2020%2001%202026%20-15h00%20-%20clientes_696fc3255016d.pdf"

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

URL_HOME = "https://www.portodoitaqui.com/porto-agora/navios/atracados"

def _get_latest_pdf_url() -> str:
    """Busca o link dinâmico do PDF no site do Itaqui."""
    logger.info(f"Buscando link do PDF em: {URL_HOME}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.portodoitaqui.com/"
    }
    
    import httpx
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    try:
        # Tentar com httpx primeiro (padrão do projeto)
        with httpx.Client(timeout=30, verify=False, headers=headers) as client:
            r = client.get(URL_HOME, follow_redirects=True)
            r.raise_for_status()
            html = r.text
            
        soup = BeautifulSoup(html, "lxml")
        
        # Procura por link que contém "Mapa de Atracação" no texto ou span
        link_node = soup.find('span', string=lambda text: text and ('Mapa de Atracação' in text or 'MAPA' in text.upper()))
        if not link_node:
             link_node = soup.find('a', string=lambda text: text and 'Mapa de Atracação' in text)
             
        if link_node:
            a_tag = link_node if link_node.name == 'a' else link_node.find_parent('a')
            if a_tag and a_tag.get('href'):
                pdf_url = a_tag['href']
                if not pdf_url.startswith("http"):
                    pdf_url = "https://www.portodoitaqui.com" + ("/" + pdf_url.lstrip("/"))
                logger.info(f"URL do PDF encontrada: {pdf_url}")
                return pdf_url
        
        # Fallback 1: procurar em todos os links da página
        for a in soup.find_all('a', href=True):
            href = a['href'].upper()
            if "MAPA" in href and "ATRACA" in href and ".PDF" in href:
                pdf_url = a['href']
                if not pdf_url.startswith("http"):
                    pdf_url = "https://www.portodoitaqui.com" + ("/" + pdf_url.lstrip("/"))
                logger.info(f"URL do PDF encontrada (fallback links): {pdf_url}")
                return pdf_url
    
    except Exception as e:
        logger.error(f"Erro ao buscar link dinâmico do Itaqui com httpx: {e}")
        
    # Fallback 2: Tentar capturar o link diretamente se soubermos a página correta
    # Como último recurso, o link fornecido pelo usuário pode ser usado se o scraper falhar
    # mas aqui tentamos ser dinâmicos.
    
    return ""


def _extract_berco_from_cell(cell: str) -> str:
    if not cell:
        return ""
    c_up = str(cell).upper()
    if "TEGRAM" in c_up:
        return "TEGRAM"
    if "TMG" in c_up:
        return "TMG"
    if "PVP" in c_up:
        return "PVP"
    if "MARINA" in c_up:
        return "V. MARINA"
    digits = re.sub(r"\D", "", c_up)
    m = re.search(r"10[0-9]", digits)
    if m:
        return m.group(0)
    return ""


def _parse_pdf(pdf_path: str) -> pd.DataFrame:
    """Parseia tabelas do PDF de mapa de atracacao com logica heuristica para lidar com layouts variaveis."""
    if not HAS_PDFPLUMBER:
        logger.error("pdfplumber nao instalado, nao e possivel processar PDF")
        return pd.DataFrame()

    all_rows = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table:
                        continue

                    table_berco = ""
                    for row in table:
                        for cell in row:
                            if not cell:
                                continue
                            candidate = _extract_berco_from_cell(str(cell))
                            if candidate:
                                table_berco = candidate
                                break
                        if table_berco:
                            break

                    for row in table:
                        raw_row = [str(c).strip() if c is not None else "" for c in row]
                        row_berco = ""
                        for c in raw_row:
                            candidate = _extract_berco_from_cell(c)
                            if candidate:
                                row_berco = candidate
                                break

                        clean_row = [c for c in raw_row if c]
                        if len(clean_row) < 5:
                            continue

                        status_candidates = {"ATRACADO", "FUNDEADO", "ESPERADO", "PROGRAMADO", "AO LARGO", "MANUTENCAO"}
                        status = ""
                        imo = ""
                        navio = ""
                        berco = row_berco or table_berco

                        for s in status_candidates:
                            if any(s in c.upper() for c in clean_row):
                                status = s
                                break

                        for c in clean_row:
                            digits = c.replace(".", "").replace("-", "")
                            if digits.isdigit() and len(digits) == 7:
                                imo = digits
                                break

                        if not berco:
                            for c in clean_row:
                                candidate = _extract_berco_from_cell(c)
                                if candidate:
                                    berco = candidate
                                    break

                        for c in clean_row:
                            if c.isupper() and len(c) > 3 and c not in status_candidates and c != berco:
                                if not navio:
                                    navio = c
                                    if "NAVIO" in c.upper():
                                        navio = c.replace("NAVIO", "").strip()
                                        break

                        if not navio:
                            continue

                        row_dict = {
                            "navio": navio,
                            "imo": imo,
                            "berco": berco,
                            "status": status,
                            "carga": "",
                            "prev_chegada": "",
                            "comp(m)": "",
                            "dwt": "",
                            "calado(m)": "",
                            "agencia": "",
                            "operacao": "",
                            "qtdcarga": "",
                            "bordo": "",
                            "ultima_atualizacao": ""
                        }

                        if navio and navio.lower() != "navio":
                            all_rows.append(row_dict)

    except Exception as e:
        logger.error(f"Erro ao processar PDF: {e}")
        return pd.DataFrame()

    if not all_rows:
        return pd.DataFrame()

    return pd.DataFrame(all_rows)

def _standardize_df(df: pd.DataFrame, pdf_url: str) -> pd.DataFrame:
    df = df.copy()
    df["porto"] = "Itaqui"
    df["fonte_url"] = pdf_url
    return df

def _filter_vegetais(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "carga" not in df.columns:
        return df
    
    mask = df["carga"].str.upper().str.contains("|".join(VEGETAIS), na=False)
    filtered = df.loc[mask].copy()
    
    if len(filtered) == 0:
        logger.info("Nenhum granel vegetal identificado no filtro estrito, mantendo todos para análise manual posterior")
        return df
    
    logger.info(f"Filtrado {len(filtered)} de {len(df)} registros (granéis vegetais)")
    return filtered

def run() -> pd.DataFrame:
    """Executa coleta do Porto do Itaqui."""
    pdf_url = _get_latest_pdf_url()
    if not pdf_url:
        logger.warning(f"Não foi possível encontrar a URL dinâmica. Usando fallback: {URL_FALLBACK}")
        pdf_url = URL_FALLBACK
        
    logger.info(f"Coletando Itaqui PDF: {pdf_url}")
    
    try:
        pdf_content = fetch_url(pdf_url)
    except Exception as e:
        logger.error(f"Erro ao baixar PDF de Itaqui: {e}")
        if pdf_url != URL_FALLBACK:
            logger.info(f"Tentando novamente com o fallback após erro: {URL_FALLBACK}")
            try:
                pdf_content = fetch_url(URL_FALLBACK)
                pdf_url = URL_FALLBACK
            except Exception as e2:
                logger.error(f"Erro no segundo fallback de Itaqui: {e2}")
                return pd.DataFrame()
        else:
            return pd.DataFrame()
    
    pdf_path = save_raw("itaqui", pdf_content, "pdf")
    
    df = _parse_pdf(str(pdf_path))
    if df.empty:
        logger.warning("Nenhum dado extraído do PDF de Itaqui")
        return df
    
    df = _standardize_df(df, pdf_url)
    df = _filter_vegetais(df)
    
    if not df.empty:
        df["produto"] = df["carga"].apply(normalize_produto)
        df["id_evento"] = df.apply(make_id, axis=1)
        save_parquet("curated", "itaqui", df)
        logger.success(f"Itaqui PDF: {len(df)} registros salvos")
    
    return df

if __name__ == "__main__":
    run()
