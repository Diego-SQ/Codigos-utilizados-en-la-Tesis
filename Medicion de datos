import serial
import mysql.connector
import time
from datetime import datetime

# ---------------- CONFIGURACIÓN ----------------

PUERTO = "COM6"
BAUDRATE = 115200

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",  # En XAMPP normalmente está vacío
    "database": "scada_db"
}

# ------------------------------------------------

def conectar_bd():
    return mysql.connector.connect(**DB_CONFIG)

def insertar_datos(cursor, datos):
    query = """
        INSERT INTO mediciones
        (fecha_hora,
         corriente_in,
         corriente_out,
         voltaje_in,
         voltaje_out,
         potencia_in,
         potencia_out,
         angulo)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """

    ahora = datetime.now()

    cursor.execute(query, (
        ahora,
        datos["corr_in"],
        datos["corr_out"],
        datos["volt_in"],
        datos["volt_out"],
        datos["pot_in"],
        datos["pot_out"],
        0.0   # Ángulo 
    ))

def parsear_linea(linea):
    if linea.startswith("<") and linea.endswith(">"):
        contenido = linea[1:-1]
        valores = contenido.split(",")

        if len(valores) == 8:
            volt_in  = round(float(valores[0]) + 0.0, 2)
            corr_in  = round(float(valores[1]) + 12.7, 2)
            volt_out = round(float(valores[2]) + 0.0 , 2)
            corr_out = round(float(valores[3]) - 1.8 , 2)
            #pot_in   = -float(valores[4])
            #pot_out  = -float(valores[5])

            pot_in  = round(volt_in * corr_in, 2)
            pot_out = round(volt_out * corr_out, 2)

            return {
                "volt_in": volt_in,
                "corr_in": corr_in,
                "volt_out": volt_out,
                "corr_out": corr_out,
                "pot_in": pot_in,
                "pot_out": pot_out
            }

    return None

def main():

    print(f"Conectando a {PUERTO}...")
    ser = serial.Serial(PUERTO, BAUDRATE, timeout=1)
    time.sleep(2)
    print("Conectado correctamente.")

    conexion = conectar_bd()
    cursor = conexion.cursor()

    try:
        while True:

            linea = ser.readline().decode("utf-8").strip()

            if not linea:
                continue

            datos = parsear_linea(linea)

            if datos:
                insertar_datos(cursor, datos)
                conexion.commit()
                print("Insertado:", datos)

    except KeyboardInterrupt:
        print("\nFinalizando...")

    finally:
        cursor.close()
        conexion.close()
        ser.close()

if __name__ == "__main__":
    main()
