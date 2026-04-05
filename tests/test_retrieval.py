"""
Test de verificación del motor RAG — busqueda.buscar_articulos_clave
Ejecutar: python tests/test_retrieval.py
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("Cargando motor RAG...")
from busqueda import buscar_articulos_clave

# (pregunta, espera_articulos: bool, descripcion)
CASOS = [
    # Constitucional / derechos
    ("¿Pueden revisar mi teléfono en una alcabala?",            True,  "CRBV privacidad"),
    ("¿Cuáles son mis derechos si me detienen?",                True,  "CRBV detención"),
    ("Me detuvieron sin orden judicial, ¿qué hago?",            True,  "CRBV/COPP detención"),
    # Laboral
    ("¿Cuántos días de vacaciones me corresponden?",            True,  "LOTTT vacaciones"),
    ("Me despidieron sin causa justificada, ¿qué hago?",        True,  "LOTTT despido"),
    ("¿Pueden despedirme por quedarme dormido en el trabajo?",  True,  "LOTTT causa justa"),
    ("¿Cuánto me tienen que pagar de prestaciones sociales?",   True,  "LOTTT prestaciones"),
    # Tránsito
    ("Me chocaron el carro y el conductor se fue, ¿qué hago?",  True,  "Tránsito choque"),
    ("¿Cuánto es la multa por no usar cinturón de seguridad?",  True,  "Tránsito multa"),
    ("¿Pueden quitarme el carnet en una alcabala?",             True,  "Tránsito documentos"),
    # Arrendamiento / vivienda
    ("El casero quiere desalojarme sin aviso, ¿es legal?",      True,  "Arrendamientos desalojo"),
    ("¿Cuánto me pueden aumentar el alquiler?",                 True,  "Arrendamientos canon"),
    # Penal
    ("Mi vecino me amenazó de muerte, ¿qué hago?",             True,  "CP amenazas"),
    ("Me robaron el celular en la calle, ¿qué hago?",           True,  "CP robo"),
    # Familia / civil
    ("¿Cómo funciona la herencia en Venezuela?",                True,  "CC herencia"),
    ("¿Cuánto tiempo tarda un divorcio en Venezuela?",          True,  "CC divorcio"),
    # Fuera de dominio (el retrieval puede devolver algo, pero el LLM debe rechazar)
    ("¿Cuál es la capital de Francia?",                         False, "fuera dominio — geografía"),
    ("Dame una receta de arepas",                               False, "fuera dominio — receta"),
]

print(f"\n{'─'*75}")
print(f"{'DESCRIPCIÓN':<28} {'ARTS':^5} {'LEYES'}")
print(f"{'─'*75}")

ok = fail = 0
for pregunta, espera_arts, desc in CASOS:
    arts, temas = buscar_articulos_clave(pregunta)
    n = len(arts)
    leyes_unicas = list(dict.fromkeys(a["ley"][:25] for a in arts))[:2]

    if espera_arts:
        if n > 0:
            status = f"✅  {n:2d} arts"
            ok += 1
        else:
            status = f"❌  0 arts  (temas={temas})"
            fail += 1
    else:
        # No esperamos artículos — el retrieval puede igual devolver algo
        status = f"ℹ️   {n:2d} arts (revisar con LLM)"
        ok += 1

    ley_str = " | ".join(leyes_unicas) if leyes_unicas else ""
    print(f"  {desc:<26} {status:<22} {ley_str}")

print(f"{'─'*75}")
total_legales = sum(1 for _, e, _ in CASOS if e)
print(f"Resultado: {ok}/{len(CASOS)} OK ({fail} FAIL en {total_legales} consultas legales)\n")

if fail:
    sys.exit(1)
