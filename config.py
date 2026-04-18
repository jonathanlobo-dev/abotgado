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

# Verificador de relevancia post-retrieval: filtra artículos tangenciales antes
# de pasarlos al LLM principal. Si False, se omite (útil para tests/debug).
VERIFICADOR_HABILITADO = os.getenv("VERIFICADOR_HABILITADO", "1") == "1"
VERIFICADOR_TIMEOUT_S  = float(os.getenv("VERIFICADOR_TIMEOUT_S", "2.5"))

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
