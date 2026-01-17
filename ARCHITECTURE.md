# Guia de Arquitectura - Plantilla para Apps Similares

Esta guia explica la arquitectura del sistema y como usarla como plantilla para crear aplicaciones similares de generacion de documentos con flujo de aprobacion.

---

## Indice

1. [Vision General](#1-vision-general)
2. [Componentes del Sistema](#2-componentes-del-sistema)
3. [Sistema de Plugins](#3-sistema-de-plugins)
4. [Crear un Nuevo Plugin](#4-crear-un-nuevo-plugin)
5. [Sistema de Plantillas](#5-sistema-de-plantillas)
6. [Renderizado Dual (Word/HTML)](#6-renderizado-dual-wordhtml)
7. [Bloques Editables](#7-bloques-editables)
8. [Sistema de Aprobacion](#8-sistema-de-aprobacion)
9. [API REST](#9-api-rest)
10. [Frontend Streamlit](#10-frontend-streamlit)
11. [Extender el Sistema](#11-extender-el-sistema)

---

## 1. Vision General

### Arquitectura de Alto Nivel

```
┌────────────────────────────────────────────────────────────────────┐
│                         CAPA DE PRESENTACION                        │
├─────────────────────────────┬──────────────────────────────────────┤
│      Streamlit App          │         HTML Preview                  │
│   (Formulario/Interaccion)  │    (Vista previa interactiva)        │
└─────────────────────────────┴──────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────┐
│                           CAPA DE API                               │
├─────────────────────────────┬──────────────────────────────────────┤
│     FastAPI Routes          │         Services                      │
│  /reviews, /manager         │  render_html, render_docx, storage   │
└─────────────────────────────┴──────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────┐
│                         CAPA DE NEGOCIO                             │
├─────────────────────────────┬──────────────────────────────────────┤
│     Plugin Loader           │       Context Builder                 │
│  (Carga configuracion YAML) │  (Construye contexto de variables)   │
├─────────────────────────────┼──────────────────────────────────────┤
│     Rule Engine             │       Block Parser                    │
│  (Evalua condiciones)       │  (Procesa bloques editables)         │
├─────────────────────────────┼──────────────────────────────────────┤
│     Renderer DOCX           │       Renderer HTML                   │
│  (Genera documento Word)    │  (Genera vista previa HTML)          │
└─────────────────────────────┴──────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────┐
│                         CAPA DE DATOS                               │
├─────────────────────────────┬──────────────────────────────────────┤
│     config/yamls/           │       storage/                        │
│  (Configuracion de plugins) │  (Revisiones, codigos, documentos)   │
├─────────────────────────────┼──────────────────────────────────────┤
│     config/templates/       │       schemas/                        │
│  (Plantillas Word/HTML)     │  (Esquemas de validacion JSON)       │
└─────────────────────────────┴──────────────────────────────────────┘
```

### Flujo de Datos

```
Usuario Input → Validacion → Context Builder → Renderer → Output
     │              │              │               │          │
     ▼              ▼              ▼               ▼          ▼
 Formulario    Schema JSON    Variables      Word/HTML   Documento
 Streamlit     Pydantic       Jinja2         Templates    Final
```

---

## 2. Componentes del Sistema

### 2.1 Modulos Core (`modules/`)

| Modulo | Proposito |
|--------|-----------|
| `plugin_loader.py` | Carga dinamica de configuracion YAML |
| `context_builder.py` | Construye diccionario de variables para templates |
| `renderer_docx.py` | Renderiza plantilla Word con variables |
| `rule_engine.py` | Evalua reglas condicionales |
| `dsl_evaluator.py` | Evaluador de expresiones DSL |
| `contract_validator.py` | Valida contratos de datos |

### 2.2 Servicios API (`api/services/`)

| Servicio | Proposito |
|----------|-----------|
| `render_html.py` | Genera HTML preview con Jinja2 |
| `render_docx.py` | Genera documento Word final |
| `block_parser.py` | Procesa bloques `[[BLOCK:key]]` |
| `storage.py` | Almacena/recupera revisiones |
| `supervisor_auth.py` | Autenticacion de supervisores |
| `validation.py` | Validacion de entrada |

### 2.3 Rutas API (`api/routes/`)

| Ruta | Proposito |
|------|-----------|
| `review.py` | CRUD de revisiones (empleados) |
| `manager.py` | Aprobacion/descarga (supervisores) |

---

## 3. Sistema de Plugins

El sistema usa una arquitectura basada en plugins donde cada tipo de documento es un plugin con su propia configuracion.

### Estructura de un Plugin

```
config/
├── yamls/
│   └── {plugin_id}/           # Ej: carta_manifestacion
│       ├── manifest.yaml      # Metadatos del plugin
│       ├── config.yaml        # Configuracion general
│       ├── fields.yaml        # Definicion de campos
│       ├── formatting.yaml    # Formato de datos
│       ├── derived.yaml       # Campos calculados
│       ├── logic.yaml         # Reglas condicionales
│       ├── tables.yaml        # Definicion de tablas
│       ├── texts.yaml         # Textos estaticos
│       └── decision_map.yaml  # Mapeo de decisiones
│
└── templates/
    └── {plugin_id}/
        ├── template.docx      # Plantilla Word
        └── template.html      # Plantilla HTML
```

### Carga de Plugins

```python
from modules.plugin_loader import PluginLoader

# Cargar plugin
loader = PluginLoader()
plugin = loader.load("carta_manifestacion")

# Acceder a configuracion
fields = plugin.fields
formatting = plugin.formatting
template_path = plugin.template_path
```

---

## 4. Crear un Nuevo Plugin

### Paso 1: Crear directorio de configuracion

```bash
mkdir -p config/yamls/nuevo_documento
mkdir -p config/templates/nuevo_documento
```

### Paso 2: Crear manifest.yaml

```yaml
# config/yamls/nuevo_documento/manifest.yaml
plugin:
  id: nuevo_documento
  name: "Nuevo Tipo de Documento"
  version: "1.0.0"
  description: "Descripcion del documento"
  template_type: docx
  template_path: "config/templates/nuevo_documento/template.docx"
```

### Paso 3: Crear fields.yaml

```yaml
# config/yamls/nuevo_documento/fields.yaml
fields:
  # Campo de texto simple
  nombre_cliente:
    type: string
    label: "Nombre del Cliente"
    section: cliente
    required: true
    editable: true
    validation:
      max_length: 200
      min_length: 1

  # Campo de fecha
  fecha_documento:
    type: date
    label: "Fecha del Documento"
    section: fechas
    required: true
    editable: true
    format: "%d de %B de %Y"

  # Campo booleano (si/no)
  incluir_anexo:
    type: boolean
    label: "Incluir Anexo"
    section: opciones
    required: false
    editable: true
    default: false

  # Campo enum (seleccion)
  tipo_documento:
    type: enum
    label: "Tipo de Documento"
    section: opciones
    required: true
    editable: true
    options:
      - value: tipo_a
        label: "Tipo A"
      - value: tipo_b
        label: "Tipo B"

  # Campo lista
  lista_participantes:
    type: list
    label: "Participantes"
    section: participantes
    required: false
    editable: true
    item_schema:
      nombre:
        type: string
        label: "Nombre"
      cargo:
        type: string
        label: "Cargo"

sections:
  - id: cliente
    label: "Datos del Cliente"
    order: 1
  - id: fechas
    label: "Fechas"
    order: 2
  - id: opciones
    label: "Opciones"
    order: 3
  - id: participantes
    label: "Participantes"
    order: 4
```

### Paso 4: Crear formatting.yaml

```yaml
# config/yamls/nuevo_documento/formatting.yaml
date_formats:
  default: "%d de %B de %Y"
  short: "%d/%m/%Y"
  iso: "%Y-%m-%d"

currency:
  symbol: "EUR"
  decimal_separator: ","
  thousands_separator: "."

colors:
  # Colores para celdas de tabla basados en contenido
  "si": "#90EE90"     # Verde claro
  "no": "#FFB6C1"     # Rosa claro
  "parcial": "#FFFFE0" # Amarillo claro

text_transforms:
  # Transformaciones de texto
  uppercase_fields:
    - nombre_cliente
```

### Paso 5: Crear derived.yaml

```yaml
# config/yamls/nuevo_documento/derived.yaml
derived_fields:
  # Campo calculado a partir de otros
  anio_anterior:
    formula: "int(anio_actual) - 1"
    depends_on:
      - anio_actual

  # Campo formateado
  fecha_formateada:
    formula: "format_date(fecha_documento, '%d de %B de %Y')"
    depends_on:
      - fecha_documento

  # Campo condicional
  texto_tipo:
    formula: "'Documento Tipo A' if tipo_documento == 'tipo_a' else 'Documento Tipo B'"
    depends_on:
      - tipo_documento
```

### Paso 6: Crear logic.yaml

```yaml
# config/yamls/nuevo_documento/logic.yaml
conditionals:
  # Condicion para mostrar/ocultar secciones
  mostrar_anexo:
    condition: "incluir_anexo == 'si' or incluir_anexo == true"
    affects:
      - seccion_anexo

  # Condicion para texto dinamico
  texto_participantes:
    condition: "len(lista_participantes) > 0"
    true_value: "Los participantes son:"
    false_value: "No hay participantes registrados."

rules:
  # Regla de validacion
  fecha_valida:
    condition: "fecha_documento <= fecha_actual"
    error_message: "La fecha no puede ser futura"
```

### Paso 7: Crear plantilla Word

Crear `config/templates/nuevo_documento/template.docx` con:

```
TITULO DEL DOCUMENTO

Fecha: {{ fecha_documento }}
Cliente: {{ nombre_cliente }}

{% if incluir_anexo == 'si' or incluir_anexo == true %}
ANEXO

Contenido del anexo...
{% endif %}

[[BLOCK:contenido_principal]]
Contenido base del bloque que puede ser editado.
[[/BLOCK]]
```

### Paso 8: Crear plantilla HTML

Crear `config/templates/nuevo_documento/template.html` con estructura similar:

```html
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>{{ nombre_cliente }} - Documento</title>
  <style>
    /* Estilos CSS */
    .text-red { color: #FF0000; }
    .text-bold { font-weight: 700; }
    .text-underline { text-decoration: underline; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border: 1px solid #000; padding: 8px; }
  </style>
</head>
<body>
  <div class="page">
    <h1>TITULO DEL DOCUMENTO</h1>
    <p><strong>Fecha:</strong> {{ fecha_documento }}</p>
    <p><strong>Cliente:</strong> {{ nombre_cliente }}</p>

    {% if incluir_anexo == 'si' or incluir_anexo == true %}
    <h2>ANEXO</h2>
    <p>Contenido del anexo...</p>
    {% endif %}
  </div>
</body>
</html>
```

### Paso 9: Crear schema JSON

```json
// schemas/nuevo_documento.json
{
  "doc_type": "nuevo_documento",
  "version": "1.0.0",
  "fields": {
    "nombre_cliente": {
      "type": "string",
      "label": "Nombre del Cliente",
      "required": true
    }
  },
  "sections": [
    { "id": "cliente", "label": "Datos del Cliente" }
  ],
  "blocks": {
    "contenido_principal": {
      "custom_field": "contenido_principal_custom",
      "append_mode": "newline",
      "custom_type": "text",
      "max_length": 2000,
      "required": false,
      "description": "Contenido principal editable"
    }
  }
}
```

---

## 5. Sistema de Plantillas

### Variables Jinja2

```
{{ variable }}              # Variable simple
{{ variable | default('valor', true) }}  # Con valor por defecto
{{ variable | int }}        # Conversion a entero
{{ (variable | int) - 1 }}  # Operacion matematica
```

### Condicionales

```jinja2
{% if condicion == 'si' or condicion == true %}
  Contenido si es verdadero
{% elif otra_condicion %}
  Contenido alternativo
{% else %}
  Contenido por defecto
{% endif %}
```

### Bucles

```jinja2
{% for item in lista_items %}
  {{ item.nombre }}: {{ item.valor }}
  {% if not loop.last %}, {% endif %}
{% endfor %}
```

### Bloques Editables

```
[[BLOCK:nombre_bloque]]
Contenido base que se muestra siempre.
El usuario puede agregar texto adicional.
[[/BLOCK]]
```

---

## 6. Renderizado Dual (Word/HTML)

### Renderizador Word (`modules/renderer_docx.py`)

```python
class DocxRenderer:
    def render(self, context: dict) -> Document:
        # 1. Cargar plantilla
        doc = Document(self.template_path)

        # 2. Procesar condicionales
        self._process_conditionals(doc, context)

        # 3. Reemplazar variables en parrafos
        for para in doc.paragraphs:
            self._replace_variables(para, context)

        # 4. Reemplazar variables en tablas
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        self._replace_variables(para, context)

        # 5. Aplicar formato (colores, etc)
        self._apply_formatting(doc)

        return doc
```

### Renderizador HTML (`api/services/render_html.py`)

```python
from jinja2 import Environment, FileSystemLoader

class HTMLRenderer:
    def __init__(self):
        self.env = Environment(
            loader=FileSystemLoader('config/templates'),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True
        )
        # Registrar filtros personalizados
        self.env.filters['date_es'] = self.date_es_filter
        self.env.filters['currency_eur'] = self.currency_eur_filter

    def render(self, doc_type: str, context: dict) -> str:
        template = self.env.get_template(f'{doc_type}/template.html')
        return template.render(**context)
```

---

## 7. Bloques Editables

### Estructura de un Bloque

```json
{
  "blocks": {
    "nombre_bloque": {
      "custom_field": "nombre_bloque_custom",  // Campo para texto personalizado
      "append_mode": "newline",                 // Como combinar base + custom
      "label": "Nota adicional:",               // Etiqueta (para modo labelled)
      "custom_type": "text",                    // text | richtext_limited
      "max_length": 2000,                       // Maximo caracteres
      "required": false,                        // Obligatorio?
      "description": "Descripcion del bloque"   // Para UI
    }
  }
}
```

### Modos de Combinacion (append_mode)

| Modo | Resultado |
|------|-----------|
| `newline` | `base\ncustom` |
| `inline` | `base custom` |
| `labelled` | `base\nLabel: custom` |

### Procesamiento de Bloques

```python
# api/services/block_parser.py
class BlockParser:
    def parse_and_render(self, template_content: str, context: dict, blocks_config: dict) -> dict:
        """
        Extrae bloques de la plantilla y genera variables __block_*__
        """
        block_vars = {}

        for block_key, config in blocks_config.items():
            # Extraer contenido base del template
            base_content = self._extract_block(template_content, block_key)

            # Renderizar base con variables
            rendered_base = self._render_with_context(base_content, context)

            # Obtener contenido personalizado
            custom_field = config['custom_field']
            custom_content = context.get(custom_field, '')

            # Combinar segun modo
            combined = self._combine(rendered_base, custom_content, config)

            # Crear variable para el template
            block_vars[f'__block_{block_key}__'] = combined

        return block_vars
```

---

## 8. Sistema de Aprobacion

### Flujo de Aprobacion

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Empleado   │    │  Sistema    │    │  Supervisor │    │  Descarga   │
│  completa   │───▶│  genera     │───▶│  verifica   │───▶│  documento  │
│  formulario │    │  codigo     │    │  y aprueba  │    │  aprobado   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

### Estructura de Codigo de Aprobacion

```json
{
  "ABCD1234": {
    "code": "ABCD1234",
    "review_id": "uuid-de-la-revision",
    "supervisor_id": "admin",
    "created_at": "2024-01-15T10:30:00",
    "expires_at": "2024-01-18T10:30:00",
    "used": false,
    "used_at": null
  }
}
```

### Configuracion de Supervisores

```json
// config/supervisors.json
{
  "supervisors": {
    "admin": {
      "name": "Administrador",
      "email": "admin@empresa.com",
      "password_hash": "sha256_hash",
      "active": true
    }
  },
  "settings": {
    "approval_code_ttl_hours": 72,
    "download_token_ttl_seconds": 300
  }
}
```

---

## 9. API REST

### Endpoints de Revision

```
POST   /reviews                    # Crear revision
GET    /reviews/{id}               # Obtener revision
GET    /reviews/{id}/preview       # Vista previa HTML
GET    /reviews/{id}/data          # Obtener datos
PATCH  /reviews/{id}/data          # Actualizar datos
POST   /reviews/{id}/submit        # Enviar para aprobacion
DELETE /reviews/{id}               # Eliminar revision
```

### Endpoints de Manager

```
GET    /manager/reviews/{id}           # Pagina de descarga
POST   /manager/reviews/{id}/authorize # Verificar credenciales
GET    /manager/reviews/{id}/download  # Descargar documento
GET    /manager/reviews/{id}/audit     # Ver auditoria
```

### Ejemplo de Request/Response

```bash
# Crear revision
POST /reviews
Content-Type: application/json

{
  "doc_type": "carta_manifestacion",
  "data": {
    "nombre_cliente": "ACME Corp",
    "fecha_documento": "2024-01-15"
  }
}

# Response
{
  "review_id": "abc123",
  "status": "draft",
  "created_at": "2024-01-15T10:00:00"
}
```

---

## 10. Frontend Streamlit

### Estructura de la App

```python
# ui/streamlit_app/app.py
import streamlit as st

def main():
    st.set_page_config(page_title="Generador de Documentos")

    # Sidebar para seleccion de rol
    role = st.sidebar.selectbox(
        "Tipo de Usuario",
        ["Usuario Normal", "Usuario Superior (Supervisor)"]
    )

    if role == "Usuario Normal":
        show_employee_form()
    else:
        show_supervisor_form()

def show_employee_form():
    st.header("Generar Documento")

    # Cargar campos desde schema
    schema = load_schema("carta_manifestacion")

    # Renderizar formulario dinamico
    data = {}
    for section in schema['sections']:
        st.subheader(section['label'])
        for field_id, field in schema['fields'].items():
            if field['section'] == section['id']:
                data[field_id] = render_field(field_id, field)

    # Boton de envio
    if st.button("Generar Documento"):
        response = api_create_review(data)
        st.success(f"Codigo de aprobacion: {response['approval_code']}")

def show_supervisor_form():
    st.header("Aprobar Documento")

    code = st.text_input("Codigo de Aprobacion")
    password = st.text_input("Contrasena", type="password")

    if st.button("Verificar y Aprobar"):
        if api_authorize(code, password):
            st.download_button(
                "Descargar Documento",
                api_download(code),
                file_name="documento.docx"
            )
```

---

## 11. Extender el Sistema

### Agregar Nuevo Filtro Jinja2

```python
# api/services/render_html.py
def custom_filter(value, param):
    """Mi filtro personalizado"""
    return processed_value

# Registrar en el Environment
env.filters['mi_filtro'] = custom_filter
```

### Agregar Nueva Ruta API

```python
# api/routes/custom.py
from fastapi import APIRouter

router = APIRouter(prefix="/custom", tags=["custom"])

@router.get("/endpoint")
async def custom_endpoint():
    return {"message": "Hello"}

# Registrar en app.py
from api.routes import custom
app.include_router(custom.router)
```

### Agregar Validacion Personalizada

```python
# api/services/validation.py
from pydantic import BaseModel, validator

class CustomData(BaseModel):
    campo: str

    @validator('campo')
    def validate_campo(cls, v):
        if not v.startswith('PREFIX_'):
            raise ValueError('Campo debe comenzar con PREFIX_')
        return v
```

### Agregar Nuevo Tipo de Campo

```python
# modules/context_builder.py
class ContextBuilder:
    def _process_field(self, field_id, field_config, value):
        field_type = field_config.get('type')

        if field_type == 'mi_tipo_nuevo':
            return self._process_mi_tipo(value, field_config)
        # ... otros tipos

    def _process_mi_tipo(self, value, config):
        """Procesar mi tipo de campo personalizado"""
        # Logica personalizada
        return processed_value
```

---

## Resumen

Esta arquitectura permite:

1. **Modularidad**: Cada documento es un plugin independiente
2. **Configuracion**: Todo via YAML/JSON, sin cambiar codigo
3. **Dual Rendering**: Word para descarga, HTML para preview
4. **Seguridad**: Flujo de aprobacion con supervisores
5. **Extensibilidad**: Facil agregar nuevos tipos de documentos

Para crear una nueva aplicacion similar:

1. Copiar estructura de directorios
2. Crear plugin con configuracion YAML
3. Crear plantillas Word/HTML
4. Crear schema JSON
5. (Opcional) Personalizar UI Streamlit
