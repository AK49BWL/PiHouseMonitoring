# Read TMP36 temperature sensors using MCP3008 ADC, read the status of my HVAC system, control my attic fans, output
# data to SSD1306-compliant displays, and log data to file + send to my website
# This script has been written for Python 2.7
# Author: AK49BWL
# Updated: 06/09/2024 11:54

# Imports!
import Adafruit_GPIO.SPI as SPI
from Adafruit_MCP3008 import MCP3008
from Adafruit_SSD1306 import SSD1306_128_64 as SSD1306
import ctypes
import datetime
from gpiozero import Button, CPUTemperature
import gzip
import json
from PIL import Image, ImageDraw, ImageFont
import requests
import RPi.GPIO as GPIO
import serial
import shutil
import smbus
import struct
import threading
import time

# RPi's role in the HVAC system: Receiver, Relay, or Controller
piRole = 'Receiver'

# Modules?
import daviswx # Davis Vantage Pro2 weather center
import gv # Global variables
cc = gv.cc

# Files
logfile = 'history.csv' # Local file for logging temp and HVAC stat data
bkpfile = 'dynbkp.json' # Backup file for variables to reload from last run
wvfile = 'webvars.json' # File for vars changed by website

# File loads
bkp = json.loads(open(bkpfile, 'r').read())
wvl = json.loads(open(wvfile, 'r').read())
# Check files for valid data
try:
    if bkp['saved']:
        print(cc['suc'] + 'Loaded backup file ' + bkpfile + ', last saved ' + bkp['saved'] + cc['e'])
    else:
        bkp = 0
except NameError:
    print(cc['err'] + 'Error loading backup file: No data or data corrupt, resetting values' + cc['e'])
    bkp = 0

# Current date/time array (UnixTime, string, month old and new for log rotation, script start unixtime)
now = { 'u': 0, 's': '', 'om': 0 if not bkp else bkp['om'], 'nm': 0, 'scr': int(time.mktime(datetime.datetime.now().timetuple())) }
firstrun = 1 # For things that need it

# Set up backed-up data vars...
backup = {
    'saved': 0,
    'om': now['om'],
    'num_sens': 0 if not bkp else bkp['num_sens'],
    'lastWebChange': 0 if not bkp else bkp['lastWebChange']
}

# Timers and decrement counters - All timers are in seconds
timer = {
    'cmd': 10, # Main output to console
    'temp': 30, # Temp sensor reads
    'file': 300, # File writes for temp/HVAC data
    'web': 300, # Website data sends
    'loadwebvars': 300, # Update variables from website and repopulate settings dict
    'chkattic': 300, # Checking attic temp for fan toggle
    'display': 60, # Display screens timeout
    'disp_upd': 5, # Display screens update
    'wx': 300, # Weather Center loop read
    'wxminmax': 12, # decreases on run of wxloop, therefore a value of 12 will run wxminmax every hour if wx is set to 300 (5 minutes)
}
dec = { # Decrement vars for timers
    'cmd': 0,
    'temp': 0,
    'file': 0,
    'web': 0,
    'loadwebvars': 150, # Offset this guy from the other 5 minute timers lol
    'chkattic': 15,
    'display': timer['display'],
    'disp_upd': 0,
    'wx': 0,
    'wxminmax': timer['wxminmax'], # Runs on first loop
}
disp = SSD1306(rst=None, i2c_bus = 1, i2c_address=0x3C) # Set up our 128x64 screens
displays = 5 # Number of screens
i2cmulti_reset_pin = 4 # Physical pin 7: GPIO pin 4 for resetting I2C multiplexer
pca3548a=[0b00000001,0b00000010,0b00000100,0b00001000,0b00010000,0b00100000,0b01000000,0b10000000] # I2C Multiplexer channels
disp_act_pin = 25 # Physical pin 22: GPIO pin 25 for button to activate displays
font = ImageFont.load_default() # SSD1306 screen text font

# Init
notes = { 0: 'thermo.py has just started up' } # This message will only be sent on first run
notesi = 1
do_log = 1
display_off = 0
wxdtu = 0 # Weather center update unixtime

# Hardware SPI configuration:
mcp0 = MCP3008(spi=SPI.SpiDev(0, 0)) # SPI Port 0, Device 0
mcp1 = MCP3008(spi=SPI.SpiDev(0, 1)) # SPI Port 0, Device 1

# Attic fans are controlled exclusively by the Pi so we'll use physical pin 40 (GPIO 21) for the relay coil output
# In Receiver and Relay modes, original HVAC thermostat controls the HVAC system so we're receiving its triggers
# Use physical pins 11, 13, 15 (GPIO 17, 27, 22) for A/C, Heat, HFan status receive from the thermostat with pulldown resistors
# In Relay and Controller modes, the Pi will be in control of the output to the HVAC system. Relay mode requires both receive and transmit pins.
# Use physical pins 29, 31, 33 (GPIO 5, 6, 13) for A/C, Heat, HFan control
# Power loss detection is on phys pin 32 (GPIO 12) for detecting whether AC mains power is applied (Pi must be powered by an UPS for this to work!)
hvac = {
    'ac':   { 'rpin': 17, 'tpin': 0,  'stat': 0 if not bkp else bkp['hvac']['ac']['stat'],   'laston': 0 if not bkp else bkp['hvac']['ac']['laston'],   'lastoff': 0 if not bkp else bkp['hvac']['ac']['lastoff'],   'name': 'A/C' },
    'heat': { 'rpin': 27, 'tpin': 0,  'stat': 0 if not bkp else bkp['hvac']['heat']['stat'], 'laston': 0 if not bkp else bkp['hvac']['heat']['laston'], 'lastoff': 0 if not bkp else bkp['hvac']['heat']['lastoff'], 'name': 'Heater' },
    'hfan': { 'rpin': 22, 'tpin': 0,  'stat': 0 if not bkp else bkp['hvac']['hfan']['stat'], 'laston': 0 if not bkp else bkp['hvac']['hfan']['laston'], 'lastoff': 0 if not bkp else bkp['hvac']['hfan']['lastoff'], 'name': 'HVAC Blower' },
    'afan': { 'rpin': 21, 'tpin': 21, 'stat': 0 if not bkp else bkp['hvac']['afan']['stat'], 'laston': 0 if not bkp else bkp['hvac']['afan']['laston'], 'lastoff': 0 if not bkp else bkp['hvac']['afan']['lastoff'], 'name': 'Attic Fan' },
    'Power': { 'rpin': 12, 'tpin': 0,  'stat': 0 if not bkp else bkp['hvac']['Power']['stat'], 'laston': 0 if not bkp else bkp['hvac']['Power']['laston'], 'lastoff': 0 if not bkp else bkp['hvac']['Power']['lastoff'], 'name': 'AC Mains Power' }
}
# Hacky way of setting up the "foreach" array ... A/C being on or not will determine which array gets used for switching and monitoring.
hvs = { 0: ['ac', 'heat', 'afan', 'hfan', 'Power'], 1: ['hfan', 'ac', 'heat', 'afan', 'Power'] }
# Do GPIO setup
GPIO.setwarnings(False) # Disable errors caused by script restarts
GPIO.setmode(GPIO.BCM) # Use Broadcom Pin Numbering rather than the Board Physical Pin Numbering
for h in hvs[0]:
    if hvac[h]['rpin']:
        GPIO.setup(hvac[h]['rpin'], GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    if hvac[h]['tpin']:
        GPIO.setup(hvac[h]['tpin'], GPIO.OUT)
GPIO.setup(disp_act_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# Set up temperature sensor data (Names, Chip and Pin numbers, Enable, dynamic temperature data array, voltage error correction)
sensor = {
    0: { 'p': 0,  'enable': 1, 'temp': {}, 'corr': -3, 'shn': ' Out ', 'con': '\x1b[1;36;44m Out \x1b[0m', 'dispname': 'Outside',      'name': 'Outside (West Wall)' },
    1: { 'p': 8,  'enable': 1, 'temp': {}, 'corr': 0,  'shn': 'Attic', 'con': '\x1b[1;37;41mAttic\x1b[0m', 'dispname': 'Attic',        'name': 'Attic' },
    2: { 'p': 2,  'enable': 1, 'temp': {}, 'corr': 0,  'shn': 'Hall ', 'con': '\x1b[1;32;42mHall \x1b[0m', 'dispname': 'Hallway',      'name': 'Hallway (Thermostat)' },
    3: { 'p': 3,  'enable': 1, 'temp': {}, 'corr': 0,  'shn': 'Vent ', 'con': '\x1b[1;31;44mVent \x1b[0m', 'dispname': 'LivRoom Vent', 'name': 'Living Room HVAC Vent' },
    4: { 'p': 7,  'enable': 1, 'temp': {}, 'corr': 0,  'shn': 'Laund', 'con': 'Laund',                     'dispname': 'Laundry',      'name': 'Laundry Room' },
    5: { 'p': 10, 'enable': 1, 'temp': {}, 'corr': 0,  'shn': 'Kitch', 'con': 'Kitch',                     'dispname': 'Kitchen',      'name': 'Kitchen' },
    6: { 'p': 12, 'enable': 1, 'temp': {}, 'corr': 0,  'shn': 'VR Rm', 'con': 'VR Rm',                     'dispname': 'VR Room',      'name': 'VR Room' },
    7: { 'p': 13, 'enable': 1, 'temp': {}, 'corr': 0,  'shn': 'BedRm', 'con': 'BedRm',                     'dispname': 'Bedroom',      'name': 'Master Bathroom' },
    8: { 'enable': 1, 'temp': {}, 'shn': 'PiCPU', 'con': 'PiCPU', 'name': 'Raspberry Pi CPU' }
}
cpusens = 8

# Set up short-name array for console output
shn = [0]*8
for i in range(8):
    shn[i] = sensor[i]['con']

# Set up log-file sensor header line
schk = 0
xs = 0
sens_str = ['Date','Power','A/C','Heat','HFan','AFan']
while xs < len(sensor):
    if sensor[xs]['enable']:
        schk += 1
        sens_str.append(sensor[xs]['shn'])
    xs += 1
if not schk == backup['num_sens']:
    print('Sensor data changed: ' + str(schk) + ' sensors (old: ' + str(backup['num_sens']) + ')')
    f = open(logfile, 'a')
    f.write('Sensors changed! ' + str(backup['num_sens']) + ' -> ' + str(schk) + '\r\n')
    f.write(','.join(map(str, sens_str)))
    f.write('\r\n')
    f.close()
    backup['num_sens'] = schk

# Get system uptime
libc = ctypes.CDLL('libc.so.6')
buf = ctypes.create_string_buffer(4096)
def systemUpTime():
    if libc.sysinfo(buf) != 0:
        print(cc['err'] + 'Failed to get sysUpTime' + cc['e'])
        return 0
    uptime = struct.unpack_from('@l', buf.raw)[0]
    return uptime

def str_or_int(var):
    try:
        return int(var)
    except ValueError:
        return str(var)

# Send data to website with no expectation of a response
def logToWeb(senddata = {}, dest = 0, retry = 0):
    if not senddata or not dest: # Honestly, this should never happen.
        print(cc['cer'] + 'logToWeb called without proper args!' + cc['e'])
        return 0
    try:
        r = requests.post(gv.webauth['baseURL'] + gv.webauth[dest], data=json.dumps(senddata), timeout=(10,10), headers={'User-Agent': gv.webauth['ua'], 'Content-Type': 'application/json'})
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        print(cc['cer'] + 'Error sending ' + dest + ' data to website: ' + str(e) + cc['e'])
        if retry:
            global dec
            dec[retry] = 60 # Try again in a minute
    else:
        print(cc['snt'] + dest + 'data sent to website! Response: ' + str(r.status_code) + cc['e'])

# Get WebVars from website and set up settings dict
def webvarloader():
    wvl = json.loads(open(wvfile, 'r').read()) # If this fails, well... lol
    try:
        r = requests.get(gv.webauth['baseURL'] + gv.webauth['lwv'], timeout=(10,10), headers={'User-Agent': gv.webauth['ua'], 'Content-Type': 'application/json'})
    except requests.exceptions.ConnectionError:
        print(cc['cer'] + 'Connection error while getting WebVars from the website - Check Pi connectivity' + cc['e'])
    except requests.exceptions.Timeout:
        print(cc['err'] + 'Request timed out trying to get WebVars from the website' + cc['e'])
    else:
        try:
            js = r.json()
            if js['data'] == 'good':
                if not int(js['lastWebChange']) == int(wvl['lastWebChange']): # Let's not bother updating if nothing's changed.
                    f = open(wvfile, 'w')
                    f.write(str(json.dumps(js)))
                    f.close()
                    print(cc['suc'] + 'New WebVars downloaded and saved successfully' + cc['e'])
                    wvl = js # Use updated settings for the second half!
            else:
                print(cc['err'] + 'This JSON data sucks!' + cc['e'])
        except (requests.exceptions.InvalidJSONError, TypeError, NameError, OSError) as exceptionerror:
            print(cc['err'] + 'Error getting WebVars from website, attempting to reuse existing WebVars')
            print(exceptionerror + cc['e'])
    try:
        if firstrun or (int(wvl['lastWebChange']) and not int(wvl['lastWebChange']) == int(backup['lastWebChange'])): # Let's update some vars!
            global setting, notes, notesi, do_log
            wv = dict([(str(k), str_or_int(v)) for k, v in wvl.items()]) # Take care of variable type-casting
            setting = {
                'hvac': { # 1 = Enable, 0 = Disable
                    'ac': 1 if not wv else wv['enable_ac'],
                    'heat': 1 if not wv else wv['enable_heat'],
                    'hfan': 1 if not wv else wv['enable_hfan'],
                    'afan': 1 if not wv else wv['enable_afan']
                },
                'tempRefVolt': 330 if not wv else wv['tempRefVolt'], # 3.3 volt MCP3008 reference, no need to change unless we're vastly changing the hardware ref voltage.
                'tempGlobalCorr': 0 if not wv else wv['tempGlobalCorr'], # Change this instead if we need to fine-tune readings.
                'lastWebChange': 0 if not wv else wv['lastWebChange'],
                'tempLow': 65 if not wv else wv['tempLow'], # Low temperature to turn on Heater
                'tempHigh': 75 if not wv else wv['tempHigh'], # High temperature to turn on A/C
                'tempHyst': 2 if not wv else wv['tempHyst'], # Temperature Hysteresis
                'afanTempOvr': 0 if not wv else wv['afanTempOvr'], # Override low temperature limits for attic fan activation
                'wx': 1 if not wv else wv['wx'], # Enable or disable weather center
            }
            if not firstrun or not wv['lastWebChange'] == backup['lastWebChange']:
                log_stat(to_file = 1, customtext = 'Reloaded webvars last saved ' + wv['lastWebChangeStr'])
                notes[notesi] = 'Reloaded webvars last saved ' + wv['lastWebChangeStr']
                notesi += 1
                do_log = 1
            print(cc['suc'] + 'Reloaded webvars last saved ' + wv['lastWebChangeStr'] + cc['e'])
            backup['lastWebChange'] = wv['lastWebChange']
        else:
            print('WebVars loaded but unchanged from ' + str(wvl['lastWebChangeStr']))
    except (NameError, OSError) as exceptionerror: # Problem? Forget it. Everything is broken.
        print(cc['err'] + 'Error loading webvars, reusing existing values - ' + str(exceptionerror) + cc['e'])
        breakstuff = setting # Kill us completely if setting is not defined because without it, nothing will work.
        log_stat(to_file = 1, customtext = 'Error loading webvars, reusing existing values - ' + str(exceptionerror))

# Turn on or off one system
def turn_on_off(sys, on = 0):
    global hvac, notes, notesi, do_log
    if not hvac[sys]['tpin']:
        print(cc['cer'] + hvac[sys]['name'] + ' does not have a GPIO transmit pin designation!!!' + cc['e'])
        return 0
    # Is the output already in the desired position??? The system status var needs updating!
    if (GPIO.input(hvac[sys]['tpin']) and on) or (not GPIO.input(hvac[sys]['tpin']) and not on):
        print(cc['err'] + hvac[sys]['name'] + ' is already ' + ('on' if on else 'off') + '!' + cc['e'])
        hvac[sys]['stat'] = 1 if GPIO.input(hvac[sys]['tpin']) else 0
        return 0
    # But wait... Is the system in question even enabled?
    if setting['hvac'][sys]:
        print(cc['trn'] + 'Turning ' + hvac[sys]['name'] + ' ' + ('on' if on else 'off') + cc['e'])
        GPIO.output(hvac[sys]['tpin'], GPIO.HIGH if on else GPIO.LOW)
        hvac[sys]['stat'] = 1 if GPIO.input(hvac[sys]['tpin']) else 0
        hvac[sys]['laston' if hvac[sys]['stat'] else 'lastoff'] = now['s']
        notes[notesi] = hvac[sys]['name'] + ' turned ' + ('on' if on else 'off')
        notesi += 1
        do_log = 1

# Update system status
def update_on_off():
    global notes, notesi, do_log
    for s in hvs[hvac['ac']['stat']]:
        if not hvac[s]['rpin']:
            continue
        if (hvac[s]['stat'] and not GPIO.input(hvac[s]['rpin'])) or (not hvac[s]['stat'] and GPIO.input(hvac[s]['rpin'])):
            # Update system var and lastx then log the change
            hvac[s]['stat'] = 1 if GPIO.input(hvac[s]['rpin']) else 0
            hvac[s]['laston' if hvac[s]['stat'] else 'lastoff'] = now['s']
            print(cc['trn'] + hvac[s]['name'] + ' has turned ' + ('on' if hvac[s]['stat'] else 'off') + cc['e'])
            notes[notesi] = hvac[s]['name'] + ' has turned ' + ('on' if hvac[s]['stat'] else 'off')
            notesi += 1
            time.sleep(1) # Wait a moment as there is a delay between multiple HVAC system changes...
            do_log = 1

# Log enabled temperatures and all HVAC status to file and web
def log_stat(to_file = 0, to_web = 0, customtext = 0):
    global dec, sensor
    if to_file:
        print(cc['fh'] + 'Writing ' + ('custom text to ' if customtext else '') + logfile + cc['e'])
        f = open(logfile, 'a')
        if not customtext:
            outstr = [now['s'],hvac['Power']['stat'],hvac['ac']['stat'],hvac['heat']['stat'],hvac['hfan']['stat'],hvac['afan']['stat']]
            xs = 0
            while xs < len(sensor):
                if sensor[xs]['enable']:
                    outstr.append(values['f'][xs])
                xs += 1
            f.write(','.join(map(str, outstr)))
            f.write('\r\n')
            dec['file'] = timer['file']
        else:
            f.write(now['s'] + ',' + customtext + '\r\n')
        f.close()
    if to_web:
        # Create the data array (which is basically literally every variable in this script)
        for x in range(8):
            sensor[x]['temp'] = { 'v': values['v'][x], 'c': values['c'][x], 'f': values['f'][x] }
        backup['hvac'] = hvac
        webdata = {
            'auth': gv.webauth['auth'],
            'backup': backup,
            'date': now,
            'notes': notes,
            'setting': setting,
            'tempdata': sensor,
            'wx': {
                'data': gv.wxData,
                'minmax': gv.wxMinMax,
            }
        }
        print(cc['ws'] + 'Sending data to website' + cc['e'])
        threading.Thread(target=logToWebThr, args=(webdata,)).start() # Fire away fro fro fro fro from this place that we call home...
        dec['web'] = timer['web']

        # Back up the current system status dynamic variable array.
        backup['saved'] = now['s']
        bkpf = open(bkpfile, 'w')
        bkpf.write(json.dumps(backup))
        bkpf.close()
        print(cc['fbu'] + 'Wrote ' + bkpfile + cc['e'])
def logToWebThr(sd): # Forwarder because threading doesn't like my args lol
    logToWeb(senddata = sd, dest = 'log', retry = 'web')

# For log rotation - compresses history logfile into a .gz with year and month, then clears history.csv for the new month
def rotatelogs():
    with open(logfile, 'r') as f_in:
        with gzip.open('history-' + now['om'] + '.csv.gz', mode='w', compresslevel=9) as f_out:
            shutil.copyfileobj(f_in, f_out)
    f_in.close()
    open(logfile, 'w').close()
    f = open(logfile, 'a')
    f.write(','.join(map(str, sens_str)))
    f.write('\r\n')
    f.close()
    print(cc['fbu'] + 'Log File gzipped and erased' + cc['e'])

# Get weather center data
def wxloop(minmax = 0):
    try:
        gv.wx = daviswx.openWxComm()
        thing = daviswx.readWxData()
        if thing: # Everything seems to be working, send it to the website
            global wxdtu
            gv.wxData['auth'] = gv.webauth['auth']
            gv.wxData['now_s'] = now['s']
            gv.wxData['now_u'] = wxdtu = now['u']
            logToWeb(senddata = gv.wxData, dest = 'wxd')
            gv.wxFail = 0
            setting['wx'] = 1
            if minmax:
                daviswx.readWxHL()
                gv.wxMinMax['now_s'] = now['s']
                gv.wxMinMax['now_u'] = now['u']
            return 1
    except (serial.SerialException, TypeError, NameError) as e:
        print(cc['cer'] + 'Wx broke: ' + str(e) + cc['e'])
    print(cc['err'] + 'Weather center data for this iteration not saved' + cc['e'])
    gv.wxFail += 1
    dec['wx'] = 60
    if gv.wxFail >= 10: # If weather center is not responding for an extended period, just stop trying until the problem is fixed
        print(cc['cer'] + 'Weather center data check disabled due to multiple failures' + cc['e'])
        setting['wx'] = 0

# Switch between the (T/P)CA3548A I2C Multiplexer channels and reset
def i2cmulti_switch(mp_addr = 0x70, i2c_chan = 0):
    smbus.SMBus(1).write_byte(mp_addr, pca3548a[i2c_chan])
    # print('TCA9548A I2C channel status:', bin(smbus.SMBus(1).read_byte(mp_addr)))
def i2cmulti_reset():
    GPIO.setup(i2cmulti_reset_pin, GPIO.OUT)
    GPIO.output(i2cmulti_reset_pin, GPIO.LOW)
    time.sleep(0.01)
    GPIO.setup(i2cmulti_reset_pin, GPIO.IN)

# Clear all SSD1306 displays
def cleardisplays():
    for i in range(displays):
        i2cmulti_switch(i2c_chan = i)
        disp.clear()
        disp.display()
    i2cmulti_reset()

# Send data to the screens
def updatedisplays():
    for i in range(displays):
        i2cmulti_switch(i2c_chan = i)
        # Init and clear display
        disp.begin()
        # Create image
        image = Image.new('1', (128, 64))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0,0,128,64), outline=0, fill=0)
        # Text -- max characters per line is 21, max 8 lines at 8 pixel line height (padding -2)
        p = -8
        for j in range(8):
            p += 8
            if not dispdata[i][j]:
                continue
            draw.text((0, -2 + p), dispdata[i][j], font=font, fill=255)
        disp.image(image)
        disp.display() # Show!
    i2cmulti_reset()

webvarloader() # Populate settings dict before jumping into things
# Main loop
while 1:
    # Press a button to re-enable the 128x64 screens when they're sleeping
    if GPIO.input(disp_act_pin) and display_off:
        dec['display'] = timer['display']
        display_off = 0
        i2cmulti_switch(i2c_chan = 2)
        image = Image.open('happycat_oled_64.ppm').convert('1') # Hehe *Flash*
        disp.image(image)
        disp.display()
        i2cmulti_reset()

    # Reload WebVars
    if not dec['loadwebvars']:
        dec['loadwebvars'] = timer['loadwebvars']
        threading.Thread(target=webvarloader).start()
    dec['loadwebvars'] -= 1

    # Current date and time
    now['s'] = datetime.datetime.now().strftime('%b %d %Y %H:%M:%S')
    now['u'] = int(time.mktime(datetime.datetime.now().timetuple()))
    now['sut'] = systemUpTime()
    now['nm'] = datetime.datetime.now().strftime('%Y%m')
    if not now['om'] == 0 and not now['nm'] == now['om']:
        rotatelogs()
        now['om'] = backup['om'] = now['nm']

    # Update weather center data
    if not dec['wx']:
        dec['wx'] = timer['wx']
        if firstrun:
            wxloop(minmax = 1) # No subthread for the first run, and we want all the data
        elif setting['wx']:
            if not dec['wxminmax']:
                threading.Thread(target=wxloop, args=({'minmax': 1},)).start()
                dec['wxminmax'] = timer['wxminmax']
            else:
                threading.Thread(target=wxloop).start()
        dec['wxminmax'] -= 1
    dec['wx'] -= 1

    # Check status of HVAC systems
    update_on_off()

    # Temperature stuff
    if not dec['temp']:
        # Initialize temperature value array - this has to come before anything else otherwise values will be undefined!
        values = { 'v': {}, 'c': {}, 'f': {} }
        pr_v = [0]*8
        pr_c = [0]*8
        pr_f = [0]*8
        # Get TMP36 sensor data
        for i in range(8):
            pr_v[i] = values['v'][i] = (mcp0.read_adc(sensor[i]['p']) if sensor[i]['p'] < 8 else mcp1.read_adc(sensor[i]['p']-8)) + setting['tempGlobalCorr'] + sensor[i]['corr'] # Get the voltage value of the channels from both MCP3008 ADC chips, adjusting as needed
            pr_c[i] = values['c'][i] = round(((values['v'][i] * setting['tempRefVolt']) / 1024.0) -50.0, 1) # Conversion to Celsius: MCP3008 Ref voltage / 10-bit ADC - TMP36 sensor 0-value is -50*C
            pr_f[i] = values['f'][i] = round((values['c'][i] * 1.8) + 32, 1) # Conversion to Fahrenheit
        t_out = pr_f[0]
        t_in = pr_f[2]
        t_attic = pr_f[1]
        t_use = 'TMP36 Temp Sensors'
        # Get Pi CPU Temperature and convert to Fahrenheit
        sensor[cpusens]['temp']['c'] = values['c'][cpusens] = round(CPUTemperature().temperature, 1)
        sensor[cpusens]['temp']['f'] = values['f'][cpusens] = round((values['c'][cpusens] * 1.8) + 32, 1)

        # If weather center data is up-to-date within a 15 minute leeway, use its inside and outside temperatures for HVAC system checks... If it's receiving data from the outdoor unit!
        if wxdtu > now['u'] - 900 and not gv.wxData['ISSerror']:
            t_out = gv.wxData['tempOut'] if gv.wxData['tempOut'] < 3200 else pr_f
            t_in = gv.wxData['tempIn']
            t_use = 'Davis Weather Center'

    if not dec['cmd']:
        print(now['s'] + ' -- Pi Uptime: ' + str(datetime.timedelta(seconds=now['sut'])) + ' -- Script Runtime: ' + str(datetime.timedelta(seconds=now['u'] - now['scr'])) + ' -- CPU Temp: ' + str(values['f'][cpusens]) + '*F')

    # Check attic temp for fans
    if not dec['chkattic']:
        dec['chkattic'] = timer['chkattic']
        if not hvac['afan']['stat']:
            if t_attic - 5 > t_out and setting['hvac']['afan'] and (setting['afanTempOvr'] or (t_out > 68 and t_in > 68)): # If attic temp is 5+ degrees over outside temp (and both outside and inside temps are above 68 degrees), turn fans on if enabled
                turn_on_off('afan', 1)
        else:
            if t_attic - 3 < t_out or not setting['hvac']['afan'] or (not setting['afanTempOvr'] and t_out < 65 and t_in < 65): # Turn fans off when attic temp reaches below 3 degrees over outside temp, or when outside and inside temp drops below 65
                turn_on_off('afan', 0)
    dec['chkattic'] -= 1

    # Write csv logfile
    if not dec['file'] or do_log:
        log_stat(to_file = 1)
    dec['file'] -= 1
    # Send all current data to the website
    if not dec['web'] or do_log:
        log_stat(to_web = 1)
    dec['web'] -= 1

    # Print current status of systems
    if not dec['cmd']:
        dec['cmd'] = timer['cmd']
        print('A/C is ' + (cc['dis'] if not setting['hvac']['ac'] else cc['on'] if hvac['ac']['stat'] else cc['off']) + ', Heater is ' + (cc['dis'] if not setting['hvac']['heat'] else cc['on'] if hvac['heat']['stat'] else cc['off']) + ', HVAC Blower is ' + (cc['dis'] if not setting['hvac']['hfan'] else cc['on'] if hvac['hfan']['stat'] else cc['off']) + ', Attic Fan is ' + (cc['dis'] if not setting['hvac']['afan'] else cc['on'] if hvac['afan']['stat'] else cc['off']) + ', AC Power is ' + (cc['on'] if hvac['Power']['stat'] else cc['off']))
    dec['cmd'] -= 1

    if not dec['temp']:
        dec['temp'] = timer['temp']
        # Print the MCP3008 values to terminal last that way all other output is written first
        print('| {} | {} | {} | {} | {} | {} | {} | {} |'.format(*shn))
        print('| {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} |'.format(*pr_v)) # Show raw ADC values
        # print('| {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} |'.format(*pr_c)) # Show Celsius
        print('| {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} |'.format(*pr_f)) # Show Fahrenheit
        # Also print WxData temps and which the system is using currently
        print('WxData Inside Temp: ' + str(gv.wxData['tempIn']) + '*F, Outside Temp: ' + str(gv.wxData['tempOut']) + '*F, currently using ' + t_use + ' for HVAC control')

    # Send output to 128x64 screens if they're not sleeping
    if dec['display']:
        if dec['temp'] > timer['disp_upd']:
            dec['temp'] = timer['disp_upd']
        if not dec['disp_upd']:
            dec['disp_upd'] = timer['disp_upd'] # Override the temperature sensor update interval if we're watching the screens
            dispdata = {}
            for d in range(displays):
                dispdata[d] = {0:0,1:0,2:0,3:0,4:0,5:0,6:0,7:0} # All variables will have data, even if they won't be displayed.
            # Screen 1 will give us the date and time, Pi CPU Temp, and Power status
            dispdata[0][0] = now['s']
            dispdata[0][2] = 'Pi: ' + str(sensor[cpusens]['temp']['c']) + '*C (' + str(sensor[cpusens]['temp']['f']) + '*F)'
            dispdata[0][4] = 'AC Mains Power is ' + ('On' if hvac['Power']['stat'] else 'Off')
            # We'll use screens 2 and 3 to output all the temperature sensor data
            for d in range(1, 2): # range(1, 3) if using 16 temp sensors, else screen 3 will be blank
                for e in range(8):
                    dispdata[d][e] = str(sensor[e if d == 1 else e + 8]['dispname']) + ': ' + str('--' if pr_f[e if d == 1 else e + 8] <= -50 else pr_f[e if d == 1 else e + 8])
            # Screen 4 will show HVAC status
            e = 0
            for s in hvs[0]:
                dispdata[3][e] = hvac[s]['name'] + ' is ' + ('on' if hvac[s]['stat'] else 'off')
                dispdata[3][e+1] = 'Last ' + ('off' if hvac[s]['stat'] else 'on')
                e += 2
            # Screen 5 will show recent HVAC runtimes
            e = 0
            for s in hvs[0]:
                dispdata[4][e] = hvac[s]['laston' if hvac[s]['stat'] else 'lastoff']
                dispdata[4][e+1] = hvac[s]['lastoff' if hvac[s]['stat'] else 'laston']
                e += 2
            threading.Thread(target=updatedisplays).start() # Send it! In its own thread even!
        dec['display'] -= 1
        dec['disp_upd'] -= 1
    elif not display_off:
        cleardisplays()
        display_off = 1

    # Reset and update vars
    dec['temp'] -= 1
    notes = {}
    notesi = 0
    do_log = 0
    firstrun = 0

    time.sleep(1)