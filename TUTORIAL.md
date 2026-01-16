# Tutorial: Sistema de Cartas de Manifestacion

## 1. Plantillas del Sistema

### 1.1 Plantilla Word Principal

**Ubicacion:**
```
config/templates/carta_manifestacion/template.docx
```

**Copia de referencia en raiz:**
```
Modelo de plantilla.docx
```

La aplicacion lee la plantilla desde `config/templates/carta_manifestacion/template.docx`. Si no existe, busca `Modelo de plantilla.docx` en el directorio raiz.

### 1.2 Plantillas HTML (Vista Previa Web)

**Plantilla base:**
```
templates_html/_base/preview.html
```

**Plantilla especifica del documento:**
```
templates_html/carta_manifestacion/preview.html
```

**Pagina del manager:**
```
templates_html/_base/manager.html
```

---

## 2. Sistema de Marcadores [[BLOCK:key]]...[[/BLOCK]]

### 2.1 Que son los bloques?

Los bloques son secciones del documento que:
1. Contienen texto generado por el sistema (base)
2. Permiten al usuario agregar contenido personalizado (custom)
3. Se combinan automaticamente segun el modo configurado

### 2.2 Sintaxis

```
[[BLOCK:nombre_del_bloque]]
Contenido base con {{ variables }} dinamicas
[[/BLOCK]]
```

### 2.3 Como agregar bloques en la plantilla Word

1. **Abrir el archivo** `config/templates/carta_manifestacion/template.docx`

2. **Localizar la seccion** donde desea agregar contenido editable

3. **Insertar el marcador** con la sintaxis:

```
[[BLOCK:alcance_auditoria]]
El alcance de la auditoria incluye la revision de {{ Nombre_Cliente }}
para el ejercicio finalizado el {{ FF_Ejecicio }}.
[[/BLOCK]]
```

4. **Guardar el documento**

5. **Registrar el bloque** en el schema (`schemas/carta_manifestacion.json`):

```json
{
  "blocks": {
    "alcance_auditoria": {
      "custom_field": "alcance_auditoria_custom",
      "append_mode": "newline",
      "label": "",
      "custom_type": "text",
      "max_length": 2000,
      "required": false,
      "description": "Alcance de la auditoria"
    }
  }
}
```

### 2.4 Como agregar bloques en la plantilla HTML

En `templates_html/_base/preview.html`, localice la seccion de bloques y agregue:

```html
{% for block in blocks %}
<section class="doc-block" data-block="{{ block.key }}">
    <div class="doc-block-header">
        <span class="block-label">{{ block.description or block.key }}</span>
    </div>
    <div class="doc-block-base">
        <div class="base-content">{{ block.base_html }}</div>
    </div>
    <div class="doc-block-custom">
        <label for="{{ block.custom_field }}">Complemento (opcional)</label>
        <textarea
            name="{{ block.custom_field }}"
            data-field="{{ block.custom_field }}"
            maxlength="{{ block.max_length }}"
            placeholder="Agregar comentario adicional...">{{ block.custom_value }}</textarea>
        <span class="char-count">0 / {{ block.max_length }}</span>
    </div>
</section>
{% endfor %}
```

### 2.5 Modos de combinacion (append_mode)

| Modo | Resultado | Ejemplo |
|------|-----------|---------|
| `newline` | base + salto de linea + custom | "Texto base\nTexto personalizado" |
| `inline` | base + espacio + custom | "Texto base Texto personalizado" |
| `labelled` | base + salto + etiqueta + custom | "Texto base\nNota: Texto personalizado" |

### 2.6 Tipos de campo personalizado (custom_type)

| Tipo | Descripcion |
|------|-------------|
| `text` | Texto plano sin formato |
| `richtext_limited` | HTML limitado (b, i, u, br, ul, ol, li, p) |

### 2.7 Ejemplo completo

**En template.docx:**
```
[[BLOCK:hechos_posteriores]]
No hemos tenido conocimiento de ningun hecho posterior al cierre del ejercicio
que requiera ajuste o revelacion en los estados financieros.
[[/BLOCK]]
```

**En carta_manifestacion.json:**
```json
{
  "blocks": {
    "hechos_posteriores": {
      "custom_field": "hechos_posteriores_custom",
      "append_mode": "inline",
      "label": "",
      "custom_type": "text",
      "max_length": 1000,
      "required": false,
      "description": "Hechos posteriores al cierre"
    }
  }
}
```

**Resultado cuando el usuario escribe "Salvo lo indicado en la nota 15.":**
```
No hemos tenido conocimiento de ningun hecho posterior al cierre del ejercicio
que requiera ajuste o revelacion en los estados financieros. Salvo lo indicado en la nota 15.
```

---

## 3. Flujo de la Aplicacion

### 3.1 Usuario Normal (Empleado)

1. **Seleccionar "Usuario Normal"** en la barra lateral
2. **Completar el formulario** con los datos del cliente
3. **Vista previa**: Revisar el documento generado
4. **Editar bloques**: Modificar campos con marcador [[BLOCK:key]]
5. **Seleccionar supervisor**: Elegir el responsable de aprobacion
6. **Generar codigo**: Obtener codigo unico para el supervisor
7. **Compartir codigo** con el supervisor seleccionado

### 3.2 Usuario Superior (Supervisor/Manager)

1. **Seleccionar "Usuario Superior"** en la barra lateral
2. **Ingresar codigo** de aprobacion recibido
3. **Ingresar contrasena** del supervisor
4. **Vista previa**: Revisar el contenido del documento
5. **Aprobar y descargar**: Generar archivo Word final

---

## 4. Supervisores del Sistema

### 4.1 Supervisores predefinidos

| ID | Nombre | Contrasena |
|----|--------|------------|
| admin | Administrador | Forvis30 |
| maria_jose | Maria Jose | maria_jose123 |

### 4.2 Agregar nuevos supervisores

Edite el archivo `config/supervisors.json`:

```json
{
  "supervisors": {
    "admin": {
      "name": "Administrador",
      "password_hash": "sha256_hash_aqui"
    },
    "nuevo_supervisor": {
      "name": "Nombre del Supervisor",
      "password_hash": "sha256_hash_de_la_contrasena"
    }
  }
}
```

Para generar el hash SHA-256:
```python
import hashlib
password = "mi_contrasena_segura"
hash = hashlib.sha256(password.encode()).hexdigest()
print(hash)
```

---

## 5. Configuracion del Esquema de Campos

### 5.1 Ubicacion del esquema
```
schemas/carta_manifestacion.json
```

### 5.2 Estructura de un campo

```json
{
  "Nombre_Campo": {
    "type": "string",           // string, date, boolean, enum, list
    "label": "Etiqueta visible",
    "section": "seccion_id",
    "editable": true,           // true = empleado puede editar
    "required": true,
    "validation": {
      "max_length": 200,
      "min_length": 1,
      "pattern": "^[A-Z].*"     // Regex opcional
    }
  }
}
```

### 5.3 Campos editables vs solo lectura

- **editable: true** - El empleado puede modificar en vista previa (fondo amarillo)
- **editable: false** - Solo visualizacion, no modificable (fondo gris)

---

## 6. Variables disponibles en plantillas

### 6.1 Variables basicas

| Variable | Descripcion |
|----------|-------------|
| `{{ Nombre_Cliente }}` | Nombre del cliente |
| `{{ Fecha_de_hoy }}` | Fecha actual formateada |
| `{{ Fecha_encargo }}` | Fecha del encargo |
| `{{ FF_Ejecicio }}` | Fecha fin del ejercicio |
| `{{ Fecha_cierre }}` | Fecha de cierre |
| `{{ Direccion_Oficina }}` | Direccion de la oficina |
| `{{ CP }}` | Codigo postal |
| `{{ Ciudad_Oficina }}` | Ciudad |

### 6.2 Variables de bloque (auto-generadas)

| Variable | Descripcion |
|----------|-------------|
| `{{ __block_scope_base__ }}` | Contenido combinado del bloque scope_base |
| `{{ __block_hechos_posteriores__ }}` | Contenido combinado del bloque hechos_posteriores |

---

## 7. API Endpoints

### 7.1 Endpoints para empleados (/reviews)

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| POST | /reviews | Crear nueva revision |
| GET | /reviews/{id}/preview | Vista previa HTML |
| GET | /reviews/{id}/data | Obtener datos |
| PATCH | /reviews/{id}/data | Actualizar campos editables |
| POST | /reviews/{id}/submit | Enviar para aprobacion |

### 7.2 Endpoints para supervisores (/manager)

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | /manager/reviews/{id} | Pagina de descarga |
| POST | /manager/reviews/{id}/authorize | Verificar contrasena |
| GET | /manager/reviews/{id}/download | Descargar Word |
| GET | /manager/reviews/{id}/audit | Ver registro de auditoria |

---

## 8. Solucionar problemas comunes

### 8.1 El bloque no aparece en la vista previa

1. Verificar que el bloque este registrado en `schemas/carta_manifestacion.json`
2. Verificar que la sintaxis `[[BLOCK:key]]...[[/BLOCK]]` sea correcta
3. Reiniciar el servidor FastAPI

### 8.2 Las variables no se reemplazan

1. Verificar que la sintaxis sea `{{ NombreVariable }}` (con espacios)
2. Verificar que la variable este definida en `fields.yaml`
3. Verificar que el valor se pase en el formulario

### 8.3 Error de autorizacion del supervisor

1. Verificar que el codigo de aprobacion no haya expirado
2. Verificar la contrasena del supervisor
3. Verificar que el documento este en estado SUBMITTED

---

## 9. Arquitectura del Sistema

```
+-------------------+     +------------------+     +----------------+
|   Streamlit App   |---->|   FastAPI        |---->|  Word/HTML     |
|   (Formulario)    |     |   (API Backend)  |     |  Templates     |
+-------------------+     +------------------+     +----------------+
        |                        |                       |
        v                        v                       v
+-------------------+     +------------------+     +----------------+
|  Session State    |     |  JSON Storage    |     |  Generated     |
|  (Datos temp)     |     |  (Revisiones)    |     |  Documents     |
+-------------------+     +------------------+     +----------------+
```

---

## 10. Requisitos del Sistema

- Python 3.9+
- Streamlit 1.34+
- FastAPI 0.109+
- python-docx 1.0+

Ver `requirements.txt` para lista completa de dependencias.
