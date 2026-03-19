"""
aBOTgado - Motor de busqueda hibrida
======================================
- Artículos clave por tema (keyword matching)
- BM25 (palabras exactas)
- Embeddings (semántica)
- Búsqueda directa por artículo
- Guías institucionales por tema
- Respuesta con LLM (Groq)
"""

import re
import logging
import unicodedata
import chromadb
from groq import Groq
from rank_bm25 import BM25Okapi

import config
import embeddings

logger = logging.getLogger(__name__)

# ─── CLIENTES ─────────────────────────────────────────────────────────────────

groq_client = Groq(api_key=config.GROQ_API_KEY)
chroma      = chromadb.PersistentClient(path=config.DB_PATH)
coleccion   = chroma.get_collection("leyes_venezolanas")

# ─── ÍNDICE BM25 ──────────────────────────────────────────────────────────────

logger.info("Construyendo índice BM25...")
todos      = coleccion.get(include=["documents", "metadatas"], limit=10000)
docs_bm25  = todos["documents"]
metadatas  = todos["metadatas"]


def tokenizar(texto: str) -> list[str]:
    texto = texto.lower()
    texto = re.sub(r'[^\w\sáéíóúüñ]', ' ', texto)
    return texto.split()


corpus_tokenizado = [tokenizar(doc) for doc in docs_bm25]
bm25              = BM25Okapi(corpus_tokenizado)
logger.info(f"Índice BM25 listo — {len(docs_bm25)} artículos")


# ─── ARTÍCULOS CLAVE POR TEMA ────────────────────────────────────────────────

ARTICULOS_CLAVE = {
    "transito": {
        "keywords": ["carro", "coche", "vehículo", "vehiculo", "moto", "motocicleta",
                     "camión", "camion", "alcabala", "tránsito", "transito", "seguro",
                     "rcv", "licencia", "conducir", "conductor", "accidente", "choque",
                     "multa", "placa", "circulación", "circulacion", "autopista",
                     "certificado médico", "certificado medico", "revision vehicular",
                     "revisión vehicular", "papeles del carro", "documentos del carro",
                     "registro vehicular", "titulo de propiedad vehiculo"],
        "ley": "Ley de Tránsito Terrestre",
        "articulos": [12, 13, 14, 24, 25, 26, 27, 50, 51, 52, 95, 96, 97, 98]
    },
    "laboral": {
        "keywords": ["trabajo", "trabajador", "trabajadora", "empleo", "empleado",
                     "empleada", "jefe", "patrono", "patrona",
                     "despido", "despidieron", "despedir", "despedido", "despedida",
                     "botar", "botaron", "botado", "echar", "echaron",
                     "sueldo", "salario", "vacaciones",
                     "prestaciones", "liquidación", "liquidacion", "bono", "utilidades",
                     "maternidad", "inamovilidad", "reenganche", "nómina", "nomina",
                     "contrato laboral", "jornada", "horas extras", "sindicato",
                     "cesta ticket", "cestaticket", "pagar", "pagarme",
                     "sin pagar", "no me pagan", "no me pagaron"],
        "ley": "Ley Orgánica del Trabajo (LOTTT)",
        "articulos": [85, 86, 87, 88, 89, 90, 141, 142, 143, 190, 191, 192]
    },
    "derechos": {
        "keywords": ["detener", "detienen", "detenido", "detenida", "detención",
                     "detencion", "arrestar", "arrestado", "arrestaron", "preso",
                     "presa", "policía", "policia", "abuso", "golpear", "golpearon",
                     "maltratar", "maltrataron",
                     "teléfono", "telefono", "comunicaciones", "privacidad",
                     "allanar", "allanamiento", "allanaron", "registro", "requisar",
                     "requisaron", "tortura",
                     "comisaría", "comisaria", "funcionario", "derechos humanos",
                     "whatsapp", "chats", "mensajes", "revisar celular",
                     "calabozo", "encerrar", "encerrado", "libertad"],
        "ley": "Constitución de la República Bolivariana de Venezuela",
        "articulos": [44, 45, 46, 47, 48, 49, 50, 55, 60, 139]
    },
    "vivienda_cc": {
        "keywords": ["casero", "arrendador", "inquilino", "arrendatario", "alquiler",
                     "arrendamiento", "desalojo", "echar de la casa", "sacar de la casa",
                     "canon", "casa alquilada", "contrato de arrendamiento",
                     "prorroga legal", "prórroga legal", "deposito de arrendamiento"],
        "ley": "Código Civil venezolano",
        "articulos": [1579, 1580, 1581, 1582, 1583, 1584, 1585, 1600, 1601, 1615]
    },
    "vivienda_desalojo": {
        "keywords": ["casero", "arrendador", "inquilino", "arrendatario", "alquiler",
                     "arrendamiento", "desalojo", "echar de la casa", "sacar de la casa",
                     "canon", "casa alquilada", "quieren sacar", "me quieren desalojar",
                     "me quieren echar", "lanzamiento", "notificación de desalojo"],
        "ley": "Ley contra el Desalojo Arbitrario de Viviendas",
        "articulos": [1, 2, 4, 5, 6, 7, 10, 11, 12, 13, 15]
    },
    "vivienda_arrendamiento": {
        "keywords": ["casero", "arrendador", "inquilino", "arrendatario", "alquiler",
                     "arrendamiento", "desalojo", "canon", "casa alquilada",
                     "aumento de alquiler", "contrato de arrendamiento", "sunavi",
                     "prorroga", "prórroga", "causales de desalojo"],
        "ley": "Ley para la Regularización y Control de los Arrendamientos de Vivienda",
        "articulos": [1, 2, 3, 4, 6, 11, 40, 50, 88, 91, 93]
    },
    "arrendamiento_comercial": {
        "keywords": ["local comercial", "local alquilado", "arrendamiento comercial",
                     "oficina alquilada", "galpón", "galpon", "alquiler de local",
                     "arrendatario comercial", "canon comercial", "sundde",
                     "inquilino comercial", "contrato comercial"],
        "ley": "Ley de Regulación del Arrendamiento Inmobiliario para el Uso Comercial",
        "articulos": [1, 2, 3, 6, 7, 8, 15, 21, 31, 32, 40]
    },
    "propiedad_horizontal": {
        "keywords": ["condominio", "cuota de condominio", "administración del edificio",
                     "junta de condominio", "propietario del apartamento",
                     "gastos comunes", "edificio", "piso", "área común",
                     "reglamento de condominio", "propietario piso"],
        "ley": "Ley de Propiedad Horizontal",
        "articulos": [1, 3, 5, 6, 7, 8, 9, 11, 12, 13, 14, 18]
    },
    "civil": {
        "keywords": ["préstamo", "prestamo", "deber", "pagar", "deuda", "cobrar",
                     "dinero", "debe", "obligación", "obligacion", "contrato",
                     "incumplimiento", "daños", "perjuicios"],
        "ley": "Código Civil venezolano",
        "articulos": [1133, 1134, 1159, 1160, 1264, 1354, 1474, 1745, 1746, 1747]
    },
    "propiedad": {
        "keywords": ["propiedad", "dueño", "dueno", "propietario", "comprar",
                     "vender", "escritura", "hipoteca", "herencia", "testamento",
                     "sucesión", "sucesion", "heredar", "bienes"],
        "ley": "Código Civil venezolano",
        "articulos": [545, 546, 547, 548, 549, 796, 807, 808, 809, 810]
    },
    "familia": {
        "keywords": ["hijo", "hija", "niño", "niña", "menor", "adolescente",
                     "custodia", "guarda", "manutención", "pension alimentaria",
                     "alimentos", "divorcio", "separación", "separacion",
                     "matrimonio", "patria potestad", "adopción", "adopcion"],
        "ley": "Ley Orgánica para la Protección de Niños, Niñas y Adolescentes (LOPNA)",
        "articulos": [5, 7, 8, 26, 27, 30, 32, 76, 85, 86, 358, 359, 360]
    },
    "maternidad_paternidad": {
        "keywords": ["embarazada", "embarazo", "maternidad", "paternidad", "prenatal",
                     "postnatal", "lactancia", "permiso de maternidad",
                     "permiso de paternidad", "permiso paternal", "reposo maternal",
                     "inamovilidad por maternidad", "fuero materno", "fuero maternal",
                     "despedir embarazada", "despedida embarazada", "madre trabajadora",
                     "recién nacido", "recien nacido", "bono de parto"],
        "ley": "Ley para la Protección de las Familias, la Maternidad y la Paternidad",
        "articulos": [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14]
    },
    "trabajadores_residenciales": {
        "keywords": ["portero", "portera", "conserje", "conserjes", "conserjería",
                     "conserjeria", "vigilante residencial", "trabajador residencial",
                     "trabajadora residencial", "sereno", "guardia de edificio",
                     "vivir en el edificio", "apartamento de servicio"],
        "ley": "Ley Especial para la Dignificación de Trabajadores Residenciales",
        "articulos": [1, 2, 4, 5, 6, 7, 9, 10, 11, 12]
    },
    "violencia_mujer": {
        "keywords": ["violencia", "maltrato", "golpiza", "agresión", "agresion",
                     "violencia doméstica", "violencia domestica", "esposo me golpea",
                     "pareja me maltrata", "femicidio", "acoso", "abuso sexual",
                     "violencia de género", "violencia de genero", "mujer maltratada"],
        "ley": "Ley Orgánica sobre el Derecho de las Mujeres a una Vida Libre de Violencia",
        "articulos": [1, 2, 3, 14, 15, 39, 40, 41, 42, 43]
    },
    "corrupcion": {
        "keywords": ["corrupción", "corrupcion", "soborno", "coima", "extorsión",
                     "extorsion", "matraca", "matraqueo", "mordida",
                     "malversación", "malversacion", "peculado", "cohecho",
                     "pide dinero", "pidio dinero", "cobro ilegal", "cobrar coima",
                     "piden plata", "te cobran", "me cobra", "me cobró", "cobro",
                     "permiso de construcción", "permiso de construccion",
                     "alcaldía pide", "alcaldia pide", "funcionario pide dinero",
                     "me pidió dinero", "me pide dinero", "para darme el permiso"],
        "ley": "Ley contra la Corrupción",
        "articulos": [1, 2, 3, 4, 52, 53, 54, 55, 56, 57, 58]
    },
    "comercial": {
        "keywords": ["empresa", "empresas", "registrar empresa", "registro mercantil",
                     "sociedad anónima", "sociedad anonima", "compañía", "compania",
                     "s.a.", "s.r.l.", "srl", "c.a.", "firma mercantil",
                     "socios", "accionistas", "capital social", "razón social",
                     "razon social", "constituir empresa", "abrir empresa",
                     "rif empresa", "nit comercial", "actividad comercial",
                     "comerciante", "comercio", "negocio", "registro de comercio"],
        "ley": "Código de Comercio",
        "articulos": [200, 201, 202, 203, 204, 205, 210, 212, 214, 215, 219, 220]
    },
    "discapacidad": {
        "keywords": ["discapacidad", "discapacitado", "persona con discapacidad",
                     "minusvalía", "minusvalia", "accesibilidad", "inclusión",
                     "inclusion", "silla de ruedas"],
        "ley": "Ley para la Inclusión de Personas con Discapacidad",
        "articulos": [1, 2, 3, 5, 10, 11, 12, 35, 36]
    },
    "animales": {
        "keywords": ["perro", "gato", "mascota", "animal doméstico", "animal domestico",
                     "maltrato animal", "fauna doméstica", "fauna domestica",
                     "abandono animal"],
        "ley": "Ley de Protección de la Fauna Doméstica",
        "articulos": [1, 2, 3, 4, 5, 10, 11, 12, 15, 16]
    },
    "ambiente": {
        "keywords": ["contaminación", "contaminacion", "ruido excesivo", "ruido del vecino",
                     "basura", "desechos", "vertidos", "polución", "polucion",
                     "daño ambiental", "dano ambiental", "ambiente", "ecología",
                     "ecologia", "tala", "quema", "aguas residuales", "humo"],
        "ley": "Ley Orgánica del Ambiente",
        "articulos": [1, 2, 3, 4, 5, 6, 9, 10, 80, 81, 82]
    },
    "municipal": {
        "keywords": ["alcaldía", "alcaldia", "alcalde", "municipio", "ordenanza",
                     "catastro", "servicio municipal", "impuesto municipal",
                     "tasa municipal", "cabildo", "concejo municipal",
                     "funcionario municipal", "permiso municipal", "bomberos",
                     "recolección de basura", "recoleccion de basura"],
        "ley": "Ley Orgánica del Poder Público Municipal",
        "articulos": [1, 2, 3, 4, 5, 54, 55, 56, 88, 89, 260, 261]
    },
    "penal": {
        "keywords": ["robo", "robar", "robaron", "hurto", "asesinato", "homicidio", "matar",
                     "cárcel", "carcel", "prisión", "prision", "delito", "denuncia",
                     "estafa", "fraude", "secuestro", "violación", "violacion", "pena",
                     "ladrón", "ladron", "agresión física", "agresion fisica",
                     "amenaza", "amenazaron", "lesiones", "apuñalar", "apunalar",
                     "disparar", "dispararon", "arma", "navaja", "cuchillo"],
        "ley": "Código Penal",
        "articulos": [405, 406, 407, 413, 414, 415, 451, 453, 455, 457, 458, 460, 462, 464]
    },
    "justicia_paz": {
        "keywords": ["vecino", "vecinos", "vecina", "ruido", "bulla", "música alta",
                     "musica alta", "ladra", "ladrar", "ladrido", "perro ladra",
                     "perro del vecino", "basura del vecino", "cerca", "lindero",
                     "medianera", "conflicto vecinal", "pelea con vecino",
                     "juez de paz", "justicia de paz", "conciliación", "conciliacion",
                     "mediación vecinal", "mediacion vecinal", "gimnasio clandestino",
                     "fiesta", "escándalo", "escandalo", "molestia", "perturbación",
                     "perturbacion"],
        "ley": "Ley de Justicia de Paz Comunal",
        "articulos": [1, 2, 3, 4, 5, 6, 8, 36, 37, 38, 39, 40]
    },
    "faltas_penales": {
        "keywords": ["vecino", "vecinos", "ruido", "bulla", "música alta",
                     "musica alta", "perturbación", "perturbacion", "escándalo",
                     "escandalo", "desorden", "alboroto", "molestia",
                     "gimnasio clandestino", "fiesta ruidosa", "gritos"],
        "ley": "Código Penal",
        "articulos": [501, 502, 503, 504, 505, 506, 507, 508]
    },
    "adultos_mayores": {
        "keywords": ["abuelo", "abuela", "anciano", "anciana", "adulto mayor",
                     "adulta mayor", "tercera edad", "persona mayor", "jubilado",
                     "jubilada", "pensionado", "pensionada", "pensión", "pension",
                     "geriátrico", "geriatrico", "maltrato al abuelo", "abandono anciano",
                     "hogar de ancianos", "asilo"],
        "ley": "Ley de Atención Integral de las Personas Adultas Mayores",
        "articulos": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    },
    "antecedentes_penales": {
        "keywords": ["antecedentes penales", "antecedentes", "certificado de buena conducta",
                     "record policial", "récord policial", "registro penal",
                     "carta de buena conducta", "hoja de antecedentes",
                     "no tener antecedentes", "limpiar antecedentes",
                     "eliminar antecedentes", "cancelar antecedentes"],
        "ley": "Ley de Registro de Antecedentes Penales",
        "articulos": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    },
    "zonas_economicas": {
        "keywords": ["zona económica especial", "zona economica especial",
                     "zona franca", "zona libre", "incentivo fiscal",
                     "exención tributaria zona", "exencion tributaria zona",
                     "inversión extranjera", "inversion extranjera"],
        "ley": "Ley Orgánica de las Zonas Económicas Especiales",
        "articulos": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    },
    "tributario": {
        "keywords": ["impuesto", "impuestos", "tributo", "tributos", "seniat",
                     "iva", "islr", "renta", "declaración de renta", "declaracion de renta",
                     "retención", "retencion", "contribuyente", "fiscal", "fiscalización",
                     "fiscalizacion", "evasión", "evasion", "multa fiscal",
                     "obligación tributaria", "obligacion tributaria", "exención",
                     "exencion", "exoneración", "exoneracion", "factura", "facturación",
                     "facturacion", "ilícito tributario", "ilicito tributario",
                     "pago de impuestos", "deuda fiscal"],
        "ley": "Código Orgánico Tributario",
        "articulos": [1, 2, 3, 13, 14, 22, 23, 25, 36, 55, 91, 99, 109, 115, 116, 117]
    },
    "procesal_penal": {
        "keywords": ["fiscalía", "fiscalia", "fiscal", "ministerio público",
                     "ministerio publico", "imputado", "acusado", "audiencia",
                     "preliminar", "juicio oral", "tribunal penal", "flagrancia",
                     "orden de aprehensión", "orden de aprehension", "medida cautelar",
                     "medida privativa", "privativa de libertad", "boleta de excarcelación",
                     "boleta de excarcelacion", "sobreseimiento", "archivo fiscal",
                     "acusación", "acusacion", "investigación penal", "investigacion penal",
                     "defensor público", "defensor publico", "víctima", "victima",
                     "querella", "presentación", "presentacion", "48 horas",
                     "procedimiento abreviado", "flagrante"],
        "ley": "Código Orgánico Procesal Penal (COPP)",
        "articulos": [1, 8, 9, 10, 12, 44, 49, 111, 112, 113, 120, 127, 132, 133, 236, 237, 242, 243, 250, 262, 263, 280, 300, 308, 309, 356, 373, 374]
    },
    "consumidor": {
        "keywords": ["consumidor", "compré", "compre", "producto defectuoso",
                     "garantía", "garantia", "devolución", "devolucion", "devolver",
                     "reclamo", "reclamar", "indepabis", "sundde", "precios",
                     "especulación", "especulacion", "precio justo", "cobrar de más",
                     "cobrar de mas", "estafa comercial", "publicidad engañosa",
                     "publicidad enganosa", "tienda", "vendedor", "proveedor",
                     "servicio deficiente", "no me quieren devolver"],
        "ley": "Ley para la Defensa de las Personas en el Acceso a Bienes y Servicios (INDEPABIS)",
        "articulos": [1, 2, 3, 4, 5, 7, 8, 16, 17, 18, 31, 32, 35, 44, 65, 66, 73, 74, 75, 76, 77]
    },
    "bancario": {
        "keywords": ["banco", "bancos", "cuenta bancaria", "tarjeta", "crédito",
                     "credito", "débito", "debito", "préstamo bancario",
                     "prestamo bancario", "intereses", "comisión bancaria",
                     "comision bancaria", "sudeban", "superintendencia de bancos",
                     "cajero", "transferencia", "bloqueo de cuenta",
                     "fraude bancario", "clonación", "clonacion", "punto de venta"],
        "ley": "Ley de Instituciones del Sector Bancario",
        "articulos": [1, 2, 3, 5, 6, 44, 45, 46, 62, 63, 64, 65, 76, 77, 78, 79, 172, 173]
    },
    "seguro_social": {
        "keywords": ["seguro social", "ivss", "pensión ivss", "pension ivss",
                     "cotizaciones", "jubilación", "jubilacion", "pensionado",
                     "incapacidad", "reposo", "maternidad ivss", "paro forzoso",
                     "seguro de paro", "cuenta individual", "semanas cotizadas"],
        "ley": "Ley del Seguro Social",
        "articulos": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    },
    "islr": {
        "keywords": ["islr", "impuesto sobre la renta", "declaración de renta",
                     "declaracion de renta", "renta", "ganancias", "enriquecimiento",
                     "desgravámenes", "desgravamenes", "rebaja de impuesto",
                     "exención islr", "exencion islr", "retención islr",
                     "retencion islr", "persona natural", "persona jurídica",
                     "persona juridica", "unidad tributaria"],
        "ley": "Ley de Impuesto Sobre la Renta (ISLR)",
        "articulos": [1, 2, 3, 4, 5, 14, 27, 31, 55, 56, 57, 59, 60, 79, 80, 81, 86, 87, 88]
    },
    "delitos_informaticos": {
        "keywords": ["hacker", "hackeo", "hackearon", "hackear", "virus",
                     "malware", "ciberdelito", "informático", "informatico",
                     "cuenta hackeada", "robaron mi cuenta", "phishing",
                     "suplantación de identidad", "suplantacion de identidad",
                     "pornografía infantil", "pornografia infantil", "ciberacoso",
                     "grooming", "espionaje", "datos personales", "privacidad digital",
                     "acceso indebido", "sabotaje informático", "sabotaje informatico",
                     "clonaron mi tarjeta", "estafa por internet", "estafa online"],
        "ley": "Ley Especial contra los Delitos Informáticos",
        "articulos": [1, 2, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
    },
    "tramites": {
        "keywords": ["trámite", "tramite", "trámites", "tramites", "burocracia",
                     "papelería", "papeleria", "requisitos", "ventanilla",
                     "simplificación", "simplificacion", "papeleo",
                     "documento apostillado", "apostilla", "legalización",
                     "legalizacion", "certificación", "certificacion",
                     "funcionario no me atiende", "no me quieren atender"],
        "ley": "Ley Orgánica de Simplificación de Trámites Administrativos",
        "articulos": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 35, 36, 37, 38]
    },
}


# ─── ALIAS DE LEYES ──────────────────────────────────────────────────────────

ALIAS_LEYES = {
    # Constitución
    "constitucion": "Constitución de la República Bolivariana de Venezuela",
    "constitucion de venezuela": "Constitución de la República Bolivariana de Venezuela",
    "crbv": "Constitución de la República Bolivariana de Venezuela",
    # Código Civil
    "codigo civil": "Código Civil venezolano",
    "cc": "Código Civil venezolano",
    # Código Penal
    "codigo penal": "Código Penal",
    "cp": "Código Penal",
    # Código de Procedimiento Civil
    "codigo de procedimiento civil": "Código de Procedimiento Civil",
    "cpc": "Código de Procedimiento Civil",
    # LOTTT
    "lottt": "Ley Orgánica del Trabajo (LOTTT)",
    "ley del trabajo": "Ley Orgánica del Trabajo (LOTTT)",
    "ley organica del trabajo": "Ley Orgánica del Trabajo (LOTTT)",
    # Código de Comercio
    "codigo de comercio": "Código de Comercio",
    # Tránsito
    "ley de transito": "Ley de Tránsito Terrestre",
    "ley de transito terrestre": "Ley de Tránsito Terrestre",
    "transito": "Ley de Tránsito Terrestre",
    # LOPNA
    "lopna": "Ley Orgánica para la Protección de Niños, Niñas y Adolescentes (LOPNA)",
    "ley de ninos": "Ley Orgánica para la Protección de Niños, Niñas y Adolescentes (LOPNA)",
    # Violencia
    "ley de violencia": "Ley Orgánica sobre el Derecho de las Mujeres a una Vida Libre de Violencia",
    "ley de la mujer": "Ley Orgánica sobre el Derecho de las Mujeres a una Vida Libre de Violencia",
    # Tributario
    "codigo organico tributario": "Código Orgánico Tributario",
    "cot": "Código Orgánico Tributario",
    # Arrendamiento
    "ley de arrendamiento": "Ley para la Regularización y Control de los Arrendamientos de Vivienda",
    "ley de arrendamientos": "Ley para la Regularización y Control de los Arrendamientos de Vivienda",
    "arrendamiento": "Ley para la Regularización y Control de los Arrendamientos de Vivienda",
    # Desalojo
    "ley contra el desalojo": "Ley contra el Desalojo Arbitrario de Viviendas",
    "desalojo": "Ley contra el Desalojo Arbitrario de Viviendas",
    # Corrupción
    "ley contra la corrupcion": "Ley contra la Corrupción",
    "corrupcion": "Ley contra la Corrupción",
    # Propiedad Horizontal
    "ley de propiedad horizontal": "Ley de Propiedad Horizontal",
    "propiedad horizontal": "Ley de Propiedad Horizontal",
    # Ambiente
    "ley del ambiente": "Ley Orgánica del Ambiente",
    "ley organica del ambiente": "Ley Orgánica del Ambiente",
    # Justicia Militar
    "codigo de justicia militar": "Código Orgánico de Justicia Militar",
    # Registros
    "ley de registros y notarias": "Ley de Registros y Notarías",
    # Familia
    "ley de familias": "Ley para la Protección de las Familias, la Maternidad y la Paternidad",
    "maternidad": "Ley para la Protección de las Familias, la Maternidad y la Paternidad",
    # Arrendamiento Comercial
    "arrendamiento comercial": "Ley de Regulación del Arrendamiento Inmobiliario para el Uso Comercial",
    "ley de arrendamiento comercial": "Ley de Regulación del Arrendamiento Inmobiliario para el Uso Comercial",
    # Trabajadores Residenciales
    "trabajadores residenciales": "Ley Especial para la Dignificación de Trabajadores Residenciales",
    # Discapacidad
    "discapacidad": "Ley para la Inclusión de Personas con Discapacidad",
    # Fauna
    "fauna domestica": "Ley de Protección de la Fauna Doméstica",
    "ley de fauna": "Ley de Protección de la Fauna Doméstica",
    # Municipal
    "ley municipal": "Ley Orgánica del Poder Público Municipal",
    "poder publico municipal": "Ley Orgánica del Poder Público Municipal",
    # Justicia de Paz
    "justicia de paz": "Ley de Justicia de Paz Comunal",
    # Adultos Mayores
    "adultos mayores": "Ley de Atención Integral de las Personas Adultas Mayores",
    # Antecedentes
    "antecedentes penales": "Ley de Registro de Antecedentes Penales",
    # Zonas Económicas
    "zonas economicas": "Ley Orgánica de las Zonas Económicas Especiales",
    # Comunas
    "ley de comunas": "Ley Orgánica de las Comunas",
    "consejos comunales": "Ley Orgánica de los Consejos Comunales",
    # Contraloría
    "contraloria": "Ley Orgánica de la Contraloría General de la República",
    # Residuos
    "ley de residuos": "Ley de Residuos y Desechos Sólidos",
    # Odio
    "ley contra el odio": "Ley Constitucional contra el Odio",
    # COPP
    "copp": "Código Orgánico Procesal Penal (COPP)",
    "codigo organico procesal penal": "Código Orgánico Procesal Penal (COPP)",
    "procesal penal": "Código Orgánico Procesal Penal (COPP)",
    # Consumidor / INDEPABIS
    "indepabis": "Ley para la Defensa de las Personas en el Acceso a Bienes y Servicios (INDEPABIS)",
    "ley del consumidor": "Ley para la Defensa de las Personas en el Acceso a Bienes y Servicios (INDEPABIS)",
    "consumidor": "Ley para la Defensa de las Personas en el Acceso a Bienes y Servicios (INDEPABIS)",
    "proteccion al consumidor": "Ley para la Defensa de las Personas en el Acceso a Bienes y Servicios (INDEPABIS)",
    # Sector Bancario
    "ley de bancos": "Ley de Instituciones del Sector Bancario",
    "sector bancario": "Ley de Instituciones del Sector Bancario",
    "ley bancaria": "Ley de Instituciones del Sector Bancario",
    # Seguro Social
    "seguro social": "Ley del Seguro Social",
    "ley del seguro social": "Ley del Seguro Social",
    "ivss": "Ley del Seguro Social",
    # ISLR
    "islr": "Ley de Impuesto Sobre la Renta (ISLR)",
    "impuesto sobre la renta": "Ley de Impuesto Sobre la Renta (ISLR)",
    "ley de islr": "Ley de Impuesto Sobre la Renta (ISLR)",
    "renta": "Ley de Impuesto Sobre la Renta (ISLR)",
    # Delitos Informáticos
    "delitos informaticos": "Ley Especial contra los Delitos Informáticos",
    "ley de delitos informaticos": "Ley Especial contra los Delitos Informáticos",
    "ciberdelitos": "Ley Especial contra los Delitos Informáticos",
    # Simplificación de Trámites
    "simplificacion de tramites": "Ley Orgánica de Simplificación de Trámites Administrativos",
    "ley de tramites": "Ley Orgánica de Simplificación de Trámites Administrativos",
    "tramites": "Ley Orgánica de Simplificación de Trámites Administrativos",
    # Procesos Electorales
    "procesos electorales": "Ley Orgánica de Procesos Electorales",
    "ley electoral": "Ley Orgánica de Procesos Electorales",
    "elecciones": "Ley Orgánica de Procesos Electorales",
    "voto": "Ley Orgánica de Procesos Electorales",
}

# Catálogo agrupado para /leyes (nombre_mostrar → [alias])
CATALOGO_LEYES = {
    "Codigos y Bases": [
        ("Constitución", "CRBV, constitucion"),
        ("Código Civil", "CC, codigo civil"),
        ("Código de Procedimiento Civil", "CPC"),
        ("Código Penal", "CP, codigo penal"),
        ("Código Orgánico Procesal Penal", "COPP, procesal penal"),
        ("Código de Comercio", "codigo de comercio"),
        ("Código Orgánico Tributario", "COT"),
        ("LOTTT (Trabajo)", "LOTTT, ley del trabajo"),
        ("Ley de Tránsito Terrestre", "transito"),
    ],
    "Vivienda": [
        ("Desalojo Arbitrario", "desalojo"),
        ("Arrendamiento de Vivienda", "arrendamiento"),
        ("Arrendamiento Comercial", "arrendamiento comercial"),
        ("Propiedad Horizontal", "propiedad horizontal"),
    ],
    "Familia y Proteccion": [
        ("LOPNA (Niños y Adolescentes)", "LOPNA"),
        ("Maternidad y Paternidad", "maternidad"),
        ("Violencia contra la Mujer", "ley de violencia"),
        ("Adultos Mayores", "adultos mayores"),
        ("Discapacidad", "discapacidad"),
        ("Trabajadores Residenciales", "trabajadores residenciales"),
    ],
    "Economia y Finanzas": [
        ("Impuesto Sobre la Renta (ISLR)", "ISLR, renta"),
        ("Seguro Social (IVSS)", "IVSS, seguro social"),
        ("Sector Bancario", "ley de bancos, sector bancario"),
        ("Consumidor (INDEPABIS)", "INDEPABIS, consumidor"),
    ],
    "Estado y Justicia": [
        ("Ley contra la Corrupcion", "corrupcion"),
        ("Poder Publico Municipal", "ley municipal"),
        ("Justicia de Paz Comunal", "justicia de paz"),
        ("Procesos Electorales", "ley electoral, elecciones"),
        ("Simplificacion de Tramites", "tramites"),
        ("Antecedentes Penales", "antecedentes penales"),
        ("Zonas Economicas Especiales", "zonas economicas"),
        ("Ley del Ambiente", "ley del ambiente"),
        ("Fauna Domestica", "fauna domestica"),
        ("Registros y Notarias", "ley de registros y notarias"),
        ("Ley contra el Odio", "ley contra el odio"),
        ("Contraloria General", "contraloria"),
        ("Ley de Residuos", "ley de residuos"),
        ("Ley de Comunas", "ley de comunas"),
        ("Consejos Comunales", "consejos comunales"),
        ("Justicia Militar", "codigo de justicia militar"),
    ],
    "Tecnologia": [
        ("Delitos Informaticos", "delitos informaticos, ciberdelitos"),
    ],
}


# ─── PROMPTS ─────────────────────────────────────────────────────────────────

PROMPT_REFORMULAR = """Eres un experto en derecho venezolano. Transforma la pregunta en términos jurídicos formales venezolanos para búsqueda en base de datos legal.

Identifica: área del derecho, figuras jurídicas, leyes aplicables.
Si la pregunta menciona ley o artículo específico, inclúyelo exactamente.
Si es muy corta, expándela con contexto jurídico.
Responde con 5-10 términos jurídicos clave, sin explicaciones."""

SYSTEM_PROMPT = """Eres aBOTgado, asistente jurídico virtual especializado en leyes venezolanas para Telegram. Tono profesional, accesible y en español venezolano.

REGLA PRINCIPAL — PROHIBICIÓN ABSOLUTA DE INVENTAR:
- Los artículos disponibles están numerados [1], [2], [3], etc. en la lista que recibirás.
- SOLO puedes citar artículos de ESA lista. NUNCA uses tu conocimiento interno para citar leyes o artículos que NO estén en la lista.

REGLA DE RELEVANCIA — MÁS IMPORTANTE QUE CITAR:
- Antes de citar un artículo, pregúntate: "¿Este artículo REALMENTE resuelve o aplica al problema ESPECÍFICO del usuario?"
- Si un artículo habla de policía pero el usuario pregunta por ruido → NO LO CITES
- Si un artículo habla de niños pero el usuario pregunta por vecinos → NO LO CITES
- Si un artículo es genérico sobre "derechos" pero no aplica al caso concreto → NO LO CITES
- Es MUCHO MEJOR no citar NINGÚN artículo que citar artículos irrelevantes
- Máximo 2-3 artículos citados. Solo los MÁS relevantes.

SI NINGÚN ARTÍCULO ES RELEVANTE, usa esta respuesta (es perfectamente válida):

📌 <b>Respuesta:</b> [Responde con tu conocimiento general sobre el tema, SIN inventar artículos]

💡 <b>Qué hacer:</b> [Pasos concretos con instituciones]

⚠️ <i>No tengo artículos específicos sobre este tema en mi base. Consulta con un abogado para orientación precisa.</i>

- NUNCA inventes números de artículos. NUNCA cites leyes que no estén en la lista.
- Cuando cites, usa el nombre y número EXACTOS como aparecen en la lista.

ESTRUCTURA OBLIGATORIA (sé CONCISO). Usa formato HTML para Telegram:

📌 <b>Respuesta:</b> [1-2 oraciones DIRECTAS. Sin "es importante recordar" ni introducciones.]

📖 <b>Qué dice la ley:</b>
- <b>Ley, Art. N:</b> "[cita breve — máx 2 líneas]"
- <b>Ley, Art. N:</b> "[cita breve — máx 2 líneas]"
(SOLO artículos de la lista que sean RELEVANTES al problema. Si solo 1 aplica, cita solo 1. Si ninguno aplica, OMITE esta sección.)

💡 <b>Qué hacer:</b>
1. [PASO CONCRETO con institución, teléfono o web si los tienes]
2. [Segundo paso concreto]
3. [Tercer paso si aplica]
(USA LA GUÍA INSTITUCIONAL que te daré al final del contexto. Incluye nombres de instituciones, teléfonos, plazos, y documentos necesarios.)

⚠️ <i>Info orientativa. Consulta un abogado.</i>

REGLAS DE FORMATO Y REDACCIÓN:
- Usa <b>negritas HTML</b> en nombre de ley y artículo en cada cita.
- Usa <i>itálica HTML</i> solo para el disclaimer final.
- NO uses asteriscos (*) para formato. SOLO usa etiquetas HTML: <b> para negritas, <i> para itálica.
- Sé breve y directo. PROHIBIDO: "es importante", "debes considerar", "debes solicitar asesoramiento legal".
- NO repitas el mismo artículo dos veces.
- Si mencionas un artículo, DEBES decir qué dice.
- En "Qué hacer": USA LA INFORMACIÓN DE LA GUÍA INSTITUCIONAL. Incluye instituciones REALES, teléfonos, plazos legales, documentos que debe llevar. NUNCA digas solo "busca un abogado" o "acude a la autoridad competente". Sé ESPECÍFICO: nombre de la institución, qué llevar, qué pedir, y si hay teléfono o web, inclúyelos."""

PROMPT_EXPLICAR_ARTICULO = """Eres aBOTgado, asistente jurídico venezolano. El usuario quiere entender un artículo de ley.

Explica el artículo de forma BREVE y CLARA en español sencillo venezolano. Formato HTML para Telegram:

📖 <b>Qué dice:</b> [1-2 oraciones explicando el artículo en palabras simples]

💡 <b>En la práctica:</b> [1-2 oraciones con un ejemplo real de cómo se aplica]

NO inventes contenido. Basa tu explicación SOLO en el texto del artículo que te doy.
Sé breve. Máximo 5 líneas total."""


# ─── GUÍAS INSTITUCIONALES POR TEMA ─────────────────────────────────────────

GUIAS_INSTITUCIONALES = {
    "laboral": """
INSTITUCIONES Y PASOS CONCRETOS PARA TEMAS LABORALES:
- Inspectoría del Trabajo: Presenta denuncia por despido injustificado, cobro de prestaciones, o reenganche. Lleva cédula, contrato (si tienes), y recibos de pago.
- Si te despidieron: Tienes 10 días hábiles para solicitar reenganche ante la Inspectoría del Trabajo de tu jurisdicción.
- Prestaciones: El patrono tiene 5 días después del despido para pagar. Si no paga, denuncia en la Inspectoría.
- Línea gratuita MPPPST: 0800-TRABAJO (0800-872-2256)
- Si es acoso laboral: Denuncia ante la Inspectoría y ante la Fiscalía del Ministerio Público.
""",
    "derechos": """
INSTITUCIONES Y PASOS CONCRETOS PARA VIOLACIÓN DE DERECHOS:
- Fiscalía del Ministerio Público: Presenta denuncia formal. Lleva cédula y cualquier evidencia (fotos, videos, testigos).
- Defensoría del Pueblo: Si un funcionario violó tus derechos. Línea: 0800-DEFENSORIA (0800-333-3676).
- Si te detuvieron ilegalmente: Tienes derecho a comunicarte con un abogado y a ser presentado ante un juez en menos de 48 horas.
- CICPC: Si necesitas denunciar un delito. Línea: 0800-CICPC-00 (0800-24272-00).
- Tribunal de Control: Si necesitas un amparo constitucional por violación de derechos fundamentales.
""",
    "penal": """
INSTITUCIONES Y PASOS CONCRETOS PARA DELITOS:
- CICPC (Cuerpo de Investigaciones): Denuncia robos, hurtos, estafas, lesiones. Línea: 0800-CICPC-00 (0800-24272-00). Lleva cédula y evidencia.
- Fiscalía del Ministerio Público: Presenta denuncia formal para iniciar investigación penal.
- Policía Nacional (PNB): Para denuncias inmediatas. 171 (emergencias).
- Si te robaron un vehículo: Denuncia en CICPC + notifica a tu aseguradora en las primeras 24 horas + bloquea el vehículo en el INTT.
- Si sufriste estafa: Guarda capturas, recibos, conversaciones. Denuncia en CICPC con toda la evidencia.
""",
    "familia": """
INSTITUCIONES Y PASOS CONCRETOS PARA TEMAS DE FAMILIA:
- Tribunal de Protección de Niños, Niñas y Adolescentes: Para custodia, régimen de visitas, pensión alimentaria.
- Consejo de Protección del Niño (municipal): Para denunciar maltrato o abandono de menores. Hay uno en cada municipio.
- IDENNA (Instituto Nacional de Niños): Línea 0800-NIÑOS-00 (0800-6466-700).
- Pensión alimentaria: Se fija en el Tribunal de Protección. El monto es entre 20% y 30% del ingreso del obligado.
- Divorcio: Acude al Tribunal de Municipio (mutuo acuerdo) o Tribunal Civil (contencioso).
""",
    "violencia_mujer": """
INSTITUCIONES Y PASOS CONCRETOS PARA VIOLENCIA DE GÉNERO:
- 0800-MUJERES (0800-685-3737): Línea de atención gratuita 24 horas.
- Fiscalía con competencia en violencia de género: Denuncia directa, no necesitas abogado.
- Casas de Abrigo: Refugio temporal para mujeres en riesgo. Pregunta en la Fiscalía o el 0800-MUJERES.
- INAMUJER: Instituto Nacional de la Mujer, ofrece asesoría jurídica gratuita.
- Policía: Puede dictar medidas de protección inmediatas (orden de alejamiento).
- NO necesitas ir con tu agresor. Puedes ir sola a denunciar.
""",
    "vivienda_desalojo": """
INSTITUCIONES Y PASOS CONCRETOS PARA DESALOJO/ARRENDAMIENTO:
- SUNAVI (Superintendencia Nacional de Arrendamiento de Vivienda): Es OBLIGATORIO agotar la vía administrativa en SUNAVI antes de ir a tribunal. Teléfono: (0212) 408-5000.
- Si te quieren desalojar: Tu arrendador NO puede sacarte sin orden judicial. Si lo intenta, denuncia ante la Fiscalía.
- Procedimiento: El arrendador debe solicitar ante SUNAVI la autorización de desalojo. Tú serás citado para audiencia conciliatoria.
- Si tienes contrato vigente: No pueden desalojarte hasta que venza el contrato + la prórroga legal.
""",
    "vivienda_arrendamiento": """
INSTITUCIONES Y PASOS CONCRETOS PARA ARRENDAMIENTO:
- SUNAVI: Regula todo lo relacionado con arrendamiento de vivienda. Teléfono: (0212) 408-5000.
- Canon de arrendamiento: Debe fijarse según los criterios de SUNAVI. Si te cobran de más, denuncia.
- Prórroga legal: Al vencer el contrato, tienes derecho a prórroga (6 meses a 3 años según antigüedad).
- Depósito: No pueden exigirte más de 1 mes de garantía.
""",
    "vivienda_cc": """
INSTITUCIONES Y PASOS CONCRETOS PARA ARRENDAMIENTO:
- SUNAVI: Para cualquier conflicto de arrendamiento de vivienda. Teléfono: (0212) 408-5000.
- Tribunal de Municipio: Si el conflicto no se resuelve en SUNAVI, acude al tribunal civil competente.
- Si no te devuelven el depósito: Denuncia ante SUNAVI.
""",
    "comercial": """
INSTITUCIONES Y PASOS CONCRETOS PARA REGISTRO DE EMPRESA:
- Registro Mercantil: Acude al de tu jurisdicción. Necesitas: acta constitutiva, estatutos, cédulas de los socios, RIF de los socios, reserva de nombre de la empresa.
- SENIAT: Después de registrar, solicita el RIF de la empresa. Web: seniat.gob.ve
- Alcaldía: Solicita la Licencia de Actividades Económicas (patente de industria y comercio).
- Tipos comunes: C.A. (Compañía Anónima) para 2+ socios, S.R.L. para responsabilidad limitada, Firma Personal para 1 solo dueño.
- Costo aproximado: Registro ante el Registro Mercantil + honorarios del abogado que redacte el acta constitutiva.
""",
    "corrupcion": """
INSTITUCIONES Y PASOS CONCRETOS PARA CORRUPCIÓN:
- Fiscalía del Ministerio Público: Denuncia formal contra el funcionario. No necesitas abogado para denunciar.
- Contraloría General de la República: Si el funcionario maneja fondos públicos. Web: cgr.gob.ve
- Defensoría del Pueblo: Si el funcionario te niega un servicio público. Línea: 0800-DEFENSORIA.
- Guarda toda evidencia: grabaciones, mensajes, nombres, fechas, testigos.
- Denuncia anónima: Puedes denunciar sin identificarte ante la Fiscalía.
""",
    "transito": """
INSTITUCIONES Y PASOS CONCRETOS PARA TRÁNSITO:
- INTT (Instituto Nacional de Transporte Terrestre): Para licencias, registros vehiculares, infracciones. Web: intt.gob.ve
- Si te quitaron la licencia: Acude al INTT para solicitar el procedimiento de recuperación.
- Accidente de tránsito: Llama a la policía (171), no muevas los vehículos, toma fotos, intercambia datos del seguro.
- Multas: Puedes pagarlas en el INTT o en las oficinas autorizadas.
- Seguro RCV: Es obligatorio. Si no tienes, la multa es de 50% del salario mínimo.
""",
    "propiedad": """
INSTITUCIONES Y PASOS CONCRETOS PARA PROPIEDAD:
- Registro Subalterno (Registro Inmobiliario): Para compraventa, hipotecas, liberación de gravámenes.
- Si compraste un inmueble con hipoteca ajena: Acude a un abogado y solicita al Registro Subalterno un certificado de gravámenes para verificar la situación legal del inmueble.
- SUNDDE: Si hay problemas con precios de inmuebles regulados.
- Tribunal Civil: Para demandas por reivindicación, desalojo, o nulidad de venta.
""",
    "tributario": """
INSTITUCIONES Y PASOS CONCRETOS PARA TEMAS TRIBUTARIOS:
- SENIAT: Para declaración de ISLR, IVA, retenciones. Web: seniat.gob.ve. Portal fiscal: declaraciones.seniat.gob.ve
- Plazo ISLR personas naturales: Hasta el 31 de marzo de cada año.
- Si te multaron: Tienes 25 días hábiles para recurrir ante la Gerencia Regional del SENIAT.
- Recurso jerárquico: Ante el SENIAT. Si no funciona, recurso contencioso tributario ante el Tribunal Superior Tributario.
""",
    "animales": """
INSTITUCIONES Y PASOS CONCRETOS PARA MALTRATO ANIMAL:
- Fiscalía del Ministerio Público: Denuncia por maltrato animal.
- Policía Municipal: Pueden intervenir inmediatamente si hay maltrato visible.
- Si tu vecino maltrata a un animal: Toma fotos/videos como evidencia y denuncia ante la Fiscalía.
- Redes de rescate animal: Contacta organizaciones locales de tu ciudad para ayuda inmediata.
""",
    "justicia_paz": """
INSTITUCIONES Y PASOS CONCRETOS PARA CONFLICTOS VECINALES:
- Juez de Paz Comunal: Es gratuito y está en tu comunidad. Resuelve conflictos entre vecinos sin necesidad de tribunal.
- Consejo Comunal: Puede mediar en conflictos vecinales antes de llegar al Juez de Paz.
- Si el ruido es excesivo: Primero habla con tu vecino. Si no funciona, denuncia ante el Juez de Paz o la policía municipal.
- Ordenanzas municipales: Tu alcaldía tiene normas sobre ruido, mascotas, y convivencia. Consulta en la alcaldía.
""",
    "adultos_mayores": """
INSTITUCIONES Y PASOS CONCRETOS PARA ADULTOS MAYORES:
- INASS (Instituto Nacional de Servicios Sociales): Atención al adulto mayor.
- Defensoría del Pueblo: Si se violan derechos de un adulto mayor.
- Pensión IVSS: Si el adulto mayor no tiene pensión, puede solicitarla en el IVSS (Instituto Venezolano de los Seguros Sociales) o a través del Sistema Patria.
- Fiscalía: Para denunciar abandono o maltrato de adultos mayores.
""",
    "discapacidad": """
INSTITUCIONES Y PASOS CONCRETOS PARA DISCAPACIDAD:
- CONAPDIS (Consejo Nacional para las Personas con Discapacidad): Emite el certificado de discapacidad y asesora sobre derechos.
- Si te discriminan por discapacidad: Denuncia ante CONAPDIS y ante la Defensoría del Pueblo.
- Trabajo: Las empresas con más de 20 trabajadores DEBEN emplear al menos 5% de personas con discapacidad.
""",
    "maternidad_paternidad": """
INSTITUCIONES Y PASOS CONCRETOS PARA MATERNIDAD/PATERNIDAD:
- Inspectoría del Trabajo: Si te despidieron estando embarazada o en período de inamovilidad (hasta 2 años después del parto).
- IVSS: Para tramitar el reposo prenatal y postnatal.
- Inamovilidad: La madre tiene inamovilidad laboral desde el embarazo hasta 2 años después del parto. El padre tiene 2 años desde el nacimiento.
- Si te despidieron embarazada: Acude INMEDIATAMENTE a la Inspectoría del Trabajo. Tienes 30 días para solicitar reenganche.
""",
    "trabajadores_residenciales": """
INSTITUCIONES Y PASOS CONCRETOS PARA TRABAJADORES RESIDENCIALES:
- Inspectoría del Trabajo: Para reclamar derechos laborales del conserje/portero.
- SUNAVI: Si el conflicto involucra la vivienda asignada al trabajador residencial.
- El trabajador residencial tiene derecho a vivienda, y NO pueden desalojarlo sin procedimiento legal.
""",
    "propiedad_horizontal": """
INSTITUCIONES Y PASOS CONCRETOS PARA PROPIEDAD HORIZONTAL:
- Junta de Condominio: Es el primer paso para resolver conflictos dentro del edificio.
- Tribunal de Municipio: Si la Junta no resuelve, puedes demandar ante el tribunal civil.
- Si no pagan condominio: La Junta puede demandar al moroso ante el Tribunal de Municipio.
- Asamblea de propietarios: Las decisiones importantes requieren mayoría calificada (75% de los propietarios).
""",
    "arrendamiento_comercial": """
INSTITUCIONES Y PASOS CONCRETOS PARA ARRENDAMIENTO COMERCIAL:
- SUNDDE: Regula arrendamientos de locales comerciales.
- Tribunal de Municipio: Para demandas por desalojo de local comercial, cobro de cánones, etc.
- Prórroga legal comercial: Depende de la antigüedad (6 meses a 3 años).
- Si te quieren subir el canon: Debe hacerse según los parámetros del SUNDDE.
""",
    "procesal_penal": """
INSTITUCIONES Y PASOS CONCRETOS PARA PROCESO PENAL:
- Fiscalía del Ministerio Público: Inicia la investigación penal. Presenta denuncia con cédula y evidencia.
- Defensa Pública: Si no tienes abogado, tienes derecho a un defensor público GRATUITO.
- Tribunal de Control: Audiencia de presentación (dentro de 48 horas si hay detención). Decide medidas cautelares.
- Tribunal de Juicio: Fase de juicio oral y público.
- Si te detuvieron en flagrancia: Deben presentarte ante un juez en máximo 48 horas. Tienes derecho a llamar a un abogado o familiar.
- Medidas cautelares sustitutivas (Art. 242 COPP): Presentación periódica, prohibición de salida del país, etc. Son alternativas a la prisión.
""",
    "consumidor": """
INSTITUCIONES Y PASOS CONCRETOS PARA DEFENSA DEL CONSUMIDOR:
- SUNDDE (Superintendencia Nacional para la Defensa de los Derechos Socioeconómicos): Denuncia por precios abusivos, especulación, acaparamiento. Web: sundde.gob.ve. Línea: 0800-SUNDDE-0.
- INDEPABIS: Reclamos por productos defectuosos, garantías incumplidas, publicidad engañosa.
- Si compraste algo defectuoso: Tienes derecho a reparación, reposición o devolución del dinero.
- Guarda siempre: factura, ticket, fotos del producto, conversaciones con el vendedor.
""",
    "bancario": """
INSTITUCIONES Y PASOS CONCRETOS PARA PROBLEMAS BANCARIOS:
- SUDEBAN (Superintendencia de Bancos): Reclamos contra bancos. Web: sudeban.gob.ve. Si el banco no resuelve tu reclamo en 20 días, acude a SUDEBAN.
- Defensor del Cliente Bancario: Cada banco tiene uno, es tu primer recurso.
- Si clonaron tu tarjeta o hubo fraude: Reporta inmediatamente al banco, solicita bloqueo y apertura de reclamo por escrito. Denuncia en el CICPC.
- Comisiones ilegales: Los bancos NO pueden cobrar comisiones no autorizadas por SUDEBAN. Denuncia si lo hacen.
""",
    "seguro_social": """
INSTITUCIONES Y PASOS CONCRETOS PARA SEGURO SOCIAL:
- IVSS (Instituto Venezolano de los Seguros Sociales): Para pensiones, reposos, incapacidad. Web: ivss.gob.ve
- Pensión de vejez: Hombres 60 años con 750 cotizaciones, Mujeres 55 años con 750 cotizaciones.
- Reposo médico: Tu médico lo emite, debe ser validado por el IVSS.
- Paro forzoso: Si te despidieron, tienes derecho a 5 meses de prestación. Acude al IVSS con carta de despido.
- Sistema Patria: Para registrar pensiones y beneficios sociales.
""",
    "islr": """
INSTITUCIONES Y PASOS CONCRETOS PARA IMPUESTO SOBRE LA RENTA:
- SENIAT: Declaración y pago de ISLR. Web: seniat.gob.ve. Portal fiscal: declaraciones.seniat.gob.ve
- Plazo personas naturales: Hasta el 31 de marzo de cada año.
- Quiénes declaran: Personas naturales con ingresos superiores a 1.000 Unidades Tributarias anuales.
- Desgravámenes: Gastos de salud, educación, vivienda principal que reducen la base imponible.
- Si te multaron: Recurso jerárquico ante el SENIAT (25 días hábiles) o recurso contencioso ante el Tribunal Superior Tributario.
""",
    "delitos_informaticos": """
INSTITUCIONES Y PASOS CONCRETOS PARA DELITOS INFORMÁTICOS:
- CICPC - División contra Delitos Informáticos: Denuncia hackeos, estafas online, suplantación de identidad. Línea: 0800-CICPC-00.
- Fiscalía del Ministerio Público: Denuncia formal para iniciar investigación.
- Si hackearon tu cuenta: Cambia contraseñas inmediatamente, activa verificación en 2 pasos, guarda capturas de pantalla como evidencia.
- Si es estafa online: Guarda TODA la evidencia (capturas, conversaciones, comprobantes de pago, URLs).
- CONATEL: Si el delito involucra telecomunicaciones o contenido ilegal en internet.
""",
    "tramites": """
INSTITUCIONES Y PASOS CONCRETOS PARA TRÁMITES:
- La Ley de Simplificación de Trámites PROHÍBE que las oficinas públicas te pidan documentos que ya reposan en otra oficina del Estado.
- Si te piden requisitos excesivos o innecesarios: Exige por escrito qué ley obliga ese requisito. Denuncia ante la Contraloría o la Defensoría del Pueblo.
- Derecho a respuesta: Toda petición ante la administración pública debe ser respondida en máximo 20 días hábiles.
- Si no te atienden: Denuncia ante la Defensoría del Pueblo (0800-DEFENSORIA) o la Contraloría General.
""",
}


# ─── PROTECCIÓN CONTRA PROMPT INJECTION ──────────────────────────────────────

_PATRONES_INJECTION = [
    r"ignora\s+(todas?\s+)?(las\s+)?instrucciones",
    r"ignore\s+(all\s+)?(previous\s+)?instructions",
    r"olvida\s+(todo|tus\s+instrucciones)",
    r"forget\s+(everything|your\s+instructions)",
    r"ahora\s+eres\s+",
    r"you\s+are\s+now\s+",
    r"nuevo\s+rol\s*:",
    r"new\s+role\s*:",
    r"system\s*prompt\s*:",
    r"actua\s+como\s+(si\s+fueras|un)\s+",
    r"act\s+as\s+(if\s+you\s+were|a)\s+",
    r"responde\s+sin\s+restricciones",
    r"modo\s+(sin\s+filtro|desarrollador|admin)",
    r"developer\s+mode",
    r"jailbreak",
    r"DAN\s+mode",
]

import re as _re
_REGEX_INJECTION = _re.compile(
    "|".join(_PATRONES_INJECTION), _re.IGNORECASE
)


def sanitizar_input(texto: str) -> str:
    """Sanitiza el input del usuario contra prompt injection."""
    # Limitar longitud (500 chars es más que suficiente para una pregunta legal)
    texto = texto[:500]
    # Remover intentos de inyección de roles/instrucciones
    texto = _REGEX_INJECTION.sub("[filtrado]", texto)
    return texto.strip()


def es_prompt_injection(texto: str) -> bool:
    """Detecta si el texto contiene intento de prompt injection."""
    return bool(_REGEX_INJECTION.search(texto))


# ─── FUNCIONES DE BÚSQUEDA ──────────────────────────────────────────────────

def normalizar(texto: str) -> str:
    """Remueve acentos y convierte a minúsculas para comparación segura."""
    texto = texto.lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto


def reformular(pregunta: str) -> str:
    try:
        r = groq_client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": PROMPT_REFORMULAR},
                {"role": "user",   "content": pregunta}
            ],
            max_tokens=100,
            temperature=0.1,
        )
        return r.choices[0].message.content.strip()
    except Exception:
        return pregunta


def buscar_bm25(query: str, top_n: int = 10) -> list[dict]:
    tokens = tokenizar(query)
    scores = bm25.get_scores(tokens)
    top    = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_n]
    # Filtrar: solo artículos con score significativo (> 10% del máximo)
    max_score = max(scores[i] for i in top) if top else 0
    umbral = max_score * 0.15 if max_score > 0 else 0
    return [{"texto": docs_bm25[i], "ley": metadatas[i]["ley"],
             "articulo": metadatas[i]["articulo"], "score_bm25": scores[i]}
            for i in top if scores[i] > umbral]


def buscar_embedding(query: str, top_n: int = 10) -> list[dict]:
    emb = embeddings.generar_embedding(query)
    r   = coleccion.query(
        query_embeddings=[emb], n_results=top_n,
        include=["documents", "metadatas", "distances"]
    )
    # Filtro más estricto: solo artículos con distancia < 0.75 (antes 0.95)
    return [{"texto": r["documents"][0][i], "ley": r["metadatas"][0][i]["ley"],
             "articulo": r["metadatas"][0][i]["articulo"],
             "distancia": r["distances"][0][i]}
            for i in range(len(r["documents"][0])) if r["distances"][0][i] < 0.75]


def buscar_articulos_clave(pregunta: str) -> tuple[list[dict], list[str]]:
    """Retorna (artículos, temas_detectados)."""
    pregunta_norm = normalizar(pregunta)
    articulos      = []
    ids_vistos     = set()
    temas          = []
    for tema, cfg in ARTICULOS_CLAVE.items():
        if any(normalizar(k) in pregunta_norm for k in cfg["keywords"]):
            logger.info(f"  Tema detectado: {tema}")
            temas.append(tema)
            resultado = coleccion.get(
                where={"$and": [
                    {"ley":      {"$eq": cfg["ley"]}},
                    {"articulo": {"$in": cfg["articulos"]}}
                ]},
                include=["documents", "metadatas"]
            )
            for i in range(len(resultado["documents"])):
                clave = f"{resultado['metadatas'][i]['ley']}_{resultado['metadatas'][i]['articulo']}"
                if clave not in ids_vistos:
                    articulos.append({
                        "texto":    resultado["documents"][i],
                        "ley":      resultado["metadatas"][i]["ley"],
                        "articulo": resultado["metadatas"][i]["articulo"],
                    })
                    ids_vistos.add(clave)
    return articulos, temas


# ─── BÚSQUEDA DIRECTA POR ARTÍCULO ──────────────────────────────────────────

def buscar_ley_por_alias(texto_ley: str) -> str | None:
    """Busca el nombre completo de una ley por su alias. Retorna None si no encuentra."""
    texto_norm = normalizar(texto_ley).strip()
    # Primero: coincidencia exacta
    if texto_norm in ALIAS_LEYES:
        return ALIAS_LEYES[texto_norm]
    # Segundo: match parcial (alias contenido en texto o viceversa)
    for alias, nombre in ALIAS_LEYES.items():
        if alias in texto_norm or texto_norm in alias:
            return nombre
    # Tercero: todas las palabras del alias presentes en el texto
    mejor = ""
    resultado = None
    for alias, nombre in ALIAS_LEYES.items():
        palabras_alias = alias.split()
        if all(p in texto_norm for p in palabras_alias) and len(alias) > len(mejor):
            mejor = alias
            resultado = nombre
    return resultado


def buscar_articulo_en_db(ley_real: str, num_art: int) -> list[dict]:
    """Busca un artículo específico en ChromaDB. Retorna lista de artículos encontrados."""
    resultado = coleccion.get(
        where={"$and": [
            {"ley":      {"$eq": ley_real}},
            {"articulo": {"$eq": num_art}}
        ]},
        include=["documents", "metadatas"]
    )
    if not resultado["documents"]:
        return []

    arts = []
    for i in range(len(resultado["documents"])):
        arts.append({
            "texto":    resultado["documents"][i],
            "ley":      resultado["metadatas"][i]["ley"],
            "articulo": resultado["metadatas"][i]["articulo"],
        })
    return arts


def buscar_articulo_directo(pregunta: str) -> list[dict]:
    """
    Detecta si el usuario pide un artículo específico de una ley
    (ej: 'artículo 69 de la constitución') y lo busca directo en ChromaDB.
    """
    pregunta_norm = normalizar(pregunta)

    patrones = [
        r'(?:articulo|art\.?)\s+(\d+)\s+(?:de\s+(?:la|el|los|las)\s+)?(.+)',
        r'(?:que\s+dice\s+el\s+)?(?:articulo|art\.?)\s+(\d+)\s+(?:de\s+(?:la|el|los|las)\s+)?(.+)',
    ]

    for patron in patrones:
        match = re.search(patron, pregunta_norm)
        if match:
            num_art = int(match.group(1))
            ley_mencionada = match.group(2).strip().rstrip('?.,!')

            ley_real = buscar_ley_por_alias(ley_mencionada)
            if not ley_real:
                continue

            logger.info(f"  Búsqueda directa: Art. {num_art} de {ley_real}")

            arts = buscar_articulo_en_db(ley_real, num_art)
            if arts:
                # También buscar artículos cercanos para contexto
                for delta in [-1, 1, -2, 2]:
                    vecinos = buscar_articulo_en_db(ley_real, num_art + delta)
                    if vecinos:
                        arts.append(vecinos[0])
                logger.info(f"  → Encontrado Art. {num_art} + {len(arts)-1} vecinos")
                return arts

    return []


def explicar_articulo(texto_articulo: str, ley: str, num: int) -> str:
    """Usa el LLM para dar una explicación breve de un artículo."""
    try:
        r = groq_client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": PROMPT_EXPLICAR_ARTICULO},
                {"role": "user", "content":
                    f"Explica este artículo:\n\n"
                    f"{ley}, Artículo {num}:\n{texto_articulo}"}
            ],
            max_tokens=300,
            temperature=0.1,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error explicando artículo: {e}")
        return ""


# ─── SEGUIMIENTO DE CONVERSACIÓN ────────────────────────────────────────────

PALABRAS_SEGUIMIENTO = [
    "explícame", "explicame", "explica", "dime más", "dime mas", "cuéntame",
    "cuentame", "y qué", "y que", "qué más", "que mas", "a dónde", "a donde",
    "adónde", "adonde", "cómo hago", "como hago", "qué hago", "que hago",
    "qué puedo", "que puedo", "pero", "y si", "en ese caso", "entonces",
    "amplía", "amplia", "detalla", "profundiza", "ese artículo", "ese articulo",
    "esa ley", "eso que dijiste", "lo anterior", "lo que dijiste", "más info",
    "mas info", "más información", "mas informacion", "repite", "no entendí",
    "no entendi", "qué significa", "que significa", "a quién", "a quien",
    "dónde denuncio", "donde denuncio", "dónde acudo", "donde acudo",
]


def es_seguimiento(pregunta: str) -> bool:
    """Detecta si la pregunta es un seguimiento de la conversación anterior."""
    pregunta_lower = pregunta.lower().strip()
    # Solo considerar seguimiento si tiene palabras clave de seguimiento
    # (antes: cualquier pregunta corta era seguimiento, causando resultados raros)
    if any(p in pregunta_lower for p in PALABRAS_SEGUIMIENTO):
        return True
    # Pregunta muy corta Y no parece ser tema nuevo
    if len(pregunta_lower.split()) <= 4 and not _tiene_tema_legal(pregunta_lower):
        return True
    return False


def _tiene_tema_legal(texto: str) -> bool:
    """Detecta si el texto contiene un tema legal específico."""
    temas_legales = [
        "despido", "trabajo", "robo", "policía", "policia", "detener", "detenido",
        "desalojo", "alquiler", "divorcio", "custodia", "pensión", "pension",
        "impuesto", "empresa", "herencia", "accidente", "denuncia", "demanda",
        "violencia", "maltrato", "vecino", "ruido", "banco", "estafa", "hackeo",
        "arrendamiento", "contrato", "deuda", "multa", "licencia",
    ]
    return any(t in texto for t in temas_legales)


def es_consulta_no_legal(pregunta: str) -> bool:
    """Detecta saludos y preguntas no legales que no necesitan búsqueda RAG."""
    pregunta_lower = pregunta.lower().strip()
    patrones_no_legal = [
        r"^(hola|hey|buenas?|saludos|hi|hello|buenos?\s+d[ií]as?|buenas?\s+tardes?|buenas?\s+noches?)[\s!.?]*$",
        r"^(gracias|thanks?|ok|vale|entendido|perfecto|listo|genial)[\s!.?]*$",
        r"^(qu[ée]\s+(?:tal|onda|hubo)|c[oó]mo\s+est[aá]s?)[\s!.?]*$",
        r"^(adi[oó]s|chao|bye|hasta\s+luego|nos\s+vemos)[\s!.?]*$",
        r"^(qui[eé]n\s+eres|qu[eé]\s+eres|qu[eé]\s+haces|c[oó]mo\s+te\s+llamas)[\s!.?]*$",
    ]
    return any(re.match(p, pregunta_lower) for p in patrones_no_legal)


# ─── PIPELINE PRINCIPAL ─────────────────────────────────────────────────────

def buscar_articulos_nuevos(pregunta: str) -> tuple[list[dict], str]:
    """Pipeline de búsqueda híbrida. Retorna (artículos_finales, contexto_formateado)."""

    pregunta_juridica = reformular(pregunta)
    logger.info(f"  Original:    {pregunta}")
    logger.info(f"  Reformulada: {pregunta_juridica}")

    ids_vistos = set()
    relevantes = []

    def agregar(arts):
        for art in arts:
            clave = f"{art['ley']}_{art['articulo']}"
            if clave not in ids_vistos:
                relevantes.append(art)
                ids_vistos.add(clave)

    # 0. Búsqueda directa por artículo (si pide uno específico)
    directos = buscar_articulo_directo(pregunta)
    if directos:
        agregar(directos)
        logger.info(f"  Búsqueda directa: {len(directos)} artículos")

    # 1. Artículos Clave (más precisos)
    arts_clave, temas_detectados = buscar_articulos_clave(pregunta)
    agregar(arts_clave)

    # 2. Embeddings (Semántica pura)
    agregar(buscar_embedding(pregunta_juridica, top_n=10))

    # 3. BM25 (Palabras exactas) - complemento
    agregar(buscar_bm25(pregunta_juridica, top_n=8))
    agregar(buscar_bm25(pregunta, top_n=5))

    # 4. Filtro de Diversidad (Máx 4 por ley, máx 10 total)
    # Priorizar artículos clave (keyword match) sobre BM25/embeddings
    por_ley = {}
    relevantes_finales = []
    MAX_POR_LEY = 4
    MAX_TOTAL = 10

    for art in relevantes:
        ley = art["ley"]
        if ley not in por_ley:
            por_ley[ley] = 0

        if por_ley[ley] < MAX_POR_LEY:
            relevantes_finales.append(art)
            por_ley[ley] += 1

        if len(relevantes_finales) >= MAX_TOTAL:
            break

    logger.info(f"  Total al LLM: {len(relevantes_finales)}")

    if not relevantes_finales:
        return [], ""

    # Formato numerado
    contexto = "LISTA DE ARTÍCULOS DISPONIBLES (SOLO puedes citar de esta lista):\n\n"
    for idx, art in enumerate(relevantes_finales, 1):
        contexto += f"[{idx}] {art['ley']}, Art. {art['articulo']}:\n{art['texto']}\n\n"

    # Inyectar guías institucionales según temas detectados
    guias_usadas = set()
    for tema in temas_detectados:
        if tema in GUIAS_INSTITUCIONALES and tema not in guias_usadas:
            contexto += GUIAS_INSTITUCIONALES[tema]
            guias_usadas.add(tema)

    # Si no se detectaron temas por keyword, intentar inyectar guía por contexto general
    if not guias_usadas:
        pregunta_lower = pregunta.lower()
        mapeo_rapido = {
            "empresa": "comercial", "registrar": "comercial", "negocio": "comercial",
            "despid": "laboral", "trabajo": "laboral", "sueldo": "laboral",
            "robar": "penal", "robo": "penal", "estafa": "penal",
            "vecino": "justicia_paz", "ruido": "justicia_paz",
            "desaloj": "vivienda_desalojo", "arrendad": "vivienda_arrendamiento",
            "divorc": "familia", "custodia": "familia", "hijo": "familia",
            "golpe": "violencia_mujer", "maltrat": "violencia_mujer",
            "impuesto": "tributario", "seniat": "tributario",
        }
        for palabra, tema in mapeo_rapido.items():
            if palabra in pregunta_lower and tema in GUIAS_INSTITUCIONALES:
                contexto += GUIAS_INSTITUCIONALES[tema]
                break

    return relevantes_finales, contexto


def buscar_y_responder(pregunta: str, historial: list[dict] = None,
                       user_id: int = None) -> str:
    """Pipeline híbrido con seguimiento de conversación para premium."""
    import db  # import aquí para evitar circular

    # Protección contra prompt injection
    if es_prompt_injection(pregunta):
        logger.warning(f"  ⚠️ Prompt injection detectado de user {user_id}")
        return "No puedo procesar esa solicitud. Escribe tu consulta legal y te ayudo."

    pregunta = sanitizar_input(pregunta)

    # Si es un saludo o pregunta no legal, responder sin búsqueda RAG
    if es_consulta_no_legal(pregunta):
        logger.info(f"  → Consulta no legal, respondiendo sin RAG")
        try:
            response = groq_client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": "Eres aBOTgado, asistente jurídico venezolano en Telegram. "
                     "El usuario te saluda o hace una pregunta casual. Responde breve y amigable en español venezolano, "
                     "e invítalo a hacer su consulta legal. NO cites artículos ni leyes. Máximo 2 líneas."},
                    {"role": "user", "content": pregunta}
                ],
                max_tokens=100,
                temperature=0.3,
            )
            return response.choices[0].message.content
        except Exception:
            return "¡Hola! Soy aBOTgado, tu asistente jurídico. ¿En qué te puedo ayudar?"

    es_premium = user_id and db.es_premium(user_id)
    seguimiento = es_premium and historial and es_seguimiento(pregunta)

    if seguimiento:
        logger.info(f"  → Pregunta de seguimiento detectada")
        contexto_previo = db.cargar_contexto(user_id)

        if contexto_previo:
            # Para seguimiento, usar SOLO el contexto previo
            # No hacer búsqueda nueva que trae artículos irrelevantes
            contexto = contexto_previo
        else:
            # Si no hay contexto previo, buscar normalmente
            _, contexto = buscar_articulos_nuevos(pregunta)
            if not contexto:
                return ("No tengo artículos específicos sobre este tema en mi base actual.\n\n"
                        "⚠️ Consulta con un abogado.")
    else:
        relevantes, contexto = buscar_articulos_nuevos(pregunta)
        if not relevantes:
            return ("No tengo artículos específicos sobre este tema en mi base actual.\n\n"
                    "⚠️ Consulta con un abogado.")

    if es_premium:
        db.guardar_contexto(user_id, contexto)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if historial:
        messages += historial

    instruccion_guia = ("IMPORTANTE: Al final del contexto hay una GUÍA INSTITUCIONAL con pasos concretos, "
                        "teléfonos, plazos y documentos. ÚSALA en la sección 'Qué hacer'. "
                        "NO digas 'busca un abogado' ni 'acude a la autoridad competente' — "
                        "di el NOMBRE de la institución, el teléfono si lo tienes, y qué documentos llevar.")

    if seguimiento:
        messages.append({"role": "user", "content":
            f"PREGUNTA DE SEGUIMIENTO: {pregunta}\n\n"
            f"El usuario hace una pregunta sobre tu respuesta anterior. "
            f"Usa los artículos del contexto para dar más detalles.\n\n"
            f"{contexto}\n\n"
            f"RECUERDA: Solo cita artículos de la lista. No inventes ninguno.\n"
            f"{instruccion_guia}"})
    else:
        messages.append({"role": "user", "content":
            f"PREGUNTA: {pregunta}\n\n{contexto}\n\n"
            f"RECUERDA: Solo cita artículos de la lista anterior. No inventes ninguno.\n"
            f"{instruccion_guia}"})

    try:
        response = groq_client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=messages,
            max_tokens=700,
            temperature=0.05,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error en Groq LLM: {e}")
        return "Hubo un error procesando tu consulta. Por favor intenta de nuevo en unos minutos."


# ─── FORMATO DE RESPUESTA ───────────────────────────────────────────────────

def formatear_respuesta(texto: str) -> str:
    """
    Post-procesa la respuesta del LLM para garantizar formato HTML en Telegram.
    """
    # Markdown → HTML
    texto = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', texto, flags=re.DOTALL)
    texto = re.sub(r'\*([^\n*]+?)\*', r'<b>\1</b>', texto)
    texto = re.sub(r'(?<!\w)_([^\n_]+?)_(?!\w)', r'<i>\1</i>', texto)

    # Negritas en encabezados de sección
    for plano, html in [
        ('📌 Respuesta:',        '📌 <b>Respuesta:</b>'),
        ('📖 Qué dice la ley:',  '📖 <b>Qué dice la ley:</b>'),
        ('💡 Qué hacer:',        '💡 <b>Qué hacer:</b>'),
    ]:
        if plano in texto and html not in texto:
            texto = texto.replace(plano, html)

    # Negritas automáticas en citas de artículos
    def negrita_cita(m):
        prefijo = m.group(1)
        cita    = m.group(2)
        if '<b>' in cita:
            return m.group(0)
        return f'{prefijo}<b>{cita}</b>'

    texto = re.sub(
        r'([-•]\s*)([^\n<>:]+,\s*Art\.\s*[\d.]+\s*:)',
        negrita_cita,
        texto
    )

    # Itálica en disclaimer
    disc_plano = '⚠️ Info orientativa. Consulta un abogado.'
    disc_html  = '⚠️ <i>Info orientativa. Consulta un abogado.</i>'
    if disc_plano in texto and disc_html not in texto:
        texto = texto.replace(disc_plano, disc_html)

    return texto


def generar_texto_leyes() -> str:
    """Genera el texto del comando /leyes dinámicamente desde el catálogo."""
    total = coleccion.count()
    texto = f"📚 <b>{total} articulos</b> indexados\n\n"

    for categoria, leyes in CATALOGO_LEYES.items():
        texto += f"<b>{categoria}:</b>\n"
        for nombre, alias in leyes:
            texto += f"  • {nombre} (<code>{alias}</code>)\n"
        texto += "\n"

    texto += "Usa /ley &lt;alias&gt; &lt;numero&gt; para ver un articulo.\n"
    texto += "Ej: <code>/ley LOTTT 85</code>"
    return texto
