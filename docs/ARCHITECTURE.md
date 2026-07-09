# Arquitectura de `cdcs`

Este documento describe la arquitectura del prototipo **Contract-Driven
Code Synthesis (CDCS)** desde la perspectiva de un revisor académico:
qué hace cada capa, por qué está donde está, y cómo el código del
repositorio refleja la especificación descrita en
[`docs/cdcs_tesis_unrc.pdf`](cdcs_tesis_unrc.pdf) (en
adelante "el PDF"). Está pensado para leerse de corrido en menos de
quince minutos.

> Convención: las referencias a secciones del PDF aparecen como
> *PDF §N*. Las rutas de archivos son relativas a la raíz del
> repositorio.

---

## 1. Mirada de 30 segundos

CDCS toma una función Python con un **contrato conductual embebido**
en su docstring —comportamiento, ejemplos ejecutables, errores,
restricciones— y produce una implementación verificada más un módulo
de tests, ambos generados por un LLM. La salida del modelo se trata
como código **no confiable**: solo se acepta tras superar una cadena
de compuertas estáticas y dinámicas. La fuente de verdad es el
contrato; los artefactos sintetizados son desechables y se regeneran
cada vez que el contrato cambia.

El sistema tiene tres entradas operativas:

| Comando                          | Qué hace                                                                 |
| -------------------------------- | ------------------------------------------------------------------------ |
| `cdcs src.py`               | analiza + valida + emite reporte JSON (sin LLM)                          |
| `cdcs compile src.py`       | sintetiza implementación y tests, escribe `*.generated.py` + `cdcs.lock` |
| `cdcs check src.py`         | modo CI: verifica que los artefactos están sincronizados con el contrato |

---

## 2. Pipeline (PDF §6)

```
source.py
  │
  ├── (1) source_parser ──► firma del lenguaje (AST nativo)
  │
  ├── (2) dsl_parser ────► contrato @generate
  │         (behavior, examples, constraints, calls, reads)
  │
  ├── (3) validators ────► diagnostics (PDF §7-§8)
  │         • signature consistency
  │         • completeness
  │         • missing samples
  │         • examples consistency
  │         • callable-surface
  │
  ├── (4) augmented prompt ──► LLM
  │         (signature canónica + contrato + project + verification + mode)
  │
  ├── (5) gate chain ────► structure / security / callee-allowlist / complexity
  │         + bucle de reparación (≤ max_repair_iterations)
  │
  ├── (6) test prompt INDEPENDIENTE ──► LLM ──► gates de sanidad
  │
  └── (7) artifact emitter ──► foo.generated.py, test_foo.generated.py, cdcs.lock
                                                              (hash de provenance)
```

Cada nodo del pipeline tiene un módulo dedicado y un punto de entrada
estable. La orquestación lineal de estos pasos vive en
`src/cdcs/application/synthesis_service.py` y
`src/cdcs/synthesis/orchestrator.py`.

### 2.1 Mapeo a las secciones del PDF

| Fase                                  | Módulo                                          | PDF       |
| ------------------------------------- | ----------------------------------------------- | --------- |
| Parseo de fuente                      | `parsing/source_parser.py`                      | §6        |
| Extracción de firma                   | `parsing/source_parser.py` (vía AST)            | §2, §5    |
| Parseo del contrato                   | `parsing/dsl_parser.py`                         | §4, §6    |
| Validación (5 fases)                  | `validation/validators.py`                      | §7-§8     |
| Prompt aumentado                      | `synthesis/prompt.py`                           | §5        |
| Síntesis de implementación + repair   | `synthesis/orchestrator.py`                     | §6, §9    |
| Compuertas (AST + estáticas)          | `synthesis/gates.py`                            | §15       |
| Síntesis de tests (llamada separada)  | `synthesis/orchestrator.py::_synthesize_tests`  | §9        |
| Emisión de artefactos + lock          | `synthesis/artifacts.py`                        | §10       |
| Modo `check` (CI)                     | `application/synthesis_service.py::check`       | §17       |

---

## 3. Capas

El paquete `src/cdcs/` está organizado en capas concéntricas. La
regla es estricta: **las dependencias siempre apuntan hacia adentro**.
La capa `domain` no importa nada del proyecto; `application` puede
importar de cualquier capa interior pero no al revés.

```
                       ┌────────────────────────────────┐
                       │            cli.py              │   driver
                       └──────────────┬─────────────────┘
                                      ▼
                       ┌────────────────────────────────┐
                       │         application/           │   composición
                       │ report_service, synthesis_svc  │   (glue)
                       └──────────────┬─────────────────┘
                                      ▼
   ┌─────────────────────┬────────────┴────────────┬──────────────────────┐
   ▼                     ▼                         ▼                      ▼
┌────────────┐   ┌──────────────────┐   ┌────────────────────┐   ┌────────────────┐
│ parsing/   │   │  validation/     │   │  synthesis/        │   │  reporting/    │
│ source_p.  │   │  validators      │   │  orchestrator      │   │  json_reporter │
│ dsl_parser │   │  (5 validadores) │   │  gates / prompt    │   │  schema        │
└─────┬──────┘   └─────────┬────────┘   │  llm / policy      │   └────────┬───────┘
      │                    │            │  artifacts         │            │
      │                    │            └──────────┬─────────┘            │
      └────────────────────┴───────────────────────┴──────────────────────┘
                                      ▼
                       ┌────────────────────────────────┐
                       │           domain/              │   modelos
                       │  models, diagnostics           │   inmutables
                       └────────────────────────────────┘
                                      ▲
                       ┌──────────────┴─────────────────┐
                       │          language/             │   adaptadores
                       │  base (Protocols)              │   per-lenguaje
                       │  python/, typescript/          │
                       └────────────────────────────────┘
```

### Reglas por capa

| Capa          | Responsabilidad                                                                   | Imports permitidos                                  |
| ------------- | --------------------------------------------------------------------------------- | --------------------------------------------------- |
| `domain`      | Modelos inmutables (`Signature`, `Contract`, `Diagnostic`, …)                     | solo stdlib                                         |
| `language`    | Protocols + adaptadores por host language (Python, TypeScript)                    | `domain`                                            |
| `parsing`     | Source parser (AST) y DSL parser (contrato `@generate`)                           | `domain`, `language`                                |
| `validation`  | Validadores funcionales puros (firma ↔ contrato, ejemplos, llamadas, completitud) | `domain`, `language`                                |
| `synthesis`   | Prompt aumentado, orquestación LLM, compuertas, emisión, lockfile                 | `domain`, `language`, `parsing` (solo para tipos)   |
| `reporting`   | Serializadores deterministas hacia JSON                                           | `domain`                                            |
| `application` | Composición de las capas anteriores en *use cases* (`build_report`, `compile`)    | todas las internas                                  |
| `cli`         | Driver: parseo de argumentos, *rich* rendering, exit codes                        | `application`, `reporting`, `synthesis` (tipos)     |

Cualquier violación de estas reglas debería levantar una alerta en
revisión de código. `ruff` impone `ban-relative-imports`, y los
nombres de módulo son lo suficientemente largos para que importar
"hacia afuera" sea visible al instante.

---

## 4. Decisiones de diseño

Esta sección enumera las decisiones que no son obvias del código y
que un revisor querrá ver justificadas.

### 4.1 Inmutabilidad por defecto

Todos los modelos de `domain/` son `@dataclass(frozen=True, slots=True)`.
Las colecciones internas son `tuple` o `frozenset`, no `list` ni `set`.

**Por qué.** El pipeline atraviesa varias capas y, en presencia de
*repair loops*, una misma entidad puede ser leída desde múltiples
puntos del proceso. La inmutabilidad elimina por construcción una
fuente entera de bugs: nadie puede mutar el contrato a mitad de
camino sin que el compilador rechace el código. El costo (rebuild
incremental vía constructores) es despreciable a la escala del POC.

### 4.2 Inyección de dependencias vía `Protocol`

Las costuras de extensibilidad —`ExpressionParser`, `SourceParserProtocol`,
`LanguageAdapter`, `LLMClient`, `Reporter`— son `typing.Protocol`s
marcados como `@runtime_checkable`. No hay clases base abstractas, no
hay herencia.

**Por qué.** El testing se vuelve trivial: cualquier dataclass que
implemente la firma satisface el contrato. Permite además que el
soporte multi-lenguaje (Python ya, TypeScript en `language/typescript/`)
se sume sin tocar el núcleo. La regla operativa es:

> Cada nuevo lenguaje implementa cuatro Protocols y entrega un
> `LanguageAdapter`. El resto del pipeline no se entera.

### 4.3 Unidad de síntesis: una función

PDF §3 (*context-token proof design*): el LLM nunca ve el repositorio
completo. Recibe únicamente la firma canónica + el contrato + las
políticas de proyecto/verificación + el modo. El costo de síntesis
escala con la complejidad del subprograma, no con el tamaño del repo.

**Por qué.** Maximiza reproducibilidad, minimiza alucinaciones por
contexto irrelevante, y permite usar el `contract_hash` como clave
estable en `cdcs.lock` para detectar drift en CI.

### 4.4 Síntesis de tests en llamada independiente

`SynthesisOrchestrator._synthesize_tests` arma su propio prompt y
hace una llamada **separada** al LLM. La implementación generada
**nunca** se pasa al test prompt.

**Por qué.** Si el test ve la implementación, los tests tienden a
"pegarse" a esa implementación específica y se vuelven cómplices de
sus bugs. La separación reduce el sesgo de implementación (PDF §9).

### 4.5 Salida del modelo como código no confiable

Toda llamada al LLM produce texto que atraviesa, en orden:

1. **Parse**: `ast.parse` para Python, TS Compiler API para TypeScript.
2. **Structure gate**: la salida define exactamente una función con la
   firma esperada.
3. **Security gate**: AST scan de operaciones prohibidas
   (`eval`, `exec`, `subprocess`, `os.system`, lectura/escritura de
   archivos no autorizada, etc.).
4. **Callee allow-list gate**: las funciones invocadas existen en
   built-ins o están declaradas en `Calls:`.
5. **Complexity gate**: ciclomática, longitud, profundidad de anidamiento.

Si cualquier compuerta falla, el orquestador construye un *repair
prompt* y reintenta. Si agota el presupuesto
(`max_repair_iterations`), emite un código de error de la taxonomía
PDF §8 (`UNSAFE_GENERATED_CODE`, `EXCEEDED_LINT_ITERATIONS`, …).

### 4.6 Taxonomía de errores tipo compilador (PDF §8)

`DiagnosticCode` (en `domain/diagnostics.py`) enumera todos los
códigos posibles que el pipeline puede emitir. Cada error mapea a una
condición concreta y a una etapa concreta del pipeline. El JSON de
salida usa los nombres como strings (`StrEnum`) para que un consumidor
pueda hacer *string match* sin acoplarse al runtime de Python.

### 4.7 Provenance: `cdcs.lock`

`synthesis/artifacts.py` emite, junto a cada `.generated.py`, un
encabezado con `Source contract hash`, `Generator`, `Model` y `Mode`,
y mantiene `cdcs.lock` con los hashes de cada función sintetizada. El
modo `check` recalcula el hash y rechaza el commit si difieren —
manual edits y contratos no regenerados quedan bloqueados en CI.

---

## 5. Mapa de módulos

| Módulo                                            | Líneas | Responsabilidad principal                                                    |
| ------------------------------------------------- | -----: | ---------------------------------------------------------------------------- |
| `domain/models.py`                                |    134 | `Signature`, `Contract`, `Example`, `BehaviorStep`, `CallableSpec`, `Report` |
| `domain/diagnostics.py`                           |     43 | `DiagnosticCode` (PDF §8), `Diagnostic` (sortable, `frozen`)                 |
| `language/base.py`                                |    138 | Protocols (`ExpressionParser`, `LanguageAdapter`, `SourceParserProtocol`)    |
| `language/python/adapter.py`                      |     45 | Adaptador para Python 3.12+                                                  |
| `language/python/expression_parser.py`            |     86 | `ast.parse` para expresiones inline del DSL                                  |
| `language/typescript/adapter.py`                  |     87 | Adaptador para TypeScript (vía subprocess a `ts-runtime/`)                   |
| `language/typescript/source_parser.py`            |    149 | Parseo AST de TS delegado a un runtime Node externo                          |
| `parsing/source_parser.py`                        |    126 | AST walk: descubre funciones `@generate` y extrae firmas                     |
| `parsing/dsl_parser.py`                           |    507 | Parser line-oriented del DSL embebido en docstrings                          |
| `validation/validators.py`                        |    403 | 5 validadores funcionales puros + chain por adaptador                        |
| `synthesis/policy.py`                             |     90 | `SynthesisPolicy` = generation + project + verification                      |
| `synthesis/prompt.py`                             |    405 | `PromptBuilder`: arma el prompt aumentado (impl, test, repair)               |
| `synthesis/orchestrator.py`                       |    407 | Bucle de síntesis + reparación, llamada separada para tests                  |
| `synthesis/gates.py`                              |    580 | `GateChain` (structure, security, callee, complexity, externos)              |
| `synthesis/llm.py`                                |    500 | `LLMClient` Protocol + 4 backends (Anthropic, Cerebras, Ollama, Pollinations) |
| `synthesis/artifacts.py`                          |    394 | Emisión `.generated.py` + `cdcs.lock` + detección de drift                   |
| `reporting/json_reporter.py`                      |    128 | Serializador determinista a JSON (orden fijo de claves)                      |
| `application/report_service.py`                   |    108 | Compone `parsing` + `validation` para el modo *analyzer*                     |
| `application/synthesis_service.py`                |    256 | Compone todo para los modos `compile` y `check`                              |
| `cli.py`                                          |    608 | Driver: argparse + `rich` rendering + 3 subcomandos                          |

Total: **≈ 5.600 líneas** de Python + **≈ 595 líneas** de TypeScript
en `ts-runtime/`.

---

## 6. Modelo de datos

Los tres tipos más importantes del dominio:

### `Signature`
Lo único que el desarrollador **no** escribe en el contrato. Se deriva
del lenguaje (AST de Python o nodo `FunctionDeclaration` de TypeScript)
y es **autoritativo** (PDF §2): si el contrato contradice la firma,
el sistema emite `InconsistentPromptError`, no le pregunta al modelo.

```python
@dataclass(frozen=True, slots=True)
class Signature:
    parameters: tuple[Parameter, ...]
    returns: str | None
    has_variadic: bool = False
```

### `Contract`
La parte que **sí** escribe el desarrollador, parseada del docstring
`@generate`:

```python
@dataclass(frozen=True, slots=True)
class Contract:
    behavior: tuple[BehaviorStep, ...]          # require / return / operation
    examples: tuple[Example, ...]                # == o raises
    constraints: tuple[str, ...]                 # texto libre
    calls: tuple[CallableSpec, ...] = ()         # allow-list de callees
    reads: tuple[AttributeReadSpec, ...] = ()    # lecturas de atributos
    has_examples_section: bool = False
```

### `Diagnostic`
Mensajes en formato compiler-style con ubicación y código:

```python
@dataclass(frozen=True, slots=True, order=True)
class Diagnostic:
    line: int | None
    code: DiagnosticCode    # StrEnum: SyntaxError, MalformedDSLError, ...
    message: str
```

`order=True` permite ordenar diagnósticos por `(line, code, message)`,
garantizando salida determinista del reporter.

---

## 7. Estrategia de testing

| Suite                          | Ubicación                  | Propósito                                                        |
| ------------------------------ | -------------------------- | ---------------------------------------------------------------- |
| Unitarios por capa             | `tests/{capa}/`            | Cada módulo con su test sibling                                  |
| Integración end-to-end         | `tests/application/`       | Compone `report_service` y `synthesis_service` con fixtures      |
| Property-based (Hypothesis)    | `tests/properties/`        | Determinismo del DSL parser, round-trip JSON, consistencia de validadores |
| Backend HTTP (FastAPI)         | `tests/backend/`           | `web/backend/` — endpoints REST sobre el core                    |
| CLI                            | `tests/cli/`               | Driver, exit codes, rendering                                    |
| Fixtures malformadas           | `tests/fixtures/`          | Casos de prueba en Python/TypeScript (excluidos de lint y mypy)  |

**Métricas actuales** (rama `feat/cdcs-compiler`):

* 165 tests, todos verdes (`make quality`)
* Cobertura por ramas: **≈ 82 %** (umbral CI: 80 %, `coverage` fail-under)
* `mypy --strict` sin escapatorias salvo 3 `# type: ignore` documentados
  (interop con `anthropic` SDK opcional y con runtime TS subprocess)

---

## 8. Extender el sistema

### 8.1 Agregar un nuevo lenguaje

1. Crear `src/cdcs/language/{lang}/` con cuatro piezas:
   - `expression_parser.py` (implementa `ExpressionParser`)
   - `source_parser.py` (implementa `SourceParserProtocol`)
   - `adapter.py` (implementa `LanguageAdapter`)
   - `__init__.py` que reexporta el adapter.
2. Registrar la extensión en `cli._select_adapter`.
3. Si la sintaxis requiere parser externo (caso TypeScript con
   `ts-runtime/`), encapsular la llamada subprocess en `_runtime.py`
   para mantener el código Python sincrónico y testeable.

El resto del pipeline (DSL parser, validadores, prompt, gates) no
debería tocarse.

### 8.2 Agregar una nueva compuerta de verificación

1. Implementar `Gate` (en `synthesis/gates.py`) con un método
   `evaluate(candidate) -> tuple[GateFailure, ...]`.
2. Sumarla a `GateChain` (orden importa: parsing first, security
   antes que complejidad, etc.).
3. Si requiere herramienta externa (ruff, mypy, pytest), encapsular
   en un `ExternalToolGate` específico que reciba el path del
   artefacto en disco.

### 8.3 Agregar un nuevo proveedor de LLM

1. Implementar el `Protocol` `LLMClient` (`complete(prompt) -> str`).
2. Registrar el discriminador en `synthesis/llm.py::default_llm_client`
   con su orden de resolución por variable de entorno.

---

## 9. Referencias

- **Especificación de la tesis:** `docs/cdcs_tesis_unrc.pdf`.
- **Especificación original del challenge:** `docs/cdcs_challenge_candidate_version.pdf`.
- **Plantilla LaTeX de la tesis:** `docs/cdcs_tesis_unrc.tex`.
- **Propuesta de Trabajo Final** (formato UNRC): ver carta de propuesta.

Para una guía paso a paso de cómo usar el CLI y los ejemplos, ver el
[`README.md`](../README.md).
