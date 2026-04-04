"""
aBOTgado - API REST para Telegram Mini App
==========================================
Corre como proceso 'web' en Railway (independiente del bot Telegram).
El bot Telegram sigue corriendo como proceso 'worker' sin cambios.

Endpoints:
  POST /consultar  → pregunta legal o comando (/leyes, /ayuda…), devuelve respuesta HTML
  POST /feedback   → calificación de una respuesta (👍👎)
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ─── Modelos ─────────────────────────────────────────────────────────────────

class MensajeHistorial(BaseModel):
    rol: str
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

class FeedbackRequest(BaseModel):
    msg_id: str
    valor: int   # 1 = 👍, -1 = 👎

# ─── Motor de búsqueda (lazy) ─────────────────────────────────────────────────
_busqueda = None

def get_busqueda():
    global _busqueda
    if _busqueda is None:
        logger.info("Cargando motor de búsqueda...")
        import busqueda
        _busqueda = busqueda
        logger.info("Motor de búsqueda listo.")
    return _busqueda

# ─── Textos de comandos TMA ───────────────────────────────────────────────────

AYUDA_HTML = """📌 <b>Comandos disponibles en aBOTgado</b>

<b>✅ Plan Gratis</b>
• <code>/leyes</code> — Ver las leyes disponibles en el sistema
• <code>/ayuda</code> — Mostrar esta ayuda
• <code>/estado</code> — Ver tu plan y consultas restantes
• <code>/referir</code> — Obtener tu enlace de referido
• <code>/soporte</code> — Contactar al equipo de soporte
• <code>/nuevo</code> — Limpiar el chat y empezar de cero

<b>⭐ Plan Pionero</b>
• <code>/ley [ley] [número]</code> — Buscar artículo específico
• <code>/comparar</code> — Comparar dos leyes o artículos
• <code>/guardar</code> — Guardar la última respuesta
• <code>/mis_consultas</code> — Ver consultas guardadas
• <code>/stats</code> — Ver tus estadísticas de uso

<b>💎 Plan Premium</b>
• <code>/documento</code> — Generar un documento legal en PDF

<i>⚠️ Los comandos de plan Pionero y Premium requieren cuenta activa en el bot de Telegram (@aBOTgadoVE).</i>"""

SOPORTE_HTML = """📌 <b>Soporte aBOTgado</b>

Para recibir ayuda del equipo, tienes estas opciones:

💬 <b>Por Telegram:</b> Abre el bot y usa el comando <code>/soporte</code> para enviarnos un mensaje directamente.

⚠️ <i>aBOTgado es un asistente informativo. Para casos legales urgentes, consulta siempre un abogado colegiado.</i>"""

PLAN_TELEGRAM_HTML = """⚠️ <b>Comando de plan superior</b>

Este comando requiere verificar tu cuenta y plan en el bot de Telegram.

Abre <b>@aBOTgadoVE</b> en Telegram y úsalo ahí donde el bot puede identificarte y confirmar tu plan activo."""

# ─── Manejador de comandos ────────────────────────────────────────────────────

def _manejar_comando(cmd_raw: str) -> ConsultaResponse | None:
    """
    Si el texto es un comando (/leyes, /ayuda…), devuelve la respuesta directamente
    sin pasar por el RAG. Retorna None si no es un comando conocido.
    """
    partes = cmd_raw.strip().split()
    cmd = partes[0].lower()

    if cmd == "/ayuda":
        return ConsultaResponse(respuesta=AYUDA_HTML, temas=[], confianza="n/a")

    if cmd == "/soporte":
        return ConsultaResponse(respuesta=SOPORTE_HTML, temas=[], confianza="n/a")

    if cmd == "/leyes":
        try:
            motor = get_busqueda()
            texto_leyes = motor.generar_texto_leyes()
            html = f"📌 <b>Leyes disponibles en aBOTgado</b>\n\n{texto_leyes}"
            return ConsultaResponse(respuesta=html, temas=[], confianza="n/a")
        except Exception as e:
            logger.warning(f"Error generando lista de leyes: {e}")
            return ConsultaResponse(
                respuesta="⚠️ No se pudo obtener la lista de leyes en este momento.",
                temas=[], confianza="n/a"
            )

    if cmd in ("/estado", "/referir", "/guardar", "/mis_consultas",
               "/ver_guardado", "/borrar_guardados", "/stats",
               "/comparar", "/ley", "/documento"):
        return ConsultaResponse(respuesta=PLAN_TELEGRAM_HTML, temas=[], confianza="n/a")

    # Comando desconocido → dejar que el RAG lo intente
    return None

# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "servicio": "aBOTgado API"}


@app.post("/consultar", response_model=ConsultaResponse)
def consultar(req: ConsultaRequest):
    """
    Recibe una pregunta legal (o comando) y devuelve la respuesta del motor RAG.
    Los comandos (/leyes, /ayuda, etc.) se manejan directamente sin pasar por el RAG.
    El campo `respuesta` viene en HTML; la TMA lo renderiza con innerHTML.
    """
    # ── Detectar comandos ──────────────────────────────────────────
    if req.pregunta.startswith("/"):
        resultado_cmd = _manejar_comando(req.pregunta)
        if resultado_cmd is not None:
            return resultado_cmd

    # ── RAG normal ─────────────────────────────────────────────────
    try:
        motor = get_busqueda()

        historial_fmt = [
            {"role": "user" if m.rol == "usuario" else "assistant", "content": m.texto}
            for m in req.historial
        ]

        resultado = motor.buscar_y_responder(
            pregunta=req.pregunta,
            historial=historial_fmt if historial_fmt else None,
            user_id=None,
        )

        if isinstance(resultado, dict):
            return ConsultaResponse(
                respuesta=resultado.get("respuesta", ""),
                temas=resultado.get("temas", []),
                confianza=str(resultado.get("confianza", "n/a")),
            )

        return ConsultaResponse(respuesta=str(resultado), temas=[], confianza="n/a")

    except Exception as e:
        logger.error(f"Error en /consultar: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error interno procesando la consulta. Intenta de nuevo."
        )


@app.post("/feedback")
def feedback(req: FeedbackRequest):
    """Registra la calificación del usuario (👍 = 1, 👎 = -1)."""
    try:
        logger.info(f"Feedback: msg_id={req.msg_id} valor={req.valor}")
        # TODO: persistir en DB cuando se integre user_id de Telegram
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error en /feedback: {e}")
        raise HTTPException(status_code=500, detail="Error registrando feedback")
