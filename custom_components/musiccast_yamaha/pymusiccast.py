from pymusiccast import exceptions
from pymusiccast import McDevice
from pymusiccast import Zone
from .helpers import request
from .const import ENDPOINTS, STATE_ON, STATE_OFF
from datetime import datetime
import logging
import random
_LOGGER = logging.getLogger(__name__)


class McDevice(McDevice):

    def initialize_zones(self):
        """initialize receiver zones"""
        zone_list = self.location_info.get('zone_list', {'main': True})

        for zone_id in zone_list:
            if zone_list[zone_id]:  # Location setup is valid
                self.zones[zone_id] = Zone(self, zone_id=zone_id)
            else:                   # Location setup is not valid
                _LOGGER.debug("Ignoring zone: %s", zone_id)

    def initialize(self):
        """initialize the object"""
        self.network_status = self.get_network_status()
        self.name = self.network_status.get('network_name', 'Unknown')
        self.location_info = self.get_location_info()
        self.device_info = self.get_device_info()
        self.device_id = (
            self.device_info.get('device_id')
            if self.device_info else "Unknown")
        self.initialize_socket()
        self.initialize_worker()
        self.initialize_zones()
        self.update_distribution_info()
        self._volume_db_control = False
        self.volume_db_control()

    def update_distribution_info(self):
        """Get distribution info from device and update zone"""
        req_url = ENDPOINTS["getDistributionInfo"].format(self._ip_address)
        response = request(req_url)
        _LOGGER.debug("%s: Distribution Info Message: %s", self._ip_address,
                      response)
        if 'server_zone' in response:
            server_zone = response.get('server_zone')
            self.zones[server_zone].update_distribution_info(response)
        else:
            self.zones['main'].update_distribution_info(response)

    def volume_db_control(self):
        for i in self.get_features()['zone']:
            if i['id'] == 'main':
                if 'actual_volume' in i['func_list']:
                    self._volume_db_control = True

    def handle_event(self, message):
        """Dispatch all event messages"""
        # _LOGGER.debug(message)
        needs_update = 0
        for zone in self.zones:
            if zone in message:
                _LOGGER.debug("%s: Received message for zone: %s: %s",
                              self._ip_address, zone, message)
                self.zones[zone].update_status(message[zone])

        if 'netusb' in message:
            needs_update += self.handle_netusb(message['netusb'])

        if 'dist' in message:
            _LOGGER.debug("%s: Received dist update for zone %s: %s",
                          self._ip_address, zone, message)
            self.update_distribution_info()

        if needs_update > 0:
            _LOGGER.debug("%s: needs_update: %d", self._ip_address,
                          needs_update)
            self.update_hass()


class Zone(Zone):

    def __init__(self, receiver, zone_id='main'):
        super().__init__(receiver)
        self._distribution_info = None
        self.get_db_range_volume()

    @property
    def distribution_info(self):
        """Returns distribution_info."""
        return self._distribution_info

    @distribution_info.setter
    def distribution_info(self, stat):
        self._distribution_info = stat

    @property
    def group_id(self):
        """Returns the distribution group id."""
        return self._distribution_info.get("group_id")

    @property
    def group_is_server(self):
        """Returns true if this zone believes it is a server."""
        return self._distribution_info.get('role') == 'server' and \
            self.group_id != '00000000000000000000000000000000'

    @property
    def group_clients(self):
        """Returns the ip address of distribution group clients."""
        if not self.group_is_server:
            return []
        if self._distribution_info.get('client_list') is None:
            return []
        return [e.get('ip_address') for e in
                self._distribution_info.get('client_list')]

    @property
    def receiver(self):
        """Returns the receiver."""
        return self._receiver

    def get_db_range_volume(self):
        """Returns the min and max db volume."""
        for i in self.receiver.get_features()['zone']:
            if i['id'] == 'main':
                for x in i['range_step']:
                    if x['id'] == 'actual_volume_db':
                        self._volume_max = x['max']
                        self._volume_min = x['min']

    def handle_message(self, message):
        """Process UDP messages"""
        if self._yamaha:
            if 'power' in message:
                _LOGGER.debug("Power: %s", message.get('power'))
                self._yamaha.power = (
                    STATE_ON if message.get('power') == "on" else STATE_OFF)
            if 'input' in message:
                _LOGGER.debug("Input: %s", message.get('input'))
                self._yamaha._source = message.get('input')
            if self.receiver._volume_db_control:
                self._yamaha.volume_max =\
                        self._decibel_to_ratio(self._volume_max)
                if 'actual_volume' in message:
                    volume = message.get('actual_volume')
                    volume = volume['value']
                self._yamaha.volume = self._decibel_to_ratio(volume)
            else:
                if 'volume' in message:
                    volume = message.get('volume')

                    if 'max_volume' in message:
                        volume_max = message.get('max_volume')
                    else:
                        volume_max = self._yamaha.volume_max

                    _LOGGER.debug("Volume: %d / Max: %d", volume, volume_max)

                    self._yamaha.volume = volume / volume_max
                    self._yamaha.volume_max = volume_max
            if 'mute' in message:
                _LOGGER.debug("Mute: %s", message.get('mute'))
                self._yamaha.mute = message.get('mute', False)
        else:
            _LOGGER.debug("No yamaha-obj found")

    def update_distribution_info(self, new_dist=None):
        """Get distribution info from device and update zone"""
        _LOGGER.debug("%s: update_distribution_info: Zone %s",
                      self._ip_address, self.zone_id)
        if new_dist is None:
            return

        old_dist = self.distribution_info or {}
        # merge new_dist with existing for comparison
        _LOGGER.debug("%s: Set distribution_info: provided", self._ip_address)
        distribution_info = old_dist.copy()
        distribution_info.update(new_dist)
        new_dist = distribution_info
        if new_dist == old_dist:
            return

        _LOGGER.debug("%s: old_dist: %s", self._ip_address, old_dist)
        _LOGGER.debug("%s: new_dist: %s", self._ip_address, new_dist)
        if old_dist.get('role') != 'server':
            null_group = '00000000000000000000000000000000'
            if (old_dist.get('group_id') != null_group and
                    new_dist.get('group_id') == null_group) or \
               (old_dist.get('role') == 'client' and
                    new_dist.get('role') == 'none'):
                # The client has left, the master must update its client list
                if self._yamaha:
                    self._yamaha.update_master()
        self._status_sent = False
        self.distribution_info = new_dist

        if not self._status_sent:
            self._status_sent = self.update_hass()

    def distribution_group_set_name(self, group_name):
        """For SERVER: Set the new name of the group"""
        req_url = ENDPOINTS["setGroupName"].format(self._ip_address)
        payload = {'name': group_name}
        return request(req_url, method='POST', json=payload)

    def distribution_group_add(self, clients):
        """For SERVER: Add clients to distribution group and start serving."""
        if not clients:
            return
        group_id = self.group_id
        if group_id == '00000000000000000000000000000000':
            group_id = '%032x' % random.randrange(16**32)
        _LOGGER.debug("%s: Setting the clients to be clients: %s",
                      self._ip_address, clients)
        for client in clients:
            req_url = ENDPOINTS["setClientInfo"].format(client)
            payload = {'group_id': group_id,
                       'zone': self._zone_id,
                       'server_ip_address': self._ip_address
                       }
            request(req_url, method='POST', json=payload)

        _LOGGER.debug("%s: adding to the server the clients: %s",
                      self._ip_address, clients)
        req_url = ENDPOINTS["setServerInfo"].format(self._ip_address)
        payload = {'group_id': group_id,
                   'type': 'add',
                   'client_list': clients}
        request(req_url, method='POST', json=payload)

        _LOGGER.debug("%s: Starting the distribution", self._ip_address)
        req_url = ENDPOINTS["startDistribution"].format(self.ip_address)
        params = {"num": int(0)}
        request(req_url, params=params)

    def distribution_group_check_clients(self):
        """For SERVER: Checking clients are still serving this group."""
        if not self.group_is_server:
            return
        _LOGGER.debug("%s: Checking client status. Current registered \
                      clients: %s", self._ip_address, self.group_clients)
        clients_to_remove = []
        for client in self.group_clients:
            # check if it is still a client with correct group and input
            req_url = ENDPOINTS["getDistributionInfo"].format(client)
            response = request(req_url)
            if response.get('role') != 'client' or \
               response.get('group_id') != self.group_id:
                clients_to_remove.append(client)
                continue
            req_url = ENDPOINTS["getStatus"].format(client, self.zone_id)
            response = request(req_url)
            if response.get('input') != "mc_link":
                clients_to_remove.append(client)
        if clients_to_remove:
            _LOGGER.debug("%s: Clients: %s does not seem to be connected \
                          anymore... removing it.", self._ip_address,
                          clients_to_remove)
            self.distribution_group_remove(clients_to_remove)

    def distribution_group_remove(self, clients):
        """For SERVER: Remove clients, stop distribution if no more."""
        if not self.group_is_server or not clients:
            return
        old_clients = self.group_clients.copy()

        for client in clients:
            if client in old_clients:
                old_clients.remove(client)

        _LOGGER.debug("%s: Removing from server the clients: %s",
                      self._ip_address, clients)
        req_url = ENDPOINTS["setServerInfo"].format(self._ip_address)
        payload = {'group_id': self.group_id,
                   'type': 'remove',
                   'client_list': clients}
        request(req_url, method='POST', json=payload)

        if old_clients:
            req_url = ENDPOINTS["startDistribution"].format(self.ip_address)
            params = {"num": int(0)}
            _LOGGER.debug("%s: Updating the distribution with remaining \
                          clients: %s", self._ip_address, old_clients)
            request(req_url, params=params)
        else:
            _LOGGER.debug("%s: No more clients, resetting server",
                          self._ip_address)
            req_url = ENDPOINTS["setServerInfo"].format(self._ip_address)
            payload = {'group_id': ''}
            request(req_url, method='POST', json=payload)

            req_url = ENDPOINTS["stopDistribution"].format(self.ip_address)
            _LOGGER.debug("%s: Stopping the distribution", self._ip_address)
            request(req_url)

        for client in clients:
            _LOGGER.debug("%s: Resetting client: %s", self._ip_address, client)
            req_url = ENDPOINTS["setClientInfo"].format(client)
            payload = {'group_id': '',
                       'zone': self._zone_id}
            request(req_url, method='POST', json=payload)

    def distribution_group_stop(self):
        """For SERVER: Remove all clients and stop the distribution group."""
        if not self.group_is_server:
            return
        _LOGGER.debug("%s: stopDistribution client_list: %s", self._ip_address,
                      self.group_clients)
        self.distribution_group_remove(self.group_clients)

    def distribution_group_leave(self):
        """For CLIENT: The client disconnect from group.
        (The server will need to then updates its group)"""
        if self.group_is_server:
            self.distribution_group_stop()
            return
        _LOGGER.debug("%s: client is leaving the group", self._ip_address)
        req_url = ENDPOINTS["setClientInfo"].format(self.ip_address)
        payload = {'group_id': '',
                   'zone': self._zone_id}
        request(req_url, method='POST', json=payload)

    def _decibel_to_ratio(self, decibel):
        """Convert dB linearly to ratio ."""
        return (decibel - self._volume_min) /\
               (self._volume_max - self._volume_min)

    def _ratio_to_decibel(self, ratio):
        """Convert ratio scale to dB."""
        return ratio * (self._volume_max - self._volume_min) + self._volume_min

    def set_volume(self, volume):
        """Send Volume command."""
        if self.receiver._volume_db_control:
            req_url = ENDPOINTS["setActualVolume"].format(self.ip_address,
                                                          self.zone_id)
            volume = self._ratio_to_decibel(volume)
            params = {"mode": "db", "value": round(float(volume)*2)/2}
        else:
            req_url = ENDPOINTS["setVolume"].format(self.ip_address,
                                                    self.zone_id)
            params = {"volume": int(volume)}
        return request(req_url, params=params)
