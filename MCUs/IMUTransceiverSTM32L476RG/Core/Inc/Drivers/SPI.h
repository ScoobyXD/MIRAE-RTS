#ifndef SPI_H_
#define SPI_H_

#include <stdint.h>

//SPI1 Pins (Arduino header on Nucleo-L476RG):
//PA5 - SPI1_SCK  (D13, also LD2 LED -- we sacrifice LD2, heartbeat is on PA8)
//PA6 - SPI1_MISO (D12)
//PA7 - SPI1_MOSI (D11)
//PB6 - CS (manual GPIO, directly driven, active low)

void SPI1_Config(void);
uint8_t SPI1_TransferByte(uint8_t data);
void SPI1_CS_Low(void);
void SPI1_CS_High(void);

#endif
