"""Constants for RedBot Media Player integration."""

DOMAIN = "redbot_media_player"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_GUILD_ID = "guild_id"
CONF_CHANNEL_ID = "channel_id"
CONF_ACTOR_USER_ID = "actor_user_id"

CONF_AUDIODB_ENABLE = "audiodb_enable"
CONF_AUDIODB_API_KEY = "audiodb_api_key"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6133

SERVICE_PLAY = "play"
SERVICE_BUMPPLAY = "bumpplay"
SERVICE_ENQUEUE = "enqueue"
SERVICE_PAUSE = "pause"
SERVICE_QUEUE = "queue"
SERVICE_PLAYLIST_START = "playlist_start"
SERVICE_PLAYLIST_SAVE_START = "playlist_save_start"
SERVICE_SUMMON = "summon"
SERVICE_DISCONNECT = "disconnect"
SERVICE_VOICE_STATE = "voice_state"

ATTR_QUERY = "query"
ATTR_PLAYLIST_NAME = "playlist_name"
ATTR_PLAYLIST_URL = "playlist_url"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_ACTOR_USER_ID = "actor_user_id"
ATTR_SELF_MUTE = "self_mute"
ATTR_SELF_DEAF = "self_deaf"

# RPC method sets: Red registers ``HAREDRPC__*`` from class ``HARedRPC`` (see Red get_name()).
# Used when GET_METHODS fails and to document the minimal cog before player-control RPCs existed.
LEGACY_HA_RED_RPC_METHODS = frozenset(
    {
        "HAREDRPC__PLAY",
        "HAREDRPC__BUMPPLAY",
        "HAREDRPC__ENQUEUE",
        "HAREDRPC__PAUSE",
        "HAREDRPC__QUEUE",
        "HAREDRPC__PLAYLIST_LIST",
        "HAREDRPC__PLAYLIST_START",
        "HAREDRPC__PLAYLIST_SAVE_START",
        "HAREDRPC__SUMMON",
        "HAREDRPC__DISCONNECT",
        "HAREDRPC__VOICE_STATE",
    }
)

FULL_HA_RED_RPC_METHODS = frozenset(
    {
        *LEGACY_HA_RED_RPC_METHODS,
        "HAREDRPC__STOP",
        "HAREDRPC__SKIP",
        "HAREDRPC__PREVIOUS",
        "HAREDRPC__QUEUE_CLEAR",
        "HAREDRPC__SHUFFLE",
        "HAREDRPC__REPEAT",
        "HAREDRPC__SEEK",
        "HAREDRPC__VOLUME",
    }
)

REPAIRS_ISSUE_RPC_UNAVAILABLE = "rpc_unavailable"
REPAIRS_ISSUE_PLAYLIST_RPC_UNAVAILABLE = "playlist_rpc_unavailable"
