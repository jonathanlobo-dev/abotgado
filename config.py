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

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
HF_EMBED_URL    = f"https://router.huggingface.co/hf-inference/models/{EMBEDDING_MODEL}/pipeline/feature-extraction"
LLM_MODEL       = "llama-3.3-70b-versatile"

# ─── NIVELES DE PLAN ─────────────────────────────────────────────────────────
# 0 = Gratis, 1 = Tester/Pionero, 2 = Premium

PLAN_GRATIS  = 0
PLAN_TESTER  = 1
PLAN_PREMIUM = 2

PLANES = {
    PLAN_GRATIS:  {"nombre": "Gratis",     "icono": "\U0001f193", "consultas": 3,  "memoria": False, "docs_mes": 0},
    PLAN_TESTER:  {"nombre": "Pionero",    "icono": "\u2b50",     "consultas": 5,  "memoria": True,  "docs_mes": 1},
    PLAN_PREMIUM: {"nombre": "Premium",    "icono": "\U0001f48e", "consultas": -1, "memoria": True,  "docs_mes": -1},
}

MAX_HISTORIAL = 10
