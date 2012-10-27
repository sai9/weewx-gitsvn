#
#    Copyright (c) 2012 Tom Keffer <tkeffer@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#
#    $Revision$
#    $Author$
#    $Date$
#
"""Console simulator for the weewx weather system"""

import math
import time

import weeutil.weeutil
import weewx.abstractstation

def loader(config_dict):

    if config_dict['Simulator'].has_key('start'):
        start_tt = time.strptime(config_dict['Simulator']['start'], "%Y-%m-%d %H:%M")
        start_ts = time.mktime(start_tt)
    else:
        start_ts = None
    station = Simulator(start_ts=start_ts, **config_dict['Simulator'])
    
    return station
        
class Simulator(weewx.abstractstation.AbstractStation):
    """Station simulator"""
    
    def __init__(self, **stn_dict):
        """Initialize the simulator
        
        NAMED ARGUMENTS:
        
        loop_interval: The time (in seconds) between emitting LOOP packets. [Optional. Default is 2.5]
        
        start_ts: The start time in unix epoch time [Optional. Default is to use the present time.]

        mode: Required. One of either:
            'simulator': Real-time simulator. It will sleep between emitting LOOP packets.
            'generator': Emit packets as fast as it can (useful for testing).
        """

        self.loop_interval = float(stn_dict.get('loop_interval', 2.5))
        self.start_ts      = float(stn_dict.get('start_ts', time.time()))
        self.mode          = stn_dict['mode']
        self.the_time      = self.start_ts if self.start_ts else time.time()
        
        sod = weeutil.weeutil.startOfDay(self.the_time)
                
        self.observations = {'outTemp'   : Observation(magnitude=20.0, average=50.0, period=24.0, phase_lag=14.0, start=sod),
                             'inTemp'    : Observation(magnitude=5.0,  average=68.0, period=24.0, phase_lag=12.0, start=sod),
                             'barometer' : Observation(magnitude=1.0,  average=30.1, period=96.0, phase_lag=48.0, start=sod)}

    def genLoopPackets(self):

        while True:

            # If we are in simulator mode, sleep first (as if we are gathering
            # observations). If we are in generator mode, don't sleep at all.
            if self.mode == 'simulator':
                # Determine how long to sleep
                if self.start_ts:
                    # A start time was specified, so we are not in realtime. Just sleep
                    # the appropriate interval
                    time.sleep(self.loop_interval)
                else:
                    # No start time was specified, so we are in real time. Try to keep
                    # synched up with the wall clock
                    time.sleep(self.the_time + self.loop_interval - time.time())

            # Update the simulator clock:
            self.the_time += self.loop_interval
            
            # Because a packet represents the measurements observed over the
            # time interval, we want the measurement values at the middle
            # of the interval.
            avg_time = self.the_time - self.loop_interval/2.0
            
            _packet = {'dateTime': int(self.the_time+0.5),
                       'usUnits' : weewx.US }
            for obs_type in self.observations:
                _packet[obs_type] = self.observations[obs_type].value_at(avg_time)

            yield _packet

                
    def genArchiveRecords(self, lastgood_ts):
        # What this will do is bring the simulator in synch with the last good
        # time in the database. The result is that it will resume starting at
        # that time.
        if lastgood_ts:
            self.the_time = lastgood_ts
        # However, it does not actually emit any records, so we still have
        # to signal that there is no implementation.
        raise NotImplementedError
    
    def getTime(self):
        return self.the_time
    
    def setTime(self, newtime_ts):
        # If the Simulator is not running in real time, you don't want to
        # change the time.
        if self.start_ts is None:
            self.the_time = newtime_ts
        
    @property
    def hardware_name(self):
        return "Simulator"
        
class Observation(object):
    
    def __init__(self, magnitude=1.0, average=0.0, period=96.0, phase_lag=0.0, start=None):
        """Initialize an observation function.
        
        magnitude: The value at max. The range will be twice this value
        average: The average value, averaged over a full cycle.
        period: The cycle period in hours.
        phase_lag: The number of hours after the start time when the observation hits its max
        start: Time zero for the observation in unix epoch time."""
         
        if not start:
            raise ValueError("No start time specified")
        self.magnitude = magnitude
        self.average   = average
        self.period    = period * 3660.0
        self.phase_lag = phase_lag * 3660.0
        self.start     = start
        
    def value_at(self, time_ts):
        """Return the observation value at the given time.
        
        time_ts: The time in unix epoch time."""

        phase = 2.0 * math.pi * (time_ts - self.start - self.phase_lag) / self.period
        return self.magnitude * math.cos(phase) + self.average
        



if __name__ == "__main__":

    station = Simulator(mode='simulator',loop_interval=2.0)
    for packet in station.genLoopPackets():
        print weeutil.weeutil.timestamp_to_string(packet['dateTime']), packet
        
    