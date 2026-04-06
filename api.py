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
import time
import json
import hmac
import hashlib
import logging
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

import config

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
    allow_methods=["GET", "POST", "PUT", "DELETE"],
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
    valor: int        # 1 = 👍, -1 = 👎
    user_id: str = "tma_anonimo"
    pregunta: str = ""
    respuesta: str = ""
    motivo: str = ""       # opcional — por qué fue mala (solo 👎)
    init_data: str = ""    # firmado por Telegram — valida user_id real


class ResolverRequest(BaseModel):
    init_data: str = ""
    notificar: bool = True

class ConversacionRequest(BaseModel):
    user_id: str
    titulo: str = "Nueva consulta"

class RenombrarRequest(BaseModel):
    user_id: str
    titulo: str


# ─── Startup: asegurar que el DB esté inicializado ───────────────────────────
@app.on_event("startup")
def _startup():
    """
    Garantiza que las tablas (incluyendo tma_conversaciones/tma_mensajes)
    existen antes de que llegue la primera petición.
    El bot también llama a inicializar_db() al arrancar, pero la API
    puede recibir peticiones antes que el bot termine de cargar.
    """
    try:
        import db as database
        database.inicializar_db()
        logger.info("DB inicializada correctamente.")
    except Exception as e:
        logger.error(f"Error inicializando DB en startup: {e}")


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

AYUDA_ADMIN_HTML = """

👑 <b>Comandos de Administrador</b>
• <code>/ping</code> — Estado del servidor y artículos en DB
• <code>/usuarios</code> — Listar usuarios registrados (últimos 30)
• <code>/stats_admin</code> — Estadísticas generales del bot
• <code>/abogados</code> — Directorio de abogados registrados

<i>Comandos avanzados (requieren argumentos, disponibles en el bot de Telegram):</i>
<code>/premium_on</code> · <code>/premium_off</code> · <code>/plan_add</code> · <code>/anuncio</code>
<code>/add_abogado</code> · <code>/del_abogado</code> · <code>/activar_abogado</code> · <code>/backup</code>"""

NO_ADMIN_HTML = """⛔ <b>Acceso denegado</b>

Este comando es exclusivo de administradores."""

# ─── Manejador de comandos ────────────────────────────────────────────────────

def _manejar_comando(cmd_raw: str, user_id_raw: str = "tma_anonimo") -> ConsultaResponse | None:
    """
    Si el texto es un comando (/leyes, /ayuda…), devuelve la respuesta directamente
    sin pasar por el RAG. Retorna None si no es un comando conocido.
    """
    partes = cmd_raw.strip().split()
    cmd = partes[0].lower()

    if cmd == "/ayuda":
        texto = AYUDA_HTML
        if _es_admin(user_id_raw):
            texto += AYUDA_ADMIN_HTML
        return ConsultaResponse(respuesta=texto, temas=[], confianza="n/a")

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

    # ── Comandos de usuario que sí podemos implementar en TMA ────────
    if cmd == "/estado":
        return _cmd_estado(user_id_raw)

    if cmd == "/stats":
        return _cmd_stats_usuario(user_id_raw)

    if cmd == "/referir":
        return _cmd_referir(user_id_raw)

    if cmd in ("/guardar", "/mis_consultas", "/ver_guardado",
               "/borrar_guardados", "/comparar", "/ley", "/documento"):
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


def _cmd_estado(user_id_raw: str) -> ConsultaResponse:
    """Muestra plan, consultas usadas/disponibles y estado de memoria."""
    try:
        uid = int(user_id_raw)
    except (ValueError, TypeError):
        return ConsultaResponse(
            respuesta="⚠️ Abre la app desde Telegram para ver tu estado.",
            temas=[], confianza="n/a"
        )
    try:
        import db as database
        import config as cfg

        plan_id   = database.obtener_plan(uid)
        plan      = cfg.PLANES.get(plan_id, cfg.PLANES[0])
        usadas    = database.consultas_hoy(uid)
        limite    = plan["consultas"]
        restantes = database.consultas_restantes(uid)
        memoria   = plan["memoria"] or bool(database.info_plan(uid) if hasattr(database, 'info_plan') else False)

        # Barra de progreso visual
        if limite == -1:
            barra = "∞ ilimitadas"
            pct_txt = ""
        else:
            pct = min(int((usadas / limite) * 10), 10) if limite > 0 else 0
            barra = "🟦" * pct + "⬜" * (10 - pct)
            pct_txt = f" ({usadas}/{limite})"

        # Info de memoria
        try:
            u_info = database.resolver_usuario(uid)
            tiene_memoria = plan["memoria"] or u_info.get("bono_memoria", 0)
        except Exception:
            tiene_memoria = plan["memoria"]

        texto = (
            f"📍 <b>Tu estado en aBOTgado</b>\n\n"
            f"{plan['icono']} <b>Plan:</b> {plan['nombre']}\n\n"
            f"📊 <b>Consultas hoy:</b>\n"
            f"{barra}{pct_txt}\n"
        )
        if limite == -1:
            texto += "✅ Consultas ilimitadas\n"
        else:
            texto += f"Usadas: <b>{usadas}</b> · Restantes: <b>{restantes}</b>\n"

        texto += f"\n🧠 <b>Memoria:</b> {'✅ Activa' if tiene_memoria else '❌ No disponible en tu plan'}\n"

        if plan_id == cfg.PLAN_GRATIS:
            texto += "\n💡 <i>Actualiza a Pionero para más consultas y memoria.</i>"

        return ConsultaResponse(respuesta=texto, temas=[], confianza="n/a")

    except Exception as e:
        logger.error(f"Error en /estado: {e}", exc_info=True)
        return ConsultaResponse(
            respuesta="❌ Error obteniendo tu estado. Intenta de nuevo.",
            temas=[], confianza="n/a"
        )


def _cmd_stats_usuario(user_id_raw: str) -> ConsultaResponse:
    """Muestra estadísticas personales del usuario."""
    try:
        uid = int(user_id_raw)
    except (ValueError, TypeError):
        return ConsultaResponse(
            respuesta="⚠️ Abre la app desde Telegram para ver tus estadísticas.",
            temas=[], confianza="n/a"
        )
    try:
        import db as database
        s = database.stats_usuario(uid)
        texto = (
            f"📈 <b>Tus estadísticas</b>\n\n"
            f"💬 Consultas hoy: <b>{s['consultas_hoy']}</b>\n"
            f"📚 Consultas totales: <b>{s['consultas_total']}</b>\n"
            f"⭐ Respuestas guardadas: <b>{s.get('favoritos', 0)}</b>\n"
        )
        return ConsultaResponse(respuesta=texto, temas=[], confianza="n/a")
    except Exception as e:
        logger.error(f"Error en /stats usuario: {e}", exc_info=True)
        return ConsultaResponse(
            respuesta="❌ Error obteniendo estadísticas.",
            temas=[], confianza="n/a"
        )


def _cmd_referir(user_id_raw: str) -> ConsultaResponse:
    """Muestra el enlace de referido del usuario."""
    try:
        uid = int(user_id_raw)
    except (ValueError, TypeError):
        return ConsultaResponse(
            respuesta="⚠️ Abre la app desde Telegram para obtener tu enlace de referido.",
            temas=[], confianza="n/a"
        )
    try:
        import db as database
        count = database.obtener_referidos_count(uid)
        enlace = f"https://t.me/aBOTgadoVEBot?start=ref_{uid}"
        texto = (
            f"🔗 <b>Tu enlace de referido</b>\n\n"
            f"<code>{enlace}</code>\n\n"
            f"👥 Personas referidas: <b>{count}</b>\n\n"
            f"<i>Comparte este enlace. Cuando alguien se registre con él, "
            f"ambos obtienen beneficios.</i>"
        )
        return ConsultaResponse(respuesta=texto, temas=[], confianza="n/a")
    except Exception as e:
        logger.error(f"Error en /referir: {e}", exc_info=True)
        return ConsultaResponse(
            respuesta="❌ Error obteniendo enlace de referido.",
            temas=[], confianza="n/a"
        )


def _es_admin(user_id_raw: str) -> bool:
    try:
        return int(user_id_raw) in config.ADMIN_IDS
    except Exception:
        return False


def _validar_init_data(init_data: str, max_age_seconds: int = 604800) -> dict | None:
    """Valida el initData firmado de Telegram WebApp.

    Spec: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    Retorna el dict del user si la firma es válida y no está vencida; None si no.
    """
    if not init_data:
        return None
    token = getattr(config, "TELEGRAM_TOKEN", "") or ""
    if not token:
        return None
    try:
        # strict_parsing=False: tolera formatos no estándar que Telegram puede enviar
        parsed = dict(parse_qsl(init_data, strict_parsing=False, keep_blank_values=True))
        recv_hash = parsed.pop("hash", None)
        if not recv_hash:
            logger.debug("initData: no contiene campo 'hash'")
            return None
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        calc_hash = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc_hash, recv_hash):
            logger.debug("initData: HMAC no coincide")
            return None
        # Rechazar si auth_date tiene más de 7 días (era 24h, ampliado para sesiones largas)
        try:
            auth_date = int(parsed.get("auth_date", 0))
        except ValueError:
            return None
        if auth_date <= 0 or auth_date < time.time() - max_age_seconds:
            logger.debug(f"initData: auth_date vencida ({auth_date})")
            return None
        user_json = parsed.get("user", "")
        if not user_json:
            return None
        return json.loads(user_json)
    except Exception as e:
        logger.debug(f"initData inválido: {e}")
        return None


def _user_id_from_init_data(init_data: str) -> int | None:
    """Extrae el user_id del initData validado. None si la firma falla."""
    user = _validar_init_data(init_data)
    if user and isinstance(user.get("id"), int):
        return user["id"]
    return None


def _admin_from_init_data(init_data: str) -> int | None:
    """Devuelve el user_id si es admin válido (initData firmado), None si no.

    En DEV_MODE permite saltear la validación HMAC (útil para browser desktop).
    """
    uid = _user_id_from_init_data(init_data)
    if uid is not None and uid in config.ADMIN_IDS:
        return uid
    # Escape de desarrollo local: DEV_MODE=1 usa el primer ADMIN_ID
    if os.getenv("DEV_MODE", "").lower() in ("1", "true", "si"):
        return config.ADMIN_IDS[0] if config.ADMIN_IDS else None
    return None


def _enviar_mensaje_telegram(chat_id: int, texto: str) -> bool:
    """Envía un mensaje por la HTTP API de Telegram (no depende del Application del bot)."""
    token = getattr(config, "TELEGRAM_TOKEN", "") or ""
    if not token or not chat_id:
        return False
    try:
        import httpx
        r = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": texto},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"No se pudo notificar al usuario {chat_id}: {e}")
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

@app.get("/perfil/{user_id}")
def perfil_usuario(user_id: str):
    """
    Devuelve información de perfil del usuario para mostrar en el sidebar de la TMA:
    plan, consultas hoy / límite / restantes, y si tiene memoria activa.
    """
    if user_id == "tma_anonimo":
        return {"plan_id": None, "plan_nombre": None, "plan_icono": "👤",
                "consultas_hoy": 0, "consultas_limite": 0, "consultas_restantes": 0,
                "memoria": False}
    try:
        uid = int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="user_id inválido")

    try:
        import db as database
        import config as cfg

        plan_id   = database.obtener_plan(uid)
        plan      = cfg.PLANES.get(plan_id, cfg.PLANES[0])
        usadas    = database.consultas_hoy(uid)
        limite    = plan["consultas"]
        restantes = database.consultas_restantes(uid)

        try:
            u_info      = database.resolver_usuario(uid)
            tiene_mem   = bool(plan["memoria"] or u_info.get("bono_memoria", 0))
        except Exception:
            tiene_mem = plan["memoria"]

        return {
            "plan_id":             plan_id,
            "plan_nombre":         plan["nombre"],
            "plan_icono":          plan["icono"],
            "consultas_hoy":       usadas,
            "consultas_limite":    limite,   # -1 = ilimitadas
            "consultas_restantes": restantes,
            "memoria":             tiene_mem,
        }
    except Exception as e:
        logger.error(f"Error en /perfil: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error obteniendo perfil")


@app.get("/health")
def health():
    return {"status": "ok", "servicio": "aBOTgado API"}


@app.get("/directorio")
def directorio_abogados(especialidad: str = None, estado: str = None):
    """
    Lista pública de abogados verificados del directorio.
    Acepta filtros opcionales: ?especialidad=laboral&estado=miranda
    """
    try:
        import db as database
        abogados = database.listar_abogados(
            especialidad=especialidad,
            estado=estado,
            solo_activos=True
        )
        # Excluir cédula de la respuesta pública
        return [
            {
                "id":            a["id"],
                "nombre":        a["nombre"],
                "inpreabogado":  a["inpreabogado"],
                "especialidad":  a["especialidad"],
                "telefono":      a["telefono"],
                "estado":        a["estado"],
                "notas":         a.get("notas", ""),
            }
            for a in abogados
        ]
    except Exception as e:
        logger.error(f"Error en /directorio: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error obteniendo directorio")


@app.get("/stats/usuario/{user_id}")
def stats_usuario_endpoint(user_id: str):
    """Estadísticas personales para el dashboard de la TMA."""
    if user_id == "tma_anonimo":
        raise HTTPException(status_code=401, detail="No autenticado")
    try:
        uid = int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="user_id inválido")
    try:
        import db as database
        s = database.stats_usuario(uid)
        return {
            "consultas_total": s["consultas_total"],
            "consultas_hoy":   s["consultas_hoy"],
            "favoritos":       s["favoritos"],
        }
    except Exception as e:
        logger.error(f"Error en /stats/usuario: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error")


@app.get("/stats/admin")
def stats_admin_endpoint(user_id: str = "", init_data: str = ""):
    """Estadísticas globales — solo para administradores.

    Prefiere validación por initData firmado. Acepta user_id legacy solo si
    coincide con ADMIN_IDS Y DEV_MODE=1 (para desarrollo local).
    """
    admin_id = _admin_from_init_data(init_data)
    if not admin_id:
        # Fallback legacy: solo en DEV_MODE
        if not (os.getenv("DEV_MODE", "").lower() in ("1", "true", "si")
                and _es_admin(user_id)):
            raise HTTPException(status_code=403, detail="No autorizado")
    try:
        import db as database
        import config as cfg
        import embeddings as emb_module
        s = database.stats_globales()
        por_plan = {}
        for plan_id, count in s["por_plan"].items():
            plan_info = cfg.PLANES.get(plan_id, {"nombre": f"Plan {plan_id}", "icono": ""})
            por_plan[plan_info["nombre"]] = count
        return {
            "total_usuarios":   s["total_usuarios"],
            "consultas_hoy":    s["consultas_hoy"],
            "consultas_semana": s["consultas_semana"],
            "consultas_mes":    s["consultas_mes"],
            "por_plan":         por_plan,
            "embed_cache":      emb_module.cache_info(),
        }
    except Exception as e:
        logger.error(f"Error en /stats/admin: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error")


@app.post("/consultar", response_model=ConsultaResponse)
def consultar(req: ConsultaRequest):
    """
    Recibe una pregunta legal (o comando) y devuelve la respuesta del motor RAG.
    Los comandos (/leyes, /ayuda, etc.) se manejan directamente sin pasar por el RAG.
    El campo `respuesta` viene en HTML; la TMA lo renderiza con innerHTML.
    """
    # ── Detectar comandos ──────────────────────────────────────────
    if req.pregunta.startswith("/"):
        resultado_cmd = _manejar_comando(req.pregunta, req.user_id)
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
def eliminar_conversacion(conv_id: int, user_id: str):
    """
    Elimina una conversación y todos sus mensajes.
    user_id se pasa como query param: DELETE /conversaciones/123?user_id=456
    """
    try:
        import db as database
        database.tma_eliminar_conversacion(conv_id, user_id)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error eliminando: {e}")
        raise HTTPException(status_code=500, detail="Error eliminando conversación")


@app.post("/feedback")
def feedback(req: FeedbackRequest):
    """Registra la calificación del usuario (👍 = 1, 👎 = -1)."""
    try:
        import db as database
        tipo = "positivo" if req.valor == 1 else "negativo"
        # Si hay initData válido, usar ese user_id (anti-suplantación).
        # Si no, caer al user_id del body (compat con TMA sin initData todavía).
        uid_auth = _user_id_from_init_data(req.init_data)
        if uid_auth is not None:
            uid = uid_auth
        else:
            try:
                uid = int(req.user_id)
            except (ValueError, TypeError):
                uid = 0
        fb_id = database.guardar_feedback_v2(
            uid, tipo, req.pregunta, req.respuesta, req.motivo
        )
        logger.info(
            f"Feedback guardado id={fb_id} user={uid} tipo={tipo} "
            f"motivo_len={len(req.motivo or '')}"
        )
        return {"ok": True, "id": fb_id}
    except Exception as e:
        logger.error(f"Error en /feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error registrando feedback")


@app.get("/admin/feedback")
def admin_listar_feedback(init_data: str = "", estado: str = "nuevo",
                          tipo: str | None = None, limit: int = 50, offset: int = 0):
    """Lista tickets de feedback — solo admins con initData firmado."""
    admin_id = _admin_from_init_data(init_data)
    if not admin_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    try:
        import db as database
        estado_filtro = None if estado in ("", "todos") else estado
        tipo_filtro = None if tipo in ("", "todos", None) else tipo
        items = database.listar_feedback_tickets(
            estado=estado_filtro, tipo=tipo_filtro, limit=limit, offset=offset
        )
        return {"items": items, "count": len(items)}
    except Exception as e:
        logger.error(f"Error en /admin/feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error listando feedback")


@app.post("/admin/feedback/{feedback_id}/resolver")
def admin_resolver_feedback(feedback_id: int, req: ResolverRequest):
    """Marca un feedback como resuelto y opcionalmente notifica al usuario."""
    admin_id = _admin_from_init_data(req.init_data)
    if not admin_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    try:
        import db as database
        fb = database.marcar_feedback_resuelto(feedback_id, admin_id)
        if not fb:
            raise HTTPException(status_code=404, detail="Feedback no existe")
        notificado = False
        if req.notificar and fb.get("user_id") and fb["user_id"] > 0:
            notificado = _enviar_mensaje_telegram(
                fb["user_id"],
                "✅ ¡Gracias por tu reporte! Revisamos tu feedback y ya fue corregido. "
                "Puedes intentar tu pregunta de nuevo y verificar que la respuesta mejoró."
            )
        logger.info(f"Feedback {feedback_id} resuelto por admin {admin_id}, notificado={notificado}")
        return {"ok": True, "notificado": notificado, "feedback": fb}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en /admin/feedback/{feedback_id}/resolver: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error resolviendo feedback")


# ─── Modelos de abogados ──────────────────────────────────────────────────────

class SolicitudAbogadoRequest(BaseModel):
    init_data: str
    nombre: str
    cedula: str
    inpreabogado: str
    especialidades: list[str]
    telefono: str
    estado_geo: str
    biografia: str = ""
    modalidad: str = "presencial"
    metodos_pago: list[str] = []

class ActualizarPerfilAbogadoRequest(BaseModel):
    init_data: str
    biografia: str | None = None
    modalidad: str | None = None
    metodos_pago: list[str] | None = None
    telefono: str | None = None
    notas: str | None = None

class AprobarSolicitudRequest(BaseModel):
    init_data: str
    membresia: str = "inactiva"
    ranking_bonus: int = 0
    expira: str | None = None

class RechazarSolicitudRequest(BaseModel):
    init_data: str
    motivo: str = ""

class ActualizarAbogadoAdminRequest(BaseModel):
    init_data: str
    nombre: str | None = None
    especialidad: str | None = None
    telefono: str | None = None
    estado: str | None = None
    notas: str | None = None
    membresia: str | None = None
    ranking: int | None = None
    verificado: int | None = None
    activo: int | None = None

class MembresiaRequest(BaseModel):
    init_data: str
    tipo: str   # "activa" | "inactiva" | "beta"
    expira: str | None = None

class AccionAbogadoRequest(BaseModel):
    init_data: str


# ─── Endpoints de abogados ────────────────────────────────────────────────────

@app.post("/abogados/solicitud")
def crear_solicitud(req: SolicitudAbogadoRequest):
    """Registra una solicitud de abogado verificado desde la TMA."""
    uid = _user_id_from_init_data(req.init_data)
    if uid is None:
        raise HTTPException(status_code=403, detail="No autorizado")

    # Validaciones de dominio
    if not req.especialidades:
        raise HTTPException(status_code=400, detail="Selecciona al menos una especialidad")
    for e in req.especialidades:
        if e not in config.ESPECIALIDADES_ABOGADO:
            raise HTTPException(status_code=400, detail=f"Especialidad inválida: {e}")
    invalidos = [m for m in req.metodos_pago if m not in config.METODOS_PAGO_VALIDOS]
    if invalidos:
        raise HTTPException(status_code=400, detail=f"Métodos de pago inválidos: {invalidos}")

    try:
        import db as database
        sol_id = database.crear_solicitud_abogado(
            user_id=uid,
            nombre=req.nombre,
            cedula=req.cedula,
            inpreabogado=req.inpreabogado,
            especialidad=req.especialidades,
            telefono=req.telefono,
            estado_geo=req.estado_geo,
            biografia=req.biografia,
            modalidad=req.modalidad,
            metodos_pago=req.metodos_pago,
        )
        # Notificar admin con datos de contacto
        u_info = database._usuario_info(uid)
        username_txt = f"@{u_info['username']}" if u_info.get("username") else "sin username"
        esp_txt = " · ".join(req.especialidades)
        for admin_id in config.ADMIN_IDS:
            _enviar_mensaje_telegram(
                admin_id,
                f"📋 Nueva solicitud de abogado\n"
                f"👤 {req.nombre} (user_id: {uid} · {username_txt})\n"
                f"🪪 INPRE {req.inpreabogado} · Cédula {req.cedula}\n"
                f"⚖️ {esp_txt}\n"
                f"📍 {req.estado_geo} · {req.modalidad}\n"
                f"📱 {req.telefono}\n"
                f"🔢 ID solicitud: {sol_id}"
            )
        logger.info(f"Solicitud abogado creada id={sol_id} user={uid}")
        return {"ok": True, "solicitud_id": sol_id}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Error en /abogados/solicitud: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error registrando solicitud")


@app.get("/abogado/estado-solicitud")
def estado_solicitud(init_data: str = ""):
    """Devuelve el estado de solicitud/membresía del usuario para decidir qué mostrar en la TMA.
    Incluye is_admin para que el frontend no necesite una segunda llamada.
    """
    uid = _user_id_from_init_data(init_data)
    if uid is None:
        return {"es_abogado": False, "tiene_solicitud": False, "estado": None, "is_admin": False}
    try:
        import db as database
        result = database.estado_solicitud_usuario(uid)
        result["is_admin"] = uid in config.ADMIN_IDS
        return result
    except Exception as e:
        logger.error(f"Error en /abogado/estado-solicitud: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error")


@app.get("/admin/is-admin")
def check_is_admin(user_id: str = ""):
    """Verifica si un user_id es admin. Solo devuelve bool — no expone datos.
    Usado como fallback en la TMA cuando HMAC no está disponible.
    """
    return {"is_admin": _es_admin(user_id)}


@app.delete("/abogados/solicitud")
def cancelar_solicitud_endpoint(init_data: str = ""):
    """El usuario cancela su propia solicitud pendiente."""
    uid = _user_id_from_init_data(init_data)
    if uid is None:
        raise HTTPException(status_code=403, detail="No autorizado")
    try:
        import db as database
        ok = database.cancelar_solicitud(uid)
        if not ok:
            raise HTTPException(status_code=404, detail="No hay solicitud activa para cancelar")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en DELETE /abogados/solicitud: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error")


@app.post("/abogado/baja")
def baja_abogado_endpoint(req: dict):
    """El abogado se da de baja (se marca inactivo)."""
    init_data = req.get("init_data", "")
    uid = _user_id_from_init_data(init_data)
    if uid is None:
        raise HTTPException(status_code=403, detail="No autorizado")
    try:
        import db as database
        ok = database.baja_abogado(uid)
        if not ok:
            raise HTTPException(status_code=404, detail="No eres abogado activo")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en POST /abogado/baja: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error")


@app.get("/abogado/perfil")
def perfil_abogado(init_data: str = ""):
    """Perfil completo del abogado para el Escritorio (solo si es abogado)."""
    uid = _user_id_from_init_data(init_data)
    if uid is None:
        raise HTTPException(status_code=403, detail="No autorizado")
    try:
        import db as database
        perfil = database.obtener_abogado_por_user(uid)
        if not perfil:
            raise HTTPException(status_code=404, detail="No eres abogado verificado")
        return perfil
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en GET /abogado/perfil: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error obteniendo perfil")


@app.put("/abogado/perfil")
def actualizar_perfil_abogado(req: ActualizarPerfilAbogadoRequest):
    """El abogado edita su propia bio, modalidad, métodos de pago y teléfono."""
    uid = _user_id_from_init_data(req.init_data)
    if uid is None:
        raise HTTPException(status_code=403, detail="No autorizado")

    campos = {}
    if req.biografia is not None:
        campos["biografia"] = req.biografia
    if req.modalidad is not None:
        campos["modalidad"] = req.modalidad
    if req.metodos_pago is not None:
        invalidos = [m for m in req.metodos_pago if m not in config.METODOS_PAGO_VALIDOS]
        if invalidos:
            raise HTTPException(status_code=400, detail=f"Métodos inválidos: {invalidos}")
        campos["metodos_pago"] = req.metodos_pago
    if req.telefono is not None:
        campos["telefono"] = req.telefono
    if req.notas is not None:
        campos["notas"] = req.notas

    if not campos:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar")

    try:
        import db as database
        ok = database.actualizar_perfil_abogado(uid, campos)
        if not ok:
            raise HTTPException(status_code=404, detail="No eres abogado verificado")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en PUT /abogado/perfil: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error actualizando perfil")


# ─── Endpoints admin de solicitudes ──────────────────────────────────────────

@app.get("/admin/solicitudes")
def admin_listar_solicitudes(init_data: str = "", estado: str = "pendiente", limit: int = 50):
    """Lista solicitudes de abogados filtradas por estado — solo admins."""
    admin_id = _admin_from_init_data(init_data)
    if not admin_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    try:
        import db as database
        items = database.listar_solicitudes(estado_solicitud=estado, limit=limit)
        return {"items": items, "count": len(items)}
    except Exception as e:
        logger.error(f"Error en /admin/solicitudes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error listando solicitudes")


@app.post("/admin/solicitudes/{solicitud_id}/aprobar")
def admin_aprobar_solicitud(solicitud_id: int, req: AprobarSolicitudRequest):
    """Aprueba una solicitud: mueve datos a tabla abogados y asigna membresía."""
    admin_id = _admin_from_init_data(req.init_data)
    if not admin_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    try:
        import db as database
        result = database.aprobar_solicitud(solicitud_id, admin_id)
        if not result:
            raise HTTPException(status_code=404, detail="Solicitud no encontrada o ya procesada")

        abogado_id = result.get("abogado_id")
        # Asignar membresía si se especificó
        if abogado_id and req.membresia in ("activa", "beta"):
            database.set_membresia(abogado_id, req.membresia, req.expira)
        # Ranking bonus extra
        if abogado_id and req.ranking_bonus > 0:
            with database.get_db() as con:
                con.execute(
                    "UPDATE abogados SET ranking = ranking + ? WHERE id = ?",
                    (req.ranking_bonus, abogado_id)
                )

        # Notificar al usuario
        if result.get("user_id"):
            _enviar_mensaje_telegram(
                result["user_id"],
                "✅ ¡Tu solicitud fue aprobada! Ya eres Abogado Verificado en aBOTgado. "
                "Abre la app para completar tu perfil en el Escritorio del Abogado."
            )
        logger.info(f"Solicitud {solicitud_id} aprobada por admin {admin_id}, abogado_id={abogado_id}")
        return {"ok": True, "abogado_id": abogado_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error aprobando solicitud {solicitud_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error aprobando solicitud")


@app.post("/admin/solicitudes/{solicitud_id}/rechazar")
def admin_rechazar_solicitud(solicitud_id: int, req: RechazarSolicitudRequest):
    """Rechaza una solicitud de abogado y notifica al usuario."""
    admin_id = _admin_from_init_data(req.init_data)
    if not admin_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    try:
        import db as database
        result = database.rechazar_solicitud(solicitud_id, admin_id, req.motivo)
        if not result:
            raise HTTPException(status_code=404, detail="Solicitud no encontrada o ya procesada")
        if result.get("user_id"):
            motivo_txt = f" Motivo: {req.motivo}" if req.motivo else ""
            _enviar_mensaje_telegram(
                result["user_id"],
                f"❌ Tu solicitud de Abogado Verificado fue rechazada.{motivo_txt}"
            )
        logger.info(f"Solicitud {solicitud_id} rechazada por admin {admin_id}")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rechazando solicitud {solicitud_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error rechazando solicitud")


class EditarSolicitudRequest(BaseModel):
    init_data: str
    nombre: str | None = None
    cedula: str | None = None
    inpreabogado: str | None = None
    especialidades: list[str] | None = None
    telefono: str | None = None
    estado_geo: str | None = None
    biografia: str | None = None
    modalidad: str | None = None
    metodos_pago: list[str] | None = None

class PedirCorreccionRequest(BaseModel):
    init_data: str
    mensaje: str

class MensajeDirectoRequest(BaseModel):
    init_data: str
    mensaje: str


@app.post("/admin/solicitudes/{solicitud_id}/en-revision")
def admin_marcar_en_revision(solicitud_id: int, req: AccionAbogadoRequest):
    """Marca la solicitud como en revisión y notifica al solicitante."""
    admin_id = _admin_from_init_data(req.init_data)
    if not admin_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    try:
        import db as database
        result = database.marcar_en_revision(solicitud_id, admin_id)
        if not result:
            return {"ok": True, "ya_en_revision": True}  # ya estaba revisada, no es error
        if result.get("user_id"):
            _enviar_mensaje_telegram(
                result["user_id"],
                f"👀 Tu solicitud de Abogado Verificado está siendo revisada. "
                f"Te notificaremos cuando tengamos una respuesta."
            )
        logger.info(f"Solicitud {solicitud_id} marcada en_revision por admin {admin_id}")
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error marcando en_revision {solicitud_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error")


@app.put("/abogados/solicitud/{solicitud_id}")
def editar_solicitud(solicitud_id: int, req: EditarSolicitudRequest):
    """El solicitante edita su solicitud (solo si está en pendiente o correccion_solicitada)."""
    uid = _user_id_from_init_data(req.init_data)
    if uid is None:
        raise HTTPException(status_code=403, detail="No autorizado")
    if req.especialidades is not None:
        for e in req.especialidades:
            if e not in config.ESPECIALIDADES_ABOGADO:
                raise HTTPException(status_code=400, detail=f"Especialidad inválida: {e}")
    if req.metodos_pago is not None:
        invalidos = [m for m in req.metodos_pago if m not in config.METODOS_PAGO_VALIDOS]
        if invalidos:
            raise HTTPException(status_code=400, detail=f"Métodos inválidos: {invalidos}")
    campos = {k: v for k, v in {
        "nombre": req.nombre, "cedula": req.cedula, "inpreabogado": req.inpreabogado,
        "especialidad": req.especialidades, "telefono": req.telefono,
        "estado_geo": req.estado_geo, "biografia": req.biografia,
        "modalidad": req.modalidad, "metodos_pago": req.metodos_pago,
    }.items() if v is not None}
    if not campos:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar")
    try:
        import db as database
        ok = database.actualizar_solicitud(solicitud_id, uid, campos)
        if not ok:
            raise HTTPException(status_code=409, detail="No puedes editar esta solicitud")
        # Notificar admins que la solicitud fue reenviada
        u_info = database._usuario_info(uid)
        username_txt = f"@{u_info['username']}" if u_info.get("username") else f"user_id {uid}"
        for admin_id in config.ADMIN_IDS:
            _enviar_mensaje_telegram(
                admin_id,
                f"✏️ Solicitud #{solicitud_id} actualizada por {username_txt}. "
                f"Volvió a estado Pendiente."
            )
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error editando solicitud {solicitud_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error editando solicitud")


@app.post("/admin/solicitudes/{solicitud_id}/pedir-correccion")
def admin_pedir_correccion(solicitud_id: int, req: PedirCorreccionRequest):
    """Solicita correcciones al abogado sin rechazarlo."""
    admin_id = _admin_from_init_data(req.init_data)
    if not admin_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    try:
        import db as database
        result = database.pedir_correccion(solicitud_id, admin_id, req.mensaje)
        if not result:
            raise HTTPException(status_code=404, detail="Solicitud no encontrada o ya procesada")
        if result.get("user_id"):
            _enviar_mensaje_telegram(
                result["user_id"],
                f"✏️ Tu solicitud de Abogado Verificado necesita una corrección:\n\n"
                f"{req.mensaje}\n\n"
                f"Abre el directorio en la app y usa el botón 'Editar solicitud' para corregirla."
            )
        logger.info(f"Corrección solicitada en solicitud {solicitud_id} por admin {admin_id}")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pidiendo corrección {solicitud_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error")


@app.post("/admin/solicitudes/{solicitud_id}/mensaje")
def admin_enviar_mensaje(solicitud_id: int, req: MensajeDirectoRequest):
    """Envía un mensaje directo al solicitante vía Telegram."""
    admin_id = _admin_from_init_data(req.init_data)
    if not admin_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    try:
        import db as database
        sol = database.obtener_solicitud(solicitud_id)
        if not sol or not sol.get("user_id"):
            raise HTTPException(status_code=404, detail="Solicitud no encontrada")
        enviado = _enviar_mensaje_telegram(sol["user_id"], req.mensaje)
        if not enviado:
            raise HTTPException(status_code=502, detail="No se pudo enviar el mensaje")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enviando mensaje a solicitud {solicitud_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error")


# ─── Endpoints admin de gestión de abogados ──────────────────────────────────

@app.get("/admin/abogados")
def admin_listar_abogados(init_data: str = "", incluir_inactivos: bool = True):
    """Lista todos los abogados para el panel admin (con datos completos)."""
    admin_id = _admin_from_init_data(init_data)
    if not admin_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    try:
        import db as database
        return {"items": database.listar_abogados_admin(incluir_inactivos=incluir_inactivos)}
    except Exception as e:
        logger.error(f"Error en /admin/abogados: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error")


@app.put("/admin/abogados/{abogado_id}")
def admin_actualizar_abogado(abogado_id: int, req: ActualizarAbogadoAdminRequest):
    """Admin edita cualquier campo de un abogado."""
    admin_id = _admin_from_init_data(req.init_data)
    if not admin_id:
        raise HTTPException(status_code=403, detail="No autorizado")

    campos = {k: v for k, v in {
        "nombre": req.nombre,
        "especialidad": req.especialidad,
        "telefono": req.telefono,
        "estado": req.estado,
        "notas": req.notas,
        "membresia": req.membresia,
        "ranking": req.ranking,
        "verificado": req.verificado,
        "activo": req.activo,
    }.items() if v is not None}

    if not campos:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar")

    try:
        import db as database
        ok = database.admin_actualizar_abogado(abogado_id, campos)
        if not ok:
            raise HTTPException(status_code=404, detail="Abogado no encontrado")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en PUT /admin/abogados/{abogado_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error actualizando abogado")


@app.post("/admin/abogados/{abogado_id}/membresia")
def admin_set_membresia(abogado_id: int, req: MembresiaRequest):
    """Establece o cambia la membresía de un abogado."""
    admin_id = _admin_from_init_data(req.init_data)
    if not admin_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    if req.tipo not in ("activa", "inactiva", "beta"):
        raise HTTPException(status_code=400, detail="Tipo de membresía inválido")
    try:
        import db as database
        ok = database.set_membresia(abogado_id, req.tipo, req.expira)
        if not ok:
            raise HTTPException(status_code=404, detail="Abogado no encontrado")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en /admin/abogados/{abogado_id}/membresia: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error")


@app.post("/admin/abogados/{abogado_id}/suspender")
def admin_suspender_abogado(abogado_id: int, req: AccionAbogadoRequest):
    """Desactiva un abogado y le notifica."""
    admin_id = _admin_from_init_data(req.init_data)
    if not admin_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    try:
        import db as database
        ab = database.admin_actualizar_abogado(abogado_id, {"activo": 0})
        if not ab:
            raise HTTPException(status_code=404, detail="Abogado no encontrado")
        # Buscar user_id para notificar
        abogados = database.listar_abogados_admin(incluir_inactivos=True)
        for a in abogados:
            if a["id"] == abogado_id and a.get("user_id"):
                _enviar_mensaje_telegram(
                    a["user_id"],
                    "⚠️ Tu perfil de Abogado Verificado en aBOTgado ha sido suspendido temporalmente. "
                    "Contacta al soporte para más información."
                )
                break
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error suspendiendo abogado {abogado_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error")


@app.post("/admin/abogados/{abogado_id}/activar")
def admin_activar_abogado(abogado_id: int, req: AccionAbogadoRequest):
    """Reactiva un abogado suspendido y le notifica."""
    admin_id = _admin_from_init_data(req.init_data)
    if not admin_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    try:
        import db as database
        ok = database.admin_actualizar_abogado(abogado_id, {"activo": 1})
        if not ok:
            raise HTTPException(status_code=404, detail="Abogado no encontrado")
        abogados = database.listar_abogados_admin(incluir_inactivos=True)
        for a in abogados:
            if a["id"] == abogado_id and a.get("user_id"):
                _enviar_mensaje_telegram(
                    a["user_id"],
                    "✅ Tu perfil de Abogado Verificado en aBOTgado ha sido reactivado. "
                    "Ya apareces nuevamente en el directorio."
                )
                break
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activando abogado {abogado_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error")


# ─── Directorio público mejorado ─────────────────────────────────────────────

@app.get("/directorio")
def directorio_abogados(
    especialidad: str | None = None,
    estado: str | None = None,
    modalidad: str | None = None,
):
    """
    Lista pública de abogados verificados con membresía activa o beta.
    Ordenada por ranking DESC. No expone user_id ni cédula.
    Filtros: ?especialidad=Penal&estado=Miranda&modalidad=online
    """
    try:
        import db as database
        abogados = database.listar_abogados_directorio(
            especialidad=especialidad,
            estado_geo=estado,
            modalidad=modalidad,
        )
        return abogados
    except Exception as e:
        logger.error(f"Error en /directorio: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error obteniendo directorio")
