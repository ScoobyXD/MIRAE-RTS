#include "Drivers/I2C.h"
#include "stm32l476xx.h"

volatile uint32_t tmpreg;


void I2C1_MultiRead(uint8_t devAddr, uint8_t regAddr, uint8_t *buf, uint8_t len){
    while(I2C1->ISR & I2C_ISR_BUSY);

    // Write register address
    I2C1->CR2 = (devAddr << 1) //i dont think i need this bevause we do it again later
              | (1 << I2C_CR2_NBYTES_Pos);

    I2C1->CR2 |= I2C_CR2_START;

    while(!(I2C1->ISR & I2C_ISR_TXIS));//we want ISR to be 2 in order to get out of loop
    I2C1->TXDR = regAddr;

    while(!(I2C1->ISR & I2C_ISR_TC));

    // Read multiple bytes
    I2C1->CR2 = (devAddr << 1)
              | (len << I2C_CR2_NBYTES_Pos)
              | I2C_CR2_RD_WRN
              | I2C_CR2_AUTOEND;

    I2C1->CR2 |= I2C_CR2_START;

    for(uint8_t i=0; i<len; i++){
    	while(!(I2C1->ISR & I2C_ISR_RXNE));
    	buf[i] = I2C1->RXDR; //remember indexing already sets it to value of pointer, not the address
    }

    while(!(I2C1->ISR & I2C_ISR_STOPF));
    I2C1->ICR = I2C_ICR_STOPCF;
}


uint8_t I2C1_Read(uint8_t devAddr, uint8_t regAddr){
	uint8_t data;

	while(I2C1->ISR & I2C_ISR_BUSY); //Wait until bus is free

	// First: Write the register address (no AUTOEND - we need restart)
	I2C1->CR2 = (devAddr << 1)
			  | (1 << I2C_CR2_NBYTES_Pos); // 1 byte (register addr)

	I2C1->CR2 |= I2C_CR2_START; //Send slave address + R/W bit to slave device and wait for an ack

	uint32_t timeout = 1000000;
	while (!(I2C1->ISR & I2C_ISR_TXIS)) {
	    //uint32_t isr = I2C1->ISR;

	    //if (isr & I2C_ISR_NACKF) break;
	   // if (isr & I2C_ISR_BERR)  break;
	   // if (isr & I2C_ISR_ARLO)  break;
	   // if (isr & I2C_ISR_TIMEOUT) break;
	   // if (--timeout == 0) break;
	}

	//while(!(I2C1->ISR & I2C_ISR_TXIS)); //Any time you read a register, you’re working on a copy and with "if" statement, anytime result is not 0, then its true. Remember for every START its SDA goes low when SCL high and every devic on the bus sees this signal. Start and ACK are SDA pulled low.
	I2C1->TXDR = regAddr;

	// Wait for transfer complete (TC), not STOPF since no AUTOEND
	while(!(I2C1->ISR & I2C_ISR_TC));

	// Second: Read 1 byte with repeated START
	I2C1->CR2 = (devAddr << 1)
			  | (1 << I2C_CR2_NBYTES_Pos)
			  | I2C_CR2_RD_WRN             // Read mode
			  | I2C_CR2_AUTOEND;

	I2C1->CR2 |= I2C_CR2_START;            // Repeated START

	// Wait for RXNE (data received)
	while(!(I2C1->ISR & I2C_ISR_RXNE));
	data = I2C1->RXDR;

	// Wait for STOP
	while(!(I2C1->ISR & I2C_ISR_STOPF));
	I2C1->ICR = I2C_ICR_STOPCF;

	return data;
}


void I2C1_Write(uint8_t devAddr, uint8_t regAddr, uint8_t data){

	while(I2C1->ISR & I2C_ISR_BUSY); //Wait until bus is free

	I2C1->CR2 = (devAddr << 1)           //7-bit addr shifted to bits [7:1]
			  | (2 << I2C_CR2_NBYTES_Pos) //2 bytes to send (reg + data)
			  | I2C_CR2_AUTOEND;          //Auto end after transfer

	I2C1->CR2 |= I2C_CR2_START; //Start I2C

	while(!(I2C1->ISR & I2C_ISR_TXIS)); // Wait for when TXIS is cleared (this register clears itself everytime it TXs)
	I2C1->TXDR = regAddr;

	// Wait for TXIS, send data
	while(!(I2C1->ISR & I2C_ISR_TXIS));
	I2C1->TXDR = data;

	// Wait for STOPF (transfer complete)
	while(!(I2C1->ISR & I2C_ISR_STOPF));
	I2C1->ICR = I2C_ICR_STOPCF;  // Clear STOP flag
}


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
	RCC->CCIPR = RCC_CCIPR_I2C1SEL_1;
	//RCC->CR &= ~RCC_CR_HSION;
	//RCC->CR |= RCC_CR_HSION;
	//RCC->CCIPR &= ~RCC_CCIPR_I2C1SEL_1;
	//RCC->CCIPR |= RCC_CCIPR_I2C1SEL_1; //chose the HSI16 clock (16MHz), this is not the I2C SCL speed, its just the internal peripheral clock feeding the I2C timing generator

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
