# lineup_pipeline (MVP)

Coleta de lineups públicos (programação de navios) de portos brasileiros e exportação para Parquet local.
Focado em **granéis vegetais**: soja, milho, farelo, trigo.

## Portos Suportados

| Porto | Estado | Autoridade | Tipo de Fonte |
|-------|--------|------------|---------------|
| Santos | SP | SPA | HTML |
| Paranaguá/Antonina | PR | APPA | HTML |
| Itaqui | MA | EMAP | HTML (Web Status) |
| Rio Grande | RS | Portos RS | HTML (Portoweb) + PDF (OCR) + HTML (Pilots) |
| São Francisco do Sul | SC | SCPAR | PDF |
| Vila do Conde | PA | CDP | HTML |
| Santarém | PA | CDP | HTML |
| Aratu-Candeias | BA | CODEBA | HTML |
| Ilhéus | BA | CODEBA | HTML |
| Salvador | BA | CODEBA | HTML |

## Rodar (Linux/Mac/Windows)
```bash
python -m venv .venv
# Linux/Mac:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate

pip install -U pip
pip install pandas pyarrow httpx beautifulsoup4 lxml camelot-py[cv] pdfplumber python-dateutil loguru

python -m src.main
```

## Gerar histórico consolidado
Após rodar a coleta, consolide tudo em um único Parquet:

```bash
python -m src.build_history
```

Saída:
- `data/history/lineup_history.parquet`

## Saídas
- `data/raw/`     (HTML/PDF baixados)
- `data/curated/` (Parquet por porto e data)
- `data/history/` (histórico consolidado)

## Estrutura do Projeto

```
lineup_pipeline/
├── src/
│   ├── main.py              # Orquestrador principal
│   ├── build_history.py     # Consolidação de histórico
│   ├── core/
│   │   ├── fetch.py         # HTTP client
│   │   ├── normalize.py     # Normalização de produtos
│   │   └── storage.py       # Salva raw/parquet
│   └── ports/
│       ├── cdp.py               # Vila do Conde + Santarém
│       ├── paranagua_appa.py    # Paranaguá/Antonina
│       ├── santos_spa.py        # Santos (oficial)
│       ├── santos_ecoporto.py   # Santos (fallback)
│       ├── itaqui_web.py        # Itaqui (Web Status)
│       ├── rio_grande.py        # Rio Grande (Portoweb/PDF)
│       ├── rio_grande_pilots.py # Rio Grande (Praticos da Barra)
│       ├── sao_francisco_sul.py # São Francisco do Sul
│       └── codeba.py            # Aratu, Ilhéus, Salvador
├── data/
│   ├── raw/      # Arquivos brutos baixados
│   ├── curated/  # Parquet processados
│   └── history/  # Histórico consolidado
└── pyproject.toml
```

## Observações

- **Santos**: Usa fonte oficial da SPA. Se falhar, tenta fallback Ecoporto.
- **Rio Grande**: tenta primeiro o lineup web publico e, se nao houver dados, tenta o Portoweb com login
  (`PORTOWEB_USER`/`PORTOWEB_PASS` ou `PORTOWEB_COOKIE`). Fallback para PDFs mensais (muitos sao escaneados; para OCR
  instale `pytesseract` e `pdf2image`, instale o Tesseract no sistema e configure `TESSERACT_CMD`, e (no Windows)
  instale Poppler e configure `POPPLER_PATH`). Complemento: Praticos da Barra (`https://www.rgpilots.com.br/atracados`).
- **São Francisco do Sul**: PDF pode apresentar instabilidade (timeout).
- **Paranaguá/Antonina (APPA)**: o site pode exigir login. Para coletar, defina
  `APPAWEB_USER` e `APPAWEB_PASS`, ou use `APPAWEB_COOKIE` com os cookies de sessão
  do navegador (ex.: `ASP.NET_SessionId=...; SessionIDInstance=...`).
