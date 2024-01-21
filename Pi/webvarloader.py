# Pulls data from website to update variables used by thermo.py
# This script has been written for Python 2.7
# Author: AK49BWL
# Updated: 01/13/2024 20:42

import datetime
import json
import requests
import time

# Load Webdata auth stuff
webauth = json.loads(open('codes.json', 'r').read())

while 1:
    try:
        r = requests.get(webauth['lwvURL'], timeout=(10,10), headers={'User-Agent': webauth['ua'], 'Content-Type': 'application/json'})
    except requests.exceptions.ConnectionError:
        print('\x1b[1;37;41mConnection error - Check Pi connectivity\x1b[0m')
    except requests.exceptions.Timeout:
        print('\x1b[1;33;41mRequest timed out trying to get WebVars from website\x1b[0m')
    else:
        try:
            js = r.json()
        except (requests.exceptions.InvalidJSONError, TypeError) as exceptionerror:
            print("\x1b[1;33;41mInvalid JSON - %s\x1b[0m" % (exceptionerror))
        else:
            if js['data'] == 'good':
                old = json.loads(open('webvars.json', 'r').read())
                if not int(js['lastWebChange']) == int(old['lastWebChange']): # Let's not bother updating if nothing's changed.
                    f = open("webvars.json", "w")
                    f.write(r.content)
                    f.close()
                    print('\x1b[1;32;42mReloaded WebVars successfully\x1b[0m')
                else:
                    print('WebVars unchanged')
            else:
                print("\x1b[1;33;41mThis JSON data sucks!\x1b[0m")
    time.sleep(300)