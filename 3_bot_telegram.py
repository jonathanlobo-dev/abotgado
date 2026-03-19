"""
aBOTgado - Bot de Telegram
============================
Handlers de comandos y lógica del bot.
El motor de búsqueda está en busqueda.py
"""

import logging
import asyncio
import os
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
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
                    db.regalar_documento(user_id, 1)
                    db.regalar_documento(referidor_id, 1)
                    try:
                        await context.bot.send_message(
                            chat_id=referidor_id,
                            text=f"🎉 Tu amigo {user.first_name} se registro con tu link. Gracias por compartir aBOTgado!",
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
    s = db.stats_globales()

    texto = (
        "📊 <b>Estadisticas globales</b>\n\n"
        f"Total usuarios: <b>{s['total_usuarios']}</b>\n"
        f"Consultas hoy: <b>{s['consultas_hoy']}</b>\n"
        f"Consultas esta semana: <b>{s['consultas_semana']}</b>\n"
        f"Consultas este mes: <b>{s['consultas_mes']}</b>\n\n"
    )

    texto += "<b>Por plan:</b>\n"
    for plan_id, count in s["por_plan"].items():
        info = config.PLANES.get(plan_id, config.PLANES[0])
        texto += f"  {info['icono']} {info['nombre']}: {count}\n"

    if s["usuario_mas_activo"]:
        texto += f"\nMas activo (semana): ID {s['usuario_mas_activo'][0]} ({s['usuario_mas_activo'][1]} consultas)"

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
        "Comparte este link para que tus amigos\n"
        "tambien tengan acceso a consultas legales.\n\n"
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
        await update.message.reply_text("Uso: /premium_on <user_id>")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("El user_id debe ser un numero.")
        return
    db.activar_premium(target_id)
    await update.message.reply_text(f"Premium activado para {target_id}")


async def cmd_premium_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Uso: /premium_off <user_id>")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("El user_id debe ser un numero.")
        return
    db.desactivar_premium(target_id)
    await update.message.reply_text(f"Premium desactivado para {target_id}")


async def cmd_tester(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Uso: /tester <user_id>")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("El user_id debe ser un numero.")
        return
    db.cambiar_plan(target_id, config.PLAN_TESTER)
    await update.message.reply_text(f"Plan Pionero activado para {target_id}")


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
        await update.message.reply_text("Uso: /regalar_memoria <user_id>")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("El user_id debe ser un numero.")
        return

    db.activar_bono_memoria(target_id)
    await update.message.reply_text(f"Memoria activada para {target_id}")

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text="🎉 <b>Memoria de conversacion activada!</b>\n\n"
                 "Ahora puedo recordar nuestras conversaciones anteriores.\n"
                 "Escribe /estado para ver tus beneficios.",
            parse_mode="HTML"
        )
    except Exception:
        pass


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
        texto += (f"{plan_info['icono']} {u['nombre']} (@{u['username']}) "
                  f"— ID: <code>{u['user_id']}</code> — hoy: {u['consultas_hoy']}{extras}\n")
    await enviar_respuesta(update.message, texto)


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
        # También cancelar feedback/soporte pendiente
        feedback_pendiente.discard(user_id)
        soporte_pendiente.discard(user_id)
        msg = documentos.cancelar_documento(user_id)
        await update.message.reply_text(msg)
    except Exception as e:
        logger.error(f"Error en cmd_cancelar: {e}", exc_info=True)
        await update.message.reply_text(f"Error: {e}")


# ─── HANDLER PRINCIPAL ──────────────────────────────────────────────────────

async def responder_consulta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = user.id
    pregunta = update.message.text

    if not pregunta or not pregunta.strip():
        return

    db.registrar_usuario(user_id, user.first_name, user.username or "")

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

    # ── Consulta jurídica normal ─────────────────────────────────────────
    logger.info(f"Consulta recibida del usuario ID: {user_id}")

    if not db.puede_consultar(user_id):
        plan_info = db.info_plan(user_id)
        limite = plan_info["consultas"]
        await enviar_respuesta(
            update.message,
            f"⏰ <b>Limite diario alcanzado</b>\n\n"
            f"Has usado tus {limite} consultas de hoy.\n\n"
            "<b>Plan Pionero</b> ($2/mes): 5 consultas + memoria + 1 doc/mes\n"
            "<b>Plan Premium</b> ($5/mes): ilimitado + memoria + docs ilimitados\n\n"
            "Escribe /estado para ver tu plan."
        )
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    con_memoria = db.tiene_memoria(user_id)
    historial = db.cargar_historial(user_id) if con_memoria else None

    respuesta = await asyncio.to_thread(busqueda.buscar_y_responder, pregunta, historial, user_id)

    db.registrar_consulta(user_id)
    if con_memoria:
        db.guardar_mensaje(user_id, "user", pregunta)
        db.guardar_mensaje(user_id, "assistant", respuesta)

    ultima_respuesta[user_id] = {"pregunta": pregunta, "respuesta": respuesta}

    restantes = db.consultas_restantes(user_id)
    if restantes != -1 and restantes <= 1:
        respuesta += f"\n\n<i>Consultas restantes hoy: {restantes}</i>"

    await enviar_respuesta(update.message, respuesta)


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

    # Comandos de usuario
    app.add_handler(CommandHandler("start",           start))
    app.add_handler(CommandHandler("ayuda",           ayuda))
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

    # Mensajes normales
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        responder_consulta
    ))

    app.run_polling()


if __name__ == "__main__":
    main()
