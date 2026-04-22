# Changelog

## [1.0.1] - 2026-04-23

### Added (1.0.1)

- Root README now references the `docs/` screenshot set and Lovelace card YAML example for easier dashboard setup.

### Changed (1.0.1)

- `playlist_save_start` now supports resolving source playlist titles and using named save/start RPC when available.
- Playlist names are normalized to alphanumeric-only values before named save/start calls.
- Integration version advanced to `1.0.1`.

### Links (1.0.1)

- Repository changelog: `CHANGELOG.md`
- Red cog (`ha_red_rpc`): <https://github.com/AtticusG3/redbot-media-player-cog>
- Home Assistant add-on repo: <https://github.com/AtticusG3/redBot-hass>

## [1.0.0] - 2026-04-23

### Added (1.0.0)

- Home Assistant integration services for Red Discord bot audio control.
- Playlist save/start and queue-related entities.

### Changed (1.0.0)

- Improved media title and artist normalization.
- Artwork lookup support and coordinator refresh behavior.
- Documentation polish for HACS-first install instructions and accurate cross-repo references.

### Links (1.0.0)

- Repository changelog: `CHANGELOG.md`
- Red cog (`ha_red_rpc`): <https://github.com/AtticusG3/redbot-media-player-cog>
- Home Assistant add-on repo: <https://github.com/AtticusG3/redBot-hass>

### Notes

- This is the first public release baseline for `redbot_media_player`.
- Earlier pre-rename work was alpha validation and is not carried as public semver history.
