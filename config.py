"""
aBOTgado - Configuración centralizada
======================================
Carga variables desde .env y define constantes del proyecto.
En Railway: DATA_DIR=/data (Volume persistente)
En local:   DATA_DIR no se define, usa la carpeta del proyecto
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env desde la raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ─── SECRETS (desde .env) ────────────────────────────────────────────────────

GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
HF_API_KEY     = os.getenv("HF_API_KEY", "")

# Múltiples admins: "509717419,123456789" → [509717419, 123456789]
_admin_raw = os.getenv("ADMIN_IDS", os.getenv("ADMIN_ID", "0"))
ADMIN_IDS  = [int(x.strip()) for x in _admin_raw.split(",") if x.strip()]
ADMIN_ID   = ADMIN_IDS[0] if ADMIN_IDS else 0  # compatibilidad

# ─── PATHS ───────────────────────────────────────────────────────────────────
# DATA_DIR: donde viven los datos persistentes
#   - Local: misma carpeta del proyecto
#   - Railway: /data (Volume montado)

DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR)))

DB_PATH         = str(DATA_DIR / "abotgado_db")
PDF_FOLDER      = str(BASE_DIR / "leyes")        # PDFs siempre en el código
SQLITE_DB_FILE  = str(DATA_DIR / "abotgado_usuarios.db")
PLANTILLAS_DIR  = str(BASE_DIR / "plantillas")    # Plantillas siempre en el código

# ─── MODELOS ─────────────────────────────────────────────────────────────────

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
HF_EMBED_URL    = f"https://router.huggingface.co/hf-inference/models/{EMBEDDING_MODEL}/pipeline/feature-extraction"

# Modelo LLM principal — se puede sobreescribir con la variable de entorno LLM_MODEL
# Historial: llama-3.3-70b-versatile → openai/gpt-oss-120b (Llama 4 Maverick deprecado Feb 2026)
# Alternativa más rápida: openai/gpt-oss-20b (1000 tok/s, 20B params)
LLM_MODEL       = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

# Modelo LLM rápido para tareas auxiliares (verificador de relevancia, clasificador OOD)
# Debe ser barato y rápido — solo decide "sí/no/lista de números", no genera texto largo.
LLM_MODEL_FAST  = os.getenv("LLM_MODEL_FAST", "llama-3.1-8b-instant")

# Modelo LLM para el router unificado de routing/clasificación.
# Reemplaza 6 funciones hardcoded (es_consulta_no_legal, es_fuera_de_dominio,
# _tiene_tema_legal, es_seguimiento, reformular_y_clasificar, _descomponer_consulta).
# Salida: JSON estructurado. Necesita razonamiento + adherencia a JSON estricto.
# Posición intermedia entre LLM_MODEL_FAST (8B, falla JSON) y LLM_MODEL (120B, overkill).
LLM_MODEL_ROUTER = os.getenv("LLM_MODEL_ROUTER", "llama-3.3-70b-versatile")
ROUTER_TIMEOUT_S = float(os.getenv("ROUTER_TIMEOUT_S", "4.0"))
ROUTER_HABILITADO = os.getenv("ROUTER_HABILITADO", "1") == "1"

# Verificador de relevancia post-retrieval: filtra artículos tangenciales antes
# de pasarlos al LLM principal. Si False, se omite (útil para tests/debug).
VERIFICADOR_HABILITADO = os.getenv("VERIFICADOR_HABILITADO", "1") == "1"
VERIFICADOR_TIMEOUT_S  = float(os.getenv("VERIFICADOR_TIMEOUT_S", "2.5"))

# Guardrail de validación de salida (Self-RAG ligero): tras generar la respuesta,
# verifica que los artículos citados existan en el contexto recuperado. Si detecta
# una cita fabricada (número de artículo que no estaba en el contexto), regenera
# una vez con la lista de artículos permitidos. Detectable + verificable contra la
# fuente — no elimina alucinaciones, las atrapa cuando ocurren.
GUARDRAIL_CITAS_HABILITADO = os.getenv("GUARDRAIL_CITAS_HABILITADO", "1") == "1"

# ─── NIVELES DE PLAN ─────────────────────────────────────────────────────────
# 0 = Gratis, 1 = Tester/Pionero, 2 = Premium

PLAN_GRATIS  = 0
PLAN_TESTER  = 1
PLAN_PREMIUM = 2

PLANES = {
    PLAN_GRATIS:  {"nombre": "Gratis",     "icono": "\U0001f193", "consultas": 5,  "memoria": False, "docs_mes": 0},
    PLAN_TESTER:  {"nombre": "Pionero",    "icono": "\u2b50",     "consultas": 5,  "memoria": True,  "docs_mes": 2},
    PLAN_PREMIUM: {"nombre": "Premium",    "icono": "\U0001f48e", "consultas": -1, "memoria": True,  "docs_mes": -1},
}

DOCS_HABILITADOS = True

MAX_HISTORIAL = 10

# Memoria corta para usuarios SIN plan de memoria (gratis): guarda/usa los
# últimos N mensajes (≈2-3 turnos) para que los seguimientos inmediatos ("¿y si
# insiste?", "pero aquí no nos dan el contrato") no se rompan. La memoria LARGA
# (MAX_HISTORIAL) y la persistencia de contexto siguen siendo premium.
MAX_HISTORIAL_GRATIS = int(os.getenv("MAX_HISTORIAL_GRATIS", "4"))

# Longitud máxima de una consulta (caracteres). Una pregunta legal real cabe
# de sobra; el tope evita que peguen leyes/textos completos —que Telegram parte
# en varios mensajes y disparan varias consultas RAG fragmentadas, quemando el
# rate limit del LLM—. El pipeline internamente ya trunca a 500 para la búsqueda.
MAX_CONSULTA_CHARS = int(os.getenv("MAX_CONSULTA_CHARS", "1000"))

# ─── ANTI-FLOOD (límite de ráfaga) ───────────────────────────────────────────
# Independiente de la cuota diaria del plan: limita cuántas consultas RAG puede
# disparar un mismo usuario en una ventana corta, para frenar abuso/scripts/DoS
# (cada consulta cuesta llamadas a Groq + HuggingFace). Un humano con preguntas
# legítimas no lo alcanza; un bucle automatizado sí. En memoria (se reinicia con
# el proceso); los admins están exentos.
RATE_LIMIT_MAX_CONSULTAS = int(os.getenv("RATE_LIMIT_MAX_CONSULTAS", "5"))
RATE_LIMIT_VENTANA_SEG = int(os.getenv("RATE_LIMIT_VENTANA_SEG", "20"))

# ─── AUTO TESTERS ─────────────────────────────────────────────────────────────
MAX_AUTO_TESTERS = 50  # primeros N usuarios reciben 14 días de Pionero gratis

# ─── BOT ─────────────────────────────────────────────────────────────────────
BOT_USERNAME = os.getenv("BOT_USERNAME", "abotgadoBOT")

# ─── DEV MODE ─────────────────────────────────────────────────────────────────
# Con DEV_MODE=1 se salta la validación HMAC de initData (desarrollo local)
DEV_MODE = os.getenv("DEV_MODE", "0") == "1"

# ─── ABOGADOS VERIFICADOS ────────────────────────────────────────────────────

ESPECIALIDADES_ABOGADO = [
    "Penal", "Civil", "Laboral", "Mercantil", "Familia", "Tránsito",
    "Administrativo", "Tributario", "Inmobiliario", "Migratorio",
    "Electoral", "Ambiental", "Otro",
]

METODOS_PAGO_VALIDOS = [
    "pago_movil", "zinli", "binance", "paypal", "wally", "zelle", "efectivo",
]

ESTADOS_VENEZUELA = [
    "Amazonas", "Anzoátegui", "Apure", "Aragua", "Barinas", "Bolívar",
    "Carabobo", "Cojedes", "Delta Amacuro", "Distrito Capital", "Falcón",
    "Guárico", "Lara", "Mérida", "Miranda", "Monagas", "Nueva Esparta",
    "Portuguesa", "Sucre", "Táchira", "Trujillo", "Vargas", "Yaracuy", "Zulia",
]
