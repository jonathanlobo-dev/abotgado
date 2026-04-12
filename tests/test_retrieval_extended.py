"""
Test extendido de verificación RAG — batería amplia de temas.
Ejecutar: pytest tests/test_retrieval_extended.py -v
"""
import pytest
from busqueda import buscar_articulos_clave

CASOS = [
    # ── LABORAL ──────────────────────────────────────────────────────────
    ("Me despidieron sin preaviso, ¿qué me deben pagar?",                "laboral: despido sin preaviso"),
    ("¿Cuántas horas máximo puedo trabajar por día?",                     "laboral: jornada máxima"),
    ("Mi jefe no me pagó el bono vacacional, ¿qué hago?",                "laboral: bono vacacional"),
    ("Estoy embarazada y me quieren despedir, ¿pueden?",                  "laboral: inamovilidad maternidad"),
    ("¿Qué es el salario integral y cómo se calcula?",                    "laboral: salario integral"),
    ("No me pagan horas extras desde hace meses",                         "laboral: horas extra"),
    ("¿Cuánto es el período de prueba en Venezuela?",                     "laboral: período de prueba"),
    ("¿Puedo trabajar para dos empresas al mismo tiempo?",                "laboral: doble empleo"),
    ("¿Límite de trabajadores extranjeros que puedo contratar?",          "laboral: trabajadores extranjeros"),
    # ── COMERCIO ─────────────────────────────────────────────────────────
    ("¿Qué diferencia hay entre Firma Personal y Compañía Anónima?",      "comercio: firma personal vs CA"),
    ("Quiero abrir una C.A., ¿cuántos socios necesito?",                  "comercio: constitución CA"),
    ("¿Cuánto capital mínimo necesito para abrir una compañía en Venezuela?", "comercio: capital mínimo"),
    ("¿Qué es una sociedad de responsabilidad limitada en Venezuela?",     "comercio: SRL"),
    ("Tengo un negocio informal, ¿me pueden multar por no tener RIF?",    "tributario: RIF negocio"),
    # ── REGISTROS ────────────────────────────────────────────────────────
    ("¿Puedo vender una casa con un poder firmado en el extranjero?",     "registros: poder en extranjero"),
    ("¿Qué es la apostilla y para qué sirve?",                            "registros: apostilla"),
    ("¿Cuánto tiempo tiene de validez un poder notariado?",               "registros: validez poder"),
    ("¿Qué documentos necesito para registrar una venta de casa?",        "registros: venta inmueble"),
    ("¿Puedo hacer una donación de terreno sin ir al registro?",          "registros: donación"),
    # ── COMPRA-VENTA ─────────────────────────────────────────────────────
    ("Compré un carro y el motor se dañó a los 3 días, ¿qué puedo hacer?", "civil: vicios ocultos vehículo"),
    ("Me vendieron un apartamento con plagas y el vendedor no avisó",     "civil: vicios ocultos inmueble"),
    ("Hice un contrato de venta verbal, ¿tiene validez legal?",           "civil: contrato verbal"),
    ("El comprador no me pagó la segunda cuota, ¿qué hago?",             "civil: incumplimiento contrato"),
    ("¿Puedo retractarme de una compra antes de firmar el registro?",     "civil: arras / retracto"),
    # ── ALQUILERES ───────────────────────────────────────────────────────
    ("El dueño del apartamento subió el canon sin avisar, ¿puede?",       "arrendamiento: aumento ilegal"),
    ("Llevo 8 años de inquilino, ¿tengo derecho a preferencia de compra?", "arrendamiento: preferencia ofertiva"),
    ("El arrendador quiere entrar al apartamento sin mi permiso",         "arrendamiento: acceso arrendador"),
    ("¿Cuánto tiempo tengo para desalojar si me notificaron?",            "arrendamiento: plazo desalojo"),
    ("Mi arrendador no me devuelve el depósito de garantía",              "arrendamiento: depósito garantía"),
    ("Quiero alquilar un local comercial, ¿rige la misma ley?",          "arrendamiento: local comercial"),
    # ── VECINOS / COMUNIDAD ──────────────────────────────────────────────
    ("El vecino puso un taller mecánico en su garaje y hay ruido hasta las 11pm", "vecinos: ruido taller"),
    ("El vecino construyó una pared que tapa mi ventana sin permiso",     "vecinos: construcción ilegal"),
    ("¿A quién me quejo si mi vecino bota basura en la calle?",          "vecinos: basura / salubridad"),
    ("El vecino de arriba tiene una fuga de agua que daña mi techo",     "vecinos: daños por filtración"),
    ("¿Puedo poner una reja en el pasillo si todos los vecinos están de acuerdo?", "vecinos: áreas comunes"),
    ("El condominio me cobra una cuota que no aprobé en asamblea",       "vecinos: condominio cuotas"),
    # ── NEGOCIOS INFORMALES ──────────────────────────────────────────────
    ("¿Necesito permiso sanitario para vender comida en mi casa?",        "sanitario: permiso venta comida"),
    ("¿Me pueden decomisar la mercancía si vendo en la calle sin permiso?", "sanitario: decomiso mercancía"),
    ("¿Qué pasa si me agarran vendiendo sin declarar el IVA?",           "tributario: IVA informal"),
    ("Quiero poner una bodega, ¿qué permisos necesito de la alcaldía?",  "municipal: permiso bodega"),
    # ── PROPIEDAD / HERENCIA ─────────────────────────────────────────────
    ("Fallecieron mis padres sin testamento, ¿cómo se divide la herencia?", "herencia: ab intestato"),
    ("Mi hermano vendió una propiedad heredada sin mi consentimiento",    "herencia: venta sin consentimiento"),
    ("¿Puedo desheredar a un hijo?",                                      "herencia: desheredamiento"),
    ("¿Qué es la legítima en Venezuela?",                                 "herencia: legítima"),
    ("Tengo una casa en posesión hace 20 años pero sin título",          "propiedad: prescripción adquisitiva"),
    # ── CONSUMIDOR ───────────────────────────────────────────────────────
    ("Me vendieron un celular nuevo y llegó dañado, ¿qué hago?",         "consumidor: garantía producto"),
    ("Una tienda no me quiere hacer el cambio de un producto dañado",    "consumidor: derecho a cambio"),
    ("Me cobraron de más en el supermercado por precio diferente al exhibido", "consumidor: sobreprecio"),
    ("La aerolínea perdió mi maleta, ¿qué derechos tengo?",             "consumidor: equipaje perdido"),
    # ── PENAL ────────────────────────────────────────────────────────────
    ("Me acusan de robo pero soy inocente, ¿qué hago?",                  "penal: acusado de robo"),
    ("¿Cuánto tiempo puede durarme una medida cautelar privativa?",       "penal: medida privativa"),
    ("¿Qué es el procedimiento abreviado en Venezuela?",                  "penal: proc. abreviado"),
    ("Me cayeron sin orden de allanamiento, ¿qué hago?",                 "penal: allanamiento ilegal"),
    # ── FAMILIA ──────────────────────────────────────────────────────────
    ("Quiero el divorcio pero mi pareja no quiere firmar",               "familia: divorcio contencioso"),
    ("¿Con cuántos meses de separación puedo pedir el divorcio?",        "familia: causal divorcio"),
    ("El papá de mis hijos no paga la manutención, ¿qué hago?",         "familia: manutención"),
    ("¿Cómo solicito la custodia compartida de mis hijos?",              "familia: custodia compartida"),
]


@pytest.mark.parametrize("pregunta,desc", CASOS, ids=[c[1] for c in CASOS])
def test_retrieval_extendido(pregunta, desc):
    """Cada consulta legal debe devolver al menos 1 artículo."""
    arts, temas = buscar_articulos_clave(pregunta)
    assert len(arts) > 0, f"0 artículos para «{pregunta}» (temas={temas})"
