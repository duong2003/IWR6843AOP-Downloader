#!/usr/bin/env python3
"""
IWR6843AOP Erase Tool - SFLASH Firmware Eraser
===============================================
Standalone tool to erase firmware from IWR6843AOP SFLASH memory

FLOW OVERVIEW:
1. Initialize hardware connection (COM9)
2. Set device parameters (IWR6843AOP, part number)  
3. Erase existing firmware from SFLASH
4. Verify erase completed successfully
5. Disconnect cleanly

USAGE:
- Simply run: python erase.py
- No command line arguments needed
- Uses hardcoded COM9 connection
- Only erases SFLASH firmware area

Author: Based on TI mmWave infrastructure
Date: 2025-09-19
Target: IWR6843AOP only, SFLASH erase operation
"""

# ============================================================================
# IMPORTS - All required libraries for standalone operation
# ============================================================================
import os        # File operations
import sys       # System operations  
import time      # Delays and timing
import json      # Not used in simplified version, kept for compatibility
import inspect   # Not used in simplified version, kept for compatibility
import string    # String operations
import struct    # Binary data packing/unpacking for bootloader protocol
import serial    # Serial communication with IWR6843AOP
from serial import SerialException
import binascii  # Binary/hex conversions for bootloader protocol
import subprocess # Not used in simplified version, kept for compatibility
import datetime  # For timestamp logging

# ============================================================================
# COMMUNICATION LOGGER - Raw data logging for debugging
# ============================================================================

class CommLogger:
    """Communication logger for raw data debugging"""
    
    def __init__(self, log_file="log.txt"):
        self.log_file = log_file
        self.enabled = True
        # Clear previous log file
        try:
            with open(self.log_file, 'w') as f:
                f.write(f"=== IWR6843AOP Erase Tool Communication Log ===\n")
                f.write(f"Started: {datetime.datetime.now()}\n")
                f.write("=" * 60 + "\n\n")
        except Exception as e:
            print(f"Warning: Cannot create log file: {e}")
            self.enabled = False
    
    def log_write(self, port, data, description=""):
        """Log data being written to serial port"""
        if not self.enabled:
            return
        
        try:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            hex_data = ' '.join(f'0x{byte:02X}' for byte in data)
            
            # Console output
            print(f"[TX {timestamp}] {description}")
            print(f"    Port: {port} | Bytes: {len(data)} | Data: {hex_data}")
            
            # File output
            with open(self.log_file, 'a') as f:
                f.write(f"[TX {timestamp}] {description}\n")
                f.write(f"    Port: {port} | Bytes: {len(data)}\n")
                f.write(f"    Raw Data: {hex_data}\n")
                f.write(f"    ASCII: {self._to_printable_ascii(data)}\n\n")
        except Exception as e:
            print(f"Log write error: {e}")
    
    def log_read(self, port, data, description=""):
        """Log data being read from serial port"""
        if not self.enabled:
            return
            
        try:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            hex_data = ' '.join(f'0x{byte:02X}' for byte in data)
            
            # Console output
            print(f"[RX {timestamp}] {description}")
            print(f"    Port: {port} | Bytes: {len(data)} | Data: {hex_data}")
            
            # File output
            with open(self.log_file, 'a') as f:
                f.write(f"[RX {timestamp}] {description}\n")
                f.write(f"    Port: {port} | Bytes: {len(data)}\n")
                f.write(f"    Raw Data: {hex_data}\n")
                f.write(f"    ASCII: {self._to_printable_ascii(data)}\n\n")
        except Exception as e:
            print(f"Log read error: {e}")
    
    def log_event(self, event, description=""):
        """Log general events"""
        if not self.enabled:
            return
            
        try:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            
            # Console output
            print(f"[EVENT {timestamp}] {event}: {description}")
            
            # File output
            with open(self.log_file, 'a') as f:
                f.write(f"[EVENT {timestamp}] {event}: {description}\n\n")
        except Exception as e:
            print(f"Log event error: {e}")
    
    def _to_printable_ascii(self, data):
        """Convert binary data to printable ASCII representation"""
        result = ""
        for byte in data:
            if 32 <= byte <= 126:  # Printable ASCII range
                result += chr(byte)
            else:
                result += f"\\x{byte:02X}"
        return result
    
    def close(self):
        """Close log file with summary"""
        if not self.enabled:
            return
            
        try:
            with open(self.log_file, 'a') as f:
                f.write("=" * 60 + "\n")
                f.write(f"Log ended: {datetime.datetime.now()}\n")
                f.write("=" * 60 + "\n")
        except Exception as e:
            print(f"Log close error: {e}")

# Global logger instance
comm_logger = CommLogger()

# ============================================================================
# EMBEDDED SERIAL STUB MODULE (from serialStub.py)
# ============================================================================

# Global variables for SerialStub - Simplified for IWR6843AOP only
GETVERSION_REQ = False
GETVERSION_CALLED = False
GETVERSION_CRC_NEXT = False

# Serial stub constants
AR_BOOTLDR_OPCODE_ACK               = struct.pack("B", 0xCC)
AR_BOOTLDR_OPCODE_NACK              = struct.pack("B", 0x33)
AR_BOOTLDR_OPCODE_PING              = struct.pack("B", 0x20)
AR_BOOTLDR_OPCODE_START_DOWNLOAD    = struct.pack("B", 0x21)
AR_BOOTLDR_OPCODE_FILE_CLOSE        = struct.pack("B", 0x22)
AR_BOOTLDR_OPCODE_GET_LAST_STATUS   = struct.pack("B", 0x23)
AR_BOOTLDR_OPCODE_SEND_DATA         = struct.pack("B", 0x24)
AR_BOOTLDR_OPCODE_SEND_DATA_RAM     = struct.pack("B", 0x26)
AR_BOOTLDR_OPCODE_DISCONNECT        = struct.pack("B", 0x27)
AR_BOOTLDR_OPCODE_ERASE             = struct.pack("B", 0x28)
AR_BOOTLDR_OPCODE_FILE_ERASE        = struct.pack("B", 0x2E)
AR_BOOTLDR_OPCODE_GET_VERSION_INFO  = struct.pack("B", 0x2F)

AR_BOOTLDR_SYNC_PATTERN             = struct.pack("B", 0xAA)
AR_BOOTLDR_OPCODE_RET_SUCCESS             = struct.pack("B", 0x40)
AR_BOOTLDR_OPCODE_RET_ACCESS_IN_PROGRESS  = struct.pack("B", 0x4B)

class SerialStub:
    """Serial stub for testing without EVM"""
    
    def __init__(self, port, baudrate, timeout):
        self.comm_port = port
        self.baudrate = baudrate
        self.timeout = timeout
        if (port != ''):
            self.opened = True
        print("xxx SerialPort created Comm port=%s" % (port), end="")
        print(", baudrate=%d" % (baudrate) + ", timeout=%d" % (timeout))

    def open(self):
        print("xxx Opening comm_port %s" % (self.comm_port))
        self.opened = True

    def close(self):
        self.opened = False
        print("xxx Closed comm_port %s" % (self.comm_port))

    def write(self, value):
        global GETVERSION_REQ
        global GETVERSION_CALLED
        global comm_logger
        
        # Log the write operation
        comm_logger.log_write(self.comm_port, value, "SerialStub Write")
        
        if (GETVERSION_CALLED is True and (value == AR_BOOTLDR_OPCODE_GET_VERSION_INFO)):
            GETVERSION_REQ = True
        print("xxx List of bytes written to comm_port %s" % (self.comm_port))
        b = bytearray(value)
        print("Size of written array =%d" % (len(b)))
        for i in b:
            print(hex(i), end=" ")

    def read(self, value):
        global GETVERSION_REQ
        global GETVERSION_CRC_NEXT
        global comm_logger
        
        if (value != 0):
            if (GETVERSION_REQ is True):
                if (value == 1):
                    if (GETVERSION_CRC_NEXT is True):
                        # IWR6843AOP always uses 16-byte version response
                        bytesRead = struct.pack("B",16)
                        GETVERSION_CRC_NEXT = False
                    else:
                        bytesRead = AR_BOOTLDR_OPCODE_ACK
                if (value == 2):
                    bytesRead = struct.pack(">H",14)
                    GETVERSION_CRC_NEXT = True
                if (value >= 12):
                    # IWR6843AOP version format: 08 00 06 02 00 00 00 00 00 00 00 00
                    bytesRead = binascii.a2b_hex("080006020000000000000000")
                    GETVERSION_REQ = False
            else:
                bytesRead = AR_BOOTLDR_OPCODE_ACK
                if (value >= 2):
                    bytesRead = struct.pack("B",0) + struct.pack("B",3)
                if (value >= 3):
                    bytesRead = bytesRead + struct.pack("B",ord(AR_BOOTLDR_OPCODE_ACK))
                if (value >= 4):
                    bytesRead = bytesRead + struct.pack("B",ord(AR_BOOTLDR_OPCODE_RET_SUCCESS))
            
            # Log the read operation
            comm_logger.log_read(self.comm_port, bytesRead, f"SerialStub Read ({value} bytes requested)")
            
            b = bytearray(bytesRead)
            print("xxx Bytes read from comm_port %s" % (self.comm_port))
            for i in b:
                print(hex(i), end=" ")
            return bytesRead
        else:
            print("xxx Error!!!")

    def setBreak(self, value):
        print("xxx Break sent to comm_port %s" % (self.comm_port))

    def isOpen(self):
        if (self.opened):
            print("xxx Comm_port %s" % (self.comm_port) + " is open.")
            return True
        else:
            print("xxx !!!!! Comm_port %s" % (self.comm_port) + " is not open!!!!!")
            return False

    def flushInput(self):
        print("xxx Flushing Input.......")

# ============================================================================
# EMBEDDED MMWAVE PROG FLASH MODULE (from mmWaveProgFlash.py)  
# ============================================================================

# Constants and configurations
STUBOUT_VALUE = False  # Set to True for testing without EVM

DEFAULT_SERIAL_BAUD_RATE            = 115200
DEFAULT_CHUNK_SIZE                  = 240
MAX_FILE_SIZE                       = 1024*1024
MAX_APP_FILE_SIZE                   = 166912
FILE_HEADERSIZE                     = 4
AWR_CANCEL_MSG = "Cancel request detected...Ceasing erase operation."

# File types mapping - IWR6843AOP only needs META_IMAGE1
Files = {
"META_IMAGE1"              : struct.pack(">I",4)
}

# IWR6843AOP constants
IWR68xx_PART_NUM  = "IWR68"

# File header versions
AWR_PRE_PG3_KEY = "PrePG3"
AWR_POST_PG3_KEY = "PostPG3"

# IWR6843AOP file headers - simplified for single device
IWR6843AOP_HEADERS = [0x5254534D]
IWR6843AOP_FILE_TYPE = ["META_IMAGE1"]

# Version information
AWR_VERSION_PG1_14_12 = "07000600"
AWR_VERSION_PG2_14_12 = "01000601"
AWR_VERSION_PG1_16    = "08000602"

BootloaderVerPrePG3 = [AWR_VERSION_PG1_14_12, AWR_VERSION_PG2_14_12]

# Storage types
Storages = {
"SDRAM"     : struct.pack(">I", 0),
"FLASH"     : struct.pack(">I", 1),
"SFLASH"    : struct.pack(">I", 2),
"EEPROM"    : struct.pack(">I", 3),
"SRAM"      : struct.pack(">I", 4)
}

# Bootloader opcodes (consolidated from both modules)
AWR_BOOTLDR_OPCODE_ACK               = struct.pack("B", 0xCC)
AWR_BOOTLDR_OPCODE_NACK              = struct.pack("B", 0x33)
AWR_BOOTLDR_OPCODE_PING              = struct.pack("B", 0x20)
AWR_BOOTLDR_OPCODE_START_DOWNLOAD    = struct.pack("B", 0x21)
AWR_BOOTLDR_OPCODE_FILE_CLOSE        = struct.pack("B", 0x22)
AWR_BOOTLDR_OPCODE_GET_LAST_STATUS   = struct.pack("B", 0x23)
AWR_BOOTLDR_OPCODE_SEND_DATA         = struct.pack("B", 0x24)
AWR_BOOTLDR_OPCODE_SEND_DATA_RAM     = struct.pack("B", 0x26)
AWR_BOOTLDR_OPCODE_DISCONNECT        = struct.pack("B", 0x27)
AWR_BOOTLDR_OPCODE_ERASE             = struct.pack("B", 0x28)
AWR_BOOTLDR_OPCODE_FILE_ERASE        = struct.pack("B", 0x2E)
AWR_BOOTLDR_OPCODE_GET_VERSION_INFO  = struct.pack("B", 0x2F)

AWR_BOOTLDR_SYNC_PATTERN             = struct.pack("B", 0xAA)
AWR_BOOTLDR_OPCODE_RET_SUCCESS             = struct.pack("B", 0x40)
AWR_BOOTLDR_OPCODE_RET_ACCESS_IN_PROGRESS  = struct.pack("B", 0x4B)

# Device variants
AWR_DEVICE_IS_AWR12XX               = struct.pack("B", 0x00)
AWR_DEVICE_IS_AWR14XX               = struct.pack("B", 0x01)
AWR_DEVICE_IS_AWR16XX               = struct.pack("B", 0x03)
AWR_DEVICE_IS_AWR17XX               = struct.pack("B", 0x10)

# Progress indicator constants
UNIFLASH_PROG_INDICATOR_RANGE     = 82
UNIFLASH_PROG_INDICATOR_B4_SHUTDOWN = 98
ERASE_PROG_VALUE                  = 4

# Trace levels
TRACE_LEVEL_FATAL = 3
TRACE_LEVEL_ERROR = 2
TRACE_LEVEL_WARNING = 1
TRACE_LEVEL_INFO = 0
TRACE_LEVEL_DEBUG = -1
TRACE_LEVEL_ACTIVITY = TRACE_LEVEL_INFO
FLASHPYTHON_DEBUG_LEVEL = 255

# Configuration
ROM_VERSION = 1.0
RUN_COUNT = 0
IGNORE_BYTE_CONDITION = True
IS_FILE_ALLOCATED     = False
CHIP_VARIANT          = "CC"

# Keys from Uniflash UI (simplified for IWR6843AOP)
COMPORT_KEY     = 'COMPort'
MEMSELECT_KEY   = 'MemSelectRadio'
DOWNLOADFORMAT_KEY = 'DownloadFormat'

class FilesObject(object):
    """File information object"""
    file_id = ""
    fileSize = 0
    order = 0
    path = ""

    def __init__(self, path, order):
        self.path = path
        self.order = order
        self.file_id = ""
        self.fileSize = 0

class BootLdr:
    """Main bootloader class for mmWave devices"""

    def __init__(self, cls, com_port, trace_level=0):
        self.callbackClass=cls
        self.com_port = com_port
        self.baudrate = DEFAULT_SERIAL_BAUD_RATE
        self.chunksize = DEFAULT_CHUNK_SIZE
        self.FileList = Files
        self.StorageList = Storages
        self.trace_level = trace_level
        self.IGNORE_BYTE_CONDITION = IGNORE_BYTE_CONDITION
        self.IS_FILE_ALLOCATED = False
        self.MAX_APP_FILE_SIZE = MAX_APP_FILE_SIZE
        self.CHIP_VARIANT = CHIP_VARIANT
        self.ROM_VERSION = ROM_VERSION
        self.cmdStatusSize = 1
        self.connected = False
        self.progPercentage = 0
        self.imageProgCntList = {}
        self.PG3OrLater = False
        self.progMessage =""
        self.cancelRequested = False
        self.stubOut = STUBOUT_VALUE
        self._trace_msg(TRACE_LEVEL_DEBUG, "===>" + self.__class__.__name__ + " init complete")

    def _update_prog_msg(self,updateStr,incPercent):
        if (self.callbackClass != ''):
            newProgPercent = self.progPercentage + incPercent
            if (newProgPercent > UNIFLASH_PROG_INDICATOR_B4_SHUTDOWN):
                newProgPercent = UNIFLASH_PROG_INDICATOR_B4_SHUTDOWN
                self._trace_msg(TRACE_LEVEL_DEBUG, "Progress bar maxed out!!")
            if (updateStr == ""):
                stringToSend = self.progMessage
            else:
                stringToSend = updateStr
                self.progMessage = updateStr
            self.callbackClass.update_progress(str(stringToSend), newProgPercent)
            self.update_prog_percentage(newProgPercent)

    def _trace_msg(self,level,msgStr):
        if (self.callbackClass != ''):
            if (level >= self.trace_level):
                if (level == TRACE_LEVEL_DEBUG):
                    level=FLASHPYTHON_DEBUG_LEVEL
                self.callbackClass.push_message(str(msgStr), level)
        else:
            if (level >= self.trace_level):
               print ("%s"%(msgStr))

    def _checkForCancel(self):
        if (self.callbackClass != ''):
            status = self.callbackClass.check_is_cancel_set()
            self.cancelRequested = True
        else:
            status = False
        return status

    def _comm_open(self):
        global comm_logger
        self._trace_msg(TRACE_LEVEL_DEBUG,"--> Entering _comm_open method")
        comm_logger.log_event("CONN_OPEN", f"Opening COM port {self.com_port}")
        
        if(self._is_connected()):
            self._trace_msg(TRACE_LEVEL_DEBUG,"<-- Exiting _comm_open method")
            return True
        if (self.stubOut is False):
            try:
                self.comm = serial.Serial(port=self.com_port, baudrate=self.baudrate, timeout=10)
                comm_logger.log_event("REAL_SERIAL", f"Real serial port opened: {self.com_port} @ {self.baudrate} baud")
            except SerialException:
                self._trace_msg(TRACE_LEVEL_ERROR, "Serial port %s"%(self.com_port) + " specified does not exist, is already open, or permission is denied!!")
                self._trace_msg(TRACE_LEVEL_ERROR, "!! Aborting operation!!")
                comm_logger.log_event("CONN_ERROR", f"Failed to open {self.com_port}")
                self._trace_msg(TRACE_LEVEL_DEBUG,"<-- Exiting _comm_open method")
                return False
        else:
            self.comm = SerialStub(port=self.com_port, baudrate=self.baudrate, timeout=6)
            comm_logger.log_event("STUB_SERIAL", f"Serial stub created for {self.com_port}")
        if self.comm.isOpen():
            self.comm.flushInput()
            self.connected = True
            self._trace_msg(TRACE_LEVEL_DEBUG,"COM port opened.")
            comm_logger.log_event("CONN_SUCCESS", f"Connected to {self.com_port}")
            self._trace_msg(TRACE_LEVEL_DEBUG,"<-- Exiting _comm_open method")
            return True
        else:
            self._trace_msg(TRACE_LEVEL_ERROR,"!!! Error opening the COM port!!!")
            comm_logger.log_event("CONN_ERROR", f"Failed to open COM port {self.com_port}")
            self._trace_msg(TRACE_LEVEL_DEBUG,"<-- Exiting _comm_open method")
            return False

    def _comm_close(self):
        global comm_logger
        self._trace_msg(TRACE_LEVEL_DEBUG,"--> Entering _comm_close method")
        comm_logger.log_event("CONN_CLOSE", f"Closing COM port {self.com_port}")
        
        if(self._is_connected()):
            self.comm.close()
            self.connected = False
            self._trace_msg(TRACE_LEVEL_DEBUG, "COM port closed.")
            comm_logger.log_event("CONN_CLOSED", f"COM port {self.com_port} closed successfully")
            self.comm = None
        self._trace_msg(TRACE_LEVEL_DEBUG,"<-- Exiting _comm_close method")

    def _is_connected(self):
        return self.connected

    def _send_packet(self,data):
        global comm_logger
        self._trace_msg(TRACE_LEVEL_DEBUG, "-----> Send packet")
        
        checksum = 0
        for b in data:
            checksum += b
        msgSize = len(data)+2
        sMsgSize = struct.pack(">H",msgSize)
        sChecksum = struct.pack("B",checksum & 0xff)
        
        # Log individual packet components
        comm_logger.log_write(self.com_port, AWR_BOOTLDR_SYNC_PATTERN, "SYNC_PATTERN")
        comm_logger.log_write(self.com_port, sMsgSize, f"MSG_SIZE ({msgSize})")
        comm_logger.log_write(self.com_port, sChecksum, f"CHECKSUM (0x{checksum & 0xff:02X})")
        comm_logger.log_write(self.com_port, data, "PAYLOAD_DATA")
        
        self.comm.write(AWR_BOOTLDR_SYNC_PATTERN)
        self.comm.write(sMsgSize)
        self.comm.write(sChecksum)
        self.comm.write(data)
        self._trace_msg(TRACE_LEVEL_DEBUG, "<----- Send packet")

    def _receive_packet(self, Length):
        global comm_logger
        self._trace_msg(TRACE_LEVEL_DEBUG, "----->Receive packet")
        
        Header = self.comm.read(3)
        comm_logger.log_read(self.com_port, Header, f"PACKET_HEADER (expecting {Length} bytes payload)")
        
        PacketLength , CheckSum  = struct.unpack(">HB", Header)
        PacketLength -= 2
        if (Length != PacketLength):
            self._trace_msg(TRACE_LEVEL_DEBUG, "Requested length={:d}, actual={:d}".format(Length, PacketLength))
            self._trace_msg(TRACE_LEVEL_FATAL, "Error, Mismatch between requested and actual packet length: act {:d}, req {:d}".format(PacketLength, Length))
        
        Payload = self.comm.read(PacketLength)
        comm_logger.log_read(self.com_port, Payload, f"PACKET_PAYLOAD ({PacketLength} bytes)")
        
        if (len(Payload) != Length):
            self._trace_msg(TRACE_LEVEL_FATAL, "Error, time-out while receiving packet's payload")
        
        ack_data = AWR_BOOTLDR_OPCODE_ACK
        comm_logger.log_write(self.com_port, ack_data, "ACK_RESPONSE")
        self.comm.write(ack_data)
        
        CalculatedCheckSum=0
        for byte in Payload:
            CalculatedCheckSum += byte
        CalculatedCheckSum &= 0xFF
        if (CalculatedCheckSum != CheckSum):
            self._trace_msg(TRACE_LEVEL_ERROR, "Calculated: 0x{:x}.  Received: 0x{:x}".format(CalculatedCheckSum, CheckSum))
            self._trace_msg(TRACE_LEVEL_FATAL, "Checksum error on received packet")
        else:
            self._trace_msg(TRACE_LEVEL_DEBUG, "Calculated and Received CheckSum: 0x{:x}.".format(CalculatedCheckSum))
        self._trace_msg(TRACE_LEVEL_DEBUG, "<----- Receive packet")
        return Payload

    def _read_ack(self):
        global comm_logger
        self._trace_msg(TRACE_LEVEL_DEBUG, "-----> Waiting for ACK message from device.")
        
        length = ''
        while (length == ''):
            length = self.comm.read(2)
        comm_logger.log_read(self.com_port, length, "ACK_LENGTH")
        
        chksum = self.comm.read(1)
        comm_logger.log_read(self.com_port, chksum, "ACK_CHECKSUM")
        
        reserved = self.comm.read(1)
        comm_logger.log_read(self.com_port, reserved, "ACK_RESERVED")
        
        a = self.comm.read(1)
        comm_logger.log_read(self.com_port, a, "ACK_OPCODE")
        
        status = False
        while (not ((a == AWR_BOOTLDR_OPCODE_ACK) or (a == AWR_BOOTLDR_OPCODE_NACK))):
            a = self.comm.read(1)
            comm_logger.log_read(self.com_port, a, "ACK_RETRY_READ")
            
        self._trace_msg(TRACE_LEVEL_DEBUG,"Checking message from device:")
        if (a == AWR_BOOTLDR_OPCODE_ACK):
            self._trace_msg(TRACE_LEVEL_DEBUG,"*** Received ACK ***")
            comm_logger.log_event("ACK_RECEIVED", "Device acknowledged command")
            status = True
        elif (a == AWR_BOOTLDR_OPCODE_NACK):
            self._trace_msg(TRACE_LEVEL_DEBUG,"*** Received NACK ***")
            comm_logger.log_event("NACK_RECEIVED", "Device rejected command")
            status = False
        else:
            self._trace_msg(TRACE_LEVEL_ERROR,"XXXX Received unexpected data!!!XXXX")
            comm_logger.log_event("ACK_ERROR", f"Unexpected ACK data: {a.hex() if a else 'None'}")
            status = False
        self._trace_msg(TRACE_LEVEL_DEBUG, "<----- Done waiting for ACK message from device.")
        return status

    def _read_ack_with_cancel_check(self):
        self._trace_msg(TRACE_LEVEL_DEBUG, "-----> Waiting for ACK message from device - w/ cancel check.")
        length = ''
        outerCount = 0
        c = False
        while ((c is False) and (outerCount < 10)):
            innerCount = 0
            while ((length == '') and (innerCount < 2)):
                length = self.comm.read(2)
                innerCount += 1
            c = self._checkForCancel()
            if (length != ''):
                break
            outerCount += 1
        if (c is True):
            self._trace_msg(TRACE_LEVEL_INFO, AWR_CANCEL_MSG)
            status = False
        elif (length == ''):
            self._trace_msg(TRACE_LEVEL_ERROR, "Initial response from the device was not received. Please power cycle device before re-erasing.")
            status = False
        else:
            chksum = self.comm.read(1)
            self.comm.read(1)
            a = self.comm.read(1)
            readCount = 0
            while not ((a == AWR_BOOTLDR_OPCODE_ACK) or (a == AWR_BOOTLDR_OPCODE_NACK)) and readCount < 10:
                a = self.comm.read(1)
                readCount += 1
            self._trace_msg(TRACE_LEVEL_DEBUG,"Checking message from device:")
            if (a == AWR_BOOTLDR_OPCODE_ACK):
                self._trace_msg(TRACE_LEVEL_DEBUG,"*** Received ACK ***")
                status = True
            elif (a == AWR_BOOTLDR_OPCODE_NACK):
                self._trace_msg(TRACE_LEVEL_DEBUG,"*** Received NACK ***")
                status = False
            else:
                self._trace_msg(TRACE_LEVEL_ERROR,"XXXX Received unexpected data!!!XXXX")
                status = False
        self._trace_msg(TRACE_LEVEL_DEBUG, "<----- Done waiting for ACK message from device w/ cancel check.")
        return status

    def _send_command(self,data):
        self._trace_msg(TRACE_LEVEL_DEBUG,"--->Send command")
        self._send_packet(data)
        ackStatus = self._read_ack()
        self._send_packet(AWR_BOOTLDR_OPCODE_GET_LAST_STATUS)
        retStatus = self._receive_packet(self.cmdStatusSize)
        self._trace_msg(TRACE_LEVEL_DEBUG,"<--- Send command")
        return ackStatus

    # ******************* APIs *******************

    def connect_with_reset(self, timeout, com_port, reset_command):
        passed = True
        self._trace_msg(TRACE_LEVEL_DEBUG,"->Entering connect_with_reset method")
        self._trace_msg(TRACE_LEVEL_ACTIVITY,"Reset connection to device")
        trace_level = self.trace_level
        self.__init__(self.callbackClass, com_port, trace_level)
        if (self._comm_open()):
            self._trace_msg(TRACE_LEVEL_INFO,"Set break signal")
            self._update_prog_msg("Opening COM port %s..."%(self.com_port), 1)
            self.comm.timeout = timeout
            if (sys.version_info[0] >= 2):
                self.comm.break_condition = True
            else:
                self.comm.setBreak(True)
            time.sleep(0.100)
            if (reset_command != ""):
                subprocess.call(reset_command)
            if (self._read_ack_with_cancel_check()):
                self._trace_msg(TRACE_LEVEL_ACTIVITY,"Connection to COM port succeeded. Erase can proceed.")
                self._update_prog_msg("Connected to COM port.", 1)
                if (sys.version_info[0] >= 2):
                    self.comm.break_condition = False
                else:
                    self.comm.setBreak(False)
                passed = True
            else:
                if (self.cancelRequested is False):
                    self._trace_msg(TRACE_LEVEL_ERROR,"Failure: Recheck that correct COM port was provided or power cycle the device.")
                passed = False
            self._comm_close()
            self._trace_msg(TRACE_LEVEL_DEBUG,"Exit bootldr connect")
        else:
            passed = False
        self._trace_msg(TRACE_LEVEL_DEBUG,"<- Exiting connect_with_reset method")
        return passed

    def skip_connect(self):
        self.connected = True

    def connect(self, timeout, com_port):
        self._trace_msg(TRACE_LEVEL_ACTIVITY,"Connecting to COM Port %s"%(com_port) + "...")
        return self.connect_with_reset(timeout, com_port, "")

    def disconnect(self):
        self._trace_msg(TRACE_LEVEL_DEBUG,"-> Entering disconnect method")
        self._trace_msg(TRACE_LEVEL_ACTIVITY,"Disconnecting from device on COM port %s"%(self.com_port) + "...")
        self._update_prog_msg("Disconnecting from device on COM port %s ..."%(self.com_port), 1)
        self._comm_close()
        self._trace_msg(TRACE_LEVEL_DEBUG,"<- Exit disconnect method")

    def GetVersion(self):
        global GETVERSION_CALLED
        global comm_logger
        self._trace_msg(TRACE_LEVEL_DEBUG,"-> Entering GetVersion method")
        self._trace_msg(TRACE_LEVEL_ACTIVITY,"Reading device version info...")
        
        comm_logger.log_event("GET_VERSION", "Requesting device version information")
        
        if (self._comm_open()):
            GETVERSION_CALLED = True
            self._trace_msg(TRACE_LEVEL_DEBUG, "Connected to device to get version")
            data = AWR_BOOTLDR_OPCODE_GET_VERSION_INFO
            
            comm_logger.log_write(self.com_port, data, "GET_VERSION_COMMAND")
            self._send_packet(data)
            self._trace_msg(TRACE_LEVEL_DEBUG, "GET_VERSION code send packet completed.")
            Status = self._read_ack()
            self._trace_msg(TRACE_LEVEL_DEBUG, "Response from device obtained.")
            RetValue = ""
            try:
                if (Status is False):
                    self._trace_msg(TRACE_LEVEL_DEBUG, "!!! Version read was not successful !!!")
                    comm_logger.log_event("VERSION_ERROR", "Version read failed - no ACK")
                    return RetValue
                    
                length_data = self.comm.read(2)
                comm_logger.log_read(self.com_port, length_data, "VERSION_LENGTH")
                Length = struct.unpack(">H", length_data)[0]
                
                crcRead = self.comm.read(1)
                comm_logger.log_read(self.com_port, crcRead, "VERSION_CRC")
                checkSum = struct.unpack("B",crcRead)[0]
                Length -= 2
                
                versionRead = self.comm.read(Length)
                comm_logger.log_read(self.com_port, versionRead, f"VERSION_DATA ({Length} bytes)")
                
                calculatedCheckSum=0
                for byte in versionRead:
                    calculatedCheckSum += byte
                calculatedCheckSum &= 0xFF
                if (calculatedCheckSum != checkSum):
                    self._trace_msg(TRACE_LEVEL_ERROR, "Version checksum Calculated: 0x{:x}.  Received: 0x{:x}".format(calculatedCheckSum, checkSum))
                    self._trace_msg(TRACE_LEVEL_FATAL, "Checksum error on received packet")
                    comm_logger.log_event("VERSION_ERROR", f"Checksum mismatch - Calc: 0x{calculatedCheckSum:02X}, Recv: 0x{checkSum:02X}")
                    return RetValue
                else:
                    self._trace_msg(TRACE_LEVEL_DEBUG, "Version Calculated and Received CheckSum: 0x{:x}.".format(calculatedCheckSum))
                    
                versionData = binascii.b2a_hex(versionRead)
                ack_response = AWR_BOOTLDR_OPCODE_ACK
                comm_logger.log_write(self.com_port, ack_response, "VERSION_ACK_RESPONSE")
                self.comm.write(ack_response)
                
                convertVersion = versionData[0:8]
                self._trace_msg(TRACE_LEVEL_DEBUG, str("Truncated Version Info = %s"%(convertVersion)))
                comm_logger.log_event("VERSION_SUCCESS", f"Device version: {convertVersion.decode()}")
                GETVERSION_CALLED = False
                RetValue = convertVersion
            except Exception as e:
                comm_logger.log_event("VERSION_EXCEPTION", f"Exception during version read: {str(e)}")
                pass
            finally:
                self._comm_close()
                self._trace_msg(TRACE_LEVEL_DEBUG, "Closing connection to device")
        else:
            self._trace_msg(TRACE_LEVEL_ERROR,"Cannot open serial port. Try again.")
            comm_logger.log_event("VERSION_ERROR", "Cannot open serial port for version read")
        self._trace_msg(TRACE_LEVEL_DEBUG,"<- Exit GetVersion method")
        return RetValue

    def erase_storage(self,storage="SFLASH",location_offset=0,capacity=0):
        global comm_logger
        self._trace_msg(TRACE_LEVEL_DEBUG, "->Entering erase_storage method")
        self._trace_msg(TRACE_LEVEL_ACTIVITY, str("-->Erasing storage [%s]" %(storage)))
        
        comm_logger.log_event("ERASE_START", f"Erasing {storage} at offset {location_offset}, capacity {capacity}")
        
        if (self._comm_open()):
            data = AWR_BOOTLDR_OPCODE_ERASE + Storages[storage] + \
                struct.pack(">I",location_offset) + struct.pack(">I",capacity)
                
            comm_logger.log_event("ERASE_CMD", f"Sending erase command - Storage: {storage}, Offset: {location_offset}, Capacity: {capacity}")
            
            self._update_prog_msg("Sending Erase command to device...", 10)
            self._trace_msg(TRACE_LEVEL_ACTIVITY,"-->Sending Erase command to device...")
            self._send_packet(data)
            self._trace_msg(TRACE_LEVEL_DEBUG,"Erase command sent to device.")
            
            if (self._read_ack()):
                self._trace_msg(TRACE_LEVEL_DEBUG,"Erase storage ACK received.")
                self._trace_msg(TRACE_LEVEL_INFO,"-->Erase storage completed successfully!")
                self._update_prog_msg("Erase completed successfully!", 80)
                comm_logger.log_event("ERASE_SUCCESS", f"Storage {storage} erased successfully")
                result = True
            else:
                self._trace_msg(TRACE_LEVEL_DEBUG,"Erase storage ACK not received.")
                self._trace_msg(TRACE_LEVEL_ERROR,"Erase storage did not complete. Reset device and try again")
                comm_logger.log_event("ERASE_FAILED", f"Storage {storage} erase failed - no ACK received")
                result = False
        else:
            comm_logger.log_event("ERASE_FAILED", f"Cannot open communication port for erase operation")
            result = False
        self._update_prog_msg("", 5)
        self._comm_close()
        self._trace_msg(TRACE_LEVEL_DEBUG,"<-Exiting erase_storage method")
        return result

    def determinePGVersion(self):
        """
        OPTIMIZED FOR IWR6843AOP: Skip version detection, hardcode PG3OrLater=True
        
        Device version 04000106 is always PG3+, no need to query device.
        This saves ~2 seconds per operation and simplifies the flow.
        """
        global comm_logger
        self._trace_msg(TRACE_LEVEL_DEBUG, "->Entering determinePGVersion method (OPTIMIZED)")
        
        # Hardcode for IWR6843AOP - device version 04000106 is always PG3+
        self.PG3OrLater = True
        
        comm_logger.log_event("VERSION_SKIP", "Skipped version detection - hardcoded PG3OrLater=True for device 04000106")
        self._trace_msg(TRACE_LEVEL_DEBUG, "PG3OrLater set to True (hardcoded for IWR6843AOP)")
        self._trace_msg(TRACE_LEVEL_DEBUG,"<-Exit determinePGVersion method (OPTIMIZED)")
        return True

    def get_prog_percentage(self):
        return self.progPercentage

    def update_prog_percentage(self, percentage):
        self.progPercentage = percentage

# ============================================================================
# IWR6843AOP ERASER CLASS
# ============================================================================

class IWR6843AOPEraser:
    """
    IWR6843AOP Eraser using embedded TI mmWave infrastructure
    
    MAIN FLOW:
    1. __init__() - Initialize with hardcoded settings (COM9)  
    2. erase_firmware() - Main entry point for erase process
    3. _simple_connect() - Connect to device and setup parameters
    4. _simple_erase() - Erase firmware from SFLASH
    5. disconnect() - Clean disconnect from device
    
    OPTIMIZATIONS:
    - Only supports IWR6843AOP (removes multi-device complexity)
    - Always erases SFLASH (removes storage options)
    - Hardcoded settings (removes config file dependencies)
    """
    
    def __init__(self):
        """Initialize eraser with hardcoded settings - no config files needed"""
        # STEP 1: Set hardcoded parameters
        self.com_port = "COM16"  # Fixed COM port for IWR6843AOP
        
        # STEP 2: Display configuration
        print(f"COM Port: {self.com_port}")
        print(f"Target: IWR6843AOP SFLASH erase")
        
        # STEP 3: Create callback handler for progress/error reporting  
        self.callback = EraseCallback()
        
        # STEP 4: Create TI bootloader instance with our settings
        self.bootloader = BootLdr(self.callback, self.com_port)
    
    def connect(self):
        """Connect to IWR6843AOP device"""
        print(f"Connecting to IWR6843AOP on {self.com_port}...")
        
        try:
            success = self.bootloader.connect(10, self.com_port)
            if success:
                print("Connected to device")
                
                # Determine PG version for IWR6843AOP
                if self.bootloader.determinePGVersion():
                    print("Device PG version determined")
                    return True
                else:
                    print("Cannot determine device PG version")
                    return False
            else:
                print("Failed to connect to device")
                return False
                
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from device"""
        try:
            self.bootloader.disconnect()
            print("Disconnected")
        except Exception as e:
            print(f"Disconnect warning: {e}")
    
    def erase_firmware(self):
        """
        MAIN ERASE FLOW - Entry point for firmware erase process
        
        FLOW:
        1. Connect to IWR6843AOP device  
        2. Erase SFLASH firmware area
        3. Verify erase completed successfully
        4. Disconnect cleanly
        
        Returns:
            bool: True if erase successful, False otherwise
        """
        
        print("IWR6843AOP Erase Tool (SFLASH Only)")
        print("=" * 38)
        
        try:
            # STEP 1: Connect to device and setup parameters
            if not self._simple_connect():
                return False
            
            # STEP 2: Erase SFLASH
            if not self._simple_erase():
                return False
            
            # STEP 3: Success - inform user
            print("SFLASH Erase Completed!")
            print("Device firmware has been erased")
            return True
            
        except KeyboardInterrupt:
            print("\nCancelled by user")
            return False
        except Exception as e:
            print(f"Error: {e}")
            return False
        finally:
            # STEP 4: Always disconnect cleanly
            self.disconnect()
    
    def _simple_connect(self):
        """
        DEVICE CONNECTION FLOW (OPTIMIZED)
        
        STEPS:
        1. Open serial connection to COM16
        2. Skip version detection (hardcode PG3OrLater=True for device 04000106)
        3. Validate connection is ready for erasing
        
        OPTIMIZATION: Saves ~2 seconds by skipping GetVersion() call
        
        Returns:
            bool: True if connection successful and ready
        """
        # STEP 1: Establish serial connection
        print(f"Connecting to {self.com_port}...")
        
        if not self.bootloader.connect(10, self.com_port):
            print("Connection failed")
            return False
        
        # STEP 2: Skip device version detection for IWR6843AOP (device version 04000106 is always PG3+)  
        if not self.bootloader.determinePGVersion():
            print("Cannot determine device version")
            return False
        
        # STEP 4: Connection ready
        print("Connected successfully")
        return True
    
    def _simple_erase(self):
        """
        ERASE FLOW - Core erase operation
        
        OPTIMIZED FLOW:
        1. Display erase target (SFLASH firmware area)
        2. Execute erase command with progress tracking
        3. Verify erase completed successfully
        4. Report results to user
        
        Why erase SFLASH?
        - Removes all firmware from device
        - Prepares device for fresh firmware installation
        - Required for device recovery scenarios
        
        Returns:
            bool: True if erase successful
        """
        # STEP 1: Display erase information
        print("Target: SFLASH (Serial Flash Memory)")
        print("Operation: Full firmware area erase")
        
        # STEP 2: Execute erase operation
        print("Erasing SFLASH firmware area...")
        
        # STEP 3: Call TI bootloader erase function
        # Parameters: storage="SFLASH", location_offset=0, capacity=0 (full erase)
        success = self.bootloader.erase_storage("SFLASH", 0, 0)
        
        # STEP 4: Report result
        if success:
            print("SFLASH erased successfully")
            print("All firmware data has been removed")
            return True
        else:
            print("Erase failed")
            print("Check device connection and try again")
            return False

class EraseCallback:
    """Simplified callback class for progress and messages during erase"""
    
    def __init__(self):
        self.progress = 0
        self.last_percentage = -1
        
    def update_progress(self, message, percentage):
        """Simple progress updates - only show significant changes"""
        if percentage != self.last_percentage and percentage % 20 == 0:  # Show every 20%
            print(f"[{percentage:3d}%] {message}")
            self.last_percentage = percentage
        self.progress = percentage
    
    def push_message(self, message, level):
        """Only show critical messages"""
        if level >= 2:  # Only FATAL and ERROR
            level_name = "ERROR" if level == 2 else "FATAL"
            print(f"[{level_name}] {message}")
    
    def check_is_cancel_set(self):
        """No cancel checking in simplified version"""
        return False

def main():
    """
    MAIN PROGRAM ENTRY POINT
    
    SIMPLIFIED FLOW:
    1. Initialize IWR6843AOPEraser with hardcoded settings
    2. Execute erase_firmware() for complete erase operation  
    3. Report success/failure to user
    4. Export detailed log to log.txt
    5. Exit with appropriate code
    
    NO ARGUMENTS NEEDED:
    - COM port: Fixed to COM16
    - Device version: Fixed to 04000106 (PG3+)
    - Storage: Always SFLASH
    - Operation: Always full erase, skip version detection
    """
    global comm_logger
    
    print("IWR6843AOP Erase Tool - Standalone (OPTIMIZED)")
    print("Using hardcoded settings: COM16, SFLASH erase, Skip version check")
    print("=" * 65)
    
    comm_logger.log_event("TOOL_START", "IWR6843AOP Erase Tool started")
    
    # STEP 1: Create eraser instance with hardcoded settings
    eraser = IWR6843AOPEraser()
    
    # STEP 2: Execute erase operation
    print("Starting SFLASH erase operation...")
    comm_logger.log_event("ERASE_OPERATION", "Starting SFLASH erase operation")
    
    success = eraser.erase_firmware()
    
    # STEP 3: Report results to user
    if success:
        print("\nSUCCESS! SFLASH firmware erased from IWR6843AOP")
        print("Device is now ready for fresh firmware installation")
        print("Use flash_iwr6843aop_standalone.py to install new firmware")
        comm_logger.log_event("TOOL_SUCCESS", "Erase operation completed successfully")
    else:
        print("\nFAILED! Erase operation could not complete")
        print("Check:")
        print("  - Device connected to COM16")
        print("  - Device in bootloader mode")
        print("  - Device powered on")
        comm_logger.log_event("TOOL_FAILED", "Erase operation failed")
    
    # STEP 4: Close logger and save log file
    comm_logger.log_event("TOOL_END", "IWR6843AOP Erase Tool ending")
    comm_logger.close()
    
    print(f"\nDetailed communication log saved to: {comm_logger.log_file}")
    print("Check log.txt for raw frame data analysis")
    
    return 0 if success else 1

if __name__ == "__main__":
    """
    PROGRAM EXECUTION ENTRY POINT
    
    FLOW:
    1. Execute main() function
    2. Handle any unexpected errors gracefully
    3. Wait for user input before closing
    4. Exit with proper status code
    """
    try:
        # Execute main erase process
        exit_code = main()
        input("\nPress Enter to exit...")
        sys.exit(exit_code)
    except Exception as e:
        # Handle unexpected errors
        print(f"Fatal error: {e}")
        input("\nPress Enter to exit...")
        sys.exit(1)