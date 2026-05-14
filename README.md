# cdcs-mini

Herramienta que analiza código Python y genera
un reporte JSON **determinístico** sobre los contratos `@generate`
embebidos en docstrings.

> 📄 **Para la lectura detallada de decisiones
> arquitectónicas, ver el PDF**:
> [`docs/cdcs_mini_tesis_unrc.pdf`](docs/cdcs_mini_tesis_unrc.pdf).

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
cdcs-mini/
├── src/cdcs_mini/        # núcleo Python (parser, validators, reporter, CLI)
│   ├── domain/           # modelos inmutables + diagnósticos
│   ├── parsing/          # AST + DSL
│   ├── validation/       # validators con Protocol
│   ├── reporting/        # JSON reporter + schema TypedDict + base Protocol
│   ├── application/      # ReportService (orquestador)
│   └── cli.py            # entry point con rich UI
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

```bash
cdcs-mini tests/fixtures/valid_input.py --out report.json
```

Sin `--out`, el JSON va a *stdout*. El chrome del CLI (banner, resumen,
tabla de diagnósticos, JSON con syntax highlighting) va a *stderr*.
Códigos de salida: `0` = sin diagnósticos · `1` = con diagnósticos ·
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

- **Tesis / presentación del proyecto**: [`docs/cdcs_mini_tesis_unrc.pdf`](docs/cdcs_mini_tesis_unrc.pdf).
- **Spec original del challenge**: [`docs/cdcs_challenge_candidate_version.pdf`](docs/cdcs_challenge_candidate_version.pdf).
- **API interactiva (Swagger)**: `http://127.0.0.1:8000/docs` con el backend corriendo. Alternativa en `/redoc`.
- **Demo en vivo**: https://cdcs-mini-app.vercel.app (frontend) · https://cdcs-mini-api.vercel.app/docs (Swagger).

## Tests, types y lint

```bash
pytest                                      # 35 tests
mypy --strict src tests web api             # 40 archivos, 0 issues
ruff check src tests web api                # 0 issues
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

Tres secciones (`behavior`, `examples`, `constraints`); pasos
clasificados como `operation`, `require` o `return`. Las expresiones se
re-parsean con `ast` para extraer identificadores (sin regex sobre
código Python).

## Diagnósticos

| Código                       | Causa                                                |
|------------------------------|------------------------------------------------------|
| `SyntaxError`                | el archivo no parsea con `ast.parse`                 |
| `MissingGenerateError`       | función sin docstring `@generate`                    |
| `MissingSamplesError`        | contrato sin sección `examples:`                     |
| `InconsistentPromptError`    | referencia a un parámetro inexistente                |
| `UnsupportedSignatureError`  | uso de `*args` o `**kwargs`                          |
| `MalformedDSLError`          | sección desconocida o sintaxis inválida              |
| `InvalidExampleError`        | ejemplo sin `==` ni `raises`                         |

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