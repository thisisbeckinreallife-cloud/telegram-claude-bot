# Proyectos activos

Proyectos en los que Lara está trabajando ahora mismo, con contexto, estado y decisiones recientes. El bot mantiene este archivo actualizado.

## Formato por proyecto
```
### Nombre del proyecto
- **Ruta**: /Users/lara/proyectos/...
- **Estado**: activo / pausado / terminado
- **Objetivo**:
- **Stack**:
- **Decisiones clave**:
- **Próximos pasos**:
- **Notas**:
```

---

### telegram-claude-bot
- **Ruta**: /Users/lara/telegram-claude-bot
- **Estado**: activo
- **Objetivo**: Bot de Telegram que delega a Claude vía claude-agent-sdk para operar la Mac mini de Lara desde el móvil.
- **Stack**: Python 3.12, python-telegram-bot, claude-agent-sdk, openai (TTS/STT), launchd
- **Decisiones clave**:
  - Modelo auto-ruteado (haiku/sonnet/opus) según complejidad de la tarea
  - Memoria CAG mediante archivos en memory/knowledge/ inyectados en el system prompt
  - Modo autónomo por defecto (bypassPermissions), /safe on para confirmaciones
  - Sesiones persistentes entre reinicios vía sessions.json + resume=session_id
  - **Concurrency safety (2026-04-08)**: Locks por sesión (asyncio.Lock) para evitar race conditions con concurrent_updates=True
- **Mejoras implementadas (2026-04-08)**:
  1. ✅ SESSION_LOCKS: Mutex por chat_id para sincronizar apply_routing → ensure_client → close_session
  2. ✅ Queue para confirmaciones: pending_decisions como asyncio.Queue (evita sobrescrituras simultáneas)
  3. ✅ Typing indicator: Loop cada 4s para mantener UI responsiva en tareas largas (>5s)
  4. ✅ Limpieza de archivos: try/finally en handle_photo/handle_document
  5. ✅ Deadlock fix: close_session_unlocked() para evitar lock reentrante
  6. ✅ Tracking de coste: `session.total_cost` acumula USD, comando `/cost` lo muestra
- **Próximos pasos**: Testear en producción con concurrencia real (múltiples mensajes simultáneos).

### Claude&Codex (workspace vibe-coding)
- **Ruta**: /Users/lara/proyectos/Claude&Codex
- **Estado**: activo
- **Objetivo**: Workspace operador inspirado en Manus para vibe-coding con spine Project → Folder → Task → Chat → Attachments → Model Selection → GitHub Bootstrap → Railway Deploy → Preview/Deploy Truth.
- **Stack**: Next.js App Router, TypeScript, Prisma, PostgreSQL, Tailwind
- **Notas**: Tiene CLAUDE.md con reglas estrictas (diffs mínimos, no refactors oportunistas, etc.)
