# Guia de Usuario - Sistema de Cartas de Manifestacion

## Introduccion

Este sistema permite generar Cartas de Manifestacion de forma automatizada con un flujo de aprobacion por parte de supervisores.

---

## Tipos de Usuario

### Usuario Normal (Empleado)

Los empleados pueden:
- Completar formularios con datos del cliente
- Importar datos desde archivos (JSON, Excel, Word)
- Generar documentos de borrador
- Seleccionar supervisor y generar codigo de aprobacion
- Exportar metadatos para uso futuro

### Usuario Superior (Supervisor)

Los supervisores pueden:
- Revisar documentos usando codigo de aprobacion
- Aprobar documentos con su contrasena personal
- Descargar el documento Word final aprobado

---

## Flujo de Trabajo

### Paso 1: Generar Documento (Usuario Normal)

1. **Acceder a la aplicacion**
   - Abrir la aplicacion Streamlit
   - Seleccionar "Usuario Normal" en la barra lateral

2. **Completar el formulario**
   - Seleccionar oficina
   - Introducir nombre del cliente
   - Configurar fechas
   - Seleccionar opciones condicionales
   - Agregar directivos
   - Completar informacion de firma

3. **Revisar datos**
   - Verificar que todos los campos obligatorios estan completos
   - El sistema mostrara alertas si faltan campos

4. **Seleccionar supervisor**
   - En la seccion "Enviar para Aprobacion"
   - Elegir el supervisor responsable del desplegable

5. **Generar documento y codigo**
   - Hacer clic en "Generar Documento y Codigo de Aprobacion"
   - El sistema generara un codigo de 8 caracteres
   - **Guardar este codigo** - es necesario para la aprobacion

6. **Comunicar al supervisor**
   - Enviar el codigo de aprobacion al supervisor seleccionado
   - El codigo es valido por 72 horas

### Paso 2: Aprobar Documento (Supervisor)

1. **Acceder a la aplicacion**
   - Abrir la aplicacion Streamlit
   - Seleccionar "Usuario Superior (Supervisor)" en la barra lateral

2. **Introducir credenciales**
   - Codigo de aprobacion: 8 caracteres recibidos del empleado
   - Contrasena: Su contrasena personal de supervisor

3. **Verificar y aprobar**
   - Hacer clic en "Verificar y Aprobar"
   - Si las credenciales son correctas, el documento se aprueba

4. **Descargar documento**
   - Hacer clic en "Descargar Documento Aprobado"
   - El documento Word final se descargara

---

## Supervisores Predefinidos

| ID | Nombre | Contrasena |
|----|--------|------------|
| admin | Administrador | Forvis30 |
| maria_jose | Maria Jose | maria_jose123 |

---

## Importacion de Datos

### Desde JSON

1. Preparar archivo JSON con estructura:
```json
{
  "Nombre_Cliente": "ACME Corporation",
  "Fecha_encargo": "15/01/2024",
  "comision": "si"
}
```

2. Cargar en la seccion "Importar Metadatos"

### Desde Excel

1. Preparar archivo Excel con dos columnas:
   - Columna A: Nombre de variable
   - Columna B: Valor

2. Cargar en la seccion correspondiente

### Desde Word

1. Preparar documento con formato:
```
Nombre_Cliente: ACME Corporation
Fecha_encargo: 15/01/2024
```

2. Cargar en la seccion correspondiente

---

## Exportacion de Datos

Los datos del formulario se pueden exportar en:
- **JSON**: Para reimportar posteriormente
- **Excel**: Para revision y archivo

---

## Solucionar Problemas

### "Faltan campos obligatorios"

- Verificar que todos los campos marcados como obligatorios estan completos
- Campos obligatorios: Nombre del Cliente, Direccion de Oficina, Codigo Postal, Ciudad

### "Codigo de aprobacion no encontrado"

- Verificar que el codigo tiene exactamente 8 caracteres
- Verificar que se introdujo correctamente (mayusculas)
- Solicitar nuevo codigo al empleado si es necesario

### "Codigo de aprobacion ha expirado"

- Los codigos expiran despues de 72 horas
- El empleado debe generar un nuevo codigo

### "Contrasena incorrecta"

- Verificar que esta usando su contrasena de supervisor
- Contactar con el administrador si olvido su contrasena

### "Este codigo ya ha sido utilizado"

- Cada codigo solo puede usarse una vez
- Solicitar un nuevo codigo al empleado

---

## Contacto y Soporte

Para problemas tecnicos o preguntas:
- Consultar con el administrador del sistema
- Revisar la documentacion en TUTORIAL.md
- Revisar el manual de mantenimiento en MAINTENANCE.md
