import serial
import time
import requests

import config

def get_rfid():

    ser = serial.Serial(config.SERIAL_DEVICE, config.SERIAL_BAUD_RATE, timeout=1)

    while 1:
        time.sleep(1)
        str1 = ser.readline()

        if len(str1) > 3:
            s = str1.lstrip('\x02').rstrip()
            payload = {"message":s}
            print payload
            r = requests.put(config.MESSAGE_QUEUE,data=payload)

get_rfid()
