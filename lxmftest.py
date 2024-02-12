import os
import sys
import time

import RNS
import LXMF


__APPNAME__ = 'pyjs8call'
notify_destination_hash = bytes.fromhex(sys.argv[1])

def handle_lxmf_delivery(message):
    print(message.content_as_string())

def announce_router():
    global router
    global source
    router.announce(source.hash)
    print('Router announce sent')

def send_test_msg(content='testing lxmf'):
    global notify_destination_hash
    global router
    global __APPNAME__

    if not RNS.Transport.has_path(notify_destination_hash):
        print('Requesting path to notification destination...')
        RNS.Transport.request_path(notify_destination_hash)
        
        while not RNS.Transport.has_path(notify_destination_hash):
            time.sleep(0.1)
    
        print('Path to notification destination found')
    
    recipient_id = RNS.Identity.recall(notify_destination_hash)
    target_destination = RNS.Destination(recipient_id, RNS.Destination.OUT, RNS.Destination.SINGLE, 'lxmf', 'delivery')
    
    lxm = LXMF.LXMessage(target_destination, source, content)
    router.handle_outbound(lxm)
    print('Test message sent')


RNS.Reticulum()

# load local Identiy or create a new Identity
config_path = os.path.join(os.path.expanduser('~'), '.pyjs8call')
identity_path = os.path.join(config_path, 'identity')

if not os.path.exists(config_path):
    os.makedirs(config_path)
    
if os.path.exists(identity_path):
    router_id = RNS.Identity.from_file(identity_path)
else:
    os.makedirs(identity_path)
    router_id = RNS.Identity()
    router_id.to_file(identity_path)
    
router = LXMF.LXMRouter(identity = router_id, storagepath='./tmp')
router.register_delivery_callback(handle_lxmf_delivery)
source = router.register_delivery_identity(router_id, display_name='JS8Call')
print('JS8Call destination created')


while True:
    menu = '''
    Enter a menu option and press Enter:
        a) send router announce
        m) send test message
        x) exit
    '''
    menu_option = input(menu)

    if menu_option == 'a':
        announce_router()
    elif menu_option == 'm':
        send_test_msg()
    elif menu_option == 'x':
        break
