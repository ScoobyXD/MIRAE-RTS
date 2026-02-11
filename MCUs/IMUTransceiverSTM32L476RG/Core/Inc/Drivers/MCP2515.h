#ifndef MCP2515_H_
#define MCP2515_H_

#include <stdint.h>

// ============================================================================
// MCP2515 Register Addresses
// ============================================================================

//Configuration registers (only writable in Configuration mode)
#define MCP_CNF1        0x2A
#define MCP_CNF2        0x2B
#define MCP_CNF3        0x2C
#define MCP_CANINTE     0x2B  //Interrupt enable -- WAIT this conflicts. Let me fix.

//Actually let me use the correct MCP2515 register map:
//Control registers
#undef MCP_CNF1
#undef MCP_CNF2
#undef MCP_CNF3
#undef MCP_CANINTE

#define MCP_RXF0SIDH    0x00
#define MCP_RXF0SIDL    0x01
#define MCP_RXF0EID8    0x02
#define MCP_RXF0EID0    0x03
#define MCP_RXF1SIDH    0x04
#define MCP_RXF1SIDL    0x05
#define MCP_RXF2SIDH    0x08
#define MCP_RXF2SIDL    0x09
#define MCP_RXF3SIDH    0x10
#define MCP_RXF3SIDL    0x11
#define MCP_RXF4SIDH    0x14
#define MCP_RXF4SIDL    0x15
#define MCP_RXF5SIDH    0x18
#define MCP_RXF5SIDL    0x19

#define MCP_RXM0SIDH    0x20
#define MCP_RXM0SIDL    0x21
#define MCP_RXM0EID8    0x22
#define MCP_RXM0EID0    0x23
#define MCP_RXM1SIDH    0x24
#define MCP_RXM1SIDL    0x25
#define MCP_RXM1EID8    0x26
#define MCP_RXM1EID0    0x27

#define MCP_CNF3        0x28
#define MCP_CNF2        0x29
#define MCP_CNF1        0x2A
#define MCP_CANINTE     0x2B
#define MCP_CANINTF     0x2C
#define MCP_EFLG        0x2D

#define MCP_TXB0CTRL    0x30
#define MCP_TXB0SIDH    0x31
#define MCP_TXB0SIDL    0x32
#define MCP_TXB0EID8    0x33
#define MCP_TXB0EID0    0x34
#define MCP_TXB0DLC     0x35
#define MCP_TXB0D0      0x36

#define MCP_RXB0CTRL    0x60
#define MCP_RXB0SIDH    0x61
#define MCP_RXB0SIDL    0x62
#define MCP_RXB0EID8    0x63
#define MCP_RXB0EID0    0x64
#define MCP_RXB0DLC     0x65
#define MCP_RXB0D0      0x66

#define MCP_RXB1CTRL    0x70
#define MCP_RXB1SIDH    0x71
#define MCP_RXB1SIDL    0x72
#define MCP_RXB1DLC     0x75
#define MCP_RXB1D0      0x76

#define MCP_CANSTAT     0x0E
#define MCP_CANCTRL     0x0F

// ============================================================================
// MCP2515 SPI Commands
// ============================================================================
#define MCP_CMD_RESET       0xC0
#define MCP_CMD_READ        0x03
#define MCP_CMD_WRITE       0x02
#define MCP_CMD_RTS_TX0     0x81  //Request-to-send for TX buffer 0
#define MCP_CMD_READ_STATUS 0xA0
#define MCP_CMD_RX_STATUS   0xB0
#define MCP_CMD_BIT_MODIFY  0x05
#define MCP_CMD_READ_RX0    0x90  //Read RX buffer 0 starting at SIDH
#define MCP_CMD_READ_RX1    0x94  //Read RX buffer 1 starting at SIDH
#define MCP_CMD_LOAD_TX0    0x40  //Load TX buffer 0 starting at SIDH

// ============================================================================
// MCP2515 Mode bits (CANCTRL register, bits [7:5])
// ============================================================================
#define MCP_MODE_NORMAL     0x00
#define MCP_MODE_SLEEP      0x20
#define MCP_MODE_LOOPBACK   0x40
#define MCP_MODE_LISTEN     0x60
#define MCP_MODE_CONFIG     0x80
#define MCP_MODE_MASK       0xE0

// ============================================================================
// Interrupt flags (CANINTF register)
// ============================================================================
#define MCP_RX0IF           0x01  //RX buffer 0 full
#define MCP_RX1IF           0x02  //RX buffer 1 full
#define MCP_TX0IF           0x04  //TX buffer 0 empty
#define MCP_TX1IF           0x08
#define MCP_TX2IF           0x10
#define MCP_ERRIF           0x20  //Error interrupt
#define MCP_WAKIF           0x40  //Wake-up interrupt
#define MCP_MERRF           0x80  //Message error

// ============================================================================
// Our CAN Protocol Message IDs
// ============================================================================
#define CAN_ID_HEARTBEAT    0x100  //STM32 -> Pi: heartbeat + uptime
#define CAN_ID_IMU_AG       0x101  //STM32 -> Pi: accel+gyro (ax,ay,az,gx,gy,gz)
#define CAN_ID_IMU_AG2      0x102  //STM32 -> Pi: accel+gyro part 2
#define CAN_ID_ENCODER      0x103  //STM32 -> Pi: encoder counts + velocities
#define CAN_ID_STATUS       0x104  //STM32 -> Pi: status flags, battery, errors

#define CAN_ID_NAV_CMD      0x200  //Pi -> STM32: navigate (heading, speed)
#define CAN_ID_STOP_CMD     0x201  //Pi -> STM32: emergency stop
#define CAN_ID_SPEED_CMD    0x202  //Pi -> STM32: set max speed
#define CAN_ID_PING         0x2FF  //Pi -> STM32: ping (STM32 responds with heartbeat)

// ============================================================================
// CAN Message struct
// ============================================================================
typedef struct {
    uint16_t id;        //Standard CAN ID (11-bit, 0x000-0x7FF)
    uint8_t  dlc;       //Data length code (0-8)
    uint8_t  data[8];   //Payload
} CAN_Message;

// ============================================================================
// API
// ============================================================================
uint8_t MCP2515_Init(void);          //Returns 1 on success, 0 on failure
uint8_t MCP2515_SendMessage(CAN_Message *msg);  //Returns 1 on success
uint8_t MCP2515_ReadMessage(CAN_Message *msg);   //Returns 1 if message available
uint8_t MCP2515_CheckRxStatus(void); //Returns non-zero if message waiting
uint8_t MCP2515_GetErrorFlags(void); //Returns EFLG register

//Low-level SPI helpers (also used by Init)
void    MCP2515_Reset(void);
uint8_t MCP2515_ReadReg(uint8_t addr);
void    MCP2515_WriteReg(uint8_t addr, uint8_t val);
void    MCP2515_BitModify(uint8_t addr, uint8_t mask, uint8_t val);

#endif
