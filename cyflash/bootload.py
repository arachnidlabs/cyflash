"""PSoC bootloader command line tool."""


__version__ = "1.01"


import argparse
import sys

from . import cyacd
from . import protocol


parser = argparse.ArgumentParser(description="Bootloader tool for Cypress PSoC devices")

group = parser.add_mutually_exclusive_group(required=True)
group.add_argument(
	'--serial',
	action='store',
	dest='serial',
	metavar='PORT',
	default=None,
	help="Use a serial interface")

parser.add_argument(
	'--serial_baudrate',
	action='store',
	dest='serial_baudrate',
	metavar='BAUD',
	default=115200,
	type=int,
	help="Baud rate to use when flashing using serial (default 115200)")
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
	'image',
	action='store',
	type=argparse.FileType(mode='r'),
	help="Image to read flash data from")


checksum_types = {
	1: protocol.crc16_checksum,
}


class BootloaderError(Exception): pass


def make_session(args, checksum_type):
	if args.serial:
		import serial
		ser = serial.Serial(args.serial, args.serial_baudrate, timeout=args.timeout)
		transport = protocol.SerialTransport(ser)
	else:
		raise BootloaderError("No valid interface specified")

	try:
		checksum_func = checksum_types[checksum_type]
	except KeyError:
		raise BootloaderError("Invalid checksum type: %d" % (checksum_type,))

	return protocol.BootloaderSession(transport, checksum_func)


def seek_permission(default, message):
	if default is not None:
		return lambda remote, local: default
	else:
		def prompt(*args):
			while True:
				result = raw_input(message % args)
				if result.lower().startswith('y'):
					return True
				elif result.lower().startswith('n'):
					return False


class BootloaderHost(object):
	def __init__(self, session, out):
		self.session = session
		self.out = out
		self.row_ranges = {}

	def bootload(self, data, downgrade, newapp):
		self.enter_bootloader(data)
		self.verify_row_ranges(data)
		self.check_metadata(data, downgrade, newapp)
		self.write_rows(data)
		if not self.session.verify_checksum():
			raise BootloaderError("Flash checksum does not verify! Aborting.")
		else:
			self.out.write("Device checksum verifies OK.\n")
		self.out.write("Rebooting device.\n")
		self.session.exit_bootloader()

	def verify_row_ranges(self, data):
		for array_id, array in data.arrays.iteritems():
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
		silicon_id, silicon_rev, bootloader_version = self.session.enter_bootloader()
		self.out.write("Silicon ID 0x%.8x, revision %d.\n" % (silicon_id, silicon_rev))
		if silicon_id != data.silicon_id:
			raise ValueError("Silicon ID of device (0x%.8x) does not match firmware file (0x%.8x)"
							 % (silicon_id, data.silicon_id))
		if silicon_rev != data.silicon_rev:
			raise ValueError("Silicon revision of device (0x%.2x) does not match firmware file (0x%.2x)"
							 % (silicon_rev, data.silicon_rev))

	def check_metadata(self, data, downgrade, newapp):
		try:
			metadata = self.session.get_metadata(0)
			self.out.write("Device application_id %d, version %d.\n" % (
				metadata.app_id, metadata.app_version))
		except protocol.InvalidApp:
			self.out.write("No valid application on device.\n")
			return

		# TODO: Make this less horribly hacky
		metadata_row = data.arrays[0][self.row_ranges[0][1]]
		local_metadata = protocol.GetMetadataResponse(metadata_row.data[64:120])

		if metadata.app_version > local_metadata.app_version:
			message = "Device application version is v%d.%d, but local application version is v%d.%d." % (
				metadata.app_version >> 8, metadata.app_version & 0xFF,
				local_metadata.app_version >> 8, local_metadata.app_version & 0xFF)
			if not downgrade(metadata.app_version, loca_metadata.app_version):
				raise ValueError(message + " Aborting.")

		if metadata.app_id != local_metadata.app_id:
			message = "Device application ID is %d, but local application ID is %d." % (
				metadata.application_id, local_metadata.application_id)
			if not newapp(metadata.app_id, local_metadata.app_id):
				raise ValueError(message + " Aborting.")

	def write_rows(self, data):
		total = sum(len(x) for x in data.arrays.values())
		i = 0
		for array_id, array in data.arrays.iteritems():
			for row_number, row in array.iteritems():
				i += 1
				self.session.program_row(array_id, row_number, row.data)
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
	data = cyacd.BootloaderData.read(args.image)
	session = make_session(args, data.checksum_type)
	bl = BootloaderHost(session, sys.stdout)
	try:
		bl.bootload(
			data,
			seek_permission(
				args.downgrade,
				"Device version %d is greater than local version %d. Flash anyway? (Y/N)"),
			seek_permission(
				args.newapp,
				"Device app ID %d is different from local app ID %d. Flash anyway? (Y/N)"))
	except (protocol.BootloaderError, BootloaderError), e:
		print e.message
		sys.exit(1)


if __name__ == '__main__':
	main()
