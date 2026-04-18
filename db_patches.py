"""
db_patches.py — Parches puntuales para chunks mal indexados en ChromaDB.

Cada parche tiene:
  - id:       identificador único del parche (para saber si ya se aplicó)
  - ley:      nombre exacto de la ley en ChromaDB
  - articulo: número del artículo (int)
  - texto:    texto correcto del artículo
  - detectar: texto que identifica el chunk erróneo (substring)

Se aplican en start.py antes de arrancar el bot. Son idempotentes:
si el chunk ya tiene el texto correcto, no se toca.
"""

from __future__ import annotations
import os
import json
import logging

logger = logging.getLogger(__name__)

# ─── REGISTRO DE PARCHES ─────────────────────────────────────────────────────
# Agregar aquí cada corrección puntual. Formato:
# {
#   "id":       str único,
#   "ley":      str (nombre exacto en ChromaDB),
#   "articulo": int,
#   "texto":    str (texto correcto completo),
#   "detectar": str (substring del texto erróneo — para saber si hay que parchear),
# }

PARCHES: list[dict] = [
    {
        "id": "lovlv_15_formas_violencia_v1",
        "ley": "Ley Orgánica sobre el Derecho de las Mujeres a una Vida Libre de Violencia",
        "articulo": 15,
        "detectar": "quedando la redacción en los términos siguientes",
        "texto": (
            "Artículo 15. Formas de violencia. Se consideran formas de violencia de género "
            "en contra de las mujeres, las siguientes:\n"
            "1. Violencia psicológica: toda conducta activa u omisiva ejercida en deshonra, "
            "descrédito o menosprecio al valor o dignidad personal, tratos humillantes y "
            "vejatorios, vigilancia constante, aislamiento, marginalización, negligencia, "
            "abandono, celotipia, comparaciones destructivas, amenazas y actos que conllevan "
            "a la víctima a disminuir su autoestima, perjudicar o perturbar su sano desarrollo.\n"
            "2. Acoso u hostigamiento: toda conducta abusiva y especialmente los comportamientos, "
            "palabras, actos, gestos, escritos o mensajes electrónicos dirigidos a perseguir, "
            "intimidar, chantajear, apremiar, importunar y vigilar a una mujer que pueda atentar "
            "contra su estabilidad emocional, dignidad, prestigio, integridad física o psíquica.\n"
            "3. Amenaza: el anuncio verbal o con actos de la ejecución de un daño físico, "
            "psicológico, sexual, laboral o patrimonial con el fin de intimidar a la mujer.\n"
            "4. Violencia física: toda acción u omisión que directa o indirectamente está "
            "dirigida a ocasionar un daño o sufrimiento físico a la mujer, tales como: "
            "lesiones internas o externas, heridas, hematomas, quemaduras, empujones o "
            "cualquier otro maltrato que afecte su integridad física.\n"
            "5. Violencia doméstica: toda conducta activa u omisiva, constante o no, de "
            "empleo de fuerza física o violencia psicológica, intimidación, persecución o "
            "amenaza contra la mujer por parte del cónyuge, el concubino, ex cónyuge, ex "
            "concubino, persona con quien mantiene o mantuvo relación de afectividad, "
            "ascendientes, descendientes, parientes colaterales, consanguíneos y afines.\n"
            "6. Violencia sexual: toda conducta que amenace o vulnere el derecho de la mujer "
            "a decidir voluntaria y libremente su sexualidad, comprendiendo ésta no sólo el "
            "acto sexual sino toda forma de contacto o acceso sexual, genital o no genital.\n"
            "7. Acceso carnal violento: forma de violencia sexual en la cual el hombre mediante "
            "violencias o amenazas, constriñe a la cónyuge, concubina, persona con quien hace "
            "vida marital o mantenga unión estable de hecho o no, a un acto carnal por vía "
            "vaginal, anal u oral, o introduzca objetos por alguna de las dos primeras vías.\n"
            "8. Prostitución forzada, 9. Esclavitud sexual, 10. Acoso sexual, 11. Violencia laboral, "
            "12. Violencia patrimonial y económica, 13. Violencia obstétrica, 14. Esterilización "
            "forzada, 15. Violencia mediática, 16. Violencia institucional, 17. Violencia simbólica, "
            "18. Tráfico de mujeres, niñas y adolescentes, 19. Trata de mujeres, niñas y "
            "adolescentes, 20. Femicidio, 21. Inducción o ayuda al suicidio."
        ),
    },
    {
        "id": "cpc_340_libelo_v1",
        "ley": "Código de Procedimiento Civil",
        "articulo": 340,
        "detectar": "fundamentales del recurso",   # texto del chunk erróneo
        "texto": (
            "Artículo 340 \n"
            "El libelo de la demanda deberá expresar: \n"
            "\n"
            "1° La indicación del Tribunal ante el cual se propone la demanda. \n"
            "2° El nombre, apellido y domicilio del demandante y del demandado y el carácter que tiene. \n"
            "3° Si el demandante o el demandado fuere una persona jurídica, la demanda deberá contener la "
            "denominación o razón social y los datos relativos a su creación o registro. \n"
            "4° El objeto de la pretensión, el cual deberá determinarse con precisión, indicando su situación y "
            "linderos, si fuere inmueble; las marcas, colores, o distintivos si fuere semoviente; los signos, "
            "señales y particularidades que puedan determinar su identidad, si fuere mueble; y los datos, "
            "títulos y explicaciones necesarios si se tratare de derechos u objetos incorporales. \n"
            "5° La relación de los hechos y los fundamentos de derecho en que se base la pretensión, "
            "con las pertinentes conclusiones. \n"
            "6° Los instrumentos en que se fundamente la pretensión, esto es, aquéllos de los cuales se "
            "derive inmediatamente el derecho deducido, los cuales deberán producirse con el libelo. \n"
            "7° Si se demandare la indemnización de daños y perjuicios, la especificación de éstos y sus causas. \n"
            "8° El nombre y apellido del mandatario y la consignación del poder. \n"
            "9° La sede o dirección del demandante a que se refiere el artículo 174."
        ),
    },
]


# ─── ARCHIVO DE CONTROL ───────────────────────────────────────────────────────

def _ruta_control(data_dir: str) -> str:
    return os.path.join(data_dir, ".db_patches_aplicados.json")


def _cargar_aplicados(data_dir: str) -> set[str]:
    ruta = _ruta_control(data_dir)
    if not os.path.exists(ruta):
        return set()
    try:
        return set(json.loads(open(ruta).read()))
    except Exception:
        return set()


def _guardar_aplicados(data_dir: str, aplicados: set[str]):
    ruta = _ruta_control(data_dir)
    with open(ruta, "w") as f:
        json.dump(sorted(aplicados), f)


# ─── APLICADOR ───────────────────────────────────────────────────────────────

def aplicar_parches(data_dir: str, db_path: str) -> int:
    """Aplica parches pendientes a ChromaDB. Retorna número de parches aplicados.

    Es idempotente: si el chunk ya tiene el texto correcto (o el parche ya fue
    aplicado en un deploy anterior), no hace nada.
    """
    import chromadb

    aplicados = _cargar_aplicados(data_dir)
    pendientes = [p for p in PARCHES if p["id"] not in aplicados]

    if not pendientes:
        logger.info("[db_patches] Todos los parches ya aplicados.")
        return 0

    try:
        client = chromadb.PersistentClient(db_path)
        col = client.get_collection("leyes_venezolanas")
    except Exception as e:
        logger.warning(f"[db_patches] No se pudo conectar a ChromaDB: {e}")
        return 0

    # Importar módulo de embeddings del proyecto
    try:
        from busqueda import embeddings as emb_module
    except Exception as e:
        logger.warning(f"[db_patches] No se pudo importar embeddings: {e}")
        return 0

    n_aplicados = 0
    for parche in pendientes:
        try:
            pid = parche["id"]
            ley = parche["ley"]
            art = parche["articulo"]
            texto_correcto = parche["texto"]
            detectar = parche["detectar"]

            # Buscar chunks actuales del artículo
            r = col.get(
                where={"$and": [
                    {"ley": {"$eq": ley}},
                    {"articulo": {"$eq": art}},
                ]},
                include=["documents", "metadatas"],
            )

            if not r["ids"]:
                # No hay ningún chunk — insertar directamente
                logger.info(f"[db_patches] {pid}: Art. {art} no encontrado, insertando.")
                necesita_insertar = True
                ids_a_borrar = []
            else:
                # Verificar si algún chunk tiene el texto erróneo
                tiene_error = any(detectar in doc for doc in r["documents"])
                ya_correcto = any(
                    texto_correcto[:50] in doc or "El libelo de la demanda" in doc
                    for doc in r["documents"]
                )
                if ya_correcto and not tiene_error:
                    logger.info(f"[db_patches] {pid}: ya correcto, saltando.")
                    aplicados.add(pid)
                    continue
                necesita_insertar = True
                ids_a_borrar = r["ids"]

            # Borrar chunks erróneos
            if ids_a_borrar:
                col.delete(ids=ids_a_borrar)
                logger.info(f"[db_patches] {pid}: eliminados {len(ids_a_borrar)} chunks erróneos.")

            if necesita_insertar:
                # Generar embedding y agregar chunk correcto
                emb = emb_module.generar_embedding(texto_correcto)
                nuevo_id = f"patch_{pid}"
                # Obtener rama del chunk anterior si estaba disponible
                rama = "civil"
                if r.get("metadatas"):
                    rama = r["metadatas"][0].get("rama", "civil")

                col.add(
                    ids=[nuevo_id],
                    documents=[texto_correcto],
                    metadatas=[{"ley": ley, "articulo": art, "rama": rama}],
                    embeddings=[emb],
                )
                logger.info(f"[db_patches] {pid}: chunk correcto insertado (ID: {nuevo_id}).")

            aplicados.add(pid)
            n_aplicados += 1

        except Exception as e:
            logger.error(f"[db_patches] Error aplicando parche {parche['id']}: {e}")

    _guardar_aplicados(data_dir, aplicados)

    if n_aplicados:
        logger.info(f"[db_patches] {n_aplicados} parche(s) aplicado(s).")
    return n_aplicados
