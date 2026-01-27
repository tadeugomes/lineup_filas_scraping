from pathlib import Path
import pandas as pd

def build_history(curated_dir: str = "data/curated", out_path: str = "data/history/lineup_history.parquet"):
    curated = Path(curated_dir)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    files = list(curated.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"Nenhum parquet encontrado em {curated.resolve()}")

    dfs = []
    for f in files:
        df = pd.read_parquet(f)
        # Add metadata from path if missing
        if "porto_slug" not in df.columns:
            # path like data/curated/porto=XYZ/lineup_YYYY-MM-DD.parquet
            try:
                porto_slug = f.parent.name.replace("porto=", "")
            except Exception:
                porto_slug = None
            df["porto_slug"] = porto_slug
        if "source_file" not in df.columns:
            df["source_file"] = str(f)
        dfs.append(df)

    hist = pd.concat(dfs, ignore_index=True)

    # Standard columns requested by user + metadata
    standard_cols = ["berco", "imo", "navio", "bordo", "comp(m)", "dwt", "carga", 
                     "qtdcarga", "calado(m)", "agencia", "ultima_atualizacao", 
                     "operacao", "prev_chegada"]
    metadata_cols = ["porto", "fonte_url", "porto_slug", "source_file", "id_evento", "produto"]
    
    # Filter to keep only relevant columns
    all_needed = standard_cols + metadata_cols
    existing_cols = [c for c in all_needed if c in hist.columns]
    hist = hist[existing_cols]

    # Enforce string type for all columns to avoid Arrow type mismatches
    # (Parquet/Arrow is strict about schemas, and we may have mixed types from different collectors)
    for col in hist.columns:
        hist[col] = hist[col].astype(str)

    # Deduplicate by id_evento if present; else fallback on subset
    if "id_evento" in hist.columns:
        hist = hist.drop_duplicates(subset=["porto_slug", "id_evento", "prev_chegada"], keep="last")
    else:
        keep_cols = [c for c in ["porto_slug", "porto", "navio", "prev_chegada", "berco"] if c in hist.columns]
        if keep_cols:
            hist = hist.drop_duplicates(subset=keep_cols, keep="last")

    hist.to_parquet(out, index=False)
    return out

if __name__ == "__main__":
    p = build_history()
    print(f"Historico consolidado em: {p}")
