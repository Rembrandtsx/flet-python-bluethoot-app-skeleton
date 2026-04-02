package dev.flet.ble;

import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;

/**
 * Concrete {@link BluetoothGattCallback} wired from Python via Pyjnius.
 * Python implements {@link Events} (a real Java interface); Pyjnius cannot extend
 * abstract classes like BluetoothGattCallback directly (Proxy is interface-only).
 */
public class BleGattBridge extends BluetoothGattCallback {

    public interface Events {
        void onConnectionStateChange(BluetoothGatt gatt, int status, int newState);

        void onServicesDiscovered(BluetoothGatt gatt, int status);

        void onCharacteristicChanged(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic);

        void onDescriptorWrite(BluetoothGatt gatt, BluetoothGattDescriptor descriptor, int status);
    }

    private Events events;

    public void setEvents(Events e) {
        this.events = e;
    }

    @Override
    public void onConnectionStateChange(BluetoothGatt gatt, int status, int newState) {
        if (events != null) {
            events.onConnectionStateChange(gatt, status, newState);
        }
    }

    @Override
    public void onServicesDiscovered(BluetoothGatt gatt, int status) {
        if (events != null) {
            events.onServicesDiscovered(gatt, status);
        }
    }

    @Override
    public void onCharacteristicChanged(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic) {
        if (events != null) {
            events.onCharacteristicChanged(gatt, characteristic);
        }
    }

    @Override
    public void onDescriptorWrite(BluetoothGatt gatt, BluetoothGattDescriptor descriptor, int status) {
        if (events != null) {
            events.onDescriptorWrite(gatt, descriptor, status);
        }
    }
}
