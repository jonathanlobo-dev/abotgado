# Comandos de administrador — aBOTgado

Referencia completa de los comandos para administradores del bot de Telegram.
Solo responden a los IDs listados en `ADMIN_IDS` (variable de entorno en `.env`).
Se escriben en el chat del bot como cualquier mensaje.

**Identificar usuarios:** donde dice `<ID o @username>` puedes usar el ID numérico
de Telegram (ej: `5331232692`) o el `@usuario` (ej: `@DALL970`). El usuario debe
haber usado el bot al menos una vez para existir en la base de datos; y para
buscarlo por `@username` debe tener su username público en Telegram.

---

# 👥 Comandos de usuario (los que ve cualquier persona)

Disponibles para todos los que usan el bot. El acceso depende del plan:
🆓 todos · ⭐ Pionero o superior · 💎 Premium.

| Comando | Plan | Qué hace | Ejemplo |
|---|---|---|---|
| `/start` | 🆓 | Inicia el bot y muestra el mensaje de bienvenida. | `/start` |
| `/ayuda` | 🆓 | Muestra la ayuda y la lista de comandos disponibles. | `/ayuda` |
| `/leyes` | 🆓 | Lista las leyes disponibles en el sistema (con sus alias). | `/leyes` |
| `/estado` | 🆓 | Muestra tu plan y cuántas consultas te quedan. | `/estado` |
| `/nuevo` | 🆓 | Limpia el chat/historial y empieza una conversación de cero. | `/nuevo` |
| `/referir` | 🆓 | Te da tu enlace de referido (invitar amigos = Pionero gratis). | `/referir` |
| `/app` | 🆓 | Abre la Mini App (versión web embebida en Telegram). | `/app` |
| `/soporte` | 🆓 | Inicia un ticket para contactar al equipo de soporte. | `/soporte` |
| `/opinion` | 🆓 | Deja tu opinión / feedback sobre el bot. | `/opinion` |
| `/ping` | 🆓 | Verifica que el bot está activo. | `/ping` |
| `/cancelar` | 🆓 | Cancela un flujo en curso (soporte, opinión, etc.). | `/cancelar` |
| `/ley` | ⭐ | Busca un artículo específico de una ley. | `/ley constitución 49` |
| `/comparar` | ⭐ | Compara dos artículos o leyes. | `/comparar LOTTT 79 vs CP 409` |
| `/guardar` | ⭐ | Guarda la última respuesta recibida. | `/guardar` |
| `/mis_consultas` | ⭐ | Lista tus respuestas guardadas. | `/mis_consultas` |
| `/ver_guardado` | ⭐ | Muestra una respuesta guardada por su número. | `/ver_guardado 1` |
| `/borrar_guardados` | ⭐ | Borra todas tus respuestas guardadas. | `/borrar_guardados` |
| `/stats` | ⭐ | Tus estadísticas de uso (consultas, favoritos). | `/stats` |
| `/documento` | 💎 | Genera un documento legal (.docx) a partir de una plantilla. | `/documento` |

> Para hacer una consulta legal NO hace falta ningún comando: el usuario escribe
> su pregunta en lenguaje normal y el bot responde.

---

# 🔐 Comandos de administrador

Lo que sigue solo responde a los IDs en `ADMIN_IDS`.

---

## 👁️ Ver la configuración de los usuarios

### `/usuarios`
Lista los usuarios registrados (los 20 más recientes) con su plan, consumo de hoy
y extras. Las etiquetas `[MEM]` = memoria activa, `[DOC:n]` = documentos
disponibles, `exp:fecha` = vencimiento del plan Pionero.

```
/usuarios
```
Salida (ejemplo):
```
👥 15 usuarios

💎 Alexander (@Alexmendoza11) — ID: 811423133 — hoy: 3
⭐ Diego (@DALL970) — ID: 5331232692 — hoy: 1 [MEM] exp:2026-07-01
🆓 Gerardo (@ge13rge13r) — ID: 2140814867 — hoy: 5
```

### `/usuario <ID o @username>`  ← ver la config completa de UN usuario
Muestra toda la configuración básica de un usuario: plan, límite, consultas
(hoy / restantes / histórico), memoria, documentos, consultas extra, favoritos y
vencimiento si es Pionero.

```
/usuario @DALL970
/usuario 5331232692
```
Salida (ejemplo):
```
⭐ Diego (@DALL970)
ID: 5331232692
Registrado: 2026-06-10

📋 Plan: Pionero
🎫 Límite: 5 / día
📊 Consultas: hoy 1 · restantes 4 · histórico 37
🧠 Memoria: Sí
📄 Documentos disponibles: 2
➕ Consultas extra: 0
⭐ Favoritos: 3
⏳ Pionero expira: 2026-07-01
```

> **Nota:** estos comandos leen la base de datos viva (en Railway, `/data/abotgado_usuarios.db`).
> El archivo `abotgado_usuarios.db` del repo es local/de prueba y puede estar desactualizado.

---

## 🎛️ Planes y límites de consultas

### `/set_plan <plan> <cantidad> <diario|semanal|mensual>`
Cambia el límite de consultas de **TODO un plan** (en caliente, sin redeploy).
`plan`: `gratis`, `pionero`, `premium`. `cantidad`: entero (`-1` = ilimitado).

```
/set_plan gratis 3 semanal      → los gratis tendrán 3 consultas por semana
/set_plan pionero 10 diario     → los Pionero, 10 por día
/set_plan premium -1 diario     → Premium ilimitado
```

### `/set_user_limit <ID o @username> <cantidad> <diario|semanal|mensual>`
Fija un límite **personalizado a UN usuario**, que sobrescribe el de su plan.

```
/set_user_limit 5331232692 20 mensual    → ese usuario: 20 por mes
/set_user_limit @DALL970 -1 diario        → ese usuario: ilimitado
```

### `/quitar_user_limit <ID o @username>`
Quita el límite personalizado y devuelve al usuario al límite normal de su plan.

```
/quitar_user_limit @DALL970
```

### `/regalar_consultas <ID o @username> [cantidad]`
Suma consultas extra puntuales (se acumulan sobre el límite normal). Si omites la
cantidad, suma un valor por defecto.

```
/regalar_consultas @DALL970 10     → +10 consultas extra
/regalar_consultas 5331232692      → +5 (default)
```

### `/ver_planes`
Muestra los límites actuales configurados para cada plan.

```
/ver_planes
```

---

## 👤 Planes y membresías de usuarios

### `/premium_on <ID o @username> [más...]`
Activa el plan Premium a uno o varios usuarios (acepta varios separados por espacio).

```
/premium_on @DALL970
/premium_on 5331232692 811423133 @Alexmendoza11
```

### `/premium_off <ID o @username> [más...]`
Quita Premium (vuelve a Gratis).

```
/premium_off @DALL970
```

### `/tester <ID o @username> [más...]`
Activa el plan Pionero/Tester (con vigencia temporal).

```
/tester @DALL970
/tester 5331232692 811423133
```

### `/plan_add <ID o @username> [días]`
Extiende la vigencia de la membresía. Por defecto suma 7 días.

```
/plan_add @DALL970          → +7 días
/plan_add @DALL970 30       → +30 días
```

### `/plan_del <ID o @username> [días]`
Reduce la vigencia de la membresía. Por defecto resta 7 días.

```
/plan_del @DALL970 14       → -14 días
```

### `/regalar_memoria <ID o @username> [más...]`
Activa la memoria de conversación (la larga, normalmente premium) a un usuario.

```
/regalar_memoria @DALL970
```

### `/regalar_doc <ID o @username> [cantidad]`
Regala documentos generables (.docx) al usuario.

```
/regalar_doc @DALL970 3     → +3 documentos
/regalar_doc 5331232692     → +1 (default)
```

---

## 📊 Monitoreo y diagnóstico

### `/stats_admin`
Estadísticas globales: usuarios por plan, consultas (hoy/semana/total), temas más
consultados.

```
/stats_admin
```

### `/ping`
Verifica que el bot responde y muestra el total de artículos indexados en ChromaDB.

```
/ping        → 🏓 Pong — Artículos en DB: 14007
```

### `/debug <consulta>`
Corre el pipeline de búsqueda mostrando el detalle interno (temas detectados,
scores, artículos recuperados). Sirve para diagnosticar por qué una consulta
responde mal.

```
/debug Mi vecino puso un gimnasio y pone música alta
/debug un paciente me grabó en la consulta
```

### `/auditar [días]`  ← revisar TODAS las preguntas y respuestas
Exporta un **Excel (.xlsx)** descargable y formateado con **todas las consultas**
(pregunta + respuesta completa + confianza + distancia + temas + leyes) de los
últimos N días (default 7, máx 90). No depende del feedback: te deja revisar
respuestas que nadie reportó. El archivo trae encabezado fijo, autofiltro, la
columna **Confianza** coloreada (verde=alta, ámbar=media, rojo=baja) y la fecha y
la distancia ya formateadas. Usa el filtro del encabezado para ordenar por
`Confianza` o `Distancia` y hallar las respuestas dudosas primero.

```
/auditar          → últimos 7 días
/auditar 3        → últimos 3 días
/auditar 30       → último mes
```

### `/historial <ID o @username> [N]`  ← ver la conversación completa de UN usuario
Muestra el hilo de las últimas N consultas (default 20, máx 50) de un usuario en
orden cronológico, con la pregunta y el resumen (📌) de cada respuesta, más la
confianza (🟢/🟡/🔴) y los temas. Ideal para **depurar** cuando una alerta de
confianza media/baja se ve mal y quieres entender de dónde viene el hilo (los
seguimientos solo tienen sentido viendo la conversación completa). Lee de
`consultas_log`, así que muestra el histórico real, no el ring-buffer recortado.

```
/historial @milygc        → últimas 20 consultas de esa usuaria
/historial 754152388 15   → últimas 15 de ese ID
```

### `/feedback`
Lista los tickets de feedback negativo (👎) que dejaron los usuarios.

```
/feedback
```

### `/feedback_borrar`
Borra feedback registrado (según filtros).

```
/feedback_borrar
```

---

## 📣 Comunicación con usuarios

### `/anuncio <mensaje>`
Envía un anuncio masivo a TODOS los usuarios.

```
/anuncio Estamos en mantenimiento esta noche de 11pm a 12am. Gracias.
```

### `/mensaje <ID o @username> <texto>`
Envía un mensaje directo a un usuario puntual. (Acepta `@username`.)

```
/mensaje @DALL970 Hola, vimos tu consulta y queremos ayudarte mejor.
/mensaje 5331232692 Tu plan Pionero fue extendido 30 días.
```

### `/responder <ID o @username> <mensaje>`
Responde a un ticket de soporte de un usuario. (Acepta `@username`.)

```
/responder @DALL970 Ya corregimos el problema que reportaste, gracias.
/responder 5331232692 Tu documento está listo, revisa tu chat.
```

---

## ⚖️ Directorio de abogados

### `/add_abogado`
Inicia el registro interactivo de un abogado verificado (te pide los datos paso a paso).

```
/add_abogado
```

### `/abogados`
Lista los abogados registrados en el directorio.

```
/abogados
```

### `/del_abogado <ID>`
Elimina un abogado del directorio. **Ojo:** aquí el `<ID>` es el ID interno del
abogado en la base de datos (lo ves con `/abogados`), NO el user_id de Telegram.

```
/del_abogado 4
```

### `/activar_abogado <ID>`
Activa/verifica un abogado. El `<ID>` también es el ID interno del abogado.

```
/activar_abogado 4
```

---

## 🗄️ Sistema

### `/backup`
Genera y envía un respaldo de la base de datos SQLite al chat.

```
/backup
```

---

## Configuración por variables de entorno (Railway, no por comando)

Estas no se cambian con un comando del bot, sino en las variables de entorno del
deploy. Reinician el bot al cambiarlas.

| Variable | Para qué |
|---|---|
| `ADMIN_IDS` | Quién es admin (IDs separados por comas). |
| `LLM_MODEL`, `LLM_MODEL_FAST`, `LLM_MODEL_ROUTER` | Modelos de Groq del pipeline. |
| `MAX_CONSULTA_CHARS` | Tope de longitud de una consulta (default 1000). |
| `MAX_HISTORIAL_GRATIS` | Mensajes de memoria corta para usuarios gratis (default 4 ≈ 2 turnos). |
| `GUARDRAIL_CITAS_HABILITADO` | Validación de citas (Self-RAG); default activado. |
| `VERIFICADOR_HABILITADO` | Verificador de relevancia post-retrieval. |
| `ROUTER_HABILITADO` | Router LLM de clasificación. |
| `TMA_ORIGINS` | Dominios permitidos para CORS en la Mini App. |

**Recordatorio:** el preview de respuesta en las alertas admin se corta a ~1500
caracteres; **la respuesta que recibe el usuario NO se trunca** (sale completa).
