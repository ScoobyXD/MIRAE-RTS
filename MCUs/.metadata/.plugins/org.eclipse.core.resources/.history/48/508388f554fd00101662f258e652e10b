#ifndef I2C_H_
#define I2C_H_

#ifndef UNUSED
#define UNUSED(X) (void)X
#endif

#include <stdint.h>

void I2C1_MultiRead(uint8_t devAddr, uint8_t regAddr, uint8_t *buf, uint8_t len);
uint8_t I2C1_Read(uint8_t devAddr, uint8_t regAddr);
void I2C1_Write(uint8_t devAddr, uint8_t regAddr, uint8_t data);
void I2C1_Config(void);

#endif
