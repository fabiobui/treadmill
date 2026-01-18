#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later

import dbus
import dbus.mainloop.glib
import dbus.service
import time

from gi.repository import GLib
from random import randint
from dbus.service import signal


############################
# Constants
############################
BLUEZ_SERVICE_NAME = 'org.bluez'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
DBUS_OM_IFACE      = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE    = 'org.freedesktop.DBus.Properties'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE    = 'org.bluez.GattCharacteristic1'
ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
ADVERTISEMENT_IFACE = 'org.bluez.LEAdvertisement1'

# Treadmill Service + Treadmill Data Characteristic
TREADMILL_SERVICE_UUID      = "00001826-0000-1000-8000-00805f9b34fb"
TREADMILL_DATA_CHAR_UUID    = "00002acd-0000-1000-8000-00805f9b34fb"

mainloop = None

############################
# D-Bus Exceptions
############################
class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.freedesktop.DBus.Error.InvalidArgs'

class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotSupported'

############################
# Application
############################
class Application(dbus.service.Object):
    """
    Minimal GATT Application with one Treadmill Service.
    """
    def __init__(self, bus, treadmill_app):
        """
        We receive a reference to the parent TreadmillApp,
        so we can pass it down to the characteristic.
        """
        self.path = '/'
        self.services = []
        self.treadmill_app = treadmill_app
        dbus.service.Object.__init__(self, bus, self.path)

        # Add our single Treadmill service
        self.add_service(TreadmillService(bus, 0, treadmill_app))

        # Add Heart Rate Service
        self.add_service(HeartRateService(bus, 1, treadmill_app))

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        """
        Called by BlueZ to enumerate all objects (services, characteristics).
        """
        response = {}
        print("GetManagedObjects called")

        for service in self.services:
            response[service.get_path()] = service.get_properties()
            for chrc in service.get_characteristics():
                response[chrc.get_path()] = chrc.get_properties()

        return response

############################
# Base Service
############################
class Service(dbus.service.Object):
    PATH_BASE = '/org/bluez/example/service'

    def __init__(self, bus, index, uuid, primary):
        self.bus = bus
        self.path = f"{self.PATH_BASE}{index}"
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                'UUID': self.uuid,
                'Primary': self.primary,
                'Characteristics': dbus.Array(
                    self.get_characteristic_paths(),
                    signature='o'
                )
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, chrc):
        self.characteristics.append(chrc)

    def get_characteristic_paths(self):
        return [c.get_path() for c in self.characteristics]

    def get_characteristics(self):
        return self.characteristics

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_SERVICE_IFACE]

############################
# Base Characteristic
############################
class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.bus = bus
        self.path = service.get_path() + '/char' + str(index)
        self.uuid = uuid
        self.flags = flags
        self.service = service
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                'Service': self.service.get_path(),
                'UUID': self.uuid,
                'Flags': self.flags,
                'Descriptors': dbus.Array([], signature='o')
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='a{sv}', out_signature='ay')
    def ReadValue(self, options):
        print("Default ReadValue called, returning error")
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        print("Default WriteValue called, returning error")
        raise NotSupportedException()

############################
# Treadmill Service / Characteristic
############################
class TreadmillService(Service):
    def __init__(self, bus, index, treadmill_app):
        super().__init__(bus, index, TREADMILL_SERVICE_UUID, True)
        # Add treadmill data characteristic
        self.add_characteristic(TreadmillDataCharacteristic(bus, 0, self, treadmill_app))


class TreadmillDataCharacteristic(Characteristic):
    """
    The Treadmill Data Characteristic (0x2ACD).
    We'll pull speed/distance/energy/time from the TreadmillApp
    in _send_measurement().
    """
    def __init__(self, bus, index, service, treadmill_app):
        super().__init__(
            bus,
            index,
            TREADMILL_DATA_CHAR_UUID,
            ['notify'],  # notify only
            service
        )
        self.notifying = False

        # Keep a reference to the TreadmillApp object
        self.treadmill_app = treadmill_app

    @signal(DBUS_PROP_IFACE, signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        if self.notifying:
            return
        self.notifying = True
        GLib.timeout_add(1000, self._send_measurement)

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        self.notifying = False

    def _send_measurement(self):
        """
        Called every second by GLib.timeout_add. We read the current
        speed, distance, time, energy from the TreadmillApp's
        shared variables, then build the Treadmill Data packet.
        """
        if not self.notifying:
            return False

        (speed_m_s, distance_m, energy, bpm, elapsed_s) = self.treadmill_app.get_measures()

        # Convert speed => 1/256 m/s
        speed_256 = int(speed_m_s * 100)
        distance_int = int(distance_m)
        energy = int(energy)

        # Flags for Distance (bit2), Expended Energy (bit7), and Elapsed Time (bit10)
        flags_low  = 0x84
        flags_high = 0x04

        val = [
            dbus.Byte(flags_low),
            dbus.Byte(flags_high),

            # Speed (2 bytes)
            dbus.Byte(speed_256 & 0xFF),
            dbus.Byte((speed_256 >> 8) & 0xFF),

            # Distance (3 bytes)
            dbus.Byte(distance_int & 0xFF),
            dbus.Byte((distance_int >> 8) & 0xFF),
            dbus.Byte((distance_int >> 16) & 0xFF),

            # Expended Energy (2 bytes)
            dbus.Byte(energy & 0xFF),
            dbus.Byte((energy >> 8) & 0xFF),

            # 3 placeholder bytes
            dbus.Byte(0x00),
            dbus.Byte(0x00),
            dbus.Byte(0x00),


            # Elapsed Time (2 bytes)
            dbus.Byte(elapsed_s & 0xFF),
            dbus.Byte((elapsed_s >> 8) & 0xFF),
        ]

        print(f"[Notify] Speed={speed_m_s:.2f} m/s, Dist={distance_m:.1f}m, "
              f"Energy={energy}, Bpm={bpm}, Time={elapsed_s}s")

        self.PropertiesChanged(
            GATT_CHRC_IFACE,
            {'Value': dbus.Array(val, signature='y')},
            []
        )

        return True  # keep scheduling


############################
# Heart Service / Characteristic
############################


class HeartRateService(Service):
    """
    GATT Service for Heart Rate.
    """
    def __init__(self, bus, index, treadmill_app):
        super().__init__(bus, index, "0000180D-0000-1000-8000-00805f9b34fb", True)
        self.add_characteristic(HeartRateMeasurementCharacteristic(bus, 0, self, treadmill_app))


class HeartRateMeasurementCharacteristic(Characteristic):
    """
    GATT Characteristic for Heart Rate Measurement.
    """
    def __init__(self, bus, index, service, treadmill_app):
        super().__init__(
            bus,
            index,
            "00002A37-0000-1000-8000-00805f9b34fb",  # Heart Rate Measurement UUID
            ['notify'],  # Supports notifications
            service
        )
        self.notifying = False
        # Keep a reference to the TreadmillApp object
        self.treadmill_app = treadmill_app

    @signal(DBUS_PROP_IFACE, signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        if self.notifying:
            return
        self.notifying = True
        GLib.timeout_add(1000, self._send_heart_rate)

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        self.notifying = False

    def _send_heart_rate(self):
        if not self.notifying:
            return False

        (speed_m_s, distance_m, energy, bpm, elapsed_s) = self.treadmill_app.get_measures()

        heart_rate = int(bpm)  # Simulated heart rate (60-100 bpm)
        #print(f"Hert rate: {heart_rate}")
        flags = 0x00  # Flags for an 8-bit heart rate value

        value = [
            dbus.Byte(flags),       # Flags
            dbus.Byte(heart_rate),  # Heart rate value
        ]

        print(f"[Heart Rate Notify] BPM={heart_rate}")

        self.PropertiesChanged(
            GATT_CHRC_IFACE,
            {'Value': dbus.Array(value, signature='y')},
            []
        )
        return True



############################
# Advertisement
############################
class Advertisement(dbus.service.Object):
    PATH_BASE = '/org/bluez/example/advertisement'

    def __init__(self, bus, index, ad_type):
        self.path = f"{self.PATH_BASE}{index}"
        self.bus = bus
        self.ad_type = ad_type
        self.service_uuids = []
        self.manufacturer_data = {}
        self.solicit_uuids = []
        self.data = {}
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service_uuid(self, uuid):
        self.service_uuids.append(uuid)

    def get_properties(self):
        return {
            ADVERTISEMENT_IFACE: {
                'Type': self.ad_type,
                'ServiceUUIDs': dbus.Array(self.service_uuids, signature='s'),
                'ManufacturerData': dbus.Dictionary(self.manufacturer_data, signature='qv'),
                'SolicitUUIDs': dbus.Array(self.solicit_uuids, signature='s'),
                'Data': dbus.Dictionary(self.data, signature='sv'),
                'Discoverable': True,  # Allow discovery
                'Secure': False  # Disable secure connections
            }
        }

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != ADVERTISEMENT_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[ADVERTISEMENT_IFACE]

    @dbus.service.method(ADVERTISEMENT_IFACE)
    def Release(self):
        print(f"{self.path}: Released")


############################
# Pairing Agent
############################
class PairingAgent(dbus.service.Object):
    AGENT_PATH = "/org/bluez/example/agent"

    def __init__(self, bus):
        dbus.service.Object.__init__(self, bus, self.AGENT_PATH)

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        print(f"RequestPinCode for device: {device}")
        return "1234"  # Return a fixed PIN code

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        print(f"RequestPasskey for device: {device}")
        return dbus.UInt32(123456)  # Return a fixed passkey

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def DisplayPasskey(self, device, passkey):
        print(f"DisplayPasskey for device {device}: {passkey}")

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        print(f"RequestConfirmation for passkey {passkey} on device {device}")
        # Automatically confirm pairing
        return

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Release(self):
        print("Pairing agent released")

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self):
        print("Pairing canceled")


############################
# Registration Helpers
############################

def find_adapter(bus, adapter_name="hci1"):
    """Return the path of the specified adapter that has GattManager1."""
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'),
                               DBUS_OM_IFACE)
    objects = remote_om.GetManagedObjects()
    for path, ifaces in objects.items():
        if GATT_MANAGER_IFACE in ifaces:
            # Check if this is the adapter we're looking for
            if adapter_name in path:
                return path
    return None

def set_bluetooth_name(bus, adapter_path, name):
    """Set the alias (Bluetooth name) of the adapter."""
    adapter_props = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
        DBUS_PROP_IFACE
    )
    try:
        adapter_props.Set("org.bluez.Adapter1", "Alias", dbus.String(name))
        print(f"Bluetooth name set to: {name}")
    except dbus.DBusException as e:
        print(f"Failed to set Bluetooth name: {str(e)}")

def setup_pairing_agent(bus):
    """Setup the pairing agent to disable pairing code."""
    print("Skipping pairing agent setup for no pairing requirement.")
    # Commented out to avoid D-Bus main loop issues
    # The pairing agent requires the main loop to be running
    # but we call this before starting the main loop
    return
    
    # """Setup the pairing agent and make it the default."""
    # agent = PairingAgent(bus)
    # manager = dbus.Interface(
    #     bus.get_object("org.bluez", "/org/bluez"),
    #     "org.bluez.AgentManager1"
    # )
    #
    # # Register the pairing agent
    # manager.RegisterAgent(PairingAgent.AGENT_PATH, "KeyboardDisplay")
    # print("Pairing agent registered with capability: KeyboardDisplay")
    #
    # # Set it as the default agent
    # manager.RequestDefaultAgent(PairingAgent.AGENT_PATH)
    # print("Pairing agent set as default")

def restart_adapter(bus, adapter_path):
    """Restart the Bluetooth adapter to apply changes."""
    props = dbus.Interface(
        bus.get_object("org.bluez", adapter_path),
        "org.freedesktop.DBus.Properties"
    )
    try:
        props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(False))
        time.sleep(0.5)
        props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(True))
        print("Bluetooth adapter restarted")
    except dbus.DBusException as e:
        print(f"Failed to restart adapter: {str(e)}")

def register_ad_cb():
    print("Advertisement registered")

def register_ad_error_cb():
    global mainloop
    print("Failed to register advertisement")
    mainloop.quit()

def register_app_cb():
    print("GATT application registered (Treadmill).")

def register_app_error_cb():
    global mainloop
    print("Failed to register application")
    mainloop.quit()


############################
# The Class: TreadmillSimulate
############################
class TreadmillSimulate:
    """
    A class that encapsulates the fake treadmill GATT server logic.
    You can set speed/distance/energy/time using set_measures(...)
    Then the TreadmillDataCharacteristic will read them each second.
    """
    def __init__(self, device_name="Test-Treadmill", adapter="hci1"):
        global mainloop
        self.device_name = device_name
        self.adapter = adapter  # Bluetooth adapter to use for broadcast
        mainloop = None

        # "Live" treadmill data that the characteristic will read
        self.speed_m_s = 0.0  # default 3 km/h
        self.distance_m = 0.0
        self.energy = 0
        self.bpm = 0
        self.elapsed_s = 0

    def set_measures(self, speed_m_s=None, distance_m=None, energy=None, bpm=None, elapsed_s=None):
        """
        Update treadmill data. These are read each second
        by TreadmillDataCharacteristic::_send_measurement().
        """
        if speed_m_s is not None:
            self.speed_m_s = speed_m_s
        if distance_m is not None:
            self.distance_m = distance_m
        if energy is not None:
            self.energy = energy
        if bpm is not None:
            self.bpm = bpm
        if elapsed_s is not None:
            self.elapsed_s = elapsed_s

    def get_measures(self):
        """Return the current (speed, distance, energy, time)."""
        return (
            self.speed_m_s,
            self.distance_m,
            self.energy,
            self.bpm,
            self.elapsed_s
        )

    def start(self):
        global mainloop
        # D-Bus main loop is now configured globally in app.py
        bus = dbus.SystemBus()

        adapter_path = find_adapter(bus, self.adapter)
        if not adapter_path:
            print(f"GattManager1 interface not found on {self.adapter}. Is bluetoothd running with --experimental?")
            return
        print(f"Using adapter {self.adapter} ({adapter_path}) for broadcast")

        # Set the Bluetooth device name
        set_bluetooth_name(bus, adapter_path, self.device_name)
        restart_adapter(bus, adapter_path)

        # Set up the pairing agent
        setup_pairing_agent(bus)

        service_manager = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
            GATT_MANAGER_IFACE
        )

        # Create our GATT application (Treadmill Service + Characteristic)
        app = Application(bus, self)

        # Create an advertisement
        advertisement = Advertisement(bus, 0, 'peripheral')
        advertisement.add_service_uuid(TREADMILL_SERVICE_UUID)

        ad_manager = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
            ADVERTISING_MANAGER_IFACE
        )

        print("Registering advertisement...")
        ad_manager.RegisterAdvertisement(
            advertisement.get_path(),
            {},  # no special options
            reply_handler=register_ad_cb,
            error_handler=register_ad_error_cb
        )

        print("Registering the Treadmill GATT application...")
        service_manager.RegisterApplication(
            app.get_path(),
            {},  # no special options
            reply_handler=register_app_cb,
            error_handler=register_app_error_cb
        )

        # Start the GLib loop
        mainloop = GLib.MainLoop()
        print(f"Fake treadmill '{self.device_name}' running. Ctrl+C to stop.")
        mainloop.run()

    def stop(self):
        global mainloop
        if mainloop:
            mainloop.quit()
            print("Stopping treadmill app...")
