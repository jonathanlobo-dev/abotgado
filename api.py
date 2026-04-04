"""
aBOTgado - API REST para Telegram Mini App
==========================================
Corre como proceso 'web' en Railway (independiente del bot Telegram).
El bot Telegram sigue corriendo como proceso 'worker' sin cambios.

Endpoints:
  POST /consultar  → pregunta legal, devuelve respuesta HTML
  GET  /health     → health check
"""

import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [API] %(message)s")
logger = logging.getLogger(__name__)

# ─── App ────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="aBOTgado API",
    description="API REST para el asistente jurídico venezolano aBOTgado",
    version="1.0.0",
)

# CORS: permitir que la TMA (cualquier origen por ahora) llame a la API.
# En producción, reemplazar ["*"] con el dominio real de la TMA.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ─── Modelos ─────────────────────────────────────────────────────────────────

class MensajeHistorial(BaseModel):
    rol: str       # "usuario" o "bot"
    texto: str

class ConsultaRequest(BaseModel):
    pregunta: str
    user_id: str = "tma_anonimo"
    historial: list[MensajeHistorial] = []

    @field_validator("pregunta")
    @classmethod
    def pregunta_no_vacia(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("La pregunta no puede estar vacía")
        if len(v) > 2000:
            raise ValueError("La pregunta no puede superar los 2000 caracteres")
        return v

class ConsultaResponse(BaseModel):
    respuesta: str
    temas: list[str]
    confianza: str

# ─── Importar motor de búsqueda (lazy, para no bloquear el arranque) ─────────
_busqueda = None

def get_busqueda():
    global _busqueda
    if _busqueda is None:
        logger.info("Cargando motor de búsqueda...")
        import busqueda
        _busqueda = busqueda
        logger.info("Motor de búsqueda listo.")
    return _busqueda

# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Verifica que la API esté corriendo."""
    return {"status": "ok", "servicio": "aBOTgado API"}


@app.post("/consultar", response_model=ConsultaResponse)
def consultar(req: ConsultaRequest):
    """
    Recibe una pregunta legal y devuelve la respuesta del motor RAG.

    El campo `respuesta` viene en HTML (mismo formato que el bot Telegram).
    La TMA puede renderizarlo directamente en un div con innerHTML.
    """
    try:
        motor = get_busqueda()

        # Convertir historial al formato que espera buscar_y_responder
        historial_fmt = [
            {"role": "user" if m.rol == "usuario" else "assistant", "content": m.texto}
            for m in req.historial
        ]

        resultado = motor.buscar_y_responder(
            pregunta=req.pregunta,
            historial=historial_fmt if historial_fmt else None,
            user_id=None,   # TMA no tiene user_id de Telegram
        )

        # buscar_y_responder devuelve dict con respuesta/temas/confianza
        if isinstance(resultado, dict):
            return ConsultaResponse(
                respuesta=resultado.get("respuesta", ""),
                temas=resultado.get("temas", []),
                confianza=str(resultado.get("confianza", "n/a")),
            )

        # Fallback: si devuelve string directamente
        return ConsultaResponse(respuesta=str(resultado), temas=[], confianza="n/a")

    except Exception as e:
        logger.error(f"Error en /consultar: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error interno procesando la consulta. Intenta de nuevo."
        )
