# Estado del Proyecto — aBOTgado

## Resumen
Bot jurídico venezolano en Telegram con RAG híbrido (keywords + BM25 + embeddings). Desplegado en Railway.

---

## Completado ✅

- [x] Pipeline RAG híbrido funcionando (keywords + BM25 + embeddings + Groq LLM)
- [x] 50+ temas en ARTICULOS_CLAVE con keywords específicos
- [x] Sistema de exclusiones (`"excluir"`) para evitar falsos positivos (ej: testamento vs herencia)
- [x] Sistema de confianza (alta/media/baja) con alertas admin 🟢🟡🔴
- [x] Comando `/debug on|off` para admin
- [x] Corrección "Ley de Transporte Terrestre" → "Ley de Tránsito Terrestre" en busqueda.py (14 ocurrencias)
- [x] Artículos CC >999 redirigidos a embedding search (no existen en DB parcial)
- [x] Detección de prompt injection (20 patrones)
- [x] Sistema de planes: Gratis / Pionero / Premium
- [x] Auto-tester para primeros 50 usuarios (2 semanas Pionero gratis)
- [x] Sistema de referidos (+7 días Pionero por referido)
- [x] Favoritos, feedback, soporte, estadísticas
- [x] Registro de abogados verificados
- [x] Comparador de artículos (Pionero+)
- [x] Inline mode para búsqueda rápida
- [x] Auto-reindex por fingerprint de PDFs en start.py
- [x] Indexación incremental por hash MD5 en 1_procesar_leyes.py

---

## Pendiente 🔧

### Crítico
- [ ] **Reindexar ChromaDB con PDFs nuevos/actualizados**:
  - `CÓDIGO_CIVIL.pdf` — versión completa (218 páginas), reemplaza parcial anterior
  - `Ley-Orgánica-de-Precios-Justos.pdf` — nueva, no existe en DB
  - `Ley para la Protección de la Fauna Doméstica...pdf` — existe en carpeta pero 0 artículos en DB
- [ ] **Verificar Ley de Tránsito completa**: PDF actual solo tiene Art. 1-136 + algunos sueltos (243, 312, 340, 366). Faltan Art. 137-242 (sanciones, multas, estacionamiento)
- [ ] **Corregir `1_procesar_leyes.py` línea 54**: Cambiar `"Ley de Transporte Terrestre"` → `"Ley de Tránsito Terrestre"` ANTES de reindexar

### Mejoras
- [x] Inline mode eliminado (quemaba cuota/costo por keystroke + riesgo reputacional)
- [ ] 12 PDFs escaneados necesitan versiones con texto (OCR o reemplazo)
- [ ] Agregar más temas a ARTICULOS_CLAVE según pruebas con usuarios reales
- [ ] Implementar generación de documentos (DOCS_HABILITADOS = False actualmente)
- [ ] Integrar pasarela de pago para plan Premium
- [ ] Tests automatizados para validar respuestas del bot
- [ ] Dashboard web para estadísticas admin

### Deuda técnica (resuelta 2026-04-12)
- [x] ~~Unificar sistema de nombres de leyes~~ → `leyes_config.json` como fuente única
- [x] ~~Mover ARTICULOS_CLAVE a archivo JSON separado~~ → `articulos_clave.json`
- [x] ~~busqueda.py demasiado largo~~ → separado en `seguridad.py`, `prompts.py`, `scoring.py`
- [x] ~~State machines manuales en 3_bot_telegram.py~~ → ConversationHandler
- [x] ~~3 temas con 998 artículos (dump inútil)~~ → sub-clasificados a 17-21 arts curados
- [x] ~~Sin tests automatizados~~ → 234 tests pytest (pipeline, retrieval, edge cases)

### Deuda técnica (pendiente)
- [ ] Cache de embeddings para queries frecuentes
- [ ] Rate limiting más granular por plan

---

## Métricas clave a monitorear
- Alertas 🔴 (baja confianza) → indica temas faltantes en ARTICULOS_CLAVE
- Alertas 🟡 (media confianza) → posibles mejoras en keywords
- Feedback negativo → respuestas incorrectas que necesitan corrección
- Artículos citados por el bot → verificar que existan en DB y sean correctos
