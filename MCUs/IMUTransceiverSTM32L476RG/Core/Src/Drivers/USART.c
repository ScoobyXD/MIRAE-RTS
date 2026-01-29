#include <Drivers/USART.h>
#include "stm32l476xx.h"
#include <stdio.h>
#include "Drivers/LSM6DS3.h"
#include "Drivers/I2C.h"

void USART2_Config(void) {
	//Port A already opened in TurretMotors_Config
	RCC->APB1ENR1 &= ~RCC_APB1ENR1_USART2EN_Msk;
	RCC->APB1ENR1 |= RCC_APB1ENR1_USART2EN; //start APB1 timer (didnt need AHB1 to open APB1)
	tmpreg = RCC->APB1ENR1;
	UNUSED(tmpreg);

	GPIOA->MODER &= ~GPIO_MODER_MODE2_Msk; //keep in mind the reset value is 11, so need to BIC the mask first
	GPIOA->MODER |= GPIO_MODER_MODE2_1; //PA_2 (TX) 10 Alternate function
	GPIOA->MODER &= ~GPIO_MODER_MODE3_Msk;
	GPIOA->MODER |= GPIO_MODER_MODE3_1; //PA_3 (RX) 10 Alternate function

	GPIOA->AFR[0] |= (0x7UL << 8U); //Alternate function 0111 (USART2) for PA_2
	GPIOA->AFR[0] |= (0x7UL << 12U); //Alternate function 0111 (USART2) for PA_3

	//USART2->CR1 |= USART_CR1_PCE //parity control (1)enable/(0)disable
	//USART2->CR1 |= USART_CR1_PS; //parity 0 even, 1 odd. This field only written when USART disabled
	//USART2->CR1 &= ~USART_CR1_M1; //I want M[1:0] to be 00: 1 Start bit, 8 data bits, n stop bits (reset value)
	//USART2->CR1 &= ~USART_CR1_M0; (reset value)
	//USART2->CR2 &= ~USART_CR2_STOP; //set n stop bits to 1 stop bit (also, keep in mind 0 for all of these are default) im just setting these here for learning reasons (reset value)

	USART2->CR1 |= (
			USART_CR1_RE | //receiver enable
			USART_CR1_TE | //transmitter enable (only need if you are tx back to something, which I might do eventually)
			//USART_CR1_TXEIE | // it means TXIE interrupt will fire when you're no longer actively putting data into TDR. if you turn this on, then CR1's IDLE and TC will automatically turn on and constantly fire interrupts, ISR will constantly have IDLE, TXIE, and TC flags, the ensuing interrupt storm will cause live locks.
			USART_CR1_RXNEIE | //allow RXNE interrupts in USART2
			USART_CR1_UE); //enable usart2. This is last because other USART2 stuff needs to configure first
						   //also keep in mind, bit 28 M1 word length default at 0, 1 start bit, 8 data bits, n stop bits.

	USART2->BRR = 4000000 / 9600; //4mHz/9600 baud. Gives 417hz/1 baud. UART frame is 1 bit every 417 APB1 clock cycles
								   //we set M[1:0] as 00 so 1 start bit, 8 data bits, and 1 end bit. 10 x 417 is 4170 clock cycles per word
								   //if 4mHz that mean each uart word should take about 1ms and each bit is 1x10^-4 s. Which is sort of slow?
	NVIC_SetIRQ(USART2_IRQn); //set up NVIC to allow USART2 interrupts. Now the hardware takes over so whenever RDR has data, the hardware will trigger the interrupt handler
}


