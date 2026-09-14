# Sistema SCADA y Control de Convertidor Buck para Panel Solar

Este repositorio contiene el código fuente desarrollado para el proyecto de tesis de Ingeniería /Mecatrónica de la Facultad de Ingeniería y Ciencias Agropecuarias (FICA) - Universidad Nacional de San Luis (UNSL). 

**Autores:** Peralta, Santiago - Silvera, Diego

## 📝 Descripción del Proyecto
El proyecto consiste en el diseño e implementación de un sistema de supervisión, control y adquisición de datos (SCADA) para paneles solares, integrando el control automático de un convertidor DC-DC topología Buck. El sistema maximiza la extracción de energía del panel mediante un algoritmo MPPT y regula el voltaje de salida utilizando un controlador digital en el plano Z. Adicionalmente, se gestiona el posicionamiento del panel mediante un seguidor solar (Tracker).

## 🏗️ Arquitectura del Sistema

El proyecto está dividido en tres pilares fundamentales de hardware y software:

### 1. Sistema SCADA (Python)
Desarrollado en Python, proporciona la interfaz gráfica (HMI) y la gestión de la base de datos:
* **Interfaz Gráfica:** Permite la visualización de variables eléctricas (Voltaje, Corriente, Potencia) y el control de parámetros de operación.
* **Base de Datos:** Almacenamiento histórico de variables mediante MySQL (`scada_db.sql`).
* **Comunicación:** Enlace serial bidireccional con los microcontroladores.

### 2. Control de Potencia (STM32F103C8T6)
El microcontrolador STM32 es el cerebro de la planta de potencia, encargado de:
* **Adquisición de Datos (ADC + DMA):** Muestreo sincronizado en el centro del pulso PWM para evadir el ruido de conmutación.
* **Algoritmo MPPT:** Implementación del método de *Conductancia Incremental* con paso adaptativo, ejecutado cada 25 ms.
* **Controlador Digital:** Compensador discreto en el plano Z, ejecutado cada 2.5 ms, encargado de regular la tensión de salida.
* **Telemetría:** Comunicación con la PC mediante puerto serie virtual (USB CDC).

### 3. Seguidor Solar (ESP32)
Encargado del posicionamiento físico del panel solar:
* Recepción de consignas de ángulo (Set-point) enviadas desde el sistema SCADA.
* Actuación sobre los motores del seguidor para alinear el panel perpendicularmente a la radiación solar.

## 📂 Estructura del Repositorio

* `scada.py` : Archivo principal de la interfaz gráfica del sistema SCADA.
* `medicion_de_datos.py` : Módulo encargado del procesamiento y escalado de la información recibida.
* `conexion_stm32.py` : Script de manejo del puerto serie para la comunicación con el microcontrolador.
* `scada_db.sql` : Script de creación y estructuración de la base de datos MySQL.
* `main.c` : Código fuente principal en C para el microcontrolador STM32 (Lazos de control, PWM, ADC).

## 🚀 Requisitos y Tecnologías Utilizadas

* **Hardware:** STM32F103C8T6, ESP32, Convertidor Buck, Sensores ACS712, Divisores resistivos.
* **Software embebido:** STM32CubeIDE, librerías HAL, C/C++.
* **Software PC:** Python 3.x (Tkinter, Pyserial), MySQL Server.

## ⚙️ Uso y Ejecución
1. Configurar la base de datos local importando el archivo `scada_db.sql` en MySQL.
2. Compilar y cargar el código `.c` en el STM32 y el correspondiente en el ESP32.
3. Conectar los microcontroladores a los puertos USB de la PC.
4. Ejecutar el script `medicion_de_datos.py` y `scada.py` para iniciar la interfaz de supervisión.
5. Ejecutar el script `conexion_stm32.py` para enviar el angulo al microcontrolador del seguidor solar.

---
*Proyecto de Trabajo Final de Grado - 2026*
