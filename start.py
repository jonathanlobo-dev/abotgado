"""
aBOTgado - Script de inicio para Railway
==========================================
1. Verifica si ChromaDB ya existe en el Volume
2. Si no existe, indexa las leyes automáticamente
3. Arranca el bot
"""

import os
import sys
import config


def main():
    print("=" * 50)
    print("aBOTgado - Iniciando...")
    print(f"  DATA_DIR: {config.DATA_DIR}")
    print(f"  DB_PATH:  {config.DB_PATH}")
    print(f"  PDFs:     {config.PDF_FOLDER}")
    print("=" * 50)

    # Crear DATA_DIR si no existe (Railway Volume)
    os.makedirs(config.DATA_DIR, exist_ok=True)

    # Verificar si ChromaDB ya existe
    chroma_existe = os.path.exists(config.DB_PATH) and os.listdir(config.DB_PATH)

    # Detectar cambios en PDFs + config (nombre + tamaño + leyes_config.json → hash)
    # Incrementar REINDEX_VERSION para forzar reindex en el próximo deploy
    REINDEX_VERSION = "4"
    import hashlib
    pdf_hash_file = os.path.join(str(config.DATA_DIR), ".pdf_hash")
    pdfs_actuales = 0
    pdf_fingerprint = ""
    if os.path.exists(config.PDF_FOLDER):
        pdfs = sorted(f for f in os.listdir(config.PDF_FOLDER) if f.endswith(".pdf"))
        pdfs_actuales = len(pdfs)
        # Hash de nombres + tamaños para detectar reemplazos
        partes = []
        for f in pdfs:
            try:
                sz = os.path.getsize(os.path.join(config.PDF_FOLDER, f))
            except OSError:
                sz = 0
            partes.append(f"{f}:{sz}")
        # También incluir leyes_config.json en el fingerprint
        # para detectar cambios en mapeo de leyes/aliases/ramas
        config_path = os.path.join(str(config.BASE_DIR), "leyes_config.json")
        if os.path.exists(config_path):
            try:
                cfg_sz = os.path.getsize(config_path)
                partes.append(f"leyes_config.json:{cfg_sz}")
            except OSError:
                pass
        partes.append(f"REINDEX_VERSION:{REINDEX_VERSION}")
        pdf_fingerprint = hashlib.md5("|".join(partes).encode()).hexdigest()

    fingerprint_anterior = ""
    if os.path.exists(pdf_hash_file):
        try:
            fingerprint_anterior = open(pdf_hash_file).read().strip()
        except IOError:
            pass

    hay_leyes_nuevas = pdf_fingerprint != fingerprint_anterior
    forzar_reindex = os.getenv("REINDEX", "").lower() in ("1", "true", "si")

    if not chroma_existe or forzar_reindex or hay_leyes_nuevas:
        if hay_leyes_nuevas:
            razon = f"Cambios en PDFs detectados ({pdfs_actuales} PDFs, fingerprint cambió)"
        elif forzar_reindex:
            razon = "REINDEX=1 activado"
        else:
            razon = "ChromaDB no encontrada"
        print(f"\n[!] {razon}. Indexando leyes...")
        print("    Esto toma ~10-15 minutos.\n")

        # Borrar ChromaDB vieja para reindex limpio
        if chroma_existe:
            import shutil
            shutil.rmtree(config.DB_PATH)
            print("    ChromaDB anterior eliminada.")

        # Importar y ejecutar el indexador
        from importlib import import_module
        sys.argv = ["1_procesar_leyes.py", "--full"]
        indexador = import_module("1_procesar_leyes")
        indexador.main()

        # Guardar fingerprint de PDFs para próxima vez
        with open(pdf_hash_file, "w") as f:
            f.write(pdf_fingerprint)

        print("\n[OK] Indexación completada.\n")
    else:
        print(f"\n[OK] ChromaDB encontrada en {config.DB_PATH} ({pdfs_actuales} PDFs)")

    # Crear carpeta de documentos generados
    docs_dir = os.path.join(str(config.DATA_DIR), "documentos_generados")
    os.makedirs(docs_dir, exist_ok=True)

    # Arrancar API REST en hilo de fondo (para Telegram Mini App)
    # Hilo daemon: si start.py termina, el hilo termina con él.
    # Si el hilo falla, el bot de Telegram NO se ve afectado.
    try:
        import threading
        import uvicorn

        api_port = int(os.getenv("PORT", 8080))

        def _run_api():
            print(f"[>>] Arrancando API REST en puerto {api_port}...")
            uvicorn.run("api:app", host="0.0.0.0", port=api_port, log_level="info")

        api_thread = threading.Thread(target=_run_api, daemon=True, name="api-rest")
        api_thread.start()
        print(f"[OK] API REST arrancando en segundo plano (puerto {api_port})\n")
    except Exception as e:
        print(f"[!] No se pudo arrancar API REST: {e} — el bot continúa igual.\n")

    # Arrancar el bot
    print("\n[>>] Arrancando bot de Telegram...\n")
    from importlib import import_module
    bot = import_module("3_bot_telegram")
    bot.main()


if __name__ == "__main__":
    main()
