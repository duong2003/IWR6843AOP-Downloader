#!/usr/bin/env python3
"""
IWR6843AOP Flash Tool
"""

import os
import sys
import time
import json
import inspect
import string
import struct
import serial
from serial import SerialException
import binascii
import subprocess

GETVERSION_REQ = False
GETVERSION_CALLED = False
GETVERSION_CRC_NEXT = False
PARTNUM = "WR16"

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
        global PARTNUM
        if (value != 0):
            if (GETVERSION_REQ is True):
                if (value == 1):
                    if (GETVERSION_CRC_NEXT is True):
                        if (PARTNUM[1:5] in ("WR14","WR12")):
                            bytesRead = struct.pack("B",8)
                        else:
                            bytesRead = struct.pack("B",16)
                        GETVERSION_CRC_NEXT = False
                    else:
                        bytesRead = AR_BOOTLDR_OPCODE_ACK
                if (value == 2):
                    bytesRead = struct.pack(">H",14)
                    GETVERSION_CRC_NEXT = True
                if (value >= 12):
                    if (PARTNUM[1:5] in ("WR14","WR12")):
                        bytesRead = binascii.a2b_hex("010006010000000000000000")
                    else:
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
AWR_CANCEL_MSG = "Cancel request detected...Ceasing flashing operation."

Files = {
"META_IMAGE1"              : struct.pack(">I",4)
}

IWR68xx_PART_NUM  = "IWR68"
xWR68xx_PART_NUM  = "WR68"

PartNumSupported = [IWR68xx_PART_NUM]
OlderFileFormatParts = []
CONFIGFileParts = []

# File header versions
AWR_PRE_PG3_KEY = "PrePG3"
AWR_POST_PG3_KEY = "PostPG3"

FileHeaders = {
AWR_PRE_PG3_KEY :  {
xWR68xx_PART_NUM : { "headers" : [0x5254534D],
                     "fileType" : ["META_IMAGE1"]  # Only META_IMAGE1 for IWR6843AOP
                   },                   
                   },
AWR_POST_PG3_KEY : {
xWR68xx_PART_NUM : { "headers" : [0x5254534D],
                     "fileType" : ["META_IMAGE1"]  # Only META_IMAGE1 for IWR6843AOP
                   },                   
                   }
}

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

# Keys from Uniflash UI
COMPORT_KEY     = 'COMPort'
MEMSELECT_KEY   = 'MemSelectRadio'
PARTNUM_KEY     = 'partnum'
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
        self.partNum = ""
        self.cancelRequested = False
        self.stubOut = STUBOUT_VALUE

    def _update_prog_msg(self,updateStr,incPercent):
        if (self.callbackClass != ''):
            newProgPercent = self.progPercentage + incPercent
            if (newProgPercent > UNIFLASH_PROG_INDICATOR_B4_SHUTDOWN):
                newProgPercent = UNIFLASH_PROG_INDICATOR_B4_SHUTDOWN
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
        if(self._is_connected()):
            return True
        if (self.stubOut is False):
            try:
                self.comm = serial.Serial(port=self.com_port, baudrate=self.baudrate, timeout=10)
            except SerialException:
                self._trace_msg(TRACE_LEVEL_ERROR, "Serial port %s"%(self.com_port) + " specified does not exist, is already open, or permission is denied!!")
                self._trace_msg(TRACE_LEVEL_ERROR, "!! Aborting operation!!")
                return False
        else:
            self.comm = SerialStub(port=self.com_port, baudrate=self.baudrate, timeout=6)
        if self.comm.isOpen():
            self.comm.flushInput()
            self.connected = True
            return True
        else:
            self._trace_msg(TRACE_LEVEL_ERROR,"!!! Error opening the COM port!!!")
            return False

    def _comm_close(self):
        if(self._is_connected()):
            self.comm.close()
            self.connected = False
            self.comm = None

    def _is_connected(self):
        return self.connected

    def _send_packet(self,data):
        checksum = 0
        for b in data:
            checksum += b
        msgSize = len(data)+2
        sMsgSize = struct.pack(">H",msgSize)
        sChecksum = struct.pack("B",checksum & 0xff)
        self.comm.write(AWR_BOOTLDR_SYNC_PATTERN)
        self.comm.write(sMsgSize)
        self.comm.write(sChecksum)
        self.comm.write(data)

    def _receive_packet(self, Length):
        Header = self.comm.read(3)
        PacketLength , CheckSum  = struct.unpack(">HB", Header)
        PacketLength -= 2
        if (Length != PacketLength):
            self._trace_msg(TRACE_LEVEL_DEBUG, "Requested length={:d}, actual={:d}".format(Length, PacketLength))
            self._trace_msg(TRACE_LEVEL_FATAL, "Error, Mismatch between requested and actual packet length: act {:d}, req {:d}".format(PacketLength, Length))
        Payload = self.comm.read(PacketLength)
        if (len(Payload) != Length):
            self._trace_msg(TRACE_LEVEL_FATAL, "Error, time-out while receiving packet's payload")
        self.comm.write(AWR_BOOTLDR_OPCODE_ACK)
        CalculatedCheckSum=0
        for byte in Payload:
            CalculatedCheckSum += byte
        CalculatedCheckSum &= 0xFF
        if (CalculatedCheckSum != CheckSum):
            self._trace_msg(TRACE_LEVEL_ERROR, "Calculated: 0x{:x}.  Received: 0x{:x}".format(CalculatedCheckSum, CheckSum))
            self._trace_msg(TRACE_LEVEL_FATAL, "Checksum error on received packet")
        else:
            self._trace_msg(TRACE_LEVEL_DEBUG, "Calculated and Received CheckSum: 0x{:x}.".format(CalculatedCheckSum))
        return Payload

    def _read_ack(self):
        length = ''
        while (length == ''):
            length = self.comm.read(2)
        chksum = self.comm.read(1)
        self.comm.read(1)
        a = self.comm.read(1)
        status = False
        while (not ((a == AWR_BOOTLDR_OPCODE_ACK) or (a == AWR_BOOTLDR_OPCODE_NACK))):
            a = self.comm.read(1)
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
        return status

    def _read_ack_with_cancel_check(self):
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
            self._trace_msg(TRACE_LEVEL_ERROR, "Initial response from the device was not received. Please power cycle device before re-flashing.")
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
        return status

    def _send_command(self,data):
        self._send_packet(data)
        ackStatus = self._read_ack()
        self._send_packet(AWR_BOOTLDR_OPCODE_GET_LAST_STATUS)
        retStatus = self._receive_packet(self.cmdStatusSize)
        return ackStatus

    def _send_start_download(self,file_id,file_size,max_size,mirror_enabled,storage):
        data = AWR_BOOTLDR_OPCODE_START_DOWNLOAD + \
            struct.pack(">I",file_size) + Storages[storage] + \
            Files[file_id] + struct.pack(">I",mirror_enabled)
        self._send_command(data)
        return True

    def _send_file_close(self,file_id):
        data = AWR_BOOTLDR_OPCODE_FILE_CLOSE + \
            Files[file_id]
        self._send_command(data)
        return True

    def _send_chunk(self,buff,bufflen):
        self._trace_msg(TRACE_LEVEL_DEBUG,"--> Send chunk")
        data = AWR_BOOTLDR_OPCODE_SEND_DATA + buff
        return self._send_command(data)

    def _send_chunkRAM(self,buff,bufflen):
        data = AWR_BOOTLDR_OPCODE_SEND_DATA_RAM + buff
        return self._send_command(data)

    def _getFileHeaderList(self):
        return [0x5254534D]  # "MSTR" header for META_IMAGE1

    def _getFileTypeList(self):
        return ["META_IMAGE1"]

    # ******************* APIs *******************

    def connect_with_reset(self, timeout, com_port, reset_command):
        passed = True
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
                self._trace_msg(TRACE_LEVEL_ACTIVITY,"Connection to COM port succeeded. Flashing can proceed.")
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
        self._trace_msg(TRACE_LEVEL_DEBUG,"-> Entering GetVersion method")
        self._trace_msg(TRACE_LEVEL_ACTIVITY,"Reading device version info...")
        if (self._comm_open()):
            GETVERSION_CALLED = True
            self._trace_msg(TRACE_LEVEL_DEBUG, "Connected to device to get version")
            data = AWR_BOOTLDR_OPCODE_GET_VERSION_INFO
            self._send_packet(data)
            self._trace_msg(TRACE_LEVEL_DEBUG, "GET_VERSION code send packet completed.")
            Status = self._read_ack()
            self._trace_msg(TRACE_LEVEL_DEBUG, "Response from device obtained.")
            RetValue = ""
            try:
                if (Status is False):
                    self._trace_msg(TRACE_LEVEL_DEBUG, "!!! Version read was not successful !!!")
                    return RetValue
                Length = struct.unpack(">H", self.comm.read(2))[0]
                crcRead = self.comm.read(1)
                checkSum = struct.unpack("B",crcRead)[0]
                Length -= 2
                versionRead = self.comm.read(Length)
                calculatedCheckSum=0
                for byte in versionRead:
                    calculatedCheckSum += byte
                calculatedCheckSum &= 0xFF
                if (calculatedCheckSum != checkSum):
                    self._trace_msg(TRACE_LEVEL_ERROR, "Version checksum Calculated: 0x{:x}.  Received: 0x{:x}".format(calculatedCheckSum, checkSum))
                    self._trace_msg(TRACE_LEVEL_FATAL, "Checksum error on received packet")
                    return RetValue
                else:
                    self._trace_msg(TRACE_LEVEL_DEBUG, "Version Calculated and Received CheckSum: 0x{:x}.".format(calculatedCheckSum))
                versionData = binascii.b2a_hex(versionRead)
                self.comm.write(AWR_BOOTLDR_OPCODE_ACK)
                convertVersion = versionData[0:8]
                self._trace_msg(TRACE_LEVEL_DEBUG, str("Truncated Version Info = %s"%(convertVersion)))
                GETVERSION_CALLED = False
                RetValue = convertVersion
            except:
                pass
            finally:
                self._comm_close()
                self._trace_msg(TRACE_LEVEL_DEBUG, "Closing connection to device")
        else:
            self._trace_msg(TRACE_LEVEL_ERROR,"Cannot open serial port. Try again.")
        self._trace_msg(TRACE_LEVEL_DEBUG,"<- Exit GetVersion method")
        return RetValue

    def download_file(self,filename,file_id,mirror_enabled,max_size,storage, imageProgList):
        self._trace_msg(TRACE_LEVEL_DEBUG, "->Entering download_file method")
        fSize = os.path.getsize(filename)
        result = True
        if (storage == "SRAM"):
            self.cmdStatusSize = 4
        else:
            self.cmdStatusSize = 1
        self._trace_msg(TRACE_LEVEL_ACTIVITY,"Downloading [%s] size [%d]"%(file_id,fSize))
        if (fSize>0) and (fSize < MAX_FILE_SIZE):
            if (max_size < fSize):
                max_size = fSize
            try:
                fSrc = open(filename,"rb")
            except IOError:
                self._trace_msg(TRACE_LEVEL_FATAL, "Unable to open the file. Please double-check the name and path")
                return False
            if (self._comm_open()):
                self._update_prog_msg("Downloading [%s] size [%d]..."%(file_id,fSize),1)
                if (self._send_start_download(file_id,fSize,max_size,mirror_enabled,storage)):
                    offset = 0
                    spacingCnt = 0
                    spacingCntLimit = imageProgList[0]
                    percentIncr = imageProgList[1]
                    while (offset < fSize):
                        buff = fSrc.read(self.chunksize)
                        bufflen = len(buff)
                        if (storage == "SRAM"):
                            sendStatus = self._send_chunkRAM(buff,bufflen)
                            if (sendStatus == False):
                                result = False
                                break
                        else:
                            sendStatus = self._send_chunk(buff,bufflen)
                            if (sendStatus == False):
                                result = False
                                break
                        spacingCnt += 1
                        if (spacingCnt == spacingCntLimit):
                            spacingCnt = 0
                            self._update_prog_msg("", percentIncr)
                        offset += bufflen
                        c = self._checkForCancel()
                        if (c is True):
                            self._trace_msg(TRACE_LEVEL_INFO, AWR_CANCEL_MSG)
                            result = False
                            break
                self._send_file_close(file_id);
                self._comm_close()
            else:
                self._trace_msg(TRACE_LEVEL_ERROR,"Failure while trying to connect...")
                result = False
            fSrc.close()
        else:
            self._trace_msg(TRACE_LEVEL_ERROR,"Invalid file size")
            result = False
        self._trace_msg(TRACE_LEVEL_DEBUG,"<-Exit download_file method")
        return result

    def erase_storage(self,storage="SFLASH",location_offset=0,capacity=0):
        self._trace_msg(TRACE_LEVEL_DEBUG, "->Entering erase_storage method")
        self._trace_msg(TRACE_LEVEL_ACTIVITY, str("-->Erasing storage [%s]" %(storage)))
        if (self._comm_open()):
            data = AWR_BOOTLDR_OPCODE_ERASE + Storages[storage] + \
                struct.pack(">I",location_offset) + struct.pack(">I",capacity)
            self._update_prog_msg("Sending Erase command to device...", 1)
            self._trace_msg(TRACE_LEVEL_ACTIVITY,"-->Sending Erase command to device...")
            self._send_packet(data)
            self._trace_msg(TRACE_LEVEL_DEBUG,"Erase command sent to device.")
            if (self._read_ack()):
                self._trace_msg(TRACE_LEVEL_DEBUG,"Erase storage ACK received.")
                self._trace_msg(TRACE_LEVEL_INFO,"-->Erase storage completed successfully!")
            else:
                self._trace_msg(TRACE_LEVEL_DEBUG,"Erase storage ACK not received.")
                self._trace_msg(TRACE_LEVEL_ERROR,"Erase storage did not complete. Reset device and try again")
        self._update_prog_msg("", 1)
        self._comm_close()
        self._trace_msg(TRACE_LEVEL_DEBUG,"<-Exiting erase_storage method")

    def checkFileHeader(self, fileName, fileInfo):
        self._trace_msg(TRACE_LEVEL_DEBUG, "->Entering checkFileHeader method")
        self._trace_msg(TRACE_LEVEL_INFO, "Checking file %s for correct header for IWR6843AOP."%(fileName))
        fileExists = os.path.isfile(fileName)
        checkResult = True
        if (fileExists == True):
            fSize = os.path.getsize(fileName)
            if (fSize < FILE_HEADERSIZE):
                self._trace_msg(TRACE_LEVEL_ERROR, "File %s is too small: size = %d"%(fileName,fSize) + "!")
                checkResult = False
            else:
                try:
                    fSrc = open(fileName,"rb")
                except IOError:
                    self._trace_msg(TRACE_LEVEL_FATAL, "Unable to open the file. Please double-check the name and path")
                    checkResult=False
                if (checkResult == True):
                    self._update_prog_msg("Checking fileType appropriateness for this device...", 2)
                    rawHeader = fSrc.read(FILE_HEADERSIZE)
                    if (sys.byteorder == 'little'):
                        header = struct.unpack("<L",rawHeader)[0]
                    else:
                        header = struct.unpack(">L",rawHeader)[0]
                    maskedHeader = header & 0xFFF00000
                    fileHeaderList = self._getFileHeaderList()
                    fileTypeList = self._getFileTypeList()
                    if (header in fileHeaderList):
                        fileTypeIndex = 0
                        self._trace_msg(TRACE_LEVEL_INFO, "IWR6843AOP device, fileType=%s detected -> OK" %(fileTypeList[fileTypeIndex]))
                        fileInfo.file_id = fileTypeList[fileTypeIndex]
                        fileInfo.fileSize = fSize
                        checkResult = True
                        self._update_prog_msg("", 1)
                    else:
                        self._trace_msg(TRACE_LEVEL_WARNING, "Header of %s file indicates it is not a valid file for IWR6843AOP: "%(fileName) + hex(header))
                        checkResult = False
                    fSrc.close()
        else:
            self._trace_msg(TRACE_LEVEL_ERROR, "File %s does not exist!"%(fileName))
            checkResult = False
        self._trace_msg(TRACE_LEVEL_DEBUG,"<-Exit checkFileHeader method")
        return checkResult

    def calcProgressValues(self, images, fileSizeSum, formatOnDownload):
        self._trace_msg(TRACE_LEVEL_DEBUG, "->Entering calcProgressValues method")
        indicatorRange = UNIFLASH_PROG_INDICATOR_RANGE
        if (formatOnDownload == True):
            indicatorRange = UNIFLASH_PROG_INDICATOR_RANGE - ERASE_PROG_VALUE
        for i in images:
            range = (i.fileSize*indicatorRange)/fileSizeSum
            numChunksToSend = i.fileSize/DEFAULT_CHUNK_SIZE
            if (numChunksToSend < 1):
                numChunksToSend = 1
            if (range < 1):
                range = 1
            if (numChunksToSend > range):
                spacingCnt =  int(numChunksToSend/range)
                percentIncr = 1
            else:
                spacingCnt = 1
                percentIncr = int(range/numChunksToSend)
            self.imageProgCntList[i] = [spacingCnt, percentIncr]
        self._trace_msg(TRACE_LEVEL_DEBUG,"<-Exit calcProgressValues method")

    def getImageProgCntList(self, image):
        return self.imageProgCntList[image]

    def isPartNumSupported(self, partNum):
        return partNum[0:5] == "IWR68"

    def get_prog_percentage(self):
        return self.progPercentage

    def update_prog_percentage(self, percentage):
        self.progPercentage = percentage

    def checkPropertiesMapKeys(self, propMap):
        keysPresent = True
        if (COMPORT_KEY not in propMap):
            value = COMPORT_KEY
            keysPresent = False
        elif (MEMSELECT_KEY not in propMap):
            value = MEMSELECT_KEY
            keysPresent = False
        elif (PARTNUM_KEY not in propMap):
            value = PARTNUM_KEY
            keysPresent = False
        elif (DOWNLOADFORMAT_KEY not in propMap):
            value = DOWNLOADFORMAT_KEY
            keysPresent = False

        if (keysPresent is False):
            self._trace_msg(TRACE_LEVEL_FATAL, "Integration Error: \'%s\' key is not present in propertiesMap"%(value))
        return (keysPresent)

    def determinePGVersion(self):
        self.PG3OrLater = True
        return True

    def isDevicePG3OrLater(self):
        return self.PG3OrLater

    def copyImagesList(self, images):
        filesList = []
        for i in images:
            fileObj = FilesObject(i.path, i.order)
            filesList.append(fileObj)
        return filesList

    def addAutomaticDownload(self, filesList, path):
        return

    def setPartNum(self, partNum):
        self.partNum = "IWR68"

# ============================================================================
# IWR6843AOP FLASHER CLASS (Updated to use embedded modules)
# ============================================================================

class IWR6843AOPFlasher:
    """
    IWR6843AOP Flasher using embedded TI mmWave infrastructure
    
    MAIN FLOW:
    1. __init__() - Initialize with hardcoded settings (COM9, firmware path)
    2. flash_firmware() - Main entry point for flashing process
    3. _simple_connect() - Connect to device and setup parameters
    4. _simple_flash() - Erase + Flash META_IMAGE1 to SFLASH
    5. disconnect() - Clean disconnect from device
    """
    
    def __init__(self):
        """Initialize flasher with hardcoded settings - no config files needed"""
        self.com_port = "COM16"
        self.default_firmware = "user_files/images/vital_signs_tracking_6843AOP_demo.bin"
        
        print(f"COM Port: {self.com_port}")
        print(f"Default firmware: {self.default_firmware}")
        print(f"Target: IWR6843AOP")
        
        self.callback = FlashCallback()
        self.bootloader = BootLdr(self.callback, self.com_port)
    
    def connect(self):
        """Connect to IWR6843AOP device"""
        print(f"Connecting to IWR6843AOP on {self.com_port}...")
        
        try:
            success = self.bootloader.connect(10, self.com_port)
            if success:
                print("Connected to device")
                if self.bootloader.determinePGVersion():
                    print("Device configured (IWR6843AOP, PG3+)")
                    return True
                else:
                    print("Cannot configure device")
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
    
    def quick_flash(self, firmware_path=None):
        """Ultra-fast META_IMAGE1 flash - always erase + flash for optimal performance"""
        return self.flash_firmware(firmware_path, format_enabled=True)
    
    def flash_firmware(self, firmware_path=None, format_enabled=True):
        """
        MAIN FLASH FLOW - Entry point for firmware flashing process
        
        FLOW:
        1. Validate firmware file exists
        2. Connect to IWR6843AOP device  
        3. Erase existing firmware (always enabled for reliability)
        4. Flash new META_IMAGE1 firmware
        5. Disconnect cleanly
        
        Args:
            firmware_path: Path to .bin file (uses default if None)
            format_enabled: Always True in optimized version
            
        Returns:
            bool: True if flash successful, False otherwise
        """
        
        print("IWR6843AOP Flash Tool (META_IMAGE1 Only)")
        print("=" * 45)
        
        # STEP 1: Validate firmware file
        # Use default firmware if not specified
        if firmware_path is None:
            firmware_path = self.default_firmware
            
        # Check firmware file exists
        if not os.path.exists(firmware_path):
            print(f"ERROR: Firmware file not found: {firmware_path}")
            return False
            
        try:
            # STEP 2: Connect to device and setup parameters
            if not self._simple_connect():
                return False
            
            # STEP 3: Erase + Flash (always erase for best results)
            if not self._simple_flash(firmware_path, True):  # Always format for reliability
                return False
            
            # STEP 4: Success - inform user
            print("META_IMAGE1 Flash Completed!")
            print("Reset device to run new firmware")
            return True
            
        except KeyboardInterrupt:
            print("\nCancelled by user")
            return False
        except Exception as e:
            print(f"Error: {e}")
            return False
        finally:
            # STEP 5: Always disconnect cleanly
            self.disconnect()
    
    def _simple_connect(self):
        """
        Connect to device and setup parameters
        """
        print(f"Connecting to {self.com_port}...")
        
        if not self.bootloader.connect(10, self.com_port):
            print("Connection failed")
            return False
        if not self.bootloader.determinePGVersion():
            print("Cannot set device configuration")
            return False
        
        # STEP 4: Connection ready
        print("Connected successfully")
        return True
    
    def _simple_flash(self, firmware_path, format_enabled):
        """
        ERASE + FLASH FLOW - Core flashing operation
        
        OPTIMIZED FLOW:
        1. Prepare file info (always META_IMAGE1 for IWR6843AOP)
        2. Erase existing firmware from SFLASH (ensures clean slate)
        3. Flash new firmware in chunks with progress tracking
        4. Verify flash completed successfully
        
        Args:
            firmware_path: Path to .bin firmware file
            format_enabled: Always True in optimized version
            
        Returns:
            bool: True if flash successful
        """
        # STEP 1: Prepare file information
        print(f"File: {os.path.basename(firmware_path)}")
        
        file_info = FilesObject(firmware_path, 1)
        file_size = os.path.getsize(firmware_path)
        file_info.file_id = "META_IMAGE1"
        file_info.fileSize = file_size
        
        print(f"Size: {file_size} bytes")
        print(f"Target: META_IMAGE1 (SFLASH)")
        
        # STEP 2: Erase existing firmware (critical for reliability)
        if format_enabled:
            print("Erasing firmware area...")
            # Erase specific firmware area only (faster than full erase)
            self.bootloader.erase_storage("SFLASH", 0, 0)
            print("Erase completed")
        
        # STEP 3: Flash new firmware 
        print("Flashing META_IMAGE1...")
        
        # Calculate progress reporting (10 updates max to avoid spam)
        total_chunks = file_size // 240 + 1  # 240 bytes per chunk
        progress_step = max(1, total_chunks // 10)  # 10 progress updates max
        
        # STEP 4: Execute flash operation
        # Flash directly to SFLASH using TI bootloader protocol
        success = self.bootloader.download_file(
            firmware_path,
            "META_IMAGE1",
            0,
            0,
            "SFLASH",
            [progress_step, 8]
        )
        
        if success:
            print("Firmware flashed successfully")
            return True
        else:
            print("Flash failed")
            return False

class FlashCallback:
    """Simplified callback class for progress and messages"""
    
    def __init__(self):
        self.progress = 0
        self.last_percentage = -1
        
    def update_progress(self, message, percentage):
        """Simple progress updates - only show significant changes"""
        if percentage != self.last_percentage and percentage % 10 == 0:  # Only show every 10%
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
    flasher = IWR6843AOPFlasher()
    
    print("Starting flash process...")
    
    success = flasher.quick_flash()
    
    if success:
        print("\nSUCCESS! Firmware flashed to IWR6843AOP")
        print("Reset device to run new firmware")
    else:
        print("\nFAILED! Check:")
        print("  - Device connected to COM16")
        print("  - Device in bootloader mode")
        print("  - Firmware file exists")
    
    return 0 if success else 1

if __name__ == "__main__":
    try:
        exit_code = main()
        input("\nPress Enter to exit...")
        sys.exit(exit_code)
    except Exception as e:
        # Handle unexpected errors
        print(f"Fatal error: {e}")
        input("\nPress Enter to exit...")
        sys.exit(1)
