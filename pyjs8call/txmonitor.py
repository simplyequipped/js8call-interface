import time
import threading

import pyjs8call


class TxMonitor:
    PENDING  = 'pending'
    ACTIVE   = 'active'
    COMPLETE = 'complete'
    
    def __init__(self, client):
        self.client = client
        self.monitor_text = []
        self.monitor_text_lock = threading.Lock()
        self.monitor_text_size_limit = 10
        self.tx_complete_callback = None

        monitor_thread = threading.Thread(target=self._monitor)
        monitor_thread.setDaemon(True)
        monitor_thread.start()

    def set_tx_complete_callback(self, callback):
        self.tx_complete_callback = callback

    def monitor(self, text, identifier=None):
        new_text = {'text': text.upper(), 'state': TxMonitor.PENDING, 'id': identifier}

        self.monitor_text_lock.acquire()
        self.monitor_text.append(new_text)
        
        if len(self.monitor_text) > self.monitor_text_size_limit:
            self.monitor_text.pop(0)
       
        self.monitor_text_lock.release()

    def _monitor(self):
        while self.client.online:
            time.sleep(1)
            tx_text = self.client.get_tx_text()

            if tx_text == None:
                continue

            tx_text.strip(' ' + pyjs8call.Message.EOM)
            self.monitor_text_lock.acquire()

            for i in range(len(self.monitor_text)):
                if self.monitor_text[i]['text'] in tx_text and self.monitor_text[i]['state'] == TxMonitor.PENDING:
                    self.monitor_text[i]['state'] = TxMonitor.ACTIVE
                        
                elif self.monitor_text[i]['text'] not in tx_text and self.monitor_text[i]['state'] == TxMonitor.ACTIVE:
                    self.monitor_text[i]['state'] = TxMonitor.COMPLETE
                    if self.tx_complete_callback != None:
                        if self.monitor_text[i]['id'] == None:
                            self.tx_complete_callback(self.monitor_text[i]['text'])
                        else:
                            self.tx_complete_callback(self.monitor_text[i]['id'])
                        
            self.monitor_text_lock.release()
                        
