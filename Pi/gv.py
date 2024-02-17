# Read data from my Davis Vantage Pro 2 and send to my website
# This script has been written for Python 2.7
# This script uses content from WOSPi (http://www.annoyingdesigns.com/wospi/) modified to suit my own needs
# Author: AK49BWL
# Updated: 02/16/2024 17:59

import json

cc = { # Console text coloring
    'e': '\x1b[0m',
    'off': '\x1b[1;31;40mOff\x1b[0m',
    'on': '\x1b[1;32;40mOn\x1b[0m',
    'dis': '\x1b[1;37;41mDisabled\x1b[0m',
    'snt': '\x1b[1;32;42m',
    'fh': '\x1b[1;33;40m',
    'err': '\x1b[1;33;41m',
    'ws': '\x1b[1;33;45m',
    'trn': '\x1b[1;36;40m',
    'suc': '\x1b[1;36;42m',
    'fbu': '\x1b[1;36;46m',
    'cer': '\x1b[1;37;41m',
    'ups': '\x1b[1;37;42m',
}
webauth = json.loads(open('codes.json', 'r').read()) # PASSWORDS n stuff
wx = 0
wxData = {}