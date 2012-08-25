#
#    Copyright (c) 2009, 2010, 2012 Tom Keffer <tkeffer@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#
#    $Revision$
#    $Author$
#    $Date$
#

"""Main engine for the weewx weather system."""

# Python imports
from optparse import OptionParser
import Queue
import os.path
import signal
import socket
import sys
import syslog
import time

# 3rd party imports:
import configobj
import daemon

# weewx imports:
import weewx.archive
import weewx.stats
import weewx.station
import weewx.restful
import weewx.reportengine
import weeutil.weeutil

usagestr = """
  %prog config_path [--help] [--daemon] [--pidfile=PIDFILE] [--version] [--exit]

  Entry point to the weewx weather program. Can be run from the command
  line or, by specifying the '--daemon' option, as a daemon.

Arguments:
    config_path: Path to the weewx configuration file to be used.
"""

class BreakLoop(Exception):
    pass

#===============================================================================
#                    Class StdEngine
#===============================================================================

class StdEngine(object):
    """The main engine responsible for the creating and dispatching of events
    from the weather station.
    
    It loads a set of services, specified by an option in the configuration file.
    
    When a service loads, it binds callbacks to events. When an event occurs,
    the bound callback will be called."""
    
    def __init__(self, options, args):
        """Initialize an instance of StdEngine.
        
        options: An object containing values for all options, as returned
        by OptionParser
        
        args: The command line arguments, as returned by OptionParser.
        """
        config_dict = self.getConfiguration(options, args)

        # Set the logging facility.        
        syslog.openlog('weewx', syslog.LOG_PID|syslog.LOG_CONS)
        # Look for the debug flag. If set, ask for extra logging
        weewx.debug = int(config_dict.get('debug', 0))
        if weewx.debug:
            syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_DEBUG))
        else:
            syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_INFO))

        syslog.syslog(syslog.LOG_INFO, "wxengine: Starting up weewx version %s." % weewx.__version__)

        # Set a default socket time out, in case FTP or HTTP hang:
        timeout = int(config_dict.get('socket_timeout', 20))
        socket.setdefaulttimeout(timeout)

        # Set up the weather station hardware:
        self.setupStation(config_dict)

        # Hook for performing any chores before loading the services:
        self.preLoadServices(config_dict)
        
        # Load the services:
        self.loadServices(config_dict)
        
        # Another hook for after the services load.
        self.postLoadServices(config_dict)
        
    def getConfiguration(self, options, args):

        # Get and set the absolute path of the configuration file. A service
        # might to a chdir(), and then another service would be unable to find it.
        self.config_path = os.path.abspath(args[0])
        # Try to open up the given configuration file. Declare an error if
        # unable to.
        try :
            config_dict = configobj.ConfigObj(self.config_path, file_error=True)
        except IOError:
            sys.stderr.write("Unable to open configuration file %s" % args[0])
            syslog.syslog(syslog.LOG_CRIT, "wxengine: Unable to open configuration file %s" % args[0])
            # Reraise the exception (this will eventually cause the program to exit)
            raise
        except configobj.ConfigObjError:
            syslog.syslog(syslog.LOG_CRIT, "wxengine: Error while parsing configuration file %s" % args[0])
            raise

        syslog.syslog(syslog.LOG_INFO, "wxengine: Using configuration file %s." % self.config_path)
        
        return config_dict
    
    def setupStation(self, config_dict):
        """Set up the weather station hardware."""
        # Get the hardware type from the configuration dictionary. This will be
        # a string such as "VantagePro"
        stationType = config_dict['Station']['station_type']
    
        # Find the driver name for this type of hardware
        driver = config_dict[stationType]['driver']
        
        # Import the driver:
        __import__(driver)
    
        # Open up the weather station, wrapping it in a try block in case of failure.
        try:
            # This is a bit of Python wizardry. First, find the driver module in sys.modules.
            driver_module = sys.modules[driver]
            # Now find the function 'loader' within the module:
            loader_function = getattr(driver_module, 'loader')
            # Now call it with the configuration dictionary as the only argument:
            self.station = loader_function(config_dict)
        except Exception, ex:
            # Caught unrecoverable error. Log it:
            syslog.syslog(syslog.LOG_CRIT, "wxengine: Unable to open WX station hardware: %s" % ex)
            # Reraise the exception:
            raise
        
    def preLoadServices(self, config_dict):
        
        # Set up the callback dictionary:
        self.callbacks = dict()
        if hasattr(self.station, 'hardware_name'):
            hardware = self.station.hardware_name
        else:
            hardware = 'Unknown'
        self.stn_info = weewx.station.StationInfo(hardware=hardware, **config_dict['Station'])
        
    def loadServices(self, config_dict):
        """Set up the services to be run."""
        
        # This will hold the list of services to be run:
        self.service_obj = []

        # Get the names of the services to be run:
        service_names = weeutil.weeutil.option_as_list(config_dict['Engines']['WxEngine'].get('service_list'))
        
        # Wrap the instantiation of the services in a try block, so if an exception
        # occurs, any service that may have started can be shut down in an orderly way.
        try:
            for svc in service_names:
                # For each listed service in service_list, instantiates an instance of
                # the class, passing self and the configuration dictionary as the
                # arguments:
                syslog.syslog(syslog.LOG_DEBUG, "wxengine: Loading service %s" % svc)
                self.service_obj.append(weeutil.weeutil._get_object(svc, self, config_dict))
                syslog.syslog(syslog.LOG_DEBUG, "wxengine: Finished loading service %s" % svc)
        except:
            # An exception occurred. Shut down any running services, then
            # reraise the exception.
            self.shutDown()
            raise
        
    def postLoadServices(self, config_dict):
        pass

    def run(self):
        """Main execution entry point."""
        
        # Wrap the outer loop in a try block so we can do an orderly shutdown
        # should an exception occur:
        try:
            # Send out a STARTUP event:
            self.dispatchEvent(weewx.Event(weewx.STARTUP))
            
            syslog.syslog(syslog.LOG_INFO, "wxengine: Starting main packet loop.")

            # This is the outer loop. 
            while True:

                # First, let any interested services know the packet LOOP is about to start
                self.dispatchEvent(weewx.Event(weewx.PRE_LOOP))
    
                # Get ready to enter the main packet loop. An exception of type
                # BreakLoop will get thrown when a service wants to break the loop and
                # interact with the console.
                try:
                
                    # And this is the main packet LOOP. It will continuously
                    # generate LOOP packets until some service breaks it by throwing
                    # an exception (usually when an archive period has passed).
                    for packet in self.station.genLoopPackets():
                        
                        # Package the packet as an event, then dispatch it.            
                        self.dispatchEvent(weewx.Event(weewx.NEW_LOOP_PACKET, packet=packet))

                        # Allow services to break the loop by throwing an exception:
                        self.dispatchEvent(weewx.Event(weewx.CHECK_LOOP))
    
                except BreakLoop:
                    
                    # Send out an event saying the packet LOOP is done:
                    self.dispatchEvent(weewx.Event(weewx.POST_LOOP))

        finally:
            # The main loop has exited. Shut the engine down.
            self.shutDown()

    def bind(self, event_type, callback):
        """Binds an event to a callback function."""

        # Each event type has a list of callback functions to be called.
        # If we have not seen the event type yet, then create an empty list        
        if not self.callbacks.has_key(event_type):
            self.callbacks[event_type] = list()
        # Add this callback to the end of the list. This will result in them getting
        # called in the order they were originally bound.
        self.callbacks[event_type].append(callback)
    
    def dispatchEvent(self, event):
        """Call all registered callbacks for an event."""
        # See if any callbacks have been registered for this event type:
        if self.callbacks.has_key(event.event_type):
            # Yes, at least one has been registered. Call them in order:
            for callback in self.callbacks[event.event_type]:
                # Call the function with the event as an argument:
                callback(event)

    def shutDown(self):
        """Run when an engine shutdown is requested."""
        # If we've gotten as far as having a list of service objects, then shut
        # them all down:
        if hasattr(self, 'service_obj'):
            # Shutdown all the services:
            for obj in self.service_obj:
                # Wrap each individual service shutdown, in case of a problem.
                try:
                    obj.shutDown()
                except:
                    pass
            # Unbind the service. This will allow it to be garbage collected w/o
            # a circular reference:
                del obj
            del self.service_obj
            
        try:
            del self.callbacks
        except:
            pass

        try:
            # Close the console:
            self.station.closePort()
        except:
            pass


#===============================================================================
#                    Class StdService
#===============================================================================

class StdService(object):
    """Abstract base class for all services."""
    
    def __init__(self, engine, *dummy, **dummy_kwargs):
        self.engine = engine

    def bind(self, event_type, callback):
        """Bind the specified event to a callback."""
        # Just forward the request to the main engine:
        self.engine.bind(event_type, callback)

#===============================================================================
#                    Class StdConvert
#===============================================================================

class StdConvert(StdService):
    """Service for performing unit conversions.
    
    This service acts as a filter. Whatever packets and records come in are
    converted to a target unit system.
    
    This service should be run before most of the others, so observations appear
    in the correct unit."""
    
    def __init__(self, engine, config_dict):
        # Initialize my base class:
        super(StdConvert, self).__init__(engine, config_dict)

        # Get the target unit nickname (something like 'US' or 'METRIC'):
        target_unit_nickname = config_dict['StdConvert']['target_unit']
        # Get the target unit. This will be weewx.US or weewx.METRIC
        self.target_unit = weewx.units.unit_nicknames[target_unit_nickname.upper()]
        # Bind self.converter to the appropriate standard converter
        self.converter = weewx.units.StdUnitConverters[self.target_unit]
        
        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        
        syslog.syslog(syslog.LOG_INFO, "wxengine: StdConvert target unit is 0x%x" % self.target_unit)
        
    def new_loop_packet(self, event):
        """Do unit conversions for a LOOP packet"""
        # No need to do anything if the packet is already in the target
        # unit system
        if event.packet['usUnits'] == self.target_unit: return
        # Perform the conversion
        converted_packet = self.converter.convertDict(event.packet)
        # Add the new unit system
        converted_packet['usUnits'] = self.target_unit
        # Replace the old packet with the new, converted packet:
        event.packet = converted_packet

    def new_archive_record(self, event):
        """Do unit conversions for an archive record."""
        # No need to do anything if the record is already in the target
        # unit system
        if event.record['usUnits'] == self.target_unit: return
        # Perform the conversion
        converted_record = self.converter.convertDict(event.record)
        # Add the new unit system
        converted_record['usUnits'] = self.target_unit
        # Replace the old record with the new, converted record
        event.record = converted_record
        
#===============================================================================
#                    Class StdCalibrate
#===============================================================================

class StdCalibrate(StdService):
    """Adjust data using calibration expressions.
    
    This service must be run before StdArchive, so the correction is applied
    before the data is archived."""
    
    def __init__(self, engine, config_dict):
        # Initialize my base class:
        super(StdCalibrate, self).__init__(engine, config_dict)
        
        # Get the list of calibration corrections to apply. If a section
        # is missing, a KeyError exception will get thrown:
        try:
            correction_dict = config_dict['StdCalibrate']['Corrections']
            self.corrections = {}

            # For each correction, compile it, then save in a dictionary of
            # corrections to be applied:
            for obs_type in correction_dict.scalars:
                self.corrections[obs_type] = compile(correction_dict[obs_type], 
                                                     'StdCalibrate', 'eval')
            
            self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
            self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        except KeyError:
            syslog.syslog(syslog.LOG_NOTICE, "wxengine: No calibration information in config file. Ignored.")
            
    def new_loop_packet(self, event):
        """Apply a calibration correction to a LOOP packet"""
        for obs_type in self.corrections:
            if event.packet.has_key(obs_type) and event.packet[obs_type] is not None:
                event.packet[obs_type] = eval(self.corrections[obs_type], None, event.packet)

    def new_archive_record(self, event):
        """Apply a calibration correction to an archive packet"""
        for obs_type in self.corrections:
            if event.record.has_key(obs_type) and event.record[obs_type] is not None:
                event.record[obs_type] = eval(self.corrections[obs_type], None, event.record)

#===============================================================================
#                    Class StdQC
#===============================================================================

class StdQC(StdService):
    """Performs quality check on incoming data."""

    def __init__(self, engine, config_dict):
        super(StdQC, self).__init__(engine, config_dict)

        # If the 'StdQC' or 'MinMax' sections do not exist in the configuration
        # dictionary, then an exception will get thrown and nothing will be
        # done.
        try:
            min_max_dict = config_dict['StdQC']['MinMax']
            self.min_max_dict = {}
    
            for obs_type in min_max_dict.scalars:
                self.min_max_dict[obs_type] = (float(min_max_dict[obs_type][0]),
                                               float(min_max_dict[obs_type][1]))
            
            self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
            self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        except KeyError:
            syslog.syslog(syslog.LOG_NOTICE, "wxengine: No QC information in config file. Ignored.")
        
    def new_loop_packet(self, event):
        """Apply quality check to the data in a LOOP packet"""
        for obs_type in self.min_max_dict:
            if event.packet.has_key(obs_type) and event.packet[obs_type] is not None:
                if not self.min_max_dict[obs_type][0] <= event.packet[obs_type] <= self.min_max_dict[obs_type][1]:
                    event.packet[obs_type] = None

    def new_archive_record(self, event):
        """Apply quality check to the data in an archive packet"""
        for obs_type in self.min_max_dict:
            if event.record.has_key(obs_type) and event.record[obs_type] is not None:
                if not self.min_max_dict[obs_type][0] <= event.record[obs_type] <= self.min_max_dict[obs_type][1]:
                    event.record[obs_type] = None

#===============================================================================
#                    Class StdArchive
#===============================================================================

class StdArchive(StdService):
    """Service that archives LOOP and archive data in the SQL databases."""
    
    # This service manages an "accumulator", which records high/lows and averages
    # of LOOP packets over an archive period. At the end of the archive period
    # it then emits an archive record.
    
    def __init__(self, engine, config_dict):
        super(StdArchive, self).__init__(engine, config_dict)

        # If the station hardware supports an archive interval, use that.
        # Otherwise, get it out of the configuration file.
        if hasattr(self.engine.station, 'archive_interval'):
            self.archive_interval = self.engine.station.archive_interval
            syslog.syslog(syslog.LOG_DEBUG, "wxengine: Using station archive interval of %d" % self.archive_interval)
        else:
            self.archive_interval = config_dict['StdArchive'].as_int('archive_interval')
            syslog.syslog(syslog.LOG_DEBUG, "wxengine: Using archive interval of %d from config file" % self.archive_interval)
        self.archive_delay    = config_dict['StdArchive'].as_int('archive_delay')
        
        self.setupArchiveDatabase(config_dict)
        self.setupStatsDatabase(config_dict)
        
        self.bind(weewx.STARTUP,            self.startup)
        self.bind(weewx.PRE_LOOP,           self.pre_loop)
        self.bind(weewx.POST_LOOP,          self.post_loop)
        self.bind(weewx.CHECK_LOOP,         self.check_loop)
        self.bind(weewx.NEW_LOOP_PACKET,    self.new_loop_packet)
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
    
    def startup(self, event):
        """Called when the engine is starting up."""
        # The engine is starting up. The main task is to do a catch up on any
        # data still on the station, but not yet put in the database.
        self._catchup()
                    
    def pre_loop(self, event):
        """Called before the main packet loop is entered."""
        
        # The only thing that needs to be done is to calculate the end of the
        # archive period, and the end of the archive delay period.
        self.end_archive_period_ts = (int(time.time() / self.archive_interval) + 1) * self.archive_interval
        self.end_archive_delay_ts  =  self.end_archive_period_ts + self.archive_delay

    def new_loop_packet(self, event):
        """Called when A new LOOP record has arrived."""
        
        the_time = event.packet['dateTime']
        
        # Do we have an accumulator at all? If not, create one:
        if not hasattr(self, "accumulator"):
            self.accumulator = self._new_accumulator(the_time)

        # Try adding the LOOP packet to the existing accumulator. If the timestamp is
        # outside the timespan of the accumulator, an exception will be thrown:
        try:
            self.accumulator.addRecord(event.packet)
        except weewx.accum.OutOfSpan:
            # Shuffle accumulators:
            (self.old_accumulator, self.accumulator) = (self.accumulator, self._new_accumulator(the_time))
            # Add the LOOP packet to the new accumulator:
            self.accumulator.addRecord(event.packet)

    def check_loop(self, event):
        """Called after any loop packets have been processed. This is the opportunity
        to break the main loop by throwing an exception."""
        # Has the end of the archive delay period ended? If so, break the loop.
        if time.time() >= self.end_archive_delay_ts:
            raise BreakLoop

    def post_loop(self, event):
        """The main packet loop has ended. Time to process the old accumulator."""
        # If we happen to startup in the small time interval between the end of
        # the archive interval and the end of the archive delay period, then
        # there will be no old accumulator and an exception will be thrown. Be
        # prepared to catch it.
        try:
            self.statsDb.updateHiLo(self.old_accumulator)
        except AttributeError:
            return
        
        if self.engine.station.record_generation.lower() == 'software':
            # Extract a record out of the old accumulator. 
            record = self.old_accumulator.getRecord()
            # Add the archive interval
            record['interval'] = self.archive_interval / 60
            
            # Send out an event with the new record:
            self.engine.dispatchEvent(weewx.Event(weewx.NEW_ARCHIVE_RECORD, record=record))
        elif self.engine.station.record_generation.lower() == 'hardware':
            self._catchup()
        else:
            raise ValueError("Unknown station record generation value %s" % self.engine.station.record_generation)

    def new_archive_record(self, event):
        """Called when a new archive record has arrived. 
        Put it in the archive database."""
        self.archive.addRecord(event.record)
        self.statsDb.addRecord(event.record)

    def setupArchiveDatabase(self, config_dict):
        """Setup the main database archive"""
        archiveFilename = os.path.join(config_dict['Station']['WEEWX_ROOT'], 
                                       config_dict['StdArchive']['archive_file'])
        # Try to open up the database. If it doesn't exist or has not been initialized, an exception
        # will be thrown. Catch it, configure the database, and then try again.
        try:
            self.archive = weewx.archive.Archive(archiveFilename)
        except StandardError:
            # It's uninitialized. Configure it:
            weewx.archive.config(archiveFilename)
            # Try again to open it up:
            self.archive = weewx.archive.Archive(archiveFilename)

    def setupStatsDatabase(self, config_dict):
        """Setup the stats database"""
        
        statsFilename = os.path.join(config_dict['Station']['WEEWX_ROOT'], 
                                     config_dict['StdArchive']['stats_file'])
        # Try to open up the database. If it doesn't exist or has not been initialized, an exception
        # will be thrown. Catch it, configure the database, and then try again.
        try:
            self.statsDb = weewx.stats.StatsDb(statsFilename)
        except StandardError:
            # It's uninitialized. Configure it:
            weewx.stats.config(statsFilename, 
                               config_dict['StdArchive'].get('stats_types'))
            # Try again to open it up:
            self.statsDb = weewx.stats.StatsDb(statsFilename)

        # Backfill it with data from the archive. This will do nothing if the
        # stats database is already up-to-date.
        weewx.stats.backfill(self.archive, self.statsDb)
        
    def shutDown(self):
        self.archive.close()
        self.statsDb.close()
        
    def _catchup(self):
        """Pull any unarchived records off the console and archive them.""" 

        # Find out when the archive was last updated.
        lastgood_ts = self.archive.lastGoodStamp()      
        # Now ask the console for any new records since then. (Not all consoles
        # support this feature).
        try:
            for record in self.engine.station.genArchiveRecords(lastgood_ts):
                self.engine.dispatchEvent(weewx.Event(weewx.NEW_ARCHIVE_RECORD, record=record))
        except NotImplementedError:
            pass
        
    def _new_accumulator(self, timestamp):
        start_archive_ts = weeutil.weeutil.startOfInterval(timestamp,
                                                           self.archive_interval)
        end_archive_ts = start_archive_ts + self.archive_interval
        
        new_accumulator =  weewx.accum.DictAccum(weeutil.weeutil.TimeSpan(start_archive_ts,
                                                                          end_archive_ts))
        return new_accumulator
                                                  
#===============================================================================
#                    Class StdTimeSynch
#===============================================================================

class StdTimeSynch(StdService):
    """Regularly asks the station to synch up its clock."""
    
    def __init__(self, engine, config_dict):
        super(StdTimeSynch, self).__init__(engine, config_dict)
        
        # Zero out the time of last synch, and get the time between synchs.
        self.last_synch_ts = 0
        self.clock_check = int(config_dict['Station'].get('clock_check', 14400))
        self.max_drift   = int(config_dict['Station'].get('max_drift', 5))
        
        self.bind(weewx.PRE_LOOP, self.pre_loop)
        
    def pre_loop(self, event):
        """Ask the station to synch up if enough time has passed."""
        # Synch up the station's clock if it's been more than clock_check
        # seconds since the last check:
        now_ts = time.time()
        if now_ts - self.last_synch_ts >= self.clock_check:
            self.last_synch_ts = now_ts
            try:
                console_time = self.engine.station.getTime()
                if console_time is None: return
                diff = console_time - now_ts
                syslog.syslog(syslog.LOG_INFO, 
                              "wxengine: Clock error is %.2f seconds (positive is fast)" % diff)
                if abs(now_ts - console_time) > self.max_drift:
                    try:
                        self.engine.station.setTime(now_ts)
                    except NotImplementedError:
                        syslog.syslog(syslog.LOG_DEBUG, "wxengine: Station does not support setting the time")
            except NotImplementedError:
                syslog.syslog(syslog.LOG_DEBUG, "wxengine: Station does not support reading the time")

#===============================================================================
#                    Class StdPrint
#===============================================================================

class StdPrint(StdService):
    """Service that prints diagnostic information when a LOOP
    or archive packet is received."""
    
    def __init__(self, engine, config_dict):
        super(StdPrint, self).__init__(engine, config_dict)

        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        
    def new_loop_packet(self, event):
        """Print out the new LOOP packet"""
        print "LOOP:  ", weeutil.weeutil.timestamp_to_string(event.packet['dateTime']), event.packet
    
    def new_archive_record(self, event):
        """Print out the new archive record."""
        print "REC:   ", weeutil.weeutil.timestamp_to_string(event.record['dateTime']), event.record
        
#===============================================================================
#                    Class TestAccum
#===============================================================================

class TestAccum(StdService):
    """Allows comparison of archive records generated in software from
    LOOP data, versus archive records retrieved from the console. This only
    works for hardware that has an internal data logger."""

    def __init__(self, engine, config_dict):
        super(TestAccum, self).__init__(engine, config_dict)

        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        
    def new_archive_record(self, event):
        # Nothing to do unless the record generation is being done in software:
        if self.engine.station.record_generation.lower() != 'software':
            return
        accum_record = event.record
        
        timestamp = accum_record['dateTime']
        last_timestamp = timestamp - self.engine.station.archive_interval
        
        for stn_record in self.engine.station.genArchiveRecords(last_timestamp):
            
            if timestamp==stn_record['dateTime']:
            
                for obs_type in sorted(accum_record.keys()):
                    print "%10s, %10s, %10s" % (obs_type, accum_record[obs_type], stn_record.get(obs_type, 'N/A'))

                accum_set = set(accum_record.keys())
                stn_set   = set(stn_record.keys())
                
                missing = stn_set - accum_set
                print "Missing keys:", missing
        
#===============================================================================
#                    Class StdRESTful
#===============================================================================

class StdRESTful(StdService):
    """Launches a thread that will monitor a queue of new data, which is to be
    posted to RESTful websites. Then, put new data in the queue. """

    def __init__(self, engine, config_dict):
        super(StdRESTful, self).__init__(engine, config_dict)

        obj_list = []

        # Each subsection in section [StdRESTful] represents a different upload
        # site:
        for site in config_dict['StdRESTful'].sections:

            # Get the site dictionary:
            site_dict = self.getSiteDict(config_dict, site)

            try:
                # Instantiate an instance of the class that implements the
                # protocol used by this site. It will throw an exception if not
                # enough information is available to instantiate.
                obj_class = 'weewx.restful.' + site_dict['protocol']
                obj = weeutil.weeutil._get_object(obj_class, site, **site_dict)
            except KeyError, e:
                syslog.syslog(syslog.LOG_DEBUG, "wxengine: Data will not be posted to %s" % (site,))
                syslog.syslog(syslog.LOG_DEBUG, "    ****  %s" % e)
            else:
                obj_list.append(obj)
                syslog.syslog(syslog.LOG_DEBUG, "wxengine: Data will be posted to %s" % (site,))
        
        # Were there any valid upload sites?
        if len(obj_list) > 0 :
            # Yes. Proceed by setting up the queue and thread.
            
            # Create an instance of weewx.archive.Archive
            archiveFilename = os.path.join(config_dict['Station']['WEEWX_ROOT'], 
                                           config_dict['StdArchive']['archive_file'])
            # Create the queue into which we'll put the timestamps of new data
            self.queue = Queue.Queue()
            # Start up the thread:
            self.thread = weewx.restful.RESTThread(archiveFilename, self.queue, obj_list)
            self.thread.start()
            syslog.syslog(syslog.LOG_DEBUG, "wxengine: Started thread for RESTful upload sites.")
        
        else:
            self.queue  = None
            self.thread = None
            syslog.syslog(syslog.LOG_DEBUG, "wxengine: No RESTful upload sites. No need to start thread.")
            
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        
    def new_archive_record(self, event):
        """Post the new archive data to the WU queue"""
        if self.queue:
            self.queue.put(event.record['dateTime'])

    def shutDown(self):
        """Shut down the RESTful thread"""
        # Make sure we have initialized:
        if self.queue:
            # Put a None in the queue. This will signal to the thread to shutdown
            self.queue.put(None)
            # Wait up to 20 seconds for the thread to exit:
            self.thread.join(20.0)
            if self.thread.isAlive():
                syslog.syslog(syslog.LOG_ERR, "wxengine: Unable to shut down StdRESTful thread")
            else:
                syslog.syslog(syslog.LOG_DEBUG, "wxengine: Shut down StdRESTful thread.")
            
    def getSiteDict(self, config_dict, site):
        """Return the site dictionary for the given site.
        
        This function can be overridden by subclassing if you need something
        extra in the site dictionary.
        """
        # Get the dictionary for this site out of the config dictionary:
        site_dict = config_dict['StdRESTful'][site]
        # Some protocols require extra entries:
        site_dict['latitude']  = config_dict['Station']['latitude']
        site_dict['longitude'] = config_dict['Station']['longitude']
        # If a hardware type has not been specified, then provide a default:
        # TODO: Can now get this directly from the hardware
        if not site_dict.has_key('hardware'):
            site_dict['hardware'] = config_dict['Station']['station_type']
        return site_dict
    
    
#===============================================================================
#                    Class StdReport
#===============================================================================

class StdReport(StdService):
    """Launches a separate thread to do reporting."""
    
    def __init__(self, engine, config_dict):
        super(StdReport, self).__init__(engine, config_dict)
        self.thread = None
        self.first_run = True
        
        self.bind(weewx.POST_LOOP, self.launch_report_thread)
        
    def launch_report_thread(self, event):
        """Called after the packet LOOP. Processes any new data."""
        # Now process the data, using a separate thread
        self.thread = weewx.reportengine.StdReportEngine(self.engine.config_path,
                                                         self.engine.stn_info,
                                                         first_run=self.first_run) 
        self.thread.start()
        self.first_run = False

    def shutDown(self):
        if self.thread:
            self.thread.join(20.0)
            if self.thread.isAlive():
                syslog.syslog(syslog.LOG_ERR, "wxengine: Unable to shut down StdReport thread")
            else:
                syslog.syslog(syslog.LOG_DEBUG, "wxengine: Shut down StdReport thread.")
                self.thread = None
        self.first_run = True

#===============================================================================
#                       function parseArgs()
#===============================================================================

def parseArgs():
    """Parse any command line options."""

    parser = OptionParser(usage=usagestr)
    parser.add_option("-d", "--daemon",  action="store_true", dest="daemon",  help="Run as a daemon")
    parser.add_option("-p", "--pidfile", type="string",       dest="pidfile", help="Path to process ID file", default="/var/run/weewx.pid")     
    parser.add_option("-v", "--version", action="store_true", dest="version", help="Give version number then exit")
    parser.add_option("-x", "--exit",    action="store_true", dest="exit"   , help="Exit on I/O error (rather than restart)")
    (options, args) = parser.parse_args()
    
    if options.version:
        print weewx.__version__
        sys.exit()
        
    if len(args) < 1:
        sys.stderr.write("Missing argument(s).\n")
        sys.stderr.write(parser.parse_args(["--help"]))
        sys.exit(weewx.CMD_ERROR)
    
    if options.daemon:
        daemon.daemonize(pidfile=options.pidfile)

    return (options, args)

#===============================================================================
#                       Signal handler
#===============================================================================

class Restart(Exception):
    """Exception thrown when restarting the engine is desired."""
    
def sigHUPhandler(dummy_signum, dummy_frame):
    syslog.syslog(syslog.LOG_DEBUG, "wxengine: Received signal HUP. Throwing Restart exception.")
    raise Restart

#===============================================================================
#                    Function main
#===============================================================================

def main(EngineClass=StdEngine) :
    """Prepare the main loop and run it. 

    Mostly consists of a bunch of high-level preparatory calls, protected
    by try blocks in the case of an exception."""

    # Save the current working directory. A service might
    # change it. In case of a restart, we need to change it back.
    cwd = os.getcwd()

    # Get the command line options and arguments:
    (options, args) = parseArgs()
    
    while True:

        try:
    
            os.chdir(cwd)
            # Create and initialize the engine
            engine = EngineClass(options, args)
            # Set up the reload signal handler:
            signal.signal(signal.SIGHUP, sigHUPhandler)
            # Run the main event loop:
            engine.run()
    
        # Catch any recoverable weewx I/O errors:
        except weewx.WeeWxIOError, e:
            # Caught an I/O error. Log it, wait 60 seconds, then try again
            syslog.syslog(syslog.LOG_CRIT, "wxengine: Caught WeeWxIOError: %s" % e)
            if options.exit :
                syslog.syslog(syslog.LOG_CRIT, "    ****  Exiting...")
                sys.exit(weewx.IO_ERROR)
            syslog.syslog(syslog.LOG_CRIT, "    ****  Waiting 60 seconds then retrying...")
            time.sleep(60)
            syslog.syslog(syslog.LOG_NOTICE, "wxengine: retrying...")
            
        except OSError, e:
            # Caught an OS error. Log it, wait 10 seconds, then try again
            syslog.syslog(syslog.LOG_CRIT, "wxengine: Caught OSError: %s" % e)
            syslog.syslog(syslog.LOG_CRIT, "    ****  Waiting 10 seconds then retrying...")
            time.sleep(10)
            syslog.syslog(syslog.LOG_NOTICE,"wxengine: retrying...")
    
        except Restart:
            syslog.syslog(syslog.LOG_NOTICE, "wxengine: Received signal HUP. Restarting.")
            
        # If run from the command line, catch any keyboard interrupts and log them:
        except KeyboardInterrupt:
            syslog.syslog(syslog.LOG_CRIT,"wxengine: Keyboard interrupt.")
            # Reraise the exception (this will eventually cause the program to exit)
            raise
    
        # Catch any non-recoverable errors. Log them, exit
        except Exception, ex:
            # Caught unrecoverable error. Log it, exit
            syslog.syslog(syslog.LOG_CRIT, "wxengine: Caught unrecoverable exception in wxengine:")
            syslog.syslog(syslog.LOG_CRIT, "    ****  %s" % ex)
            # Include a stack traceback in the log:
            weeutil.weeutil.log_traceback("    ****  ")
            syslog.syslog(syslog.LOG_CRIT, "    ****  Exiting.")
            # Reraise the exception (this will eventually cause the program to exit)
            raise
