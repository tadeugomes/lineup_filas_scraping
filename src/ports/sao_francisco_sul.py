"""
Coletor de lineup do Porto de São Francisco do Sul
SCPAR Porto SFS

URL: https://www.portosaofrancisco.com.br/public/uploads/pdfs/lineup.pdf
Tipo: PDF direto (link fixo)
"""

import pandas as pd
from loguru import logger

from src.core.fetch import fetch_url
from src.core.storage import save_raw, save_parquet
from src.core.normalize import normalize_produto, make_id, VEGETAIS

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

URL = "https://www.portosaofrancisco.com.br/public/uploads/pdfs/lineup.pdf"

# VEGETAIS agora importado de core.normalize


def _parse_pdf(pdf_path: str) -> pd.DataFrame:
    """Parseia tabelas do PDF de lineup com lógica específica para SFS."""
    if not HAS_PDFPLUMBER:
        logger.error("pdfplumber não instalado, não é possível processar PDF")
        return pd.DataFrame()
    
    all_rows = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table:
                        continue
                    
                    for row in table:
                        clean_row = [str(c).strip() if c is not None else "" for c in row]
                        
                        # Heurística para SFS:
                        # Coluna 2: Nome do Navio
                        # Coluna 3: IMO
                        # Coluna 10 ou 11: Chegada Barra / ETA
                        # Coluna 15: Produto
                        
                        if len(clean_row) < 16:
                            continue
                            
                        # Validar se é uma linha de dados
                        navio = clean_row[2]
                        imo = clean_row[3].replace(".", "").replace("-", "")
                        
                        if not navio or navio.lower() in ["navios", "nome", "embarcação"]:
                            continue
                            
                        if not (imo.isdigit() and len(imo) >= 6) and not any(v in clean_row[15].upper() for v in VEGETAIS):
                            # Se não tem IMO válido e não é um vegetal óbvio, ignorar
                            if not navio.replace(" ", "").isalpha(): # Check if it looks like a ship name
                                continue

                        row_dict = {
                            "navio": navio,
                            "imo": clean_row[3],
                            "prev_chegada": clean_row[10] if clean_row[10] else clean_row[11],
                            "carga": clean_row[15],
                            "berco": clean_row[8] if len(clean_row) > 8 else "",
                            "comp(m)": clean_row[5],
                            "calado(m)": clean_row[7],
                            "agencia": clean_row[9],
                            "operacao": clean_row[13],
                            "qtdcarga": clean_row[16] if len(clean_row) > 16 else "",
                            "bordo": "",
                            "dwt": "",
                            "ultima_atualizacao": ""
                        }
                        all_rows.append(row_dict)
                            
    except Exception as e:
        logger.error(f"Erro ao processar PDF de SFS: {e}")
        return pd.DataFrame()
    
    if not all_rows:
        return pd.DataFrame()
    
    return pd.DataFrame(all_rows)


def _standardize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Padroniza colunas para o schema comum do pipeline."""
    df = df.copy()
    df["porto"] = "São Francisco do Sul"
    df["fonte_url"] = URL
    return df


def _filter_vegetais(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra apenas cargas de granéis vegetais."""
    if df.empty or "carga" not in df.columns:
        return df
    
    # REMOVIDO: Agora retorna todos os dados sem filtrar
    logger.info(f"SFS: Mantendo todos os {len(df)} registros (filtro de vegetais desabilitado)")
    return df


def run() -> pd.DataFrame:
    """Executa coleta do Porto de São Francisco do Sul."""
    logger.info(f"Coletando São Francisco do Sul: {URL}")
    
    try:
        pdf_content = fetch_url(URL)
    except Exception as e:
        logger.error(f"Erro ao baixar PDF de São Francisco do Sul: {e}")
        return pd.DataFrame()
    
    pdf_path = save_raw("sao_francisco_sul", pdf_content, "pdf")
    
    # Parsear PDF
    df = _parse_pdf(str(pdf_path))
    if df.empty:
        logger.warning("Nenhum dado extraído do PDF de São Francisco do Sul")
        return df
    
    df = _standardize_df(df)
    df = _filter_vegetais(df)
    
    if not df.empty:
        df["produto"] = df["carga"].apply(normalize_produto)
        df["id_evento"] = df.apply(make_id, axis=1)
        save_parquet("curated", "sao_francisco_sul", df)
        logger.success(f"São Francisco do Sul: {len(df)} registros salvos")
    
    return df


if __name__ == "__main__":
    run()
