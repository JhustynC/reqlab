# Arquitectura Multi-Agente de ReqLab (Tesis)

Este documento describe formalmente la arquitectura multi-agente especializada con recuperación aumentada por generación (RAG Híbrido) implementada en **ReqLab**.

---

## 1. Diagrama General de la Arquitectura

```mermaid
flowchart TD
    %% Subgraphs
    subgraph UI["Capa de Presentación (Frontend Angular)"]
        UI_App["SPA Angular (OnPush, Signals)"]
        UI_Views["Vistas: Proyectos | Fuentes | Ficha Definición | Artefactos | Validación"]
    end

    subgraph API["Capa de Servicios y Orquestación (FastAPI)"]
        Router["Endpoints REST (/api)"]
        Service["ProjectApplicationService (Casos de Uso)"]
    end

    subgraph AGENTS["Ecosistema Multi-Agente Especializado"]
        subgraph Elicit["Fase de Elicitación y Aclaración"]
            Ag_Def["ProjectDefinitionAgent<br/><i>(Análisis Map-Reduce por lotes + Síntesis)</i>"]
        end

        subgraph Gen["Fase de Generación Secuencial y Coherente"]
            Ag_RF["SpecializedGenerationAgent (RF)<br/><i>Analista de Requisitos Funcionales</i>"]
            Ag_RNF["SpecializedGenerationAgent (RNF)<br/><i>Analista de Calidad y Restricciones</i>"]
            Ag_HU["SpecializedGenerationAgent (HU)<br/><i>Analista de Historias de Usuario</i>"]
        end

        subgraph Eval["Fase de Control de Calidad y Evolución"]
            Ag_Val["TraceabilityConsistencyAgent<br/><i>(Validación Determinista + Duplicados Cross-Type)</i>"]
            Ag_Rev["RevisionAgent<br/><i>(Propuestas asistidas de edición)</i>"]
        end
    end

    subgraph RAG["Subsistema RAG Híbrido Avanzado"]
        Chunker["TextSegmentationService<br/><i>(Segmentación estructural por tipo de fuente)</i>"]
        Lexical["TfidfRetrievalAgent<br/><i>(Recuperación Léxica)</i>"]
        Vector["ChromaProjectVectorStore<br/><i>(Embeddings Multilingües E5/MiniLM)</i>"]
        RRF["Reciprocal Rank Fusion (RRF)<br/><i>(Fusión ponderada léxico-semántica)</i>"]
        Reranker["CrossEncoderReranker<br/><i>(Reordenamiento de candidatos opcional)</i>"]
    end

    subgraph LLM_LAYER["Capa de Inferencia LLM (Desacoplada)"]
        LLM_Proto["LLMClient (Protocol)"]
        LLM_Client["OpenAICompatibleClient<br/><i>(DeepSeek, Groq, Ollama, OpenAI)</i>"]
        Pydantic["Validación de Esquema Pydantic + Reintentos"]
        Telemetry["Telemetría: Latencia (ms), Tokens (usage), Intentos"]
    end

    subgraph STORAGE["Capa de Persistencia Aislada por Proyecto"]
        DB[(SQLite: Metadatos, Artefactos, Versiones, Runs con Métricas)]
        Chroma[(ChromaDB: Colecciones vectoriales de fragmentos)]
        FS[("Sistema de Archivos: data/projects/")]
    end

    %% Relaciones
    UI_App -->|HTTP / JSON| Router
    Router --> Service
    Service --> Chunker
    Chunker -->|Fragmentos estructurados| DB
    Chunker -->|Indexación incremental| Vector

    %% Flujo de Definición
    Service --> Ag_Def
    Ag_Def -->|Prompt y Síntesis| LLM_Proto

    %% Flujo RAG hacia Agentes de Generación
    Service --> Ag_RF
    Service --> Ag_RNF
    Service --> Ag_HU

    Ag_RF -.->|1. Query especializada RF| RAG
    Ag_RNF -.->|2. Query especializada RNF| RAG
    Ag_HU -.->|3. Query especializada HU| RAG

    Lexical & Vector --> RRF
    RRF --> Reranker
    Reranker -->|Evidencia citada| Ag_RF & Ag_RNF & Ag_HU

    %% Coherencia Inter-Agente
    Ag_RF -->|Inyección de contexto RFs| Ag_RNF
    Ag_RF -->|Inyección de contexto RFs| Ag_HU

    %% Inferencia LLM
    Ag_RF & Ag_RNF & Ag_HU & Ag_Rev --> LLM_Proto
    LLM_Proto --> LLM_Client
    LLM_Client --> Pydantic
    LLM_Client --> Telemetry
    Telemetry -.->|Registro de métricas| DB

    %% Validación
    Ag_RF & Ag_RNF & Ag_HU -->|Artefactos generados| Ag_Val
    Ag_Val -->|Reporte de consistencia y duplicados| DB
    Ag_Val --> Service
    Service --> Ag_Rev
```

---

## 2. Descripción de los Roles y Agentes

| Agente | Responsabilidad Principal | Estrategia / Técnica |
|---|---|---|
| **`ProjectDefinitionAgent`** | Elicitación y detección de incertidumbres iniciales. | **Map-Reduce:** Analiza los fragmentos en lotes de hasta 18.000 caracteres extrayendo hallazgos en 8 dimensiones clave (objetivo, actores, alcance, etc.) y sintetiza un perfil provisional con preguntas adaptativas. |
| **`SpecializedGenerationAgent (RF)`** | Identificar capacidades y comportamientos observables del sistema. | Recuperación RAG orientada a verbos y procesos operativos (`permitir`, `registrar`, `consultar`, `gestionar`). Generación estructurada con citas exactas a fragmentos. |
| **`SpecializedGenerationAgent (RNF)`** | Identificar atributos de calidad, rendimiento y restricciones medibles. | Recuperación RAG orientada a seguridad, latencia, disponibilidad y normativas. Recibe los **RF previos** como contexto para asociar calidad a capacidades reales. |
| **`SpecializedGenerationAgent (HU)`** | Modelar las necesidades y valor desde la perspectiva de los actores. | Recuperación RAG orientada a roles y beneficios. Recibe los **RF previos** para alinear las historias a las capacidades del sistema sin duplicar su redacción técnica. |
| **`TraceabilityConsistencyAgent`** | Auditoría y control de calidad determinista (sin consumo de LLM). | Verificación de citas válidas, sintaxis obligatoria de HU (*Como / Quiero / Para*), reglas heurísticas de taxonomía y **detección de duplicados internos y cross-type** mediante similitud Jaccard. |
| **`RevisionAgent`** | Proponer ediciones iterativas sobre artefactos existentes. | Recupera evidencia relevante según la instrucción del usuario y formula una propuesta sin sobreescribir la versión vigente en SQLite. |

---

## 3. Flujo Metodológico de Datos

```mermaid
sequenceDiagram
    autonumber
    actor Usuario
    participant UI as Frontend Angular
    participant Service as Orquestador (services.py)
    participant RAG as Subsistema RAG Híbrido
    participant Ag_RF as Agente RF
    participant Ag_RNF as Agente RNF
    participant Ag_HU as Agente HU
    participant Val as Agente de Validación
    participant DB as SQLite / ChromaDB

    Note over Usuario, DB: Fase 1: Ingesta y Segmentación Contextual
    Usuario->>UI: Carga de documentos (PDF, DOCX, TXT, MD)
    UI->>Service: POST /sources
    Service->>RAG: Segmentar según tipo (email, entrevista, markdown)
    RAG->>DB: Guardar fragmentos e indexar embeddings

    Note over Usuario, DB: Fase 2: Elicitación y Ficha de Definición
    Usuario->>UI: Solicitar análisis de definición
    UI->>Service: POST /definition/analyze
    Service->>DB: Guardar perfil provisional y preguntas
    Usuario->>UI: Responde preguntas y confirma ficha
    UI->>Service: POST /definition/confirm

    Note over Usuario, DB: Fase 3: Generación Secuencial y Coherente
    Usuario->>UI: Iniciar Generación de Requisitos
    UI->>Service: POST /generation (asíncrono)
    
    Service->>Ag_RF: 1. Ejecutar Agente RF
    Ag_RF->>RAG: Query especializada en capacidades funcionales
    RAG-->>Ag_RF: Evidencia recuperada
    Ag_RF-->>Service: RF-001...RF-n + Métricas (latencia, tokens)

    Service->>Ag_RNF: 2. Ejecutar Agente RNF (Contexto: Evidencia + RFs)
    Ag_RNF->>RAG: Query especializada en calidad y restricciones
    RAG-->>Ag_RNF: Evidencia recuperada
    Ag_RNF-->>Service: RNF-001...RNF-n + Métricas

    Service->>Ag_HU: 3. Ejecutar Agente HU (Contexto: Evidencia + RFs)
    Ag_HU->>RAG: Query especializada en actores y valor
    RAG-->>Ag_HU: Evidencia recuperada
    Ag_HU-->>Service: HU-001...HU-n + Métricas

    Note over Usuario, DB: Fase 4: Validación y Control de Calidad
    Service->>Val: Evaluar trazabilidad y duplicados cross-type
    Val-->>Service: Reporte de validación
    Service->>DB: Persistir artefactos, reporte y telemetría de runs
    Service-->>UI: Estado: Listo para revisión (Polling /runs/{id})
```
