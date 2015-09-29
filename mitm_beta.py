#! /bin/env python
# -*- coding: utf-8 -*-

"""

Ethernet Bridge

Description: Ethernet bridge for man-in-the-middle attacks.

Markus Mahrla
GAI NetConsult GmbH

Last change: 28-09-2015

"""

import sys, signal, os, argparse, struct, fcntl 
from fcntl import ioctl
from threading import *
from socket import *
from ConfigParser import *
import pdb

MTU = 32676
ETH_P_ALL = 0x03

TUNSETIFF = 0x400454ca
IFF_TAP   = 0x0002

BUFFERSIZE_DEV = 65000

class sniffer():

    def __init__(self, iface0, iface1, mitm_in, mitm_out, filter):
        if mitm_in:
           self.s_iface0 = socket(AF_PACKET, SOCK_RAW, htons(ETH_P_ALL))
           self.s_iface0.setblocking(0)
           self.s_iface0.bind((iface0, ETH_P_ALL))

           self.s_iface1 = socket(AF_PACKET, SOCK_RAW)
           self.s_iface1.bind((iface1, ETH_P_ALL)) 

           self.receive = self.socket_receive
           self.send = self.socket_send1
           self.redirect = self.device_send

        if mitm_out:
           self.s_iface0 = socket(AF_PACKET, SOCK_RAW)
           self.s_iface0.bind((iface0, 0)) 

           self.s_iface1 = socket(AF_PACKET, SOCK_RAW)
           self.s_iface1.bind((iface1, 0)) 

           self.receive = self.device_receive
           self.send = self.socket_send0
           self.redirect = self.socket_send1

        if filter:
           self.filter = filter
        else:
           self.filter = ""

    def lock_check(self):
        return not still_running_lock.locked()

    def apply_filter(self, pkt_ip, pkt_port):
       if self.filter:
          for filter in self.filter:
             if filter[0] == pkt_ip or filter[0] == "0.0.0.0":
                if filter[1] == pkt_port or filter[1] == "": 
                   return True 
       return False
    
    def socket_receive(self):
       try:
          pkt, sa = self.s_iface0.recvfrom(MTU)
          if sa[2] != PACKET_OUTGOING:
             return pkt
       except error:
          pass
 
    def socket_send0(self, pkt):
       try:
          self.s_iface0.send(pkt)
       except error:
           pass

    def socket_send1(self, pkt):
       try:
          self.s_iface1.send(pkt)
       except error:
          pass

    def device_receive(self):
       try:
          p = os.read(tap_device, BUFFERSIZE_DEV)
          return p 
       except error:
          pass

    def device_send(self, pkt):
       try:
          p = os.write(tap_device, pkt)
       except error:
          pass

    def recv_send_loop(self):
        while True:
           pkt = self.receive()
           if pkt:
              if self.apply_filter(pkt[0x1e:][:4], pkt[0x24:][:2]):
                 pkt_new = pkt[0:6] + "128926521146".decode("hex") + pkt[0xc:0x1e] + filter[0][0] + pkt[0x20:] 
                 self.redirect(pkt_new)
              else:
                 self.send(pkt)
           if self.lock_check() == True:
              break

thread1 = None
thread2 = None 
thread3 = None 
still_running_lock = Lock()

def signal_handler(signal, frame):
    still_running_lock.release()
    thread1.join()
    thread2.join()
    thread3.join()
    sys.exit(0)

def parse_config():
        config = ConfigParser()
        config.readfp(open('mitm.conf'))
        print config.get('Server','ip')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Ethernet Bridge')
    parser.add_argument("-f", nargs=1, dest="file_name", type=str, action='store',
       help='config file to block ip address and/or tcp port (file syntax per line: <ip>:<port> (e.g. "192.168.0.1:443", "0.0.0.0:80", "192.168.1.1")')
    parser.add_argument("-r", dest="rewrite", action='store_true', help='rewrite mac address on second interface (taken from first interface)')
    parser.add_argument("interface1", nargs=1, type=str, action='store', help='first interface to bridge')
    parser.add_argument("interface2", nargs=1, type=str, action='store', help='man-in-the-middle interface')
    parser.add_argument("interface3", nargs=1, type=str, action='store', help='second interface to bridge')

    args = parser.parse_args()

    host1_interface = args.interface1[0]
    mitm_interface = args.interface2[0]
    host2_interface = args.interface3[0]

    filter = []
    if args.file_name:
       file = open(args.file_name[0]).readlines()
       for line in file:
          ip, colon, port = line.partition(":")
          if port:
             filter.append([inet_aton(ip), struct.pack(">H", int(port))])
          else:
             filter.append([inet_aton(ip), ""])

    if args.rewrite:
       rewrite = args.rewrite[0]
       
    os.system("ifconfig " + host1_interface + " promisc")
    os.system("ifconfig " + host2_interface + " promisc")

    tap_device = os.open('/dev/net/tun', os.O_RDWR | os.O_NONBLOCK)
    flags = struct.pack('16sH', "tap0", IFF_TAP)
    fcntl.ioctl(tap_device, TUNSETIFF, flags)

    sniffer1 = sniffer(host1_interface, host2_interface, mitm_interface, 0, filter)
    sniffer2 = sniffer(host2_interface, host1_interface, mitm_interface, 0, filter)
    sniffer3 = sniffer(host1_interface, host2_interface, 0, mitm_interface, filter)

    thread1 = Thread(target=sniffer1.recv_send_loop) 
    thread2 = Thread(target=sniffer2.recv_send_loop)
    thread3 = Thread(target=sniffer1.recv_send_loop) 

    still_running_lock.acquire()

    thread1.start()
    thread2.start()
    thread3.start()

    signal.signal(signal.SIGINT, signal_handler)
    signal.pause()