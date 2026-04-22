# RedBot Media Player (Home Assistant)

Standalone Home Assistant custom integration repository for `redbot_media_player`.

Current documented release: `1.0.0` (see `CHANGELOG.md` and `custom_components/redbot_media_player/CHANGELOG.md`).

## Installation (HACS-first)

### Option 1: HACS (recommended first)

1. HACS -> Integrations -> three-dot menu -> Custom repositories.
2. Add repository URL: `https://github.com/AtticusG3/redbot-media-player-homeassistant`
3. Category: Integration
4. Install **RedBot Media Player**
5. Restart Home Assistant

### Option 2: Manual install

Copy `custom_components/redbot_media_player` into your Home Assistant config under `custom_components/`.

## Related projects

- Red cog repo (`ha_red_rpc`): <https://github.com/AtticusG3/redbot-media-player-cog>
- Home Assistant add-on repo (`redBot-hass`): <https://github.com/AtticusG3/redBot-hass>

## Documentation map

- Integration README: `custom_components/redbot_media_player/README.md`
- Integration changelog: `custom_components/redbot_media_player/CHANGELOG.md`
- Repository changelog: `CHANGELOG.md`

## Requirements

- Red bot running with `--rpc`
- `ha_red_rpc` cog loaded from `redbot-media-player-cog`
- Red Audio loaded
