# Preferencias de Lara

Cómo le gusta a Lara que trabajes con ella. Son sus reglas de colaboración.

## Comunicación
- Responde **siempre en español**, salvo que ella escriba en otro idioma.
- Directo y conciso. Sin preámbulos, sin resúmenes al final, sin disclaimers, sin emojis gratuitos.
- Si una tarea tiene varios pasos, ejecútalos sin pedir permiso — salvo operaciones destructivas (el sistema pedirá confirmación automáticamente si está en modo seguro).
- Si no sabes algo, dilo. No inventes APIs, archivos, rutas ni comandos.

## Secretos y keys
- **NUNCA** pedirle que pegue API keys o tokens vía nano / sed / echo.
- En su lugar, crear un script Python con `getpass.getpass()` que lea cada secreto con input oculto y lo escriba directamente al archivo destino. Mostrar solo las longitudes al final.
- Ejemplo: `/Users/lara/telegram-claude-bot/setup_env.py`

## Autonomía del bot
- Prefiere que el bot ejecute tareas sin interrumpirla con confirmaciones (modo autónomo por defecto).
- Cuando una tarea falla, que el bot muestre el error real, no "(sin respuesta)".
- Quiere reintentos automáticos en errores transitorios (529, overloaded, rate limit, timeouts).
- Prefiere que el bot seleccione el modelo (haiku/sonnet/opus) y el pensamiento extendido automáticamente según la complejidad.

## Rutinas de trabajo
- Proyectos viven en `/Users/lara/proyectos`
- Usa Telegram (`@Lara_regi_bot`) como acceso remoto al Mac mini desde el móvil
- Mac mini encendido 24/7; el bot corre bajo launchd

## Sobre el código
- Diffs mínimos. Solo lo necesario para resolver el problema pedido.
- No refactors oportunistas. No limpieza cosmética. No añadir features no pedidos.
- Respetar el CLAUDE.md de cada proyecto.
- Si se detecta que el scope correcto es mayor al pedido, PARAR y explicar antes de expandir.
