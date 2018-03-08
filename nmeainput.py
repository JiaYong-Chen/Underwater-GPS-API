from __future__ import print_function
import requests
import argparse
import time
import logging
import sys
import serial
import pynmea2
import socket


log = logging.getLogger()
logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)

class SetupException(Exception):
    pass

class SerialReader(object):
    def __init__(self, port, baud):
        try:
            self.ser = serial.Serial(port, baud, timeout=5.0)
        except serial.SerialException as err:
            print("Serial connection error: {}".format(err))
            raise SetupException()

    def iter(self):
        while True:
            yield self.ser.read()

class UDPReader(object):
    def __init__(self, host, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind((host, port))
        except socket.error as err:
            print("UDP setup: Could not bind to {}:{}. Error: {}".format(host, port, err))
            raise SetupException()

    def iter(self):
        while True:
            data, addr = self.sock.recvfrom(1024)
            print("Got {} bytes from {}: {}".format(len(data), addr, data))
            if not data:
                break
            # Add newline if not present
            if data[-1] != "\n":
                data = data + "\n"
            yield data
        self.sock.close()

def set_position_master(url, latitude, longitude, orientation):
    payload = dict(lat=latitude, lon=longitude, orientation=orientation)
    r = requests.put(url, json=payload, timeout=10)
    if r.status_code != 200:
        log.error("Error setting position and orientation: {} {}".format(r.status_code, r.text))


def run(base_url, conn):
    lat = 0
    lon = 0
    orientation = 0
    gotUpdate = False

    reader = pynmea2.NMEAStreamReader()

    for data in conn.iter():
        try:
          for msg in reader.next(data):
            if type(msg) == pynmea2.types.talker.GGA:
                lat = msg.latitude
                lon = msg.longitude
                gotUpdate = True

            elif type(msg) == pynmea2.types.talker.HDT:
                orientation = msg.heading
                gotUpdate = True

        except pynmea2.ParseError as e:
            log.warning("Error while parsing NMEA string: {}".format(e))

        if gotUpdate:
            log.info('Sending position and orientation')
            set_position_master('{}/api/v1/external/master'.format(base_url), lat, lon, orientation)
            gotUpdate = False

def main():
    parser = argparse.ArgumentParser(description="Read NMEA from UDP or serial and send position and orientation to Underwater GPS")
    parser.add_argument('-u', '--url', help='IP/URL of Underwater GPS kit. Typically http://192.168.2.94', type=str, default='http://demo.waterlinked.com')
    # UDP options
    parser.add_argument('-p', '--port', help="Port to listen for UDP packets", type=int, default=10110)
    parser.add_argument('-i', '--ip', help="Enable UDP by specifying interface to listen for UDP packets. Typically 'localhost' or '0.0.0.0'. Default disabled", type=str, default='')
    # Serial options
    parser.add_argument('-s', '--serial', help="Enable Serial by specifying serial port to use. Example: '/dev/ttyUSB0' or 'COM1' Default disabled", type=str, default='')
    parser.add_argument('-b', '--baud', help="Serial port baud rate", type=int, default=9600)
    args = parser.parse_args()

    if not (args.ip or args.serial):
        parser.print_help()
        print("")
        print("ERROR: Please specify either serial port or UDP port to use")
        print("")
        sys.exit(1)

    if (args.ip and args.serial):
        parser.print_help()
        print("")
        print("ERROR: Please specify either serial port or UDP port to use")
        print("")
        sys.exit(1)

    print("Sending data to Underwater GPS on url: {}".format(args.url))
    if args.serial:
        print("Source Serial {} at {} baud".format(args.serial, args.baud))
        try:
            ser = SerialReader(args.serial, args.baud)
        except SetupException:
            print("Aborting")
            sys.exit(1)

        run(args.url, ser)
        return

    if args.ip:
        print("Source UDP port {} on interface {}".format(args.port, args.ip))
        try:
            reader = UDPReader(args.ip, args.port)
        except SetupException:
            print("Aborting")
            sys.exit(1)

        run(args.url, reader)
        return

if __name__ == "__main__":
    main()
