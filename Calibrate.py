import socket
import sys
import time,csv
from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtCore import pyqtSlot, QObject, pyqtSignal, QThread
from PyQt5.QtWidgets import QMainWindow, QTextEdit
import numpy as np
import pyqtgraph as pg




global pixel_number, one_cycle
pixel_number = 45
one_cycle = 20 # seconds

class EmittingStream(QObject):
    textWritten = pyqtSignal(str)

    def write(self, text):
        self.textWritten.emit(str(text))
        
class WifiConnectThread(QThread):
    connection_success = pyqtSignal()
    connection_failed = pyqtSignal(str)

    def __init__(self, esp_ip, esp_port):
        super().__init__()
        self.esp_ip = esp_ip
        self.esp_port = esp_port
        self.socket_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_tcp.settimeout(5)  # 设置超时

    def run(self):
        addr = (self.esp_ip, self.esp_port)
        while True:
            try:
                print(f"Connecting to server @ {self.esp_ip}:{self.esp_port}...")
                self.socket_tcp.connect(addr)
                print("Connected!", addr)
                self.connection_success.emit()
                break
            except socket.timeout:
                self.connection_failed.emit("Connection timed out. Retrying...")
                time.sleep(1)
            except socket.error as e:
                self.connection_failed.emit(f"Socket error: {e}. Retrying...")
                time.sleep(1)
                
class Stats(QMainWindow):
    old_image = pyqtSignal(np.ndarray)

    def __init__(self):
        super().__init__()
        # Load UI
        self.ui = uic.loadUi("CalibrateGUI.ui", self)
        self.setWindowTitle("Gas Source Tracking System")

        # Output Display
        sys.stdout = EmittingStream(textWritten=self.normalOutputWritten)
        self.outputTextEdit = self.ui.findChild(QTextEdit, "Console")

        # Parameters
        self.esp_ip = "192.168.8.165"
        self.esp_port = 54080

        # Initialize data
        self.linedata = np.zeros((pixel_number, 1000))
        self.x = np.arange(1000)

        # Events
        self.ui.wifi_init.clicked.connect(self.Wifi_Init)
        self.ui.scan.clicked.connect(self.Scan)
        self.ui.stop.clicked.connect(self.Stop)

        # Network
        self.addr = (self.esp_ip, self.esp_port)
        self.socket_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Form Greyscale Color Map
        colors = [(i, i / 2, 0) for i in range(256)]
        self.colormap = pg.ColorMap(pos=np.linspace(0.0, 1.0, 256), color=colors)

        # Figures Initialization
        self.plot = self.ui.IMG1
        self.plotline = self.ui.IMG6
        self.plot.setBackground('w')
        self.plotline.setBackground('w')
        pg.setConfigOption('background', 'w')  # 设置背景为白色
        pg.setConfigOption('foreground', 'k')


        self.lines = []

        plot_instance1 = self.plotline.addPlot()
        plot_instance1.showGrid(x=True, y=True)
        plot_instance1.enableAutoRange()

        for i in range(pixel_number):
            pen = pg.mkPen(color=pg.intColor(i, 9), width=2)  # 不同颜色
            line = plot_instance1.plot(self.x, self.linedata[i], pen=pen, name=f"Line {i+1}")
            self.lines.append(line)

        self.show()
        self.csv_file = "calibrate_data/data_pixel1" +str(time.time()) +".csv"
        self.init_csv()

    @pyqtSlot(str)
    def normalOutputWritten(self, text):
        cursor = self.outputTextEdit.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        cursor.insertText(text)
        self.outputTextEdit.setTextCursor(cursor)
        self.outputTextEdit.ensureCursorVisible()

    def Create_Scan_Thread(self):
        self.scan_thread = ScanThread(self.ui, self.wifi_thread)
        self.scan_thread.stats = self
        self.scan_thread.update_data.connect(self.Handle_Update_Image)
        print("Scan thread ready")

    def Wifi_Init(self):
        self.wifi_thread = WifiConnectThread(self.esp_ip, self.esp_port)
        self.wifi_thread.connection_success.connect(self.on_connection_success)
        self.wifi_thread.connection_failed.connect(self.on_connection_failed)
        self.wifi_thread.start()

    def on_connection_success(self):
        print("Successfully connected to the server!")

    def on_connection_failed(self, error_message):
        print(error_message)
    
    @pyqtSlot(np.ndarray)
    def Handle_Update_Image(self, new_data):
        # 滚动数据，移除最旧的数据点
        self.linedata = np.roll(self.linedata, -1, axis=1)
        self.linedata[:, -1] = new_data  # 将新数据插入到最后一列

        # 更新每条折线的数据
        for i in range(pixel_number):
            self.lines[i].setData(self.x, self.linedata[i])
        
        self.show()
        self.append_to_csv(new_data)

    def init_csv(self):
        """初始化 CSV 文件，写入表头"""
        with open(self.csv_file, mode='w', newline='') as file:
            writer = csv.writer(file)
            # 写入表头，分别对应 Line1, Line2, ..., Line9
            header = [f"pixel{i+1}" for i in range(5)]
            writer.writerow(header)

    def append_to_csv(self, new_data):
        """将新数据追加到 CSV 文件中"""
        with open(self.csv_file, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(new_data)
 
    def Scan(self):
        try:
            self.Create_Scan_Thread()
        except:
            print("Thread Error.")
        if not self.scan_thread.isRunning():
            print("Start Scanning...")
            self.scan_thread.start()

    def Stop(self):
        self.scan_thread.stop()
        print("Scanning Stop.")

class ScanThread(QThread):
    update_data = pyqtSignal(np.ndarray)

    def __init__(self, ui, wifi):
        super().__init__()
        self.ui = ui
        self.is_running = False
        self.stats = None
        self.wifi = wifi

    def run(self):
        self.is_running = True
        while self.is_running:
            try:
                msg = 'filter_off'
                self.wifi.socket_tcp.send(msg.encode('utf-8'))
                time.sleep(0.01)
                st = time.time()
                while self.is_running and time.time() - st < one_cycle / 2:
                    msg = 'data'
                    self.wifi.socket_tcp.send(msg.encode('utf-8'))
                    rmsg = self.wifi.socket_tcp.recv(8192)
                    str_data = (rmsg.decode('utf-8'))[3:-4]
                    raw_data = np.array(list(map(int, str_data.split('.'))))
                    self.update_data.emit(raw_data)
                    time.sleep(0.01)
                msg = 'filter_on'
                self.wifi.socket_tcp.send(msg.encode('utf-8'))
                time.sleep(0.01)
                st = time.time()
                while self.is_running and time.time() - st < one_cycle / 2:
                    msg = 'data'
                    self.wifi.socket_tcp.send(msg.encode('utf-8'))
                    rmsg = self.wifi.socket_tcp.recv(8192)
                    str_data = (rmsg.decode('utf-8'))[3:-4]
                    raw_data = np.array(list(map(int, str_data.split('.'))))
                    self.update_data.emit(raw_data)
                    time.sleep(0.01)
            except Exception as e:
                print("Thread Error:", e)
                break

    def stop(self):
        self.is_running = False

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    stats = Stats()

    stats.show()
    sys.exit(app.exec_())
