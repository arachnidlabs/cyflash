/** \file
 *  
 *  This file implements the Cypress bootloader transport interface
 *  on raw standard (11bit IDs) CANbus frames.
 *  The CANbus component should be named "CAN", no interrupts, all
 *  mboxes configured as basic.
 *  The Bootloader component needs to be configured on "custom interface"
 *  communication component, since I'm too lazy to implement the remaining
 *  bells & whistles.
 *  If you want to update specific devices on the bus, define
 *  CHECK_DEVICE_CANBUS_ID and place the relevant ID in the external
 *  CANbus_ID variable. In this case you can also define a "broadcast" id with
 *  CANBUS_BROADCAST_ID.
 *  If neither are defined all incoming frames are used.
 *  By default the frame is just read from CANbus and passed up.
 *  Optionally you can define ECHO_CANBUS_FRAMES in order to echo back the read
 *  frame on the bus using own device ID. Useful if you are updating a single
 *  device at a time and want to keep the bootloader
 *  host in sync.
 *  
 *  \author Giuseppe Corbelli <giuseppe.corbelli@weightpack.com>
 *  \author Weightpack SRL - http://www.weightpack.com
 *  \copyright GNU Public License V3
 *
 *  SVN ID: $Id$
 */

#include <cytypes.h>

#include "CAN.h"

/** How much do we wait between mailboxes checks */
#define WAIT_STEP_MS    1u

/** Check if an RX mailbox is full */
#if (CY_PSOC3 || CY_PSOC5)
#   define CAN_RX_MAILBOX_IS_FULL(i)    ((CAN_RX[i].rxcmd.byte[0u] & CAN_RX_ACK_MSG) != 0)
#else  /* CY_PSOC4 */
#   define CAN_RX_MAILBOX_IS_FULL(i)    ((CAN_RX_CMD_REG(i) & CAN_RX_ACK_MSG) != 0)
#endif /* CY_PSOC3 || CY_PSOC5 */

/** Mark an RX mailbox as "free", that is mark the message as processed */
#if (CY_PSOC3 || CY_PSOC5)
#   define CAN_RX_MAILBOX_FREE(i)    (CAN_RX[i].rxcmd.byte[0u] |= CAN_RX_ACK_MSG)
#else  /* CY_PSOC4 */
#   define CAN_RX_MAILBOX_FREE(i)    (CAN_RX_CMD_REG(i) |= CAN_RX_ACK_MSG)
#endif /* CY_PSOC3 || CY_PSOC5 */

/** Check if a TX mailbox is full */
#if (CY_PSOC3 || CY_PSOC5)
// Both should be the same
//  #define CAN_TX_MAILBOX_IS_FULL(i) (CAN_BUF_SR_REG.byte[2] & (uint8)(1u << i))
#   define CAN_TX_MAILBOX_IS_FULL(i) (CAN_TX[i].txcmd.byte[0] & CAN_TX_REQUEST_PENDING)
#else  /* CY_PSOC4 */
#   error CAN_TX_MAILBOX_IS_FULL is only implemented on PSOC3/PSOC5
#endif /* CY_PSOC3 || CY_PSOC5 */

// --------------------------------------------------------------------------

// Pointer to the last RX mailbox examined. Must apply a FIFO order.
static uint8 mailbox = 0;

extern uint16 CANbus_ID;

// --------------------------------------------------------------------------

void CyBtldrCommStart(void)
{
    CAN_Start();
}

void CyBtldrCommStop(void)
{
    CAN_Stop();
}

void CyBtldrCommReset(void)
{
    uint8 i;

    // Abort pending messages
    for (i = 0u; i < CAN_NUMBER_OF_TX_MAILBOXES; i++) {
        CAN_TX_ABORT_MESSAGE(i);
        CAN_RX_RTR_ABORT_MESSAGE(i);
    }
    CAN_Stop();
    CAN_Start();
}

/** Write a packet to basic TX mailbox 0 */
cystatus CyBtldrCommWrite(uint8* buffer, uint16 size, uint16* count, uint8 timeout)
{
    CAN_TX_MSG msg;
    uint32 regTemp;
    int16 timeout_ms = 10 * timeout;
    uint8 i, j;
    uint16 pointer = 0;
    uint8 chunk = 0;
    cystatus result = CYRET_TIMEOUT;

    if (size == 0)
        return CYRET_TIMEOUT;

    // For sake of simplicity we're using just mailbox 0
    // Besides, we prefer to go slow and safe and make sure
    // no outgoing messages are overlapping (in terms of priorities)
    // Make sure it's a basic mailbox
    CYASSERT((CAN_TX_MAILBOX_TYPE & 0x01) == 0u);

    msg.id = CANbus_ID;
    msg.ide = CAN_STANDARD_MESSAGE;
    msg.rtr = CAN_STANDARD_MESSAGE;
    msg.irq = CAN_TRANSMIT_INT_DISABLE;

    // Make sure there's no TX pending in the first mbox
    do {
        if (!CAN_TX_MAILBOX_IS_FULL(0))
            break;
        if (timeout) {
            CyDelay(WAIT_STEP_MS);
            timeout_ms -= WAIT_STEP_MS;
        }
    } while (timeout_ms >= 0);

    if (timeout_ms < 0) {
        return CYRET_TIMEOUT;
    }

    // Ok, mailbox is free
    while ((pointer < size) && (timeout_ms >= 0)) {
        chunk = ((size - pointer) > CAN_TX_DLC_MAX_VALUE) ? CAN_TX_DLC_MAX_VALUE : (size - pointer);
        msg.dlc = chunk;

        regTemp = 0u;

        /* Set message parameters */
        CAN_SET_TX_ID_STANDARD_MSG(0, msg.id);
        if (msg.dlc < CAN_TX_DLC_MAX_VALUE) {
            regTemp |= ((uint32)msg.dlc) << CAN_TWO_BYTE_OFFSET;
        } else {
            regTemp |= CAN_TX_DLC_UPPER_VALUE;
        }
        for (j = 0u; (j < msg.dlc) && (j < CAN_TX_DLC_MAX_VALUE); j++) {
            CAN_TX_DATA_BYTE(0, j) = buffer[j+pointer];
        }
        pointer += chunk;
        /* Reuse variable to mark the current error count */
        j = CAN_GetTXErrorCount();

        /* Disable isr */
        CyIntDisable(CAN_ISR_NUMBER);
        /* WPN[23] and WPN[3] set to 1 for write to CAN Control reg */
        CY_SET_REG32(CAN_TX_CMD_PTR(0), (regTemp | CAN_TX_WPN_SET));
        CY_SET_REG32(CAN_TX_CMD_PTR(0), CAN_SEND_MESSAGE);
        /* Enable isr */
        CyIntEnable(CAN_ISR_NUMBER);

        // Check that the mailbox is free (that is, frame sent)
        do {
            i = CAN_GetTXErrorCount();
            if (j != i) {
                // TX failed, error count increased
                CAN_TxCancel(0);
                return CYRET_TIMEOUT;
            } else {
                result = CYRET_SUCCESS;
            }
            if (timeout) {
                CyDelay(WAIT_STEP_MS);
                timeout_ms -= WAIT_STEP_MS;
            }
        } while (CAN_TX_MAILBOX_IS_FULL(0) && (CAN_GetErrorState() == 0) && (timeout_ms >= 0));
    }

    if (timeout_ms < 0) {
        return CYRET_TIMEOUT;
    }

    // Useless as of bootloader v1.5
    *count = size;

    result |= CAN_GetErrorState();
    return (result == 0) ? CYRET_SUCCESS : CYRET_TIMEOUT;
}

/** Read a packet from a basic RX mailbox (FIFO) and optionally echo it back before returning */
cystatus CyBtldrCommRead(uint8* buffer, uint16 size, uint16* count, uint8 timeout)
{
    int16 timeout_ms = 10 * timeout;
    uint16 frame_id;
    uint16 copied = 0;
    uint16 pointer = 0;
    uint8 full_mailboxes = 0;
    uint8 dlc;
    uint8 bswap_dest[] = {3u, 2u, 1u, 0u, 7u, 6u, 5u, 4u};
#if (CY_PSOC3)
    bit got_sop;
    bit got_eop;
#else
    uint8 got_sop;
    uint8 got_eop;
#endif

    *count = 0;
    if (size == 0)
        return CYRET_SUCCESS;

    memset(buffer, 0, size);

    // Make sure we have room in the buffer to accomodate a full CAN frame
    // Buffer should be 300 bytes, see Bootloader_SIZEOF_COMMAND_BUFFER
    CYASSERT(size >= CAN_TX_DLC_MAX_VALUE);

    do {
        // Restart from the last-used mailbox, see static definition above
        if (mailbox >= CAN_NUMBER_OF_RX_MAILBOXES) {
            mailbox = 0;
            full_mailboxes = 0;
        }
        for (; mailbox < CAN_NUMBER_OF_RX_MAILBOXES; mailbox++) {
            // Reuse variable
            copied = CAN_GetErrorState();
            switch (copied) {
                case (0x0000):  // Error active
                case (0x0001):  // Error passive
                    break;
                default:  // Bus off
                    return CYRET_INVALID_STATE;
            }

            // Check message available
            if (!CAN_RX_MAILBOX_IS_FULL(mailbox)) {
                // No message, check next mailbox
                continue;
            }

#ifdef CHECK_DEVICE_CANBUS_ID
            frame_id = (CY_GET_REG32((reg32 *) (&CAN_RX->rxid)) >> CAN_SET_TX_ID_STANDARD_MSG_SHIFT);
            if ((frame_id != CANbus_ID)
#   ifdef CANBUS_BROADCAST_ID
                && (frame_id != CANBUS_BROADCAST_ID)
#   endif // CANBUS_BROADCAST_ID
            )
            {
                CAN_RX_MAILBOX_FREE(mailbox);
                continue;  // Message for another recipient, next mbox
            }
#endif

            full_mailboxes++;

            dlc = CAN_RX[mailbox].rxcmd.byte[2u] & 0x0F;
            copied = dlc;
            // Apparently a data payload sent from IXXAT Minimon/Codesys as
            // 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08
            // gets interpreted here as
            // 0x04, 0x03, 0x02, 0x01, 0x08, 0x07, 0x06, 0x05
            // Seems the usual big/little endian issue

            while (copied) {
                copied--;
                buffer[*count + copied] = CAN_RX[mailbox].rxdata.byte[bswap_dest[copied]];
            }
            CAN_RX_MAILBOX_FREE(mailbox);

#ifdef ECHO_CANBUS_FRAMES
            // Send back what we have just received
            CyBtldrCommWrite(buffer+(*count), dlc, &copied, 0);
#endif  // ECHO_CANBUS_FRAMES

            *count += dlc;

            // Check if the high level packet is completed, so we can stop
            // the reading loop without waiting for timeout

            // Reuse variable, data length field in packet
            copied = *(uint16*)(buffer+2);
#if CY_PSOC3
            copied = CYSWAP_ENDIAN16(copied);
#endif
            got_sop = (buffer[0] == 0x01);
            got_eop = (buffer[(*count)-1] == 0x17);
            // Got start and end of packet, check that we have
            // SOP + command + 2 bytes data length + payload + 2 bytes checksum + eop
            // Reuse variable
            frame_id = 1 + 1 + 2 + copied + 2 + 1;
            if ((*count == frame_id) && (got_sop) && (got_eop)) {
                return CYRET_SUCCESS;
            }
            
        }  // for mailboxes loop -------------------------------------------------
        
        // Wait a little if all the mailboxes in the last scan were empty
        if (timeout && !full_mailboxes) {
            CyDelay(WAIT_STEP_MS);
            timeout_ms -= WAIT_STEP_MS;
        }
    } while (timeout_ms >= 0);

    got_sop = (buffer[0] == 0x01);
    got_eop = (buffer[(*count)-1] == 0x17);
    frame_id = 1 + 1 + 2 + copied + 2 + 1;
    if ((*count == frame_id) && (got_sop) && (got_eop)) {
        return CYRET_SUCCESS;
    }
    
    return CYRET_TIMEOUT;
}
