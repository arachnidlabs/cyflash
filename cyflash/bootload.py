"""PSoC bootloader command line tool."""

import argparse
import codecs
import time
import six
import sys

from builtins import input

from . import cyacd
from . import protocol


__version__ = "1.07"


def auto_int(x):
    return int(x, 0)

parser = argparse.ArgumentParser(description="Bootloader tool for Cypress PSoC devices")

group = parser.add_mutually_exclusive_group(required=True)
group.add_argument(
    '--serial',
    action='store',
    dest='serial',
    metavar='PORT',
    default=None,
    help="Use a serial interface")
group.add_argument(
    '--canbus',
    action='store',
    dest='canbus',
    metavar='BUSTYPE',
    default=None,
    help="Use a CANbus interface (requires python-can)")

parser.add_argument(
    '--serial_baudrate',
    action='store',
    dest='serial_baudrate',
    metavar='BAUD',
    default=115200,
    type=int,
    help="Baud rate to use when flashing using serial (default 115200)")
parser.add_argument(
    '--canbus_baudrate',
    action='store',
    dest='canbus_baudrate',
    metavar='BAUD',
    default=125000,
    type=int,
    help="Baud rate to use when flashing using CANbus (default 125000)")
parser.add_argument(
    '--canbus_channel',
    action='store',
    dest='canbus_channel',
    metavar='CANBUS_CHANNEL',
    default=0,
    help="CANbus channel to be used")
parser.add_argument(
    '--canbus_id',
    action='store',
    dest='canbus_id',
    metavar='CANBUS_ID',
    default=0,
    type=auto_int,
    help="CANbus frame ID to be used")

group = parser.add_mutually_exclusive_group(required=False)
group.add_argument(
    '--canbus_echo',
    action='store_true',
    dest='canbus_echo',
    default=False,
    help="Use echoed back received CAN frames to keep the host in sync")
group.add_argument(
    '--canbus_wait',
    action='store',
    dest='canbus_wait',
    metavar='CANBUS_WAIT',
    default=5,
    type=int,
    help="Wait for CANBUS_WAIT ms amount of time after sending a frame if you're not using echo frames as a way to keep host in sync")

parser.add_argument(
    '--timeout',
    action='store',
    dest='timeout',
    metavar='SECS',
    default=5.0,
    type=float,
    help="Time to wait for a Bootloader response (default 5)")

group = parser.add_mutually_exclusive_group()
group.add_argument(
    '--downgrade',
    action='store_true',
    dest='downgrade',
    default=None,
    help="Don't prompt before flashing old firmware over newer")
group.add_argument(
    '--nodowngrade',
    action='store_false',
    dest='downgrade',
    default=None,
    help="Fail instead of prompting when device firmware is newer")

group = parser.add_mutually_exclusive_group()
group.add_argument(
    '--newapp',
    action='store_true',
    dest='newapp',
    default=None,
    help="Don't prompt before flashing an image with a different application ID")
group.add_argument(
    '--nonewapp',
    action='store_false',
    dest='newapp',
    default=None,
    help="Fail instead of flashing an image with a different application ID")

parser.add_argument(
    'logging_config',
    action='store',
    type=argparse.FileType(mode='r'),
    nargs='?',
    help="Python logging configuration file")

parser.add_argument(
    '--psoc5',
    action='store_true',
    dest='psoc5',
    default=False,
    help="Add tag to parse PSOC5 metadata")

def validate_key(string):
    if len(string) != 14:
        raise argparse.ArgumentTypeError("key is of unexpected length")

    try:
        val = int(string, base=16)
        key = []
        key.append((val >> 40) & 0xff)
        key.append((val >> 32) & 0xff)
        key.append((val >> 24) & 0xff)
        key.append((val >> 16) & 0xff)
        key.append((val >> 8) & 0xff)
        key.append(val & 0xff)
        return key
    except ValueError:
        raise argparse.ArgumentTypeError("key is of unexpected format")

parser.add_argument(
    '--key',
    action='store',
    dest='key',
    default=None,
    type=validate_key,
    help="Optional security key (six bytes, on the form 0xAABBCCDDEEFF)")

DEFAULT_CHUNKSIZE = 25
parser.add_argument(
    '-cs',
    '--chunk-size',
    action='store',
    dest='chunk_size',
    default=DEFAULT_CHUNKSIZE,
    type=int,
    help="Chunk size to use for transfers - default %d" % DEFAULT_CHUNKSIZE)

parser.add_argument(
    '-v',
    '--verbose',
    action='store_true',
    dest='verbose',
    default=False,
    help="Enable verbose debug output")

parser.add_argument(
    'image',
    action='store',
    type=argparse.FileType(mode='r'),
    help="Image to read flash data from")

checksum_types = {
    0: protocol.sum_2complement_checksum,
    1: protocol.crc16_checksum,
}


class BootloaderError(Exception): pass


def make_session(args, checksum_type):
    if args.serial:
        import serial
        ser = serial.Serial(args.serial, args.serial_baudrate, timeout=args.timeout)
        ser.flushInput()  # need to clear any garbage off the serial port
        ser.flushOutput()
        transport = protocol.SerialTransport(ser, args.verbose)
    elif args.canbus:
        import can
        # Remaining configuration options should follow python-can practices
        canbus = can.interface.Bus(bustype=args.canbus, channel=args.canbus_channel, bitrate=args.canbus_baudrate)
        # Wants timeout in ms, we have it in s
        transport = protocol.CANbusTransport(canbus, args.canbus_id, int(args.timeout * 1000), args.canbus_echo,
                                             args.canbus_wait)
        transport.MESSAGE_CLASS = can.Message
    else:
        raise BootloaderError("No valid interface specified")

    try:
        checksum_func = checksum_types[checksum_type]
    except KeyError:
        raise BootloaderError("Invalid checksum type: %d" % (checksum_type,))

    return protocol.BootloaderSession(transport, checksum_func)


def seek_permission(argument, message):
    if argument is not None:
        return lambda remote, local: argument
    else:
        def prompt(*args):
            while True:
                result = input(message % args)
                if result.lower().startswith('y'):
                    return True
                elif result.lower().startswith('n'):
                    return False
        return prompt


class BootloaderHost(object):
    def __init__(self, session, args, out):
        self.session = session
        self.key = args.key
        self.chunk_size = args.chunk_size
        self.out = out
        self.row_ranges = {}

    def bootload(self, data, downgrade, newapp, psoc5):
        self.out.write("Entering bootload.\n")
        self.enter_bootloader(data)
        self.out.write("Verifying row ranges.\n")
        self.verify_row_ranges(data)
        self.out.write("Checking metadata.\n")
        self.check_metadata(data, downgrade, newapp, psoc5)
        self.out.write("Starting flash operation.\n")
        self.write_rows(data)
        if not self.session.verify_checksum():
            raise BootloaderError("Flash checksum does not verify! Aborting.")
        else:
            self.out.write("Device checksum verifies OK.\n")
        self.out.write("Rebooting device.\n")
        self.session.exit_bootloader()

    def verify_row_ranges(self, data):
        for array_id, array in six.iteritems(data.arrays):
            start_row, end_row = self.session.get_flash_size(array_id)
            self.out.write("Array %d: first row %d, last row %d.\n" % (
                array_id, start_row, end_row))
            self.row_ranges[array_id] = (start_row, end_row)
            for row_number in array:
                if row_number < start_row or row_number > end_row:
                    raise BootloaderError(
                        "Row %d in array %d out of range. Aborting."
                        % (row_number, array_id))

    def enter_bootloader(self, data):
        self.out.write("Initialising bootloader.\n")
        silicon_id, silicon_rev, bootloader_version = self.session.enter_bootloader(self.key)
        self.out.write("Silicon ID 0x%.8x, revision %d.\n" % (silicon_id, silicon_rev))
        if silicon_id != data.silicon_id:
            raise ValueError("Silicon ID of device (0x%.8x) does not match firmware file (0x%.8x)"
                             % (silicon_id, data.silicon_id))
        if silicon_rev != data.silicon_rev:
            raise ValueError("Silicon revision of device (0x%.2x) does not match firmware file (0x%.2x)"
                             % (silicon_rev, data.silicon_rev))

    def check_metadata(self, data, downgrade, newapp, psoc5):
        try:
            if psoc5:
                metadata = self.session.get_psoc5_metadata(0)
            else:
                metadata = self.session.get_metadata(0)
            self.out.write("Device application_id %d, version %d.\n" % (
                metadata.app_id, metadata.app_version))
        except protocol.InvalidApp:
            self.out.write("No valid application on device.\n")
            return
        except protocol.BootloaderError as e:
            self.out.write("Cannot read metadata from device: {}\n".format(e))
            return

        # TODO: Make this less horribly hacky
        # Fetch from last row of last flash array
        metadata_row = data.arrays[max(data.arrays.keys())][self.row_ranges[max(data.arrays.keys())][1]]
        if psoc5:
            local_metadata = protocol.GetPSOC5MetadataResponse(metadata_row.data[192:192+56])
        else:
            local_metadata = protocol.GetMetadataResponse(metadata_row.data[64:120])

        if metadata.app_version > local_metadata.app_version:
            message = "Device application version is v%d.%d, but local application version is v%d.%d." % (
                metadata.app_version >> 8, metadata.app_version & 0xFF,
                local_metadata.app_version >> 8, local_metadata.app_version & 0xFF)
            if not downgrade(metadata.app_version, local_metadata.app_version):
                raise ValueError(message + " Aborting.")

        if metadata.app_id != local_metadata.app_id:
            message = "Device application ID is %d, but local application ID is %d." % (
                metadata.app_id, local_metadata.app_id)
            if not newapp(metadata.app_id, local_metadata.app_id):
                raise ValueError(message + " Aborting.")

    def write_rows(self, data):
        total = sum(len(x) for x in data.arrays.values())
        i = 0
        for array_id, array in six.iteritems(data.arrays):
            for row_number, row in array.items():
                i += 1
                self.session.program_row(array_id, row_number, row.data, self.chunk_size)
                actual_checksum = self.session.get_row_checksum(array_id, row_number)
                if actual_checksum != row.checksum:
                    raise BootloaderError(
                        "Checksum does not match in array %d row %d. Expected %.2x, got %.2x! Aborting." % (
                            array_id, row_number, row.checksum, actual_checksum))
                self.progress("Uploading data", i, total)
            self.progress()

    def progress(self, message=None, current=None, total=None):
        if not message:
            self.out.write("\n")
        else:
            self.out.write("\r%s (%d/%d)" % (message, current, total))
        self.out.flush()


def main():
    args = parser.parse_args()

    if (args.logging_config):
        import logging
        import logging.config
        logging.config.fileConfig(args.logging_config)

    if (six.PY3):
        t0 = time.perf_counter()
    else:
        t0 = time.clock()
    data = cyacd.BootloaderData.read(args.image)
    session = make_session(args, data.checksum_type)
    bl = BootloaderHost(session, args, sys.stdout)
    try:
        bl.bootload(
            data,
            seek_permission(
                args.downgrade,
                "Device version %d is greater than local version %d. Flash anyway? (Y/N)"),
            seek_permission(
                args.newapp,
                "Device app ID %d is different from local app ID %d. Flash anyway? (Y/N)"),
            args.psoc5)
    except (protocol.BootloaderError, BootloaderError) as e:
        print("Unhandled error: {}".format(e))
        return 1
    if (six.PY3):
        t1 = time.perf_counter()
    else:
        t1 = time.clock()
    print("Total running time {0:02.2f}s".format(t1 - t0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
