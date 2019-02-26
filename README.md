# cyflash


Cyflash is a tool for uploading firmware to Cypress PSoC devices via Cypress's
standard bootloader protocol.

Basic usage is simple: specify an interface to connect to the device via
(currently only serial is supported) and a .cyacd file to upload, and cyflash
does the rest.

Cyflash also has the advantage of being about 5 times faster than Cypress's
tool, being cross-platform, and not requiring all of PSoC creator to work.

Cyflash is still quite new, and should be considered beta-quality software.
Pull requests and bug reports are most welcome.

## Installation
Install cyflash from pypi with `pip install cyflash`, or (from source)
`python setup.py install`.
This will install the cyflash.exe in python\Scripts directory

You can also run cyflash directly from python:
```
python cyflash_run.py --help
```


## Flash over Serial
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

## Flash over CANBUS
cyflash can use raw CANbus frames as transport with the python-can library.
On the target side please see the CANbus_Bootloader.c file that implements
the Cypress boodloader communication interface.

#### Install python-can library
```
pip installl python-can
```
#### Install hardware specific drivers
PEAK drivers for pcan [Device Drivers](https://www.peak-system.com/Downloads.76.0.html?&L=1)<br>
During installlation make sure you also install the PCAN-BASIC API

#### Run cyflash
* --canbus=pcan - Peak's PCAN interface
* --canbus_channel=PCAN_USBBUS1 - HW usb channel.
* --canbus_baudrate=1000000 - bitrate 1Mbit/s

```
cyflash Application.cyacd --canbus=pcan --canbus_channel=PCAN_USBBUS1 --canbus_id=0x0AB --canbus_baudrate=1000000
```


## Cypress Bootloader metadata component bug
Bootloader component v1.40 and 1.50 have a bug that prevents the GET_METADATA
command to work correctly. The #define Bootloader_RSP_SIZE_GET_METADATA (0x56u)
in Bootloader_PVT.h should be #define Bootloader_RSP_SIZE_GET_METADATA (56u)
Version 1.60 should resolve this issue
