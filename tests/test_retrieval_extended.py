"""
Test extendido de verificación RAG — batería amplia de temas.
Ejecutar: python tests/test_retrieval_extended.py
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("Cargando motor RAG...")
from busqueda import buscar_articulos_clave

CASOS = [
    # ── LABORAL ──────────────────────────────────────────────────────────
    ("Me despidieron sin preaviso, ¿qué me deben pagar?",                True,  "laboral: despido sin preaviso"),
    ("¿Cuántas horas máximo puedo trabajar por día?",                     True,  "laboral: jornada máxima"),
    ("Mi jefe no me pagó el bono vacacional, ¿qué hago?",                True,  "laboral: bono vacacional"),
    ("Estoy embarazada y me quieren despedir, ¿pueden?",                  True,  "laboral: inamovilidad maternidad"),
    ("¿Qué es el salario integral y cómo se calcula?",                    True,  "laboral: salario integral"),
    ("No me pagan horas extras desde hace meses",                         True,  "laboral: horas extra"),
    ("¿Cuánto es el período de prueba en Venezuela?",                     True,  "laboral: período de prueba"),
    ("¿Puedo trabajar para dos empresas al mismo tiempo?",                True,  "laboral: doble empleo"),
    ("¿Límite de trabajadores extranjeros que puedo contratar?",          True,  "laboral: trabajadores extranjeros"),

    # ── CREACIÓN DE EMPRESAS / COMERCIO ───────────────────────────────────
    ("¿Qué diferencia hay entre Firma Personal y Compañía Anónima?",      True,  "comercio: firma personal vs CA"),
    ("Quiero abrir una C.A., ¿cuántos socios necesito?",                  True,  "comercio: constitución CA"),
    ("¿Cuánto capital mínimo necesito para abrir una compañía en Venezuela?", True, "comercio: capital mínimo"),
    ("¿Qué es una sociedad de responsabilidad limitada en Venezuela?",     True,  "comercio: SRL"),
    ("Tengo un negocio informal, ¿me pueden multar por no tener RIF?",    True,  "tributario: RIF negocio"),

    # ── REGISTROS Y NOTARÍAS ─────────────────────────────────────────────
    ("¿Puedo vender una casa con un poder firmado en el extranjero?",     True,  "registros: poder en extranjero"),
    ("¿Qué es la apostilla y para qué sirve?",                            True,  "registros: apostilla"),
    ("¿Cuánto tiempo tiene de validez un poder notariado?",               True,  "registros: validez poder"),
    ("¿Qué documentos necesito para registrar una venta de casa?",        True,  "registros: venta inmueble"),
    ("¿Puedo hacer una donación de terreno sin ir al registro?",          True,  "registros: donación"),

    # ── COMPRA-VENTA ──────────────────────────────────────────────────────
    ("Compré un carro y el motor se dañó a los 3 días, ¿qué puedo hacer?", True, "civil: vicios ocultos vehículo"),
    ("Me vendieron un apartamento con plagas y el vendedor no avisó",     True,  "civil: vicios ocultos inmueble"),
    ("Hice un contrato de venta verbal, ¿tiene validez legal?",           True,  "civil: contrato verbal"),
    ("El comprador no me pagó la segunda cuota, ¿qué hago?",             True,  "civil: incumplimiento contrato"),
    ("¿Puedo retractarme de una compra antes de firmar el registro?",     True,  "civil: arras / retracto"),

    # ── ALQUILERES ────────────────────────────────────────────────────────
    ("El dueño del apartamento subió el canon sin avisar, ¿puede?",       True,  "arrendamiento: aumento ilegal"),
    ("Llevo 8 años de inquilino, ¿tengo derecho a preferencia de compra?", True, "arrendamiento: preferencia ofertiva"),
    ("El arrendador quiere entrar al apartamento sin mi permiso",         True,  "arrendamiento: acceso arrendador"),
    ("¿Cuánto tiempo tengo para desalojar si me notificaron?",            True,  "arrendamiento: plazo desalojo"),
    ("Mi arrendador no me devuelve el depósito de garantía",              True,  "arrendamiento: depósito garantía"),
    ("Quiero alquilar un local comercial, ¿rige la misma ley?",          True,  "arrendamiento: local comercial"),

    # ── VECINOS / COMUNIDAD ───────────────────────────────────────────────
    ("El vecino puso un taller mecánico en su garaje y hay ruido hasta las 11pm", True, "vecinos: ruido taller"),
    ("El vecino construyó una pared que tapa mi ventana sin permiso",     True,  "vecinos: construcción ilegal"),
    ("¿A quién me quejo si mi vecino bota basura en la calle?",          True,  "vecinos: basura / salubridad"),
    ("El vecino de arriba tiene una fuga de agua que daña mi techo",     True,  "vecinos: daños por filtración"),
    ("¿Puedo poner una reja en el pasillo si todos los vecinos están de acuerdo?", True, "vecinos: áreas comunes"),
    ("El condominio me cobra una cuota que no aprobé en asamblea",       True,  "vecinos: condominio cuotas"),

    # ── NEGOCIOS INFORMALES / PERMISOS ───────────────────────────────────
    ("¿Necesito permiso sanitario para vender comida en mi casa?",        True,  "sanitario: permiso venta comida"),
    ("¿Me pueden decomisar la mercancía si vendo en la calle sin permiso?", True, "sanitario: decomiso mercancía"),
    ("¿Qué pasa si me agarran vendiendo sin declarar el IVA?",           True,  "tributario: IVA informal"),
    ("Quiero poner una bodega, ¿qué permisos necesito de la alcaldía?",  True,  "municipal: permiso bodega"),

    # ── PROPIEDAD / HERENCIA ──────────────────────────────────────────────
    ("Fallecieron mis padres sin testamento, ¿cómo se divide la herencia?", True, "herencia: ab intestato"),
    ("Mi hermano vendió una propiedad heredada sin mi consentimiento",    True,  "herencia: venta sin consentimiento"),
    ("¿Puedo desheredar a un hijo?",                                      True,  "herencia: desheredamiento"),
    ("¿Qué es la legítima en Venezuela?",                                 True,  "herencia: legítima"),
    ("Tengo una casa en posesión hace 20 años pero sin título",          True,  "propiedad: prescripción adquisitiva"),

    # ── CONSUMIDOR / GARANTÍAS ────────────────────────────────────────────
    ("Me vendieron un celular nuevo y llegó dañado, ¿qué hago?",         True,  "consumidor: garantía producto"),
    ("Una tienda no me quiere hacer el cambio de un producto dañado",    True,  "consumidor: derecho a cambio"),
    ("Me cobraron de más en el supermercado por precio diferente al exhibido", True, "consumidor: sobreprecio"),
    ("La aerolínea perdió mi maleta, ¿qué derechos tengo?",             True,  "consumidor: equipaje perdido"),

    # ── PENAL ─────────────────────────────────────────────────────────────
    ("Me acusan de robo pero soy inocente, ¿qué hago?",                  True,  "penal: acusado de robo"),
    ("¿Cuánto tiempo puede durarme una medida cautelar privativa?",       True,  "penal: medida privativa"),
    ("¿Qué es el procedimiento abreviado en Venezuela?",                  True,  "penal: proc. abreviado"),
    ("Me cayeron sin orden de allanamiento, ¿qué hago?",                 True,  "penal: allanamiento ilegal"),

    # ── FAMILIA ───────────────────────────────────────────────────────────
    ("Quiero el divorcio pero mi pareja no quiere firmar",               True,  "familia: divorcio contencioso"),
    ("¿Con cuántos meses de separación puedo pedir el divorcio?",        True,  "familia: causal divorcio"),
    ("El papá de mis hijos no paga la manutención, ¿qué hago?",         True,  "familia: manutención"),
    ("¿Cómo solicito la custodia compartida de mis hijos?",              True,  "familia: custodia compartida"),
]

print(f"\n{'─'*78}")
print(f"  {'DESCRIPCIÓN':<38} {'ARTS':^5}  {'LEYES'}")
print(f"{'─'*78}")

ok = fail = 0
secciones = {}

for pregunta, espera, desc in CASOS:
    seccion = desc.split(":")[0].strip()
    arts, temas = buscar_articulos_clave(pregunta)
    n = len(arts)
    leyes = list(dict.fromkeys(a["ley"][:22] for a in arts))[:2]

    if espera:
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

    ley_str = " | ".join(leyes)
    print(f"  {desc:<38} {status:<22} {ley_str}")

    # Separador de sección
    if CASOS.index((pregunta, espera, desc)) < len(CASOS)-1:
        next_sec = CASOS[CASOS.index((pregunta, espera, desc))+1][2].split(":")[0].strip()
        if next_sec != seccion:
            print()

print(f"{'─'*78}")
print(f"Resultado: {ok}/{len(CASOS)} OK, {fail} FAIL\n")
if secciones:
    print("Secciones con fallos:")
    for s, c in sorted(secciones.items()):
        print(f"  {s}: {c} fallo(s)")

if fail:
    sys.exit(1)
