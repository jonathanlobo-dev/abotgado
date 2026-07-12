"""Endpoints de administración para el panel web (dashboard del dueño).

Seguridad: TODOS los endpoints exigen el header X-Admin-Key == env ADMIN_KEY.
Si ADMIN_KEY no está seteada en el entorno, los endpoints quedan deshabilitados
(403 siempre) — así un deploy sin la variable no expone nada.

Se monta en api.py con:  app.include_router(admin_router)
"""
import logging
import os
import time

import requests
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel

import config
import db as database

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/admin", tags=["admin"])


def _check(key: str) -> None:
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key or key != admin_key:
        raise HTTPException(status_code=403, detail="No autorizado")


def _tg_enviar(chat_id: int, texto: str) -> bool:
    """Envía un mensaje por Telegram (independiente del bot en ejecución)."""
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": texto, "parse_mode": "HTML"},
            timeout=15,
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"admin: fallo enviando a {chat_id}: {e}")
        return False


# ─── Resumen ─────────────────────────────────────────────────────────────────

@admin_router.get("/resumen")
def resumen(x_admin_key: str = Header("")):
    _check(x_admin_key)
    su = database.stats_usuarios()
    sc = database.obtener_stats()
    fb = database.contar_feedback()
    return {
        "usuarios": su,
        "consultas": {"hoy": sc["consultas_hoy"], "7d": sc["consultas_7d"],
                      "total": sc["consultas_total"]},
        "temas_top": sc.get("temas_top", [])[:8],
        "abogados_activos": database.contar_abogados(solo_activos=True),
        "feedback": fb,
    }


# ─── Usuarios ────────────────────────────────────────────────────────────────

@admin_router.get("/usuarios")
def usuarios(x_admin_key: str = Header("")):
    _check(x_admin_key)
    return database.listar_usuarios()


@admin_router.get("/usuarios/{user_id}")
def usuario_detalle(user_id: int, x_admin_key: str = Header("")):
    _check(x_admin_key)
    u = database.obtener_usuario(user_id)
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    return {
        "usuario": u,
        "stats": database.stats_usuario(user_id),
        "historial": database.historial_consultas_usuario(user_id, 20),
    }


class PlanReq(BaseModel):
    plan_id: int  # 0 Gratis · 1 Pionero · 2 Premium


@admin_router.post("/usuarios/{user_id}/plan")
def cambiar_plan(user_id: int, req: PlanReq, x_admin_key: str = Header("")):
    _check(x_admin_key)
    if req.plan_id not in config.PLANES:
        raise HTTPException(400, f"plan_id inválido. Opciones: {list(config.PLANES)}")
    database.cambiar_plan(user_id, req.plan_id)
    return {"ok": True, "user_id": user_id, "plan": config.PLANES[req.plan_id]["nombre"]}


class RegaloReq(BaseModel):
    tipo: str            # consultas | doc | memoria | tester
    cantidad: int = 5    # consultas/docs; días para tester


@admin_router.post("/usuarios/{user_id}/regalo")
def regalo(user_id: int, req: RegaloReq, x_admin_key: str = Header("")):
    _check(x_admin_key)
    if req.tipo == "consultas":
        database.regalar_consultas(user_id, req.cantidad)
    elif req.tipo == "doc":
        database.regalar_documento(user_id, req.cantidad)
    elif req.tipo == "memoria":
        database.activar_bono_memoria(user_id)
    elif req.tipo == "tester":
        database.activar_tester_temporal(user_id, req.cantidad)
    else:
        raise HTTPException(400, "tipo inválido: consultas | doc | memoria | tester")
    return {"ok": True, "user_id": user_id, "tipo": req.tipo, "cantidad": req.cantidad}


# ─── Consultas (log de preguntas/respuestas) ────────────────────────────────

@admin_router.get("/consultas")
def consultas(dias: int = 7, x_admin_key: str = Header("")):
    _check(x_admin_key)
    return database.exportar_consultas_log(max(1, min(dias, 90)))


# ─── Abogados ────────────────────────────────────────────────────────────────

@admin_router.get("/abogados")
def abogados(x_admin_key: str = Header("")):
    _check(x_admin_key)
    return database.listar_abogados_admin(incluir_inactivos=True)


class ActivoReq(BaseModel):
    activo: bool


@admin_router.post("/abogados/{abogado_id}/activo")
def abogado_activo(abogado_id: int, req: ActivoReq, x_admin_key: str = Header("")):
    _check(x_admin_key)
    ok = (database.activar_abogado(abogado_id) if req.activo
          else database.desactivar_abogado(abogado_id))
    if not ok:
        raise HTTPException(404, "Abogado no encontrado")
    return {"ok": True, "abogado_id": abogado_id, "activo": req.activo}


@admin_router.get("/solicitudes")
def solicitudes(estado: str = "pendiente", x_admin_key: str = Header("")):
    _check(x_admin_key)
    return database.listar_solicitudes(estado_solicitud=estado)


# ─── Feedback ────────────────────────────────────────────────────────────────

@admin_router.get("/feedback")
def feedback(estado: str | None = None, x_admin_key: str = Header("")):
    _check(x_admin_key)
    return database.listar_feedback_tickets(estado=estado)


# ─── Mensajería ──────────────────────────────────────────────────────────────

class MensajeReq(BaseModel):
    user_id: int
    texto: str


@admin_router.post("/mensaje")
def mensaje_directo(req: MensajeReq, x_admin_key: str = Header("")):
    _check(x_admin_key)
    if not req.texto.strip():
        raise HTTPException(400, "Texto vacío")
    ok = _tg_enviar(req.user_id, f"📩 <b>Mensaje del equipo aBOTgado</b>\n\n{req.texto}")
    return {"ok": ok, "user_id": req.user_id}


class AnuncioReq(BaseModel):
    texto: str


def _broadcast(texto: str) -> None:
    usuarios = database.listar_usuarios()
    enviados = 0
    for u in usuarios:
        if _tg_enviar(u["user_id"], f"📢 <b>Anuncio de aBOTgado</b>\n\n{texto}"):
            enviados += 1
        time.sleep(0.08)  # respetar el rate limit de Telegram (~30 msg/s global)
    logger.info(f"admin: anuncio enviado a {enviados}/{len(usuarios)} usuarios")


@admin_router.post("/anuncio")
def anuncio(req: AnuncioReq, background: BackgroundTasks, x_admin_key: str = Header("")):
    _check(x_admin_key)
    if not req.texto.strip():
        raise HTTPException(400, "Texto vacío")
    total = len(database.listar_usuarios())
    background.add_task(_broadcast, req.texto)
    return {"ok": True, "encolado_para": total}
