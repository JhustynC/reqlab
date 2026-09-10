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
Generar RF, RNF y HU mediante agentes especializados
      ↓
Validar trazabilidad, formato y posibles duplicados
      ↓
Revisar manualmente o solicitar una propuesta de edición
      ↓
Exportar DOCX o JSON
```

El agente de definición recorre todos los fragmentos del proyecto mediante análisis jerárquico por lotes. Primero obtiene hallazgos trazables, después construye un perfil provisional editable y formula preguntas únicamente para información ausente o dudosa, contradicciones y decisiones relevantes. Las respuestas confirmadas se almacenan como fragmentos `USR-DEF-*`, por lo que pueden citarse como evidencia sin confundirse con las fuentes originales.

## Persistencia

| Medio | Responsabilidad |
|---|---|
| SQLite | Proyectos, metadatos de fuentes, preguntas, respuestas, artefactos, versiones, ejecuciones y validaciones. |
| ChromaDB | Embeddings y búsqueda semántica de fragmentos, aislados por proyecto. |
| Sistema de archivos | Documentos originales, caché del modelo de embeddings y exportaciones descargadas por el usuario. |

La recuperación es híbrida: combina TF-IDF y similitud vectorial mediante Reciprocal Rank Fusion. Los embeddings se calculan localmente con un modelo multilingüe de `sentence-transformers`; DeepSeek se utiliza para interpretar el corpus, generar preguntas adaptativas y artefactos, y proponer revisiones.

## Ejecución con Docker

Requisitos:

- Docker Desktop en ejecución.
- Un archivo `.env` basado en `config.example.env`.
- Una clave válida en `DEEPSEEK_API_KEY`.

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

Las pruebas del núcleo y del flujo web no consumen la API:

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
- `services.py`: casos de uso y orquestación del flujo.
- `validation.py`: controles deterministas de trazabilidad y consistencia.
- `exporters.py`: exportación a Word.

## Límites actuales del MVP

- Ejecución local y de un solo usuario; no incluye autenticación.
- Los PDF deben contener texto seleccionable; no se ha incorporado OCR.
- Las entrevistas deben estar transcritas.
- La validación automática produce alertas y no sustituye la evaluación de expertos.
- No compara modelos ni variantes arquitectónicas; implementa la arquitectura definida para la tesis.
