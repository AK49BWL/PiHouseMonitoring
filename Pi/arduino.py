# Read data from an Arduino
# This script has been written for Python 2.7
# Author: AK49BWL
# Updated: 03/16/2024 17:33

import json
import serial
import struct
import time

# Modules?
import gv
cc = gv.cc

com = { # Serial config
    'port': '/dev/ttyUSB1',
    'baud': 9600,
    'byte': serial.EIGHTBITS,
    'parity': serial.PARITY_NONE,
    'stop': serial.STOPBITS_ONE,
    'timeout': 3,
    'onoff': 0,
}

# "Talk" to Arduino containing fridgetemp-x.ino
def fridgetemp_open():
    try:
        ard = serial.Serial(com['port'], com['baud'], com['byte'], com['parity'], com['stop'], com['timeout'], com['onoff'])
    except serial.SerialException as exerr:
        print(cc['err'] + 'No comms with Arduino, check cable/port! ' + com['port'] + ' did not respond\n\r' + str(exerr) + cc['e'])
        return 0
    print('Waiting for Arduino to reset...')
    time.sleep(5) # Wait for the Arduino to boot up
    print("Init::\n\r" + ard.read(ard.inWaiting()).decode("utf-8").strip())
    time.sleep(1)
    return ard

def fridgetemp_read(ard):
    if not ard:
        return 0
    try:
        ard.write('S\n')
        time.sleep(0.5)
        read = ard.read(ard.inWaiting()).decode("utf-8").strip()
        dc = json.loads(read)
        strout = 'Fridge: %s*F, %d%% // Freezer: %s, %d%%' % (dc['T1'], dc['H1'], dc['T2'], dc['H2'])
        print(strout)
        return strout
    except (serial.SerialException, NameError, ValueError) as exceptionerror:
        print(cc['cer'] + str(read) + "\n\r" + str(exceptionerror) + cc['e'])
        return 0

if __name__ == '__main__':
    ftcon = 0
    while 1:
        if not ftcon:
            ftcon = fridgetemp_open()
        fridge = fridgetemp_read(ftcon)
        time.sleep(10)