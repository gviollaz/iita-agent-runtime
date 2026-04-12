# Shadow mode

## Qué es

V4 procesa el mismo input que v3 pero NO responde al usuario. Solo loggea para comparación.

## Cómo comparar

Frontend `AgentRuntime.jsx` en `IITA-Proyectos/iitacrm`:
- Inline prompt fragment editing
- Star ratings por output
- Shadow compare side-by-side v3 vs v4
- Webhook monitor

## Cuándo desactivar shadow

Solo cuando:
1. V3 key verificada
2. Meta tokens válidos
3. Webhook registration confirmada
4. Fases 4-6 completas

## Pendientes bloqueantes

- Verificar V3 key
- Verificar Meta tokens
- Registrar webhook
- Cerrar Fases 4-6
