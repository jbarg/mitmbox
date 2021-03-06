import sys
import signal
import argparse
from threading import *
from ConfigParser import *
from pdb import *
from scapy.all import *
from socket import *
import Queue
import time

from .bridging.parse_config import Parse_MitmConfig
from .bridging.bridge import sniffer
from .bridging.tapDevice import init_tapDevices


thread1 = None
thread2 = None
thread3 = None

still_running_lock = Lock()

# currently this Queue is used to tell the Bridging Threads to quit.
# int the future this feature could be used, to trigger a reread of the config
control_queue = Queue.Queue()


def signal_handler(signal, frame):
    print "\nEXITING MITMBOX"
    control_queue.put(('quit',))
    time.sleep(1)
    sys.exit(0)


def mitmbox():

    parser = argparse.ArgumentParser(
        description='mitmbox ethernet intercepter')

    parser.add_argument("-c", nargs=1, dest="config_file", type=str, action='store',
                        help='config file to intercept traffic', default='mitm.conf')

    args = parser.parse_args()
    mitm_config = Parse_MitmConfig(args.config_file[0])

    bridge0_interface = mitm_config.bridge0_interface
    bridge1_interface = mitm_config.bridge1_interface
    mitm_interface = mitm_config.mitm_interface

    init_tapDevices(bridge0_interface, bridge1_interface)

    sniffer1 = sniffer(bridge0_interface, bridge1_interface,
                       mitm_interface, 0, mitm_config.dst_ip, mitm_config.dst_mac, mitm_config.dst_port, control_queue)
    sniffer2 = sniffer(bridge1_interface, bridge0_interface,
                       mitm_interface, 0, mitm_config.dst_ip, mitm_config.dst_mac, mitm_config.dst_port, control_queue)
    sniffer3 = sniffer(bridge0_interface, bridge1_interface, 0,
                       mitm_interface, mitm_config.dst_ip, mitm_config.dst_mac, mitm_config.dst_port, control_queue)

    thread1 = Thread(target=sniffer1.recv_send_loop)
    thread2 = Thread(target=sniffer2.recv_send_loop)
    thread3 = Thread(target=sniffer3.recv_send_loop)

    # still_running_lock.acquire()

    thread1.start()
    thread2.start()
    thread3.start()

    signal.signal(signal.SIGINT, signal_handler)
    signal.pause()

    sys.exit(0)
