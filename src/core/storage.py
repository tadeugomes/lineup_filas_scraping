from pathlib import Path
import pandas as pd
from datetime import datetime

BASE = Path("data")

def save_raw(porto: str, content: bytes, ext: str) -> Path:
    dt = datetime.now().strftime("%Y-%m-%d")
    path = BASE / "raw" / f"porto={porto}" / f"dt={dt}"
    path.mkdir(parents=True, exist_ok=True)
    file = path / f"lineup.{ext}"
    file.write_bytes(content)
    return file

def save_parquet(layer: str, porto: str, df: pd.DataFrame):
    dt = datetime.now().strftime("%Y-%m-%d")
    path = BASE / layer / f"porto={porto}"
    path.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path / f"lineup_{dt}.parquet", index=False)