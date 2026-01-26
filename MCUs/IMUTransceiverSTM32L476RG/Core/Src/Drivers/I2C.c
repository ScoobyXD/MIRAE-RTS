#include "Drivers/I2C.h"
#include "stm32l476xx.h"

volatile uint32_t tmpreg;

void I2C1_Config(void){
	RCC->AHB2ENR |= RCC_AHB2ENR_GPIOBEN; //Turn on clock for AHB2 bus
	tmpreg = RCC->AHB2ENR;
	UNUSED(tmpreg);
	GPIOB->MODER &= ~(GPIO_MODER_MODE8_Msk | GPIO_MODER_MODE9_Msk);
	GPIOB->MODER |= (GPIO_MODER_MODE8_1 | GPIO_MODER_MODE9_1); //Alternate Function
	GPIOB->AFR[1] &= ~(GPIO_AFRH_AFSEL8_Msk | GPIO_AFRH_AFSEL9_Msk);
	GPIOB->AFR[1] |= (GPIO_AFRH_AFSEL8_2 | GPIO_AFRH_AFSEL9_2); //AF4 (0100)
	GPIOB->OTYPER |= GPIO_OTYPER_OT8 | GPIO_OTYPER_OT9; //Output type open-drain, needed for I2C because open-drain allows multiple devices to share SDA/SCL safely
	GPIOB->PUPDR &= ~((GPIO_PUPDR_PUPD8_0) | (GPIO_PUPDR_PUPD9_0));
	GPIOB->PUPDR |= (GPIO_PUPDR_PUPD8_0) | (GPIO_PUPDR_PUPD9_0); //PB8/PB9 pull-up register. We set output type to be open-drain,so we need a pull up resistor, also need external 4.7kOhms resistor, internal one too weak
	GPIOB->OSPEEDR &= ~((GPIO_OSPEEDR_OSPEED8) | (GPIO_OSPEEDR_OSPEED9));
	GPIOB->OSPEEDR |= (GPIO_OSPEEDR_OSPEED8) | (GPIO_OSPEEDR_OSPEED9); //Set speed to the highest (very high speed) cuz why not(11)

	RCC->APB1ENR1 |= RCC_APB1ENR1_I2C1EN;
	tmpreg = RCC->APB1ENR1;
	UNUSED(tmpreg);
	I2C1->CR1 &= ~I2C_CR1_PE; //Turn off I2C1 control for now
	RCC->APB1RSTR1 |= RCC_APB1RSTR1_I2C1RST; //Im not sure why its recommended to reset, but I guess if we REALLY want to make sure, we reset
	RCC->APB1RSTR1 &= ~RCC_APB1RSTR1_I2C1RST; //So we don't want to keep the register value as 1, or else it will constantly reset, we set it back to 0 to stop resetting.

	// Keep analog filter ON (default), digital filter DNF=0 (default)
	I2C1->CR1 &= ~I2C_CR1_ANFOFF; // 0 = analog filter enabled (This removes very short glitches/spikes (typical <50 ns) that could be mistaken as edges. You almost always leave it enabled)
	I2C1->CR1 &= ~I2C_CR1_DNF;  // DNF = 0 digital filter off (I guess similar role of filtering random stuff but digitally?
	RCC->CCIPR = RCC_CCIPR_I2C1SEL_1; //chose the HSI16 clock (16MHz), this is not the I2C SCL speed, its just the internal peripheral clock feeding the I2C timing generator

	//Configured I2C for 400kHz mode
	I2C1->TIMINGR = //TIMINGR should be fully assigned, so = not |=
		0x1U << I2C_TIMINGR_PRESC_Pos | //prescaler
		0x3U << I2C_TIMINGR_SCLDEL_Pos | //delay between when the clock falling edge and the SDA change (4+1)ticks * 100ns = 400ns
		0x2U << I2C_TIMINGR_SDADEL_Pos | //extra time SDA is held stable after SCL rising edge (2) * 100ns = 200ns
		0x3U << I2C_TIMINGR_SCLH_Pos | //period the clock stays low (49+1)ticks * 100ns = 5us
		0x9U << I2C_TIMINGR_SCLL_Pos; //period the clock stays high (49+1)ticks * 100ns = 5us

	//I2C1->CR1 |= (I2C_CR1_TXDMAEN) | (I2C_CR1_RXDMAEN); //Enable TX and RX to read using DMA
	//I2C1->ICR = I2C_ICR_CLEAR; //clear I2C ICR masks

	//NVIC_SetIRQ(I2C1_EV_IRQn); //enable interrupt events
	//NVIC_SetIRQ(I2C1_ER_IRQn); //enable interrupt errors

	I2C1->CR1 |= I2C_CR1_PE; //enable the I2C peripheral
}
