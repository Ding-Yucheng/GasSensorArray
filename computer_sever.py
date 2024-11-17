import socket
import sys
import time
from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtCore import pyqtSlot, QObject, pyqtSignal, QThread
from PyQt5.QtWidgets import QMainWindow, QTextEdit
import numpy as np
import pyqtgraph as pg

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
        self.ui = uic.loadUi("ScanGUI.ui", self)
        self.setWindowTitle("Gas Source Tracking System")

        # Output Display
        sys.stdout = EmittingStream(textWritten=self.normalOutputWritten)
        self.outputTextEdit = self.ui.findChild(QTextEdit, "Console")

        # Parameters
        self.esp_ip = "192.168.8.165"
        self.esp_port = 54080

        # Initialize data
        self.data = np.arange(45).reshape(5, 3, 3)

        # Events
        self.ui.wifi_init.clicked.connect(self.Wifi_Init)
        self.ui.scan.clicked.connect(self.Scan)
        self.ui.stop.clicked.connect(self.Stop)

        # Concentration Display
        self.texts = [self.ui.C1, self.ui.C2, self.ui.C3, self.ui.C4, self.ui.C5]
        for cc in self.texts:
            cc.setText("Concentration: 0 ppm")
        
        # Network
        self.addr = (self.esp_ip, self.esp_port)
        self.socket_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Form Greyscale Color Map
        colors = [(i, i / 2, 0) for i in range(256)]
        self.colormap = pg.ColorMap(pos=np.linspace(0.0, 1.0, 256), color=colors)

        # Figures Initialization
        self.plots = [self.ui.IMG1, self.ui.IMG2, self.ui.IMG3, self.ui.IMG4, self.ui.IMG5]
        self.data_indices = range(5)
        self.img_items = []

        # Parameters
        self.linear_k = [1, 1, 1, 1, 1]
        self.linear_c = [0, 0, 0, 0, 0]
        self.i = 1
        self.j = 1
        self.sensor_positions = np.array([[0, 0],[-1, 1],[-1, -1],[1, -1],[1, 1]])
        self.weights = []
        self.concentrations = np.zeros(5)

        for pos in self.sensor_positions:
            distance = np.linalg.norm([0, 0]- pos)
            if distance != 0:
                self.weights.append(1 / (distance ** 2))
            else:
                self.weights.append(0)

        self.weights = np.array(self.weights)

        for plot, index in zip(self.plots, self.data_indices):
            img_item = pg.ImageItem()
            plot_instance = plot.addPlot()
            plot_instance.addItem(img_item)
            img_item.setLookupTable(self.colormap.getLookupTable())
            img_item.setImage(self.data[index])
            plot_instance.hideAxis('bottom')
            plot_instance.hideAxis('left')
            self.img_items.append(img_item)
        
        plot_instance = self.ui.IMG6.addViewBox()
        plot_instance.setAspectLocked(True)
        plot_instance.setRange(QtCore.QRectF(-10, -10, 20, 20))
        
        circle_radii = np.linspace(1, 10, 10)
        for radius in circle_radii:
            circle = QtWidgets.QGraphicsEllipseItem(-radius, -radius, radius*2, radius*2)
            circle.setPen(pg.mkPen('gray', style=QtCore.Qt.DashLine))
            plot_instance.addItem(circle)
        self.img_source_dir = pg.ArrowItem(pos=(0,0),angle=0, tipAngle=30, headLen=10, tailLen=0, pen={'color': 'b', 'width': 2})
        self.img_source_len = pg.PlotDataItem()
        self.img_source_len.setPen(width=4, color=(0, 0, 155))
        plot_instance.addItem(self.img_source_len)
        plot_instance.addItem(self.img_source_dir)
        self.show()

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
        matrices = new_data.reshape(5, 3, 3)
        for img_item, index in zip(self.img_items, self.data_indices):
            img_item.setImage(matrices[index])  # Use the stored img_item to update the image
            self.concentrations[index] =round(float(matrices[index][self.i][self.j]) * self.linear_k[index] + self.linear_c[index],2)
            self.texts[index].setText("Concentration: " + str(self.concentrations[index])+" ppm")
        x,y = self.estimate_source_location()
        line = QtCore.QLineF(0, 0, x, y)
        self.img_source_dir.setPos(x,y)
        self.img_source_dir.setStyle(angle = line.angle()+180)
        self.img_source_len.setData([0,x],[0,y])
        self.show()

    def estimate_source_location(self):
        weighted_concentrations = self.weights * self.concentrations
        print(weighted_concentrations)
        # Estimate source location using weighted average
        estimated_x = np.sum(self.sensor_positions[:, 0] * weighted_concentrations) / np.sum(weighted_concentrations)
        estimated_y = np.sum(self.sensor_positions[:, 1] * weighted_concentrations) / np.sum(weighted_concentrations)

        return estimated_x, estimated_y
 
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
                msg = 'heating_off'
                self.wifi.socket_tcp.send(msg.encode('utf-8'))
                time.sleep(4.95)
                msg = 'data1'
                self.wifi.socket_tcp.send(msg.encode('utf-8'))
                rmsg = self.wifi.socket_tcp.recv(8192)
                str_data = (rmsg.decode('utf-8'))[3:-4]
                raw_data_before = np.array(list(map(int, str_data.split('.'))))
                time.sleep(0.1)
                msg = 'data2'
                self.wifi.socket_tcp.send(msg.encode('utf-8'))
                rmsg = self.wifi.socket_tcp.recv(8192)
                str_data = (rmsg.decode('utf-8'))[3:-4]
                raw_data_after = np.array(list(map(int, str_data.split('.'))))
                self.update_data.emit(raw_data_after-raw_data_before)
                time.sleep(4.95)
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
