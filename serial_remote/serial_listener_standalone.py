import serial
import time,sys

import requests

import config
from daemon import Daemon

class SerialListener(object):

    def run(self):

        ser = serial.Serial(config.SERIAL_DEVICE, config.SERIAL_BAUD_RATE, timeout=1)

        while 1:

            try:
                time.sleep(1)
                str1 = ser.readline()

                if len(str1) > 3:
                    s = str1.lstrip('\x02').rstrip()
                    payload = {"message":s}
                    r = requests.put(config.MESSAGE_QUEUE,data=payload)

            except (KeyboardInterrupt, SystemExit):
                raise
            except:
                pass

if __name__ == '__main__':
    SerialListener().run()
