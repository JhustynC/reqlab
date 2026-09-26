# Evaluación inicial de viabilidad de Jev sin revisión humana

> Nota de vigencia: este informe conserva las condiciones de la revisión inicial. La integración posterior ya fue probada con OpenRouter y cuenta con auditoría persistente; la utilidad de Jev frente a expertos continúa pendiente de evaluación.

Fecha de evaluación: 21 de septiembre de 2026.

Rama evaluada: `feature/jev-semantic-validation`.

## Decisión

Jev es técnicamente viable como componente opcional y exploratorio de validación semántica en ReqLab. No es viable, bajo la restricción actual de eliminar toda revisión humana, como fundamento para afirmar que la trazabilidad o la calidad de los requisitos mejoró.

La recomendación para la tesis es mantenerlo fuera del tratamiento principal M0/T1 y, si se conserva, presentarlo como una integración experimental no concluyente. Si el plazo obliga a escoger, la integración puede dejarse implementada y desactivada sin ejecutar el piloto remoto.

## Qué se pudo comprobar sin una respuesta remota de Jev

El código de ReqLab ya cubre el contrato técnico del piloto:

- El cliente usa un endpoint de decisiones configurable; con la clave disponible apunta a `POST /api/alpha/decisions` de OpenRouter y no intenta tratar Jev como Chat Completions.
- La respuesta se valida antes de aceptarse: preguntas completas, opciones exactas, probabilidades válidas y confianza dentro del intervalo esperado.
- Se evalúan por separado el respaldo conjunto del artefacto y la relación de cada fragmento citado.
- Las citas inexistentes se descartan sin llamada remota.
- Un fallo de red, credenciales, límite o contrato no se convierte en una decisión `completo`.
- El modo `shadow` no modifica el texto, estado, aprobación, tipo ni relaciones del artefacto.
- Las huellas de entradas permiten marcar como `stale` un resultado después de una edición.
- Las respuestas exitosas conservan el estado y las preguntas enviadas, la versión del modelo, las probabilidades, la confianza y la telemetría.

En la revisión inicial, las ocho pruebas específicas del módulo y la suite entonces disponible (41 pruebas) pasaban con clientes simulados. La suite actual se reporta en `docs/cierre_estabilizacion.md`. Estas pruebas verifican la integración, no la inteligencia de Jev.

## Evidencia que no existe todavía

En esa revisión, la clave disponible era de OpenRouter. Antes de la corrección, ReqLab todavía apuntaba por defecto a la API directa de TypeSafe, por lo que no era válido usar esa clave con la configuración anterior. La ruta se corrigió para OpenRouter (`/api/alpha/decisions`, modelo `typesafe/jev-1.13`). En aquel entorno la prueba mínima confirmó que la configuración cargaba la clave sin exponerla, pero la conexión saliente fue bloqueada con `WinError 10013`; por ello ese informe inicial no contenía resultados reales sobre el corpus Altavista, español, latencia, costo, tasa de errores o estabilidad entre repeticiones.

Tampoco existe una referencia externa para decidir si una clasificación semántica es correcta. Sustituir a dos expertos por otra respuesta generada por un modelo, incluido este asistente, produciría una comparación circular: serviría como prueba de funcionamiento, pero no como validación independiente.

## Análisis de adecuación al problema

La tarea elegida —determinar si una cita respalda una obligación de un requisito— encaja con `Choice`: el espacio de salida es cerrado y el programa puede procesar las etiquetas. Jev no necesita generar texto, código ni explicaciones para producir esa señal.

El encaje disminuye en estos casos del corpus:

- contradicciones entre varias fuentes;
- negaciones, excepciones y condiciones encadenadas;
- reglas pendientes que solo quedan resueltas por una decisión de usuario;
- requisitos en español con referencias ambiguas;
- RNF que contienen cifras, plazos o umbrales;
- evidencia extensa con detalles irrelevantes.

La documentación oficial indica que el idioma principal de entrenamiento es el inglés, que las entradas en otros idiomas deben probarse, y que Jev es literal, tiene dificultades con números, indirección, contexto irrelevante e instrucciones adversarias. [Modelos](https://docs.typesafe.ai/models) y [limitaciones de Jev 1.13](https://docs.typesafe.ai/model-jaggedness/jev-1.13).

## Valor práctico bajo la restricción de no usar humanos

Hay tres usos posibles:

| Uso | Viabilidad | Juicio |
|---|---:|---|
| Señal auxiliar para ordenar artefactos que conviene inspeccionar | Alta | Puede funcionar aunque no se conozca todavía su exactitud; no debe aprobar automáticamente. |
| Filtro automático que impide aprobar un requisito | Baja | Un falso positivo puede bloquear salidas válidas y un falso negativo puede ocultar una traza defectuosa. |
| Evidencia experimental de mejora frente a M0/T1 | Baja | Sin etiquetas independientes no se puede medir precisión, recall ni reducción real de errores. |

La confianza de Jev tampoco resuelve el problema: TypeSafe la define como una medida derivada de su distribución y advierte que la calibración describe grupos de predicciones, no garantiza que una predicción individual sea correcta. [Confidence](https://docs.typesafe.ai/confidence).

## Veredicto para la tesis

La integración es defendible como decisión de diseño y prototipo opcional. No es defendible como resultado de evaluación de calidad si solo se ejecuta y se acepta su propia salida.

Con el plazo actual, la opción metodológicamente más segura es:

1. mantener el módulo en modo `shadow` y desactivado por defecto;
2. no incorporarlo a los resultados comparativos principales;
3. describirlo como extensión exploratoria o trabajo futuro;
4. no reportar exactitud, mejora, reducción de errores ni superioridad;
5. si se habilita la salida de red, hacer únicamente una prueba técnica pequeña y reportar sus salidas como observaciones no validadas.

Una prueba con casos obvios y etiquetas escritas por nosotros puede servir para detectar fallos groseros de integración, pero no cambia este veredicto: sería un smoke test, no una evaluación científica de Jev.

## Trabajo que puede omitirse ahora

Bajo esta decisión se pueden aplazar sin riesgo para la tesis:

- conjunto de 80–120 casos;
- doble anotación y adjudicación;
- métricas de precisión, recall, F1, Brier y acuerdo interevaluador;
- botón y vista Angular para ejecutar el piloto;
- integración automática después de cada generación;
- optimización de concurrencia y presupuesto remoto.

La implementación actual queda preparada para retomarlos si cambia el plazo o aparece disponibilidad de evaluadores.
