# Integración Telegram — aBOTgado

## Archivo principal: `3_bot_telegram.py`

## Comandos del usuario

| Comando | Descripción | Plan mínimo |
|---------|-------------|-------------|
| `/start` | Bienvenida, auto-registro, referidos | Todos |
| `/ayuda` | Menú de ayuda | Todos |
| `/leyes` | Lista todas las leyes disponibles | Todos |
| `/ley <ley> <num>` | Consulta directa de artículo con explicación | Todos |
| `/estado` | Ver plan actual y consultas restantes | Todos |
| `/ping` | Health check | Todos |
| `/nuevo` | Limpiar historial de conversación | Todos |
| `/stats` | Estadísticas personales | Todos |
| `/opinion` | Dejar feedback (positivo/negativo/comentario) | Todos |
| `/referir` | Obtener link de referido | Todos |
| `/soporte` | Enviar mensaje a soporte | Todos |
| `/comparar <ley1> <art1> vs <ley2> <art2>` | Comparar artículos | Pionero+ |
| `/guardar` | Guardar última respuesta | Pionero+ |
| `/mis_consultas` | Ver respuestas guardadas | Pionero+ |
| `/ver_guardado N` | Ver guardado específico | Pionero+ |
| `/borrar_guardados` | Eliminar todos los guardados | Pionero+ |

## Comandos admin

| Comando | Descripción |
|---------|-------------|
| `/debug on\|off` | Activar/desactivar alertas 🟢 de TODAS las consultas |
| `/premium_on <id>` | Activar Premium a usuario |
| `/premium_off <id>` | Desactivar Premium |
| `/tester <id>` | Dar 2 semanas de Pionero |
| `/regalar_consultas <id> [N]` | Regalar consultas extra (default 5) |
| `/regalar_memoria <id>` | Activar bono de memoria |
| `/plan_add <id> [días]` | Agregar días Pionero |
| `/plan_del <id> [días]` | Quitar días Pionero |
| `/anuncio <msg>` | Broadcast a todos los usuarios |
| `/mensaje <id> <msg>` | Mensaje directo a usuario |
| `/responder <id> <msg>` | Responder ticket de soporte |
| `/feedback [pág] [tipo]` | Ver feedback (paginado, filtrable) |
| `/feedback_borrar [tipo] [id]` | Borrar feedback |
| `/usuarios` | Lista de usuarios con desglose por plan |
| `/stats_admin` | Estadísticas globales |
| `/backup` | Descargar backup de DB |
| `/add_abogado` | Registrar abogado (formulario multi-paso) |
| `/abogados` | Listar abogados verificados |
| `/del_abogado <id>` | Desactivar abogado |
| `/activar_abogado <id>` | Reactivar abogado |

## Sistema de alertas admin

```
debug_mode = False (default)

Si confianza == "baja":  → 🔴 ALERTA siempre
Si confianza == "media": → 🟡 ALERTA siempre
Si confianza == "alta":  → 🟢 Solo si debug_mode == True
```

Formato de alerta:
```
{icono} CONSULTA {TIPO}
Confianza: {conf} | Dist: {dist:.3f}
Temas: {temas}
Usuario: {nombre} (@{username}, ID: {id})
Pregunta: {pregunta[:200]}
```

## Inline mode
- Handler: `InlineQueryHandler(handle_inline)`
- Busca leyes directamente desde cualquier chat
- Retorna `InlineQueryResultArticle`
- **Problema**: Cada tecla dispara una búsqueda → spam de alertas

## Seguridad

### Anti-inyección
- 20 patrones regex en `_PATRONES_INYECCION`
- Detecta: "ignora instrucciones", "modo desarrollador", "repite tu prompt", etc.
- Respuesta genérica: `RESPUESTA_INYECCION`

### Detección de consultas no legales
- `es_consulta_no_legal()`: Saludos, agradecimientos, despedidas
- `es_fuera_de_dominio()`: Recetas, clima, horóscopo, código, etc.

## Estado en memoria (no persistente)
```python
feedback_pendiente = set()     # Usuarios esperando dar feedback
soporte_pendiente  = set()     # Usuarios esperando enviar soporte
ultima_respuesta   = {}        # Cache de última respuesta por usuario
registro_abogado   = {}        # Formulario multi-paso de abogados
esperando_ley      = {}        # Usuario buscando artículo específico
debug_mode         = False     # Toggle global de debug
```
