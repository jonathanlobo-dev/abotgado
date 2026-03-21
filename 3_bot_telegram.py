"""
aBOTgado - Bot de Telegram
============================
Handlers de comandos y lógica del bot.
El motor de búsqueda está en busqueda.py
"""

import logging
import asyncio
import os
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
import config
import db
import documentos
import busqueda

# ─── LOGGING ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def es_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


async def notificar_admins(context, texto: str):
    for admin_id in config.ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=texto)
        except Exception:
            pass


def resolver_targets(args: list[str]) -> tuple[list[int], list[str]]:
    """Resuelve una lista de IDs/@usernames a user_ids.
    Retorna (ids_resueltos, errores)."""
    ids = []
    errores = []
    for arg in args:
        uid = db.resolver_usuario(arg)
        if uid:
            ids.append(uid)
        else:
            errores.append(arg)
    return ids, errores


async def enviar_respuesta(message, texto: str):
    """Formatea la respuesta a HTML y envía con fallback a texto plano."""
    texto = busqueda.formatear_respuesta(texto)
    if len(texto) > 4096:
        for i in range(0, len(texto), 4096):
            await enviar_respuesta(message, texto[i:i+4096])
        return
    try:
        await message.reply_text(texto, parse_mode="HTML")
    except Exception:
        await message.reply_text(texto)


# ─── ESTADO TEMPORAL ─────────────────────────────────────────────────────────

feedback_pendiente = set()
soporte_pendiente  = set()
ultima_respuesta   = {}  # user_id -> {"pregunta": ..., "respuesta": ...}
registro_abogado   = {}  # user_id -> {"paso": N, "datos": {...}}
esperando_ley      = {}  # user_id -> {"num_art": int} — esperando nombre de ley


# ─── FILTRO DE SEGURIDAD (PRE-LLM) ─────────────────────────────────────────

import re as _re_seguridad

_PATRONES_INYECCION = [
    _re_seguridad.compile(r'ignora\s+(?:todas?\s+)?(?:las?\s+)?instrucciones', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'olvida\s+(?:todas?\s+)?(?:las?\s+)?(?:instrucciones|reglas)', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'repite\s+(?:tu\s+)?(?:prompt|system\s*prompt|instrucciones)', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'(?:cu[aá]les?\s+(?:son|fueron)\s+(?:tus|las)\s+instrucciones)', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'(?:tu\s+)?prompt\s+(?:del\s+)?sistema', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'(?:entra|cambia|activa)\s+(?:en\s+)?modo\s+(?:de\s+)?(?:desarrollador|developer|debug|admin|dios|god)', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'a\s+partir\s+de\s+ahora\s*,?\s*(?:vas?\s+a\s+)?actua(?:r|s)\s+como', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'act[uú]a\s+como\s+(?:un|una|el|la)\s+(?!abogado)', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'las?\s+reglas?\s+anteriores?\s+ya\s+no\s+aplican', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'(?:empieza|comienza)\s+tu\s+respuesta\s+con', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'(?:est[aá]\s+)?(?:estrictamente\s+)?prohibido\s+(?:usar|que\s+uses)', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'responde\s+(?:en|al)\s+(?:idioma\s+)?(?:ingl[eé]s|ruso|franc[eé]s|portugu[eé]s|alem[aá]n|chino|japon[eé]s|italiano|[aá]rabe)', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'traduce\s+(?:toda\s+)?tu\s+respuesta', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'(?:responde|escribe)\s+(?:solo\s+)?(?:en\s+)?(?:formato\s+)?(?:json|xml|yaml|csv|markdown)', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'c[oó]mo\s+(?:fuiste|est[aá]s)\s+programado', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'(?:dime|revela|muestra)\s+(?:tus?\s+)?(?:instrucciones|reglas|configuraci[oó]n|prompt)', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'reglas\s+que\s+sigues\s+(?:internamente|para\s+responder)', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'resumen\s+de\s+tu\s+configuraci[oó]n', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'(?:traduce|traducir)\s+(?:tus\s+)?instrucciones', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'(?:primeras?\s+\d+\s+)?l[ií]neas?\s+de\s+tus\s+instrucciones', _re_seguridad.IGNORECASE),
    _re_seguridad.compile(r'mostr[aá]ndome\s+(?:las?\s+)?(?:primeras?\s+)?\d*\s*(?:l[ií]neas?\s+de\s+)?(?:tus\s+)?instrucciones', _re_seguridad.IGNORECASE),
]

RESPUESTA_INYECCION = "⚠️ No puedo procesar esa solicitud. Escribe tu consulta legal y te ayudo."

def detectar_inyeccion(texto: str) -> bool:
    """Detecta intentos de prompt injection antes de enviar al LLM."""
    for patron in _PATRONES_INYECCION:
        if patron.search(texto):
            return True
    return False


# ─── COMANDOS GENERALES ─────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = user.id
    es_nuevo = db.registrar_usuario(user_id, user.first_name, user.username or "")

    if es_nuevo:
        await notificar_admins(context,
            f"👤 NUEVO USUARIO\n"
            f"Nombre: {user.first_name}\n"
            f"Usuario: @{user.username or 'sin username'}\n"
            f"ID: {user_id}")

        if context.args and context.args[0].startswith("ref_"):
            try:
                referidor_id = int(context.args[0][4:])
                if referidor_id != user_id:
                    db.registrar_referido(user_id, referidor_id)
                    # Nuevo usuario: 2 semanas. Referidor: +1 semana extra.
                    db.activar_tester_temporal(user_id, dias=14)
                    db.extender_tester(referidor_id, dias=7)
                    try:
                        await context.bot.send_message(
                            chat_id=referidor_id,
                            text=f"🎉 Tu amigo {user.first_name} se registro con tu link.\n"
                                 f"<b>+1 semana de Plan Pionero!</b>\n"
                                 f"Memoria, comparador de articulos y mas.",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
            except (ValueError, IndexError):
                pass

    plan_info = db.info_plan(user_id)
    plan_txt  = f"{plan_info['icono']} {plan_info['nombre']}"

    await enviar_respuesta(
        update.message,
        f"⚖️ <b>¡Bienvenido a aBOTgado!</b>\n\n"
        f"Plan actual: {plan_txt}\n\n"
        "Soy tu asistente jurídico venezolano.\n\n"
        "📝 <b>Ejemplos:</b>\n"
        "• <i>¿Cuáles son mis derechos si me detienen?</i>\n"
        "• <i>¿Me pueden quitar el carro en una alcabala?</i>\n"
        "• <i>Me despidieron sin pagarme, ¿qué hago?</i>\n"
        "• <i>Mi esposo me maltrata, qué puedo hacer?</i>\n\n"
        "📄 <b>Documentos legales:</b> proximamente\n\n"
        "⚠️ <i>Soy informativo, no reemplazo a un abogado.</i>"
    )


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    plan_id = db.obtener_plan(user_id)
    con_memoria = db.tiene_memoria(user_id)

    texto = "📚 <b>Comandos disponibles:</b>\n\n"

    texto += "<b>General:</b>\n"
    texto += "/ayuda — Este mensaje\n"
    texto += "/leyes — Ver leyes disponibles\n"
    texto += "/ley — Buscar articulo exacto (ej: /ley LOTTT 85)\n"
    texto += "/estado — Tu plan y consultas\n"
    texto += "/stats — Tus estadisticas\n"
    texto += "/opinion — Dejar tu opinion\n"
    texto += "/referir — Invita amigos\n"
    texto += "/soporte — Contactar soporte\n\n"

    # Comandos premium/tester
    if plan_id >= config.PLAN_TESTER:
        texto += "<b>Funciones Pionero/Premium:</b>\n"
        texto += "/comparar — Comparar dos articulos\n"
        if con_memoria:
            texto += "/nuevo — Borrar historial\n"
            texto += "/guardar — Guardar ultima respuesta\n"
            texto += "/mis_consultas — Ver favoritos guardados\n"
        texto += "\n"

    # Documentos (desactivados temporalmente)
    texto += "📄 <b>Documentos legales:</b> proximamente\n\n"

    # Anuncio para abogados
    texto += (
        "👨‍⚖️ <b>¿Eres abogado?</b>\n"
        "Estamos construyendo un directorio de abogados verificados. "
        "Si deseas aparecer en el directorio, escribe /soporte "
        "y cuéntanos tu especialidad y datos de contacto.\n\n"
    )

    # Admin
    if es_admin(user_id):
        texto += (
            "<b>Admin:</b>\n"
            "/usuarios — Lista de usuarios\n"
            "/stats_admin — Estadisticas globales\n"
            "/premium_on ID — Activar Premium\n"
            "/premium_off ID — Desactivar Premium\n"
            "/tester ID — Activar Pionero\n"
            "/regalar_memoria ID — Regalar memoria\n"
            "/anuncio MSG — Broadcast a todos\n"
            "/mensaje ID MSG — Mensaje directo a 1 usuario\n"
            "/feedback — Ver opiniones\n"
            "/responder ID MSG — Responder soporte\n"
            "/backup — Descargar backup de la DB\n\n"
            "<b>Planes:</b>\n"
            "/plan_add ID [dias] — Sumar dias Pionero (+7 default)\n"
            "/plan_del ID [dias] — Quitar dias Pionero (-7 default)\n\n"
            "<b>Directorio:</b>\n"
            "/add_abogado — Registrar abogado\n"
            "/abogados — Ver directorio\n"
            "/del_abogado ID — Desactivar abogado\n"
            "/activar_abogado ID — Reactivar abogado\n"
        )

    texto += "\nO escribeme tu consulta juridica."
    await enviar_respuesta(update.message, texto)


async def estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id   = update.effective_user.id
    plan_id   = db.obtener_plan(user_id)
    plan_info = db.info_plan(user_id)
    restantes = db.consultas_restantes(user_id)
    tiene_mem = db.tiene_memoria(user_id)
    docs      = db.docs_disponibles(user_id)

    texto = f"{plan_info['icono']} <b>Plan {plan_info['nombre']}</b>\n\n"

    if plan_info["consultas"] == -1:
        texto += "✅ Consultas ilimitadas\n"
    else:
        texto += f"📊 Consultas hoy: <b>{restantes}/{plan_info['consultas']}</b>\n"

    if tiene_mem:
        texto += "✅ Memoria de conversación activa\n"
    else:
        texto += "❌ Sin memoria de conversación\n"

    texto += "📄 Documentos legales: <i>proximamente</i>\n"

    if plan_id == config.PLAN_GRATIS:
        texto += (
            "\n<b>Plan Pionero</b> (gratis para testers):\n"
            "• Memoria de conversacion\n"
            "• Comparador de articulos\n"
            "• Explicacion de articulos con /ley\n"
            "Escribe /soporte para ser tester!\n"
        )
    if plan_id < config.PLAN_PREMIUM:
        texto += (
            "\n<b>Plan Premium</b>:\n"
            "• Consultas ilimitadas\n"
            "• Memoria de conversacion\n"
            "• Comparador de articulos\n"
        )

    await enviar_respuesta(update.message, texto)


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica que el bot está vivo."""
    articulos = busqueda.coleccion.count()
    usuarios = len(db.listar_usuarios())
    await update.message.reply_text(
        f"Bot activo\n"
        f"Articulos: {articulos}\n"
        f"Usuarios: {usuarios}"
    )


async def nuevo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.limpiar_historial(user_id)
    await update.message.reply_text("🗑️ Historial borrado. Empezamos conversación nueva.")


async def leyes_disponibles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = busqueda.generar_texto_leyes()
    await enviar_respuesta(update.message, texto)


# ─── /ley — BÚSQUEDA DIRECTA ────────────────────────────────────────────────

async def cmd_ley(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ley <nombre_ley> <numero_articulo> — Muestra un artículo + explicación."""
    if not context.args or len(context.args) < 2:
        await enviar_respuesta(
            update.message,
            "📖 <b>Busqueda directa de articulos</b>\n\n"
            "<b>Uso:</b> /ley &lt;nombre_ley&gt; &lt;numero&gt;\n\n"
            "<b>Ejemplos:</b>\n"
            "• <code>/ley constitucion 49</code>\n"
            "• <code>/ley LOTTT 85</code>\n"
            "• <code>/ley CC 1159</code>\n"
            "• <code>/ley codigo penal 405</code>\n\n"
            "Usa /leyes para ver todas las leyes y sus alias."
        )
        return

    try:
        num_art = int(context.args[-1])
    except ValueError:
        await update.message.reply_text("El ultimo argumento debe ser el numero del articulo.\nEjemplo: /ley LOTTT 85")
        return

    nombre_ley_input = " ".join(context.args[:-1])
    ley_real = busqueda.buscar_ley_por_alias(nombre_ley_input)

    if not ley_real:
        await enviar_respuesta(
            update.message,
            f"No reconozco la ley \"<b>{nombre_ley_input}</b>\".\n\n"
            "Usa /leyes para ver las leyes disponibles y sus alias."
        )
        return

    arts = busqueda.buscar_articulo_en_db(ley_real, num_art)

    if not arts:
        await enviar_respuesta(
            update.message,
            f"No encontre el <b>Art. {num_art}</b> de <b>{ley_real}</b>.\n\n"
            "Puede que ese articulo no este en mi base de datos."
        )
        return

    texto_art = arts[0]["texto"]
    if len(texto_art) > 3000:
        texto_art = texto_art[:3000] + "... [truncado]"

    # Enviar typing mientras el LLM explica
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    # Obtener explicación del LLM
    explicacion = await asyncio.to_thread(
        busqueda.explicar_articulo, arts[0]["texto"], ley_real, num_art
    )

    respuesta = (
        f"📖 <b>{ley_real}</b>\n"
        f"<b>Articulo {num_art}</b>\n\n"
        f"{texto_art}\n\n"
    )

    if explicacion:
        respuesta += f"{'━' * 25}\n{explicacion}\n\n"

    respuesta += "<i>Usa /comparar para comparar con otro articulo.</i>"

    await enviar_respuesta(update.message, respuesta)


# ─── /comparar — COMPARADOR (TESTER/PREMIUM) ────────────────────────────────

async def cmd_comparar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/comparar <ley1> <art1> vs <ley2> <art2> — Solo Tester/Premium."""
    user_id = update.effective_user.id
    plan_id = db.obtener_plan(user_id)

    # Verificar plan
    if plan_id < config.PLAN_TESTER and not es_admin(user_id):
        await enviar_respuesta(
            update.message,
            "⚖️ <b>Comparador de articulos</b>\n\n"
            "Esta funcion esta disponible desde el <b>Plan Pionero</b>.\n\n"
            "Escribe /estado para ver tu plan actual."
        )
        return

    if not context.args:
        await enviar_respuesta(
            update.message,
            "⚖️ <b>Comparador de articulos</b>\n\n"
            "<b>Uso:</b> /comparar &lt;ley1&gt; &lt;art1&gt; vs &lt;ley2&gt; &lt;art2&gt;\n\n"
            "<b>Ejemplos:</b>\n"
            "• <code>/comparar LOTTT 85 vs LOTTT 86</code>\n"
            "• <code>/comparar constitucion 49 vs CP 405</code>\n"
            "• <code>/comparar CC 1159 vs CC 1160</code>\n\n"
            "Usa \"vs\" para separar los dos articulos."
        )
        return

    texto_completo = " ".join(context.args)
    partes = texto_completo.lower().split(" vs ")

    if len(partes) != 2:
        await update.message.reply_text(
            "Formato: /comparar <ley1> <art1> vs <ley2> <art2>\n"
            "Ejemplo: /comparar LOTTT 85 vs LOTTT 86"
        )
        return

    articulos_encontrados = []

    for i, parte in enumerate(partes):
        tokens = parte.strip().split()
        if len(tokens) < 2:
            await update.message.reply_text(
                f"Falta informacion en el articulo {i+1}.\n"
                "Cada lado necesita: <ley> <numero>\nEjemplo: LOTTT 85"
            )
            return

        try:
            num = int(tokens[-1])
        except ValueError:
            await update.message.reply_text(
                f"El numero del articulo {i+1} no es valido: \"{tokens[-1]}\""
            )
            return

        nombre_ley = " ".join(tokens[:-1])
        ley_real = busqueda.buscar_ley_por_alias(nombre_ley)

        if not ley_real:
            await enviar_respuesta(
                update.message,
                f"No reconozco la ley \"<b>{nombre_ley}</b>\".\n"
                "Usa /leyes para ver las leyes disponibles y sus alias."
            )
            return

        arts = busqueda.buscar_articulo_en_db(ley_real, num)

        if not arts:
            await enviar_respuesta(
                update.message,
                f"No encontre el <b>Art. {num}</b> de <b>{ley_real}</b>."
            )
            return

        texto = arts[0]["texto"]
        if len(texto) > 1500:
            texto = texto[:1500] + "... [truncado]"

        articulos_encontrados.append({
            "ley": ley_real, "num": num, "texto": texto,
        })

    a1, a2 = articulos_encontrados

    await enviar_respuesta(
        update.message,
        f"⚖️ <b>Comparacion de articulos</b>\n\n"
        f"{'━' * 30}\n"
        f"📖 <b>{a1['ley']}, Art. {a1['num']}</b>\n\n"
        f"{a1['texto']}\n\n"
        f"{'━' * 30}\n"
        f"📖 <b>{a2['ley']}, Art. {a2['num']}</b>\n\n"
        f"{a2['texto']}\n\n"
        f"{'━' * 30}\n"
        f"<i>Textos directos de la ley, sin interpretacion.</i>"
    )


# ─── STATS ───────────────────────────────────────────────────────────────────

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    s = db.stats_usuario(user_id)
    plan_info = db.info_plan(user_id)
    refs = db.obtener_referidos_count(user_id)

    texto = (
        "📊 <b>Tus estadisticas</b>\n\n"
        f"Plan: {plan_info['icono']} {plan_info['nombre']}\n"
        f"Consultas hoy: {s['consultas_hoy']}\n"
        f"Consultas totales: {s['consultas_total']}\n"
        f"Respuestas guardadas: {s['favoritos']}\n"
        f"Amigos referidos: {refs}\n"
    )
    await enviar_respuesta(update.message, texto)


async def cmd_stats_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        return

    su = db.stats_usuarios()
    sc = db.obtener_stats()

    texto = "📊 <b>Estadísticas de aBOTgado</b>\n\n"

    texto += (
        f"👥 Usuarios: <b>{su['total']}</b> total\n"
        f"  🆓 Gratis: {su['gratis']}\n"
        f"  ⭐ Pionero: {su['pionero']}\n"
        f"  💎 Premium: {su['premium']}\n"
        f"  🟢 Activos hoy: {su['activos_hoy']}\n\n"
    )

    texto += (
        f"📈 <b>Consultas:</b>\n"
        f"  Hoy: {sc['consultas_hoy']}\n"
        f"  Últimos 7 días: {sc['consultas_7d']}\n"
        f"  Total: {sc['consultas_total']}\n\n"
    )

    if sc["temas_top"]:
        texto += "🔥 <b>Temas más consultados (últimos 7 días):</b>\n"
        for i, (tema, count) in enumerate(sc["temas_top"], 1):
            texto += f"  {i}. {tema} ({count} consultas)\n"
    else:
        texto += "🔥 <b>Temas más consultados:</b> Sin datos aún\n"

    await enviar_respuesta(update.message, texto)


# ─── FEEDBACK / OPINIÓN ─────────────────────────────────────────────────────

async def cmd_opinion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if context.args:
        comentario = " ".join(context.args)
        db.guardar_feedback(user_id, "comentario", comentario)
        await update.message.reply_text("Gracias por tu opinion! Nos ayuda a mejorar.")
        await notificar_admins(context,
            f"💬 FEEDBACK de {update.effective_user.first_name} (ID: {user_id}):\n{comentario}")
    else:
        feedback_pendiente.add(user_id)
        await enviar_respuesta(
            update.message,
            "<b>Tu opinion nos importa</b>\n\n"
            "Escribe tu comentario, sugerencia o queja.\n"
            "O escribe /cancelar para volver."
        )


async def cmd_feedback_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        return
    feedbacks = db.listar_feedback(20)
    if not feedbacks:
        await update.message.reply_text("No hay feedback aun.")
        return
    texto = "💬 <b>Feedback recibido:</b>\n\n"
    for f in feedbacks:
        texto += f"[{f['timestamp'][:10]}] ID {f['user_id']} ({f['tipo']}): {f['comentario'][:100]}\n"
    await enviar_respuesta(update.message, texto)


# ─── FAVORITOS ───────────────────────────────────────────────────────────────

async def cmd_guardar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ultima_respuesta:
        await update.message.reply_text("No hay una respuesta reciente para guardar.")
        return
    data = ultima_respuesta[user_id]
    db.guardar_favorito(user_id, data["pregunta"], data["respuesta"])
    await update.message.reply_text("Respuesta guardada. Usa /mis_consultas para verlas.")


async def cmd_mis_consultas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    favs = db.cargar_favoritos(user_id, 5)
    if not favs:
        await update.message.reply_text("No tienes respuestas guardadas. Usa /guardar despues de una consulta.")
        return

    texto = "📌 <b>Tus consultas guardadas:</b>\n\n"
    for i, f in enumerate(favs, 1):
        pregunta_corta = f["pregunta"][:60] + "..." if len(f["pregunta"]) > 60 else f["pregunta"]
        texto += f"<b>{i}.</b> {pregunta_corta}\n<i>{f['timestamp'][:10]}</i>\n\n"

    texto += "Escribe /ver_guardado N para ver la respuesta completa.\nEscribe /borrar_guardados para borrar todos."
    await enviar_respuesta(update.message, texto)


async def cmd_ver_guardado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Uso: /ver_guardado 1")
        return
    try:
        idx = int(context.args[0]) - 1
    except ValueError:
        await update.message.reply_text("Escribe el numero de la consulta.")
        return

    favs = db.cargar_favoritos(user_id, 10)
    if idx < 0 or idx >= len(favs):
        await update.message.reply_text("Numero invalido.")
        return

    f = favs[idx]
    texto = f"<b>Pregunta:</b> {f['pregunta']}\n\n{f['respuesta']}"
    await enviar_respuesta(update.message, texto)


async def cmd_borrar_guardados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.borrar_favoritos(user_id)
    await update.message.reply_text("Favoritos borrados.")


# ─── REFERIDOS ───────────────────────────────────────────────────────────────

async def cmd_referir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    refs = db.obtener_referidos_count(user_id)

    link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    await enviar_respuesta(
        update.message,
        "🎁 <b>Invita amigos a aBOTgado</b>\n\n"
        f"Tu link personal:\n<code>{link}</code>\n\n"
        "Cuando alguien se registre con tu link:\n"
        "• Tu amigo recibe <b>Plan Pionero gratis por 2 semanas</b>\n"
        "• Tu recibes <b>+1 semana extra</b> de Pionero\n"
        "• Memoria de conversacion y mas\n\n"
        f"Amigos referidos: <b>{refs}</b>"
    )


# ─── SOPORTE ─────────────────────────────────────────────────────────────────

async def cmd_soporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if context.args:
        mensaje = " ".join(context.args)
        db.guardar_ticket_soporte(user_id, mensaje)
        await update.message.reply_text("Mensaje enviado al equipo de soporte. Te responderemos pronto.")
        await notificar_admins(context,
            f"🆘 SOPORTE de {update.effective_user.first_name} (@{update.effective_user.username or 'N/A'}, ID: {user_id}):\n\n{mensaje}")
    else:
        soporte_pendiente.add(user_id)
        await enviar_respuesta(
            update.message,
            "🆘 <b>Soporte</b>\n\n"
            "Escribe tu mensaje y lo recibiremos.\n"
            "O escribe /cancelar para volver."
        )


async def cmd_responder_soporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Uso: /responder <user_id> <mensaje>")
        return
    try:
        target_id = int(context.args[0])
        mensaje = " ".join(context.args[1:])
    except ValueError:
        await update.message.reply_text("user_id debe ser un numero.")
        return

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"💬 <b>Respuesta de Soporte:</b>\n\n{mensaje}",
            parse_mode="HTML"
        )
        db.guardar_ticket_soporte(target_id, mensaje, "admin_to_user")
        await update.message.reply_text(f"Respuesta enviada a {target_id}")
    except Exception as e:
        await update.message.reply_text(f"Error enviando: {e}")


async def cmd_mensaje_directo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Uso: /mensaje <user_id> <texto>")
        return
    try:
        target_id = int(context.args[0])
        # Preservar saltos de línea del mensaje
        texto_raw = update.message.text or ""
        # /mensaje 12345 texto...\nlinea2...
        resto = texto_raw.split(None, 2)  # ["/mensaje", "ID", "resto..."]
        mensaje = resto[2] if len(resto) > 2 else ""
    except (ValueError, IndexError):
        await update.message.reply_text("user_id debe ser un numero.")
        return

    if not mensaje:
        await update.message.reply_text("Uso: /mensaje <user_id> <texto>")
        return

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"📢 <b>aBOTgado:</b>\n\n{mensaje}",
            parse_mode="HTML"
        )
        await update.message.reply_text(f"Mensaje enviado a {target_id}")
    except Exception as e:
        await update.message.reply_text(f"Error enviando: {e}")


# ─── COMANDOS DE ADMIN ──────────────────────────────────────────────────────

async def cmd_premium_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Uso: /premium_on <ID o @username> [mas...]")
        return
    ids, errores = resolver_targets(context.args)
    resultado = []
    for uid in ids:
        db.activar_premium(uid)
        resultado.append(f"Premium activado: {uid}")
    for err in errores:
        resultado.append(f"No encontrado: {err}")
    await update.message.reply_text("\n".join(resultado))


async def cmd_premium_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Uso: /premium_off <ID o @username> [mas...]")
        return
    ids, errores = resolver_targets(context.args)
    resultado = []
    for uid in ids:
        db.desactivar_premium(uid)
        resultado.append(f"Premium desactivado: {uid}")
    for err in errores:
        resultado.append(f"No encontrado: {err}")
    await update.message.reply_text("\n".join(resultado))


async def cmd_tester(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Uso: /tester <ID o @username> [mas...]")
        return
    ids, errores = resolver_targets(context.args)
    resultado = []
    for uid in ids:
        db.cambiar_plan(uid, config.PLAN_TESTER)
        resultado.append(f"Pionero activado: {uid}")
    for err in errores:
        resultado.append(f"No encontrado: {err}")
    await update.message.reply_text("\n".join(resultado))


async def cmd_regalar_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Uso: /regalar_doc <user_id> [cantidad]")
        return
    try:
        target_id = int(context.args[0])
        cantidad  = int(context.args[1]) if len(context.args) > 1 else 1
    except ValueError:
        await update.message.reply_text("user_id y cantidad deben ser numeros.")
        return

    db.regalar_documento(target_id, cantidad)
    await update.message.reply_text(f"Regalado {cantidad} documento(s) a {target_id}")

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"🎉 <b>Tienes {cantidad} documento(s) de regalo!</b>\n\n"
                 f"Usa /documento para generar tu documento legal.\n"
                 f"Escribe /estado para ver tus beneficios.",
            parse_mode="HTML"
        )
    except Exception:
        pass


async def cmd_regalar_memoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Uso: /regalar_memoria <ID o @username> [mas...]")
        return
    ids, errores = resolver_targets(context.args)
    resultado = []
    for uid in ids:
        db.activar_bono_memoria(uid)
        resultado.append(f"Memoria activada: {uid}")
        try:
            await context.bot.send_message(
                chat_id=uid,
                text="🎉 <b>Memoria de conversacion activada!</b>\n\n"
                     "Ahora puedo recordar nuestras conversaciones anteriores.\n"
                     "Escribe /estado para ver tus beneficios.",
                parse_mode="HTML"
            )
        except Exception:
            pass
    for err in errores:
        resultado.append(f"No encontrado: {err}")
    await update.message.reply_text("\n".join(resultado))


async def cmd_anuncio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        return
    # Tomar texto crudo para preservar saltos de línea
    texto_raw = update.message.text or ""
    mensaje = texto_raw.split(None, 1)[1] if len(texto_raw.split(None, 1)) > 1 else ""
    if not mensaje:
        await update.message.reply_text("Uso: /anuncio Tu mensaje aqui...")
        return

    usuarios = db.listar_usuarios()
    enviados = 0
    fallidos = 0

    await update.message.reply_text(f"Enviando anuncio a {len(usuarios)} usuarios...")

    for u in usuarios:
        try:
            await context.bot.send_message(
                chat_id=u["user_id"],
                text=f"📢 <b>Anuncio de aBOTgado:</b>\n\n{mensaje}",
                parse_mode="HTML"
            )
            enviados += 1
            await asyncio.sleep(0.1)
        except Exception:
            fallidos += 1

    await update.message.reply_text(
        f"Anuncio enviado.\nRecibido: {enviados}\nFallidos: {fallidos}"
    )


async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envía la base de datos SQLite como archivo por Telegram."""
    if not es_admin(update.effective_user.id):
        return
    import shutil
    from datetime import datetime as _dt
    db_path = config.SQLITE_DB_FILE
    if not os.path.exists(db_path):
        await update.message.reply_text("No se encontró la base de datos.")
        return
    # Copiar para no enviar archivo en uso (WAL mode)
    timestamp = _dt.now().strftime("%Y%m%d_%H%M")
    backup_path = f"{db_path}.backup_{timestamp}"
    try:
        shutil.copy2(db_path, backup_path)
        with open(backup_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"abotgado_backup_{timestamp}.db",
                caption=f"Backup de la DB — {timestamp}"
            )
    except Exception as e:
        await update.message.reply_text(f"Error creando backup: {e}")
    finally:
        try:
            os.remove(backup_path)
        except Exception:
            pass


async def cmd_usuarios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        return
    usuarios = db.listar_usuarios()
    if not usuarios:
        await update.message.reply_text("No hay usuarios registrados.")
        return
    texto = f"👥 <b>{len(usuarios)} usuarios</b>\n\n"
    for u in usuarios[:20]:
        plan_info = config.PLANES.get(u["plan_id"], config.PLANES[0])
        extras = ""
        if u["bono_memoria"]:
            extras += " [MEM]"
        if u["docs_disponibles"] > 0:
            extras += f" [DOC:{u['docs_disponibles']}]"
        # Mostrar expiración si es tester
        if u["plan_id"] == config.PLAN_TESTER and u["tester_expira"]:
            extras += f" exp:{u['tester_expira']}"
        texto += (f"{plan_info['icono']} {u['nombre']} (@{u['username']}) "
                  f"— ID: <code>{u['user_id']}</code> — hoy: {u['consultas_hoy']}{extras}\n")
    await enviar_respuesta(update.message, texto)


async def cmd_plan_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/plan_add <ID> [dias] — Suma días al plan Pionero (default: 7)."""
    if not es_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Uso: /plan_add <ID o @username> [dias]\nDefault: +7 dias")
        return
    ids, errores = resolver_targets(context.args[:1])
    dias = 7
    if len(context.args) > 1:
        try:
            dias = int(context.args[1])
        except ValueError:
            await update.message.reply_text("Los dias deben ser un numero.")
            return
    resultado = []
    for uid in ids:
        db.extender_tester(uid, dias=dias)
        expira = db.obtener_expiracion_tester(uid)
        resultado.append(f"+{dias}d Pionero para {uid} (expira: {expira})")
    for err in errores:
        resultado.append(f"No encontrado: {err}")
    await update.message.reply_text("\n".join(resultado))


async def cmd_plan_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/plan_del <ID> [dias] — Quita días al plan Pionero (default: 7). Si llega a 0, pasa a Gratis."""
    if not es_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Uso: /plan_del <ID o @username> [dias]\nDefault: -7 dias")
        return
    ids, errores = resolver_targets(context.args[:1])
    dias = 7
    if len(context.args) > 1:
        try:
            dias = int(context.args[1])
        except ValueError:
            await update.message.reply_text("Los dias deben ser un numero.")
            return
    resultado = []
    for uid in ids:
        db.extender_tester(uid, dias=-dias)
        expira = db.obtener_expiracion_tester(uid)
        if expira and expira <= date.today().isoformat():
            db.desactivar_premium(uid)
            resultado.append(f"Pionero expirado para {uid} → Gratis")
        else:
            resultado.append(f"-{dias}d Pionero para {uid} (expira: {expira})")
    for err in errores:
        resultado.append(f"No encontrado: {err}")
    await update.message.reply_text("\n".join(resultado))


# ─── HANDLERS DE DOCUMENTOS ─────────────────────────────────────────────────

async def cmd_documento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Documentos desactivados temporalmente
    if not config.DOCS_HABILITADOS:
        await enviar_respuesta(
            update.message,
            "📄 <b>Documentos Legales</b>\n\n"
            "Esta funcion estara disponible proximamente.\n"
            "Estamos preparando plantillas revisadas por abogados.\n\n"
            "Te avisaremos cuando este listo!"
        )
        return

    try:
        user_id = update.effective_user.id
        db.registrar_usuario(user_id, update.effective_user.first_name,
                             update.effective_user.username or "")

        docs = db.docs_disponibles(user_id)
        if docs <= 0:
            await enviar_respuesta(
                update.message,
                "<b>Generador de Documentos</b>\n\n"
                "No tienes documentos disponibles.\n\n"
                "Escribe /estado para ver tu plan actual."
            )
            return

        if context.args:
            opcion = context.args[0].strip()
            primera_pregunta = documentos.iniciar_documento(user_id, opcion)
            if primera_pregunta:
                await enviar_respuesta(update.message, primera_pregunta)
                return

        documentos.marcar_menu_pendiente(user_id)
        menu = documentos.listar_plantillas()
        await enviar_respuesta(
            update.message,
            "<b>Generador de Documentos</b>\n\n"
            "Elige el documento que necesitas:\n\n"
            f"{menu}\n\n"
            "Responde con el <b>numero</b> del documento (1-5).\n"
            "Escribe /cancelar para salir."
        )
    except Exception as e:
        logger.error(f"Error en cmd_documento: {e}", exc_info=True)
        await update.message.reply_text(f"Error: {e}")


async def cmd_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        # También cancelar feedback/soporte/registro pendiente
        feedback_pendiente.discard(user_id)
        soporte_pendiente.discard(user_id)
        if user_id in registro_abogado:
            del registro_abogado[user_id]
        if user_id in esperando_ley:
            del esperando_ley[user_id]
        msg = documentos.cancelar_documento(user_id)
        await update.message.reply_text(msg)
    except Exception as e:
        logger.error(f"Error en cmd_cancelar: {e}", exc_info=True)
        await update.message.reply_text(f"Error: {e}")


# ─── DEBUG (ADMIN) ─────────────────────────────────────────────────────────

async def cmd_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Diagnóstico del pipeline de búsqueda para una consulta."""
    if not es_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Uso: /debug <consulta>\nEj: /debug Mi vecino puso un gimnasio y pone música alta")
        return

    consulta = " ".join(context.args)
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    resultado = await asyncio.to_thread(busqueda.debug_busqueda, consulta)

    # Dividir si es muy largo
    if len(resultado) > 4096:
        for i in range(0, len(resultado), 4096):
            await update.message.reply_text(resultado[i:i+4096])
    else:
        await update.message.reply_text(resultado)


# ─── DIRECTORIO DE ABOGADOS (ADMIN) ────────────────────────────────────────

PASOS_ABOGADO = [
    ("nombre",        "📝 <b>Paso 1/6</b> — Nombre completo del abogado:\n\n<i>Ej: Abg. Juan Pérez</i>"),
    ("cedula",        "🪪 <b>Paso 2/6</b> — Cédula de identidad:\n\n<i>Ej: V-12345678</i>"),
    ("inpreabogado",  "📋 <b>Paso 3/6</b> — Número de INPREABOGADO:\n\n<i>Ej: 185432</i>"),
    ("especialidad",  "⚖️ <b>Paso 4/6</b> — Especialidad:\n\n"
                      + "\n".join(f"  • {e}" for e in db.ESPECIALIDADES_VALIDAS)
                      + "\n\n<i>Escribe una o varias separadas por coma</i>"),
    ("telefono",      "📱 <b>Paso 5/6</b> — Teléfono de contacto:\n\n<i>Ej: +58 412-1234567</i>"),
    ("estado",        "📍 <b>Paso 6/6</b> — Estado/Ciudad:\n\n<i>Ej: Caracas, Zulia, Carabobo</i>"),
]


async def cmd_add_abogado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el flujo conversacional para registrar un abogado."""
    user_id = update.effective_user.id
    if not es_admin(user_id):
        return

    registro_abogado[user_id] = {"paso": 0, "datos": {}}
    _, mensaje = PASOS_ABOGADO[0]
    await enviar_respuesta(
        update.message,
        "👨‍⚖️ <b>Registrar abogado en el directorio</b>\n\n"
        f"{mensaje}\n\n"
        "Escribe /cancelar para salir."
    )


def procesar_paso_abogado(user_id: int, texto: str) -> tuple[str | None, bool]:
    """Procesa un paso del registro de abogado.
    Retorna (mensaje_siguiente, completado)."""
    if user_id not in registro_abogado:
        return None, False

    reg = registro_abogado[user_id]

    # Si ya preguntamos las notas, este texto son las notas
    if reg.get("esperando_notas"):
        notas = texto.strip() if texto.strip() != "-" else ""
        datos = reg["datos"]

        abogado_id = db.agregar_abogado(
            nombre=datos["nombre"],
            cedula=datos["cedula"],
            inpreabogado=datos["inpreabogado"],
            especialidad=datos["especialidad"],
            telefono=datos["telefono"],
            estado=datos["estado"],
            notas=notas,
        )

        del registro_abogado[user_id]

        resumen = (
            f"✅ <b>Abogado registrado</b> (ID: {abogado_id})\n\n"
            f"👤 {datos['nombre']}\n"
            f"🪪 C.I.: {datos['cedula']}\n"
            f"📋 INPREABOGADO: {datos['inpreabogado']}\n"
            f"⚖️ {datos['especialidad']}\n"
            f"📱 {datos['telefono']}\n"
            f"📍 {datos['estado']}\n"
        )
        if notas:
            resumen += f"📝 {notas}\n"

        return resumen, True

    paso_actual = reg["paso"]
    campo, _ = PASOS_ABOGADO[paso_actual]

    # Guardar dato del paso actual
    reg["datos"][campo] = texto.strip()
    reg["paso"] += 1

    # ¿Hay más pasos?
    if reg["paso"] < len(PASOS_ABOGADO):
        _, siguiente_msg = PASOS_ABOGADO[reg["paso"]]
        return siguiente_msg, False

    # Todos los pasos completados — preguntar por notas
    reg["esperando_notas"] = True
    return ("📝 <b>Notas adicionales</b> (opcional):\n\n"
            "<i>Email, horario, precio de consulta, idiomas, etc.\n"
            "Escribe \"-\" para omitir.</i>"), False


async def cmd_abogados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista abogados. Filtro opcional: /abogados penal o /abogados Caracas."""
    user_id = update.effective_user.id
    if not es_admin(user_id):
        return

    filtro = " ".join(context.args) if context.args else None

    # Intentar filtrar por especialidad o estado
    abogados = []
    if filtro:
        abogados = db.listar_abogados(especialidad=filtro)
        if not abogados:
            abogados = db.listar_abogados(estado=filtro)
    if not abogados:
        abogados = db.listar_abogados()

    total = db.contar_abogados()

    if not abogados:
        await enviar_respuesta(
            update.message,
            "👨‍⚖️ <b>Directorio de Abogados</b>\n\n"
            "No hay abogados registrados.\n"
            "Usa /add_abogado para agregar uno."
        )
        return

    texto = f"👨‍⚖️ <b>Directorio de Abogados</b> ({total} registrados)\n\n"

    for a in abogados:
        texto += (
            f"<b>#{a['id']}</b> — {a['nombre']}\n"
            f"  🪪 C.I.: {a['cedula']}\n"
            f"  📋 INPREABOGADO: {a['inpreabogado']}\n"
            f"  ⚖️ {a['especialidad']}\n"
            f"  📱 {a['telefono']}\n"
            f"  📍 {a['estado']}\n"
        )
        if a['notas']:
            texto += f"  📝 {a['notas']}\n"
        estado_txt = "🟢 Activo" if a['activo'] else "🔴 Inactivo"
        texto += f"  {estado_txt}\n\n"

    texto += "<i>/del_abogado ID — desactivar\n/activar_abogado ID — reactivar</i>"
    await enviar_respuesta(update.message, texto)


async def cmd_del_abogado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Desactiva un abogado por ID."""
    if not es_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Uso: /del_abogado <ID>")
        return
    try:
        abogado_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("El ID debe ser un número.")
        return

    abogado = db.obtener_abogado(abogado_id)
    if not abogado:
        await update.message.reply_text(f"No existe abogado con ID {abogado_id}.")
        return

    db.desactivar_abogado(abogado_id)
    await update.message.reply_text(f"🔴 Abogado #{abogado_id} ({abogado['nombre']}) desactivado.")


async def cmd_activar_abogado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reactiva un abogado por ID."""
    if not es_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Uso: /activar_abogado <ID>")
        return
    try:
        abogado_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("El ID debe ser un número.")
        return

    abogado = db.obtener_abogado(abogado_id)
    if not abogado:
        await update.message.reply_text(f"No existe abogado con ID {abogado_id}.")
        return

    db.activar_abogado(abogado_id)
    await update.message.reply_text(f"🟢 Abogado #{abogado_id} ({abogado['nombre']}) reactivado.")


# ─── HANDLER PRINCIPAL ──────────────────────────────────────────────────────

async def responder_consulta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = user.id
    pregunta = update.message.text

    if not pregunta or not pregunta.strip():
        return

    db.registrar_usuario(user_id, user.first_name, user.username or "")

    # ── Esperando nombre de ley (flujo "explícame artículo X") ───────────
    if user_id in esperando_ley:
        datos = esperando_ley.pop(user_id)
        num_art = datos["num_art"]
        ley_input = pregunta.strip()

        ley_real = busqueda.buscar_ley_por_alias(ley_input)
        if not ley_real:
            await enviar_respuesta(
                update.message,
                f"No reconozco la ley \"<b>{ley_input}</b>\".\n\n"
                "Usa /leyes para ver las leyes disponibles y sus alias.\n"
                "O escribe tu consulta nuevamente."
            )
            return

        arts = busqueda.buscar_articulo_en_db(ley_real, num_art)
        if not arts:
            await enviar_respuesta(
                update.message,
                f"No encontré el <b>Art. {num_art}</b> de <b>{ley_real}</b>.\n\n"
                "Puede que ese artículo no esté en mi base de datos."
            )
            return

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action="typing"
        )
        texto_art = arts[0]["texto"]
        if len(texto_art) > 3000:
            texto_art = texto_art[:3000] + "... [truncado]"
        explicacion = await asyncio.to_thread(
            busqueda.explicar_articulo, arts[0]["texto"], ley_real, num_art
        )
        respuesta = f"📖 <b>{ley_real}</b>\n<b>Artículo {num_art}</b>\n\n{texto_art}\n\n"
        if explicacion:
            respuesta += f"{'━' * 25}\n{explicacion}\n\n"
        respuesta += "<i>Usa /comparar para comparar con otro artículo.</i>"
        await enviar_respuesta(update.message, respuesta)
        return

    # ── Registro de abogado (flujo conversacional admin) ────────────────
    if user_id in registro_abogado:
        mensaje, completado = procesar_paso_abogado(user_id, pregunta)
        if mensaje:
            await enviar_respuesta(update.message, mensaje)
        return

    # ── Feedback pendiente ───────────────────────────────────────────────
    if user_id in feedback_pendiente:
        feedback_pendiente.discard(user_id)
        db.guardar_feedback(user_id, "comentario", pregunta)
        await update.message.reply_text("Gracias por tu opinion! Nos ayuda a mejorar.")
        await notificar_admins(context,
            f"💬 FEEDBACK de {user.first_name} (ID: {user_id}):\n{pregunta}")
        return

    # ── Soporte pendiente ────────────────────────────────────────────────
    if user_id in soporte_pendiente:
        soporte_pendiente.discard(user_id)
        db.guardar_ticket_soporte(user_id, pregunta)
        await update.message.reply_text("Mensaje enviado al equipo de soporte. Te responderemos pronto.")
        await notificar_admins(context,
            f"🆘 SOPORTE de {user.first_name} (@{user.username or 'N/A'}, ID: {user_id}):\n\n{pregunta}")
        return

    # ── Selección de menú de documentos ──────────────────────────────────
    if documentos.esperando_seleccion(user_id):
        resultado = documentos.procesar_seleccion_menu(user_id, pregunta.strip())
        if resultado:
            await enviar_respuesta(update.message, resultado)
        return

    # ── Llenando un documento ────────────────────────────────────────────
    if documentos.esta_en_documento(user_id):
        texto = pregunta.strip()
        respuesta_doc, ruta_archivo = documentos.procesar_respuesta(user_id, texto)

        if ruta_archivo:
            db.registrar_doc_usado(user_id)
            await enviar_respuesta(update.message, respuesta_doc)
            with open(ruta_archivo, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=os.path.basename(ruta_archivo),
                    caption="Documento generado por aBOTgado"
                )
            try:
                os.remove(ruta_archivo)
            except Exception:
                pass
        else:
            await enviar_respuesta(update.message, respuesta_doc)
        return

    # ── Filtrar comandos / escritos como texto (no admin) ────────────────
    if pregunta.startswith("/"):
        # Si es un comando admin escrito como texto, ignorar
        await update.message.reply_text(
            "Ese comando no existe o no tienes permiso.\n"
            "Usa /ayuda para ver los comandos disponibles."
        )
        return

    # ── Filtro de seguridad (bloquea inyección antes del LLM) ────────────
    if detectar_inyeccion(pregunta):
        logger.warning(f"Inyección bloqueada de user {user_id}: {pregunta[:80]}")
        await update.message.reply_text(RESPUESTA_INYECCION)
        return

    # ── Detección de "explícame el artículo X [de Y]" ────────────────────
    import re as _re
    pregunta_lower = busqueda.normalizar(pregunta)
    # Patrones: "explicame el articulo 5", "que dice el articulo 48 de la constitucion", "articulo 12"
    _pat_art = _re.search(
        r'(?:explicame|dime|que\s+dice|muestrame|dame|lee(?:me)?)\s+'
        r'(?:el\s+)?(?:articulo|art\.?)\s+(\d+)'
        r'(?:\s+(?:de(?:l|\s+la|\s+el|\s+los|\s+las)?\s+)?(.+))?',
        pregunta_lower
    )
    if not _pat_art:
        # También "artículo 5 de la constitución" sin verbo previo
        _pat_art = _re.search(
            r'^(?:el\s+)?(?:articulo|art\.?)\s+(\d+)'
            r'(?:\s+(?:de(?:l|\s+la|\s+el|\s+los|\s+las)?\s+)?(.+))?$',
            pregunta_lower.strip()
        )

    if _pat_art:
        _num_art = int(_pat_art.group(1))
        _ley_texto = (_pat_art.group(2) or "").strip().rstrip("?.,!")

        if _ley_texto:
            # Tiene ley → buscar directamente
            _ley_real = busqueda.buscar_ley_por_alias(_ley_texto)
            if _ley_real:
                _arts = busqueda.buscar_articulo_en_db(_ley_real, _num_art)
                if _arts:
                    await context.bot.send_chat_action(
                        chat_id=update.effective_chat.id, action="typing"
                    )
                    _texto_art = _arts[0]["texto"]
                    if len(_texto_art) > 3000:
                        _texto_art = _texto_art[:3000] + "... [truncado]"
                    _explicacion = await asyncio.to_thread(
                        busqueda.explicar_articulo, _arts[0]["texto"], _ley_real, _num_art
                    )
                    _resp = f"📖 <b>{_ley_real}</b>\n<b>Artículo {_num_art}</b>\n\n{_texto_art}\n\n"
                    if _explicacion:
                        _resp += f"{'━' * 25}\n{_explicacion}\n\n"
                    _resp += "<i>Usa /comparar para comparar con otro artículo.</i>"
                    db.registrar_consulta(user_id)
                    await enviar_respuesta(update.message, _resp)
                    return
                else:
                    await enviar_respuesta(
                        update.message,
                        f"No encontré el <b>Art. {_num_art}</b> de <b>{_ley_real}</b>.\n\n"
                        "Puede que ese artículo no esté en mi base de datos."
                    )
                    return
        else:
            # No tiene ley → preguntar
            esperando_ley[user_id] = {"num_art": _num_art}
            await enviar_respuesta(
                update.message,
                f"📖 ¿De qué ley quieres el <b>Artículo {_num_art}</b>?\n\n"
                "Escribe el nombre o alias de la ley.\n"
                "Ej: <code>constitución</code>, <code>LOTTT</code>, <code>código penal</code>\n\n"
                "Usa /leyes para ver todas las disponibles.\n"
                "Usa /cancelar para cancelar."
            )
            return

    # ── Consulta jurídica normal ─────────────────────────────────────────
    logger.info(f"Consulta recibida del usuario ID: {user_id}")

    if not db.puede_consultar(user_id):
        plan_info = db.info_plan(user_id)
        limite = plan_info["consultas"]
        await enviar_respuesta(
            update.message,
            f"⏰ <b>Limite diario alcanzado</b>\n\n"
            f"Has usado tus {limite} consultas de hoy.\n\n"
            "Escribe /referir para invitar amigos y obtener\n"
            "Plan Pionero gratis por 2 semanas.\n\n"
            "Escribe /estado para ver tu plan."
        )
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    con_memoria = db.tiene_memoria(user_id)
    historial = db.cargar_historial(user_id) if con_memoria else None

    resultado = await asyncio.to_thread(busqueda.buscar_y_responder, pregunta, historial, user_id)
    respuesta = resultado["respuesta"]
    temas = resultado.get("temas", [])
    confianza = resultado.get("confianza", "n/a")

    db.registrar_consulta(user_id)
    if con_memoria:
        db.guardar_mensaje(user_id, "user", pregunta)
        db.guardar_mensaje(user_id, "assistant", respuesta)

    ultima_respuesta[user_id] = {"pregunta": pregunta, "respuesta": respuesta}

    # Alerta al admin: consulta sin tema detectado (respuesta de baja confianza)
    if confianza == "baja" and not es_admin(user_id):
        await notificar_admins(context,
            f"⚠️ CONSULTA SIN TEMA\n"
            f"Usuario: {user.first_name} (@{user.username or 'N/A'}, ID: {user_id})\n"
            f"Pregunta: {pregunta[:200]}\n"
            f"Confianza: {confianza}")

    restantes = db.consultas_restantes(user_id)
    if restantes != -1 and restantes <= 1:
        respuesta += f"\n\n<i>Consultas restantes hoy: {restantes}</i>"

    # Botones de feedback
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👍", callback_data=f"fb_up_{user_id}"),
         InlineKeyboardButton("👎", callback_data=f"fb_down_{user_id}")]
    ])

    texto_formateado = busqueda.formatear_respuesta(respuesta)
    if len(texto_formateado) > 4096:
        # Enviar en partes, botones solo en el último
        for i in range(0, len(texto_formateado), 4096):
            parte = texto_formateado[i:i+4096]
            es_ultima = (i + 4096 >= len(texto_formateado))
            try:
                await update.message.reply_text(
                    parte, parse_mode="HTML",
                    reply_markup=keyboard if es_ultima else None)
            except Exception:
                await update.message.reply_text(
                    parte,
                    reply_markup=keyboard if es_ultima else None)
    else:
        try:
            await update.message.reply_text(
                texto_formateado, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            await update.message.reply_text(
                texto_formateado, reply_markup=keyboard)


# ─── FEEDBACK BUTTONS ────────────────────────────────────────────────────────

async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones de 👍/👎 después de cada respuesta."""
    query = update.callback_query
    logger.info(f"Feedback recibido: {query.data} de user {query.from_user.id}")

    try:
        data = query.data  # fb_up_123456 o fb_down_123456
        partes = data.split("_")
        if len(partes) < 3:
            await query.answer()
            return

        tipo = partes[1]  # "up" o "down"
        try:
            feedback_user_id = int(partes[2])
        except ValueError:
            await query.answer()
            return

        # Solo el usuario que hizo la consulta puede dar feedback
        if query.from_user.id != feedback_user_id:
            await query.answer("Este botón es para el usuario que hizo la consulta.")
            return

        # Obtener la pregunta/respuesta del usuario
        datos = ultima_respuesta.get(feedback_user_id, {})
        pregunta_original = datos.get("pregunta", "")

        if tipo == "up":
            db.guardar_feedback(feedback_user_id, "positivo", pregunta_original[:200])
            await query.answer("👍 ¡Gracias por tu feedback!")
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
        elif tipo == "down":
            db.guardar_feedback(feedback_user_id, "negativo", pregunta_original[:200])
            await query.answer("👎 Gracias. Revisaremos esta respuesta.")
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            # Notificar admin sobre feedback negativo
            resp_texto = datos.get("respuesta", "")[:300]
            await notificar_admins(context,
                f"👎 FEEDBACK NEGATIVO\n"
                f"Usuario: {query.from_user.first_name} "
                f"(@{query.from_user.username or 'N/A'}, ID: {feedback_user_id})\n"
                f"Pregunta: {pregunta_original[:200]}\n"
                f"Respuesta (inicio): {resp_texto}")
        else:
            await query.answer()
    except Exception as e:
        logger.error(f"Error en handle_feedback: {e}")
        try:
            await query.answer("Error procesando feedback")
        except Exception:
            pass


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    if not config.GROQ_API_KEY:
        print("GROQ_API_KEY no configurada. Revisa tu archivo .env")
        return
    if not config.TELEGRAM_TOKEN:
        print("TELEGRAM_TOKEN no configurado. Revisa tu archivo .env")
        return

    db.inicializar_db()

    print(f"aBOTgado iniciando...")
    print(f"   LLM:       {config.LLM_MODEL} via Groq")
    print(f"   Busqueda:  Clave + BM25 + Embeddings + Diversidad")
    print(f"   Articulos: {busqueda.coleccion.count()}")
    print(f"   Bot corriendo. Ctrl+C para detener.\n")

    app = Application.builder().token(config.TELEGRAM_TOKEN).build()

    # Notificar admins que el bot arrancó
    async def post_init(application):
        usuarios = db.listar_usuarios()
        for admin_id in config.ADMIN_IDS:
            try:
                await application.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        f"✅ aBOTgado iniciado\n"
                        f"Articulos: {busqueda.coleccion.count()}\n"
                        f"Usuarios: {len(usuarios)}\n"
                        f"DB: {config.SQLITE_DB_FILE}"
                    )
                )
            except Exception:
                pass

    app.post_init = post_init

    # Comandos de usuario
    app.add_handler(CommandHandler("start",           start))
    app.add_handler(CommandHandler("ayuda",           ayuda))
    app.add_handler(CommandHandler("ping",            cmd_ping))
    app.add_handler(CommandHandler("leyes",           leyes_disponibles))
    app.add_handler(CommandHandler("ley",             cmd_ley))
    app.add_handler(CommandHandler("comparar",        cmd_comparar))
    app.add_handler(CommandHandler("estado",          estado))
    app.add_handler(CommandHandler("nuevo",           nuevo))
    app.add_handler(CommandHandler("documento",       cmd_documento))
    app.add_handler(CommandHandler("cancelar",        cmd_cancelar))
    app.add_handler(CommandHandler("stats",           cmd_stats))
    app.add_handler(CommandHandler("opinion",         cmd_opinion))
    app.add_handler(CommandHandler("guardar",         cmd_guardar))
    app.add_handler(CommandHandler("mis_consultas",   cmd_mis_consultas))
    app.add_handler(CommandHandler("ver_guardado",    cmd_ver_guardado))
    app.add_handler(CommandHandler("borrar_guardados",cmd_borrar_guardados))
    app.add_handler(CommandHandler("referir",         cmd_referir))
    app.add_handler(CommandHandler("soporte",         cmd_soporte))

    # Comandos de admin
    app.add_handler(CommandHandler("premium_on",      cmd_premium_on))
    app.add_handler(CommandHandler("premium_off",     cmd_premium_off))
    app.add_handler(CommandHandler("tester",          cmd_tester))
    app.add_handler(CommandHandler("regalar_doc",     cmd_regalar_doc))
    app.add_handler(CommandHandler("regalar_memoria", cmd_regalar_memoria))
    app.add_handler(CommandHandler("anuncio",         cmd_anuncio))
    app.add_handler(CommandHandler("stats_admin",     cmd_stats_admin))
    app.add_handler(CommandHandler("feedback",        cmd_feedback_admin))
    app.add_handler(CommandHandler("responder",       cmd_responder_soporte))
    app.add_handler(CommandHandler("mensaje",         cmd_mensaje_directo))
    app.add_handler(CommandHandler("usuarios",        cmd_usuarios))
    app.add_handler(CommandHandler("backup",          cmd_backup))
    app.add_handler(CommandHandler("plan_add",        cmd_plan_add))
    app.add_handler(CommandHandler("plan_del",        cmd_plan_del))
    app.add_handler(CommandHandler("debug",           cmd_debug))
    app.add_handler(CommandHandler("add_abogado",     cmd_add_abogado))
    app.add_handler(CommandHandler("abogados",        cmd_abogados))
    app.add_handler(CommandHandler("del_abogado",     cmd_del_abogado))
    app.add_handler(CommandHandler("activar_abogado", cmd_activar_abogado))

    # Feedback buttons (👍/👎)
    app.add_handler(CallbackQueryHandler(handle_feedback))

    # Mensajes normales
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        responder_consulta
    ))

    # Error handler global — envía errores al admin
    async def error_handler(update, context):
        logger.error(f"Error: {context.error}", exc_info=context.error)
        for admin_id in config.ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"🔴 ERROR:\n{type(context.error).__name__}: {context.error}"
                )
            except Exception:
                pass

    app.add_error_handler(error_handler)

    app.run_polling()


if __name__ == "__main__":
    main()
