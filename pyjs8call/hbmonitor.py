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

'''Monitor heartbeat messaging.'''

__docformat__ = 'google'


import time
import threading


class HeartbeatMonitor:
    '''Monitor heartbeat messaging.

    Send heaertbeat messages automatically on a timed interval.
    '''
    def __init__(self, client):
        '''Initialize heartbeat monitor object.

        Args:
            client (pyjs8call.client): Parent client object

        Returns:
            pyjs8call.hbmonitor: Constructed heartbeat object
        '''
        self._client = client
        self._enabled = False
        self._paused = False

    def enable(self, interval=10):
        '''Enable heartbeat monitoring.

        Args:
            interval (int): Number of minutes between outgoing messages, defaults to 10
        '''
        if self._enabled:
            return

        self._enabled = True

        thread = threading.Thread(target=self._monitor, args=(interval,))
        thread.daemon = True
        thread.start()

    def disable(self):
        '''Disable heartbeat monitoring.'''
        self._enabled = False

    def pause(self):
        '''Pause heartbeat monitoring.'''
        self._paused = True

    def resume(self):
        '''Resume heartbeat monitoring.'''
        self._paused = False

    def _monitor(self, interval):
        '''Heartbeat monitor thread.'''
        interval *= 60
        last_hb_timestamp = time.time()

        while self._enabled:
            while last_hb_timestamp + interval > time.time():
                time.sleep(1)

                # allow disable while waiting
                if not self._enabled:
                    return

            if not self.paused:
                self._client.send_heartbeat()
                last_hb_timestamp = time.time()

