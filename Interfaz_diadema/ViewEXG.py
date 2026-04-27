# ViewEXG.py
# Description:
# Main application that displays and saves acquired signals.
# Author: Mario Valderrama

import os
import sys
import time

import matplotlib
import numpy as np
import struct as st
from libViewEXGBLE import *
from scipy import signal
from datetime import datetime
import f_SignalProcFuncLibs as sigpro
from scipy.ndimage import gaussian_filter
from bleak import BleakScanner, BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
matplotlib.use('QtAgg')

from PyQt6 import QtCore, QtWidgets, QtGui

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt


class MplCanvas(FigureCanvas):

    def __init__(self, parent=None, width=5, height=4, position=[0.1,0.1,0.8,0.8], dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        # self.axes = fig.add_subplot(111)
        self.axes = fig.add_axes((position))
        super(MplCanvas, self).__init__(fig)

# ############################################
## class MainWindow
class MainWindow(QtWidgets.QMainWindow):

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        self.setWindowTitle("ViewEXG")
        self.resize(2280, 1520)

        # Acq parameters
        self.eegCharacteristicUUID = "980d0c33-ada0-4a16-a6f5-499477dcfefd"
        self.triggerCharacteristicUUID = ""

        self.dataFsHz = 250
        self.plotWinLenSec = 10
        self.plotWinLenSam = int(self.plotWinLenSec * self.dataFsHz)
        self.plotTFWinLenSec = self.plotWinLenSec
        self.plotTFWinLenSam = int(self.plotTFWinLenSec * self.dataFsHz)
        self.tfWinSizeSec = 3.0
        self.tfWinSizeSam = int(self.tfWinSizeSec * self.dataFsHz)
        self.bufferLenSec = 3 * 60
        self.bufferLenSam = int(self.bufferLenSec * self.dataFsHz)
        self.dataBuffer = np.zeros(self.bufferLenSam)
        self.timeBuffer = np.zeros(self.bufferLenSam)
        self.refreshTimeMS = 50
        self.refreshTimeTFSec = 0.250
        self.bufferInd = -1
        self.bufferIndAux = -1
        self.bufferIndTFAux = -1
        self.bufferPlotInd = -1
        self.bufferTFPlotInd = -1
        self.tfPlotSec = 0
        self.win_size_list_options = ['3','5','7','10','20','30','60']
        self.scale_list_options = ['0.01','0.02','0.05','0.1','0.2','0.5',
                                   '1','2','5','10','50','100','200','500',
                                   '1000','2000','3000','5000','10000',
                                   '15000','20000','30000','50000','100000','200000','500000','1000000','2000000','5000000']
        self.scaleDefaultOption = 100000
        self.filter_list_options = ['0.3','0.5','1','2','3','4','5','8','10',
                                    '12','16','18','20','25','30','35','40','45','50','55','60','65','70','80','90','100']
        filterDefaultFreqHz = [0.3, 35]
        self.filterCurrentFreqHzInd = [self.filter_list_options.index(str(filterDefaultFreqHz[0])),
                                       self.filter_list_options.index(str(filterDefaultFreqHz[1]))]
        #self.tfCurrentFreqHz = filterDefaultFreqHz
        self.tfCurrentFreqHz = [3, 70]
        self.tfFreqResHz = 1.0
        self.tfNumofCycles = 6
        self.tfElapsedTimeSec = 0

        self.triggerVal = 0
        self.filterTaps = []
        self.filter1Flag = True
        self.recFlag = False
        self.acqFlag = False
        self.exitFlag = False
        self.reStartFlag = False
        self.discover_timeout = 10
        self.dev_list_name = []
        self.dev_list_address = []
        # self.uuid_list = []
        self.root_ble_name = 'ViewEXG'
        self.ble_main_stream_hld = None
        self.ble_cfg_eeg_hld = None
        self.triggerQueue = queue.Queue()
        ####################
        # self.n_data = 50
        # self.xdata = list(range(self.n_data))
        # self.ydata = [random.randint(0, 10) for i in range(self.n_data)]
        # self.inddata = 0

        self.create_ui()

        # We need to store a reference to the plotted line
        # somewhere, so we can apply the new data to it.
        self.plotRef = None
        self.tfPlotRef = None
        self.tfUpdateFreqs = False
        self.on_set_filter1()
        self.on_set_tf1()
        self.update_ui()

        self.show()

        # Setup a timer to trigger the redraw by calling update_plot.
        self.timer_ui = QtCore.QTimer()
        self.timer_ui.setInterval(self.refreshTimeMS)
        self.timer_ui.timeout.connect(self.update_ui)
        self.timer_ui.start()

    def create_ui(self):
        """Set up the user interface, signals & slots
        """
        self.widget = QtWidgets.QWidget(self)
        self.setCentralWidget(self.widget)

        self.vplotbox = QtWidgets.QVBoxLayout()
        self.dynamic_canvas = MplCanvas(self, width=5, height=4, position=[0.05,0.1,0.925,0.85], dpi=100)
        self.vplotbox.addWidget(self.dynamic_canvas)

        self.tf_canvas = MplCanvas(self, width=5, height=4, position=[0.05,0.15,0.925,0.75], dpi=100)
        self.vplotbox.addWidget(self.tf_canvas)

        self.vplotbox.setStretchFactor(self.dynamic_canvas, 6)
        self.vplotbox.setStretchFactor(self.tf_canvas, 4)

        toolbar = QtWidgets.QToolBar("Main toolbar")
        toolbar.setIconSize(QtCore.QSize(16, 16))
        self.addToolBar(toolbar)

        self.searchbutton = QtGui.QAction("Scan", self)
        self.searchbutton.setStatusTip("Scan devices")
        self.searchbutton.triggered.connect(self.on_scan)
        self.searchbutton.setCheckable(True)
        toolbar.addAction(self.searchbutton)

        self.devlist = QtWidgets.QComboBox(self)
        self.devlist.setMinimumWidth(300)
        self.devlist.addItems(self.dev_list_name)
        toolbar.addWidget(self.devlist)

        verLabel = QtWidgets.QLabel(self)
        verLabel.setText('|')
        toolbar.addWidget(verLabel)

        self.acqbutton = QtGui.QAction("Start", self)
        self.acqbutton.setStatusTip("Start Acquisition")
        self.acqbutton.triggered.connect(self.on_start_stop)
        self.acqbutton.setCheckable(True)
        toolbar.addAction(self.acqbutton)

        verLabel = QtWidgets.QLabel(self)
        verLabel.setText('|')
        toolbar.addWidget(verLabel)

        self.recbutton = QtGui.QAction("Record on", self)
        self.recbutton.setStatusTip("Start Recording")
        self.recbutton.triggered.connect(self.on_rec)
        self.recbutton.setCheckable(True)
        toolbar.addAction(self.recbutton)

        # toolbar.addSeparator()
        verLabel = QtWidgets.QLabel(self)
        verLabel.setText('|')
        toolbar.addWidget(verLabel)

        self.scaleLabel = QtWidgets.QLabel(self)
        self.scaleLabel.setText('Scale uV')
        toolbar.addWidget(self.scaleLabel)

        self.scaleOptions = QtWidgets.QComboBox(self)
        self.scaleOptions.addItems(self.scale_list_options)
        self.scaleOptions.setCurrentIndex(
            self.scale_list_options.index(str(self.scaleDefaultOption)))
        toolbar.addWidget(self.scaleOptions)

        verLabel = QtWidgets.QLabel(self)
        verLabel.setText('|')
        toolbar.addWidget(verLabel)

        self.winsizeLabel = QtWidgets.QLabel(self)
        self.winsizeLabel.setText('WinSize sec')
        toolbar.addWidget(self.winsizeLabel)

        self.winsizeOptions = QtWidgets.QComboBox(self)
        self.winsizeOptions.addItems(self.win_size_list_options)
        self.winsizeOptions.setCurrentIndex(
            self.win_size_list_options.index(str(self.plotWinLenSec)))
        toolbar.addWidget(self.winsizeOptions)

        verLabel = QtWidgets.QLabel(self)
        verLabel.setText('|')
        toolbar.addWidget(verLabel)

        self.filter1button = QtGui.QAction("Filter off", self)
        self.filter1button.setStatusTip("Set Filter")
        self.filter1button.triggered.connect(self.on_filter1)
        self.filter1button.setCheckable(True)
        toolbar.addAction(self.filter1button)

        filterLPLabel = QtWidgets.QLabel(self)
        filterLPLabel.setText('- LP(Hz):')
        toolbar.addWidget(filterLPLabel)

        self.filterLPOptions = QtWidgets.QComboBox(self)
        self.filterLPOptions.addItems(self.filter_list_options)
        self.filterLPOptions.setCurrentIndex(self.filterCurrentFreqHzInd[0])
        self.filterLPOptions.currentIndexChanged.connect(self.on_set_filter1)
        toolbar.addWidget(self.filterLPOptions)

        filterHPLabel = QtWidgets.QLabel(self)
        filterHPLabel.setText('HP(Hz):')
        toolbar.addWidget(filterHPLabel)

        self.filterHPOptions = QtWidgets.QComboBox(self)
        self.filterHPOptions.addItems(self.filter_list_options)
        self.filterHPOptions.setCurrentIndex(self.filterCurrentFreqHzInd[1])
        self.filterHPOptions.currentIndexChanged.connect(self.on_set_filter1)
        toolbar.addWidget(self.filterHPOptions)

        verLabel = QtWidgets.QLabel(self)
        verLabel.setText('|')
        toolbar.addWidget(verLabel)

        tfLFLabel = QtWidgets.QLabel(self)
        tfLFLabel.setText('TF - LF(Hz):')
        toolbar.addWidget(tfLFLabel)

        self.tfLFOptions = QtWidgets.QComboBox(self)
        self.tfLFOptions.addItems(self.filter_list_options)
        self.tfLFOptions.setCurrentIndex(self.filter_list_options.index(str(self.tfCurrentFreqHz[0])))
        self.tfLFOptions.currentIndexChanged.connect(self.on_set_tf1)
        toolbar.addWidget(self.tfLFOptions)

        tfHFLabel = QtWidgets.QLabel(self)
        tfHFLabel.setText('HF(Hz):')
        toolbar.addWidget(tfHFLabel)

        self.tfHFOptions = QtWidgets.QComboBox(self)
        self.tfHFOptions.addItems(self.filter_list_options)
        self.tfHFOptions.setCurrentIndex(self.filter_list_options.index(str(self.tfCurrentFreqHz[-1])))
        self.tfHFOptions.currentIndexChanged.connect(self.on_set_tf1)
        toolbar.addWidget(self.tfHFOptions)


        verLabel = QtWidgets.QLabel(self)
        verLabel.setText('|')
        toolbar.addWidget(verLabel)

        self.vboxlayout = QtWidgets.QVBoxLayout()
        self.vboxlayout.addLayout(self.vplotbox)
        #self.vboxlayout.addWidget(self.positionslider)
        #self.vboxlayout.addLayout(self.hbuttonbox)

        self.setStatusBar(QtWidgets.QStatusBar(self))

        self.widget.setLayout(self.vboxlayout)

        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("&File")

        # Add actions to file menu
        close_action = QtGui.QAction("Close App", self)
        close_action.triggered.connect(self.on_close)
        file_menu.addAction(close_action)

    def start_data_stream_thread(self):
        self.dataStreamThread = threading.Thread(target=self.data_stream_thread,
                                                 args=(self,))
        self.dataStreamThread.start()

    def set_ble_eeg_hdl(self, bleEEGClassHdl):
        self.ble_main_stream_hld = bleEEGClassHdl
        self.ble_main_stream_hld.set_data_characteristic_UUID(self.eegCharacteristicUUID)
        self.ble_main_stream_hld.set_trigger_characteristic_UUID(self.triggerCharacteristicUUID)

    def set_ble_cfg_eeg_hdl(self, bleCfgEEGClassHdl):
        self.ble_cfg_eeg_hld = bleCfgEEGClassHdl
        self.ble_cfg_eeg_hld.ble_set_dev_list_hdl(self.devlist)
        self.ble_cfg_eeg_hld.ble_set_dev_list_name(self.dev_list_name)
        self.ble_cfg_eeg_hld.ble_set_dev_list_address(self.dev_list_address)

    def clear_trigger_queue(self):
        while not self.triggerQueue.empty():
            self.triggerQueue.get_nowait()

    def closeEvent(self, event):
        self.on_close()

    def on_close(self):
        self.exitFlag = True
        self.timer_ui.stop()
        if self.recFlag:
            self.recFileHdl.close()
            self.recFileTriggerHdl.close()
        if self.ble_main_stream_hld is not None:
            self.ble_main_stream_hld.ble_set_exit_flag(True)
        if self.ble_cfg_eeg_hld is not None:
            self.ble_cfg_eeg_hld.ble_set_exit_flag(True)
        time.sleep(2)
        sys.exit()

    def on_scan(self):
        self.devlist.clear()
        self.ble_cfg_eeg_hld.set_ble_scan_flag(True)
        self.ble_cfg_eeg_hld.ble_set_root_ble_name(self.root_ble_name)
        self.msgBox = QtWidgets.QMessageBox()
        self.msgBox.setText("Searching BLE devices...")
        self.msgBox.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint)
        self.msgBox.setStandardButtons(QtWidgets.QMessageBox.StandardButton.NoButton)
        self.ble_cfg_eeg_hld.ble_set_msg_box_hdl(self.msgBox)
        self.msgBox.exec()

    def on_start_stop(self):
        if self.acqbutton.text() == 'Start':
            # self.timer_ui.start()
            # self.serialHdl.open()
            dev_name = self.devlist.currentText()
            if len(dev_name) == 0:
                QtWidgets.QMessageBox.warning(self, 'No BLE device selected',
                                              'Please select a BLE device from the list or do a scan for devices first!')
                return

            self.ble_main_stream_hld.set_ble_dev_name(dev_name)
            self.ble_main_stream_hld.ble_set_notify_flag(True)
            self.acqFlag = True
            self.triggerVal = 0

            self.acqbutton.setText("Stop")
        else:
            self.acqFlag = False

            self.ble_main_stream_hld.ble_set_notify_flag(False)
            # self.serialHdl.close()
            # self.timer_ui.stop()
            if self.reStartFlag:
                self.reStartFlag = False
                self.start_stop()
            time.sleep(2.0)
            self.acqbutton.setText("Start")

    def on_filter1(self):
        if self.acqFlag and not self.filter1Flag:
            self.filter1button.setText('Filter off')
            self.filter1Flag = True
        else:
            self.filter1button.setText('Filter on')
            self.filter1Flag = False

    def on_set_filter1(self):
        lpFreqHz = np.double(self.filterLPOptions.currentText())
        hpFreqHz = np.double(self.filterHPOptions.currentText())
        if (hpFreqHz - lpFreqHz) <= 0:
            QtWidgets.QMessageBox.warning(self, 'Filter settings',
                                          'High-Pass cut frequency should be higher than Low-Pass cut frequency!')
            self.filterLPOptions.setCurrentIndex(self.filterCurrentFreqHzInd[0])
            self.filterHPOptions.setCurrentIndex(self.filterCurrentFreqHzInd[1])
            return
        print('[ViewEXG] - Setting filter LP: ', lpFreqHz, ' HP: ', hpFreqHz)
        self.filterTaps = sigpro.f_GetFIRBPKaiserFilter(self.dataFsHz, [lpFreqHz, hpFreqHz])
        self.filterCurrentFreqHzInd = [self.filterLPOptions.currentIndex(), self.filterHPOptions.currentIndex()]

    def on_set_tf1(self):
        lpFreqHz = np.double(self.tfLFOptions.currentText())
        hpFreqHz = np.double(self.tfHFOptions.currentText())
        if (hpFreqHz - lpFreqHz) < 5:
            QtWidgets.QMessageBox.warning(self, 'TF settings',
                                          'High frequency should be higher than Low frequency by at least 5 Hz!')
            self.tfLFOptions.setCurrentIndex(self.tfCurrentFreqHz[0])
            self.tfHFOptions.setCurrentIndex(self.tfCurrentFreqHz[1])
            return
        print('[ViewEXG] - Setting TF frequencies LP: ', lpFreqHz, ' HP: ', hpFreqHz)
        self.tfCurrentFreqHz = [lpFreqHz, hpFreqHz]
        self.tfUpdateFreqs = True

    def on_rec(self):
        if self.acqFlag and not self.recFlag:
            dateNow = datetime.now()
            if not os.path.isdir('./data/'):
                os.mkdir('./data/')
            self.recFileName = './data/{}_{}{:02}{:02}_{:02}{:02}{:02}_{}Hz'.\
                format(self.ble_main_stream_hld.get_ble_dev_name(), dateNow.year, dateNow.month,
                       dateNow.day, dateNow.hour, dateNow.minute,
                       dateNow.second, int(self.dataFsHz))
            self.recFileTriggerName = self.recFileName + '_trigger.data'
            self.recFileName = self.recFileName + '.data'
            try:
                self.recFileHdl = open(self.recFileName, 'wb')
                self.recFileTriggerHdl = open(self.recFileTriggerName, 'wb')
                self.recFlag = True
                self.recbutton.setText("Record off")
            except Exception as excep_info:
                print('[ViewEXG] - Exception creating file: ', excep_info)
        else:
            try:
                self.recFlag = False
                self.recFileHdl.close()
                self.recFileTriggerHdl.close()
                self.recbutton.setText("Record on")
            except Exception as excep_info:
                print('[ViewEXG] - Exception closing file: ', excep_info)

    def data_stream_thread(self, parentHdl):
        print('[ViewEXG] - Starting data_stream_thread')
        dataQueue = self.ble_main_stream_hld.get_conv_data_queue()
        triggerQueue = self.ble_main_stream_hld.get_conv_trigger_queue()
        timePeriod = 1.0 / self.dataFsHz
        while 1:
            if self.exitFlag:
                break
            try:
                if self.acqFlag:
                    dataArray = dataQueue.get()

                    if len(dataArray) == 0:
                        continue

                    timeValue = np.float32(dataArray[0])
                    dataArray = np.float32(dataArray[1])

                    if self.recFlag:
                        dataValuesBin = st.pack('f', timeValue)
                        parentHdl.recFileHdl.write(dataValuesBin)
                        dataValuesBin = st.pack('f' * len(dataArray), *dataArray)
                        parentHdl.recFileHdl.write(dataValuesBin)
                        parentHdl.recFileHdl.flush()

                    timeArray = timePeriod * np.arange(len(dataArray))
                    timeArray += timeValue
                    timeArray = np.mod(timeArray, 512.0)
                    parentHdl.bufferInd += 1
                    bufferI1 = self.bufferInd
                    bufferI2 = bufferI1 + len(dataArray)
                    if bufferI2 <= self.dataBuffer.size:
                        parentHdl.dataBuffer[bufferI1:bufferI2] = dataArray
                        parentHdl.timeBuffer[bufferI1:bufferI2] = timeArray
                        parentHdl.bufferInd = bufferI2 - 1
                    else:
                        parentHdl.dataBuffer[bufferI1:] = dataArray[:(self.dataBuffer.size - bufferI1)]
                        parentHdl.dataBuffer[:(bufferI2 - self.dataBuffer.size)] = dataArray[(self.dataBuffer.size - bufferI1):]
                        parentHdl.timeBuffer[bufferI1:] = timeArray[:(self.dataBuffer.size - bufferI1)]
                        parentHdl.timeBuffer[:(bufferI2 - self.dataBuffer.size)] = timeArray[(self.dataBuffer.size - bufferI1):]
                        parentHdl.bufferInd = bufferI2 - self.dataBuffer.size

                    if parentHdl.bufferInd >= self.dataBuffer.size:
                        parentHdl.bufferInd = 0

                    if not triggerQueue.empty():
                        dataTrigger = triggerQueue.get_nowait()
                        dataTrigger = np.float32(dataTrigger[0])
                        # WARNING: check the size of this queue if it grows and grows
                        self.triggerQueue.put(dataTrigger)
                        print('[ViewEXG] - Trigger received: ', dataTrigger)
                        # print('[ViewEXG] - Time value: ', timeValue)
                        if self.recFlag:
                            dataValuesBin = st.pack('f', dataTrigger)
                            parentHdl.recFileTriggerHdl.write(dataValuesBin)
                else:
                    time.sleep(0.01)

            except Exception as excep_info:
                print('[ViewEXG] - Exception in data_stream_thread: ',
                      excep_info)
        print('[ViewEXG] - data_stream_thread is end!')

    def update_ui(self):
        currWinSize = np.double(self.winsizeOptions.currentText())
        if self.plotRef is None or currWinSize != self.plotWinLenSec or self.tfUpdateFreqs:
            self.plotWinLenSec = currWinSize
            self.plotWinLenSam = int(self.plotWinLenSec * self.dataFsHz)
            self.bufferPlotInd = -1
            self.tfUpdateFreqs = False

            # First time we have no plot reference, so do a normal plot.
            # .plot returns a list of line <reference>s, as we're
            # only getting one we can take the first element.
            self.xdata = np.double(list(range(self.plotWinLenSam)))
            self.xdata = self.xdata / self.dataFsHz
            self.xdataTicks = np.arange(self.xdata[0], self.xdata[-1], 1.0)
            self.xdataTicks = self.xdataTicks[1:]
            # self.ydata = [random.randint(0, 1) for i in range(self.n_data)]
            self.ydata = np.zeros(self.plotWinLenSam)
            if self.plotRef is None:
                self.plotParentRefs = self.dynamic_canvas.axes.plot(self.xdata, self.ydata, 'r', linewidth=1)
                self.plotRef = self.plotParentRefs[0]
            else:
                self.plotRef.set_xdata(self.xdata)
                self.plotRef.set_ydata(self.ydata)

            self.dynamic_canvas.axes.set_xlim([self.xdata[0],self.xdata[-1]])
            self.dynamic_canvas.axes.set_xticks(self.xdataTicks)
            self.dynamic_canvas.axes.grid()

            self.dynamic_canvas.draw()

            self.tfElapsedTimeSec = 0
            self.tfMat, self.tfTimeArrayHz, self.tfFreqArrayHz = \
                sigpro.f_GaborTFTransform(self.xdata, self.dataFsHz, self.tfCurrentFreqHz[0],
                                          self.tfCurrentFreqHz[-1], self.tfFreqResHz, self.tfNumofCycles)
            # self.tfMat = np.abs(self.tfMat)
            self.tfMat = np.zeros((len(self.tfFreqArrayHz), len(self.xdata)))
            self.tfPlotRef = self.tf_canvas.axes.imshow(np.abs(self.tfMat), cmap='viridis', interpolation='none',
                                                        origin='lower', aspect='auto',
                                                        extent=[self.tfTimeArrayHz[0], self.tfTimeArrayHz[-1],
                                                                self.tfFreqArrayHz[0], self.tfFreqArrayHz[-1]])
            self.tf_canvas.axes.set_xlim([self.tfTimeArrayHz[0], self.tfTimeArrayHz[-1]])
            xDataTicks = np.arange(self.tfTimeArrayHz[0], self.tfTimeArrayHz[-1], 1.0)
            xDataTicks = xDataTicks[1:]
            self.tf_canvas.axes.set_xticks(xDataTicks)

            # self.tf_canvas.axes.set_xlabel('Time (Sec)')
            self.tf_canvas.axes.set_ylabel('Freq. (Hz)')
            self.tf_canvas.draw()
            #return

        if not self.acqFlag or self.bufferInd < 0:
            return

        if self.bufferIndAux == self.bufferInd:
            return

        indBufferIni = self.bufferIndAux + 1
        indBufferEnd = self.bufferInd
        # print(indBufferIni, indBufferEnd)
        if indBufferEnd > indBufferIni:
            dataSigPlot = self.dataBuffer[indBufferIni:indBufferEnd + 1]
        else:
            dataSigPlot = self.dataBuffer[indBufferIni:]
            dataSigPlot = np.concatenate((dataSigPlot, self.dataBuffer[:indBufferEnd + 1]), axis=0)

        dataSigTF = dataSigPlot
        # #####indEndAux = self.bufferPlotInd + 1 + len(dataSigPlot) - 1
        # #####dataSigTF =

        if self.filter1Flag:
            indIni = indBufferIni - len(self.filterTaps) - 1
            #print(len(self.filterTaps), indIni)
            if indIni < 0:
                dataSigCI = self.dataBuffer[indIni:]
                dataSigCI = np.concatenate((dataSigCI, self.dataBuffer[:indBufferIni + 1]), axis=0)
            else:
                dataSigCI = self.dataBuffer[indIni:indBufferIni]

            dataSigFilt = dataSigCI
            dataSigFilt = np.concatenate((dataSigFilt, dataSigPlot), axis=0)
            dataSigFilt = dataSigFilt - np.mean(dataSigFilt)
            dataSigFilt = signal.lfilter(self.filterTaps, 1, dataSigFilt)
            dataSigPlot = dataSigFilt[-len(dataSigPlot):]
        else:
            dataSigPlot = dataSigPlot - np.mean(dataSigPlot)

        if len(dataSigPlot) > self.plotWinLenSam:
            dataSigPlot = dataSigPlot[-self.plotWinLenSam + 1:]
            dataSigTF = dataSigTF[-self.plotWinLenSam + 1:]
            print('[ViewEXG] - Warning: len(dataSigPlot) > self.plotWinLenSam')

        indIni = self.bufferPlotInd + 1
        indEnd = indIni + len(dataSigPlot) - 1
        indIniTF = indIni
        indEndTF = indEnd
        # print(len(self.ydata), len(dataSigPlot), indIni, indEnd)
        if indEnd >= self.plotWinLenSam:
            self.ydata[indIni:] = dataSigPlot[:self.plotWinLenSam - indIni]
            indEnd -= self.plotWinLenSam
            self.ydata[:indEnd + 1] = dataSigPlot[self.plotWinLenSam - indIni:]
        else:
            self.ydata[indIni:indEnd + 1] = dataSigPlot

        # self.ydata = self.ydata - np.mean(self.ydata)
        #self.ydata = dataSigPlot
        #self.ydata = [random.random() for i in range(self.plotWinLenSam)]
        #print(dataSigPlot)
        self.plotRef.set_ydata(self.ydata)
        scaleVal = self.scaleOptions.currentText()
        self.dynamic_canvas.axes.set_ylim([-1.0 * np.double(scaleVal), np.double(scaleVal)])
        self.dynamic_canvas.draw()

        # ###### Time-Frequency plot
        indIni = indBufferIni - self.tfWinSizeSam - 1
        # print(len(self.filterTaps), indIni)
        if indIni < 0:
            dataSigCI = self.dataBuffer[indIni:]
            dataSigCI = np.concatenate((dataSigCI, self.dataBuffer[:indBufferIni + 1]), axis=0)
        else:
            dataSigCI = self.dataBuffer[indIni:indBufferIni]

        dataSigFilt = dataSigCI
        dataSigFilt = np.concatenate((dataSigFilt, dataSigTF), axis=0)
        dataSigFilt = dataSigFilt - np.mean(dataSigFilt)
        tfMatAux, self.tfTimeArrayHz, self.tfFreqArrayHz = \
            sigpro.f_GaborTFTransform(dataSigFilt, self.dataFsHz, self.tfCurrentFreqHz[0],
                                      self.tfCurrentFreqHz[-1], self.tfFreqResHz, self.tfNumofCycles)
        tfMatAux = tfMatAux[:, -len(dataSigTF):]
        tfMatAux = np.abs(tfMatAux)
        tfMatAux = sigpro.f_TFNormToZScore(tfMatAux.transpose())
        tfMatAux = tfMatAux.transpose()

        if indEndTF >= self.plotWinLenSam:
            self.tfMat[:, indIniTF:] = tfMatAux[:, :self.plotWinLenSam - indIniTF]
            indEndTF -= self.plotWinLenSam
            self.tfMat[:, :indEndTF + 1] = tfMatAux[:, self.plotWinLenSam - indIniTF:]
        else:
            self.tfMat[:, indIniTF:indEndTF + 1] = tfMatAux

        tfMatAux = self.tfMat
        tfMatAux[:, :indEndTF] = gaussian_filter(self.tfMat[:, :indEndTF], sigma=[0, 2])
        tfMatAux[:, indEndTF:] = gaussian_filter(self.tfMat[:, indEndTF:], sigma=[0, 2])
        self.tfPlotRef.set_data(tfMatAux)
        # self.tfPlotRef.set_data(self.tfMat)
        # print(np.min(self.tfMat), np.max(self.tfMat))
        # self.tfPlotRef.set_clim(np.min(self.tfMat), np.max(self.tfMat))
        self.tfPlotRef.set_clim(-1, 2)
        #self.tfPlotRef.set_clim(-2, 2)
        self.tf_canvas.draw()

        self.bufferIndAux = indBufferEnd
        self.bufferPlotInd = indEnd

app = QtWidgets.QApplication(sys.argv)
mainWinHdl = MainWindow()
bleCfgEEGClassHdl = bleCfgClass()
mainWinHdl.set_ble_cfg_eeg_hdl(bleCfgEEGClassHdl)
bleEEGClassHdl = bleClass()
mainWinHdl.set_ble_eeg_hdl(bleEEGClassHdl)
mainWinHdl.start_data_stream_thread()
app.exec()
