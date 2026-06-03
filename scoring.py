"""
aBOTgado - Módulo de scoring y ranking
=======================================
- Scoring unificado (embedding, BM25, domain boost)
- Mapeos ley→rama, tema→rama
- Exclusiones de leyes por tema
- Constantes de puntuación
"""

# ─── UMBRAL DE RECHAZO ──────────────────────────────────────────────────────

# Umbral de distancia coseno para considerar un artículo semánticamente relevante.
# < UMBRAL_RECHAZO → relevante; >= UMBRAL_RECHAZO → rechazar (query fuera de dominio legal).
UMBRAL_RECHAZO: float = 0.75


# ─── LEYES A EXCLUIR DEL RETRIEVAL SECUNDARIO CUANDO UN TEMA ES PRINCIPAL ───
# Cuando el tema principal ya cubre el caso, estas leyes producen artículos
# semánticamente cercanos pero contextualmente incorrectos.
LEYES_EXCLUIR_POR_TEMA: dict[str, set[str]] = {
    "animales_via": {
        # CP Art. 480 (matar animal ajeno) y Fauna Doméstica Art. 12 (abandono
        # declarado por municipio) no aplican a la prohibición de animales en vía
        "Código Penal",
        "Ley de Protección de la Fauna Doméstica",
    },
    "comercial": {
        # CRBV Art. 44 (libertad personal/arresto) llega como falso positivo BM25
        # en queries de registro de empresa. Los derechos constitucionales
        # al emprendimiento (Art. 112) deben incluirse directamente en ARTICULOS_CLAVE
        # si son necesarios, no via retrieval secundario.
        "Constitución de la República Bolivariana de Venezuela",
    },
    "negocio_casa": {
        # Mismo caso: CRBV no es relevante para permisos de negocio en casa
        "Constitución de la República Bolivariana de Venezuela",
    },
    "vivienda_arrendamiento": {
        # La Ley especial de Arrendamientos de Vivienda (2011) rige todo.
        # CC Art. 1587/1590 (vicios/reparaciones del arrendador) llegan como
        # falsos positivos semánticos y no aplican a casos de mora o desalojo.
        "Código Civil venezolano",
    },
    "vivienda_desalojo": {
        # Ley de Arrendamientos Inmobiliarios rige el procedimiento de desalojo.
        # CC Art. 1587/1590 llegan como falsos positivos semánticos pero no aplican.
        "Código Civil venezolano",
    },
    "transito_estacionamiento": {
        # CC Art. 660 (servidumbre de paso para predios enclavados) llega como
        # falso positivo semántico en queries sobre apartar puesto / obstaculizar vía.
        "Código Civil venezolano",
    },
    "libre_transito": {
        # Mismo caso: CC no es relevante para obstaculización de vía pública.
        "Código Civil venezolano",
    },
    "herencia": {
        # Ley de Tránsito Art. 58 (RCV/seguro obligatorio) y
        # Ley de Registros y Notarías Art. 40 (certificaciones) llegan como
        # falsos positivos semánticos cuando la query involucra un vehículo
        # heredado. El CC (Art. 822+) y el SENIAT son la fuente correcta.
        "Ley de Tránsito Terrestre",
        "Ley de Registros y Notarías",
    },
    "lesiones_personales": {
        # CRBV aparece como falso positivo (Art. 54 esclavitud, Art. 114 consumidor,
        # Art. 271 imprescriptibilidad) cuando el reformulador LLM malinterpreta
        # "golpear con la cartera" como crimen económico. La respuesta correcta
        # es siempre el CP (Arts. 414-422 lesiones). La CRBV no aplica directamente.
        "Constitución de la República Bolivariana de Venezuela",
    },
    "bancario": {
        # LCC (Ley contra la Corrupción) aparece como falso positivo semántico
        # para queries de comisiones/cobros bancarios. La LCC regula funcionarios
        # públicos, no bancos privados; LISB (Arts. 59, 62, 71, 80) es la ley correcta.
        "Ley contra la Corrupción",
    },
    "ciencia_tecnologia": {
        # Código de Comercio aparece como falso positivo ("empresa" + "obligaciones")
        # en queries sobre LOCTI. La LOCTI rige las obligaciones de I+D; el Código de
        # Comercio regula actos de comercio y sociedades, no investigación científica.
        "Código de Comercio",
    },
    "moneda_curso_legal": {
        # Código de Comercio Arts. 449/489 (letras de cambio/cheques) aparecen como
        # falsos positivos para queries sobre obligatoriedad de petro/dólar.
        # La institución correcta es SUNDDE y el fundamento es la CRBV/Ley del BCV.
        "Código de Comercio",
    },
}

# ─── MAPEO LEY → RAMA (desde leyes_config.json) ───────────────────────────────
# Fuente única de verdad: leyes_config.json define nombre canónico → rama.
import json as _json
import pathlib as _pathlib

_leyes_cfg = _json.loads(
    _pathlib.Path(__file__).parent.joinpath("leyes_config.json")
    .read_text(encoding="utf-8")
)
LEY_A_RAMA: dict[str, str] = {
    _ley["nombre"]: _ley["rama"] for _ley in _leyes_cfg["leyes"]
}
del _leyes_cfg


def rama_de_ley(nombre_ley: str) -> str:
    """Retorna la rama del derecho de una ley. 'general' si no se conoce."""
    return LEY_A_RAMA.get(nombre_ley, "general")


# ─── MAPEO TEMA → RAMA (debe coincidir con CLASIFICACION_LEYES del indexador) ─
RAMA_POR_TEMA = {
    "laboral_despido": "laboral", "laboral_vacaciones": "laboral",
    "laboral_prestaciones": "laboral", "laboral_general": "laboral",
    "transito_infracciones": "transito", "transito_licencia": "transito",
    "transito_accidente": "transito", "transito_vehiculo": "transito",
    "transito_general": "transito", "transito_estacionamiento": "transito",
    "libre_transito": "civil",
    "drogas": "penal", "corrupcion": "penal", "penal": "penal",
    "civil": "civil", "propiedad": "civil", "testamento": "civil", "divorcio": "civil",
    "comercial": "civil",
    "familia": "familia", "maternidad_paternidad": "familia", "despido_maternidad": "laboral",
    "violencia_mujer": "familia",
    "vivienda_cc": "vivienda", "vivienda_desalojo": "vivienda",
    "vivienda_arrendamiento": "vivienda", "arrendamiento_comercial": "vivienda",
    "propiedad_horizontal": "vivienda",
    "derechos": "constitucional", "comunicaciones": "constitucional",
    "tributario": "tributario",
    "animales": "animales", "animales_via": "transito", "ambiente": "ambiente",
    "discapacidad": "administrativo", "municipal": "administrativo",
    "trabajadores_residenciales": "laboral",
    "proteccion_consumidor": "civil", "mala_praxis": "penal",
    "deuda_civil": "civil",
    "robo_vehiculo": "penal", "pago_feriados": "laboral", "permiso_medico": "laboral",
    "herencia": "civil", "amenazas": "penal",
    "recurso_multa": "administrativo",
    "negocio_casa": "administrativo",
    "negocio_sanidad_alimentos": "administrativo",
    "decomiso_mercancia": "administrativo",
    "demanda_civil_general": "civil",
    "consulta_generica": "civil",
    "alcabala_revision": "penal",
    "lesiones_personales": "penal",
    "maltrato_animal": "administrativo",
    "detencion_arbitraria": "constitucional", "sobreprecio": "consumidor",
    "vicios_ocultos": "civil",
    "insai_sanidad": "administrativo",
    "marca_propiedad_industrial": "comercial",
    "licores_alcohol": "tributario",
    "secuestro_extorsion": "penal",
    "odio_discriminacion": "penal",
    "bancario": "bancario",
    "laboral_contratista": "laboral",
    "difamacion": "penal",
    "moneda_curso_legal": "constitucional",
    "consejos_comunales": "administrativo",
    "comunas": "administrativo",
    "contraloria": "administrativo",
    "entrega_cargos_publicos": "administrativo",
    "residuos_desechos": "administrativo",
    "etica_abogado": "administrativo",
    "poder_popular": "administrativo",
    "permisos_sanitarios": "administrativo",
    "justicia_militar": "penal",
    "ciencia_tecnologia": "tecnologia",
    "alimentos_regulacion": "administrativo",
    "genero_lenguaje": "constitucional",
    "infogobierno": "administrativo",
    "arrendamiento_comercial_ley": "civil",
    "desalojo_arbitrario": "vivienda",
    "poder_publico_municipal": "administrativo",
    "ambiente_ley": "ambiente",
}


# ─── SCORING UNIFICADO ──────────────────────────────────────────────────────

def _score_embedding(distancia: float) -> float:
    """Convierte distancia coseno (0–0.75) a score (1.0–0.0)."""
    return max(0.0, 1.0 - distancia / 0.75)


def _score_bm25(score: float, max_score: float) -> float:
    """Normaliza score BM25 al rango 0.0–1.0."""
    return score / max_score if max_score > 0 else 0.0


SCORE_ARTICULO_CLAVE = 0.95  # Keyword match exacto → alta confianza
SCORE_DIRECTO = 1.0          # Lookup exacto "Art. X de Ley Y" → confianza máxima

# Umbral mínimo de score_final para pasar artículos al LLM.
# Si el mejor artículo candidato tiene score_final < este valor,
# se descarta todo el contexto → LLM activa el mensaje "sin artículos específicos".
# Valor calibrado: keyword match = 0.95, embedding bueno = 0.4-0.7, basura = 0.10-0.20
UMBRAL_MIN_RELEVANCIA_FINAL: float = 0.22

# Domain boost: artículos de la rama correcta suben, los de otra rama bajan,
# la CRBV (constitucional) nunca se penaliza porque aplica a todos los dominios.
DOMAIN_BOOST   = 1.3
DOMAIN_NEUTRAL = 1.0
DOMAIN_PENALTY = 0.5

# Límites de diversidad en resultados finales
MAX_POR_LEY = 4
MAX_TOTAL = 10


def _domain_multiplier(rama_art: str, ramas_detectadas: "set[str] | None") -> float:
    """Multiplicador de relevancia según coincidencia de rama legal."""
    if not ramas_detectadas:
        return 1.0
    if rama_art in ramas_detectadas:
        return DOMAIN_BOOST
    if rama_art in ("constitucional", "general"):
        return DOMAIN_NEUTRAL  # CRBV y genéricas nunca penalizadas
    return DOMAIN_PENALTY
