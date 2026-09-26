# Arquitectura implementada y flujo del prototipo web

## Propósito

El prototipo analiza fuentes textuales de cualquier dominio y genera RF, RNF e historias de usuario con trazabilidad. La aplicación no implementa el sistema descrito por las fuentes; implementa el proceso de ingeniería de requisitos asistido por agentes. La interfaz no precarga casos ni corpus de demostración.

## Vista por capas

```text
Interfaz Angular
  ├── proyectos y fuentes
  ├── definición guiada
  ├── generación y progreso
  ├── revisión y versiones
  └── exportación
            │ HTTP / JSON
API FastAPI
  ├── validación de solicitudes y archivos
  ├── rutas de proyectos, fuentes y definición
  ├── ejecución y consulta de progreso
  ├── rutas de revisión, versiones y exportación
  └── composición de casos de uso
            │
Servicio de aplicación / orquestador
  ├── extracción y segmentación
  ├── agente de definición
  ├── recuperación híbrida RAG
  ├── agente RF
  ├── agente RNF
  ├── agente HU
  ├── validación de trazabilidad y consistencia
  └── agente de revisión
            │
Persistencia
  ├── SQLite: estado estructurado y versiones
  ├── ChromaDB: vectores y metadatos de fragmentos
  └── archivos locales: fuentes originales y caché del modelo
```

## Componentes y contratos

| Componente | Entrada | Responsabilidad | Salida |
|---|---|---|---|
| Servicio de extracción | Bytes y nombre de archivo, o texto pegado | Extraer texto de PDF, DOCX, TXT o Markdown, aceptar correos, entrevistas, conversaciones y notas sin una plantilla previa, y rechazar fuentes vacías. | Texto normalizado y huella SHA-256. |
| Servicio de segmentación | Texto y código de fuente | Formar fragmentos solapados con identificadores estables `SRC-###-F###`. | Fragmentos trazables. |
| Índice vectorial | Fragmentos y metadatos de proyecto | Calcular embeddings locales y persistirlos en ChromaDB. | Colección vectorial filtrable por proyecto. |
| Agente recuperador híbrido | Consulta del agente | Fusionar ranking TF-IDF y vectorial con Reciprocal Rank Fusion. | Evidencia contextual ordenada. |
| Agente de definición | Todos los fragmentos de las fuentes del proyecto | Analizar el corpus completo por lotes, consolidar hallazgos y contradicciones, construir una interpretación provisional y preguntar solo por información ausente, dudosa o decisiva. | Perfil provisional trazable, cobertura del análisis y preguntas adaptativas. |
| Agente RF | Evidencia recuperada | Generar capacidades observables con patrones EARS, sin atributos de calidad ni diseño inventado. | RF citados y con criterio de verificación. |
| Agente RNF | Evidencia recuperada | Generar atributos/restricciones verificables sin inventar métricas ni umbrales. | RNF citados con categoría y campos de medición explícitos o pendientes. |
| Agente HU | Evidencia recuperada | Generar historias con rol, objetivo, beneficio y criterios de aceptación. | HU estructuradas y citadas. |
| Validador determinista | Artefactos y catálogo de fragmentos | Detectar citas ausentes/inválidas, formato EARS y HU, criterios faltantes, RNF incompletos, prioridades sin procedencia y posibles duplicados. | Reporte de alertas reproducible. |
| Agente de revisión | Artefacto, solicitud del usuario y evidencia | Proponer una edición sin sobrescribir la versión vigente. | Propuesta aceptable o descartable. |
| Exportador | Perfil, artefactos, fragmentos y validación | Construir fichas por tipo y matriz artefacto--fragmento, además de la salida estructurada. | DOCX y JSON. |

## Estado del proyecto

```text
created
   ↓
sources_ready
   ↓
definition
   ↓
ready_to_generate
   ↓
generating
   ↓
review
   ↓
exported
```

La confirmación de la interpretación provisional es una condición de entrada de la generación. Los ocho campos de definición no son un cuestionario obligatorio: ReqLab intenta completarlos desde el corpus, permite corregirlos y exige respuesta solamente para las preguntas adaptativas pendientes. Toda modificación posterior de una fuente o respuesta invalida la confirmación anterior.

## Interpretación completa del corpus

El agente de definición no selecciona únicamente los primeros fragmentos. Divide la totalidad del corpus en lotes limitados por tamaño, extrae hallazgos con citas en cada lote y consolida esos resúmenes de manera jerárquica antes de construir el perfil. La respuesta registra `fragment_count` y `batch_count`, lo que permite comprobar la cobertura del análisis sin exceder la ventana de contexto del LLM.

## Trazabilidad de las aclaraciones

Las preguntas y respuestas confirmadas se convierten en fragmentos `USR-DEF-001`, `USR-DEF-002`, etc. Estos fragmentos se indexan junto con las fuentes documentales, pero conservan `origin: user_definition` en sus metadatos. Así se diferencia la procedencia documental de la decisión aportada por el usuario.

## Recuperación aumentada

1. El agente formula una consulta específica para su responsabilidad.
2. TF-IDF recupera coincidencias léxicas.
3. ChromaDB recupera similitud semántica mediante embeddings multilingües.
4. Reciprocal Rank Fusion combina ambos rankings.
5. El agente recibe texto, identificador y encabezado de cada fragmento.
6. El contrato exige citar identificadores exactos en la salida JSON.

Esta separación permite registrar el método de recuperación y revisar qué evidencia recibió cada agente.

## Persistencia y versionado

SQLite contiene tablas independientes para proyectos, fuentes, fragmentos, preguntas, perfiles, ejecuciones, artefactos, versiones y reportes de validación. Los índices responden a las consultas reales por proyecto, fase y tipo de artefacto.

Cada modificación crea una fila inmutable en `artifact_versions`. La edición asistida produce primero una propuesta; solamente la aceptación del usuario crea la versión siguiente.

## Límites de la implementación

- El sistema está delimitado a texto digital y no incorpora OCR ni transcripción de audio.
- Los agentes utilizan un mismo LLM con contratos distintos; la especialización no depende de modelos diferentes.
- La evaluación experta conserva la decisión final sobre calidad y utilidad.
- ChromaDB y SQLite se ejecutan localmente, sin servicios de infraestructura externos.
