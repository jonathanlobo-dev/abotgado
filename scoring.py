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
}

# ─── MAPEO LEY → RAMA (resuelve rama por nombre de ley, sin depender del metadata) ─
# Debe coincidir con CLASIFICACION_LEYES en 1_procesar_leyes.py. Se usa como fuente
# de verdad para el filtro de rama ya que el metadata indexado puede estar
# desactualizado o ausente en DBs viejas.
LEY_A_RAMA: dict[str, str] = {
    # Laboral
    "Ley Orgánica del Trabajo (LOTTT)": "laboral",
    "Ley del Seguro Social": "laboral",
    # Penal
    "Código Penal": "penal",
    "Código Orgánico Procesal Penal (COPP)": "penal",
    "Ley Especial contra los Delitos Informáticos": "penal",
    "Ley contra la Corrupción": "penal",
    "Ley Orgánica de Drogas": "penal",
    "Código Orgánico de Justicia Militar": "penal",
    "Ley de Registro de Antecedentes Penales": "penal",
    "Ley Constitucional contra el Odio": "penal",
    "Ley Orgánica contra la Delincuencia Organizada y Financiamiento al Terrorismo (LOPDOFT)": "penal",
    "Ley Contra el Secuestro y la Extorsión": "penal",
    # Civil / Mercantil (tratadas como civil para filtros)
    "Código Civil venezolano": "civil",
    "Código de Procedimiento Civil": "civil",
    "Ley de Registros y Notarías": "civil",
    "Código de Comercio": "civil",
    "Ley de Arrendamientos Inmobiliarios": "civil",
    # Familia
    "Ley Orgánica para la Protección de Niños, Niñas y Adolescentes (LOPNA)": "familia",
    "Ley para la Protección de las Familias, la Maternidad y la Paternidad": "familia",
    "Ley Orgánica sobre el Derecho de las Mujeres a una Vida Libre de Violencia": "familia",
    # Tránsito
    "Ley de Tránsito Terrestre": "transito",
    # Tributario
    "Código Orgánico Tributario": "tributario",
    "Ley de Impuesto Sobre la Renta (ISLR)": "tributario",
    # Vivienda
    "Ley de Propiedad Horizontal": "vivienda",
    "Ley para la Regularización y Control de los Arrendamientos de Vivienda": "vivienda",
    # Constitucional
    "Constitución de la República Bolivariana de Venezuela": "constitucional",
    # Administrativo
    "Ley Orgánica de la Contraloría General de la República": "administrativo",
    "Ley Orgánica de Contraloría Social": "administrativo",
    "Ley Orgánica del Poder Popular": "administrativo",
    "Ley Orgánica de las Comunas": "administrativo",
    "Ley Orgánica de los Consejos Comunales": "administrativo",
    "Ley Orgánica de Gestión Comunitaria": "administrativo",
    "Ley Orgánica del Sistema Económico Comunal": "administrativo",
    "Ley Orgánica de Planificación Pública y Popular": "administrativo",
    "Ley Orgánica de Simplificación de Trámites Administrativos": "administrativo",
    "Ley para la Promoción y Uso del Lenguaje de Género": "administrativo",
    "Ley Orgánica de Justicia de Paz Comunal": "administrativo",
    "Ley de Atención Integral de las Personas Adultas Mayores": "administrativo",
    "Ley para la Inclusión de Personas con Discapacidad": "administrativo",
    "Ley Orgánica de las Zonas Económicas Especiales": "administrativo",
    # Consumidor
    "Ley Orgánica de Precios Justos": "consumidor",
    # Animales / Ambiente
    "Ley de Protección de la Fauna Doméstica": "animales",
    "Ley de Residuos y Desechos Sólidos": "ambiente",
    # General
    "Código de Ética Profesional del Abogado Venezolano": "general",
}


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
    "negocio_casa": "comercial",
    "detencion_arbitraria": "constitucional", "sobreprecio": "consumidor",
    "vicios_ocultos": "civil",
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
