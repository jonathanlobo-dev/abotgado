"""
aBOTgado - Base de datos local (SQLite)
========================================
Sistema de niveles:
  - Plan 0: Gratis (3 consultas/día, sin memoria, sin docs)
  - Plan 1: Tester/Pionero (5 consultas/día, memoria, 1 doc/mes)
  - Plan 2: Premium (ilimitado, memoria, docs ilimitados)
Feature flags:
  - bono_memoria: activa memoria sin cambiar de plan
  - docs_disponibles: documentos regalados bajo demanda
"""

import sqlite3
from datetime import date, datetime
import config


def get_db():
    """Crea una conexión segura con timeout y modo WAL para alta concurrencia."""
    con = sqlite3.connect(config.SQLITE_DB_FILE, timeout=10.0)
    con.execute("PRAGMA journal_mode=WAL;")
    return con


# ─── INICIALIZACIÓN ───────────────────────────────────────────────────────────

def inicializar_db():
    """Crea las tablas si no existen y migra columnas nuevas."""
    with get_db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                user_id     INTEGER PRIMARY KEY,
                nombre      TEXT,
                username    TEXT,
                premium     INTEGER DEFAULT 0,
                fecha_reg   TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS consultas_diarias (
                user_id  INTEGER,
                fecha    TEXT,
                cantidad INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, fecha)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS historial (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER,
                rol       TEXT,
                mensaje   TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS ultimo_contexto (
                user_id   INTEGER PRIMARY KEY,
                contexto  TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── Migración: agregar columnas nuevas si no existen ──────────────
        columnas = {r[1] for r in con.execute("PRAGMA table_info(usuarios)").fetchall()}

        if "plan_id" not in columnas:
            con.execute("ALTER TABLE usuarios ADD COLUMN plan_id INTEGER DEFAULT 0")
            # Migrar: premium=1 → plan_id=2
            con.execute("UPDATE usuarios SET plan_id = 2 WHERE premium = 1")

        if "bono_memoria" not in columnas:
            con.execute("ALTER TABLE usuarios ADD COLUMN bono_memoria INTEGER DEFAULT 0")

        if "docs_disponibles" not in columnas:
            con.execute("ALTER TABLE usuarios ADD COLUMN docs_disponibles INTEGER DEFAULT 0")

        if "docs_usados_mes" not in columnas:
            con.execute("ALTER TABLE usuarios ADD COLUMN docs_usados_mes INTEGER DEFAULT 0")

        if "mes_docs" not in columnas:
            con.execute("ALTER TABLE usuarios ADD COLUMN mes_docs TEXT DEFAULT ''")

        if "referido_por" not in columnas:
            con.execute("ALTER TABLE usuarios ADD COLUMN referido_por INTEGER DEFAULT 0")

        if "referidos_count" not in columnas:
            con.execute("ALTER TABLE usuarios ADD COLUMN referidos_count INTEGER DEFAULT 0")

        if "tester_expira" not in columnas:
            con.execute("ALTER TABLE usuarios ADD COLUMN tester_expira TEXT DEFAULT ''")

        # ── Tablas nuevas ────────────────────────────────────────────────
        con.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER,
                tipo      TEXT,
                comentario TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS favoritos (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER,
                pregunta  TEXT,
                respuesta TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS soporte (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER,
                mensaje   TEXT,
                direccion TEXT DEFAULT 'user_to_admin',
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

    # Log de ruta para diagnóstico
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"DB inicializada en: {config.SQLITE_DB_FILE}")

    # Verificar cuántos usuarios hay
    with get_db() as con:
        count = con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        logger.info(f"Usuarios en DB: {count}")

    # Auto-setup: admins siempre son Premium
    _setup_admins()


def _setup_admins():
    """Asegura que todos los admin IDs estén registrados como Premium."""
    with get_db() as con:
        for admin_id in config.ADMIN_IDS:
            cur = con.execute("SELECT plan_id FROM usuarios WHERE user_id = ?", (admin_id,))
            fila = cur.fetchone()
            if fila:
                # Admin existe, asegurar Premium
                if fila[0] != config.PLAN_PREMIUM:
                    con.execute(
                        "UPDATE usuarios SET plan_id = ?, premium = 1 WHERE user_id = ?",
                        (config.PLAN_PREMIUM, admin_id)
                    )
            else:
                # Admin no existe aún → crearlo como Premium
                con.execute(
                    "INSERT INTO usuarios (user_id, nombre, username, plan_id, premium) "
                    "VALUES (?, 'Admin', '', ?, 1)",
                    (admin_id, config.PLAN_PREMIUM)
                )
                import logging
                logging.getLogger(__name__).info(f"Admin {admin_id} creado como Premium")


# ─── USUARIOS ─────────────────────────────────────────────────────────────────

def registrar_usuario(user_id: int, nombre: str, username: str) -> bool:
    """Registra usuario si es nuevo. Retorna True si es nuevo."""
    with get_db() as con:
        cur = con.execute("SELECT 1 FROM usuarios WHERE user_id = ?", (user_id,))
        if cur.fetchone():
            return False  # ya existía
        con.execute("""
            INSERT INTO usuarios (user_id, nombre, username, plan_id)
            VALUES (?, ?, ?, 0)
        """, (user_id, nombre, username or ""))
        return True  # nuevo usuario


def buscar_por_username(username: str) -> int | None:
    """Busca user_id por username (sin @). Retorna None si no existe."""
    username = username.lstrip("@").strip().lower()
    if not username:
        return None
    with get_db() as con:
        cur = con.execute(
            "SELECT user_id FROM usuarios WHERE LOWER(username) = ?",
            (username,)
        )
        fila = cur.fetchone()
        return fila[0] if fila else None


def resolver_usuario(texto: str) -> int | None:
    """Resuelve un identificador a user_id. Acepta ID numérico o @username."""
    texto = texto.strip()
    if texto.startswith("@"):
        return buscar_por_username(texto)
    try:
        return int(texto)
    except ValueError:
        return buscar_por_username(texto)


def obtener_plan(user_id: int) -> int:
    """Retorna el plan_id del usuario (0, 1, o 2). Verifica expiración de tester."""
    _verificar_expiracion_tester(user_id)
    with get_db() as con:
        cur = con.execute("SELECT plan_id FROM usuarios WHERE user_id = ?", (user_id,))
        fila = cur.fetchone()
        return fila[0] if fila else 0


def info_plan(user_id: int) -> dict:
    """Retorna info completa del plan del usuario."""
    plan_id = obtener_plan(user_id)
    return config.PLANES.get(plan_id, config.PLANES[0])


def es_premium(user_id: int) -> bool:
    """Compatibilidad: True si plan >= Tester (tiene privilegios)."""
    return obtener_plan(user_id) >= config.PLAN_TESTER


def cambiar_plan(user_id: int, plan_id: int):
    """Cambia el plan de un usuario."""
    with get_db() as con:
        con.execute("UPDATE usuarios SET plan_id = ?, premium = ? WHERE user_id = ?",
                    (plan_id, 1 if plan_id >= 2 else 0, user_id))


def activar_premium(user_id: int):
    cambiar_plan(user_id, config.PLAN_PREMIUM)


def desactivar_premium(user_id: int):
    cambiar_plan(user_id, config.PLAN_GRATIS)


def activar_tester_temporal(user_id: int, dias: int = 14):
    """Activa plan Tester por N días."""
    from datetime import timedelta
    expira = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")
    with get_db() as con:
        con.execute(
            "UPDATE usuarios SET plan_id = ?, tester_expira = ? WHERE user_id = ?",
            (config.PLAN_TESTER, expira, user_id)
        )


def _verificar_expiracion_tester(user_id: int):
    """Si el tester expiró, regresa a plan gratis."""
    with get_db() as con:
        cur = con.execute(
            "SELECT plan_id, tester_expira FROM usuarios WHERE user_id = ?",
            (user_id,)
        )
        fila = cur.fetchone()
        if not fila:
            return
        plan_id, expira = fila
        if plan_id == config.PLAN_TESTER and expira:
            if date.today().isoformat() > expira:
                con.execute(
                    "UPDATE usuarios SET plan_id = 0, tester_expira = '' WHERE user_id = ?",
                    (user_id,)
                )


# ─── FEATURE FLAGS ─────────────────────────────────────────────────────────────

def tiene_memoria(user_id: int) -> bool:
    """Tiene memoria si su plan lo incluye O tiene bono_memoria."""
    plan = obtener_plan(user_id)
    plan_info = config.PLANES.get(plan, config.PLANES[0])
    if plan_info["memoria"]:
        return True
    with get_db() as con:
        cur = con.execute("SELECT bono_memoria FROM usuarios WHERE user_id = ?", (user_id,))
        fila = cur.fetchone()
        return bool(fila and fila[0])


def activar_bono_memoria(user_id: int):
    with get_db() as con:
        con.execute("UPDATE usuarios SET bono_memoria = 1 WHERE user_id = ?", (user_id,))


def desactivar_bono_memoria(user_id: int):
    with get_db() as con:
        con.execute("UPDATE usuarios SET bono_memoria = 0 WHERE user_id = ?", (user_id,))


def docs_disponibles(user_id: int) -> int:
    """Cuántos documentos puede generar este mes."""
    plan_id = obtener_plan(user_id)
    plan_info = config.PLANES.get(plan_id, config.PLANES[0])

    # Premium = ilimitado
    if plan_info["docs_mes"] == -1:
        return 999

    _resetear_docs_mes(user_id)

    with get_db() as con:
        cur = con.execute(
            "SELECT docs_usados_mes, docs_disponibles FROM usuarios WHERE user_id = ?",
            (user_id,)
        )
        fila = cur.fetchone()
        if not fila:
            return 0

        usados = fila[0] or 0
        bonos  = fila[1] or 0
        limite_plan = plan_info["docs_mes"]

        return max(0, (limite_plan - usados) + bonos)


def registrar_doc_usado(user_id: int):
    """Registra que el usuario generó un documento."""
    _resetear_docs_mes(user_id)
    with get_db() as con:
        # Primero usa bonos, luego el cupo del plan
        cur = con.execute("SELECT docs_disponibles FROM usuarios WHERE user_id = ?", (user_id,))
        fila = cur.fetchone()
        bonos = fila[0] if fila else 0

        if bonos > 0:
            con.execute("UPDATE usuarios SET docs_disponibles = docs_disponibles - 1 WHERE user_id = ?",
                       (user_id,))
        else:
            con.execute("UPDATE usuarios SET docs_usados_mes = docs_usados_mes + 1 WHERE user_id = ?",
                       (user_id,))


def regalar_documento(user_id: int, cantidad: int = 1):
    """Regala documentos a un usuario."""
    with get_db() as con:
        con.execute("UPDATE usuarios SET docs_disponibles = docs_disponibles + ? WHERE user_id = ?",
                   (cantidad, user_id))


def _resetear_docs_mes(user_id: int):
    """Resetea contador mensual si cambió el mes."""
    mes_actual = datetime.now().strftime("%Y-%m")
    with get_db() as con:
        cur = con.execute("SELECT mes_docs FROM usuarios WHERE user_id = ?", (user_id,))
        fila = cur.fetchone()
        if fila and fila[0] != mes_actual:
            con.execute("UPDATE usuarios SET docs_usados_mes = 0, mes_docs = ? WHERE user_id = ?",
                       (mes_actual, user_id))


def listar_usuarios() -> list[dict]:
    with get_db() as con:
        cur = con.execute("""
            SELECT u.user_id, u.nombre, u.username, u.plan_id, u.fecha_reg,
                   COALESCE(c.cantidad, 0) as consultas_hoy,
                   u.bono_memoria, u.docs_disponibles
            FROM usuarios u
            LEFT JOIN consultas_diarias c
                ON u.user_id = c.user_id AND c.fecha = ?
            ORDER BY u.fecha_reg DESC
        """, (date.today().isoformat(),))
        rows = cur.fetchall()
        return [{"user_id": r[0], "nombre": r[1], "username": r[2],
                 "plan_id": r[3] or 0, "premium": (r[3] or 0) >= 2,
                 "fecha_reg": r[4], "consultas_hoy": r[5],
                 "bono_memoria": bool(r[6]), "docs_disponibles": r[7] or 0}
                for r in rows]


# ─── LÍMITES DE CONSULTAS ─────────────────────────────────────────────────────

def consultas_hoy(user_id: int) -> int:
    hoy = date.today().isoformat()
    with get_db() as con:
        cur = con.execute("""
            SELECT cantidad FROM consultas_diarias
            WHERE user_id = ? AND fecha = ?
        """, (user_id, hoy))
        fila = cur.fetchone()
        return fila[0] if fila else 0


def limite_diario(user_id: int) -> int:
    """Retorna el límite de consultas según el plan."""
    plan_info = info_plan(user_id)
    return plan_info["consultas"]


def puede_consultar(user_id: int) -> bool:
    limite = limite_diario(user_id)
    if limite == -1:  # ilimitado
        return True
    return consultas_hoy(user_id) < limite


def registrar_consulta(user_id: int):
    hoy = date.today().isoformat()
    with get_db() as con:
        con.execute("""
            INSERT INTO consultas_diarias (user_id, fecha, cantidad)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, fecha) DO UPDATE SET cantidad = cantidad + 1
        """, (user_id, hoy))


def consultas_restantes(user_id: int) -> int:
    limite = limite_diario(user_id)
    if limite == -1:
        return -1  # ilimitado
    return max(0, limite - consultas_hoy(user_id))


# ─── HISTORIAL DE CONVERSACIÓN ────────────────────────────────────────────────

def guardar_mensaje(user_id: int, rol: str, mensaje: str):
    with get_db() as con:
        con.execute("""
            INSERT INTO historial (user_id, rol, mensaje)
            VALUES (?, ?, ?)
        """, (user_id, rol, mensaje))

        con.execute("""
            DELETE FROM historial
            WHERE user_id = ? AND id NOT IN (
                SELECT id FROM historial
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
        """, (user_id, user_id, config.MAX_HISTORIAL))


def cargar_historial(user_id: int) -> list[dict]:
    with get_db() as con:
        cur = con.execute("""
            SELECT rol, mensaje FROM historial
            WHERE user_id = ?
            ORDER BY id ASC
        """, (user_id,))
        rows = cur.fetchall()
        return [{"role": r[0], "content": r[1]} for r in rows]


def limpiar_historial(user_id: int):
    with get_db() as con:
        con.execute("DELETE FROM historial WHERE user_id = ?", (user_id,))
        con.execute("DELETE FROM ultimo_contexto WHERE user_id = ?", (user_id,))


# ─── CONTEXTO DE ARTÍCULOS ───────────────────────────────────────────────────

def guardar_contexto(user_id: int, contexto: str):
    with get_db() as con:
        con.execute("""
            INSERT INTO ultimo_contexto (user_id, contexto)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                contexto = excluded.contexto,
                timestamp = CURRENT_TIMESTAMP
        """, (user_id, contexto))


def cargar_contexto(user_id: int) -> str | None:
    with get_db() as con:
        cur = con.execute(
            "SELECT contexto FROM ultimo_contexto WHERE user_id = ?",
            (user_id,)
        )
        fila = cur.fetchone()
        return fila[0] if fila else None


# ─── ESTADÍSTICAS ─────────────────────────────────────────────────────────────

def stats_globales() -> dict:
    """Estadísticas globales para admins."""
    hoy = date.today().isoformat()
    with get_db() as con:
        total_usuarios = con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        consultas_hoy_total = con.execute(
            "SELECT COALESCE(SUM(cantidad),0) FROM consultas_diarias WHERE fecha = ?",
            (hoy,)
        ).fetchone()[0]
        consultas_semana = con.execute(
            "SELECT COALESCE(SUM(cantidad),0) FROM consultas_diarias WHERE fecha >= date(?, '-7 days')",
            (hoy,)
        ).fetchone()[0]
        consultas_mes = con.execute(
            "SELECT COALESCE(SUM(cantidad),0) FROM consultas_diarias WHERE fecha >= date(?, '-30 days')",
            (hoy,)
        ).fetchone()[0]
        usuario_activo = con.execute(
            "SELECT user_id, SUM(cantidad) as total FROM consultas_diarias "
            "WHERE fecha >= date(?, '-7 days') GROUP BY user_id ORDER BY total DESC LIMIT 1",
            (hoy,)
        ).fetchone()
        planes = con.execute(
            "SELECT plan_id, COUNT(*) FROM usuarios GROUP BY plan_id"
        ).fetchall()
        return {
            "total_usuarios": total_usuarios,
            "consultas_hoy": consultas_hoy_total,
            "consultas_semana": consultas_semana,
            "consultas_mes": consultas_mes,
            "usuario_mas_activo": usuario_activo,
            "por_plan": {r[0]: r[1] for r in planes},
        }


def stats_usuario(user_id: int) -> dict:
    """Estadísticas personales de un usuario."""
    hoy = date.today().isoformat()
    with get_db() as con:
        consultas_total = con.execute(
            "SELECT COALESCE(SUM(cantidad),0) FROM consultas_diarias WHERE user_id = ?",
            (user_id,)
        ).fetchone()[0]
        consultas_hoy_u = con.execute(
            "SELECT COALESCE(cantidad,0) FROM consultas_diarias WHERE user_id = ? AND fecha = ?",
            (user_id, hoy)
        ).fetchone()
        favoritos_count = con.execute(
            "SELECT COUNT(*) FROM favoritos WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        return {
            "consultas_total": consultas_total,
            "consultas_hoy": consultas_hoy_u[0] if consultas_hoy_u else 0,
            "favoritos": favoritos_count,
        }


# ─── FEEDBACK ─────────────────────────────────────────────────────────────────

def guardar_feedback(user_id: int, tipo: str, comentario: str = ""):
    with get_db() as con:
        con.execute(
            "INSERT INTO feedback (user_id, tipo, comentario) VALUES (?, ?, ?)",
            (user_id, tipo, comentario)
        )


def listar_feedback(limit: int = 20) -> list[dict]:
    with get_db() as con:
        cur = con.execute(
            "SELECT user_id, tipo, comentario, timestamp FROM feedback ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        return [{"user_id": r[0], "tipo": r[1], "comentario": r[2], "timestamp": r[3]}
                for r in cur.fetchall()]


# ─── FAVORITOS ────────────────────────────────────────────────────────────────

def guardar_favorito(user_id: int, pregunta: str, respuesta: str):
    with get_db() as con:
        con.execute(
            "INSERT INTO favoritos (user_id, pregunta, respuesta) VALUES (?, ?, ?)",
            (user_id, pregunta, respuesta)
        )


def cargar_favoritos(user_id: int, limit: int = 10) -> list[dict]:
    with get_db() as con:
        cur = con.execute(
            "SELECT id, pregunta, respuesta, timestamp FROM favoritos "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        )
        return [{"id": r[0], "pregunta": r[1], "respuesta": r[2], "timestamp": r[3]}
                for r in cur.fetchall()]


def borrar_favoritos(user_id: int):
    with get_db() as con:
        con.execute("DELETE FROM favoritos WHERE user_id = ?", (user_id,))


# ─── REFERIDOS ────────────────────────────────────────────────────────────────

def registrar_referido(user_id: int, referido_por: int):
    """Registra quién refirió a este usuario."""
    with get_db() as con:
        con.execute("UPDATE usuarios SET referido_por = ? WHERE user_id = ?",
                   (referido_por, user_id))
        con.execute("UPDATE usuarios SET referidos_count = referidos_count + 1 WHERE user_id = ?",
                   (referido_por,))


def obtener_referidos_count(user_id: int) -> int:
    with get_db() as con:
        cur = con.execute("SELECT referidos_count FROM usuarios WHERE user_id = ?", (user_id,))
        fila = cur.fetchone()
        return fila[0] if fila else 0


def fue_referido_por(user_id: int) -> int:
    """Retorna el ID de quien refirió a este usuario, o 0."""
    with get_db() as con:
        cur = con.execute("SELECT referido_por FROM usuarios WHERE user_id = ?", (user_id,))
        fila = cur.fetchone()
        return fila[0] if fila else 0


# ─── SOPORTE ──────────────────────────────────────────────────────────────────

def guardar_ticket_soporte(user_id: int, mensaje: str, direccion: str = "user_to_admin"):
    with get_db() as con:
        con.execute(
            "INSERT INTO soporte (user_id, mensaje, direccion) VALUES (?, ?, ?)",
            (user_id, mensaje, direccion)
        )
