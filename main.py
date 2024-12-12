"""
MicroPython on ESP32
"""
import usocket as socket
import time, utime
from machine import Pin
from machine import SoftSPI
import network
import esp
esp.osdebug(None)
import gc
gc.collect()

# Network setting
ssid = 'fanlab'
password = 'goodlife'
host_ip = '192.168.8.165'
host_port = 54080

station = network.WLAN(network.STA_IF)
station.active(True)

while station.isconnected() == False:
    try:
        station.connect(ssid, password)
        pass
    except:
        print('Connecting')
        time.sleep(1)

print('Connection successful')
print(station.ifconfig())

addr = socket.getaddrinfo(host_ip, host_port)[0][-1]
s = socket.socket()
s.bind(addr)
s.listen(1)
conn, addr = s.accept()
print('listening on', addr)

sarr = ''       

TopCtrl = [
    Pin(32, Pin.OUT),
    Pin(33, Pin.OUT),
    Pin(25, Pin.OUT),
    Pin(26, Pin.OUT)
]

BotCtrl = [
    Pin(27, Pin.OUT),
    Pin(14, Pin.OUT),
    Pin(13, Pin.OUT),
    Pin(15, Pin.OUT)
]

spi = SoftSPI(baudrate=115200, polarity=0, phase=0, sck=Pin(22), mosi=Pin(4), miso=Pin(21))
cs = Pin(19, Pin.OUT)
cs.value(1)

heat = Pin(17, Pin.OUT) # 0/1: OFF/ON
heat.value(0)
flt = Pin(16, Pin.OUT)  # 0/1: OFF/ON
flt.value(0)

sensor_data = []

for i in range(45):
    sensor_data.append(0) # Init

def read_data():
    cs.value(0)
    data = spi.read(3)
    cs.value(1)
    merged_data = (((data[0] << 16)| (data[1] << 8) | data[2]) >> 2)&0xFFFF
    return merged_data

def select(pins, index):
    for i in range(4):
        bit = (index >> i) & 1       
        pins[i].value(bit)

def scan():
    
    for i in range(15):
        select(TopCtrl, i)
        for j in range(3):
            select(BotCtrl, i - i % 3  + j)
            time.sleep_ms(5)
            read_data()
            sensor_data[i * 3 + (j % 3)] = read_data()
    """
    for i in range(5):
        select(TopCtrl, 3*i)
        select(BotCtrl, 3*i)
        time.sleep_ms(5)
        for t in range(3):
            read_data()
            time.sleep_ms(3)
        sensor_data[i] = read_data()
    """
def list_to_str():
    global sarr
    sarr = 'str'
    for i in sensor_data:
        sarr += str(i)
        sarr += '.'
    sarr += 'end'

print('\r\n\r\nSnake Gas Sensor Demo.\r\n')
heat.value(0)

while True:
    request = conn.recv(512)
    if len(request) > 0:
        #print("Received:%s"%request)
        if request.decode('utf-8') == 'filter_off':
            flt.value(1)
            print("flt off")
        elif request.decode('utf-8') == 'filter_on':  
            flt.value(0)
            print("flt on")
        elif request.decode('utf-8') == 'data':
            scan()
            list_to_str()
            print(sarr)
            conn.send(sarr.encode('utf-8'))  
        else:
            time.sleep_us(100)
        continue
