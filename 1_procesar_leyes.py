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


# ─── NOMBRES CORRECTOS ───────────────────────────────────────────────────────

NOMBRES_CORRECTOS = {
    # ── Leyes base ────────────────────────────────────────────────────────────
    "ley_transito_terrestre.pdf":                   "Ley de Tránsito Terrestre",
    "constitucion.pdf":                             "Constitución de la República Bolivariana de Venezuela",
    "CONSTITUCIÓN DE LA REPÚBLICA BOLIVARIANA DE VENEZUELA.pdf":
        "Constitución de la República Bolivariana de Venezuela",
    "CÓDIGO_CIVIL.pdf":                             "Código Civil venezolano",
    "CÓDIGO CIVIL.pdf":                             "Código Civil venezolano",
    "CÓDIGO_PROCEDIMIENTO_CIVIL.pdf":               "Código de Procedimiento Civil",
    "CÓDIGO PROCEDIMIENTO CIVIL.pdf":               "Código de Procedimiento Civil",
    "ley_trabajo.pdf":                              "Ley Orgánica del Trabajo (LOTTT)",

    # ── Familia, Niñez y Mujer ────────────────────────────────────────────────
    "lopna.pdf":
        "Ley Orgánica para la Protección de Niños, Niñas y Adolescentes (LOPNA)",
    "LEY DE REFORMA PARCIAL DE LA LEY ORGÁNICA PARA LA PROTECCIÓN DE NIÑOS, NIÑAS Y ADOLESCENTES.pdf":
        "Ley Orgánica para la Protección de Niños, Niñas y Adolescentes (LOPNA)",
    "LEY ORGÁNICA DE REFORMA A LA LEY ORGÁNICA SOBRE EL DERECHO DE LAS MUJERES A UNA VIDA LIBRE DE VIOLENCIA.pdf":
        "Ley Orgánica sobre el Derecho de las Mujeres a una Vida Libre de Violencia",
    "LEY DE REFORMA DE LA LEY PARA LA PROTECCIÓN DE LAS FAMILIAS, LA MATERNIDAD Y LA PATERNIDAD.pdf":
        "Ley para la Protección de las Familias, la Maternidad y la Paternidad",
    "LEY CONSTITUCIONAL CONTRA EL ODIO POR LA CONVIVENCIA PACÍFICA Y LA TOLERANCIA.pdf":
        "Ley Constitucional contra el Odio",

    # ── Vivienda y Arrendamiento ──────────────────────────────────────────────
    "LEY CONTRA EL DESALOJO ARBITRARIO DE VIVIENDAS.pdf":
        "Ley contra el Desalojo Arbitrario de Viviendas",
    "LEY REGULARIZACIÓN Y CONTROL ARRENDAMIENTOS DE VIVIENDA.pdf":
        "Ley para la Regularización y Control de los Arrendamientos de Vivienda",
    "DECRETO N° 929 MEDIANTE EL CUAL SE DICTA EL DECRETO CON RANGO VALOR Y FUERZA DE LEY DE REGULACIÓN DEL ARRENDAMIENTO INMOBILIARIO PARA EL USO COMERCIAL.pdf":
        "Ley de Regulación del Arrendamiento Inmobiliario para el Uso Comercial",
    "LEY PROPIEDAD HORIZONTAL.pdf":
        "Ley de Propiedad Horizontal",

    # ── Discapacidad y Fauna ──────────────────────────────────────────────────
    "LEY ORGÁNICA PARA LA INCLUSIÓN, IGUALDAD Y DESARROLLO INTEGRAL DE LAS PERSONAS CON DISCAPACIDAD.pdf":
        "Ley para la Inclusión de Personas con Discapacidad",
    "LEY ORGÁNICA PARA LA INCLUSIÓN, IGUALDAD Y DESARROLLO INTEGRAL DE LAS PERSONAS CON DISCAPACIDAD (2).pdf":
        "Ley para la Inclusión de Personas con Discapacidad",
    "LEY PARA LA PROTECCIÓN DE LA FAUNA DOMÉSTICA LIBRE Y EN CAUTIVERIO.pdf":
        "Ley de Protección de la Fauna Doméstica",

    # ── Corrupción, Estado y Municipio ────────────────────────────────────────
    "LEY DE REFORMA DEL DECRETO CON RANGO, VALOR Y FUERZA DE LEY CONTRA LA CORRUPCIÓN.pdf":
        "Ley contra la Corrupción",
    "LEY ORGÁNICA DEL PODER PÚBLICO MUNICIPAL.pdf":
        "Ley Orgánica del Poder Público Municipal",
    "ley_organica_de_la_contraloria_general_de_la_republica.pdf":
        "Ley Orgánica de la Contraloría General de la República",
    "LEY DE REFORMA DE LA LEY ORGÁNICA DE CONTRALORÍA SOCIAL.pdf":
        "Ley Orgánica de Contraloría Social",

    # ── Registros y Notarías ──────────────────────────────────────────────────
    "LEY DE REGISTROS Y NOTARIAS.pdf":
        "Ley de Registros y Notarías",

    # ── Trabajadores Residenciales ────────────────────────────────────────────
    "DECRETO LEY PARA LA DIGNIFICACIÓN TRABAJADORES RESIDENCIALES.pdf":
        "Ley Especial para la Dignificación de Trabajadores Residenciales",

    # ── Ambiente ──────────────────────────────────────────────────────────────
    "LEY ORGÁNICA DEL AMBIENTE.pdf":                "Ley Orgánica del Ambiente",
    "LEY ORGÁNICA DE AMBIENTE.pdf":                 "Ley Orgánica del Ambiente",
    "LEY DE RESIDUOS Y DESECHOS SOLIDOS.pdf":       "Ley de Residuos y Desechos Sólidos",

    # ── Comunas y Poder Popular ──────────────────────────────────────────────
    "LEY ORGÁNICA DE GESTIÓN COMUNITARIA.pdf":      "Ley Orgánica de Gestión Comunitaria",
    "LEY ORGÁNICA DE LAS COMUNAS.pdf":              "Ley Orgánica de las Comunas",
    "LEY ORGÁNICA DE REFORMA DE LA LEY ORGÁNICA DE LOS CONSEJOS COMUNALES.pdf":
        "Ley Orgánica de los Consejos Comunales",
    "LEY ORGÁNICA DE REFORMA DE LA LEY ORGÁNICA DEL PODER POPULAR.pdf":
        "Ley Orgánica del Poder Popular",
    "L.O. SISTEMA ECONÓMICO COMUNAL.pdf":           "Ley Orgánica del Sistema Económico Comunal",
    "LEY ORGÁNICA DEL SISTEMA ECONÓMICO COMUNAL.pdf": "Ley Orgánica del Sistema Económico Comunal",
    "LEY ORGÁNICA CONSEJO FEDERAL DE GOBIERNO.pdf": "Ley Orgánica del Consejo Federal de Gobierno",
    "DECRETO 8959 REGLAMENTO LEY ORGÁNICA DEL CONSEJO FEDERAL DE GOBIERNO 2012.pdf":
        "Reglamento de la Ley Orgánica del Consejo Federal de Gobierno",
    "ley_organica_de_planificacion_publica_y_popular.pdf":
        "Ley Orgánica de Planificación Pública y Popular",
    "DECRETO CON RANGO, VALOR Y FUERZA DE LEY DE REFORMA DE LA LEY ORGÁNICA DE PLANIFICACIÓN PÚBLICA Y POPULAR.pdf":
        "Ley Orgánica de Planificación Pública y Popular",

    # ── Género ────────────────────────────────────────────────────────────────
    "LEY PARA LA PROMOCIÓN Y USO DEL LENGUAJE DE GÉNERO.pdf":
        "Ley para la Promoción y Uso del Lenguaje de Género",

    # ── Código Penal ──────────────────────────────────────────────────────────
    "codigo_penal.pdf":                             "Código Penal",
    "reforma-del-codigo-penal.pdf":                 "Código Penal",

    # ── Justicia de Paz Comunal ──────────────────────────────────────────────
    "LEY DE REFORMA PARCIAL DE LA LEY ORGÁNICA DE LA JURISDICCIÓN ESPECIAL DE JUSTICIA DE PAZ COMUNAL.pdf":
        "Ley de Justicia de Paz Comunal",

    # ── Personas Adultas Mayores ─────────────────────────────────────────────
    "LEY ORGÁNICA PARA LA ATENCIÓN Y DESARROLLO INTEGRAL DE LAS PERSONAS ADULTAS MAYORES.pdf":
        "Ley de Atención Integral de las Personas Adultas Mayores",

    # ── Código de Comercio ───────────────────────────────────────────────────
    "codigo-de-comercio.pdf":                      "Código de Comercio",

    # ── Tributario ───────────────────────────────────────────────────────────
    "6-Código Orgánico Tributario 2020.pdf":        "Código Orgánico Tributario",

    # ── Justicia Militar ─────────────────────────────────────────────────────
    "codigo-organico-de-justicia-militar.pdf":      "Código Orgánico de Justicia Militar",

    # ── Arrendamiento (duplicado con otro nombre) ────────────────────────────
    "mietengesetz-venezuela.pdf":
        "Ley para la Regularización y Control de los Arrendamientos de Vivienda",

    # ── Zonas Económicas Especiales ──────────────────────────────────────────
    "ley-organi-20220801161552.pdf":
        "Ley Orgánica de las Zonas Económicas Especiales",

    # ── Registro de Antecedentes Penales ─────────────────────────────────────
    "ley-regist-20220728163728.pdf":
        "Ley de Registro de Antecedentes Penales",
}


# ─── FUNCIONES DE EXTRACCIÓN ─────────────────────────────────────────────────

def extraer_texto(ruta):
    doc   = fitz.open(ruta)
    texto = ""
    for p in doc:
        texto += p.get_text()
    doc.close()
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

        for i, (art, emb) in enumerate(zip(articulos, embs)):
            coleccion.upsert(
                ids       =[art["id"]],
                documents =[art["texto"]],
                embeddings=[emb],
                metadatas =[{"ley": art["ley"], "articulo": art["articulo"]}]
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
