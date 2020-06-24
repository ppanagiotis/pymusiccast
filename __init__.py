"""The yamaha_musiccast component."""
import logging
import voluptuous as vol

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import config_validation as cv

DOMAIN = 'musiccast_yamaha'

SERVICE_JOIN = 'join'
SERVICE_UNJOIN = 'unjoin'

ATTR_MASTER = 'master'

SERVICE_SCHEMA = vol.Schema({
    vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
})

JOIN_SERVICE_SCHEMA = SERVICE_SCHEMA.extend({
    vol.Required(ATTR_MASTER): cv.entity_id,
})

_LOGGER = logging.getLogger(__name__)


def setup(hass, config):
    """Handle service configuration."""

    def service_handle(service):
        """Handle services."""
        _LOGGER.debug("service_handle from id: %s",
                      service.data.get('entity_id'))
        entity_ids = service.data.get('entity_id')
        entities = hass.data[DOMAIN].entities
        if entity_ids:
            entities = [e for e in entities if e.entity_id in entity_ids]

        if service.service == SERVICE_JOIN:
            master = [e for e in hass.data[DOMAIN].entities
                      if e.entity_id == service.data[ATTR_MASTER]]
            if master:
                client_entities = [e for e in entities
                                   if e.entity_id != master[0].entity_id]
                _LOGGER.debug("**JOIN** set clients %s for master %s",
                              [e.entity_id for e in client_entities],
                              master[0].ip_address)
                master[0].join_add(client_entities)

        elif service.service == SERVICE_UNJOIN:
            _LOGGER.debug("**UNJOIN** entities: %s", entities)
            masters = [entities for entities in entities
                       if entities.is_master]
            if masters:
                for master in masters:
                    master.unjoin()
            else:
                for entity in entities:
                    entity.unjoin()

    hass.services.register(
        DOMAIN, SERVICE_JOIN, service_handle, schema=JOIN_SERVICE_SCHEMA)
    hass.services.register(
        DOMAIN, SERVICE_UNJOIN, service_handle, schema=SERVICE_SCHEMA)

    return True
