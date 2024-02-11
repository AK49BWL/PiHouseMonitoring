# Pulls data from website to update variables used by thermo.py
# This script has been written for Python 2.7
# Author: AK49BWL
# Updated: 02/07/2024 18:15

import datetime
import json
import requests
import time

# Load Webdata auth stuff
webauth = json.loads(open('codes.json', 'r').read())

while 1:
    ct = datetime.datetime.now().strftime("%b %d %Y %H:%M:%S")
    try:
        r = requests.get(webauth['lwvURL'], timeout=(10,10), headers={'User-Agent': webauth['ua'], 'Content-Type': 'application/json'})
    except requests.exceptions.ConnectionError:
        print('\x1b[1;37;41m' + ct + ' -- Connection error - Check Pi connectivity\x1b[0m')
    except requests.exceptions.Timeout:
        print('\x1b[1;33;41m' + ct + ' -- Request timed out trying to get WebVars from website\x1b[0m')
    else:
        try:
            js = r.json()
            if js['data'] == 'good':
                old = json.loads(open('webvars.json', 'r').read())
                if not int(js['lastWebChange']) == int(old['lastWebChange']): # Let's not bother updating if nothing's changed.
                    toStr = dict([(str(k), str(v)) for k, v in js.items()]) # Make this NOT UNICODE!
                    f = open("webvars.json", "w")
                    f.write(str(json.dumps(toStr)))
                    f.close()
                    print('\x1b[1;32;42m' + ct + ' -- Reloaded WebVars successfully\x1b[0m')
                else:
                    print(ct + ' -- WebVars unchanged')
            else:
                print('\x1b[1;33;41m' + ct + ' -- This JSON data sucks!\x1b[0m')
        except (requests.exceptions.InvalidJSONError, TypeError, NameError) as exceptionerror:
            print('\x1b[1;33;41m' + ct + ' -- Error - ' + exceptionerror + '%s\x1b[0m')
    time.sleep(300)