import struct


class BootloaderRow(object):
    def __init__(self):
        self.array_id = None
        self.row_number = None
        self.data = None

    @classmethod
    def read(cls, data, line=None):
        self = cls()
        if data[0] != ':':
            raise ValueError("Bootloader rows must start with a colon")
        data = data[1:].decode('hex')
        self.array_id, self.row_number, data_length = struct.unpack('>BHH', data[:5])
        self.data = data[5:-1]
        if len(self.data) != data_length:
            raise ValueError("Row specified %d bytes of data, but got %d"
                             % (data_length, len(self.data)))
        (checksum,) = struct.unpack('B', data[-1])
        data_checksum = 0x100 - (sum(ord(x) for x in data[:-1]) & 0xFF)
        if data_checksum == 0x100:
            data_checksum = 0
        if checksum != data_checksum:
            raise ValueError("Computed checksum of 0x%.2x, but expected 0x%.2x on line %d"
                             % (data_checksum, checksum, line))
        return self

    @property
    def checksum(self):
        """Returns the data checksum. Should match what the bootloader returns."""
        return 0xFF & (1 + ~sum(ord(x) for x in self.data))


class BootloaderData(object):
    def __init__(self):
        self.silicon_id = None
        self.silicon_rev = None
        self.checksum_type = None
        self.arrays = {}

    @classmethod
    def read(cls, f):
        header = f.readline().strip().decode('hex')
        if len(header) != 6:
            raise ValueError("Expected 12 byte header line first")
        self = cls()
        self.silicon_id, self.silicon_rev, self.checksum_type = struct.unpack('>LBB', header)
        for i, line in enumerate(f):
            row = BootloaderRow.read(line.strip(), i + 2)
            if row.array_id not in self.arrays:
                self.arrays[row.array_id] = {}
            self.arrays[row.array_id][row.row_number] = row
        return self
