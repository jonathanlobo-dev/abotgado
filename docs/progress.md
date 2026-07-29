# Estado del Proyecto — aBOTgado

## Resumen
Bot jurídico venezolano en Telegram con RAG híbrido (keywords curados + BM25 + embeddings + Groq LLM). Desplegado en Railway. Incluye Mini App (TMA) y panel de administración web.

---

## Completado ✅

### Motor / RAG
- Pipeline híbrido funcionando: keywords curados (114 temas en `articulos_clave.json`) + BM25 + embeddings + Groq LLM, con router de intención (nueva/seguimiento/saludo/fuera_dominio)
- 77 leyes indexadas (~14.276 artículos), incluida la Ley Orgánica de Educación
- Auto-reindex por fingerprint de PDFs + `leyes_config.json` en `start.py`, con validación de umbral mínimo de artículos (evita arrancar con DB corrupta)
- Indexación incremental por hash MD5 en `1_procesar_leyes.py`
- Sistema de confianza (alta/media/baja) con alertas admin 🟢🟡🔴
- Cache de embeddings (`lru_cache`, 2000 entradas) para queries repetidas
- Sistema de exclusiones (`"excluir"`) por tema para evitar falsos positivos

### Guardrails anti-alucinación
- Prohibición absoluta de citar artículos fuera de la lista recuperada + guardrail de auto-regeneración si detecta cita fabricada
- Principio de libertad ("no está prohibido = permitido") para actividades no reguladas
- Anti-invención de instituciones/ministerios (incluida regla específica para constituir organizaciones/colegios profesionales)
- Nomenclatura corregida de forma determinista (Corte Suprema → TSJ, Tribunal de Circuito → tribunal competente)
- Especificidad numérica: no deducir edades/plazos/montos de artículos que no los dan
- Dead-end en 2 niveles sin loops: pregunta vaga → pide contexto una vez; sin cobertura tras pregunta detallada/seguimiento → admite honestamente, sin repetir
- Hedge de ambigüedad cross-rama endurecido (solo con tema curado como ancla)
- Repregunta determinista para arrendamiento vivienda vs. comercial (sin LLM extra)
- Detección de prompt injection e intención dañina

### Bot de Telegram
- Sistema de planes: Gratis / Pionero / Premium, con límites configurables en caliente
- Memoria de conversación activada para TODOS los usuarios en fase de pruebas (`MEMORIA_PARA_TODOS`)
- `/historial <usuario>` para ver el hilo completo de un usuario (debugging de casos reportados)
- `/auditar` exporta Excel (.xlsx) formateado con todas las consultas (no solo las que recibieron feedback)
- Acuse automático y tranquilizador al recibir 👎 (sin trabajo manual por caso)
- Rate limit anti-flood en memoria (máx `RATE_LIMIT_MAX_CONSULTAS` por `RATE_LIMIT_VENTANA_SEG`), aparte del límite diario del plan
- Modo inline ELIMINADO (quemaba cuota del usuario por keystroke + costo API + riesgo reputacional de respuestas de un tiro compartidas en público)
- Auto-tester (2 semanas Pionero gratis) + sistema de referidos (+7 días Pionero)
- Favoritos, feedback, soporte, estadísticas (`/stats_admin`, `/feedback`)
- Registro de abogados verificados + comparador de artículos (Pionero+)
- Avisos automáticos por Telegram al usuario cuando el admin cambia su plan o le regala algo

### Mini App (TMA) y panel admin
- TMA con auth vía `initData` firmado (HMAC), CORS configurable
- Panel de administración web (`api_admin.py`) con su propia auth (`X-Admin-Key`, comparación en tiempo constante) — resumen, usuarios, consultas log, abogados, feedback, mensajes/anuncios

### Calidad
- **392 tests automatizados** (pytest) cubriendo pipeline, retrieval, edge cases, verificador y domain boost — todos pasando

---

## Pendiente 🔧

### Leyes bloqueadas por falta de fuente (ver `auditoria_vigencia.csv`)
- [ ] **Ley Orgánica de las Comunas** — reforma 2024 (G.O. 6.872) confirmada, pero sin texto completo público limpio
- [ ] **Ley de Celeridad y Optimización de Trámites** (reemplaza la de Simplificación de Trámites de 1999) — G.O. 7.018 (08-04-2026), texto aún no disponible
- [ ] **Convenio Cambiario N°1 2018** (BCV) — fuentes bloquean la descarga, bajo tráfico ciudadano

Estas tres necesitan que se consiga el PDF oficial; en cuanto aparezca uno, se indexa con el flujo normal.

### Por verificar / decidir
- [ ] **Generación de documentos**: `DOCS_HABILITADOS = True` en config, pero no se ha verificado de punta a punta que `documentos.py` + plantillas funcionen en producción con usuarios reales
- [ ] **Pasarela de pago automatizada**: hoy solo existe una lista de métodos válidos (`METODOS_PAGO_VALIDOS`: Pago Móvil, Zinli, Binance, PayPal, Wally, Zelle, efectivo) que el admin usa para registrar pagos manualmente — no hay cobro/activación automática
- [ ] **App móvil (Android/iOS)**: evaluado como viable reutilizando la TMA + API existentes (login vía Telegram Widget como puente); no iniciado. Ruta recomendada: PWA instalable primero, Play Store después si hay tracción, iOS solo si la demanda de diáspora lo justifica (costo $99/año + IAP obligatorio)
- [ ] Dashboard web para métricas — parcialmente cubierto por el panel admin nuevo; falta ver si complementa o reemplaza `/stats_admin`

### Deuda técnica pendiente
- [ ] Rate limiting más granular por plan (hoy el anti-flood es uniforme; el límite diferenciado real es el de consultas/día por plan)

---

## Resuelto (histórico)
- ~~Código Civil incompleto (solo hasta Art. 1013)~~ → 1.899 artículos indexados, hasta el Art. 1995
- ~~Ley de Tránsito Terrestre truncada~~ → 215 artículos (la ley completa)
- ~~Ley Orgánica de Precios Justos sin indexar~~ → 90 artículos
- ~~Ley de Protección de la Fauna Doméstica sin indexar~~ → 74 artículos
- ~~PDFs escaneados sin texto~~ → auditados y reemplazados por versiones con texto seleccionable donde había fuente disponible
- ~~Cache de embeddings~~ → implementado (`lru_cache`)
- ~~Unificar sistema de nombres de leyes~~ → `leyes_config.json` como fuente única
- ~~busqueda.py demasiado largo~~ → separado en `seguridad.py`, `prompts.py`, `scoring.py`
- ~~Sin tests automatizados~~ → 392 tests pytest

---

## Métricas clave a monitorear
- `/auditar` → barrido completo de preguntas + respuestas (no depende de que alguien reporte)
- `/historial <usuario>` → hilo completo de un usuario para depurar un caso puntual
- Alertas 🔴 (baja confianza) / 🟡 (media) → temas faltantes o keywords a mejorar en `articulos_clave.json`
- Preguntas sin tema detectado (`/stats_admin`) → gaps de cobertura, con datos reales de qué indexar después
- Feedback negativo (👎) → respuestas incorrectas que necesitan corrección
