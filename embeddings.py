"""
aBOTgado - Motor de embeddings (HuggingFace API)
==================================================
Reemplaza Ollama por la API gratuita de HuggingFace.
Modelo: paraphrase-multilingual-mpnet-base-v2 (768 dims, multilingue)
"""

import time
import logging
import requests
import config

logger = logging.getLogger(__name__)

_headers = {"Authorization": f"Bearer {config.HF_API_KEY}"} if config.HF_API_KEY else {}


def generar_embedding(texto: str, reintentos: int = 3) -> list[float]:
    """
    Genera embedding de un texto usando HuggingFace Inference API.
    Reintenta si el modelo está cargando (cold start ~20s).
    """
    payload = {"inputs": texto[:512]}  # Limitar a 512 chars como hacíamos con Ollama

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
                # Rate limit
                logger.warning(f"  Rate limit, esperando 5s...")
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


def generar_embeddings_batch(textos: list[str], batch_size: int = 20) -> list[list[float]]:
    """
    Genera embeddings en lotes para indexación masiva.
    Más eficiente que uno por uno.
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


def test_conexion() -> bool:
    """Verifica que la API de HuggingFace funcione."""
    try:
        emb = generar_embedding("test de conexión")
        logger.info(f"HuggingFace API OK — dimensiones: {len(emb)}")
        return True
    except Exception as e:
        logger.error(f"Error conectando a HuggingFace: {e}")
        return False
