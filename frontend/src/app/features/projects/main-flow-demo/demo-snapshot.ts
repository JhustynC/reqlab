// Output from the synthetic SIGSAT thesis case, with a generic display name. See HTML_DEMO.md.
// No project IDs, runtime paths, credentials, or live API calls are included.
export const DEMO_SNAPSHOT = {
  // Export uses its own alert count; cross-type duplicates are excluded by the real export UI.
  exportAlertCount: 34,
  name: 'Proyecto de ejemplo',
  sources: [
    {
      source_code: 'SRC-001',
      original_name: '01_correo_direccion_operaciones.txt',
      label: 'Correo',
    },
    {
      source_code: 'SRC-002',
      original_name: '02_procedimiento_actual_atencion.docx',
      label: 'DOCX',
    },
    {
      source_code: 'SRC-003',
      original_name: '03_entrevista_coordinadora_mesa.txt',
      label: 'Entrevista',
    },
    {
      source_code: 'SRC-004',
      original_name: '04_entrevista_tecnico_campo.txt',
      label: 'Entrevista',
    },
    {
      source_code: 'SRC-005',
      original_name: '05_entrevista_supervisora_cliente.txt',
      label: 'Entrevista',
    },
    {
      source_code: 'SRC-006',
      original_name: '06_chat_mesa_y_tecnicos.txt',
      label: 'Conversación',
    },
    {
      source_code: 'SRC-007',
      original_name: '07_catalogo_servicios_prioridades.docx',
      label: 'DOCX',
    },
    {
      source_code: 'SRC-008',
      original_name: '08_extracto_acuerdo_niveles_servicio.pdf',
      label: 'PDF',
    },
    {
      source_code: 'SRC-009',
      original_name: '09_informe_incidentes_reaperturas.md',
      label: 'Nota',
    },
    {
      source_code: 'SRC-010',
      original_name: '10_cadena_correos_proveedor_externo.txt',
      label: 'Correo',
    },
    {
      source_code: 'SRC-011',
      original_name: '11_minuta_comite_transformacion.md',
      label: 'Reunión',
    },
    {
      source_code: 'SRC-012',
      original_name: '12_nota_privacidad_seguridad.docx',
      label: 'Nota',
    },
    {
      source_code: 'SRC-013',
      original_name: '13_exportacion_legacy_casos.txt',
      label: 'Texto',
    },
    {
      source_code: 'SRC-014',
      original_name: '14_mensajes_y_quejas_clientes.txt',
      label: 'Conversación',
    },
    {
      source_code: 'SRC-015',
      original_name: '15_resolucion_spdp_2025_0006_clausulas_datos.pdf',
      label: 'PDF',
    },
    {
      source_code: 'SRC-016',
      original_name: '16_resultados_piloto_movil.md',
      label: 'Nota',
    },
  ],
  fragmentCount: 135,
  question: {
    question: 'Objetivo principal del sistema',
    answer:
      'El sistema permite gestionar solicitudes de asistencia técnica y órdenes de trabajo de clientes corporativos, desde el registro hasta el cierre o reapertura, con trazabilidad de eventos, decisiones y responsables. Debe cubrir registro multicanal (mesa y autoservicio del cliente), clasificación, asignación, programación, atención en campo, evidencias, seguimiento, notificaciones y reportes operativos. La finalidad operativa declarada es gestionar y demostrar la prestación del servicio, calculando indicadores desde los casos registrados y no desde copias manuales. Debe ofrecer visibilidad diferenciada interna, de cliente y de proveedor, con filtros visibles y acceso al detalle de cada indicador. Se busca preservar eventos, procedencia, decisiones, responsabilidades y condiciones contractuales, además de mejorar la comunicación con el cliente sobre el estado del caso y habilitar la coordinación con proveedores externos sin exponer información no relacionada.',
    evidence: [
      'SRC-001-F002',
      'SRC-001-F003',
      'SRC-003-F006',
      'SRC-003-F007',
      'SRC-003-F008',
      'SRC-004-F001',
      'SRC-005-F001',
      'SRC-006-F002',
      'SRC-006-F005',
      'SRC-009-F007',
      'SRC-011-F001',
      'SRC-012-F001',
      'SRC-013-F001',
      'SRC-014-F002',
      'SRC-014-F003',
      'SRC-016-F001',
    ],
  },
  artifacts: [
    {
      artifact_key: 'RF-001',
      artifact_type: 'RF',
      title: 'Registro de solicitudes de asistencia técnica',
      description:
        'El sistema deberá permitir el registro de solicitudes de asistencia técnica y órdenes de trabajo para clientes corporativos, tanto por registro manual de la mesa de ayuda como por autoservicio del cliente.',
      priority: 'Media',
      status: 'aceptado',
      citations: ['USR-DEF-004', 'USR-DEF-001', 'SRC-011-F001'],
      details: {
        verification_criteria: [
          'Comprobar que una solicitud creada por la mesa y otra creada por autoservicio del cliente quedan registradas en el sistema con su canal de origen.',
        ],
        ears_pattern: 'Ubicuo',
        quality_category: '',
        metric: '',
        unit: '',
        target: '',
        verification_method: '',
        priority_source: 'usuario',
        rationale:
          'La primera versión cubrirá solicitudes de asistencia técnica y órdenes de trabajo con registro manual por mesa y autoservicio del cliente.',
      },
    },
    {
      artifact_key: 'RNF-001',
      artifact_type: 'RNF',
      title: 'Responsable humano en decisiones críticas',
      description:
        'El sistema deberá conservar un responsable humano en la prioridad final, las excepciones de cierre y las autorizaciones; el sistema podrá advertir, ordenar y dejar evidencia, pero no decidir por el personal.',
      priority: 'Media',
      status: 'aceptado',
      citations: ['USR-DEF-007'],
      details: {
        verification_criteria: [
          'Comprobar que ninguna decisión de prioridad final, excepción de cierre o autorización se ejecuta sin confirmación de un usuario autorizado y que queda registro del responsable.',
        ],
        ears_pattern: 'No aplica',
        quality_category: 'Usabilidad / Control humano',
        metric: '',
        unit: '',
        target: '',
        verification_method: '',
        priority_source: 'usuario',
        rationale:
          'La expectativa confirmada exige que las decisiones críticas mantengan responsable humano y que el sistema solo advierta, ordene y deje evidencia.',
      },
    },
    {
      artifact_key: 'HU-001',
      artifact_type: 'HU',
      title: 'Registro de solicitud por autoservicio del cliente',
      description:
        'Como solicitante de un cliente corporativo, quiero registrar mi solicitud de asistencia técnica por autoservicio, para que quede una ficha única desde el inicio y no se pierda en llamadas, correos o chats.',
      priority: 'Media',
      status: 'aceptado',
      citations: ['USR-DEF-001', 'SRC-001-F002', 'USR-DEF-003'],
      details: {
        verification_criteria: [],
        ears_pattern: 'No aplica',
        quality_category: '',
        metric: '',
        unit: '',
        target: '',
        verification_method: '',
        priority_source: 'usuario',
        rationale:
          'USR-DEF-001 declara registro multicanal con autoservicio del cliente y ficha única; SRC-001-F002 describe la pérdida de solicitudes entre canales y la necesidad de conservar el texto original; USR-DEF-003 identifica al solicitante y la restricción de visibilidad por organización.',
      },
    },
  ],
  counts: {
    HU: 24,
    RF: 24,
    RNF: 24,
  },
  artifactCount: 72,
  evidence: {
    fragment_key: 'SRC-011-F001',
    heading: 'Minuta de trabajo del comité del proyecto',
    text: '# Minuta de trabajo del comité del proyecto\n\nFecha: 14 de agosto de 2026 \nAsistentes ficticios: Operaciones, Mesa de ayuda, Supervisión técnica, Calidad, Tecnología, Finanzas y representante de clientes\n\n## Motivo\n\nRevisar el alcance de la primera versión y las decisiones pendientes antes de solicitar estimación de desarrollo.\n\n## Acuerdos de alcance\n\nLa primera versión cubrirá solicitudes de asistencia técnica y órdenes de trabajo para clientes corporativos. Incluirá canales de registro manual por mesa y autoservicio del cliente. No integrará WhatsApp automáticamente en esta etapa; los mensajes recibidos por ese medio podrán copiarse o adjuntarse, conservando el canal de origen. Tampoco reemplazará contabilidad, compras, facturación, nómina ni inventario financiero.\n\nSe permitirá relacionar casos posiblemente duplicados sin eliminarlos. La fusión definitiva requiere revisión de coordinación y debe conservar textos, adjuntos y participantes originales. El diagnóstico automático y la asignación totalmente automática quedan fuera. El sistema puede recomendar categoría, prioridad o técnico, pero un usuario autorizado confirma la decisión.',
    source_name: '11_minuta_comite_transformacion.md',
  },
  budget: {
    RF: {
      minimum: 1,
      suggested: 24,
      maximum: 30,
      signal_fragments: 91,
      signal_ratio: 0.5948,
    },
    RNF: {
      minimum: 1,
      suggested: 24,
      maximum: 30,
      signal_fragments: 91,
      signal_ratio: 0.5948,
    },
    HU: {
      minimum: 1,
      suggested: 24,
      maximum: 30,
      signal_fragments: 137,
      signal_ratio: 0.8954,
    },
  },
  confirmedFragmentCount: 153,
  alertCount: 37,
} as const;
