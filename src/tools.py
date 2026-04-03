"""OpenAI Function Calling tools — backed by v3 CRM RPCs."""
import json
from src.db import v3_rpc, v3_available

# ═══════════════════════════════════════
# TOOL DEFINITIONS (OpenAI function schema)
# ═══════════════════════════════════════

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_courses",
            "description": "Buscar cursos disponibles en IITA con horarios, precios y cupos. Usar siempre que pregunten por cursos, horarios, ediciones o disponibilidad.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Texto de búsqueda: nombre del curso, área (robótica, python, IA, videojuegos, marketing, 3d, arduino) o palabra clave"
                    },
                    "age": {
                        "type": "integer",
                        "description": "Edad del alumno para filtrar ediciones por rango de edad"
                    },
                    "modality": {
                        "type": "string",
                        "enum": ["Presencial", "Virtual"],
                        "description": "Filtrar por modalidad"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_payment_link",
            "description": "Generar un link de pago de MercadoPago para un alumno. SOLO usar después de confirmar: nombre del alumno, curso elegido y horario/sede.",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "integer",
                        "description": "ID de la persona en el CRM"
                    },
                    "course_id": {
                        "type": "integer",
                        "description": "ID del curso"
                    },
                    "amount": {
                        "type": "number",
                        "description": "Monto a cobrar en ARS"
                    },
                    "description": {
                        "type": "string",
                        "description": "Descripción del pago (ej: 'Inscripción Robótica Educativa')"
                    }
                },
                "required": ["person_id", "course_id", "amount", "description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_asset",
            "description": "Enviar un archivo o video al contacto (programa del curso, video testimonial, etc). Usar cuando pidan info detallada de un curso o el programa.",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "integer",
                        "description": "ID de la persona"
                    },
                    "course_id": {
                        "type": "integer",
                        "description": "ID del curso para el cual enviar el asset"
                    }
                },
                "required": ["person_id", "course_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Escalar la conversación a un humano via Slack. Usar cuando no puedas resolver la consulta o el contacto pida hablar con una persona.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Motivo de la escalación"
                    }
                },
                "required": ["reason"]
            }
        }
    }
]

# ═══════════════════════════════════════
# TOOL EXECUTION
# ═══════════════════════════════════════

async def execute_tool(name: str, args: dict, context: dict = None) -> str:
    """Execute a tool call and return the result as string."""
    context = context or {}

    if name == "search_courses":
        return await tool_search_courses(args)
    elif name == "create_payment_link":
        return await tool_create_payment_link(args, context)
    elif name == "send_asset":
        return await tool_send_asset(args, context)
    elif name == "escalate_to_human":
        return await tool_escalate(args, context)
    else:
        return f"Tool '{name}' not implemented."


async def tool_search_courses(args: dict) -> str:
    """Search courses via v3 CRM RPC."""
    if not v3_available():
        return "Error: CRM v3 no conectado. No puedo buscar horarios en este momento."
    result = await v3_rpc("search_courses_complete", {
        "p_query": args.get("query", ""),
        "p_age": args.get("age"),
        "p_modality": args.get("modality"),
    })
    if result is None:
        return "Error al buscar cursos. Intentá de nuevo."
    return str(result)


async def tool_create_payment_link(args: dict, ctx: dict) -> str:
    """Create MercadoPago payment link via v3 CRM."""
    if not v3_available():
        return "Error: CRM v3 no conectado."
    result = await v3_rpc("create_mp_payment_link", {
        "p_person_id": args.get("person_id"),
        "p_course_id": args.get("course_id"),
        "p_amount": args.get("amount"),
        "p_description": args.get("description", "Pago IITA"),
    })
    if result is None:
        return "Error al crear link de pago."
    if isinstance(result, dict) and result.get("url"):
        return f"Link de pago generado: {result['url']}"
    return json.dumps(result)


async def tool_send_asset(args: dict, ctx: dict) -> str:
    """Send asset (PDF/video) to contact via v3 CRM."""
    if not v3_available():
        return "Error: CRM v3 no conectado."
    result = await v3_rpc("get_available_assets_for_ai", {
        "p_course_id": args.get("course_id"),
    })
    if result is None or (isinstance(result, list) and len(result) == 0):
        return f"No hay archivos disponibles para el curso {args.get('course_id')}. Describí el contenido en texto."
    return f"Assets disponibles para enviar: {json.dumps(result)}"


async def tool_escalate(args: dict, ctx: dict) -> str:
    """Escalate to human via Slack."""
    return f"Escalación registrada. Motivo: {args.get('reason', 'sin especificar')}. Un humano se encargará."
