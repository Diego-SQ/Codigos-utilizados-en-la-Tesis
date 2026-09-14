import time
import socket
import mysql.connector

# =========================
# CONFIGURACION MYSQL
# =========================
DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "",          # <- aca va la contraseña
    "database": "scada_db",
}

# =========================
# CONFIGURACION ESP32 TCPh
# =========================
ESP32_IP = "10.104.14.1"
ESP32_PORT = 5000

# Cada cuánto leer la BD (segundos)
POLL_S = 1.0

# Rango permitido 
ANGLE_MIN = 0
ANGLE_MAX = 90


def leer_ultimo_angulo():
    """
    Lee el último registro de modo_operacion y devuelve:
    (id, modo, angulo_deseado, fecha_hora) o None si no hay.
    """
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, modo, angulo_deseado, fecha_hora
        FROM modo_operacion
        WHERE angulo_deseado IS NOT NULL
        ORDER BY id DESC
        LIMIT 1
    """)
    row = cur.fetchone()

    cur.close()
    conn.close()
    return row


def enviar_tcp_angulo(angulo: int) -> str:
    """
    Se conecta al ESP32 y manda 'angulo\\n'.
    Devuelve la respuesta del ESP32 (si manda algo) o string vacío.
    """
    msg = f"{angulo}\n".encode("utf-8")

    with socket.create_connection((ESP32_IP, ESP32_PORT), timeout=3) as s:
        s.sendall(msg)

        # Intentar leer respuesta (ACK). Si no llega, no falla.
        s.settimeout(1.0)
        try:
            data = s.recv(64)
            return data.decode("utf-8", errors="ignore").strip()
        except socket.timeout:
            return ""


def clamp(x, a, b):
    return max(a, min(b, x))


def main():
    print("=== BRIDGE SCADA -> ESP32 (TCP) ===")
    print(f"MySQL: {DB_CONFIG['host']} / DB={DB_CONFIG['database']}")
    print(f"ESP32: {ESP32_IP}:{ESP32_PORT}")
    print("Leyendo modo_operacion. Ctrl+C para salir.\n")

    ultimo_id = None

    while True:
        try:
            row = leer_ultimo_angulo()
            if not row:
                time.sleep(POLL_S)
                continue

            cmd_id, modo, angulo, fecha = row

            # Si no cambió el registro, no enviar repetido
            if cmd_id == ultimo_id:
                time.sleep(POLL_S)
                continue

            ultimo_id = cmd_id

            # Convertir a int seguro
            try:
                angulo_int = int(float(angulo))
            except Exception:
                print(f"[WARN] angulo_deseado inválido: {angulo} (cmd_id={cmd_id})")
                time.sleep(POLL_S)
                continue

            angulo_int = clamp(angulo_int, ANGLE_MIN, ANGLE_MAX)

            resp = enviar_tcp_angulo(angulo_int)

            print(f"[OK] Enviado {angulo_int}° | cmd_id={cmd_id} | modo={modo} | {fecha} | resp='{resp}'")

        except mysql.connector.Error as e:
            print(f"[ERROR] MySQL: {e}")
        except (OSError, socket.error) as e:
            print(f"[ERROR] TCP ESP32: {e}")
        except KeyboardInterrupt:
            print("\nSaliendo...")
            break
        except Exception as e:
            print(f"[ERROR] General: {e}")

        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
