"""
aBOTgado - Clasificador de Tema vía LLM
=========================================
Opción A: usa Groq para clasificar la pregunta en un tema jurídico
cuando el matching de keywords de ARTICULOS_CLAVE no detecta ninguno.

Ventaja: captura variantes semánticas que nunca se hardcodearían.
Ejemplo: "me embistió un potro en la autopista" → transito_accidente
         "me echaron sin avisarme" → laboral_despido
         "el dueño del edificio quiere que me vaya" → vivienda_desalojo

Costo: una llamada extra a Groq (~50 tokens) solo cuando keywords fallan.
"""

import logging
from groq import Groq
import config

logger = logging.getLogger(__name__)

_groq_client = Groq(api_key=config.GROQ_API_KEY)

# Mapa de temas clasificables → coincide con los buckets de ARTICULOS_CLAVE
# Agrupados por área para que el prompt sea corto y el LLM sea más preciso.
TEMAS_CLASIFICABLES = {
    # Tránsito
    "transito_accidente":     "accidente de tránsito, choque, atropello, volcamiento, fuga del conductor",
    "transito_infracciones":  "infracción de tránsito, semáforo, velocidad, alcohol al volante, manejar ebrio, piques",
    "transito_licencia":      "licencia de conducir, renovar licencia, certificado médico conductor",
    "transito_vehiculo":      "seguro vehicular, placa, revisión vehicular, papeles del carro, retención vehículo",
    "transito_estacionamiento": "estacionamiento ilegal, grúa, remolcar, obstaculizar vía, conos en la calle",
    "animales_via":           "animal en la carretera, vaca suelto, caballo suelto, ganado en la vía, animal causa accidente",
    # Laboral
    "laboral_despido":        "despido, botaron del trabajo, reenganche, inamovilidad, estabilidad laboral",
    "laboral_vacaciones":     "vacaciones, bono vacacional, días de descanso laboral",
    "laboral_prestaciones":   "prestaciones sociales, liquidación, utilidades, antigüedad",
    "laboral_general":        "problemas laborales, salario, sueldo, cesta ticket, horas extras, contrato de trabajo",
    "pago_feriados":          "trabajo en domingo o feriado, pago doble, descanso semanal",
    "permiso_medico":         "permiso médico, reposo, cita médica, suspensión por enfermedad laboral",
    "maternidad_paternidad":  "embarazo, maternidad, paternidad, fuero materno, inamovilidad embarazada",
    # Familia
    "familia":                "custodia, guarda, patria potestad, pensión alimentaria, régimen de visitas hijos",
    "divorcio":               "divorcio, separación, bienes gananciales, matrimonio, comunidad conyugal",
    "violencia_mujer":        "violencia doméstica, maltrato, femicidio, abuso, violencia de género",
    # Vivienda / Arrendamiento
    "vivienda_desalojo":      "desalojo arbitrario, echar de la casa, orden de desalojo",
    "vivienda_arrendamiento": "arrendamiento de vivienda, alquiler, canon, prórroga legal, SUNAVI",
    "arrendamiento_comercial":"local comercial alquilado, arrendamiento comercial, SUNDDE",
    "propiedad_horizontal":   "condominio, junta de condominio, gastos comunes, edificio, área común",
    # Penal / Seguridad
    "penal":                  "robo, hurto, homicidio, estafa, lesiones, delito penal, denuncia penal",
    "robo_vehiculo":          "robo del carro, hurto del vehículo, se llevaron la moto",
    "drogas":                 "drogas, marihuana, cocaína, posesión de drogas, narcotráfico",
    "amenazas":               "amenazas de muerte, intimidación, acoso, amenaza por WhatsApp",
    "derechos":               "detención arbitraria, abuso policial, allanamiento, derechos humanos, preso",
    "detencion_arbitraria":   "me detuvieron ilegalmente, preso sin orden judicial, arresto arbitrario",
    "procesal_penal":         "proceso penal, fiscalía, imputado, audiencia, defensor público, flagrancia",
    # Civil
    "herencia":               "herencia, herederos, sucesión, bienes del fallecido, testamento",
    "testamento":             "hacer testamento, testamento abierto, última voluntad, desheredar",
    "deuda_civil":            "cobrar deuda, préstamo impago, deuda entre personas",
    "vicios_ocultos":         "vicios ocultos en inmueble, casa con defectos, filtraciones, defectos de construcción",
    "propiedad":              "propiedad, escritura, hipoteca, comprar casa, vender inmueble",
    # Consumidor / Comercio
    "consumidor":             "producto defectuoso, garantía, devolución, reclamo al vendedor, derechos consumidor",
    "sobreprecio":            "cobro excesivo, precio abusivo, especulación, me cobraron de más",
    "comercial":              "registrar empresa, sociedad anónima, C.A., registro mercantil",
    "negocio_casa":           "abrir negocio, bodega, vender comida, permiso sanitario, licencia comercial",
    # Derechos / Constitucional
    "comunicaciones":         "inviolabilidad del teléfono, revisar celular, espiar mensajes, WhatsApp privado",
    "libre_transito":         "bloquear la calle, conos en la acera, impedir circulación, libre tránsito",
    "recurso_multa":          "recurrir multa, multa injusta, apelar sanción administrativa",
    "detencion_arbitraria":   "detención arbitraria, me llevaron preso sin orden",
    # Tributario / Financiero
    "tributario":             "impuestos, SENIAT, IVA, ISLR, multa fiscal, declaración renta",
    "islr":                   "impuesto sobre la renta, declarar renta, ISLR, enriquecimiento",
    "bancario":               "cuenta bancaria, fraude bancario, SUDEBAN, clonaron tarjeta",
    "seguro_social":          "IVSS, seguro social, pensión vejez, paro forzoso, cotizaciones",
    # Otros
    "animales":               "maltrato animal, perro, gato, mascota, crueldad animal, envenenar animal",
    "corrupcion":             "corrupción, coima, soborno, extorsión, matraca, funcionario pide dinero",
    "discapacidad":           "discapacidad, persona con discapacidad, accesibilidad, CONAPDIS",
    "adultos_mayores":        "adulto mayor, anciano, pensionado, jubilado, maltrato a abuelo",
    "justicia_paz":           "conflicto vecinal, ruido del vecino, bulla, juez de paz comunal",
    "municipal":              "alcaldía, ordenanza, impuesto municipal, permiso municipal",
    "tramites":               "trámites administrativos, burocracia, papeleo, requisitos legales",
    "mala_praxis":            "negligencia médica, mala praxis, error del médico, operaron mal",
    "ambiente":               "contaminación, daño ambiental, tala, quema, residuos",
    "delitos_informaticos":   "hackeo, estafa por internet, suplantación identidad, ciberdelito",
}

# Prompt ultra-corto — solo el listado de claves y sus descripciones
_PROMPT_CLASIFICADOR = """Eres un clasificador de temas jurídicos venezolanos.
Dado un mensaje, responde ÚNICAMENTE con la clave del tema más relevante de la lista de abajo.
Si el mensaje no tiene tema legal claro, responde: ninguno

TEMAS (clave: descripción):
{lista_temas}

Responde SOLO la clave. Sin explicaciones. Sin puntuación."""


def _construir_prompt() -> str:
    lineas = [f"{clave}: {desc}" for clave, desc in TEMAS_CLASIFICABLES.items()]
    return _PROMPT_CLASIFICADOR.format(lista_temas="\n".join(lineas))


_PROMPT_SISTEMA = _construir_prompt()


def clasificar_tema(pregunta: str, timeout_ms: int = 3000) -> str | None:
    """
    Clasifica la pregunta en un tema jurídico usando Groq.

    Retorna:
        str   — clave de tema (ej: "transito_accidente") si se detectó
        None  — si no es tema legal o hubo error

    Costo: ~60-80 tokens de entrada + ~5 tokens de salida.
    Latencia esperada: 200-400ms (llama-3.3-70b con prompt corto).
    """
    try:
        response = _groq_client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": _PROMPT_SISTEMA},
                {"role": "user",   "content": pregunta[:300]},
            ],
            max_tokens=15,       # Solo necesitamos la clave (~10 chars max)
            temperature=0.0,     # Determinista
        )
        resultado = response.choices[0].message.content.strip().lower()
        resultado = resultado.strip(".,;:\"'").replace(" ", "_")

        if resultado == "ninguno" or resultado not in TEMAS_CLASIFICABLES:
            logger.info(f"  Clasificador LLM: '{resultado}' → sin tema reconocido")
            return None

        logger.info(f"  Clasificador LLM: '{pregunta[:60]}' → {resultado}")
        return resultado

    except Exception as e:
        logger.warning(f"  Clasificador LLM falló (no crítico): {e}")
        return None
