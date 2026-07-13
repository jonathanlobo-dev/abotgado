# Seguridad — aBOTgado

Invariantes de seguridad del proyecto. **Cualquier cambio debe respetarlas.**
Última auditoría: 2026-07-13 (superficie de ataque completa de api.py + bot).

## Invariantes (NO romper)

1. **La identidad del usuario en la TMA sale SOLO del `initData` firmado de
   Telegram** (`_validar_init_data`, HMAC con el token del bot, max 7 días).
   El `user_id` que venga en body/path/query es informativo y suplantable —
   jamás usarlo como identidad. El fallback `DEV_MODE=1` es solo para dev
   local y no debe estar activo en Railway.
2. **Privilegios de admin por dos vías, ambas server-side**: (a) initData
   firmado cuyo uid esté en `ADMIN_IDS` (TMA/bot); (b) header `X-Admin-Key`
   comparado con `hmac.compare_digest` contra la env `ADMIN_KEY` (panel web,
   `api_admin.py`). Sin la env definida, los endpoints `/admin/*` del panel
   devuelven 403 siempre. No crear endpoints privilegiados con otra auth.
3. **Cuotas server-side**: `puede_consultar` + anti-flood de ráfaga ANTES de
   tocar el LLM. Los límites por plan viven en la DB/config del servidor,
   nunca en el cliente.
4. **Entrada del usuario = hostil**: toda pregunta pasa por `seguridad.py`
   (detección de prompt injection ~20 patrones, `sanitizar_input`, filtro de
   teléfonos/montos inventados en la salida). Los campos de documentos pasan
   por `_sanitizar_campo_doc` (tipo + longitud). No saltarse estos filtros al
   agregar flujos nuevos.
5. **Secretos solo en env de Railway**: `TELEGRAM_TOKEN`, `GROQ_API_KEY`,
   `HF_API_KEY`, `ADMIN_IDS`, `ADMIN_KEY`. Nunca en el repo (`.env` ignorado)
   ni en la TMA.
6. **SQL siempre parametrizado** (db.py usa `?` placeholders en todo). No
   interpolar strings del usuario en consultas.
7. **Mensajería saliente** (mensaje directo, anuncios): solo desde endpoints
   admin; el broadcast respeta el rate limit de Telegram (~0.08s/msg) y corre
   en BackgroundTasks. Nada permite a un usuario normal enviar mensajes a
   otros usuarios.
8. **El disclaimer legal** ("Info orientativa. Consulta un abogado.") es parte
   del producto — no removerlo de las respuestas.

## Riesgos aceptados / a vigilar

- La TMA renderiza `respuesta` con innerHTML (HTML estilo Telegram generado
  por el LLM). Mitigado por los prompts y el subconjunto de tags usado, pero
  es el punto a endurecer si algún día el LLM queda expuesto a contenido de
  terceros (ej. RAG sobre documentos subidos por usuarios): ahí habría que
  sanitizar la salida con allowlist de tags.
- `/directorio` (abogados activos) es público a propósito — no incluir en él
  datos que el abogado no haya aceptado publicar.
- SQLite en volumen de Railway: sin réplica; el backup es responsabilidad
  operativa (export periódico pendiente).

## Al agregar features nuevas — checklist

- ¿Identifica a un usuario? → initData firmado, nunca el id declarado.
- ¿Es acción de admin? → ADMIN_IDS (initData) o X-Admin-Key (compare_digest).
- ¿Llega texto al LLM? → pasar por seguridad.py.
- ¿Genera mensajes salientes? → solo admin + rate limit.
- ¿Nuevo secreto? → env en Railway.
