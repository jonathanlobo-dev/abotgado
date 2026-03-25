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
    └─► 5. LLM (Groq - llama-3.3-70b)
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

## Mapeo de nombres de leyes

**Flujo crítico**: El nombre en `NOMBRES_CORRECTOS` (1_procesar_leyes.py) define cómo se guarda en ChromaDB. Luego `ARTICULOS_CLAVE` (busqueda.py) busca por ese mismo nombre. Si no coinciden → 0 resultados.

```
PDF filename → NOMBRES_CORRECTOS → ChromaDB metadata "ley" → ARTICULOS_CLAVE["ley"]
```

## Alias de leyes (ALIAS_LEYES)
200+ alias normalizados para que el usuario pueda escribir "lottt", "cc", "constitución", etc. y se resuelva al nombre canónico en ChromaDB.
