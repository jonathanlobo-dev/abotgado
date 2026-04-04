"""
aBOTgado - Motor de embeddings (HuggingFace API)
==================================================
Modelo: paraphrase-multilingual-MiniLM-L12-v2 (384 dims, multilingüe, 50+ idiomas)

Caché en memoria (LRU, 2000 entradas ≈ 6 MB):
  - Misma query en la misma request → 0 llamadas extra a HuggingFace
  - Query repetida por otro usuario → respuesta instantánea desde RAM
  - El proceso de Railway vive horas/días → la caché se acumula con el tiempo
"""

import time
import logging
import requests
from functools import lru_cache

import config

logger = logging.getLogger(__name__)

_headers = {"Authorization": f"Bearer {config.HF_API_KEY}"} if config.HF_API_KEY else {}


# ─── CAPA DE CACHÉ ────────────────────────────────────────────────────────────

@lru_cache(maxsize=2000)
def _embedding_cacheado(texto: str) -> tuple:
    """
    Llama a HuggingFace y devuelve el embedding como tuple (inmutable → cacheable).
    lru_cache guarda hasta 2000 entradas; las más antiguas se descartan automáticamente.
    NUNCA llamar directamente — usar generar_embedding().
    """
    return tuple(_fetch_embedding(texto))


def generar_embedding(texto: str, reintentos: int = 3) -> list[float]:
    """
    Genera el embedding de un texto.
    Devuelve desde caché si el texto ya fue procesado antes (O(1)).
    Llama a HuggingFace solo si es la primera vez que ve ese texto.
    """
    key = texto[:512]   # mismo truncado que antes
    resultado = _embedding_cacheado(key)

    # Log ocasional de estadísticas (cada 100 hits)
    info = _embedding_cacheado.cache_info()
    if (info.hits + info.misses) % 100 == 0 and info.misses > 0:
        tasa = info.hits / (info.hits + info.misses) * 100
        logger.info(f"[Embed caché] hits={info.hits} misses={info.misses} tasa={tasa:.1f}%")

    return list(resultado)


def cache_info() -> dict:
    """Devuelve estadísticas de la caché para el dashboard admin."""
    info = _embedding_cacheado.cache_info()
    total = info.hits + info.misses
    return {
        "hits":     info.hits,
        "misses":   info.misses,
        "total":    total,
        "tasa_pct": round(info.hits / total * 100, 1) if total else 0,
        "size":     info.currsize,
        "maxsize":  info.maxsize,
    }


def limpiar_cache():
    """Vacía la caché de embeddings (útil tras reindexar)."""
    _embedding_cacheado.cache_clear()
    logger.info("[Embed caché] Caché limpiada.")


# ─── LLAMADA REAL A HUGGINGFACE ───────────────────────────────────────────────

def _fetch_embedding(texto: str, reintentos: int = 3) -> list[float]:
    """
    Hace la petición HTTP a HuggingFace Inference API.
    Solo se llama cuando el texto NO está en caché.
    """
    payload = {"inputs": texto}

    for intento in range(reintentos):
        try:
            resp = requests.post(
                config.HF_EMBED_URL,
                headers=_headers,
                json=payload,
                timeout=60
            )

            if resp.status_code == 503:
                # Modelo cargando (cold start)
                data = resp.json()
                wait = data.get("estimated_time", 20)
                logger.info(f"  Modelo cargando, esperando {wait:.0f}s...")
                time.sleep(min(wait, 30))
                continue

            if resp.status_code == 429:
                logger.warning("  Rate limit HuggingFace, esperando 5s...")
                time.sleep(5)
                continue

            resp.raise_for_status()
            result = resp.json()

            # La API retorna [[embedding]] o [embedding] según el modelo
            if isinstance(result, list):
                if isinstance(result[0], list):
                    return result[0]
                return result

            raise ValueError(f"Formato inesperado: {type(result)}")

        except requests.exceptions.Timeout:
            logger.warning(f"  Timeout en intento {intento + 1}/{reintentos}")
            time.sleep(5)
        except Exception as e:
            logger.error(f"  Error embedding (intento {intento + 1}): {e}")
            if intento < reintentos - 1:
                time.sleep(3)

    raise RuntimeError(f"No se pudo generar embedding después de {reintentos} intentos")


# ─── BATCH (solo para indexación) ─────────────────────────────────────────────

def generar_embeddings_batch(textos: list[str], batch_size: int = 20) -> list[list[float]]:
    """
    Genera embeddings en lotes para indexación masiva.
    No usa caché (los textos de artículos no se repiten en producción).
    """
    todos = []

    for i in range(0, len(textos), batch_size):
        batch = [t[:512] for t in textos[i:i + batch_size]]
        payload = {"inputs": batch}

        for intento in range(3):
            try:
                resp = requests.post(
                    config.HF_EMBED_URL,
                    headers=_headers,
                    json=payload,
                    timeout=120
                )

                if resp.status_code == 503:
                    data = resp.json()
                    wait = data.get("estimated_time", 20)
                    logger.info(f"  Modelo cargando, esperando {wait:.0f}s...")
                    time.sleep(min(wait, 30))
                    continue

                if resp.status_code == 429:
                    time.sleep(5)
                    continue

                resp.raise_for_status()
                result = resp.json()
                todos.extend(result)
                break

            except Exception as e:
                logger.error(f"  Error batch embedding: {e}")
                if intento == 2:
                    # Fallback: uno por uno
                    for texto in batch:
                        todos.append(generar_embedding(texto))
                else:
                    time.sleep(3)

    return todos


# ─── DIAGNÓSTICO ──────────────────────────────────────────────────────────────

def test_conexion() -> bool:
    """Verifica que la API de HuggingFace funcione."""
    try:
        emb = generar_embedding("test de conexión")
        logger.info(f"HuggingFace API OK — dimensiones: {len(emb)}")
        return True
    except Exception as e:
        logger.error(f"Error conectando a HuggingFace: {e}")
        return False
