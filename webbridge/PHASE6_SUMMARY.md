# Phase 6: Control Operations - Implementation Summary

## Overview
Phase 6 implements remote ECU control capabilities allowing users to manage log levels, verbose modes, and other ECU parameters through the web UI without requiring command-line tools.

## Architecture

### Backend Components

#### 1. Control Message Builder (`app/ingestion/control_messages.py`)
Constructs DLT control messages for sending to remote ECUs:
- **SET_LOG_LEVEL** (0x01): Set minimum log level for APID/CTID
- **SET_VERBOSE_MODE** (0x1A): Enable/disable verbose output for APID/CTID
- **GET_LOG_INFO** (0x03): Query current log level settings
- **GET_SOFTWARE_VERSION** (0x23): Query ECU software version

**Key Function Signature:**
```python
def build_set_log_level_request(apid: str, ctid: str, log_level: int) -> bytes
def build_set_verbose_mode_request(apid: str, ctid: str, verbose: bool) -> bytes
```

**Message Format:** Non-verbose DLT control messages (HTYP=0x3D)
- HTYP: 0x3D (STD|WEID|WSID|WTMS|UEH flags set, non-verbose)
- MCNT: Message counter
- LENGTH: Message length (2 bytes, big-endian)
- ECU ID, Session ID, Timestamp (optional fields per HTYP)
- Extended Header: Message type control (0x2x), Service ID
- Payload: Control data (service-specific format)

#### 2. Control Operation Models (`app/models.py`)
Pydantic request/response models for type validation:
```python
class SetLogLevelRequest(BaseModel):
    apid: str
    ctid: str
    log_level: Literal[1, 2, 3, 4, 5, 6]

class SetVerboseModeRequest(BaseModel):
    apid: str
    ctid: str
    verbose: bool

class ControlOperationResponse(BaseModel):
    session_id: str
    status: str
    message: str
    operation: str
```

#### 3. REST Endpoints (`app/main.py`)
Three new endpoints for control operations:

**POST /sessions/{session_id}/control/set-log-level**
- Sends SET_LOG_LEVEL control message to ECU
- Validates: session connected, transport is TCP, log_level in range 1-6
- Returns: ControlOperationResponse with status

**POST /sessions/{session_id}/control/set-verbose-mode**
- Sends SET_VERBOSE_MODE control message to ECU
- Validates: session connected, transport is TCP
- Returns: ControlOperationResponse with status

**GET /sessions/{session_id}/control/supported-operations**
- Returns list of supported control operations for session's transport type
- TCP: All operations (SET_LOG_LEVEL, SET_VERBOSE_MODE, GET_LOG_INFO, GET_SOFTWARE_VERSION)
- UDP: Empty list (no control support for UDP)

#### 4. TCP Client Integration (`app/ingestion/tcp_client.py`)
Enhanced to support sending control messages:
- Added `_writer: asyncio.StreamWriter` to store active TCP connection
- Added `_writer_lock: asyncio.Lock()` for thread-safe access
- Method `async _send_control_message(message: bytes)` sends control data to ECU
- Integration: Called by REST endpoints when user sends control operation

### Frontend Components

#### Control Operations UI Panel
**Location:** Message detail drawer (opens when message selected)

**Visibility Rules:**
- Shown only when:
  - Message is selected
  - Session is connected
  - Transport is TCP (not UDP)

**UI Elements:**
1. Log Level Control:
   - Input field: number 1-6
   - Button: "Set Log Level"
   - Action: Sends POST to `/control/set-log-level`

2. Verbose Mode Control:
   - Checkbox: Enable/disable
   - Button: "Apply"
   - Action: Sends POST to `/control/set-verbose-mode`

3. Status Display:
   - Feedback area for operation results
   - Shows: Success message or error description
   - Auto-updates after each operation

#### JavaScript Functions

**`sendControlSetLogLevel()`**
- Extracts APID/CTID from selected message
- Reads log level from input field (validates 1-6)
- POSTs to `/sessions/{id}/control/set-log-level`
- Displays response status in UI

**`sendControlSetVerboseMode()`**
- Extracts APID/CTID from selected message
- Reads verbose flag from checkbox
- POSTs to `/sessions/{id}/control/set-verbose-mode`
- Displays response status in UI

## Testing

### Test Suite: `tests/test_control_operations.py`
9 comprehensive tests covering:

1. **Message Construction (3 tests)**
   - SET_LOG_LEVEL message building and verification
   - GET_LOG_INFO message building and verification
   - SET_VERBOSE_MODE message building (both enable/disable)
   - Validates HTYP=0x3D (non-verbose flag)

2. **REST Endpoint Validation (6 tests)**
   - SET_LOG_LEVEL endpoint: validates session connected, log_level range 1-6
   - SET_VERBOSE_MODE endpoint: validates session connected
   - GET_SUPPORTED_OPERATIONS: returns ops for TCP, empty for UDP
   - Error handling: not connected session returns 400 error
   - Error handling: invalid log level returns 422 validation error
   - Transport restriction: UDP sessions reject control operations

**All 50 Tests Passing** (41 Phase 5 + 9 Phase 6)

## Usage Workflow

1. **Create Session**: User creates DLT ingestion session (TCP to ECU)
2. **Connect**: User clicks "Connect" to establish TCP connection
3. **View Messages**: Live DLT messages stream in table
4. **Select Message**: User clicks on message to open detail drawer
5. **Send Control Op**: User adjusts log level/verbose and clicks button
6. **See Result**: Response displayed in status area (success/error)
7. **Verify**: Next messages reflect the control operation effect

### Example: Change Log Level to 3 (Warning)
```
1. Select message from APP/CTX context
2. Enter "3" in log level input
3. Click "Set Log Level"
4. Status shows: "✓ Control message sent for SET_LOG_LEVEL"
5. ECU receives control message and adjusts log output
6. Subsequent messages show only Warning level and above
```

## Limitations & Future Work

### Current Limitations
- Control messages are one-way (send-only)
  - No response parsing or acknowledgment handling
  - User must manually verify effect on subsequent messages
- No control message history/logging
- No bulk operations (multiple APID/CTID at once)
- UDP transport not supported (requires stateful connection)

### Future Enhancements (Phase 7+)
1. **Response Handling**: Parse GET_LOG_INFO and GET_SOFTWARE_VERSION responses
2. **History**: Log all sent control operations in UI
3. **Bulk Operations**: Send same operation to multiple APID/CTID pairs
4. **Additional Operations**: STORE_CONFIG, RESET_TO_FACTORY_DEFAULT, etc.
5. **Performance**: Track control message send rate and success metrics
6. **Undo/Redo**: Allow reverting control operations

## Technical Details

### DLT Control Message Format
```
HTYP (0x3D)       1 byte  - Standard header, with ECU/Session/Timestamp, no verbose
MCNT              1 byte  - Message counter
LENGTH (BE)       2 bytes - Total message length (big-endian)
ECU_ID            4 bytes - Optional, per HTYP flags
SESSION_ID        4 bytes - Optional, per HTYP flags
TIMESTAMP         4 bytes - Optional, per HTYP flags
EXT_HDR           1 byte  - Message type=control (0x2x), number of args
APID              4 bytes - Application ID
CTID              4 bytes - Context ID
SERVICE_ID        1 byte  - Control operation ID (0x01=SET_LOG_LEVEL, 0x1A=SET_VERBOSE_MODE, etc.)
PAYLOAD           N bytes - Service-specific data
```

### Log Level Constants
```
1 = FATAL
2 = ERROR
3 = WARN
4 = INFO
5 = DEBUG
6 = VERBOSE
```

### Transport Support Matrix
```
Transport | Control Ops | Status
----------|-------------|--------
TCP       | Yes         | Full support
UDP       | No          | Not supported (stateless)
```

## Git Commit History
```
f6d21b5 Complete Phase 6 control operations UI with JavaScript integration
8b73ae1 Add comprehensive E2E tests and Phase 5 summary documentation
f804fc8 Fix DLT message framing in simulator
```

## Files Modified/Created
- **Created**: `app/ingestion/control_messages.py` (180 lines)
- **Created**: `tests/test_control_operations.py` (230 lines)
- **Modified**: `app/models.py` (added control models)
- **Modified**: `app/main.py` (added 3 control endpoints)
- **Modified**: `app/ingestion/tcp_client.py` (added writer management)
- **Modified**: `webbridge/static/index.html` (added control panel UI, JavaScript functions)

## Status
✅ **COMPLETE** - Phase 6 fully implemented with backend, frontend, tests, and integration
