# Carta de Manifestacion Control

Sistema de generacion automatizada de Cartas de Manifestacion con flujo de aprobacion y control de supervisores.

## Descripcion

Este sistema permite:
- Generar documentos Word de Cartas de Manifestacion a partir de plantillas
- Vista previa HTML interactiva con edicion de campos
- Flujo de aprobacion con codigos de autorizacion
- Control de acceso por supervisores con autenticacion segura
- Preservacion de formato (colores, negritas, subrayado) entre Word y HTML

## Arquitectura

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Streamlit UI   │────▶│  FastAPI        │────▶│  Templates      │
│  (Frontend)     │     │  (Backend API)  │     │  (Word/HTML)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  config/        │     │  storage/       │     │  output/        │
│  (YAML/JSON)    │     │  (Reviews)      │     │  (Generated)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Estructura del Proyecto

```
Carta-Manifestacion-Control/
├── api/                          # Backend FastAPI
│   ├── routes/                   # Endpoints HTTP
│   │   ├── manager.py            # Rutas de supervisor
│   │   └── review.py             # Rutas de revision
│   ├── services/                 # Logica de negocio
│   │   ├── block_parser.py       # Parser de bloques [[BLOCK:key]]
│   │   ├── render_docx.py        # Renderizado Word
│   │   ├── render_html.py        # Renderizado HTML
│   │   ├── storage.py            # Almacenamiento
│   │   ├── supervisor_auth.py    # Autenticacion
│   │   └── validation.py         # Validacion de datos
│   ├── models/                   # Modelos Pydantic
│   └── app.py                    # Aplicacion FastAPI
│
├── config/                       # Configuracion
│   ├── supervisors.json          # Credenciales de supervisores
│   ├── yamls/                    # Configuracion por plugin
│   │   └── carta_manifestacion/
│   │       ├── manifest.yaml     # Metadatos del plugin
│   │       ├── config.yaml       # Configuracion general
│   │       ├── fields.yaml       # Definicion de campos
│   │       ├── formatting.yaml   # Formato (fechas, colores)
│   │       ├── derived.yaml      # Campos derivados/calculados
│   │       ├── logic.yaml        # Logica condicional
│   │       ├── tables.yaml       # Definicion de tablas
│   │       ├── texts.yaml        # Textos fijos
│   │       └── decision_map.yaml # Mapeo de decisiones
│   └── templates/                # Plantillas de documentos
│       └── carta_manifestacion/
│           ├── template.docx     # Plantilla Word
│           └── template.html     # Plantilla HTML
│
├── modules/                      # Modulos core
│   ├── plugin_loader.py          # Cargador de plugins YAML
│   ├── context_builder.py        # Constructor de contexto
│   ├── renderer_docx.py          # Renderizador Word
│   ├── rule_engine.py            # Motor de reglas
│   ├── dsl_evaluator.py          # Evaluador DSL
│   └── contract_validator.py     # Validador de contratos
│
├── schemas/                      # Esquemas JSON
│   └── carta_manifestacion.json  # Esquema de campos y bloques
│
├── storage/                      # Almacenamiento persistente
│   ├── approval_codes.json       # Codigos de aprobacion
│   ├── generated/                # Documentos generados
│   └── reviews/                  # Revisiones guardadas
│
├── templates_html/               # Plantillas HTML base
│   ├── _base/
│   │   ├── preview.html          # Vista previa base
│   │   ├── document_preview.html # Contenedor de documento
│   │   ├── manager.html          # Pagina del supervisor
│   │   └── edit_form.html        # Formulario de edicion
│   └── carta_manifestacion/
│       └── preview.html          # Preview especifico
│
├── ui/                           # Interfaz de usuario
│   └── streamlit_app/
│       └── app.py                # Aplicacion Streamlit
│
├── static/                       # Archivos estaticos
│   └── preview.css               # Estilos CSS
│
├── tests/                        # Pruebas unitarias
├── scripts/                      # Scripts utilitarios
│
├── requirements.txt              # Dependencias Python
├── .env.example                  # Variables de entorno ejemplo
├── README.md                     # Este archivo
├── ARCHITECTURE.md               # Guia de arquitectura (template)
├── TUTORIAL.md                   # Tutorial tecnico
├── MAINTENANCE.md                # Manual de mantenimiento
└── GUIA_USUARIO.md               # Guia de usuario final
```

## Instalacion

### Requisitos

- Python 3.9+
- pip

### Pasos

1. **Clonar repositorio**
   ```bash
   git clone <repository-url>
   cd Carta-Manifestacion-Control
   ```

2. **Crear entorno virtual**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # o
   venv\Scripts\activate     # Windows
   ```

3. **Instalar dependencias**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar variables de entorno**
   ```bash
   cp .env.example .env
   # Editar .env con sus valores
   ```

## Uso

### Iniciar API Backend

```bash
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

### Iniciar Frontend Streamlit

```bash
streamlit run ui/streamlit_app/app.py
```

### Acceder a la aplicacion

- **Frontend Streamlit**: http://localhost:8501
- **API Documentacion**: http://localhost:8000/docs

## Caracteristicas Principales

### Sistema de Plantillas Dual

- **Word (.docx)**: Documento final para descarga
- **HTML**: Vista previa interactiva con edicion en tiempo real

### Bloques Editables

```
[[BLOCK:nombre_bloque]]
Contenido base con {{ variables }}
[[/BLOCK]]
```

Los usuarios pueden agregar texto personalizado que se combina con el contenido base.

### Preservacion de Formato

El sistema preserva el formato del documento Word en la vista HTML:
- Colores de texto (rojo para campos editables)
- Negritas y cursivas
- Subrayado
- Tablas con bordes
- Listas con vietas

### Flujo de Aprobacion

1. **Empleado**: Completa formulario → Genera codigo de aprobacion
2. **Supervisor**: Verifica codigo + contrasena → Descarga documento aprobado

## Documentacion

| Documento | Descripcion |
|-----------|-------------|
| [README.md](README.md) | Introduccion y guia rapida |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Arquitectura detallada y guia para crear apps similares |
| [TUTORIAL.md](TUTORIAL.md) | Tutorial tecnico completo |
| [MAINTENANCE.md](MAINTENANCE.md) | Manual de mantenimiento |
| [GUIA_USUARIO.md](GUIA_USUARIO.md) | Guia para usuarios finales |

## API Endpoints

### Revisiones (Empleados)

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| POST | `/reviews` | Crear revision |
| GET | `/reviews/{id}/preview` | Vista previa HTML |
| GET | `/reviews/{id}/data` | Obtener datos |
| PATCH | `/reviews/{id}/data` | Actualizar campos |
| POST | `/reviews/{id}/submit` | Enviar para aprobacion |

### Manager (Supervisores)

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/manager/reviews/{id}` | Pagina de descarga |
| POST | `/manager/reviews/{id}/authorize` | Verificar credenciales |
| GET | `/manager/reviews/{id}/download` | Descargar Word |

## Tecnologias

- **Backend**: FastAPI, Python 3.9+
- **Frontend**: Streamlit
- **Plantillas**: Jinja2, python-docx
- **Validacion**: Pydantic
- **Almacenamiento**: JSON/Archivos

## Licencia

Uso interno - Forvis Mazars

## Soporte

Para soporte tecnico, consultar la documentacion o contactar al equipo de desarrollo.
