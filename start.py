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
    forzar_reindex = os.getenv("REINDEX", "").lower() in ("1", "true", "si")

    if not chroma_existe or forzar_reindex:
        razon = "REINDEX=1 activado" if forzar_reindex else "ChromaDB no encontrada"
        print(f"\n[!] {razon}. Indexando leyes...")
        print("    Esto toma ~10-15 minutos.\n")

        # Borrar ChromaDB vieja si existe (para reindex limpio)
        if forzar_reindex and chroma_existe:
            import shutil
            shutil.rmtree(config.DB_PATH)
            print("    ChromaDB anterior eliminada.")

        # Importar y ejecutar el indexador
        from importlib import import_module
        sys.argv = ["1_procesar_leyes.py", "--full"]
        indexador = import_module("1_procesar_leyes")
        indexador.main()

        print("\n[OK] Indexación completada.\n")
    else:
        print(f"\n[OK] ChromaDB encontrada en {config.DB_PATH}")

    # Crear carpeta de documentos generados
    docs_dir = os.path.join(str(config.DATA_DIR), "documentos_generados")
    os.makedirs(docs_dir, exist_ok=True)

    # Arrancar el bot
    print("\n[>>] Arrancando bot de Telegram...\n")
    from importlib import import_module
    bot = import_module("3_bot_telegram")
    bot.main()


if __name__ == "__main__":
    main()
