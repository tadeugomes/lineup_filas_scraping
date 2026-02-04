import pandas as pd
import re
from src.core.fetch import fetch_url
from src.core.storage import save_raw, save_parquet
from src.core.normalize import normalize_produto, make_id, VEGETAIS

SOURCES = {
    # "vila_do_conde": {
    #     "porto_label": "Vila do Conde",
    #     "porto_slug": "cdp_vila_do_conde",
    #     "url": "https://www.cdp.com.br/programacao-de-navios-do-porto-de-vila-do-conde/",
    # },
    "santarem": {
        "porto_label": "Santarém",
        "porto_slug": "cdp_santarem",
        "url": "https://cdpport.cdp.com.br/cdpport/pesquisa.aspx?WCI=relLineUp_008&Mv=Link&sqlCodDominio=6",
    },
}

# VEGETAIS agora importado de core.normalize


def _extract_berco_label(raw: str) -> str:
    if not raw:
        return ""
    text = " ".join(str(raw).split())
    m = re.search(r"\(([^)]+)\)", text)
    if m:
        return m.group(1).strip()
    m = re.search(r"BER.?O\s+(.*?)(?:-LOA|$)", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text


def _expand_cdp_table(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.columns, pd.MultiIndex):
        return df

    field_map = {
        "PROGRAMACAO": "programacao",
        "EMBARCACAO": "embarcacao",
        "AGENTE": "agente",
        "ETA": "eta",
        "CHEGADA": "chegada",
        "ATRACACAO": "atracacao",
        "DESATRACACAO": "desatracacao",
        "STATUS": "status",
        "MERCADORIA": "mercadoria",
        "QUANTIDADET": "quantidade (t)",
        "CLIENTE": "cliente",
        "OPERADOR": "operador",
    }

    entries = []
    for col in df.columns:
        parts = [str(p).strip() for p in col if p is not None]
        parts = [p for p in parts if p and not p.lower().startswith("unnamed")]
        berth = None
        field = None
        for p in parts:
            norm = re.sub(r"[^A-Z]", "", p.upper())
            if not berth and "BER" in norm:
                berth = p
            if not field and norm in field_map:
                field = field_map[norm]
        if berth and field:
            entries.append((col, berth, field))

    if not entries:
        return df

    from collections import defaultdict

    grouped = defaultdict(list)
    for col, berth, field in entries:
        grouped[berth].append((col, field))

    frames = []
    for berth, cols in grouped.items():
        sub = df[[c for c, _ in cols]].copy()
        sub.columns = [field for _, field in cols]
        sub["berco"] = _extract_berco_label(berth)
        frames.append(sub)

    out = pd.concat(frames, ignore_index=True)
    if "embarcacao" in out.columns:
        out = out[out["embarcacao"].astype(str).str.strip().ne("")].copy()
    return out


def _standardize_df(df: pd.DataFrame, porto_label: str, url: str) -> pd.DataFrame:
    df = df.copy()
    # Normalize headers to lowercase for easier mapping
    df.columns = [str(c).strip().lower().replace("\n", " ") for c in df.columns]
    
    df["porto"] = porto_label
    df["fonte_url"] = url

    # Mapping columns
    standard_cols = ["berco", "imo", "navio", "bordo", "comp(m)", "dwt", "carga", 
                     "qtdcarga", "calado(m)", "agencia", "ultima_atualizacao", 
                     "operacao", "prev_chegada", "status", "chegada", "atracacao", "desatracacao"]
    
    # Initialize missing
    for col in standard_cols:
        if col not in df.columns:
            df[col] = ""

    # Ship name -> 'embarcação'
    navio_col = None
    for cand in ["embarcação", "embarcacao", "navio", "embarcação/nome"]:
        if cand in df.columns:
            navio_col = cand
            break
    if navio_col:
        df["navio"] = df[navio_col].astype(str)
        
    # ETA / Previsão -> 'eta' or 'chegada'
    if "eta" in df.columns:
        df["prev_chegada"] = df["eta"].astype(str)
    
    # Status
    if "status" in df.columns:
        df["status"] = df["status"].astype(str)

    # Cargo -> 'mercadoria'
    if "mercadoria" in df.columns:
        df["carga"] = df["mercadoria"].astype(str)
        
    # Qtd -> 'quantidade (t)'
    qtd_col = next((c for c in df.columns if "quantidade" in c), None)
    if qtd_col:
        df["qtdcarga"] = df[qtd_col].astype(str)
        
    # Agente
    if "agente" in df.columns:
        df["agencia"] = df["agente"].astype(str)
        
    # Operador
    if "operador" in df.columns:
        df["operacao"] = df["operador"].astype(str)

    # filter vegetal (best-effort)
    mask = df["carga"].str.upper().str.contains("|".join(VEGETAIS), na=False)
    if mask.any():
        df = df.loc[mask].copy()

    df["produto"] = df["carga"].apply(normalize_produto)
    df["id_evento"] = df.apply(make_id, axis=1)

    # Garantir tipos compatíveis com Parquet (evita objetos mistos, ex.: float/str)
    def _to_str(v):
        if pd.isna(v):
            return ""
        if isinstance(v, bytes):
            try:
                return v.decode("utf-8", errors="ignore")
            except Exception:
                return str(v)
        return str(v)

    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(_to_str)
    
    return df

def run_all():
    out = {}
    for key, cfg in SOURCES.items():
        url = cfg["url"]
        porto_slug = cfg["porto_slug"]
        porto_label = cfg["porto_label"]

        html = fetch_url(url)
        save_raw(porto_slug, html, "html")

        try:
            tables = pd.read_html(html, flavor="lxml")
        except ValueError:
            tables = []
            
        frames = []
        for t in tables:
            if isinstance(t.columns, pd.MultiIndex):
                cols_str = " ".join(
                    str(x).upper()
                    for level in range(t.columns.nlevels)
                    for x in t.columns.get_level_values(level)
                )
            else:
                cols_str = " ".join([str(c).upper() for c in t.columns])

            cols_norm = re.sub(r"[^A-Z]", "", cols_str)
            if "EMBARC" in cols_norm or "NAVIO" in cols_norm:
                if isinstance(t.columns, pd.MultiIndex):
                    t = _expand_cdp_table(t)
                frames.append(t)

        if frames:

            df = pd.concat(frames, ignore_index=True)
        elif tables:
            df = max(tables, key=lambda t: t.size)
        else:
            df = pd.DataFrame()

        if not df.empty:
            df = _expand_cdp_table(df)
            df = _standardize_df(df, porto_label=porto_label, url=url)
            save_parquet("curated", porto_slug, df)
            out[key] = df
    return out
