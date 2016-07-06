cyflash
=======

Cyflash is a tool for uploading firmware to Cypress PSoC devices via Cypress's
standard bootloader protocol.

Basic usage is simple: specify an interface to connect to the device via
(currently only serial is supported) and a .cyacd file to upload, and cyflash
does the rest.

Cyflash also has the advantage of being about 5 times faster than Cypress's
tool, being cross-platform, and not requiring all of PSoC creator to work.

Install cyflash from pypi with `pip install cyflash`, or (from source)
`python setup.py install`.

Example command line:

    cyflash --serial=/dev/tty.usb-device myfirmware.cyacd

Example output:

    Initialising bootloader.
    Silicon ID 0x04a61193, revision 17.
    Array 0: first row 22, last row 255.
    Device application_id 0, version 258.
    Uploading data (198/198)
    Device checksum verifies OK.
    Rebooting device.

If cyflash detects a valid metadata record on the device already, it will read
and compare this to your image's metadata. By default, cyflash will prompt you
before overwriting the firmware with an older version or one with a different
application ID. You can force this behaviour with --downgrade or --nodowngrade
and --newapp and --nonewapp, respectively.

Cyflash is still quite new, and should be considered beta-quality software.
Pull requests and bug reports are most welcome.


Cypress Bootloader metadata component bug
=========================================
Bootloader component v1.40 and 1.50 have a bug that prevents the GET_METADATA
command to work correctly. The #define Bootloader_RSP_SIZE_GET_METADATA (0x56u)
in Bootloader_PVT.h should be #define Bootloader_RSP_SIZE_GET_METADATA (56u)
Version 1.60 should resolve this issue

CANbus as transport
===================
cyflash can use raw CANbus frames as transport with the python-can library.
On the target side please see the CANbus_Bootloader.c file that implements
the Cypress boodloader communication interface.
