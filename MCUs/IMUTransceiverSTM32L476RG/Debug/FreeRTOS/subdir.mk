################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (12.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../FreeRTOS/heap_4.c 

OBJS += \
./FreeRTOS/heap_4.o 

C_DEPS += \
./FreeRTOS/heap_4.d 


# Each subdirectory must supply rules for building sources it contributes
FreeRTOS/%.o FreeRTOS/%.su FreeRTOS/%.cyclo: ../FreeRTOS/%.c FreeRTOS/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m4 -std=gnu11 -g3 -DDEBUG -DUSE_HAL_DRIVER -DSTM32L476xx -c -I../Core/Inc -I../Drivers/STM32L4xx_HAL_Driver/Inc -I../Drivers/STM32L4xx_HAL_Driver/Inc/Legacy -I../Drivers/CMSIS/Device/ST/STM32L4xx/Include -I../Drivers/CMSIS/Include -I../FreeRTOS/include -I../FreeRTOS/ARM_CM4F -O0 -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb -o "$@"

clean: clean-FreeRTOS

clean-FreeRTOS:
	-$(RM) ./FreeRTOS/heap_4.cyclo ./FreeRTOS/heap_4.d ./FreeRTOS/heap_4.o ./FreeRTOS/heap_4.su

.PHONY: clean-FreeRTOS

