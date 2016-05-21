import struct

class InvalidPacketError(Exception):
    pass


class BootloaderError(Exception):
    pass


class TimeoutError(BootloaderError):
    pass


class IncorrectLength(BootloaderError):
    STATUS = 0x03


class InvalidData(BootloaderError):
    STATUS = 0x04


class InvalidCommand(BootloaderError):
    STATUS = 0x05


class InvalidChecksum(BootloaderError):
    STATUS = 0x08


class InvalidArray(BootloaderError):
    STATUS = 0x09


class InvalidFlashRow(BootloaderError):
    STATUS = 0x0A


class InvalidApp(BootloaderError):
    STATUS = 0x0C


class UnknownError(BootloaderError):
    STATUS = 0x0F


class BootloaderResponse(object):
    FORMAT = ""
    ARGS = ()

    ERRORS = {klass.STATUS: klass for klass in [
        IncorrectLength,
        InvalidData,
        InvalidCommand,
        InvalidChecksum,
        InvalidArray,
        InvalidFlashRow,
        InvalidApp,
        UnknownError
    ]}

    def __init__(self, data):
        for arg, value in zip(self.ARGS, struct.unpack(self.FORMAT, data)):
            if arg:
                setattr(self, arg, value)

    @classmethod
    def decode(cls, data, checksum_func):
        start, status, length = struct.unpack("<BBH", data[:4])
        if start != 0x01:
            raise InvalidPacketError()
        if length != len(data) - 7:
            raise InvalidPacketError()
        checksum, end = struct.unpack("<HB", data[-3:])
        data = data[:length+4]
        if end != 0x17:
            raise InvalidPacketError()
        if checksum != checksum_func(data):
            raise InvalidPacketError()

        data = data[4:]
        if status == 0x00:
            return cls(data)
        else:
            response_class = cls.ERRORS.get(status)
            if response_class:
                raise response_class()
            else:
                raise InvalidPacketError()


class BootloaderCommand(object):
    COMMAND = None
    FORMAT = ""
    ARGS = ()
    RESPONSE = None

    def __init__(self, **kwargs):
        for arg in kwargs:
            if arg not in self.ARGS:
                raise TypeError("Argument %d not in command arguments" % (arg,))
        self.args = [kwargs[arg] for arg in self.ARGS]

    @property
    def data(self):
        return struct.pack(self.FORMAT, *self.args)


class BooleanResponse(BootloaderResponse):
    FORMAT = "B"
    ARGS = ("status",)


class VerifyChecksumCommand(BootloaderCommand):
    COMMAND = 0x31
    RESPONSE = BooleanResponse


class GetFlashSizeResponse(BootloaderResponse):
    FORMAT = "<HH"
    ARGS = ("first_row", "last_row")


class GetFlashSizeCommand(BootloaderCommand):
    COMMAND = 0x32
    FORMAT = "B"
    ARGS = ("array_id",)
    RESPONSE = GetFlashSizeResponse


class EmptyResponse(BootloaderResponse):
    pass

class EraseRowCommand(BootloaderCommand):
    COMMAND = 0x34
    FORMAT = "<BH"
    ARGS = ("array_id", "row_id")
    RESPONSE = EmptyResponse


class SyncBootloaderCommand(BootloaderCommand):
    COMMAND = 0x35
    RESPONSE = EmptyResponse


class SendDataCommand(BootloaderCommand):
    COMMAND = 0x37
    RESPONSE = EmptyResponse

    def __init__(self, data):
        self._data = data
        super(SendDataCommand, self).__init__()

    @property
    def data(self):
        return self._data


class EnterBootloaderResponse(BootloaderResponse):
    FORMAT = "<IBHB"
    ARGS = ("silicon_id", "silicon_rev", "bl_version", "bl_version_2")


class EnterBootloaderCommand(BootloaderCommand):
    COMMAND = 0x38
    RESPONSE = EnterBootloaderResponse


class ProgramRowCommand(BootloaderCommand):
    COMMAND = 0x39
    FORMAT = "<BH"
    ARGS = ("array_id", "row_id")
    RESPONSE = EmptyResponse

    def __init__(self, data, **kwargs):
        self._data = data
        super(ProgramRowCommand, self).__init__(**kwargs)

    @property
    def data(self):
        return super(ProgramRowCommand, self).data + self._data


class ChecksumResponse(BootloaderResponse):
    FORMAT = "<B"
    ARGS = ("checksum",)


class VerifyRowCommand(BootloaderCommand):
    COMMAND = 0x3A
    FORMAT = "<BH"
    ARGS = ("array_id", "row_id")
    RESPONSE = ChecksumResponse


class ExitBootloaderCommand(BootloaderCommand):
    COMMAND = 0x3B
    RESPONSE = EmptyResponse


class GetMetadataResponse(BootloaderResponse):
    FORMAT = "<BIIIxxxxxxxBBHHHxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    ARGS = (
        "checksum",
        "bootloadable_addr",
        "bootloader_last_row",
        "bootloadable_len",
        "active",
        "verified",
        "app_version",
        "app_id",
        "custom_id",
    )


class GetMetadataCommand(BootloaderCommand):
    COMMAND = 0x3C
    FORMAT = "<B"
    ARGS = ("application_id", )
    RESPONSE = GetMetadataResponse


class BootloaderSession(object):
    def __init__(self, transport, checksum_func):
        self.transport = transport
        self.checksum_func = checksum_func
        self.debug = False

    def send(self, command, read=True):
        data = command.data
        packet = "\x01" + struct.pack("<BH", command.COMMAND, len(data)) + data
        packet = packet + struct.pack('<H', self.checksum_func(packet)) + "\x17"
        if self.debug:
            print "Sending %s" % ("".join(" 0x%02x" % ord(b) for b in packet))
        self.transport.send(packet)
        if read:
            response = self.transport.recv()
            return command.RESPONSE.decode(response, self.checksum_func)
        else:
            return None

    def enter_bootloader(self):
        response = self.send(EnterBootloaderCommand())
        return response.silicon_id, response.silicon_rev, response.bl_version | (response.bl_version_2 << 16)

    def exit_bootloader(self):
        self.send(ExitBootloaderCommand(), read=False)

    def get_flash_size(self, array_id):
        response = self.send(GetFlashSizeCommand(array_id=array_id))
        return response.first_row, response.last_row

    def verify_checksum(self):
        return bool(self.send(VerifyChecksumCommand()).status)

    def get_metadata(self, application_id=0):
        return self.send(GetMetadataCommand(application_id=application_id))

    def program_row(self, array_id, row_id, rowdata):
        self.send(ProgramRowCommand(
            rowdata,
            array_id=array_id,
            row_id=row_id))

    def get_row_checksum(self, array_id, row_id):
        return self.send(VerifyRowCommand(array_id=array_id, row_id=row_id)).checksum

    def send_data(self, data):
        self.send(SendDataCommand(
            data))


class SerialTransport(object):
    def __init__(self, f):
        self.f = f
        self.debug = False

    def send(self, data):
        self.f.write(data)

    def recv(self):
        data = self.f.read(4)
        if len(data) < 4:
            raise TimeoutError("Timed out waiting for Bootloader response.")
        size = struct.unpack("<H", data[-2:])[0]
        data += self.f.read(size + 3)
        if len(data) < size + 7:
            raise TimeoutError("Timed out waiting for Bootloader response.")
        if self.debug:
            print "Received %s" % ("".join(" 0x%02x" % ord(b) for b in data))
        return data


def crc16_checksum(data):
    crc = 0xffff

    for b in data:
        b = ord(b)
        for i in range(8):
            if (crc & 1) ^ (b & 1):
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
            b >>= 1

    crc = (crc << 8) | (crc >> 8)
    return ~crc & 0xffff

def summation_checksum(data):
    checksum = 0

    for b in data:
        checksum += ord(b)
    checksum = 1 + ~checksum

    return checksum & 0xffff
