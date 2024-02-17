<?php // pitemp.php v2.0.20240217.1447
include $_SERVER['DOCUMENT_ROOT'].'/includes/include.php';
// PHP7 does some weird shit with floats and JSON so we need to ini_set precisions. [Done here because of remote hosting possibly ignoring custom php.ini and .htaccess modifications]
ini_set('precision', -1);
ini_set('serialize_precision', -1);

$house = array(
    'db' => $ak['db']['dbs'][0],
    'sys' => array('ac', 'heat', 'afan', 'hfan'),
);

// No action, go to index
if (!isset($_GET['do']) && !isset($_POST['do']))
    $do = 'index';
else
    $do = $_GET['do'];

// Allowed actions
$doarr = array(
    'index' => array( 'title' => 'House Temperatures and Statuses' ),
    'logFromPi' => array( 'title' => '' ), // Triggered only by my RPi sending HVAC and temp data to the site and returns no output
    'logWxFromPi' => array( 'title' => '' ), // Triggered only by my RPi sending weather data to the site and returns no output
    'loadWebVars' => array( 'title' => '' ), // Triggered by RPi request and returns JSON data containing values changeable on the website
    'setWebVars' => array( 'title' => 'Set thermo.py Values' ), // For changing values to be loaded by the RPi remotely
    'viewSysHistory' => array( 'title' => 'House HVAC System History' ), // Shows HVAC system switching history
    'viewAllWeatherData' => array( 'title' => 'Current Davis Weather Center Data' ), // <-- This
    'about' => array( 'title' => 'House Status Info' ), // About the system and how it works and stuff

/* More?

    'viewTempHistory' => array( 'title' => 'House Temperature History' ),

*/
);
// No known action? Index.
if (!isset($doarr[$do]))
    $do = 'index';

// Get into it!
$postdata = getCommittedData();
$_GET['action'] = 'siteloc_house_'.$do;
$doFunc = 'house_'.$do;
$returned = $doFunc();

echo AKheader($doarr[$do]['title'], (isset($returned['title2']) ? $returned['title2'] : 0), 'extras,house', (isset($returned['extrahead']) ? $returned['extrahead'] : 0)).(isset($postdata['info']) ? '
<div class="notice" align="center">'.$postdata['info'].'</div>' : '').'
'.$returned['data'].($context['user']['is_admin'] ? '<br /><br />

<a href="pitemp.php?do=viewSysHistory">View HVAC System History</a> || <a href="pitemp.php?do=setWebVars">Change WebVars</a> || <a href="pitemp.php?showfile">Show RPi POST Content</a>' : '');

echo AKfooter();



/** Functions **/

function house_index() {
    global $ak, $house, $context;

    // Get the data from MySQL. If we can.
    if (!$ak['nodb']) {
        list($data) = mysqli_fetch_row(mysqli_query($ak['mysqli'], "SELECT `value` FROM `$house[db]`.`site` WHERE `setting` = 'piTempReceivedData'"));
        $data = json_decode($data, 1);
        list($wxData) = mysqli_fetch_row(mysqli_query($ak['mysqli'], "SELECT `value` FROM `$house[db]`.`site` WHERE `setting` = 'piWxReceivedData'"));
        $wxData = json_decode($wxData, 1);
    } else
        $data = 'NoMySQL';

    if (is_array($data)) {
        // Check if the data is current or possibly thermo.py has died
        if ($data['date']['u'] + 960 < time()) {
            $oldData = 1;
            // Log this to the database if it hasn't been already.
            list($poop) = mysqli_fetch_row(mysqli_query($ak['mysqli'], "SELECT `value` FROM `$house[db]`.`site` WHERE `setting` = 'piTempActive'"));
            if ($poop) {
                $result1 = mysqli_query($ak['mysqli'], "INSERT INTO `$house[db]`.`house_hvacStatusLog` (`date`, `sys`, `stat`, `comment`) VALUES (".time().", 'Log', 0, 'No activity from thermo.py in over 15 minutes, last receive ".$data['date']['s']."')");
                $result2 = mysqli_query($ak['mysqli'], "REPLACE INTO `$house[db]`.`site` (`setting`, `value`) VALUES ('piTempActive', 0)");
            }
        } else
            $oldData = 0;
        $tskip = 0;
        foreach ($data['notes'] as $note)
            $noteout[] = $note;
        foreach ($data['backup']['hvac'] as $key => $value) {
            if ($value['stat'])
                $sysout1[] = $value['name'].' is <span class="hvon">on</span> since '.$value['laston'].', last off: '.(date('Ymd', strtotime($value['laston'])) == date('Ymd', strtotime($value['lastoff'])) ? date('H:i:s', strtotime($value['lastoff'])) : $value['lastoff']);
            else
                $sysout2[] = $value['name'].' is <span class="hv'.($data['setting']['hvac'][$key] ? 'off">off' : 'dis">disabled').'</span>'.($value['laston'] && $value['lastoff'] ? ', Last runtime: '.$value['laston'].' to '.(date('Ymd', strtotime($value['laston'])) == date('Ymd', strtotime($value['lastoff'])) ? date('H:i:s', strtotime($value['lastoff'])) : $value['lastoff']) : '');
        }
        foreach ($data['tempdata'] as $tempdata) {
            if (!$tempdata['enable']) {
                $tskip++;
                continue;
            }
            $tempout[] = ($context['user']['is_admin'] && isset($tempdata['ch']) ? 'Sensor '.($tempdata['ch'] ? $tempdata['p'] + 8 : $tempdata['p']).': ' : '').$tempdata['name'].': '.$tempdata['temp']['f'].'&#176;F, '.$tempdata['temp']['c'].'&#176;C';
        }
        $return = '<br />
<span class="notice">'.date('F j, Y H:i:s', strtotime($data['date']['s'])).'</span><br />'.($oldData ? '
<span class="pagedesc">No data from RPi in over 15 minutes</span><br />' : '').(isset($noteout) ? '
<span class="pagedesc">'.implode(', ', $noteout).'</span><br />' : '').'
<span class=notice2>Raspberry Pi Status:</span><br />
Pi Uptime: '.getTimeFromSeconds($data['date']['sut'], 'array', 0, 0)['str'].'<br />
Script Runtime: '.getTimeFromSeconds(($data['date']['u'] - $data['date']['scr']), 'array', 0, 0)['str'].'<br />'.($data['ups']['enable'] ? '
Power Source: '.($data['ups']['data']['bat']['chg'] == 'Discharging' ? 'UPS Battery (AC Power '.($data['backup']['power1'] ? 'On' : 'Off').')' : 'AC Mains (UPS Enabled)').'<br />
UPS Battery: '.$data['ups']['data']['main']['battCap'].'% Capacity, '.$data['ups']['data']['bat']['v'].' Volts, '.($data['ups']['data']['bat']['chg'] == 'Discharging' ? 'Discharging at '.str_replace('-', '', $data['ups']['data']['bat']['a']).'mA to power Pi and systems' : 'Charging at '.$data['ups']['data']['bat']['a'].'mA').'<br />' : '
Power Source: AC Mains (UPS Disabled)<br />').'
Last recorded AC power loss: '.$data['backup']['powerlastoff'].', '.($data['backup']['power1'] ? 'on since '.$data['backup']['powerlaston'] : ', ongoing (last on: '.$data['backup']['powerlaston'].')').'<br />
<span class=notice2>HVAC Status:</span><br />
'.implode('<br />', (isset($sysout1) ? array(implode('<br />', $sysout1), implode('<br />', $sysout2)) : $sysout2)).'<br />
<span class="notice2">Temperatures:</span><br />
'.implode ('<br />
', $tempout).'<br />'.($data['ups']['enable'] ? '
System UPS Battery: '.round((($data['ups']['data']['main']['battTempC'] * 1.8) + 32), 1).'&#176;F, '.$data['ups']['data']['main']['battTempC'].'&#176;C<br />' : '').($tskip ? '
'.$tskip.' sensors skipped due to not being in use<br />
<span class="notice2">Weather Center (Updated '.$wxData['now_s'].'):</span><br />
Outside Temp, Humidity: '.$wxData['tempOut'].'&#176;F, '.$wxData['humOut'].'%'.($wxData['heatIndex'] > $wxData['tempOut'] + 3 ? ' -- Heat Index: '.$wxData['heatIndex'].'&#176;F' : '').'<br />
Inside Temp, Humidity: '.$wxData['tempIn'].'&#176;F, '.$wxData['humIn'].'%<br />
Wind (10 minute average): '.$wxData['windNow_dir'].'&#176; '.$wxData['windNow_car'].' at '.$wxData['windAvg10_mph'].'mph '.($wxData['windGust10_mph'] > $wxData['windAvg10_mph'] ? 'gusting to '.$wxData['windGust10_mph'].'mph' : '').($wxData['windChill'] < $wxDATA['tempOut'] - 3 ? ' -- Wind Chill: '.$wxData['windChill'].'&#176;F' : '').'<br />'.($wxData['rain24hr'] ? '
Rain Inches (last 15min, 1hr, 24hr): '.round($wxData['rain15min'], 2).', '.round($wxData['rain60min'], 2).', '.round($wxData['rain24hr'], 2).($wxData['rainRate'] ? ', currently raining at '.round($wxData['rainRate'], 2).'in/hr' : '').'<br />' : '').'
Rain Today: '.round($wxData['rainD'], 2).'in -- This month: '.round($wxData['rainM'], 2).'in -- This year: '.round($wxData['rainY'], 2).'in<br />
<br /><a href="pitemp.php?do=about">About this page</a><br />' : '');

    } else
        $return = 'Something really broke.<br />';
    if (isset($_GET['showfile']) && $context['user']['is_admin']) {
        ksortRec($data);
		ksortRec($wxData);
        $return .= '<br /><br />'.nl2br(str_replace(' ', '&nbsp', print_r(array($data, $wxData), 1)));
    }
    return array( 'data' => $return );
}

function house_about() {
    global $ak;
    $return = '<br />
<span class="box">Data provided by my Raspberry Pi 3B+ microcontroller running my very own Python script for systems monitoring<br />
Data updates every 5 minutes OR when a system status changes<br />
Custom circuitry includes:<br />
-- TMP36 analog output temperature sensors with an MCP3008 ADC IC with 3.3v reference read via SPI<br />
-- 24v relays from a receiver amplifier activated by my HVAC system thermostat, relays activate GPIO pins on the Pi for reading system status<br />
-- optocoupler relay module to switch 110vAC power to my attic fans based on temperature readings<br />
-- MakerHawk UPS+ EP-0136 battery backup module for keeping the Pi running and detecting power outages<br /></span><br />
Further data such as indoor and outdoor humidity, rain rate, wind speed and direction, heat index, and more is provided by a Davis Vantage Pro 2 Weather Center via Serial Data (using code from <a href="https://www.annoyingdesigns.com/wospi/" target="_blank">WOSPi Python library</a>)<br />
<img src="'.$ak['url'].'/img/pi.jpg" alt="Pi" title="Pi" />';
    return array( 'data' => $return );
}

function house_logFromPi() {
    global $ak, $house;

    // Has any usable data been sent?
    if (empty($_SERVER['CONTENT_LENGTH'])) {
        die; // Nope
    }
    // Gotta do some JSON stuff.
    $post = json_decode(file_get_contents("php://input"), 1);
    if (!isset($post['auth']) || $post['auth'] !== $ak['auth'])
        die(AKerr('House monitoring RPi sent data to website without auth key', 'fatal')); // No verify. Roflmao. You tried, you died.

    // NoMySQL? NoMySQL. Send this interation to file and forget the rest.
    if ($ak['nodb'])
        die(AKerr('Unable to log RPi data due to MySQL outage', 'fatal')); // Nah just forget it completely.

    // Store the received data, minus the auth key...
    unset($post['auth']);
    $ins = mysqli_real_escape_string($ak['mysqli'], json_encode($post));
    $result = mysqli_query($ak['mysqli'], "REPLACE INTO `$house[db]`.`site` (`setting`, `value`) VALUES ('piTempActive', '".$post['date']['u']."'), ('piTempReceivedData', '$ins')");
    if (!$result)
        AKerr('fuck me! '.mysqli_error($ak['mysqli']));

    foreach($house['sys'] as $h) {
        // Any HVAC system status changes?
        if (($post['backup']['hvac'][$h]['stat'] == 0 && $post['date']['s'] == $post['backup']['hvac'][$h]['lastoff'] && $post['backup']['hvac'][$h]['lastoff'] !== 0) || ($post['backup']['hvac'][$h]['stat'] == 1 && $post['date']['s'] == $post['backup']['hvac'][$h]['laston'] && $post['backup']['hvac'][$h]['laston'] !== 0)) {
            if ($h == 'hfan' && $post['backup']['hvac']['ac']['stat']) // Honeywell thermostat switches on A/C then HFan, switches off HFan then A/C. So do not log HFan to MySQL if A/C is on.
                continue;
            $data[] = array( 'date' => $post['date']['u'], 'sys' => $h, 'stat' => $post['backup']['hvac'][$h]['stat'], 'comment' => ($post['backup']['power1'] ? 0 : 'No AC Power, System Not Active') );
        } else {
        // Possible a system change will be missed by data not being properly sent to the site. We can potentially recover and add the most recent changes.
            foreach(array(0, 1) as $ss) {
                if ($post['backup']['hvac'][$h][($ss ? 'laston' : 'lastoff')] !== 0) { // Do nothing if the system in question has no history
                    if ($h == 'hfan') { // HFan special because of course.
                        $dbe = mysqli_fetch_assoc(mysqli_query($ak['mysqli'], "SELECT * FROM `$house[db]`.`house_hvacStatusLog` WHERE `date` > '".(strtotime($post['backup']['hvac'][$h][($ss ? 'laston' : 'lastoff')]) - 10)."' AND `date` < '".(strtotime($post['backup']['hvac'][$h][($ss ? 'laston' : 'lastoff')]) + 10)."' AND `sys` = 'ac' AND `stat` = '$ss'"));
                        if ($dbe)
                            continue; // Ignore HFan status changes within 20 seconds of A/C status changes
                    }
                    $dbe = mysqli_fetch_assoc(mysqli_query($ak['mysqli'], "SELECT * FROM `$house[db]`.`house_hvacStatusLog` WHERE `date` = '".strtotime($post['backup']['hvac'][$h][($ss ? 'laston' : 'lastoff')])."' AND `sys` = '$h' AND `stat` = '$ss'"));
                    if (!$dbe) { // Looks like we need to add this entry.
                        $data[] = array( 'date' => strtotime($post['backup']['hvac'][$h][($ss ? 'laston' : 'lastoff')]), 'sys' => $h, 'stat' => $ss, 'comment' => 0 );
                    }
                }
            }
        }
    }

    // Check AC Power status
    if ($post['backup']['power1'] !== $post['backup']['power2'])
        $data[] = array( 'date' => $post['date']['u'], 'sys' => 'Power', 'stat' => $post['backup']['power1'], 'comment' => 'V-In MicroUSB: '.$post['ups']['data']['main']['v_chgM'].'mV, V-In USB-C: '.$post['ups']['data']['main']['v_chgC'].'mV' );

    // One last check, has thermo.py been freshly restarted?
    if (!$post['backup']['saved'])
        $data[] = array( 'date' => $post['date']['u'], 'sys' => 'Log', 'stat' => 1, 'comment' => 'thermo.py restarted' );

    // Send it... If there's anything to send
    if (isset($data)) {
        $e=0;
        foreach ($data as $d) {
            foreach ($d as $var => $val) {
                $allvars[] = $var;
                $sanitized[$e][$var] = ($val !== 'NULL' && !is_numeric($val) ? '\'' : '').mysqli_real_escape_string($ak['mysqli'], $val).($val !== 'NULL' && !is_numeric($val) ? '\'' : '');
            }
            $e++;
        }
        $allvars = array_unique($allvars);
        $query = 'INSERT INTO `ak49bwl_ak49bwl`.`house_hvacStatusLog` (`'.implode('`, `', $allvars).'`) VALUES ';
        foreach ($sanitized as $ins)
            $queryins[] = '('.implode(', ', $ins).')';
        $query .= implode(', ', $queryins);
        $result = mysqli_query($ak['mysqli'], $query);
        if (!$result)
            AKerr('fuck me again! '.mysqli_error($ak['mysqli']));
    }
    die(AKfooter(1)); // This doesn't need any output returned to the source.
}

function house_logWxFromPi() { // A lot simpler than the HVAC stuff because we're not actually logging anything lol
    global $ak, $house;

    // Has any usable data been sent?
    if (empty($_SERVER['CONTENT_LENGTH'])) {
        die; // Nope
    }
    // Gotta do some JSON stuff.
    $post = json_decode(file_get_contents("php://input"), 1);
    if (!isset($post['auth']) || $post['auth'] !== $ak['auth'])
        die(AKerr('House monitoring RPi sent data to website without auth key', 'fatal')); // No verify. Roflmao. You tried, you died.

    // NoMySQL? NoMySQL. Send this interation to file and forget the rest.
    if ($ak['nodb'])
        die(AKerr('Unable to log weather data due to MySQL outage', 'fatal')); // Nah just forget it completely.

    // Store the received data, minus the auth key...
    unset($post['auth']);
    $ins = mysqli_real_escape_string($ak['mysqli'], json_encode($post));
    $result = mysqli_query($ak['mysqli'], "REPLACE INTO `$house[db]`.`site` (`setting`, `value`) VALUES ('piWxReceivedData', '$ins')");
    if (!$result)
        die(AKerr(mysqli_error($ak['mysqli'])));
    die(AKfooter(1)); // This doesn't need any output returned to the source.
}

function house_viewSysHistory() {
    global $ak, $house;

    $query = mysqli_query($ak['mysqli'], "SELECT * FROM `$house[db]`.`house_hvacStatusLog` ORDER BY `date` DESC LIMIT 500");
    while ($h = mysqli_fetch_assoc($query)) {
        $data[$h['sys']][] = $h;
    }
    $i=0;
    foreach($house['sys'] as $sys) {
        if (!isset($data[$sys]))
            continue;
        $i++;
        foreach($data[$sys] as $run) { // We're just going to ASSuME that for every on there is an off. Oh well if not, system may be on or data is missing.
            if ($run['stat'] && isset($off))
                $on = $run['date'];
            else if (!$run['stat'])
                $off = $run['date'];
            else
                continue;
            if (isset($off) && isset($on)) {
                $output[$sys][] = array( 'on' => $on, 'off' => $off, 'runtime' => getTimeFromSeconds(($off - $on), 'array'));
                unset($off, $on);
            }
        }
    }
    $html = '<table>
    <tr>';
    foreach($output as $k => $v) {
        $html .= '
        <td class="table_ext">
            <table border="1px">
                <tr class="table_int">
                    <td>System</td> <td>On</td> <td>Off</td> <td>Runtime</td>
                </tr>';
        foreach($output[$k] as $p) {
            $html .= '
                <tr class="table_int">
                    <td>'.$k.'</td> <td>'.date('m/j/Y H:i:s', $p['on']).'</td> <td>'.(date('j', $p['on']) == date('j', $p['off']) ? date('H:i:s', $p['off']) : date('m/j/Y H:i:s', $p['off'])).'</td> <td>'.$p['runtime']['str'].'</td>
                </tr>';
        }
        $html .= '
            </table>
        </td>';
    }
    $html .= '
    </tr>
</table>';

    return array( 'data' => $html ); // .'<br />'.nl2br(str_replace(' ', '&nbsp', print_r(array('data' => $data, 'output' => $output), 1)))
}

function house_viewAllWeatherData() {
    global $ak, $house, $context;
    list($wxData) = mysqli_fetch_row(mysqli_query($ak['mysqli'], "SELECT `value` FROM `$house[db]`.`site` WHERE `setting` = 'piWxReceivedData'"));
    $wxData = json_decode($wxData, 1);
    ksort($wxData);
    return array( 'data' => nl2br(print_r($wxData,1)));
}

// Change remote RPi variables
function house_setWebVars() {
    global $ak, $context, $house;
    if (!$context['user']['is_admin'])
        AKredirect('You are not an Administrator of the site.', '/extras/pitemp.php', 1);
    if (isset($_POST) && !empty($_POST['set']['static']['value'])) { // POSTDATA means we're doing an insert now
        // Do we have a NEW setting to add? If not, let's get rid of the [new] offset.
        if (empty($_POST['set']['new']['setting']))
            unset($_POST['set']['new']);

        // Give it all a place.
        foreach ($_POST['set'] as $set) {
            if ($set['setting'] == 'lastWebChange')
                $set['value'] = time(); // This should always be as up-to-date as possible to reflect the latest change
            if ($set['setting'] == 'lastWebChangeStr')
                $set['value'] = date('M j Y H:i:s');
            $setAr[] = array(
                'setting' => (!empty($set['setting']) ? $set['setting'] : 0),
                'value' => (!empty($set['value']) ? $set['value'] : 0),
            );
        }

        // Make everything insertable...
        $i=0;
        foreach ($setAr as $v) {
            foreach ($v as $var => $val) {
                $allvars[] = "$var";
                $sanitized[$i][$var] = ($val !== 'NULL' ? '\'' : '').mysqli_real_escape_string($ak['mysqli'], $val).($val !== 'NULL' ? '\'' : '');
            }
            $i++;
        }
        $allvars = array_unique($allvars);

        // Insertion! Yay.
        $query = 'REPLACE INTO `'.$house['db'].'`.`house_webvars` (`'.implode('`, `', $allvars).'`) VALUES ';
        foreach ($sanitized as $ins)
            $queryins[] = '('.implode(', ', $ins).')';
        $query .= implode(', ', $queryins);

        // Here goes...
        $mysql = mysqli_query($ak['mysqli'], $query);
        if (!$mysql)
            commitRefresh(array( 'type' => 'data', 'info' => '<br />MySQL Error when querying:<br /><span class="sqlError">'.$query.'<br />'.mysqli_error($ak['mysqli']).'</span>', 'data' => $_POST['set'] ), 'pitemp.php?do=setWebVars'); // Aaww faack!

        // Well, if all went well, I guess we go back to where we were and let everyone know... Oh wait, it's just me here.
        AKerr('House Monitor RPi Settings Updated', 5);
        commitRefresh(array( 'type' => 'info', 'info' => 'Updated' ), 'pitemp.php?do=setWebVars');
    } else { // We're gonna make some changes.
        // Get the current cameras to populate our table.
        $query = mysqli_query($ak['mysqli'], "SELECT * FROM `$house[db]`.`house_webvars`");
        while ($s = mysqli_fetch_assoc($query))
            $data[] = $s;

        $return['data'] = '
<div id="pagetitle">Edit House RPi Values</div>
<div align="center">
    <form name="setWebVars" method="post" action="'.$_SERVER['PHP_SELF'].'?do=setWebVars">
        <table border="10px" width="1000px" cellspacing="2">
            <tr>
                <td width="120px">Setting</td>
                <td width="330px">Value</td>
            </tr>';

        // This is simple too.
        $i=0;
        $ti=1;
        foreach ($data as $set) {
            $return['data'] .= '
            <tr>
                <td><input name="set['.$i.'][setting]" type="text" size="15" value="'.$set['setting'].'" tabindex="'.$ti++.'" /></td>
                <td><input name="set['.$i.'][value]" type="text" size="50" value="'.$set['value'].'" tabindex="'.$ti++.'" /></td>
            </tr>';
            $i++;
        }
        // Now add one more table set, for any possible new tags!
        $return['data'] .= '
            <tr>
                <td colspan="3" style="text-align: center;" class="notice">New Setting</td>
            </tr>
            <tr>
                <td><input name="set[new][setting]" type="text" size="15" value="" tabindex="'.$ti++.'" /></td>
                <td><input name="set[new][value]" type="text" size="50" value="" tabindex="'.$ti++.'" /></td>
            </tr>
        </table>
        <input name="set[static][value]" type="hidden" value="'.time().'" />
        <button name="set[static][setting]" value="lastWebChange" tabindex="9001">Submit Settings</button>
    </form>
</div>';

        return $return;
    }
}

function house_loadWebVars() {
    global $ak, $house;
    // NoMySQL? No data.
    if (!$ak['nodb']) {
        $query = mysqli_query($ak['mysqli'], "SELECT * FROM `$house[db]`.`house_webvars`");
        while ($s = mysqli_fetch_assoc($query))
            $data[$s['setting']] = $s['value'];
        $data['data'] = 'good'; // Just so webvarloader.py can verify the data is in fact usable!
    } else
        $data['data'] = 'NoMySQL'; // But it's not usable because there is no data.
    die(json_encode($data));
}

function ksortRec(&$array) {
    if (!is_array($array))
        return false;
    ksort($array);
    foreach ($array as &$arr) {
        ksortRec($arr);
    }
}

function file_read_last_line($file_path) {
    $line = '';

    $f = fopen($file_path, 'r');
    $cursor = -1;
    fseek($f, $cursor, SEEK_END);
    $char = fgetc($f);
    // Trim trailing newline chars of the file
    while ($char === "\n" || $char === "\r") {
        fseek($f, $cursor--, SEEK_END);
        $char = fgetc($f);
    }
    // Read until the start of file or first newline char
    while ($char !== false && $char !== "\n" && $char !== "\r") {
        // Prepend the new char
        $line = $char . $line;
        fseek($f, $cursor--, SEEK_END);
        $char = fgetc($f);
    }
    fclose($f);
    return $line;
}

?>