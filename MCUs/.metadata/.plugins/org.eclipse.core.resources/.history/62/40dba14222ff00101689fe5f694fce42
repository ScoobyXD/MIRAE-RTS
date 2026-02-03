#ifndef LSM6DS3_H_
#define LSM6DS3_H_
#endif

#include "stm32l476xx.h" //do i need this?
#include <stdint.h>

#define LSM6DS3_ADDR	0x6A //If SA0 connected to GND, if connected to VCC than 0x6B, remember this is a 7-bit address, it caps at 0x7F

#define WHO_AM_I		0x0F //Should return 0x69
#define CTRL1_XL		0x10 //Acceleration 833Hz sampling rate, 2g before saturation, 400Hz in changes per second
#define CTRL2_G			0x11 //Gyroscope 416Hz sampling rate, 250 dps
#define CTRL3_C			0x12
//theres a lot more control registers but not sure if we need them

//later temp

#define GyroAccelReadSize	0x0C
#define OUTX_L_Gyro		0x22
#define OUTX_H_Gyro		0x23
#define OUTY_L_Gyro		0x24
#define OUTY_H_Gyro		0x25
#define OUTZ_L_Gyro		0x26
#define OUTZ_H_Gyro		0x27

#define OUTX_L_Accel	0x28
#define OUTX_H_Accel	0x29
#define OUTY_L_Accel	0x2A
#define OUTY_H_Accel	0x2B
#define OUTZ_L_Accel	0x2C
#define OUTZ_H_Accel	0x2D

//later magnetometer OUT_MAG_RAW_X_L

typedef struct{
	int16_t	gx, gy, gz;
	int16_t ax, ay, az;
}LSM6DS3_Sample;

void LSM6DS3_Init(void);      // Returns WHO_AM_I value (0x69 = success)
void LSM6DS3_GyroAccelRead(LSM6DS3_Sample *data);

//rounding pg 58?
//temp?
//external magnetometer?

