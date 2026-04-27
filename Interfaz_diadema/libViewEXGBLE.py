# libViewEXGBLE.py
# Description:
# Library containing functions to handle the Bluetooth Low Energy connection
# with the acquisition board.
# Author: Mario Valderrama

import time
import queue
import asyncio
import threading
import numpy as np
import struct as st
from bleak import BleakScanner, BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic


def bleCfgThread(parentHdl):
    while 1:
        if parentHdl.bleExitFlag:
            print("[libViewEXGBLE] - bleCfgThread is end!")
            break
        if not parentHdl.bleScanDevFlag:
            time.sleep(2)
            continue
        try:
            parentHdl.bleScanDevFlag = False
            asyncio.run(bleDiscoverDev(parentHdl))
        except Exception as excep_info:
            print('[libViewEXGBLE] - Exception in bleDiscoverDev: ', excep_info)


async def bleDiscoverDev(parentHdl):
    try:
        devices = await BleakScanner.discover(timeout=parentHdl.bleDiscoverTimeout)
        parentHdl.dev_list_name.clear()
        parentHdl.dev_list_address.clear()
        lenind = len(parentHdl.root_ble_name)
        for d in devices:
            if d.name is not None:
                if lenind == 0 or d.name[:lenind] == \
                        parentHdl.root_ble_name:
                    parentHdl.dev_list_name.append(d.name)
                    parentHdl.dev_list_address.append(d.address)
                # else:
                #     if   # if the name of the device starts with the root name
                #         # add the device to the list of devices
                #         parentHdl.dev_list_address.append(d.address)
                #         print(d.address)
        parentHdl.devlist.addItems(parentHdl.dev_list_name)
    except Exception as excep_info:
        print('[libViewEXGBLE] - Exception in discover ble devices: ', excep_info)
    parentHdl.msgBox.deleteLater()


class bleCfgClass():

    def __init__(self, *args, **kwargs):
        self.bleScanDevFlag = False
        self.bleExitFlag = False
        self.bleDiscoverTimeout = 10
        self.root_ble_name = []
        self.dev_list_name = []
        self.dev_list_address = []
        self.devlist = None
        self.msgBox = None
        bleMainThreadHdl = threading.Thread(target=bleCfgThread,
                                            args=(self,))
        bleMainThreadHdl.start()

    def set_ble_discover_timeout(self, bleDiscoverTimeout):
        self.bleDiscoverTimeout = bleDiscoverTimeout

    def set_ble_scan_flag(self, bleScanFlag):
        self.bleScanDevFlag = bleScanFlag

    def ble_set_exit_flag(self, exitFlag):
        self.bleExitFlag = exitFlag

    def ble_set_dev_list_name(self, devListName):
        self.dev_list_name = devListName

    def ble_set_dev_list_address(self, devListAddress):
        self.dev_list_address = devListAddress

    def ble_set_dev_list_hdl(self, devListHdl):
        self.devlist = devListHdl

    def ble_set_msg_box_hdl(self, msgBoxHdl):
        self.msgBox = msgBoxHdl

    def ble_set_root_ble_name(self, rootBleName):
        self.root_ble_name = rootBleName


async def bleMainLoop(parentHdl):
    while 1:
        if parentHdl.bleExitFlag or not parentHdl.bleNotifyFlag:
            print("[libViewEXGBLE] - bleMainLoop is end!")
            break
        print("[libViewEXGBLE] - Starting scan...")

        device = await BleakScanner.find_device_by_name(
            parentHdl.bleDevName)
        if device is None:
            print("[libViewEXGBLE] - Could not find device: ",
                  parentHdl.bleDevName)
            await asyncio.sleep(5.0)
            continue

        print("[libViewEXGBLE] - Connecting to device: ",
              parentHdl.bleDevName)

        async with BleakClient(device) as client:
            if not client.is_connected:
                print('[libViewEXGBLE] - Could not connect to device with name: ',
                      parentHdl.bleDevName)
                await asyncio.sleep(5.0)
                continue
            print("[libViewEXGBLE] - Connected to device: ",
                  parentHdl.bleDevName)
            parentHdl.ble_set_current_client_hdl(client)

            # This part can be useful in the future to automatically get
            # the uuid of different services
            # services = client.services
            # for service in services:
            #     # print('\nservice', service.handle, service.uuid, service.description)
            #     characteristics = service.characteristics
            #     for char in characteristics:
            #         # print('  characteristic', char.handle, char.uuid, char.description, char.properties)
            #         if 'notify' in char.properties:
            #             parentHdl.uuid_list.append(char.uuid)
            #         # descriptors = char.descriptors
            #         # for desc in descriptors:
            #         #     print('    descriptor', desc)

            await client.start_notify(parentHdl.dataCharacteristicUUID,
                                      parentHdl.ble_notification_handler)
            # await client.start_notify(parentHdl.triggerCharacteristicUUID,
            #                           parentHdl.ble_trigger_notification_handler)
            while 1:
                if not client.is_connected:
                    print("[libViewEXGBLE] - Connection lost with device: ",
                          parentHdl.bleDevName)
                    break
                if parentHdl.bleExitFlag or not parentHdl.bleNotifyFlag:
                    break
                await asyncio.sleep(2.0)
            if not client.is_connected:
                continue
            else:
                await client.stop_notify(parentHdl.dataCharacteristicUUID)
                # await client.stop_notify(parentHdl.triggerCharacteristicUUID)


def bleMainThread(parentHdl):
    try:
        asyncio.run(bleMainLoop(parentHdl))
    except Exception as excep_info:
        print('[libViewEXGBLE] - Exception in bleMainThread: ', excep_info)


class bleClass():

    def __init__(self, *args, **kwargs):
        self.bleDevName = ''
        self.dataCharacteristicUUID = ''
        self.triggerCharacteristicUUID = ''
        self.vRef = 1.8
        self.devGain = 10 ** 6
        self.bleNotifyFlag = False
        self.bleExitFlag = False
        self.dataStreamQueue = queue.Queue()
        self.triggerStreamQueue = queue.Queue()

    def set_data_characteristic_UUID(self, bleUUIDStr):
        self.dataCharacteristicUUID = bleUUIDStr

    def set_trigger_characteristic_UUID(self, bleUUIDStr):
        self.triggerCharacteristicUUID = bleUUIDStr

    def set_ble_dev_name(self, bleDevNameStr):
        self.bleDevName = bleDevNameStr

    def get_ble_dev_name(self):
        return self.bleDevName

    def ble_set_notify_flag(self, notifyFlag):
        if self.bleNotifyFlag == notifyFlag:
            return
        self.bleNotifyFlag = notifyFlag
        if notifyFlag:
            bleMainThreadHdl = threading.Thread(target=bleMainThread,
                                                args=(self,))
            bleMainThreadHdl.start()

    def ble_set_current_client_hdl(self, bleClient):
        self.bleClient = bleClient

    def ble_set_exit_flag(self, exitFlag):
        self.bleExitFlag = exitFlag

    def get_conv_data_queue(self):
        return self.dataStreamQueue

    def get_conv_trigger_queue(self):
        return self.triggerStreamQueue

    def ble_notification_handler(self, characteristic: BleakGATTCharacteristic,
                                 data: bytearray):
        """Simple notification handler which prints the data received."""
        timeValue, dataArray = self.convert_bin_to_raw_data(data)
        # print(timeValue, dataArray)
        self.dataStreamQueue.put([[timeValue], dataArray])

    def ble_trigger_notification_handler(self, characteristic: BleakGATTCharacteristic,
                                         data: bytearray):
        """Simple notification handler which prints the data received."""
        timeValue = self.convert_bin_to_raw_time(data)
        # print(timeValue)
        self.triggerStreamQueue.put([[timeValue]])

    def convert_bin_to_raw_data(self, data2Convert):

        dataArray = st.unpack('h' * int(len(data2Convert) / 2), data2Convert)
        timeValue = dataArray[0]
        dataArray = dataArray[1:]

        return timeValue, dataArray

    def convert_bin_to_raw_time(self, data2Convert):

        dataArray = st.unpack('h' * int(len(data2Convert) / 2), data2Convert)
        timeValue = dataArray[0]

        return timeValue
