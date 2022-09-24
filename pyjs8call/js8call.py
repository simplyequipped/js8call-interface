import time
import json
import socket
import threading

import pyjs8call
from pyjs8call import Message


class JS8Call:
    
    def __init__(self, host='localhost', port=2442):
        self._host = host
        self._port = port
        self._rx_queue = []
        self._tx_queue = []
        self._socket = socket.socket()
        self._watch_timeout = 3 # seconds
        self._last_rx_timestamp = 0
        self._socket_heartbeat_delay = 60 * 5 # seconds
        self._app = None
        self.pending = False # rx pending
        self.connected = False
        self.online = False
        self.spots = {}

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

        #self._start_app()
        self._connect()
        self.online = True
        
        tx_thread = threading.Thread(target=self._tx)
        tx_thread.setDaemon(True)
        tx_thread.start()

        rx_thread = threading.Thread(target=self._rx)
        rx_thread.setDaemon(True)
        rx_thread.start()

        hb_thread = threading.Thread(target=self._hb)
        hb_thread.setDaemon(True)
        hb_thread.start()

        # get callsign
        msg = Message()
        msg.type = Message.STATION_GET_CALLSIGN
        self.send(msg)
        self.watch('callsign')

        self.spots[self.state['callsign']] = {}
        
    def stop(self):
        self.online = False

        if self._app != None:
            self._app.terminate()

    def _start_app(self):
        #TODO start js8call application
        self._app = subprocess.Popen(['js8call'])
        time.sleep(3)

    def _connect(self):
        try:
            self._socket.connect((self._host, int(self._port)))
            self._socket.settimeout(1)
        except:
            #TODO handle
            pass

    def send(self, msg):
        packed = msg.pack()
        self._tx_queue.append(packed)

    def get(self):
        if len(self._rx_queue) > 0:
            return self._rx_queue.pop(0)

    def watch(self, item):
        if item not in self.state.keys():
            return None

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
        
        return self.state[item]

    def _hb(self):
        while self.online:
            # if no recent rx,check the connection by making a request
            timeout = self._last_rx_timestamp + self._socket_heartbeat_delay
            if time.time() > timeout:
                self.connected = False
                msg = Message()
                msg.type = Message.STATION_GET_CALLSIGN
                self.send(msg)
                
            time.sleep(1)

    def _tx(self):
        while self.online:
            while len(self._tx_queue) == 0:
                time.sleep(0.1)

            for i in range(len(self._tx_queue)):
                item = self._tx_queue.pop(0)
                self._socket.sendall(item)
                time.sleep(0.25)
                
    def _rx(self):
        while self.online:
            data = b''
            data_str = ''

            try:
                data += self._socket.recv(65535)
            except socket.timeout:
                # if rx from socket fails, stop processing
                continue

            try: 
                data_str = data.decode('utf-8')
            except:
                # if decode fails, stop processing
                continue

            # if rx data is empty, stop processing
            if len(data_str) == 0:
                continue

            self._last_rx_timestamp = time.time()
            self.connected = True

            #split received data into messages
            msgs = data_str.split('\n')

            for msg_str in msgs:
                # if message is empty, stop processing
                if len(msg_str) == 0:
                    continue

                try:
                    msg = Message().parse(msg_str)
                except:
                    # if parsing message fails, stop processing
                    continue

                # if error in message value, stop processing
                if pyjs8call.Message.ERR in msg.value:
                    continue

                #TODO
                print(msg_str)

                if msg.params['CMD'] == 'HEARTBEAT SNR':
                    if msg.params['FROM'] not in self.spots.keys():
                        self.spots[msg.params['FROM']] = {}
                    if msg.params['TO'] not in self.spots[msg.params['FROM']].keys():
                        self.spots[msg.params['FROM']][msg.params['TO']] = []
                    self.spots[msg.params['FROM']][msg.params['TO']].append(msg)

                elif msg.params['CMD'] == 'SNR':
                    if msg.params['FROM'] not in self.spots.keys():
                        self.spots[msg.params['FROM']] = {}
                    if msg.params['TO'] not in self.spots[msg.params['FROM']].keys():
                        self.spots[msg.params['FROM']][msg.params['TO']] = []
                    self.spots[msg.params['FROM']][msg.params['TO']].append(msg)
                    #receive message
                    self._rx_queue.append(msg)

                elif msg.params['CMD'] == 'GRID':
                    if msg.params['FROM'] not in self.spots.keys():
                        self.spots[msg.params['FROM']] = {}
                    if msg.params['TO'] not in self.spots[msg.params['FROM']].keys():
                        self.spots[msg.params['FROM']][msg.params['TO']] = []
                    self.spots[msg.params['FROM']][msg.params['TO']].append(msg)
                    #receive message
                    self._rx_queue.append(msg)

                elif msg.params['CMD'] == 'HEARING':
                    if msg.params['FROM'] not in self.spots.keys():
                        self.spots[msg.params['FROM']] = {}
                    if not Message.ERR in msg.params['TEXT']:
                        hearing = msg.params['TEXT'].split()[3:]
                        for station in hearing:
                            if station not in self.spots[msg.params['FROM']].keys():
                                self.spots[msg.params['FROM']][station] = []
                            self.spots[msg.params['FROM']][station].append(msg)
                    #receive message
                    self._rx_queue.append(msg)

                #TODO no example, test response and update code
                #if msg.params['CMD'] == 'QUERY CALL':
                #    if msg.params['FROM'] not in self.spots.keys():
                #        self.spots[msg.params['FROM']] = {}
                #    if msg.params['TO'] not in self.spots[msg.params['FROM']].keys():
                #        self.spots[msg.params['FROM']][msg.params['TO']] = []
                #    self.spots[msg.params['FROM']][msg.params['TO']].append(msg)
                #    #receive message
                #    self._rx_queue.append(msg)

                if msg.type == 'INBOX.MESSAGES':
                    msg_data = [m['params'] for m in msg.params['MESSAGES']]
                    messages = []

                    for m in msg_data:
                        message = {
                            'id' : m['_ID'],
                            'time' : m['UTC'],
                            'from' : m['FROM'],
                            'to' : m['TO'],
                            'path' : m['PATH'],
                            'message' : m['TEXT']
                        }
                        messages.append(message)

                    self.state['inbox'] = messages
                
                elif msg.type == 'RX.SPOT':
                    if msg.params['CALL'] not in self.spots.keys():
                        self.spots[msg.params['CALL']] = {}
                    if self.state['callsign'] not in self.spots[msg.params['CALL']].keys():
                        self.spots[msg.params['CALL']][self.state['callsign']] = []
                    self.spots[msg.params['CALL']][self.state['callsign']].append(msg)

                elif msg.type == 'RX.DIRECTED':
                    if msg.params['FROM'] not in self.spots.keys():
                        self.spots[msg.params['FROM']] = {}
                    if self.state['callsign'] not in self.spots[msg.params['FROM']].keys():
                        self.spots[msg.params['FROM']][self.state['callsign']] = []
                    self.spots[msg.params['FROM']][self.state['callsign']].append(msg)
                    #receive message
                    self._rx_queue.append(msg)

                elif msg.type == 'RIG.FREQ':
                    self.state['dial'] = msg.params['DIAL']
                    self.state['freq'] = msg.params['FREQ']
                    self.state['offset'] = msg.params['OFFSET']

                elif msg.type == 'RIG.PTT':
                    if msg.value == 'on':
                        self.state['ptt'] = True
                    else:
                        self.state['ptt'] = False

                elif msg.type == 'STATION.CALLSIGN':
                    self.state['callsign'] = msg.value

                elif msg.type == 'STATION.GRID':
                    self.state['grid'] = msg.value

                elif msg.type == 'STATION.INFO':
                    self.state['info'] = msg.value

                elif msg.type == 'MODE.SPEED':
                    self.state['speed'] = msg.params['SPEED']

                elif msg.type == 'TX.TEXT':
                    self.state['tx_text'] = msg.value

                elif msg.type == 'RX.TEXT':
                    self.state['rx_text'] = msg.value

                elif msg.type == 'RX.CALL_SELECTED':
                    self.state['selected_call'] = msg.value

                elif msg.type == 'RX.CALL_ACTIVITY':
                    activity = []
                    for key, value in msg.params.items():
                        if key == '_ID' or value == None:
                            continue

                        call = {
                            'callsign' : key,
                            'grid' : value['GRID'],
                            'snr' : value['SNR'],
                            'time' : value['UTC']
                        }

                        activity.append(call)

                    self.state['call_activity'] = activity

                elif msg.type == 'RX.BAND_ACTIVITY':
                    activity = []
                    for key, value in msg.params.items():
                        try:
                            # if key is not a freq offset this will error and continue
                            int(key)
                            activity.append(value)
                        except:
                            continue

                    self.state['band_activity'] = activity

                #TODO should this be used? use RX.BAND_ACTIVITY for now
                elif msg.type == 'RX.ACTIVITY':
                    pass

        if len(self._rx_queue) > 0:
            self.pending = True
        else:
            self.pending = False

        time.sleep(0.1)



