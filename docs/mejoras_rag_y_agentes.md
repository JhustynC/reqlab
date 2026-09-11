# ReqLab: Reporte Consolidado de Mejoras RAG y Arquitectura Multi-Agente

Este documento detalla las mejoras implementadas en la rama `feature/rag-and-agent-improvements`, su justificación y las extensiones realizadas en Angular. Los contratos existentes se conservaron y los campos nuevos son aditivos.

## Resultado de la auditoría técnica

| Hallazgo original | Corrección aplicada | Verificación |
|---|---|---|
| El tipo de fuente no llegaba al segmentador | `source_kind` se transmite desde la ingesta | Prueba con segmentación de correo |
| Una consulta E5 recibía `passage: query:` | Consulta y pasaje se codifican por rutas separadas | Prueba de prefijos asimétricos |
| El reranker estaba creado pero desconectado | Se inyecta en todos los recuperadores del servicio | Prueba de composición del servicio |
| `RETRIEVAL_TOP_K` era ignorado | El valor configurado llega al agente generador | Prueba con top-k controlado |
| La indexación incremental no se utilizaba | Ingesta, eliminación y definición usan upsert/delete selectivo | Pruebas del flujo persistente |
| Un fallo de Pydantic activaba una llamada sin validar | El fallback solo existe para clientes que carecen del método validado | Prueba de fallo sin bypass |
| Los reintentos duplicaban latencia y tokens | Acumulación única por intento y telemetría aislada por contexto | Prueba exacta de dos intentos |
| Un cambio de modelo podía mezclar dimensiones vectoriales | Colección versionada por modelo y prefijos | Nombre de colección determinista |
| Esquemas débiles y revisión no validada | Prioridades/estados estrictos, citas y relaciones controladas, HU con criterios | Esquemas Pydantic y pruebas de flujo |
| La configuración se perdía al cambiar `.env` | Instantánea completa persistida en cada ejecución | Vista “Ejecución” y exportación |
| Los umbrales parecían valores universales | Son configurables y se presentan como heurísticos | Reporte incluye los umbrales usados |
| El frontend no mostraba los nuevos datos | Se añadieron relaciones, alertas por artefacto y ejecución | Compilación de producción Angular |

---

## 1. Desacoplamiento del Proveedor LLM y Salidas Estructuradas con Reintentos

### ¿Qué se hizo?
- Se reemplazó la dependencia rígida de DeepSeek por un protocolo genérico `LLMClient` y un cliente unificado `OpenAICompatibleClient` (`src/reqlab/llm.py`).
- Se introdujo `complete_json_validated()` utilizando esquemas **Pydantic** (`src/reqlab/llm_schemas.py`) con un bucle de reintentos configurable (`LLM_MAX_RETRIES`).
- Se preservó el alias retrocompatible `DeepSeekClient = OpenAICompatibleClient`.

### ¿Por qué?
1. **Flexibilidad de proveedor:** El cliente funciona con servicios que implementen Chat Completions, autenticación Bearer y salida JSON de forma compatible. DeepSeek es el proveedor validado; Azure OpenAI, Ollama u otros servicios pueden requerir adaptadores específicos.
2. **Robustez y Tolerancia a Fallos:** Los LLMs ocasionalmente devuelven JSON con claves faltantes o tipos incorrectos. Con Pydantic y reintentos guiados por el error exacto, el agente corrige automáticamente su respuesta si el primer intento no cumple el contrato.

---

## 2. Modelo de Embeddings Especializado y Prefijos Asimétricos

### ¿Qué se hizo?
- En `src/reqlab/settings.py` y `src/reqlab/vector_store.py`, el modelo de embeddings ahora es completamente configurable vía `EMBEDDING_MODEL`.
- Se introdujo soporte nativo para **prefijos de consulta y pasaje** (`EMBEDDING_QUERY_PREFIX` y `EMBEDDING_PASSAGE_PREFIX`), con auto-detección para la familia de modelos **E5** (`query: ` y `passage: `).
- Se implementó la factoría `ChromaProjectVectorStore.from_settings()`.

### ¿Por qué?
1. **Capacidad de experimentación:** El modelo base es rápido; modelos como `intfloat/multilingual-e5-base` o `BAAI/bge-m3` son alternativas multilingües cuya calidad deberá compararse con el corpus y las métricas del experimento.
2. **Requisitos de Embeddings Modernos:** Modelos como E5 requieren explícitamente diferenciar si el vector corresponde a una consulta de búsqueda o a un pasaje documental para calcular similitudes de coseno precisas.

---

## 3. Reranker Post-RRF con Cross-Encoder (Opcional)

### ¿Qué se hizo?
- Se creó la clase `CrossEncoderReranker` en `src/reqlab/vector_store.py`.
- Se integró de manera opcional en el servicio de aplicación, activable mediante `RERANKER_ENABLED=True`. La configuración de ejemplo utiliza un modelo mMARCO multilingüe apto para español.

### ¿Por qué?
1. **Arquitectura RAG en Dos Etapas (Retrieve & Rerank):**
   - **Etapa 1 (Bi-Encoder / RRF):** Recupera rápidamente un conjunto amplio de candidatos (ej. 24 a 48 fragmentos) maximizando el *recall* (exhaustividad).
   - **Etapa 2 (Cross-Encoder):** Evalúa la relevancia profunda consulta-fragmento mediante atención cruzada completa, maximizando la *precisión*.
2. **Valor Metodológico para la Tesis:** Permite realizar experimentos formales comparando el desempeño del RAG con y sin etapa de reranking.

---

## 4. Indexación Vectorial Incremental

### ¿Qué se hizo?
- Se crearon los métodos `upsert_fragments()` y `delete_fragments()` en `ChromaProjectVectorStore`.
- La ingesta, eliminación y confirmación de la definición utilizan las operaciones incrementales. Una reconstrucción completa queda disponible para mantenimiento explícito.
- El índice se versiona por modelo y prefijos de embeddings, evitando mezclar vectores de dimensiones incompatibles.

### ¿Por qué?
1. **Eficiencia en Ingesta:** Anteriormente, ante cualquier cambio o agregado de una fuente, se eliminaba toda la colección de ChromaDB y se re-computaban los embeddings de todo el proyecto.
2. **Escalabilidad:** Ahora es posible actualizar o dar de baja fragmentos de una fuente específica sin penalizar el rendimiento ni recalcular fragmentos no afectados.

---

## 5. Segmentación Estructural Contextual por Tipo de Fuente

### ¿Qué se hizo?
- En `src/reqlab/documents.py`, `TextSegmentationService` pasó de una división genérica ciega por longitud a una segmentación que respeta la estructura según el `source_kind`:
  - `email`: Segmentación guiada por encabezados de correos (`De:`, `Para:`, `Asunto:`).
  - `interview`: Segmentación por turnos de diálogo (`Entrevistador:`, `Pregunta:`, `Respuesta:`).
  - `conversation`: Segmentación por cambios de interlocutor (`Usuario:`, `Agente:`).
  - `meeting_notes` / `note`: Segmentación por encabezados Markdown (`#`, `##`, `###`).
  - `document`: Párrafos con solapamiento configurable (`CHUNK_SIZE`, `CHUNK_OVERLAP`).
- Se mejoró la extracción automática de títulos (`heading`) representativos para cada fragmento.

### ¿Por qué?
1. **Integridad Semántica de la Evidencia:** Trocear un correo o una entrevista en un número fijo de caracteres deja preguntas sin sus respuestas o divide frases normativas clave.
2. **Mejores Citas:** Las citas en los artefactos generados ahora apuntan a bloques con coherencia temática natural.

---

## 6. Consultas RAG Especializadas por Tipo de Agente

### ¿Qué se hizo?
- Se añadió el campo `retrieval_query` en `AgentContract` (`src/reqlab/agents.py`), poblando un vocabulario denso y discriminativo para cada rol:
  - **RF:** *capacidades funcionales, procesos, acciones, comportamientos observables, permitir, registrar, consultar, modificar, gestionar.*
  - **RNF:** *rendimiento, tiempo de respuesta, disponibilidad, seguridad, autenticación, cifrado, retención de datos, usabilidad, normativa.*
  - **HU:** *actor, usuario, rol, administrador, cliente, necesidad, beneficio, escenario, interacción, valor.*

### ¿Por qué?
- Anteriormente todos los agentes consultaban al RAG casi con la misma frase genérica (`{proyecto} {dominio} {tarea}`). La especialización busca favorecer evidencia pertinente para cada tipo, pero su efecto debe comprobarse mediante evaluación; el vocabulario se registra como parámetro experimental y no como garantía de mejora.

---

## 7. Coherencia Inter-Agente en Tiempo de Generación

### ¿Qué se hizo?
- En `src/reqlab/agents.py`, `SpecializedGenerationAgent.generate()` ahora acepta `existing_artifacts: list[Artifact]`.
- En `src/reqlab/services.py`, al iterar por el pipeline secuencial (`RF` $\rightarrow$ `RNF` $\rightarrow$ `HU`), se inyectan los artefactos ya consolidados como contexto en el prompt del siguiente agente:
  - El agente **HU** recibe los RFs para alinear cada historia con las capacidades del sistema, enfocándose en el rol y beneficio sin duplicar la redacción funcional.
  - El agente **RNF** recibe los RFs para formular restricciones y atributos de calidad medibles que apliquen a esas capacidades.

### ¿Por qué?
- Reduce el aislamiento entre agentes y proporciona contexto explícito para revisar coherencia. No garantiza ausencia de contradicciones: la validación automática y el juicio experto siguen siendo necesarios.
- Los artefactos generados se distinguen de la evidencia documental y se enlazan mediante `related_artifacts`; nunca se aceptan como citas de fuente.

---

## 8. Validación Cruzada de Duplicados entre Tipos Distintos (Cross-Type)

### ¿Qué se hizo?
- En `src/reqlab/validation.py`, se ajustó `_duplicates()` para evaluar únicamente artefactos del **mismo tipo** (umbral Jaccard $\ge 0.72$).
- Se añadió `_cross_type_duplicates()` para detectar superposiciones léxicas entre **tipos distintos** (ej. un RF idéntico a una HU) con un umbral más sensible ($\ge 0.55$).
- El reporte de validación incluye ahora `cross_type_duplicates` detallando `left_type`, `right_type`, índice de similitud y motivo.

### ¿Por qué?
- Una similitud alta es una alerta heurística, no una decisión automática. Los umbrales son configurables y deben calibrarse con el caso de evaluación; la métrica únicamente asiste al analista humano.

---

## 9. Observabilidad y Telemetría de Runs (Latencia, Tokens y Reintentos)

### ¿Qué se hizo?
- **Medición Precisa en `llm.py`:**
  - Registro de `latency_ms` utilizando `time.perf_counter()`.
  - Extracción de tokens consumidos (`prompt_tokens`, `completion_tokens`, `total_tokens`) del campo estándar `usage` del API del proveedor.
  - Contador de `attempts` realizados en caso de reintentos por validación de esquema.
- **Persistencia Transparente en `storage.py`:**
  - `finish_run()` ahora recibe opcionalmente `metrics: dict` y los almacena dentro del JSON `parameters_json` existente en la base de datos SQLite.
- **Agregación en `services.py`:**
  - Cada agente guarda sus métricas en su child run.
  - El run orquestador principal consolida `total_latency_ms`, `total_tokens` y `total_attempts`.

### ¿Por qué?
1. **Auditoría y Costos:** Permite conocer con precisión el tiempo y consumo de tokens de cada fase del laboratorio.
2. **Material Experimental para la Tesis:** Permite tabular tiempos medios de inferencia, costo en tokens por tipo de requisito y tasa de éxito en primer intento frente a distintos modelos (ej. DeepSeek vs GPT-4o-mini vs Llama 3).

---

## 10. Configuración Centralizada de Experimentos

### ¿Qué se hizo?
- Se documentaron e implementaron las nuevas variables en `config.example.env` y `src/reqlab/settings.py`:
  - `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_MAX_RETRIES`
  - `EMBEDDING_MODEL`, `EMBEDDING_QUERY_PREFIX`, `EMBEDDING_PASSAGE_PREFIX`
  - `RERANKER_ENABLED`, `RERANKER_MODEL`
  - `RRF_LEXICAL_WEIGHT`, `RRF_SEMANTIC_WEIGHT`, `RETRIEVAL_TOP_K`
  - `CHUNK_SIZE`, `CHUNK_OVERLAP`
  - `DUPLICATE_THRESHOLD`, `CROSS_TYPE_DUPLICATE_THRESHOLD`, `PROMPT_VERSION`

### ¿Por qué?
- Cada ejecución guarda una instantánea del modelo, embeddings, reranker, RRF, segmentación, umbrales y versión de prompts. Esto permite interpretar y repetir una ejecución aunque el `.env` cambie después.

---

## Compatibilidad con el Frontend Angular

| Endpoint / Contrato | ¿Hubo cambios que rompan Angular? | Observación |
|---|---|---|
| `POST /api/projects/{id}/generation` | **No** | Mismo payload de inicio y respuesta `202 Accepted`. |
| `GET /api/runs/{run_id}` | **No** | `parameters` mantiene `progress`, `message`, `step` y agrega configuración y métricas. |
| `GET /api/projects/{id}/runs/latest` | Nuevo | Recupera la última ejecución principal para la vista de reproducibilidad. |
| `GET /api/projects/{id}/artifacts` | **No** | Agrega `related_artifacts` y `validation`; conserva todos los campos previos. |
| `GET /api/projects/{id}/validation` | **No** | Agrega relaciones inválidas, duplicados cruzados, umbrales y evaluación por artefacto. |
| `POST /api/projects/{id}/sources` | **No** | Mismo contrato de subida y procesamiento. |

Angular muestra ahora la procedencia documental, las relaciones RF–RNF–HU, las observaciones por artefacto y una síntesis de la configuración de la ejecución. Se conservaron la composición visual, los componentes y los estilos base de ReqLab.
