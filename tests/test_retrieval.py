"""
Test de verificación del motor RAG — busqueda.buscar_articulos_clave
Ejecutar: pytest tests/test_retrieval.py -v
"""
import pytest
from busqueda import buscar_articulos_clave

CASOS_LEGALES = [
    ("¿Pueden revisar mi teléfono en una alcabala?",            "CRBV privacidad"),
    ("¿Cuáles son mis derechos si me detienen?",                "CRBV detención"),
    ("Me detuvieron sin orden judicial, ¿qué hago?",            "CRBV/COPP detención"),
    ("¿Cuántos días de vacaciones me corresponden?",            "LOTTT vacaciones"),
    ("Me despidieron sin causa justificada, ¿qué hago?",        "LOTTT despido"),
    ("¿Pueden despedirme por quedarme dormido en el trabajo?",  "LOTTT causa justa"),
    ("¿Cuánto me tienen que pagar de prestaciones sociales?",   "LOTTT prestaciones"),
    ("Me chocaron el carro y el conductor se fue, ¿qué hago?",  "Tránsito choque"),
    ("¿Cuánto es la multa por no usar cinturón de seguridad?",  "Tránsito multa"),
    ("¿Pueden quitarme el carnet en una alcabala?",             "Tránsito documentos"),
    ("El casero quiere desalojarme sin aviso, ¿es legal?",      "Arrendamientos desalojo"),
    ("¿Cuánto me pueden aumentar el alquiler?",                 "Arrendamientos canon"),
    ("Mi vecino me amenazó de muerte, ¿qué hago?",             "CP amenazas"),
    ("Me robaron el celular en la calle, ¿qué hago?",           "CP robo"),
    ("¿Cómo funciona la herencia en Venezuela?",                "CC herencia"),
    ("¿Cuánto tiempo tarda un divorcio en Venezuela?",          "CC divorcio"),
]


@pytest.mark.parametrize("pregunta,desc", CASOS_LEGALES, ids=[c[1] for c in CASOS_LEGALES])
def test_retrieval_legal(pregunta, desc):
    """Consulta legal debe devolver al menos 1 artículo."""
    arts, temas = buscar_articulos_clave(pregunta)
    assert len(arts) > 0, f"0 artículos para «{pregunta}» (temas={temas})"


CASOS_FUERA_DOMINIO = [
    ("¿Cuál es la capital de Francia?",  "fuera dominio — geografía"),
    ("Dame una receta de arepas",        "fuera dominio — receta"),
]


@pytest.mark.parametrize("pregunta,desc", CASOS_FUERA_DOMINIO, ids=[c[1] for c in CASOS_FUERA_DOMINIO])
def test_fuera_de_dominio(pregunta, desc):
    """Consultas fuera de dominio: el retrieval puede devolver algo, no es fallo."""
    arts, temas = buscar_articulos_clave(pregunta)
    # Solo verificamos que no crashea — el LLM se encarga del rechazo
    assert isinstance(arts, list)
