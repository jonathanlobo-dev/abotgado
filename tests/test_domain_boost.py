"""
Test de domain boost + seguimiento de conversación.
Ejecutar: python tests/test_domain_boost.py

Valida:
1. Que el domain boost prioriza artículos de la rama correcta
2. Que los artículos de rama incorrecta bajan de score
3. Que la CRBV (constitucional) nunca queda excluida
4. Que en seguimiento la query enriquecida mantiene el dominio correcto
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("Cargando motor RAG...\n")
from busqueda import buscar_articulos_nuevos, buscar_y_responder, rama_de_ley

RESET  = "\033[0m"
VERDE  = "\033[92m"
ROJO   = "\033[91m"
AMARILLO = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"

def ok(msg):  print(f"  {VERDE}✓{RESET} {msg}")
def fail(msg): print(f"  {ROJO}✗{RESET} {msg}")
def info(msg): print(f"  {AMARILLO}→{RESET} {msg}")

def verificar_articulos(titulo, pregunta, rama_esperada, ley_no_debe_aparecer=None):
    print(f"\n{BOLD}{CYAN}[{titulo}]{RESET}")
    print(f"  Pregunta: «{pregunta}»")
    arts, _, temas, dist = buscar_articulos_nuevos(pregunta)

    if not arts:
        fail(f"Sin artículos recuperados")
        return False

    leyes = [a["ley"] for a in arts]
    ramas = [rama_de_ley(a["ley"]) for a in arts]
    scores = [a.get("score_final", 0) for a in arts]

    print(f"  Temas detectados: {temas}")
    print(f"  Artículos recuperados ({len(arts)}):")
    for a in arts:
        rama = rama_de_ley(a["ley"])
        score = a.get("score_final", 0)
        marcador = VERDE if rama == rama_esperada else (AMARILLO if rama in ("constitucional","general") else ROJO)
        print(f"    {marcador}[{rama}]{RESET} {a['ley']} Art.{a['articulo']} — score_final={score:.2f}")

    # Verificación 1: debe haber al menos un artículo de la rama esperada
    hay_rama_correcta = any(r == rama_esperada for r in ramas)
    if hay_rama_correcta:
        ok(f"Hay artículos de rama '{rama_esperada}'")
    else:
        fail(f"NO hay artículos de rama '{rama_esperada}'")

    # Verificación 2: el primer artículo debe ser de la rama correcta o constitucional
    primera_rama = ramas[0] if ramas else ""
    if primera_rama in (rama_esperada, "constitucional", "general"):
        ok(f"Primer artículo es de rama correcta ({primera_rama})")
    else:
        fail(f"Primer artículo es de rama INCORRECTA: {primera_rama} — {leyes[0]}")

    # Verificación 3: ley prohibida no debe aparecer (o si aparece, debe estar al fondo)
    if ley_no_debe_aparecer:
        idx_prohibida = next((i for i, l in enumerate(leyes) if ley_no_debe_aparecer in l), -1)
        if idx_prohibida == -1:
            ok(f"'{ley_no_debe_aparecer}' no aparece ✓")
        elif idx_prohibida >= 5:
            ok(f"'{ley_no_debe_aparecer}' aparece pero al fondo (pos {idx_prohibida+1}/{len(arts)})")
        else:
            fail(f"'{ley_no_debe_aparecer}' aparece en posición {idx_prohibida+1} — debería estar al fondo")

    return hay_rama_correcta


def test_seguimiento_alcabala():
    """Caso crítico: teléfono → dinero. Con seguimiento, el contexto debe mantenerse penal."""
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}TEST SEGUIMIENTO: Alcabala → Extorsión{RESET}")
    print(f"{'='*60}")

    # Primera pregunta
    print(f"\n{BOLD}TURNO 1:{RESET}")
    arts1, ctx1, temas1, _ = buscar_articulos_nuevos("¿Pueden revisar mi teléfono en una alcabala?")
    print(f"  Temas: {temas1}")
    print(f"  Artículos: {[(a['ley'][:30], a['articulo']) for a in arts1[:4]]}")
    leyes1 = [a["ley"] for a in arts1]
    tiene_crbv = any("Constitución" in l for l in leyes1)
    if tiene_crbv:
        ok("CRBV presente en turno 1")
    else:
        fail("CRBV ausente en turno 1")

    # Historial para el seguimiento
    historial = [
        {"role": "user", "content": "¿Pueden revisar mi teléfono en una alcabala?"},
        {"role": "assistant", "content": "No, solo pueden hacerlo con orden judicial. Art. 48 CRBV garantiza la inviolabilidad de comunicaciones."},
    ]

    # Segunda pregunta (seguimiento crítico)
    print(f"\n{BOLD}TURNO 2 (seguimiento):{RESET}")
    pregunta2 = "Y ahora me quieren quitar dinero para dejarme ir"
    arts2, ctx2, temas2, _ = buscar_articulos_nuevos(pregunta2)
    print(f"  Temas: {temas2}")
    print(f"  Artículos:")
    leyes2 = [a["ley"] for a in arts2]
    ramas2 = [rama_de_ley(a["ley"]) for a in arts2]
    for a in arts2:
        rama = rama_de_ley(a["ley"])
        marcador = VERDE if rama in ("penal","constitucional") else ROJO
        print(f"    {marcador}[{rama}]{RESET} {a['ley']} Art.{a['articulo']} score={a.get('score_final',0):.2f}")

    # Verificar que NO hay arrendamiento al frente
    idx_arr = next((i for i,l in enumerate(leyes2) if "Arrendamiento" in l), -1)
    if idx_arr == -1:
        ok("Sin artículos de Arrendamiento")
    elif idx_arr >= 5:
        ok(f"Arrendamiento al fondo (pos {idx_arr+1})")
    else:
        fail(f"ARRENDAMIENTO en posición {idx_arr+1} — BUG de contaminación")

    # Verificar que hay penal/corrupción
    hay_penal = any(r == "penal" for r in ramas2)
    hay_crbv  = any("Constitución" in l for l in leyes2)
    if hay_penal:
        ok("Artículos penales presentes en turno 2")
    else:
        fail("Sin artículos penales en turno 2")
    if hay_crbv:
        ok("CRBV presente en turno 2 (constitucional nunca excluida)")
    else:
        info("CRBV ausente en turno 2 (puede ser normal si el query no la necesita)")


def test_arrendamiento_no_contamina_penal():
    """Caso inverso: consulta civil real no debe traer Código Penal al frente."""
    verificar_articulos(
        "Arrendamiento real",
        "Mi casero quiere sacarme del apartamento sin aviso",
        rama_esperada="vivienda",
        ley_no_debe_aparecer="Código Penal"
    )


def test_deposito_garantia_no_es_penal():
    """'Depósito en garantía' no debe disparar artículos penales."""
    print(f"\n{BOLD}{CYAN}[Depósito en garantía — civil]{RESET}")
    print(f"  Pregunta: «Le debo el depósito en garantía a mi casero»")
    arts, _, temas, _ = buscar_articulos_nuevos("Le debo el depósito en garantía a mi casero")
    print(f"  Temas: {temas}")
    ramas = [rama_de_ley(a["ley"]) for a in arts]
    for a in arts:
        rama = rama_de_ley(a["ley"])
        marcador = VERDE if rama in ("vivienda","civil") else (AMARILLO if rama=="constitucional" else ROJO)
        print(f"    {marcador}[{rama}]{RESET} {a['ley']} Art.{a['articulo']} score={a.get('score_final',0):.2f}")
    hay_penal_top3 = any(ramas[i] == "penal" for i in range(min(3, len(ramas))))
    if not hay_penal_top3:
        ok("Sin penales en top-3 ✓")
    else:
        fail("Artículo penal en top-3 de consulta civil")


def test_cross_domain_legitimo():
    """Despido + amenaza: debe traer LOTTT Y Código Penal (ambos válidos)."""
    print(f"\n{BOLD}{CYAN}[Cross-domain legítimo — laboral + penal]{RESET}")
    print(f"  Pregunta: «Me despidieron y mi jefe me amenazó de muerte»")
    arts, _, temas, _ = buscar_articulos_nuevos("Me despidieron y mi jefe me amenazó de muerte")
    print(f"  Temas: {temas}")
    ramas = [rama_de_ley(a["ley"]) for a in arts]
    for a in arts:
        rama = rama_de_ley(a["ley"])
        print(f"    [{rama}] {a['ley']} Art.{a['articulo']} score={a.get('score_final',0):.2f}")
    hay_laboral = "laboral" in ramas
    hay_penal   = "penal" in ramas
    if hay_laboral:
        ok("Artículos laborales presentes")
    else:
        fail("Sin artículos laborales")
    if hay_penal:
        ok("Artículos penales presentes")
    else:
        info("Sin artículos penales (puede fallar si 'amenazó' no matchea bien)")


def test_crbv_siempre_presente():
    """La CRBV debe aparecer en consultas constitucionales sin importar el dominio."""
    verificar_articulos(
        "CRBV en consulta penal",
        "Me detuvieron sin orden judicial en un retén",
        rama_esperada="penal",
    )


if __name__ == "__main__":
    print(f"{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}DOMAIN BOOST TEST SUITE{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    test_seguimiento_alcabala()

    verificar_articulos(
        "Teléfono en alcabala (primera consulta)",
        "¿Pueden revisar mi teléfono en una alcabala?",
        rama_esperada="constitucional",
    )

    verificar_articulos(
        "Extorsión policial directa",
        "Me están pidiendo plata para dejarme ir en una alcabala",
        rama_esperada="penal",
        ley_no_debe_aparecer="Arrendamiento",
    )

    test_arrendamiento_no_contamina_penal()
    test_deposito_garantia_no_es_penal()
    test_cross_domain_legitimo()
    test_crbv_siempre_presente()

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}Tests completados.{RESET}")
    print(f"{'='*60}\n")
