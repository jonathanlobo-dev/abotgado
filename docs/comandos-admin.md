# Comandos de administrador — aBOTgado

Referencia de todos los comandos disponibles para administradores en el bot de Telegram.
Solo responden a los IDs listados en `ADMIN_IDS` (variable de entorno `.env`).
Todos se escriben en el chat del bot, igual que cualquier mensaje.

> **Nota sobre los argumentos:** `<ID o @username>` acepta tanto el ID numérico
> de Telegram como el `@usuario`. El usuario destino debe haber usado el bot al
> menos una vez (para que exista en la base de datos).

---

## 🎛️ Planes, límites y consultas (lo que cambia "esas cosas")

| Comando | Uso | Qué hace |
|---|---|---|
| `/set_plan` | `/set_plan <plan> <cantidad> <diario\|semanal\|mensual>` | Cambia el **límite de consultas de TODO un plan**. `plan`: `gratis`, `pionero`, `premium`. `cantidad`: entero (`-1` = ilimitado). Ej: `/set_plan gratis 3 semanal` |
| `/set_user_limit` | `/set_user_limit <ID o @username> <cantidad> <diario\|semanal\|mensual>` | Fija un **límite personalizado a UN usuario** (sobrescribe el de su plan). Ej: `/set_user_limit 123456 20 mensual` |
| `/quitar_user_limit` | `/quitar_user_limit <ID o @username>` | Quita el límite personalizado y devuelve al usuario al límite de su plan. |
| `/regalar_consultas` | `/regalar_consultas <ID o @username> [cantidad]` | Suma consultas extra puntuales al usuario (se acumulan sobre su límite). |
| `/ver_planes` | `/ver_planes` | Muestra los límites actuales de cada plan. |

> **El que buscabas para "cambiar esas cosas":** `/set_plan` (afecta a todos los
> de un plan) o `/set_user_limit` (a un usuario puntual).

---

## 👤 Gestión de usuarios y planes

| Comando | Uso | Qué hace |
|---|---|---|
| `/premium_on` | `/premium_on <ID o @username> [más...]` | Activa plan Premium a uno o varios usuarios. |
| `/premium_off` | `/premium_off <ID o @username> [más...]` | Desactiva Premium (vuelve a Gratis). |
| `/tester` | `/tester <ID o @username> [más...]` | Activa plan Pionero/Tester. |
| `/set_plan` | (ver arriba) | También se usa para límites de plan. |
| `/plan_add` | `/plan_add <ID o @username> [días]` | Extiende la membresía del usuario (default `+7` días). |
| `/plan_del` | `/plan_del <ID o @username> [días]` | Reduce la membresía (default `-7` días). |
| `/regalar_doc` | `/regalar_doc <ID o @username> [cantidad]` | Regala documentos generables (.docx) al usuario. |
| `/regalar_memoria` | `/regalar_memoria <ID o @username> [más...]` | Activa la memoria de conversación a un usuario. |
| `/usuarios` | `/usuarios` | Lista los usuarios registrados con su plan y consumo. |

---

## 📊 Monitoreo y estadísticas

| Comando | Uso | Qué hace |
|---|---|---|
| `/stats_admin` | `/stats_admin` | Estadísticas globales: usuarios por plan, consultas, temas top. |
| `/ping` | `/ping` | Verifica que el bot responde y muestra el total de artículos en ChromaDB. |
| `/debug` | `/debug <consulta>` | Corre el pipeline de búsqueda mostrando el detalle del retrieval (temas, scores, artículos). Útil para diagnosticar por qué una consulta responde mal. |
| `/feedback` | `/feedback` | Lista los tickets de feedback (👎) de los usuarios. |
| `/feedback_borrar` | `/feedback_borrar [filtros]` | Borra feedback registrado. |

---

## 📣 Comunicación con usuarios

| Comando | Uso | Qué hace |
|---|---|---|
| `/anuncio` | `/anuncio <mensaje>` | Envía un anuncio masivo a todos los usuarios. |
| `/mensaje` | `/mensaje <user_id> <texto>` | Envía un mensaje directo a un usuario puntual. |
| `/responder` | `/responder <user_id> <mensaje>` | Responde a un ticket de soporte de un usuario. |

---

## ⚖️ Directorio de abogados

| Comando | Uso | Qué hace |
|---|---|---|
| `/add_abogado` | `/add_abogado` (flujo interactivo) | Inicia el registro de un abogado verificado. |
| `/abogados` | `/abogados` | Lista los abogados registrados. |
| `/del_abogado` | `/del_abogado <ID>` | Elimina un abogado del directorio. |
| `/activar_abogado` | `/activar_abogado <ID>` | Activa/verifica un abogado. |

---

## 🗄️ Sistema

| Comando | Uso | Qué hace |
|---|---|---|
| `/backup` | `/backup` | Genera y envía un respaldo de la base de datos SQLite. |
| `/plan_add`, `/plan_del` | (ver arriba) | Gestión de vigencia de membresías. |

---

## Notas operativas

- **Variables de entorno relacionadas** (se cambian en Railway, no por comando):
  - `ADMIN_IDS` — quién es admin (lista separada por comas).
  - `LLM_MODEL`, `LLM_MODEL_FAST`, `LLM_MODEL_ROUTER` — modelos de Groq.
  - `MAX_CONSULTA_CHARS` — tope de longitud de una consulta (default 1000).
  - `MAX_HISTORIAL_GRATIS` — mensajes de memoria corta para usuarios gratis (default 4).
  - `GUARDRAIL_CITAS_HABILITADO`, `VERIFICADOR_HABILITADO`, `ROUTER_HABILITADO` — flags del pipeline.
  - `TMA_ORIGINS` — dominios permitidos para CORS en la Mini App.
- Los límites por plan por defecto viven en `config.py` (`PLANES`); `/set_plan` los
  cambia en caliente sin redeploy.
- El preview de respuesta en las alertas admin se corta a ~1500 caracteres; **la
  respuesta que recibe el usuario NO se trunca** (sale completa).
