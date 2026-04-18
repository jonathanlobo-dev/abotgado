"""
aBOTgado - Módulo de seguridad y filtrado
==========================================
- Detección de prompt injection
- Sanitización de input
- Filtrado de teléfonos inventados por el LLM
- Filtrado de montos inventados por el LLM
"""

import re

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
    # Fuga de prompt — pedir instrucciones/prompt/reglas
    r"(?:dime|repite|muestra|imprime|revela|comparte)\s+(?:tu|el|las?)\s+(?:prompt|instrucciones|reglas|system\s*prompt)",
    r"(?:cu[aá]les?\s+(?:son|fueron)\s+)?(?:tus|las)\s+instrucciones",
    r"(?:c[oó]mo\s+(?:te|fuiste)\s+)?(?:programaron|configuraron|crearon)",
    r"(?:primera?\s+)?(?:oraci[oó]n|l[ií]nea|palabra)\s+de\s+tu\s+(?:prompt|sistema)",
    # Autoridad falsa — hacerse pasar por developer/admin
    r"soy\s+(?:el\s+)?(?:desarrollador|creador|admin|programador|due[ñn]o)",
    r"(?:auditor[ií]a|test|prueba)\s+de\s+seguridad",
    r"orden\s+directa\s+de\s+mantenimiento",
    # Payload splitting — concatenar variables
    r"(?:define|asigna|pon)\s+(?:la\s+)?variable\s+[A-Z]\s+como",
    r"concatena\s+[A-Z]\s*\+\s*[A-Z]",
    # Context poisoning — simular historial falso
    r"Bot:\s+.{5,}\s+Usuario:",
    # Codificación oculta
    r"(?:decodifica|decode|base64|hexadecimal)\s+(?:esto|this|el\s+siguiente)",
    # Preguntas sobre el bot/configuración
    r"reglas\s+que\s+sigues\s+(?:internamente|para\s+responder)",
    r"resumen\s+de\s+tu\s+configuracion",
    r"mostr[aá]ndome\s+(?:las?\s+)?(?:primeras?\s+)?\d*\s*(?:l[ií]neas?\s+de\s+)?(?:tus\s+)?instrucciones",
    # Forzar formato/idioma
    r"(?:responde|contesta|escribe)\s+(?:en|solo\s+en)\s+(?:ruso|ingl[eé]s|franc[eé]s|japon[eé]s|alem[aá]n|portugu[eé]s|chino|[aá]rabe|italiano)",
    r"(?:responde|contesta|escribe)\s+(?:en|solo\s+en)\s+(?:JSON|json|xml|markdown|c[oó]digo|formato\s+(?:JSON|xml|csv))",
    r"(?:est[aá]\s+)?(?:estrictamente\s+)?prohibido\s+(?:usar|que\s+uses)\s+(?:emojis|vi[ñn]etas)",
    # Marcadores de rol tipo jailbreak (ChatML, Anthropic, OpenAI)
    r"<\|(?:im_start|im_end|endoftext|system|assistant|user)\|>",
    r"###\s*(?:system|assistant|user|instruction)s?\s*[:\n]",
    r"\[(?:system|assistant|user|INST|/INST)\]",
    r"(?:^|\n)\s*(?:System|Assistant|Human|User)\s*:\s*[A-Z]",
    # Simulación / role-play hacia otro bot
    r"simulacro\s+de\s+(?:otro|un)\s+(?:bot|asistente|IA)",
    r"role[-\s]*play\s+(?:como|as)\s+",
    r"finge\s+(?:que\s+eres|ser)",
    r"imagina\s+que\s+eres\s+(?:otro|un)\s+",
    # Payload JSON/XML que simula mensajes de API
    r'"role"\s*:\s*"(?:system|assistant|user)"',
    r"<message\s+role\s*=",
    # Simulacro / role-play ampliado
    r"haz\s+(?:de\s+cuenta|como\s+si)\s+",
    r"pretend\s+(?:you\s+are|to\s+be)\s+",
    r"f[ií]ngete\s+(?:que\s+eres|como)\s+",
    r"en\s+este\s+juego\s+de\s+roles?\s+",
    # Intento de sobreescribir instrucciones con autoridad ficticia
    r"(?:a\s+partir\s+de\s+ahora|desde\s+este\s+momento)\s+(?:eres|tu\s+nuevo\s+rol|ignora)",
    r"nueva\s+instrucci[oó]n\s+(?:de\s+sistema|del\s+sistema)\s*:",
    r"override\s+(?:all\s+)?(?:previous\s+)?(?:instructions|rules|constraints)",
    # Prompt de continuación — "continúa el texto:" con payload
    r"contin[uú]a\s+(?:el\s+siguiente\s+)?(?:texto|di[aá]logo|conversaci[oó]n)\s*:\s*(?:Bot|Sistema|User|Asistente)\s*:",
]

_REGEX_INJECTION = re.compile(
    "|".join(_PATRONES_INJECTION), re.IGNORECASE
)

# Caracteres Unicode invisibles / bidireccionales usados para ocultar payloads
_REGEX_UNICODE_OCULTO = re.compile(
    r"[\u200B-\u200F\u202A-\u202E\u2060-\u2064\uFEFF]"
)

# Base64 largo puro (>=60 chars) — señal de payload codificado
_REGEX_BASE64_LARGO = re.compile(r"[A-Za-z0-9+/]{60,}={0,2}")


def sanitizar_input(texto: str) -> str:
    """Sanitiza el input del usuario contra prompt injection."""
    # Limitar longitud (500 chars es más que suficiente para una pregunta legal)
    texto = texto[:500]
    # Quitar caracteres Unicode invisibles / bidi (usados para ocultar payloads)
    texto = _REGEX_UNICODE_OCULTO.sub("", texto)
    # Remover intentos de inyección de roles/instrucciones
    texto = _REGEX_INJECTION.sub("[filtrado]", texto)
    # Filtrar strings base64 largos
    texto = _REGEX_BASE64_LARGO.sub("[base64]", texto)
    return texto.strip()


def es_prompt_injection(texto: str) -> bool:
    """Detecta si el texto contiene intento de prompt injection."""
    if _REGEX_INJECTION.search(texto):
        return True
    if _REGEX_BASE64_LARGO.search(texto):
        return True
    if _REGEX_UNICODE_OCULTO.search(texto):
        return True
    return False


# ─── DETECCIÓN DE INTENCIÓN DAÑINA ──────────────────────────────────────────
# Consultas que expresan intención de cometer un delito (no son preguntas
# jurídicas legítimas). Distinto a prompt injection: acá el usuario pregunta
# "¿puedo hacer X?" donde X es un crimen. No elaboramos respuesta legal —
# respondemos brevemente que es un delito y cerramos.

_PATRONES_INTENCION_DANINA = [
    # Violación / agresión sexual en 1ra persona
    r"\bpuedo\s+violar\b",
    r"\bquiero\s+violar\b",
    r"\bvoy\s+a\s+violar\b",
    r"\bc[oó]mo\s+(puedo\s+)?violar\b",
    r"\bpuedo\s+abusar\s+(sexualmente\s+)?(de\s+)?(una|un|mi|el|la)\b",
    r"\bquiero\s+abusar\s+(sexualmente\s+)?(de\s+)?\b",
    # Homicidio / lesiones en 1ra persona
    r"\bc[oó]mo\s+(puedo\s+)?matar\s+(a\s+)?(mi|una|un|el|la|su)\b",
    r"\bpuedo\s+matar\s+(a\s+)?(mi|una|un|el|la|su)\b",
    r"\bquiero\s+matar\s+(a\s+)?(mi|una|un|el|la|su)\b",
    r"\bc[oó]mo\s+(le\s+)?doy\s+un\s+golpe\s+sin\s+que\b",
    r"\bc[oó]mo\s+(puedo\s+)?golpear\s+(a\s+)?(mi|una|un|el|la)\b",
    # Robo / extorsión activos en 1ra persona
    r"\bc[oó]mo\s+(puedo\s+)?robar\s+(a\s+)?(mi|una|un|el|la|su)\b",
    r"\bquiero\s+robar\s+(a\s+)?(mi|una|un|el|la|su)\b",
    r"\bc[oó]mo\s+(puedo\s+)?extorsionar\b",
    r"\bquiero\s+extorsionar\b",
    # Drogas: producir / traficar (no consumir — eso sí es consulta legítima)
    r"\bc[oó]mo\s+(puedo\s+)?fabricar\s+(drogas?|cocain|marihuana|crack|sustancias?\s+ilegales?)\b",
    r"\bc[oó]mo\s+(puedo\s+)?traficar\s+(drogas?|sustancias?)\b",
    # Maltrato / abuso animal activo en 1ra persona
    r"\bpuedo\s+(golpear|matar|abusar|violar|torturar)\s+(a\s+)?(mi\s+)?(mascota|perro|gato|animal|peludito)\b",
    r"\bquiero\s+(golpear|matar|abusar|violar|torturar)\s+(a\s+)?(mi\s+)?(mascota|perro|gato|animal|peludito)\b",
    # Secuestro activo
    r"\bc[oó]mo\s+(puedo\s+)?secuestrar\b",
    r"\bquiero\s+secuestrar\b",
]

_REGEX_INTENCION_DANINA = re.compile(
    "|".join(_PATRONES_INTENCION_DANINA), re.IGNORECASE
)

_RESPUESTA_INTENCION_DANINA = (
    "⚠️ <b>Consulta no procesable</b>\n\n"
    "Lo que describes constituye un delito en Venezuela.\n\n"
    "aBOTgado está diseñado para orientar legalmente a personas que "
    "buscan defender sus derechos o entender la ley — no para asistir "
    "en conductas que puedan dañar a otros.\n\n"
    "Si tienes una consulta legal legítima, escríbela y te ayudo."
)


def detectar_intencion_danina(texto: str) -> bool:
    """Retorna True si la consulta expresa intención explícita de cometer un delito.

    Distinto a prompt injection: no es un ataque al sistema, es una pregunta
    que el bot no debe responder con información legal detallada.
    """
    return bool(_REGEX_INTENCION_DANINA.search(texto))


def respuesta_intencion_danina() -> str:
    """Mensaje de rechazo para consultas con intención dañina."""
    return _RESPUESTA_INTENCION_DANINA


# ─── POST-FILTRO DE TELÉFONOS INVENTADOS ────────────────────────────────────

# Teléfonos REALES de las guías institucionales (whitelist)
_TELEFONOS_REALES = {
    "0800-872-2256", "0800-TRABAJO",
    "0800-333-3676", "0800-DEFENSORIA",
    "0800-24272-00", "0800-CICPC-00", "0800-CICPC",
    "0800-6466-700", "0800-NIÑOS-00", "0800-NINOS-00",
    "0800-685-3737", "0800-MUJERES",
    "0800-SUNDDE-0", "0800-SUNDDE",
    "(0212) 408-5000", "0212-408-5000", "0212-4085000",
    "171",
}

def _filtrar_telefonos_inventados(texto: str) -> str:
    """Elimina números de teléfono que el LLM inventó (no están en la whitelist)."""
    def es_telefono_real(fragmento):
        fragmento = fragmento.strip()
        for real in _TELEFONOS_REALES:
            if real in fragmento or fragmento in real:
                return True
        return False

    def reemplazar_numerico(m):
        if es_telefono_real(m.group(0)):
            return m.group(0)
        return ""

    def reemplazar_0800_alfa(m):
        if es_telefono_real(m.group(0)):
            return m.group(0)
        return ""

    # 1. Capturar 0800-PALABRA (ej: 0800-IDEFENSO, 0800-SALUD)
    resultado = re.sub(
        r'0800-[A-ZÁÉÍÓÚÑa-záéíóúñ][-A-ZÁÉÍÓÚÑa-záéíóúñ0-9]*',
        reemplazar_0800_alfa,
        texto
    )

    # 2. Capturar numéricos: 0212-XXX, (0212) XXX, 0800-123-4567
    resultado = re.sub(
        r'\(?\d{4}\)?\s*[-.]?\s*\d{3,4}\s*[-.]?\s*\d{2,4}(?:\s*[-.]?\s*\d{2,4})?',
        reemplazar_numerico,
        resultado
    )

    # Limpiar restos: paréntesis vacíos, "teléfono:" sin número, dobles espacios
    resultado = re.sub(r'(?:tel[eé]fono|l[ií]nea|n[uú]mero)\s*:\s*\)', '', resultado, flags=re.IGNORECASE)
    resultado = re.sub(r'(?:tel[eé]fono|l[ií]nea|n[uú]mero)\s*:\s*(?=[.\s,])', '', resultado, flags=re.IGNORECASE)
    resultado = re.sub(r'\(\s*\)', '', resultado)
    resultado = re.sub(r'  +', ' ', resultado)
    resultado = re.sub(r'\.\s*\.', '.', resultado)
    resultado = re.sub(r',\s*\.', '.', resultado)
    return resultado


def _filtrar_montos_inventados(texto: str) -> str:
    """Elimina montos/porcentajes que el LLM inventó en la sección 'Qué hacer'.
    Solo filtra en la parte DESPUÉS de los artículos citados (💡 Qué hacer)."""
    # Patrones de montos inventados comunes de Llama 3.3
    patrones_montos = [
        # "que es de 50% del salario mínimo" → eliminar frase completa
        r',?\s*que\s+es\s+de\s+\d+[^.]*(?:salario|ingreso|sueldo|bolívar|bs)[^.]*',
        # "50% del salario mínimo", "20-30% del ingreso", etc.
        r'\b\d+(?:[.,]\d+)?%\s+del\s+(?:salario|ingreso|sueldo)[^.]*',
        # "entre X% y Y% del ingreso"
        r'entre\s+\d+%?\s+y\s+\d+%\s+del\s+(?:salario|ingreso|sueldo)[^.]*',
    ]
    for patron in patrones_montos:
        texto = re.sub(patron, '', texto, flags=re.IGNORECASE)
    # Limpiar artefactos: "es de .", puntos dobles, espacios dobles
    texto = re.sub(r'(?:es|será?)\s+de\s*\.', '.', texto, flags=re.IGNORECASE)
    texto = re.sub(r'\.\s*\.', '.', texto)
    texto = re.sub(r',\s*\.', '.', texto)
    texto = re.sub(r'  +', ' ', texto)
    return texto
