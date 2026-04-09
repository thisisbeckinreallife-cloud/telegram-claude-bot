# Decisiones importantes

Decisiones de diseño, producto o estrategia que Lara ha tomado — con el razonamiento. Evita tener que re-discutir lo mismo.

## Formato
```
### YYYY-MM-DD — Título de la decisión
- **Contexto**:
- **Decisión**:
- **Razón**:
- **Alternativas descartadas**:
```

---

### 2026-04-07 — Arquitectura del bot de Telegram: CAG en vez de RAG
- **Contexto**: Necesitaba memoria persistente y escalable para el bot de Telegram.
- **Decisión**: Memoria basada en archivos .md en memory/knowledge/, inyectados en el system prompt (Cache-Augmented Generation). Sin vector DB, sin embeddings.
- **Razón**: Más simple, sin dependencias extra, aprovecha el prompt caching automático de Anthropic, y el volumen de memoria esperado cabe en el contexto de Sonnet (200k tokens).
- **Alternativas descartadas**: RAG con sqlite-vss + OpenAI embeddings (más complejo, más latencia, riesgo de chunks perdidos).

### 2026-04-07 — Modelo autónomo por defecto (bypassPermissions)
- **Contexto**: Las confirmaciones continuas paraban el trabajo del bot.
- **Decisión**: Modo `bypassPermissions` por defecto, con `/safe on` para reactivar confirmaciones.
- **Razón**: Lara quiere que las tareas se completen sin interrupciones.
- **Alternativas descartadas**: Listas blancas por herramienta (complejo y fácil de romper).

### 2026-04-07 — Auto-routing de modelo
- **Contexto**: Fijar un solo modelo (Opus) es caro; usar siempre Haiku sacrifica calidad.
- **Decisión**: Router con Haiku que clasifica cada mensaje y elige haiku/sonnet/opus + thinking_budget.
- **Razón**: Balance coste/calidad, transparente para el usuario.
- **Alternativas descartadas**: Heurísticas locales (frágiles), rutas fijas por comando (requiere decidir a mano).
