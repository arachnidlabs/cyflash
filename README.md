cyflash
=======

Cyflash is a tool for uploading firmware to Cypress PSoC devices via Cypress's
standard bootloader protocol.

Basic usage is simple: specify an interface to connect to the device via
(currently only serial is supported) and a .cyacd file to upload, and cyflash
does the rest.

When using a bootloader with plenty bytes of RX/TX buffer, the Cyflash can be
about 5 times faster than Cypress's tool, being cross-platform, and not
requiring all of PSoC creator to work.

The chunk of data, in bytes, sent in every writing packet is part sent is
configured with the --chunksize, or -c, option. The maximum chunk size deppends
on the RX/TX buffer configured in the bootloader. Smaller chunk sizes is slower
but give more retries chances for a communication link with some error rate.
Bigger chunk sizes gives more speed. Can be configured as 16, 32, 64, or 128
bytes, default is 32.

A very useful feature is the --repetitive-init-sec SECS, or -r SECS, that
repetitively send data to initialize the bootloader, every 100 ms, for the
specified time. This gives time to unplug/plug the equipment, turn it on or
press some reset button. Default is 2 secs, zero value sends only one try and
waits for the timeout of the serial port (blocking). Negative number approach
infinite tries.

With the --erase option the flash is erased, row by row, before the new firmware
 is written. This grants known initial erased state for areas of the flash that
 could be used to store program data, like emulated eeprom data.

Install cyflash from pypi with `pip install cyflash`, or (from source)
`python setup.py install`.

Example command line:

  cyflash --erase --serial COM1 --serial_baudrate 38400 --parity E --stopbits 2
    -c 32 myfirmware.cyacd -r 10

Example output:

    Initialising bootloader...
    Entered bootloader! Silicon ID 0x04c81193, revision 17.

    Verifying row range...
    Array 0: first row 38, last row 255.
    Ok!

    Checking metadata...
    Invalid Command! Maybe metadata is not supported by the bootloader.

    Erasing all rows...
    Erasing row... (255/255), packet errors 0
    Done!

    Writing rows...
    Uploading data (17/17), packet errors 0
    Device checksum verifies OK.
    Rebooting device.

If cyflash detects a valid metadata record on the device already, it will read
and compare this to your image's metadata. By default, cyflash will prompt you
before overwriting the firmware with an older version or one with a different
application ID. You can force this behaviour with --downgrade or --nodowngrade
and --newapp and --nonewapp, respectively.

usage: cyflash [-h] [--erase] --serial PORT [--serial_baudrate BAUD]
                   [--timeout SECS] [--parity {N,E,O}] [--stopbits {1,2}]
                   [--downgrade | --nodowngrade] [--newapp | --nonewapp]
                   [-c {16,32,64,128}] [-r SECS]
                   image


Cyflash is still quite new, and should be considered beta-quality software.
Pull requests and bug reports are most welcome.
