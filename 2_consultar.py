"""
aBOTgado - Paso 2: Consultar la base vectorial (RAG)
=====================================================
Stack gratuito para fase de pruebas:
  - Embeddings: Ollama + mxbai-embed-large (local, $0)
  - LLM:        Groq + openai/gpt-oss-120b (gratis en tier gratuito; ver config.py)
  - Vector DB:  ChromaDB local ($0)

Requisitos previos:
  1. Ollama corriendo con mxbai-embed-large
  2. API key de Groq en .env
  3. pip install chromadb ollama groq python-dotenv

Uso:
    python 2_consultar.py
"""

import chromadb
import ollama
from groq import Groq
import config

# ─── CLIENTES ────────────────────────────────────────────────────────────────

groq_client = Groq(api_key=config.GROQ_API_KEY)

# ─── PROMPT ANTI-ALUCINACIÓN ──────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres aBOTgado, un asistente jurídico especializado en las leyes de la República Bolivariana de Venezuela.

REGLAS ESTRICTAS que DEBES seguir siempre:

1. SOLO responde usando la información de los artículos que te proporciono. No inventes nada.

2. SIEMPRE cita la fuente así: [Nombre de la Ley, Art. N] — al final de cada afirmación importante.

3. Si los artículos que te doy NO contienen información suficiente para responder, di exactamente:
   "No encontré artículos aplicables a tu consulta en las leyes disponibles. Te recomiendo consultar con un abogado."

4. Usa lenguaje SIMPLE y claro, como si le explicaras a alguien sin conocimientos legales.
   - Evita tecnicismos innecesarios
   - Si usas un término legal, explícalo con palabras sencillas
   - Usa ejemplos prácticos cuando ayude

5. Estructura tu respuesta así:
   → Respuesta directa (1-2 oraciones)
   → Explicación con detalle
   → Artículos citados
   → Recomendación final si aplica

6. Termina SIEMPRE con esta línea:
   "⚠️ Esta información es orientativa. Para tu caso específico, consulta con un abogado."

7. Nunca inventes artículos, números o leyes que no estén en los fragmentos proporcionados.
8. Responde siempre en español venezolano, de forma cálida y accesible."""


# ─── BÚSQUEDA EN LA BASE VECTORIAL ────────────────────────────────────────────

def buscar_articulos(pregunta: str, coleccion, n: int = 20) -> list[dict]:
    """Busca los artículos más relevantes para la pregunta usando Ollama."""

    response = ollama.embeddings(model=config.EMBEDDING_MODEL, prompt=pregunta)
    emb      = response["embedding"]

    resultados = coleccion.query(
        query_embeddings=[emb],
        n_results=n,
        include=["documents", "metadatas", "distances"]
    )

    articulos = []
    for i in range(len(resultados["documents"][0])):
        articulos.append({
            "texto":     resultados["documents"][0][i],
            "ley":       resultados["metadatas"][0][i]["ley"],
            "articulo":  resultados["metadatas"][0][i]["articulo"],
            "distancia": resultados["distances"][0][i],
        })

    return articulos


# ─── GENERAR RESPUESTA CON GROQ ───────────────────────────────────────────────

def responder(pregunta: str, coleccion) -> str:
    """Pipeline completo RAG: buscar → filtrar → generar respuesta citada."""

    # 1. Buscar artículos relevantes
    articulos = buscar_articulos(pregunta, coleccion)

    # 2. Filtrar por relevancia (distancia coseno < 0.95)
    relevantes = [a for a in articulos if a["distancia"] < 0.95]

    if not relevantes:
        return ("No encontré artículos aplicables a tu consulta en las leyes disponibles.\n\n"
                "⚠️ Te recomiendo consultar directamente con un abogado.")

    # 3. Construir contexto para el LLM
    contexto = "ARTÍCULOS ENCONTRADOS:\n\n"
    for art in relevantes:
        contexto += f"[{art['ley']}, Art. {art['articulo']}]\n"
        contexto += f"{art['texto']}\n\n---\n\n"

    # 4. Llamar a Groq
    response = groq_client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"PREGUNTA DEL USUARIO: {pregunta}\n\n{contexto}"}
        ],
        max_tokens=800,
        temperature=0.1,
    )

    return response.choices[0].message.content


# ─── MAIN INTERACTIVO ─────────────────────────────────────────────────────────

def main():
    if not config.GROQ_API_KEY:
        print("❌ GROQ_API_KEY no configurada. Revisa tu archivo .env")
        return

    chroma = chromadb.PersistentClient(path=config.DB_PATH)

    try:
        coleccion = chroma.get_collection("leyes_venezolanas")
        total     = coleccion.count()
        print(f"⚖️  aBOTgado listo — {total} artículos en base de datos")
        print(f"   LLM: {config.LLM_MODEL} vía Groq (gratis)")
        print(f"   Embeddings: {config.EMBEDDING_MODEL} vía Ollama (local)")
        print("\n   Escribe tu pregunta jurídica (o 'salir' para terminar)\n")
    except Exception:
        print("❌ Base de datos no encontrada.")
        print("   Ejecuta primero: python 1_procesar_leyes.py")
        return

    while True:
        pregunta = input("👤 Tu pregunta: ").strip()

        if pregunta.lower() in ["salir", "exit", "q"]:
            print("¡Hasta luego!")
            break

        if not pregunta:
            continue

        print("\n⚖️  Consultando leyes venezolanas...\n")
        respuesta = responder(pregunta, coleccion)
        print(f"🤖 aBOTgado:\n{respuesta}\n")
        print("─" * 60 + "\n")


if __name__ == "__main__":
    main()
