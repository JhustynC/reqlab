# Cierre de estabilización previo a la evaluación

Este documento registra las cuatro condiciones técnicas que deben cumplirse antes de congelar ReqLab para el experimento de tesis.

## 1. Reanudación y tolerancia a fallos

- Definición: cada lote analizado se guarda con una huella de su contenido. Un nuevo intento reutiliza los lotes coincidentes y repite solamente lo pendiente, incluida la síntesis final.
- Generación: cada agente terminado guarda artefactos, evidencia recuperada y telemetría. Si un agente posterior falla, la reanudación conserva los anteriores.
- Configuración: una reanudación conserva límites, modelos, recuperación y reranker capturados por la ejecución original.
- Contabilidad: el trabajo reutilizado se marca como tal y no vuelve a sumarse como consumo de la nueva ejecución.
- Proveedor remoto: Jev reintenta únicamente fallos recuperables de transporte, HTTP 429 y HTTP 5xx. Un fallo definitivo queda visible y no activa otro proveedor silenciosamente.

## 2. Resumen de generación

La interfaz informa por RF, RNF y HU la relación `generados / máximo solicitado`, el total de la ejecución y si el resultado está completo o es recuperable. También explica que los límites son máximos, no cantidades obligatorias.

## 3. Auditoría de Jev

La ejecución registra por candidato el ID del fragmento, rango y puntuación RRF, relevancia temática, utilidad como evidencia, promedio utilizado, rango final y selección. Por solicitud registra modelo solicitado y servido, proveedor, ID, intentos, tokens, costo reportado y latencia. La pestaña Ejecución permite inspeccionar los candidatos. Esta auditoría aporta reproducibilidad, no demuestra superioridad de Jev.

## 4. Prueba integral

La suite automatizada contiene 61 pruebas y cubre el recorrido desde fuentes textuales no estructuradas hasta definición, generación, validación, aprobación y serialización de la exportación. Incluye además fallos controlados en la síntesis de definición y en el agente HU para demostrar que los puntos de control evitan repetir etapas terminadas.

Comando de verificación:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
cd frontend
npm run build
```

Antes de congelar la versión se debe ejecutar además el recorrido completo en Docker con el corpus final y guardar el identificador de la ejecución, la configuración capturada y la exportación resultante.
