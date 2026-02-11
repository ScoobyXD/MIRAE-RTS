#include "stm32l476xx.h"
#include "Drivers/SPI.h"
#include "Drivers/USART.h"

//SPI1 on STM32L476RG:
//  PA5 = SCK  (AF5)
//  PA6 = MISO (AF5)
//  PA7 = MOSI (AF5)
//  PB6 = CS   (GPIO output, directly driven)
//
//SPI1 is on APB2 bus. At 80MHz SYSCLK with APB2 divider=1, APB2 = 80MHz.
//MCP2515 max SPI clock is 10MHz, so we use prescaler /8 = 10MHz or /16 = 5MHz.
//Using /16 = 5MHz to be safe with jumper wires.

void SPI1_Config(void){
    volatile uint32_t tmpreg;

    //--- GPIO clock for Port A (PA5,PA6,PA7) and Port B (PB6) ---
    //Port A clock should already be on from USART2_Config, but set it anyway
    RCC->AHB2ENR |= RCC_AHB2ENR_GPIOAEN;
    RCC->AHB2ENR |= RCC_AHB2ENR_GPIOBEN;
    tmpreg = RCC->AHB2ENR;
    UNUSED(tmpreg);

    //--- PA5 (SCK): Alternate function mode ---
    GPIOA->MODER &= ~GPIO_MODER_MODE5_Msk;
    GPIOA->MODER |= GPIO_MODER_MODE5_1; //10 = AF
    //--- PA6 (MISO): Alternate function mode ---
    GPIOA->MODER &= ~GPIO_MODER_MODE6_Msk;
    GPIOA->MODER |= GPIO_MODER_MODE6_1; //10 = AF
    //--- PA7 (MOSI): Alternate function mode ---
    GPIOA->MODER &= ~GPIO_MODER_MODE7_Msk;
    GPIOA->MODER |= GPIO_MODER_MODE7_1; //10 = AF

    //AF5 for SPI1 on PA5, PA6, PA7 (all in AFRL, positions 5,6,7)
    //Each pin gets 4 bits in AFR[0] (AFRL). AF5 = 0101 = 0x5
    //PA5: bits [23:20], PA6: bits [27:24], PA7: bits [31:28]
    GPIOA->AFR[0] &= ~((0xFUL << 20) | (0xFUL << 24) | (0xFUL << 28));
    GPIOA->AFR[0] |=  ((0x5UL << 20) | (0x5UL << 24) | (0x5UL << 28));

    //High speed for SPI pins (11 = very high speed)
    GPIOA->OSPEEDR |= (GPIO_OSPEEDR_OSPEED5 | GPIO_OSPEEDR_OSPEED6 | GPIO_OSPEEDR_OSPEED7);

    //No pull-up/pull-down for SCK and MOSI, pull-up on MISO
    GPIOA->PUPDR &= ~(GPIO_PUPDR_PUPD5_Msk | GPIO_PUPDR_PUPD6_Msk | GPIO_PUPDR_PUPD7_Msk);
    //MISO pull-up can help when CS is not selected, but usually not needed. Leave floating.

    //--- PB6 (CS): General purpose output, push-pull, start HIGH (deselected) ---
    GPIOB->MODER &= ~GPIO_MODER_MODE6_Msk;
    GPIOB->MODER |= GPIO_MODER_MODE6_0; //01 = General output
    GPIOB->OTYPER &= ~GPIO_OTYPER_OT6;  //0 = Push-pull
    GPIOB->OSPEEDR |= GPIO_OSPEEDR_OSPEED6; //Very high speed
    GPIOB->ODR |= GPIO_ODR_OD6; //Start HIGH (CS deselected, active low)

    //--- SPI1 peripheral clock enable ---
    RCC->APB2ENR |= RCC_APB2ENR_SPI1EN;
    tmpreg = RCC->APB2ENR;
    UNUSED(tmpreg);

    //--- SPI1 configuration ---
    //Disable SPI first
    SPI1->CR1 &= ~SPI_CR1_SPE;

    SPI1->CR1 = 0; //Clear everything first

    //Master mode
    SPI1->CR1 |= SPI_CR1_MSTR;

    //Baud rate: fPCLK/16 = 80MHz/16 = 5MHz
    //BR[2:0] = 011 for /16
    SPI1->CR1 |= (SPI_CR1_BR_0 | SPI_CR1_BR_1);

    //CPOL=0, CPHA=0 (SPI Mode 0, which MCP2515 uses: sample on rising edge)
    //These are already 0 from the clear above

    //MSB first (LSBFIRST=0, already 0)

    //Software slave management: SSM=1, SSI=1
    //This means we control CS manually via PB6 GPIO
    //SSI=1 keeps the internal NSS high so master mode stays active
    SPI1->CR1 |= SPI_CR1_SSM;
    SPI1->CR1 |= SPI_CR1_SSI;

    //Full duplex (BIDIMODE=0, RXONLY=0, already 0)

    //8-bit data frame -- on STM32L4, data size is in CR2 DS[3:0] bits
    //DS = 0111 for 8-bit (bits 11:8 of CR2)
    SPI1->CR2 &= ~SPI_CR2_DS_Msk;
    SPI1->CR2 |= (SPI_CR2_DS_0 | SPI_CR2_DS_1 | SPI_CR2_DS_2); //0111 = 8-bit

    //FRXTH=1: RXNE event generated when FIFO level >= 8-bit (1 byte)
    //Without this, STM32L4 SPI waits for 16-bit worth of data before setting RXNE
    SPI1->CR2 |= SPI_CR2_FRXTH;

    //Enable SPI
    SPI1->CR1 |= SPI_CR1_SPE;
}

uint8_t SPI1_TransferByte(uint8_t data){
    //Wait for TXE (transmit buffer empty)
    while(!(SPI1->SR & SPI_SR_TXE));

    //Write data to DR -- MUST write as 8-bit to avoid sending 16 bits
    //On STM32L4, DR is 16-bit wide but we want 8-bit transfers
    *((volatile uint8_t*)&SPI1->DR) = data;

    //Wait for RXNE (receive buffer not empty)
    while(!(SPI1->SR & SPI_SR_RXNE));

    //Read received byte
    return *((volatile uint8_t*)&SPI1->DR);
}

void SPI1_CS_Low(void){
    GPIOB->ODR &= ~GPIO_ODR_OD6; //PB6 LOW = chip selected
}

void SPI1_CS_High(void){
    GPIOB->ODR |= GPIO_ODR_OD6; //PB6 HIGH = chip deselected
}
