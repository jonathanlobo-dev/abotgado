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

# REEMPLAZOS_TEXTO: PDF filename → [[buscar, reemplazar], ...]
# Corrige artefactos de OCR puntuales (ej: el ordinal "1°" leído como "10" o
# "12", que crea artículos fantasma y ensombrece a los reales). Se definen en
# leyes_config.json (campo opcional "reemplazos_texto" por ley) para no
# hardcodear correcciones en el código.
REEMPLAZOS_TEXTO: dict[str, list] = {}
for _ley in _leyes_data["leyes"]:
    if _ley.get("reemplazos_texto"):
        for _pdf in _ley["archivos_pdf"]:
            REEMPLAZOS_TEXTO[_pdf] = _ley["reemplazos_texto"]

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


def detectar_nombre_ley(texto: str, nombre_archivo: str) -> str | None:
    """Nombre canónico desde leyes_config.json. None si el PDF no está registrado.

    Antes había un fallback que tomaba la primera línea del PDF como nombre de
    ley — en gacetas eso produce basura tipo "6.854 Extraordinario GACETA
    OFICIAL..." que contamina la DB con leyes fantasma. Fuente única de verdad:
    todo PDF debe registrarse en leyes_config.json o se salta con advertencia.
    """
    return NOMBRES_CORRECTOS.get(nombre_archivo)


# Encabezados estructurales que aparecen ENTRE artículos y no deben quedar
# pegados al final del artículo anterior. Anclado a inicio de línea y seguido de
# numeral romano/ordinal/arábigo (o palabra estructural) para no cortar frases
# legítimas como "título de propiedad" o "sección de un terreno" en medio del texto.
# Artículos-preámbulo de leyes de reforma: las gacetas de reforma empiezan con
# "Artículo 1. Se modifica el artículo 30, en la forma siguiente: ..." y luego
# reimprimen el texto íntegro. Como la deduplicación se queda con la PRIMERA
# ocurrencia de cada número, esos artículos de la reforma ENSOMBRECEN a los
# artículos reales del mismo número (bug detectado en COPP, Justicia de Paz,
# Violencia contra la Mujer, Corrupción, Poder Popular, Familias/Maternidad).
# Se descartan: su cuerpo es fórmula de reforma, no derecho sustantivo.
# El sustantivo puede venir con rellenos: "Se agrega un NUEVO artículo",
# "Se incorpora un nuevo artículo", "Se agregan DOS numerales MÁS",
# "Se modifica EL ACÁPITE Y el artículo 2". Permitimos hasta 40 chars entre
# el verbo y el sustantivo estructural. OJO: "Se crea..." NO se filtra —
# es contenido sustantivo legítimo (leyes que crean instituciones/fondos).
_RE_FORMULA_REFORMA = re.compile(
    r'^\s*Se\s+(?:modifica|reforma|incorpora|suprime|elimina|agrega|sustituye)n?\b'
    r'[^.]{0,40}?'
    r'\b(?:art[íi]culo|t[íi]tulo|cap[íi]tulo|secci[oó]n|ep[íi]grafe|'
    r'denominaci[oó]n|numeral|literal|disposici[oó]n|ac[aá]pite)',
    re.IGNORECASE,
)

_RE_CORTE_SECCION = re.compile(
    r'(?im)^\s*(?:'
    r'(?:cap[ií]tulo|t[ií]tulo|secci[oó]n|sub-?secci[oó]n)\s+'
    r'(?:[ivxlcdm]{1,7}|primer[oa]|segund[oa]|tercer[oa]|cuart[oa]|quint[oa]|'
    r'sext[oa]|s[eé]ptim[oa]|octav[oa]|noven[oa]|d[eé]cim[oa]|'
    r'[0-9]{1,3}|preliminar|[uú]nic[oa]|final)\b'
    r'|disposici[oó]n(?:es)?\s+(?:transitori|final|derogatori|general|complementari)'
    r')'
)


# Palabras que preceden a una REFERENCIA intratexto ("...en el artículo 39...")
# y nunca a una cabecera real. Si la palabra anterior a "Artículo N." es una de
# estas, NO es cabecera y no se parte la línea.
_PALABRAS_REFERENCIA = frozenset(
    "el del al este ese dicho dicha presente siguiente anterior mismo misma "
    "citado citada referido referida los las un una y o u e en con por sobre "
    "segun según conforme ver vease véase numeral paragrafo parágrafo".split()
)

# Cabecera inline: epígrafe y cabecera en la misma línea (común en gacetas con
# layout a columnas), ej: "Requisitos de importación y exportación Artículo 24."
# Detectado en Ley de Salud Agrícola Integral (30+ artículos perdidos).
# Guardas anti-falso-positivo (el bug histórico eran referencias intratexto):
#   1. 'Artículo' con A mayúscula (las referencias van en minúscula casi siempre)
#   2. el número debe ir seguido de punto/°/º (referencias usan coma o nada)
#   3. la palabra anterior no puede ser determinante/preposición de referencia
_RE_CABECERA_INLINE = re.compile(
    r'(\S+)([ \t]+)(Artículo[ \t]*\n?[ \t]*\d+[ \t]*[.°º])'
)


# Referencia intratexto partida por el wrapping del PDF: la línea termina en
# un conector ("...previstos en el") y la siguiente empieza con "artículo 114"
# (minúscula). El patrón anclado a inicio de línea la tomaba como CABECERA,
# mutilando el artículo real (ej: Precios Justos Art. 51 quedaba en 15 chars
# y aparecía un art. "114" espurio). Se re-une con su línea anterior.
# Solo minúscula: las cabeceras reales van con 'Artículo' capitalizado.
_RE_REF_PARTIDA = re.compile(
    # (?m) sin (?i): 'artículo' SOLO en minúscula — cabeceras reales van con
    # 'Artículo' capitalizado y no deben re-unirse.
    r'(?m)^(.*?\b(?:' + '|'.join(_PALABRAS_REFERENCIA) + r'))[ \t]*\n[ \t]*(art[íi]culo[ \t]+\d)'
)


def _desenvolver_referencias(texto: str) -> str:
    """Une referencias 'el \\n artículo N' partidas por el wrapping del PDF."""
    # Iterar hasta estabilizar (una línea puede contener varias referencias)
    prev = None
    while prev != texto:
        prev = texto
        texto = _RE_REF_PARTIDA.sub(lambda m: f"{m.group(1)} {m.group(2)}", texto)
    return texto


def _normalizar_cabeceras(texto: str) -> str:
    """Inserta salto de línea antes de cabeceras 'Artículo N.' que quedaron a
    mitad de línea (pegadas al epígrafe), para que el patrón anclado a inicio
    de línea las detecte. Conservador: ante la duda, no toca nada."""
    def _reemplazo(m):
        palabra_previa = m.group(1).strip().strip('.,;:()').lower()
        if palabra_previa in _PALABRAS_REFERENCIA:
            return m.group(0)  # referencia intratexto — no tocar
        return f"{m.group(1)}\n{m.group(3)}"
    return _RE_CABECERA_INLINE.sub(_reemplazo, texto)


def extraer_articulos(texto, nombre_ley, nombre_pdf):
    r"""
    Divide el texto del PDF en artículos individuales.

    BUG HISTÓRICO (corregido): el patrón antiguo r'(?i)(Art[íi]culo\s+(\d+)...)'
    matcheaba TAMBIÉN referencias intratexto del tipo "...previsto en el
    artículo 414..." y las trataba como nueva cabecera, cortando el cuerpo del
    artículo real en mitad de oración (terminado en preposición tipo "en el",
    "a que se refiere el", etc.). Causó ~80 artículos mutilados en la corpus
    (CP 413, CC 135/494/497, Ley contra la Corrupción 38, etc.).

    FIX: anclar el patrón a INICIO DE LÍNEA con re.MULTILINE. Las cabeceras
    reales aparecen al inicio de línea; las referencias intratexto van en medio
    de oraciones (después de "el", "del", "al"...) y nunca al inicio de línea.
    """
    articulos      = []
    # Re-unir referencias intratexto partidas por el wrapping del PDF
    texto          = _desenvolver_referencias(texto)
    # Rescatar cabeceras que quedaron a mitad de línea (epígrafe + cabecera)
    texto          = _normalizar_cabeceras(texto)
    # ^\s* + MULTILINE: solo matchea "Artículo N" al INICIO de línea (con
    # indentación opcional). Bloquea referencias intratexto.
    patron         = r'(?im)^\s*(Art[íi]culo\s+(\d+)[°º\.]?\.?)'
    partes         = re.split(patron, texto)
    numeros_vistos = set()

    i = 0
    while i < len(partes):
        if i + 2 < len(partes) and re.match(r'(?i)\s*Art[íi]culo\s+\d+', partes[i]):
            numero    = partes[i + 1].strip()
            contenido = re.sub(r'\n{3,}', '\n\n', partes[i + 2]).strip()
            # El cuerpo del artículo es todo hasta el siguiente "Artículo N", así
            # que los encabezados de CAPÍTULO/TÍTULO/SECCIÓN/DISPOSICIONES (y sus
            # notas marginales) que van ENTRE artículos se desbordan al final del
            # anterior. Los recortamos. Anclado a inicio de línea + numeral/ordinal
            # para no cortar frases tipo "título de propiedad" en medio del texto.
            corte = _RE_CORTE_SECCION.search(contenido)
            if corte:
                contenido = contenido[:corte.start()].strip()
            num_int   = int(numero)

            # Saltar artículos-preámbulo de reforma ("Se modifica el artículo...")
            # para que NO ensombrezcan al artículo real con el mismo número.
            if _RE_FORMULA_REFORMA.match(contenido):
                i += 3
                continue

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
        for _buscar, _reemplazar in REEMPLAZOS_TEXTO.get(nombre_pdf, []):
            texto = texto.replace(_buscar, _reemplazar)
        nombre_ley = detectar_nombre_ley(texto, nombre_pdf)
        if nombre_ley is None:
            print(f"   ⚠️  SALTADO: '{nombre_pdf}' no está registrado en leyes_config.json")
            print(f"      Agrega una entrada (id, nombre, rama, archivos_pdf, aliases) y reintenta.")
            continue
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
