# Read data from my Davis Vantage Pro 2 and send to my website
# This script has been written for Python 2.7
# This script uses content from WOSPi (http://www.annoyingdesigns.com/wospi/) modified to suit my own needs
# Author: AK49BWL
# Updated: 02/11/2024 12:07

import datetime
import json
import requests
import serial
import struct
import threading
import time

setting = {
    'maxtry': 5, # Max number of attempts to wake console
    'int': 300, # Main loop interval in seconds
}
com = { # Serial config
    'port': '/dev/ttyUSB0',
    'baud': 19200,
    'byte': serial.EIGHTBITS,
    'parity': serial.PARITY_NONE,
    'stop': serial.STOPBITS_ONE,
    'timeout': 3,
    'onoff': 0,
    'delay': 0.5,
}

cc = { # Console text coloring
    'e': '\x1b[0m',
    'off': '\x1b[1;31;40mOff\x1b[0m',
    'on': '\x1b[1;32;40mOn\x1b[0m',
    'snt': '\x1b[1;32;42m',
    'fh': '\x1b[1;33;40m',
    'err': '\x1b[1;33;41m',
    'ws': '\x1b[1;33;45m',
    'trn': '\x1b[1;36;40m',
    'suc': '\x1b[1;36;42m',
    'fbu': '\x1b[1;36;46m',
    'cer': '\x1b[1;37;41m',
    'ups': '\x1b[1;37;42m'
}

# Write to console, terminate string with termChar, then delay
def wxWrite(s, termChar='\n'):
    if wx:
        s = s + termChar
        wx.write(s)
        time.sleep(com['delay'])
        return 1
    return 0

def openWxComm():
    wx = serial.Serial(com['port'], com['baud'], com['byte'], com['parity'], com['stop'], com['timeout'], com['onoff'])
    time.sleep(com['delay'])
    if not wx:
        return 0
    wake = 0
    for attemptNo in range(1, setting['maxtry'] + 1):
        print('Waking console, attempt %s of %s' % (attemptNo, setting['maxtry']))
        wx.write('\n')
        if wx.inWaiting() == 2:
            dummyBuffer = wx.read(wx.inWaiting())
            print('Console is awake after %s %s' % (attemptNo, 'try' if attemptNo == 1 else 'tries'))
            wake = 1
            wxWrite('TEST')
            time.sleep(com['delay'])
            dummyBuffer = wx.read(wx.inWaiting())
            break
        else:
            print('Console not yet responding to wakeup call')
            dummyBuffer = wx.read(wx.inWaiting())
            time.sleep(1.5)
    if wake:
        print('The console is responding')
    else:
        print('Unable to wake up the console (is cable connected?)')
        wx.close()
        wx = 0
    return wx

# Loads data from console - populates wxData, return 1 if success, 0 if failure
def readWxData():
    if not wx:
        return 0
    i = j = 0
    s = t = ''
    wxWrite('VER')
    i = wx.inWaiting()
    t = wx.read(i).replace('\n\r', ' ', 5)
    i = t.find('OK') + 3
    wxData['VER'] = t[i:]
    if wxData['VER'].strip() == '':
        wxWrite('VER')
        i = wx.inWaiting()
        t = wx.read(i).replace('\n\r', ' ', 5)
        i = t.find('OK') + 3
        wxData['VER'] = t[i:]
    i = wxData['VER'].find('OK')
    if i >= 0:
        wxData['VER'] = wxData['VER'][i + 3:]
    wxWrite('NVER')
    i = wx.inWaiting()
    t = wx.read(i).replace('\n\r', ' ', 5)
    i = t.find('OK') + 3
    wxData['NVER'] = t[i:]
    wx.flushInput()
    wx.flushOutput()
    time.sleep(com['delay'])
    wxData['BARDATA'] = ''
    wxWrite('BARDATA')
    i = wx.inWaiting()
    if i > 0:
        s = wx.read(i)
        wxData['BARDATA'] = s
        i = s.find('DEW POINT') + 10
        s = s[i:]
        i = s.find('\n\r')
        s = s[:i]
        wxData['DEWPOINT_F'] = float(s)
    wxData['CRC-CALC'] = 1
    # Loop 1
    wxWrite('LOOP 1')
    loopSize = i = wx.inWaiting()
    print('Read LOOP packet from console, received %d bytes' % (i))
    if loopSize != 100:
        print('Aborting, LOOP packet size <> 100')
        return 0
    else:
        s = q = wx.read(i)
        s = s[3:]
        wxData['CRC_PAD'] = struct.unpack_from('H', q, 95)[0]
        wxData['CRC-CALC'] = CRC(q[1:101])
        if wxData['CRC-CALC'] == 0:
            print('LOOP packet CRC is verified')
            L1 = q[1:]
        else:
            print('No LOOP packet or invalid LOOP packet CRC')
            return 0
        j = wxData['BAROTREND'] = struct.unpack_from('B', s, 1)[0]
        t = 'Barometric pressure is '
        if j == 0:
            t += 'steady'
        elif j == 20:
            t += 'rising slowly'
        elif j == 60:
            t += 'rising rapidly'
        elif j == 196:
            t += 'falling rapidly'
        elif j == 236:
            t += 'falling slowly'
        else:
            t = 'Barometric trend is not available'
        wxData['BAROTRENDTEXT'] = t
        j = wxData['BAROMETER_INHG'] = round(struct.unpack_from('H', s, 5)[0] / 1000.0, 2)
        wxData['BAROMETER_HPA'] = round(j * 33.8639, 1)
        j = wxData['INTEMP_F'] = struct.unpack_from('H', s, 7)[0] / 10.0
        wxData['INHUM_P'] = struct.unpack_from('B', s, 9)[0]
        j = wxData['OUTTEMP_F'] = struct.unpack_from('H', s, 10)[0] / 10.0
        j = wxData['AVGWIND10_MPH'] = struct.unpack_from('B', s, 13)[0]
        if j > 300:
            j = 0
            wxData['AVGWIND10_MPH'] = 0
        wxData['AVGWIND10_KTS'] = round(j * 0.868976, 1)
        wxData['AVGWIND10_MSEC'] = round(j * 0.44704, 1)
        j = wxData['WIND_MPH'] = struct.unpack_from('B', s, 12)[0]
        wxData['WIND_KTS'] = round(j * 0.868976, 1)
        wxData['WIND_MSEC'] = round(j * 0.44704, 1)
        t = str(struct.unpack_from('H', s, 14)[0])
        if t == '0':
            t = '000'
        if len(t) < 3:
            t = '0' + t
        if len(t) < 3:
            t = '0' + t
        wxData['WINDDIR'] = t
        wxData['WIND_CARDINAL'] = getCardinalDirection(int(t))
        wxData['OUTHUM_P'] = struct.unpack_from('B', s, 31)[0]
        if wxData['OUTHUM_P'] > 100:
            print('Value out of range (manually verify console value) : OUTHUM_P = %d' % (wxData['OUTHUM_P']))
            wxData['OUTHUM_P'] = -1
            wxData['DATAERROR'] = True
        wxData['RAINRATE_INHR'] = struct.unpack_from('H', s, 39)[0] * 0.01
        wxData['DAYRAIN_IN'] = struct.unpack_from('H', s, 48)[0] * 0.01
        wxData['STORMRAIN_IN'] = struct.unpack_from('H', s, 44)[0] * 0.01
        wxData['MONTHRAIN_IN'] = struct.unpack_from('H', s, 50)[0] * 0.01
        wxData['YEARRAIN_IN'] = struct.unpack_from('H', s, 52)[0] * 0.01
        t = struct.unpack_from('H', s, 46)[0]
        if t == 65535:
            wxData['STORMSTART'] = '01.01.1970'
        else:
            storm_year = t % 128
            t = t - storm_year
            storm_day = t % 4096
            storm_day = storm_day >> 7
            t = t - storm_day
            t = t >> 12
            storm_month = t
            t = ''
            if storm_day < 10:
                t = '0'
            t += str(storm_day) + '.'
            if storm_month < 10:
                t += '0'
            t += str(storm_month) + '.'
            t += str(2000 + storm_year)
            wxData['STORMSTART'] = t
        t = 0
        t = wxData['ET_DAY_IN'] = struct.unpack_from('H', s, 54)[0] * 0.001
        wxData['ET_MONTH_IN'] = t + struct.unpack_from('H', s, 56)[0] * 0.01
        wxData['ET_YEAR_IN'] = t + struct.unpack_from('H', s, 58)[0] * 0.01
        wxData['FCICON'] = struct.unpack_from('B', s, 87)[0]
        wxData['VOLTAGE'] = round(struct.unpack_from('H', s, 85)[0] * 300 / 512 / 100, 2)
        wxData['BATTERYSTATUS'] = struct.unpack_from('B', s, 84)[0]
        wxData['SUNRISE_LT'] = unpackTime(s, 89)
        wxData['SUNSET_LT'] = unpackTime(s, 91)
        wxWrite('\n\n')
        wx.flushOutput()
        wx.flushInput()
        # Loop 2
        wxWrite('LPS 2 1')
        time.sleep(com['delay'])
        loopSize = i = wx.inWaiting()
        print('Read LOOP 2 packet from console, received %d bytes' % (i))
        if i != 100:
            print('Aborting, LOOP2 packet size <> 100')
            return 0
        print('Read LOOP2 packet from console, received %d bytes' % (loopSize))
        s = q = wx.read(i)
        s = s[3:]
        if CRC(q[1:101]) == 0:
            print('LOOP2 packet CRC is verified')
            L2 = q[1:]
            j = wxData['AVGWIND10_MPH'] = struct.unpack_from('H', s, 16)[0] / 10.0
            if j > 300:
                j = 0
                wxData['AVGWIND10_MPH'] = 0
            wxData['AVGWIND10_KTS'] = round(j * 0.868976, 1)
            wxData['AVGWIND10_MSEC'] = round(j * 0.44704, 1)
            j = wxData['AVGWIND2_MPH'] = struct.unpack_from('H', s, 18)[0] / 10.0
            if j > 300:
                j = 0
                wxData['AVGWIND2_MPH'] = 0
            wxData['AVGWIND2_KTS'] = round(j * 0.868976, 1)
            wxData['AVGWIND2_MSEC'] = round(j * 0.44704, 1)
            j = wxData['GUST10_MPH'] = struct.unpack_from('H', s, 20)[0]
            wxData['GUST10_KTS'] = round(j * 0.868976, 1)
            wxData['GUST10_MSEC'] = round(j * 0.44704, 1)
            t = str(struct.unpack_from('H', s, 22)[0])
            if t == '0':
                t = '000'
            if len(t) < 3:
                t = '0' + t
            if len(t) < 3:
                t = '0' + t
            wxData['GUST10DIR'] = t
            wxData['GUST_CARDINAL'] = getCardinalDirection(int(t))
            wxData['RAINFALL15_IN'] = struct.unpack_from('H', s, 50)[0] * 0.01
            wxData['RAINFALL60_IN'] = struct.unpack_from('H', s, 52)[0] * 0.01
            wxData['RAINFALL24H_IN'] = struct.unpack_from('H', s, 56)[0] * 0.01
            wxData['WC_F'] = struct.unpack_from('H', s, 35)[0] / 1.0
            wxData['DEWPOINT_F'] = struct.unpack_from('H', s, 28)[0] / 1.0
            wxData['THSW_F'] = struct.unpack_from('H', s, 37)[0] / 1.0
            wxData['HINDEX_F'] = struct.unpack_from('H', s, 33)[0] / 1.0
        else:
            print('No LOOP2 packet or invalid LOOP2 packet CRC')
            return 0
        return 1

# CCITT-16 CRC implementation, function should return 0
def CRC(inputData):
    crcTab = (0, 4129, 8258, 12387, 16516, 20645, 24774, 28903, 33032, 37161, 41290,
              45419, 49548, 53677, 57806, 61935, 4657, 528, 12915, 8786, 21173, 17044,
              29431, 25302, 37689, 33560, 45947, 41818, 54205, 50076, 62463, 58334,
              9314, 13379, 1056, 5121, 25830, 29895, 17572, 21637, 42346, 46411,
              34088, 38153, 58862, 62927, 50604, 54669, 13907, 9842, 5649, 1584,
              30423, 26358, 22165, 18100, 46939, 42874, 38681, 34616, 63455, 59390,
              55197, 51132, 18628, 22757, 26758, 30887, 2112, 6241, 10242, 14371,
              51660, 55789, 59790, 63919, 35144, 39273, 43274, 47403, 23285, 19156,
              31415, 27286, 6769, 2640, 14899, 10770, 56317, 52188, 64447, 60318,
              39801, 35672, 47931, 43802, 27814, 31879, 19684, 23749, 11298, 15363,
              3168, 7233, 60846, 64911, 52716, 56781, 44330, 48395, 36200, 40265,
              32407, 28342, 24277, 20212, 15891, 11826, 7761, 3696, 65439, 61374,
              57309, 53244, 48923, 44858, 40793, 36728, 37256, 33193, 45514, 41451,
              53516, 49453, 61774, 57711, 4224, 161, 12482, 8419, 20484, 16421, 28742,
              24679, 33721, 37784, 41979, 46042, 49981, 54044, 58239, 62302, 689,
              4752, 8947, 13010, 16949, 21012, 25207, 29270, 46570, 42443, 38312,
              34185, 62830, 58703, 54572, 50445, 13538, 9411, 5280, 1153, 29798,
              25671, 21540, 17413, 42971, 47098, 34713, 38840, 59231, 63358, 50973,
              55100, 9939, 14066, 1681, 5808, 26199, 30326, 17941, 22068, 55628,
              51565, 63758, 59695, 39368, 35305, 47498, 43435, 22596, 18533, 30726,
              26663, 6336, 2273, 14466, 10403, 52093, 56156, 60223, 64286, 35833,
              39896, 43963, 48026, 19061, 23124, 27191, 31254, 2801, 6864, 10931,
              14994, 64814, 60687, 56684, 52557, 48554, 44427, 40424, 36297, 31782,
              27655, 23652, 19525, 15522, 11395, 7392, 3265, 61215, 65342, 53085,
              57212, 44955, 49082, 36825, 40952, 28183, 32310, 20053, 24180, 11923,
              16050, 3793, 7920)
    crcAcc = 0
    for byte in (ord(part) for part in inputData):
        ushort = crcAcc << 8 & 65280
        crcAcc = ushort ^ crcTab[(crcAcc >> 8 ^ 255 & byte)]
    return crcAcc

def getCardinalDirection(direction):
    """Returns cardinal wind direction."""
    s = '-'
    if direction >= 0 and direction < 11.25:
        s = 'N'
    elif direction >= 11.25 and direction < 33.75:
        s = 'NNE'
    elif direction >= 33.75 and direction < 56.25:
        s = 'NE'
    elif direction >= 56.25 and direction < 78.75:
        s = 'ENE'
    elif direction >= 78.75 and direction < 101.25:
        s = 'E'
    elif direction >= 101.25 and direction < 123.75:
        s = 'ESE'
    elif direction >= 123.75 and direction < 146.25:
        s = 'SE'
    elif direction >= 146.25 and direction < 168.75:
        s = 'SSE'
    elif direction >= 168.75 and direction < 191.25:
        s = 'S'
    elif direction >= 191.25 and direction < 213.75:
        s = 'SSW'
    elif direction >= 213.75 and direction < 236.25:
        s = 'SW'
    elif direction >= 236.25 and direction < 258.75:
        s = 'WSW'
    elif direction >= 258.75 and direction < 281.25:
        s = 'W'
    elif direction >= 281.25 and direction < 303.75:
        s = 'WNW'
    elif direction >= 303.75 and direction < 326.25:
        s = 'NW'
    elif direction >= 326.25 and direction < 348.75:
        s = 'NNW'
    elif direction >= 348.75 and direction <= 360:
        s = 'N'
    return s

# Returns time (HH:MM) from theString at offset
def unpackTime(theString, offset):
    theTime = ''
    j = struct.unpack_from('H', theString, offset)[0]
    if j == 65535:
        return '00:00'
    hr = j // 100
    mn = j % 100
    z = str(hr)
    if len(z) < 2:
        z = '0' + z
    theTime = z + ':'
    z = str(mn)
    if len(z) < 2:
        z = '0' + z
    theTime = theTime + z
    return theTime

# Load Webdata auth stuff
webauth = json.loads(open('codes.json', 'r').read())
# Set up the website request threading system
def to_web(senddata):
    try:
        r = requests.post(webauth['wxdURL'], data=json.dumps(senddata), timeout=(10,10), headers={'User-Agent': webauth['ua'], 'Content-Type': 'application/json'})
    except requests.exceptions.ConnectionError:
        print(cc['cer'] + 'Connection error - Check Pi connectivity' + cc['e'])
    except requests.exceptions.Timeout:
        print(cc['err'] + 'Request timed out trying to send data to the website' + cc['e'])
    else:
        print(cc['snt'] + 'Data sent to website! Response: ' + str(r.status_code) + cc['e'])

wx = 0
wxData = {}

# MAIN LOOP! But do we actually want a loop? ... Meh, for now we'll just run this separately from thermo.py, but later we may integrate this part if it proves to be stable enough.
while 1:
    try:
        # Current date and time
        now = { 's': datetime.datetime.now().strftime('%b %d %Y %H:%M:%S'), 'u': int(time.mktime(datetime.datetime.now().timetuple())) }
        print(now['s'])
        wx = openWxComm()
        wxData = { 'now_s': now['s'], 'now_u': now['u'] }
        thing = readWxData()
        if thing: # Everything seems to be working, send it to the website
            wxData['auth'] = webauth['auth']
            to_web(wxData)
    except (serial.SerialException, TypeError, NameError) as e:
        print('Broke: ' + str(e))
    time.sleep(setting['int'])
