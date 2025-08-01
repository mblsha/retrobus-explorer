# FT Status Codes
FT_OK = 0
FT_INVALID_HANDLE = 1
FT_DEVICE_NOT_FOUND = 2
FT_DEVICE_NOT_OPENED = 3
FT_IO_ERROR = 4
FT_INSUFFICIENT_RESOURCES = 5
FT_INVALID_PARAMETER = 6
FT_INVALID_BAUD_RATE = 7
FT_DEVICE_NOT_OPENED_FOR_ERASE = 8
FT_DEVICE_NOT_OPENED_FOR_WRITE = 9
FT_FAILED_TO_WRITE_DEVICE = 10
FT_EEPROM_READ_FAILED = 11
FT_EEPROM_WRITE_FAILED = 12
FT_EEPROM_ERASE_FAILED = 13
FT_EEPROM_NOT_PRESENT = 14
FT_EEPROM_NOT_PROGRAMMED = 15
FT_INVALID_ARGS = 16
FT_NOT_SUPPORTED = 17
FT_NO_MORE_ITEMS = 18
FT_TIMEOUT = 19
FT_OPERATION_ABORTED = 20
FT_RESERVED_PIPE = 21
FT_INVALID_CONTROL_REQUEST_DIRECTION = 22
FT_INVALID_CONTROL_REQUEST_TYPE = 23
FT_IO_PENDING = 24
FT_IO_INCOMPLETE = 25
FT_HANDLE_EOF = 26
FT_BUSY = 27
FT_NO_SYSTEM_RESOURCES = 28
FT_DEVICE_LIST_NOT_READY = 29
FT_DEVICE_NOT_CONNECTED = 30
FT_INCORRECT_DEVICE_PATH = 31
FT_OTHER_ERROR = 32

# Standard Descriptor Types
FT_DEVICE_DESCRIPTOR_TYPE = 0x01
FT_CONFIGURATION_DESCRIPTOR_TYPE = 0x02
FT_STRING_DESCRIPTOR_TYPE = 0x03
FT_INTERFACE_DESCRIPTOR_TYPE = 0x04

# Power Configuration
FT_SELF_POWERED_MASK = 0x40
FT_REMOTE_WAKEUP_MASK = 0x20

# Reserved pipes
FT_RESERVED_INTERFACE_INDEX = 0x0
FT_RESERVED_PIPE_INDEX_SESSION = 0x0
FT_RESERVED_PIPE_INDEX_NOTIFICATION = 0x1
FT_RESERVED_PIPE_SESSION = 0x1
FT_RESERVED_PIPE_NOTIFICATION = 0x81

# Create flags
FT_OPEN_BY_SERIAL_NUMBER = 0x00000001
FT_OPEN_BY_DESCRIPTION = 0x00000002
FT_OPEN_BY_LOCATION = 0x00000004
FT_OPEN_BY_GUID = 0x00000008
FT_OPEN_BY_INDEX = 0x00000010

# ListDevices flags
FT_LIST_ALL = 0x20000000
FT_LIST_BY_INDEX = 0x40000000
FT_LIST_NUMBER_ONLY	= 0x80000000

# GPIO direction, value
FT_GPIO_DIRECTION_IN = 0
FT_GPIO_DIRECTION_OUT = 1
FT_GPIO_VALUE_LOW = 0
FT_GPIO_VALUE_HIGH = 1
FT_GPIO_0 = 0
FT_GPIO_1 = 1
FT_GPIO_MASK_GPIO_0 = 1
FT_GPIO_MASK_GPIO_1 = 2

# GPIO pull
FT_GPIO_PULL_LOW = 0
FT_GPIO_PULL_HIGH = 1
FT_GPIO_PULL_50K_PD = 0
FT_GPIO_PULL_HIZ = 1
FT_GPIO_PULL_50K_PU = 2
FT_GPIO_PULL_DEFAULT = 0

# Pipe types
FT_PIPE_TYPE_CONTROL = 0
FT_PIPE_TYPE_ISOCHRONOUS = 1
FT_PIPE_TYPE_BULK = 2
FT_PIPE_TYPE_INTERRUPT = 3

# Pipe direction
FT_PIPE_DIR_IN = 0
FT_PIPE_DIR_OUT = 1

# Notification callback type
FT_NOTIFICATION_CALLBACK_TYPE_DATA = 0
FT_NOTIFICATION_CALLBACK_TYPE_GPIO = 1

# Chip configuration - FlashEEPROMDetection
FT_CONFIGURATION_FLASH_ROM_BIT_ROM = 0
FT_CONFIGURATION_FLASH_ROM_BIT_MEMORY_NOTEXIST = 1
FT_CONFIGURATION_FLASH_ROM_BIT_CUSTOMDATA_INVALID = 2
FT_CONFIGURATION_FLASH_ROM_BIT_CUSTOMDATACHKSUM_INVALID = 3
FT_CONFIGURATION_FLASH_ROM_BIT_CUSTOM = 4
FT_CONFIGURATION_FLASH_ROM_BIT_GPIO_INPUT = 5
FT_CONFIGURATION_FLASH_ROM_BIT_GPIO_0 = 6
FT_CONFIGURATION_FLASH_ROM_BIT_GPIO_1 = 7

# Chip configuration - Battery charging
FT_CONFIGURATION_BATCHG_BIT_OFFSET_DCP = 6
FT_CONFIGURATION_BATCHG_BIT_OFFSET_CDP = 4
FT_CONFIGURATION_BATCHG_BIT_OFFSET_SDP = 2
FT_CONFIGURATION_BATCHG_BIT_OFFSET_DEF = 0
FT_CONFIGURATION_BATCHG_BIT_MASK = 3

# Chip configuration - FIFO Clock Speed
FT_CONFIGURATION_FIFO_CLK_100 = 0x0
FT_CONFIGURATION_FIFO_CLK_66 = 0x1
FT_CONFIGURATION_FIFO_CLK_COUNT = 0x2

# Chip configuration - FIFO Mode
FT_CONFIGURATION_FIFO_MODE_245 = 0x0
FT_CONFIGURATION_FIFO_MODE_600 = 0x1
FT_CONFIGURATION_FIFO_MODE_COUNT = 0x2

# Chip configuration - Channel Configuration
FT_CONFIGURATION_CHANNEL_CONFIG_4 = 0x0
FT_CONFIGURATION_CHANNEL_CONFIG_2 = 0x1
FT_CONFIGURATION_CHANNEL_CONFIG_1 = 0x2
FT_CONFIGURATION_CHANNEL_CONFIG_1_OUTPIPE = 0x3
FT_CONFIGURATION_CHANNEL_CONFIG_1_INPIPE = 0x4
FT_CONFIGURATION_CHANNEL_CONFIG_COUNT = 0x5

# Chip configuration - Optional Feature Support
FT_CONFIGURATION_OPTIONAL_FEATURE_DISABLEALL = 0x0000
FT_CONFIGURATION_OPTIONAL_FEATURE_ENABLEBATTERYCHARGING = 0x0001
FT_CONFIGURATION_OPTIONAL_FEATURE_DISABLECANCELSESSIONUNDERRUN = 0x0002
FT_CONFIGURATION_OPTIONAL_FEATURE_ENABLENOTIFICATIONMESSAGE_INCH1 = 0x0004
FT_CONFIGURATION_OPTIONAL_FEATURE_ENABLENOTIFICATIONMESSAGE_INCH2 = 0x0008
FT_CONFIGURATION_OPTIONAL_FEATURE_ENABLENOTIFICATIONMESSAGE_INCH3 = 0x0010
FT_CONFIGURATION_OPTIONAL_FEATURE_ENABLENOTIFICATIONMESSAGE_INCH4 = 0x0020
FT_CONFIGURATION_OPTIONAL_FEATURE_ENABLENOTIFICATIONMESSAGE_INCHALL = 0x003C
FT_CONFIGURATION_OPTIONAL_FEATURE_DISABLEUNDERRUN_INCH1 = 0x0040
FT_CONFIGURATION_OPTIONAL_FEATURE_DISABLEUNDERRUN_INCH2 = 0x0080
FT_CONFIGURATION_OPTIONAL_FEATURE_DISABLEUNDERRUN_INCH3 = 0x0100
FT_CONFIGURATION_OPTIONAL_FEATURE_DISABLEUNDERRUN_INCH4 = 0x0200
FT_CONFIGURATION_OPTIONAL_FEATURE_DISABLEUNDERRUN_INCHALL = 0x03C0
FT_CONFIGURATION_OPTIONAL_FEATURE_ENABLEALL = 0xFFFF

# Chip configuration - Default values
FT_CONFIGURATION_DEFAULT_VENDORID = 0x0403
FT_CONFIGURATION_DEFAULT_PRODUCTID_600 = 0x601E
FT_CONFIGURATION_DEFAULT_PRODUCTID_601 = 0x601F
FT_CONFIGURATION_DEFAULT_INTERRUPT_INTERVAL = 0x9
FT_CONFIGURATION_DEFAULT_POWERATTRIBUTES = 0xE0
FT_CONFIGURATION_DEFAULT_POWERCONSUMPTION = 0x60
FT_CONFIGURATION_DEFAULT_FIFOCLOCK = FT_CONFIGURATION_FIFO_CLK_100
FT_CONFIGURATION_DEFAULT_FIFOMODE = FT_CONFIGURATION_FIFO_MODE_600
FT_CONFIGURATION_DEFAULT_CHANNELCONFIG = FT_CONFIGURATION_CHANNEL_CONFIG_4
FT_CONFIGURATION_DEFAULT_OPTIONALFEATURE = FT_CONFIGURATION_OPTIONAL_FEATURE_DISABLEALL
FT_CONFIGURATION_DEFAULT_BATTERYCHARGING = 0xE4
FT_CONFIGURATION_DEFAULT_BATTERYCHARGING_TYPE_DCP = 0x3
FT_CONFIGURATION_DEFAULT_BATTERYCHARGING_TYPE_CDP = 0x2
FT_CONFIGURATION_DEFAULT_BATTERYCHARGING_TYPE_SDP = 0x1
FT_CONFIGURATION_DEFAULT_BATTERYCHARGING_TYPE_OFF = 0x0
FT_CONFIGURATION_DEFAULT_FLASHDETECTION = 0x0
FT_CONFIGURATION_DEFAULT_MSIOCONTROL = 0x10800
FT_CONFIGURATION_DEFAULT_GPIOCONTROL = 0x0

# Device types
FT_DEVICE_UNKNOWN = 3
FT_DEVICE_600 = 600
FT_DEVICE_601 = 601

# Device information
FT_FLAGS_OPENED = 1
FT_FLAGS_HISPEED = 2
FT_FLAGS_SUPERSPEED = 4

# Device information SIZE
FT_MAX_MANUFACTURER_SIZE = 16
FT_MAX_DESCRIPTION_SIZE = 32
FT_MAX_SERIAL_NUMBER_SIZE = 16
