# Laboratorio web de requisitos

Prototipo de tesis para transformar fuentes textuales heterogéneas en requisitos funcionales (RF), requisitos no funcionales (RNF) e historias de usuario (HU). La aplicación organiza el trabajo por proyectos, incorpora una fase de aclaración con el usuario, genera mediante agentes especializados y conserva trazabilidad a nivel de fragmento.

El núcleo y la interfaz son independientes del dominio: cada proyecto se construye exclusivamente a partir de sus propias fuentes y respuestas de definición. No existe un corpus de demostración precargado en la aplicación.

## Flujo implementado

```text
Crear proyecto
      ↓
Cargar PDF, DOCX, TXT o Markdown, o pegar texto libre
      ↓
Extraer, segmentar e indexar las fuentes
      ↓
Revisar la interpretación provisional y responder solo las aclaraciones necesarias
      ↓
Revisar y, si se desea, ajustar el presupuesto adaptativo por tipo
      ↓
Generar RF, RNF y HU mediante agentes especializados
      ↓
Validar trazabilidad, formato y posibles duplicados
      ↓
Ejecutar opcionalmente validación semántica de evidencia con Jev
      ↓
Revisar manualmente o solicitar una propuesta de edición
      ↓
Exportar DOCX o JSON
```

El agente de definición recorre todos los fragmentos del proyecto mediante análisis jerárquico por lotes. Primero obtiene hallazgos trazables, después construye un perfil provisional editable y formula preguntas únicamente para información ausente o dudosa, contradicciones y decisiones relevantes. Las respuestas confirmadas se almacenan como fragmentos `USR-DEF-*`, por lo que pueden citarse como evidencia sin confundirse con las fuentes originales.

Si una definición se confirma nuevamente después de haber generado resultados, la aplicación solicita confirmación antes de eliminar la generación anterior. Al aceptar se conservan fuentes y respuestas, pero se reinician artefactos, versiones, observaciones y ejecuciones para impedir que convivan salidas producidas desde definiciones distintas.

## Persistencia

| Medio | Responsabilidad |
|---|---|
| SQLite | Proyectos, metadatos de fuentes, preguntas, respuestas, artefactos, versiones, ejecuciones y validaciones. |
| ChromaDB | Embeddings y búsqueda semántica de fragmentos, aislados por proyecto. |
| Sistema de archivos | Documentos originales, caché del modelo de embeddings y exportaciones descargadas por el usuario. |

La recuperación es híbrida: combina TF-IDF y similitud vectorial mediante Reciprocal Rank Fusion, con reranking multilingüe opcional. Los embeddings se calculan localmente con `sentence-transformers`; DeepSeek es el proveedor LLM validado para interpretar el corpus, generar preguntas adaptativas y artefactos, y proponer revisiones.

Desde Configuración en la página de Proyectos se puede activar el reranking y elegir entre el modelo local y Jev vía OpenRouter. La elección se guarda en SQLite y se aplica a las siguientes generaciones y revisiones. El modelo local usa CPU y memoria del equipo; Jev envía la consulta y los fragmentos candidatos a OpenRouter, consume créditos y requiere `OPENROUTER_API_KEY` en `.env`. Si Jev falla, la ejecución informa el error para que no parezca que se usó el proveedor seleccionado. Fuentes se procesa localmente y no consume tokens de API. En Revisión, la pestaña Ejecución muestra los tokens registrados por proyecto, con desglose de Definición, Generación, Revisiones, Validación semántica y Jev. Las ejecuciones anteriores sin telemetría completa se indican como tales.

## Reanudación y resultados de generación

El análisis de definición guarda un punto de control por lote. Si falla la síntesis final, el siguiente intento reutiliza únicamente los lotes cuyo contenido conserva la misma huella SHA-256 y repite la síntesis, no todas las llamadas anteriores.

La generación guarda RF, RNF y HU al finalizar cada agente. Si una ejecución se interrumpe, la interfaz muestra qué tipos quedaron conservados y permite reanudar desde el primer agente pendiente. Una reanudación mantiene los límites y la configuración experimental de la ejecución original, y no contabiliza otra vez los tokens de los agentes reutilizados.

Al finalizar se presenta la cantidad generada frente al máximo solicitado por tipo. El máximo es un presupuesto operativo, no una cuota; devolver menos artefactos no constituye por sí solo un error.

Cuando Jev se usa como reranker, cada ejecución conserva la auditoría de todos los candidatos: posición y puntuación RRF, probabilidad de relevancia, probabilidad de evidencia útil, promedio aplicado, posición final y selección. También registra solicitudes, identificadores informados por OpenRouter, modelo solicitado y servido, proveedor, intentos, tokens, costo cuando está disponible y latencia. Las respuestas 429 y 5xx se reintentan de forma acotada; no existe sustitución silenciosa por otro reranker.

La configuración de referencia utiliza `deepseek-flash`, identificador oficial de DeepSeek-V4.1-Flash. ReqLab desactiva explícitamente el modo de razonamiento para mantener una generación JSON controlada y reproducible, conserva una temperatura de `0.1`, limita cada respuesta a `12000` tokens y registra el modelo servido, la huella del sistema, el motivo de finalización y el consumo desglosado cuando la API los proporciona. Estos valores pueden configurarse mediante `LLM_MODEL`, `LLM_THINKING_ENABLED` y `LLM_MAX_TOKENS`, pero deben congelarse antes del experimento formal.

Cada ejecución conserva una instantánea de su configuración técnica. Los resultados incluyen relaciones explícitas RF–RNF–HU, validación por artefacto y vínculos separados hacia la evidencia documental. Angular presenta esta información en las vistas de revisión, trazabilidad, observaciones y ejecución.

Las observaciones son alertas, no decisiones automáticas. Cada una permite abrir el artefacto afectado para editarlo, reclasificarlo, cambiar su estado o solicitar una propuesta asistida. Una reclasificación crea una nueva versión, asigna una clave acorde con el nuevo tipo y actualiza las relaciones internas que utilizaban la clave anterior.

Los RF utilizan patrones EARS y los RF/RNF incluyen criterios de verificación. Los RNF conservan categoría de calidad, métrica, unidad, umbral y método de verificación cuando están sustentados; lo ausente queda pendiente. La prioridad admite `No definida` y nunca se completa automáticamente como media. La exportación DOCX presenta fichas según el tipo de artefacto y una matriz con fragmento, fuente y extracto de evidencia.

## Piloto opcional de validación semántica con Jev

ReqLab puede evaluar, de manera separada, si los fragmentos citados respaldan semánticamente cada artefacto. Jev clasifica el respaldo conjunto como `completo`, `parcial`, `ausente`, `contradictorio` o `indeterminado`, y cada enlace como `aporta_respaldo`, `solo_contexto`, `irrelevante`, `contradice` o `indeterminado`.

El componente funciona exclusivamente en modo `shadow`: no edita, aprueba, rechaza ni reclasifica artefactos y no sustituye la validación determinista ni el juicio experto. Se mantiene desactivado por defecto. Una edición del artefacto, sus citas o la evidencia hace que el último informe aparezca como obsoleto.

Para habilitar una prueba remota, configure en `.env`:

```text
SEMANTIC_VALIDATION_ENABLED=True
SEMANTIC_VALIDATION_MODE=shadow
OPENROUTER_API_KEY=<clave>
TYPESAFE_BASE_URL=https://openrouter.ai/api
TYPESAFE_ENDPOINT_PATH=/alpha/decisions
TYPESAFE_MODEL=typesafe/jev-1.13
```

Después de generar artefactos:

```text
POST /api/projects/{project_id}/semantic-validation
GET  /api/projects/{project_id}/semantic-validation
GET  /api/runs/{run_id}
```

El `POST` ejecuta la evaluación en segundo plano. El `GET` devuelve la configuración, la última ejecución y el informe separado, incluido el indicador `stale`. Las pruebas automatizadas usan clientes simulados y nunca realizan llamadas ni generan cargos. Las preguntas, entradas, versión efectiva del modelo, probabilidades, latencia, consumo e intentos se conservan para reproducir el piloto; las credenciales no se almacenan.

Antes de generar, la API calcula para RF, RNF y HU un intervalo operativo a partir del volumen de evidencia y de indicios lingüísticos generales presentes en los fragmentos. Angular muestra el mínimo, el valor sugerido y el máximo mediante controles deslizantes independientes. El valor seleccionado es un **tope de salida**, no una cuota ni una estimación del número real de requisitos: los agentes deben devolver menos elementos cuando la evidencia no sustente más. La recomendación, el método utilizado y la selección del usuario quedan registrados en la ejecución.

## Ejecución con Docker

Requisitos:

- Docker Desktop en ejecución.
- Un archivo `.env` basado en `config.example.env`.
- Una clave válida en `LLM_API_KEY` o, por retrocompatibilidad, `DEEPSEEK_API_KEY`.

Desde esta carpeta:

```powershell
docker compose up --build
```

Después abre la aplicación:

```text
http://localhost:8080/projects
```

La documentación interactiva de la API está disponible en `http://localhost:8000/docs`.

Para detener la aplicación:

```powershell
docker compose down
```

El directorio `data/` se monta como volumen, por lo que los proyectos sobreviven al reinicio del contenedor. La primera indexación puede tardar mientras se descarga y almacena el modelo local de embeddings en `data/model_cache`.

El archivo `.env` no se copia a la imagen Docker ni se incluye en el control de versiones.

## Ejecución local sin Docker

API:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = "$PWD\src"
uvicorn reqlab.api.app:app --reload --port 8000
```

Frontend, en otra terminal:

```powershell
cd frontend
npm install
npm start
```

## Pruebas

Las pruebas del núcleo y del flujo web no consumen un proveedor LLM externo:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover -s tests -v
```

## Componentes principales

- `frontend/src/app`: interfaz Angular, rutas, estado y componentes reutilizables.
- `api/app.py`: aplicación FastAPI y composición de rutas HTTP.
- `storage.py`: esquema y repositorio SQLite.
- `documents.py`: extracción y segmentación de fuentes.
- `vector_store.py`: ChromaDB, embeddings y recuperación híbrida.
- `agents.py`: contratos de los agentes RF, RNF, HU, definición y revisión.
- `generation_budget.py`: cálculo versionado del presupuesto adaptativo de generación.
- `services.py`: casos de uso y orquestación del flujo.
- `validation.py`: controles deterministas de trazabilidad y consistencia.
- `semantic_validation.py`: evaluación opcional del respaldo documental y política de abstención.
- `typesafe_client.py`: cliente independiente para el endpoint System One de TypeSafe.
- `exporters.py`: exportación a Word.

## Límites actuales del MVP

- Ejecución local y de un solo usuario; no incluye autenticación.
- Los PDF deben contener texto seleccionable; no se ha incorporado OCR.
- Las entrevistas deben estar transcritas.
- La validación automática produce alertas y no sustituye la evaluación de expertos.
- No compara modelos ni variantes arquitectónicas; implementa la arquitectura definida para la tesis.
