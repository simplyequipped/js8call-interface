import time
import threading

import pyjs8call
from pyjs8call import Message


class TxMonitor:
    def __init__(self, client):
        self.client = client
        self.msg_queue = []
        self.msg_queue_lock = threading.Lock()
        # initialize msg max age to 30 tx cycles in fast mode (10 sec cycles)
        self.msg_max_age = 10 * 30 # 5 minutes
        self.tx_complete_callback = None
        self.tx_failed_callback = None

        monitor_thread = threading.Thread(target=self._monitor)
        monitor_thread.setDaemon(True)
        monitor_thread.start()

    def set_tx_complete_callback(self, callback):
        self.tx_complete_callback = callback

    def set_tx_failed_callback(self, callback):
        self.tx_failed_callback = callback

    def monitor(self, msg):
        msg.status = Message.STATUS_QUEUED

        self.msg_queue_lock.acquire()
        self.msg_queue.append(msg)
        self.msg_queue_lock.release()

    def _monitor(self):
        while self.client.online:
            time.sleep(1)
            tx_text = self.client.get_tx_text()

            # no text in tx field, nothing to process
            if tx_text == None:
                continue

            tx_text.strip(' ' + Message.EOM)
            
            # update msg max age based on speed setting (30 tx cycles)
            #    3 min in turbo mode (6 sec cycles)
            #    5 min in fast mode (10 sec cycles)
            #    7.5 min in normal mode (15 sec cycles)
            #    15 min in slow mode (30 sec cycles)
            tx_window = self.client.get_tx_window_duration()
            self.msg_max_age = tx_window * 30
            
            self.msg_queue_lock.acquire()

            # process msg queue
            for i in range(len(self.msg_queue)):
                msg = self.msg_queue.pop(0)
                drop = False

                if msg.value in tx_text and msg.status == Message.STATUS_QUEUED:
                    # msg text was added to js8call tx field, sending
                    msg.status = Message.STATUS_SENDING
                        
                elif msg.value not in tx_text and msg.status == Message.STATUS_SENDING:
                    # msg text was removed from js8call tx field, sent
                    msg.status = Message.STATUS_SENT

                    if self.tx_complete_callback != None:
                        self.tx_complete_callback(msg)
                        
                    drop = True
                       
                elif time.time() > msg.timestamp + self.msg_max_age:
                    # msg sending failed
                    if self.tx_failed_callback != None:
                        self.tx_failed_callback(msg)
                        
                    drop = True

                if not drop:
                    self.msg_queue.append(msg)
                        
            self.msg_queue_lock.release()
            
