# Agent Runtime — Arquitectura

## Deploy

- Plataforma: Railway
- Versión: v0.8.1
- Repo: este (`gviollaz/iita-agent-runtime`)

## Componentes

- **4 tools** registradas en runtime
- **4 prompt_fragments** en Supabase v4
- Shadow mode activo comparando outputs v3 vs v4

## Supabase v4

- Project: `rvdgbdmjkaqnxdkrqjci`
- 44 tablas (ver ESTADO_SITUACION en `gviollaz/iita-system docs/platform-v4/`)

## Flujo de mensaje

1. Webhook recibe inbound (WA/IG/Messenger)
2. Runtime v4 procesa en paralelo con v3 (shadow)
3. V3 responde al usuario (producción)
4. V4 log output para comparación
5. Dashboard frontend muestra diff
