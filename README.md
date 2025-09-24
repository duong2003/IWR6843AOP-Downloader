# IWR6843AOP Bootloader Protocol Analysis

## Overview

This document analyzes the UART communication protocol used by the IWR6843AOP flash tool to communicate with the Texas Instruments mmWave radar bootloader.

## UART Configuration

- **Baud Rate**: 115200
- **Data Bits**: 8
- **Stop Bits**: 1
- **Parity**: None
- **Flow Control**: None
- **Timeout**: 10 seconds

## Packet Structure

### Outgoing Packets (Host to Device)

All packets sent to the device follow this structure:

```
[SYNC][LENGTH][CHECKSUM][PAYLOAD]
```

#### Field Descriptions

| Field | Size | Value | Description |
|-------|------|-------|-------------|
| SYNC | 1 byte | 0xAA | Synchronization pattern |
| LENGTH | 2 bytes | Big-endian | Payload size + 2 |
| CHECKSUM | 1 byte | Sum & 0xFF | Simple sum of payload bytes |
| PAYLOAD | Variable | - | Command data |

#### Checksum Calculation

```python
def calculate_checksum(payload):
    checksum = 0
    for byte in payload:
        checksum += byte
    return checksum & 0xFF
```

#### Length Calculation

```python
def calculate_length(payload):
    return len(payload) + 2  # Payload size + 2
```

### Incoming Packets (Device to Host)

Response packets from the device:

```
[LENGTH][CHECKSUM][PAYLOAD]
```

| Field | Size | Value | Description |
|-------|------|-------|-------------|
| LENGTH | 2 bytes | Big-endian | Payload size + 2 |
| CHECKSUM | 1 byte | Sum & 0xFF | Simple sum of payload bytes |
| PAYLOAD | Variable | - | Response data |

## Command Opcodes

### Bootloader Commands

| Command | Opcode | Description |
|---------|--------|-------------|
| PING | 0x20 | Test communication |
| START_DOWNLOAD | 0x21 | Begin file download |
| FILE_CLOSE | 0x22 | End file download |
| GET_LAST_STATUS | 0x23 | Get operation status |
| SEND_DATA | 0x24 | Send data chunk |
| SEND_DATA_RAM | 0x26 | Send data to RAM |
| DISCONNECT | 0x27 | Close connection |
| ERASE | 0x28 | Erase storage |
| FILE_ERASE | 0x2E | Erase specific file |
| GET_VERSION_INFO | 0x2F | Get device version |

### Response Codes

| Response | Value | Description |
|----------|-------|-------------|
| ACK | 0xCC | Command acknowledged |
| NACK | 0x33 | Command rejected |
| SUCCESS | 0x40 | Operation successful |
| IN_PROGRESS | 0x4B | Operation in progress |

## Communication Flow

### 1. Connection Establishment

```
Host -> Device: PING command
Device -> Host: ACK/NACK response
```

### 2. File Download Flow

#### Step 1: Start Download
```
Host -> Device: START_DOWNLOAD + file_size + storage_type + file_type + mirror_flag
Device -> Host: ACK/NACK
Host -> Device: GET_LAST_STATUS
Device -> Host: Status response
```

**START_DOWNLOAD Payload Structure:**
```
[OPCODE][FILE_SIZE][STORAGE][FILE_TYPE][MIRROR]
1 byte   4 bytes    4 bytes  4 bytes   4 bytes
```

#### Step 2: Send Data Chunks
```
Loop for each chunk:
    Host -> Device: SEND_DATA + chunk_data
    Device -> Host: ACK/NACK
    Host -> Device: GET_LAST_STATUS  
    Device -> Host: Status response
```

**SEND_DATA Payload Structure:**
```
[OPCODE][CHUNK_DATA]
1 byte   240 bytes (max)
```

#### Step 3: Close File
```
Host -> Device: FILE_CLOSE + file_type
Device -> Host: ACK/NACK
Host -> Device: GET_LAST_STATUS
Device -> Host: Status response
```

### 3. Storage Erase Flow

```
Host -> Device: ERASE + storage_type + offset + capacity
Device -> Host: ACK/NACK (operation may take several seconds)
```

**ERASE Payload Structure:**
```
[OPCODE][STORAGE][OFFSET][CAPACITY]
1 byte   4 bytes  4 bytes 4 bytes
```

## File Format Analysis

### META_IMAGE1 Binary Structure

The IWR6843AOP uses META_IMAGE1 format for firmware files.

#### File Header

```
[MAGIC][METADATA][PAYLOAD]
4 bytes Variable  Variable
```

**Magic Number**: `0x5254534D` ("MSTR" in big-endian)

#### Header Validation

```python
def validate_file_header(filename):
    with open(filename, 'rb') as f:
        header_bytes = f.read(4)
        if sys.byteorder == 'little':
            header = struct.unpack("<L", header_bytes)[0]
        else:
            header = struct.unpack(">L", header_bytes)[0]
        
        # Check if header matches META_IMAGE1 magic
        return header == 0x5254534D
```

### Chunking Strategy

Files are transmitted in chunks for reliable transfer:

- **Chunk Size**: 240 bytes
- **Progress Tracking**: Every N chunks (calculated based on file size)
- **Error Handling**: Each chunk requires ACK before proceeding

```python
def calculate_progress_steps(file_size):
    total_chunks = file_size // 240 + 1
    return max(1, total_chunks // 10)  # 10 progress updates
```

## Storage Types

| Storage | Value | Description |
|---------|-------|-------------|
| SDRAM | 0 | System RAM |
| FLASH | 1 | Internal Flash |
| SFLASH | 2 | Serial Flash (primary firmware storage) |
| EEPROM | 3 | EEPROM |
| SRAM | 4 | Static RAM |

## File Types

| File Type | Value | Description |
|-----------|-------|-------------|
| META_IMAGE1 | 4 | Firmware image for IWR6843AOP |

## Error Handling

### Timeout Handling
- **Connection Timeout**: 10 seconds
- **Response Timeout**: Wait for ACK/NACK with retry logic
- **Cancel Detection**: Check for user cancellation between chunks

### Checksum Verification
Both outgoing and incoming packets use simple sum checksums:

```python
def verify_checksum(payload, received_checksum):
    calculated = sum(payload) & 0xFF
    return calculated == received_checksum
```

### Retry Logic
```python
def read_ack_with_retry(self, max_retries=10):
    for attempt in range(max_retries):
        response = self.comm.read(1)
        if response in [ACK, NACK]:
            return response == ACK
        time.sleep(0.1)
    return False
```

## Practical Examples

### Send PING Command

```python
# Construct packet
opcode = struct.pack("B", 0x20)  # PING
length = struct.pack(">H", 3)    # 1 byte payload + 2
checksum = struct.pack("B", 0x20 & 0xFF)
sync = struct.pack("B", 0xAA)

# Send packet
packet = sync + length + checksum + opcode
comm.write(packet)
```

### Send Data Chunk

```python
# Prepare chunk
chunk_data = file.read(240)
opcode = struct.pack("B", 0x24)  # SEND_DATA
payload = opcode + chunk_data

# Calculate values
length = len(payload) + 2
checksum = sum(payload) & 0xFF

# Build packet
packet = struct.pack("B", 0xAA)           # SYNC
packet += struct.pack(">H", length)       # LENGTH
packet += struct.pack("B", checksum)      # CHECKSUM
packet += payload                         # PAYLOAD

comm.write(packet)
```

### Parse Response

```python
# Read response header
header = comm.read(3)
length, checksum = struct.unpack(">HB", header)
length -= 2  # Remove header size

# Read payload
payload = comm.read(length)

# Verify checksum
calculated_checksum = sum(payload) & 0xFF
if calculated_checksum != checksum:
    raise ChecksumError("Invalid checksum")

# Send ACK
comm.write(struct.pack("B", 0xCC))
```

## Performance Considerations

### Optimization Strategies
1. **Skip Version Detection**: Hardcode PG3+ settings for IWR6843AOP
2. **Fixed Parameters**: Use known device characteristics
3. **Efficient Progress**: Limit progress updates to prevent spam
4. **Chunk Size**: 240 bytes optimal for UART reliability

### Timing Analysis
- **Connection**: ~1-2 seconds
- **Erase**: ~2-3 seconds  
- **Flash Rate**: ~8KB/second (at 115200 baud with protocol overhead)
- **Total Time**: Varies by file size (typical 1MB firmware takes ~2-3 minutes)

This protocol analysis provides the foundation for implementing compatible bootloader tools or debugging communication issues with IWR6843AOP devices.
