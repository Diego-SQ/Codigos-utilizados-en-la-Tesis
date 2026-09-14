/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "usb_device.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "usbd_cdc_if.h"
#include <stdio.h>
#include <string.h>
#include <math.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

#define K_VOLT_IN    89.43f
#define K_VOLT_OUT   89.23f
#define K_SENSOR     1.0f
#define ADC_MAX      4095.0f

// Multiplicador para reconstruir el voltaje del ACS712 (Divisor 10k serie / 18k a GND)
#define K_DIV_CORR   1.5555f

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
ADC_HandleTypeDef hadc1;
DMA_HandleTypeDef hdma_adc1;

TIM_HandleTypeDef htim2;

/* USER CODE BEGIN PV */

#define NUM_SAMPLES 50
uint16_t adc_buffer[4 * NUM_SAMPLES]; // Buffer de 200 espacios (4 canales x 50 muestras)

volatile float Volt_in = 0.0f;
volatile float Volt_out = 0.0f;
volatile float Corr_in = 0.0f;
volatile float Corr_out = 0.0f;
volatile float Pot_in = 0.0f;
volatile float Pot_out = 0.0f;

float V_sensor = 0.0f;

/* Calibración */
float calib_volt_in_gain  = 1.0f;
float calib_volt_out_gain = 1.0f;
float calib_corr_in_offset  = 2.549f;
float calib_corr_out_offset = 2.564f;

// Variable global para telemetría
volatile float Vref_actual = 60.0f;

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_DMA_Init(void);
static void MX_ADC1_Init(void);
static void MX_TIM2_Init(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

// ==========================================================
// 1. ALGORITMO MPPT (Conductancia Incremental Adaptativa)
// ==========================================================
float mppt_inccond(float V, float I) {
    float alpha = 0.2f;
    float epsV  = 1e-3f;
    float Vmin_oper = 1.0f;
    float delta_min = 0.005f;
    float delta_max = 0.05f;
    float Kstep     = 0.1f;
    float MPP_tol   = 0.05f;
    float Vref_min  = 45.0f;
    float Vref_max  = 75.0f;

    static float V_prev = 0.0f, I_prev = 0.0f;
    static float Vf_prev = 0.0f, If_prev = 0.0f;
    static float Vref_prev = 60.0f;
    static uint8_t init_done = 0;

    if (!init_done) {
        V_prev = V; I_prev = I;
        Vf_prev = V; If_prev = I;
        Vref_prev = 60.0f;
        init_done = 1;
    }

    // Filtro pasa bajo
    float Vf = alpha * V + (1.0f - alpha) * Vf_prev;
    float If = alpha * I + (1.0f - alpha) * If_prev;

    float dV = Vf - V_prev;
    float dI = If - I_prev;
    float Vref_new = Vref_prev;

    if (Vf >= Vmin_oper) {
        if (fabs(dV) < epsV) {
            if (fabs(dI) < 1e-6f) {
                Vref_new = Vref_prev;
            } else if (dI > 0.0f) {
                Vref_new = Vref_prev + delta_min;
            } else {
                Vref_new = Vref_prev - delta_min;
            }
        } else {
            float slope  = dI / dV;
            float target = -If / Vf;
            float denom = (fabs(target) > 1e-6f) ? fabs(target) : 1e-6f;
            float err = (slope - target) / denom;

            float delta = Kstep * fabs(err);
            if(delta < delta_min) delta = delta_min;
            if(delta > delta_max) delta = delta_max;

            if (fabs(err) < MPP_tol) {
                Vref_new = Vref_prev;
            } else if (slope > target) {
                Vref_new = Vref_prev + delta;
            } else {
                Vref_new = Vref_prev - delta;
            }
        }
    }

    // Saturación
    if (Vref_new < Vref_min) Vref_new = Vref_min;
    if (Vref_new > Vref_max) Vref_new = Vref_max;

    // Actualización de estados
    V_prev = Vf; I_prev = If;
    Vf_prev = Vf; If_prev = If;
    Vref_prev = Vref_new;

    return Vref_new;
}

// ==========================================================
// 2. CONTROLADOR DIGITAL EN EL PLANO Z
// ==========================================================
float calcular_controlador(float Ref, float y) {
    static float ek_1 = 0.0f, ek_2 = 0.0f;
    static float uk_1 = 0.0f, uk_2 = 0.0f;

    // Coeficientes calculados para el lazo
    const float a = 0.0066177f;
    const float b = -1.934f;
    const float c = 0.9675f;
    const float d = 0.5f;
    const float e = 0.5f;

    // Regulación de salida: si y cae respecto a Ref, el duty debe aumentar
    float ek = Ref - y;

    // --- CÁLCULO DISCRETO ---
    float uk_raw = ek*a - ek_1*b + ek_2*c + uk_1*d + uk_2*e;

    // --- SATURACIÓN ---
    float uk;
    if (uk_raw > 0.95f) {
        uk = 0.95f;
    } else if (uk_raw < 0.05f) {
        uk = 0.05f;
    } else {
        uk = uk_raw;
    }

    // --- ACTUALIZACIÓN DE ESTADOS ---
    ek_2 = ek_1;
    ek_1 = ek;
    uk_2 = uk_1;
    uk_1 = uk;

    return uk;
}

// ==========================================================
// 3. RUTINA DE INTERRUPCIÓN DEL ADC (CALLBACK)
// ==========================================================
void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef* hadc) {
    if(hadc->Instance == ADC1) {
        uint32_t sum_adc0 = 0, sum_adc1 = 0, sum_adc2 = 0, sum_adc3 = 0;

        // 1. Promedios directos
        for(int i = 0; i < NUM_SAMPLES; i++){
            sum_adc0 += adc_buffer[i * 4 + 0];
            sum_adc1 += adc_buffer[i * 4 + 1];
            sum_adc2 += adc_buffer[i * 4 + 2];
            sum_adc3 += adc_buffer[i * 4 + 3];
        }

        // 2. Escalado físico
        Volt_in  = (((float)sum_adc0 / NUM_SAMPLES) * K_VOLT_IN)  / ADC_MAX * calib_volt_in_gain;
        Volt_out = (((float)sum_adc1 / NUM_SAMPLES) * K_VOLT_OUT) / ADC_MAX * calib_volt_out_gain;

        float V_pin_in = (((float)sum_adc2 / NUM_SAMPLES) * 3.3f) / ADC_MAX;
        Corr_in = ((V_pin_in * K_DIV_CORR) - calib_corr_in_offset) / 0.2f * 1.0f;
        if(Corr_in > -0.05f && Corr_in < 0.05f) Corr_in = 0.0f;

        float V_pin_out = (((float)sum_adc3 / NUM_SAMPLES) * 3.3f) / ADC_MAX;
        Corr_out = ((V_pin_out * K_DIV_CORR) - calib_corr_out_offset) / 0.2f * 1.0f;
        if(Corr_out > -0.05f && Corr_out < 0.05f) Corr_out = 0.0f;

        Pot_in  = Volt_in  * Corr_in;
        Pot_out = Volt_out * Corr_out;

        // 3. Lazo externo: MPPT (cada 25 ms)
        static int mppt_counter = 0;
        mppt_counter++;
        if (mppt_counter >= 10) {
            Vref_actual = mppt_inccond(Volt_in, Corr_in);
            mppt_counter = 0;
        }

        // 4. Lazo interno: Controlador discreto regulando Volt_out
        float duty_norm = calcular_controlador(Vref_actual, Volt_out);

        // Conversión a ticks de timer (ARR = 3599)
        float duty_nuevo = duty_norm * 3600.0f;

        // --- PROTECCIÓN DE SOBRECORRIENTE (OCP) ---
        float I_MAX = 6.0f;
        if (Corr_out > I_MAX || Corr_in > I_MAX) {
            duty_nuevo = 180.0f; // Duty al mínimo seguro (5%)
        }

        // 5. Actualización del PWM físico y del disparo del ADC en el centro del pulso
        __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_1, (uint32_t)duty_nuevo);
        __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_2, (uint32_t)(duty_nuevo / 2.0f));
    }
}
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{
  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/
  HAL_Init();

  /* Configure the system clock */
  SystemClock_Config();

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_DMA_Init();
  MX_ADC1_Init();
  MX_USB_DEVICE_Init();
  MX_TIM2_Init();

  /* USER CODE BEGIN 2 */
  HAL_ADCEx_Calibration_Start(&hadc1);
  HAL_ADC_Start_DMA(&hadc1, (uint32_t*)adc_buffer, 4 * NUM_SAMPLES);

  // Inicialización de disparo a la mitad del pulso inicial
  __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_2, (__HAL_TIM_GET_COMPARE(&htim2, TIM_CHANNEL_1) / 2));

  HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_1);
  HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_2);
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
      char buffer[200];
      int len = sprintf(buffer,
          "<%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%lu>\r\n",
          Volt_in, Corr_in, Volt_out, Corr_out, Pot_in, Pot_out,
          Vref_actual, __HAL_TIM_GET_COMPARE(&htim2, TIM_CHANNEL_1));

      if (CDC_Transmit_FS((uint8_t*)buffer, len) == USBD_OK)
      {
          // Transmitido por USB
      }

      HAL_Delay(1000);

    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};
  RCC_PeriphCLKInitTypeDef PeriphClkInit = {0};

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
  PeriphClkInit.PeriphClockSelection = RCC_PERIPHCLK_ADC|RCC_PERIPHCLK_USB;
  PeriphClkInit.AdcClockSelection = RCC_ADCPCLK2_DIV6;
  PeriphClkInit.UsbClockSelection = RCC_USBCLKSOURCE_PLL_DIV1_5;
  if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInit) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief ADC1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_ADC1_Init(void)
{
  ADC_ChannelConfTypeDef sConfig = {0};

  hadc1.Instance = ADC1;
  hadc1.Init.ScanConvMode = ADC_SCAN_ENABLE;
  hadc1.Init.ContinuousConvMode = DISABLE;
  hadc1.Init.DiscontinuousConvMode = DISABLE;
  hadc1.Init.ExternalTrigConv = ADC_EXTERNALTRIGCONV_T2_CC2;
  hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  hadc1.Init.NbrOfConversion = 4;
  if (HAL_ADC_Init(&hadc1) != HAL_OK)
  {
    Error_Handler();
  }

  sConfig.Channel = ADC_CHANNEL_0;
  sConfig.Rank = ADC_REGULAR_RANK_1;
  sConfig.SamplingTime = ADC_SAMPLETIME_28CYCLES_5;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }

  sConfig.Channel = ADC_CHANNEL_1;
  sConfig.Rank = ADC_REGULAR_RANK_2;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }

  sConfig.Channel = ADC_CHANNEL_2;
  sConfig.Rank = ADC_REGULAR_RANK_3;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }

  sConfig.Channel = ADC_CHANNEL_3;
  sConfig.Rank = ADC_REGULAR_RANK_4;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief TIM2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM2_Init(void)
{
  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};
  TIM_OC_InitTypeDef sConfigOC = {0};

  htim2.Instance = TIM2;
  htim2.Init.Prescaler = 0;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 3599;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim2) != HAL_OK)
  {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim2, &sClockSourceConfig) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_Init(&htim2) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim2, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigOC.OCMode = TIM_OCMODE_PWM1;
  sConfigOC.Pulse = 1800;
  sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
  sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
  if (HAL_TIM_PWM_ConfigChannel(&htim2, &sConfigOC, TIM_CHANNEL_1) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigOC.OCMode = TIM_OCMODE_PWM2;
  if (HAL_TIM_PWM_ConfigChannel(&htim2, &sConfigOC, TIM_CHANNEL_2) != HAL_OK)
  {
    Error_Handler();
  }

  HAL_TIM_MspPostInit(&htim2);
}

/**
  * Enable DMA controller clock
  */
static void MX_DMA_Init(void)
{
  __HAL_RCC_DMA1_CLK_ENABLE();
  HAL_NVIC_SetPriority(DMA1_Channel1_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(DMA1_Channel1_IRQn);
}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
}

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  __disable_irq();
  while (1)
  {
  }
}

#ifdef  USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line)
{
}
#endif /* USE_FULL_ASSERT */
