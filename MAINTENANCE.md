# Manual de Mantenimiento - Sistema de Cartas de Manifestacion

## Arquitectura del Sistema

```
+-------------------+     +------------------+     +----------------+
|   Streamlit App   |---->|   FastAPI        |---->|  Templates     |
|   (Frontend)      |     |   (API Backend)  |     |  (Word/HTML)   |
+-------------------+     +------------------+     +----------------+
        |                        |                       |
        v                        v                       v
+-------------------+     +------------------+     +----------------+
|  config/          |     |  storage/        |     |  output/       |
|  supervisors.json |     |  approval_codes  |     |  documents     |
+-------------------+     +------------------+     +----------------+
```

---

## Estructura de Directorios

```
Carta-Manifestacion-Control/
|-- api/                        # Backend FastAPI
|   |-- routes/                 # Endpoints
|   |   |-- manager.py          # Rutas de supervisor
|   |   |-- review.py           # Rutas de revision
|   |-- services/               # Servicios
|       |-- supervisor_auth.py  # Autenticacion de supervisores
|       |-- block_parser.py     # Parser de bloques
|       |-- render_docx.py      # Renderizado Word
|       |-- render_html.py      # Renderizado HTML
|
|-- config/
|   |-- supervisors.json        # Configuracion de supervisores
|   |-- yamls/                  # Configuracion YAML del plugin
|   |-- templates/              # Plantillas Word
|
|-- schemas/
|   |-- carta_manifestacion.json # Esquema de validacion
|
|-- storage/
|   |-- approval_codes.json     # Codigos de aprobacion activos
|   |-- reviews/                # Revisiones guardadas (API)
|
|-- templates_html/             # Plantillas HTML
|   |-- _base/
|       |-- preview.html        # Vista previa
|       |-- manager.html        # Pagina del supervisor
|
|-- ui/
|   |-- streamlit_app/
|       |-- app.py              # Aplicacion principal
|
|-- output/                     # Documentos generados
|
|-- TUTORIAL.md                 # Tutorial tecnico
|-- GUIA_USUARIO.md            # Guia de usuario
|-- MAINTENANCE.md             # Este documento
```

---

## Gestion de Supervisores

### Archivo de Configuracion

**Ubicacion:** `config/supervisors.json`

### Estructura

```json
{
  "supervisors": {
    "supervisor_id": {
      "name": "Nombre Completo",
      "email": "email@ejemplo.com",
      "password": "contrasena_texto_plano",
      "password_hash": "hash_sha256_opcional",
      "active": true
    }
  },
  "settings": {
    "approval_code_ttl_hours": 72,
    "download_token_ttl_seconds": 300
  }
}
```

### Agregar Nuevo Supervisor

1. **Generar hash de contrasena** (recomendado para produccion):

```python
import hashlib
password = "nueva_contrasena_segura"
hash_value = hashlib.sha256(password.encode()).hexdigest()
print(hash_value)
```

2. **Editar config/supervisors.json**:

```json
{
  "supervisors": {
    "nuevo_supervisor": {
      "name": "Juan Garcia",
      "email": "juan.garcia@empresa.com",
      "password_hash": "el_hash_generado_arriba",
      "active": true
    }
  }
}
```

3. **Reiniciar la aplicacion** (si es necesario)

### Desactivar Supervisor

Cambiar `"active": true` a `"active": false` en el supervisor correspondiente.

### Cambiar Contrasena

1. Generar nuevo hash
2. Actualizar `password_hash` en el archivo
3. Opcionalmente, eliminar el campo `password` si solo usa hash

---

## Gestion de Plantillas

### Plantilla Word

**Ubicacion:** `config/templates/carta_manifestacion/template.docx`

### Modificar Plantilla

1. Abrir el archivo con Microsoft Word
2. Realizar cambios manteniendo las variables `{{ NombreVariable }}`
3. Guardar el archivo
4. Probar generacion de documento

### Variables Disponibles

| Variable | Descripcion |
|----------|-------------|
| `{{ Nombre_Cliente }}` | Nombre del cliente |
| `{{ Fecha_de_hoy }}` | Fecha actual |
| `{{ Fecha_encargo }}` | Fecha del encargo |
| `{{ FF_Ejecicio }}` | Fecha fin ejercicio |
| `{{ Direccion_Oficina }}` | Direccion oficina |
| `{{ CP }}` | Codigo postal |
| `{{ Ciudad_Oficina }}` | Ciudad |

### Agregar Nuevo Campo

1. **Agregar variable en plantilla:**
   - Insertar `{{ Nuevo_Campo }}` en template.docx

2. **Definir en esquema:**
   - Editar `schemas/carta_manifestacion.json`
   - Agregar definicion del campo

3. **Agregar al formulario:**
   - Editar `ui/streamlit_app/app.py`
   - Agregar input en la seccion correspondiente

---

## Bloques Editables [[BLOCK:key]]

### Agregar Nuevo Bloque

1. **En la plantilla Word:**

```
[[BLOCK:nuevo_bloque]]
Contenido base del bloque con {{ variables }}
[[/BLOCK]]
```

2. **En el esquema JSON:**

```json
{
  "blocks": {
    "nuevo_bloque": {
      "custom_field": "nuevo_bloque_custom",
      "append_mode": "newline",
      "custom_type": "text",
      "max_length": 2000,
      "required": false,
      "description": "Descripcion del bloque"
    }
  }
}
```

### Modos de Combinacion

- `newline`: Contenido base + salto de linea + contenido personalizado
- `inline`: Contenido base + espacio + contenido personalizado
- `labelled`: Contenido base + salto + etiqueta + contenido personalizado

---

## Almacenamiento

### Codigos de Aprobacion

**Ubicacion:** `storage/approval_codes.json`

**Estructura:**
```json
{
  "ABCD1234": {
    "code": "ABCD1234",
    "review_id": "trace_id_documento",
    "supervisor_id": "admin",
    "created_at": "2024-01-15T10:30:00",
    "expires_at": "2024-01-18T10:30:00",
    "used": false,
    "used_at": null
  }
}
```

### Limpieza de Codigos Expirados

Los codigos expirados se pueden limpiar manualmente o mediante script:

```python
import json
from datetime import datetime
from pathlib import Path

codes_path = Path("storage/approval_codes.json")
with open(codes_path, 'r') as f:
    codes = json.load(f)

# Filtrar codigos no expirados o ya usados (mantener para auditoria)
now = datetime.utcnow()
active_codes = {
    code: data for code, data in codes.items()
    if data.get("used") or datetime.fromisoformat(data["expires_at"]) > now
}

with open(codes_path, 'w') as f:
    json.dump(active_codes, f, indent=2)
```

---

## Configuracion del Servidor

### Variables de Entorno

| Variable | Descripcion | Valor por defecto |
|----------|-------------|-------------------|
| `DOWNLOAD_TOKEN_TTL` | TTL token descarga (seg) | 300 |

### Iniciar Aplicacion Streamlit

```bash
cd /path/to/Carta-Manifestacion-Control
streamlit run ui/streamlit_app/app.py
```

### Iniciar API FastAPI

```bash
cd /path/to/Carta-Manifestacion-Control
uvicorn api.app:app --host 0.0.0.0 --port 8000
```

---

## Seguridad

### Recomendaciones

1. **Usar hashes de contrasena** en produccion (no texto plano)
2. **Limitar acceso** al archivo supervisors.json
3. **Rotacion regular** de contrasenas de supervisores
4. **Backup regular** de storage/ y config/
5. **HTTPS** para conexiones en produccion

### Auditoria

Los eventos se registran en:
- `storage/reviews/` - Logs de revision por documento
- `storage/approval_codes.json` - Historial de codigos

---

## Actualizaciones

### Procedimiento

1. **Backup** de config/ y storage/
2. **Actualizar** codigo fuente
3. **Verificar** compatibilidad de esquemas
4. **Probar** en entorno de desarrollo
5. **Desplegar** en produccion

### Compatibilidad de Datos

- Los codigos de aprobacion existentes seguiran funcionando
- Los documentos generados no se ven afectados
- Verificar migraciones de esquema si cambian campos

---

## Resolucion de Problemas

### La aplicacion no inicia

1. Verificar dependencias: `pip install -r requirements.txt`
2. Verificar Python 3.9+
3. Verificar rutas de archivos de configuracion

### Error de generacion de documento

1. Verificar que template.docx existe
2. Verificar sintaxis de variables `{{ }}`
3. Revisar logs de error

### Supervisor no puede aprobar

1. Verificar que el codigo no ha expirado
2. Verificar que el supervisor esta activo en config
3. Verificar contrasena correcta

### Documento no se descarga

1. Verificar permisos en output/
2. Verificar espacio en disco
3. Revisar logs de generacion

---

## Contacto Tecnico

Para soporte tecnico avanzado, revisar:
- `TUTORIAL.md` - Documentacion tecnica detallada
- Codigo fuente en los archivos mencionados
- Logs de la aplicacion
