"""
Tests del verificador de relevancia post-retrieval.
Ejecutar: pytest tests/test_verificador.py -v

Cubre:
  - Whitelist por fuente (curado/directo no se evalúan)
  - Filtrado correcto de fuzzy irrelevantes
  - Comportamiento conservador ante fallos (timeout, parsing, "ninguno")
  - Casos edge (lista vacía, 1 artículo, todo curado)
"""
import pytest
from unittest.mock import patch, MagicMock

import config
from busqueda import verificar_relevancia_articulos


# ─── HELPERS ───────────────────────────────────────────────────────────────

def _art(ley, num, texto="Texto del artículo", fuente=None, score=0.5):
    """Construye un dict de artículo para testing."""
    a = {
        "ley": ley,
        "articulo": num,
        "texto": texto,
        "score_final": score,
        "relevance_score": score,
    }
    if fuente:
        a["fuente"] = fuente
    return a


def _mock_groq(respuesta_str):
    """Crea un mock de groq_client.chat.completions.create."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = respuesta_str
    return MagicMock(return_value=mock_response)


# ─── EDGE CASES ────────────────────────────────────────────────────────────

def test_lista_vacia():
    """Lista vacía → retorna vacía sin llamar al LLM."""
    aprobados, descartados = verificar_relevancia_articulos("query", [])
    assert aprobados == []
    assert descartados == []


def test_un_solo_articulo():
    """Con 1 solo artículo, no se verifica (no aporta filtrar)."""
    arts = [_art("CRBV", 44, fuente="curado")]
    with patch("busqueda.groq_client.chat.completions.create") as mock:
        aprobados, descartados = verificar_relevancia_articulos("query", arts)
    assert aprobados == arts
    assert descartados == []
    mock.assert_not_called()


def test_verificador_deshabilitado(monkeypatch):
    """Si VERIFICADOR_HABILITADO=False, retorna sin filtrar."""
    monkeypatch.setattr(config, "VERIFICADOR_HABILITADO", False)
    arts = [
        _art("LOTTT", 79, fuente="curado"),
        _art("CC", 1873, fuente="fuzzy"),
    ]
    with patch("busqueda.groq_client.chat.completions.create") as mock:
        aprobados, descartados = verificar_relevancia_articulos("query", arts)
    assert aprobados == arts
    assert descartados == []
    mock.assert_not_called()


# ─── WHITELIST POR FUENTE ──────────────────────────────────────────────────

def test_todos_curados_skip_llm():
    """Si todos son 'curado', no se llama al LLM."""
    arts = [
        _art("CRBV", 44, fuente="curado"),
        _art("CRBV", 47, fuente="curado"),
        _art("COPP", 202, fuente="curado"),
    ]
    with patch("busqueda.groq_client.chat.completions.create") as mock:
        aprobados, descartados = verificar_relevancia_articulos("query", arts)
    assert aprobados == arts
    assert descartados == []
    mock.assert_not_called()


def test_directo_es_whitelist():
    """Articulos con fuente='directo' no se cuestionan."""
    arts = [
        _art("LOTTT", 79, fuente="directo"),
        _art("CC", 1873, fuente="fuzzy"),
    ]
    with patch("busqueda.groq_client.chat.completions.create",
               new=_mock_groq("ninguno")):
        aprobados, descartados = verificar_relevancia_articulos("query", arts)
    # CC fuzzy descartado, LOTTT directo se mantiene
    assert len(aprobados) == 1
    assert aprobados[0]["fuente"] == "directo"
    assert len(descartados) == 1


# ─── FILTRADO NORMAL ───────────────────────────────────────────────────────

def test_filtra_fuzzy_irrelevantes():
    """LLM dice '1, 3' → mantener fuzzy 1 y 3, descartar 2."""
    arts = [
        _art("CRBV", 44, fuente="curado"),
        _art("LOPJ", 49, texto="precios justos", score=0.7),  # fuzzy idx 1
        _art("CC", 1873, texto="contratos civiles", score=0.4),  # fuzzy idx 2
        _art("LOPJ", 30, texto="análisis socioeconómico", score=0.6),  # fuzzy idx 3
    ]
    with patch("busqueda.groq_client.chat.completions.create",
               new=_mock_groq("1, 3")):
        aprobados, descartados = verificar_relevancia_articulos(
            "me cobran de más", arts
        )
    # Curado siempre + fuzzy aprobados (LOPJ 49 y LOPJ 30)
    aprobados_arts = [(a["ley"], a["articulo"]) for a in aprobados]
    assert ("CRBV", 44) in aprobados_arts
    assert ("LOPJ", 49) in aprobados_arts
    assert ("LOPJ", 30) in aprobados_arts
    assert ("CC", 1873) not in aprobados_arts
    assert len(descartados) == 1
    assert descartados[0]["ley"] == "CC"


def test_aprueba_todos_los_fuzzy():
    """Si LLM dice '1, 2, 3' aprueba todos los fuzzy."""
    arts = [
        _art("LOPJ", 49, score=0.7),
        _art("LOPJ", 53, score=0.6),
        _art("LOPJ", 62, score=0.5),
    ]
    with patch("busqueda.groq_client.chat.completions.create",
               new=_mock_groq("1, 2, 3")):
        aprobados, descartados = verificar_relevancia_articulos("query", arts)
    assert len(aprobados) == 3
    assert descartados == []


# ─── COMPORTAMIENTO ANTE 'NINGUNO' ─────────────────────────────────────────

def test_ninguno_con_curados_mantiene_curados():
    """Si LLM responde 'ninguno' pero hay curados, mantenemos curados."""
    arts = [
        _art("LOVLV", 1, fuente="curado"),
        _art("LOVLV", 2, fuente="curado"),
        _art("CC", 999, score=0.3),  # fuzzy
    ]
    with patch("busqueda.groq_client.chat.completions.create",
               new=_mock_groq("ninguno")):
        aprobados, descartados = verificar_relevancia_articulos("query", arts)
    assert len(aprobados) == 2
    assert all(a["fuente"] == "curado" for a in aprobados)
    assert len(descartados) == 1


def test_ninguno_sin_curados_no_filtra():
    """Si 'ninguno' y NO hay curados → fallback conservador, no filtra."""
    arts = [
        _art("CC", 100, score=0.3),
        _art("CC", 200, score=0.4),
    ]
    with patch("busqueda.groq_client.chat.completions.create",
               new=_mock_groq("ninguno")):
        aprobados, descartados = verificar_relevancia_articulos("query", arts)
    # Conservador: no romper la query, retornar originales
    assert len(aprobados) == 2
    assert descartados == []


# ─── ROBUSTEZ ANTE FALLOS ──────────────────────────────────────────────────

def test_api_error_no_rompe():
    """Si la API de Groq falla, retorna lista original sin filtrar."""
    arts = [_art("CC", 1, score=0.4), _art("CC", 2, score=0.4)]
    with patch("busqueda.groq_client.chat.completions.create",
               side_effect=Exception("API timeout")):
        aprobados, descartados = verificar_relevancia_articulos("query", arts)
    assert aprobados == arts
    assert descartados == []


def test_respuesta_no_parseable_no_rompe():
    """Si LLM responde basura no parseable, no filtra."""
    arts = [_art("CC", 1, score=0.4), _art("CC", 2, score=0.4)]
    with patch("busqueda.groq_client.chat.completions.create",
               new=_mock_groq("hola que tal cómo va")):
        aprobados, descartados = verificar_relevancia_articulos("query", arts)
    assert aprobados == arts
    assert descartados == []


def test_indices_fuera_de_rango_se_ignoran():
    """Si LLM cita índices fuera de rango (ej: '5, 99'), solo cuenta los válidos."""
    arts = [
        _art("CC", 1, score=0.4),
        _art("CC", 2, score=0.4),
        _art("CC", 3, score=0.4),
    ]
    with patch("busqueda.groq_client.chat.completions.create",
               new=_mock_groq("2, 99, 100")):
        aprobados, descartados = verificar_relevancia_articulos("query", arts)
    # Solo idx 2 es válido
    assert len(aprobados) == 1
    assert aprobados[0]["articulo"] == 2
    assert len(descartados) == 2


def test_respuesta_con_explicacion_sigue_funcionando():
    """LLM se desvía y agrega texto, pero los números deben extraerse igual."""
    arts = [
        _art("CC", 1, score=0.4),
        _art("CC", 2, score=0.4),
    ]
    with patch("busqueda.groq_client.chat.completions.create",
               new=_mock_groq("Los relevantes son: 1 y 2.")):
        aprobados, descartados = verificar_relevancia_articulos("query", arts)
    assert len(aprobados) == 2


# ─── ORDEN DE RESULTADOS ───────────────────────────────────────────────────

def test_orden_por_score_post_filtrado():
    """El resultado final viene ordenado por score_final descendente."""
    arts = [
        _art("A", 1, score=0.3),
        _art("B", 2, score=0.9, fuente="curado"),
        _art("C", 3, score=0.6),
    ]
    with patch("busqueda.groq_client.chat.completions.create",
               new=_mock_groq("1, 2")):  # aprueba ambos fuzzy
        aprobados, _ = verificar_relevancia_articulos("query", arts)
    # B (curado, 0.9) → C (0.6) → A (0.3)
    assert [a["articulo"] for a in aprobados] == [2, 3, 1]
