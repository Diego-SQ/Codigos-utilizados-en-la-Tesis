from tkinter import *
from tkinter import ttk
import tkinter as tk
from tkinter import Toplevel
import locale                   #libreria para tener el mes en español
from datetime import datetime   #libreria para el tiempo
from tkinter import messagebox  #libreria para cuadro de mensajes
from PIL import Image, ImageTk  #libreria para imagen (Necesita instalar Pillow [pip install pillow])
import pandas as pd             #libreria para excel
import hashlib                  #Para hashear contraseñas

import matplotlib.pyplot as plt                                           #Librerias necesarias para los graficos
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.animation import FuncAnimation

import mysql.connector                                                    #Librerias para conectar con la base de datos
import mysql.connector.pooling                                            # Para el pool de conexiones
import sys                                                                # Para cerrar la app si la BD falla al inicio

from tkcalendar import DateEntry                                          #Librerias para el popup Alertas

import requests                                                           #Para consultar la pagina de la estacion meteorologica (REM San Luis)
from bs4 import BeautifulSoup                                             #Para extraer los datos del HTML de la estacion (pip install beautifulsoup4)
import threading                                                          #Para consultar la web sin congelar la interfaz


#----------------------------------------------------------------------Variables para el popup rendimiento---------------------------------------------------------------

last_values = (0, 0, 0, 0, 0, 0)
x_data = []
corriente1_data, corriente2_data = [], []
voltaje1_data, voltaje2_data = [], []
potencia1_data, potencia2_data = [], []


#-------------------------------------------------- Variables para almacenar el modo actual ("Manual" o "Automático") y el ángulo actual---------------------------------
modo_actual = "Automático"  # Modo inicial
angulo_actual = None  # Valor inicial del ángulo actual
ultimo_angulo_optimo = None
# Variable global para almacenar el ángulo deseado
angulo_deseado = None

registro_sesion_id = None   # Variable global para almacenar el usuario 
usuario_actual_id = None
jerarquia_actual = None     # Variable global para almacenar rol
usuario_logueado = None


limites_operacion = {
    "corriente_in":  {"min": None, "max": None},
    "corriente_out": {"min": None, "max": None},
    "voltaje_in":    {"min": None, "max": None},
    "voltaje_out":   {"min": None, "max": None},
    "potencia_in":   {"min": None, "max": None},
    "potencia_out":  {"min": None, "max": None}
}   #Variable global para el popup de alertas


entry_usuario = None
entry_password = None

alarma_seleccionada = {}
alarmas = []
ventana_config_alertas = None


cerrando_app = False        # Variable global para que no tire error tk al cerra el scada


#---------------------------------------------------------------------------- Pool de Conexiones a BD -------------------------------------------------------------------

# Configuración de la base de datos
db_config = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "scada_db"
}

try:
    # Crear el pool de conexiones
    db_pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="scada_pool",
        pool_size=5,
        **db_config
    )
    print("Pool de conexiones a la BD creado exitosamente.")
except mysql.connector.Error as err:
    print(f"Error al crear el pool de conexiones: {err}")
    # Usamos un 'Toplevel' temporal para mostrar el error si 'Tk()' falla
    root_error = Tk()
    root_error.withdraw()
    messagebox.showerror("Error Crítico de BD", f"No se pudo conectar a la base de datos: {err}\nLa aplicación se cerrará.", parent=root_error)
    root_error.destroy()
    sys.exit() # Cierra la aplicación si no se puede conectar


#---------------------------------------------------------------------------- Función para obtener datos del clima (REM San Luis) -----------------------------------------

URL_ESTACION_CLIMA = "https://clima.sanluis.gob.ar/Estacion.aspx?Estacion=42"   # Estación Villa Mercedes

def obtener_datos_clima():
    """
    Consulta la página de la estación meteorológica de Villa Mercedes (REM San Luis)
    y devuelve un diccionario con temperatura (°C), viento (km/h) y radiación (W/m2).
    Devuelve None si falla la conexión o no se pudo interpretar la página.
    """
    try:
        respuesta = requests.get(URL_ESTACION_CLIMA, timeout=10)
        respuesta.raise_for_status()

        soup = BeautifulSoup(respuesta.content, "html.parser")

        lineas = [linea.strip() for linea in soup.get_text("\n").split("\n") if linea.strip()]

        def valor_despues_de(etiqueta):

            for i, linea in enumerate(lineas):
                if linea == etiqueta:
                    return lineas[i + 1]
            return None

        temp_txt = valor_despues_de("Temperatura:")
        viento_txt = valor_despues_de("Intensidad:")   # Aparece dentro del bloque "Viento"
        rad_txt = valor_despues_de("Radiación:")

        if temp_txt is None or viento_txt is None or rad_txt is None:
            print("No se encontraron todos los valores en la página de la estación.")
            return None

        temperatura = float(temp_txt.replace(",", "."))

        viento_kmh_txt = viento_txt.split("(")[0].replace(",", ".")
        viento = float(viento_kmh_txt)

        radiacion = float(rad_txt.replace(",", "."))

        return {"temperatura": temperatura, "viento": viento, "radiacion": radiacion}

    except requests.exceptions.RequestException as e:
        print(f"Error de conexión al consultar la estación meteorológica: {e}")
        return None
    except (ValueError, IndexError) as e:
        print(f"Error al interpretar los datos de la estación meteorológica: {e}")
        return None


#---------------------------------------------------------------------------- Funciones para Login ---------------------------------------------------------------------

def hash_password(password):
    """Hashea la contraseña usando SHA-256 para compararla con la base de datos."""
    return hashlib.sha256(password.encode()).hexdigest()

def registrar_login(user_id):
    """
    Registra el inicio de sesión en la tabla registro_usuarios
    y guarda el id del registro para cerrar sesión luego.
    """
    global registro_sesion_id
    conn = None
    cursor = None
    try:
        ahora = datetime.now()
        query = """
            INSERT INTO registro_usuarios (usuario_id, hora_inicio)
            VALUES (%s, %s)
        """

        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, (user_id, ahora))
        conn.commit()

        registro_sesion_id = cursor.lastrowid  # clave para cerrar sesión

    except mysql.connector.Error as err:
        print(f"Error al registrar login: {err}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def registrar_logout():
    """
    Registra la hora de salida del usuario al cerrar el SCADA.
    """
    global registro_sesion_id
    if registro_sesion_id is None:
        return

    conn = None
    cursor = None
    try:
        ahora = datetime.now()
        query = """
            UPDATE registro_usuarios
            SET hora_salida = %s
            WHERE id = %s
        """

        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, (ahora, registro_sesion_id))
        conn.commit()

    except mysql.connector.Error as err:
        print(f"Error al registrar logout: {err}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------


#----------------------------------------------------------------Función para obtener ángulo automático desde BD------------------------------------------------------

def obtener_angulo_automatico():
    """
    Obtiene el ángulo óptimo desde la tabla angulos_optimos
    según el mes actual.
    """
    mes_actual = datetime.now().month
    conn = None
    cursor = None
    try:
        query = """
            SELECT angulo_horizontal_optimo
            FROM angulos_optimos
            WHERE mes = %s
        """
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, (mes_actual,))
        resultado = cursor.fetchone()

        if resultado:
            return resultado[0]
        else:
            return None

    except mysql.connector.Error as err:
        print(f"Error al obtener ángulo automático: {err}")
        return None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


#---------------------------------------------------------------------------------------------------------------------------------------------------------------------


#----------------------------------------------------------------Función para Registrar el modo de operación en BD------------------------------------------------------

def registrar_modo_operacion(modo, angulo=None):
    """
    Registra el modo de operación en la base de datos.
    """
    global usuario_actual_id
    conn = None
    cursor = None
    try:
        query = """
            INSERT INTO modo_operacion (fecha_hora, modo, angulo_deseado, usuario_id)
            VALUES (NOW(), %s, %s, %s)
        """
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, (modo, angulo, usuario_actual_id))
        conn.commit()

    except mysql.connector.Error as err:
        print(f"Error al registrar modo de operación: {err}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


#---------------------------------------------------------------------------------------------------------------------------------------------------------------------

#-------------------------------------------------------------------------Funcion para permisos de usuario---------------------------------------------------------------------


def aplicar_permisos_usuario():

    if jerarquia_actual == "solo_lectura":
        boton_manual.config(state="disabled")
        boton_automatico.config(state="disabled")
        entry_valor.config(state="disabled")
        boton_confirmar.config(state="disabled")

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------



#----------------------------------------------------------------------------Obtencion base de datos--------------------------------------------------------------------

def get_last_row():
    conn = None
    cursor = None
    try:
        # Pedir una conexión del pool
        conn = db_pool.get_connection() 
        cursor = conn.cursor()
        
        cursor.execute("SELECT corriente_in, voltaje_in, potencia_in, corriente_out, voltaje_out, potencia_out FROM mediciones ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        return row if row else (0,0,0,0,0,0)
        
    except mysql.connector.Error as err:
        print(f"Error en get_last_row: {err}")
        return (0,0,0,0,0,0) # Devolver valor default en caso de error
    finally:
        # Devolver la conexión al pool
        if cursor:
            cursor.close()
        if conn:
            conn.close() 


def obtener_ultima_medicion_completa():
    conexion = None
    cursor = None
    try:
        conexion = db_pool.get_connection()
        cursor = conexion.cursor()

        cursor.execute("""
            SELECT id, fecha_hora,
                   corriente_in, corriente_out,
                   voltaje_in, voltaje_out,
                   potencia_in, potencia_out
            FROM mediciones
            ORDER BY id DESC
            LIMIT 1
        """)

        return cursor.fetchone()

    except mysql.connector.Error as err:
        print("Error al obtener medición:", err)
        return None

    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()

# ------------------------------------------------------------------------- Umbrales para las alarmas ----------------------------------------------------------------
#CORRIENTE_MAX = 9.0
#CORRIENTE_MIN = 0.5
#VOLTAJE_MAX = 75.0
#VOLTAJE_MIN = 10.0
#POTENCIA_MAX = 250.0
#POTENCIA_MIN = 50.0


# Variable para controlar qué etiquetas están parpadeando actualmente
labels_parpadeando = set()
COLOR_ALARMA = "#855454"
COLOR_NORMAL_FONDO = "#353E44"
COLOR_NORMAL_TEXTO = "white"
INTERVALO_PARPADEO = 400 # Milisegundos (0.4 segundos)

# Diccionario para gestionar el estado de las alarmas y evitar popups repetitivos
alarmas_activas = {
    "corriente_in": False, "corriente_out": False,
    "voltaje_in": False, "voltaje_out": False,
    "potencia_in": False, "potencia_out": False
}

#---------------------------------------------------------------------------Codigo para las Alertas------------------------------------------------------------------

#-------------------------------------------limites para los popup de Alertas-------------------------------------------

def actualizar_limites_desde_bd():
    global limites_operacion

    configs = obtener_config_alarmas()

    # Reiniciar estructura completa
    limites_operacion = {
        "corriente_in":  {"min": None, "max": None},
        "corriente_out": {"min": None, "max": None},
        "voltaje_in":    {"min": None, "max": None},
        "voltaje_out":   {"min": None, "max": None},
        "potencia_in":   {"min": None, "max": None},
        "potencia_out":  {"min": None, "max": None}
    }

    for config in configs:

        variable = config["variable"]     # <-- clave real
        operador = config["operador"]
        umbral = config["umbral"]

        if variable not in limites_operacion:
            continue

        if operador in (">", ">="):
            limites_operacion[variable]["max"] = umbral

        elif operador in ("<", "<="):
            limites_operacion[variable]["min"] = umbral



#-------------------------------------------Configuración de Alertas-------------------------------------------


def obtener_config_alarmas():
    conexion = None
    cursor = None
    try:
        conexion = db_pool.get_connection()
        cursor = conexion.cursor(dictionary=True)


        cursor.execute("""
            SELECT codigo, condicion, descripcion, categoria,
                    operador, umbral, variable
            FROM config_alarmas
            WHERE habilitada = 1
        """)

        return cursor.fetchall()

    except mysql.connector.Error as err:
        print("Error config alarmas:", err)
        return []

    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()
            

#-------------------------------------------Evaluacion de Alertas-------------------------------------------

def evaluar_alarma(config, valor_medido):
    op = config["operador"]
    umbral = config["umbral"]

    if op == ">" and valor_medido > umbral:
        return True
    if op == "<" and valor_medido < umbral:
        return True
    if op == ">=" and valor_medido >= umbral:
        return True
    if op == "<=" and valor_medido <= umbral:
        return True

    return False

#-------------------------------------------Generacion de Alertas-------------------------------------------

def generar_alerta(condicion, codigo, descripcion, categoria, valor):
    conexion = db_pool.get_connection()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT id FROM alarmas
        WHERE codigo = %s AND estado = 'Activa'
        ORDER BY id DESC LIMIT 1
    """, (codigo,))

    if cursor.fetchone() is None:
        # Buscamos qué usuario tiene la sesión abierta (inició sesión y todavía no la cerró)
        # justo en el momento en que se dispara la alarma.
        cursor.execute("""
            SELECT usuario_id FROM registro_usuarios
            WHERE hora_salida IS NULL
            ORDER BY hora_inicio DESC
            LIMIT 1
        """)
        fila_sesion = cursor.fetchone()
        usuario_id = fila_sesion[0] if fila_sesion else None

        cursor.execute("""
            INSERT INTO alarmas
            (condicion, codigo, descripcion, estado, categoria, valor, hora_inicio, usuario_id)
            VALUES (%s, %s, %s, 'Activa', %s, %s, NOW(), %s)
        """, (condicion, codigo, descripcion, categoria, valor, usuario_id))
        conexion.commit()

    cursor.close()
    conexion.close()

#---------------------------------------------Resolver Alertas--------------------------------------------


def resolver_alerta(codigo):
    conexion = db_pool.get_connection()
    cursor = conexion.cursor()

    cursor.execute("""
        UPDATE alarmas
        SET estado = 'Resuelta', hora_fin = NOW()
        WHERE codigo = %s AND estado = 'Activa'
    """, (codigo,))

    if cursor.rowcount > 0:
        conexion.commit()

    cursor.close()
    conexion.close()

#---------------------------------------------Procesar Alertas--------------------------------------------


def procesar_alarmas(fila_medicion):
    _, _, corriente_in, corriente_out, voltaje_in, voltaje_out, potencia_in, potencia_out = fila_medicion

    configs = obtener_config_alarmas()

    for config in configs:
        categoria = config["categoria"]
        codigo = config["codigo"]

        if categoria == "Voltaje":
            valor = voltaje_in
        elif categoria == "Corriente":
            valor = corriente_in
        elif categoria == "Potencia":
            valor = potencia_out
        else:
            continue

        if evaluar_alarma(config, valor):
            generar_alerta(
                config["condicion"],
                codigo,
                config["descripcion"],
                categoria,
                valor
            )
        else:
            resolver_alerta(codigo)

#--------------------------------------Funcion para obtener las Alertas-------------------------------------


def obtener_alarmas_config_admin():
    conexion = None
    cursor = None
    try:
        conexion = db_pool.get_connection()
        cursor = conexion.cursor()

        cursor.execute("""
            SELECT id, condicion, codigo, descripcion, categoria, operador, umbral, habilitada
            FROM config_alarmas
            ORDER BY categoria, codigo
        """)

        return cursor.fetchall()

    except mysql.connector.Error as err:
        messagebox.showerror("Error BD", f"No se pudieron leer las alarmas:\n{err}")
        return []

    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()

#--------------------------------------Funcion para actualizar las Alertas-------------------------------------

def actualizar_alarma_config(id_alarma, operador, umbral, habilitada):

    actualizar_limites_desde_bd()
    conexion = None
    cursor = None
    try:
        conexion = db_pool.get_connection()
        cursor = conexion.cursor()

        cursor.execute("""
            UPDATE config_alarmas
            SET operador = %s,
                umbral = %s,
                habilitada = %s,
                usuario_id = %s,
                fecha_modificacion = NOW()
            WHERE id = %s
        """, (operador, umbral, habilitada, usuario_actual_id, id_alarma))

        conexion.commit()
        messagebox.showinfo("Éxito", "Configuración de alarma actualizada")

    except mysql.connector.Error as err:
        messagebox.showerror("Error BD", f"No se pudo actualizar:\n{err}")

    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()

#------------------------------------------Funcion para crear las Alertas---------------------------------------

def crear_alarma_config(condicion, codigo, descripcion, categoria, operador, umbral, habilitada):

    actualizar_limites_desde_bd()
    if jerarquia_actual != "administrador":
        messagebox.showerror("Error", "Permisos insuficientes.")
        return

    if not condicion or not codigo or not descripcion or not categoria or not operador:
        messagebox.showwarning("Datos incompletos", "Complete todos los campos.")
        return

    try:
        umbral = float(umbral)
    except ValueError:
        messagebox.showerror("Error", "El umbral debe ser numérico.")
        return

    conexion = None
    cursor = None
    try:
        conexion = db_pool.get_connection()
        cursor = conexion.cursor()

        cursor.execute("""
            INSERT INTO config_alarmas
            (condicion, codigo, descripcion, categoria, operador, umbral, habilitada, usuario_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            condicion,
            codigo,
            descripcion,
            categoria,
            operador,
            umbral,
            habilitada,
            usuario_actual_id
        ))

        conexion.commit()
        messagebox.showinfo("Éxito", "Alarma creada correctamente.")

    except mysql.connector.Error as err:
        messagebox.showerror("Error BD", f"No se pudo crear la alarma:\n{err}")

    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()

#------------------------------------------Funcion para eliminar las Alertas---------------------------------------

def eliminar_alarma_seleccionada():

    actualizar_limites_desde_bd()
    if jerarquia_actual != "administrador":
        messagebox.showerror(
            "Permiso denegado",
            "Solo el administrador puede eliminar alarmas."
        )
        return

    alarma_id = alarma_seleccionada.get("id")
    if not alarma_id:
        messagebox.showwarning(
            "Sin selección",
            "Seleccione una alarma para eliminar."
        )
        return

    confirmar = messagebox.askyesno(
        "Confirmar eliminación",
        "¿Está seguro de eliminar esta alarma?\nEsta acción no se puede deshacer."
    )

    if not confirmar:
        return

    conexion = None
    cursor = None
    try:
        conexion = db_pool.get_connection()
        cursor = conexion.cursor()

        cursor.execute(
            "DELETE FROM config_alarmas WHERE id = %s",
            (alarma_id,)
        )

        conexion.commit()
        messagebox.showinfo("Éxito", "Alarma eliminada correctamente.")

        alarma_seleccionada.clear()

        if ventana_config_alertas:
            ventana_config_alertas.destroy()

        abrir_configuracion_alertas()

    except mysql.connector.Error as err:
        messagebox.showerror(
            "Error BD",
            f"No se pudo eliminar la alarma:\n{err}"
        )

    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()



#-----------------------------------------Popup de configuracion de Alertas-------------------------------------


def abrir_configuracion_alertas():
    global ventana_config_alertas
    if jerarquia_actual != "administrador":
        messagebox.showwarning(
            "Acceso denegado",
            "Solo el administrador puede configurar alertas."
        )
        return


    popup_config_alertas = Toplevel()
    popup_config_alertas.title("Configuración de alertas")
    popup_config_alertas.config(bg="#5F686F")  # fondo general oscuro

    # Centrar la ventana en la pantalla
    window_width = 900
    window_height = 530
    screen_width = popup_config_alertas.winfo_screenwidth()
    screen_height = popup_config_alertas.winfo_screenheight()
    center_x = int(screen_width/2 - window_width / 2)
    center_y = int(screen_height/2 - window_height / 2)
    popup_config_alertas.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
    popup_config_alertas.resizable(False, False)

    # Icono (opcional)
    try:
        popup_config_alertas.iconbitmap("icono.ico")
    except Exception:
        pass


    # Configurar de filas y columnas que puedan expandirse
    popup_config_alertas.grid_rowconfigure(0, weight=1)  # Fila del título
    popup_config_alertas.grid_rowconfigure(1, weight=1)  # Fila de configuracion alarmas
    popup_config_alertas.grid_rowconfigure(2, weight=1)  # Fila de configuracion alarmas


    popup_config_alertas.grid_columnconfigure(0, weight=1)  # Columna 1
    popup_config_alertas.grid_columnconfigure(1, weight=1)  # Columna 1

    #-------------------------------- Frame superior --------------------------------
    etiqueta_popup_configalarmas = Frame(popup_config_alertas, bg="#353E44", height=50)
    etiqueta_popup_configalarmas.grid(row=0, column=0, columnspan=2, sticky="enw")

    # Label principal "alertas"
    label_usuarios1 = tk.Label(etiqueta_popup_configalarmas, text="⚠ Gestión de alertas", font=("Arial", 18, "bold"), bg="#353E44", fg="white")
    label_usuarios1.grid(row=0, column=0, sticky="w", padx=10, pady=10)

    # Subtítulo
    label_usuarios2 = tk.Label(etiqueta_popup_configalarmas, text="Configuración de alertas del sistema", font=("Arial", 11), bg="#353E44", fg="lightgray")
    label_usuarios2.grid(row=0, column=1, sticky="w", padx=5, pady=10)

    #-------------------------------- Frame inferior --------------------------------


    #---------------------------------------------- Estilos -----------------------------------------------
    style = ttk.Style()
    style.theme_use("default")

    # Fondo del Treeview
    style.configure("Dark.Treeview", background="#FFFFFF", foreground="#000000", rowheight=28, fieldbackground="#353E44",  font=("Segoe UI", 10))

    # Encabezados
    style.configure("Dark.Treeview.Heading", background="#353E44", foreground="white", font=("Segoe UI", 10, "bold"))

    # Para cambiar el color de la fila seleccionada
    style.map("Dark.Treeview", background=[("selected", "#4A6984")])

    # Columna seleccionada
    style.map("Dark.Treeview.Heading", background=[("selected", "#4A6984")], foreground=[("selected", "white")])


    #Estilo Barras
       

    style.configure("Dark.Vertical.TScrollbar",
                    gripcount=0,
                    background="#5F686F",      # color del thumb
                    darkcolor="#353E44",       # borde oscuro
                    lightcolor="#353E44",      # borde claro
                    troughcolor="#353E44",     # canaleta
                    bordercolor="#353E44",
                    arrowcolor="white")
        
    style.map("Dark.Vertical.TScrollbar",
              background=[("active", "#6D7275")]) # Sirve para cambiar el color cuando el mouse esta encima de la barra
    

    #----------------------------------------------------------------------------------------------------------------

    frame_alertas = Frame(popup_config_alertas, bg="#5F686F")
    frame_alertas.grid(row=1, column=0,columnspan=2, sticky="enw")

    label_Configalertas1 = tk.Label(frame_alertas, text="Alertas existentes", font=("Arial", 14, "bold"), bg="#5F686F", fg="white")
    label_Configalertas1.grid(row=0, column=0, pady=10, padx=0)

    columnas = ("id","condicion", "codigo", "descripcion", "categoria", "operador", "umbral", "habilitada")

    tree = ttk.Treeview( frame_alertas, columns=columnas, show="headings", height=4, selectmode="browse", style="Dark.Treeview")

    #tree.column("id", width=0, stretch=False)

    tree.heading("id", text="id")
    tree.heading("condicion", text="Condicion")
    tree.heading("codigo", text="Codigo")
    tree.heading("descripcion", text="Descripcion")
    tree.heading("categoria", text="Categoria")
    tree.heading("operador", text="Operador")
    tree.heading("umbral", text="Umbral")
    tree.heading("habilitada", text="Habilitada")

    tree.column("id", width=40, anchor="center")
    tree.column("condicion", width=120, anchor="w")
    tree.column("codigo", width=70, anchor="center")
    tree.column("descripcion", width=270, anchor="w")
    tree.column("categoria", width=100, anchor="center")
    tree.column("operador", width=80, anchor="center")
    tree.column("umbral", width=100, anchor="center")
    tree.column("habilitada", width=100, anchor="center")

    #for col in columnas:
        #tree.heading(col, text=col.capitalize())
        #tree.column(col, width=110)


    scroll_y = ttk.Scrollbar(frame_alertas, orient="vertical", command=tree.yview, style="Dark.Vertical.TScrollbar")
    tree.configure(yscrollcommand=scroll_y.set)
    scroll_y.grid(row=1, column=1, sticky="ns")

    frame_alertas.grid_columnconfigure(0, weight=1)
    frame_alertas.grid_rowconfigure(1, weight=1)

    tree.grid(row=1, column=0, sticky="ns")#,fill="x")

    alarmas = obtener_alarmas_config_admin()
    for alarma in alarmas:
        tree.insert("", "end", values=alarma)

    Button(frame_alertas,text="Eliminar alerta",fg="white",bg="#8B3A3A",command=eliminar_alarma_seleccionada).grid(row=2, column=0,pady=10, sticky="ns")

    # ------------------ edición ------------------

    frame_edit = Frame(popup_config_alertas, bg="#5F686F")
    frame_edit.grid(row=2, column=0, sticky="n")

    Label(frame_edit, text="Modificar alerta", font=("Arial", 13, "bold"), bg="#5F686F", fg="white").grid(row=0, column=0, columnspan=2, pady=5)

    Label(frame_edit, text="Operador", bg="#5F686F", fg="white").grid(row=1, column=0, padx=5)
    combo_op = ttk.Combobox(frame_edit, values=[">", "<", ">=", "<="],width=18, state="readonly")
    combo_op.grid(row=1, column=1)

    Label(frame_edit, text="Umbral", bg="#5F686F", fg="white").grid(row=2, column=0, padx=5)
    entry_umbral = Entry(frame_edit)
    entry_umbral.grid(row=2, column=1)

    var_hab = IntVar(value=1)
    chk = Checkbutton(frame_edit, text="Habilitada",variable=var_hab, onvalue=1, offvalue=0,fg="black", bg="#5F686F", activebackground="#5F686F")
    chk.grid(row=3, column=1, sticky="w")

    #alarma_seleccionada = {"id": None}

    def seleccionar(event):
        item = tree.selection()
        if not item:
            return

        valores = tree.item(item[0], "values")

        alarma_seleccionada["id"] = valores[0]

        combo_categoria.set(valores[4])
        combo_op.set(valores[5])

        entry_umbral.delete(0, END)
        entry_umbral.insert(0, valores[6])

        var_hab.set(int(valores[7]))



    tree.bind("<<TreeviewSelect>>", seleccionar)

    def guardar():
        if alarma_seleccionada["id"] is None:
            messagebox.showwarning("Aviso", "Seleccione una alarma")
            return

        try:
            umbral = float(entry_umbral.get())
        except ValueError:
            messagebox.showerror("Error", "Umbral inválido")
            return

        actualizar_alarma_config(
            alarma_seleccionada["id"],
            combo_op.get(),
            umbral,
            var_hab.get()
        )

        popup_config_alertas.destroy()
        abrir_configuracion_alertas()  # refrescar

    Button(frame_edit, text="Guardar cambios", command=guardar).grid(row=4, column=0, columnspan=2, sticky="ns")

    


# ------------------ Alta de alarma ------------------

    frame_alta = Frame(popup_config_alertas, bg="#5F686F")
    frame_alta.grid(row=2, column=1, sticky="n")

    Label(frame_alta, text="Nueva alerta", font=("Arial", 13, "bold"), bg="#5F686F", fg="white").grid(row=0, column=0, columnspan=2, pady=5)

    Label(frame_alta, text="Condición", bg="#5F686F", fg="white").grid(row=1, column=0)
    entry_condicion = Entry(frame_alta)
    entry_condicion.grid(row=1, column=1)

    Label(frame_alta, text="Código", bg="#5F686F", fg="white").grid(row=2, column=0)
    entry_codigo = Entry(frame_alta)
    entry_codigo.grid(row=2, column=1)

    Label(frame_alta, text="Descripción", bg="#5F686F", fg="white").grid(row=3, column=0)
    entry_descripcion = Entry(frame_alta)
    entry_descripcion.grid(row=3, column=1)

    Label(frame_alta, text="Categoría", bg="#5F686F", fg="white").grid(row=4, column=0)
    combo_categoria = ttk.Combobox(
    frame_alta,
    values=["Voltaje", "Corriente", "Potencia"],width=18,
    state="readonly"
    )
    combo_categoria.grid(row=4, column=1)

    Label(frame_alta, text="Operador", bg="#5F686F", fg="white").grid(row=5, column=0)
    combo_operador = ttk.Combobox(
        frame_alta,
        values=[">", "<", ">=", "<="],width=18,
        state="readonly"
    )
    combo_operador.grid(row=5, column=1)

    Label(frame_alta, text="Umbral", bg="#5F686F", fg="white").grid(row=6, column=0)
    entry_umbral_nuevo = Entry(frame_alta)
    entry_umbral_nuevo.grid(row=6, column=1)

    var_habilitada_nueva = IntVar(value=1)
    Checkbutton(
        frame_alta,
        text="Habilitada",
        variable=var_habilitada_nueva,fg="black", bg="#5F686F", activebackground="#5F686F"
    ).grid(row=7, column=1)

    Button(
        frame_alta,
        text="Agregar alerta",
        command=lambda: crear_alarma_config(
            entry_condicion.get(),
            entry_codigo.get(),
            entry_descripcion.get(),
            combo_categoria.get(),
            combo_operador.get(),
            entry_umbral_nuevo.get(),
            var_habilitada_nueva.get()
        )
    ).grid(row=8, column=0, columnspan=2, pady=5)


#----------------------------------------------------------------------------Funcion popup Alertas-------------------------------------------------------------------

def cargar_alertas(popupAlertas_tree):
    conn = None
    cursor = None
    try:
        # Pedir una conexión del pool
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT a.condicion, a.codigo, a.descripcion, a.estado, a.categoria, a.valor,
                   a.hora_inicio, a.hora_fin, COALESCE(u.usuario, '-') AS usuario
            FROM alarmas a
            LEFT JOIN usuarios u ON a.usuario_id = u.id
            WHERE a.estado = 'Activa'
            ORDER BY a.id DESC
            LIMIT 50
        """)
        registros = cursor.fetchall()

        # Limpiar tabla
        for row in popupAlertas_tree.get_children():
            popupAlertas_tree.delete(row)

        # Insertar registros en la tabla visual con filas alternadas
        for i, r in enumerate(registros):
            if i % 2 == 0:
                popupAlertas_tree.insert("", "end", values=r, tags=("evenrow",))
            else:
                popupAlertas_tree.insert("", "end", values=r, tags=("oddrow",))
                
    except mysql.connector.Error as err:
        print(f"Error en cargar_alertas: {err}")
    finally:
        # Devolver la conexión al pool
        if cursor:
            cursor.close()
        if conn:
            conn.close()



#----------------------------------------------------------------------- Inicio de la App SCADA Principal ----------------------------------------------------------
def run_main_scada_app(usuario_id):
    """
    Esta función contiene TODA la lógica de la aplicación SCADA principal.
    Solo se llama DESPUÉS de un inicio de sesión exitoso.
    El 'usuario_id' se pasa por si se quiere usar en el futuro.
    """
    global boton_manual, boton_automatico, entry_valor, boton_confirmar
    global boton_configurar_usuario
 
    #----------------------------------------------------------------------------Datos BD--------------------------------------------------------------------------
    def get_corriente1():
        return last_values[0]  # corriente de entrada simulada

    def get_corriente2():
        return last_values[3]  # corriente de salida simulada

    def get_voltaje1():
        return last_values[1]  # voltaje de entrada simulada

    def get_voltaje2():
        return last_values[4]  # voltaje de salida simulada

    def get_potencia1():
        return last_values[2]  # potencia de entrada simulada

    def get_potencia2():
        return last_values[5]  # potencia de salida simulada

# ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
#                                                                           Creacion de la Pantalla Principal 
# ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    raiz = Tk()
    raiz.title("Scada Panel Solar")
    raiz.config(bg="#5F686F")

    actualizar_limites_desde_bd()


    # Cambio de icono
    #raiz.iconbitmap("icono.ico")
    try:
        raiz.iconbitmap("icono.ico")
    except Exception:
        pass

    # Hacer la ventana en pantalla completa
    raiz.attributes("-fullscreen", True)

    def salir_pantalla_completa(event):
        raiz.attributes("-fullscreen", False)

    # Detectar la tecla 'Esc' para salir de pantalla completa
    raiz.bind("<Escape>", salir_pantalla_completa)

    # Configurar para que las filas y columnas puedan expandirse
    raiz.grid_rowconfigure(0, weight=1)  # Fila del título
    raiz.grid_rowconfigure(1, weight=1)  # Fila de los primeros frames
    raiz.grid_rowconfigure(2, weight=1)  # Fila del frame inferior
    raiz.grid_rowconfigure(3, weight=1)  # Fila del frame más abajo

    raiz.grid_columnconfigure(0, weight=1)  # Columna 1 (primer frame)
    raiz.grid_columnconfigure(1, weight=1)  # Columna 2 (frame central)
    raiz.grid_columnconfigure(2, weight=1)  # Columna 3 (último frame)

    # Texto centrado en la ventana principal
    miLabel = Label(raiz, text="SCADA Paneles Solares", fg="white", bg="#5F686F", font=("arial", 40, "bold"))
    miLabel.grid(row=0, column=0, columnspan=3,padx=0, pady=0, sticky="nsew")  # Centrado en la ventana

    # Imagenes de logos de la faculta

    imagen_izq = Image.open("imagenunsl.png")       #con esto cargo la imagen
    imagen_izq = ImageTk.PhotoImage(imagen_izq)     #con esto la paso a un formato que lo entiende tkinter

    etiqueta_imagenizq = Label(raiz, image=imagen_izq, bg="#5F686F")    #Lo añado a la raiz
    etiqueta_imagenizq.grid(row=0, column=0,padx=30, sticky="w")                #Lo acomodo


    imagen_der = Image.open("imagenfica.png")       #con esto cargo la imagen
    imagen_der = ImageTk.PhotoImage(imagen_der)     #con esto la paso a un formato que lo entiende tkinter

    etiqueta_imagender = Label(raiz, image=imagen_der, bg="#5F686F")    #Lo añado a la raiz
    etiqueta_imagender.grid(row=0, column=2,padx=30,sticky="e")                #Lo acomodo


    # Función para cerrar la ventana principal
    def cerrar_ventana():
        global cerrando_app
        cerrando_app = True
        registrar_logout()
        raiz.destroy()
        # No cerramos la conexión aquí, el pool se maneja solo.



    etiqueta_angulo_actual = Label(raiz)
    etiqueta_imagen = Label(raiz)

    # ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    #                                                                                   Funciones 
    # ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    #-----------------Función para actualizar la fecha y hora-------------------------

    def actualizar_fecha_hora():
        if cerrando_app:
            return
        # Obtener fecha y hora actuales
        locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')        #De esta forma obtengo los meses en español
        ahora = datetime.now()
        formato_fecha_hora = ahora.strftime("Fecha y hora: %d/%m/%Y - %H:%M hs")  # Formato: "Fecha y hora: DD/MM/AAAA - HH:MM"
        etiqueta_fecha_hora.config(text=formato_fecha_hora)  # Actualizar el texto del Label
        
        # Llamar a esta función de nuevo después de 60000ms (1 minuto)
        etiqueta_fecha_hora.after(60000, actualizar_fecha_hora)
        
    #--------------------------------------------------------------------------------

    #-----Función para leer el archivo de Excel y mostrar el ángulo del mes actual---

    def mostrar_angulo_mesexcel():
        try:
        # Obtener ángulo óptimo desde la base de datos
            angulo_db = obtener_angulo_automatico()

            if angulo_db is not None:
                global angulo_horizontal, angulo_actual, ultimo_angulo_optimo

                angulo_horizontal = angulo_db
                ultimo_angulo_optimo = angulo_horizontal

                mes_actual = datetime.now().strftime("%B")

            # Actualizar interfaz
                datos_label_mes.config(text=f"Mes actual: {mes_actual}")
                datos_label_angulo.config(
                    text=f"Ángulo Horizontal óptimo: {angulo_horizontal}°"
                )

            # Si el modo es Automático, aplicar el ángulo
                if modo_actual == "Automático":
                    angulo_actual = angulo_horizontal
                    mostrar_angulo_mes()
                    actualizar_imagen_angulo(angulo_actual)

            else:
                messagebox.showwarning(
                    "Sin datos",
                    "No hay datos de ángulo óptimo para el mes actual en la base de datos."
                )

        except Exception as e:
            messagebox.showerror("Error", f"Se produjo un error: {e}")

    # Programar la próxima actualización en 24 horas
        raiz.after(86400000, mostrar_angulo_mesexcel)


    #--------------------------------------------------------------------------------


    #--------Función para mostrar el ángulo actual en el modo de operación-----------

    def mostrar_angulo_mes():
        etiqueta_angulo_actual.config(text=f"Ángulo Actual: {angulo_actual}°")

    #--------------------------------------------------------------------------------


    #------------------------------imagen--------------------------------------------

    # Función para actualizar la imagen basada en el ángulo
    def actualizar_imagen_angulo(angulo):
        # Determina la imagen a mostrar según el ángulo
        if 0 <= angulo <= 9:
            nueva_imagen = Image.open("Imagen1.png")
        elif 10 <= angulo <= 19:
            nueva_imagen = Image.open("Imagen2.png")
        elif 20 <= angulo <= 29:
            nueva_imagen = Image.open("Imagen3.png")
        elif 30 <= angulo <= 39:
            nueva_imagen = Image.open("Imagen4.png")
        elif 40 <= angulo <= 49:
            nueva_imagen = Image.open("Imagen5.png")
        elif 50 <= angulo <= 59:
            nueva_imagen = Image.open("Imagen6.png")
        elif 60 <= angulo <= 69:
            nueva_imagen = Image.open("Imagen7.png")
        elif 70 <= angulo <= 79:
            nueva_imagen = Image.open("Imagen8.png")
        elif 80 <= angulo <= 89:
            nueva_imagen = Image.open("Imagen9.png")
        elif angulo == 90:
            nueva_imagen = Image.open("Imagen10.png")

        # Actualizar la imagen en el Label
        nueva_imagen = ImageTk.PhotoImage(nueva_imagen)
        etiqueta_imagen.config(image=nueva_imagen)
        etiqueta_imagen.image = nueva_imagen  # Necesario para evitar que Python elimine la imagen de memoria

    #--------------------------------------------------------------------------------


    #---------------------------Funciones modo de operacion---------------------------

    def mostrar_angulo_mes():
        # Mostrar el ángulo actual
        etiqueta_angulo_actual.config(text=f"Angulo Actual: {angulo_actual}°")

    #--------------------------------------------------------------------------------


    #--------Función para confirmar el cambio de modo, solo si es necesario----------
    def confirmar_cambio_modo(nuevo_modo):
        global modo_actual
        if nuevo_modo != modo_actual:
            respuesta = messagebox.askyesno("Confirmación", f"¿Está seguro que desea cambiar a modo {nuevo_modo}?")
            if respuesta:
                cambiar_modo(nuevo_modo)
    #--------------------------------------------------------------------------------

    #-----Función para cambiar el modo manual o automático con cambio de colores-----
    def cambiar_modo(nuevo_modo):
        if jerarquia_actual == "solo_lectura":
            messagebox.showwarning(
                "Acceso denegado",
                "Usuario en modo solo lectura. No puede cambiar el modo de operación."
            )
            return

        global modo_actual
        modo_actual = nuevo_modo
        if modo_actual == "Manual":
            boton_manual.config(bg="#6D8A6B", fg="white")
            boton_automatico.config(bg="gray", fg="black")  # Cambia a gris el botón de Automático
            entry_valor.config(state="normal", fg="black", bg="white")  # Habilitar el campo de entrada en modo Manual
            boton_confirmar.config(bg="#6D8A6B")

            # REGISTRO EN BD (MODO MANUAL)
            #registrar_modo_operacion("Manual", angulo_actual)

        else:
            boton_manual.config(bg="gray", fg="black")  # Cambia a gris el botón de Manual
            boton_automatico.config(bg="#A89F75", fg="white")
            entry_valor.delete(0,END)           #lo utilizo para borrar el valor ingresado
            entry_valor.config(state="disabled", fg="light gray")  # Deshabilitar el campo de entrada en modo Automático
            boton_confirmar.config(bg="gray")
            mostrar_angulo_mesexcel()                                                       #Esto es para actualizar el angulo actual al estar en automatico
            
            # REGISTRO EN BD (MODO AUTOMÁTICO)
            registrar_modo_operacion("Automatico", angulo_horizontal)
            #etiqueta_angulo_actual.config(text=f"Ángulo Actual: {ultimo_angulo_optimo}")   #Esto es para actualizar el angulo actual al estar en automatico
            #actualizar_imagen_angulo(angulo_actual)
    #--------------------------------------------------------------------------------


    #----Función para procesar el valor ingresado al presionar el botón de envío-----
    def procesar_valor():

        if jerarquia_actual == "visor":
            messagebox.showwarning(
                "Acceso denegado",
                "Este usuario no puede modificar valores."
        )
            return
    
        global angulo_deseado, angulo_actual  # Variables globales para almacenar el ángulo deseado y actual



        if modo_actual == "Automático":
            messagebox.showwarning("Advertencia", "No se puede ingresar un valor en modo Automático.")
        else:
            valor_ingresado = entry_valor.get()
            if valor_ingresado:
                try:
                    angulo = int(valor_ingresado)
                    if 0 <= angulo <= 90:
                        respuesta = messagebox.askyesno("Valor ingresado", f"Esta seguro de cambiar el angulo a: {angulo}°")
                        if respuesta:
                            angulo_deseado = angulo  # Guarda el ángulo en la variable global angulo_deseado
                            angulo_actual = angulo  # Actualiza el ángulo actual con el valor ingresado
                            mostrar_angulo_mes()  # Actualiza la etiqueta para mostrar el nuevo ángulo actual -------------ver si es necesario---------------
                            actualizar_imagen_angulo(angulo_actual)
                            entry_valor.delete(0,END)       #lo utilizo para borrar el valor ingresado

                             # REGISTRO EN BD (MODO MANUAL)
                            registrar_modo_operacion("Manual", angulo_actual)
                            
                    else:
                        messagebox.showwarning("Valor no válido", "El valor debe estar entre 0° y 90°.")
                        entry_valor.delete(0,END)       #lo utilizo para borrar el valor ingresado
                except ValueError:
                    messagebox.showwarning("Valor no válido", "Por favor, ingrese un número válido.")
                    entry_valor.delete(0,END)       #lo utilizo para borrar el valor ingresado
            else:
                messagebox.showwarning("Campo vacío", "Por favor, ingrese un ángulo.")
    #--------------------------------------------------------------------------------

    # ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    #                                                                           Funciones Del PopUp
    # ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    # --------------------------------------------------------------------------PopUp configuracion alertas y usuarios------------------------------------------------------------------------------
    def abrir_configuracion():
        global tree_usuarios
        if jerarquia_actual != "administrador":
            messagebox.showwarning(
                "Acceso denegado",
                "Solo el administrador puede acceder a la configuración."
            )
            return

        popup_config_usuarios = Toplevel()
        popup_config_usuarios.title("Configuracion de usuarios")
        popup_config_usuarios.config(bg="#5F686F")  # fondo general oscuro

        # Centrar la ventana en la pantalla
        window_width = 800
        window_height = 300
        screen_width = popup_config_usuarios.winfo_screenwidth()
        screen_height = popup_config_usuarios.winfo_screenheight()
        center_x = int(screen_width/2 - window_width / 2)
        center_y = int(screen_height/2 - window_height / 2)
        popup_config_usuarios.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
        popup_config_usuarios.resizable(False, False)

                # Icono (opcional)
        try:
            popup_config_usuarios.iconbitmap("icono.ico")
        except Exception:
            pass

        # Configurar de filas y columnas que puedan expandirse
        popup_config_usuarios.grid_rowconfigure(0, weight=1)  # Fila del título
        popup_config_usuarios.grid_rowconfigure(1, weight=1)  # Fila de configuracion usuarios

        popup_config_usuarios.grid_columnconfigure(0, weight=1)  # Columna 1
        popup_config_usuarios.grid_columnconfigure(1, weight=1)  # Columna 2

        #-------------------------------- Frame superior --------------------------------
        etiqueta_popup_configUsuarios = Frame(popup_config_usuarios, bg="#353E44", height=50)
        etiqueta_popup_configUsuarios.grid(row=0, column=0, columnspan=2, sticky="enw")

        # Label principal "alertas"
        label_usuarios1 = tk.Label(etiqueta_popup_configUsuarios, text="👤 Gestión de usuarios", font=("Arial", 18, "bold"), bg="#353E44", fg="white")
        label_usuarios1.grid(row=0, column=0, sticky="w", padx=10, pady=10)

        # Subtítulo
        label_usuarios2 = tk.Label(etiqueta_popup_configUsuarios, text="Configuración de acceso al sistema", font=("Arial", 11), bg="#353E44", fg="lightgray")
        label_usuarios2.grid(row=0, column=1, sticky="w", padx=5, pady=10)


        #-------------------------------- Frame inferior --------------------------------
        #------------------------------interfaz para crear usuario-----------------------
        frame_usuarios = Frame(popup_config_usuarios, bg="#5F686F")
        frame_usuarios.grid(row=1, column=0, sticky="enw")

        label_Configusuarios1 = tk.Label(frame_usuarios, text="Alta de usuario", font=("Arial", 12, "bold"), bg="#5F686F", fg="white")
        label_Configusuarios1.grid(row=0, column=0, columnspan=2, pady=10, padx=100)

        label_Configusuarios2 = tk.Label(frame_usuarios, text="Usuario:", bg="#5F686F", fg="white")
        label_Configusuarios2.grid(row=1, column=0, sticky="e")

        entry_nuevo_usuario = Entry(frame_usuarios)
        entry_nuevo_usuario.grid(row=1, column=1)

        label_Configusuarios3 = tk.Label(frame_usuarios, text="Contraseña:", bg="#5F686F", fg="white")
        label_Configusuarios3.grid(row=2, column=0, sticky="e")

        entry_nueva_password = Entry(frame_usuarios, show="*")
        entry_nueva_password.grid(row=2, column=1)

        label_Configusuarios4 = tk.Label(frame_usuarios, text="Jerarquía:", bg="#5F686F", fg="white")
        label_Configusuarios4.grid(row=3, column=0, sticky="e")

        combo_jerarquia = ttk.Combobox( frame_usuarios, values=["admin", "operador", "solo_lectura"],width=18, state="readonly")
        combo_jerarquia.grid(row=3, column=1)
        combo_jerarquia.current(1)

        #-------------------------------------------------------------

        Button(frame_usuarios,text="Crear usuario", bg="#353E44", fg="#FFFFFF",command=lambda: crear_usuario(entry_nuevo_usuario.get(),entry_nueva_password.get(),combo_jerarquia.get())).grid(row=4, column=0, columnspan=2, pady=10)

        


        #-------------------------------- Estilos --------------------------------
        style = ttk.Style()
        style.theme_use("default")

        # Fondo del Treeview
        style.configure("Dark.Treeview", background="#FFFFFF", foreground="#000000", rowheight=28, fieldbackground="#353E44",  font=("Segoe UI", 10))

        # Encabezados
        style.configure("Dark.Treeview.Heading", background="#353E44", foreground="white", font=("Segoe UI", 10, "bold"))

        # Para cambiar el color de la fila seleccionada
        style.map("Dark.Treeview", background=[("selected", "#4A6984")])

        # Columna seleccionada
        style.map("Dark.Treeview.Heading", background=[("selected", "#4A6984")], foreground=[("selected", "white")])


        #Estilo Barras
       

        style.configure("Dark.Vertical.TScrollbar",
                    gripcount=0,
                    background="#5F686F",      # color del thumb
                    darkcolor="#353E44",       # borde oscuro
                    lightcolor="#353E44",      # borde claro
                    troughcolor="#353E44",     # canaleta
                    bordercolor="#353E44",
                    arrowcolor="white")
        
        style.map("Dark.Vertical.TScrollbar",
              background=[("active", "#6D7275")]) # Sirve para cambiar el color cuando el mouse esta encima de la barra
        
        #------------------- listado de usuarios --------------------

        frame_lista = Frame(popup_config_usuarios, bg="#5F686F")
        frame_lista.grid(row=1, column=1, sticky="enw")

        label_usuarios_existentes = tk.Label( frame_lista, text="Usuarios existentes", font=("Arial", 12, "bold"), bg="#5F686F", fg="white")
        label_usuarios_existentes.grid(row=0, column=0, columnspan=2, pady=0, padx=0)

        tree_usuarios = ttk.Treeview(frame_lista, columns=("usuario", "jerarquia"), show="headings", height=4, selectmode="browse", style="Dark.Treeview")

        tree_usuarios.heading("usuario", text="Usuario")
        tree_usuarios.heading("jerarquia", text="Jerarquía")

        tree_usuarios.column("usuario", width=150, anchor="w")
        tree_usuarios.column("jerarquia", width=200, anchor="w")

        scroll_y = ttk.Scrollbar(frame_lista, orient="vertical", command=tree_usuarios.yview, style="Dark.Vertical.TScrollbar")
        tree_usuarios.configure(yscrollcommand=scroll_y.set)
        scroll_y.grid(row=1, column=1, sticky="ns")

        frame_lista.grid_columnconfigure(0, weight=1)
        frame_lista.grid_rowconfigure(1, weight=1)


        tree_usuarios.grid(row=1, column=0, sticky="nsew")

        Button( frame_lista, text="Eliminar usuario seleccionado", bg="#353E44", fg="#F0AFAF", command=lambda: eliminar_usuario_seleccionado()).grid(row=2, column=0, columnspan=2, pady=10)
        
        cargar_usuarios_en_tabla()

    # -------------------------------------------------------------Funcion para crear usuario------------------------------------------------------------------------------------- 
    def crear_usuario(usuario, password, jerarquia):
        if jerarquia_actual != "administrador":
            messagebox.showerror("Error", "Permisos insuficientes.")
            return

        if not usuario or not password or not jerarquia:
            messagebox.showwarning("Datos incompletos", "Complete todos los campos.")
            return

        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()

            conexion = db_pool.get_connection()
            cursor = conexion.cursor()

            cursor.execute(
                "INSERT INTO usuarios (usuario, password_hash, jerarquia) VALUES (%s, %s, %s)",
                (usuario, password_hash, jerarquia)
            )

            conexion.commit()
            messagebox.showinfo("Éxito", "Usuario creado correctamente.")

            cargar_usuarios_en_tabla()

        except mysql.connector.Error as err:
            messagebox.showerror("Error BD", f"No se pudo crear el usuario:\n{err}")

        finally:
            if cursor:
                cursor.close()
            if conexion:
                conexion.close()



    # -------------------------------------------------------------Funcion para eliminar usuario------------------------------------------------------------------------------------- 
    def eliminar_usuario(usuario):

        if jerarquia_actual != "administrador":
            messagebox.showerror("Error", "Permisos insuficientes.")
            return

        if not usuario:
            messagebox.showwarning("Dato requerido", "Ingrese un usuario.")
            return

        if usuario == usuario_logueado:  # si guardás el nombre
            messagebox.showwarning("Acción no permitida", "No puede eliminarse a sí mismo.")
            return

        confirmar = messagebox.askyesno(
            "Confirmar eliminación",
            f"¿Está seguro de eliminar el usuario '{usuario}'?"
        )

        if not confirmar:
            return

        try:
            conexion = db_pool.get_connection()
            cursor = conexion.cursor()

            cursor.execute("DELETE FROM usuarios WHERE usuario = %s", (usuario,))
            conexion.commit()

            if cursor.rowcount == 0:
                messagebox.showwarning("Aviso", "El usuario no existe.")
            else:
                messagebox.showinfo("Éxito", "Usuario eliminado correctamente.")

                cargar_usuarios_en_tabla()


        except mysql.connector.Error as err:
            messagebox.showerror("Error BD", f"No se pudo eliminar el usuario:\n{err}")

        finally:
            if cursor:
                cursor.close()
            if conexion:
                conexion.close()

    # -------------------------------------------------------------Funcion para obtener los usuarios actuales------------------------------------------------------------------------------------- 

    def eliminar_usuario_seleccionado():
        seleccion = tree_usuarios.selection()

        if not seleccion:
            messagebox.showwarning(
                "Sin selección",
                "Seleccione un usuario de la lista."
            )
            return

        valores = tree_usuarios.item(seleccion[0], "values")
        usuario = valores[0]

        eliminar_usuario(usuario)

            
    # -------------------------------------------------------------Funcion para obtener los usuarios actuales------------------------------------------------------------------------------------- 
    def obtener_usuarios():
        conexion = None
        cursor = None
        try:
            conexion = db_pool.get_connection()
            cursor = conexion.cursor()

            query = "SELECT usuario, jerarquia FROM usuarios"
            cursor.execute(query)

            return cursor.fetchall()  # lista de tuplas

        except mysql.connector.Error as err:
            messagebox.showerror("Error BD", f"No se pudieron obtener los usuarios:\n{err}")
            return []

        finally:
            if cursor:
                cursor.close()
            if conexion:
                conexion.close()

    # -------------------------------------------------------------Funcion para cargar los usuarios------------------------------------------------------------------------------------- 

    def cargar_usuarios_en_tabla():
        tree_usuarios.delete(*tree_usuarios.get_children())

        usuarios = obtener_usuarios()
        for usuario, jerarquia in usuarios:
            tree_usuarios.insert("", "end", values=(usuario, jerarquia))



    # ------------------------------------------------------------------------------HISTÓRICO DE ALERTAS-------------------------------------------------------------------------------- 

    def abrir_popupHistorico(raiz):
        popupHistorico = Toplevel(raiz)
        popupHistorico.title("Histórico de Alertas")
        popupHistorico.config(bg="#5F686F")

     # Centrar la ventana en la pantalla
        window_width = 1100
        window_height = 650
        screen_width = popupHistorico.winfo_screenwidth()
        screen_height = popupHistorico.winfo_screenheight()
        center_x = int(screen_width/2 - window_width / 2)
        center_y = int(screen_height/2 - window_height / 2)
        popupHistorico.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')

        try:
            popupHistorico.iconbitmap("Alertas.ico")
        except Exception:
            pass
        
        # Configuración de filas y columnas
        popupHistorico.grid_rowconfigure(0, weight=0)   # Filtros arriba
        popupHistorico.grid_rowconfigure(1, weight=1)   # Tabla

        popupHistorico.grid_columnconfigure(0, weight=1) # Columna

    #------------------------------- Frame superior con filtros ---------------------------------------------
        etiqueta_popupHistorico = Frame(popupHistorico, bg="#353E44", height=70)
        etiqueta_popupHistorico.grid(row=0, column=0, sticky="ew")

        etiqueta_popupHistorico.grid_rowconfigure(0, weight=0)  # Textos y filtros
        etiqueta_popupHistorico.grid_columnconfigure(0, weight=1)
        etiqueta_popupHistorico.grid_columnconfigure(1, weight=1)
        etiqueta_popupHistorico.grid_columnconfigure(2, weight=1)
        etiqueta_popupHistorico.grid_columnconfigure(3, weight=1)
        etiqueta_popupHistorico.grid_columnconfigure(4, weight=1)
        etiqueta_popupHistorico.grid_columnconfigure(5, weight=1)
        etiqueta_popupHistorico.grid_columnconfigure(6, weight=1)
        etiqueta_popupHistorico.grid_columnconfigure(7, weight=1)

        Etiqueta_HistoricosR1 = tk.Label(etiqueta_popupHistorico, text="Histórico de Alertas", font=("Arial", 16, "bold"), bg="#353E44", fg="white")
        Etiqueta_HistoricosR1.grid(row=0, column=0, padx=10, pady=10, sticky="w")


    #----------------------------------------------Filtros de fecha--------------------------------------------
        etiquetal_Historicos2 = tk.Label(etiqueta_popupHistorico, text="Desde:", bg="#353E44", fg="white")
        etiquetal_Historicos2.grid(row=0, column=1, sticky="e") #row=0, column=2, padx=0, pady=5, sticky="w")

        entry_desde = DateEntry(etiqueta_popupHistorico, width=12, background="darkblue", foreground="white", borderwidth=2, date_pattern="yyyy-mm-dd")
        entry_desde.grid(row=0, column=2, padx=5) #row=0, column=2, padx=10, pady=5, sticky="e")


        etiqueta_Historicos3 = tk.Label(etiqueta_popupHistorico, text="Hasta:", bg="#353E44", fg="white")
        etiqueta_Historicos3.grid(row=0, column=3, sticky="e") #row=0, column=3, padx=0, pady=5, sticky="w")

        entry_hasta = DateEntry(etiqueta_popupHistorico, width=12, background="darkblue", foreground="white", borderwidth=2, date_pattern="yyyy-mm-dd")  #dd-mm-yyyy
        entry_hasta.grid(row=0, column=4, padx=5) #row=0, column=3, padx=10, pady=5, sticky="e")

        # Filtro por categoría
        etiqueta_Historicos4 = tk.Label(etiqueta_popupHistorico, text="Categoría:", bg="#353E44", fg="white")
        etiqueta_Historicos4.grid(row=0, column=5, sticky="e") #row=0, column=4, padx=0, pady=5, sticky="w")

        combo_categoria = ttk.Combobox(etiqueta_popupHistorico, values=["Todas", "Voltaje", "Corriente", "Potencia", "Seguridad", "Mantenimiento"], state="readonly", width=15)
        combo_categoria.current(0)
        combo_categoria.grid(row=0, column=6, padx=5) #row=0, column=4, padx=20, pady=5, sticky="e")

    #----------------------------------------------- Función para cargar histórico ------------------------------
        def cargar_historico_db():
            desde = entry_desde.get_date().strftime("%Y-%m-%d")
            hasta = entry_hasta.get_date().strftime("%Y-%m-%d")
            categoria_seleccionada = combo_categoria.get()
        
            conn = None
            cursor = None
            try:
                conn = db_pool.get_connection() # Usamos el pool global
                cursor = conn.cursor()
            
                query = """ SELECT a.condicion, a.codigo, a.descripcion, a.estado, a.categoria, a.valor,
                                   a.hora_inicio, a.hora_fin, COALESCE(u.usuario, '-') AS usuario
                            FROM alarmas a
                            LEFT JOIN usuarios u ON a.usuario_id = u.id
                            WHERE a.estado = 'Resuelta' """
                params = []

                if desde:
                    query += " AND a.hora_fin >= %s"
                    params.append(desde + " 00:00:00")
                if hasta:
                    query += " AND a.hora_fin <= %s"
                    params.append(hasta + " 23:59:59")

                if categoria_seleccionada != "Todas":
                    query += " AND a.categoria = %s"
                    params.append(categoria_seleccionada)

                query += " ORDER BY a.hora_fin DESC LIMIT 200"
                cursor.execute(query, params)
                registros = cursor.fetchall()

            # Limpiar y llenar tabla
                for row in tree_hist.get_children():
                    tree_hist.delete(row)

                for i, r in enumerate(registros):
                    tag = "evenrow" if i % 2 == 0 else "oddrow"
                    tree_hist.insert("", "end", values=r, tags=(tag,))

            except mysql.connector.Error as err:
                print(f"Error al cargar histórico: {err}")
            finally:
                if cursor: cursor.close()
                if conn: conn.close()

        boton_filtro = tk.Button(etiqueta_popupHistorico, text="Aplicar Filtro", command=cargar_historico_db, bg="#5F686F", fg="white", font=("Arial", 10, "bold"))
        boton_filtro.grid(row=0, column=7, padx=10, pady=5, sticky="w")

    #-------------------------------------------------- Frame  Tabla Alertas ----------------------------------------

        groupBox_H= LabelFrame(popupHistorico, text="Histórico de Alertas", padx=5, pady=5, bg="#5F686F", fg="white", font=("Arial", 12, "bold"), labelanchor="n")
        groupBox_H.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        columnas = ("Condición", "Código", "Descripción", "Estado", "Categoría", "Valor", "Hora de inicio", "Hora de fin", "Usuario")

        tree_hist = ttk.Treeview(groupBox_H, columns=columnas, show="headings", height=15, style="Dark.Treeview")

    # Configuración de columnas
        for col, ancho in zip(columnas, [120, 80, 300, 100, 120, 100, 150, 150, 150]):
            tree_hist.column(col, width=ancho, anchor="center")
            tree_hist.heading(col, text=col)

    # Configuracion de los Scrollbars
        scroll_x = ttk.Scrollbar(groupBox_H, orient="horizontal", command=tree_hist.xview, style="Dark.Horizontal.TScrollbar")
        scroll_y = ttk.Scrollbar(groupBox_H, orient="vertical", command=tree_hist.yview, style="Dark.Vertical.TScrollbar")
        tree_hist.configure(xscrollcommand=scroll_x.set, yscrollcommand=scroll_y.set)

        tree_hist.grid(row=0, column=0, sticky="nsew")
        scroll_x.grid(row=1, column=0, sticky="ew")
        scroll_y.grid(row=0, column=1, sticky="ns")

        groupBox_H.grid_rowconfigure(0, weight=1)
        groupBox_H.grid_columnconfigure(0, weight=1)

        # Filas alternadas
        tree_hist.tag_configure("oddrow", background="#414B52")
        tree_hist.tag_configure("evenrow", background="#525B63")

        cargar_historico_db() # Carga inicial

    # -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------




    # ------------------------------------------------------------------------------Popup con las Alertas--------------------------------------------------------------------------------
    def abrir_popupAlertas():
        popupAlertas = Toplevel(raiz)
        popupAlertas.title("Alertas")
        popupAlertas.config(bg="#5F686F")  # fondo general oscuro

        # Centrar la ventana en la pantalla
        window_widthAlertas = 900
        window_heightAlertas = 600
        screen_width = popupAlertas.winfo_screenwidth()
        screen_height = popupAlertas.winfo_screenheight()
        center_x = int(screen_width/2 - window_widthAlertas / 2)
        center_y = int(screen_height/2 - window_heightAlertas / 2)
        popupAlertas.geometry(f'{window_widthAlertas}x{window_heightAlertas}+{center_x}+{center_y}')

        # Icono (opcional)
        try:
            popupAlertas.iconbitmap("Alertas.ico")
        except Exception:
            pass

        # Configurar de filas y columnas que puedan expandirse
        popupAlertas.grid_rowconfigure(0, weight=1)  # Fila del título
        popupAlertas.grid_rowconfigure(1, weight=1)  # Fila de los botones

        popupAlertas.grid_columnconfigure(0, weight=1)  # Columna 1

        #-------------------------------- Estilos --------------------------------
        style = ttk.Style()
        style.theme_use("default")

        # Fondo del Treeview
        style.configure("Dark.Treeview", background="#00345C", foreground="white", rowheight=28, fieldbackground="#353E44",  font=("Segoe UI", 10))

        # Encabezados
        style.configure("Dark.Treeview.Heading", background="#353E44", foreground="white", font=("Segoe UI", 10, "bold"))

        # Para cambiar el color de la fila seleccionada
        style.map("Dark.Treeview", background=[("selected", "#4A6984")])

        # Columna seleccionada
        style.map("Dark.Treeview.Heading", background=[("selected", "#4A6984")], foreground=[("selected", "white")])


        #Estilo Barras
        style.configure("Dark.Horizontal.TScrollbar",
                    gripcount=0,
                    background="#5F686F",      # color del thumb
                    darkcolor="",       # borde oscuro
                    lightcolor="#353E44",      # borde claro
                    troughcolor="#353E44",     # canaleta
                    bordercolor="#353E44",
                    arrowcolor="white")
        
        style.map("Dark.Horizontal.TScrollbar",
              background=[("active", "#6D7275")]) # Sirve para cambiar el color cuando el mouse esta encima de la barra
        

        style.configure("Dark.Vertical.TScrollbar",
                    gripcount=0,
                    background="#5F686F",      # color del thumb
                    darkcolor="#353E44",       # borde oscuro
                    lightcolor="#353E44",      # borde claro
                    troughcolor="#353E44",     # canaleta
                    bordercolor="#353E44",
                    arrowcolor="white")
        
        style.map("Dark.Vertical.TScrollbar",
              background=[("active", "#6D7275")]) # Sirve para cambiar el color cuando el mouse esta encima de la barra
        

        #-------------------------------- Frame superior --------------------------------
        etiqueta_popupAlertas = Frame(popupAlertas, bg="#353E44", height=50)
        etiqueta_popupAlertas.grid(row=0, column=0, sticky="enw")

        # Label principal "Rendimiento"
        label_Alertas1 = tk.Label(etiqueta_popupAlertas, text="⚠ Alertas", font=("Arial", 18, "bold"), bg="#353E44", fg="white")
        label_Alertas1.grid(row=0, column=0, sticky="w", padx=10, pady=10)

        # Subtítulo
        label_Alertas2 = tk.Label(etiqueta_popupAlertas, text="Incidencias y notificaciones del sistema", font=("Arial", 11), bg="#353E44", fg="lightgray")
        label_Alertas2.grid(row=0, column=1, sticky="w", padx=5, pady=10)

        boton_historicosA = tk.Button(etiqueta_popupAlertas, text="Valores historicos", bg="#5F686F", fg="white", font=("Arial", 11, "bold"), width=18, command=lambda: abrir_popupHistorico(popupAlertas))
        boton_historicosA.grid(row=0, column=1, sticky="e", padx=550, pady=10)


        #-------------------------------- Frame Alertas --------------------------------
        groupBox = LabelFrame(popupAlertas, text="Alertas del Sistema", padx=5, pady=5, bg="#5F686F", fg="white",font=("Arial", 12, "bold"), labelanchor="n")
        groupBox.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        columnas = ("Condición", "Código", "Descripción", "Estado", "Categoría", "Valor", "Hora de inicio", "Hora de fin", "Usuario")

        popupAlertas_tree = ttk.Treeview(groupBox, columns=columnas, show="headings", height=15, style="Dark.Treeview")

        # Configuración de columnas
        popupAlertas_tree.column("Condición", width=120, anchor="center")
        popupAlertas_tree.column("Código", width=80, anchor="center")
        popupAlertas_tree.column("Descripción", width=300, anchor="w")
        popupAlertas_tree.column("Estado", width=100, anchor="center")
        popupAlertas_tree.column("Categoría", width=120, anchor="center")
        popupAlertas_tree.column("Valor", width=100, anchor="center")
        popupAlertas_tree.column("Hora de inicio", width=150, anchor="center")
        popupAlertas_tree.column("Hora de fin", width=150, anchor="center")
        popupAlertas_tree.column("Usuario", width=150, anchor="center")

        for col in columnas:
            popupAlertas_tree.heading(col, text=col)
        
        scroll_x = ttk.Scrollbar(groupBox, orient="horizontal", command=popupAlertas_tree.xview, style="Dark.Horizontal.TScrollbar")
        scroll_y = ttk.Scrollbar(groupBox, orient="vertical", command=popupAlertas_tree.yview, style="Dark.Vertical.TScrollbar")

        popupAlertas_tree.configure(xscrollcommand=scroll_x.set, yscrollcommand=scroll_y.set)

        popupAlertas_tree.grid(row=0, column=0, sticky="nsew")
        scroll_x.grid(row=1, column=0, sticky="ew")
        scroll_y.grid(row=0, column=1, sticky="ns")

        groupBox.grid_rowconfigure(0, weight=1)
        groupBox.grid_columnconfigure(0, weight=1)

          #  Aquí cargamos las alertas desde la BD
        def auto_refresh():
            cargar_alertas(popupAlertas_tree) # Esta función ya usa el pool
            popupAlertas.after(5000, auto_refresh)  # refrescar cada 5s

            fila = obtener_ultima_medicion_completa()
            if fila:
                procesar_alarmas(fila)

        auto_refresh()

        #-------------------------- Filas alternadas (striped rows) --------------------------------
        popupAlertas_tree.tag_configure("oddrow", background="#414B52")
        popupAlertas_tree.tag_configure("evenrow", background="#525B63")

        return popupAlertas
    
    # ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------


    # ------------------------------------------------------------------------------Historico De Rendimiento----------------------------------------------------------------------------


    def abrir_popupHistoricoRendimiento(raiz):
        popupHistoricoR = Toplevel(raiz)
        popupHistoricoR.title("Histórico de Rendimiento")
        popupHistoricoR.config(bg="#5F686F")

     # Centrar la ventana en la pantalla
        window_width = 1100
        window_height = 650
        screen_width = popupHistoricoR.winfo_screenwidth()
        screen_height = popupHistoricoR.winfo_screenheight()
        center_x = int(screen_width/2 - window_width / 2)
        center_y = int(screen_height/2 - window_height / 2)
        popupHistoricoR.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')

        try:
            popupHistoricoR.iconbitmap("Rendimiento.ico")
        except Exception:
            pass
        
        # Configuración de filas y columnas
        popupHistoricoR.grid_rowconfigure(0, weight=0)   # Filtros arriba
        popupHistoricoR.grid_rowconfigure(1, weight=1)   # Tabla

        popupHistoricoR.grid_columnconfigure(0, weight=1) # Columna

    #---------------------------------------------------- Frame superior con filtros -------------------------------------------------
        etiqueta_popupHistorico_R = Frame(popupHistoricoR, bg="#353E44", height=70)
        etiqueta_popupHistorico_R.grid(row=0, column=0, sticky="ew")

        etiqueta_popupHistorico_R.grid_rowconfigure(0, weight=0)  # Textos y filtros
        etiqueta_popupHistorico_R.grid_columnconfigure(0, weight=1)
        etiqueta_popupHistorico_R.grid_columnconfigure(1, weight=1)
        etiqueta_popupHistorico_R.grid_columnconfigure(2, weight=1)
        etiqueta_popupHistorico_R.grid_columnconfigure(3, weight=1)
        etiqueta_popupHistorico_R.grid_columnconfigure(4, weight=1)
        etiqueta_popupHistorico_R.grid_columnconfigure(5, weight=1)
        etiqueta_popupHistorico_R.grid_columnconfigure(6, weight=1)
        etiqueta_popupHistorico_R.grid_columnconfigure(7, weight=1)

        Etiqueta_HistoricosR1 = tk.Label(etiqueta_popupHistorico_R, text="Histórico de Rendimiento", font=("Arial", 16, "bold"), bg="#353E44", fg="white")
        Etiqueta_HistoricosR1.grid(row=0, column=0, padx=10, pady=10, sticky="w")


    #----------------------------------------------Filtros de fecha--------------------------------------------------------------------
        Etiqueta_HistoricosR2 = tk.Label(etiqueta_popupHistorico_R, text="Desde:", bg="#353E44", fg="white")
        Etiqueta_HistoricosR2.grid(row=0, column=1, sticky="e")

        entry_desde = DateEntry(etiqueta_popupHistorico_R, width=12, background="darkblue", foreground="white", borderwidth=2, date_pattern="yyyy-mm-dd")
        entry_desde.grid(row=0, column=2, padx=5)

        Etiqueta_HistoricosR3 = tk.Label(etiqueta_popupHistorico_R, text="Hasta:", bg="#353E44", fg="white")
        Etiqueta_HistoricosR3.grid(row=0, column=3, sticky="e")

        entry_hasta = DateEntry(etiqueta_popupHistorico_R, width=12, background="darkblue", foreground="white", borderwidth=2, date_pattern="yyyy-mm-dd")
        entry_hasta.grid(row=0, column=4, padx=5)

        # Filtro por categoría
        Etiqueta_HistoricosR4 = tk.Label(etiqueta_popupHistorico_R, text="Parámetro:", bg="#353E44", fg="white")
        Etiqueta_HistoricosR4.grid(row=0, column=5, sticky="e")

        combo_parametro = ttk.Combobox(etiqueta_popupHistorico_R, values=["Todos", "Corriente", "Voltaje", "Potencia"], state="readonly", width=15)
        combo_parametro.current(0)
        combo_parametro.grid(row=0, column=6, padx=10)


    #------------------------------------------------------- Función para cargar histórico -------------------------------------------
        def cargar_rendimiento_db():
            desde = entry_desde.get_date().strftime("%Y-%m-%d")
            hasta = entry_hasta.get_date().strftime("%Y-%m-%d")
            parametro = combo_parametro.get()
        
            conn = None
            cursor = None
            try:
                conn = db_pool.get_connection() # Usamos el pool global
                cursor = conn.cursor()
            
                query = "SELECT fecha_hora, corriente_in, corriente_out, voltaje_in, voltaje_out, potencia_in, potencia_out, angulo FROM mediciones WHERE 1=1"
                params = []

                if desde:
                    query += " AND fecha_hora >= %s"
                    params.append(desde + " 00:00:00")
                if hasta:
                    query += " AND fecha_hora <= %s"
                    params.append(hasta + " 23:59:59")

                query += " ORDER BY fecha_hora DESC LIMIT 200"
                cursor.execute(query, params)
                registros = cursor.fetchall()

            # Limpiar y llenar tabla
                for row in tree_hist_R.get_children():
                    tree_hist_R.delete(row)

                for i, r in enumerate(registros):
                    tag = "evenrow" if i % 2 == 0 else "oddrow"
                    # El ángulo (r[7]) se muestra siempre, sin importar el filtro de parámetro
                    if parametro == "Todos": values = r
                    elif parametro == "Corriente": values = (r[0], r[1], r[2], "", "", "", "", r[7])
                    elif parametro == "Voltaje": values = (r[0], "", "", r[3], r[4], "", "", r[7])
                    elif parametro == "Potencia": values = (r[0], "", "", "", "", r[5], r[6], r[7])
                
                    tree_hist_R.insert("", "end", values=values, tags=(tag,))

            except mysql.connector.Error as err:
                print(f"Error al cargar histórico: {err}")
            finally:
                if cursor: cursor.close()
                if conn: conn.close()

        btn_filtrar = tk.Button(etiqueta_popupHistorico_R, text="Aplicar Filtro", command=cargar_rendimiento_db, bg="#5F686F", fg="white", font=("Arial", 10, "bold"))
        btn_filtrar.grid(row=0, column=7, padx=10, pady=5, sticky="w")

    #-------------------------------------------------- Frame  Tabla Rendimiento ------------------------------------------

        groupBox_HistoricoR = LabelFrame(popupHistoricoR, text="Valores de Rendimiento", padx=5, pady=5, bg="#5F686F", fg="white", font=("Arial", 12, "bold"), labelanchor="n")
        groupBox_HistoricoR.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        columnas = ("Fecha/Hora", "Corriente In (A)", "Corriente Out (A)", "Voltaje In (V)", "Voltaje Out (V)", "Potencia In (W)", "Potencia Out (W)", "Angulo (°)")

        tree_hist_R = ttk.Treeview(groupBox_HistoricoR, columns=columnas, show="headings", height=15, style="Dark.Treeview")

    # Configuración de columnas
        for col, ancho in zip(columnas, [150, 120, 120, 120, 120, 120, 120, 120]):
            tree_hist_R.column(col, width=ancho, anchor="center")
            tree_hist_R.heading(col, text=col)

    # Configuracion de los Scrollbars
        scroll_x = ttk.Scrollbar(groupBox_HistoricoR, orient="horizontal", command=tree_hist_R.xview, style="Dark.Horizontal.TScrollbar")
        scroll_y = ttk.Scrollbar(groupBox_HistoricoR, orient="vertical", command=tree_hist_R.yview, style="Dark.Vertical.TScrollbar")
        tree_hist_R.configure(xscrollcommand=scroll_x.set, yscrollcommand=scroll_y.set)

        tree_hist_R.grid(row=0, column=0, sticky="nsew")
        scroll_x.grid(row=1, column=0, sticky="ew")
        scroll_y.grid(row=0, column=1, sticky="ns")

        groupBox_HistoricoR.grid_rowconfigure(0, weight=1)
        groupBox_HistoricoR.grid_columnconfigure(0, weight=1)

        # Filas alternadas
        tree_hist_R.tag_configure("oddrow", background="#414B52")
        tree_hist_R.tag_configure("evenrow", background="#525B63")

        cargar_rendimiento_db() # Carga inicial


    # -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------



    # -----------------------------------------------------------------------------Popup del Rendimiento---------------------------------------------------------------------------------
    def abrir_popupRendimiento():
        popup = Toplevel(raiz)
        popup.title("Rendimiento")
        popup.geometry("900x600") #+460+220")   #anchoxalto + valor para posicionar en la pantalla
        popup.config(bg="#5F686F")
        #popup.iconbitmap("Rendimiento.ico")


        # Centrar la ventana en la pantalla
        window_widthRendimiento = 900
        window_heightRendimiento = 600
        screen_width = popup.winfo_screenwidth()
        screen_height = popup.winfo_screenheight()
        center_x = int(screen_width/2 - window_widthRendimiento / 2)
        center_y = int(screen_height/2 - window_heightRendimiento / 2)
        popup.geometry(f'{window_widthRendimiento}x{window_heightRendimiento}+{center_x}+{center_y}')

        #cambio de icono
        try:
            popup.iconbitmap("Rendimiento.ico")
        except Exception:
            pass

        # Configurar de filas y columnas que puedan expandirse
        popup.grid_rowconfigure(0, weight=1)  # Fila del título
        popup.grid_rowconfigure(1, weight=1)  # Fila de los botones
        popup.grid_rowconfigure(2, weight=1)  # Fila del grafico 1
        popup.grid_rowconfigure(3, weight=1)  # Fila del grafico 2
        popup.grid_rowconfigure(4, weight=1)  # Fila del grafico 3


        popup.grid_columnconfigure(0, weight=1)  # Columna 1 
        popup.grid_columnconfigure(1, weight=1)  # Columna 2 
        popup.grid_columnconfigure(2, weight=1)  # Columna 3 

        #-------------------------------- Estilos --------------------------------
        style = ttk.Style()
        style.theme_use("default")

        # Fondo del Treeview
        style.configure("Dark.Treeview", background="#00345C", foreground="white", rowheight=28, fieldbackground="#353E44",  font=("Segoe UI", 10))

        # Encabezados
        style.configure("Dark.Treeview.Heading", background="#353E44", foreground="white", font=("Segoe UI", 10, "bold"))

        # Para cambiar el color de la fila seleccionada
        style.map("Dark.Treeview", background=[("selected", "#4A6984")])

        # Columna seleccionada
        style.map("Dark.Treeview.Heading", background=[("selected", "#4A6984")], foreground=[("selected", "white")])


        #Estilo Barras
        style.configure("Dark.Horizontal.TScrollbar",
                    gripcount=0,
                    background="#5F686F",      # color del thumb
                    darkcolor="",       # borde oscuro
                    lightcolor="#353E44",      # borde claro
                    troughcolor="#353E44",     # canaleta
                    bordercolor="#353E44",
                    arrowcolor="white")
        
        style.map("Dark.Horizontal.TScrollbar",
              background=[("active", "#6D7275")]) # Sirve para cambiar el color cuando el mouse esta encima de la barra
        

        style.configure("Dark.Vertical.TScrollbar",
                    gripcount=0,
                    background="#5F686F",      # color del thumb
                    darkcolor="#353E44",       # borde oscuro
                    lightcolor="#353E44",      # borde claro
                    troughcolor="#353E44",     # canaleta
                    bordercolor="#353E44",
                    arrowcolor="white")
        
        style.map("Dark.Vertical.TScrollbar",
              background=[("active", "#6D7275")]) # Sirve para cambiar el color cuando el mouse esta encima de la barra

        
        #----------------------------------------Frame superior-------------------------------------------------------
        etiqueta_popupAlertas = Frame(popup, bg="#353E44", height=50)
        etiqueta_popupAlertas.grid(row=0, column=0, columnspan=3 , padx=0, pady=0, sticky="enw")
     
        # Label principal "Rendimiento"
        label_title = tk.Label(etiqueta_popupAlertas, text="⚡Rendimiento", font=("Arial", 18, "bold"), bg="#353E44", fg="white")
        label_title.grid(row=0, column=0, sticky="w", padx=10, pady=10)

        # Subtítulo
        label_subtitle = tk.Label(etiqueta_popupAlertas, text="KPIs energéticos y métricas operativas", font=("Arial", 11),  bg="#353E44", fg="lightgray")
        label_subtitle.grid(row=0, column=1, sticky="w", padx=5, pady=10)

        boton_historicosR = tk.Button(etiqueta_popupAlertas, text="Valores historicos", bg="#5F686F", fg="white", font=("Arial", 11, "bold"), width=18, command=lambda: abrir_popupHistoricoRendimiento(popup))
        boton_historicosR.grid(row=0, column=1, sticky="e", padx=490, pady=10)

        #---------------------------------------Botones------------------------------------------------------------------

        #-----------Funciones para setear el tipo de grafico------------
        def mostrar_corrientes():  
            Framecorrientes.tkraise()                                             

        def mostrar_voltajes():
            Framevoltajes.tkraise() 

        def mostrar_potencias():
            Framepotencia.tkraise() 
        
        #-----------------Configuracion de los botones-----------------


        frame_botones = Frame(popup, bg="#5F686F", height=200)
        frame_botones.grid(row=1, column=0, columnspan=3, pady=10, sticky="nsew")


        # Configurar de filas y columnas que puedan expandirse
        frame_botones.grid_rowconfigure(0, weight=1)  # Fila del título

        frame_botones.grid_columnconfigure(0, weight=1)  # Columna 1 
        frame_botones.grid_columnconfigure(1, weight=1)  # Columna 2 
        frame_botones.grid_columnconfigure(2, weight=1)  # Columna 3 

        boton_corriente = Button(frame_botones, text="Corrientes", bg="#353E44", fg="white", font=("Arial", 12, "bold"), width=20, command=mostrar_corrientes)
        boton_corriente.grid(row=1, column=0, padx=5, pady=0)

        boton_voltaje = Button(frame_botones, text="Voltajes", bg="#353E44", fg="white", font=("Arial", 12, "bold"), width=20, command=mostrar_voltajes)
        boton_voltaje.grid(row=1, column=1, padx=5, pady=0)

        boton_potencia= Button(frame_botones, text="Potencias", bg="#353E44", fg="white", font=("Arial", 12, "bold"), width=20, command=mostrar_potencias)
        boton_potencia.grid(row=1, column=2, padx=5, pady=0)


        #--------------------------------------Creacion de Grafico de corriente (Frame 1)----------------------------------------------------
        Framecorrientes = Frame(popup, bg="#353E44")
        Framecorrientes.grid(row=2, column=0,columnspan=3, padx=20, pady=20, sticky="nsew")


        # Configuracion de filas y columnas de Framecorrientes para centrar y alinear
        Framecorrientes.grid_rowconfigure(0, weight=1)
        Framecorrientes.grid_columnconfigure(0, weight=1)



        fig1, (ax1,ax2) = plt.subplots(2, 1, figsize=(4, 4.4))   #figsize=(ancho, alto)   El 1,1 hace referencia a si queremos una matriz de graficos o como en este caso a uno solo


        #------------------Configuración gráfico 1 (Corriente de entrada)----------------------------------
        line_corriente1, = ax1.plot([], [], "#DDE00E", label="Corriente de entrada")
        ax1.legend(loc="upper left")                                    #fijo la posicion del texto
        ax1.set_xlim(0, 50)
        ax1.set_ylim(0, 9)
        ax1.set_xlabel("Tiempo (s)", fontsize=10)#, fontweight="bold", color = "w")
        ax1.set_ylabel("Corriente (A)", fontsize=10)#, fontweight="bold", color = "w")
        ax1.grid(True, linestyle="--", color="gray", alpha=1)           #Sirve para agregar lineas punteadas de acuerdo a los valores de los ejes
        #ax1.axhline(y=80, color="red", linestyle="--", linewidth=1)    #Esta linea sirve para agregar una linea punteada en un valor especifico
        #ax1.set_facecolor("lightgray")                                 #Esta linea sirve para cambiar el fondo dentro de los graficos
        ax1.set_title("Corriente de entrada", fontsize=14, fontweight="bold", color = "w")              #Codigo para personalizar textos y titulos
        fig1.tight_layout(pad=0.5)                                      #Esto es para darle mas espacio donde va el texto del eje x y que no se corte(cualquiera de las 2 opciones sirve)
        fig1.subplots_adjust(left=0.1, right=0.95, top=0.95, bottom=0.1, hspace=0.5)
        #fig1.subplots_adjust(bottom=0.2)
        fig1.patch.set_facecolor("#5F686F")  # Esta linea sirve para cambiar el fondo de los graficos
        
        
        #------------------Configuración gráfico 2 (corriente de salida)----------------------------------
        line_corriente2, = ax2.plot([], [], "#DDE00E", label="Corriente de salida")
        ax2.legend(loc="upper left")                                   #fijo la posicion del texto
        ax2.set_xlim(0, 50)
        ax2.set_ylim(0, 9)
        ax2.set_xlabel("Tiempo (s)", fontsize=10)   
        ax2.set_ylabel("Corriente (A)", fontsize=10)
        ax2.grid(True, linestyle="--", color="gray", alpha=1)         #Sirve para agregar lineas punteadas de acuerdo a los valores de los ejes
        #ax2.axhline(y=80, color="red", linestyle="--", linewidth=1)    #Esta linea sirve para agregar una linea punteada en un valor especifico
        #ax2.set_facecolor("lightgray")                                 #Esta linea sirve para cambiar el fondo dentro de los graficos
        ax2.set_title("Corriente de salida", fontsize=14, fontweight="bold", color = "w")            #Codigo para personalizar textos y titulos
        #fig2.tight_layout(pad=0.5)                                      #Esto es para darle mas espacio donde va el texto del eje x y que no se corte(cualquiera de las 2 opciones sirve)
        #fig2.subplots_adjust(left=0.1, right=0.95, top=0.9, bottom=0.2)
        #fig2.subplots_adjust(bottom=0.2)
        #fig2.patch.set_facecolor("#5F686F")  # Esta linea sirve para cambiar el fondo de los graficos

        #------------------Textos dinámicos para mostrar valores actuales--------------------------------
        text_graf_C1 = ax1.text(0.98, 0.88, "", transform=ax1.transAxes, ha="right", va="center", fontsize=10, bbox=dict(facecolor="black", alpha=0.1, edgecolor="black", boxstyle="round,pad=0.3"))
        text_graf_C2 = ax2.text(0.98, 0.88, "", transform=ax2.transAxes, ha="right", va="center", fontsize=10, bbox=dict(facecolor="black", alpha=0.1, edgecolor="black", boxstyle="round,pad=0.3"))


        #------------------Canvas de Matplotlib dentro del popup para el grafico 1----------------------
        canvas_C = FigureCanvasTkAgg(fig1, master=Framecorrientes)
        canvas_C.get_tk_widget().grid(row=0, column=0, columnspan=3,padx=0, pady=0, sticky="nsew") 

        #------------------------------------------------------------------Creacion de Grafico de Voltaje (Frame 2)-------------------------------------------------------------------------
        Framevoltajes = Frame(popup, bg="#353E44")
        Framevoltajes.grid(row=2, column=0,columnspan=3, padx=20, pady=20, sticky="nsew")


        # Configuracion de filas y columnas de Framecorrientes para centrar y alinear
        Framevoltajes.grid_rowconfigure(0, weight=1)
        Framevoltajes.grid_columnconfigure(0, weight=1)

        fig2, (ax3,ax4) = plt.subplots(2, 1, figsize=(4, 4.4))   #figsize=(ancho, alto)   El 1,1 hace referencia a si queremos una matriz de graficos o como en este caso a uno solo


        #------------------Configuración gráfico 1 (Voltaje de entrada)----------------------------------
        line_voltaje1, = ax3.plot([], [], "#0E57E0", label="Voltaje de entrada")
        ax3.legend(loc="upper left")                                    #fijo la posicion del texto
        ax3.set_xlim(0, 50)
        ax3.set_ylim(0, 80)
        ax3.set_xlabel("Tiempo (s)", fontsize=10)#, fontweight="bold", color = "w")
        ax3.set_ylabel("Voltaje(V)", fontsize=10)#, fontweight="bold", color = "w")
        ax3.grid(True, linestyle="--", color="gray", alpha=1)           #Sirve para agregar lineas punteadas de acuerdo a los valores de los ejes
        #ax3.axhline(y=80, color="red", linestyle="--", linewidth=1)    #Esta linea sirve para agregar una linea punteada en un valor especifico
        #ax3.set_facecolor("lightgray")                                 #Esta linea sirve para cambiar el fondo dentro de los graficos
        ax3.set_title("Voltaje de entrada", fontsize=14, fontweight="bold", color = "w")              #Codigo para personalizar textos y titulos
        fig2.tight_layout(pad=0.5)                                      #Esto es para darle mas espacio donde va el texto del eje x y que no se corte(cualquiera de las 2 opciones sirve)
        fig2.subplots_adjust(left=0.1, right=0.95, top=0.95, bottom=0.1, hspace=0.5)
        #fig2.subplots_adjust(bottom=0.2)
        fig2.patch.set_facecolor("#5F686F")  # Esta linea sirve para cambiar el fondo de los graficos
        
        
        #------------------Configuración gráfico 2 (Voltaje de salida)----------------------------------
        line_voltaje2, = ax4.plot([], [], "#0E57E0", label="Voltaje de salida")
        ax4.legend(loc="upper left")                                   #fijo la posicion del texto
        ax4.set_xlim(0, 50)
        ax4.set_ylim(0, 80)
        ax4.set_xlabel("Tiempo (s)", fontsize=10)   
        ax4.set_ylabel("Voltaje (V)", fontsize=10)
        ax4.grid(True, linestyle="--", color="gray", alpha=1)         #Sirve para agregar lineas punteadas de acuerdo a los valores de los ejes
        #ax4.axhline(y=80, color="red", linestyle="--", linewidth=1)    #Esta linea sirve para agregar una linea punteada en un valor especifico
        #ax4.set_facecolor("lightgray")                                 #Esta linea sirve para cambiar el fondo dentro de los graficos
        ax4.set_title("Voltaje de salida", fontsize=14, fontweight="bold", color = "w")            #Codigo para personalizar textos y titulos
        #fig2.tight_layout(pad=0.5)                                      #Esto es para darle mas espacio donde va el texto del eje x y que no se corte(cualquiera de las 2 opciones sirve)
        #fig2.subplots_adjust(left=0.1, right=0.95, top=0.9, bottom=0.2)
        #fig2.subplots_adjust(bottom=0.2)
        #fig2.patch.set_facecolor("#5F686F")  # Esta linea sirve para cambiar el fondo de los graficos

        #------------------Textos dinámicos para mostrar valores actuales--------------------------------
        text_graf_V1 = ax3.text(0.98, 0.88, "", transform=ax3.transAxes, ha="right", va="center", fontsize=10, bbox=dict(facecolor="black", alpha=0.1, edgecolor="black", boxstyle="round,pad=0.3"))
        text_graf_V2 = ax4.text(0.98, 0.88, "", transform=ax4.transAxes, ha="right", va="center", fontsize=10, bbox=dict(facecolor="black", alpha=0.1, edgecolor="black", boxstyle="round,pad=0.3"))


        #------------------Canvas de Matplotlib dentro del popup para el grafico 2----------------------
        canvas_V = FigureCanvasTkAgg(fig2, master=Framevoltajes)
        canvas_V.get_tk_widget().grid(row=0, column=0, columnspan=3,padx=0, pady=0, sticky="nsew")


        #---------------------------------Creacion de Grafico de Potencia (Frame 3)-------------------------------------------------
        Framepotencia = Frame(popup, bg="#353E44")
        Framepotencia.grid(row=2, column=0,columnspan=3, padx=20, pady=20, sticky="nsew")

        # Configuracion de filas y columnas de Framecorrientes para centrar y alinear
        Framepotencia.grid_rowconfigure(0, weight=1)
        Framepotencia.grid_columnconfigure(0, weight=1)


        fig3, (ax5,ax6) = plt.subplots(2, 1, figsize=(4, 4.4))   #figsize=(ancho, alto)   El 1,1 hace referencia a si queremos una matriz de graficos o como en este caso a uno solo


        #------------------Configuración gráfico 1 (Potencia de entrada)----------------------------------
        line_potencia1, = ax5.plot([], [], "#CF2711", label="Potencia de entrada")
        ax5.legend(loc="upper left")                                    #fijo la posicion del texto
        ax5.set_xlim(0, 50)
        ax5.set_ylim(0, 520)
        ax5.set_xlabel("Tiempo (s)", fontsize=10)#, fontweight="bold", color = "w")
        ax5.set_ylabel("Potencia(W)", fontsize=10)#, fontweight="bold", color = "w")
        ax5.grid(True, linestyle="--", color="gray", alpha=1)           #Sirve para agregar lineas punteadas de acuerdo a los valores de los ejes
        #ax5.axhline(y=80, color="red", linestyle="--", linewidth=1)    #Esta linea sirve para agregar una linea punteada en un valor especifico
        #ax5.set_facecolor("lightgray")                                 #Esta linea sirve para cambiar el fondo dentro de los graficos
        ax5.set_title("Potencia de entrada", fontsize=14, fontweight="bold", color = "w")              #Codigo para personalizar textos y titulos
        fig3.tight_layout(pad=0.5)                                      #Esto es para darle mas espacio donde va el texto del eje x y que no se corte(cualquiera de las 2 opciones sirve)
        fig3.subplots_adjust(left=0.1, right=0.95, top=0.95, bottom=0.1, hspace=0.5)
        #fig3.subplots_adjust(bottom=0.2)
        fig3.patch.set_facecolor("#5F686F")  # Esta linea sirve para cambiar el fondo de los graficos
        
        
        #------------------Configuración gráfico 2 (Potencia de salida)----------------------------------
        line_potencia2, = ax6.plot([], [], "#CF2711", label="Potencia de salida")
        ax6.legend(loc="upper left")                                   #fijo la posicion del texto
        ax6.set_xlim(0, 50)
        ax6.set_ylim(0, 520)
        ax6.set_xlabel("Tiempo (s)", fontsize=10)   
        ax6.set_ylabel("Potencia (w)", fontsize=10)
        ax6.grid(True, linestyle="--", color="gray", alpha=1)         #Sirve para agregar lineas punteadas de acuerdo a los valores de los ejes
        #ax6.axhline(y=80, color="red", linestyle="--", linewidth=1)    #Esta linea sirve para agregar una linea punteada en un valor especifico
        #ax6.set_facecolor("lightgray")                                 #Esta linea sirve para cambiar el fondo dentro de los graficos
        ax6.set_title("Potencia de salida", fontsize=14, fontweight="bold", color = "w")            #Codigo para personalizar textos y titulos
        #fig3.tight_layout(pad=0.5)                                      #Esto es para darle mas espacio donde va el texto del eje x y que no se corte(cualquiera de las 2 opciones sirve)
        #fig3.subplots_adjust(left=0.1, right=0.95, top=0.9, bottom=0.2)
        #fig3.subplots_adjust(bottom=0.2)
        #fig3.patch.set_facecolor("#5F686F")  # Esta linea sirve para cambiar el fondo de los graficos

        #------------------Textos dinámicos para mostrar valores actuales--------------------------------
        text_graf_P1 = ax5.text(0.98, 0.88, "", transform=ax5.transAxes, ha="right", va="center", fontsize=10, bbox=dict(facecolor="black", alpha=0.1, edgecolor="black", boxstyle="round,pad=0.3"))
        text_graf_P2 = ax6.text(0.98, 0.88, "", transform=ax6.transAxes, ha="right", va="center", fontsize=10, bbox=dict(facecolor="black", alpha=0.1, edgecolor="black", boxstyle="round,pad=0.3"))


        #------------------Canvas de Matplotlib dentro del popup para el grafico 2----------------------
        canvas_P = FigureCanvasTkAgg(fig3, master=Framepotencia)
        canvas_P.get_tk_widget().grid(row=0, column=0, columnspan=3,padx=0, pady=0, sticky="nsew")



        

        #--------------------------------------Función de actualización---------------------------------------------
        def update(frame):

            global last_values
            global ultimo_valor_rendimiento 
            last_values = get_last_row()  # lee el último registro de MySQL (¡AHORA USA EL POOL!)

            x_data.append(frame)

            corriente1_data.append(get_corriente1())
            corriente2_data.append(get_corriente2())

            voltaje1_data.append(get_voltaje1())
            voltaje2_data.append(get_voltaje2())

            potencia1_data.append(get_potencia1())
            potencia2_data.append(get_potencia2())

            # Mantiene solo últimos 50 puntos
            if len(x_data) > 50:
                x_data.pop(0)
                corriente1_data.pop(0)
                corriente2_data.pop(0)

                voltaje1_data.pop(0)
                voltaje2_data.pop(0)

                potencia1_data.pop(0)
                potencia2_data.pop(0)

            # actualiza datos
            line_corriente1.set_data(range(len(x_data)), corriente1_data)
            line_corriente2.set_data(range(len(x_data)), corriente2_data)
            line_voltaje1.set_data(range(len(x_data)), voltaje1_data)
            line_voltaje2.set_data(range(len(x_data)), voltaje2_data)
            line_potencia1.set_data(range(len(x_data)), potencia1_data)
            line_potencia2.set_data(range(len(x_data)), potencia2_data)

            # actualiza textos
            text_graf_C1.set_text(f"Valor actual: {corriente1_data[-1]} A")
            text_graf_C2.set_text(f"Valor actual: {corriente2_data[-1]} A")

            text_graf_V1.set_text(f"Valor actual: {voltaje1_data[-1]} V")
            text_graf_V2.set_text(f"Valor actual: {voltaje2_data[-1]} V")

            text_graf_P1.set_text(f"Valor actual: {potencia1_data[-1]} W")
            text_graf_P2.set_text(f"Valor actual: {potencia2_data[-1]} W")





            return line_corriente1, line_corriente2, line_voltaje1, line_voltaje2, line_potencia1, line_potencia2, text_graf_C1, text_graf_C2, text_graf_V1, text_graf_V2, text_graf_P1, text_graf_P2



        # Animación (blit=False para que funcione bien en Tkinter)
        ani1 = FuncAnimation(fig1, update, interval=1000, blit=False, cache_frame_data=False)
        ani2 = FuncAnimation(fig2, update, interval=1000, blit=False, cache_frame_data=False)
        ani3 = FuncAnimation(fig3, update, interval=1000, blit=False, cache_frame_data=False)

        # Forzar un primer dibujado
           
        canvas_P.draw()
        canvas_V.draw()
        canvas_C.draw()

    # ------------------------------------------------------------------------------------------------------------------------------------------------

    # ---------------------------------------------------------- Funciones para el parpadeo de alarmas -----------------------------------------------

    def ejecutar_ciclo_parpadeo(label):
        """
        Función recursiva que cambia el color de fondo de una etiqueta para crear un efecto de parpadeo.
        """
        if label in labels_parpadeando:
            # Obtener el color actual del fondo
            color_actual = label.cget("background")
            
            # Alternar el color
            nuevo_color = COLOR_NORMAL_FONDO if color_actual == COLOR_ALARMA else COLOR_ALARMA
            label.config(background=nuevo_color)
            
            # Programar la siguiente ejecución de este ciclo
            raiz.after(INTERVALO_PARPADEO, lambda: ejecutar_ciclo_parpadeo(label))

    def iniciar_parpadeo(label):
        """
        Inicia el efecto de parpadeo para una etiqueta si no está ya parpadeando.
        """
        if label not in labels_parpadeando:
            labels_parpadeando.add(label)
            label.config(fg=COLOR_NORMAL_TEXTO) # Aseguramos que el texto sea visible
            ejecutar_ciclo_parpadeo(label)

    def detener_parpadeo(label):
        """
        Detiene el efecto de parpadeo y restaura los colores originales de la etiqueta.
        """
        if label in labels_parpadeando:
            labels_parpadeando.discard(label)
            label.config(background=COLOR_NORMAL_FONDO, fg=COLOR_NORMAL_TEXTO)


    def mostrar_alerta_popup(nombre_variable, tipo_alerta):
        """
        Muestra una ventana emergente personalizada con el estilo del SCADA.
        """
        # 1. Crear la ventana Toplevel
        popup = Toplevel(raiz)
        popup.title("Alertas del Sistema")
        popup.config(bg="#353E44") # Fondo oscuro y borde realzado
        popup.resizable(False, False) # Evitar que se pueda cambiar el tamaño

        # Icono
        try:
            popup.iconbitmap("Alertas.ico")
        except Exception:
            pass

        # 2. Centrar la ventana en la pantalla
        window_width = 450
        window_height = 200
        screen_width = popup.winfo_screenwidth()
        screen_height = popup.winfo_screenheight()
        center_x = int(screen_width/2 - window_width / 2)
        center_y = int(screen_height/2 - window_height / 2)
        popup.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')

        # 3. Crear un frame interior para organizar el contenido
        frame_interior = Frame(popup, bg="#353E44")
        frame_interior.pack(pady=20, padx=20, fill="both", expand=True)
        
        # 4. Contenido del popup
        color_texto_alerta = "#FFD700" # Un color amarillo/dorado para la alerta
        
        # Ícono y Título de la alerta
        label_titulo = Label(frame_interior, 
                             text=f"⚠️ Alerta de Nivel {tipo_alerta} ⚠️", 
                             font=("Arial", 16), 
                             bg="#353E44", 
                             fg=color_texto_alerta)
        label_titulo.pack(pady=(0, 10))

        # Mensaje descriptivo
        mensaje = f"El valor de '{nombre_variable}' ha salido del rango normal."
        label_mensaje = Label(frame_interior, 
                              text=mensaje, 
                              font=("Arial", 12), 
                              bg="#353E44", 
                              fg="white",
                              wraplength=400) # El texto se ajustará si es muy largo
        label_mensaje.pack(pady=(5, 10))


        # ✅ NUEVO: Obtener la hora actual y crear la etiqueta
        hora_actual = datetime.now().strftime("%H:%M:%S hs")
        label_hora = Label(frame_interior,
                           text=f"Hora de la alerta: {hora_actual}",
                           font=("Arial", 10, "italic"),
                           bg="#353E44",
                           fg="lightgray")
        label_hora.pack(pady=(5, 10))

        # Botón para cerrar
        boton_aceptar = Button(frame_interior, 
                               text="Aceptar", 
                               font=("Arial", 12, "bold"), 
                               bg="#FFFFFF", # Mismo color que el botón "Salir"
                               fg="black", 
                               width=15,
                               command=popup.destroy) # El comando destruye la ventana
        boton_aceptar.pack()
        
        # 5. Hacer la ventana modal (bloquea la ventana principal)
        popup.transient(raiz)
        popup.grab_set()
        raiz.wait_window(popup)

    #----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------



    #----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    #                                                                               Frame 1
    #----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    miFrame1 = Frame(raiz, width=530, height=270, bg="#353E44", bd=5)
    miFrame1.grid(row=1, column=0, padx=20, pady=20, sticky="nsew")

    # Configuracion de filas y columnas de miFrame1 para centrar y alinear
    miFrame1.grid_rowconfigure(0, weight=1)
    miFrame1.grid_rowconfigure(1, weight=1)
    miFrame1.grid_rowconfigure(2, weight=1)
    miFrame1.grid_rowconfigure(3, weight=1)
    miFrame1.grid_rowconfigure(4, weight=1)
    miFrame1.grid_columnconfigure(0, weight=1)

    # Título centrado en la parte superior del frame
    Datosclima_label = Label(miFrame1, text="Datos del clima: ", fg="white", bg="#353E44", font=("arial", 18, "bold"))
    Datosclima_label.grid(row=0, column=0, pady=10, sticky="n")  # Centrado en la fila superior

    viento_label = Label(miFrame1, text="Velocidad del viento: -- km/h", fg="white", bg="#353E44", font=("arial", 15))
    viento_label.grid(row=1, column=0, padx=10, pady=5, sticky="w")  #prueba

    temp_label = Label(miFrame1, text="Temperatura: -- °C", fg="white", bg="#353E44", font=("arial", 15))
    temp_label.grid(row=2, column=0, padx=10, pady=5, sticky="w")  #prueba

    rad_label = Label(miFrame1, text="Radiacion solar: -- W/m2", fg="white", bg="#353E44", font=("arial", 15))
    rad_label.grid(row=3, column=0, padx=10, pady=5, sticky="w")  #prueba

    #-----------------Función para actualizar los datos del clima (REM San Luis)-------------------------

    INTERVALO_CLIMA = 300000  # 5 minutos en milisegundos. La estación no actualiza los datos más seguido que eso.

    def _aplicar_datos_clima(datos):
        """Se ejecuta en el hilo principal de Tkinter para volcar los datos a los labels."""
        if cerrando_app:
            return
        if datos is not None:
            viento_label.config(text=f"Velocidad del viento: {datos['viento']:.1f} km/h")
            temp_label.config(text=f"Temperatura: {datos['temperatura']:.1f} °C")
            rad_label.config(text=f"Radiacion solar: {datos['radiacion']:.1f} W/m2")
        else:
            # Si falló la consulta, avisamos en los labels en vez de dejar datos viejos silenciosamente
            viento_label.config(text="Velocidad del viento: sin datos")
            temp_label.config(text="Temperatura: sin datos")
            rad_label.config(text="Radiacion solar: sin datos")

        # Programamos la próxima actualización
        raiz.after(INTERVALO_CLIMA, actualizar_datos_clima)

    def actualizar_datos_clima():
        if cerrando_app:
            return

        def tarea_en_hilo():
            datos = obtener_datos_clima()
            if not cerrando_app:
                # Volvemos al hilo principal de Tkinter para tocar los widgets
                raiz.after(0, lambda: _aplicar_datos_clima(datos))

        threading.Thread(target=tarea_en_hilo, daemon=True).start()

    #--------------------------------------------------------------------------------

    angulo_label = Label(miFrame1, text=" ", fg="white", bg="#353E44", font=("arial", 15, "bold"))
    angulo_label.grid(row=4, column=0, padx=10, pady=0, sticky="w")  # Centrado en la fila superior


    #----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    #                                                                               Frame 2
    #----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    miFrame2 = Frame(raiz, width=600, height=270, bg="#353E44")
    miFrame2.grid(row=1, column=1, padx=20, pady=20, sticky="nsew")

    # Configuracion de filas y columnas de miFrame2 para centrar y alinear
    miFrame2.grid_rowconfigure(0, weight=1)
    miFrame2.grid_rowconfigure(1, weight=1)
    miFrame2.grid_rowconfigure(2, weight=1)
    miFrame2.grid_rowconfigure(3, weight=1)
    miFrame2.grid_rowconfigure(4, weight=1)
    miFrame2.grid_columnconfigure(0, weight=1)

    # Título centrado en la parte superior del frame
    Datosoperacion_label = Label(miFrame2, text="Datos de operación:", fg="white", bg="#353E44", font=("arial", 18, "bold"))
    Datosoperacion_label.grid(row=0, column=0, pady=10, sticky="n")  # Centrado en la fila superior

    datos_label_mes = Label(miFrame2, text="", fg="white", bg="#353E44", font=("arial", 15))
    datos_label_mes.grid(row=1, column=0, padx=10, pady=5, sticky="w")

    datos_label_angulo = Label(miFrame2, text="", fg="white", bg="#353E44", font=("arial", 15))
    datos_label_angulo.grid(row=2, column=0, padx=10, pady=5, sticky="w")

    # Crear y ubicar el Label para la fecha y hora alineado a la izquierda
    etiqueta_fecha_hora = Label(miFrame2, font=("Arial", 15), fg="white", bg="#353E44")
    etiqueta_fecha_hora.grid(row=3, column=0, sticky="w", padx=10, pady=5)  # Alineado a la izquierda


    # Crear y ubicar el Label para el angulo y el mes
    angulo_label = Label(miFrame2, text=" ", fg="white", bg="#353E44", font=("arial", 15))
    angulo_label.grid(row=4, column=0, padx=10, pady=0, sticky="w")  # Centrado en la fila superior

    # Llamar a la función por primera vez para iniciar la actualización
    actualizar_fecha_hora()
    actualizar_datos_clima()

    # Inicializar la primera actualización
    mostrar_angulo_mesexcel()

    #REGISTRO DEL ESTADO INICIAL
    registrar_modo_operacion("Automatico", angulo_actual)




    #----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    #                                                                               Frame 3
    #----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    miFrame3 = Frame(raiz, width=300, height=270, bg="#353E44")
    miFrame3.grid(row=1, column=2, padx=20, pady=20, sticky="nsew")

    # Configuracion de filas y columnas de miFrame3 para centrar y alinear
    miFrame3.grid_rowconfigure(0, weight=1)
    miFrame3.grid_rowconfigure(1, weight=1)
    miFrame3.grid_rowconfigure(2, weight=1)
    miFrame3.grid_rowconfigure(3, weight=1)


    miFrame3.grid_columnconfigure(0, weight=1)
    miFrame3.grid_columnconfigure(1, weight=1)

    # --- Título del Frame ---
    operacion_label = Label( miFrame3, text="Valores de operación:", fg="white", bg="#353E44", font=("arial", 18, "bold"))
    operacion_label.grid(row=0, column=0,columnspan=2, pady=10, sticky="n")


    # --- Primera fila ---
    I_in_label = Label(miFrame3, text="I in: --", width= 25, height= 2, relief="sunken", bg= "#353E44", fg="white", font= ("arial", 12, "bold"))
    I_in_label.grid(row=1, column=0, padx=0, pady=5)

    I_out_label = Label(miFrame3, text="I out: --", width= 25, height= 2, relief="sunken", bg= "#353E44", fg="white", font= ("arial", 12, "bold"))
    I_out_label.grid(row=1, column=1, padx=0, pady=5)

    # --- Segunda fila ---
    Vin_in_label = Label(miFrame3, text="Vin: --", width= 25, height= 2, relief="sunken", bg= "#353E44", fg="white", font= ("arial", 12, "bold"))
    Vin_in_label.grid(row=2, column=0, padx=0, pady=5)

    Vin_out_label = Label(miFrame3, text="Vout: --", width= 25, height= 2, relief="sunken", bg= "#353E44", fg="white", font= ("arial", 12, "bold"))
    Vin_out_label.grid(row=2, column=1, padx=0, pady=5)

    # --- Tercera fila ---
    P_in_label = Label(miFrame3, text="P in: --", width= 25, height= 2, relief="sunken", bg= "#353E44", fg="white", font= ("arial", 12, "bold"),)
    P_in_label.grid(row=3, column=0, padx=0, pady=5)

    P_out_label = Label(miFrame3, text="P out: --", width= 25, height= 2, relief="sunken", bg= "#353E44", fg="white", font= ("arial", 12, "bold"))
    P_out_label.grid(row=3, column=1, padx=0, pady=5)

    # ---------Funcion para actualizar valores de operacion---
    # --- VERSIÓN FINAL DE LA FUNCIÓN DE ACTUALIZACIÓN ---
    def actualizar_valores_operacion():
        #print(limites_operacion)

        if cerrando_app:
            return
        """
        Obtiene valores, actualiza etiquetas, gestiona parpadeo y muestra popups de alerta de un solo disparo.
        """
        valores = get_last_row() # Esta función ya usa el pool

        if valores:
            corriente_in, voltaje_in, potencia_in, corriente_out, voltaje_out, potencia_out = valores


            # --- Obtener límites individuales ---
            lim_ci = limites_operacion.get("corriente_in", {})
            lim_co = limites_operacion.get("corriente_out", {})
            lim_vi = limites_operacion.get("voltaje_in", {})
            lim_vo = limites_operacion.get("voltaje_out", {})
            lim_pi = limites_operacion.get("potencia_in", {})
            lim_po = limites_operacion.get("potencia_out", {})


            # 1. Actualizar textos de las etiquetas (sin cambios aquí)
            I_in_label.config(text=f"I in: {corriente_in:.2f} A")
            I_out_label.config(text=f"I out: {corriente_out:.2f} A")
            Vin_in_label.config(text=f"Vin: {voltaje_in:.2f} V")
            Vin_out_label.config(text=f"Vout: {voltaje_out:.2f} V")
            P_in_label.config(text=f"P in: {potencia_in:.2f} W")
            P_out_label.config(text=f"P out: {potencia_out:.2f} W")

            # 2. Lógica de comprobación de umbrales con popups de disparo único
            # (Toda esta lógica se mantiene igual)

            # --- Corriente de Entrada ---
            if lim_ci.get("max") is not None and corriente_in > lim_ci["max"]:
                iniciar_parpadeo(I_in_label)
                if not alarmas_activas["corriente_in"]:
                    mostrar_alerta_popup("Corriente de Entrada", "ALTO")
                    alarmas_activas["corriente_in"] = True
            elif lim_ci.get("min") is not None and corriente_in < lim_ci["min"]:
                iniciar_parpadeo(I_in_label)
                if not alarmas_activas["corriente_in"]:
                    mostrar_alerta_popup("Corriente de Entrada", "BAJO")
                    alarmas_activas["corriente_in"] = True
            else: # El valor es normal
                detener_parpadeo(I_in_label)
                if alarmas_activas["corriente_in"]:
                    alarmas_activas["corriente_in"] = False # Reactivar la alerta

            # --- Corriente de Salida ---
            if lim_co.get("max") is not None and corriente_out > lim_co["max"]:
                iniciar_parpadeo(I_out_label)
                if not alarmas_activas["corriente_out"]:
                    mostrar_alerta_popup("Corriente de Salida", "ALTO")
                    alarmas_activas["corriente_out"] = True
            elif lim_co.get("min") is not None and corriente_out < lim_co["min"]:
                iniciar_parpadeo(I_out_label)
                if not alarmas_activas["corriente_out"]:
                    mostrar_alerta_popup("Corriente de Salida", "BAJO")
                    alarmas_activas["corriente_out"] = True
            else:
                detener_parpadeo(I_out_label)
                if alarmas_activas["corriente_out"]:
                    alarmas_activas["corriente_out"] = False

            # --- Voltaje de Entrada ---
            if lim_vi.get("max") is not None and voltaje_in > lim_vi["max"]:
                iniciar_parpadeo(Vin_in_label)
                if not alarmas_activas["voltaje_in"]:
                    mostrar_alerta_popup("Voltaje de Entrada", "ALTO")
                    alarmas_activas["voltaje_in"] = True

            elif lim_vi.get("min") is not None and voltaje_in < lim_vi["min"]:
                iniciar_parpadeo(Vin_in_label)
                if not alarmas_activas["voltaje_in"]:
                    mostrar_alerta_popup("Voltaje de Entrada", "BAJO")
                    alarmas_activas["voltaje_in"] = True
            else:
                detener_parpadeo(Vin_in_label)
                if alarmas_activas["voltaje_in"]:
                    alarmas_activas["voltaje_in"] = False


            # --- Voltaje de Salida ---
            if lim_vo.get("max") is not None and voltaje_out > lim_vo["max"]:
                iniciar_parpadeo(Vin_out_label)
                if not alarmas_activas["voltaje_out"]:
                    mostrar_alerta_popup("Voltaje de Salida", "ALTO")
                    alarmas_activas["voltaje_out"] = True
            elif lim_vo.get("min") is not None and voltaje_out < lim_vo["min"]:
                iniciar_parpadeo(Vin_out_label)
                if not alarmas_activas["voltaje_out"]:
                    mostrar_alerta_popup("Voltaje de Salida", "BAJO")
                    alarmas_activas["voltaje_out"] = True
            else:
                detener_parpadeo(Vin_out_label)
                if alarmas_activas["voltaje_out"]:
                    alarmas_activas["voltaje_out"] = False

            # --- Potencia de Entrada ---
            if lim_pi.get("max") is not None and potencia_in > lim_pi["max"]:
                iniciar_parpadeo(P_in_label)
                if not alarmas_activas["potencia_in"]:
                    mostrar_alerta_popup("Potencia de Entrada", "ALTO")
                    alarmas_activas["potencia_in"] = True
            elif lim_pi.get("min") is not None and potencia_in < lim_pi["min"]:
                iniciar_parpadeo(P_in_label)
                if not alarmas_activas["potencia_in"]:
                    mostrar_alerta_popup("Potencia de Entrada", "BAJO")
                    alarmas_activas["potencia_in"] = True
            else:
                detener_parpadeo(P_in_label)
                if alarmas_activas["potencia_in"]:
                    alarmas_activas["potencia_in"] = False


            # --- Potencia de Salida ---
            if lim_po.get("max") is not None and potencia_out > lim_po["max"]:
                iniciar_parpadeo(P_out_label)
                if not alarmas_activas["potencia_out"]:
                    mostrar_alerta_popup("Potencia de Salida", "ALTO")
                    alarmas_activas["potencia_out"] = True
            elif lim_po.get("min") is not None and potencia_out < lim_po["min"]:
                iniciar_parpadeo(P_out_label)
                if not alarmas_activas["potencia_out"]:
                    mostrar_alerta_popup("Potencia de Salida", "BAJO")
                    alarmas_activas["potencia_out"] = True
            else:
                detener_parpadeo(P_out_label)
                if alarmas_activas["potencia_out"]:
                    alarmas_activas["potencia_out"] = False

        # Programar la próxima actualización
        raiz.after(1000, actualizar_valores_operacion)



    #----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    #                                                                               Frame 4
    #----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    miFrame4 = Frame(raiz, width=530, height=270, bg="#353E44")                     
    miFrame4.grid(row=2, column=0, padx=20, pady=20, columnspan=3, sticky="nsew")

    # Configuracion de filas y columnas de miFrame4 para centrar y alinear
    miFrame4.grid_rowconfigure(0, weight=1)
    miFrame4.grid_rowconfigure(1, weight=1)
    miFrame4.grid_rowconfigure(2, weight=1)
    miFrame4.grid_rowconfigure(3, weight=1)
    miFrame4.grid_rowconfigure(4, weight=1)
    miFrame4.grid_rowconfigure(5, weight=1)
    miFrame4.grid_columnconfigure(0, weight=1)
    miFrame4.grid_columnconfigure(1, weight=1)
    miFrame4.grid_columnconfigure(2, weight=1)
    miFrame4.grid_columnconfigure(3, weight=1)

    mododeop_label = Label(miFrame4, text="Modo de operación:", fg="white", bg="#353E44", font=("arial", 18, "bold"))
    mododeop_label.grid(row=0, column=1, pady=10, sticky="n")


    ingreseangulo_label = Label(miFrame4, text="Ingrese el angulo deseado:", fg="white", bg="#353E44", font=("arial", 15))
    ingreseangulo_label.grid(row=3, column=1, pady=0, sticky="n")


    # Botones para seleccionar el modo de operacion
    boton_manual = Button(miFrame4, text="Manual", command=lambda: confirmar_cambio_modo("Manual"), bg="gray", fg="black", font=("Arial", 12, "bold"), width=20)
    boton_manual.grid(row=1, column=1, padx=5, pady=0)

    boton_automatico = Button(miFrame4, text="Automático",command=lambda: confirmar_cambio_modo("Automático"), bg="#A89F75", fg="white", font=("Arial", 12, "bold"), width=20)
    boton_automatico.grid(row=2, column=1, padx=5, pady=0)


    # Botón de configuracion usuario
    boton_configurar_usuario = Button(miFrame4, text="Configuración de usuarios", font=("Arial", 12, "bold"), bg="#66747B", fg="white", command=abrir_configuracion)
    boton_configurar_usuario.grid(row=1, column=0, padx=10, pady=0)

    if jerarquia_actual != "administrador":
        boton_configurar_usuario.config(state="disabled")

    # Botón de configuracion alertas
    boton_configurar_alarmas = Button(miFrame4, text=" Configuración de alertas ", font=("Arial", 12, "bold"), bg="#7B6668", fg="white", command=abrir_configuracion_alertas)
    boton_configurar_alarmas.grid(row=2, column=0, padx=10, pady=0)

    if jerarquia_actual != "administrador":
        boton_configurar_alarmas.config(state="disabled")


    # Botón de camara
    #boton_camara = Button(miFrame4, text="Abrir camara", font=("Arial", 12, "bold"), bg="#174360", fg="white")#, command=abrir_configuracion)
    #boton_camara.grid(row=2, column=3, padx=10, pady=10)


    # Campo de entrada para el ángulo (inicialmente deshabilitado y con fondo gris porque el modo es "Automático")
    entry_valor = Entry(miFrame4, font=("Arial", 12), width=25, state="disabled", bg="light gray")
    entry_valor.grid(row=4, column=1, columnspan=1, padx=10, pady=0, sticky="n")

    # Botón para confirmar el ángulo ingresado (con ícono de flecha)
    boton_confirmar = Button(miFrame4, text="Ingresar →", font=("Arial", 12, "bold"), bg="gray", fg="white", width=20, height=1, command=procesar_valor)
    boton_confirmar.grid(row=5, column=1, pady=0, sticky="n")

    # Etiqueta para mostrar el ángulo actual
    etiqueta_angulo_actual = Label(miFrame4, text="", fg="white", bg="#353E44", font=("Arial", 18, "bold"))
    etiqueta_angulo_actual.grid(row=0, column=2, padx=10, pady=10, sticky="n")

    #-----------------------------------imagen----------------------------------------------

    etiqueta_imagen = Label(miFrame4, bg="#353E44")
    etiqueta_imagen.grid(row=1, column=2, sticky="n", rowspan=5)

    # Cargar la imagen inicial
    actualizar_imagen_angulo(angulo_actual)

    #---------------------------------------------------------------------------------------

    # Llamar a la función para mostrar el ángulo actual inicial
    mostrar_angulo_mes()

    #Inicializa los permisos
    aplicar_permisos_usuario()

    #----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    #                                                                               Frame 5
    #----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    miFrame5 = Frame(raiz, width=530, height=80, bg="#353E44")                     
    miFrame5.grid(row=3, column=0, padx=0, pady=40, columnspan=3, sticky="nsew")

    # Configuracion de filas y columnas de miFrame4 para centrar y alinear
    miFrame5.grid_rowconfigure(0, weight=1)
    miFrame5.grid_columnconfigure(0, weight=1)
    miFrame5.grid_columnconfigure(1, weight=1)
    miFrame5.grid_columnconfigure(2, weight=1)

    # Botón de Alertas
    boton_alertas = Button(miFrame5, text="Alertas", font=("Arial", 12, "bold"), bg="#AC8A66", fg="white", width=18, height=2, command=abrir_popupAlertas)
    boton_alertas.grid(row=0, column=0, padx=10, pady=10)

    # Botón de Rendimiento
    boton_rendimiento = Button(miFrame5, text="Rendimiento", font=("Arial", 12, "bold"), bg="#657888", fg="white", width=18, height=2, command=abrir_popupRendimiento)
    boton_rendimiento.grid(row=0, column=1, padx=10, pady=10)

    # Botón de Salir con un icono de "X" (Unicode)
    boton_salir = Button(miFrame5, text="Salir ✖", font=("Arial", 12, "bold"), bg="#855454", fg="white", width=18, height=2, command=cerrar_ventana)
    boton_salir.grid(row=0, column=2, padx=10, pady=10)
    #------------------------------------------------------------------------------------------------------------------------------------- 


    #Con esto llamo la funcion para actualizar los valores del frame 3
    actualizar_valores_operacion()

    raiz.mainloop()

    # (Ya no se cierran conexiones aquí)
    pass
    # Fin de la función run_main_scada_app


#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
#                                                                               Ventana de Login
#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def crear_ventana_login():
    """Crea y muestra la ventana de login INICIAL."""
    
    pantallainicio = Tk()
    pantallainicio.title("Inicio de Sesión - SCADA")
    pantallainicio.config(bg="#5F686F") # Fondo oscuro
    pantallainicio.resizable(False, False)

    try:
        pantallainicio.iconbitmap("icono.ico")
    except Exception:
        pass

    # Hacer la ventana en pantalla completa
    #pantallainicio.attributes("-fullscreen", True)

    #def salir_pantalla_completa(event):
        #pantallainicio.attributes("-fullscreen", False)

    # Detectar la tecla 'Esc' para salir de pantalla completa
    #pantallainicio.bind("<Escape>", salir_pantalla_completa)


    # Configurar para que las filas y columnas puedan expandirse
    pantallainicio.grid_rowconfigure(0, weight=1)  # Fila del título
    pantallainicio.grid_rowconfigure(1, weight=1)  # Fila de los primeros frames
    pantallainicio.grid_rowconfigure(2, weight=1)  # Fila del frame inferior
    pantallainicio.grid_rowconfigure(3, weight=1)  # Fila del frame más abajo
    pantallainicio.grid_rowconfigure(4, weight=1)  # Fila del frame inferior
    pantallainicio.grid_rowconfigure(5, weight=1)  # Fila del frame más abajo

    pantallainicio.grid_columnconfigure(0, weight=1)  # Columna 1 (primer frame)
    pantallainicio.grid_columnconfigure(1, weight=1)  # Columna 2 (frame central)
    pantallainicio.grid_columnconfigure(2, weight=1)  # Columna 3 (último frame)

    # --- Centrar la ventana de login ---
    window_width = 1400
    window_height = 700
    screen_width = pantallainicio.winfo_screenwidth()
    screen_height = pantallainicio.winfo_screenheight()
    center_x = int(screen_width/2 - window_width / 2)
    center_y = int(screen_height/2 - window_height / 2)
    pantallainicio.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')

    # Texto centrado en la ventana principal
    miLabel = Label(pantallainicio, text="SCADA - Paneles Solares", fg="white", bg="#5F686F", font=("arial", 37, "bold"))
    miLabel.grid(row=0, column=1, columnspan=1,padx=0, pady=0, sticky="nsew")  # Centrado en la ventana


    # Imagenes de logos de la faculta
    imagen_izq = Image.open("imagenunsl.png")       #con esto cargo la imagen
    imagen_izq = ImageTk.PhotoImage(imagen_izq)     #con esto la paso a un formato que lo entiende tkinter

    etiqueta_imagenizq = Label(pantallainicio, image=imagen_izq, bg="#5F686F")    #Lo añado a la raiz
    etiqueta_imagenizq.grid(row=0, column=0,padx=30, sticky="w")                #Lo acomodo


    imagen_der = Image.open("imagenfica.png")       #con esto cargo la imagen
    imagen_der = ImageTk.PhotoImage(imagen_der)     #con esto la paso a un formato que lo entiende tkinter

    etiqueta_imagender = Label(pantallainicio, image=imagen_der, bg="#5F686F")    #Lo añado a la raiz
    etiqueta_imagender.grid(row=0, column=2,padx=30,sticky="e")                #Lo acomodo



    def on_cancel():
        """Cierra la app si se cancela el login."""
        pantallainicio.destroy()
        sys.exit() # Simplemente cierra el script
    
    pantallainicio.protocol("WM_DELETE_WINDOW", on_cancel) # Manejar cierre con la 'X'

    # --- Función interna para validar ---
    def intentar_login():
        username = user_entry.get()
        password = pass_entry.get()

        global usuario_logueado, jerarquia_actual


        if not username or not password:
            messagebox.showwarning("Campos Vacíos", "Por favor, ingrese usuario y contraseña.", parent=pantallainicio)
            return

        # Variables locales para la conexión
        conn = None 
        cursor = None
        try:
            # 1. Hashear la contraseña ingresada
            pass_hash_ingresado = hash_password(password)

            # 2. Consultar la BD
            conn = db_pool.get_connection() # Pedir conexión al pool
            cursor = conn.cursor()
            
            query = "SELECT id, password_hash, jerarquia FROM usuarios WHERE usuario = %s"


            cursor.execute(query, (username,))
            resultado = cursor.fetchone()

            # 3. Validar
            if resultado:
                user_id, pass_hash_bd, jerarquia_usuario = resultado
                
                if pass_hash_ingresado == pass_hash_bd:
                    # ¡Éxito!

                    global usuario_actual_id
                    #global usuario_ingresado

                    usuario_actual_id = user_id

                    jerarquia_actual = jerarquia_usuario
                    usuario_logueado = username

                    print("Jerarquia del usuario:", jerarquia_actual)
                    registrar_login(user_id)  # Esta función ya usa el pool
                    pantallainicio.destroy()      # 1. Destruir ventana de login
                    run_main_scada_app(user_id) # 2. Lanzar la app principal
                else:
                    messagebox.showerror("Error", "Contraseña incorrecta.", parent=pantallainicio)
            else:
                messagebox.showerror("Error", "Usuario no encontrado.", parent=pantallainicio)
        
        except mysql.connector.Error as err:
            messagebox.showerror("Error de Base de Datos", f"Error al conectar: {err}", parent=pantallainicio)
        
        finally:
            # ¡Importante! Devolver la conexión al pool
            if cursor:
                cursor.close()
            if conn:
                conn.close() 
                 
    #-------------configuracion de la pantalla de inicio de sesion--------------

    pantallainicio.grid_rowconfigure(0, weight=1)
    pantallainicio.grid_columnconfigure(0, weight=1)


    login_frame = Frame(pantallainicio, bg="#353E44")
    login_frame.grid(row=2, column=1, sticky="nsew")


    #configuracion de filas y columnas    
    login_frame.grid_columnconfigure(0, weight=1) # Columna Izq
    login_frame.grid_columnconfigure(1, weight=0) # Columna Central
    login_frame.grid_columnconfigure(2, weight=1) # Columna Der

    login_frame.grid_rowconfigure(0, weight=1) # Fila Arriba
    login_frame.grid_rowconfigure(1, weight=0) # Titulo
    login_frame.grid_rowconfigure(2, weight=0) # Label Usuario
    login_frame.grid_rowconfigure(3, weight=0) # Entry Usuario
    login_frame.grid_rowconfigure(4, weight=0) # Label Contraseña
    login_frame.grid_rowconfigure(5, weight=0) # Entry Contraseña
    login_frame.grid_rowconfigure(6, weight=0) # Botones
    login_frame.grid_rowconfigure(7, weight=1) # Fila Abajo


    # 4. Añadir los widgets al login_frame (columna 1)

    titulo_label = Label(login_frame, text="Ingrese su usuario y contraseña", font=("arial", 22, "bold"), bg="#353E44", fg="white")
    titulo_label.grid(row=1, column=0, columnspan=3, pady=(0, 20)) # Centrado en la ventana
    
    usuario_label = Label(login_frame, text="Usuario:", font=("arial", 12, "bold" ), bg="#353E44", fg="white")
    usuario_label.grid(row=2, column=1, sticky="nsew") # "sticky='w'" alinea a la izquierda (West)


    user_entry = Entry(login_frame, font=("arial", 12), width=30) 
    user_entry.grid(row=3, column=1, pady=5) # Debajo del label

    contraseña_label = Label(login_frame, text="Contraseña:", font=("arial", 12, "bold"), bg="#353E44", fg="white")
    contraseña_label.grid(row=4, column=1, sticky="nsew", pady=(10,0)) # Un poco de espacio arriba


    pass_entry = Entry(login_frame, font=("arial", 12), width=30, show="*") 
    pass_entry.grid(row=5, column=1, pady=5) # Debajo del label

    # --- Frame para botones ---
    button_frame = Frame(login_frame, bg="#353E44")
    button_frame.grid(row=6, column=1, pady=15) # Debajo del entry de contraseña


    Button(button_frame, text="Ingresar", font=("arial", 12, "bold"), bg="#FFFFFF", fg="black", width=12, command=intentar_login).pack(side="left", padx=5)
    Button(button_frame, text="Salir", font=("arial", 12, "bold"), bg="#FFFFFF", fg="black", width=12, command=on_cancel).pack(side="left", padx=5)

    # Permitir login con la tecla "Enter"
    pantallainicio.bind("<Return>", lambda event: intentar_login())
    
    # Poner el foco en el primer campo de entrada
    user_entry.focus()

    # Iniciar el bucle SÓLO para la ventana de login
    pantallainicio.mainloop()

#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

#------------------------------------------------------------------------------- Punto de Entrada Principal -----------------------------------------------------------------------
if __name__ == "__main__":
    # Iniciar el proceso de login.
    # La aplicación principal (run_main_scada_app) solo se llamará
    # desde 'crear_ventana_login' si el login es exitoso.
    crear_ventana_login()
    actualizar_limites_desde_bd()
