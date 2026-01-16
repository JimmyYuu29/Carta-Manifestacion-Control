"""
Main Streamlit Application - Carta de Manifestacion Generator
Aplicacion principal de Streamlit - Generador de Cartas de Manifestacion

Features:
- Normal User: Fill form -> Preview -> Edit blocks -> Select supervisor -> Generate code
- Supervisor User: Enter code + password -> Preview -> Approve and download
"""

import streamlit as st
from datetime import datetime, date
from pathlib import Path
import sys
import json
import io
import pandas as pd
from docx import Document
import requests
import hashlib

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.plugin_loader import load_plugin
from modules.generate import generate_from_form
from modules.context_builder import format_spanish_date, parse_date_string

from ui.streamlit_app.state_store import (
    init_session_state,
    set_imported_data,
)
from ui.streamlit_app.form_renderer import FormRenderer


# Plugin configuration
PLUGIN_ID = "carta_manifestacion"

# API configuration
API_BASE_URL = "http://localhost:8000"

# Supervisors configuration path
SUPERVISORS_CONFIG_PATH = PROJECT_ROOT / "config" / "supervisors.json"


def load_supervisors():
    """Load supervisors from configuration file"""
    if SUPERVISORS_CONFIG_PATH.exists():
        with open(SUPERVISORS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
            supervisors = []
            for sup_id, sup_data in config.get("supervisors", {}).items():
                if sup_data.get("active", True):
                    supervisors.append({
                        "id": sup_id,
                        "name": sup_data.get("name", sup_id),
                        "email": sup_data.get("email", "")
                    })
            return supervisors
    return [
        {"id": "admin", "name": "Administrador", "email": "admin@forvismazars.com"},
        {"id": "maria_jose", "name": "Maria Jose", "email": "maria.jose@forvismazars.com"}
    ]


def verify_supervisor_password(supervisor_id: str, password: str) -> bool:
    """Verify supervisor password locally"""
    if SUPERVISORS_CONFIG_PATH.exists():
        with open(SUPERVISORS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
            sup_data = config.get("supervisors", {}).get(supervisor_id)
            if sup_data:
                # Check hash first
                stored_hash = sup_data.get("password_hash")
                if stored_hash:
                    if hashlib.sha256(password.encode()).hexdigest() == stored_hash:
                        return True
                # Check plain password
                if sup_data.get("password") == password:
                    return True
    return False


def process_uploaded_file(uploaded_file, file_type: str) -> dict:
    """
    Process uploaded Excel or Word file
    Procesar archivo Excel o Word cargado
    """
    extracted_data = {}

    try:
        if file_type == "excel":
            df = pd.read_excel(uploaded_file, header=None)

            if df.shape[1] >= 2:
                for index, row in df.iterrows():
                    if pd.notna(row[0]) and pd.notna(row[1]):
                        var_name = str(row[0]).strip()
                        var_value = row[1]

                        if pd.api.types.is_datetime64_any_dtype(type(var_value)) or isinstance(var_value, datetime):
                            var_value = var_value.strftime("%d/%m/%Y")
                        else:
                            var_value = str(var_value).strip()

                        # Normalize boolean values
                        if var_value.upper() in ['SI', 'SI'] or var_value == '1':
                            var_value = True
                        elif var_value.upper() == 'NO' or var_value == '0':
                            var_value = False

                        extracted_data[var_name] = var_value

        elif file_type == "word":
            doc = Document(uploaded_file)

            for paragraph in doc.paragraphs:
                text = paragraph.text.strip()
                if text and ':' in text:
                    parts = text.split(':', 1)
                    if len(parts) == 2:
                        var_name = parts[0].strip()
                        var_value = parts[1].strip()

                        if var_value.upper() in ['SI', 'SI'] or var_value == '1':
                            var_value = True
                        elif var_value.upper() == 'NO' or var_value == '0':
                            var_value = False

                        extracted_data[var_name] = var_value

    except Exception as e:
        st.error(f"Error al procesar el archivo: {str(e)}")
        return {}

    return extracted_data


def process_json_file(uploaded_file) -> dict:
    """
    Process uploaded JSON file
    Procesar archivo JSON cargado
    """
    try:
        content = uploaded_file.read().decode('utf-8')
        data = json.loads(content)

        # Normalize boolean values
        for key, value in data.items():
            if isinstance(value, str):
                if value.upper() in ['SI', 'SI', 'TRUE', 'YES']:
                    data[key] = True
                elif value.upper() in ['NO', 'FALSE']:
                    data[key] = False

        return data
    except Exception as e:
        st.error(f"Error al procesar el archivo JSON: {str(e)}")
        return {}


def serialize_for_export(data: dict) -> dict:
    """
    Serialize data for JSON/Excel export, converting date objects to strings
    Serializar datos para exportacion JSON/Excel, convirtiendo fechas a strings
    """
    result = {}
    for key, value in data.items():
        if isinstance(value, (date, datetime)):
            result[key] = value.strftime("%d/%m/%Y")
        elif isinstance(value, list):
            # Handle list of dicts (like directors)
            result[key] = value
        else:
            result[key] = value
    return result


def export_to_json(data: dict) -> str:
    """Export data to JSON string"""
    serialized = serialize_for_export(data)
    return json.dumps(serialized, indent=2, ensure_ascii=False)


def export_to_excel(data: dict) -> bytes:
    """Export data to Excel bytes"""
    serialized = serialize_for_export(data)

    # Flatten the data for Excel
    rows = []
    for key, value in serialized.items():
        if isinstance(value, list):
            # For lists like directors, create a JSON string representation
            rows.append({"Variable": key, "Valor": json.dumps(value, ensure_ascii=False)})
        elif isinstance(value, bool):
            rows.append({"Variable": key, "Valor": "SI" if value else "NO"})
        else:
            rows.append({"Variable": key, "Valor": str(value) if value else ""})

    df = pd.DataFrame(rows)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Metadatos')
    output.seek(0)

    return output.getvalue()


def render_normal_user_interface(plugin, form_renderer, template_path):
    """Render the normal user (employee) interface"""

    # Main title / Titulo principal
    st.title("Generador de Cartas de Manifestacion - Forvis Mazars")
    st.markdown("---")

    # Template analysis message
    st.success("Plantilla analizada correctamente.")

    # Form subtitle / Subtitulo del formulario
    st.subheader("Informacion de la Carta")

    # Import section / Seccion de importacion
    st.markdown("---")
    st.subheader("Importar Metadatos")

    col_import1, col_import2, col_import3 = st.columns(3)

    with col_import1:
        uploaded_json = st.file_uploader(
            "Cargar archivo JSON (.json)",
            type=['json'],
            help="Archivo JSON con metadatos exportados previamente",
            key="json_upload"
        )

    with col_import2:
        uploaded_excel = st.file_uploader(
            "Cargar archivo Excel (.xlsx, .xls)",
            type=['xlsx', 'xls'],
            help="Formato: Columna 1 = Nombre variable, Columna 2 = Valor",
            key="excel_upload"
        )

    with col_import3:
        uploaded_word = st.file_uploader(
            "Cargar archivo Word (.docx)",
            type=['docx'],
            help="Formato: nombre_variable: valor (una por linea)",
            key="word_upload"
        )

    # Process uploaded files
    imported_data = {}

    if uploaded_json is not None:
        with st.spinner("Procesando archivo JSON..."):
            imported_data = process_json_file(uploaded_json)
            if imported_data:
                set_imported_data(imported_data)
                st.success(f"Se importaron {len(imported_data)} valores desde JSON")

    elif uploaded_excel is not None:
        with st.spinner("Procesando archivo Excel..."):
            imported_data = process_uploaded_file(uploaded_excel, "excel")
            if imported_data:
                set_imported_data(imported_data)
                st.success(f"Se importaron {len(imported_data)} valores desde Excel")

    elif uploaded_word is not None:
        with st.spinner("Procesando archivo Word..."):
            imported_data = process_uploaded_file(uploaded_word, "word")
            if imported_data:
                set_imported_data(imported_data)
                st.success(f"Se importaron {len(imported_data)} valores desde Word")

    st.markdown("---")

    # Form sections in columns / Secciones del formulario en columnas
    col1, col2 = st.columns(2)

    # Get current form data
    var_values = dict(st.session_state.form_data)
    cond_values = {}

    with col1:
        # Office section / Seccion de oficina
        st.markdown("### Informacion de la Oficina")
        var_values = form_renderer.render_oficina_section(var_values)

        # Client section / Seccion de cliente
        st.markdown("### Nombre de cliente")
        var_values['Nombre_Cliente'] = st.text_input(
            "Nombre del Cliente",
            value=var_values.get('Nombre_Cliente', ''),
            key="nombre_cliente"
        )

        # Dates section / Seccion de fechas
        st.markdown("### Fechas")

        # Store dates as date objects for validation, formatting happens in context_builder
        fecha_hoy = parse_date_string(var_values.get('Fecha_de_hoy', ''))
        if not fecha_hoy:
            fecha_hoy = datetime.now().date()
        var_values['Fecha_de_hoy'] = st.date_input("Fecha de Hoy", value=fecha_hoy, key="fecha_hoy")

        fecha_encargo = parse_date_string(var_values.get('Fecha_encargo', ''))
        if not fecha_encargo:
            fecha_encargo = datetime.now().date()
        var_values['Fecha_encargo'] = st.date_input("Fecha del Encargo", value=fecha_encargo, key="fecha_encargo")

        fecha_ff = parse_date_string(var_values.get('FF_Ejecicio', ''))
        if not fecha_ff:
            fecha_ff = datetime.now().date()
        var_values['FF_Ejecicio'] = st.date_input("Fecha Fin del Ejercicio", value=fecha_ff, key="ff_ejercicio")

        fecha_cierre = parse_date_string(var_values.get('Fecha_cierre', ''))
        if not fecha_cierre:
            fecha_cierre = datetime.now().date()
        var_values['Fecha_cierre'] = st.date_input("Fecha de Cierre", value=fecha_cierre, key="fecha_cierre")

        # General info section / Seccion de informacion general
        st.markdown("### Informacion General")
        var_values['Lista_Abogados'] = st.text_area(
            "Lista de abogados y asesores fiscales",
            value=var_values.get('Lista_Abogados', ''),
            placeholder="Ej: Despacho ABC - Asesoria fiscal\nDespacho XYZ - Asesoria legal",
            key="abogados"
        )
        var_values['anexo_partes'] = st.text_input(
            "Numero anexo partes vinculadas",
            value=var_values.get('anexo_partes', '2'),
            key="anexo_partes"
        )
        var_values['anexo_proyecciones'] = st.text_input(
            "Numero anexo proyecciones",
            value=var_values.get('anexo_proyecciones', '3'),
            key="anexo_proyecciones"
        )

    with col2:
        # Administration organ section / Seccion organo de administracion
        st.markdown("### Organo de Administracion")
        organo_options = ['consejo', 'administrador_unico', 'administradores']
        organo_labels = {
            'consejo': 'Consejo de Administracion',
            'administrador_unico': 'Administrador Unico',
            'administradores': 'Administradores'
        }
        organo_default = var_values.get('organo', 'consejo')
        if organo_default not in organo_options:
            organo_default = 'consejo'

        cond_values['organo'] = st.selectbox(
            "Tipo de Organo de Administracion",
            options=organo_options,
            index=organo_options.index(organo_default),
            format_func=lambda x: organo_labels.get(x, x),
            key="organo"
        )

        # Conditional options section / Seccion opciones condicionales
        st.markdown("### Opciones Condicionales")

        cond_values['comision'] = 'si' if st.checkbox(
            "Existe Comision de Auditoria?",
            value=var_values.get('comision', False) if isinstance(var_values.get('comision'), bool) else var_values.get('comision') == 'si',
            key="comision"
        ) else 'no'

        cond_values['junta'] = 'si' if st.checkbox(
            "Incluir Junta de Accionistas?",
            value=var_values.get('junta', False) if isinstance(var_values.get('junta'), bool) else var_values.get('junta') == 'si',
            key="junta"
        ) else 'no'

        cond_values['comite'] = 'si' if st.checkbox(
            "Incluir Comite?",
            value=var_values.get('comite', False) if isinstance(var_values.get('comite'), bool) else var_values.get('comite') == 'si',
            key="comite"
        ) else 'no'

        cond_values['incorreccion'] = 'si' if st.checkbox(
            "Hay incorrecciones no corregidas?",
            value=var_values.get('incorreccion', False) if isinstance(var_values.get('incorreccion'), bool) else var_values.get('incorreccion') == 'si',
            key="incorreccion"
        ) else 'no'

        if cond_values['incorreccion'] == 'si':
            with st.container():
                st.markdown("##### Detalles de incorrecciones")
                var_values['Anio_incorreccion'] = st.text_input(
                    "Ano de la incorreccion",
                    value=var_values.get('Anio_incorreccion', ''),
                    key="anio_inc"
                )
                var_values['Epigrafe'] = st.text_input(
                    "Epigrafe afectado",
                    value=var_values.get('Epigrafe', ''),
                    key="epigrafe"
                )
                cond_values['limitacion_alcance'] = 'si' if st.checkbox(
                    "Hay limitacion al alcance?",
                    value=var_values.get('limitacion_alcance', False) if isinstance(var_values.get('limitacion_alcance'), bool) else var_values.get('limitacion_alcance') == 'si',
                    key="limitacion"
                ) else 'no'
                if cond_values['limitacion_alcance'] == 'si':
                    var_values['detalle_limitacion'] = st.text_area(
                        "Detalle de la limitacion",
                        value=var_values.get('detalle_limitacion', ''),
                        key="det_limitacion"
                    )

        cond_values['dudas'] = 'si' if st.checkbox(
            "Existen dudas sobre empresa en funcionamiento?",
            value=var_values.get('dudas', False) if isinstance(var_values.get('dudas'), bool) else var_values.get('dudas') == 'si',
            key="dudas"
        ) else 'no'

        cond_values['rent'] = 'si' if st.checkbox(
            "Incluir parrafo sobre arrendamientos?",
            value=var_values.get('rent', False) if isinstance(var_values.get('rent'), bool) else var_values.get('rent') == 'si',
            key="rent"
        ) else 'no'

        cond_values['A_coste'] = 'si' if st.checkbox(
            "Hay activos valorados a coste en vez de valor razonable?",
            value=var_values.get('A_coste', False) if isinstance(var_values.get('A_coste'), bool) else var_values.get('A_coste') == 'si',
            key="a_coste"
        ) else 'no'

        cond_values['experto'] = 'si' if st.checkbox(
            "Se utilizo un experto independiente?",
            value=var_values.get('experto', False) if isinstance(var_values.get('experto'), bool) else var_values.get('experto') == 'si',
            key="experto"
        ) else 'no'

        if cond_values['experto'] == 'si':
            with st.container():
                st.markdown("##### Informacion del experto")
                var_values['nombre_experto'] = st.text_input(
                    "Nombre del experto",
                    value=var_values.get('nombre_experto', ''),
                    key="experto_nombre"
                )
                var_values['experto_valoracion'] = st.text_input(
                    "Elemento valorado por experto",
                    value=var_values.get('experto_valoracion', ''),
                    key="experto_val"
                )

        cond_values['unidad_decision'] = 'si' if st.checkbox(
            "Bajo la misma unidad de decision?",
            value=var_values.get('unidad_decision', False) if isinstance(var_values.get('unidad_decision'), bool) else var_values.get('unidad_decision') == 'si',
            key="unidad_decision"
        ) else 'no'

        if cond_values['unidad_decision'] == 'si':
            with st.container():
                st.markdown("##### Informacion de la unidad de decision")
                var_values['nombre_unidad'] = st.text_input(
                    "Nombre de la unidad",
                    value=var_values.get('nombre_unidad', ''),
                    key="nombre_unidad"
                )
                var_values['nombre_mayor_sociedad'] = st.text_input(
                    "Nombre de la mayor sociedad",
                    value=var_values.get('nombre_mayor_sociedad', ''),
                    key="nombre_mayor_sociedad"
                )
                var_values['localizacion_mer'] = st.text_input(
                    "Localizacion o domiciliacion mercantil",
                    value=var_values.get('localizacion_mer', ''),
                    key="localizacion_mer"
                )

        cond_values['activo_impuesto'] = 'si' if st.checkbox(
            "Hay activos por impuestos diferidos?",
            value=var_values.get('activo_impuesto', False) if isinstance(var_values.get('activo_impuesto'), bool) else var_values.get('activo_impuesto') == 'si',
            key="activo_impuesto"
        ) else 'no'

        if cond_values['activo_impuesto'] == 'si':
            with st.container():
                st.markdown("##### Recuperacion de activos")
                var_values['ejercicio_recuperacion_inicio'] = st.text_input(
                    "Ejercicio inicio recuperacion",
                    value=var_values.get('ejercicio_recuperacion_inicio', ''),
                    key="rec_inicio"
                )
                var_values['ejercicio_recuperacion_fin'] = st.text_input(
                    "Ejercicio fin recuperacion",
                    value=var_values.get('ejercicio_recuperacion_fin', ''),
                    key="rec_fin"
                )

        cond_values['operacion_fiscal'] = 'si' if st.checkbox(
            "Operaciones en paraisos fiscales?",
            value=var_values.get('operacion_fiscal', False) if isinstance(var_values.get('operacion_fiscal'), bool) else var_values.get('operacion_fiscal') == 'si',
            key="operacion_fiscal"
        ) else 'no'

        if cond_values['operacion_fiscal'] == 'si':
            with st.container():
                st.markdown("##### Detalle operaciones")
                var_values['detalle_operacion_fiscal'] = st.text_area(
                    "Detalle operaciones paraisos fiscales",
                    value=var_values.get('detalle_operacion_fiscal', ''),
                    key="det_fiscal"
                )

        cond_values['compromiso'] = 'si' if st.checkbox(
            "Compromisos por pensiones?",
            value=var_values.get('compromiso', False) if isinstance(var_values.get('compromiso'), bool) else var_values.get('compromiso') == 'si',
            key="compromiso"
        ) else 'no'

        cond_values['gestion'] = 'si' if st.checkbox(
            "Incluir informe de gestion?",
            value=var_values.get('gestion', False) if isinstance(var_values.get('gestion'), bool) else var_values.get('gestion') == 'si',
            key="gestion"
        ) else 'no'

    # Directors section / Seccion alta direccion
    st.markdown("---")
    st.markdown("### Alta Direccion")

    st.info("Introduce los nombres y cargos de los altos directivos. Estos reemplazaran completamente el ejemplo en la plantilla.")

    num_directivos = st.number_input(
        "Numero de altos directivos",
        min_value=0,
        max_value=10,
        value=2,
        key="num_directivos"
    )

    # Store directors as list of dicts for validation, formatting happens in context_builder
    directivos_list = []
    directivos_display = []
    indent = "                                  "

    for i in range(num_directivos):
        col_nombre, col_cargo = st.columns(2)
        with col_nombre:
            nombre = st.text_input(f"Nombre completo {i+1}", key=f"dir_nombre_{i}")
        with col_cargo:
            cargo = st.text_input(f"Cargo {i+1}", key=f"dir_cargo_{i}")
        if nombre and cargo:
            directivos_list.append({"nombre": nombre, "cargo": cargo})
            directivos_display.append(f"{indent} D. {nombre} - {cargo}")

    var_values['lista_alto_directores'] = directivos_list

    # Signature section / Seccion persona de firma
    st.markdown("---")
    st.markdown("### Persona de firma")

    var_values['Nombre_Firma'] = st.text_input(
        "Nombre del firmante",
        value=var_values.get('Nombre_Firma', ''),
        key="nombre_firma"
    )
    var_values['Cargo_Firma'] = st.text_input(
        "Cargo del firmante",
        value=var_values.get('Cargo_Firma', ''),
        key="cargo_firma"
    )

    # Preview directors list
    if directivos_display:
        st.markdown("#### Vista previa de la lista de directivos:")
        st.code("\n".join(directivos_display))

    # Update session state
    st.session_state.form_data = {**var_values, **cond_values}

    # Automatic review section / Seccion de revision automatica
    st.markdown("---")
    st.header("Revision automatica")

    # Required fields validation
    required_fields = ['Nombre_Cliente', 'Direccion_Oficina', 'CP', 'Ciudad_Oficina']
    missing_fields = [f for f in required_fields if not var_values.get(f)]

    # Show import summary if data was imported
    if imported_data:
        st.info(f"Datos importados: {len(imported_data)} valores")

    # Inform user about validation status
    if not missing_fields:
        st.success("Todas las variables y condiciones estan completas.")
    else:
        st.warning(f"Faltan {len(missing_fields)} campos obligatorios: {', '.join(missing_fields)}")

    # Export metadata section / Seccion exportar metadatos
    st.markdown("---")
    st.subheader("Exportar Metadatos")
    st.info("Exporta los datos del formulario para usarlos posteriormente o compartirlos.")

    # Combine all current data for export
    all_current_data = {**var_values, **cond_values}

    col_export1, col_export2 = st.columns(2)

    with col_export1:
        # Export to JSON
        json_data = export_to_json(all_current_data)
        client_name_safe = var_values.get('Nombre_Cliente', 'documento').replace(' ', '_').replace('/', '_')
        json_filename = f"metadatos_{client_name_safe}_{datetime.now().strftime('%Y%m%d')}.json"

        st.download_button(
            label="Exportar a JSON",
            data=json_data,
            file_name=json_filename,
            mime="application/json",
            help="Descarga los metadatos en formato JSON para importarlos posteriormente"
        )

    with col_export2:
        # Export to Excel
        excel_data = export_to_excel(all_current_data)
        excel_filename = f"metadatos_{client_name_safe}_{datetime.now().strftime('%Y%m%d')}.xlsx"

        st.download_button(
            label="Exportar a Excel",
            data=excel_data,
            file_name=excel_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Descarga los metadatos en formato Excel"
        )

    # Supervisor selection and approval code generation
    st.markdown("---")
    st.header("Enviar para Aprobacion")

    st.info("Seleccione el supervisor responsable y genere un codigo de aprobacion. El supervisor usara este codigo junto con su contrasena para aprobar y descargar el documento.")

    # Load supervisors
    supervisors = load_supervisors()

    col_sup1, col_sup2 = st.columns([2, 1])

    with col_sup1:
        supervisor_options = {s["id"]: f"{s['name']} ({s['email']})" for s in supervisors}
        selected_supervisor = st.selectbox(
            "Seleccionar Supervisor",
            options=list(supervisor_options.keys()),
            format_func=lambda x: supervisor_options[x],
            key="selected_supervisor"
        )

    with col_sup2:
        st.write("")  # Spacing
        st.write("")

    # Generate document and approval code
    st.markdown("---")

    if st.button("Generar Documento y Codigo de Aprobacion", type="primary"):
        if missing_fields:
            st.error(f"Por favor completa los siguientes campos obligatorios: {', '.join(missing_fields)}")
        else:
            with st.spinner("Generando documento y codigo..."):
                try:
                    # Combine all data
                    all_data = {**var_values, **cond_values}

                    # Generate document
                    result = generate_from_form(
                        plugin_id=PLUGIN_ID,
                        form_data=all_data,
                        list_data={},
                        output_dir=PROJECT_ROOT / "output",
                        template_path=template_path
                    )

                    if result.success and result.output_path:
                        # Store review ID in session for API call
                        st.session_state.current_review_id = result.trace_id

                        # Generate approval code locally
                        import secrets
                        import string
                        approval_code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))

                        # Store approval code info
                        approval_codes_path = PROJECT_ROOT / "storage" / "approval_codes.json"
                        approval_codes_path.parent.mkdir(parents=True, exist_ok=True)

                        existing_codes = {}
                        if approval_codes_path.exists():
                            with open(approval_codes_path, 'r', encoding='utf-8') as f:
                                existing_codes = json.load(f)

                        from datetime import timedelta
                        expires_at = datetime.utcnow() + timedelta(hours=72)

                        existing_codes[approval_code] = {
                            "code": approval_code,
                            "review_id": result.trace_id,
                            "supervisor_id": selected_supervisor,
                            "created_at": datetime.utcnow().isoformat(),
                            "expires_at": expires_at.isoformat(),
                            "used": False,
                            "used_at": None
                        }

                        with open(approval_codes_path, 'w', encoding='utf-8') as f:
                            json.dump(existing_codes, f, indent=2, ensure_ascii=False)

                        # Display success
                        st.success("Documento generado exitosamente!")

                        # Display approval code prominently
                        st.markdown("### Codigo de Aprobacion")
                        st.markdown(f"""
                        <div style="background-color: #d4edda; border: 2px solid #28a745; border-radius: 10px; padding: 20px; text-align: center; margin: 20px 0;">
                            <h2 style="color: #155724; margin: 0; font-family: monospace; letter-spacing: 0.3em;">{approval_code}</h2>
                            <p style="color: #155724; margin-top: 10px;">Codigo para: <strong>{supervisor_options[selected_supervisor]}</strong></p>
                            <p style="color: #666; font-size: 0.9em;">Valido por 72 horas</p>
                        </div>
                        """, unsafe_allow_html=True)

                        st.info(f"""
                        **Instrucciones para el supervisor:**
                        1. Acceder a la pagina de aprobacion
                        2. Introducir el codigo: **{approval_code}**
                        3. Introducir su contrasena personal
                        4. Revisar y aprobar el documento
                        5. Descargar el archivo Word
                        """)

                        # Display trace code
                        st.markdown("### Codigo de Traza")
                        st.code(result.trace_id, language=None)
                        st.caption("Este codigo identifica de forma unica este documento generado.")

                        # Display generation info
                        st.info(f"Tiempo de generacion: {result.duration_ms}ms")

                        # Download button for the generated document (optional, for employee preview)
                        with open(result.output_path, 'rb') as f:
                            doc_bytes = f.read()

                        filename = f"Carta_Manifestacion_{var_values['Nombre_Cliente'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}_{result.trace_id[:8]}.docx"

                        st.download_button(
                            label="Descargar Borrador (Solo Vista Previa)",
                            data=doc_bytes,
                            file_name=filename,
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            help="Este es un borrador para revision. El documento oficial debe ser aprobado por el supervisor."
                        )
                    else:
                        st.error(f"Error al generar la carta: {result.error}")
                        if result.validation_errors:
                            st.markdown("### Errores de validacion:")
                            for err in result.validation_errors:
                                st.warning(err)
                        # Also show trace code for failed generations
                        st.caption(f"Codigo de traza: {result.trace_id}")

                except Exception as e:
                    st.error(f"Error al generar la carta: {str(e)}")
                    st.exception(e)


def render_supervisor_interface():
    """Render the supervisor (manager) interface"""

    st.title("Aprobacion de Documentos - Supervisor")
    st.markdown("---")

    st.info("Introduzca el codigo de aprobacion y su contrasena para revisar y aprobar el documento.")

    col1, col2 = st.columns(2)

    with col1:
        approval_code = st.text_input(
            "Codigo de Aprobacion",
            placeholder="XXXXXXXX",
            max_chars=8,
            help="Codigo de 8 caracteres proporcionado por el empleado",
            key="supervisor_approval_code"
        ).upper()

    with col2:
        password = st.text_input(
            "Contrasena del Supervisor",
            type="password",
            help="Su contrasena personal de supervisor",
            key="supervisor_password"
        )

    st.markdown("---")

    if st.button("Verificar y Aprobar", type="primary"):
        if not approval_code or len(approval_code) != 8:
            st.error("Por favor, introduzca un codigo de aprobacion valido (8 caracteres).")
        elif not password:
            st.error("Por favor, introduzca su contrasena.")
        else:
            with st.spinner("Verificando..."):
                # Load approval codes
                approval_codes_path = PROJECT_ROOT / "storage" / "approval_codes.json"

                if not approval_codes_path.exists():
                    st.error("No se encontraron codigos de aprobacion.")
                else:
                    with open(approval_codes_path, 'r', encoding='utf-8') as f:
                        codes = json.load(f)

                    if approval_code not in codes:
                        st.error("Codigo de aprobacion no encontrado.")
                    else:
                        code_info = codes[approval_code]

                        # Check if used
                        if code_info.get("used", False):
                            st.error("Este codigo ya ha sido utilizado.")
                        # Check expiration
                        elif datetime.fromisoformat(code_info["expires_at"]) < datetime.utcnow():
                            st.error("El codigo de aprobacion ha expirado.")
                        else:
                            # Verify password
                            supervisor_id = code_info["supervisor_id"]
                            if not verify_supervisor_password(supervisor_id, password):
                                st.error("Contrasena incorrecta.")
                            else:
                                # Success! Mark code as used
                                codes[approval_code]["used"] = True
                                codes[approval_code]["used_at"] = datetime.utcnow().isoformat()

                                with open(approval_codes_path, 'w', encoding='utf-8') as f:
                                    json.dump(codes, f, indent=2, ensure_ascii=False)

                                # Get supervisor info
                                supervisors = load_supervisors()
                                supervisor_name = next(
                                    (s["name"] for s in supervisors if s["id"] == supervisor_id),
                                    supervisor_id
                                )

                                st.success(f"Documento aprobado por {supervisor_name}")

                                # Find and serve the document
                                review_id = code_info["review_id"]
                                output_dir = PROJECT_ROOT / "output"

                                # Find document with matching trace ID
                                matching_files = list(output_dir.glob(f"*{review_id[:8]}*.docx"))

                                if matching_files:
                                    doc_path = matching_files[0]
                                    with open(doc_path, 'rb') as f:
                                        doc_bytes = f.read()

                                    st.markdown("### Documento Aprobado")
                                    st.download_button(
                                        label="Descargar Documento Aprobado",
                                        data=doc_bytes,
                                        file_name=doc_path.name,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                        type="primary"
                                    )

                                    st.info(f"""
                                    **Detalles de la aprobacion:**
                                    - Supervisor: {supervisor_name}
                                    - Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}
                                    - Codigo utilizado: {approval_code}
                                    """)
                                else:
                                    st.warning("No se encontro el documento asociado. Por favor, contacte con el administrador.")


def main():
    """Main application entry point / Punto de entrada principal"""

    # Page configuration / Configuracion de pagina
    st.set_page_config(
        page_title="Generador de Cartas de Manifestacion",
        page_icon="",
        layout="wide"
    )

    # Initialize session state
    init_session_state(PLUGIN_ID)

    # Load plugin
    try:
        plugin = load_plugin(PLUGIN_ID)
    except Exception as e:
        st.error(f"Error loading plugin: {e}")
        return

    # Create form renderer
    form_renderer = FormRenderer(plugin)

    # Get template path
    template_path = PROJECT_ROOT / "Modelo de plantilla.docx"
    if not template_path.exists():
        # Try config path
        template_path = plugin.get_template_path()

    if not template_path.exists():
        st.error("No se encontro el archivo de plantilla")
        st.info("Por favor, asegurate de que el archivo de plantilla este en la carpeta correcta.")
        return

    # Sidebar - User type selection
    st.sidebar.title("Tipo de Usuario")

    user_type = st.sidebar.radio(
        "Seleccione su rol:",
        options=["Usuario Normal", "Usuario Superior (Supervisor)"],
        index=0,
        key="user_type_selection"
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("""
    **Usuario Normal:** Empleado que genera documentos y solicita aprobacion.

    **Usuario Superior:** Supervisor que aprueba documentos con codigo y contrasena.
    """)

    # Render appropriate interface based on user type
    if user_type == "Usuario Normal":
        render_normal_user_interface(plugin, form_renderer, template_path)
    else:
        render_supervisor_interface()


if __name__ == "__main__":
    main()
