"""
Tests de casos borde, cruces de leyes y cobertura avanzada.
Ejecutar: python tests/test_edge_cases.py

Categorías:
  ✅ Esperamos artículos    → espera=True
  ⚠️  Ley faltante probable → espera=False  (marca MISSING_LAW en desc)
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("Cargando motor RAG...")
from busqueda import buscar_articulos_clave

CASOS = [

    # ══════════════════════════════════════════════════════════════════════
    # CRUCES LABORAL ↔ OTRAS LEYES
    # ══════════════════════════════════════════════════════════════════════
    ("Me accidenté en el trabajo, ¿qué cubre el seguro social?",            True,  "cruce: accidente laboral + seguro"),
    ("Mi empresa no me inscribió en el IVSS, ¿qué puedo hacer?",           True,  "cruce: LOTTT + seguro social"),
    ("Me despidieron durante una huelga sindical, ¿es ilegal?",             True,  "cruce: fuero sindical + despido"),
    ("Mi jefe me acosa sexualmente, ¿qué ley aplica?",                     True,  "cruce: acoso sexual laboral"),
    ("Me discriminan en el trabajo por ser de otra región, ¿qué hago?",    True,  "cruce: discriminación laboral CRBV"),
    ("El dueño de la empresa se fue a quiebra, ¿pierdo mis prestaciones?", True,  "cruce: quiebra empresa + prestaciones"),
    ("Trabajo en casa como empleada doméstica, ¿tengo los mismos derechos?", True, "edge: trabajadora doméstica"),
    ("Me cambiaron de sede sin avisarme de ciudad, ¿pueden hacerlo?",      True,  "edge: traslado de trabajador"),
    ("Mi contrato temporal lleva 3 renovaciones, ¿ya soy fijo?",           True,  "edge: contrato temporal → indefinido"),

    # ══════════════════════════════════════════════════════════════════════
    # CRUCES PENAL ↔ CIVIL / OTRAS LEYES
    # ══════════════════════════════════════════════════════════════════════
    ("Me extorsionan por WhatsApp y me piden dinero o publican fotos",     True,  "cruce: extorsión digital"),
    ("Hackearon mi cuenta bancaria y me robaron el dinero",                True,  "cruce: delito informático bancario"),
    ("Me enviaron correos con virus y perdí datos de mi negocio",          True,  "cruce: delito informático empresa"),
    ("Publicaron fotos mías íntimas sin mi permiso en redes sociales",     True,  "cruce: violación privacidad digital"),
    ("Un vecino me amenaza de muerte por teléfono desde hace semanas",     True,  "cruce: amenazas + COPP"),
    ("Me detuvieron sin orden judicial ni delito flagrante",               True,  "cruce: detención arbitraria COPP"),
    ("Fui testigo de un robo, ¿me obligan a declarar?",                   True,  "edge: testigo proceso penal"),
    ("Un menor de 14 años cometió un robo, ¿lo llevan preso?",            True,  "cruce: menor infractor LOPNNA"),

    # ══════════════════════════════════════════════════════════════════════
    # CRUCES FAMILIA ↔ PENAL / OTRAS LEYES
    # ══════════════════════════════════════════════════════════════════════
    ("Mi ex me tiene prohibido ver a mis hijos, ¿qué hago?",              True,  "cruce: custodia + obstrucción"),
    ("Mi pareja me golpeó delante de los niños, ¿qué hago?",              True,  "cruce: violencia doméstica + LOPNNA"),
    ("Mi hijo de 15 años quiere trabajar, ¿puede?",                       True,  "cruce: menor + trabajo LOPNNA"),
    ("Quiero reconocer a mi hijo pero la madre no quiere, ¿puedo?",       True,  "cruce: filiación CC + LOPNNA"),
    ("Me divorció y quiero la mitad de los bienes en común",              True,  "cruce: divorcio + partición bienes"),
    ("Mi pareja murió sin testamento y tenemos hijos, ¿qué hereda quién?", True, "cruce: herencia + familia"),

    # ══════════════════════════════════════════════════════════════════════
    # CRUCES PROPIEDAD / INMUEBLES ↔ OTRAS LEYES
    # ══════════════════════════════════════════════════════════════════════
    ("Compré una casa con hipoteca y no puedo pagar, ¿me la quitan?",     True,  "cruce: hipoteca + ejecución"),
    ("Mi vecino construyó en mi terreno, ¿tengo acción legal?",           True,  "cruce: invasión propiedad"),
    ("Heredé un apartamento pero tiene deuda de condominio antigua",      True,  "cruce: herencia + deuda condominio"),
    ("Tengo un terreno sin escritura, ¿cómo lo registro a mi nombre?",    True,  "cruce: propiedad + registros"),
    ("Alquilo con opción a compra, ¿qué dice la ley?",                    True,  "cruce: arrendamiento + opción compra"),
    ("Me metieron bienhechurías a mi terreno sin permiso",                True,  "cruce: bienhechurías invasión"),

    # ══════════════════════════════════════════════════════════════════════
    # EDGE CASES CONSUMIDOR / COMERCIO
    # ══════════════════════════════════════════════════════════════════════
    ("Compré ropa en línea y nunca llegó, ¿qué hago?",                    True,  "edge: compra online sin entrega"),
    ("Me vendieron un teléfono que explota y me quemó la mano",           True,  "edge: producto defectuoso con daño"),
    ("El banco me cobró comisiones que no autoricé, ¿qué hago?",          True,  "edge: banco cobro no autorizado"),
    ("Una empresa de seguro no quiere pagar mi siniestro de carro",       False, "MISSING_LAW: ley de seguros"),
    ("¿Cuánto tiempo tiene la empresa para responder una garantía?",       True,  "edge: garantía plazo respuesta"),

    # ══════════════════════════════════════════════════════════════════════
    # CASOS CON LEYES FALTANTES (esperamos 0 → False)
    # ══════════════════════════════════════════════════════════════════════
    ("Necesito permiso de construcción en mi terreno, ¿cómo lo saco?",    False, "MISSING_LAW: construcción/urbanismo"),
    ("La empresa quiere registrar una marca, ¿cómo se protege?",          False, "MISSING_LAW: propiedad intelectual"),
    ("Me accidenté en mi carro y no tengo seguro obligatorio, ¿qué pasa?", False,"MISSING_LAW: seguro obligatorio"),
    ("¿Cuáles son los derechos del pasajero de una aerolínea en Venezuela?", False,"MISSING_LAW: aviación civil"),
    ("Tengo un contrato de franquicia, ¿qué ley regula las franquicias?", False, "MISSING_LAW: franquicia"),
    ("¿Cómo funciona el seguro de desempleo en Venezuela?",               True,  "edge: seguro desempleo IVSS"),
    ("Me dieron de baja por enfermedad, ¿cuánto paga el IVSS?",          True,  "edge: incapacidad IVSS"),
    ("El banco me niega un crédito por discriminación, ¿qué hago?",       False, "MISSING_LAW: ley bancaria"),
    ("¿Cuáles son mis derechos ante CONATEL si me cortan internet?",       False, "MISSING_LAW: telecomunicaciones"),
    ("Quiero patentar un invento, ¿cómo lo registro en Venezuela?",        False, "MISSING_LAW: propiedad industrial"),

    # ══════════════════════════════════════════════════════════════════════
    # EDGE CASES CONSTITUCIONALES / DERECHOS
    # ══════════════════════════════════════════════════════════════════════
    ("Me prohibieron hacer una manifestación pacífica en la plaza",        True,  "edge: derecho a manifestación"),
    ("¿Un venezolano puede tener doble nacionalidad?",                     True,  "edge: doble nacionalidad CRBV"),
    ("Soy venezolano y me deportaron de otro país, ¿qué derechos tengo?", True,  "edge: derecho retorno CRBV"),
    ("Me censuraron una publicación en un periódico local",               True,  "edge: libertad de expresión"),

    # ══════════════════════════════════════════════════════════════════════
    # EDGE CASES AMBIGUOS (pueden tocar varias leyes)
    # ══════════════════════════════════════════════════════════════════════
    ("Mi ex vendió el carro que compramos juntos sin decirme",            True,  "edge: bienes comunidad conyugal"),
    ("¿Puedo grabar a mi jefe si me está maltratando?",                   True,  "edge: grabación conversación laboral"),
    ("Me cobraron IVA en una farmacia por un medicamento, ¿es legal?",    True,  "edge: IVA medicamentos"),
    ("Una empresa me contrató como freelance pero me exige horario fijo",  True,  "edge: falsa independencia laboral"),
    ("¿Cuánto tiempo dura la acción penal en Venezuela?",                 True,  "edge: prescripción penal"),
    ("Me pusieron una demanda civil pero vivo en otro estado, ¿qué hago?", True, "edge: competencia territorial CPC"),
]

# ──────────────────────────────────────────────────────────────────────────────
WIDTH_DESC = 42

print(f"\n{'─'*82}")
print(f"  {'DESCRIPCIÓN':<{WIDTH_DESC}} {'RESULTADO':<22}  LEYES")
print(f"{'─'*82}")

ok = fail = missing_ok = 0
secciones: dict[str, int] = {}
missing_laws: list[str] = []

for pregunta, espera, desc in CASOS:
    seccion = desc.split(":")[0].strip()
    arts, temas = buscar_articulos_clave(pregunta)
    n = len(arts)
    leyes = list(dict.fromkeys(a["ley"][:22] for a in arts))[:2]
    ley_str = " | ".join(leyes)

    if desc.startswith("MISSING_LAW"):
        # Para estas esperamos 0. Si devuelve algo, es bonus ✨
        if n == 0:
            status = f"⚠️  0  (ley faltante)"
            missing_ok += 1
            missing_laws.append(desc.replace("MISSING_LAW: ", ""))
        else:
            status = f"✨ {n:2d}  (cubierto!)"
            ok += 1
        ok += 1  # siempre suma — no es fallo
    elif espera:
        if n > 0:
            status = f"✅ {n:2d}"
            ok += 1
        else:
            status = f"❌  0  temas={temas}"
            fail += 1
            secciones[seccion] = secciones.get(seccion, 0) + 1
    else:
        status = f"ℹ️  {n:2d}"
        ok += 1

    print(f"  {desc:<{WIDTH_DESC}} {status:<28} {ley_str}")

    # Separador de sección
    idx = CASOS.index((pregunta, espera, desc))
    if idx < len(CASOS)-1:
        next_sec = CASOS[idx+1][2].split(":")[0].strip()
        if next_sec != seccion:
            print()

print(f"{'─'*82}")

legales = [c for c in CASOS if not c[2].startswith("MISSING_LAW")]
n_legales = len(legales)
total = len(CASOS)
n_missing = len([c for c in CASOS if c[2].startswith("MISSING_LAW")])

print(f"\nResultado: {ok-missing_ok}/{n_legales} casos legales OK, {fail} FAIL, {n_missing} con ley faltante\n")

if missing_laws:
    print("─── Leyes faltantes detectadas ──────────────────────────────────────────────")
    for l in missing_laws:
        print(f"  ✗  {l}")
    print()

if secciones:
    print("─── Secciones con fallos ─────────────────────────────────────────────────────")
    for s, c in sorted(secciones.items()):
        print(f"  {s}: {c} fallo(s)")

if fail:
    sys.exit(1)
