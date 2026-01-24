#include "FreeRTOS.h"
#include "task.h"
#include "stm32l4xx_hal.h"

void vApplicationStackOverflowHook(TaskHandle_t xTask, char *pcTaskName) {
    (void)xTask;
    (void)pcTaskName;
    for (;;);
}

void vApplicationTickHook(void) {
    HAL_IncTick();
}