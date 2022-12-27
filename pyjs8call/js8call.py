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

'''Manage TCP socket communication and local state associated with the JS8Call application.

This module is initialized by pyjs8call.client.
'''

__docformat__ = 'google'


import time
import json
import socket
import threading
from datetime import datetime, timezone

import pyjs8call
from pyjs8call import Message
from pyjs8call import Spot


class JS8Call:
    '''Low-level JS8Call TCP socket and local state management.

    Receives (constructs) and transmits pyjs8call.message objects, and generally manages the local state representation of the JS8Call application.

    Initializes pyjs8call.appmonitor as well as rx, tx, and application heartbeat threads.

    Attributes:
        connected (bool): Whether the JS8Call TCP socket is connected
        spots (list): List of station spots (see pyjs8call.spot and pyjs8call.client.Client.get_station_spots)
        max_spots (int): Maximum number of spots to store before dropping old spots, defaults to 1000
    '''

    def __init__(self, client, host='127.0.0.1', port=2442, headless=False):
        '''Initialize JS8Call TCP socket and local state.

        Args:
            client (pyjs8call.client): Parent client object
            host (str): JS8Call TCP address setting, defaults to '127.0.0.1'
            port (int): JS8Call TCP port setting, defaults to 2442
            headless (bool): Run JS8Call headless using xvfb (linux only, requires xvfb to be installed)

        Returns:
            pyjs8call.js8call.JS8Call: Constructed js8call object
        '''
        self._client = client
        self._host = host
        self._port = port
        self._rx_queue = []
        self._rx_queue_lock = threading.Lock()
        self._tx_queue = []
        self._tx_queue_lock = threading.Lock()
        self._socket = None
        self._watch_timeout = 3 # seconds
        self._watching = None
        self._last_rx_timestamp = 0
        self._socket_heartbeat_delay = 60 * 5 # seconds
        self._app = None
        self._debug = False
        self._debug_all = False
        self._debug_type_blacklist = [Message.TX_GET_TEXT, Message.TX_TEXT]
        self.connected = False
        self.spots = []
        self.max_spots = 1000
        self._recent_spots = []

        self.state = {
            'ptt' : None,
            'dial': None,
            'freq' : None,
            'offset' : None,
            'callsign' : None,
            'speed' : None,
            'grid' : None,
            'info' : None,
            'rx_text' : None,
            'tx_text' : None,
            'inbox': None,
            'call_activity' : None,
            'band_activity' : None,
            'selected_call' : None,
        }

        self.online = True

        # start the application monitor
        self.app_monitor = pyjs8call.AppMonitor(self)
        self.app_monitor.start(headless=headless)
        
        tx_thread = threading.Thread(target=self._tx)
        tx_thread.setDaemon(True)
        tx_thread.start()

        rx_thread = threading.Thread(target=self._rx)
        rx_thread.setDaemon(True)
        rx_thread.start()

        hb_thread = threading.Thread(target=self._hb)
        hb_thread.setDaemon(True)
        hb_thread.start()

    def stop(self):
        '''Stop threads and JS8Call application.'''
        self.online = False
        self.app_monitor.stop()

    def _connect(self):
        '''Connect to the TCP socket of the JS8Call application.'''
        self._socket = socket.socket()
        self._socket.connect((self._host, int(self._port)))
        self._socket.settimeout(1)

    def send(self, msg):
        '''Queue message for transmission to the JS8Call application.

        Sets the status of the message object to *queued* (see pyjs8call.message statuses).

        Args:
            msg (pyjs8call.message): Message object to be transmitted
        '''
        msg.status = Message.STATUS_QUEUED

        self._tx_queue_lock.acquire()
        self._tx_queue.append(msg)
        self._tx_queue_lock.release()
        
    def append_to_rx_queue(self, msg):
        '''Queue received message from the JS8Call application for handling.

        Sets the status of the message object to *queued* (see pyjs8call.message statuses).

        Args:
            msg (pyjs8call.message): Message object to be handled
        '''
        msg.status = Message.STATUS_QUEUED

        self._rx_queue_lock.acquire()
        self._rx_queue.append(msg)
        self._rx_queue_lock.release()

    def get_next_message(self):
        '''Get next received message from the queue.

        Sets the status of the message object to *received* (see pyjs8call.message statuses).

        Returns:
            pyjs8call.message: Message to be handled
        '''
        if len(self._rx_queue) > 0:
            self._rx_queue_lock.acquire()
            msg = self._rx_queue.pop(0)
            self._rx_queue_lock.release()

            msg.status = Message.STATUS_RECEIVED
            return msg

    def watch(self, item):
        '''Watch local state variable for updating based on a response from the JS8Call application.

        The JS8Call application responds to requests asynchronously, which means responses may not be received in the same order as the requests or in a reasonable timeframe following the request. To handle these asynchronous reponses, the responses set local state variables as they are received. The process is as follows:
        - Send a request to the JS8Call application
        - Set local state variable associated with anticipated response to a known value (None)
        - Wait for a response, timing out if a response is not received within 3 seconds
        - Detect a change in the local state variable indicating that a response has been received
        - Return the response (i.e. the current value of the updated local state variable)

        If a timeout occurs while waiting for a response the local state variable is set back to its previous value.

        Args:
            item (str): Name of the local state variable to watch

        Returns:
            The value of the given local state variable
        '''
        if item not in self.state.keys():
            return None

        self._watching = item
        last_state = self.state[item]
        self.state[item] = None
        timeout = time.time() + self._watch_timeout

        while timeout > time.time():
            if self.state[item] != None:
                break
            time.sleep(0.001)

        # timeout occurred, revert to last state
        if self.state[item] == None:
            self.state[item] = last_state
        
        self._watching = None
        return self.state[item]

    def spot(self, msg):
        '''Store a local spot when a station is heard.

        A spot object (see pyjs8call.spot) is constructed and stored. The new spot object is compared against a list of recent spot objects (heard within the last 10 seconds) to prevent duplicate spots from multiple JS8Call API messages associated with the same station event.

        The list of stored spots is culled once it exceeeds the maximum size set by *max_spots* by dropping the oldest spot.

        See pyjs8call.client.Client.get_station_spots to utilize stored spots.

        Args:
            msg (pyjs8call.message): Message to source spot data from
        '''
        # cull recent spots
        self._recent_spots = [spot for spot in self._recent_spots if spot.age() < 10]

        new_spot = Spot(msg)

        if new_spot not in self._recent_spots:
            self._recent_spots.append(new_spot)
            self.spots.append(new_spot)

        # cull spots
        if len(self.spots) > self.max_spots:
            self.spots.pop(0)

    def _hb(self):
        '''JS8Call application heartbeat thread.

        If no messages have been received from the JS8Call in the last 5 minutes, a request is issued to the application to make sure it is still connected and functioning as expected.
        '''
        while self.online:
            # if no recent rx, check the connection by making a request
            timeout = self._last_rx_timestamp + self._socket_heartbeat_delay
            if time.time() > timeout:
                self.connected = False
                msg = Message()
                msg.type = Message.STATION_GET_CALLSIGN
                self.send(msg)
                
            time.sleep(1)

    def _tx(self):
        '''JS8Call application transmit thread.

        The JS8Call tx text field is read every second by pyjs8call.txmonitor. This is utilized to reduce additional socket traffic by reading the local state variable directly without requesting additional updates from the application.

        When processing the transmit message queue, if a transmission is in process (i.e. there is text in the tx text field) then transmission of additional messages is prevented until the current transmission is complete.

        If debugging is enabled (see pyjs8call.client.Client.start) then the byte string of each message sent over the TCP socket is printed to the console. By default not all messages are printed in debug mode (see pyjs8call.js8call.JS8Call._debug_type_blacklist). Frequently sent and received messages used internal to pyjs8call are not printed.
        '''
        tx_text = False
        force_tx_text = False

        while self.online:
            # TxMonitor updates tx_text every second
            # do not attempt to update while value is being watched (i.e. updated)
            if self._watching != 'tx_text' and self.state['tx_text'] != None:
                if len(self.state['tx_text'].strip()) > 0:
                    tx_text = True
                    force_tx_text = False
                else:
                    tx_text = False

            self._tx_queue_lock.acquire()

            for msg in self._tx_queue.copy():

                # hold off on sending messages while there is something being sent (text in the tx text field)
                if msg.type == Message.TX_SEND_MESSAGE and (tx_text or force_tx_text):
                    continue
                else:
                    # pack msg
                    packed = msg.pack()

                    # print packed msg in debug mode
                    if self._debug:
                        if self._debug_all:
                            print('TX: ' + packed.decode('utf-8').strip())
                        elif msg.type not in self._debug_type_blacklist:
                            print('TX: ' + packed.decode('utf-8').strip())

                    # send msg via socket
                    self._socket.sendall(packed)
                    # remove msg from queue
                    self._tx_queue.remove(msg)
                    # make sure the next queued msg doesn't get sent before the tx text state updates
                    if msg.type == Message.TX_SEND_MESSAGE:
                        force_tx_text = True

                    time.sleep(0.1)

            self._tx_queue_lock.release()
            time.sleep(0.1)

    def _rx(self):
        '''JS8Call application receive thread.

        A byte string is read from the TCP socket and parsed into a pyjs8call.message. Socket data is discarded in the following cases:
            - Failure to decode received byte string to UTF-8 (likely due to corrupted or incomplete data)
            - Length of received byte string is zero (no data received)
            - Failure to parse received data into a pyjs8call.message (likely due to corrupted or incomplete data)
            - Parsed message value contains the JS8Call error character (defaults to an ellipsis)

        Received data that is successfully parsed is passed to *_process_message()* for further processing. 

        If debugging is enabled (see pyjs8call.client.Client.start) then the byte string of each message sent over the TCP socket is printed to the console. By default not all messages are printed in debug mode (see pyjs8call.js8call.JS8Call._debug_type_blacklist). Frequently sent and received messages used internal to pyjs8call are not printed.
        '''
        while self.online:
            data = b''
            data_str = ''

            try:
                data += self._socket.recv(65535)
            except (socket.timeout, OSError):
                # if rx from socket fails, stop processing
                # OSError occurs while app is restarting
                continue

            try: 
                data_str = data.decode('utf-8')
            except Exception as e:
                # if decode fails, stop processing
                continue

            # if rx data is empty, stop processing
            if len(data_str) == 0:
                continue

            self._last_rx_timestamp = time.time()
            self.connected = True

            # split received data into messages
            msgs = data_str.split('\n')

            for msg_str in msgs:
                # if message is empty, stop processing
                if len(msg_str) == 0:
                    continue

                try:
                    msg = Message().parse(msg_str)
                except Exception as e:
                    # if parsing message fails, stop processing
                    continue

                # if error in message value, stop processing
                if msg.value != None and Message.ERR in msg.value:
                    continue

                # print msg in debug mode
                if self._debug:
                    if self._debug_all:
                        print('RX: ' + str(msg.dict()))
                    elif msg.type not in self._debug_type_blacklist:
                        print('RX: ' + str(msg.dict()))

                self._process_message(msg)

        time.sleep(0.1)

    def _process_message(self, msg):
        '''Process received message.

        Messages are processed based on their command and/or their type (see pyjs8call.message for commands and types). Messages are spotted when appropriate. Responses to JS8Call setting and state requests are handled to update the associated local state variables.

        Automatic cleaning of directed message text is handled if enabled (see pyjs8call.client).

        Tx frame messages are passed to pyjs8call.windowmonitor.

        Args:
            msg (pyjs8call.message): Message to process
        '''

        ### command handling ###

        if msg.cmd == Message.CMD_HEARING:
            #TODO validate response structure
            #if not Message.ERR in msg.params['TEXT']:
            #    hearing = msg.params['TEXT'].split()[3:]
            #    for station in hearing:
            #        if station not in self.spots[msg.params['FROM']].keys():
            #            self.spots[msg.params['FROM']][station] = []
            #        self.spots[msg.params['FROM']][station].append(msg)

            # spot message
            self.spot(msg)

        #TODO no example, test response and update code
        #elif msg.params['CMD'] == 'QUERY CALL':
        #    # spot message
        #    self.spot(msg)
                
        elif msg.cmd in Message.COMMANDS:
            # spot message
            self.spot(msg)


        ### message type handling ###

        if msg.type == Message.INBOX_MESSAGES:
            self.state['inbox'] = msg.messages

        elif msg.type == Message.RX_SPOT:
            # spot message
            self.spot(msg)

        elif msg.type == Message.RX_DIRECTED:
            # clean msg text to remove callsigns, etc
            if self._client.clean_directed_text:
                msg = self._client.clean_rx_message_text(msg)

            # spot message
            self.spot(msg)

        elif msg.type == Message.RIG_FREQ:
            self.state['dial'] = msg.dial
            self.state['freq'] = msg.freq
            self.state['offset'] = msg.offset

        elif msg.type == Message.RIG_PTT:
            if msg.value == 'on':
                self.state['ptt'] = True
            else:
                self.state['ptt'] = False

        elif msg.type == Message.STATION_STATUS:
            self.state['dial'] = msg.dial
            self.state['freq'] = msg.freq
            self.state['offset'] = msg.offset
            self.state['speed'] = msg.speed

        elif msg.type == Message.STATION_CALLSIGN:
            self.state['callsign'] = msg.value

        elif msg.type == Message.STATION_GRID:
            self.state['grid'] = msg.value

        elif msg.type == Message.STATION_INFO:
            self.state['info'] = msg.value

        elif msg.type == Message.MODE_SPEED:
            self.state['speed'] = msg.speed

        elif msg.type == Message.TX_TEXT:
            self.state['tx_text'] = msg.value

        elif msg.type == Message.RX_TEXT:
            self.state['rx_text'] = msg.value

        elif msg.type == Message.RX_SELECTED_CALL:
            self.state['selected_call'] = msg.value

        elif msg.type == Message.RX_CALL_ACTIVITY:
            self.state['call_activity'] = msg.call_activity

        elif msg.type == Message.RX_BAND_ACTIVITY:
            self.state['band_activity'] = msg.band_activity

        #TODO should this be used? use RX.BAND_ACTIVITY for now
        #TODO note, RX.SPOT received immediately after RX.ACTIVITY in some cases
        elif msg.type == Message.RX_ACTIVITY:
            pass

        elif msg.type == Message.TX_FRAME:
            self._client.window_monitor.process_tx_frame(msg)

        self.append_to_rx_queue(msg)

