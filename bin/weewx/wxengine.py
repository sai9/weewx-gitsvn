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
import weeutil.daemon

# weewx imports:
import weewx.archive
import weewx.stats
import weewx.restful
import weewx.reportengine
import weeutil.weeutil

usagestr = """
  %prog config_path [--help] [--daemon] [--version] [--exit]

  Entry point to the weewx weather program. Can be run from the command
  line or, by specifying the '--daemon' option, as a daemon.

Arguments:
    config_path: Path to the weewx configuration file to be used.
"""

#===============================================================================
#                    Class StdEngine
#===============================================================================

class StdEngine(object):
    """The main engine responsible for the creating and dispatching of events
    from the weather station.
    
    This engine manages a list of 'services.' At key events, each service is
    given a chance to participate.
    """
    
    def __init__(self, options, args):
        """Initialize an instance of StdEngine.
        
        options: An object containing values for all options, as returned
        by optparse
        
        args: The command line arguments, as returned by optparse.
        """
        config_dict = self.getConfiguration(options, args)
        
        # Set a default socket time out, in case FTP or HTTP hang:
        timeout = int(config_dict.get('socket_timeout', 20))
        socket.setdefaulttimeout(timeout)

        syslog.openlog('weewx', syslog.LOG_PID|syslog.LOG_CONS)
        # Look for the debug flag. If set, ask for extra logging
        weewx.debug = int(config_dict.get('debug', 0))
        if weewx.debug:
            syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_DEBUG))
        else:
            syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_INFO))

        syslog.syslog(syslog.LOG_INFO, "wxengine: Starting up weewx version %s." % weewx.__version__)

        # Set up the callback dictionary:
        self.callbacks = dict()
        
        # Set up the services to be run:
        self.setupServices(config_dict)
        
    def getConfiguration(self, options, args):

        # Get and set the absolute path of the configuration file.  
        # A service might to a chdir(), and then another service would be unable to
        # find it.
        self.config_path = os.path.abspath(args[0])
        # Try to open up the given configuration file. Declare an error if
        # unable to.
        try :
            config_dict = configobj.ConfigObj(self.config_path, file_error=True)
        except IOError:
            sys.stderr.write("Unable to open configuration file %s" % args[0])
            syslog.syslog(syslog.LOG_CRIT, "wxengine: Unable to open configuration file %s" % args[0])
            # Reraise the exception (this will eventually cause the program to
            # exit)
            raise
        except configobj.ConfigObjError:
            syslog.syslog(syslog.LOG_CRIT, "wxengine: Error while parsing configuration file %s" % args[0])
            raise

        syslog.syslog(syslog.LOG_INFO, "wxengine: Using configuration file %s." % self.config_path)
        
        return config_dict
    
    def setupServices(self, config_dict):
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

    def setLoopFunction(self, fn):
        """Set the main loop generator function. This loop will be called to generate
        LOOP packets""" 
        self.genLoopPackets = fn

    def run(self):
        """Main execution entry point. The main loop is executed here."""
        
        # Start the main loop. Wrap it in a try block so we can do an orderly
        # shutdown should an exception occur:
        try:
            # Send out a STARTUP event:
            self.dispatchEvent(weewx.Event(weewx.STARTUP))
            
            syslog.syslog(syslog.LOG_INFO, "wxengine: Starting main packet loop.")

            # This is the main loop. 
            while True:
                # First, let any interested services know the packet LOOP is about to start
                self.dispatchEvent(weewx.Event(weewx.PRE_LOOP))
    
                # Run the packet loop. It will break when an archive record is due.
                for packet in self.genLoopPackets():
                    # Package the packet as an event, then dispatch it.            
                    event = weewx.Event(weewx.NEW_LOOP_PACKET, packet=packet)
                    self.dispatchEvent(event)
                
                # Send out an event saying the packet LOOP is done and that the archive record is due:
                self.dispatchEvent(weewx.Event(weewx.END_LOOP))

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
#                    Class StdStation
#===============================================================================

class StdStation(StdService):
    """Holds a reference to the actual weather station hardware."""
    
    def __init__(self, engine, config_dict):
        """Set up the weather station hardware."""
        super(StdStation, self).__init__(engine, config_dict)
        # Get the hardware type from the configuration dictionary.
        # This will be a string such as "VantagePro"
        stationType = config_dict['Station']['station_type']
    
        # Look for and load the module of that name:
        _moduleName = "weewx." + stationType
        __import__(_moduleName)
    
        try:
            # Now open up the weather station:
            self.station = weeutil.weeutil._get_object(_moduleName + '.' + stationType, 
                                                       **config_dict[stationType])
        except Exception, ex:
            # Caught unrecoverable error. Log it:
            syslog.syslog(syslog.LOG_CRIT, "wxengine: Unable to open WX station hardware: %s" % ex)
            # Reraise the exception:
            raise

        # TODO: archive_interval and archive_delay should probably be moved in weewx.conf
        try:        
            self.archive_interval = self.station.archive_interval
        except AttributeError:
            self.archive_interval = int(config_dict[stationType]['archive_interval'])
        self.archive_delay = int(config_dict[stationType]['archive_delay'])

        self.engine.setLoopFunction(self.genLoopPackets)
        
        self.bind(weewx.PRE_LOOP,        self.pre_loop)
        self.bind(weewx.CATCHUP_ARCHIVE, self.catchup_archive)
        self.bind(weewx.SET_TIME,        self.set_time)
        
    def genLoopPackets(self):
        """Main packet LOOP."""
        for packet in self.station.genLoopPackets():
            yield packet
            if time.time() >= self.nextArchive_ts:
                return

    def pre_loop(self, event):
        """Called on a PRE_LOOP event. Calculates when the next archive record is due."""

        self.nextArchive_ts = (int(time.time() / self.archive_interval) + 1) *\
                            self.archive_interval + self.archive_delay
                            
    def catchup_archive(self, event):
        """Called on a CATCHUP_ARCHIVE event. Adds all archive records stored in the console, 
        but not yet in the database."""
        for record in self.station.genArchivePackets(event.timestamp):
            self.engine.dispatchEvent(weewx.Event(weewx.NEW_ARCHIVE_RECORD, record=record))

    def set_time(self, event):
        self.station.setTime(event.clock_time, event.max_drift)
        
    def shutDown(self):
        """Shut down the weather station. Closes the port."""
        try:
            self.station.closePort()
        except:
            pass
        
#===============================================================================
#                    Class StdCalibrate
#===============================================================================

class StdCalibrate(StdService):
    """Adjust data using calibration expressions.
    
    This service must be run before StdArchive, so the correction is applied
    before the data is archived."""
    
    def __init__(self, engine, config_dict):
        super(StdCalibrate, self).__init__(engine, config_dict)
        
        self.corrections = {}
        # Get the list of calibration corrections to apply. If a section
        # is missing, a KeyError exception will get thrown:
        try:
            correction_dict = config_dict['Calibrate']['Corrections']
        except KeyError:
            return
        
        # For each correction, compile it, then save in a dictionary of
        # corrections to be applied:
        for obs_type in correction_dict.scalars:
            self.corrections[obs_type] = compile(correction_dict[obs_type], 
                                                 'StdCalibrate', 'eval')
        
        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        
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

        self.min_max_dict = {}
        # Nothing to do if the 'QC' section does not exist in the configuration
        # dictionary.
        if config_dict.has_key('QC'):
            min_max_dict = config_dict['QC']['MinMax']
    
            for obs_type in min_max_dict.scalars:
                self.min_max_dict[obs_type] = (float(min_max_dict[obs_type][0]),
                                               float(min_max_dict[obs_type][1]))
            
        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        
    def new_loop_packet(self, event):
        """Apply quality check to the data in a LOOP packet"""
        for obs_type in self.min_max_dict:
            if event.packet.has_key(obs_type) and event.packet[obs_type] is not None:
                if not self.min_max_dict[obs_type][0] <= event.packet[obs_type] <= self.min_max_dict[obs_type][1]:
                    event.packet[obs_type] = None

    def new_archive_record(self, event):
        """Apply quality check to the data in a LOOP packet"""
        for obs_type in self.min_max_dict:
            if event.record.has_key(obs_type) and event.record[obs_type] is not None:
                if not self.min_max_dict[obs_type][0] <= event.record[obs_type] <= self.min_max_dict[obs_type][1]:
                    event.record[obs_type] = None

#===============================================================================
#                    Class StdArchive
#===============================================================================

class StdArchive(StdService):
    """Service that archives LOOP and archive data in the SQL databases."""
    
    def __init__(self, engine, config_dict):
        super(StdArchive, self).__init__(engine, config_dict)

        self.setupArchiveDatabase(config_dict)
        self.setupStatsDatabase(config_dict)
        
        self.bind(weewx.STARTUP,            self.startup)
        self.bind(weewx.END_LOOP,           self.end_loop)
        self.bind(weewx.NEW_LOOP_PACKET,    self.new_loop_packet)
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
    
    def startup(self, event):
        """Called when the engine is starting up."""
        # The engine is starting up. The main task is to do a catch
        # up on any data still on the station, but not yet put in the
        # database. Get the last timestamp in the archive:
        lastgood_ts = self.archive.lastGoodStamp()
        catchup_event=weewx.Event(weewx.CATCHUP_ARCHIVE, timestamp=lastgood_ts)
        self.engine.dispatchEvent(catchup_event)
        
    def end_loop(self, event):
        """Called after the packet LOOP is done and a new archive record is due.
        Issues a CATCHUP_ARCHIVE event."""
        # (Clear accumulators; emit new archive record)
        lastgood_ts = self.archive.lastGoodStamp()
        # Request a catchup
        catchup_event=weewx.Event(weewx.CATCHUP_ARCHIVE, timestamp=lastgood_ts)
        self.engine.dispatchEvent(catchup_event)
        
    def new_loop_packet(self, event):
        """Called when A new LOOP record has arrived. Put it in the stats database."""
        self.statsDb.addLoopRecord(event.packet)
        
    def new_archive_record(self, event):
        """Called when a new archive record has arrived. 
        Put it in the stats and archive database."""
        self.archive.addRecord(event.record)
        self.statsDb.addArchiveRecord(event.record)

    def setupArchiveDatabase(self, config_dict):
        """Setup the main database archive"""
        archiveFilename = os.path.join(config_dict['Station']['WEEWX_ROOT'], 
                                       config_dict['Archive']['archive_file'])
        # Try to open up the database. If it doesn't exist or has not been initialized, an exception
        # will be thrown. Catch it, configure the database, and then try again.
        try:
            self.archive = weewx.archive.Archive(archiveFilename)
        except StandardError:
            weewx.archive.config(archiveFilename)
            self.archive = weewx.archive.Archive(archiveFilename)

    def setupStatsDatabase(self, config_dict):
        """Setup the stats database"""
        statsFilename = os.path.join(config_dict['Station']['WEEWX_ROOT'], 
                                     config_dict['Stats']['stats_file'])
        # Try to open up the database. If it doesn't exist or has not been initialized, an exception
        # will be thrown. Catch it, configure the database, and then try again.
        try:
            self.statsDb = weewx.stats.StatsDb(statsFilename,
                                               int(config_dict['Station'].get('cache_loop_data', '1')))
        except StandardError:
            # It's uninitialized. Configure it:
            weewx.stats.config(statsFilename, config_dict['Stats'].get('stats_types'))
            # Try again to open it up:
            self.statsDb = weewx.stats.StatsDb(statsFilename,
                                               int(config_dict['Station'].get('cache_loop_data', '1')))

        # Backfill it with data from the archive. This will do nothing if 
        # the stats database is already up-to-date.
        weewx.stats.backfill(self.archive, self.statsDb)
        
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
        # Synch up the station's clock if it's been more than 
        # clock_check seconds since the last check:
        now_ts = time.time()
        if now_ts - self.last_synch_ts >= self.clock_check:
            settime_event = weewx.Event(weewx.SET_TIME, clock_time=now_ts, max_drift=self.max_drift)
            self.engine.dispatchEvent(settime_event)
            self.last_synch_ts = now_ts
            
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
        """Print out a summary of the new LOOP packet"""
        print "LOOP:  ", weeutil.weeutil.timestamp_to_string(event.packet['dateTime']),\
                         event.packet['barometer'],\
                         event.packet['outTemp'],\
                         event.packet['windSpeed'],\
                         event.packet['windDir']
    
    def new_archive_record(self, event):
        """Print out a summary of the new archive record."""
        print "REC:-> ", weeutil.weeutil.timestamp_to_string(event.record['dateTime']),\
                        event.record['barometer'],\
                        event.record['outTemp'],\
                        event.record['windSpeed'],\
                        event.record['windDir'], " <-"

#===============================================================================
#                    Class StdRESTful
#===============================================================================

class StdRESTful(StdService):
    """Launches a thread that will monitor a queue of new data, which is to be
    posted to RESTful websites. Then, put new data in the queue. """

    def __init__(self, engine, config_dict):
        super(StdRESTful, self).__init__(engine, config_dict)

        station_list = []

        # Each subsection in section [RESTful] represents a different upload
        # site:
        for site in config_dict['RESTful'].sections:

            # Get the site dictionary:
            site_dict = self.getSiteDict(config_dict, site)

            try:
                # Instantiate an instance of the class that implements the
                # protocol used by this site. It will throw an exception if not
                # enough information is available to instantiate.
                obj_class = 'weewx.restful.' + site_dict['protocol']
                new_station = weeutil.weeutil._get_object(obj_class, site, **site_dict)
            except KeyError:
                syslog.syslog(syslog.LOG_DEBUG, "wxengine: Data will not be posted to %s" % (site,))
            else:
                station_list.append(new_station)
                syslog.syslog(syslog.LOG_DEBUG, "wxengine: Data will be posted to %s" % (site,))
        
        # Were there any valid upload sites?
        if len(station_list) > 0 :
            # Yes. Proceed by setting up the queue and thread.
            
            # Create an instance of weewx.archive.Archive
            archiveFilename = os.path.join(config_dict['Station']['WEEWX_ROOT'], 
                                           config_dict['Archive']['archive_file'])
            archive = weewx.archive.Archive(archiveFilename)
            # Create the queue into which we'll put the timestamps of new data
            self.queue = Queue.Queue()
            # Start up the thread:
            self.thread = weewx.restful.RESTThread(archive, self.queue, station_list)
            self.thread.start()
            syslog.syslog(syslog.LOG_DEBUG, "wxengine: Started thread for RESTful upload sites.")
        
        else:
            self.queue  = None
            self.thread = None
            syslog.syslog(syslog.LOG_DEBUG, "wxengine: No RESTful upload sites. Thread not started.")
            
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
            syslog.syslog(syslog.LOG_DEBUG, "Shut down RESTful thread.")
            
    def getSiteDict(self, config_dict, site):
        """Return the site dictionary for the given site.
        
        This function can be overridden by subclassing if you need something
        extra in the site dictionary.
        """
        # Get the dictionary for this site out of the config dictionary:
        site_dict = config_dict['RESTful'][site]
        # Some protocols require extra entries:
        site_dict['latitude']  = config_dict['Station']['latitude']
        site_dict['longitude'] = config_dict['Station']['longitude']
        site_dict['hardware']  = config_dict['Station']['station_type']
        return site_dict
    
    
#===============================================================================
#                    Class StdReportService
#===============================================================================

class StdReportService(StdService):
    """Launches a separate thread to do reporting."""
    
    def __init__(self, engine, config_dict):
        super(StdReportService, self).__init__(engine, config_dict)
        self.thread = None
        self.first_run = True
        
        self.bind(weewx.END_LOOP, self.end_loop)
        
    def end_loop(self, event):
        """Called after the packet LOOP. Processes any new data."""
        # Now process the data, using a separate thread
        self.thread = weewx.reportengine.StdReportEngine(self.engine.config_path,
                                                         first_run=self.first_run) 
        self.thread.start()
        self.first_run = False

    def shutDown(self):
        if self.thread:
            self.thread.join(20.0)
            syslog.syslog(syslog.LOG_DEBUG, "Shut down StdReportService thread.")
        self.first_run = True

#===============================================================================
#                       function parseArgs()
#===============================================================================

def parseArgs():
    """Parse any command line options."""

    parser = OptionParser(usage=usagestr)
    parser.add_option("-d", "--daemon",  action="store_true", dest="daemon",  help="Run as a daemon")
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
        weeutil.daemon.daemonize(pidfile='/var/run/weewx.pid')

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
