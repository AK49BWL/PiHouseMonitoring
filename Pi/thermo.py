# Read TMP36 temperature sensors using MCP3008 ADC, read the status of my HVAC system, control my attic fans, output
# data to SSD1306-compliant displays, and log data to file + send to my website
# This script has been written for Python 2.7
# Author: AK49BWL
# Updated: 10/01/2023 17:10

# TO DO: Create AC power loss reaction function? Auto-shutdown pi and UPS unit on power loss after x minutes or something. The UPS should be able to last at least 10 minutes, or at least I'd like to think so.

# Imports!
import Adafruit_GPIO.SPI as SPI
from Adafruit_MCP3008 import MCP3008
from Adafruit_SSD1306 import SSD1306_128_64 as SSD1306
import datetime
from gpiozero import Button, CPUTemperature
import gzip
import json
from PIL import Image, ImageDraw, ImageFont
import requests
import RPi.GPIO as GPIO
import shutil
import smbus
import threading
import time

# Init
slp = 5 # Time in seconds to wait between loop runs
fwt = round(300 / slp, 0) # Set number to desired seconds between file writes (Current: 5 minutes)
webt = round(600 / slp, 0) # Set number to desired seconds between website requests (Current: 10 minutes)
chkattict = round(300 / slp, 0) # Set number to desired seconds between checking attic temp for fan toggle (Current: 5 minutes)
display_on = round(60 / slp, 0) # Screens will stay active for 1 minute before sleeping
logfile = 'history.csv' # Local file for logging temp and HVAC stat data
bkpfile = 'dynbkp.json' # Backup file for dynamic variables to reload on script restart
disp = SSD1306(rst=None, i2c_bus = 1, i2c_address=0x3C) # Set up our 128x64 screens
displays = 5 # Number of screens
i2cmulti_reset_pin = 4 # GPIO pin for resetting I2C multiplexer
disp_act_pin = 25 # GPIO pin for button to activate displays
pca3548a=[0b00000001,0b00000010,0b00000100,0b00001000,0b00010000,0b00100000,0b01000000,0b10000000] # I2C Multplexer channels
font = ImageFont.load_default() # SSD1306 screen text font
fw = 0
web = 0
chkattic = 0
display_off = 0
do_log = 1
notesi = 1
notes = { 0: 'thermo.py has just started up' } # This message will only be sent on first run

# Load Webdata auth stuff
toWeb = json.loads(open('codes.json', 'r').read())
# Backup dynamic variable file load BEFORE INITIALIZING DYNAMICALLY CHANGED VARIABLES! (If there's no data in the file, just write {"0":"0"} in the file so this code will at least load it)
bkp = json.loads(open(bkpfile, 'r').read())
# Is the backup data valid?
try:
    if bkp['xdata']['saved']:
        print("Loading dynamic system variables from backup file %s, last saved %s" % (bkpfile, bkp['xdata']['saved'])) # Variable initialization below will use these values.
    else:
        bkp = 0
except NameError:
    print("Error loading dynamic backup: No data in backup or data corrupt, resetting values")
    bkp = 0
now = { 'u': 0, 's': '', 'om': 0 if not bkp else bkp['xdata']['om'], 'nm': 0 } # Current date/time array (UnixTime, string, month old and new for log rotation)

# Setup MakerHawk UPS+ EP-0136
ups = { 'enable': 0, 'set': { 'samp': 5, 'v_full': 4150, 'v_empt': 3400, 'v_prot': 3500, 'ac_rec': 1, 'cd': 120 }, 'data': { 'sup': {}, 'bat': {}, 'main': { 'data_received': 0 } }, 'read': [0x00] }
if ups['enable']:
    from ina219 import INA219, DeviceRangeError
    smbus.SMBus(1).write_byte_data(0x17, 13, ups['set']['v_full'] & 0xFF) # Battery full voltage
    smbus.SMBus(1).write_byte_data(0x17, 14, (ups['set']['v_full'] >> 8) & 0xFF)
    smbus.SMBus(1).write_byte_data(0x17, 15, ups['set']['v_empt'] & 0xFF) # Battery empty voltage
    smbus.SMBus(1).write_byte_data(0x17, 16, (ups['set']['v_empt'] >> 8) & 0xFF)
    smbus.SMBus(1).write_byte_data(0x17, 17, ups['set']['v_prot'] & 0xFF) # Battery protection voltage
    smbus.SMBus(1).write_byte_data(0x17, 18, (ups['set']['v_prot'] >> 8) & 0xFF)
    smbus.SMBus(1).write_byte_data(0x17, 21, ups['set']['samp'] & 0xFF) # Battery sampling interval
    smbus.SMBus(1).write_byte_data(0x17, 22, (ups['set']['samp'] >> 8) & 0xFF)
    smbus.SMBus(1).write_byte_data(0x17, 24, 0) # Shutdown timer
    smbus.SMBus(1).write_byte_data(0x17, 25, ups['set']['ac_rec']) # Auto Power-Up on AC Restore
    smbus.SMBus(1).write_byte_data(0x17, 26, 0) # Restart timer
    smbus.SMBus(1).write_byte_data(0x17, 42, 1) # Battery programming set by user (I don't know what this is tbh but whatever)
    print "UPS configuration updated"

# Hardware SPI configuration:
mcp0 = MCP3008(spi=SPI.SpiDev(0, 0)) # SPI Port 0, Device 0
mcp1 = MCP3008(spi=SPI.SpiDev(0, 1)) # SPI Port 0, Device 1
GPIO.setwarnings(False) # Disable errors caused by script restarts...
GPIO.setmode(GPIO.BCM) # Use Broadcom Pin Numbering rather than the Board Physical Pin Numbering
# Attic fans are controlled by the Pi so we'll use physical pin 40 (GPIO 21) for the relay coil output.
# Original HVAC thermostat is still in control of the HVAC system so we're just receiving its triggers.
# Use physical pins 11, 13, 15 (GPIO 17, 27, 22) for A/C, Heat, HFan status receive with pulldown resistors.
system = {
    'ac':   { 'pin': 17, 'stat': 0 if not bkp else bkp['ac']['stat'],   'laston': 0 if not bkp else bkp['ac']['laston'],   'lastoff': 0 if not bkp else bkp['ac']['lastoff'],   'name': 'A/C' },
    'heat': { 'pin': 27, 'stat': 0 if not bkp else bkp['heat']['stat'], 'laston': 0 if not bkp else bkp['heat']['laston'], 'lastoff': 0 if not bkp else bkp['heat']['lastoff'], 'name': 'Heater' },
    'hfan': { 'pin': 22, 'stat': 0 if not bkp else bkp['hfan']['stat'], 'laston': 0 if not bkp else bkp['hfan']['laston'], 'lastoff': 0 if not bkp else bkp['hfan']['lastoff'], 'name': 'HVAC Blower' },
    'afan': { 'pin': 21, 'stat': 0 if not bkp else bkp['afan']['stat'], 'laston': 0 if not bkp else bkp['afan']['laston'], 'lastoff': 0 if not bkp else bkp['afan']['lastoff'], 'name': 'Attic Fan' },
    'xdata': { 'saved': 0, 'om': now['om'], 'num_sensors': 0 if not bkp else bkp['xdata']['num_sensors'] }
}
GPIO.setup(system['afan']['pin'], GPIO.OUT)
GPIO.setup(system['hfan']['pin'], GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(system['ac']['pin'], GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(system['heat']['pin'], GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(disp_act_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# Set up temperature sensor data (Names, Chip and Pin numbers, Enable, dynamic temperature data array, voltage error correction)
sensor = {
    0:  { 'ch': 0, 'p': 0, 'enable': 1, 'temp': {}, 'corr': 0, 'shn': ' Out ', 'dispname': 'Outside', 'name': 'Outside (West Wall)' },
    1:  { 'ch': 0, 'p': 1, 'enable': 0, 'temp': {}, 'corr': 0, 'shn': '  2  ', 'dispname': 'N/C', 'name': '' },
    2:  { 'ch': 0, 'p': 2, 'enable': 1, 'temp': {}, 'corr': 0, 'shn': 'Hall ', 'dispname': 'Hallway', 'name': 'Hallway (Thermostat)' },
    3:  { 'ch': 0, 'p': 3, 'enable': 1, 'temp': {}, 'corr': 0, 'shn': ' A/C ', 'dispname': 'LivRoom Vent', 'name': 'Living Room HVAC Vent' },
    4:  { 'ch': 0, 'p': 4, 'enable': 0, 'temp': {}, 'corr': 0, 'shn': '  5  ', 'dispname': 'N/C', 'name': '' },
    5:  { 'ch': 0, 'p': 5, 'enable': 0, 'temp': {}, 'corr': 0, 'shn': '  6  ', 'dispname': 'N/C', 'name': '' },
    6:  { 'ch': 0, 'p': 6, 'enable': 0, 'temp': {}, 'corr': 0, 'shn': '  7  ', 'dispname': 'N/C', 'name': '' },
    7:  { 'ch': 0, 'p': 7, 'enable': 1, 'temp': {}, 'corr': 0, 'shn': 'Laund', 'dispname': 'Laundry', 'name': 'Laundry Room' },
    8:  { 'ch': 1, 'p': 0, 'enable': 1, 'temp': {}, 'corr': 0, 'shn': 'Attic', 'dispname': 'Attic', 'name': 'Attic' },
    9:  { 'ch': 1, 'p': 1, 'enable': 0, 'temp': {}, 'corr': 0, 'shn': ' 1 0 ', 'dispname': 'N/C', 'name': '' },
    10: { 'ch': 1, 'p': 2, 'enable': 1, 'temp': {}, 'corr': 0, 'shn': 'Kitch', 'dispname': 'Kitchen', 'name': 'Kitchen' },
    11: { 'ch': 1, 'p': 3, 'enable': 0, 'temp': {}, 'corr': 0, 'shn': ' 1 2 ', 'dispname': 'N/C', 'name': '' },
    12: { 'ch': 1, 'p': 4, 'enable': 1, 'temp': {}, 'corr': 0, 'shn': 'VR Rm', 'dispname': 'VR Room', 'name': 'VR Room' },
    13: { 'ch': 1, 'p': 5, 'enable': 1, 'temp': {}, 'corr': 0, 'shn': 'BedRm', 'dispname': 'Bedroom', 'name': 'Master Bathroom' },
    14: { 'ch': 1, 'p': 6, 'enable': 0, 'temp': {}, 'corr': 0, 'shn': ' 1 5 ', 'dispname': 'N/C', 'name': '' },
    15: { 'ch': 1, 'p': 7, 'enable': 0, 'temp': {}, 'corr': 0, 'shn': ' 1 6 ', 'dispname': 'N/C', 'name': '' },
    16: { 'enable': 1, 'temp': {}, 'shn': 'PiCPU', 'name': 'Raspberry Pi CPU' },
}
cpusens = 16
# The MakerHawk UPS+ causes problems with the temp sensors, likely due to different voltage supply from the UPS vs the direct power supply... Possibly need to change the reference voltage? Anyway we need a global voltage fix for now.
tempGlobalCorr = 0 if not ups['enable'] else -18

# Set up short-name array for console output
shn = [0]*16
for i in range(16):
    shn[i] = sensor[i]['shn']

# Set up log-file sensor header line
schk = 0
xs = 0
sens_str = ['Date','A/C','Heat','HFan','AFan']
while xs < len(sensor):
    if sensor[xs]['enable']:
        schk += 1
        sens_str.append(sensor[xs]['shn'])
    xs += 1
if not schk == system['xdata']['num_sensors']:
    print('Sensor data changed: %s sensors (old: %s)' % (schk, system['xdata']['num_sensors']))
    f = open(logfile, "a")
    f.write("Sensors changed! %s -> %s\r\n" % (system['xdata']['num_sensors'], schk))
    f.write(",".join(map(str, sens_str)))
    f.write("\r\n")
    f.close()
    system['xdata']['num_sensors'] = schk

# Set up the website request threading system
def to_web(senddata):
    global web
    try:
        r = requests.post(toWeb['url'], data=json.dumps(senddata), timeout=(10,10), headers={'User-Agent': toWeb['ua'], 'Content-Type': 'application/json'})
    except requests.exceptions.ConnectionError:
        print('Connection error - Check Pi connectivity')
        log_stat(to_file = 1, customtext = 'Unable to send data to website due to connection error - Check Pi connectivity')
        web = round(60 / slp, 0) # Try again in a minute
    except requests.exceptions.Timeout:
        print('Request timed out trying to send data to the website')
        log_stat(to_file = 1, customtext = 'Unable to send data to website due to request timeout')
        web = round(60 / slp, 0)
    else:
        print('Data sent to website! Response: %s' % (r.status_code))
def fire_and_forget(senddata):
    threading.Thread(target=to_web, args=(senddata,)).start()

# Turn on or off one system
def turn_on_off(sys, on = 0):
    global system, notes, notesi, do_log
    # Is the output already in the desired position??? The system status var needs updating!
    if (GPIO.input(system[sys]['pin']) and on) or (not GPIO.input(system[sys]['pin']) and not on):
        print("%s is already %s!" % (system[sys]['name'], 'on' if on else 'off'))
        system[sys]['stat'] = 1 if GPIO.input(system[sys]['pin']) else 0
        return 0
    print("Turning %s %s" % (system[sys]['name'], 'on' if on else 'off'))
    GPIO.output(system[sys]['pin'], GPIO.HIGH if on else GPIO.LOW)
    system[sys]['stat'] = 1 if GPIO.input(system[sys]['pin']) else 0
    system[sys]['laston' if system[sys]['stat'] else 'lastoff'] = now['s']
    notes[notesi] = "%s turned %s" % (system[sys]['name'], 'on' if on else 'off')
    notesi += 1
    do_log = 1

# Update system status
def update_on_off():
    global system, notes, notesi, do_log
    for s in ['ac', 'heat', 'hfan', 'afan']:
        if (system[s]['stat'] and not GPIO.input(system[s]['pin'])) or (not system[s]['stat'] and GPIO.input(system[s]['pin'])):
            # Update system var and lastx then log the change
            system[s]['stat'] = 1 if GPIO.input(system[s]['pin']) else 0
            system[s]['laston' if system[s]['stat'] else 'lastoff'] = now['s']
            print("%s has turned %s" % (system[s]['name'], 'on' if system[s]['stat'] else 'off'))
            notes[notesi] = "%s has turned %s" % (system[s]['name'], 'on' if system[s]['stat'] else 'off')
            notesi += 1
            time.sleep(0.5) # Wait a moment as there is a delay between multiple HVAC system changes...
            do_log = 1

# Log enabled temperatures and all HVAC status to file and web
def log_stat(to_file = 0, to_web = 0, customtext = 0):
    global fw, web, sensor
    if to_file:
        print("Writing %s" % (logfile))
        f = open(logfile, "a")
        if not customtext:
            outstr = [now['s'],system['ac']['stat'],system['heat']['stat'],system['hfan']['stat'],system['afan']['stat']]
            xs = 0
            while xs < len(sensor):
                if sensor[xs]['enable']:
                    outstr.append(values['f'][xs])
                xs += 1
            f.write(",".join(map(str, outstr)))
            f.write("\r\n")
            fw = fwt
        else:
            f.write("%s,%s\r\n" % (now['s'],customtext))
        f.close()
    if to_web:
        print('Sending data to website')
        # Create the data array (which is basically literally every variable in this script)
        for x in range(16):
            sensor[x]['temp'] = { 'v': values['v'][x], 'c': values['c'][x], 'f': values['f'][x] }
        webdata = {
            'date': now,
            'sys': system,
            'tempdata': sensor,
            'notes': notes,
            'ups': ups,
            'auth': toWeb['auth']
        }
        fire_and_forget(webdata) # Fire away fro fro fro fro from this place that we call home...
        web = webt

        # Back up the current system status dynamic variable array.
        system['xdata']['saved'] = now['s']
        bkpf = open(bkpfile, "w")
        bkpf.write(json.dumps(system))
        bkpf.close()
        print("Wrote %s" % (bkpfile))

# For log rotation - compresses history logfile into a .gz with year and month, then clears history.csv for the new month
def rotatelogs():
    with open(logfile, 'r') as f_in:
        with gzip.open("history-%s.csv.gz" % (now['om']), mode='w', compresslevel=9) as f_out:
            shutil.copyfileobj(f_in, f_out)
    f_in.close()
    # open(logfile, 'w').close() # Let's not delete the old log just yet until we know for a 100% fact this gzipping thing actually works. Give it two months of manually resetting and we'll enable this.
    f = open(logfile, 'a')
    f.write(",".join(map(str, sens_str)))
    f.write("\r\n")
    f.close()
    print("Log File gzipped and erased")

# Create function for switching between the (T/P)CA3548A I2C Multiplexer channels and reset
def i2cmulti_switch(mp_addr = 0x70, i2c_chan = 0):
    smbus.SMBus(1).write_byte(mp_addr, pca3548a[i2c_chan])
    # print("TCA9548A I2C channel status:", bin(smbus.SMBus(1).read_byte(mp_addr)))
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

# Send data to the screens (in a sub-thread)
def updatedisplaysthr():
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
def updatedisplays():
    threading.Thread(target=updatedisplaysthr).start()

# Main loop
while True:
    # Press a button to re-enable the 128x64 screens when they're sleeping
    if GPIO.input(disp_act_pin) and display_off:
        display_on = round(60 / slp, 0)
        display_off = 0
        i2cmulti_switch(i2c_chan = 2)
        image = Image.open('happycat_oled_64.ppm').convert('1') # Hehe *Flash*
        disp.image(image)
        disp.display()
        i2cmulti_reset()

    # Current date and time
    now['s'] = datetime.datetime.now().strftime("%b %d %Y %H:%M:%S")
    now['u'] = int(time.mktime(datetime.datetime.now().timetuple()))
    now['nm'] = datetime.datetime.now().strftime("%Y%m")
    if not now['om'] == 0 and not now['nm'] == now['om']:
        rotatelogs()
    now['om'] = system['xdata']['om'] = datetime.datetime.now().strftime("%Y%m") # Also save to system for backup purposes

    # Initialize temperature value array - this has to come before anything else otherwise values will be undefined!
    values = { 'v': {}, 'c': {}, 'f': {} }
    pr_v = [0]*16
    pr_c = [0]*16
    pr_f = [0]*16
    # Get TMP36 sensor data
    for i in range(16):
        pr_v[i] = values['v'][i] = (mcp0.read_adc(i) if i < 8 else mcp1.read_adc(i-8)) + sensor[i]['corr'] # Get the voltage value of the channels from both MCP3008 ADC chips, correcting errors as needed
        pr_c[i] = values['c'][i] = round(((values['v'][i] * 330.0) / 1024.0) -50.0, 1) # Conversion to Celsius: Ref voltage is 3.3, 10-bit ADC, TMP36 sensor 0-value is -50*C
        pr_f[i] = values['f'][i] = round((values['c'][i] * 1.8) + 32, 1) # Conversion to Fahrenheit
    # Get Pi CPU Temperature and convert to Fahrenheit
    sensor[cpusens]['temp']['c'] = values['c'][cpusens] = round(CPUTemperature().temperature, 1)
    sensor[cpusens]['temp']['f'] = values['f'][cpusens] = round((values['c'][cpusens] * 1.8) + 32, 1)
    print('%s - Pi CPU Temp: %s*C (%s*F)' % (now['s'],values['c'][cpusens],values['f'][cpusens]))

    # Check status of HVAC systems
    update_on_off()

    # Check attic temperature compared to outdoor temperature
    if chkattic == 0:
        if not system['afan']['stat']:
            if values['f'][8] - 5 > values['f'][0] and values['f'][0] > 68: # If attic temp is 5+ degrees over outside temp (and outside temp is above 68 degrees), turn fans on.
                turn_on_off('afan', 1)
        else:
            if values['f'][8] - 3 < values['f'][0]: # Turn fans off when attic temp reaches below 3 degrees over outside temp.
                turn_on_off('afan', 0)
        chkattic = chkattict

    # Get data from MakerHawk UPS+ if enabled
    if ups['enable']:
        v_sup = INA219(0.00725, busnum=1, address=0x40) # Pi Power supply output
        v_sup.configure()
        ups['data']['sup'] = { 'v': v_sup.voltage(), 'a': round(v_sup.current(), 3) }
        v_bat = INA219(0.005, busnum=1, address=0x45) # Battery
        v_bat.configure()
        try:
            ups['data']['bat']['v'] = v_bat.voltage()
            ups['data']['bat']['a'] = round(v_bat.current(), 3)
            ups['data']['bat']['chg'] = "Charging" if ups['data']['bat']['a'] > 0 else "Discharging"
        except DeviceRangeError:
            ups['data']['bat']['chg'] = "Error"
            ups['data']['bat']['a'] = 0
            notes[notesi] = "UPS Battery current too high or not readable"
            notesi += 1
            print("UPS Battery current too high or not readable")
            log_stat(to_file = 1, customtext = 'UPS Battery current too high or not readable')
        ups['read'] = [0x00]
        try:
            for i in range(1, 43):
                ups['read'].append(smbus.SMBus(1).read_byte_data(0x17, i))
            i2cnr = 0
        except IOError:
            print "UPS not responding to data query at ID %d" % (i)
            i2cnr = ups['data']['main']['i2cnr'] = 1
            if not ups['data']['main']['data_received']: # Possibility of failure on first read... Might as well zero everything out.
                for i in range(0, 43):
                    ups['read'] = 0
        if not ups['data']['main']['data_received'] or not i2cnr:
            ups['data']['main'] = {
                'date': now['s'],
                'v_cpu': "%d" % (ups['read'][2] << 8 | ups['read'][1]), # CPU mV
                'v_pi': "%d" % (ups['read'][4] << 8 | ups['read'][3]), # mV output to RPi
                'v_chgC': "%d" % (ups['read'][8] << 8 | ups['read'][7]), # USB C input mV
                'v_chgM': "%d" % (ups['read'][10] << 8 | ups['read'][9]), # MicroUSB input mV
                'battTempC': "%d" % (ups['read'][12] << 8 | ups['read'][11]), # Battery temp (estimated) Celsius
                'v_battFull': "%d" % (ups['read'][14] << 8 | ups['read'][13]), # Full battery mV
                'v_battEmpt': "%d" % (ups['read'][16] << 8 | ups['read'][15]), # Empty battery mV
                'v_battProt': "%d" % (ups['read'][18] << 8 | ups['read'][17]), # Battery protection mV
                'battCap': "%d" % (ups['read'][20] << 8 | ups['read'][19]), # Remaining battery capacity %
                'samp': "%d" % (ups['read'][22] << 8 | ups['read'][21]), # Resampling rate in minutes
                'stat': "%d" % (ups['read'][23]), # UPS status (on or off)
                'c_sd': "%d" % (ups['read'][24]), # Shutdown timer in seconds
                'c_rs': "%d" % (ups['read'][26]), # Restart timer in seconds
                'restore': "%d" % (ups['read'][25]), # A/C power loss auto-restore
                'run_total': "%d" % (ups['read'][31] << 24 | ups['read'][30] << 16 | ups['read'][29] << 8 | ups['read'][28]), # Total accumulated UPS runtime in seconds
                'run_chg': "%d" % (ups['read'][35] << 24 | ups['read'][34] << 16 | ups['read'][33] << 8 | ups['read'][32]), # Total accumulated UPS charging time in seconds
                'run_sess': "%d" % (ups['read'][39] << 24 | ups['read'][38] << 16 | ups['read'][37] << 8 | ups['read'][36]), # Total runtime this power on session in seconds
                'usr_batt': "%d" % (ups['read'][42]), # Battery parameters custom set by user
                'i2cnr': i2cnr,
                'data_received': 1
            }

    # Write csv logfile
    if fw == 0 or do_log:
        log_stat(to_file = 1)
    # Send all current data to the website
    if web == 0 or do_log:
        log_stat(to_web = 1)

    # Print current status of systems
    print('A/C is %s, Heater is %s, HVAC Blower is %s, Attic Fan is %s' % ('On' if system['ac']['stat'] else 'Off','On' if system['heat']['stat'] else 'Off','On' if system['hfan']['stat'] else 'Off','On' if system['afan']['stat'] else 'Off'))

    # Print the MCP3008 values to terminal last that way all other output is written first
    print('| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |'.format(*shn))
    print('| {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} |'.format(*pr_v)) # Show raw ADC values
    print('| {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} |'.format(*pr_c)) # Show Celsius
    print('| {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} | {:5} |'.format(*pr_f)) # Show Fahrenheit

    # Send output to 128x64 screens if they're not sleeping
    if display_on:
        dispdata = {}
        for d in range(displays):
            dispdata[d] = {0:0,1:0,2:0,3:0,4:0,5:0,6:0,7:0} # All variables will have data, even if they won't be displayed.
        # Screen 1 will give us the date and time, Pi CPU Temp, and UPS data
        dispdata[0][0] = now['s']
        dispdata[0][2] = "Pi: " + str(sensor[cpusens]['temp']['c']) + "*C (" + str(sensor[cpusens]['temp']['f']) + "*F)"
        # Only display this info if the UPS data has been properly received and is enabled
        if ups['enable']:
            dispdata[0][4] = "UPS Data Error" if i2cnr else "AC Power: %s" % ("Off" if not int(ups['data']['main']['v_chgC']) > 4000 and not int(ups['data']['main']['v_chgM']) > 4000 else "On") # This is not working properly for some reason... Stays always "On".
            if not i2cnr:
                dispdata[0][6] = "Battery: %s V" % (str(ups['data']['bat']['v']))
                dispdata[0][7] = "Current: %s mA" % (str(ups['data']['bat']['a']))
        # We'll use screens 2 and 3 to output all the temperature sensor data
        for d in range(1, 3):
            for e in range(8):
                dispdata[d][e] = str(sensor[e if d == 1 else e + 8]['dispname']) + ": " + str("--" if pr_c[e if d == 1 else e + 8] == -50 else pr_f[e if d == 1 else e + 8])
        # Screen 4 will show HVAC status
        e = 0
        for s in ['ac', 'heat', 'hfan', 'afan']:
            dispdata[3][e] = system[s]['name'] + " is " + ('on' if system[s]['stat'] else 'off')
            dispdata[3][e+1] = "Last " + ('off' if system[s]['stat'] else 'on')
            e += 2
        # Screen 5 will show recent HVAC runtimes
        e = 0
        for s in ['ac', 'heat', 'hfan', 'afan']:
            dispdata[4][e] = system[s]['laston' if system[s]['stat'] else 'lastoff']
            dispdata[4][e+1] = system[s]['lastoff' if system[s]['stat'] else 'laston']
            e += 2
        updatedisplays() # Send it!
        display_on -= 1
    elif not display_off:
        cleardisplays()
        display_off = 1

    fw -= 1
    web -= 1
    chkattic -= 1
    notes = {}
    notesi = 0
    do_log = 0

    time.sleep(slp)