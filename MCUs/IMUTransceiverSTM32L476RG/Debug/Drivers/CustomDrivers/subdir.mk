################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (12.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../Drivers/CustomDrivers/I2C.c \
../Drivers/CustomDrivers/lsm6ds3.c 

OBJS += \
./Drivers/CustomDrivers/I2C.o \
./Drivers/CustomDrivers/lsm6ds3.o 

C_DEPS += \
./Drivers/CustomDrivers/I2C.d \
./Drivers/CustomDrivers/lsm6ds3.d 


# Each subdirectory must supply rules for building sources it contributes
Drivers/CustomDrivers/%.o Drivers/CustomDrivers/%.su Drivers/CustomDrivers/%.cyclo: ../Drivers/CustomDrivers/%.c Drivers/CustomDrivers/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m4 -std=gnu11 -g3 -DDEBUG -DUSE_HAL_DRIVER -DSTM32L476xx -c -I../Core/Inc -I../Drivers/STM32L4xx_HAL_Driver/Inc -I../Drivers/STM32L4xx_HAL_Driver/Inc/Legacy -I../Drivers/CMSIS/Device/ST/STM32L4xx/Include -I../Drivers/CMSIS/Include -I../FreeRTOS/include -I../FreeRTOS/ARM_CM4F -O0 -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb -o "$@"

clean: clean-Drivers-2f-CustomDrivers

clean-Drivers-2f-CustomDrivers:
	-$(RM) ./Drivers/CustomDrivers/I2C.cyclo ./Drivers/CustomDrivers/I2C.d ./Drivers/CustomDrivers/I2C.o ./Drivers/CustomDrivers/I2C.su ./Drivers/CustomDrivers/lsm6ds3.cyclo ./Drivers/CustomDrivers/lsm6ds3.d ./Drivers/CustomDrivers/lsm6ds3.o ./Drivers/CustomDrivers/lsm6ds3.su

.PHONY: clean-Drivers-2f-CustomDrivers

