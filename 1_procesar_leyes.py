"""
aBOTgado - Indexador de leyes venezolanas (incremental)
========================================================
- Indexa solo PDFs nuevos o modificados (ahorra 30+ minutos)
- Guarda registro en indice_leyes.json
- Usa:  python 1_procesar_leyes.py            → solo nuevos
        python 1_procesar_leyes.py --full      → re-indexar todo
        python 1_procesar_leyes.py --status    → ver estado sin procesar
"""

import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
import re
import json
import hashlib
import shutil
import fitz
import chromadb
import config
import embeddings

# ─── REGISTRO DE ARCHIVOS PROCESADOS ─────────────────────────────────────────

INDICE_PATH = os.path.join(config.BASE_DIR, "indice_leyes.json")


def calcular_hash(ruta: str) -> str:
    """Hash MD5 del archivo para detectar cambios."""
    h = hashlib.md5()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(8192), b""):
            h.update(bloque)
    return h.hexdigest()


def cargar_indice() -> dict:
    """Carga el registro de PDFs ya procesados."""
    if os.path.exists(INDICE_PATH):
        with open(INDICE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def guardar_indice(indice: dict):
    """Guarda el registro de PDFs procesados."""
    with open(INDICE_PATH, "w", encoding="utf-8") as f:
        json.dump(indice, f, indent=2, ensure_ascii=False)


# ─── CONFIGURACIÓN DE LEYES (desde leyes_config.json) ────────────────────────
# Fuente única de verdad: nombres canónicos, PDFs, aliases y ramas.

import pathlib as _pathlib

_LEYES_CONFIG_PATH = _pathlib.Path(__file__).parent / "leyes_config.json"
_leyes_data = json.loads(_LEYES_CONFIG_PATH.read_text(encoding="utf-8"))

# NOMBRES_CORRECTOS: PDF filename → nombre canónico
NOMBRES_CORRECTOS = {}
for _ley in _leyes_data["leyes"]:
    for _pdf in _ley["archivos_pdf"]:
        NOMBRES_CORRECTOS[_pdf] = _ley["nombre"]

# CLASIFICACION_LEYES: nombre canónico → rama del derecho
CLASIFICACION_LEYES = {_ley["nombre"]: _ley["rama"] for _ley in _leyes_data["leyes"]}


# ─── FUNCIONES DE EXTRACCIÓN ─────────────────────────────────────────────────

def extraer_texto(ruta):
    """Extrae texto del PDF y limpia artefactos de paginación."""
    doc   = fitz.open(ruta)
    texto = ""
    for p in doc:
        texto += p.get_text()
    doc.close()
    # Eliminar números de página sueltos: líneas que contienen solo 1-4 dígitos
    # (ej: "\n52\n" ó "\n 53 \n" insertados por PyMuPDF al extraer encabezados/pies)
    texto = re.sub(r'\n[ \t]*\d{1,4}[ \t]*\n', '\n', texto)
    return texto


def detectar_nombre_ley(texto: str, nombre_archivo: str) -> str:
    if nombre_archivo in NOMBRES_CORRECTOS:
        return NOMBRES_CORRECTOS[nombre_archivo]
    encabezado = texto[:500].strip()
    lineas = [l.strip() for l in encabezado.split("\n") if len(l.strip()) > 10]
    if lineas:
        return lineas[0]
    return nombre_archivo.replace("_", " ").replace(".pdf", "").title()


def extraer_articulos(texto, nombre_ley, nombre_pdf):
    articulos      = []
    patron         = r'(?i)(Art[íi]culo\s+(\d+)[°º\.]?\.?)'
    partes         = re.split(patron, texto)
    numeros_vistos = set()

    i = 0
    while i < len(partes):
        if i + 2 < len(partes) and re.match(r'(?i)Art[íi]culo\s+\d+', partes[i]):
            numero    = partes[i + 1].strip()
            contenido = re.sub(r'\n{3,}', '\n\n', partes[i + 2]).strip()
            num_int   = int(numero)

            if num_int not in numeros_vistos and len(contenido) > 30:
                numeros_vistos.add(num_int)
                id_unico = f"{nombre_pdf.replace('.pdf','').replace(' ','_')}_{numero}"
                articulos.append({
                    "id":       id_unico,
                    "texto":    f"Artículo {numero}. {contenido}",
                    "ley":      nombre_ley,
                    "articulo": num_int,
                })
            i += 3
        else:
            i += 1

    return articulos


# ─── LISTAR PDFs (recursivo) ─────────────────────────────────────────────────

def listar_pdfs(carpeta: str) -> list[tuple[str, str]]:
    """
    Busca PDFs en la carpeta y subcarpetas.
    Retorna lista de (ruta_completa, nombre_archivo).
    Si hay duplicados (mismo nombre en raíz y subcarpeta), prioriza la raíz.
    """
    encontrados = {}  # nombre -> ruta

    for dirpath, dirnames, filenames in os.walk(carpeta):
        for f in filenames:
            if f.lower().endswith(".pdf"):
                ruta = os.path.join(dirpath, f)
                # Si ya existe el nombre, priorizar el que está en la raíz
                if f in encontrados:
                    if dirpath == carpeta:
                        encontrados[f] = ruta  # raíz tiene prioridad
                else:
                    encontrados[f] = ruta

    return [(ruta, nombre) for nombre, ruta in sorted(encontrados.items())]


# ─── BORRAR ARTÍCULOS DE UN PDF ──────────────────────────────────────────────

def borrar_articulos_de_pdf(coleccion, nombre_pdf: str):
    """Borra de ChromaDB todos los artículos que vinieron de este PDF."""
    prefijo = nombre_pdf.replace('.pdf', '').replace(' ', '_')
    # Obtener todos los IDs que empiecen con este prefijo
    todos = coleccion.get(include=[])
    ids_borrar = [id_ for id_ in todos["ids"] if id_.startswith(prefijo)]
    if ids_borrar:
        # ChromaDB tiene límite de batch, borrar en lotes
        for i in range(0, len(ids_borrar), 500):
            coleccion.delete(ids=ids_borrar[i:i+500])
    return len(ids_borrar)


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    modo_full   = "--full" in sys.argv
    modo_status = "--status" in sys.argv

    # ── Conectar HuggingFace API ──────────────────────────────────────────────
    if not modo_status:
        print(f"Conectando a HuggingFace API...")
        print(f"   Modelo: {config.EMBEDDING_MODEL}")
        if not embeddings.test_conexion():
            print("Error conectando a HuggingFace API")
            print("   Verifica tu HF_API_KEY en .env")
            return
        print("HuggingFace API conectada")

    # ── Modo full: borrar todo ───────────────────────────────────────────────
    if modo_full:
        print("\n🔄 MODO FULL: Re-indexando todo desde cero...")
        if os.path.exists(config.DB_PATH):
            try:
                shutil.rmtree(config.DB_PATH)
                print("🗑️  Base vectorial anterior borrada")
            except PermissionError:
                print("❌ Error: No puedo borrar la base de datos.")
                print("   Asegúrate de que el bot de Telegram esté APAGADO.")
                return
        # Limpiar índice
        if os.path.exists(INDICE_PATH):
            os.remove(INDICE_PATH)

    # ── Abrir/crear base ChromaDB ────────────────────────────────────────────
    if not modo_status:
        chroma    = chromadb.PersistentClient(path=config.DB_PATH)
        coleccion = chroma.get_or_create_collection(
            name="leyes_venezolanas",
            metadata={"hnsw:space": "cosine"}
        )

    # ── Buscar PDFs ──────────────────────────────────────────────────────────
    if not os.path.exists(config.PDF_FOLDER):
        print(f"⚠️  No encontré la carpeta: {config.PDF_FOLDER}")
        return

    pdfs = listar_pdfs(config.PDF_FOLDER)
    if not pdfs:
        print(f"⚠️  No hay PDFs en: {config.PDF_FOLDER}")
        return

    # ── Cargar índice de procesados ──────────────────────────────────────────
    indice = cargar_indice()

    # ── Clasificar PDFs ──────────────────────────────────────────────────────
    nuevos      = []
    modificados = []
    sin_cambio  = []

    for ruta, nombre in pdfs:
        hash_actual = calcular_hash(ruta)

        if nombre not in indice:
            nuevos.append((ruta, nombre, hash_actual))
        elif indice[nombre]["hash"] != hash_actual:
            modificados.append((ruta, nombre, hash_actual))
        else:
            sin_cambio.append(nombre)

    # PDFs eliminados (estaban en índice pero ya no existen)
    nombres_actuales = {nombre for _, nombre in pdfs}
    eliminados = [n for n in indice if n not in nombres_actuales]

    # ── Mostrar estado ───────────────────────────────────────────────────────
    print(f"\n📊 Estado de la base de leyes:")
    print(f"   📁 Total PDFs encontrados: {len(pdfs)}")
    print(f"   ✅ Ya indexados (sin cambios): {len(sin_cambio)}")
    print(f"   🆕 Nuevos por indexar: {len(nuevos)}")
    print(f"   🔄 Modificados por re-indexar: {len(modificados)}")
    print(f"   🗑️  Eliminados por limpiar: {len(eliminados)}")

    if nuevos:
        print(f"\n   🆕 Nuevos:")
        for _, nombre, _ in nuevos:
            print(f"      + {nombre}")

    if modificados:
        print(f"\n   🔄 Modificados:")
        for _, nombre, _ in modificados:
            print(f"      ~ {nombre}")

    if eliminados:
        print(f"\n   🗑️  Eliminados:")
        for nombre in eliminados:
            print(f"      - {nombre}")

    if modo_status:
        return

    # ── Nada que hacer ───────────────────────────────────────────────────────
    if not nuevos and not modificados and not eliminados:
        print(f"\n✅ Todo al día. No hay nada que procesar.")
        try:
            chroma_check = chromadb.PersistentClient(path=config.DB_PATH)
            col_check = chroma_check.get_collection("leyes_venezolanas")
            print(f"   Total en ChromaDB: {col_check.count()} artículos")
        except Exception:
            pass
        return

    # ── Eliminar artículos de PDFs borrados ──────────────────────────────────
    for nombre in eliminados:
        borrados = borrar_articulos_de_pdf(coleccion, nombre)
        print(f"\n🗑️  {nombre}: {borrados} artículos eliminados de ChromaDB")
        del indice[nombre]

    # ── Eliminar artículos de PDFs modificados (se re-indexarán) ─────────────
    for ruta, nombre, hash_actual in modificados:
        borrados = borrar_articulos_de_pdf(coleccion, nombre)
        print(f"\n🔄 {nombre}: {borrados} artículos anteriores eliminados")

    # ── Procesar nuevos + modificados ────────────────────────────────────────
    por_procesar = nuevos + modificados
    total_nuevos = 0

    for idx_pdf, (ruta, nombre_pdf, hash_actual) in enumerate(por_procesar, 1):
        print(f"\n📄 [{idx_pdf}/{len(por_procesar)}] {nombre_pdf}")

        texto      = extraer_texto(ruta)
        nombre_ley = detectar_nombre_ley(texto, nombre_pdf)
        print(f"   → {nombre_ley}")

        articulos = extraer_articulos(texto, nombre_ley, nombre_pdf)
        print(f"   → {len(articulos)} artículos únicos")

        # Generar embeddings en batch (mucho más rápido que uno por uno)
        textos = [art["texto"][:512] for art in articulos]
        print(f"   Generando embeddings ({len(textos)} articulos)...")
        embs = embeddings.generar_embeddings_batch(textos, batch_size=20)

        rama = CLASIFICACION_LEYES.get(nombre_ley, "general")
        print(f"   → Rama: {rama}")

        for i, (art, emb) in enumerate(zip(articulos, embs)):
            coleccion.upsert(
                ids       =[art["id"]],
                documents =[art["texto"]],
                embeddings=[emb],
                metadatas =[{"ley": art["ley"], "articulo": art["articulo"], "rama": rama}]
            )

            if (i + 1) % 50 == 0 or (i + 1) == len(articulos):
                print(f"   Guardado {i+1}/{len(articulos)}", end="\r")

        print()
        total_nuevos += len(articulos)

        # Guardar en índice
        indice[nombre_pdf] = {
            "hash":       hash_actual,
            "ley":        nombre_ley,
            "articulos":  len(articulos),
        }
        # Guardar después de cada PDF (por si se interrumpe)
        guardar_indice(indice)

    # ── Resumen final ────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"✅ ¡Listo!")
    print(f"   Artículos procesados ahora: {total_nuevos}")
    print(f"   Total en ChromaDB: {coleccion.count()}")
    print(f"   PDFs en índice: {len(indice)}")
    print(f"   Costo total: $0.00 💚")

    if nuevos or modificados:
        print(f"\n   💡 Si agregaste leyes nuevas, actualiza ARTICULOS_CLAVE en 3_bot_telegram.py")


if __name__ == "__main__":
    main()
