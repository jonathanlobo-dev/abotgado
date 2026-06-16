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

        if "limite_override" not in columnas:
            con.execute("ALTER TABLE usuarios ADD COLUMN limite_override INTEGER DEFAULT NULL")

        if "periodo_override" not in columnas:
            con.execute("ALTER TABLE usuarios ADD COLUMN periodo_override TEXT DEFAULT NULL")

        # ── Tabla de configuración de planes (editable en runtime) ───────
        con.execute("""
            CREATE TABLE IF NOT EXISTS config_planes (
                plan_id   INTEGER PRIMARY KEY,
                consultas INTEGER NOT NULL,
                periodo   TEXT NOT NULL DEFAULT 'diario'
            )
        """)
        # Sembrar valores por defecto desde config.PLANES si la tabla está vacía
        for pid, info in config.PLANES.items():
            con.execute("""
                INSERT INTO config_planes (plan_id, consultas, periodo)
                VALUES (?, ?, 'diario')
                ON CONFLICT(plan_id) DO NOTHING
            """, (pid, info["consultas"]))

        # ── Tabla de conteo de consultas por período ─────────────────────
        con.execute("""
            CREATE TABLE IF NOT EXISTS consultas_periodo (
                user_id  INTEGER,
                clave    TEXT,
                cantidad INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, clave)
            )
        """)

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
        # Contexto de la última consulta al momento del feedback (para debug)
        if "pregunta_contexto" not in cols_fb:
            con.execute("ALTER TABLE feedback ADD COLUMN pregunta_contexto TEXT DEFAULT ''")
        if "temas_contexto" not in cols_fb:
            con.execute("ALTER TABLE feedback ADD COLUMN temas_contexto TEXT DEFAULT ''")
        if "leyes_contexto" not in cols_fb:
            con.execute("ALTER TABLE feedback ADD COLUMN leyes_contexto TEXT DEFAULT ''")

        # Migración soporte: mismos 3 campos de contexto
        cols_sp = {r[1] for r in con.execute("PRAGMA table_info(soporte)").fetchall()}
        for col in ("pregunta_contexto", "temas_contexto", "leyes_contexto"):
            if col not in cols_sp:
                con.execute(f"ALTER TABLE soporte ADD COLUMN {col} TEXT DEFAULT ''")

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

        # consultas_log: registro enriquecido de cada consulta (para /stats detallado
        # y para correlacionar con feedback negativo / soporte). Separado de `metricas`
        # para no inflar esa tabla que solo guarda conteos de temas.
        con.execute("""
            CREATE TABLE IF NOT EXISTS consultas_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER,
                pregunta  TEXT,
                temas     TEXT DEFAULT '',
                leyes     TEXT DEFAULT '',
                confianza TEXT DEFAULT '',
                fecha     TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_consultas_log_fecha ON consultas_log(fecha)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_consultas_log_user ON consultas_log(user_id, timestamp)")
        # Migración: guardar la RESPUESTA y la distancia para poder auditar todas
        # las consultas (no solo las que generan feedback). Permite revisar
        # respuestas que nadie reportó.
        _cols_cl = {r[1] for r in con.execute("PRAGMA table_info(consultas_log)").fetchall()}
        if "respuesta" not in _cols_cl:
            con.execute("ALTER TABLE consultas_log ADD COLUMN respuesta TEXT DEFAULT ''")
        if "distancia" not in _cols_cl:
            con.execute("ALTER TABLE consultas_log ADD COLUMN distancia REAL DEFAULT 0")

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

        # ── Migración abogados: nuevas columnas para perfil verificado ──
        cols_ab = {r[1] for r in con.execute("PRAGMA table_info(abogados)").fetchall()}
        _mig_abogados = [
            ("user_id",            "ALTER TABLE abogados ADD COLUMN user_id INTEGER"),
            ("modalidad",          "ALTER TABLE abogados ADD COLUMN modalidad TEXT DEFAULT 'presencial'"),
            ("biografia",          "ALTER TABLE abogados ADD COLUMN biografia TEXT DEFAULT ''"),
            ("metodos_pago",       "ALTER TABLE abogados ADD COLUMN metodos_pago TEXT DEFAULT '[]'"),
            ("membresia",          "ALTER TABLE abogados ADD COLUMN membresia TEXT DEFAULT 'inactiva'"),
            ("membresia_expira",   "ALTER TABLE abogados ADD COLUMN membresia_expira TEXT"),
            ("ranking",            "ALTER TABLE abogados ADD COLUMN ranking INTEGER DEFAULT 0"),
            ("consultas_atendidas","ALTER TABLE abogados ADD COLUMN consultas_atendidas INTEGER DEFAULT 0"),
            ("calificacion",       "ALTER TABLE abogados ADD COLUMN calificacion REAL DEFAULT 0.0"),
            ("verificado",         "ALTER TABLE abogados ADD COLUMN verificado INTEGER DEFAULT 0"),
        ]
        for col, sql in _mig_abogados:
            if col not in cols_ab:
                con.execute(sql)

        con.execute("""
            CREATE TABLE IF NOT EXISTS solicitudes_abogado (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL,
                nombre           TEXT NOT NULL,
                cedula           TEXT NOT NULL,
                inpreabogado     TEXT NOT NULL,
                especialidad     TEXT NOT NULL,
                telefono         TEXT NOT NULL,
                estado_geo       TEXT NOT NULL,
                biografia        TEXT DEFAULT '',
                modalidad        TEXT DEFAULT 'presencial',
                metodos_pago     TEXT DEFAULT '[]',
                estado_solicitud TEXT DEFAULT 'pendiente',
                motivo_rechazo   TEXT DEFAULT '',
                revisado_por     INTEGER,
                revisado_en      TEXT,
                timestamp        TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_sol_user ON solicitudes_abogado(user_id)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_sol_estado ON solicitudes_abogado(estado_solicitud)"
        )

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
    """Retorna info completa del plan del usuario (incluye periodo configurado)."""
    plan_id = obtener_plan(user_id)
    return get_config_plan(plan_id)


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


def buscar_user_id_por_username(username: str) -> int | None:
    """Busca el user_id por username (sin @). Retorna None si no existe."""
    username = username.lstrip("@").lower()
    with get_db() as con:
        row = con.execute(
            "SELECT user_id FROM usuarios WHERE LOWER(username) = ?", (username,)
        ).fetchone()
        return row[0] if row else None


def _resetear_docs_mes(user_id: int):
    """Resetea contador mensual si cambió el mes."""
    mes_actual = datetime.now().strftime("%Y-%m")
    with get_db() as con:
        cur = con.execute("SELECT mes_docs FROM usuarios WHERE user_id = ?", (user_id,))
        fila = cur.fetchone()
        if fila and fila[0] != mes_actual:
            con.execute("UPDATE usuarios SET docs_usados_mes = 0, mes_docs = ? WHERE user_id = ?",
                       (mes_actual, user_id))


def obtener_usuario(user_id: int) -> dict | None:
    """Devuelve la configuración básica de un usuario, o None si no existe."""
    with get_db() as con:
        r = con.execute("""
            SELECT user_id, nombre, username, plan_id, fecha_reg,
                   bono_memoria, docs_disponibles, tester_expira,
                   COALESCE(consultas_extra, 0)
            FROM usuarios WHERE user_id = ?
        """, (user_id,)).fetchone()
    if not r:
        return None
    return {"user_id": r[0], "nombre": r[1], "username": r[2],
            "plan_id": r[3] or 0, "fecha_reg": r[4],
            "bono_memoria": bool(r[5]), "docs_disponibles": r[6] or 0,
            "tester_expira": r[7] or "", "consultas_extra": r[8]}


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


# ─── CONFIGURACIÓN DE PLANES (editable en runtime) ───────────────────────────

_PERIODOS_VALIDOS = ("diario", "semanal", "mensual")


def _periodo_key(periodo: str) -> str:
    """Devuelve la clave del período actual como string para la tabla consultas_periodo."""
    hoy = date.today()
    if periodo == "semanal":
        iso = hoy.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if periodo == "mensual":
        return f"{hoy.year}-{hoy.month:02d}"
    return hoy.isoformat()  # diario


def get_config_plan(plan_id: int) -> dict:
    """Devuelve la config del plan desde la BD (con fallback a config.PLANES)."""
    with get_db() as con:
        row = con.execute(
            "SELECT consultas, periodo FROM config_planes WHERE plan_id = ?", (plan_id,)
        ).fetchone()
    base = config.PLANES.get(plan_id, config.PLANES[0]).copy()
    if row:
        base["consultas"] = row[0]
        base["periodo"] = row[1]
    else:
        base["periodo"] = "diario"
    return base


def set_config_plan(plan_id: int, consultas: int, periodo: str):
    """Cambia límite y período de un plan. Persiste en la BD."""
    with get_db() as con:
        con.execute("""
            INSERT INTO config_planes (plan_id, consultas, periodo)
            VALUES (?, ?, ?)
            ON CONFLICT(plan_id) DO UPDATE SET consultas = excluded.consultas,
                                               periodo   = excluded.periodo
        """, (plan_id, consultas, periodo))


def set_limite_usuario(user_id: int, limite: int, periodo: str):
    """Override de límite/período para un usuario específico."""
    with get_db() as con:
        con.execute(
            "UPDATE usuarios SET limite_override = ?, periodo_override = ? WHERE user_id = ?",
            (limite, periodo, user_id)
        )


def quitar_limite_usuario(user_id: int):
    """Quita el override de un usuario; vuelve a usar la config del plan."""
    with get_db() as con:
        con.execute(
            "UPDATE usuarios SET limite_override = NULL, periodo_override = NULL WHERE user_id = ?",
            (user_id,)
        )


def _get_limite_y_periodo(user_id: int) -> tuple[int, str]:
    """Devuelve (limite, periodo) efectivos para un usuario.

    Prioridad:
      1. Override individual  (limite_override / periodo_override)
      2. Config del plan      (config_planes)  + consultas_extra
    """
    with get_db() as con:
        row = con.execute(
            "SELECT limite_override, periodo_override, consultas_extra FROM usuarios WHERE user_id = ?",
            (user_id,)
        ).fetchone()

    if row and row[0] is not None:
        # Override individual activo
        return (row[0], row[1] or "diario")

    # Config basada en plan
    plan_id = obtener_plan(user_id)
    cfg = get_config_plan(plan_id)
    base = cfg["consultas"]
    periodo = cfg.get("periodo", "diario")

    if base == -1:
        return (-1, periodo)

    extra = row[2] if row and row[2] else 0
    return (base + extra, periodo)


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


def consultas_periodo_actual(user_id: int) -> int:
    """Conteo de consultas del usuario en el período activo (diario/semanal/mensual)."""
    _, periodo = _get_limite_y_periodo(user_id)
    clave = _periodo_key(periodo)
    with get_db() as con:
        row = con.execute(
            "SELECT cantidad FROM consultas_periodo WHERE user_id = ? AND clave = ?",
            (user_id, clave)
        ).fetchone()
    return row[0] if row else 0


def limite_diario(user_id: int) -> int:
    """Retorna el límite efectivo del usuario (alias para compatibilidad)."""
    limite, _ = _get_limite_y_periodo(user_id)
    return limite


def puede_consultar(user_id: int) -> bool:
    limite, _ = _get_limite_y_periodo(user_id)
    if limite == -1:  # ilimitado
        return True
    return consultas_periodo_actual(user_id) < limite


def registrar_consulta(user_id: int):
    hoy = date.today().isoformat()
    # Mantener tabla legacy para estadísticas históricas
    with get_db() as con:
        con.execute("""
            INSERT INTO consultas_diarias (user_id, fecha, cantidad)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, fecha) DO UPDATE SET cantidad = cantidad + 1
        """, (user_id, hoy))
    # Tabla nueva: conteo por período activo
    _, periodo = _get_limite_y_periodo(user_id)
    clave = _periodo_key(periodo)
    with get_db() as con:
        con.execute("""
            INSERT INTO consultas_periodo (user_id, clave, cantidad)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, clave) DO UPDATE SET cantidad = cantidad + 1
        """, (user_id, clave))


def consultas_restantes(user_id: int) -> int:
    limite, _ = _get_limite_y_periodo(user_id)
    if limite == -1:
        return -1  # ilimitado
    return max(0, limite - consultas_periodo_actual(user_id))


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

def guardar_mensaje(user_id: int, rol: str, mensaje: str, limite: int = None):
    """Guarda un mensaje y recorta el historial del usuario a `limite` mensajes
    (ring buffer). `limite` permite una ventana corta para usuarios gratis."""
    if limite is None:
        limite = config.MAX_HISTORIAL
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
        """, (user_id, user_id, limite))


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

def guardar_feedback(user_id: int, tipo: str, comentario: str = "",
                     pregunta_ctx: str = "", temas_ctx: str = "",
                     leyes_ctx: str = ""):
    """Guarda feedback. Los campos *_ctx son opcionales y capturan el contexto
    de la última consulta del usuario (para análisis post-mortem de respuestas
    que generaron feedback negativo).
    """
    with get_db() as con:
        con.execute(
            "INSERT INTO feedback (user_id, tipo, comentario, "
            "pregunta_contexto, temas_contexto, leyes_contexto) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, tipo, comentario,
             (pregunta_ctx or "")[:500], temas_ctx or "", leyes_ctx or "")
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

def guardar_ticket_soporte(user_id: int, mensaje: str, direccion: str = "user_to_admin",
                           pregunta_ctx: str = "", temas_ctx: str = "",
                           leyes_ctx: str = ""):
    """Guarda ticket de soporte. Campos *_ctx capturan el contexto de la
    última consulta del usuario para análisis post-mortem.
    """
    with get_db() as con:
        con.execute(
            "INSERT INTO soporte (user_id, mensaje, direccion, "
            "pregunta_contexto, temas_contexto, leyes_contexto) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, mensaje, direccion,
             (pregunta_ctx or "")[:500], temas_ctx or "", leyes_ctx or "")
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


# ─── ABOGADOS VERIFICADOS ────────────────────────────────────────────────────

import json as _json


def es_abogado(user_id: int) -> bool:
    """True si el user_id está vinculado a un abogado activo."""
    with get_db() as con:
        row = con.execute(
            "SELECT id FROM abogados WHERE user_id = ? AND activo = 1", (user_id,)
        ).fetchone()
        return row is not None


def obtener_abogado_por_user(user_id: int) -> dict | None:
    """Obtiene el perfil del abogado vinculado a un user_id."""
    with get_db() as con:
        cur = con.execute(
            "SELECT * FROM abogados WHERE user_id = ? AND activo = 1", (user_id,)
        )
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        return dict(zip(cols, row)) if row else None


def actualizar_perfil_abogado(user_id: int, campos: dict) -> bool:
    """Abogado actualiza su propio perfil (campos permitidos solamente)."""
    _permitidos = {"biografia", "modalidad", "metodos_pago", "telefono", "notas"}
    campos_filtrados = {k: v for k, v in campos.items() if k in _permitidos}
    if not campos_filtrados:
        return False
    # Serializar metodos_pago a JSON si es lista
    if "metodos_pago" in campos_filtrados and isinstance(campos_filtrados["metodos_pago"], list):
        campos_filtrados["metodos_pago"] = _json.dumps(campos_filtrados["metodos_pago"], ensure_ascii=False)
    sets = ", ".join(f"{k} = ?" for k in campos_filtrados)
    vals = list(campos_filtrados.values()) + [user_id]
    with get_db() as con:
        cur = con.execute(
            f"UPDATE abogados SET {sets} WHERE user_id = ? AND activo = 1", vals
        )
        return cur.rowcount > 0


def admin_actualizar_abogado(abogado_id: int, campos: dict) -> bool:
    """Admin actualiza cualquier campo del perfil de un abogado."""
    if not campos:
        return False
    if "metodos_pago" in campos and isinstance(campos["metodos_pago"], list):
        campos["metodos_pago"] = _json.dumps(campos["metodos_pago"], ensure_ascii=False)
    sets = ", ".join(f"{k} = ?" for k in campos)
    vals = list(campos.values()) + [abogado_id]
    with get_db() as con:
        cur = con.execute(
            f"UPDATE abogados SET {sets} WHERE id = ?", vals
        )
        return cur.rowcount > 0


def set_membresia(abogado_id: int, tipo: str, expira: str | None = None) -> bool:
    """Asigna membresía a un abogado. Si tipo='beta', suma 100 al ranking."""
    ranking_bonus = 100 if tipo == "beta" else 0
    with get_db() as con:
        cur = con.execute(
            "UPDATE abogados SET membresia = ?, membresia_expira = ?, "
            "ranking = ranking + ? WHERE id = ?",
            (tipo, expira, ranking_bonus, abogado_id)
        )
        return cur.rowcount > 0


def listar_abogados_directorio(especialidad: str = None, estado_geo: str = None,
                                modalidad: str = None) -> list[dict]:
    """Lista pública del directorio: solo activos con membresía activa/beta,
    ordenados por ranking DESC. No expone user_id ni cedula."""
    query = ("SELECT id, nombre, inpreabogado, especialidad, telefono, estado, "
             "notas, modalidad, biografia, metodos_pago, membresia, ranking, "
             "consultas_atendidas, calificacion, verificado "
             "FROM abogados WHERE activo = 1 AND membresia IN ('activa','beta')")
    params = []
    if especialidad:
        query += " AND LOWER(especialidad) LIKE ?"
        params.append(f"%{especialidad.lower()}%")
    if estado_geo:
        query += " AND LOWER(estado) LIKE ?"
        params.append(f"%{estado_geo.lower()}%")
    if modalidad and modalidad != "todos":
        query += " AND (modalidad = ? OR modalidad = 'ambas')"
        params.append(modalidad)
    query += " ORDER BY ranking DESC, calificacion DESC"
    with get_db() as con:
        cur = con.execute(query, params)
        cols = [d[0] for d in cur.description]
        rows = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            # Parsear metodos_pago de JSON a lista
            try:
                d["metodos_pago"] = _json.loads(d.get("metodos_pago") or "[]")
            except Exception:
                d["metodos_pago"] = []
            rows.append(d)
        return rows


def listar_abogados_admin(incluir_inactivos: bool = True) -> list[dict]:
    """Lista completa para admin con todos los campos."""
    query = "SELECT * FROM abogados"
    if not incluir_inactivos:
        query += " WHERE activo = 1"
    query += " ORDER BY ranking DESC, nombre ASC"
    with get_db() as con:
        cur = con.execute(query)
        cols = [d[0] for d in cur.description]
        rows = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            try:
                d["metodos_pago"] = _json.loads(d.get("metodos_pago") or "[]")
            except Exception:
                d["metodos_pago"] = []
            rows.append(d)
        return rows


# ─── SOLICITUDES DE ABOGADO ──────────────────────────────────────────────────

def _usuario_info(user_id: int) -> dict:
    """Retorna nombre y username del usuario desde la tabla usuarios."""
    with get_db() as con:
        row = con.execute(
            "SELECT nombre, username FROM usuarios WHERE user_id = ?", (user_id,)
        ).fetchone()
    if row:
        return {"nombre": row[0] or "", "username": row[1] or ""}
    return {"nombre": "", "username": ""}


def crear_solicitud_abogado(user_id: int, nombre: str, cedula: str,
                             inpreabogado: str, especialidad: list, telefono: str,
                             estado_geo: str, biografia: str = "",
                             modalidad: str = "presencial",
                             metodos_pago: list | None = None) -> int:
    """Crea una solicitud de verificación. Retorna el id o lanza ValueError."""
    metodos_pago = metodos_pago or []
    with get_db() as con:
        # Bloquear si tiene solicitud activa (pendiente, en_revision, correccion_solicitada)
        existente = con.execute(
            "SELECT id FROM solicitudes_abogado WHERE user_id = ? "
            "AND estado_solicitud IN ('pendiente','en_revision','correccion_solicitada')",
            (user_id,)
        ).fetchone()
        if existente:
            raise ValueError("Ya tienes una solicitud activa")
        # Validar: inpreabogado no registrado
        registrado = con.execute(
            "SELECT id FROM abogados WHERE inpreabogado = ? AND activo = 1",
            (inpreabogado,)
        ).fetchone()
        if registrado:
            raise ValueError("Este INPREABOGADO ya está registrado")
        cur = con.execute("""
            INSERT INTO solicitudes_abogado
                (user_id, nombre, cedula, inpreabogado, especialidad, telefono,
                 estado_geo, biografia, modalidad, metodos_pago)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, nombre, cedula, inpreabogado,
              _json.dumps(especialidad, ensure_ascii=False), telefono,
              estado_geo, biografia, modalidad,
              _json.dumps(metodos_pago, ensure_ascii=False)))
        return cur.lastrowid


def _parsear_solicitud(d: dict) -> dict:
    """Parsea campos JSON de una solicitud."""
    try:
        d["metodos_pago"] = _json.loads(d.get("metodos_pago") or "[]")
    except Exception:
        d["metodos_pago"] = []
    try:
        esp = d.get("especialidad") or "[]"
        d["especialidad"] = _json.loads(esp) if esp.startswith("[") else [esp]
    except Exception:
        d["especialidad"] = [d.get("especialidad", "")]
    return d


def listar_solicitudes(estado_solicitud: str = "pendiente",
                       limit: int = 50) -> list[dict]:
    """Lista solicitudes de abogados filtradas por estado."""
    with get_db() as con:
        cur = con.execute(
            "SELECT * FROM solicitudes_abogado WHERE estado_solicitud = ? "
            "ORDER BY id DESC LIMIT ?",
            (estado_solicitud, limit)
        )
        cols = [d[0] for d in cur.description]
        return [_parsear_solicitud(dict(zip(cols, row))) for row in cur.fetchall()]


def obtener_solicitud(solicitud_id: int) -> dict | None:
    """Obtiene una solicitud por id."""
    with get_db() as con:
        cur = con.execute("SELECT * FROM solicitudes_abogado WHERE id = ?", (solicitud_id,))
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        if not row:
            return None
        return _parsear_solicitud(dict(zip(cols, row)))


def estado_solicitud_usuario(user_id: int) -> dict:
    """Estado de solicitud y rol del usuario para la TMA.
    Retorna datos completos de la solicitud para permitir edición."""
    with get_db() as con:
        # Abogado activo
        abogado_activo = con.execute(
            "SELECT id FROM abogados WHERE user_id = ? AND activo = 1", (user_id,)
        ).fetchone()
        if abogado_activo:
            return {"es_abogado": True, "tiene_solicitud": False, "estado": None, "solicitud": None}
        # Abogado que se dio de baja voluntariamente (activo=0) —
        # se trata como usuario nuevo: puede solicitar de nuevo sin bloquearse
        abogado_baja = con.execute(
            "SELECT id FROM abogados WHERE user_id = ? AND activo = 0", (user_id,)
        ).fetchone()
        if abogado_baja:
            return {"es_abogado": False, "tiene_solicitud": False, "estado": None, "solicitud": None}
        row = con.execute(
            "SELECT * FROM solicitudes_abogado WHERE user_id = ? "
            "AND estado_solicitud != 'cancelada' ORDER BY id DESC LIMIT 1",
            (user_id,)
        ).fetchone()
        if row:
            cols = [d[0] for d in con.execute(
                "SELECT * FROM solicitudes_abogado LIMIT 0").description]
            sol = _parsear_solicitud(dict(zip(cols, row)))
            return {
                "es_abogado": False,
                "tiene_solicitud": True,
                "estado": sol["estado_solicitud"],
                "solicitud": sol,
            }
        return {"es_abogado": False, "tiene_solicitud": False, "estado": None, "solicitud": None}


def marcar_en_revision(solicitud_id: int, admin_id: int) -> dict | None:
    """Marca una solicitud como en revisión. Retorna {user_id, nombre}."""
    with get_db() as con:
        sol = con.execute(
            "SELECT user_id, nombre FROM solicitudes_abogado "
            "WHERE id = ? AND estado_solicitud = 'pendiente'",
            (solicitud_id,)
        ).fetchone()
        if not sol:
            return None
        con.execute(
            "UPDATE solicitudes_abogado SET estado_solicitud = 'en_revision', "
            "revisado_por = ?, revisado_en = CURRENT_TIMESTAMP WHERE id = ?",
            (admin_id, solicitud_id)
        )
        return {"user_id": sol[0], "nombre": sol[1]}


def actualizar_solicitud(solicitud_id: int, user_id: int, campos: dict) -> bool:
    """Permite al solicitante editar su solicitud si está en pendiente o correccion_solicitada."""
    permitidos = {"nombre", "cedula", "inpreabogado", "especialidad", "telefono",
                  "estado_geo", "biografia", "modalidad", "metodos_pago"}
    campos = {k: v for k, v in campos.items() if k in permitidos}
    if not campos:
        return False
    # Serializar campos JSON
    if "metodos_pago" in campos and isinstance(campos["metodos_pago"], list):
        campos["metodos_pago"] = _json.dumps(campos["metodos_pago"], ensure_ascii=False)
    if "especialidad" in campos and isinstance(campos["especialidad"], list):
        campos["especialidad"] = _json.dumps(campos["especialidad"], ensure_ascii=False)
    # Resetear a pendiente al editar (recomienza el ciclo de revisión)
    campos["estado_solicitud"] = "pendiente"
    campos["motivo_rechazo"] = ""
    with get_db() as con:
        sol = con.execute(
            "SELECT id FROM solicitudes_abogado WHERE id = ? AND user_id = ? "
            "AND estado_solicitud IN ('pendiente','correccion_solicitada')",
            (solicitud_id, user_id)
        ).fetchone()
        if not sol:
            return False
        sets = ", ".join(f"{k} = ?" for k in campos)
        con.execute(
            f"UPDATE solicitudes_abogado SET {sets} WHERE id = ?",
            (*campos.values(), solicitud_id)
        )
        return True


def pedir_correccion(solicitud_id: int, admin_id: int, mensaje: str) -> dict | None:
    """Solicita correcciones al abogado. Retorna {user_id, nombre}."""
    with get_db() as con:
        sol = con.execute(
            "SELECT user_id, nombre FROM solicitudes_abogado "
            "WHERE id = ? AND estado_solicitud IN ('pendiente','en_revision')",
            (solicitud_id,)
        ).fetchone()
        if not sol:
            return None
        con.execute(
            "UPDATE solicitudes_abogado SET estado_solicitud = 'correccion_solicitada', "
            "motivo_rechazo = ?, revisado_por = ?, revisado_en = CURRENT_TIMESTAMP WHERE id = ?",
            (mensaje, admin_id, solicitud_id)
        )
        return {"user_id": sol[0], "nombre": sol[1]}


def aprobar_solicitud(solicitud_id: int, admin_id: int) -> dict | None:
    """Aprueba solicitud: la mueve a tabla abogados. Retorna dict con user_id."""
    with get_db() as con:
        sol = con.execute(
            "SELECT * FROM solicitudes_abogado WHERE id = ? "
            "AND estado_solicitud IN ('pendiente','en_revision')",
            (solicitud_id,)
        ).fetchone()
        if not sol:
            return None
        cols = [d[0] for d in con.execute("SELECT * FROM solicitudes_abogado LIMIT 0").description]
        sol_dict = dict(zip(cols, sol))
        # Marcar solicitud como aprobada
        con.execute(
            "UPDATE solicitudes_abogado SET estado_solicitud = 'aprobada', "
            "revisado_por = ?, revisado_en = CURRENT_TIMESTAMP WHERE id = ?",
            (admin_id, solicitud_id)
        )
        # Insertar en abogados
        cur = con.execute("""
            INSERT INTO abogados
                (nombre, cedula, inpreabogado, especialidad, telefono, estado,
                 notas, user_id, modalidad, biografia, metodos_pago,
                 membresia, verificado, activo)
            VALUES (?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, 'inactiva', 1, 1)
        """, (
            sol_dict["nombre"], sol_dict["cedula"], sol_dict["inpreabogado"],
            sol_dict["especialidad"], sol_dict["telefono"], sol_dict["estado_geo"],
            sol_dict["user_id"], sol_dict["modalidad"], sol_dict["biografia"],
            sol_dict["metodos_pago"],
        ))
        return {"abogado_id": cur.lastrowid, "user_id": sol_dict["user_id"],
                "nombre": sol_dict["nombre"]}


def rechazar_solicitud(solicitud_id: int, admin_id: int,
                       motivo: str = "") -> dict | None:
    """Rechaza una solicitud. Retorna dict con user_id para notificar."""
    with get_db() as con:
        sol = con.execute(
            "SELECT user_id FROM solicitudes_abogado WHERE id = ? "
            "AND estado_solicitud IN ('pendiente','en_revision','correccion_solicitada')",
            (solicitud_id,)
        ).fetchone()
        if not sol:
            return None
        con.execute(
            "UPDATE solicitudes_abogado SET estado_solicitud = 'rechazada', "
            "motivo_rechazo = ?, revisado_por = ?, revisado_en = CURRENT_TIMESTAMP WHERE id = ?",
            (motivo, admin_id, solicitud_id)
        )
        return {"user_id": sol[0]}


def cancelar_solicitud(user_id: int) -> bool:
    """El usuario cancela su solicitud pendiente o en revisión."""
    with get_db() as con:
        cur = con.execute(
            "UPDATE solicitudes_abogado SET estado_solicitud = 'cancelada' "
            "WHERE user_id = ? AND estado_solicitud IN ('pendiente','en_revision','correccion_solicitada')",
            (user_id,)
        )
        return cur.rowcount > 0


def obtener_nombre_abogado(user_id: int) -> str | None:
    """Devuelve el nombre del abogado dado su user_id."""
    with get_db() as con:
        row = con.execute(
            "SELECT nombre FROM abogados WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row[0] if row else None


def baja_abogado(user_id: int) -> bool:
    """El abogado se da de baja (activo=0)."""
    with get_db() as con:
        cur = con.execute(
            "UPDATE abogados SET activo = 0 WHERE user_id = ? AND activo = 1",
            (user_id,)
        )
        return cur.rowcount > 0


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


def registrar_consulta_log(user_id: int, pregunta: str, temas: list[str],
                           leyes: list[str], confianza: str = "",
                           respuesta: str = "", distancia: float = 0.0) -> int:
    """Registra una consulta enriquecida en consultas_log.

    Guarda pregunta (truncada a 500), temas/leyes, confianza, distancia y la
    RESPUESTA (truncada a 6000) para poder auditar todas las consultas.
    Retorna el id de la fila insertada.
    """
    pregunta = (pregunta or "").strip()[:500]
    temas_str = ",".join(temas) if temas else ""
    leyes_str = " | ".join(leyes) if leyes else ""
    respuesta = (respuesta or "").strip()[:6000]
    hoy = date.today().isoformat()
    with get_db() as con:
        cur = con.execute(
            "INSERT INTO consultas_log (user_id, pregunta, temas, leyes, confianza, "
            "fecha, respuesta, distancia) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, pregunta, temas_str, leyes_str, confianza, hoy, respuesta, distancia)
        )
        return cur.lastrowid


def exportar_consultas_log(dias: int = 7) -> list[dict]:
    """Devuelve las consultas (con respuesta) de los últimos `dias` días, para
    auditar. Más recientes primero."""
    with get_db() as con:
        cur = con.execute(
            "SELECT timestamp, user_id, confianza, distancia, temas, leyes, pregunta, respuesta "
            "FROM consultas_log "
            "WHERE fecha >= date('now', ?) "
            "ORDER BY id DESC",
            (f"-{int(dias)} days",)
        )
        cols = ["timestamp", "user_id", "confianza", "distancia", "temas", "leyes", "pregunta", "respuesta"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def obtener_ultima_consulta_log(user_id: int) -> dict | None:
    """Devuelve el contexto (pregunta/temas/leyes) de la última consulta del
    usuario. Usado para enriquecer /opinion y /soporte.
    """
    with get_db() as con:
        row = con.execute(
            "SELECT pregunta, temas, leyes, confianza FROM consultas_log "
            "WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,)
        ).fetchone()
    if not row:
        return None
    return {
        "pregunta": row[0] or "",
        "temas": row[1] or "",
        "leyes": row[2] or "",
        "confianza": row[3] or "",
    }


def obtener_preguntas_sin_tema(limit: int = 10, dias: int = 7) -> list[dict]:
    """Preguntas de los últimos N días donde no se detectó ningún tema (temas='').

    Estas son candidatas a generar nuevos temas/keywords en articulos_clave.json.
    Retorna lista de dicts con pregunta, confianza, count (agrupadas).
    """
    hoy = date.today().isoformat()
    with get_db() as con:
        filas = con.execute(
            "SELECT pregunta, confianza FROM consultas_log "
            "WHERE fecha >= date(?, ?) AND (temas = '' OR temas IS NULL) "
            "AND pregunta != ''",
            (hoy, f"-{dias - 1} days")
        ).fetchall()

    agrupado: dict[str, dict] = {}
    for pregunta, confianza in filas:
        key = pregunta.lower().strip()
        if not key:
            continue
        if key not in agrupado:
            agrupado[key] = {"pregunta": pregunta.strip(), "count": 0, "confianza": confianza or ""}
        agrupado[key]["count"] += 1

    return sorted(agrupado.values(), key=lambda x: x["count"], reverse=True)[:limit]


def obtener_top_preguntas_dia(limit: int = 20, dias: int = 1) -> list[dict]:
    """Top preguntas de los últimos N días (por defecto hoy).

    Agrupa preguntas idénticas (case-insensitive) y retorna conteo, temas
    más frecuentes por pregunta, y leyes más frecuentes.
    """
    hoy = date.today().isoformat()
    with get_db() as con:
        filas = con.execute(
            "SELECT pregunta, temas, leyes FROM consultas_log "
            "WHERE fecha >= date(?, ?) AND pregunta != ''",
            (hoy, f"-{dias - 1} days")
        ).fetchall()

    # Agrupar por pregunta normalizada (lowercase + strip)
    agrupado: dict[str, dict] = {}
    for pregunta, temas, leyes in filas:
        key = pregunta.lower().strip()
        if not key:
            continue
        if key not in agrupado:
            agrupado[key] = {
                "pregunta": pregunta.strip(),
                "count": 0,
                "temas": {},
                "leyes": {},
            }
        agrupado[key]["count"] += 1
        for t in (temas or "").split(","):
            t = t.strip()
            if t:
                agrupado[key]["temas"][t] = agrupado[key]["temas"].get(t, 0) + 1
        for l in (leyes or "").split("|"):
            l = l.strip()
            if l:
                agrupado[key]["leyes"][l] = agrupado[key]["leyes"].get(l, 0) + 1

    # Ordenar por conteo descendente
    resultado = sorted(agrupado.values(), key=lambda x: x["count"], reverse=True)[:limit]
    # Aplanar temas/leyes a lista ordenada
    for r in resultado:
        r["temas"] = sorted(r["temas"].items(), key=lambda x: x[1], reverse=True)[:5]
        r["leyes"] = sorted(r["leyes"].items(), key=lambda x: x[1], reverse=True)[:3]
    return resultado


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
