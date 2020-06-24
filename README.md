# Group MusicCast Speakers with [Home Assistant](https://github.com/home-assistant/home-assistant)


After waiting a year for [pymusiccast](https://github.com/jalmeroth/pymusiccast/) to support speakers group I decide to create a custom module, overwriting existing pymusiccast module, using code from this [PR](https://github.com/jalmeroth/pymusiccast/pull/13)
(credits [@hcoohb](https://github.com/hcoohb)).

![musiccast group management example](group_speakers.gif?raw=true "musiccast group management example")

## Install

### HACS
TODO

### Manual install
- Copy entire pymusiccast folder under `$HOMEASSISTANT_CONFIG/custom_components/`.
  or
- git clone git@github.com:ppanagiotis/pymusiccast.git under `$HOMEASSISTANT_CONFIG/custom_components/`.

## Setup
- At `media_server` component you have to add the following entry for each media player you want to add

```yaml
---
- platform: musiccast_yamaha
  host: `your.speaker.ip.address`
  port: 5009

```

## Using grouping at home assistant as a service

To add a speaker at a group:

```yaml
action:
  - service: musiccast_yamaha.join
    data:
      entity_id: `THE_CLIENT_SPEAKER`
      master: `THE_MASTER_SPEAKER`
```

To remove a spearker from group

```yaml
action:
  - service: musiccast_yamaha.unjoin
    entity_id: `THE_CLIENT_SPEAKER`
```

To add the group layout at custom:mini-media-player you have to add something like this at your ui-lovelace.yaml:
```yaml

views:
  - title: Home Assistant
    id: media_player
    icon: mdi:audio-video
    cards:
      - type: entities
        entities:
          - type: custom:mini-media-player
            group: true
            entity: media_player.livingroom
            name: LivingRoom
            toggle_power: false
            artwork: cover
            hide:
              icon: true
              power_state: false
            speaker_group:
              platform: musiccast_yamaha
              expanded: false
              entities:
                - entity_id: media_player.livingroom
                  name: LivingRoom
                - entity_id: media_player.office
                  name: Office
                - entity_id: media_player.bedroom
                  name: BedRoom
                - entity_id: media_player.yard
                  name: Yard
          - type: custom:mini-media-player
            group: true
            name: Office
            hide:
              icon: true
              controls: true
              progress: true
              source: true
              info: true
              power_state: false
            entity: media_player.office
            toggle_power: false
          - type: custom:mini-media-player
            group: true
            name: BedRoom
            hide:
              icon: true
              controls: true
              progress: true
              source: true
              info: true
              power_state: false
            entity: media_player.bedroom
            toggle_power: false
          - type: custom:mini-media-player
            group: true
            name: Yard
            hide:
              icon: true
              controls: true
              progress: true
              source: true
              info: true
              power_state: false
              volume: true
            entity: media_player.yard
            toggle_power: false
```
