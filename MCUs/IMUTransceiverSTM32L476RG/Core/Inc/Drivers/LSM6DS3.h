#ifndef LSM6DS3_H_
#define LSM6DS3_H_

#include "stm32l476xx.h" //do i need this?
#include <stdint.h>

#define LSM6DS3_ADDR	0x06A //If SA0 connected to GND, if connected to VCC than 0x06B

#define WHO_AM_I		0x0F //Should return 0x69
#define CTRL1_XL		0x10 //0x70 Acceleration 833Hz sampling rate, 2g before saturation, 400Hz in changes per second
#define CTRL2_G			0x11 //0x60 Gyroscope 416Hz sampling rate, 250 dps
#define CTRL3_G			0x12
//theres a lot more control registers but not sure if we need them

#define OUTX_L_G		0x22
#define OUTX_H_G		0x23
#define OUTY_L_G		0x24
#define OUTY_H_G		0x25
#define OUTZ_L_G		0x26
#define OUTZ_H_G		0x27

#define OUTX_L_XL		0x28
#define OUTX_H_XL		0x29
#define OUTY_L_XL		0x2A
#define OUTY_H_XL		0x2B
#define OUTZ_L_XL		0x2C
#define OUTZ_H_XL		0x2D

typedef struct{
	int16_t ax, ay, az;
	int16_t	gx, gy, gz;
} LSM6DS3_Data;

uint8_t LSM6DS3_Init(void);      // Returns WHO_AM_I value (0x69 = success)
void LSM6DS3_ReadAll(LSM6DS3_Data *data);

//rounding pg 58?
//temp?
//external magnetometer?
#endif
