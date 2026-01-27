from src.ports.cdp import run_all as cdp_run_all
from src.ports.itaqui_web import run as itaqui_web
from src.ports.paranagua_appa import run as paranagua
from src.ports.santos_ecoporto import run as santos_ecoporto
from src.ports.santos_spa import run as santos_spa
from src.ports.rio_grande import run as rio_grande
from src.ports.rio_grande_tecon import run as rio_grande_tecon
from src.ports.rio_grande_pilots import run as rio_grande_pilots
from src.ports.sao_francisco_sul import run as sao_francisco_sul
from src.ports.sfs_seatrade import run as sfs_seatrade
from src.ports.codeba import run_all as codeba_run_all
from loguru import logger


def main():
    """Executa coleta de todos os portos."""
    
    print("[*] Coletando CDP - Vila do Conde + Santarem")
    try:
        cdp_run_all()
    except Exception as e:
        logger.error(f"Erro CDP: {e}")

    print("[*] Coletando Porto do Itaqui (Web: atracados/fundeados/esperados)")
    try:
        itaqui_web()
    except Exception as e:
        logger.error(f"Erro Itaqui: {e}")

    print("[*] Coletando Paranagua/Antonina (APPA)")
    try:
        paranagua()
    except Exception as e:
        logger.error(f"Erro Paranaguá: {e}")

    print("[*] Coletando Santos (SPA - fonte oficial)")
    try:
        santos_spa()
    except Exception as e:
        logger.error(f"Erro Santos SPA: {e}")
        print("  [!] Tentando fallback Ecoporto...")
        try:
            santos_ecoporto()
        except Exception as e2:
            logger.error(f"Erro Santos Ecoporto: {e2}")

    print("[*] Coletando Porto do Rio Grande (Portoweb + Atas + Tecon + Pilots)")
    try:
        rio_grande()
        rio_grande_tecon()
        rio_grande_pilots()
    except Exception as e:
        logger.error(f"Erro Rio Grande: {e}")

    print("[*] Coletando Sao Francisco do Sul (PDF + Seatrade)")
    try:
        sao_francisco_sul()
        sfs_seatrade()
    except Exception as e:
        logger.error(f"Erro São Francisco do Sul: {e}")

    print("[*] Coletando CODEBA (Aratu, Ilheus, Salvador)")
    try:
        codeba_run_all()
    except Exception as e:
        logger.error(f"Erro CODEBA: {e}")

    print("[OK] Coleta finalizada!")


if __name__ == "__main__":
    main()
