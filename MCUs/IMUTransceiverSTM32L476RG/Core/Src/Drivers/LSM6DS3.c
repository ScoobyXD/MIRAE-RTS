#include "Drivers/LSM6DS3.h"
#include "stm32l476xx.h"
#include "Drivers/I2C.h"


uint8_t LSM6DS3_Init(void){
	uint8_t result = I2C1_Read(LSM6DS3_ADDR, WHO_AM_I);
	if(result == 0x69){
		I2C1_Write(LSM6DS3_ADDR, CTRL1_XL, 0x70); //Acceleration 833Hz sampling rate, 2g before saturation, 400Hz in changes per second
		I2C1_Write(LSM6DS3_ADDR, CTRL2_G, 0x60); //Gyroscope 416Hz sampling rate, 250 dps
		I2C1_Write(LSM6DS3_ADDR, CTRL3_C, 0x44); //Enable block data update (read MSB & LSB first then write into register) and auto increment addresses while reading multiple bytes
		return result;
	}
	return result;
}


//The LSM6DS3 will keep providing the next byte as long as the master keeps ACKing and clocking SCL.
//The master doesn’t “stop listening”; it ends the transaction by NACK + STOP (or STOP).
void LSM6DS3_GyroAccelRead(LSM6DS3_Sample *data){
	uint8_t buf[GyroAccelReadSize]; //It seems silly to copy 96 bits from IMU to MCU's buffer, then copy it again to data struct

	I2C1_MultiRead(LSM6DS3_ADDR, OUTX_L_Gyro, buf, GyroAccelReadSize); //Starts reading at OUTX_L_Gyro then register increments by GyroAccelReadSize
	data->gx = (uint16_t)(buf[1] << 8 | buf[0]);
	data->gy = (uint16_t)(buf[3] << 8 | buf[2]);
	data->gz = (uint16_t)(buf[5] << 8 | buf[4]);
	data->ax = (uint16_t)(buf[7] << 8 | buf[6]);
	data->ay = (uint16_t)(buf[9] << 8 | buf[8]);
	data->az = (uint16_t)(buf[11] << 8 | buf[10]);
}
