import hashlib

# Granéis vegetais de interesse (Centralizado)
VEGETAIS = ("SOJA", "MILHO", "FARELO", "TRIGO", "CEVADA", "MALTE", "GRAO", "GRÃO", "PELLETS", "SOY", "CORN", "MEAL", "WHEAT")

def normalize_produto(x):
    if not isinstance(x, str):
        return None
    x = x.lower()
    if "soja" in x:
        return "soja"
    if "milho" in x:
        return "milho"
    if "farelo" in x:
        return "farelo_soja"
    if "trigo" in x:
        return "trigo"
    return "outros_vegetais"

def make_id(row):
    navio = row.get('navio') or row.get('navio_nome') or ""
    chegada = row.get('prev_chegada') or row.get('eta') or ""
    porto = row.get('porto') or ""
    key = f"{porto}|{navio}|{chegada}"
    return hashlib.sha1(key.encode()).hexdigest()