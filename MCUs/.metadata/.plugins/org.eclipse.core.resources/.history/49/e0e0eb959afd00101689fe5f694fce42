//Pins
//D7-PA_8-Heartbeat LED
//D15-PB_8-SCL1
//D14-PB_9-SDA1

#include <stdio.h>
#include "stm32l476xx.h"
#include "FreeRTOS.h"
#include "task.h" //Used for FreeRTOS
#include "Drivers/I2C.h"
#include "Drivers/lsm6ds3.h"
#include "main.h"

void SystemClock_Config(void);
void GPIOPortConfig(void);
void I2CConfig(void);
static void prvCreateTasks(void);
void vHeartbeat(void *pvParameters);
void vIMURead();//void *pvParameters);

//static LSM6DS3_Sample IMU_Sample;

int main(void){
  HAL_Init(); //Necessary for now
  SystemClock_Config();
  GPIOPortConfig();
  I2C1_Config();
  LSM6DS3_Init();

  prvCreateTasks();
  vTaskStartScheduler(); //Actually runs rtos

  for(;;);
}

static void prvCreateTasks(void){
	static uint32_t rate = 500; //Static variables dont live on stack, they get permanent address in .data or .bss section that persists for the whole program
	xTaskCreate(vHeartbeat, "Heartbeat", 128, (void*)&rate, 1, NULL);
	xTaskCreate(vIMURead, "IMURead", 1024, NULL, 2, NULL);
}

void vHeartbeat(void *pvParameters){
	uint32_t *rate = (uint32_t*)pvParameters;

	for(;;){
		GPIOA->ODR |= GPIO_ODR_OD8; //Turn on external LED PA_8 (pin D7)
		vTaskDelay(pdMS_TO_TICKS(*rate));
		GPIOA->ODR &= ~GPIO_ODR_OD8; //Turn off
		vTaskDelay(pdMS_TO_TICKS(*rate));
	}
}

void vIMURead(void *pvParameters){
	LSM6DS3_Sample IMU_Sample;

	for(;;){
		LSM6DS3_GyroAccelRead(&IMU_Sample);
		printf("Gyro: gx=%d gy=%d gz=%d", IMU_Sample.gx, IMU_Sample.gy, IMU_Sample.gz);
		printf("Accel: ax=%d ay=%d az=%d", IMU_Sample.ax, IMU_Sample.ay, IMU_Sample.az);
		vTaskDelay(pdMS_TO_TICKS(50));
	}
}

void GPIOPortConfig(void){
	volatile uint32_t tmpreg;

	RCC->AHB2ENR |= RCC_AHB2ENR_GPIOAEN; //Turn on clock for AHB2 bus
	tmpreg = RCC->AHB2ENR;
	UNUSED(tmpreg);
	GPIOA->MODER &= ~GPIO_MODER_MODE8_Msk; //The starting value of MODER is like 111111111111111111111 so you need to mask to make sure the register you want is primed to set value
	GPIOA->MODER |= GPIO_MODER_MODE8_0; //General output
}

void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  if (HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1) != HAL_OK)
  {
    Error_Handler();
  }

  // Enable MSI and the PLL for 80MHz
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_MSI;
  RCC_OscInitStruct.MSIState = RCC_MSI_ON;
  RCC_OscInitStruct.MSICalibrationValue = 0;
  RCC_OscInitStruct.MSIClockRange = RCC_CR_MSIRANGE_7; // Set to 8MHz. CubeIDE defaults project to RCC_CR_MSIRANGE_6 (4MHz). Internal RC oscillator (MSI) tops out at 48MHz.
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_MSI;
  RCC_OscInitStruct.PLL.PLLM = 1; // 8MHz / 1 = 8MHz input to PLL
  RCC_OscInitStruct.PLL.PLLN = 20; // 8MHz * 20 = 160MHz VCO
  RCC_OscInitStruct.PLL.PLLR = 2; // 160MHz / 2 = 80MHz output
  RCC_OscInitStruct.PLL.PLLP = 7;
  RCC_OscInitStruct.PLL.PLLQ = 4;

  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  // Set clocks for 80MHz
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK|RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK; // Went from MSI to PLLCLK
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4) != HAL_OK) // As RCC_MSIRANGE_X goes higher, you need to increase this. 4 wait states for 80MHz because at that speed CPU much faster than flash memory can keep up with, so have it wait
  {
    Error_Handler();
  }
}

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
#endif
