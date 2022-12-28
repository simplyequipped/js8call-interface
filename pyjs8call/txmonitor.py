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

'''Monitor JS8Call tx text for queued outgoing messages.

Directed messages are monitored by default (see pyjs8call.client.Client.monitor_directed_tx).
'''

__docformat__ = 'google'


import time
import threading

import pyjs8call
from pyjs8call import Message


class TxMonitor:
    '''Monitor JS8Call tx text for queued outgoing messages.
    
    Monitored messages can have the the following status:
    - STATUS_QUEUED
    - STATUS_SENDING
    - STATUS_SENT
    - STATUS_FAILED

    A message changes to STATUS_QUEUED when monitoring begins.

    A message changes to STATUS_SENDING when the destination and value are seen in the JS8Call tx text field and the status of the message is STATUS_QUEUED.

    A message changes to STATUS_SENT when the destination and value are no longer seen in the JS8Call tx text field and the status of the message is STATUS_SENDING.

    A message changes to STATUS_FAILED when the message is not sent within 30 tx cycles. Therefore the maximum age of a monitored message depends on the JS8Call modem speed setting:
    - 3 minutes in turbo mode which has 6 second tx cycles
    - 5 minutes in fast mode which has 10 second tx cycles
    - 7.5 minutes in normal mode which has 15 second cycles
    - 15 minutes in slow mode which has 30 second tx cycles

    A message is dropped from the monitoring queue once the status is set to STATUS_SENT or STATUS_FAILED.
    '''

    def __init__(self, client):
        '''Initialize tx monitor.

        Args:
            client (pyjs8call.client): Parent client object

        Returns:
            pyjs8call.txmonitor: Constructed tx monitor object
        '''
        self._client = client
        self._msg_queue = []
        self._msg_queue_lock = threading.Lock()
        # initialize msg max age to 30 tx cycles in fast mode (10 sec cycles)
        self._msg_max_age = 10 * 30 # 5 minutes
        self._status_change_callback = None

        monitor_thread = threading.Thread(target=self._monitor)
        monitor_thread.setDaemon(True)
        monitor_thread.start()

    def set_status_change_callback(self, callback):
        '''Set callback for monitored message status change.
    
        Callback function signature: func(msg) where msg is the monitored pyjs8call.message object.

        Args:
            callback (func): Function to call when the status of a monitored message changes
        '''
        self._status_change_callback = callback

    def monitor(self, msg):
        '''Monitor a new message.

        The message status is set to STATUS_QUEUED (see pyjs8call.message) when monitoring begins.

        Args:
            msg (pyjs8call.message): Message to look for in the JS8Call tx text field
        '''
        msg.status = Message.STATUS_QUEUED

        self._msg_queue_lock.acquire()
        self._msg_queue.append(msg)
        self._msg_queue_lock.release()

    def _monitor(self):
        '''Tx monitor thread.'''
        while self._client.online:
            time.sleep(1)
            tx_text = self._client.get_tx_text()

            # no text in tx field, nothing to process
            if tx_text == None:
                continue

            # when a msg is the tx text, drop the first callsign and strip spaces and end-of-message
            # original format: 'callsign: callsign  message'
            if ':' in tx_text:
                tx_text = tx_text.split(':')[1].strip(' ' + Message.EOM)
            
            # update msg max age based on speed setting (30 tx cycles)
            #    3 min in turbo mode (6 sec cycles)
            #    5 min in fast mode (10 sec cycles)
            #    7.5 min in normal mode (15 sec cycles)
            #    15 min in slow mode (30 sec cycles)
            tx_window = self._client.get_tx_window_duration()
            self._msg_max_age = tx_window * 30
            
            self._msg_queue_lock.acquire()

            # process msg queue
            for i in range(len(self._msg_queue)):
                msg = self._msg_queue.pop(0)
                msg_value = msg.destination + '  ' + msg.value.strip()
                drop = False

                if msg_value == tx_text and msg.status == Message.STATUS_QUEUED:
                    # msg text was added to js8call tx field, sending
                    msg.status = Message.STATUS_SENDING

                    if self._status_change_callback != None:
                        self._status_change_callback(msg)
                        
                elif msg_value != tx_text and msg.status == Message.STATUS_SENDING:
                    # msg text was removed from js8call tx field, sent
                    msg.status = Message.STATUS_SENT

                    if self._status_change_callback != None:
                        self._status_change_callback(msg)
                        
                    drop = True
                       
                elif time.time() > msg.timestamp + self._msg_max_age:
                    # msg sending failed
                    msg.status = Message.STATUS_FAILED

                    if self._status_change_callback != None:
                        self._status_change_callback(msg)
                        
                    drop = True

                if not drop:
                    self._msg_queue.append(msg)
                        
            self._msg_queue_lock.release()
           
