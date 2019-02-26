## cyflash python package into a standalone windows application

### Description
You can create a stand alone cyflash.exe application to be portable between your windows PCs with no pre installation of python.
After generating cyflash.exe for windows you will only need to install on target PC your CAN hardware specific drivers.
you are now ready to go!

### Procedure 
1. Install PyInstaller 

```pip install pyinstaller```

2. Install python-can

```pip install python-can```

3. Run batch file

If error with missing path or dependinces - search for missing dlls on you PC.
channge --path "C:\Program Files (x86)\Microsoft Visual Studio\2017\Community\Common7\IDE\Remote Debugger\x86" 

look into /dist/ folder for executable.

Tested with:
* PSOC4,5
* CANBUS PEAK PCAN
* SERIAL
