import pandas as pd
from bs4 import BeautifulSoup
from src.core.fetch import fetch_url
from src.core.storage import save_raw, save_parquet
from src.core.normalize import make_id

URL = "https://op.ecoportosantos.com.br/externa/LineUpListaAtracacao"

def run():
    html = fetch_url(URL)
    save_raw("santos_ecoporto", html, "html")

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # The page is mostly a sequence of fields; we extract in a best-effort way:
    # Look for known statuses and capture the next tokens as ship/viagem/berco/eta.
    statuses = {"Previsto", "Em Operação", "Desatracado", "Encerrado"}
    rows = []
    i = 0
    while i < len(lines):
        if lines[i] in statuses:
            status = lines[i]
            # Next line usually begins with ship name and voyage, berth etc.
            if i + 1 < len(lines):
                payload = lines[i + 1]
                parts = payload.split()
                navio = parts[0] if parts else None
                viagem = parts[1] if len(parts) > 1 else None
                berco = parts[2] if len(parts) > 2 else None
                # Find a date-like token (dd/mm/yyyy)
                eta = None
                for p in parts:
                    if "/" in p and len(p) >= 8:
                        eta = p
                        break
                rows.append(
                    {
                        "porto": "Santos", 
                        "fonte_url": URL, 
                        "status": status, 
                        "navio": navio, 
                        "viagem": viagem, 
                        "berco": berco, 
                        "prev_chegada": eta,
                        "imo": "",
                        "bordo": "",
                        "comp(m)": "",
                        "dwt": "",
                        "carga": "",
                        "qtdcarga": "",
                        "calado(m)": "",
                        "agencia": "",
                        "ultima_atualizacao": "",
                        "operacao": ""
                    }
                )
            i += 2
        else:
            i += 1

    df = pd.DataFrame(rows)
    if not df.empty:
        df["id_evento"] = df.apply(make_id, axis=1)

    save_parquet("curated", "santos_ecoporto", df)
    return df