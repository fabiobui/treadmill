#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later

import dbus
import dbus.mainloop.glib
import dbus.service

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
    def __init__(self, bus):
        self.path = '/'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

        # Add our single Treadmill service
        self.add_service(TreadmillService(bus, 0))

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
    """
    Implements the Treadmill Service (0x1826).
    """
    def __init__(self, bus, index):
        super().__init__(bus, index, TREADMILL_SERVICE_UUID, True)
        # Add treadmill data characteristic
        self.add_characteristic(TreadmillDataCharacteristic(bus, 0, self))


class TreadmillDataCharacteristic(Characteristic):
    """
    The Treadmill Data Characteristic (0x2ACD).
    We'll push speed/distance/cadence/time, etc. in notifications.
    """
    def __init__(self, bus, index, service):
        super().__init__(
            bus,
            index,
            TREADMILL_DATA_CHAR_UUID,
            ['notify'],  # Typically notify only
            service
        )
        self.notifying = False
        self.elapsed_time = 0  # track total time in seconds
        self.total_distance = 0  # track total distance in meters
        self.energy = 0         # track expended energy (kcal or Joules - used loosely here)

    @signal(DBUS_PROP_IFACE, signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        """
        Signal to notify subscribed clients that properties have changed.
        """
        pass

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        if self.notifying:
            print("TreadmillDataCharacteristic: Already notifying")
            return
        print("TreadmillDataCharacteristic: StartNotify")
        self.notifying = True
        GLib.timeout_add(1000, self._send_measurement)  # Send updates every second

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        if not self.notifying:
            print("TreadmillDataCharacteristic: Not notifying")
            return
        print("TreadmillDataCharacteristic: StopNotify")
        self.notifying = False



    def _send_measurement(self):
        if not self.notifying:
            return False  # stops the GLib.timeout_add loop
        
        # Increment elapsed time
        self.elapsed_time += 1

        # Construct the message components
        instantaneous_speed = 1000  # Speed in cm/s (3.0 km/h)
        total_distance = 10        # Distance in cm
        calories = 1               # Calories

        # Construct the message using dbus.Byte
        value = [
            dbus.Byte(0x84),
            dbus.Byte(0x04),  
            dbus.Byte(instantaneous_speed & 0xFF),       # Speed low byte
            dbus.Byte((instantaneous_speed >> 8) & 0xFF),# Speed high byte
            dbus.Byte(total_distance & 0xFF),            # Distance low byte
            dbus.Byte((total_distance >> 8) & 0xFF),     # Distance middle byte
            dbus.Byte((total_distance >> 16) & 0xFF),    # Distance high byte
            dbus.Byte(calories & 0xFF),                  # Calories low byte
            dbus.Byte((calories >> 8) & 0xFF),           # Calories high byte
            dbus.Byte(0x00),                             # Reserved byte (placeholder for more fields)
            dbus.Byte(0x00),                             # Reserved byte (placeholder for more fields)
            dbus.Byte(0x00),                             # Reserved byte (placeholder for more fields)
            dbus.Byte(self.elapsed_time & 0xFF),         # Elapsed Time low byte
            dbus.Byte((self.elapsed_time >> 8) & 0xFF)   # Elapsed Time high byte
        ]

        print(f"Sending Message: {[hex(b) for b in value]}")

        # Notify subscribed clients
        self.PropertiesChanged(
            GATT_CHRC_IFACE,
            {'Value': dbus.Array(value, signature='y')},
            []
        )

        return True  # Schedule the next update



    def _send_measurement_old(self):
        """
        Build and send the Treadmill Data packet according to the BT spec:
          Flags (2 bytes), Instantaneous Speed (2 bytes),
          [Optionally Average Speed], Total Distance (3 bytes), ...
          Expended Energy (2 bytes?), etc., Elapsed Time (2 bytes)...
        """
        if not self.notifying:
            return False  # stops the GLib.timeout_add loop

        # Increase time by 1 second
        self.elapsed_time += 1

        # For example, let's do a constant speed of 3.0 km/h => ~0.833 m/s => ~213 in 1/256 m/s
        # If you want a different speed, adjust these lines:
        speed_m_s = 0.833
        speed_256 = int(speed_m_s * 256)

        # Increase total distance each second by speed * 1s
        # (distance in meters; we store as an integer)
        self.total_distance += speed_m_s

        # Increase energy slightly each second
        self.energy += 1

        # Let's say we also want to simulate cadence (not strictly part of 0x2ACD,
        # but Zwift may interpret some bits, or we can embed it in "instantaneous speed" alone).
        # For treadmill data, cadence is not typically in the Treadmill Data characteristic,
        # so we'll skip a dedicated "cadence" field. Zwift gets speed from here.

        # The Treadmill Data characteristic expects 2 bytes of flags in little-endian.
        # Let's set flags for:
        #   bit2 => Total Distance Present
        #   bit7 => Expended Energy Present
        #   bit10 => Elapsed Time Present
        #
        # So in binary:
        #  low byte = 1000 0100 = 0x84 (bits 2 and 7 set)
        #  high byte = 0000 0100 = 0x04 (bit 10 set)
        flags_low  = 0x84
        flags_high = 0x04

        # Build our data buffer:
        # Byte 0-1: Flags (little-endian) => [flags_low, flags_high]
        # Byte 2-3: Instantaneous Speed (1/256 m/s, little-endian)
        # Byte 4-6: Total Distance (in meters, 24-bit little-endian)
        # Byte 7-8: Expended Energy (2 bytes, e.g. in kilo Joules or something) (placeholder)
        # Byte 9-10: ??? Could be Speed/Energy per hour or minute if spec demands
        # Byte 11-12: ??? Typically for the "Energy" subfields
        # Byte 13-14: Elapsed Time (2 bytes, 1-second resolution, little-endian)

        # We'll fill any extra required bytes with 0x00.
        # Minimum needed for the flags we set is:
        #   2 (flags) + 2 (speed) + 3 (distance) + 2 (energy) + 2 (elapsed time) = 11 bytes
        # But we have to place them in the correct order:

        distance_int = int(self.total_distance)  # in whole meters
        val = [
            dbus.Byte(flags_low),
            dbus.Byte(flags_high),

            # Instantaneous Speed, LSB first
            dbus.Byte(speed_256 & 0xFF),
            dbus.Byte((speed_256 >> 8) & 0xFF),

            # Total Distance (3 bytes, little-endian)
            dbus.Byte(distance_int & 0xFF),
            dbus.Byte((distance_int >> 8) & 0xFF),
            dbus.Byte((distance_int >> 16) & 0xFF),

            # Expended Energy (2 bytes, placeholder)
            dbus.Byte(self.energy & 0xFF),
            dbus.Byte((self.energy >> 8) & 0xFF),

            # For simplicity, put 0s where the specification might expect more energy subfields
            dbus.Byte(0x00),
            dbus.Byte(0x00),

            # Elapsed Time (2 bytes, little-endian)
            dbus.Byte(self.elapsed_time & 0xFF),
            dbus.Byte((self.elapsed_time >> 8) & 0xFF),
        ]

        print(f"[Notify] Speed={speed_m_s*3.6:.2f} km/h, TotalDist={distance_int} m, Time={self.elapsed_time} s")

        # Notify subscribed clients that 'Value' changed
        self.PropertiesChanged(
            GATT_CHRC_IFACE,
            {'Value': dbus.Array(val, signature='y')},
            []
        )

        return True  # schedule next update

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
                'Data': dbus.Dictionary(self.data, signature='sv')
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
def register_app_cb():
    print("GATT application registered (Treadmill).")

def register_app_error_cb(error):
    print("Failed to register application:", str(error))
    mainloop.quit()

def find_adapter(bus):
    """Return the path of the first adapter that has GattManager1."""
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'),
                               DBUS_OM_IFACE)
    objects = remote_om.GetManagedObjects()
    for path, ifaces in objects.items():
        if GATT_MANAGER_IFACE in ifaces:
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
    """Setup the pairing agent and make it the default."""
    agent = PairingAgent(bus)
    manager = dbus.Interface(
        bus.get_object("org.bluez", "/org/bluez"),
        "org.bluez.AgentManager1"
    )

    # Register the pairing agent
    manager.RegisterAgent(PairingAgent.AGENT_PATH, "KeyboardDisplay")
    print("Pairing agent registered with capability: KeyboardDisplay")

    # Set it as the default agent
    manager.RequestDefaultAgent(PairingAgent.AGENT_PATH)
    print("Pairing agent set as default")

def restart_adapter(bus, adapter_path):
    """Restart the Bluetooth adapter to apply changes."""
    adapter = dbus.Interface(
        bus.get_object("org.bluez", adapter_path),
        "org.bluez.Adapter1"
    )
    try:
        adapter.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(False))
        adapter.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(True))
        print("Bluetooth adapter restarted")
    except dbus.DBusException as e:
        print(f"Failed to restart adapter: {str(e)}")

def register_ad_cb():
    print("Advertisement registered")

def register_ad_error_cb(error):
    print("Failed to register advertisement:", str(error))
    mainloop.quit()

############################
# Main
############################
def main():
    global mainloop

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    adapter_path = find_adapter(bus)
    if not adapter_path:
        print("GattManager1 interface not found. Is bluetoothd running with --experimental?")
        return

    # Set the Bluetooth device name
    set_bluetooth_name(bus, adapter_path, "ORANGE-PI3-ZERO")
    restart_adapter(bus, adapter_path)

    # Set up the pairing agent
    setup_pairing_agent(bus)

    service_manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
        GATT_MANAGER_IFACE
    )

    # Create our GATT application (Treadmill Service + Characteristic)
    app = Application(bus)

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

    mainloop = GLib.MainLoop()
    mainloop.run()

if __name__ == '__main__':
    main()
