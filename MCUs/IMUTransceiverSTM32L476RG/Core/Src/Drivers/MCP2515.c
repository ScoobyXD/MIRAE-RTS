#include "stm32l476xx.h"
#include "Drivers/MCP2515.h"
#include "Drivers/SPI.h"
#include "Drivers/USART.h"

//MCP2515 CAN Controller Driver
//
//Communicates with MCP2515 over SPI1. The MCP2515 module has an 8MHz crystal
//and a TJA1050 CAN transceiver on-board. We configure it for 500kbps CAN.
//
//Bit timing for 500kbps with 8MHz oscillator:
//  TQ = 2 * (BRP+1) / Fosc = 2 * (0+1) / 8MHz = 250ns
//  Sync = 1 TQ (fixed)
//  PropSeg = 1 TQ (CNF2 PRSEG = 0)
//  PS1 = 4 TQ (CNF2 PHSEG1 = 3, value+1)
//  PS2 = 2 TQ (CNF3 PHSEG2 = 1, value+1)
//  Total = 1+1+4+2 = 8 TQ
//  Bit rate = 1 / (8 * 250ns) = 500kbps
//  Sample point = (1+1+4)/8 = 75%

// Simple delay for MCP2515 reset settling
static void delay_ms_approx(uint32_t ms){
    //At 80MHz, ~80000 iterations per ms (rough)
    volatile uint32_t count = ms * 20000;
    while(count--);
}

// ============================================================================
// Low-level SPI register access
// ============================================================================

void MCP2515_Reset(void){
    SPI1_CS_Low();
    SPI1_TransferByte(MCP_CMD_RESET);
    SPI1_CS_High();
    delay_ms_approx(10); //MCP2515 needs time after reset
}

uint8_t MCP2515_ReadReg(uint8_t addr){
    uint8_t val;
    SPI1_CS_Low();
    SPI1_TransferByte(MCP_CMD_READ);
    SPI1_TransferByte(addr);
    val = SPI1_TransferByte(0x00); //Dummy byte to clock out data
    SPI1_CS_High();
    return val;
}

void MCP2515_WriteReg(uint8_t addr, uint8_t val){
    SPI1_CS_Low();
    SPI1_TransferByte(MCP_CMD_WRITE);
    SPI1_TransferByte(addr);
    SPI1_TransferByte(val);
    SPI1_CS_High();
}

void MCP2515_BitModify(uint8_t addr, uint8_t mask, uint8_t val){
    SPI1_CS_Low();
    SPI1_TransferByte(MCP_CMD_BIT_MODIFY);
    SPI1_TransferByte(addr);
    SPI1_TransferByte(mask);
    SPI1_TransferByte(val);
    SPI1_CS_High();
}

// ============================================================================
// Initialization
// ============================================================================

uint8_t MCP2515_Init(void){
    uint8_t mode;

    //Reset MCP2515 -- puts it in Configuration mode
    MCP2515_Reset();

    //Verify we're in Configuration mode
    mode = MCP2515_ReadReg(MCP_CANSTAT);
    if((mode & MCP_MODE_MASK) != MCP_MODE_CONFIG){
        USART2_PrintString("[CAN] ERR: MCP2515 not in config mode after reset\r\n");
        //Try once more
        MCP2515_Reset();
        mode = MCP2515_ReadReg(MCP_CANSTAT);
        if((mode & MCP_MODE_MASK) != MCP_MODE_CONFIG){
            USART2_PrintString("[CAN] ERR: MCP2515 failed to enter config mode\r\n");
            return 0;
        }
    }

    //Verify SPI communication: read CANSTAT, should show config mode (0x80)
    //Also try reading CNF1 default after reset (should be 0x00)
    uint8_t cnf1_test = MCP2515_ReadReg(MCP_CNF1);
    USART2_PrintString("[CAN] MCP2515 SPI OK, CANSTAT=0x");
    //Print hex manually
    {
        char hex[3];
        uint8_t hi = (mode >> 4) & 0x0F;
        uint8_t lo = mode & 0x0F;
        hex[0] = hi < 10 ? '0' + hi : 'A' + (hi - 10);
        hex[1] = lo < 10 ? '0' + lo : 'A' + (lo - 10);
        hex[2] = '\0';
        USART2_PrintString(hex);
    }
    USART2_PrintString("\r\n");

    // --- Bit timing for 500kbps @ 8MHz oscillator ---
    //CNF1: SJW=0 (1 TQ), BRP=0 (TQ = 250ns)
    //  [7:6] SJW = 00 (1 TQ)
    //  [5:0] BRP = 000000 (prescaler 1)
    MCP2515_WriteReg(MCP_CNF1, 0x00);

    //CNF2: BTLMODE=1 (PS2 from CNF3), SAM=0 (sample once), PHSEG1=3 (4 TQ), PRSEG=0 (1 TQ)
    //  [7] BTLMODE = 1
    //  [6] SAM = 0
    //  [5:3] PHSEG1 = 011 (4 TQ)
    //  [2:0] PRSEG = 000 (1 TQ)
    MCP2515_WriteReg(MCP_CNF2, 0x98); //1 00 11 000 = 0x98

    //CNF3: SOF=0, WAKFIL=0, PHSEG2=1 (2 TQ)
    //  [7] SOF = 0
    //  [6] WAKFIL = 0
    //  [2:0] PHSEG2 = 001 (2 TQ)
    MCP2515_WriteReg(MCP_CNF3, 0x01);

    // --- Interrupt enable: RX0 and RX1 buffer full ---
    MCP2515_WriteReg(MCP_CANINTE, MCP_RX0IF | MCP_RX1IF);

    // --- RX buffer 0: Accept all messages (mask = 0x000) ---
    //Set mask 0 to all zeros (accept everything)
    MCP2515_WriteReg(MCP_RXM0SIDH, 0x00);
    MCP2515_WriteReg(MCP_RXM0SIDL, 0x00);
    MCP2515_WriteReg(MCP_RXM0EID8, 0x00);
    MCP2515_WriteReg(MCP_RXM0EID0, 0x00);

    //Set mask 1 to all zeros too
    MCP2515_WriteReg(MCP_RXM1SIDH, 0x00);
    MCP2515_WriteReg(MCP_RXM1SIDL, 0x00);
    MCP2515_WriteReg(MCP_RXM1EID8, 0x00);
    MCP2515_WriteReg(MCP_RXM1EID0, 0x00);

    // --- RXB0CTRL: Accept all messages, rollover to RXB1 ---
    //  [6:5] RXM = 11 (turn mask/filter off, accept all)
    //  [2] BUKT = 1 (rollover to RXB1 if RXB0 full)
    MCP2515_WriteReg(MCP_RXB0CTRL, 0x64); //0110 0100

    // --- RXB1CTRL: Accept all messages ---
    MCP2515_WriteReg(MCP_RXB1CTRL, 0x60); //0110 0000

    // --- Clear all interrupt flags ---
    MCP2515_WriteReg(MCP_CANINTF, 0x00);

    // --- Switch to Normal mode ---
    MCP2515_BitModify(MCP_CANCTRL, MCP_MODE_MASK, MCP_MODE_NORMAL);

    //Wait for mode switch and verify
    delay_ms_approx(10);
    mode = MCP2515_ReadReg(MCP_CANSTAT);
    if((mode & MCP_MODE_MASK) != MCP_MODE_NORMAL){
        USART2_PrintString("[CAN] ERR: Failed to enter normal mode, CANSTAT=0x");
        {
            char hex[3];
            uint8_t hi = (mode >> 4) & 0x0F;
            uint8_t lo = mode & 0x0F;
            hex[0] = hi < 10 ? '0' + hi : 'A' + (hi - 10);
            hex[1] = lo < 10 ? '0' + lo : 'A' + (lo - 10);
            hex[2] = '\0';
            USART2_PrintString(hex);
        }
        USART2_PrintString("\r\n");
        return 0;
    }

    USART2_PrintString("[CAN] Init OK: 500kbps, normal mode\r\n");
    return 1;
}

// ============================================================================
// Send a CAN message
// ============================================================================

uint8_t MCP2515_SendMessage(CAN_Message *msg){
    //Check if TX buffer 0 is free (TXREQ bit in TXB0CTRL)
    uint8_t ctrl = MCP2515_ReadReg(MCP_TXB0CTRL);
    if(ctrl & 0x08){ //TXREQ bit is set, buffer busy
        //Try waiting briefly
        for(int i = 0; i < 100; i++){
            ctrl = MCP2515_ReadReg(MCP_TXB0CTRL);
            if(!(ctrl & 0x08)) break;
        }
        if(ctrl & 0x08){
            return 0; //TX buffer still busy
        }
    }

    //Load TX buffer 0 using sequential write
    //Standard ID: 11 bits. SIDH = ID[10:3], SIDL = ID[2:0] << 5
    uint8_t sidh = (uint8_t)(msg->id >> 3);
    uint8_t sidl = (uint8_t)((msg->id & 0x07) << 5); //EXIDE=0 (standard frame)

    //Use LOAD TX BUFFER command (faster than individual writes)
    SPI1_CS_Low();
    SPI1_TransferByte(MCP_CMD_LOAD_TX0); //Load TX0 starting at TXB0SIDH
    SPI1_TransferByte(sidh);             //TXB0SIDH
    SPI1_TransferByte(sidl);             //TXB0SIDL
    SPI1_TransferByte(0x00);             //TXB0EID8 (not used for standard)
    SPI1_TransferByte(0x00);             //TXB0EID0
    SPI1_TransferByte(msg->dlc & 0x0F); //TXB0DLC (RTR=0)
    for(uint8_t i = 0; i < msg->dlc; i++){
        SPI1_TransferByte(msg->data[i]); //TXB0D0..D7
    }
    SPI1_CS_High();

    //Request to send
    SPI1_CS_Low();
    SPI1_TransferByte(MCP_CMD_RTS_TX0);
    SPI1_CS_High();

    //Clear TX interrupt flag
    MCP2515_BitModify(MCP_CANINTF, MCP_TX0IF, 0x00);

    return 1;
}

// ============================================================================
// Receive a CAN message
// ============================================================================

uint8_t MCP2515_ReadMessage(CAN_Message *msg){
    uint8_t intf = MCP2515_ReadReg(MCP_CANINTF);

    if(intf & MCP_RX0IF){
        //Read RX buffer 0 using fast read command
        SPI1_CS_Low();
        SPI1_TransferByte(MCP_CMD_READ_RX0); //Read RXB0 starting at SIDH
        uint8_t sidh = SPI1_TransferByte(0x00); //RXB0SIDH
        uint8_t sidl = SPI1_TransferByte(0x00); //RXB0SIDL
        SPI1_TransferByte(0x00); //EID8 (skip)
        SPI1_TransferByte(0x00); //EID0 (skip)
        uint8_t dlc = SPI1_TransferByte(0x00);  //DLC
        msg->dlc = dlc & 0x0F;
        for(uint8_t i = 0; i < msg->dlc; i++){
            msg->data[i] = SPI1_TransferByte(0x00);
        }
        SPI1_CS_High();

        //Reconstruct standard ID from SIDH and SIDL
        msg->id = ((uint16_t)sidh << 3) | ((sidl >> 5) & 0x07);

        //Clear RX0IF
        MCP2515_BitModify(MCP_CANINTF, MCP_RX0IF, 0x00);
        return 1;
    }
    else if(intf & MCP_RX1IF){
        //Read RX buffer 1
        SPI1_CS_Low();
        SPI1_TransferByte(MCP_CMD_READ_RX1);
        uint8_t sidh = SPI1_TransferByte(0x00);
        uint8_t sidl = SPI1_TransferByte(0x00);
        SPI1_TransferByte(0x00);
        SPI1_TransferByte(0x00);
        uint8_t dlc = SPI1_TransferByte(0x00);
        msg->dlc = dlc & 0x0F;
        for(uint8_t i = 0; i < msg->dlc; i++){
            msg->data[i] = SPI1_TransferByte(0x00);
        }
        SPI1_CS_High();

        msg->id = ((uint16_t)sidh << 3) | ((sidl >> 5) & 0x07);

        //Clear RX1IF
        MCP2515_BitModify(MCP_CANINTF, MCP_RX1IF, 0x00);
        return 1;
    }

    return 0; //No message
}

uint8_t MCP2515_CheckRxStatus(void){
    uint8_t intf = MCP2515_ReadReg(MCP_CANINTF);
    return (intf & (MCP_RX0IF | MCP_RX1IF));
}

uint8_t MCP2515_GetErrorFlags(void){
    return MCP2515_ReadReg(MCP_EFLG);
}
