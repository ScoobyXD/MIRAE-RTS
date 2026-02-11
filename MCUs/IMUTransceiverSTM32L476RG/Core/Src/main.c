//Pins
//D7-PA_8-Heartbeat LED
//D15-PB_8-SCL1
//D14-PB_9-SDA1
//D13-PA_5-SPI1_SCK
//D12-PA_6-SPI1_MISO
//D11-PA_7-SPI1_MOSI
//D10-PB_6-SPI1_CS (MCP2515)

#include <stdio.h>
#include <stdarg.h>
#include <stdint.h>
#include "stm32l476xx.h"
#include "FreeRTOS.h"
#include "task.h"
#include "main.h"
#include "Drivers/I2C.h"
#include "Drivers/lsm6ds3.h"
#include "Drivers/USART.h"
#include "Drivers/SPI.h"
#include "Drivers/MCP2515.h"


void SystemClock_Config(void);
void SysTick_Init(uint32_t sys_clk_hz);
void GPIOPortConfig(void);
static void prvCreateTasks(void);
void vHeartbeat(void *pvParameters);
void vIMURead(void *pvParameters);
void vCANSend(void *pvParameters);
void vCANReceive(void *pvParameters);

//Helper to print hex byte via UART
static void print_hex8(uint8_t val);
static void print_hex16(uint16_t val);

volatile uint32_t ms_ticks = 0;
static volatile uint8_t can_ready = 0; //Set to 1 after MCP2515 init succeeds

//Shared IMU data between vIMURead and vCANSend
static volatile float shared_gx, shared_gy, shared_gz;
static volatile float shared_ax, shared_ay, shared_az;

//Heartbeat sequence counter
static volatile uint32_t heartbeat_seq = 0;

int main(void){
    HAL_Init();
    SystemClock_Config();
    SysTick_Init(80000000);
    GPIOPortConfig();
    I2C1_Config();
    USART2_Config(); //I2C1_Config does the RCC->HSI 16MHz clock config, so I2C has to be initialized before USART

    USART2_PrintString("\r\n");
    USART2_PrintString("========================================\r\n");
    USART2_PrintString("  Rover STM32 -- Motor Control Unit\r\n");
    USART2_PrintString("  STM32L476RG @ 80MHz, FreeRTOS\r\n");
    USART2_PrintString("========================================\r\n");
    USART2_PrintString("[INIT] GPIO OK\r\n");
    USART2_PrintString("[INIT] I2C1 OK\r\n");
    USART2_PrintString("[INIT] USART2 OK (9600 baud)\r\n");

    //Initialize LSM6DS3 IMU
    LSM6DS3_Init();

    //Initialize SPI1 for MCP2515
    SPI1_Config();
    USART2_PrintString("[INIT] SPI1 OK (5MHz, mode 0)\r\n");

    //Initialize MCP2515 CAN controller
    if(MCP2515_Init()){
        can_ready = 1;
    } else {
        USART2_PrintString("[INIT] WARNING: CAN bus not available, continuing without CAN\r\n");
    }

    USART2_PrintString("[INIT] All init complete, starting FreeRTOS scheduler\r\n");
    USART2_PrintString("========================================\r\n\r\n");

    prvCreateTasks();
    vTaskStartScheduler();

    for(;;);
}

static void prvCreateTasks(void){
    static uint32_t rate = 500;
    xTaskCreate(vHeartbeat,   "Heartbeat",  128,  (void*)&rate, 1, NULL);
    xTaskCreate(vIMURead,     "IMURead",    1024, NULL,          2, NULL);
    xTaskCreate(vCANSend,     "CANSend",    512,  NULL,          2, NULL);
    xTaskCreate(vCANReceive,  "CANRecv",    512,  NULL,          3, NULL); //Higher priority for commands
}

// ============================================================================
// Task: Heartbeat LED (PA8)
// ============================================================================

void vHeartbeat(void *pvParameters){
    uint32_t *rate = (uint32_t*)pvParameters;

    for(;;){
        GPIOA->ODR |= GPIO_ODR_OD8;
        vTaskDelay(pdMS_TO_TICKS(*rate));
        GPIOA->ODR &= ~GPIO_ODR_OD8;
        vTaskDelay(pdMS_TO_TICKS(*rate));

        heartbeat_seq++;

        //Print heartbeat to UART every 10 blinks (every 10s at 500ms rate)
        if(heartbeat_seq % 10 == 0){
            usart2_printf("[HB] seq=%u uptime=%ums can=%s\r\n",
                heartbeat_seq, ms_ticks,
                can_ready ? "OK" : "OFF");
        }
    }
}

// ============================================================================
// Task: IMU Read (LSM6DS3 via I2C)
// ============================================================================

void vIMURead(void *pvParameters){
    LSM6DS3_SISample imu;
    uint32_t imu_count = 0;

    for(;;){
        LSM6DS3_GyroAccelRead(&imu);

        //Store in shared volatile vars for CAN task
        shared_gx = imu.gx;
        shared_gy = imu.gy;
        shared_gz = imu.gz;
        shared_ax = imu.ax;
        shared_ay = imu.ay;
        shared_az = imu.az;

        imu_count++;

        //Print IMU to UART every 50 reads (every 5s at 100ms rate)
        if(imu_count % 50 == 0){
            usart2_printf("[IMU] gx:%f gy:%f gz:%f ax:%f ay:%f az:%f\r\n",
                imu.gx, imu.gy, imu.gz, imu.ax, imu.ay, imu.az);
        }

        vTaskDelay(pdMS_TO_TICKS(100)); //100ms = 10Hz IMU read rate
    }
}

// ============================================================================
// Task: CAN Send (heartbeat + IMU data to Pi)
// ============================================================================

void vCANSend(void *pvParameters){
    CAN_Message msg;
    uint32_t can_send_count = 0;
    uint32_t can_err_count = 0;

    //Wait for CAN to be ready
    while(!can_ready){
        vTaskDelay(pdMS_TO_TICKS(500));
    }
    USART2_PrintString("[CAN-TX] CAN send task running\r\n");

    for(;;){
        can_send_count++;

        // --- Send Heartbeat (every iteration, ~200ms = 5Hz) ---
        msg.id = CAN_ID_HEARTBEAT;
        msg.dlc = 8;
        //Pack: uptime (4 bytes LE) + sequence (2 bytes) + can_ready + error flags
        uint32_t uptime = ms_ticks;
        msg.data[0] = (uint8_t)(uptime & 0xFF);
        msg.data[1] = (uint8_t)((uptime >> 8) & 0xFF);
        msg.data[2] = (uint8_t)((uptime >> 16) & 0xFF);
        msg.data[3] = (uint8_t)((uptime >> 24) & 0xFF);
        msg.data[4] = (uint8_t)(heartbeat_seq & 0xFF);
        msg.data[5] = (uint8_t)((heartbeat_seq >> 8) & 0xFF);
        msg.data[6] = can_ready;
        msg.data[7] = MCP2515_GetErrorFlags();

        if(!MCP2515_SendMessage(&msg)){
            can_err_count++;
            if(can_err_count % 20 == 1){
                usart2_printf("[CAN-TX] ERR: heartbeat send failed (total errs: %u)\r\n", can_err_count);
            }
        }

        vTaskDelay(pdMS_TO_TICKS(50)); //Small gap between frames

        // --- Send IMU data (accel + gyro packed as int16 * 1000) ---
        int16_t ax_i = (int16_t)(shared_ax * 1000.0f);
        int16_t ay_i = (int16_t)(shared_ay * 1000.0f);
        int16_t az_i = (int16_t)(shared_az * 1000.0f);
        int16_t gx_i = (int16_t)(shared_gx * 1000.0f);
        int16_t gy_i = (int16_t)(shared_gy * 1000.0f);
        int16_t gz_i = (int16_t)(shared_gz * 1000.0f);

        //Frame 1: ax, ay, az (6 bytes)
        msg.id = CAN_ID_IMU_AG;
        msg.dlc = 6;
        msg.data[0] = (uint8_t)(ax_i & 0xFF);
        msg.data[1] = (uint8_t)((ax_i >> 8) & 0xFF);
        msg.data[2] = (uint8_t)(ay_i & 0xFF);
        msg.data[3] = (uint8_t)((ay_i >> 8) & 0xFF);
        msg.data[4] = (uint8_t)(az_i & 0xFF);
        msg.data[5] = (uint8_t)((az_i >> 8) & 0xFF);
        MCP2515_SendMessage(&msg);

        vTaskDelay(pdMS_TO_TICKS(10));

        //Frame 2: gx, gy, gz (6 bytes)
        msg.id = CAN_ID_IMU_AG2;
        msg.dlc = 6;
        msg.data[0] = (uint8_t)(gx_i & 0xFF);
        msg.data[1] = (uint8_t)((gx_i >> 8) & 0xFF);
        msg.data[2] = (uint8_t)(gy_i & 0xFF);
        msg.data[3] = (uint8_t)((gy_i >> 8) & 0xFF);
        msg.data[4] = (uint8_t)(gz_i & 0xFF);
        msg.data[5] = (uint8_t)((gz_i >> 8) & 0xFF);
        MCP2515_SendMessage(&msg);

        //Log CAN TX stats periodically (every 50 sends = ~10s)
        if(can_send_count % 50 == 0){
            uint8_t eflg = MCP2515_GetErrorFlags();
            usart2_printf("[CAN-TX] sent=%u errs=%u eflg=0x", can_send_count, can_err_count);
            print_hex8(eflg);
            USART2_PrintString("\r\n");
        }

        vTaskDelay(pdMS_TO_TICKS(140)); //Total loop ~200ms = 5Hz send rate
    }
}

// ============================================================================
// Task: CAN Receive (commands from Pi)
// ============================================================================

void vCANReceive(void *pvParameters){
    CAN_Message msg;
    uint32_t rx_count = 0;

    while(!can_ready){
        vTaskDelay(pdMS_TO_TICKS(500));
    }
    USART2_PrintString("[CAN-RX] CAN receive task running\r\n");

    for(;;){
        if(MCP2515_ReadMessage(&msg)){
            rx_count++;

            //Print received message
            usart2_printf("[CAN-RX] id=0x");
            print_hex16(msg.id);
            usart2_printf(" dlc=%d data=", msg.dlc);
            for(uint8_t i = 0; i < msg.dlc; i++){
                print_hex8(msg.data[i]);
                if(i < msg.dlc - 1) USART2_PrintString(",");
            }
            USART2_PrintString("\r\n");

            //Decode known command IDs
            if(msg.id == CAN_ID_NAV_CMD && msg.dlc >= 4){
                //Heading (int16 * 10) and speed (int16 * 100)
                int16_t heading_x10 = (int16_t)(msg.data[0] | (msg.data[1] << 8));
                int16_t speed_x100 = (int16_t)(msg.data[2] | (msg.data[3] << 8));
                float heading = heading_x10 / 10.0f;
                float speed = speed_x100 / 100.0f;
                usart2_printf("[CMD] NAVIGATE heading=%f speed=%f\r\n", heading, speed);
                //TODO: Feed heading and speed to PID motor control loop
            }
            else if(msg.id == CAN_ID_STOP_CMD){
                USART2_PrintString("[CMD] STOP -- motors off\r\n");
                //TODO: Set motor PWM to 0, disable motor driver
            }
            else if(msg.id == CAN_ID_SPEED_CMD && msg.dlc >= 2){
                int16_t speed_x100 = (int16_t)(msg.data[0] | (msg.data[1] << 8));
                float speed = speed_x100 / 100.0f;
                usart2_printf("[CMD] SET_SPEED max=%f m/s\r\n", speed);
                //TODO: Update max speed parameter
            }
            else if(msg.id == CAN_ID_PING){
                USART2_PrintString("[CMD] PING received, sending heartbeat\r\n");
                CAN_Message hb;
                hb.id = CAN_ID_HEARTBEAT;
                hb.dlc = 8;
                uint32_t up = ms_ticks;
                hb.data[0] = (uint8_t)(up & 0xFF);
                hb.data[1] = (uint8_t)((up >> 8) & 0xFF);
                hb.data[2] = (uint8_t)((up >> 16) & 0xFF);
                hb.data[3] = (uint8_t)((up >> 24) & 0xFF);
                hb.data[4] = (uint8_t)(heartbeat_seq & 0xFF);
                hb.data[5] = (uint8_t)((heartbeat_seq >> 8) & 0xFF);
                hb.data[6] = can_ready;
                hb.data[7] = MCP2515_GetErrorFlags();
                MCP2515_SendMessage(&hb);
            }
        }

        //Check for CAN errors periodically
        if(rx_count > 0 && rx_count % 100 == 0){
            uint8_t eflg = MCP2515_GetErrorFlags();
            if(eflg){
                usart2_printf("[CAN-RX] EFLG=0x");
                print_hex8(eflg);
                USART2_PrintString(" (");
                if(eflg & 0x01) USART2_PrintString("EWARN ");
                if(eflg & 0x02) USART2_PrintString("RXWAR ");
                if(eflg & 0x04) USART2_PrintString("TXWAR ");
                if(eflg & 0x08) USART2_PrintString("RXEP ");
                if(eflg & 0x10) USART2_PrintString("TXEP ");
                if(eflg & 0x20) USART2_PrintString("TXBO ");
                if(eflg & 0x40) USART2_PrintString("RX0OVR ");
                if(eflg & 0x80) USART2_PrintString("RX1OVR ");
                USART2_PrintString(")\r\n");
            }
        }

        vTaskDelay(pdMS_TO_TICKS(10)); //Poll CAN at 100Hz
    }
}

// ============================================================================
// Hex print helpers
// ============================================================================

static void print_hex8(uint8_t val){
    char hex[3];
    uint8_t hi = (val >> 4) & 0x0F;
    uint8_t lo = val & 0x0F;
    hex[0] = hi < 10 ? '0' + hi : 'A' + (hi - 10);
    hex[1] = lo < 10 ? '0' + lo : 'A' + (lo - 10);
    hex[2] = '\0';
    USART2_PrintString(hex);
}

static void print_hex16(uint16_t val){
    print_hex8((uint8_t)(val >> 8));
    print_hex8((uint8_t)(val & 0xFF));
}

// ============================================================================
// GPIO Config (heartbeat LED on PA8)
// ============================================================================

void GPIOPortConfig(void){
    volatile uint32_t tmpreg;

    RCC->AHB2ENR |= RCC_AHB2ENR_GPIOAEN;
    tmpreg = RCC->AHB2ENR;
    UNUSED(tmpreg);
    GPIOA->MODER &= ~GPIO_MODER_MODE8_Msk;
    GPIOA->MODER |= GPIO_MODER_MODE8_0; //General output
}

// ---- UART primitives ----
void usart2_send_char(char c) {
    while (!(USART2->ISR & (1 << 7)));
    USART2->TDR = c;
}

void usart2_send_string(const char *s) {
    while (*s) usart2_send_char(*s++);
}

// ---- conversions ----
void uint_to_str(uint32_t val, char *buf) {
    char tmp[12];
    int i = 0;
    if (val == 0) {
        tmp[i++] = '0';
    } else {
        while (val > 0) {
            tmp[i++] = '0' + (val % 10);
            val /= 10;
        }
    }
    for (int j = 0; j < i; j++)
        buf[j] = tmp[i - 1 - j];
    buf[i] = '\0';
}

void float_to_str(float val, char *buf, int decimal_places) {
    int i = 0;
    if (val < 0) {
        buf[i++] = '-';
        val = -val;
    }
    unsigned int int_part = (unsigned int)val;
    float frac = val - (float)int_part;

    char tmp[16];
    int j = 0;
    if (int_part == 0) {
        tmp[j++] = '0';
    } else {
        while (int_part > 0) {
            tmp[j++] = '0' + (int_part % 10);
            int_part /= 10;
        }
    }
    for (int k = j - 1; k >= 0; k--)
        buf[i++] = tmp[k];

    buf[i++] = '.';
    for (int d = 0; d < decimal_places; d++) {
        frac *= 10.0f;
        int digit = (int)frac;
        buf[i++] = '0' + digit;
        frac -= (float)digit;
    }
    buf[i] = '\0';
}

// ---- printf ----
void usart2_printf(const char *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    char buf[32];

    while (*fmt) {
        if (*fmt == '%') {
            fmt++;
            switch (*fmt) {
                case 'd': {
                    int val = va_arg(args, int);
                    if (val < 0) { usart2_send_char('-'); val = -val; }
                    uint_to_str((uint32_t)val, buf);
                    usart2_send_string(buf);
                    break;
                }
                case 'u': {
                    uint32_t val = va_arg(args, uint32_t);
                    uint_to_str(val, buf);
                    usart2_send_string(buf);
                    break;
                }
                case 'f': {
                    double val = va_arg(args, double);
                    float_to_str((float)val, buf, 4);
                    usart2_send_string(buf);
                    break;
                }
                case 's': {
                    char *s = va_arg(args, char *);
                    usart2_send_string(s);
                    break;
                }
                case '%': {
                    usart2_send_char('%');
                    break;
                }
                default:
                    usart2_send_char('%');
                    usart2_send_char(*fmt);
                    break;
            }
        } else {
            usart2_send_char(*fmt);
        }
        fmt++;
    }
    va_end(args);
}

void SysTick_Init(uint32_t sys_clk_hz) {
    SysTick->LOAD = (sys_clk_hz / 1000) - 1;
    SysTick->VAL  = 0;
    SysTick->CTRL = (1 << 2) | (1 << 1) | (1 << 0);
}

void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  if (HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1) != HAL_OK)
  {
    Error_Handler();
  }

  // Enable MSI and the PLL for 80MHz
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_MSI;
  RCC_OscInitStruct.MSIState = RCC_MSI_ON;
  RCC_OscInitStruct.MSICalibrationValue = 0;
  RCC_OscInitStruct.MSIClockRange = RCC_CR_MSIRANGE_7; // Set to 8MHz. CubeIDE defaults project to RCC_CR_MSIRANGE_6 (4MHz). Internal RC oscillator (MSI) tops out at 48MHz.
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_MSI;
  RCC_OscInitStruct.PLL.PLLM = 1; // 8MHz / 1 = 8MHz input to PLL
  RCC_OscInitStruct.PLL.PLLN = 20; // 8MHz * 20 = 160MHz VCO
  RCC_OscInitStruct.PLL.PLLR = 2; // 160MHz / 2 = 80MHz output
  RCC_OscInitStruct.PLL.PLLP = 7;
  RCC_OscInitStruct.PLL.PLLQ = 4;

  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  // Set clocks for 80MHz
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK|RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK; // Went from MSI to PLLCLK
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4) != HAL_OK) // As RCC_MSIRANGE_X goes higher, you need to increase this. 4 wait states for 80MHz because at that speed CPU much faster than flash memory can keep up with, so have it wait
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
