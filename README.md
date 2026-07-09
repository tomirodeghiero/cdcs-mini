# cdcs

POC del compilador **Contract-Driven Code Synthesis** (CDCS): convierte
contratos `@generate` embebidos en docstrings Python en
**implementaciones + tests sintetizados y verificados**.

Pipeline:

```
source.py
  → parse @generate        (parsing/)
  → validate contract       (validation/)
  → build augmented prompt  (synthesis/prompt.py)
  → synthesize impl         (synthesis/orchestrator.py + LLM)
  → synthesize tests        (separate LLM call, no impl visible)
  → verification gates      (synthesis/gates.py — AST + ruff/mypy/pytest)
  → emit artifacts          (synthesis/artifacts.py + cdcs.lock)
```

> 📄 **Para la lectura detallada de decisiones
> arquitectónicas, ver el PDF**:
> [`docs/cdcs_tesis_unrc.pdf`](docs/cdcs_tesis_unrc.pdf).
>
> Para una vista de pájaro del código (capas, módulos, reglas de
> dependencia, decisiones de diseño y métricas de testing) ver
> [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Cómo desarrollé el problema

El challenge pide construir, en pequeño, las primeras fases de un
**compilador**: léxico + sintáctico + análisis semántico + emisión. Lo
mapeé directo a la estructura del código:

| Fase de compilador          | Módulo                                  |
|-----------------------------|-----------------------------------------|
| Lex+parse del archivo Python | `parsing/source_parser.py` (`ast`)     |
| Lex+parse del DSL embebido  | `parsing/dsl_parser.py`                 |
| Análisis semántico          | `validation/validators.py`              |
| Emisión (IR como JSON)      | `reporting/json_reporter.py`            |
| Driver / orquestación       | `application/report_service.py`         |

Cada componente **recibe valores y devuelve valores**: nada muta estado
compartido. Eso me dio tres ventajas que valoré desde el primer día:

1. **Tests triviales**: cada capa se testea con datos puros, sin mocks.
2. **Reuso garantizado**: la misma lógica corre detrás del CLI y del
   backend HTTP. Si la salida del CLI cambia, la del backend cambia con
   ella; nunca pueden divergir.
3. **Determinismo barato**: si los datos que entran son los mismos y
   nadie muta nada por el camino, los datos que salen son los mismos.

### Decisiones de diseño que me parecieron defendibles

1. **AST primero, regex nunca para Python.** El parser de fuentes usa
   exclusivamente `ast`. Solo el parser DSL hace splits por línea sobre
   texto sin sintaxis Python (`behavior:`, `examples:`,
   `constraints:`). Cuando una línea es una expresión Python (un
   `require`, un `return`), se re-parsea con `ast.parse(mode="eval")`
   para extraer identificadores. Esto evita el clásico problema de las
   regex con strings, comentarios y casos borde.

2. **Inmutabilidad estricta del dominio.** Todos los modelos
   (`Parameter`, `Signature`, `BehaviorStep`, `Example`, `Contract`,
   `FunctionReport`, `Report`, `Diagnostic`) son
   `@dataclass(frozen=True, slots=True)`. Esto:
   - elimina toda una clase de bugs (mutación accidental),
   - permite que `Diagnostic` sea `order=True` y se ordene
     automáticamente por `(line, code, message)`,
   - hace explícito que cada paso de la pipeline produce un valor
     **nuevo**, nunca un valor mutado.

3. **Determinismo explícito en la serialización.**
   - El orden de las claves en el JSON lo controla el código, no el
     encoder (`sort_keys=False`).
   - Los diagnósticos se pre-sortean por `(line, code, message)`.
   - Los `parameters` se serializan como dict cuyo orden preserva el
     orden de declaración (Python dicts son insertion-ordered).
   - Los `references` dentro de cada `BehaviorStep` se sortean al
     emitirse a JSON.
   - Hay un test (`test_json_output_is_deterministic`) que corre el
     pipeline dos veces y compara los strings byte a byte.

4. **Capas con responsabilidades acotadas.** `parsing/` no conoce
   `validation/`. `validation/` no conoce `reporting/`. `reporting/`
   no conoce `parsing/`. `application/ReportService` es el único punto
   donde las capas se encuentran. Las interfaces entre capas son
   `Protocol`s livianas (`ContractValidator`, `Reporter`).

5. **Strategy pattern donde tiene sentido, no más.**
   - Las reglas de `behavior` (operation / require / return / catch-all)
     son una tupla de `_BehaviorRule(matches, parse)` que el dispatcher
     recorre top-to-bottom. Para sumar una regla nueva (p. ej. `assert`)
     se inserta una fila — el resto del código no se toca.
   - Los validators son una lista; el servicio los corre en orden.
     Sumar `validate_X` es agregar la función al tuple y ya.
   - Los reporters cumplen un `Protocol` con `render(report) -> str` y
     `to_dict(report) -> ReportDict`. Hoy hay uno (`JsonReporter`); el
     día que quiera YAML, HTML o lo que sea, no se rompe nada existente.

6. **JSON enriquecido (errata del challenge).** Cada paso aparece con:
   - `kind`: `operation` / `require` / `return`
   - `raw`: la línea original del docstring
   - `line`: la línea absoluta del archivo fuente
   - `references`: los identificadores que toca, ordenados

7. **El backend no duplica lógica.** `web/backend/app/main.py` arma
   una app FastAPI con dos endpoints, ambos delegan al **mismo**
   `ReportService.default()` que usa el CLI. Inyectado por FastAPI con
   `Depends`. Los tests verifican que la salida del HTTP es idéntica a
   la del CLI sobre el mismo input.

8. **El frontend no sabe parsear.** `web/frontend/` solo dispara
   peticiones, muestra un resumen y renderiza el JSON. Cualquier mejora
   del parser se propaga automáticamente.

---

## Estructura del repo

```
cdcs/
├── src/cdcs/        # núcleo Python
│   ├── domain/           # modelos inmutables + diagnósticos
│   ├── parsing/          # AST + DSL (con calls:/reads:)
│   ├── validation/       # validators con Protocol
│   ├── reporting/        # JSON reporter + schema TypedDict + base Protocol
│   ├── synthesis/        # ⭐ pipeline de síntesis (lo nuevo)
│   │   ├── policy.py     # ProjectPolicy + GenerationMode + VerificationPolicy
│   │   ├── prompt.py     # PromptBuilder + Prompt + PromptTarget
│   │   ├── llm.py        # LLMClient Protocol + Anthropic + RecordedLLMClient
│   │   ├── gates.py      # Structure/Security/CalleeAllowList/Complexity gates
│   │   ├── orchestrator.py  # synthesize loop (impl + tests separados)
│   │   └── artifacts.py  # emit .generated.py + cdcs.lock + check
│   ├── application/      # ReportService + SynthesisService (orquestadores)
│   └── cli.py            # entry point con subcomandos compile/check
├── web/
│   ├── backend/          # FastAPI (routers + dependencies + settings)
│   └── frontend/         # Next.js + Tailwind + Monaco
├── api/                  # entrypoint serverless para Vercel
├── tests/                # pytest, espejo de la estructura de src/
│   └── fixtures/
└── docs/                 # spec del challenge + tesis (PDF + LaTeX)
```

---

## Requisitos

Python **3.12+** · Node.js **18+**

## Correr el CLI

### Modo analyzer (default — el POC original)

```bash
cdcs tests/fixtures/valid_input.py --out report.json
```

Sin `--out`, el JSON va a *stdout*. El chrome del CLI (banner, resumen,
tabla de diagnósticos, JSON con syntax highlighting) va a *stderr*.

### Modo synthesizer

```bash
# Sintetiza impl + tests para cada @generate; emite .generated.py + cdcs.lock
cdcs compile path/to/ports.py --dest path/to/

# CI mode: verifica que los .generated.py no estén stale ni editados a mano
cdcs check path/to/ports.py --dest path/to/
```

#### LLM backends

El compilador y el endpoint HTTP `/synthesize/from-source` resuelven el
backend en este orden:

1. **`CDCS_LLM_PROVIDER`** explícito (`anthropic` / `ollama` / `pollinations`).
2. **`ANTHROPIC_API_KEY`** en env → Anthropic Claude (mejor calidad).
3. **Ollama local** en `localhost:11434` si está corriendo → recomendado
   para defensa de tesis (offline, sin rate limits). Instalación:
   `brew install ollama && ollama pull qwen2.5-coder:7b`.
4. **Pollinations.ai** (default). Público, sin API key, sin signup. Buen
   demo "fuera de la caja", pero rate-limited (~1 req cada 15 s a tier
   anónimo) y a veces flaky en horarios pico — el cliente reintenta
   automáticamente en 429/502/503/504.

```bash
# Forzar un backend específico
export CDCS_LLM_PROVIDER=anthropic CDCS_MODEL=claude-opus-4-7
export CDCS_LLM_PROVIDER=ollama    CDCS_MODEL=qwen2.5-coder:7b
export CDCS_LLM_PROVIDER=pollinations CDCS_MODEL=openai-fast
```

Códigos de salida: `0` = limpio · `1` = diagnósticos/drift detectados ·
`2` = error de uso.

## Correr la web (opcional)

En dos terminales:

```bash
# Backend
uvicorn web.backend.app.main:app --reload
# → http://127.0.0.1:8000
```

```bash
# Frontend
cd web/frontend
yarn install
yarn dev
# → http://localhost:3000
```

## Documentación

- **Tesis / presentación del proyecto**: [`docs/cdcs_tesis_unrc.pdf`](docs/cdcs_tesis_unrc.pdf).
- **Spec original del challenge**: [`docs/cdcs_challenge_candidate_version.pdf`](docs/cdcs_challenge_candidate_version.pdf).
- **API interactiva (Swagger)**: `http://127.0.0.1:8000/docs` con el backend corriendo. Alternativa en `/redoc`.
- **Demo en vivo**: https://cdcs-mini-app.vercel.app (frontend) · https://cdcs-mini-api.vercel.app/docs (Swagger).

## Desarrollo

El stack de calidad vive detrás de **[`uv`](https://docs.astral.sh/uv/)** + un
`Makefile` corto. El lockfile (`uv.lock`) es la fuente de verdad de las
versiones; CI corre `uv sync --locked` para reproducir el mismo entorno.

### Setup inicial

```bash
uv sync                                     # crea .venv con dev deps
# Atajo: make install
```

### Comandos diarios

| Tarea                       | uv                                              | make            |
|-----------------------------|-------------------------------------------------|-----------------|
| Lint (Ruff)                 | `uv run ruff check src tests web api`           | `make lint`     |
| Format (Ruff)               | `uv run ruff format src tests web api`          | `make format`   |
| Format check (CI)           | `uv run ruff format --check src tests web api`  | `make format-check` |
| Tipado (mypy strict)        | `uv run mypy --strict src tests web api`        | `make typecheck` |
| Tests (pytest)              | `uv run pytest`                                 | `make test`     |
| Lint YAML                   | `uv run yamllint -s .github .yamllint`          | `make yaml`     |
| Complejidad ciclomática     | `uv run radon cc -a -s src web api`             | `make complexity` |
| Maintainability Index       | `uv run radon mi -s src web api`                | `make maintainability` |
| Todo lo que corre CI        | —                                               | `make quality`  |
| Regenerar lockfile          | `uv lock`                                       | `make lock`     |

### Cómo leer Radon

- **CC (cyclomatic complexity)** por función. Grados: `A` (1-5, simple),
  `B` (6-10, ok), `C` (11-20, complejo), `D+` (refactor). Hoy el peor caso
  del repo es `B (6)` y el promedio es `A (2.77)`. CI lo reporta sin
  fallar; cuando cruce `C` consideramos un fail-gate.
- **MI (maintainability index)** por archivo. Grados: `A` (≥ 20, sano),
  `B` (10-19, atender), `C` (< 10, refactor). Todos los archivos están en
  `A`.

### pytest-mock

Disponible como `mocker` fixture (preferir sobre `unittest.mock` directo):

```python
def test_uses_mocker(mocker):
    mock_client = mocker.Mock(spec=LLMClient)
    mock_client.complete.return_value = "..."
    # ...
```

### Tipado

Se mantiene `mypy --strict` sobre todo el proyecto. No hay módulos
"legacy" exentos — la única exclusión es `tests/fixtures/` (son Python
deliberadamente malformado). Las nuevas funciones deben llegar con type
hints completos; los `Any` se justifican por comentario.

### CodeGraph (pendiente / setup externo)

CodeGraph no está integrado en este repo. Cuando se decida sumarlo,
documentar acá los pasos exactos (CLI, comando de generación del grafo,
ubicación del artefacto). No agregamos deps especulativas hasta tener
una herramienta concreta elegida.

### Nics (pendiente)

No hay referencias a Nix/Nics/NICs en el código ni en docs/. Si se
refiere a una herramienta interna específica del equipo, abrir issue
con el alcance y se integra como las demás (entrada en `[dependency-groups].dev`,
target en el Makefile, paso en CI).

## Tests, types y lint (resumen)

```bash
uv run pytest                               # 112 tests
uv run mypy --strict src tests web api      # 56 archivos, 0 issues
uv run ruff check src tests web api         # 0 issues
uv run ruff format --check src tests web api  # 56 files formatted
```

## DSL en un vistazo

```python
def parse_port(value: str) -> int:
    """@generate
    behavior:
      strip(value)
      require value matches digits
      require 1 <= int(value) <= 65535
      return int(value)

    examples:
      parse_port("80") == 80
      parse_port("0") raises ValueError

    constraints:
      no_imports
      no_network
      no_filesystem
    """
```

Cinco secciones: `behavior`, `examples`, `constraints`, **`calls:`**
y **`reads:`**. Pasos del behavior clasificados como `operation`,
`require` o `return`. Las expresiones se re-parsean con `ast` para
extraer identificadores (sin regex sobre código Python).

### La sección `calls:` y `reads:` (superficie de llamadas)

CDCS es *context-token-proof*: cada función lleva su propio contrato y
el modelo no ve el resto del módulo o de la clase. Eso obliga a
**declarar explícitamente** qué callees y atributos puede usar la
implementación. La sección sirve a la vez como:

* **input del prompt** — el modelo ve la firma + propósito de cada callee;
* **allow-list para el AST gate** — cualquier `self.X` no declarado
  produce `UndeclaredCalleeError`.

```python
class TokenService:
    def issue(self, user_id: int, ttl_seconds: int) -> str:
        """@generate
        behavior:
          require ttl_seconds > 0
          return self._sign(str(user_id))

        examples:
          issue(42, 60) raises ValueError

        calls:
          self._sign(payload: str) -> str    # HMAC of payload
          self._now() -> int                  # epoch seconds

        reads:
          self.secret_key: bytes              # used by _sign

        constraints:
          no_imports
        """
```

Sin esta sección, el LLM alucinaría llamadas a métodos privados de la
clase o duplicaría helpers ya existentes. Con ella, los `self.X` se
validan estructuralmente *antes* de aceptar el código generado.

## Diagnósticos

### Pipeline de análisis (la fase del POC original)

| Código                          | Causa                                                |
|---------------------------------|------------------------------------------------------|
| `SyntaxError`                   | el archivo no parsea con `ast.parse`                 |
| `MissingGenerateError`          | función sin docstring `@generate`                    |
| `MissingSamplesError`           | contrato sin sección `examples:`                     |
| `InconsistentPromptError`       | referencia a un parámetro inexistente                |
| `UnsupportedSignatureError`     | uso de `*args` o `**kwargs`                          |
| `MalformedDSLError`             | sección desconocida o sintaxis inválida              |
| `InvalidExampleError`           | ejemplo sin `==` ni `raises`                         |
| `IncompletePromptError`         | parámetro contenedor sin ejemplo de caso vacío       |
| `ContradictoryExamplesError`    | mismos args con resultados incompatibles             |
| `InconsistentCallableSurfaceError` | `self.X` declarado en función sin `self`         |

### Pipeline de síntesis (la fase nueva — errores tipo compilador)

| Código                          | Causa                                                |
|---------------------------------|------------------------------------------------------|
| `UnsafeGeneratedCodeError`      | código generado usa `eval`/`subprocess`/red/FS       |
| `UndeclaredCalleeError`         | `self.X(...)` no aparece en `calls:` ni `reads:`     |
| `GeneratedCodeTooComplexError`  | excede cyclomatic/lines/nesting de la política       |
| `ExceededLintIterationsError`   | no se logró código limpio en N intentos              |
| `ExceededTestIterationsError`   | no se lograron tests válidos en N intentos           |
| `PromptCannotSatisfyTestsError` | impl/tests no se reconcilian con el contrato         |

## Limitaciones conocidas

- Solo se analizan funciones a nivel de módulo. Métodos, lambdas y
  funciones anidadas se ignoran. Es deliberado: el contrato
  `@generate` es un concepto module-level en el spec.
- El parser DSL **no evalúa** expresiones. Solo las parsea con
  `ast.parse(mode="eval")` y extrae identificadores. Nada de `eval`,
  nada de `exec`.
- La numeración de líneas dentro del docstring se ancla a la línea del
  marcador `@generate`. Sigue siendo determinística aunque la
  indentación del docstring sea irregular.

---

**Autor:** Tomás Rodeghiero · [tomyrodeghiero@gmail.com](mailto:tomyrodeghiero@gmail.com)

## Licencia

Distribuido bajo licencia **MIT**. Ver [`LICENSE`](LICENSE) para los términos completos.

Copyright © 2026 Tomás Rodeghiero.