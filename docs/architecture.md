# Arquitectura — aBOTgado

## Pipeline RAG (Retrieval-Augmented Generation)

```
Usuario (Telegram)
    │
    ▼
3_bot_telegram.py ──► Detección: inyección / saludo / fuera-de-dominio / seguimiento
    │
    ▼
busqueda.py::buscar_y_responder()
    │
    ├─► 1. ARTICULOS_CLAVE (keyword match)
    │     → Busca keywords normalizados en la pregunta
    │     → Sistema de exclusiones (campo "excluir") evita falsos positivos
    │     → Si artículos ≤ 10: lookup directo en ChromaDB
    │     → Si artículos > 10: embedding search dentro de esa ley
    │
    ├─► 2. BM25 (ranking léxico)
    │     → Corpus: todos los artículos de ChromaDB tokenizados
    │     → Top-K resultados por relevancia BM25
    │
    ├─► 3. Embeddings (búsqueda semántica)
    │     → HuggingFace Inference API (all-MiniLM-L6-v2)
    │     → ChromaDB query con distancia coseno
    │     → Filtro por ley si tema detectado
    │
    ├─► 4. Fusión y deduplicación
    │     → Combina resultados de los 3 métodos
    │     → Elimina duplicados por ID de artículo
    │     → Ordena por relevancia combinada
    │
    └─► 5. LLM (Groq - openai/gpt-oss-120b, ver config.py)
          → SYSTEM_PROMPT con reglas estrictas de formato y precisión
          → Contexto: artículos encontrados + historial (si tiene memoria)
          → Respuesta en HTML con estructura 📌📖💡⚠️
```

## Sistema de Confianza

```
                    ┌─ temas + dist < 0.55 → "alta"
Confianza =         ├─ temas + dist ≥ 0.55 → "media"
                    ├─ sin temas + dist < 0.55 → "media"
                    └─ sin temas + dist ≥ 0.55 → "baja"
```

- **alta**: No alerta. Solo visible con `/debug on`
- **media**: Alerta 🟡 al admin automáticamente
- **baja**: Alerta 🔴 al admin automáticamente

## Componentes de datos

### ChromaDB (`abotgado_db/`)
- **Colección**: `leyes_venezolanas`
- **Documentos**: Texto de cada artículo
- **Metadatos**: `ley` (nombre canónico), `articulo` (número), `pdf` (nombre archivo)
- **IDs**: `{nombre_pdf}_art_{numero}`
- **Embeddings**: Generados por HuggingFace API al insertar

### SQLite (`abotgado_usuarios.db`)
- 10 tablas: usuarios, consultas_diarias, historial, ultimo_contexto, ultima_respuesta, feedback, favoritos, soporte, metricas, abogados
- Ver `db.py` para esquema completo

### Índice de PDFs (`indice_leyes.json`)
- Registro por PDF: hash MD5, nombre de ley, cantidad de artículos
- Usado por `1_procesar_leyes.py` para indexación incremental

## Flujo de indexación

```
leyes/*.pdf
    │
    ▼
1_procesar_leyes.py
    ├─► extraer_texto() → PyMuPDF (fitz)
    ├─► detectar_nombre_ley() → NOMBRES_CORRECTOS dict (85+ mappings)
    ├─► extraer_articulos() → regex: Art[íi]culo\s+(\d+)
    └─► ChromaDB.add() → con embeddings HuggingFace
```

### Auto-reindex (start.py)
1. Calcula fingerprint MD5 de todos los PDFs (nombres + tamaños)
2. Compara con `.pdf_hash` guardado
3. Si cambió (o `REINDEX=1`): borra ChromaDB y ejecuta `--full`
4. Luego inicia el bot

## Módulos extraídos de busqueda.py

| Módulo | Responsabilidad |
|--------|----------------|
| `seguridad.py` | Detección de prompt injection (20 patrones), sanitización, filtro de teléfonos/montos inventados |
| `prompts.py` | SYSTEM_PROMPT, prompts de reformulación/explicación, guías institucionales (44), catálogo de leyes |
| `scoring.py` | Score embedding/BM25, domain boost/penalty, mapeo ley→rama, constantes de scoring |
| `busqueda.py` | Orquestación RAG, BM25, ChromaDB, fusión, LLM (importa los 3 módulos anteriores) |

## Fuente única de verdad: leyes_config.json

Todos los nombres canónicos, aliases, ramas y PDFs se definen en `leyes_config.json` (62 leyes). Los módulos derivan sus dicts desde este archivo:

```
leyes_config.json
    ├─► 1_procesar_leyes.py: NOMBRES_CORRECTOS, CLASIFICACION_LEYES
    ├─► busqueda.py:          ALIAS_LEYES (110 aliases → nombre canónico)
    └─► scoring.py:           LEY_A_RAMA (nombre → rama para domain boost)
```

**Flujo crítico**: El nombre en `leyes_config.json` define cómo se guarda en ChromaDB y cómo se busca. Una sola fuente elimina inconsistencias.

```
leyes_config.json → NOMBRES_CORRECTOS → ChromaDB metadata "ley" → ARTICULOS_CLAVE["ley"]
```
