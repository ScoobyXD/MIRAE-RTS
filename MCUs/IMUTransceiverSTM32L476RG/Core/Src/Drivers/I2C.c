#include "stm32l476xx.h"
#include "Drivers/I2C.h"
#include "Drivers/USART.h"

volatile uint32_t tmpreg;


void I2C1_MultiRead(uint8_t devAddr, uint8_t regAddr, uint8_t *buf, uint8_t len){
    while(I2C1->ISR & I2C_ISR_BUSY);

    // Write register address
    I2C1->CR2 = (devAddr << 1) //i dont think i need this bevause we do it again later
              | (1 << I2C_CR2_NBYTES_Pos);
    I2C1->CR2 |= I2C_CR2_START;
    while(!(I2C1->ISR & I2C_ISR_TXIS));
    I2C1->TXDR = regAddr;

    while(!(I2C1->ISR & I2C_ISR_TC));
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

	//Handy rule list for AUTOEND & RELOAD:
	//AUTOEND=1	STOP auto-generated
	//AUTOEND=0, RELOAD=0	Check TC (you decide START or STOP)
	//RELOAD=1	RELOAD 1 means after NBYTES are sent, pause to reprogram new NBYTES for next chunk. Controls how data bytes continue, must use same address, same direction, no start, no stop, just more bytes (you must reload NBYTES and use TCR in ISR)

	//First START: Write to slave address, ack, TXIS flag gets set, then TXDR register address
	//We keep AUTOEND and RELOAD 0 because there is no STOP, we dont want to lose control of the bus so no AUTOEND and we will do a direction change from initial write to read so no RELOAD
	I2C1->CR2 = (devAddr << 1)
			  | (1 << I2C_CR2_NBYTES_Pos); //1 byte (register addr), remember that slave address (devAddr) does not count as NBYTE data bytes
	I2C1->CR2 |= I2C_CR2_START; //Generate and send I2C start signal (start signals are pull low while scl goes high), then send slave address+R/W bit to slave device, receive ACK/NACK from the slave, and process ACK/NACKF internally. If we get NACK then set NACKF on ISR, if ACK and rd_wrn = 0(write) and NBYTES > 0 then hardware sets TXIS = 1. Also every device on the bus sees this signal.
	while (!(I2C1->ISR & I2C_ISR_TXIS)); //Back an ACK confirmation. If we get ACK after START, TXIS flag on ISR should be 1, meaning TXDR is empty and ready to be filled with data to send to slave. Also, any time you read a register as done here, you’re working on a copy, as long as result is not 0 then its true.
	I2C1->TXDR = regAddr; //After the slave ACKs its address, the first data byte you send tells the slave which internal register you want to talk to, the slave stores that value as an internal register pointer. btw I2C RXDR/TXDR is only 8 bits long, thats why we have output high and low registers in IMU

	while(!(I2C1->ISR & I2C_ISR_TC)); //Wait for transfer complete, this flag is set by hardware only when RELOAD=0, AUTOEND=0 and NBYTES data have been transferred
	I2C1->CR2 = (devAddr << 1) //Second START: Read 1 byte with repeated START. Repeated STARTS lets you change read/write direction and new NBYTES (you can have multiple starts without a stop, master never releases bus)
			  | (1 << I2C_CR2_NBYTES_Pos)
			  | I2C_CR2_RD_WRN //Read mode
			  | I2C_CR2_AUTOEND; //AUTOEND 1 means when NBYTES reaches 0 automatically generate STOP. We actually want to let go of bus after this read.
	I2C1->CR2 |= I2C_CR2_START; //As the master, you really do tell the slave what to do, when to start, what registers to point to next, sends requests for what data it wants, etc

	while(!(I2C1->ISR & I2C_ISR_RXNE)); //Wait for RXNE (data received)
	data = I2C1->RXDR;

	while(!(I2C1->ISR & I2C_ISR_STOPF)); // Wait for STOP (we set AUTOEND = 1 in 2nd start which will produce STOPF flag in ISR)
	I2C1->ICR = ( //Clear flags in ICR (different from ISR)
			I2C_ICR_NACKCF |
			I2C_ICR_STOPCF |
			I2C_ICR_BERRCF |
			I2C_ICR_ARLOCF |
			I2C_ICR_OVRCF |
			I2C_ICR_TIMOUTCF);
	return data;
}


void I2C1_Write(uint8_t devAddr, uint8_t regAddr, uint8_t data){

	while(I2C1->ISR & I2C_ISR_BUSY);

	I2C1->CR2 = (devAddr << 1)
			  | (2 << I2C_CR2_NBYTES_Pos) //2 bytes to send (regAddr + data)
			  | I2C_CR2_AUTOEND;
	I2C1->CR2 |= I2C_CR2_START;
	while(!(I2C1->ISR & I2C_ISR_TXIS));
	I2C1->TXDR = regAddr;
	while(!(I2C1->ISR & I2C_ISR_TXIS));
	I2C1->TXDR = data;

	while(!(I2C1->ISR & I2C_ISR_STOPF)); //Remember we set AUTOEND=1 so it will automatically do STOPF when TX is complete
	I2C1->ICR = (
				I2C_ICR_NACKCF |
				I2C_ICR_STOPCF |
				I2C_ICR_BERRCF |
				I2C_ICR_ARLOCF |
				I2C_ICR_OVRCF |
				I2C_ICR_TIMOUTCF);
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


	RCC->CCIPR &= ~RCC_CCIPR_I2C1SEL_1;
	RCC->CCIPR |= RCC_CCIPR_I2C1SEL_1; //Choose the HSI16 clock (16MHz), this is not the I2C SCL speed, its just the internal peripheral clock feeding the I2C timing generator
	RCC->CR &= ~RCC_CR_HSION;
	RCC->CR |= RCC_CR_HSION; //Turn on HSI clock

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
