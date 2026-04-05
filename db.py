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

        con.execute("""
            CREATE TABLE IF NOT EXISTS ultima_respuesta (
                user_id   INTEGER PRIMARY KEY,
                pregunta  TEXT,
                respuesta TEXT,
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

        if "consultas_extra" not in columnas:
            con.execute("ALTER TABLE usuarios ADD COLUMN consultas_extra INTEGER DEFAULT 0")

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

        # ── Migración feedback: columnas de tickets ──────────────────────
        cols_fb = {r[1] for r in con.execute("PRAGMA table_info(feedback)").fetchall()}
        if "motivo" not in cols_fb:
            con.execute("ALTER TABLE feedback ADD COLUMN motivo TEXT DEFAULT ''")
        if "estado" not in cols_fb:
            con.execute("ALTER TABLE feedback ADD COLUMN estado TEXT DEFAULT 'nuevo'")
        if "resuelto_en" not in cols_fb:
            con.execute("ALTER TABLE feedback ADD COLUMN resuelto_en TEXT")
        if "resuelto_por" not in cols_fb:
            con.execute("ALTER TABLE feedback ADD COLUMN resuelto_por INTEGER")

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

        con.execute("""
            CREATE TABLE IF NOT EXISTS metricas (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER,
                fecha     TEXT,
                temas     TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS abogados (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre         TEXT NOT NULL,
                cedula         TEXT NOT NULL,
                inpreabogado   TEXT NOT NULL,
                especialidad   TEXT NOT NULL,
                telefono       TEXT NOT NULL,
                estado         TEXT NOT NULL,
                notas          TEXT DEFAULT '',
                activo         INTEGER DEFAULT 1,
                timestamp      TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── Tablas TMA (historial de conversaciones por sidebar) ─────
        # Completamente separadas del bot de Telegram.
        con.execute("""
            CREATE TABLE IF NOT EXISTS tma_conversaciones (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      TEXT NOT NULL,
                titulo       TEXT NOT NULL DEFAULT 'Nueva consulta',
                creado_en    TEXT DEFAULT CURRENT_TIMESTAMP,
                actualizado  TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS tma_mensajes (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                conv_id      INTEGER NOT NULL,
                rol          TEXT NOT NULL,
                texto        TEXT NOT NULL,
                temas        TEXT DEFAULT '',
                creado_en    TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conv_id) REFERENCES tma_conversaciones(id) ON DELETE CASCADE
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_tma_conv_user ON tma_conversaciones(user_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_tma_msg_conv ON tma_mensajes(conv_id)")

    # Log de ruta para diagnóstico
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"DB inicializada en: {config.SQLITE_DB_FILE}")


# ─── TMA: CONVERSACIONES ──────────────────────────────────────────────────────

def tma_nueva_conversacion(user_id: str, titulo: str = "Nueva consulta") -> int:
    """Crea una nueva conversación en el sidebar. Retorna el ID."""
    with get_db() as con:
        cur = con.execute(
            "INSERT INTO tma_conversaciones (user_id, titulo) VALUES (?, ?)",
            (str(user_id), titulo[:80])
        )
        return cur.lastrowid


def tma_listar_conversaciones(user_id: str) -> list[dict]:
    """Lista las conversaciones del usuario, más recientes primero."""
    with get_db() as con:
        rows = con.execute("""
            SELECT id, titulo, creado_en, actualizado
            FROM tma_conversaciones
            WHERE user_id = ?
            ORDER BY actualizado DESC
            LIMIT 50
        """, (str(user_id),)).fetchall()
    return [{"id": r[0], "titulo": r[1], "creado_en": r[2], "actualizado": r[3]} for r in rows]


def tma_renombrar_conversacion(conv_id: int, user_id: str, titulo: str):
    """Renombra una conversación (verifica que pertenezca al usuario)."""
    with get_db() as con:
        con.execute(
            "UPDATE tma_conversaciones SET titulo = ? WHERE id = ? AND user_id = ?",
            (titulo[:80], conv_id, str(user_id))
        )


def tma_eliminar_conversacion(conv_id: int, user_id: str):
    """Elimina una conversación y todos sus mensajes (CASCADE)."""
    with get_db() as con:
        con.execute(
            "DELETE FROM tma_conversaciones WHERE id = ? AND user_id = ?",
            (conv_id, str(user_id))
        )


def tma_guardar_mensaje(conv_id: int, rol: str, texto: str, temas: list[str] = None):
    """Guarda un mensaje en una conversación y actualiza su timestamp."""
    temas_str = ",".join(temas or [])
    with get_db() as con:
        con.execute(
            "INSERT INTO tma_mensajes (conv_id, rol, texto, temas) VALUES (?, ?, ?, ?)",
            (conv_id, rol, texto, temas_str)
        )
        con.execute(
            "UPDATE tma_conversaciones SET actualizado = CURRENT_TIMESTAMP WHERE id = ?",
            (conv_id,)
        )


def tma_obtener_mensajes(conv_id: int, user_id: str) -> list[dict]:
    """Retorna los mensajes de una conversación (verifica dueño)."""
    with get_db() as con:
        # Verificar que la conversación pertenece al usuario
        dueño = con.execute(
            "SELECT id FROM tma_conversaciones WHERE id = ? AND user_id = ?",
            (conv_id, str(user_id))
        ).fetchone()
        if not dueño:
            return []
        rows = con.execute("""
            SELECT rol, texto, temas, creado_en
            FROM tma_mensajes WHERE conv_id = ?
            ORDER BY creado_en ASC
        """, (conv_id,)).fetchall()
    return [{"rol": r[0], "texto": r[1], "temas": r[2].split(",") if r[2] else [], "creado_en": r[3]} for r in rows]


def tma_actualizar_titulo_auto(conv_id: int, primer_mensaje: str):
    """Genera título automático del primer mensaje si el título es el default."""
    titulo = primer_mensaje[:50].strip()
    if len(primer_mensaje) > 50:
        titulo += "…"
    with get_db() as con:
        con.execute("""
            UPDATE tma_conversaciones
            SET titulo = ?
            WHERE id = ? AND titulo = 'Nueva consulta'
        """, (titulo, conv_id))

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

MAX_AUTO_TESTERS = 50  # primeros N usuarios reciben Pionero gratis


def registrar_usuario(user_id: int, nombre: str, username: str) -> bool:
    """Registra usuario si es nuevo. Retorna True si es nuevo.
    Los primeros MAX_AUTO_TESTERS usuarios (excepto admins) reciben Pionero por 2 semanas."""
    with get_db() as con:
        cur = con.execute("SELECT 1 FROM usuarios WHERE user_id = ?", (user_id,))
        if cur.fetchone():
            return False  # ya existía
        con.execute("""
            INSERT INTO usuarios (user_id, nombre, username, plan_id)
            VALUES (?, ?, ?, 0)
        """, (user_id, nombre, username or ""))

    # Auto-tester: si no es admin y hay menos de MAX_AUTO_TESTERS, dar Pionero
    if user_id not in config.ADMIN_IDS:
        with get_db() as con:
            total = con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        if total <= MAX_AUTO_TESTERS:
            activar_tester_temporal(user_id, dias=14)

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


def extender_tester(user_id: int, dias: int = 7):
    """Extiende el plan Tester sumando días a la fecha actual de expiración.
    Si no es tester o ya expiró, activa desde hoy."""
    from datetime import timedelta
    with get_db() as con:
        cur = con.execute(
            "SELECT plan_id, tester_expira FROM usuarios WHERE user_id = ?",
            (user_id,)
        )
        fila = cur.fetchone()
        if not fila:
            return

        plan_id, expira_str = fila
        hoy = date.today()

        if plan_id == config.PLAN_TESTER and expira_str:
            try:
                expira_actual = date.fromisoformat(expira_str)
                # Si aún no expiró, sumar desde la fecha de expiración
                base = max(expira_actual, hoy)
            except ValueError:
                base = hoy
        else:
            base = hoy

        nueva_expira = (base + timedelta(days=dias)).isoformat()
        con.execute(
            "UPDATE usuarios SET plan_id = ?, tester_expira = ? WHERE user_id = ?",
            (config.PLAN_TESTER, nueva_expira, user_id)
        )


def obtener_expiracion_tester(user_id: int) -> str:
    """Retorna la fecha de expiración del tester, o '' si no aplica."""
    with get_db() as con:
        cur = con.execute(
            "SELECT tester_expira FROM usuarios WHERE user_id = ?",
            (user_id,)
        )
        fila = cur.fetchone()
        return fila[0] if fila and fila[0] else ""


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
                   u.bono_memoria, u.docs_disponibles, u.tester_expira
            FROM usuarios u
            LEFT JOIN consultas_diarias c
                ON u.user_id = c.user_id AND c.fecha = ?
            ORDER BY u.fecha_reg DESC
        """, (date.today().isoformat(),))
        rows = cur.fetchall()
        return [{"user_id": r[0], "nombre": r[1], "username": r[2],
                 "plan_id": r[3] or 0, "premium": (r[3] or 0) >= 2,
                 "fecha_reg": r[4], "consultas_hoy": r[5],
                 "bono_memoria": bool(r[6]), "docs_disponibles": r[7] or 0,
                 "tester_expira": r[8] or ""}
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
    """Retorna el límite de consultas según el plan + consultas extra regaladas."""
    plan_info = info_plan(user_id)
    base = plan_info["consultas"]
    if base == -1:  # ilimitado
        return -1
    with get_db() as con:
        cur = con.execute("SELECT consultas_extra FROM usuarios WHERE user_id = ?", (user_id,))
        fila = cur.fetchone()
        extra = fila[0] if fila and fila[0] else 0
    return base + extra


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


def regalar_consultas(user_id: int, cantidad: int = 5):
    """Suma consultas extra al usuario (se suman al límite diario del plan)."""
    with get_db() as con:
        con.execute(
            "UPDATE usuarios SET consultas_extra = COALESCE(consultas_extra, 0) + ? WHERE user_id = ?",
            (cantidad, user_id))


def quitar_consultas_extra(user_id: int, cantidad: int = 5):
    """Quita consultas extra al usuario."""
    with get_db() as con:
        con.execute(
            "UPDATE usuarios SET consultas_extra = MAX(0, COALESCE(consultas_extra, 0) - ?) WHERE user_id = ?",
            (cantidad, user_id))


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


def guardar_feedback_v2(user_id: int, tipo: str, pregunta: str = "",
                        respuesta: str = "", motivo: str = "") -> int:
    """Guarda feedback con pregunta, respuesta y motivo separados.

    El comentario se mantiene en formato 'pregunta\\n---\\nrespuesta' para que
    el admin viewer del bot puro siga funcionando sin cambios. El motivo va
    en su propia columna. Retorna el id del feedback insertado.
    """
    pregunta = (pregunta or "").strip()[:400]
    respuesta = (respuesta or "").strip()[:800]
    motivo = (motivo or "").strip()[:500]
    if pregunta and respuesta:
        comentario = f"{pregunta}\n---\n{respuesta}"
    else:
        comentario = pregunta or respuesta
    with get_db() as con:
        cur = con.execute(
            "INSERT INTO feedback (user_id, tipo, comentario, motivo, estado) "
            "VALUES (?, ?, ?, ?, 'nuevo')",
            (user_id, tipo, comentario, motivo)
        )
        return cur.lastrowid


def listar_feedback_tickets(estado: str = None, tipo: str = None,
                            limit: int = 50, offset: int = 0) -> list[dict]:
    """Lista feedbacks como tickets. Descompone comentario en pregunta/respuesta."""
    condiciones = []
    params: list = []
    if estado:
        condiciones.append("estado = ?")
        params.append(estado)
    if tipo:
        condiciones.append("tipo = ?")
        params.append(tipo)
    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    params.extend([limit, offset])
    with get_db() as con:
        cur = con.execute(
            f"SELECT id, user_id, tipo, comentario, motivo, estado, timestamp, "
            f"       resuelto_en, resuelto_por "
            f"FROM feedback {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params
        )
        items = []
        for r in cur.fetchall():
            comentario = r[3] or ""
            if "\n---\n" in comentario:
                pregunta, respuesta = comentario.split("\n---\n", 1)
            else:
                pregunta, respuesta = comentario, ""
            items.append({
                "id": r[0],
                "user_id": r[1],
                "tipo": r[2],
                "pregunta": pregunta,
                "respuesta": respuesta,
                "motivo": r[4] or "",
                "estado": r[5] or "nuevo",
                "timestamp": r[6],
                "resuelto_en": r[7],
                "resuelto_por": r[8],
            })
        return items


def marcar_feedback_resuelto(feedback_id: int, admin_id: int) -> dict | None:
    """Marca un feedback como resuelto. Retorna el ticket actualizado o None."""
    with get_db() as con:
        cur = con.execute(
            "UPDATE feedback SET estado = 'resuelto', "
            "resuelto_en = CURRENT_TIMESTAMP, resuelto_por = ? "
            "WHERE id = ?",
            (admin_id, feedback_id)
        )
        if cur.rowcount == 0:
            return None
        row = con.execute(
            "SELECT id, user_id, tipo, comentario, motivo, estado, timestamp, "
            "       resuelto_en, resuelto_por FROM feedback WHERE id = ?",
            (feedback_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "user_id": row[1], "tipo": row[2],
            "comentario": row[3], "motivo": row[4], "estado": row[5],
            "timestamp": row[6], "resuelto_en": row[7], "resuelto_por": row[8],
        }


def listar_feedback(limit: int = 10, offset: int = 0, tipo: str = None) -> list[dict]:
    with get_db() as con:
        if tipo:
            cur = con.execute(
                "SELECT user_id, tipo, comentario, timestamp FROM feedback "
                "WHERE tipo = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (tipo, limit, offset)
            )
        else:
            cur = con.execute(
                "SELECT user_id, tipo, comentario, timestamp FROM feedback "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
        return [{"user_id": r[0], "tipo": r[1], "comentario": r[2], "timestamp": r[3]}
                for r in cur.fetchall()]


def contar_feedback() -> dict:
    """Retorna conteo total de feedback por tipo."""
    with get_db() as con:
        cur = con.execute(
            "SELECT tipo, COUNT(*) FROM feedback GROUP BY tipo"
        )
        conteos = {r[0]: r[1] for r in cur.fetchall()}
        total = sum(conteos.values())
        return {"total": total, "positivo": conteos.get("positivo", 0),
                "negativo": conteos.get("negativo", 0),
                "comentario": conteos.get("comentario", 0)}


def borrar_feedback(feedback_tipo: str = None, user_id: int = None) -> int:
    """Borra feedback por filtro. Retorna cantidad borrada."""
    with get_db() as con:
        condiciones = []
        params = []
        if feedback_tipo:
            condiciones.append("tipo = ?")
            params.append(feedback_tipo)
        if user_id:
            condiciones.append("user_id = ?")
            params.append(user_id)
        where = " WHERE " + " AND ".join(condiciones) if condiciones else ""
        cur = con.execute(f"SELECT COUNT(*) FROM feedback{where}", params)
        cantidad = cur.fetchone()[0]
        con.execute(f"DELETE FROM feedback{where}", params)
        return cantidad


# ─── ÚLTIMA RESPUESTA (persistente) ──────────────────────────────────────────

def guardar_ultima_respuesta(user_id: int, pregunta: str, respuesta: str):
    with get_db() as con:
        con.execute("""
            INSERT INTO ultima_respuesta (user_id, pregunta, respuesta, timestamp)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                pregunta = excluded.pregunta,
                respuesta = excluded.respuesta,
                timestamp = CURRENT_TIMESTAMP
        """, (user_id, pregunta, respuesta))


def cargar_ultima_respuesta(user_id: int) -> dict:
    with get_db() as con:
        cur = con.execute(
            "SELECT pregunta, respuesta FROM ultima_respuesta WHERE user_id = ?",
            (user_id,))
        fila = cur.fetchone()
        if fila:
            return {"pregunta": fila[0], "respuesta": fila[1]}
        return {}


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


# ─── DIRECTORIO DE ABOGADOS ─────────────────────────────────────────────────

ESPECIALIDADES_VALIDAS = [
    "Penal", "Civil", "Laboral", "Mercantil", "Familia",
    "Tránsito", "Administrativo", "Tributario", "Inmobiliario",
    "Migratorio", "Electoral", "Ambiental", "Otro"
]


def agregar_abogado(nombre: str, cedula: str, inpreabogado: str,
                    especialidad: str, telefono: str, estado: str,
                    notas: str = "") -> int:
    """Agrega un abogado al directorio. Retorna el ID."""
    with get_db() as con:
        cur = con.execute("""
            INSERT INTO abogados (nombre, cedula, inpreabogado, especialidad,
                                  telefono, estado, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (nombre, cedula, inpreabogado, especialidad, telefono, estado, notas))
        return cur.lastrowid


def listar_abogados(especialidad: str = None, estado: str = None,
                    solo_activos: bool = True) -> list[dict]:
    """Lista abogados con filtros opcionales."""
    query = "SELECT * FROM abogados WHERE 1=1"
    params = []

    if solo_activos:
        query += " AND activo = 1"
    if especialidad:
        query += " AND LOWER(especialidad) LIKE ?"
        params.append(f"%{especialidad.lower()}%")
    if estado:
        query += " AND LOWER(estado) LIKE ?"
        params.append(f"%{estado.lower()}%")

    query += " ORDER BY nombre ASC"

    with get_db() as con:
        cur = con.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def obtener_abogado(abogado_id: int) -> dict | None:
    """Obtiene un abogado por ID."""
    with get_db() as con:
        cur = con.execute("SELECT * FROM abogados WHERE id = ?", (abogado_id,))
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        return dict(zip(cols, row)) if row else None


def desactivar_abogado(abogado_id: int) -> bool:
    """Desactiva un abogado (no lo borra). Retorna True si existía."""
    with get_db() as con:
        cur = con.execute("UPDATE abogados SET activo = 0 WHERE id = ?", (abogado_id,))
        return cur.rowcount > 0


def activar_abogado(abogado_id: int) -> bool:
    """Reactiva un abogado. Retorna True si existía."""
    with get_db() as con:
        cur = con.execute("UPDATE abogados SET activo = 1 WHERE id = ?", (abogado_id,))
        return cur.rowcount > 0


def contar_abogados(solo_activos: bool = True) -> int:
    """Cuenta abogados en el directorio."""
    query = "SELECT COUNT(*) FROM abogados"
    if solo_activos:
        query += " WHERE activo = 1"
    with get_db() as con:
        return con.execute(query).fetchone()[0]


# ─── MÉTRICAS DE CONSULTAS ──────────────────────────────────────────────────

def registrar_consulta_metrica(user_id: int, temas: list[str]):
    """Registra una consulta con los temas detectados para métricas."""
    hoy = date.today().isoformat()
    temas_str = ",".join(temas) if temas else ""
    with get_db() as con:
        con.execute(
            "INSERT INTO metricas (user_id, fecha, temas) VALUES (?, ?, ?)",
            (user_id, hoy, temas_str)
        )


def obtener_stats() -> dict:
    """Estadísticas de consultas: hoy, últimos 7 días, total y temas top."""
    hoy = date.today().isoformat()
    with get_db() as con:
        consultas_hoy_total = con.execute(
            "SELECT COUNT(*) FROM metricas WHERE fecha = ?", (hoy,)
        ).fetchone()[0]

        consultas_7d = con.execute(
            "SELECT COUNT(*) FROM metricas WHERE fecha >= date(?, '-7 days')",
            (hoy,)
        ).fetchone()[0]

        consultas_total = con.execute(
            "SELECT COUNT(*) FROM metricas"
        ).fetchone()[0]

        # Temas más consultados en últimos 7 días
        filas = con.execute(
            "SELECT temas FROM metricas WHERE fecha >= date(?, '-7 days') AND temas != ''",
            (hoy,)
        ).fetchall()

    # Contar temas
    conteo_temas = {}
    for (temas_str,) in filas:
        for tema in temas_str.split(","):
            tema = tema.strip()
            if tema:
                conteo_temas[tema] = conteo_temas.get(tema, 0) + 1

    temas_top = sorted(conteo_temas.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "consultas_hoy": consultas_hoy_total,
        "consultas_7d": consultas_7d,
        "consultas_total": consultas_total,
        "temas_top": temas_top,
    }


def stats_usuarios() -> dict:
    """Estadísticas de usuarios: total, por plan, activos hoy."""
    hoy = date.today().isoformat()
    with get_db() as con:
        total = con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]

        planes = con.execute(
            "SELECT plan_id, COUNT(*) FROM usuarios GROUP BY plan_id"
        ).fetchall()

        activos_hoy = con.execute(
            "SELECT COUNT(DISTINCT user_id) FROM consultas_diarias WHERE fecha = ? AND cantidad > 0",
            (hoy,)
        ).fetchone()[0]

    por_plan = {r[0]: r[1] for r in planes}

    return {
        "total": total,
        "gratis": por_plan.get(0, 0),
        "pionero": por_plan.get(1, 0),
        "premium": por_plan.get(2, 0),
        "activos_hoy": activos_hoy,
    }
