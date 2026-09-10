# ReqLab: Reporte Consolidado de Mejoras RAG y Arquitectura Multi-Agente

Este documento detalla **todas las mejoras implementadas** en la rama `feature/rag-and-agent-improvements`, explicando **qué** se hizo, **cómo** se implementó y **por qué** (justificación técnica y académica para la tesis), garantizando la compatibilidad total con el frontend Angular existente.

---

## 1. Desacoplamiento del Proveedor LLM y Salidas Estructuradas con Reintentos

### ¿Qué se hizo?
- Se reemplazó la dependencia rígida de DeepSeek por un protocolo genérico `LLMClient` y un cliente unificado `OpenAICompatibleClient` (`src/reqlab/llm.py`).
- Se introdujo `complete_json_validated()` utilizando esquemas **Pydantic** (`src/reqlab/llm_schemas.py`) con un bucle de reintentos configurable (`LLM_MAX_RETRIES`).
- Se preservó el alias retrocompatible `DeepSeekClient = OpenAICompatibleClient`.

### ¿Por qué?
1. **Flexibilidad de Proveedor:** Permite utilizar cualquier proveedor compatible con OpenAI Chat Completions (Groq, Together, OpenRouter, Azure OpenAI, Ollama local o DeepSeek) simplemente cambiando variables de entorno en el `.env`, sin modificar una sola línea de código Python.
2. **Robustez y Tolerancia a Fallos:** Los LLMs ocasionalmente devuelven JSON con claves faltantes o tipos incorrectos. Con Pydantic y reintentos guiados por el error exacto, el agente corrige automáticamente su respuesta si el primer intento no cumple el contrato.

---

## 2. Modelo de Embeddings Especializado y Prefijos Asimétricos

### ¿Qué se hizo?
- En `src/reqlab/settings.py` y `src/reqlab/vector_store.py`, el modelo de embeddings ahora es completamente configurable vía `EMBEDDING_MODEL`.
- Se introdujo soporte nativo para **prefijos de consulta y pasaje** (`EMBEDDING_QUERY_PREFIX` y `EMBEDDING_PASSAGE_PREFIX`), con auto-detección para la familia de modelos **E5** (`query: ` y `passage: `).
- Se implementó la factoría `ChromaProjectVectorStore.from_settings()`.

### ¿Por qué?
1. **Calidad de Recuperación:** El modelo base anterior (`MiniLM`) es rápido pero limitado en español técnico. Modelos como `intfloat/multilingual-e5-base` o `BAAI/bge-m3` ofrecen un *retrieval* semántico superior para requisitos de software.
2. **Requisitos de Embeddings Modernos:** Modelos como E5 requieren explícitamente diferenciar si el vector corresponde a una consulta de búsqueda o a un pasaje documental para calcular similitudes de coseno precisas.

---

## 3. Reranker Post-RRF con Cross-Encoder (Opcional)

### ¿Qué se hizo?
- Se creó la clase `CrossEncoderReranker` en `src/reqlab/vector_store.py`.
- Se integró de manera opcional en `HybridRetrievalAgent`, activable mediante las variables `RERANKER_ENABLED=True` y `RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2`.

### ¿Por qué?
1. **Arquitectura RAG en Dos Etapas (Retrieve & Rerank):**
   - **Etapa 1 (Bi-Encoder / RRF):** Recupera rápidamente un conjunto amplio de candidatos (ej. 24 a 48 fragmentos) maximizando el *recall* (exhaustividad).
   - **Etapa 2 (Cross-Encoder):** Evalúa la relevancia profunda consulta-fragmento mediante atención cruzada completa, maximizando la *precisión*.
2. **Valor Metodológico para la Tesis:** Permite realizar experimentos formales comparando el desempeño del RAG con y sin etapa de reranking.

---

## 4. Indexación Vectorial Incremental

### ¿Qué se hizo?
- Se crearon los métodos `upsert_fragments()` y `delete_fragments()` en `ChromaProjectVectorStore`.
- Se añadió el flag `full_rebuild: bool = True` al método `index()`.

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
- Anteriormente todos los agentes consultaban al RAG casi con la misma frase genérica (`{proyecto} {dominio} {tarea}`). Al especializar la consulta léxica y semántica, el agente de RNF recupera fragmentos de seguridad y desempeño, mientras que el agente de HU recupera interacciones y actores humanos.

---

## 7. Coherencia Inter-Agente en Tiempo de Generación

### ¿Qué se hizo?
- En `src/reqlab/agents.py`, `SpecializedGenerationAgent.generate()` ahora acepta `existing_artifacts: list[Artifact]`.
- En `src/reqlab/services.py`, al iterar por el pipeline secuencial (`RF` $\rightarrow$ `RNF` $\rightarrow$ `HU`), se inyectan los artefactos ya consolidados como contexto en el prompt del siguiente agente:
  - El agente **HU** recibe los RFs para alinear cada historia con las capacidades del sistema, enfocándose en el rol y beneficio sin duplicar la redacción funcional.
  - El agente **RNF** recibe los RFs para formular restricciones y atributos de calidad medibles que apliquen a esas capacidades.

### ¿Por qué?
- Evita que los agentes trabajen como "islas". Resuelve de raíz las contradicciones entre lo que promete una Historia de Usuario y lo que estipula un Requisito Funcional, elevando la calidad del conjunto de requisitos.

---

## 8. Validación Cruzada de Duplicados entre Tipos Distintos (Cross-Type)

### ¿Qué se hizo?
- En `src/reqlab/validation.py`, se ajustó `_duplicates()` para evaluar únicamente artefactos del **mismo tipo** (umbral Jaccard $\ge 0.72$).
- Se añadió `_cross_type_duplicates()` para detectar superposiciones léxicas entre **tipos distintos** (ej. un RF idéntico a una HU) con un umbral más sensible ($\ge 0.55$).
- El reporte de validación incluye ahora `cross_type_duplicates` detallando `left_type`, `right_type`, índice de similitud y motivo.

### ¿Por qué?
- Mientras que dos RF idénticos representan un error claro de duplicación, una similitud alta entre un RF y una HU suele indicar una redacción redundante donde la historia de usuario no aportó perspectiva de actor ni criterio de aceptación nuevo. Esta métrica asiste al analista humano en la revisión.

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
- Se documentaron e implementaron todas las nuevas variables en `config.example.env` y `src/reqlab/settings.py`:
  - `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_MAX_RETRIES`
  - `EMBEDDING_MODEL`, `EMBEDDING_QUERY_PREFIX`, `EMBEDDING_PASSAGE_PREFIX`
  - `RERANKER_ENABLED`, `RERANKER_MODEL`
  - `RRF_LEXICAL_WEIGHT`, `RRF_SEMANTIC_WEIGHT`, `RETRIEVAL_TOP_K`
  - `CHUNK_SIZE`, `CHUNK_OVERLAP`

### ¿Por qué?
- Facilita la reproducibilidad de experimentos científicos sin necesidad de alterar el código fuente.

---

## Compatibilidad con el Frontend Angular

| Endpoint / Contrato | ¿Hubo cambios que rompan Angular? | Observación |
|---|---|---|
| `POST /api/projects/{id}/generation` | **No** | Mismo payload de inicio y respuesta `202 Accepted`. |
| `GET /api/projects/{id}/runs/{run_id}` | **No** | `parameters` mantiene `progress`, `message`, `step` y agrega `metrics` opcional que TypeScript tolera sin error. |
| `GET /api/projects/{id}/artifacts` | **No** | Estructura de `Artifact` idéntica. |
| `GET /api/projects/{id}/validation` | **No** | Agrega la clave opcional `cross_type_duplicates`. Los campos existentes se mantienen intactos. |
| `POST /api/projects/{id}/sources` | **No** | Mismo contrato de subida y procesamiento. |
