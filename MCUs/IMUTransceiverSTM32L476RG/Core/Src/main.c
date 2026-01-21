//This file is for STM32 L476RGT3
//But the actual STM32 part on the transceiver PCB will be L476RGT6 because JLCPCB didnt have enough L476RGT3, but code should work for both just fine
//Program is for LSM6DS3TR 6-axis IMU and AT commands for cellular modem/e sim/antenna
#include "main.h"
#include "stm32l476xx.h"
#include "stm32l4xx_hal_pwr_ex.h"
#include "stdio.h"
#include "time.h"
#include "core_cm4.h"

#define MPU9250_Address 0x68u //ADO 0 device address
#define MPU9250_PWRMGMT1 0x6Bu //main power and clocking register on MPU9250
#define MPU9250_EXT_SENS_DATA_00 0x3B
#define MPU9250_SMPLRT_DIV 0x19
#define MPU9250_Config_Register 0x1A

#define DMA1_I2C1_TX DMA1_Channel6 //from datasheet, I2C1 is in DMA1 channel 6
#define DMA_ISR_TXTC DMA_ISR_TCIF6 //transfer complete (TC) interrupt flag for channel 6
#define DMA_IFCR_CLEAR 0x0FFFFFFF //clear all DMA IFCR flags

#define I2C_ICR_CLEAR 0x3F38 //clear all flags in I2C ICR

#define USART2_CLEAR 0x0F //clear USART2 ICR error flags
/*
 * I2C_ICR_STOPCF | //Clears the stop flag, which means a stop condition has been detected on the bus
 * I2C_ICR_NACKCF | //Clear the NACK flag, which appears when the receiver didn't acknowledge the byte
 * I2C_ICR_BERRCF | //Clear the bus error flag, which appears when there an error in the bus, maybe through electrical noise or misbehaving devices
 * I2C_ICR_ARLOCF | //Clear the arbitration flag, which appears when two masters try to control the bus (arbitration is resolving disputes)
 * I2C_ICR_OVRCF) //Overrun/underrun flag clear, which appears when data was lost because software/DMA didn't keep up)
 */

static uint8_t WriteBuffer[32];
static uint8_t ReadBuffer[32];
volatile uint32_t tmpreg;
volatile int16_t MPU9250_Data;
volatile int8_t MPU9250_Buffer[8];
volatile uint16_t UART_Command;

typedef enum {
	FAIL,
	COMPLETE
} Result;

void SystemClock_Config(void);
void TurretMotors_Config(void);
void TurretFire_Config(void);
void DMA1_Config(void);
void I2C1_Config(void);
void USART2_Config(void);
Result MPU9250_Config(I2C_TypeDef *I2CX, DMA_TypeDef *DMAX, DMA_Channel_TypeDef *DMA_ChannelX, uint8_t SlaveAddress, uint8_t RegisterAddress);

void NVIC_SetIRQ(IRQn_Type IRQ);
void USART2_IRQHandler(void); //must be called this name because written in interrupt vector table in .asm Startup.startup_stm21l476rgtx.s

Result I2C_Read(I2C_TypeDef *I2CX, DMA_TypeDef *DMAX, DMA_Channel_TypeDef *DMA_ChannelX, uint8_t SlaveAddress, uint8_t len);
Result I2C_Write(I2C_TypeDef *I2CX, DMA_TypeDef *DMAX, DMA_Channel_TypeDef *DMA_ChannelX, uint8_t SlaveAddress, uint8_t len);
Result I2C_BurstRead(I2C_TypeDef *I2CX, DMA_TypeDef *DMAX, DMA_Channel_TypeDef *DMA_ChannelX, uint8_t SlaveAddress, uint8_t RegisterAddress, uint8_t len);
void I2C_MPU9250_BurstRead(void);

void TurretUp(void);
void TurretDown(void);
void TurretLeft(void);
void TurretRight(void);
void TurretFire(void);
void TurretUpDownDoNothing(void);
void TurretLeftRightDoNothing(void);
void TurretFireDoNothing(void);

void wait(void);
void usartTest(void);
void ClearBuffer(uint8_t *Buffer, uint8_t len);
void Good_USART_Confirmation(void);
void Bad_USART_Confirmation(void);

int main(void)
{
	//HAL_Init();
	SystemClock_Config();
	TurretMotors_Config();
	TurretFire_Config();
	USART2_Config();

	usartTest();

	if(MPU9250_Config(I2C1, DMA1, DMA1_Channel6, MPU9250_Address, MPU9250_SMPLRT_DIV) == FAIL){

	}
/*
	while(1){
		//MPU9250 sample speed 100Hz, so this burst read will happen 100 times a second. 156 bits x 100 times a second = 15600 bits a second @400kHz means 156ms, each burst read being 156 bits and 1.56ms. From real-sensing to ReadBuffer ~1.56ms+2.9ms(delay) = ~4.46ms for gyroscope, ~1.59+1.9 = 3.49ms for temp
		//All-in-one read feature, bytes 0-5 Accelerometer, 6-7 Temperature, 8-13 Gyroscope.
		if((I2C_BurstRead(I2C1, DMA1, DMA1_Channel7, MPU9250_Address, MPU9250_EXT_SENS_DATA_00,15)) == FAIL){
			//TXUART the fail to laptop
		}
	}
*/

}

void usartTest(void){
	ReadBuffer[0] = 65;
	ReadBuffer[1] = 0x42;
	ReadBuffer[2] = 67;
	ReadBuffer[3] = 0x44;
	ReadBuffer[4] = 69;
	ReadBuffer[5] = 0x46;
	ReadBuffer[6] = 71;


	for(volatile uint8_t i = 0; i < 7; i++){
			if((USART2->ISR &= USART_ISR_TXE)!=0){
				USART2->TDR = ReadBuffer[i];
				wait();
			}
		}
	ClearBuffer(ReadBuffer,7);
	Good_USART_Confirmation();
	Bad_USART_Confirmation();
}

Result MPU9250_Config(I2C_TypeDef *I2CX, DMA_TypeDef *DMAX, DMA_Channel_TypeDef *DMA_ChannelX, uint8_t SlaveAddress, uint8_t RegisterAddress){

	WriteBuffer[0] = RegisterAddress; //DMA requires a memory pointer, length, and a buffer //Also, the buffer only needs the register in peripheral address and the value (2 bytes), the I2C peripheral automatically sends device address from I2C1->CR2
	WriteBuffer[1] = 0x01; //wake up MPU9250
	if((I2C_Write(I2C1, DMA1, DMA1_Channel6, MPU9250_Address, 2)) == COMPLETE){ //wake up MPU_9250 //at 100kHz, its 10 us per clock tick so its 9 bits (1 byte and 1 ack bit) so (9 clock tick x 3 bytes) = 270 microseconds + Start (10 us) + Stop (10 us) = 290 us

		Good_USART_Confirmation();

		WriteBuffer[1] = 0x09; // 100Hz sample rate, SAMPLE_RATE= Internal_Sample_Rate / (1 + SMPLRT_DIV)
		WriteBuffer[2] = 0x01; //increments to CONFIG //set up gyroscope and temp rates in MPU9250 184z bandwidth, 2.9ms delay, 1kHz Fs (internal sampling frequency). For temp sensor 188Hz bandwidth and 1.9ms delay
		WriteBuffer[3]= 0x08; //GYRO_CONFIG, set Fchoice_b[1:0] to = 00, then Fchoice is inverted to 11, GYRO_FS_SEL[1:0] set to 500 dps (degrees per second)
		WriteBuffer[4] = 0x08; //ACCEL_CONFIG, +- 4g(01)
		WriteBuffer[5] = 0x05; //ACCEL_CONFIG2 , 0x01 on ACCEL_FCHOICEb and 0x01 on A_DLPF_CFG, 218.1 3dB BW Hz, 1kHz, DLPF, 1.88ms, 300 ug/rtHz noise density?
		//Beware that you might need to write the XG,YG,ZG offsets to correct the zero-rate error/or bias

		if((I2C_Write(I2C1, DMA1, DMA1_Channel6, MPU9250_Address, 6)) == COMPLETE){
			Good_USART_Confirmation();
			ClearBuffer(WriteBuffer,6); //hygiene
			return COMPLETE;
		}
	}
	Bad_USART_Confirmation();
	ClearBuffer(WriteBuffer,6); //hygiene
	return FAIL;
}

Result I2C_BurstRead(I2C_TypeDef *I2CX, DMA_TypeDef *DMAX, DMA_Channel_TypeDef *DMA_ChannelX, uint8_t SlaveAddress, uint8_t RegisterAddress, uint8_t len){

	// if the MPU9250 samples at 100Hz, so every 10ms, 156bits go out, which should take 1.56ms each to finish, so the bus is free 8.44 ms every 10ms from 100Hz clock.

	WriteBuffer[0] = RegisterAddress;
	if(I2C_Write(I2C1, DMA1, DMA1_Channel6, SlaveAddress, 1)){
		ClearBuffer(WriteBuffer, 1);

		ReadBuffer[0] = RegisterAddress;
		if(I2C_Read(I2C1, DMA1, DMA1_Channel7, SlaveAddress, len)){
			for(volatile uint8_t i = 1; i < len; i++){
				USART2->TDR = ReadBuffer[i];
			}
			ClearBuffer(ReadBuffer, len);
			return COMPLETE;
		}

	}
	return FAIL;
}

Result I2C_Read(I2C_TypeDef *I2CX, DMA_TypeDef *DMAX, DMA_Channel_TypeDef *DMA_ChannelX, uint8_t SlaveAddress, uint8_t len){

	I2CX->ICR = I2C_ICR_CLEAR; //clear out potential flags in I2C from the last TX
	DMAX->IFCR = DMA_IFCR_CLEAR; //clear out potential flags in DMA from the last TX

	DMA_ChannelX->CNDTR = len;
	DMA_ChannelX->CCR |= DMA_CCR_EN;
	I2CX->CR1 |= I2C_CR1_RXDMAEN;

	I2CX->CR2 =
			(0U << I2C_CR2_ADD10_Pos | // So SADD can operate in 7 bit addressing mode
			(uint32_t) SlaveAddress << 1U |
			1U << I2C_CR2_RD_WRN_Pos |
			len << I2C_CR2_NBYTES_Pos |
			0x1UL << I2C_CR2_AUTOEND_Pos | //Autoend 1, After the NBYTES transfer is finished, the hardware automatically issues a STOP condition on the bus with I2C_ISR
			I2C_CR2_START);

	while((I2CX->ISR & (I2C_ISR_NACKF | I2C_ISR_STOPF)) == 0){
		//trade off between speed and reliability, dont count and risk something getting stuck and neither flags going off, or use CPU time to count
		//decided to prioritize speed in for reads, if it gets stuck then flush i2c
		//for(volatile int i = 0; i<(((8*len)+len+40)*200)/2; i++){} //(14 bytes*8)+14 = 126 clock cycles + 40 clock ticks for random stuff = 166 x 200 = 33200 ticks on 80MHz bus, then /2 (cuz 2 instructions for 1 increment) = 16600
	}

	DMA_ChannelX->CCR &= ~DMA_CCR_EN; //hygiene
	I2CX->CR1 &= ~I2C_CR1_RXDMAEN;
	I2CX->ICR = I2C_ICR_CLEAR;
	DMAX->IFCR = DMA_IFCR_CLEAR;

	if((I2CX->ISR & I2C_ICR_NACKCF) != 0){
		return FAIL;
	}
	return COMPLETE;
}

Result I2C_Write(I2C_TypeDef *I2CX, DMA_TypeDef *DMAX, DMA_Channel_TypeDef *DMA_ChannelX, uint8_t SlaveAddress, uint8_t len){

	I2C1->ICR = I2C_ICR_CLEAR; //clear out potential flags in I2C from the last TX
	DMA1->IFCR = DMA_IFCR_CLEAR; //clear out potential flags in DMA from the last TX

	DMA1_Channel6->CNDTR = len; //number of data registers
	DMA1_Channel6->CCR |= DMA_CCR_EN; //enable the DMA channel
	I2C1->CR1 |= I2C_CR1_TXDMAEN; //enable DMA in TX

	I2C1->CR2 =
			0U << I2C_CR2_ADD10_Pos | // So SADD can operate in 7 bit addressing mode
			(uint32_t) SlaveAddress << 1U |	//SADD[7:1]
			0UL << I2C_CR2_RD_WRN_Pos | //Write
			len << I2C_CR2_NBYTES_Pos | //the device address automatically done by hardware so not needed, use len
			0x0UL << I2C_CR2_AUTOEND_Pos | //Autoend 0, need to stop the transfer by hand
			0x0UL << I2C_CR2_RELOAD_Pos | //reload 0, so must be controlled by hand
			I2C_CR2_START;//Generate start condition for I2C communication. //remember, it will just fire whatever was in the buffer memory array

	while((I2C1->ISR & (I2C_ISR_NACKF | I2C_ISR_STOPF | I2C_ISR_TC)) == 0){ //when all NBYTES are sent and ACKed, then hardware generates STOPF flag by interrupt. but also, a STOPF can be from anything including errors
		for(volatile uint8_t i=0; i< (len+1)*9;i++){
		}
		break;
	}

	I2C1->CR1 &= ~I2C_CR1_TXDMAEN; //all this is hygiene
	DMA1_Channel6->CCR &= ~DMA_CCR_EN;
	I2C1->ICR = I2C_ICR_CLEAR;
	DMA1->IFCR = DMA_IFCR_CLEAR;

	if((I2C1->ISR & I2C_ISR_NACKF) != 0){ //only the NACKF tells us forsure if there was a problem, STOPF only tells you if something is stopped
		return FAIL;
	}
	return COMPLETE;
}

void ClearBuffer(uint8_t *Buffer, uint8_t len){
	if(len <= 32){
		for(uint8_t i=0; i<len; i++){
			Buffer[i] = 0;
		}
	}
}

void wait(void){
	for(volatile uint16_t i=0; i < 512; i++){}
}

void Good_USART_Confirmation(void){
	USART2->TDR = 88;
	wait();
	USART2->TDR = 68;
	wait();
}

void Bad_USART_Confirmation(void){
	USART2->TDR = 88;
	wait();
	USART2->TDR = 67;
	wait();
}

void ClearStuckI2CBus(uint8_t *I2CX){
	//stop peripheral
	//Puill both SCL and SDA down for 9 clock cycles and restart peripheral
	//I2CX->CR1 &= ~I2C_CR1_PE;
}

void USART2_IRQHandler(void){ //this is a hardware interrupt, so will trigger by hardware even if function not in main.
	if((USART2->ISR & USART_ISR_RXNE) != 0){ //register will be 1 if there is data in RDR register. Will be 0 if there is nothing.
		UART_Command = USART2->RDR; // Reading RDR automatically clears the RXNE flag. Volatile because variable stores interrupt data.

		if(UART_Command == 119){ //ASCII 'w' is 119
			TurretUp();
		}
		else if(UART_Command == 115){ //ASCII 's' is 115
			TurretDown();
		}
		else if(UART_Command == 97){ //ASCII 'a' is 97
			TurretLeft();
		}
		else if(UART_Command == 100){ //ASCII 'd' is 100
			TurretRight();
		}
		else if(UART_Command == 32){ //ASCII ' ' is 32
			TurretFire();
		}
		else if(UART_Command == 121){ //ASCII 'y' is 121
			TurretUpDownDoNothing();
		}
		else if(UART_Command == 120){ //ASCII 'x' is 120
			TurretLeftRightDoNothing();
		}
		else if(UART_Command == 122){ //ASCII 'z' is 120
			TurretFireDoNothing();
		}
		USART2->RQR = USART_RQR_RXFRQ;
		USART2->RQR &= ~USART_RQR_RXFRQ;
		USART2->TDR = UART_Command;
	}
	USART2->ICR = USART2_CLEAR; //hygiene
	USART2->CR1 &= ~(USART_CR1_TXEIE | USART_CR1_IDLEIE | USART_CR1_TCIE);
}


void TurretUp(void){
	GPIOA->BSRR = GPIO_BSRR_BR6; //direction pin 6
	TIM3->CR1 |= TIM_CR1_CEN; //pwm TIM3 enable
}
void TurretDown(void){
	GPIOA->BSRR = GPIO_BSRR_BS6;
	TIM3->CR1 |= TIM_CR1_CEN;
}
void TurretLeft(void){
	GPIOA->BSRR = GPIO_BSRR_BR9; //direction pin 9. Value is 1, so we are resetting to 0, so i guess not outputting pulse is left
	TIM1->CR1 |= TIM_CR1_CEN; //pwm TIM1 enables
}
void TurretRight(void){
	GPIOA->BSRR = GPIO_BSRR_BS9; //we're setting 1, which means right
	TIM1->CR1 |= TIM_CR1_CEN;
}
void TurretUpDownDoNothing(void){
	TIM3->CR1 &= ~TIM_CR1_CEN;
}
void TurretLeftRightDoNothing(void){
	TIM1->CR1 &= ~TIM_CR1_CEN;
}
void TurretFire(void){
	GPIOA->BSRR = GPIO_BSRR_BS5;
}
void TurretFireDoNothing(void){
	GPIOA->BSRR = GPIO_BSRR_BR5;
}

void TurretMotors_Config(void){
	RCC->AHB2ENR &= ~RCC_AHB2ENR_GPIOAEN;
	RCC->AHB2ENR |= RCC_AHB2ENR_GPIOAEN; //activate clock for port A
	tmpreg = RCC->AHB2ENR;
	UNUSED(tmpreg); //standard practice to delay after starting timer to give it time to start

	RCC->APB2ENR &= ~RCC_APB2ENR_TIM1EN;
	RCC->APB2ENR |= RCC_APB2ENR_TIM1EN; //enable Tim1
	tmpreg = RCC->APB2ENR;
	UNUSED(tmpreg); //standard practice to delay after starting timer to give it time to start

	// Whether CFGR stays or not doesnt affect the register but I could swear the motor is smoother if this remains.
	RCC->CFGR &= ~RCC_CFGR_PPRE2;
	RCC->CFGR |= (0 << RCC_CFGR_PPRE2_Pos); //APB high-speed prescaler (APB2) make sure PCLK2 is not divided, so HCLK not divided 0x00, default already 0 for this bit position

	//Base motor direction (push/pull) GPIO Pin 9, STM32 pin D8
	GPIOA->MODER &= ~GPIO_MODER_MODE9_Msk; //remember each pin is 2 bits wide, so when BIC must use 0x03
	GPIOA->MODER |= GPIO_MODER_MODE9_0; //set PA9 to output (01)

	//GPIOA->OTYPER &= ~GPIO_OTYPER_OT9; //Output push-pull (reset state) (default value)
	//GPIOA->PUPDR &= ~GPIO_PUPDR_PUPD9_Msk; // (reset state) set to 0x00, neither pull up nor pull down

	//Base motor direction GPIO Pin 6
	GPIOA->MODER &= ~GPIO_MODER_MODE6_Msk;
	GPIOA->MODER |= GPIO_MODER_MODE6_0; //set to output, 01


	//Base motor left/right (PWM) GPIO Pin 8, TIM1_CH1, STM32 pin D7
	GPIOA->MODER &= ~GPIO_MODER_MODE8_Msk;
	GPIOA->MODER |= GPIO_MODER_MODE8_1; //set PA8 to alternative function

	GPIOA->AFR[1] &= ~GPIO_AFRH_AFSEL8_Msk;
	GPIOA->AFR[1] |= GPIO_AFRH_AFSEL8_0; //set PA8 to AF1 (alternate function 1), which is TIM1_CH1. Also AF[0] are pins 0:7 and AF[1] are pins 8:15

	TIM1->CCMR1 &= ~TIM_CCMR1_OC1M_Msk;
	TIM1->CCMR1 |= (6<<TIM_CCMR1_OC1M_Pos); //CCMR1 has configurations for both Ch1 and Ch2  // Set PWM mode 1 on CH1 (mode 1 is in upcounting, CH1 is active as long as TIM CNT < TIM CCR1. Configures 0110 for Ch1
	//TIM1->CCMR1 |= TIM_CCMR1_OC1PE;            // Enable preload register. (. TIMx_CCR1 preload value is loaded in the active register at each update event)

	//TIM1->PSC = 0; //so we keep clock at 4mhz (default for APB1) and not divide it by anything. (x) x (0+1)
	//left right motor
	TIM1->ARR = 65535; //Max value is 16 bit width 65535. This is not Hz, its the auto-reloader's counter. So higher this is, the longer it takes to do 1 PWM cycle peak to peak.
	TIM1->CCR1 = 8192; //keep in mind CCR1 is channel 1, so CCR2 would be channel 2
	TIM1->CCER |= TIM_CCER_CC1E;  // Enable CH1 output (Capture mode enable)
	TIM1->BDTR |= TIM_BDTR_MOE;   // Main output enable (For advanced timers like TIM1/TIM8)

	//Base motor up/down (PWM) GPIO Pin 7, TIM3_CH2
	GPIOA->MODER &= ~GPIO_MODER_MODE7_Msk;
	GPIOA->MODER |= GPIO_MODER_MODE7_1; //Alternate function for pin 12

	GPIOA->AFR[0] &= ~GPIO_AFRL_AFSEL7_Msk;
	GPIOA->AFR[0] |= GPIO_AFRL_AFSEL7_1; //Pin 7, AF[0] is 0010 for TIM3_CH2. Also AF[0] are pins 0:7 and AF[1] are pins 8:15

	RCC->APB1ENR1 &= ~RCC_APB1ENR1_TIM3EN_Msk;
	RCC->APB1ENR1 |= RCC_APB1ENR1_TIM3EN; //enable Tim3
	tmpreg = RCC->APB1ENR1;
	UNUSED(tmpreg); //standard practice to delay after starting timer to give it time to start

	//up down motor
	TIM3->CCMR1 |= (6<<TIM_CCMR1_OC2M_Pos); //CCMR1 has configurations for both Ch1 and Ch2, this configures 0110 for Ch2, mode 1 which is upcounting TIM CNT < TIM CCR1
	TIM3->ARR = 65535; //Auto reload value (marks the rising edge in PWM) Max value is 16 bit width, 65535
	TIM3->CCR2 = 100; //Set duty rate for Ch2
	TIM3->CCER |= TIM_CCER_CC2E; //enable ch2 output
	//TIM3 is a general timer, not advanced like TIM1 or TIM 8 so no need for BDTR and MOE
}

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

void NVIC_SetIRQ(IRQn_Type IRQ){ //doesnt work with negative IRQs (which are error interrupts) so don't use negative ones.
	NVIC->ISER[IRQ>>5UL] = 1<<(IRQ % 32); //ISER[1] = 1<6UL, interrupts are chosen by the bit index, not by the actual bit values, so thats why 1<<6 instead of 110b
}

void TurretFire_Config(void){
	GPIOA->MODER &= ~GPIO_MODER_MODE5_Msk; //output mode 01. if the reset state is 11, you cannot just do |= 01, you must bic 11 first.
	GPIOA->MODER |= GPIO_MODER_MODE5_0; //output mode 01
}

void I2C1_Config(void){
	RCC->AHB2ENR |= RCC_AHB2ENR_GPIOBEN; //All of the I2C1 pins are PB instead of PA, so we need to open PortB now. Also, do enable the port first before starting I2C
	RCC->APB1ENR1 |= RCC_APB1ENR1_I2C1EN; //Enable I2C1 clock in APB1
	tmpreg = RCC->APB1ENR1; //remember standard practice to give the clock some time to start
	UNUSED(tmpreg);

	GPIOB->MODER &= ~(GPIO_MODER_MODE8_1 | GPIO_MODER_MODE9_1); //PB8 needs to be SCL so alternative function 10 //PB9 needs to be SDA so alternative function 10
	GPIOB->MODER |= GPIO_MODER_MODE8_1 | GPIO_MODER_MODE9_1; //PB8/PB9 needs to be SCL so alternative function 10

	GPIOB->AFR[1] &= ~((0xFUL << 0) | (0xFUL << 4U)); //remember [0] is for pins 0-7 and [1] is for pins 8-15
	GPIOB->AFR[1] |= (0x4UL << 0) | (0x4UL << 4U);  //when we look at the other datasheet, we find PortB PB8/9 I2C1_SCL and I2C1_SDA is in AF4, so 0100												// so in the AFR[1] register we push 0100 to bits 0-3 and 4-8 in AFRH.

	GPIOB->OTYPER |= GPIO_OTYPER_OT8 | GPIO_OTYPER_OT9; //PB8/PB9 output type open-drain // Needed for I2C because open-drain allows multiple devices to share SDA/SCL safely.

	GPIOB->PUPDR &= ~((GPIO_PUPDR_PUPD8_0) | (GPIO_PUPDR_PUPD9_0)); //PB8/PB9 pull-up register. We set output type to be open-drain, which means register will always go from 1 -> 0, so we need it constantly at pull-up.
	GPIOB->PUPDR |= (GPIO_PUPDR_PUPD8_0) | (GPIO_PUPDR_PUPD9_0); //(Internal pull-ups are weak for I²C; external 2.2–4.7 kΩ pull-ups on SDA/SCL are strongly recommended.)????

	GPIOB->OSPEEDR &= ~((GPIO_OSPEEDR_OSPEED8) | (GPIO_OSPEEDR_OSPEED9));
	GPIOB->OSPEEDR |= (GPIO_OSPEEDR_OSPEED8) | (GPIO_OSPEEDR_OSPEED9); //set speed to the highest (11)

	//Peripheral reset
	I2C1->CR1 &= ~I2C_CR1_PE; //turn off I2C1 control for now
	RCC->APB1RSTR1 |= RCC_APB1RSTR1_I2C1RST; //im not sure why its recommended to reset, but I guess if we REALLY want to make sure, we reset
	RCC->APB1RSTR1 &= ~RCC_APB1RSTR1_I2C1RST; //so we don't want to keep the register value as 1, or else it will constantly reset, we set it back to 0 to stop resetting.

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

	I2C1->CR1 |= (I2C_CR1_TXDMAEN) | (I2C_CR1_RXDMAEN); //Enable TX and RX to read using DMA
	I2C1->ICR = I2C_ICR_CLEAR; //clear I2C ICR masks

	NVIC_SetIRQ(I2C1_EV_IRQn); //enable interrupt events
	NVIC_SetIRQ(I2C1_ER_IRQn); //enable interrupt errors

	I2C1->CR1 |= I2C_CR1_PE; //enable the I2C peripheral
}

void DMA1_Config(void){
	RCC->AHB1ENR |= RCC_AHB1ENR_DMA1EN; //need to enable AHB1 bus for DMA1

	//DMA1_Channel6 is I2C1TX,
	DMA1->IFCR = DMA_IFCR_CLEAR; //clear out all the TX flags that could still be up
	DMA1_CSELR->CSELR |= DMA_CSELR_C6S; //map DMA channel

	DMA1_Channel6->CCR &= ~DMA_CCR_EN; //make sure DMA is off while configuring
	DMA1_Channel6->CPAR = (uint32_t)&I2C1->TXDR; //this is just the peripheral address that's loaded before it shoots out I2C data
	DMA1_Channel6->CMAR = (uint32_t)&WriteBuffer; //sets the memory address to read from the 2 byte memory buffer we declared earlier

	DMA1_Channel6->CCR |=
			0x01UL << DMA_CCR_DIR_Pos | //0x01 is read from memory
			0x01UL << DMA_CCR_MINC_Pos | //increment memory per DMA write
			DMA_CCR_PL_1; //priority 0x2

	//also keep in mind that I2C TXDR and RXDR are 8 bits by default so you don't need to set peripheral/memory byte size

	NVIC_SetIRQ(DMA1_Channel6_IRQn);


	//DMA1_Channel7 is I2C1RX
	DMA1->IFCR = DMA_IFCR_CLEAR;
	DMA1_CSELR->CSELR |= DMA_CSELR_C7S; //map DMA channel

	DMA1_Channel7->CCR &= ~DMA_CCR_EN;
	DMA1_Channel7->CPAR = (uint32_t)&I2C1->RXDR;
	DMA1_Channel7->CMAR = (uint32_t)&ReadBuffer;


	DMA1_Channel7->CCR |=
			//0x0UL << DMA_CCR_DIR_Pos | //0x0 is read from peripheral but that is already the default so commented out
			0x1UL << DMA_CCR_MINC_Pos | //increment memory per DMA read
			DMA_CCR_PL_1; //priority 0x2

	NVIC_SetIRQ(DMA1_Channel7_IRQn); //enable data received interrupt for channel 7
}

void MPU9250EXTI_Config(void){

	//PB0
	RCC->AHB2ENR |= RCC_APB2ENR_SYSCFGEN; //SYSCFG clock enable
	GPIOB->MODER |= 0x0UL << GPIO_MODER_MODE0_Pos; //Input mode
	GPIOB->PUPDR |= 0x0UL << GPIO_PUPDR_PUPD0_Pos; //Neither pull up nor pull down

	SYSCFG->EXTICR[1] |= 0x1UL << SYSCFG_EXTICR1_EXTI0_Pos; //syscfg manages the external interrupt line, 0001 on EXTICR[1] enables PB0
	EXTI->IMR1 |= 0x01UL << EXTI_EMR1_EM0_Pos; //interrrupt unmasked for IM0, so it can flow
	EXTI->RTSR1 |= 0x01UL << EXTI_RTSR1_RT0_Pos; //Rising trigger enabled (for Event and Interrupt) for input line
	EXTI->FTSR1 |= 0x00UL << EXTI_FTSR1_FT0_Pos; //disable falling edge

	NVIC_SetIRQ(EXTI0_IRQn); //enable interrupt for EXTI0
}

void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  if (HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1) != HAL_OK)
  {
    Error_Handler();
  }

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_MSI;
  RCC_OscInitStruct.MSIState = RCC_MSI_ON;
  RCC_OscInitStruct.MSICalibrationValue = 0;
  RCC_OscInitStruct.MSIClockRange = RCC_MSIRANGE_6;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_NONE;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_MSI;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_0) != HAL_OK)
  {
    Error_Handler();
  }
}

void Error_Handler(void)
{
  __disable_irq();
  while (1)
  {
  }
}

#ifdef  USE_FULL_ASSERT

void assert_failed(uint8_t *file, uint32_t line)
{
}
#endif
