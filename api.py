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
    conv_id: int | None = None   # ID de conversación del sidebar (opcional)

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

class ConversacionRequest(BaseModel):
    user_id: str
    titulo: str = "Nueva consulta"

class RenombrarRequest(BaseModel):
    user_id: str
    titulo: str

class EliminarRequest(BaseModel):
    user_id: str

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

NO_ADMIN_HTML = """⛔ <b>Acceso denegado</b>

Este comando es exclusivo de administradores."""

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

    # ── Comandos de administrador ──────────────────────────────────
    CMDS_ADMIN = {"/usuarios", "/stats_admin", "/ping", "/feedback",
                  "/premium_on", "/premium_off", "/plan_add", "/plan_del",
                  "/tester", "/anuncio", "/backup", "/debug",
                  "/regalar_doc", "/regalar_memoria", "/regalar_consultas",
                  "/add_abogado", "/abogados", "/del_abogado", "/activar_abogado"}
    if cmd in CMDS_ADMIN:
        return _manejar_admin(cmd, partes, user_id_raw)

    # Comando desconocido → dejar que el RAG lo intente
    return None


def _es_admin(user_id_raw: str) -> bool:
    try:
        import config
        return int(user_id_raw) in config.ADMIN_IDS
    except Exception:
        return False


def _manejar_admin(cmd: str, partes: list, user_id_raw: str) -> ConsultaResponse:
    """Maneja comandos de administrador en la TMA."""
    if not _es_admin(user_id_raw):
        return ConsultaResponse(respuesta=NO_ADMIN_HTML, temas=[], confianza="n/a")

    try:
        import db as database
        import config as cfg

        if cmd == "/ping":
            motor = get_busqueda()
            total = motor.coleccion.count()
            return ConsultaResponse(
                respuesta=f"🏓 <b>Pong</b>\n\nAPI respondiendo. Artículos en DB: <b>{total}</b>",
                temas=[], confianza="n/a"
            )

        if cmd == "/usuarios":
            usuarios = database.listar_usuarios()
            if not usuarios:
                return ConsultaResponse(respuesta="No hay usuarios registrados.", temas=[], confianza="n/a")
            texto = f"👥 <b>{len(usuarios)} usuarios registrados</b>\n\n"
            for u in usuarios[:30]:
                plan_info = cfg.PLANES.get(u["plan_id"], cfg.PLANES[0])
                extras = ""
                if u.get("bono_memoria"):
                    extras += " [MEM]"
                if u.get("docs_disponibles", 0) > 0:
                    extras += f" [DOC:{u['docs_disponibles']}]"
                texto += (
                    f"{plan_info['icono']} <b>{u['nombre']}</b> (@{u['username']}) "
                    f"— <code>{u['user_id']}</code>"
                    f" — hoy: {u['consultas_hoy']}{extras}\n"
                )
            if len(usuarios) > 30:
                texto += f"\n<i>…y {len(usuarios) - 30} más</i>"
            return ConsultaResponse(respuesta=texto, temas=[], confianza="n/a")

        if cmd == "/stats_admin":
            su = database.stats_usuarios()
            sc = database.obtener_stats()
            texto = (
                f"📊 <b>Estadísticas aBOTgado</b>\n\n"
                f"👥 Usuarios: <b>{su['total']}</b>\n"
                f"  🆓 Gratis: {su['gratis']}\n"
                f"  ⭐ Pionero: {su.get('pionero', 0)}\n"
                f"  💎 Premium: {su['premium']}\n"
                f"  🟢 Activos hoy: {su['activos_hoy']}\n\n"
                f"📈 <b>Consultas:</b>\n"
                f"  Hoy: {sc['consultas_hoy']}\n"
                f"  Últimos 7 días: {sc['consultas_7d']}\n"
                f"  Total: {sc['consultas_total']}\n"
            )
            if sc.get("temas_top"):
                texto += "\n🔥 <b>Temas más consultados:</b>\n"
                for i, (tema, count) in enumerate(sc["temas_top"][:5], 1):
                    texto += f"  {i}. {tema} ({count})\n"
            return ConsultaResponse(respuesta=texto, temas=[], confianza="n/a")

        if cmd == "/abogados":
            abogados = database.listar_abogados()
            if not abogados:
                return ConsultaResponse(respuesta="No hay abogados registrados.", temas=[], confianza="n/a")
            texto = f"⚖️ <b>{len(abogados)} abogados registrados</b>\n\n"
            for a in abogados:
                activo = "✅" if a.get("activo") else "❌"
                texto += f"{activo} <b>{a['nombre']}</b> — {a['especialidad']} — {a['estado']}\n"
            return ConsultaResponse(respuesta=texto, temas=[], confianza="n/a")

        # Comandos complejos (requieren argumentos o flujo multi-paso) → redirigir
        return ConsultaResponse(
            respuesta=(
                f"⚠️ <b>Comando disponible en Telegram</b>\n\n"
                f"<code>{' '.join(partes)}</code> requiere argumentos o un flujo "
                f"interactivo. Úsalo en el bot de Telegram donde tienes acceso completo."
            ),
            temas=[], confianza="n/a"
        )

    except Exception as e:
        logger.error(f"Error en comando admin {cmd}: {e}", exc_info=True)
        return ConsultaResponse(
            respuesta=f"❌ Error ejecutando <code>{cmd}</code>: {e}",
            temas=[], confianza="n/a"
        )

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
        import db as database
        motor = get_busqueda()

        historial_fmt = [
            {"role": "user" if m.rol == "usuario" else "assistant", "content": m.texto}
            for m in req.historial
        ]

        # Convertir user_id a int si es posible (para que el bot lo reconozca)
        try:
            uid_int = int(req.user_id)
        except (ValueError, TypeError):
            uid_int = None

        resultado = motor.buscar_y_responder(
            pregunta=req.pregunta,
            historial=historial_fmt if historial_fmt else None,
            user_id=uid_int,
        )

        if isinstance(resultado, dict):
            resp_html  = resultado.get("respuesta", "")
            temas      = resultado.get("temas", [])
            confianza  = str(resultado.get("confianza", "n/a"))
        else:
            resp_html  = str(resultado)
            temas      = []
            confianza  = "n/a"

        # ── Auto-guardar en conversación TMA si se indicó conv_id ──
        if req.conv_id and req.user_id != "tma_anonimo":
            try:
                database.tma_guardar_mensaje(req.conv_id, "usuario", req.pregunta)
                database.tma_guardar_mensaje(req.conv_id, "bot", resp_html, temas)
                # Generar título automático del primer mensaje
                database.tma_actualizar_titulo_auto(req.conv_id, req.pregunta)
            except Exception as e_db:
                logger.warning(f"No se pudo guardar en TMA DB: {e_db}")

        return ConsultaResponse(respuesta=resp_html, temas=temas, confianza=confianza)

    except Exception as e:
        logger.error(f"Error en /consultar: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error interno procesando la consulta. Intenta de nuevo."
        )


# ─── Endpoints de conversaciones TMA ────────────────────────────────────────

@app.get("/conversaciones/{user_id}")
def listar_conversaciones(user_id: str):
    """Lista las conversaciones del sidebar para un usuario."""
    if user_id == "tma_anonimo":
        return []
    try:
        import db as database
        return database.tma_listar_conversaciones(user_id)
    except Exception as e:
        logger.error(f"Error listando conversaciones: {e}")
        raise HTTPException(status_code=500, detail="Error obteniendo conversaciones")


@app.post("/conversaciones")
def crear_conversacion(req: ConversacionRequest):
    """Crea una nueva conversación en el sidebar."""
    if req.user_id == "tma_anonimo":
        raise HTTPException(status_code=400, detail="Se requiere user_id de Telegram")
    try:
        import db as database
        conv_id = database.tma_nueva_conversacion(req.user_id, req.titulo)
        return {"id": conv_id, "titulo": req.titulo}
    except Exception as e:
        logger.error(f"Error creando conversación: {e}")
        raise HTTPException(status_code=500, detail="Error creando conversación")


@app.get("/conversaciones/{user_id}/{conv_id}")
def obtener_mensajes(user_id: str, conv_id: int):
    """Retorna los mensajes de una conversación."""
    try:
        import db as database
        return database.tma_obtener_mensajes(conv_id, user_id)
    except Exception as e:
        logger.error(f"Error obteniendo mensajes: {e}")
        raise HTTPException(status_code=500, detail="Error obteniendo mensajes")


@app.put("/conversaciones/{conv_id}")
def renombrar_conversacion(conv_id: int, req: RenombrarRequest):
    """Renombra una conversación."""
    try:
        import db as database
        database.tma_renombrar_conversacion(conv_id, req.user_id, req.titulo)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error renombrando: {e}")
        raise HTTPException(status_code=500, detail="Error renombrando conversación")


@app.delete("/conversaciones/vacias/{user_id}")
def limpiar_vacias(user_id: str):
    """Elimina conversaciones sin mensajes (acumuladas por bug anterior)."""
    try:
        import db as database
        with database.get_db() as con:
            con.execute("""
                DELETE FROM tma_conversaciones
                WHERE user_id = ?
                AND id NOT IN (SELECT DISTINCT conv_id FROM tma_mensajes)
            """, (user_id,))
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error limpiando vacías: {e}")
        raise HTTPException(status_code=500, detail="Error")


@app.delete("/conversaciones/{conv_id}")
def eliminar_conversacion(conv_id: int, req: EliminarRequest):
    """Elimina una conversación y todos sus mensajes."""
    try:
        import db as database
        database.tma_eliminar_conversacion(conv_id, req.user_id)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error eliminando: {e}")
        raise HTTPException(status_code=500, detail="Error eliminando conversación")


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
