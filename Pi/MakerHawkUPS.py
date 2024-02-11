# MakerHawk UPS+ EP-0136 code from thermo.py ... Just in case I ever need it again I guess.
# This script has been written for Python 2.7
# Author: AK49BWL
# Updated: 02/11/2024 10:11

# After var init section::

# Set up MakerHawk UPS+ EP-0136
ups = {
    'enable': 0, # 1 to enable, 0 to disable. DO NOT ENABLE UNLESS UPS IS CONNECTED!
    'set': { 'samp': 5, 'v_full': 4150, 'v_empt': 3400, 'v_prot': 3500, 'ac_rec': 1, 'cd': 120 },
    'data': { 'sup': {}, 'bat': {}, 'main': { 'data_received': 0 } },
    'read': [0x00]
}
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
    print(cc['ups'] + 'MakerHawk UPS+ EP-0136 enabled and configuration updated' + cc['e'])

# After attic fan activation check (can even be set up as a function before the main loop I guess)::

    # Get data from MakerHawk UPS+ if enabled
    if ups['enable']:
        # Get everything, or just the bare minimum?
        if not dec['ups_all'] or not dec['ups']:
            if not dec['ups_all']:
                dec['ups_all'] = timer['ups_all']
                dec['ups'] = timer['ups']
                try:
                    v_sup = INA219(0.00725, busnum=1, address=0x40) # Pi Power supply output voltage/current
                    v_sup.configure()
                    ups['data']['sup'] = { 'v': v_sup.voltage(), 'a': round(v_sup.current(), 3) }
                    v_bat = INA219(0.005, busnum=1, address=0x45) # Battery voltage/current I/O
                    v_bat.configure()
                    ups['data']['bat'] = { 'v': v_bat.voltage(), 'a': round(v_bat.current(), 3) }
                    ups['data']['bat']['chg'] = 'Charging' if ups['data']['bat']['a'] > 0 else 'Discharging'
                except (DeviceRangeError, IOError) as exceptionerror: # Just dump it all if there's a problem
                    ups['data']['sup'] = { 'v': 'Error', 'a': 'Error' }
                    ups['data']['bat'] = { 'chg': 'Error', 'v': 'Error', 'a': 'Error' }
                    notes[notesi] = 'Pi Output V/A and Battery V/A unavailable: ' + str(exceptionerror)
                    notesi += 1
                    print(cc['err'] + 'Pi Output V/A and Battery V/A unavailable: ' + str(exceptionerror) + cc['e'])
                    log_stat(to_file = 1, customtext = 'Pi Output V/A and Battery V/A unavailable: ' + str(exceptionerror))
                ups['read'] = [0x00]
                try:
                    for i in range(1, 43):
                        ups['read'].append(smbus.SMBus(1).read_byte_data(0x17, i))
                    i2cnr = 0
                except IOError:
                    print(cc['err'] + 'UPS not responding to data query at ID ' + str(i) + cc['e'])
                    i2cnr = ups['data']['main']['i2cnr'] = 1
                    if not ups['data']['main']['data_received']: # Possibility of failure on first read... Might as well zero everything out.
                        for i in range(0, 43):
                            ups['read'] = 0
                if not ups['data']['main']['data_received'] or not i2cnr:
                    ups['data']['main'] = {
                        'date': now['s'],
                        'v_cpu': '%d' % (ups['read'][2] << 8 | ups['read'][1]), # CPU mV
                        'v_pi': '%d' % (ups['read'][4] << 8 | ups['read'][3]), # mV output to RPi
                        'v_chgC': '%d' % (ups['read'][8] << 8 | ups['read'][7]), # USB C input mV
                        'v_chgM': '%d' % (ups['read'][10] << 8 | ups['read'][9]), # MicroUSB input mV
                        'battTempC': '%d' % (ups['read'][12] << 8 | ups['read'][11]), # Battery temp (estimated) Celsius
                        'v_battFull': '%d' % (ups['read'][14] << 8 | ups['read'][13]), # Full battery mV
                        'v_battEmpt': '%d' % (ups['read'][16] << 8 | ups['read'][15]), # Empty battery mV
                        'v_battProt': '%d' % (ups['read'][18] << 8 | ups['read'][17]), # Battery protection mV
                        'battCap': '%d' % (ups['read'][20] << 8 | ups['read'][19]), # Remaining battery capacity %
                        'samp': '%d' % (ups['read'][22] << 8 | ups['read'][21]), # Resampling rate in minutes
                        'stat': '%d' % (ups['read'][23]), # UPS status (on or off)
                        'c_sd': '%d' % (ups['read'][24]), # Shutdown timer in seconds
                        'c_rs': '%d' % (ups['read'][26]), # Restart timer in seconds
                        'restore': '%d' % (ups['read'][25]), # A/C power loss auto-restore
                        'run_total': '%d' % (ups['read'][31] << 24 | ups['read'][30] << 16 | ups['read'][29] << 8 | ups['read'][28]), # Total accumulated UPS runtime in seconds
                        'run_chg': '%d' % (ups['read'][35] << 24 | ups['read'][34] << 16 | ups['read'][33] << 8 | ups['read'][32]), # Total accumulated UPS charging time in seconds
                        'run_sess': '%d' % (ups['read'][39] << 24 | ups['read'][38] << 16 | ups['read'][37] << 8 | ups['read'][36]), # Total runtime this power on session in seconds
                        'usr_batt': '%d' % (ups['read'][42]), # Battery parameters custom set by user
                        'i2cnr': i2cnr,
                        'data_received': 1
                    }
            if not dec['ups']:
                dec['ups'] = timer['ups']
                ups['read'] = [0x00]
                try:
                    for i in [7, 8, 9, 10, 19, 20]:
                        ups['read'].append(smbus.SMBus(1).read_byte_data(0x17, i))
                    i2cnr = 0
                except IOError:
                    print(cc['err'] + 'UPS not responding to data query at ID ' + str(i) + ' (short-read)' + cc['e'])
                    i2cnr = ups['data']['main']['i2cnr'] = 1
                if not i2cnr:
                    ups['data']['main']['v_chgC'] = '%d' % (ups['read'][2] << 8 | ups['read'][1])
                    ups['data']['main']['v_chgM'] = '%d' % (ups['read'][4] << 8 | ups['read'][3])
                    ups['data']['main']['battCap'] = '%d' % (ups['read'][6] << 8 | ups['read'][5])

            # Check current mains power status and log if changed
            backup['power1'] = 0 if not int(ups['data']['main']['v_chgC']) > 200 and not int(ups['data']['main']['v_chgM']) > 200 else 1 # If both USB inputs are below 200mV, we're dead
            if not backup['power1'] == backup['power2']:
                log_stat(to_file = 1, customtext = 'AC Power has been ' + 'restored' if backup['power1'] else 'lost')
                notes[notesi] = 'AC Power has been ' + 'restored' if backup['power1'] else 'lost'
                notesi += 1
                do_log = 1
                backup['powerlaston' if backup['power1'] else 'powerlastoff'] = now['s']
        dec['ups'] -= 1
        dec['ups_all'] -= 1
