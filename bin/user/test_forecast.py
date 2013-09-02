# $Id$
# Copyright: 2013 Matthew Wall
# License: GPLv3

"""Tests for weewx forecasting module."""

import configobj
import math
import os
import shutil
import string
import sys
import time
import unittest

import user
import weedb
import weewx
import weewx.wxengine as wxengine
import user.forecast as forecast

# to display output from tests that are designed to be run manually
PRINT_OUTPUT = False
#PRINT_OUTPUT = True
# put your wu api key here for testing
WU_API_KEY = 'INSERT_KEY_HERE'

# FIXME: these belong in a common testing library
TMPDIR = '/var/tmp/weewx_test'

def rmdir(d):
    try:
        os.rmdir(d)
    except:
        pass

def rmtree(d):
    try:
        shutil.rmtree(d)
    except:
        pass

def mkdir(d):
    try:
        os.makedirs(d)
    except:
        pass

def get_tmpdir():
    return TMPDIR + '/test_forecast'

def get_testdir(name):
    return get_tmpdir() + '/' + name

def rmfile(name):
    try:
        os.remove(name)
    except Exception:
        pass

def create_config(test_dir, service, skin_dir='testskin'):
    cd = configobj.ConfigObj()
    cd['debug'] = 1
    cd['WEEWX_ROOT'] = test_dir
    cd['Station'] = {
        'station_type' : 'Simulator',
        'altitude' : [10,'foot'],
        'latitude' : 10,
        'longitude' : 10
        }
    cd['Simulator'] = {
        'driver' : 'weewx.drivers.simulator',
        'mode' : 'generator'
        }
    cd['Engines'] = {
        'WxEngine' : {
            'service_list' : service
            }
        }
    cd['Databases'] = {
        'archive_sqlite' : {
            'root' : '%(WEEWX_ROOT)s',
            'database' : test_dir + '/archive.sdb',
            'driver' : 'weedb.sqlite'
            },
        'stats_sqlite' : {
            'root' : '%(WEEWX_ROOT)s',
            'database' : test_dir + '/stats.sdb',
            'driver' : 'weedb.sqlite'
            },
        'forecast_sqlite' : {
            'root' : '%(WEEWX_ROOT)s',
            'database' : test_dir + '/forecast.sdb',
            'driver' : 'weedb.sqlite'
            },
        'forecast_mysql' : {
            'host' : 'localhost',
            'user' : 'weewx',
            'password' : 'weewx',
            'database' : 'forecast',
            'driver' : 'weedb.mysql'
            }
        }
    cd['StdReport'] = {
        'HTML_ROOT' : test_dir + '/html',
        'SKIN_ROOT' : test_dir,
        'TestReport' : { 'skin' : skin_dir }
        }
    cd['StdArchive'] = {
        'archive_database' : 'archive_sqlite',
        'stats_database' : 'stats_sqlite'
        }
    cd['Forecast'] = {
        'database' : 'forecast_sqlite',
        'single_thread' : True,
        }
    return cd

# FIXME: make weewx work without having to specify so many items in config
#   Units
#   Labels
#   archive/stats databases
def create_skin_conf(test_dir, skin_dir='testskin'):
    '''create minimal skin config file for testing'''
    mkdir(test_dir + '/' + skin_dir)
    fn = test_dir + '/' + skin_dir + '/skin.conf'
    f = open(fn, 'w')
    f.write('''
[Units]
    [[Groups]]
        group_altitude     = foot
        group_degree_day   = degree_F_day
        group_direction    = degree_compass
        group_moisture     = centibar
        group_percent      = percent
        group_pressure     = mbar
        group_radiation    = watt_per_meter_squared
        group_rain         = inch
        group_rainrate     = inch_per_hour
        group_speed        = mile_per_hour
        group_speed2       = knot2
        group_temperature  = degree_F
        group_uv           = uv_index
        group_volt         = volt

        # The following groups are used internally and should not be changed:
        group_count        = count
        group_interval     = minute
        group_time         = unix_epoch
        group_elapsed      = second

    [[StringFormats]]
        centibar           = %.0f
        cm                 = %.2f
        cm_per_hour        = %.2f
        degree_C           = %.1f
        degree_F           = %.1f
        degree_compass     = %.0f
        foot               = %.0f
        hPa                = %.1f
        inHg               = %.3f
        inch               = %.2f
        inch_per_hour      = %.2f
        km_per_hour        = %.0f
        km_per_hour2       = %.1f
        knot               = %.0f
        knot2              = %.1f
        mbar               = %.1f
        meter              = %.0f
        meter_per_second   = %.1f
        meter_per_second2  = %.1f
        mile_per_hour      = %.1f
        mile_per_hour2     = %.1f
        mm                 = %.1f
        mmHg               = %.1f
        mm_per_hour        = %.1f
        percent            = %.0f
        uv_index           = %.1f
        volt               = %.1f
        watt_per_meter_squared = %.0f
        NONE               = "    -"

    [[Labels]]
        centibar          = " cb"
        cm                = " cm"
        cm_per_hour       = " cm/hr"
        degree_C          =   C
        degree_F          =   F
        degree_compass    =   deg
        foot              = " feet"
        hPa               = " hPa"
        inHg              = " inHg"
        inch              = " in"
        inch_per_hour     = " in/hr"
        km_per_hour       = " kph"
        km_per_hour2      = " kph"
        knot              = " knots"
        knot2             = " knots"
        mbar              = " mbar"
        meter             = " meters"
        meter_per_second  = " m/s"
        meter_per_second2 = " m/s"
        mile_per_hour     = " mph"
        mile_per_hour2    = " mph"
        mm                = " mm"
        mmHg              = " mmHg"
        mm_per_hour       = " mm/hr"
        percent           =   %
        volt              = " V"
        watt_per_meter_squared = " W/m^2"
        NONE              = ""
        
    [[TimeFormats]]
        day        = %H:%M
        week       = %H:%M on %A
        month      = %d.%m.%Y %H:%M
        year       = %d.%m.%Y %H:%M
        rainyear   = %d.%m.%Y %H:%M
        current    = %d.%m.%Y %H:%M
        ephem_day  = %H:%M
        ephem_year = %d.%m.%Y %H:%M
    [[DegreeDays]]
[Labels]
[Almanac]
    moon_phases = n,wc,fq,wg,f,wg,lq,wc
[FileGenerator]
    encoding = html_entities
    [[ToDate]]
        [[[current]]]
            template = index.html.tmpl
[Generators]
        generator_list = user.forecast.ForecastFileGenerator
''')
    f.close()


class FakeData(object):
    '''generate fake data for testing. portions copied from gen_fake_data.py'''

    start_tt = (2010,1,1,0,0,0,0,0,-1)
    stop_tt  = (2010,1,2,0,0,0,0,0,-1)
    start_ts = int(time.mktime(start_tt))
    stop_ts  = int(time.mktime(stop_tt))
    interval = 600

    @staticmethod
    def create_weather_databases(archive_db_dict, stats_db_dict):
        with weewx.archive.Archive.open_with_create(archive_db_dict, user.schemas.defaultArchiveSchema) as archive:
            archive.addRecord(FakeData.gen_fake_data())
            try:
                weedb.drop(stats_db_dict)
            except weedb.NoDatabase:
                pass
            with weewx.stats.StatsDb.open_with_create(stats_db_dict, user.schemas.defaultStatsSchema) as stats:
                stats.backfillFrom(archive)

    @staticmethod
    def create_forecast_database(forecast_db_dict, records):
        with weewx.archive.Archive.open_with_create(forecast_db_dict, user.forecast.defaultForecastSchema) as archive:
            archive.addRecord(records)

    @staticmethod
    def gen_fake_zambretti_data():
        ts = int(time.mktime((2013,8,22,12,0,0,0,0,-1)))
        codes = ['A', 'B', 'C', 'D', 'E', 'F', 'A', 'A', 'A']
        for code in codes:
            record = {}
            record['method'] = 'Zambretti'
            record['usUnits'] = weewx.US
            record['dateTime'] = ts
            record['issued_ts'] = ts
            record['event_ts'] = ts
            record['zcode'] = code
            ts += 300
            yield record

    @staticmethod
    def gen_fake_nws_data():
        text = '''MAZ014-262100-
CAMBRIDGE-MIDDLESEX MA
42.37N  71.12W ELEV. 10 FT
719 AM EDT MON AUG 26 2013

DATE             MON 08/26/13            TUE 08/27/13            WED 08/28/13
EDT 3HRLY     05 08 11 14 17 20 23 02 05 08 11 14 17 20 23 02 05 08 11 14 17 20
UTC 3HRLY     09 12 15 18 21 00 03 06 09 12 15 18 21 00 03 06 09 12 15 18 21 00

MAX/MIN                      81          68          83          67          82
TEMP             68 74 79 78 77 73 70 69 71 77 80 79 76 72 70 69 71 77 81 79 73
DEWPT            57 60 63 65 66 67 66 65 67 66 65 67 67 68 66 65 68 69 70 69 69
RH               68 62 58 64 69 81 87 87 87 69 60 67 74 87 87 87 90 76 69 72 87
WIND DIR         SW  W SW SW SW SW SW  W  N  E  E  E  E SE SE SE NW NE  E  E NE
WIND SPD          8 11 12 11  9  5  3  3  3  3  6  6  5  3  2  1  5  4  9  8  4
WIND GUST           21
CLOUDS           OV OV OV B2 B2 B2 B2 B2 B2 B1 B1 SC SC SC B1 B2 B2 B2 B2 B2 B2
POP 12HR                     50          20          20          20          40
QPF 12HR                   0.11        0.06           0           0        0.30
SNOW 12HR                 00-00       00-00       00-00
RAIN SHWRS        C  C  C  C  S  S              S  S     S  S  S  S  C  C  C  C
TSTMS                      S  S  S              S  S     S  S  S  S  C  C  C  C


DATE          THU 08/29/13  FRI 08/30/13  SAT 08/31/13  SUN 09/01/13
EDT 6HRLY     02 08 14 20   02 08 14 20   02 08 14 20   02 08 14 20
UTC 6HRLY     06 12 18 00   06 12 18 00   06 12 18 00   06 12 18 00

MIN/MAX          66    80      63    80      64    84      64    86
TEMP          69 69 79 72   66 67 79 73   67 69 83 74   68 68 84 76
DEWPT         66 66 64 62   61 61 60 60   59 60 59 60   61 63 62 63
PWIND DIR        NE     N       N     N      SW    SW      SW    SW
WIND CHAR        LT    LT      LT    LT      LT    LT      LT    LT
AVG CLOUDS    B2 B1 B1 B1   SC SC SC SC   SC SC SC SC   SC SC SC SC
POP 12HR         40    30      10    10      10    10       5    10
RAIN SHWRS     C  S  S  S
TSTMS          C     S  S

$$
'''
        matrix = forecast.ParseNWSForecast(text, 'MAZ014')
        records = forecast.ProcessNWSForecast('BOX', 'MAZ014', matrix)
        return records

    @staticmethod
    def gen_fake_wu_data():
        pass

    @staticmethod
    def gen_fake_xtide_data():
        records = [{'hilo': 'L', 'offset': '-0.71', 'event_ts': 1377031620,
                    'method': 'XTide', 'usUnits': 1, 'dateTime': 1377043837,
                    'issued_ts': 1377031620 },
                   {'hilo': 'H', 'offset': '11.56', 'event_ts': 1377054240,
                    'method': 'XTide', 'usUnits': 1, 'dateTime': 1377043837,
                    'issued_ts': 1377031620 },
                   {'hilo': 'L', 'offset': '-1.35', 'event_ts': 1377077040,
                    'method': 'XTide', 'usUnits': 1, 'dateTime': 1377043837,
                    'issued_ts': 1377031620 },
                   {'hilo': 'H', 'offset': '10.73', 'event_ts': 1377099480,
                    'method': 'XTide', 'usUnits': 1, 'dateTime': 1377043837,
                    'issued_ts': 1377031620 },
                   {'hilo': 'L', 'offset': '-0.95', 'event_ts': 1377121260,
                    'method': 'XTide', 'usUnits': 1, 'dateTime': 1377043837,
                    'issued_ts': 1377031620 },
                   {'hilo': 'H', 'offset': '11.54', 'event_ts': 1377143820,
                    'method': 'XTide', 'usUnits': 1, 'dateTime': 1377043837,
                    'issued_ts': 1377031620 },
                   {'hilo': 'L', 'offset': '-1.35', 'event_ts': 1377166380,
                    'method': 'XTide', 'usUnits': 1, 'dateTime': 1377043837,
                    'issued_ts': 1377031620 }]
        return records

    @staticmethod
    def gen_fake_data(start_ts=start_ts, stop_ts=stop_ts, interval=interval):
        daily_temp_range = 40.0
        annual_temp_range = 80.0
        avg_temp = 40.0

        # Four day weather cycle:
        weather_cycle = 3600*24.0*4
        weather_baro_range = 2.0
        weather_wind_range = 10.0
        avg_baro = 30.0

        count = 0
        for ts in xrange(start_ts, stop_ts+interval, interval):
            daily_phase  = (ts - start_ts) * 2.0 * math.pi / (3600*24.0)
            annual_phase = (ts - start_ts) * 2.0 * math.pi / (3600*24.0*365.0)
            weather_phase= (ts - start_ts) * 2.0 * math.pi / weather_cycle
            record = {}
            record['dateTime']  = ts
            record['usUnits']   = weewx.US
            record['interval']  = interval
            record['outTemp']   = 0.5 * (-daily_temp_range*math.sin(daily_phase) - annual_temp_range*math.cos(annual_phase)) + avg_temp
            record['barometer'] = 0.5 * weather_baro_range*math.sin(weather_phase) + avg_baro
            record['windSpeed'] = abs(weather_wind_range*(1.0 + math.sin(weather_phase)))
            record['windDir'] = math.degrees(weather_phase) % 360.0
            record['windGust'] = 1.2*record['windSpeed']
            record['windGustDir'] = record['windDir']
            if math.sin(weather_phase) > .95:
                record['rain'] = 0.02 if math.sin(weather_phase) > 0.98 else 0.01
            else:
                record['rain'] = 0.0

        # Make every 71st observation (a prime number) a null. This is a
        # deterministic algorithm, so it will produce the same results every
        # time.                             
            for obs_type in filter(lambda x : x not in ['dateTime', 'usUnits', 'interval'], record):
                count+=1
                if count%71 == 0:
                    record[obs_type] = None
            yield record



PFM_BOS = '''<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en"><head>
<meta http-equiv="Content-Type" content="application/xhtml+xml; charset=utf-8" />
<link rel="schema.DC" href="http://purl.org/dc/elements/1.1/" /><title>National Weather Service Text Product Display</title>
<meta name="DC.title" content="National Weather Service Text Product Display" />
<meta name="DC.description" content="National Weather Service is your source for the most complete weather forecast and weather related information on the web" />
<meta name="DC.creator" content="US Department of Commerce, NOAA, National Weather Service" />
<meta name="DC.date.created" scheme="ISO8601" content="2013-05-01" />
<meta name="DC.date.reviewed" scheme="ISO8601" content="2012-07-19" />
<meta name="DC.language" scheme="DCTERMS.RFC1766" content="EN-US" />
<meta name="DC.keywords" content="weather, local weather forecast, local forecast, weather forecasts, local weather, radar, fire weather, center weather service units, hamweather" />
<meta name="DC.publisher" content="NOAA's National Weather Service" />
<meta name="DC.contributor" content="National Weather Service" />
<meta name="DC.rights" content="http://www.weather.gov/disclaimer.php" />
<meta name="rating" content="General" />
<meta name="robots" content="index,follow" />
<meta name="Distribution" content="Global" />
<meta http-equiv="Content-Style-Type" content="text/css" />
<meta http-equiv="Content-Script-Type" content="text/javascript" />
<link href="/css/default/secondary.css" title="nwsstyle" rel="stylesheet" type="text/css" media="all" />
<link href="/css/product/main.css" title="nwsstyle" rel="stylesheet" type="text/css" media="all"></head>
<body>
<div id="container"><a href="#skipnav" class="skip">Skip Navigation</a>
<a name="skipnav"></a>
<div id="local"> <div id="localcontent">
<!-- // CONTENT STARTS HERE -->

<span style="font-size: 20px; font-weight:bold;">Point Forecast Matrices </span><br />Issued by NWS Boston, MA<br /><br /><div><b>Current Version</b>&nbsp;|&nbsp;<a href="?site=NWS&issuedby=BOX&product=PFM&format=TXT&version=2&glossary=0">Previous Version</a>&nbsp;|&nbsp;<a href="?site=NWS&issuedby=BOX&product=PFM&format=ci&version=1&glossary=0">Graphics & Text</a>&nbsp;|&nbsp;<a href="javascript:window.print()">Print</a>&nbsp;|&nbsp;<a href="product_types.php?site=NWS">Product List</a>&nbsp;|&nbsp;<a href="?site=NWS&issuedby=BOX&product=PFM&format=TXT&version=1&glossary=1">Glossary On</a></div><div>Versions: <b>1</b>
<a href="?site=NWS&issuedby=BOX&product=PFM&format=TXT&version=2&glossary=0">2</a>
<a href="?site=NWS&issuedby=BOX&product=PFM&format=TXT&version=3&glossary=0">3</a>
<a href="?site=NWS&issuedby=BOX&product=PFM&format=TXT&version=4&glossary=0">4</a>
<a href="?site=NWS&issuedby=BOX&product=PFM&format=TXT&version=5&glossary=0">5</a>
<a href="?site=NWS&issuedby=BOX&product=PFM&format=TXT&version=6&glossary=0">6</a>
<a href="?site=NWS&issuedby=BOX&product=PFM&format=TXT&version=7&glossary=0">7</a>
<a href="?site=NWS&issuedby=BOX&product=PFM&format=TXT&version=8&glossary=0">8</a>
<a href="?site=NWS&issuedby=BOX&product=PFM&format=TXT&version=9&glossary=0">9</a>
<a href="?site=NWS&issuedby=BOX&product=PFM&format=TXT&version=10&glossary=0">10</a> <hr size="1" width="520"noshade="noshade" align="left" /></div><pre class="glossaryProduct">
000
FOUS51 KBOX 111720
PFMBOX

POINT FORECAST MATRICES
NATIONAL WEATHER SERVICE TAUNTON MA
119 PM EDT SAT MAY 11 2013

MAZ015-112100-
BOSTON-SUFFOLK MA
42.36N  71.04W ELEV. 20 FT
119 PM EDT SAT MAY 11 2013

DATE             SAT 05/11/13            SUN 05/12/13            MON 05/13/13
EDT 3HRLY     05 08 11 14 17 20 23 02 05 08 11 14 17 20 23 02 05 08 11 14 17 20
UTC 3HRLY     09 12 15 18 21 00 03 06 09 12 15 18 21 00 03 06 09 12 15 18 21 00

MAX/MIN                      70          57          69          45          59
TEMP                   67 67 65 63 61 59 62 65 68 67 62 53 49 46 49 55 58 58 53
DEWPT                  58 57 60 58 57 56 56 55 49 42 37 34 31 30 29 29 27 30 27
RH                     73 70 84 84 87 90 81 70 51 40 39 48 50 53 46 37 30 34 36
WIND DIR               SW SW SW SW  S  S SW  W  W  W  W  W  W  W  W  W  W SW  W
WIND SPD               18 14 11  9  9  8 10 11 16 19 17 12 12 10 13  9 17 12 10
WIND GUST                                            28             20
CLOUDS                 OV OV OV OV OV OV OV OV B2 SC CL FW CL CL CL FW FW SC SC
POP 12HR                     90          90          80           0           5
QPF 12HR                   0.23        0.15        0.05           0           0
SNOW 12HR                 00-00       00-00       00-00
RAIN SHWRS                 L  D  L  C  L  D  C  C  S
TSTMS                      S  C  S  S        S  S
OBVIS                        PF PF PF PF PF


DATE          TUE 05/14/13  WED 05/15/13  THU 05/16/13  FRI 05/17/13
EDT 6HRLY     02 08 14 20   02 08 14 20   02 08 14 20   02 08 14 20
UTC 6HRLY     06 12 18 00   06 12 18 00   06 12 18 00   06 12 18 00

MIN/MAX          42    58      44    63      50    65      55    66
TEMP          45 47 57 52   46 49 62 58   52 54 64 61   56 58 65 61
DEWPT         36 34 30 33   33 36 35 40   44 48 50 51   52 52 50 50
PWIND DIR        NW    NW      NW    SW       S     S       S    SW
WIND CHAR        GN    LT      LT    LT      LT    GN      LT    LT
AVG CLOUDS    FW FW SC SC   FW FW FW SC   SC B1 B2 B2   B2 B2 B2 B2
POP 12HR          5    10       5    10      20    40      50    40
RAIN SHWRS           S  S                  S  S  S  C    C  C  C  C

$$

RIZ004-112100-
WARWICK-KENT RI
41.72N  71.43W ELEV. 55 FT
119 PM EDT SAT MAY 11 2013

DATE             SAT 05/11/13            SUN 05/12/13            MON 05/13/13
EDT 3HRLY     05 08 11 14 17 20 23 02 05 08 11 14 17 20 23 02 05 08 11 14 17 20
UTC 3HRLY     09 12 15 18 21 00 03 06 09 12 15 18 21 00 03 06 09 12 15 18 21 00

MAX/MIN                      70          58          72          42          62
TEMP                   66 65 63 60 59 59 60 64 71 68 62 52 47 43 48 57 61 60 53
DEWPT                  59 58 59 57 57 56 55 54 47 41 38 35 32 31 30 28 26 29 28
RH                     78 78 87 90 93 90 84 70 42 37 41 52 56 62 49 33 26 31 38
WIND DIR                S SW  S  S  S SW SW  W  W  W  W  W  W  W  W SW SW SW  W
WIND SPD               17 11  9  8  6  6  5 10 17 16 11  9  9  5 10 10 14 16  9
WIND GUST              27 24                         21          21
CLOUDS                 OV B2 OV OV OV OV OV OV B1 SC SC B1 CL CL FW FW FW SC SC
POP 12HR                     90          90          90           0           5
QPF 12HR                   0.17        0.21        0.04           0           0
SNOW 12HR                 00-00       00-00       00-00
RAIN SHWRS              O  O  D  L  L  L  D  L  S
TSTMS                   C  C  C  S  S     C  S  S
OBVIS                        PF PF PF PF PF


DATE          TUE 05/14/13  WED 05/15/13  THU 05/16/13  FRI 05/17/13
EDT 6HRLY     02 08 14 20   02 08 14 20   02 08 14 20   02 08 14 20
UTC 6HRLY     06 12 18 00   06 12 18 00   06 12 18 00   06 12 18 00

MIN/MAX          39    63      42    67      49    70      53    72
TEMP          43 46 61 55   45 49 65 60   52 55 68 63   56 59 71 64
DEWPT         31 32 30 34   35 37 36 41   45 49 50 51   52 52 50 51
PWIND DIR        NW    NW      NW    SW       S     S       S     S
WIND CHAR        GN    LT      LT    LT      LT    GN      LT    LT
AVG CLOUDS    FW FW FW SC   FW FW FW SC   SC B1 B2 B2   B2 B2 B2 B2
POP 12HR          5    10       5    10      20    30      30    40
RAIN SHWRS           S  S                  S  S  S  C    C  C  C  C

$$

CTZ002-112100-
WINDSOR LOCKS-HARTFORD CT
41.94N  72.68W ELEV. 173 FT
119 PM EDT SAT MAY 11 2013

DATE             SAT 05/11/13            SUN 05/12/13            MON 05/13/13
EDT 3HRLY     05 08 11 14 17 20 23 02 05 08 11 14 17 20 23 02 05 08 11 14 17 20
UTC 3HRLY     09 12 15 18 21 00 03 06 09 12 15 18 21 00 03 06 09 12 15 18 21 00

MAX/MIN                      71          55          69          38          63
TEMP                   68 67 66 62 59 57 59 63 69 65 58 48 43 40 45 56 61 61 52
DEWPT                  60 60 59 57 54 52 50 47 40 35 32 29 29 28 28 29 22 28 25
RH                     76 78 78 84 83 83 72 56 35 33 37 47 57 62 51 35 22 28 35
WIND DIR               SW  S  S  S  S SW  W  W  W  W  W  W  W SW  W  W  W  W NW
WIND SPD               13 11  8  5  4  4  5 11 16 17 12  8  8  6  9 10 13 14  8
WIND GUST              27                                        19
CLOUDS                 OV OV B2 OV OV OV OV B1 OV SC B1 CL CL CL CL FW SC SC SC
POP 12HR                    100          40          40           0          10
QPF 12HR                   0.43           0           0           0           0
SNOW 12HR                 00-00       00-00       00-00
RAIN SHWRS              O  O  C  C  C  C  C  C  S
TSTMS                   C  C  S  S


DATE          TUE 05/14/13  WED 05/15/13  THU 05/16/13  FRI 05/17/13
EDT 6HRLY     02 08 14 20   02 08 14 20   02 08 14 20   02 08 14 20
UTC 6HRLY     06 12 18 00   06 12 18 00   06 12 18 00   06 12 18 00

MIN/MAX          36    64      39    72      48    74      53    77
TEMP          40 44 62 54   43 49 70 63   52 56 72 66   56 60 75 66
DEWPT         30 32 26 31   32 35 35 41   45 49 52 53   52 52 50 51
PWIND DIR        NW    NW      NW    SW       S     S       S     W
WIND CHAR        LT    GN      LT    LT      LT    LT      LT    LT
AVG CLOUDS    SC FW FW SC   FW FW FW SC   B1 B2 B2 B2   B2 B2 B1 B1
POP 12HR          5    10       5    20      40    40      50    40
RAIN SHWRS           S  S             S    C  C  C  C    C  C  C  C

$$
</pre>



<!-- // CONTENT ENDS HERE -->
</div></div>
<hr width="100%" />
<div id="required">
<div id="firstgov"><a href="/nwsexit.php?url=http://www.usa.gov/"><img src="/css/default/images/usagov.gif" alt="USA.gov is the U.S. government's official web portal to all federal, state and local government web resources and services." class="img" width="110" height="30" /></a></div>
<ul id="contact">
<li>National Weather Service</li>
<li>National Weather Service National Headquarters</li>
<li>1325 East West Highway</li><li>Silver Spring, MD  20910</li>
<li></li>
Incorrect Region Format!<li>Web Master's E-mail: <a href="mailto:">NWS Internet Services Team</a></li>
<li>Page last modified: May 1st, 2013 15:31 UTC</li>
</ul>
<ul id="disclaimer">
<li><a href="http://www.weather.gov/disclaimer.php">Disclaimer</a></li>
<li><a href="http://www.weather.gov/credits.php">Credits</a></li>
<li><a href="http://www.weather.gov/glossary/">Glossary</a></li>
</ul>
<ul id="policy">
<li><a href="http://www.weather.gov/privacy.php">Privacy Policy</a></li>
<li><a href="http://www.weather.gov/admin.php">About Us</a></li>
<li><a href="http://www.weather.gov/careers.php">Career Opportunities</a></li>
</ul>
</div></div>
</body></html>
'''

PFM_BOS_SINGLE = '''MAZ014-112100-
CAMBRIDGE-MIDDLESEX MA
42.37N  71.12W ELEV. 10 FT
119 PM EDT SAT MAY 11 2013

DATE             SAT 05/11/13            SUN 05/12/13            MON 05/13/13
EDT 3HRLY     05 08 11 14 17 20 23 02 05 08 11 14 17 20 23 02 05 08 11 14 17 20
UTC 3HRLY     09 12 15 18 21 00 03 06 09 12 15 18 21 00 03 06 09 12 15 18 21 00

MAX/MIN                      72          57          69          43          61
TEMP                   69 68 66 63 61 59 62 66 68 68 61 52 47 44 48 56 60 59 53
DEWPT                  59 58 60 58 57 56 56 55 49 41 37 33 31 29 29 29 26 28 26
RH                     70 70 81 84 87 90 81 68 51 37 41 48 53 55 47 35 27 30 35
WIND DIR               SW SW SW  S  S  S SW  W  W  W  W  W  W  W  W  W  W SW  W
WIND SPD               17 14 11  9  8  8 10 11 16 18 14 11 10  8 12  9 16 12  9
WIND GUST                                            27          23 20    23
CLOUDS                 OV OV OV OV OV OV OV OV B2 B1 CL FW CL CL CL FW FW SC SC
POP 12HR                    100          90          70           0           5
QPF 12HR                   0.25        0.14        0.05           0           0
SNOW 12HR                 00-00       00-00       00-00
RAIN SHWRS                 L  D  L  C  L  L  C  C  S
TSTMS                      S  C  S  S        S  S
OBVIS                        PF PF PF PF PF


DATE          TUE 05/14/13  WED 05/15/13  THU 05/16/13  FRI 05/17/13
EDT 6HRLY     02 08 14 20   02 08 14 20   02 08 14 20   02 08 14 20
UTC 6HRLY     06 12 18 00   06 12 18 00   06 12 18 00   06 12 18 00

MIN/MAX          41    60      42    67      49    68      54    70
TEMP          44 47 59 53   45 49 65 60   52 55 67 63   56 59 69 63
DEWPT         35 33 29 32   33 35 34 39   44 48 50 51   52 52 50 50
PWIND DIR        NW    NW      NW    SW       S     S       S    SW
WIND CHAR        GN    LT      LT    LT      LT    LT      LT    LT
AVG CLOUDS    FW FW SC SC   FW FW FW SC   SC B1 B2 B2   B2 B2 B2 B2
POP 12HR          5    10       5    10      20    40      50    40
RAIN SHWRS           S  S                  S  S  S  C    C  C  C  C

$$
'''

# this forecast was downloaded on 25aug2013
# it contains 100% for many rh values, which means parsing on whitespace fails
PFM_GYX_SINGLE_1 = '''MEZ027-260915-
ROCKLAND-KNOX ME
44.07N  69.08W ELEV. 56 FT
423 PM EDT SUN AUG 25 2013

DATE           08/25/13      MON 08/26/13            TUE 08/27/13            WED
EDT 3HRLY     17 20 23 02 05 08 11 14 17 20 23 02 05 08 11 14 17 20 23 02 05 08
UTC 3HRLY     21 00 03 06 09 12 15 18 21 00 03 06 09 12 15 18 21 00 03 06 09 12

MIN/MAX                      58          69          58          75          59
TEMP          74 68 63 60 58 60 67 69 68 65 61 59 58 62 71 75 74 67 63 61 59 61
DEWPT         53 55 56 58 58 58 59 60 61 61 61 59 58 61 62 63 64 64 62 61 59 61
RH            48 63 78 93100 93 75 73 78 87100100100 97 73 66 71 90 97100100100
WIND DIR       S SW SW  S  S  S  S SW SW  S  W  N  N  N  E SE SE SE SE  E SE SE
WIND SPD       8  6  8  9 10 10 12 14 11  8  4  2  3  3  3  3  4  4  4  3  3  3
CLOUDS        FW FW SC B1 B2 OV B2 B1 B1 SC B1 B1 B1 B1 B1 SC SC SC SC SC B1 B1
POP 12HR                     30          20          20          20          30
QPF 12HR                      0           0           0           0        0.01
SNOW 12HR                 00-00       00-00       00-00
RAIN SHWRS           S  C  S  S  S  S  S  S  S  S  S  S  S  S              S  C
TSTMS                                                 S  S  S              S  S


DATE           08/28  THU 08/29/13  FRI 08/30/13  SAT 08/31/13  SUN 09/01/13
EDT 6HRLY     14 20   02 08 14 20   02 08 14 20   02 08 14 20   02 08 14 20
UTC 6HRLY     18 00   06 12 18 00   06 12 18 00   06 12 18 00   06 12 18 00

MAX/MIN          72      62    74      59    75      56    72      57    74
TEMP          72 68   63 65 74 67   61 62 75 67   58 59 72 65   59 60 74 66
DEWPT         64 63   62 64 65 63   59 58 57 56   53 54 53 54   55 57 58 58
PWIND DIR        SE       E     N      NW     W      NW     W      SW    SW
WIND CHAR        LT      LT    LT      LT    LT      LT    LT      LT    LT
AVG CLOUDS    B1 B2   B2 OV B2 B1   B1 SC SC SC   SC FW FW FW   SC SC SC B1
POP 12HR         40      40    40      20    20      10    10      10    20
RAIN SHWRS     C  C    C  C  C  C    S  S  S  S                        S  S
TSTMS          S  S    S  S

$$
'''

# this forecast was downloaded around 13:00 on 26aug2013
# it has MM instead of numeric values and odd values for wind chill
PFM_GYX_SINGLE_2 = '''MEZ027-262100-
ROCKLAND-KNOX ME
44.07N  69.08W ELEV. 56 FT
115 PM EDT MON AUG 26 2013

DATE             MON 08/26/13            TUE 08/27/13            WED 08/28/13
EDT 3HRLY     05 08 11 14 17 20 23 02 05 08 11 14 17 20 23 02 05 08 11 14 17 20
UTC 3HRLY     09 12 15 18 21 00 03 06 09 12 15 18 21 00 03 06 09 12 15 18 21 00

MAX/MIN                      72          58          73          60          68
TEMP                   69 70 65 63 61 60 63 68 71 68 65 62 61 61 64 66 68 67 64
DEWPT                  61 62 62 61 61 59 62 65 66 64 63 62 61 61 63 MM 68 MM 64
RH                     76 76 90 93100 96 97 90 84 87 93100100100 97 MM100 MM100
WIND DIR               SW SW SW  S  W NE  N  S  S  S  S  S SE  E NE MM  N MM NW
WIND SPD               10  8  5  5  2  2  2  3  8  4  2  2  2  3  6 MM  2 MM  3
CLOUDS                 FW SC SC SC SC B1 B2 B1 SC SC SC B1 B1 B2 B2 MM B2 MM B2
POP 12HR                     20          20          20          20          30
QPF 12HR                      0        0.01           0           0        0.12
SNOW 12HR                 00-00       00-00       00-00
RAIN SHWRS              S  S     S  S  S  S  S  S  S  S  S  S  S  S  S  S  C  C
TSTMS                                           S  S  S
OBVIS                                                      PF PF
WIND CHILL                                                         -120-120-120-120
MIN CHILL                                                            -120  -120


DATE          THU 08/29/13  FRI 08/30/13  SAT 08/31/13  SUN 09/01/13
EDT 6HRLY     02 08 14 20   02 08 14 20   02 08 14 20   02 08 14 20
UTC 6HRLY     06 12 18 00   06 12 18 00   06 12 18 00   06 12 18 00

MIN/MAX          61    68      58    73      56    72      57    74
TEMP          63 65 68 62   60 61 72 64   58 59 71 64   59 60 73 66
DEWPT         63 62 64 60   58 57 56 56   57 59 59 59   59 60 61 60
PWIND DIR        NW    NE       N    NW      SW    SW       W    SW
WIND CHAR        LT    GN      LT    LT      LT    LT      LT    LT
AVG CLOUDS    B2 B2 B2 B2   B1 B1 SC SC   SC SC SC SC   SC SC B1 SC
POP 12HR         30    40      10    10      10    10       5     5
RAIN SHWRS     C  C  C  C
TSTMS             S  C  C

$$
'''

# this forecast was downloaded around 19:45 on 26aug2013
# this forecast cleared the MM values, but still contains many 100 values
PFM_GYX_SINGLE_3 = '''MEZ027-270915-
ROCKLAND-KNOX ME
44.07N  69.08W ELEV. 56 FT
550 PM EDT MON AUG 26 2013

DATE           08/26/13      TUE 08/27/13            WED 08/28/13            THU
EDT 3HRLY     17 20 23 02 05 08 11 14 17 20 23 02 05 08 11 14 17 20 23 02 05 08
UTC 3HRLY     21 00 03 06 09 12 15 18 21 00 03 06 09 12 15 18 21 00 03 06 09 12

MIN/MAX                      58          73          59          68          61
TEMP             66 62 60 58 61 69 73 72 66 62 60 59 61 66 68 68 65 63 62 61 63
DEWPT            63 61 60 58 61 65 66 64 63 60 59 59 61 66 68 67 64 63 62 61 62
RH               90 97100100100 87 79 76 90 93 96100100100100 97 97100100100 97
WIND DIR         SW  S  W NE  N  S  S  S SE  E NE NE NE  N  N NW NW NW NW  N  N
WIND SPD          5  5  2  2  2  3  9  8  4  3  2  4  6  4  2  3  3  4  5  8 10
CLOUDS           FW SC SC SC B1 B1 SC SC B1 B1 B1 B2 B2 B2 B2 B2 B2 B2 B2 B2 B2
POP 12HR                     20          20          20          30          40
QPF 12HR                      0           0           0        0.02        0.11
SNOW 12HR                 00-00       00-00       00-00
RAIN SHWRS                 S  S  S  S  S  S  S  S  S  S  C  C  C  C  C  C  C  C
TSTMS                                                 S  C  C  C              C


DATE           08/29  FRI 08/30/13  SAT 08/31/13  SUN 09/01/13  MON 09/02/13
EDT 6HRLY     14 20   02 08 14 20   02 08 14 20   02 08 14 20   02 08 14 20
UTC 6HRLY     18 00   06 12 18 00   06 12 18 00   06 12 18 00   06 12 18 00

MAX/MIN          68      58    72      59    74      59    76      60    75
TEMP          68 64   59 61 72 66   60 62 74 67   61 62 76 69   62 63 75 68
DEWPT         64 60   59 60 60 60   58 60 61 60   60 61 61 60   59 60 62 60
PWIND DIR        NE      NE     W      SW    SW      SW    SE       S     S
WIND CHAR        GN      LT    LT      LT    LT      LT    LT      LT    GN
AVG CLOUDS    B2 B2   B1 B1 SC SC   SC SC SC SC   SC B1 B1 SC   B1 B1 B1 B1
POP 12HR         40      20    10      10    10      10    10      10    20
RAIN SHWRS     C  C    S  S                                            S  S
TSTMS          C  C

$$
'''

WU_BOS = '''
{
  "response": {
    "version": "0.1"
      ,"termsofService": "http://www.wunderground.com/weather/api/d/terms.html"
      ,"features": {
        "forecast10day": 1
        }
  }
  ,
  "forecast":{
    "txt_forecast": {
      "date":"11:00 AM EDT",
      "forecastday": [
        {
          "period":0,
          "icon":"chancerain",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/chancerain.gif",
          "title":"Wednesday",
          "fcttext":"Partly cloudy in the morning, then overcast with a chance of rain. High of 68F. Breezy. Winds from the SSW at 10 to 20 mph with gusts to 30 mph. Chance of rain 50%.",
          "fcttext_metric":"Partly cloudy in the morning, then overcast with a chance of rain. High of 20C. Windy. Winds from the SSW at 15 to 30 km/h with gusts to 50 km/h. Chance of rain 50%.",
          "pop":"50"
          }
      ,
      {
        "period":1,
          "icon":"tstorms",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/tstorms.gif",
          "title":"Wednesday Night",
          "fcttext":"Overcast with thunderstorms and rain showers in the evening, then partly cloudy with a chance of rain. Fog overnight. Low of 55F. Breezy. Winds from the SW at 10 to 20 mph. Chance of rain 60%.",
          "fcttext_metric":"Overcast with thunderstorms and rain showers in the evening, then partly cloudy with a chance of rain. Fog overnight. Low of 13C. Windy. Winds from the SW at 15 to 30 km/h. Chance of rain 60%.",
          "pop":"60"
          }
      ,
      {
        "period":2,
          "icon":"partlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
          "title":"Thursday",
          "fcttext":"Partly cloudy in the morning, then clear. High of 77F. Windy. Winds from the West at 10 to 25 mph with gusts to 35 mph.",
          "fcttext_metric":"Partly cloudy in the morning, then clear. High of 25C. Windy. Winds from the West at 20 to 40 km/h with gusts to 60 km/h.",
          "pop":"10"
          }
      ,
      {
        "period":3,
          "icon":"clear",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/clear.gif",
          "title":"Thursday Night",
          "fcttext":"Clear. Low of 54F. Winds from the WNW at 5 to 15 mph with gusts to 30 mph.",
          "fcttext_metric":"Clear. Low of 12C. Windy. Winds from the WNW at 10 to 25 km/h with gusts to 50 km/h.",
          "pop":"0"
          }
      ,
      {
        "period":4,
          "icon":"clear",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/clear.gif",
          "title":"Friday",
          "fcttext":"Clear. High of 72F. Winds from the NW at 5 to 15 mph.",
          "fcttext_metric":"Clear. High of 22C. Breezy. Winds from the NW at 10 to 20 km/h.",
          "pop":"10"
          }
      ,
      {
        "period":5,
          "icon":"clear",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/clear.gif",
          "title":"Friday Night",
          "fcttext":"Clear. Low of 54F. Winds from the SW at 5 to 10 mph shifting to the NW after midnight.",
          "fcttext_metric":"Clear. Low of 12C. Winds from the SW at 5 to 15 km/h shifting to the NW after midnight.",
          "pop":"0"
          }
      ,
      {
        "period":6,
          "icon":"partlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
          "title":"Saturday",
          "fcttext":"Mostly cloudy. High of 70F. Winds from the NW at 5 to 10 mph shifting to the ENE in the afternoon.",
          "fcttext_metric":"Mostly cloudy. High of 21C. Winds from the NW at 10 to 15 km/h shifting to the ENE in the afternoon.",
          "pop":"0"
          }
      ,
      {
        "period":7,
          "icon":"partlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
          "title":"Saturday Night",
          "fcttext":"Partly cloudy. Low of 48F. Winds from the SE at 5 to 10 mph.",
          "fcttext_metric":"Partly cloudy. Low of 9C. Winds from the SE at 5 to 15 km/h.",
          "pop":"0"
          }
      ,
      {
        "period":8,
          "icon":"mostlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/mostlycloudy.gif",
          "title":"Sunday",
          "fcttext":"Overcast. High of 66F. Winds from the SE at 5 to 10 mph.",
          "fcttext_metric":"Overcast. High of 19C. Breezy. Winds from the SE at 10 to 20 km/h.",
          "pop":"0"
          }
      ,
      {
        "period":9,
          "icon":"partlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
          "title":"Sunday Night",
          "fcttext":"Partly cloudy. Fog overnight. Low of 48F. Winds from the SSE at 5 to 10 mph.",
          "fcttext_metric":"Partly cloudy. Fog overnight. Low of 9C. Winds from the SSE at 10 to 15 km/h.",
          "pop":"0"
          }
      ,
      {
        "period":10,
          "icon":"cloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/cloudy.gif",
          "title":"Monday",
          "fcttext":"Overcast. High of 68F. Winds from the South at 10 to 15 mph.",
          "fcttext_metric":"Overcast. High of 20C. Breezy. Winds from the South at 15 to 25 km/h.",
          "pop":"0"
          }
      ,
      {
        "period":11,
          "icon":"partlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
          "title":"Monday Night",
          "fcttext":"Partly cloudy with a chance of rain. Fog overnight. Low of 52F. Winds from the South at 5 to 10 mph shifting to the WSW after midnight. Chance of rain 20%.",
          "fcttext_metric":"Partly cloudy with a chance of rain. Fog overnight. Low of 11C. Winds from the South at 10 to 15 km/h shifting to the WSW after midnight.",
          "pop":"20"
          }
      ,
      {
        "period":12,
          "icon":"mostlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/mostlycloudy.gif",
          "title":"Tuesday",
          "fcttext":"Mostly cloudy. High of 73F. Winds from the ENE at 5 to 10 mph.",
          "fcttext_metric":"Mostly cloudy. High of 23C. Breezy. Winds from the ENE at 10 to 20 km/h.",
          "pop":"0"
          }
      ,
      {
        "period":13,
          "icon":"mostlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/mostlycloudy.gif",
          "title":"Tuesday Night",
          "fcttext":"Overcast. Low of 54F. Winds from the NE at 5 to 10 mph.",
          "fcttext_metric":"Overcast. Low of 12C. Winds from the NE at 5 to 15 km/h.",
          "pop":"0"
          }
      ,
      {
        "period":14,
          "icon":"partlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
          "title":"Wednesday",
          "fcttext":"Partly cloudy. High of 77F. Winds from the East at 5 to 10 mph.",
          "fcttext_metric":"Partly cloudy. High of 25C. Winds from the East at 5 to 15 km/h.",
          "pop":"0"
          }
      ,
      {
        "period":15,
          "icon":"partlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
          "title":"Wednesday Night",
          "fcttext":"Partly cloudy. Fog overnight. Low of 55F. Winds less than 5 mph.",
          "fcttext_metric":"Partly cloudy. Fog overnight. Low of 13C. Winds less than 5 km/h.",
          "pop":"0"
          }
      ,
      {
        "period":16,
          "icon":"partlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
          "title":"Thursday",
          "fcttext":"Partly cloudy. High of 75F. Winds less than 5 mph.",
          "fcttext_metric":"Partly cloudy. High of 24C. Winds less than 5 km/h.",
          "pop":"0"
          }
      ,
      {
        "period":17,
          "icon":"partlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
          "title":"Thursday Night",
          "fcttext":"Partly cloudy. Fog overnight. Low of 54F. Winds less than 5 mph.",
          "fcttext_metric":"Partly cloudy. Fog overnight. Low of 12C. Winds less than 5 km/h.",
          "pop":"0"
          }
      ,
      {
        "period":18,
          "icon":"chancetstorms",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/chancetstorms.gif",
          "title":"Friday",
          "fcttext":"Partly cloudy with a chance of a thunderstorm. High of 75F. Winds less than 5 mph. Chance of rain 40%.",
          "fcttext_metric":"Partly cloudy with a chance of a thunderstorm. High of 24C. Winds less than 5 km/h. Chance of rain 40%.",
          "pop":"40"
          }
      ,
      {
        "period":19,
          "icon":"chancetstorms",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/chancetstorms.gif",
          "title":"Friday Night",
          "fcttext":"Partly cloudy with a chance of a thunderstorm. Fog overnight. Low of 57F. Winds less than 5 mph. Chance of rain 50% with rainfall amounts near 0.3 in. possible.",
          "fcttext_metric":"Partly cloudy with a chance of a thunderstorm. Fog overnight. Low of 14C. Winds less than 5 km/h. Chance of rain 50% with rainfall amounts near 6.6 mm possible.",
          "pop":"50"
          }
      ]
    },
    "simpleforecast": {
      "forecastday": [
        {
          "date":{
            "epoch":"1368673200",
            "pretty":"11:00 PM EDT on May 15, 2013",
            "day":15,
            "month":5,
            "year":2013,
            "yday":134,
            "hour":23,
            "min":"00",
            "sec":0,
            "isdst":"1",
            "monthname":"May",
            "weekday_short":"Wed",
            "weekday":"Wednesday",
            "ampm":"PM",
            "tz_short":"EDT",
            "tz_long":"America/New_York"
            },
          "period":1,
          "high": {
            "fahrenheit":"68",
            "celsius":"20"
            },
          "low": {
            "fahrenheit":"55",
            "celsius":"13"
            },
          "conditions":"Chance of Rain",
          "icon":"chancerain",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/chancerain.gif",
          "skyicon":"mostlycloudy",
          "pop":50,
          "qpf_allday": {
            "in": 0.10,
            "mm": 2.5
            },
          "qpf_day": {
            "in": 0.03,
            "mm": 0.8
            },
          "qpf_night": {
            "in": 0.07,
            "mm": 1.8
            },
          "snow_allday": {
            "in": 0,
            "cm": 0
            },
          "snow_day": {
            "in": 0,
            "cm": 0
            },
          "snow_night": {
            "in": 0,
            "cm": 0
            },
          "maxwind": {
            "mph": 19,
            "kph": 30,
            "dir": "South",
            "degrees": 180
            },
          "avewind": {
            "mph": 15,
            "kph": 24,
            "dir": "SSW",
            "degrees": 194
            },
          "avehumidity": 69,
          "maxhumidity": 77,
          "minhumidity": 31
          }
        ,
        { "date":{
            "epoch":"1368759600",
              "pretty":"11:00 PM EDT on May 16, 2013",
              "day":16,
              "month":5,
              "year":2013,
              "yday":135,
              "hour":23,
              "min":"00",
              "sec":0,
              "isdst":"1",
              "monthname":"May",
              "weekday_short":"Thu",
              "weekday":"Thursday",
              "ampm":"PM",
              "tz_short":"EDT",
              "tz_long":"America/New_York"
              },
          "period":2,
          "high": {
            "fahrenheit":"77",
            "celsius":"25"
            },
          "low": {
            "fahrenheit":"54",
            "celsius":"12"
            },
          "conditions":"Partly Cloudy",
          "icon":"partlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
          "skyicon":"mostlysunny",
          "pop":10,
          "qpf_allday": {
            "in": 0.00,
            "mm": 0.0
            },
          "qpf_day": {
            "in": 0.00,
            "mm": 0.0
            },
          "qpf_night": {
            "in": 0.00,
            "mm": 0.0
            },
          "snow_allday": {
            "in": 0,
            "cm": 0
            },
          "snow_day": {
            "in": 0,
            "cm": 0
            },
          "snow_night": {
            "in": 0,
            "cm": 0
            },
          "maxwind": {
            "mph": 23,
            "kph": 37,
            "dir": "West",
            "degrees": 270
            },
          "avewind": {
            "mph": 19,
            "kph": 30,
            "dir": "West",
            "degrees": 271
            },
          "avehumidity": 42,
          "maxhumidity": 80,
          "minhumidity": 31
          }
        ,
        { "date":{
            "epoch":"1368846000",
              "pretty":"11:00 PM EDT on May 17, 2013",
              "day":17,
              "month":5,
              "year":2013,
              "yday":136,
              "hour":23,
              "min":"00",
              "sec":0,
              "isdst":"1",
              "monthname":"May",
              "weekday_short":"Fri",
              "weekday":"Friday",
              "ampm":"PM",
              "tz_short":"EDT",
              "tz_long":"America/New_York"
              },
          "period":3,
          "high": {
            "fahrenheit":"72",
            "celsius":"22"
            },
          "low": {
            "fahrenheit":"54",
            "celsius":"12"
            },
          "conditions":"Clear",
          "icon":"clear",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/clear.gif",
          "skyicon":"mostlysunny",
          "pop":10,
          "qpf_allday": {
            "in": 0.00,
            "mm": 0.0
            },
          "qpf_day": {
            "in": 0.00,
            "mm": 0.0
            },
          "qpf_night": {
            "in": 0.00,
            "mm": 0.0
            },
          "snow_allday": {
            "in": 0,
            "cm": 0
            },
          "snow_day": {
            "in": 0,
            "cm": 0
            },
          "snow_night": {
            "in": 0,
            "cm": 0
            },
          "maxwind": {
            "mph": 11,
            "kph": 18,
            "dir": "NW",
            "degrees": 319
            },
          "avewind": {
            "mph": 5,
            "kph": 8,
            "dir": "NW",
            "degrees": 308
            },
          "avehumidity": 51,
          "maxhumidity": 71,
          "minhumidity": 31
          }
        ,
        { "date":{
            "epoch":"1368932400",
              "pretty":"11:00 PM EDT on May 18, 2013",
              "day":18,
              "month":5,
              "year":2013,
              "yday":137,
              "hour":23,
              "min":"00",
              "sec":0,
              "isdst":"1",
              "monthname":"May",
              "weekday_short":"Sat",
              "weekday":"Saturday",
              "ampm":"PM",
              "tz_short":"EDT",
              "tz_long":"America/New_York"
              },
          "period":4,
          "high": {
            "fahrenheit":"70",
            "celsius":"21"
            },
          "low": {
            "fahrenheit":"48",
            "celsius":"9"
          },
          "conditions":"Partly Cloudy",
          "icon":"partlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
          "skyicon":"partlycloudy",
          "pop":0,
          "qpf_allday": {
            "in": 0.00,
            "mm": 0.0
            },
          "qpf_day": {
            "in": 0.00,
            "mm": 0.0 
            },
          "qpf_night": {
           "in": 0.00,
           "mm": 0.0
           },
          "snow_allday": {
           "in": 0,
           "cm": 0
           },
          "snow_day": {
            "in": 0,
            "cm": 0
            },
          "snow_night": {
            "in": 0,
            "cm": 0
            },
          "maxwind": {
            "mph": 9,
            "kph": 14,
            "dir": "East",
            "degrees": 99
            },
          "avewind": {
            "mph": 7,
            "kph": 11,
            "dir": "SE",
            "degrees": 137
            },
          "avehumidity": 59,
            "maxhumidity": 64,
            "minhumidity": 38
          }
        ,
        { "date":{
            "epoch":"1369018800",
            "pretty":"11:00 PM EDT on May 19, 2013",
            "day":19,
            "month":5,
            "year":2013,
            "yday":138,
            "hour":23,
            "min":"00",
            "sec":0,
            "isdst":"1",
            "monthname":"May",
            "weekday_short":"Sun",
            "weekday":"Sunday",
            "ampm":"PM",
            "tz_short":"EDT",
            "tz_long":"America/New_York"
            },
          "period":5,
          "high": {
            "fahrenheit":"66",
            "celsius":"19"
            },
          "low": {
            "fahrenheit":"48",
            "celsius":"9"
            },
          "conditions":"Mostly Cloudy",
          "icon":"mostlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/mostlycloudy.gif",
          "skyicon":"mostlycloudy",
          "pop":0,
          "qpf_allday": {
            "in": 0.00,
            "mm": 0.0
            },
          "qpf_day": {
            "in": 0.00,
            "mm": 0.0
            },
          "qpf_night": {
            "in": 0.01,
            "mm": 0.3
            },
          "snow_allday": {
            "in": 0,
            "cm": 0
            },
          "snow_day": {
            "in": 0,
            "cm": 0
            },
          "snow_night": {
            "in": 0,
            "cm": 0
            },
          "maxwind": {
            "mph": 10,
            "kph": 16,
            "dir": "SSE",
            "degrees": 154
            },
          "avewind": {
            "mph": 8,
            "kph": 13,
            "dir": "SE",
            "degrees": 140
            },
          "avehumidity": 70,
          "maxhumidity": 79,
          "minhumidity": 57
          }
        ,
        { "date":{
            "epoch":"1369105200",
            "pretty":"11:00 PM EDT on May 20, 2013",
            "day":20,
            "month":5,
            "year":2013,
            "yday":139,
            "hour":23,
            "min":"00",
            "sec":0,
            "isdst":"1",
            "monthname":"May",
            "weekday_short":"Mon",
            "weekday":"Monday",
            "ampm":"PM",
            "tz_short":"EDT",
            "tz_long":"America/New_York"
            },
          "period":6,
          "high": {
            "fahrenheit":"68",
            "celsius":"20"
            },
          "low": {
            "fahrenheit":"52",
            "celsius":"11"
            },
          "conditions":"Overcast",
          "icon":"cloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/cloudy.gif",
          "skyicon":"cloudy",
          "pop":0,
          "qpf_allday": {
            "in": 0.04,
            "mm": 1.0
            },
          "qpf_day": {
            "in": 0.00,
            "mm": 0.0
            },
          "qpf_night": {
            "in": 0.03,
            "mm": 0.8
            },
          "snow_allday": {
            "in": 0,
            "cm": 0
            },
          "snow_day": {
            "in": 0,
            "cm": 0
            },
          "snow_night": {
            "in": 0,
            "cm": 0
            },
          "maxwind": {
            "mph": 13,
            "kph": 21,
            "dir": "South",
            "degrees": 183
            },
          "avewind": {
            "mph": 11,
            "kph": 18,
            "dir": "South",
            "degrees": 180
            },
          "avehumidity": 85,
          "maxhumidity": 100,
          "minhumidity": 67
          }
        ,
        { "date":{
            "epoch":"1369191600",
            "pretty":"11:00 PM EDT on May 21, 2013",
            "day":21,
            "month":5,
            "year":2013,
            "yday":140,
            "hour":23,
            "min":"00",
            "sec":0,
            "isdst":"1",
            "monthname":"May",
            "weekday_short":"Tue",
            "weekday":"Tuesday",
            "ampm":"PM",
            "tz_short":"EDT",
            "tz_long":"America/New_York"
            },
          "period":7,
          "high": {
            "fahrenheit":"73",
            "celsius":"23"
            },
          "low": {
            "fahrenheit":"54",
            "celsius":"12"
            },
          "conditions":"Fog",
          "icon":"mostlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/mostlycloudy.gif",
          "skyicon":"mostlycloudy",
          "pop":0,
          "qpf_allday": {
            "in": 0.02,
            "mm": 0.5
            },
          "qpf_day": {
            "in": 0.01,
            "mm": 0.3
            },
          "qpf_night": {
            "in": 0.02,
            "mm": 0.5
            },
          "snow_allday": {
            "in": 0,
            "cm": 0
            },
          "snow_day": {
            "in": 0,
            "cm": 0
            },
          "snow_night": {
            "in": 0,
            "cm": 0
            },
          "maxwind": {
            "mph": 10,
            "kph": 16,
            "dir": "ENE",
            "degrees": 68
            },
          "avewind": {
            "mph": 8,
            "kph": 13,
            "dir": "East",
            "degrees": 82
            },
          "avehumidity": 72,
          "maxhumidity": 100,
          "minhumidity": 64
          }
        ,
        { "date":{
            "epoch":"1369278000",
            "pretty":"11:00 PM EDT on May 22, 2013",
            "day":22,
            "month":5,
            "year":2013,
            "yday":141,
            "hour":23,
            "min":"00",
            "sec":0,
            "isdst":"1",
            "monthname":"May",
            "weekday_short":"Wed",
            "weekday":"Wednesday",
            "ampm":"PM",
            "tz_short":"EDT",
            "tz_long":"America/New_York"
            },
          "period":8,
          "high": {
            "fahrenheit":"77",
            "celsius":"25"
            },
          "low": {
            "fahrenheit":"55",
            "celsius":"13"
            },
          "conditions":"Partly Cloudy",
          "icon":"partlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
          "skyicon":"partlycloudy",
          "pop":0,
          "qpf_allday": {
            "in": 0.02,
            "mm": 0.5
            },
          "qpf_day": {
            "in": 0.00,
            "mm": 0.0
            },
          "qpf_night": {
            "in": 0.01,
            "mm": 0.3
            },
          "snow_allday": {
            "in": 0,
            "cm": 0
            },
          "snow_day": {
            "in": 0,
            "cm": 0
            },
          "snow_night": {
            "in": 0,
            "cm": 0
            },
          "maxwind": {
            "mph": 8,
            "kph": 13,
            "dir": "SE",
            "degrees": 127
          },
          "avewind": {
            "mph": 6,
            "kph": 10,
            "dir": "ESE",
            "degrees": 108
            },
          "avehumidity": 76,
          "maxhumidity": 88,
          "minhumidity": 58
          }
        ,
        { "date":{
            "epoch":"1369364400",
            "pretty":"11:00 PM EDT on May 23, 2013",
            "day":23,
            "month":5,
            "year":2013,
            "yday":142,
            "hour":23,
            "min":"00",
            "sec":0,
            "isdst":"1",
            "monthname":"May",
            "weekday_short":"Thu",
            "weekday":"Thursday",
            "ampm":"PM",
            "tz_short":"EDT",
            "tz_long":"America/New_York"
            },
          "period":9,
          "high": {
            "fahrenheit":"75",
            "celsius":"24"
            },
          "low": {
            "fahrenheit":"54",
            "celsius":"12"
            },
          "conditions":"Partly Cloudy",
          "icon":"partlycloudy",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
          "skyicon":"partlycloudy",
          "pop":0,
          "qpf_allday": {
            "in": 0.02,
            "mm": 0.5
            },
          "qpf_day": {
            "in": 0.00,
            "mm": 0.0
          },
          "qpf_night": {
            "in": 0.04,
            "mm": 1.0
          },
          "snow_allday": {
            "in": 0,
            "cm": 0
          },
          "snow_day": {
            "in": 0,
            "cm": 0
            },
          "snow_night": {
            "in": 0,
            "cm": 0
            },
          "maxwind": {
            "mph": 4,
            "kph": 6,
            "dir": "SE",
            "degrees": 141
            },
          "avewind": {
            "mph": 3,
            "kph": 5,
            "dir": "SE",
            "degrees": 139
            },
          "avehumidity": 92,
          "maxhumidity": 100,
          "minhumidity": 66
          }
        ,
        { "date":{
            "epoch":"1369450800",
            "pretty":"11:00 PM EDT on May 24, 2013",
            "day":24,
            "month":5,
            "year":2013,
            "yday":143,
            "hour":23,
            "min":"00",
            "sec":0,
            "isdst":"1",
            "monthname":"May",
            "weekday_short":"Fri",
            "weekday":"Friday",
            "ampm":"PM",
            "tz_short":"EDT",
            "tz_long":"America/New_York"
            },
          "period":10,
          "high": {
            "fahrenheit":"75",
            "celsius":"24"
            },
          "low": {
            "fahrenheit":"57",
            "celsius":"14"
            },
          "conditions":"Chance of a Thunderstorm",
          "icon":"chancetstorms",
          "icon_url":"http://icons-ak.wxug.com/i/c/k/chancetstorms.gif",
          "skyicon":"partlycloudy",
          "pop":40,
          "qpf_allday": {
            "in": 0.18,
            "mm": 4.6
             },
          "qpf_day": {
            "in": 0.02,
            "mm": 0.5
            },
          "qpf_night": {
            "in": 0.26,
            "mm": 6.6
            },
          "snow_allday": {
            "in": 0,
            "cm": 0
            },
          "snow_day": {
            "in": 0,
            "cm": 0
            },
          "snow_night": {
            "in": 0,
            "cm": 0
            },
          "maxwind": {
            "mph": 5,
            "kph": 8,
            "dir": "SE",
            "degrees": 138
            },
          "avewind": {
            "mph": 3,
            "kph": 5,
            "dir": "SE",
            "degrees": 128
            },
          "avehumidity": 90,
          "maxhumidity": 100,
          "minhumidity": 69
          }
        ]
      }
    }
}
'''

WU_TENANTS_HARBOR = '''
{
	"response": {
		"version": "0.1"
		,"termsofService": "http://www.wunderground.com/weather/api/d/terms.html"
		,"features": {
		"forecast10day": 1
		}
	}
		,
	"forecast":{
		"txt_forecast": {
		"date":"5:00 AM EDT",
		"forecastday": [
		{
		"period":0,
		"icon":"tstorms",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/tstorms.gif",
		"title":"Sunday",
		"fcttext":"Mostly cloudy with thunderstorms and rain showers. High of 86F. Winds from the SW at 10 to 15 mph. Chance of rain 40%.",
		"fcttext_metric":"Mostly cloudy with thunderstorms and rain showers. High of 30C. Breezy. Winds from the SW at 15 to 20 km/h. Chance of rain 40%.",
		"pop":"40"
		}
		,
		{
		"period":1,
		"icon":"tstorms",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/tstorms.gif",
		"title":"Sunday Night",
		"fcttext":"Overcast with thunderstorms and rain showers. Low of 73F. Winds from the South at 5 to 10 mph. Chance of rain 60%.",
		"fcttext_metric":"Overcast with thunderstorms and rain showers. Low of 23C. Winds from the South at 10 to 15 km/h. Chance of rain 60%.",
		"pop":"60"
		}
		,
		{
		"period":2,
		"icon":"tstorms",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/tstorms.gif",
		"title":"Monday",
		"fcttext":"Overcast with thunderstorms and rain showers. Fog early. High of 81F. Winds from the South at 5 to 10 mph. Chance of rain 60% with rainfall amounts near 0.3 in. possible.",
		"fcttext_metric":"Overcast with thunderstorms and rain showers. Fog early. High of 27C. Breezy. Winds from the South at 10 to 20 km/h. Chance of rain 60% with rainfall amounts near 8.9 mm possible.",
		"pop":"60"
		}
		,
		{
		"period":3,
		"icon":"chancetstorms",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/chancetstorms.gif",
		"title":"Monday Night",
		"fcttext":"Mostly cloudy with a chance of a thunderstorm and rain showers, then a chance of a thunderstorm and a chance of rain after midnight. Low of 72F. Winds from the SSW at 5 to 10 mph. Chance of rain 70% with rainfall amounts near 0.3 in. possible.",
		"fcttext_metric":"Mostly cloudy with a chance of a thunderstorm and rain showers, then a chance of a thunderstorm and a chance of rain after midnight. Low of 22C. Winds from the SSW at 10 to 15 km/h. Chance of rain 70% with rainfall amounts near 8.9 mm possible.",
		"pop":"70"
		}
		,
		{
		"period":4,
		"icon":"chancetstorms",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/chancetstorms.gif",
		"title":"Tuesday",
		"fcttext":"Mostly cloudy with a chance of a thunderstorm and a chance of rain. High of 81F. Winds from the SW at 5 to 10 mph. Chance of rain 50%.",
		"fcttext_metric":"Mostly cloudy with a chance of a thunderstorm and a chance of rain. High of 27C. Winds from the SW at 10 to 15 km/h. Chance of rain 50%.",
		"pop":"50"
		}
		,
		{
		"period":5,
		"icon":"partlycloudy",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
		"title":"Tuesday Night",
		"fcttext":"Partly cloudy with a chance of a thunderstorm and a chance of rain in the evening, then clear. Low of 61F. Winds from the West at 5 to 10 mph.",
		"fcttext_metric":"Partly cloudy with a chance of a thunderstorm and a chance of rain in the evening, then clear. Low of 16C. Winds from the West at 10 to 15 km/h.",
		"pop":"10"
		}
		,
		{
		"period":6,
		"icon":"clear",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/clear.gif",
		"title":"Wednesday",
		"fcttext":"Partly cloudy in the morning, then clear. High of 79F. Winds from the NW at 10 to 15 mph.",
		"fcttext_metric":"Partly cloudy in the morning, then clear. High of 26C. Breezy. Winds from the NW at 15 to 20 km/h.",
		"pop":"0"
		}
		,
		{
		"period":7,
		"icon":"clear",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/clear.gif",
		"title":"Wednesday Night",
		"fcttext":"Clear in the evening, then partly cloudy. Low of 59F. Winds from the West at 5 to 10 mph.",
		"fcttext_metric":"Clear in the evening, then partly cloudy. Low of 15C. Winds from the West at 10 to 15 km/h.",
		"pop":"0"
		}
		,
		{
		"period":8,
		"icon":"mostlycloudy",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/mostlycloudy.gif",
		"title":"Thursday",
		"fcttext":"Partly cloudy in the morning, then overcast. High of 75F. Winds from the West at 5 to 10 mph.",
		"fcttext_metric":"Partly cloudy in the morning, then overcast. High of 24C. Breezy. Winds from the West at 10 to 20 km/h.",
		"pop":"0"
		}
		,
		{
		"period":9,
		"icon":"clear",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/clear.gif",
		"title":"Thursday Night",
		"fcttext":"Clear with a chance of rain. Fog overnight. Low of 57F. Winds from the North at 5 to 10 mph. Chance of rain 20%.",
		"fcttext_metric":"Clear with a chance of rain. Fog overnight. Low of 14C. Winds from the North at 10 to 15 km/h.",
		"pop":"20"
		}
		,
		{
		"period":10,
		"icon":"clear",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/clear.gif",
		"title":"Friday",
		"fcttext":"Clear. High of 72F. Winds less than 5 mph.",
		"fcttext_metric":"Clear. High of 22C. Winds less than 5 km/h.",
		"pop":"0"
		}
		,
		{
		"period":11,
		"icon":"clear",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/clear.gif",
		"title":"Friday Night",
		"fcttext":"Clear. Low of 54F. Winds from the SSW at 5 to 15 mph.",
		"fcttext_metric":"Clear. Low of 12C. Breezy. Winds from the SSW at 10 to 20 km/h.",
		"pop":"0"
		}
		,
		{
		"period":12,
		"icon":"partlycloudy",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
		"title":"Saturday",
		"fcttext":"Partly cloudy. High of 79F. Winds from the SW at 10 to 15 mph.",
		"fcttext_metric":"Partly cloudy. High of 26C. Breezy. Winds from the SW at 20 to 25 km/h.",
		"pop":"0"
		}
		,
		{
		"period":13,
		"icon":"partlycloudy",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
		"title":"Saturday Night",
		"fcttext":"Clear with a chance of a thunderstorm. Fog overnight. Low of 63F. Winds from the SW at 5 to 15 mph shifting to the WNW after midnight. Chance of rain 20%.",
		"fcttext_metric":"Clear with a chance of a thunderstorm. Fog overnight. Low of 17C. Breezy. Winds from the SW at 10 to 20 km/h shifting to the WNW after midnight.",
		"pop":"20"
		}
		,
		{
		"period":14,
		"icon":"partlycloudy",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
		"title":"Sunday",
		"fcttext":"Clear. High of 77F. Winds from the NE at 5 to 10 mph.",
		"fcttext_metric":"Clear. High of 25C. Winds from the NE at 10 to 15 km/h.",
		"pop":"0"
		}
		,
		{
		"period":15,
		"icon":"clear",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/clear.gif",
		"title":"Sunday Night",
		"fcttext":"Clear. Low of 61F. Winds less than 5 mph.",
		"fcttext_metric":"Clear. Low of 16C. Winds less than 5 km/h.",
		"pop":"0"
		}
		,
		{
		"period":16,
		"icon":"partlycloudy",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
		"title":"Monday",
		"fcttext":"Partly cloudy. High of 77F. Winds less than 5 mph.",
		"fcttext_metric":"Partly cloudy. High of 25C. Winds less than 5 km/h.",
		"pop":"0"
		}
		,
		{
		"period":17,
		"icon":"partlycloudy",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
		"title":"Monday Night",
		"fcttext":"Partly cloudy. Low of 61F. Winds less than 5 mph.",
		"fcttext_metric":"Partly cloudy. Low of 16C. Winds less than 5 km/h.",
		"pop":"0"
		}
		,
		{
		"period":18,
		"icon":"partlycloudy",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
		"title":"Tuesday",
		"fcttext":"Partly cloudy. High of 79F. Winds less than 5 mph.",
		"fcttext_metric":"Partly cloudy. High of 26C. Winds less than 5 km/h.",
		"pop":"0"
		}
		,
		{
		"period":19,
		"icon":"partlycloudy",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
		"title":"Tuesday Night",
		"fcttext":"Partly cloudy. Fog overnight. Low of 61F. Winds less than 5 mph.",
		"fcttext_metric":"Partly cloudy. Fog overnight. Low of 16C. Winds less than 5 km/h.",
		"pop":"0"
		}
		]
		},
		"simpleforecast": {
		"forecastday": [
		{"date":{
	"epoch":"1378090800",
	"pretty":"11:00 PM EDT on September 01, 2013",
	"day":1,
	"month":9,
	"year":2013,
	"yday":243,
	"hour":23,
	"min":"00",
	"sec":0,
	"isdst":"1",
	"monthname":"September",
	"weekday_short":"Sun",
	"weekday":"Sunday",
	"ampm":"PM",
	"tz_short":"EDT",
	"tz_long":"America/New_York"
},
		"period":1,
		"high": {
		"fahrenheit":"86",
		"celsius":"30"
		},
		"low": {
		"fahrenheit":"73",
		"celsius":"23"
		},
		"conditions":"Thunderstorm",
		"icon":"tstorms",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/tstorms.gif",
		"skyicon":"mostlycloudy",
		"pop":40,
		"qpf_allday": {
		"in": 0.38,
		"mm": 9.7
		},
		"qpf_day": {
		"in": 0.15,
		"mm": 3.8
		},
		"qpf_night": {
		"in": 0.17,
		"mm": 4.3
		},
		"snow_allday": {
		"in": 0,
		"cm": 0
		},
		"snow_day": {
		"in": 0,
		"cm": 0
		},
		"snow_night": {
		"in": 0,
		"cm": 0
		},
		"maxwind": {
		"mph": 11,
		"kph": 18,
		"dir": "SSW",
		"degrees": 209
		},
		"avewind": {
		"mph": 10,
		"kph": 16,
		"dir": "SSW",
		"degrees": 211
		},
		"avehumidity": 83,
		"maxhumidity": 93,
		"minhumidity": 62
		}
		,
		{"date":{
	"epoch":"1378177200",
	"pretty":"11:00 PM EDT on September 02, 2013",
	"day":2,
	"month":9,
	"year":2013,
	"yday":244,
	"hour":23,
	"min":"00",
	"sec":0,
	"isdst":"1",
	"monthname":"September",
	"weekday_short":"Mon",
	"weekday":"Monday",
	"ampm":"PM",
	"tz_short":"EDT",
	"tz_long":"America/New_York"
},
		"period":2,
		"high": {
		"fahrenheit":"81",
		"celsius":"27"
		},
		"low": {
		"fahrenheit":"72",
		"celsius":"22"
		},
		"conditions":"Thunderstorm",
		"icon":"tstorms",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/tstorms.gif",
		"skyicon":"mostlycloudy",
		"pop":60,
		"qpf_allday": {
		"in": 0.72,
		"mm": 18.3
		},
		"qpf_day": {
		"in": 0.35,
		"mm": 8.9
		},
		"qpf_night": {
		"in": 0.35,
		"mm": 8.9
		},
		"snow_allday": {
		"in": 0,
		"cm": 0
		},
		"snow_day": {
		"in": 0,
		"cm": 0
		},
		"snow_night": {
		"in": 0,
		"cm": 0
		},
		"maxwind": {
		"mph": 10,
		"kph": 16,
		"dir": "SSW",
		"degrees": 199
		},
		"avewind": {
		"mph": 8,
		"kph": 13,
		"dir": "South",
		"degrees": 184
		},
		"avehumidity": 91,
		"maxhumidity": 100,
		"minhumidity": 76
		}
		,
		{"date":{
	"epoch":"1378263600",
	"pretty":"11:00 PM EDT on September 03, 2013",
	"day":3,
	"month":9,
	"year":2013,
	"yday":245,
	"hour":23,
	"min":"00",
	"sec":0,
	"isdst":"1",
	"monthname":"September",
	"weekday_short":"Tue",
	"weekday":"Tuesday",
	"ampm":"PM",
	"tz_short":"EDT",
	"tz_long":"America/New_York"
},
		"period":3,
		"high": {
		"fahrenheit":"81",
		"celsius":"27"
		},
		"low": {
		"fahrenheit":"61",
		"celsius":"16"
		},
		"conditions":"Chance of a Thunderstorm",
		"icon":"chancetstorms",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/chancetstorms.gif",
		"skyicon":"mostlycloudy",
		"pop":50,
		"qpf_allday": {
		"in": 0.21,
		"mm": 5.3
		},
		"qpf_day": {
		"in": 0.10,
		"mm": 2.5
		},
		"qpf_night": {
		"in": 0.05,
		"mm": 1.3
		},
		"snow_allday": {
		"in": 0,
		"cm": 0
		},
		"snow_day": {
		"in": 0,
		"cm": 0
		},
		"snow_night": {
		"in": 0,
		"cm": 0
		},
		"maxwind": {
		"mph": 9,
		"kph": 14,
		"dir": "SW",
		"degrees": 220
		},
		"avewind": {
		"mph": 8,
		"kph": 13,
		"dir": "SW",
		"degrees": 216
		},
		"avehumidity": 70,
		"maxhumidity": 86,
		"minhumidity": 65
		}
		,
		{"date":{
	"epoch":"1378350000",
	"pretty":"11:00 PM EDT on September 04, 2013",
	"day":4,
	"month":9,
	"year":2013,
	"yday":246,
	"hour":23,
	"min":"00",
	"sec":0,
	"isdst":"1",
	"monthname":"September",
	"weekday_short":"Wed",
	"weekday":"Wednesday",
	"ampm":"PM",
	"tz_short":"EDT",
	"tz_long":"America/New_York"
},
		"period":4,
		"high": {
		"fahrenheit":"79",
		"celsius":"26"
		},
		"low": {
		"fahrenheit":"59",
		"celsius":"15"
		},
		"conditions":"Clear",
		"icon":"clear",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/clear.gif",
		"skyicon":"sunny",
		"pop":0,
		"qpf_allday": {
		"in": 0.00,
		"mm": 0.0
		},
		"qpf_day": {
		"in": 0.00,
		"mm": 0.0
		},
		"qpf_night": {
		"in": 0.00,
		"mm": 0.0
		},
		"snow_allday": {
		"in": 0,
		"cm": 0
		},
		"snow_day": {
		"in": 0,
		"cm": 0
		},
		"snow_night": {
		"in": 0,
		"cm": 0
		},
		"maxwind": {
		"mph": 11,
		"kph": 18,
		"dir": "NW",
		"degrees": 309
		},
		"avewind": {
		"mph": 10,
		"kph": 16,
		"dir": "NW",
		"degrees": 305
		},
		"avehumidity": 78,
		"maxhumidity": 84,
		"minhumidity": 50
		}
		,
		{"date":{
	"epoch":"1378436400",
	"pretty":"11:00 PM EDT on September 05, 2013",
	"day":5,
	"month":9,
	"year":2013,
	"yday":247,
	"hour":23,
	"min":"00",
	"sec":0,
	"isdst":"1",
	"monthname":"September",
	"weekday_short":"Thu",
	"weekday":"Thursday",
	"ampm":"PM",
	"tz_short":"EDT",
	"tz_long":"America/New_York"
},
		"period":5,
		"high": {
		"fahrenheit":"75",
		"celsius":"24"
		},
		"low": {
		"fahrenheit":"57",
		"celsius":"14"
		},
		"conditions":"Mostly Cloudy",
		"icon":"mostlycloudy",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/mostlycloudy.gif",
		"skyicon":"mostlycloudy",
		"pop":0,
		"qpf_allday": {
		"in": 0.02,
		"mm": 0.5
		},
		"qpf_day": {
		"in": 0.00,
		"mm": 0.0
		},
		"qpf_night": {
		"in": 0.02,
		"mm": 0.5
		},
		"snow_allday": {
		"in": 0,
		"cm": 0
		},
		"snow_day": {
		"in": 0,
		"cm": 0
		},
		"snow_night": {
		"in": 0,
		"cm": 0
		},
		"maxwind": {
		"mph": 10,
		"kph": 16,
		"dir": "West",
		"degrees": 272
		},
		"avewind": {
		"mph": 8,
		"kph": 13,
		"dir": "West",
		"degrees": 278
		},
		"avehumidity": 90,
		"maxhumidity": 100,
		"minhumidity": 56
		}
		,
		{"date":{
	"epoch":"1378522800",
	"pretty":"11:00 PM EDT on September 06, 2013",
	"day":6,
	"month":9,
	"year":2013,
	"yday":248,
	"hour":23,
	"min":"00",
	"sec":0,
	"isdst":"1",
	"monthname":"September",
	"weekday_short":"Fri",
	"weekday":"Friday",
	"ampm":"PM",
	"tz_short":"EDT",
	"tz_long":"America/New_York"
},
		"period":6,
		"high": {
		"fahrenheit":"72",
		"celsius":"22"
		},
		"low": {
		"fahrenheit":"54",
		"celsius":"12"
		},
		"conditions":"Clear",
		"icon":"clear",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/clear.gif",
		"skyicon":"sunny",
		"pop":0,
		"qpf_allday": {
		"in": 0.00,
		"mm": 0.0
		},
		"qpf_day": {
		"in": 0.00,
		"mm": 0.0
		},
		"qpf_night": {
		"in": 0.00,
		"mm": 0.0
		},
		"snow_allday": {
		"in": 0,
		"cm": 0
		},
		"snow_day": {
		"in": 0,
		"cm": 0
		},
		"snow_night": {
		"in": 0,
		"cm": 0
		},
		"maxwind": {
		"mph": 6,
		"kph": 10,
		"dir": "NNE",
		"degrees": 15
		},
		"avewind": {
		"mph": 4,
		"kph": 6,
		"dir": "ESE",
		"degrees": 104
		},
		"avehumidity": 74,
		"maxhumidity": 87,
		"minhumidity": 49
		}
		,
		{"date":{
	"epoch":"1378609200",
	"pretty":"11:00 PM EDT on September 07, 2013",
	"day":7,
	"month":9,
	"year":2013,
	"yday":249,
	"hour":23,
	"min":"00",
	"sec":0,
	"isdst":"1",
	"monthname":"September",
	"weekday_short":"Sat",
	"weekday":"Saturday",
	"ampm":"PM",
	"tz_short":"EDT",
	"tz_long":"America/New_York"
},
		"period":7,
		"high": {
		"fahrenheit":"79",
		"celsius":"26"
		},
		"low": {
		"fahrenheit":"63",
		"celsius":"17"
		},
		"conditions":"Partly Cloudy",
		"icon":"partlycloudy",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
		"skyicon":"partlycloudy",
		"pop":0,
		"qpf_allday": {
		"in": 0.01,
		"mm": 0.3
		},
		"qpf_day": {
		"in": 0.00,
		"mm": 0.0
		},
		"qpf_night": {
		"in": 0.01,
		"mm": 0.3
		},
		"snow_allday": {
		"in": 0,
		"cm": 0
		},
		"snow_day": {
		"in": 0,
		"cm": 0
		},
		"snow_night": {
		"in": 0,
		"cm": 0
		},
		"maxwind": {
		"mph": 14,
		"kph": 22,
		"dir": "WSW",
		"degrees": 239
		},
		"avewind": {
		"mph": 11,
		"kph": 18,
		"dir": "SW",
		"degrees": 233
		},
		"avehumidity": 93,
		"maxhumidity": 100,
		"minhumidity": 60
		}
		,
		{"date":{
	"epoch":"1378695600",
	"pretty":"11:00 PM EDT on September 08, 2013",
	"day":8,
	"month":9,
	"year":2013,
	"yday":250,
	"hour":23,
	"min":"00",
	"sec":0,
	"isdst":"1",
	"monthname":"September",
	"weekday_short":"Sun",
	"weekday":"Sunday",
	"ampm":"PM",
	"tz_short":"EDT",
	"tz_long":"America/New_York"
},
		"period":8,
		"high": {
		"fahrenheit":"77",
		"celsius":"25"
		},
		"low": {
		"fahrenheit":"61",
		"celsius":"16"
		},
		"conditions":"Partly Cloudy",
		"icon":"partlycloudy",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
		"skyicon":"mostlysunny",
		"pop":0,
		"qpf_allday": {
		"in": 0.00,
		"mm": 0.0
		},
		"qpf_day": {
		"in": 0.00,
		"mm": 0.0
		},
		"qpf_night": {
		"in": 0.00,
		"mm": 0.0
		},
		"snow_allday": {
		"in": 0,
		"cm": 0
		},
		"snow_day": {
		"in": 0,
		"cm": 0
		},
		"snow_night": {
		"in": 0,
		"cm": 0
		},
		"maxwind": {
		"mph": 9,
		"kph": 14,
		"dir": "NE",
		"degrees": 49
		},
		"avewind": {
		"mph": 7,
		"kph": 11,
		"dir": "East",
		"degrees": 80
		},
		"avehumidity": 65,
		"maxhumidity": 93,
		"minhumidity": 52
		}
		,
		{"date":{
	"epoch":"1378782000",
	"pretty":"11:00 PM EDT on September 09, 2013",
	"day":9,
	"month":9,
	"year":2013,
	"yday":251,
	"hour":23,
	"min":"00",
	"sec":0,
	"isdst":"1",
	"monthname":"September",
	"weekday_short":"Mon",
	"weekday":"Monday",
	"ampm":"PM",
	"tz_short":"EDT",
	"tz_long":"America/New_York"
},
		"period":9,
		"high": {
		"fahrenheit":"77",
		"celsius":"25"
		},
		"low": {
		"fahrenheit":"61",
		"celsius":"16"
		},
		"conditions":"Partly Cloudy",
		"icon":"partlycloudy",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
		"skyicon":"partlycloudy",
		"pop":0,
		"qpf_allday": {
		"in": 0.00,
		"mm": 0.0
		},
		"qpf_day": {
		"in": 0.00,
		"mm": 0.0
		},
		"qpf_night": {
		"in": 0.00,
		"mm": 0.0
		},
		"snow_allday": {
		"in": 0,
		"cm": 0
		},
		"snow_day": {
		"in": 0,
		"cm": 0
		},
		"snow_night": {
		"in": 0,
		"cm": 0
		},
		"maxwind": {
		"mph": 4,
		"kph": 6,
		"dir": "SW",
		"degrees": 223
		},
		"avewind": {
		"mph": 3,
		"kph": 5,
		"dir": "SW",
		"degrees": 230
		},
		"avehumidity": 75,
		"maxhumidity": 82,
		"minhumidity": 51
		}
		,
		{"date":{
	"epoch":"1378868400",
	"pretty":"11:00 PM EDT on September 10, 2013",
	"day":10,
	"month":9,
	"year":2013,
	"yday":252,
	"hour":23,
	"min":"00",
	"sec":0,
	"isdst":"1",
	"monthname":"September",
	"weekday_short":"Tue",
	"weekday":"Tuesday",
	"ampm":"PM",
	"tz_short":"EDT",
	"tz_long":"America/New_York"
},
		"period":10,
		"high": {
		"fahrenheit":"79",
		"celsius":"26"
		},
		"low": {
		"fahrenheit":"61",
		"celsius":"16"
		},
		"conditions":"Partly Cloudy",
		"icon":"partlycloudy",
		"icon_url":"http://icons-ak.wxug.com/i/c/k/partlycloudy.gif",
		"skyicon":"partlycloudy",
		"pop":0,
		"qpf_allday": {
		"in": 0.00,
		"mm": 0.0
		},
		"qpf_day": {
		"in": 0.00,
		"mm": 0.0
		},
		"qpf_night": {
		"in": 0.00,
		"mm": 0.0
		},
		"snow_allday": {
		"in": 0,
		"cm": 0
		},
		"snow_day": {
		"in": 0,
		"cm": 0
		},
		"snow_night": {
		"in": 0,
		"cm": 0
		},
		"maxwind": {
		"mph": 3,
		"kph": 5,
		"dir": "South",
		"degrees": 188
		},
		"avewind": {
		"mph": 2,
		"kph": 3,
		"dir": "SSW",
		"degrees": 196
		},
		"avehumidity": 86,
		"maxhumidity": 95,
		"minhumidity": 61
		}
		]
		}
	}
}
'''

# generic templates for combinations of summary and period
# should work with each forecast source
PERIODS_TEMPLATE = '''<html>
  <body>
#for $f in $forecast.weather_periods('SOURCE', from_ts=TS, max_events=20)
$f.event_ts $f.duration $f.tempMin $f.temp $f.tempMax $f.humidity $f.dewpoint $f.windSpeed $f.windGust $f.windDir $f.windChar $f.pop
#end for
  </body>
</html>
'''

SUMMARY_TEMPLATE = '''<html>
  <body>
#set $summary = $forecast.weather_summary('SOURCE', ts=TS)
forecast for $summary.location for the day $summary.event_ts as of $summary.issued_ts
$summary.clouds
$summary.tempMin
$summary.tempMax
$summary.temp
$summary.dewpointMin
$summary.dewpointMax
$summary.dewpoint
$summary.humidityMin
$summary.humidityMax
$summary.humidity
$summary.windSpeedMin
$summary.windSpeedMax
$summary.windSpeed
$summary.windGust
$summary.windDir
#for $d in $summary.windDirs
  $d
#end for
$summary.windChar
#for $c in $summary.windChars
  $c
#end for
$summary.pop
#for $p in $summary.precip
  $p
#end for
#for $o in $summary.obvis
  $o
#end for
  </body>
</html>
'''

TABLE_TEMPLATE = '''<html>
<body>

#set $lastday = None

#for $period in $forecast.weather_periods('SOURCE', from_ts=TS)
  #set $thisday = $period.event_ts.format('%d')
  #set $thisdate = $period.event_ts.format('%Y.%m.%d')
  #set $hourid = $thisdate + '.hours'
  #if $lastday != $thisday
    #if $lastday is not None
    END_TABLE
  END_DIV
    #end if
    #set $lastday = $thisday
    #set $summary = $forecast.weather_summary('SOURCE', $period.event_ts.raw)

  BEG_DIV id='$thisdate'
    BEG_TABLE
      $thisdate
      $summary.event_ts.format('%a') $summary.event_ts.format('%d %b %Y')
    #if $summary.clouds is not None
      #set $simg = 'forecast-icons/' + $summary.clouds + '.png'
      $simg
    #end if
      $summary.tempMax.raw $summary.tempMin.raw
      $summary.dewpointMax.raw<br/>$summary.dewpointMin.raw
      $summary.humidityMax.raw<br/>$summary.humidityMin.raw
      $summary.windSpeedMin.raw - $summary.windSpeedMax.raw $summary.windGust.raw $summary.windDir $summary.windChar
      $summary.pop
      $summary.precip
      $summary.obvis
    END_TABLE
  END_DIV

  BEG_DIV id='$hourid'
    BEG_TABLE
  #end if
  #set $hour = $period.event_ts.format('%H:%M')
      BEG_ROW
      $hour
    #if $period.clouds is not None
      #set $img = 'forecast-icons/' + $period.clouds + '.png'
      $img
    #end if
      $period.temp.raw
      $period.dewpoint.raw
      $period.humidity.raw
      $period.windSpeed.raw $period.windGust.raw $period.windDir $period.windChar
      $period.pop
  #for $k,$v in $period.precip.items()
      $forecast.label('NWS',$k): $forecast.label('NWS',$v) ($k,$v)
  #end for
      $period.obvis
      END_ROW
#end for
    END_TABLE
  END_DIV
'''


class ForecastTest(unittest.TestCase):

    def compareContents(self, filename, expected):
        expected_lines = string.split(expected, '\n')

        actual = open(filename)
        actual_lines = []
        for actual_line in actual:
            actual_lines.append(actual_line)
        actual.close()
        if len(actual_lines) != len(expected_lines):
            raise AssertionError('wrong number of lines in %s: %d != %d' %
                                 (filename, len(actual_lines), len(expected_lines)))

        lineno = 0
        diffs = []
        for actual_line in actual_lines:
            try:
                self.assertEqual(string.rstrip(actual_line), expected_lines[lineno])
            except AssertionError, e:
                diffs.append('line %d: %s' % (lineno+1, e))
            lineno += 1
        if len(diffs) > 0:
            raise AssertionError('differences found in %s:\n%s' % (filename, '\n'.join(diffs)))

    def setupTemplateTest(self, tname, module, data, tmpl):
        tdir = get_testdir(tname)
        rmtree(tdir)
        cd = create_config(tdir, module)
        FakeData.create_weather_databases(cd['Databases']['archive_sqlite'],
                                          cd['Databases']['stats_sqlite'])
        FakeData.create_forecast_database(cd['Databases']['forecast_sqlite'],
                                          data)
        create_skin_conf(tdir)

        ts = int(time.mktime((2013,8,22,12,0,0,0,0,-1)))
        stn_info = weewx.station.StationInfo(**cd['Station'])
        t = weewx.reportengine.StdReportEngine(cd, stn_info, ts)
        fn = tdir + '/testskin/index.html.tmpl'
        f = open(fn, 'w')
        f.write(tmpl)
        f.close()
        return t, tdir
          
    def runTemplateTest(self, tname, module, data, tmpl, expected):
        t, tdir = self.setupTemplateTest(tname, module, data, tmpl)
        t.run()
        self.compareContents(tdir + '/html/index.html', expected)


    # -------------------------------------------------------------------------
    # zambretti tests
    # -------------------------------------------------------------------------

    def test_zambretti_code(self):
        """run through all of the permutations"""

        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 0, 1), 'B')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 0, 0), 'B')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 0, -1), 'H')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 0, 1), 'B')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 0, 0), 'B')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 0, -1), 'H')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 1, 1), 'B')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 1, 0), 'B')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 1, -1), 'H')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 1, 1), 'B')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 1, 0), 'B')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 1, -1), 'H')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 2, 1), 'C')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 2, 0), 'B')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 2, -1), 'H')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 2, 1), 'B')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 2, 0), 'B')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 2, -1), 'O')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 3, 1), 'C')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 3, 0), 'E')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 3, -1), 'H')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 3, 1), 'B')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 3, 0), 'E')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 3, -1), 'O')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 4, 1), 'C')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 4, 0), 'E')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 4, -1), 'O')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 4, 1), 'C')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 4, 0), 'E')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 4, -1), 'O')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 5, 1), 'F')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 5, 0), 'K')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 5, -1), 'O')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 5, 1), 'C')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 5, 0), 'K')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 5, -1), 'R')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 6, 1), 'F')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 6, 0), 'K')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 6, -1), 'O')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 6, 1), 'F')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 6, 0), 'K')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 6, -1), 'R')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 7, 1), 'G')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 7, 0), 'N')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 7, -1), 'R')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 7, 1), 'F')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 7, 0), 'N')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 7, -1), 'R')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 8, 1), 'G')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 8, 0), 'N')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 8, -1), 'R')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 8, 1), 'G')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 8, 0), 'N')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 8, -1), 'U')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 9, 1), 'G')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 9, 0), 'N')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 9, -1), 'R')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 9, 1), 'F')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 9, 0), 'N')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 9, -1), 'U')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 10, 1), 'F')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 10, 0), 'N')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 10, -1), 'R')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 10, 1), 'F')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 10, 0), 'N')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 10, -1), 'R')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 11, 1), 'F')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 11, 0), 'K')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 11, -1), 'O')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 11, 1), 'F')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 11, 0), 'K')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 11, -1), 'R')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 12, 1), 'F')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 12, 0), 'K')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 12, -1), 'O')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 12, 1), 'C')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 12, 0), 'K')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 12, -1), 'R')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 13, 1), 'C')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 13, 0), 'E')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 13, -1), 'O')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 13, 1), 'C')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 13, 0), 'E')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 13, -1), 'O')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 14, 1), 'C')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 14, 0), 'E')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 14, -1), 'H')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 14, 1), 'B')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 14, 0), 'E')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 14, -1), 'O')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 15, 1), 'C')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 15, 0), 'B')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 15, -1), 'H')

        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 15, 1), 'B')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 15, 0), 'B')
        self.assertEqual(forecast.ZambrettiCode(1013.0, 5, 15, -1), 'O')

    def test_zambretti_text(self):
        self.assertEqual(forecast.ZambrettiText('A'), 'Settled fine')
        self.assertEqual(forecast.ZambrettiText('B'), 'Fine weather')
        self.assertEqual(forecast.ZambrettiText('C'), 'Becoming fine')
        self.assertEqual(forecast.ZambrettiText('D'), 'Fine, becoming less settled')
        self.assertEqual(forecast.ZambrettiText('E'), 'Fine, possible showers')
        self.assertEqual(forecast.ZambrettiText('F'), 'Fairly fine, improving')
        self.assertEqual(forecast.ZambrettiText('G'), 'Fairly fine, possible showers early')
        self.assertEqual(forecast.ZambrettiText('H'), 'Fairly fine, showery later')
        self.assertEqual(forecast.ZambrettiText('I'), 'Showery early, improving')
        self.assertEqual(forecast.ZambrettiText('J'), 'Changeable, mending')
        self.assertEqual(forecast.ZambrettiText('K'), 'Fairly fine, showers likely')
        self.assertEqual(forecast.ZambrettiText('L'), 'Rather unsettled clearing later')
        self.assertEqual(forecast.ZambrettiText('M'), 'Unsettled, probably improving')
        self.assertEqual(forecast.ZambrettiText('N'), 'Showery, bright intervals')
        self.assertEqual(forecast.ZambrettiText('O'), 'Showery, becoming less settled')
        self.assertEqual(forecast.ZambrettiText('P'), 'Changeable, some rain')
        self.assertEqual(forecast.ZambrettiText('Q'), 'Unsettled, short fine intervals')
        self.assertEqual(forecast.ZambrettiText('R'), 'Unsettled, rain later')
        self.assertEqual(forecast.ZambrettiText('S'), 'Unsettled, some rain')
        self.assertEqual(forecast.ZambrettiText('T'), 'Mostly very unsettled')
        self.assertEqual(forecast.ZambrettiText('U'), 'Occasional rain, worsening')
        self.assertEqual(forecast.ZambrettiText('V'), 'Rain at times, very unsettled')
        self.assertEqual(forecast.ZambrettiText('W'), 'Rain at frequent intervals')
        self.assertEqual(forecast.ZambrettiText('X'), 'Rain, very unsettled')
        self.assertEqual(forecast.ZambrettiText('Y'), 'Stormy, may improve')
        self.assertEqual(forecast.ZambrettiText('Z'), 'Stormy, much rain')

    def test_zambretti_generator(self):
        tname = 'test_zambretti_generator'
        tdir = get_testdir(tname)
        rmtree(tdir)
        cd = create_config(tdir, 'user.forecast.ZambrettiForecast')
        eng = weewx.wxengine.StdEngine(cd)
        zf = forecast.ZambrettiForecast(eng, cd)

        # first record, no trend, so no zambretti
        event = weewx.Event(weewx.NEW_ARCHIVE_RECORD)
        event.record = {'interval': 5, 'outHumidity': 60.0, 'rainRate': 0.0, 'heatindex': 62.779999999999994, 'radiation': None, 'inTemp': 66.230000000000004, 'windGustDir': 112.5, 'status': 0.0, 'barometer': 29.838662744470582, 'windchill': 62.779999999999994, 'dewpoint': 48.684961368525371, 'rain': 0.0, 'pressure': 29.806556408741884, 'rainTotal': 0.68999999999999995, 'altimeter': 29.830054257884523, 'usUnits': 1, 'UV': None, 'dateTime': 1378143300, 'windDir': 90.0, 'outTemp': 62.779999999999994, 'windSpeed': 0.0, 'inHumidity': 78.0, 'windGust': 0.0}
        record = zf.get_forecast(event)
        self.assertEqual(record, None)

        # next record gives us a trend
        event.record = {'barometer': 29.834685721179159, 'usUnits': 1, 'dateTime': 1378143900, 'windDir': 90.0}
        record = zf.get_forecast(event)
        self.assertEqual(record, {'event_ts': 1378143900, 'dateTime': 1378143900, 'zcode': 'C', 'issued_ts': 1378143900, 'method': 'Zambretti', 'usUnits': 1})

        # now the pressure goes up slightly
        event.record = {'barometer': 29.835649151484603, 'usUnits': 1, 'dateTime': 1378144200, 'windDir': 90.0}
        record = zf.get_forecast(event)
        self.assertEqual(record, {'event_ts': 1378144200, 'dateTime': 1378144200, 'zcode': 'K', 'issued_ts': 1378144200, 'method': 'Zambretti', 'usUnits': 1})

        # now the pressure drops
        event.record = {'barometer': 29.0, 'usUnits': 1, 'dateTime': 1378144500, 'windDir': 90.0}
        record = zf.get_forecast(event)
        self.assertEqual(record, {'event_ts': 1378144500, 'dateTime': 1378144500, 'zcode': 'L', 'issued_ts': 1378144500, 'method': 'Zambretti', 'usUnits': 1})

    def test_zambretti_units(self):
        '''ensure that zambretti works with both US and METRIC'''

        tname = 'test_zambretti_units'
        tdir = get_testdir(tname)
        rmtree(tdir)
        cd = create_config(tdir, 'user.forecast.ZambrettiForecast')
        eng = weewx.wxengine.StdEngine(cd)
        zf = forecast.ZambrettiForecast(eng, cd)

        # first record, no trend, so no zambretti
        event = weewx.Event(weewx.NEW_ARCHIVE_RECORD)
        event.record = {'barometer': 1010.33712053, 'usUnits': weewx.METRIC, 'dateTime': 1378143300, 'windDir': 90.0}
        record = zf.get_forecast(event)
        self.assertEqual(record, None)

        # next record gives us a trend
        event.record = {'barometer': 1010.20245852, 'usUnits': weewx.METRIC, 'dateTime': 1378143900, 'windDir': 90.0}
        record = zf.get_forecast(event)
        self.assertEqual(record, {'event_ts': 1378143900, 'dateTime': 1378143900, 'zcode': 'C', 'issued_ts': 1378143900, 'method': 'Zambretti', 'usUnits': 1})

        # now the pressure goes up slightly
        event.record = {'barometer': 1010.23508027, 'usUnits': weewx.METRIC, 'dateTime': 1378144200, 'windDir': 90.0}
        record = zf.get_forecast(event)
        self.assertEqual(record, {'event_ts': 1378144200, 'dateTime': 1378144200, 'zcode': 'K', 'issued_ts': 1378144200, 'method': 'Zambretti', 'usUnits': 1})

    def test_zambretti_bogus_values(self):
        self.assertEqual(forecast.ZambrettiCode(0, 0, 0, 0), 'Z')
        self.assertEqual(forecast.ZambrettiCode(None, 0, 0, 0), None)
        self.assertEqual(forecast.ZambrettiCode(1013.0, 0, 16, 0), None)
        self.assertEqual(forecast.ZambrettiCode(1013.0, 12, 0, 0), None)

    def test_zambretti_templates(self):
        self.runTemplateTest('test_zambretti_templates',
                             'user.forecast.ZambrettiForecast',
                             FakeData.gen_fake_zambretti_data(),
                             '''<html>
  <body>
$forecast.zambretti.dateTime
$forecast.zambretti.issued_ts
$forecast.zambretti.event_ts
$forecast.zambretti.code
$forecast.label('Zambretti', $forecast.zambretti.code)
  </body>
</html>
''',
                             '''<html>
  <body>
22-Aug-2013 12:40
22-Aug-2013 12:40
22-Aug-2013 12:40
A
Settled fine
  </body>
</html>
''')

    def test_zambretti_template_errors(self):
        t, tdir = self.setupTemplateTest('test_zambretti_template_errors',
                                         'user.forecast.ZambrettiForecast',
                                         [], '''<html>
  <body>
$forecast.zambretti.dateTime
$forecast.zambretti.code
  </body>
</html>
''')

        # test behavior when empty database
        t.run()
        self.compareContents(tdir + '/html/index.html', '''<html>
  <body>


  </body>
</html>
''')

        # test behavior when no database
        rmfile(tdir + '/html/index.html')
        rmfile(tdir + '/forecast.sdb')
        t.run()
        self.assertEqual(os.path.exists(tdir + '/html/index.html'), False)


    # -------------------------------------------------------------------------
    # NWS tests
    # -------------------------------------------------------------------------

    def test_nws_forecast(self):
        '''end-to-end test of nws forecast; inspect manually'''
        fcast = forecast.DownloadNWSForecast('BOX') # BOX, GYX
        if PRINT_OUTPUT:
            print fcast
        matrix = forecast.ParseNWSForecast(fcast, 'MAZ014') # MAZ014, ME027
        if PRINT_OUTPUT:
            print matrix
        records = forecast.ProcessNWSForecast('BOX', 'MAZ014', matrix)
        if PRINT_OUTPUT:
            print records
        pass

    def test_nws_download(self):
        '''spit out a current text forecast from nws; inspect manually'''
        fcast = forecast.DownloadNWSForecast('GYX')
        if PRINT_OUTPUT:
            print fcast
        lines = forecast.GetNWSLocation(fcast, 'MEZ027')
        if PRINT_OUTPUT:
            print '\n', '\n'.join(lines)

    def test_nws_date_to_ts(self):
        data = {'418 PM EDT SAT MAY 11 2013': 1368303480,
                '400 PM EDT SAT MAY 11 2013': 1368302400,
                '1200 AM EDT SAT MAY 11 2013': 1368288000,
                '1100 AM EDT SAT MAY 11 2013': 1368284400,
                '418 AM EDT SAT MAY 11 2013': 1368260280,
                '400 AM EDT SAT MAY 11 2013': 1368259200,
                '000 AM EDT SAT MAY 11 2013': 1368244800}
        for x in data.keys():
            a = '%s : %d' % (x, data[x])
            b = '%s : %d' % (x, forecast.date2ts(x))
            self.assertEqual(a, b)

    def test_nws_bogus_location(self):
        matrix = forecast.ParseNWSForecast(PFM_BOS, 'foobar')
        self.assertEqual(matrix, None)

    def test_parse_multiple_nws_forecast(self):
        matrix = forecast.ParseNWSForecast(PFM_BOS, 'CTZ002')
        expected = {}
        expected['temp'] = [None, None, None, '68', '67', '66', '62', '59', '57', '59', '63', '69', '65', '58', '48', '43', '40', '45', '56', '61', '61', '52', '40', '44', '62', '54', '43', '49', '70', '63', '52', '56', '72', '66', '56', '60', '75', '66']
        expected['tempMin'] = [None, None, None, None, None, None, None, None, None, '55', None, None, None, None, None, None, None, '38', None, None, None, None, None, '36', None, None, None, '39', None, None, None, '48', None, None, None, '53', None, None]
        expected['tempMax'] = [None, None, None, None, None, '71', None, None, None, None, None, None, None, '69', None, None, None, None, None, None, None, '63', None, None, None, '64', None, None, None, '72', None, None, None, '74', None, None, None, '77']
        expected['qsf'] = [None, None, None, None, None, '00-00', None, None, None, '00-00', None, None, None, '00-00', None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None]
        for label in expected.keys():
            self.assertEqual(matrix[label], expected[label])

        matrix = forecast.ParseNWSForecast(PFM_BOS, 'RIZ004')
        expected = {}
        expected['temp'] = [None, None, None, '66', '65', '63', '60', '59', '59', '60', '64', '71', '68', '62', '52', '47', '43', '48', '57', '61', '60', '53', '43', '46', '61', '55', '45', '49', '65', '60', '52', '55', '68', '63', '56', '59', '71', '64']
        expected['tempMin'] = [None, None, None, None, None, None, None, None, None, '58', None, None, None, None, None, None, None, '42', None, None, None, None, None, '39', None, None, None, '42', None, None, None, '49', None, None, None, '53', None, None]
        expected['tempMax'] = [None, None, None, None, None, '70', None, None, None, None, None, None, None, '72', None, None, None, None, None, None, None, '62', None, None, None, '63', None, None, None, '67', None, None, None, '70', None, None, None, '72']
        expected['qsf'] = [None, None, None, None, None, '00-00', None, None, None, '00-00', None, None, None, '00-00', None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None]
        for label in expected.keys():
            self.assertEqual(matrix[label], expected[label])

    def test_parse_nws_forecast_0(self):
        matrix = forecast.ParseNWSForecast(PFM_BOS_SINGLE, 'MAZ014')
        expected = {}
        expected['ts'] = [1368262800, 1368273600, 1368284400, 1368295200, 1368306000, 1368316800, 1368327600, 1368338400, 1368349200, 1368360000, 1368370800, 1368381600, 1368392400, 1368403200, 1368414000, 1368424800, 1368435600, 1368446400, 1368457200, 1368468000, 1368478800, 1368489600, 1368511200, 1368532800, 1368554400, 1368576000, 1368597600, 1368619200, 1368640800, 1368662400, 1368684000, 1368705600, 1368727200, 1368748800, 1368770400, 1368792000, 1368813600, 1368835200]
        expected['hour'] = ['05', '08', '11', '14', '17', '20', '23', '02', '05', '08', '11', '14', '17', '20', '23', '02', '05', '08', '11', '14', '17', '20', '02', '08', '14', '20', '02', '08', '14', '20', '02', '08', '14', '20', '02', '08', '14', '20']
        expected['temp'] = [None, None, None, '69', '68', '66', '63', '61', '59', '62', '66', '68', '68', '61', '52', '47', '44', '48', '56', '60', '59', '53', '44', '47', '59', '53', '45', '49', '65', '60', '52', '55', '67', '63', '56', '59', '69', '63']
        expected['tempMin'] = [None, None, None, None, None, None, None, None, None, '57', None, None, None, None, None, None, None, '43', None, None, None, None, None, '41', None, None, None, '42', None, None, None, '49', None, None, None, '54', None, None]
        expected['tempMax'] = [None, None, None, None, None, '72', None, None, None, None, None, None, None, '69', None, None, None, None, None, None, None, '61', None, None, None, '60', None, None, None, '67', None, None, None, '68', None, None, None, '70']
        expected['qsf'] = [None, None, None, None, None, '00-00', None, None, None, '00-00', None, None, None, '00-00', None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None]
        for label in expected.keys():
            self.assertEqual(matrix[label], expected[label])

    def test_parse_nws_forecast_1(self):
        matrix = forecast.ParseNWSForecast(PFM_GYX_SINGLE_1, 'MEZ027')
        expected = {}
        expected['humidity'] = ['48', '63', '78', '93', '100', '93', '75', '73', '78', '87', '100', '100', '100', '97', '73', '66', '71', '90', '97', '100', '100', '100', None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None]
        for label in expected.keys():
            self.assertEqual(matrix[label], expected[label])

    def test_parse_nws_forecast_2(self):
        matrix = forecast.ParseNWSForecast(PFM_GYX_SINGLE_2, 'MEZ027')
        expected = {}
        expected['humidity'] = [None, None, None, '76', '76', '90', '93', '100', '96', '97', '90', '84', '87', '93', '100', '100', '100', '97', 'MM', '100', 'MM', '100', None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None]
        for label in expected.keys():
            self.assertEqual(matrix[label], expected[label])

    def test_parse_nws_forecast_3(self):
        matrix = forecast.ParseNWSForecast(PFM_GYX_SINGLE_3, 'MEZ027')
        expected = {}
        expected['humidity'] = [None, '90', '97', '100', '100', '100', '87', '79', '76', '90', '93', '96', '100', '100', '100', '100', '97', '97', '100', '100', '100', '97', None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None]
        for label in expected.keys():
            self.assertEqual(matrix[label], expected[label])

    def test_nws_template_periods(self):
        matrix = forecast.ParseNWSForecast(PFM_BOS_SINGLE, 'MAZ014')
        records = forecast.ProcessNWSForecast('BOX', 'MAZ014', matrix)
        template = PERIODS_TEMPLATE.replace('SOURCE', 'NWS')
        template = template.replace('TS', '1368328140')
        self.runTemplateTest('test_nws_template_periods',
                             'user.forecast.NWSForecast',
                             records,
                             template,
                             '''<html>
  <body>
12-May-2013 02:00 10800     - 61.0F     - 87% 57.0F 8.0 mph     - S      -
12-May-2013 05:00 10800     - 59.0F     - 90% 56.0F 8.0 mph     - S      -
12-May-2013 08:00 10800 57.0F 62.0F     - 81% 56.0F 10.0 mph     - SW  90%
12-May-2013 11:00 10800     - 66.0F     - 68% 55.0F 11.0 mph     - W      -
12-May-2013 14:00 10800     - 68.0F     - 51% 49.0F 16.0 mph     - W      -
12-May-2013 17:00 10800     - 68.0F     - 37% 41.0F 18.0 mph     - W      -
12-May-2013 20:00 10800     - 61.0F 69.0F 41% 37.0F 14.0 mph 27.0 mph W  70%
12-May-2013 23:00 10800     - 52.0F     - 48% 33.0F 11.0 mph     - W      -
13-May-2013 02:00 10800     - 47.0F     - 53% 31.0F 10.0 mph     - W      -
13-May-2013 05:00 10800     - 44.0F     - 55% 29.0F 8.0 mph     - W      -
13-May-2013 08:00 10800 43.0F 48.0F     - 47% 29.0F 12.0 mph 23.0 mph W  0%
13-May-2013 11:00 10800     - 56.0F     - 35% 29.0F 9.0 mph 20.0 mph W      -
13-May-2013 14:00 10800     - 60.0F     - 27% 26.0F 16.0 mph     - W      -
13-May-2013 17:00 10800     - 59.0F     - 30% 28.0F 12.0 mph 23.0 mph SW      -
13-May-2013 20:00 10800     - 53.0F 61.0F 35% 26.0F 9.0 mph     - W  5%
14-May-2013 02:00 21600     - 44.0F     -     - 35.0F     -     -       -
14-May-2013 08:00 21600 41.0F 47.0F     -     - 33.0F     -     - NW GN 5%
14-May-2013 14:00 21600     - 59.0F     -     - 29.0F     -     -       -
14-May-2013 20:00 21600     - 53.0F 60.0F     - 32.0F     -     - NW LT 10%
15-May-2013 02:00 21600     - 45.0F     -     - 33.0F     -     -       -
  </body>
</html>
''')

    def test_nws_template_summary(self):
        template = SUMMARY_TEMPLATE.replace('SOURCE', 'NWS')
        template = template.replace('TS', '1377525600')
        self.runTemplateTest('test_nws_template_summary',
                             'user.forecast.NWSForecast',
                             FakeData.gen_fake_nws_data(),
                             template,
                             '''<html>
  <body>
forecast for BOX MAZ014 for the day 26-Aug-2013 00:00 as of 26-Aug-2013 07:19
OV
68.0F
79.0F
74.8F
57.0F
67.0F
63.0F
58%
81%
67%
5.0 mph
12.0 mph
9.3 mph
21.0 mph
SW
  SW
  W

50%
  rainshwrs
  tstms
  </body>
</html>
''')

# this will exercise all of the labels
#  #for $k,$v in $f.items():
#$k: $v
#  #end for

    def test_nws_template_table(self):
        '''exercise the period and summary template elements'''

        template = TABLE_TEMPLATE.replace('SOURCE', 'NWS')
        template = template.replace('TS', '1377525600')
        t, tdir = self.setupTemplateTest('test_nws_template_table',
                                         'user.forecast.NWSForecast',
                                         FakeData.gen_fake_nws_data(),
                                         template)
        t.run()


    # -------------------------------------------------------------------------
    # WU tests
    # -------------------------------------------------------------------------

    def test_wu_forecast(self):
        '''end-to-end test of wu forecast; inspect manually'''
        fcast = forecast.DownloadWUForecast(WU_API_KEY, '02139')
        if PRINT_OUTPUT:
            print fcast
        matrix = forecast.CreateWUForecastMatrix(fcast)
        if PRINT_OUTPUT:
            print matrix
        records = forecast.ProcessWUForecast(matrix)
        if PRINT_OUTPUT:
            print records

    def test_wu_download(self):
        '''spit out a current text forecast from wu; inspect manually'''
        fcast = forecast.DownloadWUForecast(WU_API_KEY, '02139')
        if PRINT_OUTPUT:
            print fcast

    def test_create_wu_forecast_matrix(self):
        matrix = forecast.CreateWUForecastMatrix(WU_BOS)
        expected = {}
        expected['ts'] = [1368673200, 1368759600, 1368846000, 1368932400, 1369018800, 1369105200, 1369191600, 1369278000, 1369364400, 1369450800]
        expected['tempMin'] = [55.0, 54.0, 54.0, 48.0, 48.0, 52.0, 54.0, 55.0, 54.0, 57.0]
        expected['tempMax'] = [68.0, 77.0, 72.0, 70.0, 66.0, 68.0, 73.0, 77.0, 75.0, 75.0]
        expected['windDir'] = ['SSW', 'W', 'NW', 'SE', 'SE', 'S', 'E', 'ESE', 'SE', 'SE']
        for label in expected.keys():
            self.assertEqual(matrix[label], expected[label])

    def test_process_wu_forecast(self):
        matrix = forecast.CreateWUForecastMatrix(WU_BOS, issued_ts=1377298279)
        records = forecast.ProcessWUForecast(matrix, now=1377298279)
        expected = [
            {'clouds': 'B2', 'qsf': 0, 'hour': 23, 'event_ts': 1368673200, 'qpf': 0.10000000000000001, 'ts': 1368673200, 'pop': 50, 'dateTime': 1377298279, 'windDir': 'SSW', 'tempMin': 55.0, 'windSpeed': 15, 'windGust': 19, 'duration': 86400, 'humidity': 69, 'issued_ts':1377298279, 'method': 'WU', 'usUnits': 1, 'tempMax': 68.0},
            {'clouds': 'FW', 'qsf': 0, 'hour': 23, 'event_ts': 1368759600, 'qpf': 0.0, 'ts': 1368759600, 'pop': 10, 'dateTime': 1377298279, 'windDir': 'W', 'tempMin': 54.0, 'windSpeed': 19, 'windGust': 23, 'duration': 86400, 'humidity': 42, 'issued_ts':1377298279, 'method': 'WU', 'usUnits': 1, 'tempMax': 77.0},
            {'clouds': 'FW', 'qsf': 0, 'hour': 23, 'event_ts': 1368846000, 'qpf': 0.0, 'ts': 1368846000, 'pop': 10, 'dateTime': 1377298279, 'windDir': 'NW', 'tempMin': 54.0, 'windSpeed': 5, 'windGust': 11, 'duration': 86400, 'humidity': 51, 'issued_ts':1377298279, 'method': 'WU', 'usUnits': 1, 'tempMax': 72.0},
            {'clouds': 'B1', 'qsf': 0, 'hour': 23, 'event_ts': 1368932400, 'qpf': 0.0, 'ts': 1368932400, 'pop': 0, 'dateTime': 1377298279, 'windDir': 'SE', 'tempMin': 48.0, 'windSpeed': 7, 'windGust': 9, 'duration': 86400, 'humidity': 59, 'issued_ts':1377298279, 'method': 'WU', 'usUnits': 1, 'tempMax': 70.0},
            {'clouds': 'B2', 'qsf': 0, 'hour': 23, 'event_ts': 1369018800, 'qpf': 0.0, 'ts': 1369018800, 'pop': 0, 'dateTime': 1377298279, 'windDir': 'SE', 'tempMin': 48.0, 'windSpeed': 8, 'windGust': 10, 'duration': 86400, 'humidity': 70, 'issued_ts':1377298279, 'method': 'WU', 'usUnits': 1, 'tempMax': 66.0},
            {'clouds': 'OV', 'qsf': 0, 'hour': 23, 'event_ts': 1369105200, 'qpf': 0.040000000000000001, 'ts': 1369105200, 'pop': 0, 'dateTime': 1377298279, 'windDir': 'S', 'tempMin': 52.0, 'windSpeed': 11, 'windGust': 13, 'duration': 86400, 'humidity': 85, 'issued_ts':1377298279, 'method': 'WU', 'usUnits': 1, 'tempMax': 68.0},
            {'clouds': 'B2', 'qsf': 0, 'hour': 23, 'event_ts': 1369191600, 'qpf': 0.02, 'ts': 1369191600, 'pop': 0, 'dateTime': 1377298279, 'windDir': 'E', 'tempMin': 54.0, 'windSpeed': 8, 'windGust': 10, 'duration': 86400, 'humidity': 72, 'issued_ts':1377298279, 'method': 'WU', 'usUnits': 1, 'tempMax': 73.0},
            {'clouds': 'B1', 'qsf': 0, 'hour': 23, 'event_ts': 1369278000, 'qpf': 0.02, 'ts': 1369278000, 'pop': 0, 'dateTime': 1377298279, 'windDir': 'ESE', 'tempMin': 55.0, 'windSpeed': 6, 'windGust': 8, 'duration': 86400, 'humidity': 76, 'issued_ts':1377298279, 'method': 'WU', 'usUnits': 1, 'tempMax': 77.0},
            {'clouds': 'B1', 'qsf': 0, 'hour': 23, 'event_ts': 1369364400, 'qpf': 0.02, 'ts': 1369364400, 'pop': 0, 'dateTime': 1377298279, 'windDir': 'SE', 'tempMin': 54.0, 'windSpeed': 3, 'windGust': 4, 'duration': 86400, 'humidity': 92, 'issued_ts':1377298279, 'method': 'WU', 'usUnits': 1, 'tempMax': 75.0},
            {'clouds': 'B1', 'qsf': 0, 'hour': 23, 'event_ts': 1369450800, 'qpf': 0.17999999999999999, 'ts': 1369450800, 'pop': 40, 'dateTime': 1377298279, 'windDir': 'SE', 'tempMin': 57.0, 'windSpeed': 3, 'windGust': 5, 'duration': 86400, 'humidity': 90, 'issued_ts':1377298279, 'method': 'WU', 'usUnits': 1, 'tempMax': 75.0}
            ]
        self.assertEqual(records, expected)

    def test_download_wu_forecast_bad_key(self):
        # warning! tabs matter in the following string
        expected = '''
{
	"response": {
		"version": "0.1"
		,"termsofService": "http://www.wunderground.com/weather/api/d/terms.html"
		,"features": {
		}
		,
	"error": {
		"type": "keynotfound"
		,"description": "this key does not exist"
	}
	}
}
'''
        fcast = forecast.DownloadWUForecast('foobar', '02139')
        self.assertEqual(fcast, expected)

    def test_detect_wu_download_errors(self):
        fcast = '''
{
	"response": {
		"version": "0.1"
		,"termsofService": "http://www.wunderground.com/weather/api/d/terms.html"
		,"features": {
		}
		,
	"error": {
		"type": "keynotfound"
		,"description": "this key does not exist"
	}
	}
}
'''
        matrix = forecast.CreateWUForecastMatrix(fcast)
        self.assertEqual(matrix, None)

    def test_wu_template_periods(self):
        matrix = forecast.CreateWUForecastMatrix(WU_TENANTS_HARBOR,
                                                 issued_ts=1378090800)
        records = forecast.ProcessWUForecast(matrix)
        template = PERIODS_TEMPLATE.replace('SOURCE', 'WU')
        template = template.replace('TS', '1378090800')
        self.runTemplateTest('test_wu_template_periods',
                             'user.forecast.WUForecast',
                             records,
                             template,
                             '''<html>
  <body>
01-Sep-2013 23:00 86400 73.0F     - 86.0F 83%     - 10.0 mph 11.0 mph SSW  40%
02-Sep-2013 23:00 86400 72.0F     - 81.0F 91%     - 8.0 mph 10.0 mph S  60%
03-Sep-2013 23:00 86400 61.0F     - 81.0F 70%     - 8.0 mph 9.0 mph SW  50%
04-Sep-2013 23:00 86400 59.0F     - 79.0F 78%     - 10.0 mph 11.0 mph NW  0%
05-Sep-2013 23:00 86400 57.0F     - 75.0F 90%     - 8.0 mph 10.0 mph W  0%
06-Sep-2013 23:00 86400 54.0F     - 72.0F 74%     - 4.0 mph 6.0 mph ESE  0%
07-Sep-2013 23:00 86400 63.0F     - 79.0F 93%     - 11.0 mph 14.0 mph SW  0%
08-Sep-2013 23:00 86400 61.0F     - 77.0F 65%     - 7.0 mph 9.0 mph E  0%
09-Sep-2013 23:00 86400 61.0F     - 77.0F 75%     - 3.0 mph 4.0 mph SW  0%
10-Sep-2013 23:00 86400 61.0F     - 79.0F 86%     - 2.0 mph 3.0 mph SSW  0%
  </body>
</html>
''')

    def test_wu_template_summary(self):
        matrix = forecast.CreateWUForecastMatrix(WU_TENANTS_HARBOR,
                                                 issued_ts=1378090800)
        records = forecast.ProcessWUForecast(matrix)
        template = SUMMARY_TEMPLATE.replace('SOURCE', 'WU')
        template = template.replace('TS', '1378090800')
        self.runTemplateTest('test_wu_template_summary',
                             'user.forecast.WUForecast',
                             records,
                             template,
                             '''<html>
  <body>
forecast for None None for the day 01-Sep-2013 00:00 as of 01-Sep-2013 23:00
B2


    -


    -
83%
83%
83%
10.0 mph
10.0 mph
10.0 mph
11.0 mph
SSW
  SSW

40%
  </body>
</html>
''')

    def test_wu_template_table(self):
        '''exercise the period and summary template elements'''

        matrix = forecast.CreateWUForecastMatrix(WU_TENANTS_HARBOR)
        records = forecast.ProcessWUForecast(matrix)
        template = TABLE_TEMPLATE.replace('SOURCE', 'WU')
        template = template.replace('TS', '1378090800')
        t, tdir = self.setupTemplateTest('test_wu_template_table',
                                         'user.forecast.WUForecast',
                                         records,
                                         template)
        t.run()


    # -------------------------------------------------------------------------
    # xtide tests
    # -------------------------------------------------------------------------

    def test_xtide(self):
        tdir = get_testdir('test_xtide')
        rmtree(tdir)

        config_dict = create_config(tdir, 'user.forecast.XTideForecast')
        config_dict['Forecast']['XTide'] = {}
        config_dict['Forecast']['XTide']['location'] = 'Tenants Harbor'

        # create a simulator with which to test
        e = wxengine.StdEngine(config_dict)
        f = forecast.XTideForecast(e, config_dict)

        # check a regular set of tides
        st = '2013-08-20 12:00'
        tt = time.strptime(st, '%Y-%m-%d %H:%M')
        sts = time.mktime(tt)
        et = '2013-08-22 12:00'
        tt = time.strptime(et, '%Y-%m-%d %H:%M')
        ets = time.mktime(tt)
        lines = f.generate_tide(sts=sts, ets=ets)
        if lines is None:
            return
        
        expect = '''Tenants Harbor| Maine,2013.08.20,16:47,-0.71 ft,Low Tide
Tenants Harbor| Maine,2013.08.20,19:00,,Moonrise
Tenants Harbor| Maine,2013.08.20,19:32,,Sunset
Tenants Harbor| Maine,2013.08.20,21:45,,Full Moon
Tenants Harbor| Maine,2013.08.20,23:04,11.56 ft,High Tide
Tenants Harbor| Maine,2013.08.21,05:24,-1.35 ft,Low Tide
Tenants Harbor| Maine,2013.08.21,05:47,,Sunrise
Tenants Harbor| Maine,2013.08.21,06:28,,Moonset
Tenants Harbor| Maine,2013.08.21,11:38,10.73 ft,High Tide
Tenants Harbor| Maine,2013.08.21,17:41,-0.95 ft,Low Tide
Tenants Harbor| Maine,2013.08.21,19:31,,Sunset
Tenants Harbor| Maine,2013.08.21,19:33,,Moonrise
Tenants Harbor| Maine,2013.08.21,23:57,11.54 ft,High Tide
Tenants Harbor| Maine,2013.08.22,05:48,,Sunrise
Tenants Harbor| Maine,2013.08.22,06:13,-1.35 ft,Low Tide
Tenants Harbor| Maine,2013.08.22,07:40,,Moonset
'''
        self.assertEqual(''.join(lines), expect)

        # verify that records are created properly
        expect = [{'hilo': 'L', 'offset': '-0.71', 'event_ts': 1377031620,
                   'method': 'XTide', 'usUnits': 1, 'issued_ts': 1377043837,
                   'dateTime': 1377043837, 'location': 'Tenants Harbor' },
                  {'hilo': 'H', 'offset': '11.56', 'event_ts': 1377054240,
                   'method': 'XTide', 'usUnits': 1, 'issued_ts': 1377043837,
                   'dateTime': 1377043837, 'location': 'Tenants Harbor' },
                  {'hilo': 'L', 'offset': '-1.35', 'event_ts': 1377077040,
                   'method': 'XTide', 'usUnits': 1, 'issued_ts': 1377043837,
                   'dateTime': 1377043837, 'location': 'Tenants Harbor' },
                  {'hilo': 'H', 'offset': '10.73', 'event_ts': 1377099480,
                   'method': 'XTide', 'usUnits': 1, 'issued_ts': 1377043837,
                   'dateTime': 1377043837, 'location': 'Tenants Harbor' },
                  {'hilo': 'L', 'offset': '-0.95', 'event_ts': 1377121260,
                   'method': 'XTide', 'usUnits': 1, 'issued_ts': 1377043837,
                   'dateTime': 1377043837, 'location': 'Tenants Harbor' },
                  {'hilo': 'H', 'offset': '11.54', 'event_ts': 1377143820,
                   'method': 'XTide', 'usUnits': 1, 'issued_ts': 1377043837,
                   'dateTime': 1377043837, 'location': 'Tenants Harbor' },
                  {'hilo': 'L', 'offset': '-1.35', 'event_ts': 1377166380,
                   'method': 'XTide', 'usUnits': 1, 'issued_ts': 1377043837,
                   'dateTime': 1377043837, 'location': 'Tenants Harbor' }]
        records = f.parse_forecast(lines, now=1377043837)
        self.assertEqual(records, expect)

    def test_xtide_error_handling(self):
        tdir = get_testdir('test_xtide_error_handling')
        rmtree(tdir)

        # we need a barebones config
        config_dict = create_config(tdir, 'user.forecast.XTideForecast')
        config_dict['Forecast']['XTide'] = {}
        config_dict['Forecast']['XTide']['location'] = 'FooBar'

        # create a simulator with which to test
        e = wxengine.StdEngine(config_dict)
        f = forecast.XTideForecast(e, config_dict)

        # check a regular set of tides with the bogus location
        st = '2013-08-20 12:00'
        tt = time.strptime(st, '%Y-%m-%d %H:%M')
        sts = time.mktime(tt)
        et = '2013-08-22 12:00'
        tt = time.strptime(et, '%Y-%m-%d %H:%M')
        ets = time.mktime(tt)
        lines = f.generate_tide(sts=sts, ets=ets)
        self.assertEquals(lines, None)

    def test_xtide_templates(self):
        self.runTemplateTest('test_xtide_templates',
                             'user.forecast.XTideForecast',
                             FakeData.gen_fake_xtide_data(),
                             '''<html>
  <body>
$forecast.xtide(0, from_ts=1377043837).dateTime
$forecast.xtide(0, from_ts=1377043837).event_ts
$forecast.xtide(0, from_ts=1377043837).hilo
$forecast.xtide(0, from_ts=1377043837).offset

$forecast.xtide(1, from_ts=1377043837).dateTime
$forecast.xtide(1, from_ts=1377043837).event_ts
$forecast.xtide(1, from_ts=1377043837).hilo
$forecast.xtide(1, from_ts=1377043837).offset

tide forecast as of $forecast.xtide(0, from_ts=1377043837).dateTime
#for $tide in $forecast.xtides(from_ts=1377043837, max_events=4):
  $tide.hilo of $tide.offset at $tide.event_ts
#end for

tide forecast as of $forecast.xtide(0, from_ts=1377043837).dateTime.format("%Y.%m.%d %H:%M")
#for $tide in $forecast.xtides(from_ts=1377043837, max_events=4):
  $tide.hilo of $tide.offset.format("%.2f") at $tide.event_ts.format("%H:%M %A")
#end for
  </body>
</html>
''',
                             '''<html>
  <body>
20-Aug-2013 20:10
20-Aug-2013 23:04
H
12 feet

20-Aug-2013 20:10
21-Aug-2013 05:24
L
-1 feet

tide forecast as of 20-Aug-2013 20:10
  H of 12 feet at 20-Aug-2013 23:04
  L of -1 feet at 21-Aug-2013 05:24
  H of 11 feet at 21-Aug-2013 11:38
  L of -1 feet at 21-Aug-2013 17:41

tide forecast as of 2013.08.20 20:10
  H of 11.56 feet at 23:04 Tuesday
  L of -1.35 feet at 05:24 Wednesday
  H of 10.73 feet at 11:38 Wednesday
  L of -0.95 feet at 17:41 Wednesday
  </body>
</html>
''')

    def test_xtide_templates_bad_index(self):
        self.runTemplateTest('test_xtide_templates_bad_index',
                             'user.forecast.XTideForecast',
                             FakeData.gen_fake_xtide_data(),
                             '''<html>
  <body>
$forecast.xtide(10, from_ts=1377043837).dateTime
$forecast.xtide(10, from_ts=1377043837).event_ts
$forecast.xtide(10, from_ts=1377043837).hilo
$forecast.xtide(10, from_ts=1377043837).offset

$forecast.xtide(-1, from_ts=1377043837).dateTime
$forecast.xtide(-1, from_ts=1377043837).event_ts
$forecast.xtide(-1, from_ts=1377043837).hilo
$forecast.xtide(-1, from_ts=1377043837).offset
  </body>
</html>
''',
                             '''<html>
  <body>









  </body>
</html>
''')


    # -------------------------------------------------------------------------
    # almanac tests
    # -------------------------------------------------------------------------

    def test_almanac(self):
        # FIXME: this test does not need any data or forecaster
        self.runTemplateTest('test_almanac',
                             'user.forecast.XTideForecast',
                             [],
                             '''<html>
  <body>
#set $a = $forecast.almanac(ts=1325376000)
$a.sunrise
$a.sunset
$a.moon_fullness
#set $a = $forecast.almanac(ts=1325548800)
$a.sunrise
$a.sunset
$a.moon_fullness
  </body>
</html>
''',
                             '''<html>
  <body>
00:36
12:09
34
00:37
12:10
55
  </body>
</html>
''')


    # -------------------------------------------------------------------------
    # general forecast tests
    # -------------------------------------------------------------------------

    def test_config_inheritance(self):
        """ensure that configuration inheritance works properly"""

        tdir = get_testdir('test_config_inheritance')
        rmtree(tdir)
        config_dict = create_config(tdir, 'user.forecast.ZambrettiForecast')
        config_dict['Forecast']['max_age'] = 1
        e = wxengine.StdEngine(config_dict)
        f = forecast.ZambrettiForecast(e, config_dict)
        self.assertEqual(f.max_age, 1)

        config_dict['Forecast']['Zambretti'] = {}
        config_dict['Forecast']['Zambretti']['max_age'] = 300
        f = forecast.ZambrettiForecast(e, config_dict)
        self.assertEqual(f.max_age, 300)

    def test_pruning(self):
        """ensure that forecast pruning works properly"""

        tdir = get_testdir('test_pruning')
        rmtree(tdir)

        config_dict = create_config(tdir, 'user.forecast.ZambrettiForecast')
        config_dict['Forecast']['max_age'] = 1

        method_id = 'Zambretti'
        table = 'archive'
        dbspec = config_dict['Forecast']['database']
        archive = forecast.Forecast.setup_database(dbspec, table, method_id,
                                                   config_dict,
                                                   forecast.defaultForecastSchema)

        # create a zambretti forecaster and simulator with which to test
        e = wxengine.StdEngine(config_dict)
        f = forecast.ZambrettiForecast(e, config_dict)
        record = {}
        record['usUnits'] = weewx.METRIC
        record['barometer'] = 1030
        record['windDir'] = 180
        event = weewx.Event(weewx.NEW_ARCHIVE_RECORD)
        event.record = record
        event.record['dateTime'] = int(time.time())
        f.get_forecast(event) # first zambretti is None to set trend
        time.sleep(1)
        event.record['dateTime'] = int(time.time())
        forecast.Forecast.save_forecast(archive, f.get_forecast(event))
        time.sleep(1)
        event.record['dateTime'] = int(time.time())
        forecast.Forecast.save_forecast(archive, f.get_forecast(event))
        time.sleep(1)
        event.record['dateTime'] = int(time.time())
        forecast.Forecast.save_forecast(archive, f.get_forecast(event))
        time.sleep(1)
        event.record['dateTime'] = int(time.time())
        forecast.Forecast.save_forecast(archive, f.get_forecast(event))
        time.sleep(1)

        # make sure the records have been saved
        records = forecast.Forecast.get_saved_forecasts(archive, table, method_id)
        self.assertEqual(len(records), 4)

        # there should be one remaining after a prune
        forecast.Forecast.prune_forecasts(archive, table, method_id, event.record['dateTime'])
        records = forecast.Forecast.get_saved_forecasts(archive, table, method_id)
        self.assertEqual(len(records), 1)


# use this to run individual tests while debugging
def suite(testname):
    tests = [testname]
    return unittest.TestSuite(map(ForecastTest, tests))
            
# use '--test test_name' to specify a single test
if __name__ == '__main__':
    testname = None
    if len(sys.argv) == 3 and sys.argv[1] == '--test':
        testname = sys.argv[2]
    if testname is not None:
        unittest.TextTestRunner(verbosity=2).run(suite(testname))
    else:
        unittest.main()
