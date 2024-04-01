# MIT License
# 
# Copyright (c) 2022-2023 Simply Equipped
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

'''Monitor recent station spots.

Add callback using `client.callback.register_spots()` to receive all new activity.

Add callback using `client.callback.register_station_spot()` to receive new activity for a specific station.

Add callback using `client.callback.register_group_spot()` to receive new activity for a specific group.

See pyjs8call.client.Callbacks for callback function details.

'''

__docformat__ = 'google'


import threading
import time


class SpotMonitor:
    '''Monitor recent station spots.'''

    def __init__(self, client):
        '''Initialize spot monitor.

        Args:
            client (pyjs8call.client): Parent client object

        Returns:
            pyjs8call.spotmonitor: Constructed spot monitor object
        '''
        self._client = client
        self._enabled = False
        self._paused = False
        self._station_watch_list = []
        self._group_watch_list = []

    def enabled(self):
        '''Get enabled status.

        Returns:
            bool: True if enabled, False if disabled
        '''
        return self._enabled

    def paused(self):
        '''Get paused status.

        Returns:
            bool: True if paused, False if running
        '''
        return self._paused

    def enable(self):
        '''Enable spot monitoring.'''
        if self._enabled:
            return

        self._enabled = True

        thread = threading.Thread(target=self._monitor)
        thread.daemon = True
        thread.start()

    def disable(self):
        '''Disable spot monitoring.'''
        self._enabled = False

    def pause(self):
        '''Pause spot monitoring.'''
        self._paused = True

    def resume(self):
        '''Resume spot monitoring.'''
        self._paused = False

    def all(self):
        '''Get all stored spot messages.'''
        return self._client.js8call.get_spots()

    def filter(self, origin=None, destination=None, grid=None, distance=0, age=0, count=0, profile=None, dial_freq=None, band=None):
        '''Get filtered spot messages.

        Spots are *pyjs8call.message* objects. Specified *origin*, *destination*, and *grid* strings are converted to uppercase. *band* strings are converted to lowercase.

        When *distance*, *age*, or *count* are 0 (zero) they are ignored.

        See *pyjs8call.client.freq_to_band* for frequency band information.

        Args:
            origin (str): Message origin callsign to match, defaults to None
            destination (str): Message destination callsign or group designator to match, defaults to None
            grid (str): Message grid square to match, defaults to None
            distance (int): Maximum message grid square distance, defaults to 0 (zero)
            age (int): Maximum message age in seconds, defaults to 0 (zero)
            count (int): Number of most recent spot messages to return, defaults to 0 (zero)
            profile (str): Configuration profile at the time spot was received, defaults to None
            dial_freq (int): Dial frequency in Hz to match, defaults to None
            band (str): Frequency band (ex. \'40m\') to match, defaults to None

        Returns:
            list: Spot messages matching specified filter criteria
        '''
        spots = []
        
        for spot in self.all():
            if (
                (age == 0 or spot.age() <= age) and
                (grid is None or grid.upper() == spot.grid) and
                (distance == 0 or (spot.distance is not None and spot.distance <= distance)) and
                (origin is None or origin.upper() == spot.origin) and 
                (destination is None or destination.upper() == spot.destination) and
                (profile is None or profile == spot.profile) and
                (dial_freq is None or dial_freq == spot.dial) and
                (band is None or band.lower() == self._client.freq_to_band(spot.freq).lower())
            ):
                spots.append(spot)

        if 0 < count < len(spots):
            count *= -1
            spots = spots[count:]

        return spots

    def get_origin_grid(self, origin):
        '''Get grid square for specified origin callsign.

        Args:
            origin (str): Origin callsign to match

        Returns:
            str, None: Most recent grid square spotted for *origin*, or None if not found
        '''
        for spot in self.all():
            if spot.origin == origin.upper() and spot.grid not in (None, ''):
                return spot.grid

        return None

    def last_heard(self, count=1):
        '''Get last heard spot messages.

        Args:
            count (int): Number of spot messages to return

        Returns:
            list: Last *count* spot messages received
        '''
        count *= -1
        return self._client.js8call.get_spots()[count:]

    def add_station_watch(self, station):
        '''Add watched station.

        Args:
            station (str): Station callsign to watch for
        '''
        if station not in self._station_watch_list:
            self._station_watch_list.append(station)

    def add_group_watch(self, group):
        '''Add watched group.

        Args:
            group (str): Group designator to watch for
        '''
        if group[0] != '@':
            raise ValueError('Group designator must begin with \'@\'')

        if group not in self._group_watch_list:
            self._group_watch_list.append(group)

    def remove_station_watch(self, station):
        '''Remove watched station.

        Args:
            station (str): Station callsign to stop watching for
        '''
        if station in self._station_watch_list:
            self._station_watch_list.remove(station)

    def remove_group_watch(self, group):
        '''Remove watched group.

        Args:
            group (str): Group designator to stop watching for
        '''
        if group[0] != '@':
            raise ValueError('Group designator must begin with \'@\'')

        if group in self._group_watch_list:
            self._group_watch_list.remove(group)

    def get_watched_stations(self):
        '''Get watched stations.

        Returns:
            list: Watched station callsigns
        '''
        return self._station_watch_list

    def set_watched_stations(self, stations):
        '''Set watched stations.

        Args:
            stations (list): List of station callsigns to watch for
        '''
        if isinstance(stations, str):
            stations = [station.strip() for station in stations.split(',')]

        self._station_watch_list = stations

    def get_watched_groups(self):
        '''Get watched groups.

        Returns:
            list: Watched group designators
        '''
        return self._group_watch_list

    def set_watched_groups(self, groups):
        '''Set watched groups.

        Args:
            groups (list): List of group designators to watch for
        '''
        if isinstance(groups, str):
            groups = [group.strip() for group in groups.split(',')]

        self._groups_watch_list = groups


    def _callback(self, spots):
        '''New spots callback function handling.

        Calls each callback function in *pyjs8call.client.callback.spots*, *pyjs8call.client.callback.station_spot*, and *pyjs8call.client.callback.group_spot* using *threading.Thread*.

        Args:
            spots (list): Spotted message objects
        '''
        if len(self._client.callback.spots) > 0:
            for callback in self._client.callback.spots:
                thread = threading.Thread(target=callback, args=(spots,))
                thread.daemon = True
                thread.start()

            for spot in spots:
                if (
                    len(self._client.callback.station_spot) > 0 and
                    spot.origin in self._station_watch_list
                ):
                    for callback in self._client.callback.station_spot:
                        thread = threading.Thread(target=callback, args=(spot,))
                        thread.daemon = True
                        thread.start()

                if (
                    len(self._client.callback.group_spot) > 0 and
                    spot.destination in self._group_watch_list
                ):
                    for callback in self._client.callback.group_spot:
                        thread = threading.Thread(target=callback, args=(spot,))
                        thread.daemon = True
                        thread.start()

    def _monitor(self):
        '''Spot monitor thread.

        Uses *filter()* internally.
        '''
        last_spot_update_timestamp = 0

        while self._enabled:
            self._client.window.sleep_until_next_transition()

            if self._paused:
                continue

            # get new spots since last update
            time_since_last_update = time.time() - last_spot_update_timestamp
            new_spots = self.filter(age = time_since_last_update)
            last_spot_update_timestamp = time.time()

            if len(new_spots) > 0:
                self._callback(new_spots)
