# MyOrchestrator — Design Spec

**Fecha:** 2026-05-05
**Autor:** ipena (con asistencia de Claude Code)
**Estado:** Draft — pendiente de aprobación final del usuario antes de pasar a planning de implementación.

---

## 1. Problema y motivación

El usuario trabaja con múltiples proyectos (personales y de trabajo) en `<APPS_ROOT>/*` (ej. `gate`, `controller`, `speakingmcp`, etc.). El flujo actual es:

1. Abrir PyCharm en el proyecto.
2. Lanzar `claude` desde la terminal del proyecto.
3. Re-explicar contexto que Claude "olvidó" entre sesiones (a veces semanas de distancia).
4. Lanzar manualmente el dev server (ej. `./venv/bin/python manage.py runserver [::]:8000`).
5. Repetir todo lo anterior cada vez que cambia de proyecto.

**Dolores concretos:**
- Pérdida de memoria entre sesiones de Claude Code (ventana de contexto saturada tras meses de trabajo).
- Switching costoso entre proyectos (cada uno requiere re-arrancar el flujo).
- Re-explicar decisiones tomadas previamente.
- Sin visibilidad unificada del estado de los dev servers de cada proyecto.

**Constraint duro:**
- **No usar `ANTHROPIC_API_KEY`.** El sistema debe operar sobre la suscripción Claude Pro/Max ya autenticada en la CLI `claude`, sin consumir créditos extra de API.

## 2. Objetivos

- **Un punto de entrada único** (web local) para gestionar todos los proyectos en `<APPS_ROOT>/*`.
- **Memoria persistente cross-sesión** vía SQLite, alimentada automáticamente al cierre de cada sesión.
- **Continuidad real entre semanas:** Claude debe retomar donde quedó, sin re-explicación manual.
- **Control de dev servers** desde la misma UI.
- **Cero consumo de API key**: invocar `claude` CLI como subproceso vía PTY.
- **MVP funcional** con scope acotado (V1) y un V2 explícito para escalar después.

## 3. No-objetivos (V1)

- No es un editor de código (no compite con PyCharm).
- No hay multi-tenant ni auth (single-user, localhost-only).
- No hay multi-proyecto activo simultáneo en una sola pantalla (un proyecto a la vez).
- No hay dev servers daemonizados que sobrevivan al cierre del orquestador.
- No hay búsqueda semántica con embeddings (FTS5 es suficiente).
- No hay sync entre máquinas.

## 4. Arquitectura

### 4.1 Diagrama lógico

```
┌─────────────────────── Navegador (localhost:7000) ─────────────────────────┐
│  Sidebar de proyectos | Workspace (terminal + dev server) | Panel memoria  │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │ HTTP + WebSocket
┌────────────────────────────────────▼───────────────────────────────────────┐
│  Backend FastAPI (Python, localhost:7000)                                  │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────────┐    │
│  │ Project     │ │ Claude       │ │ Dev Server   │ │ Memory Service  │    │
│  │ Registry    │ │ Session Mgr  │ │ Mgr          │ │ (SQLite + digest)│   │
│  └─────────────┘ └──────┬───────┘ └──────────────┘ └────────┬────────┘    │
└──────────────────────────┼───────────────────────────────────┼─────────────┘
                           │ spawn (PTY)                       │ stdio
┌──────────────────────────▼─────────────────┐ ┌───────────────▼────────────┐
│  `claude` CLI subprocess                   │ │  MCP Server (myorch-mcp)   │
│  cwd=/APPS/<proyecto>/                     │ │  proceso Python separado   │
│  --mcp-config ~/.myorch/mcp.json           │ │  Tools: recall/save_*/list_*│
│  --append-system-prompt @CLAUDE.context.md │ │                             │
│  Hook Stop → save_summary vía MCP          │ │                             │
└────────────────────────────────────────────┘ └───────────────┬─────────────┘
                                                               ▼
                                                 ┌─────────────────────────┐
                                                 │ SQLite (~/.myorch/data.db)│
                                                 │ WAL mode, FTS5           │
                                                 └─────────────────────────┘
```

### 4.2 Componentes del backend (separación de responsabilidades)

| Componente | Responsabilidad única | No debe hacer |
|------------|----------------------|---------------|
| **Project Registry** | Descubrir proyectos en `APPS/*`, mantener metadata (path, tipo, dev_command, dev_port). | Tocar PTYs, lanzar procesos hijos. |
| **Claude Session Manager** | Manejo de PTY de `claude`, bombeo stdin/stdout, lifecycle de la sesión, captura de `claude_session_id`. | Acceder a SQLite directamente (delega a Memory Service). |
| **Dev Server Manager** | Arrancar/parar dev servers vía `subprocess`, ring buffer de logs en RAM. | Persistir logs en disco. |
| **Memory Service** | Única capa que toca SQLite. CRUD de `projects/sessions/decisions/recalls`. Genera digest. | Conocer detalles de la UI o del PTY. |

### 4.3 MCP Server (proceso separado)

- Script Python independiente: `python -m myorch.mcp_server`.
- Modo stdio. Spawneado por `claude` (no por FastAPI).
- Recibe `MYORCH_PROJECT` y `MYORCH_DB` por env var.
- Abre la misma SQLite con WAL para concurrencia segura.

## 5. Esquema de datos (SQLite)

```sql
CREATE TABLE projects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    path            TEXT NOT NULL UNIQUE,
    type            TEXT,                  -- 'django' | 'node' | 'python' | 'rust' | 'unknown'
    dev_command     TEXT,
    dev_port        INTEGER,
    description     TEXT,
    last_session_id TEXT,                  -- claude_session_id para --resume
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_opened_at  TIMESTAMP,
    metadata        JSON                   -- { "missing": false, "needs_review": false, ... }
);

CREATE TABLE sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    claude_session_id TEXT,
    started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at        TIMESTAMP,
    summary         TEXT,                  -- llenado por hook Stop
    files_touched   JSON,
    status          TEXT DEFAULT 'active'  -- 'active' | 'closed' | 'crashed'
);
CREATE INDEX idx_sessions_project ON sessions(project_id, started_at DESC);

CREATE TABLE decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    session_id      INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,
    tags            JSON,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_decisions_project ON decisions(project_id, created_at DESC);

CREATE TABLE recalls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    text            TEXT NOT NULL,
    tags            JSON,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_recalls_project ON recalls(project_id);
-- Nota: recalls son siempre por proyecto. Información cross-proyecto vive en
-- global_preferences (abajo) y NUNCA se mezcla con recalls de un proyecto.

CREATE TABLE global_preferences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    key             TEXT NOT NULL UNIQUE,
    value           TEXT NOT NULL,
    note            TEXT
);

CREATE VIRTUAL TABLE memory_fts USING fts5(
    content,
    project_id UNINDEXED,
    origin UNINDEXED,                       -- 'decision:42' | 'recall:7' | 'session:13'
    tokenize = 'porter unicode61'
);
-- Triggers en decisions/recalls/sessions mantienen memory_fts sincronizada.
```

**Nota:** `global_preferences` es opt-in. **No** se incluye en el digest por defecto. Solo se consulta si Claude llama explícitamente o si el usuario lo marca como global en la UI.

## 6. MCP Server — Contrato de tools

```python
# Lectura
recall(query: str, limit: int = 10) -> list[Hit]
list_recent_sessions(limit: int = 5) -> list[SessionBrief]
list_decisions(tag: str | None = None) -> list[Decision]

# Escritura
save_decision(title: str, body: str, tags: list[str] = []) -> int
save_recall(text: str, tags: list[str] = []) -> int
save_summary(summary: str, files_touched: list[str] = []) -> None
```

**Justificaciones:**
- Sin `delete_*` ni `update_*`: la memoria es append-only desde Claude. Edición/borrado solo desde la UI por el usuario.
- Sin `switch_project`: el proyecto activo es ambient (`MYORCH_PROJECT` env var), no se cambia mid-sesión.
- `recall` con FTS5 cubre el 90% de queries; embeddings se evalúan en V2 si hace falta.

### Configuración inyectada al lanzar `claude`

`~/.myorch/mcp.json`:

```json
{
  "mcpServers": {
    "myorch-memory": {
      "command": "python",
      "args": ["-m", "myorch.mcp_server"],
      "env": {
        "MYORCH_DB": "<HOME>/.myorch/data.db",
        "MYORCH_PROJECT": "<inyectado por Session Manager por sesión>"
      }
    }
  }
}
```

## 7. Flujos clave

### 7.1 Apertura de proyecto

1. Usuario hace clic en proyecto en sidebar.
2. Frontend → `POST /projects/<name>/open`.
3. Memory Service lee `projects + sessions + decisions + recalls` del proyecto.
4. Memory Service compone digest (~300–500 tokens) → escribe a `<project_path>/.myorch/CLAUDE.context.md`.
5. Project Registry lee `last_session_id`.
6. Session Manager spawneap:
   ```
   claude
     [--resume <last_session_id>]                 # si existe
     --mcp-config ~/.myorch/mcp.json
     --append-system-prompt @.myorch/CLAUDE.context.md
   ```
   con `cwd=<project_path>`, dentro de un PTY, env extendido con `MYORCH_PROJECT=<name>`.
7. Inserta fila en `sessions(status='active')`.
8. Frontend abre WebSocket a `/ws/sessions/<session_db_id>`.
9. xterm.js renderiza stdout; usuario escribe → stdin.

**Captura del `claude_session_id`:** mecánica exacta a validar en la primera tarea de implementación. Opciones a evaluar contra la versión actual del CLI `claude`:

1. Flag dedicado tipo `--print-session-id` (preferible si existe).
2. Parseo regex de las primeras líneas de stdout buscando el UUID que `claude` imprime al iniciar.
3. Lectura del directorio `~/.claude/projects/<encoded_path>/` después del primer mensaje, tomando el archivo de sesión más reciente.

La primera tarea del plan de implementación debe ser un spike de 30–60 min para confirmar cuál de estos mecanismos es estable. El resto del diseño no cambia: lo único que varía es **cómo** se captura el ID, no **dónde** se guarda (`projects.last_session_id` y `sessions.claude_session_id`) ni cómo se usa (`claude --resume <id>` en aperturas siguientes).

### 7.2 Cierre de sesión y generación de resumen

1. Frontend cierra WebSocket (cierra pestaña, click en stop, o timeout 5min idle).
2. Session Manager envía a stdin del PTY:
   ```
   Antes de cerrar: usa la tool MCP `save_summary(summary=..., files_touched=[...])`
   con un resumen de máx 5 líneas de lo que hicimos en esta sesión, archivos
   tocados, y decisiones nuevas si las hubo.
   ```
3. Claude responde y llama `save_summary` vía MCP → Memory Service escribe en `sessions.summary` + `sessions.files_touched`.
4. Session Manager espera ack (max 30s), cierra PTY (SIGTERM → SIGKILL), marca `sessions.status='closed'`, `ended_at=now()`.

**Por qué este flujo:** Claude todavía tiene el contexto completo cargado. Pedirle el resumen ANTES de cerrar es radicalmente más fiel que generarlo después de logs.

### 7.3 Paste de imagen

1. Usuario hace `Ctrl+V` con screenshot.
2. Frontend captura `paste` event, manda blob a `POST /sessions/<id>/upload-image`.
3. Backend guarda en `/tmp/myorch/<session_id>/<uuid>.png`, devuelve la ruta.
4. Frontend inserta literal `@/tmp/myorch/<session_id>/<uuid>.png ` en el textarea.
5. Usuario completa el mensaje y envía. `claude` lee la referencia nativamente.
6. Cleanup: archivos del directorio se borran al cerrar la sesión + cron al arrancar para huérfanos > 24h.

**Límite:** 5MB por imagen (validación en frontend + backend).

### 7.4 Dev server start/stop

1. Usuario hace clic en "▶ Start".
2. Dev Server Mgr: `subprocess.Popen(dev_command, cwd=project.path, stdout=PIPE, stderr=STDOUT)`.
3. Guarda PID en dict `{project_id: (pid, popen, ring_buffer)}`.
4. Hilo lector empuja líneas a ring buffer (últimas 500 líneas).
5. WebSocket `/ws/devserver/<project_id>` streamea al frontend.
6. "⏹ Stop": SIGTERM → espera 3s → SIGKILL si sigue vivo.

**V1:** dev servers son hijos del orquestador. Si Ctrl+C al orquestador, mueren.

### 7.5 Auto-scan de proyectos

1. Trigger: arranque del orquestador o clic en "+ Scan".
2. Lista directorios en `<APPS_ROOT>/*`.
3. Detección de tipo:
   - `manage.py` → `django`, propone `./venv/bin/python manage.py runserver [::]:8000`
   - `package.json` → `node`, propone `npm run dev`
   - `pyproject.toml` → `python`, lee `[tool].scripts.dev` si existe
   - `Cargo.toml` → `rust`, propone `cargo run`
   - default → `unknown`, sin propuesta
4. UPSERT en `projects`: si ya existe (mismo path), **no sobreescribe** `dev_command` (respeta overrides del usuario).
5. Si es proyecto nuevo, marca `metadata.needs_review=true` para badge en UI.

## 8. Layout web

### 8.1 Estructura

- **Sidebar (izquierda, ~240px):** lista de proyectos con dot de status (verde=sesión activa, ámbar=dev server corriendo, gris=cerrado). Búsqueda incremental. Botón "+ Scan".
- **Workspace (centro):** split horizontal.
  - **Terminal (~70%):** xterm.js + textarea de input + botón paste/clip + thumbnails de imágenes pegadas.
  - **Dev server (~30%):** estado + ▶/⏹ + tail de logs auto-scroll (toggle pausa).
- **Panel memoria (derecha, ~280px):** última sesión (resumen), decisions colapsables, recalls, búsqueda FTS5, botones "+ decision" / "+ recall" para creación manual.

### 8.2 Keyboard shortcuts

```
Ctrl+1..9         Switch a proyecto N del sidebar
Ctrl+Enter        Enviar mensaje
Ctrl+L            Limpiar terminal (no destruye sesión)
Ctrl+Shift+D      Toggle panel dev server
Ctrl+K            Focus en buscador de memoria
Esc               Cancelar mensaje en composición
```

### 8.3 Estados especiales

- **Sin proyectos detectados:** banner "No encontré proyectos en `<APPS_ROOT>/`. ¿Quieres registrar uno manual?"
- **Proyecto seleccionado, sin sesión activa:** terminal muestra botón "▶ Iniciar sesión Claude Code". No autospawn.
- **Sesión cargando:** skeleton + spinner.
- **Memoria vacía:** "Sin historial todavía. La memoria crecerá conforme trabajes."

## 9. Edge cases (V1)

| Caso | Comportamiento |
|------|----------------|
| `claude` CLI no en PATH | Banner al arranque + UI read-only para gestión de proyectos. |
| PTY muere de golpe | `sessions.status='crashed'`, evento WS al frontend, botón "Reabrir con --resume". |
| WebSocket se cae | PTY sobrevive 5 min idle. Reconectar reentrega buffer (~200 líneas). |
| Idle > 5 min sin WS | Hook Stop dispara resumen automático, cierra PTY como `closed`. Retomable después con --resume. |
| Dev server zombi | SIGKILL tras 3s sin respuesta a SIGTERM. |
| SQLite locked | WAL + retry 3x con 50ms backoff. Error visible en UI si excede. |
| Path de proyecto desapareció | `metadata.missing=true`, gris en UI, no se borra (memoria preservada). Botón "Re-localizar". |
| Imagen > 5MB | Rechazo en frontend con mensaje claro. |
| `/tmp/myorch/` lleno | Cleanup al cierre de sesión + cron al arrancar para huérfanos > 24h. |
| Dos pestañas abren mismo proyecto | Segunda pestaña pide confirmación de "tomar control"; una pestaña controla el PTY a la vez. |

## 10. Alcance MVP

### V1 — Must have

- [x] Auto-scan + override manual de `dev_command`.
- [x] Apertura de proyecto con digest inyectado vía `--append-system-prompt`.
- [x] Sesión Claude persistente vía PTY + WebSocket + xterm.js.
- [x] `--resume` automático de sesión previa.
- [x] Paste de imágenes desde clipboard.
- [x] MCP server con 6 tools (recall, list_recent_sessions, list_decisions, save_decision, save_recall, save_summary).
- [x] Hook Stop genera resumen al cerrar.
- [x] Dev server start/stop con tail de logs.
- [x] Panel de memoria: ver última sesión, decisions, recalls; búsqueda FTS5.
- [x] Crear decision/recall manualmente desde la UI.
- [x] Reconexión de WebSocket sin perder PTY.

### Nice to have (V1 si sobra tiempo)

- Tema light/dark toggle.
- Exportar memoria de un proyecto a Markdown.
- Pin de decisiones (siempre arriba en el digest).
- Tags como filtro rápido en sidebar de memoria.

### V2 (explícitamente fuera de V1)

- Multi-proyecto activo simultáneo (multi-tab real).
- Dev servers daemonizados que sobreviven al orquestador.
- Embeddings + búsqueda semántica (sqlite-vec).
- Editor de archivos embebido.
- Sync de DB entre máquinas.

## 11. Stack técnico (consolidado)

```
Backend:
  python 3.11+
  fastapi + uvicorn
  jinja2 + htmx
  websockets (incluido en starlette)
  ptyprocess o pexpect (manejo de PTY)
  sqlite3 (stdlib, modo WAL, FTS5)
  pydantic v2

Frontend:
  htmx + hyperscript
  xterm.js
  alpine.js (mínimo, donde htmx no alcance)
  Tailwind CDN

Infraestructura:
  Un solo proceso uvicorn en localhost:7000
  ~/.myorch/data.db (SQLite WAL)
  ~/.myorch/mcp.json (config para claude CLI)
  /tmp/myorch/<session_id>/ (imágenes temporales)
```

## 12. Decisiones de diseño y tradeoffs

| Decisión | Alternativa descartada | Razón |
|----------|-----------------------|-------|
| `claude` CLI subprocess vía PTY | SDK de Anthropic con API key | Constraint duro: usar suscripción, no consumir créditos. |
| FastAPI + Jinja2 + HTMX | React/Svelte SPA | Single-user local; HTMX cubre todos los casos sin build step. |
| Digest push + MCP pull (híbrido) | Solo MCP (pull) | Garantiza contexto crítico al inicio sin depender de que Claude consulte. |
| Hook Stop genera resumen | Parser ad-hoc de logs post-hoc | Claude tiene contexto completo en ese momento; el resumen es 100x más fiel. |
| SQLite + FTS5 | Postgres / vector DB | Single-user, bajo volumen, cero ops; FTS5 cubre el caso por años. |
| MCP server proceso separado | Embebido en FastAPI | Aislamiento: si FastAPI cae, Claude sigue. Múltiples sesiones independientes. |
| Append-only desde Claude (sin delete/update tools) | Claude puede editar memoria | Memoria histórica no debe ser reescrita por el agente; solo por el humano. |
| Auto-scan + override (nunca sobreescribe edits) | Config file por proyecto (`.myorch.yaml`) | No contamina repos del trabajo con archivos extra. |
| Un proyecto activo a la vez (V1) | Multi-tab desde V1 | Reduce complejidad de PTY/WS mgmt; entregable más rápido. |
| Dev servers mueren con orquestador (V1) | Daemonización con setsid | Reduce surface area; daemonización va en V2 si se necesita. |

## 13. Estructura de directorios propuesta

```
MyOrchestrator/
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-05-05-myorchestrator-design.md   ← este documento
├── myorch/
│   ├── __init__.py
│   ├── app.py                  # FastAPI app
│   ├── config.py               # paths, ports, defaults
│   ├── db.py                   # SQLite connection, migraciones
│   ├── models.py               # Pydantic models
│   ├── services/
│   │   ├── project_registry.py
│   │   ├── session_manager.py
│   │   ├── dev_server_manager.py
│   │   └── memory_service.py
│   ├── routers/
│   │   ├── projects.py
│   │   ├── sessions.py
│   │   ├── devservers.py
│   │   └── memory.py
│   ├── mcp_server.py           # entrypoint del MCP (proceso separado)
│   ├── digest.py               # generación del CLAUDE.context.md
│   ├── templates/              # Jinja2
│   │   ├── base.html
│   │   ├── workspace.html
│   │   └── partials/
│   └── static/
│       ├── xterm/
│       ├── htmx.min.js
│       └── app.css
├── tests/
│   ├── test_memory_service.py
│   ├── test_session_manager.py
│   ├── test_mcp_server.py
│   └── test_project_registry.py
├── pyproject.toml
└── README.md
```

## 14. Próximo paso

Tras aprobación del spec, pasar al skill `superpowers:writing-plans` para construir el plan de implementación detallado, dividido en milestones ejecutables.
