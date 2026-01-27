"""
Coletor de lineup do Porto do Rio Grande
Portos RS (SUPRG)

URL: https://www.portosrs.com.br/site/transparencia/atas_programacao_navio
Tipo: Lista de links para PDFs mensais (muitas vezes documentos escaneados)
"""

import os
import re
import shutil
import glob
import pandas as pd
from bs4 import BeautifulSoup
from loguru import logger

from src.core.fetch import fetch_url
from src.core.storage import save_raw, save_parquet
from src.core.normalize import normalize_produto, make_id

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import pytesseract
    from pdf2image import convert_from_path
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

URL_BASE = "https://www.portosrs.com.br"
URL_PAGE = f"{URL_BASE}/site/transparencia/atas_programacao_navio"
URL_LINEUP_PUBLIC = (
    "http://www.portosrs.com.br/portoweb/zf/login/logar/_module/atracacao/"
    "_controller/rel-lineup/_action/index/cd_usuario/publico/"
)
URL_LINEUP = "http://www.portosrs.com.br/portoweb/zf/atracacao/rel-lineup/index"
URL_LOGIN = "http://www.portosrs.com.br/portoweb/zf/login/index"

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
    df["porto"] = "Rio Grande"
    df["fonte_url"] = URL_PAGE
    return df


def _extract_pdf_links(html: bytes) -> list[str]:
    """Extrai links de PDFs da pagina de atas."""
    soup = BeautifulSoup(html, "lxml")
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "atas_programacao_navio" in href and href.endswith(".pdf"):
            if href.startswith("http"):
                links.append(href)
            else:
                links.append(URL_BASE + href)

    # Ordenar por numero do PDF (mais recente primeiro)
    def extract_num(url):
        match = re.search(r"/(\d+)\.pdf$", url)
        return int(match.group(1)) if match else 0

    links = sorted(set(links), key=extract_num, reverse=True)
    return links


def _is_login_page(html: str) -> bool:
    return "Login" in html and "cd_usuario" in html and "senha" in html


def _fetch_lineup_public_html() -> bytes:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        import httpx
    except Exception:
        return b""

    with httpx.Client(timeout=60, verify=False, headers=headers, follow_redirects=True) as client:
        r = client.get(URL_LINEUP_PUBLIC)
        r.raise_for_status()
        if _is_login_page(r.text):
            return b""
        return r.content


def _fetch_lineup_html() -> bytes:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    cookie = os.getenv("PORTOWEB_COOKIE", "").strip()
    user = os.getenv("PORTOWEB_USER", "").strip()
    password = os.getenv("PORTOWEB_PASS", "").strip()

    try:
        import httpx
    except Exception:
        return b""

    with httpx.Client(timeout=60, verify=False, headers=headers, follow_redirects=True) as client:
        if cookie:
            client.headers["Cookie"] = cookie

        r = client.get(URL_LINEUP)
        r.raise_for_status()
        if not _is_login_page(r.text):
            return r.content

        if not user or not password:
            logger.warning(
                "Rio Grande (Portoweb) exige login. Defina PORTOWEB_USER/PORTOWEB_PASS ou PORTOWEB_COOKIE."
            )
            return b""

        payload = {"cd_usuario": user, "senha": password, "conectar": "Entrar"}
        try:
            client.post(URL_LOGIN, data=payload)
        except Exception:
            pass

        r2 = client.get(URL_LINEUP)
        r2.raise_for_status()
        if _is_login_page(r2.text):
            logger.warning("Rio Grande (Portoweb): login falhou ou acesso nao autorizado.")
            return b""
        return r2.content


def _parse_lineup_html(html: bytes, source_url: str = URL_LINEUP) -> pd.DataFrame:
    if isinstance(html, bytes):
        try:
            html = html.decode("iso-8859-1")
        except Exception:
            html = html.decode("utf-8", errors="ignore")

    try:
        from io import StringIO
        tables = pd.read_html(StringIO(html), flavor="lxml")
    except ValueError:
        return pd.DataFrame()

    if not tables:
        return pd.DataFrame()

    df = None
    for t in tables:
        cols = [str(c).lower() for c in t.columns]
        if any(("navio" in c) or ("embarca" in c) or ("imo" in c) for c in cols):
            df = t
            break
    if df is None:
        df = max(tables, key=lambda t: t.shape[0])

    # Se colunas forem numéricas, tentar usar primeira linha como header
    if all(str(c).isdigit() for c in df.columns):
        first_row = df.iloc[0].astype(str).str.strip().tolist()
        if any("navio" in c.lower() or "embarca" in c.lower() for c in first_row):
            df = df[1:].copy()
            df.columns = first_row

    if isinstance(df.columns, pd.MultiIndex):
        new_cols = []
        for col in df.columns.values:
            levels = [str(l).strip() for l in col if "Unnamed" not in str(l)]
            new_cols.append(levels[-1] if levels else "unknown")
        df.columns = new_cols

    df.columns = [str(c).strip().lower().replace("\n", " ") for c in df.columns]
    df = df.loc[:, ~df.columns.duplicated()].copy()

    df["porto"] = "Rio Grande"
    df["fonte_url"] = source_url

    # Map columns (heuristics)
    for cand in ["navio", "embarcacao", "embarcação", "nome navio", "nome"]:
        if cand in df.columns:
            df["navio"] = df[cand].astype(str)
            break

    for cand in ["chegada", "eta", "prev. chegada", "previsao", "previsão", "data/hora"]:
        if cand in df.columns:
            df["prev_chegada"] = df[cand].astype(str)
            break

    for cand in ["imo", "nº imo", "n. imo", "lloyds"]:
        if cand in df.columns:
            df["imo"] = df[cand].astype(str)
            break

    for cand in ["carga", "mercadoria", "produto"]:
        if cand in df.columns:
            df["carga"] = df[cand].astype(str)
            break

    for cand in ["berco", "berço", "cais", "berco/cais", "berço/cais"]:
        if cand in df.columns:
            df["berco"] = df[cand].astype(str)
            break

    for cand in ["agencia", "agência"]:
        if cand in df.columns:
            df["agencia"] = df[cand].astype(str)
            break

    for cand in ["operacao", "operação", "situacao", "situação"]:
        if cand in df.columns:
            df["operacao"] = df[cand].astype(str)
            break

    for cand in ["calado", "calado (m)"]:
        if cand in df.columns:
            df["calado(m)"] = df[cand].astype(str)
            break

    for cand in ["comprimento", "comprimento (m)", "comp(m)"]:
        if cand in df.columns:
            df["comp(m)"] = df[cand].astype(str)
            break

    # Ensure standard columns
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

    df["produto"] = df["carga"].apply(normalize_produto)
    df["id_evento"] = df.apply(make_id, axis=1)

    final_cols = standard_cols + ["produto", "id_evento", "porto", "fonte_url"]
    cols_to_keep = [c for c in final_cols if c in df.columns]
    return df[cols_to_keep]


def _has_lineup_data(df: pd.DataFrame) -> bool:
    if df is None or df.empty:
        return False
    header_like = {"navio", "embarcacao", "imo", "carga", "operacao", "situacao", "prev", "chegada"}
    for col in ("navio", "imo", "carga", "operacao", "prev_chegada"):
        if col in df.columns:
            series = df[col].astype(str).str.strip().str.lower()
            series = series.replace("nan", "").replace("none", "")
            series = series[~series.isin(header_like)]
            if series.ne("").any():
                return True
    return False


def _parse_pdf(pdf_path: str) -> pd.DataFrame:
    """Parseia tabelas do PDF de atas de Rio Grande. Detecta se e imagem."""
    if not HAS_PDFPLUMBER:
        logger.error("pdfplumber nao instalado, nao e possivel processar PDF")
        return pd.DataFrame()

    all_rows = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Verificar se ha texto em alguma pagina (nao apenas a primeira)
            has_text = False
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text and len(page_text.strip()) >= 10:
                    has_text = True
                    break

            if not has_text:
                logger.info(
                    f"O PDF {pdf_path} parece ser baseado em imagem (scanned). "
                    "Tentando OCR."
                )
                ocr_rows = _ocr_extract_rows(pdf_path)
                if not ocr_rows:
                    logger.info(
                        "OCR indisponivel ou sem dados. Extracao de texto falhou."
                    )
                    return pd.DataFrame()
                return pd.DataFrame(ocr_rows)

            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if table and len(table) > 1:
                        # Rio Grande Atas sao variadas; extracao generica
                        for row in table:
                            clean_row = [str(c).strip() if c is not None else "" for c in row]
                            if any(clean_row):
                                all_rows.append(clean_row)
    except Exception as e:
        logger.error(f"Erro ao processar PDF de Rio Grande: {e}")
        return pd.DataFrame()

    if not all_rows:
        return pd.DataFrame()

    return pd.DataFrame(all_rows)


def _ocr_extract_rows(pdf_path: str) -> list[list[str]]:
    if not HAS_OCR:
        logger.warning(
            "OCR deps ausentes. Instale pytesseract, pdf2image e configure o Tesseract/Poppler."
        )
        return []

    tesseract_cmd = os.getenv("TESSERACT_CMD", "").strip()
    if not tesseract_cmd:
        tesseract_cmd = shutil.which("tesseract") or ""
    if not tesseract_cmd:
        for candidate in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ):
            if os.path.exists(candidate):
                tesseract_cmd = candidate
                break
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    else:
        logger.warning("OCR: tesseract nao encontrado. Configure TESSERACT_CMD.")
        return []

    poppler_path = os.getenv("POPPLER_PATH", "").strip()
    if not poppler_path:
        pdftoppm = shutil.which("pdftoppm")
        if pdftoppm:
            poppler_path = os.path.dirname(pdftoppm)
    if not poppler_path:
        candidates = glob.glob(r"C:\Program Files\poppler-*\Library\bin")
        poppler_path = candidates[0] if candidates else ""
    poppler_path = poppler_path or None
    lang = os.getenv("TESSERACT_LANG", "por")

    try:
        images = convert_from_path(pdf_path, poppler_path=poppler_path)
    except Exception as e:
        logger.error(f"OCR: falha ao converter PDF em imagem: {e}")
        return []

    rows = []
    for img in images:
        try:
            text = pytesseract.image_to_string(img, lang=lang)
        except Exception as e:
            if lang != "eng":
                try:
                    text = pytesseract.image_to_string(img, lang="eng")
                except Exception as e2:
                    logger.error(f"OCR: falha no Tesseract: {e2}")
                    continue
            else:
                logger.error(f"OCR: falha no Tesseract: {e}")
                continue

        for line in text.splitlines():
            line = line.strip()
            if not line or len(line) < 5:
                continue
            cols = re.split(r"\s{2,}", line)
            if len(cols) >= 2:
                rows.append(cols)

    return rows


def _standardize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Tenta padronizar colunas se houver dados."""
    if df.empty:
        return df

    df = df.copy()

    df["porto"] = "Rio Grande"
    df["fonte_url"] = URL_PAGE

    # Initialize all standard columns requested by user
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
        df[col] = ""

    # Basic heuristic for Rio Grande (very variable format)
    if df.shape[1] >= 2:
        df["navio"] = df.iloc[:, 0].astype(str).str.strip()
        df["carga"] = df.iloc[:, 1].astype(str).str.strip()

    if df.shape[1] >= 5:
        df["navio"] = df.iloc[:, 0].astype(str).str.strip()
        df["imo"] = df.iloc[:, 1].astype(str).str.strip()
        df["prev_chegada"] = df.iloc[:, 2].astype(str).str.strip()
        df["carga"] = df.iloc[:, 4].astype(str).str.strip()

    return df


def run() -> pd.DataFrame:
    """Executa coleta do Porto do Rio Grande."""
    logger.info(f"Coletando Rio Grande (Portoweb publico): {URL_LINEUP_PUBLIC}")
    try:
        html_lineup = _fetch_lineup_public_html()
    except Exception as e:
        logger.warning(f"Falha ao buscar lineup publico: {e}")
        html_lineup = b""

    if html_lineup:
        save_raw("rio_grande_lineup_publico", html_lineup, "html")
        df_lineup = _parse_lineup_html(html_lineup, source_url=URL_LINEUP_PUBLIC)
        if _has_lineup_data(df_lineup):
            save_parquet("curated", "rio_grande", df_lineup)
            logger.success(f"Rio Grande (Portoweb publico): {len(df_lineup)} registros extraidos")
            return df_lineup
        logger.info("Portoweb publico sem dados. Tentando acesso autenticado.")

    logger.info(f"Coletando Rio Grande (Portoweb): {URL_LINEUP}")

    try:
        html_lineup = _fetch_lineup_html()
    except Exception as e:
        logger.warning(f"Falha ao buscar lineup Portoweb: {e}")
        html_lineup = b""

    if html_lineup:
        save_raw("rio_grande_lineup", html_lineup, "html")
        df_lineup = _parse_lineup_html(html_lineup, source_url=URL_LINEUP)
        if _has_lineup_data(df_lineup):
            save_parquet("curated", "rio_grande", df_lineup)
            logger.success(f"Rio Grande (Portoweb): {len(df_lineup)} registros extraidos")
            return df_lineup
        logger.info("Portoweb sem dados (ou acesso nao autorizado). Caindo para PDF.")

    logger.info(f"Coletando Rio Grande (PDF): {URL_PAGE}")
    try:
        html = fetch_url(URL_PAGE)
    except Exception as e:
        logger.error(f"Erro ao buscar pagina Rio Grande: {e}")
        empty = _empty_df()
        save_parquet("curated", "rio_grande", empty)
        return empty

    save_raw("rio_grande", html, "html")

    pdf_links = _extract_pdf_links(html)
    if not pdf_links:
        logger.warning("Nenhum link de PDF encontrado para Rio Grande")
        empty = _empty_df()
        save_parquet("curated", "rio_grande", empty)
        return empty

    logger.info(f"Encontrados {len(pdf_links)} PDFs, baixando mais recente: {pdf_links[0]}")

    try:
        pdf_content = fetch_url(pdf_links[0])
    except Exception as e:
        logger.error(f"Erro ao baixar PDF de Rio Grande: {e}")
        empty = _empty_df()
        save_parquet("curated", "rio_grande", empty)
        return empty

    pdf_path = save_raw("rio_grande", pdf_content, "pdf")

    df = _parse_pdf(str(pdf_path))
    if df.empty:
        empty = _empty_df()
        save_parquet("curated", "rio_grande", empty)
        return empty

    df = _standardize_df(df)

    if not df.empty:
        df["produto"] = df["carga"].apply(normalize_produto)
        df["id_evento"] = df.apply(make_id, axis=1)
        save_parquet("curated", "rio_grande", df)
        logger.success(
            f"Rio Grande: {len(df)} registros extraidos (qualidade pode variar)"
        )

    return df


if __name__ == "__main__":
    run()
