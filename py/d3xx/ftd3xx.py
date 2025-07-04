import ctypes as c
import sys

if sys.platform == "win32":
    import _ftd3xx_win32 as _ft
else:
    import _ftd3xx_linux as _ft

from defines import (
    FT_LIST_ALL,
    FT_LIST_NUMBER_ONLY,
    FT_MAX_DESCRIPTION_SIZE,
    FT_OPEN_BY_INDEX,
    FT_STRING_DESCRIPTOR_TYPE,
)

msgs = [
    "FT_OK",
    "FT_INVALID_HANDLE",
    "FT_DEVICE_NOT_FOUND",
    "FT_DEVICE_NOT_OPENED",
    "FT_IO_ERROR",
    "FT_INSUFFICIENT_RESOURCES",
    "FT_INVALID_PARAMETER",
    "FT_INVALID_BAUD_RATE",
    "FT_DEVICE_NOT_OPENED_FOR_ERASE",
    "FT_DEVICE_NOT_OPENED_FOR_WRITE",
    "FT_FAILED_TO_WRITE_DEVICE",
    "FT_EEPROM_READ_FAILED",
    "FT_EEPROM_WRITE_FAILED",
    "FT_EEPROM_ERASE_FAILED",
    "FT_EEPROM_NOT_PRESENT",
    "FT_EEPROM_NOT_PROGRAMMED",
    "FT_INVALID_ARGS",
    "FT_NOT_SUPPORTED",
    "FT_NO_MORE_ITEMS",
    "FT_TIMEOUT",
    "FT_OPERATION_ABORTED",
    "FT_RESERVED_PIPE",
    "FT_INVALID_CONTROL_REQUEST_DIRECTION",
    "FT_INVALID_CONTROL_REQUEST_TYPE",
    "FT_IO_PENDING",
    "FT_IO_INCOMPLETE",
    "FT_HANDLE_EOF",
    "FT_BUSY",
    "FT_NO_SYSTEM_RESOURCES",
    "FT_DEVICE_LIST_NOT_READY",
    "FT_DEVICE_NOT_CONNECTED",
    "FT_INCORRECT_DEVICE_PATH",
    "FT_OTHER_ERROR"]

bRaiseExceptionOnError: list[bool] = []


class DeviceError(Exception):
    """Exception class for status messages"""

    def __init__(self, msgnum):
        self.message = msgs[msgnum]

    def __str__(self):
        return self.message


def call_ft(function, *args):
    """Call an FTDI function and check the status. Raise exception on error"""
    status = function(*args)
    if len(bRaiseExceptionOnError) > 0:
        if status != _ft.FT_OK:
            raise DeviceError(status)
    return status


def raiseExceptionOnError(bEnable):
    """Enable or disable exception handling"""
    origValue = len(bRaiseExceptionOnError) > 0
    if bEnable is True:
        if len(bRaiseExceptionOnError) == 0:
            bRaiseExceptionOnError.append(True)
    elif len(bRaiseExceptionOnError) > 0:
        bRaiseExceptionOnError.pop()
    return origValue


def getStrError(status):
    """Return string equivalent for error status"""
    return msgs[status]


def listDevices(flags=_ft.FT_OPEN_BY_DESCRIPTION):
    """Return a list of serial numbers(default), descriptions or
    locations (Windows only) of the connected FTDI devices depending on value of flags"""
    n = _ft.DWORD()
    call_ft(_ft.FT_ListDevices, c.byref(n), None, _ft.DWORD(FT_LIST_NUMBER_ONLY))
    devcount = n.value
    if devcount:
        if flags == _ft.FT_OPEN_BY_INDEX:
            flags = _ft.FT_OPEN_BY_DESCRIPTION
            # since ctypes has no pointer arithmetic.
        bd = [c.c_buffer(FT_MAX_DESCRIPTION_SIZE) for i in range(devcount)] + [None]
        # array of pointers to those strings, initially all NULL
        ba = (c.c_char_p * (devcount + 1))()
        for i in range(devcount):
            ba[i] = c.cast(bd[i], c.c_char_p)
        call_ft(_ft.FT_ListDevices, ba, c.byref(n), _ft.DWORD(FT_LIST_ALL | flags))
        return list(ba[:devcount])
    return None


def createDeviceInfoList():
    """Create the internal device info list and return number of entries"""
    numDevices = _ft.DWORD()
    call_ft(_ft.FT_CreateDeviceInfoList, c.byref(numDevices))
    return numDevices.value


def getDeviceInfoList():
    """Get device info list and return number of entries"""
    numDevices = _ft.DWORD()
    call_ft(_ft.FT_ListDevices, c.byref(numDevices), None, _ft.DWORD(FT_LIST_NUMBER_ONLY))
    numDevices = numDevices.value
    if numDevices == 0:
        return None
    """Use getDeviceInfoDetail instead"""
    deviceList = []
    for i in range(numDevices):
        device = _ft.FT_DEVICE_LIST_INFO_NODE()
        deviceInfo = getDeviceInfoDetail(i)
        device.Flags = deviceInfo["Flags"]
        device.ID = deviceInfo["ID"]
        device.LocId = deviceInfo["LocId"]
        device.SerialNumber = deviceInfo["SerialNumber"]
        device.Description = deviceInfo["Description"]
        deviceList.append(device)
    return deviceList


def getDeviceInfoDetail(devnum=0):
    """Get an entry from the internal device info list."""
    f = _ft.DWORD()
    t = _ft.DWORD()
    i = _ft.DWORD()
    loc = _ft.DWORD()
    h = _ft.FT_HANDLE()
    n = c.c_buffer(FT_MAX_DESCRIPTION_SIZE)
    d = c.c_buffer(FT_MAX_DESCRIPTION_SIZE)
    call_ft(_ft.FT_GetDeviceInfoDetail, _ft.DWORD(devnum),
            c.byref(f), c.byref(t), c.byref(i), c.byref(loc), n, d, c.byref(h))
    if sys.platform != "Win32":
        """Linux creates a handle to the device so close it. D3XX Linux driver issue."""
        call_ft(_ft.FT_Close, h)
    return {"Flags": f.value,
            "Type": t.value,
            "ID": i.value,
            "LocId": loc.value,
            "SerialNumber": n.value,
            "Description": d.value}


def create(id_str, flags=FT_OPEN_BY_INDEX):
    """Open a handle to a usb device by serial number, description or
    index depending on value of flags and return an FTD3XX instance for it"""
    h = _ft.FT_HANDLE()
    status = call_ft(_ft.FT_Create, id_str, _ft.DWORD(flags), c.byref(h))
    if (status != _ft.FT_OK):
        return None
    return FTD3XX(h)


def setTransferParams(conf, fifo):
    """Set transfer parameters for Linux only"""
    if sys.platform != "win32":
        call_ft(_ft.FT_SetTransferParams, c.byref(conf), fifo)


class FTD3XX:
    """Class for communicating with an FTDI device"""

    def __init__(self, handle):
        """Create an instance of the FTD3XX class with the given device handle
        and populate the device info in the instance dictionary. Set
        update to False to avoid a slow call to createDeviceInfoList."""
        self.handle = handle
        self.status = 0

    def close(self, noreset=False):
        """Close the device handle"""
        self.status = call_ft(_ft.FT_Close, self.handle)

    def getLastError(self):
        """Return status"""
        return self.status

    def flushPipe(self, pipe):
        """Flush pipe"""
        self.status = call_ft(_ft.FT_FlushPipe, self.handle, _ft.UCHAR(pipe))

    def getDeviceInfo(self):
        """Returns a dictionary describing the device. """
        deviceType = _ft.DWORD()
        deviceId = _ft.DWORD()
        desc = c.c_buffer(FT_MAX_DESCRIPTION_SIZE)
        serial = c.c_buffer(FT_MAX_DESCRIPTION_SIZE)
        self.status = call_ft(_ft.FT_GetDeviceInfo, self.handle, c.byref(deviceType), c.byref(deviceId), serial, desc,
                              None)
        return {"Type": deviceType.value,
                "ID": deviceId.value,
                "Description": desc.value,
                "Serial": serial.value}

    def getDeviceDescriptor(self):
        """Returns a dictionary describing the device descriptor. """
        devDesc = _ft.FT_DEVICE_DESCRIPTOR()
        self.status = call_ft(_ft.FT_GetDeviceDescriptor, self.handle, c.byref(devDesc))
        return devDesc

    def getStringDescriptor(self, index):
        """Returns a string descriptor. """
        strDesc = _ft.FT_STRING_DESCRIPTOR()
        lenTransferred = _ft.DWORD()
        self.status = call_ft(_ft.FT_GetDescriptor, self.handle, _ft.UCHAR(FT_STRING_DESCRIPTOR_TYPE), _ft.UCHAR(index),
                              c.pointer(strDesc), c.sizeof(strDesc), c.byref(lenTransferred))
        return strDesc

    def getConfigurationDescriptor(self):
        """Returns a dictionary describing the configuration descriptor. """
        cfgDesc = _ft.FT_CONFIGURATION_DESCRIPTOR()
        self.status = call_ft(_ft.FT_GetConfigurationDescriptor, self.handle, c.byref(cfgDesc))
        return cfgDesc

    def getInterfaceDescriptor(self, interfaceIndex):
        """Returns a dictionary describing the interface descriptor for the specified index. """
        ifDesc = _ft.FT_INTERFACE_DESCRIPTOR()
        self.status = call_ft(_ft.FT_GetInterfaceDescriptor, self.handle, _ft.UCHAR(interfaceIndex), c.byref(ifDesc))
        return ifDesc

    def getPipeInformation(self, interfaceIndex, pipeIndex):
        """Returns a dictionary describing the pipe infromationfor the specified indexes. """
        pipeDesc = _ft.FT_PIPE_INFORMATION()
        self.status = call_ft(_ft.FT_GetPipeInformation, self.handle, _ft.UCHAR(interfaceIndex), _ft.UCHAR(pipeIndex),
                              c.byref(pipeDesc))
        return pipeDesc

    def getChipConfiguration(self):
        """Returns a dictionary describing the chip configuration. """
        chipCfg = _ft.FT_60XCONFIGURATION()
        self.status = call_ft(_ft.FT_GetChipConfiguration, self.handle, c.byref(chipCfg))
        return chipCfg

    def setChipConfiguration(self, chipCfg=None):
        """Sets a chip configuration. """
        self.status = call_ft(_ft.FT_SetChipConfiguration, self.handle,
                              c.byref(chipCfg) if chipCfg is not None else None)

    def getVIDPID(self):
        """Get the VID and PID of the device"""
        vid = _ft.USHORT()
        pid = _ft.USHORT()
        self.status = call_ft(_ft.FT_GetVIDPID, self.handle, c.byref(vid), c.byref(pid))
        return (vid.value, pid.value)

    def getLibraryVersion(self):
        """Get the version of the user driver library"""
        libraryVer = _ft.DWORD()
        self.status = call_ft(_ft.FT_GetLibraryVersion, c.byref(libraryVer))
        return libraryVer.value

    def getDriverVersion(self):
        """Get the version of the kernel driver"""
        driverVer = _ft.DWORD()
        self.status = call_ft(_ft.FT_GetDriverVersion, self.handle, c.byref(driverVer))
        return driverVer.value

    def getFirmwareVersion(self):
        """Get the version of the firmware"""
        firmwareVer = _ft.DWORD()
        self.status = call_ft(_ft.FT_GetFirmwareVersion, self.handle, c.byref(firmwareVer))
        return firmwareVer.value

    def resetDevicePort(self):
        """Reset port where device is connected"""
        self.status = call_ft(_ft.FT_ResetDevicePort, self.handle)

    def enableGPIO(self, mask, direction):
        """Enable GPIO"""
        self.status = call_ft(_ft.FT_EnableGPIO, self.handle, _ft.ULONG(mask), _ft.ULONG(direction))

    def writeGPIO(self, mask, data):
        """Write GPIO"""
        self.status = call_ft(_ft.FT_WriteGPIO, self.handle, _ft.ULONG(mask), _ft.ULONG(data))

    def readGPIO(self):
        """Read GPIO"""
        gpio = _ft.ULONG()
        self.status = call_ft(_ft.FT_ReadGPIO, self.handle, c.byref(gpio))
        return gpio.value

    def setGPIOPull(self, mask, pull):
        """Set GPIO pull"""
        self.status = call_ft(_ft.FT_SetGPIOPull, self.handle, _ft.ULONG(mask), _ft.ULONG(pull))

    def setStreamPipe(self, pipe, size):
        """Set stream pipe for continous transfer of fixed size"""
        self.status = call_ft(_ft.FT_SetStreamPipe, self.handle, _ft.BOOLEAN(0), _ft.BOOLEAN(0), _ft.UCHAR(pipe),
                              _ft.ULONG(size))

    def clearStreamPipe(self, pipe):
        """Clear stream pipe for continous transfer of fixed size"""
        self.status = call_ft(_ft.FT_ClearStreamPipe, self.handle, _ft.BOOLEAN(0), _ft.BOOLEAN(0), _ft.UCHAR(pipe))


    # OS-dependent functions
    # If Windows
    if sys.platform == "win32":

        def initializeOverlapped(self, overlapped):
            """ initialize overlapped """
            self.status = call_ft(_ft.FT_InitializeOverlapped, self.handle, overlapped)
            return self.status

        def releaseOverlapped(self, overlapped):
            """ initialize overlapped """
            self.status = call_ft(_ft.FT_ReleaseOverlapped, self.handle, overlapped)
            return self.status

        def getOverlappedResults(self, overlapped, bytesTransferred):
            """ initialize overlapped """
            self.status = call_ft(_ft.FT_GetOverlappedResult, self.handle, overlapped, c.byref(bytesTransferred),
                                  _ft.BOOL(1))
            return self.status

        def writePipe(self, pipe, data, datalen):
            """Send the data to the device."""
            bytesTransferred = _ft.ULONG()
            self.status = call_ft(_ft.FT_WritePipe, self.handle, _ft.UCHAR(pipe), data, _ft.ULONG(datalen),
                                  c.byref(bytesTransferred), None)
            return bytesTransferred.value

        def writePipeAsync(self, pipe, data, datalen, transferred, overlapped):
            """Recv the data to the device."""
            self.status = call_ft(_ft.FT_WritePipeEx, self.handle, _ft.UCHAR(pipe), data, _ft.ULONG(datalen),
                                  c.byref(transferred), overlapped)
            return self.status

        def readPipe(self, pipe, data, datalen):
            """Recv the data to the device."""
            bytesTransferred = _ft.ULONG()
            self.status = call_ft(_ft.FT_ReadPipe, self.handle, _ft.UCHAR(pipe), data, _ft.ULONG(datalen),
                                  c.byref(bytesTransferred), None)
            return bytesTransferred.value

        def readPipeEx(self, pipe, datalen, raw=True):
            """Recv the data to the device."""
            bytesTransferred = _ft.ULONG()
            data = c.c_buffer(datalen)
            self.status = call_ft(_ft.FT_ReadPipeEx, self.handle, _ft.UCHAR(pipe), data, _ft.ULONG(datalen),
                                  c.byref(bytesTransferred), None)
            return {"bytesTransferred": bytesTransferred.value,
                    "bytes": data.raw[:bytesTransferred.value] if raw is True else data.value[:bytesTransferred.value]}

        def readPipeAsync(self, pipe, data, datalen, transferred, overlapped):
            """Recv the data to the device."""
            self.status = call_ft(_ft.FT_ReadPipeEx, self.handle, _ft.UCHAR(pipe), data, _ft.ULONG(datalen),
                                  c.byref(transferred), overlapped)
            return self.status

        def setPipeTimeout(self, pipeid, timeoutMS):
            """Set pipe timeout"""
            self.status = call_ft(_ft.FT_SetPipeTimeout, self.handle, _ft.UCHAR(pipeid), _ft.ULONG(timeoutMS))

        def getPipeTimeout(self, pipeid):
            """Get pipe timeout"""
            timeoutMS = _ft.ULONG()
            self.status = call_ft(_ft.FT_GetPipeTimeout, self.handle, _ft.UCHAR(pipeid), c.byref(timeoutMS))
            return timeoutMS.value


        def abortPipe(self, pipe):
            """Abort ongoing transfers for the specifed pipe"""
            self.status = call_ft(_ft.FT_AbortPipe, self.handle, _ft.UCHAR(pipe))

        def cycleDevicePort(self):
            """Cycle port where device is connected"""
            self.status = call_ft(_ft.FT_CycleDevicePort, self.handle)

        def setSuspendTimeout(self, timeout):
            """Set suspend timeout"""
            self.status = call_ft(_ft.FT_SetSuspendTimeout, self.handle, _ft.ULONG(timeout))

        def getSuspendTimeout(self):
            """Get suspend timeout"""
            timeout = _ft.ULONG()
            self.status = call_ft(_ft.FT_GetSuspendTimeout, self.handle, c.byref(timeout))
            return timeout.value

    # OS-dependent functions
    # If Linux
    else:

        def writePipe(self, channel, data, datalen, timeout=1000):
            """Send the data to the device."""
            bytesTransferred = _ft.ULONG()
            self.status = call_ft(_ft.FT_WritePipeEx, self.handle, _ft.UCHAR(channel), data, _ft.ULONG(datalen),
                                  c.byref(bytesTransferred), timeout)
            return bytesTransferred.value

        def readPipe(self, channel, data, datalen, timeout=1000):
            """Recv the data to the device."""
            bytesTransferred = _ft.ULONG()
            self.status = call_ft(_ft.FT_ReadPipeEx, self.handle, _ft.UCHAR(channel), data, _ft.ULONG(datalen),
                                  c.byref(bytesTransferred), timeout)
            return bytesTransferred.value

        def readPipeEx(self, channel, datalen, timeout=1000, raw=False):
            """Recv the data to the device."""
            bytesTransferred = _ft.ULONG()
            data = c.c_buffer(datalen)
            self.status = call_ft(_ft.FT_ReadPipeEx, self.handle, _ft.UCHAR(channel), data, _ft.ULONG(datalen),
                                  c.byref(bytesTransferred), timeout)
            return {"bytesTransferred": bytesTransferred.value,
                    "bytes": data.value[:bytesTransferred.value] if raw is False else data.raw[:bytesTransferred.value]}


__all__ = ["call_ft",
           "listDevices",
           "createDeviceInfoList",
           "getDeviceInfoDetail",
           "getDeviceInfoList",
           "getStrError",
           "setTransferParams",
           "create",
           "FTD3XX",
           "raiseExceptionOnError",
           "DeviceError"]
