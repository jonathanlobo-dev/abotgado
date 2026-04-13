# aBOTgado

Bot jurídico venezolano en Telegram. Responde consultas legales usando RAG híbrido (keywords + BM25 + embeddings semánticos) sobre 62+ leyes venezolanas indexadas.

## Stack

| Componente | Tecnología |
|-----------|-----------|
| Runtime | Python 3.12 |
| Bot | python-telegram-bot 21.10 |
| LLM | Groq (configurable via `LLM_MODEL`) |
| Embeddings | HuggingFace (`paraphrase-multilingual-MiniLM-L12-v2`) |
| Vector DB | ChromaDB (persistente) |
| Base de datos | SQLite (usuarios, historial, feedback) |
| Deploy | Railway (Procfile: `python start.py`) |
| Almacenamiento | Volume persistente en `/data` (Railway) |

## Arquitectura

```
Usuario (Telegram / Inline)
    │
    ▼
3_bot_telegram.py ── seguridad.py (inyección, sanitización)
    │
    ▼
busqueda.py::buscar_y_responder()
    │
    ├── 1. ARTICULOS_CLAVE  (keyword match → lookup o embedding)
    ├── 2. BM25              (ranking léxico)
    ├── 3. Embeddings        (semántica, ChromaDB)
    ├── 4. Fusión + scoring  (scoring.py: domain boost, dedup)
    └── 5. LLM              (Groq → respuesta HTML con 📌📖💡⚠️)
```

> Docs detallados: `docs/architecture.md`, `docs/telegram-integration.md`

## Estructura de archivos

```
abotgado/
├── start.py                  # Entry point Railway (auto-reindex si PDFs cambiaron)
├── config.py                 # Paths, API keys, planes, constantes
├── 3_bot_telegram.py         # Handlers Telegram, ConversationHandlers, inline
├── busqueda.py               # Motor RAG: BM25 + embeddings + fusión + LLM
├── seguridad.py              # Detección de inyección, sanitización, filtros
├── prompts.py                # SYSTEM_PROMPT, guías institucionales, catálogo
├── scoring.py                # Domain boost, score embedding/BM25, LEY_A_RAMA
├── db.py                     # SQLite: usuarios, historial, feedback, abogados
├── embeddings.py             # Llamadas a HuggingFace Inference API
├── documentos.py             # Generación de documentos legales
├── api.py                    # API web (endpoints REST)
├── 1_procesar_leyes.py       # Indexador: PDF → artículos → ChromaDB
├── leyes_config.json         # Fuente única: nombres, aliases, ramas (62 leyes)
├── articulos_clave.json      # Temas + keywords + artículos por tema
├── leyes/                    # PDFs de leyes venezolanas (65+)
├── plantillas/               # Templates DOCX para documentos
├── tests/                    # pytest: 234 tests (retrieval, pipeline, edge cases)
│   ├── conftest.py
│   ├── test_rag_pipeline.py  # Seguridad, scoring, config, búsqueda (60 tests)
│   ├── test_domain_boost.py  # Domain boost y seguimiento (5 tests)
│   ├── test_retrieval.py     # Retrieval básico (18 tests)
│   ├── test_retrieval_extended.py  # Retrieval ampliado (55 tests)
│   └── test_edge_cases.py    # Cruces de leyes, MISSING_LAW (96 tests)
├── docs/
│   ├── architecture.md       # Pipeline RAG detallado
│   ├── progress.md           # Estado y TODOs
│   ├── telegram-integration.md
│   └── monetization.md
└── landing/                  # Landing page web
```

## Variables de entorno

Crear `.env` en la raíz:

```env
# Obligatorias
GROQ_API_KEY=gsk_...
TELEGRAM_TOKEN=7xxx:AAH...
HF_API_KEY=hf_...
ADMIN_IDS=123456789,987654321

# Opcionales
LLM_MODEL=openai/gpt-oss-120b     # Modelo Groq (default)
DATA_DIR=/data                      # Railway volume (default: directorio del proyecto)
BOT_USERNAME=abotgadoBOT
DEV_MODE=0                          # 1 = skip HMAC validation
```

## Comandos de desarrollo

```bash
# Iniciar bot (auto-reindexar si PDFs cambiaron)
python start.py

# Forzar reindex completo
REINDEX=1 python start.py

# Indexar leyes manualmente
python 1_procesar_leyes.py --full      # Reindexar todo
python 1_procesar_leyes.py --status    # Ver estado del índice

# Tests
pip install pytest                      # Solo primera vez
pytest tests/ -v                        # Suite completa (234 tests)
pytest tests/test_rag_pipeline.py -v    # Solo pipeline (60 tests)
pytest tests/test_domain_boost.py -v    # Solo domain boost (5 tests)
```

## Flujo principal de ejecución

```
1. start.py
   ├── Verifica/crea DATA_DIR
   ├── Calcula fingerprint MD5 de leyes/*.pdf
   ├── Si fingerprint cambió → ejecuta 1_procesar_leyes.py --full
   └── Importa y ejecuta 3_bot_telegram.py::main()

2. 3_bot_telegram.py::main()
   ├── Inicializa DB (SQLite)
   ├── Registra ConversationHandlers (feedback, soporte, abogado)
   ├── Registra CommandHandlers (30+ comandos)
   ├── Registra MessageHandler → responder_consulta()
   └── app.run_polling()

3. responder_consulta() [por cada mensaje de texto]
   ├── Verifica estados pendientes (esperando_ley, documentos)
   ├── Detecta inyección de prompt (seguridad.py)
   ├── Detecta saludo / fuera de dominio / seguimiento
   ├── Verifica límite de consultas del plan
   ├── Llama busqueda.buscar_y_responder()
   │   ├── Reformula query con LLM
   │   ├── buscar_articulos_nuevos() → RAG híbrido
   │   ├── Genera respuesta con Groq
   │   └── Filtra teléfonos/montos inventados
   └── Envía respuesta HTML con botones 👍👎
```

## Fuente única de verdad: leyes_config.json

Todas las leyes, aliases, nombres canónicos y ramas legales se definen en `leyes_config.json`. Los módulos que la consumen:

| Módulo | Qué lee |
|--------|---------|
| `1_procesar_leyes.py` | `NOMBRES_CORRECTOS` (PDF → nombre), `CLASIFICACION_LEYES` (nombre → rama) |
| `busqueda.py` | `ALIAS_LEYES` (alias → nombre canónico) |
| `scoring.py` | `LEY_A_RAMA` (nombre → rama para domain boost) |

Para agregar una ley nueva: editar solo `leyes_config.json` y reindexar.

## Problemas conocidos

| Problema | Impacto | Workaround |
|----------|---------|-----------|
| Código Civil incompleto | Solo Arts. 1-1013 indexados (de ~1982). Faltan contratos, arrendamiento CC, vicios ocultos | Embedding search compensa parcialmente. Reindexar con PDF completo |
| Ley de Tránsito truncada | Solo Arts. 1-136 + algunos sueltos. Faltan 137-242 (sanciones, multas) | Conseguir PDF completo y reindexar |
| 12 PDFs escaneados | Sin texto extraíble (imágenes). 0 artículos indexados | Necesitan OCR o versión con texto |
| API key Groq expira | Error 401 en `reformular_y_clasificar`. Bot responde "Hubo un error" | Rotar key en Railway env vars |
| Inline mode spamea alertas | Cada keystroke del usuario dispara búsqueda y alerta admin | Pendiente implementar debounce |
| `DOCS_HABILITADOS = False` | Generación de documentos deshabilitada en producción | Habilitar en config.py cuando esté listo |
