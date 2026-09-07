# -*- coding: utf-8 -*-
# Tata Play Binge (VideoReady) API constants.
# Values reverse-engineered from the public Tata Play Binge Android/web clients.

ADDON_ID = 'plugin.video.binge'

# Base endpoints
API_KONG    = "https://kong-tatasky.videoready.tv"
API_TS      = "https://ts-api.videoready.tv"
API_TM      = "https://tm.tapi.videoready.tv"

# Hardcoded app credentials (OTT app / Dvr-UI web SDK)
X_APP_ID         = "ott-app"
X_API_KEY        = "9a8087f911b248c7945b926f254c833b"
X_APP_KEY        = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcHBJZCI6ImR2ci11aSIsImtleSI6IiJ9.XUQUYRo82fD_6yZ9ZEWcJkc0Os1IKbpzynLzSRtQJ-E"
X_DEVICE_ID      = "YVJNVFZWVlZ7S01UZmRZTWNNQ3lHe0RvS0VYS0NHSwA"
X_DEVICE_PLATFORM = "MOBILE"
X_DEVICE_TYPE    = "ANDROID"
USER_AGENT       = "PostmanRuntime/7.26.10"
WEB_USER_AGENT   = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.41 Safari/537.36"

# device_details body sent with auth requests
DEVICE_DETAILS = ('{"app":"11.0","lo":"en_IN","os":"10","device_id":"YVJNVFZWVlZ7S01UZmRZTWNNQ3lHe0RvS0VYS0NHSwA",'
                  '"ip":"","dn":"ONEPLUS A6003","device_type":"ANDROID","device_category":"open","manufacturer":"OnePlus",'
                  '"ma":"","car":"","sname":"","device_platform":"MOBILE","location":"","model":"ONEPLUS A6003",'
                  '"pl":"Android","net":"Wifi"}')
WEB_DEVICE_DETAILS = ('{"pl":"web","os":"WINDOWS","lo":"en-us","app":"1.36.21","dn":"PC","bv":101,"bn":"CHROME",'
                      '"device_id":"nkdvk1941cbv2icfgjxjjos113d6euws","device_type":"WEB","device_platform":"PC",'
                      '"device_category":"open","manufacturer":"WINDOWS_CHROME_101","model":"PC","sname":""}')

# Endpoints (auth/login moved to the watch.tataplay.com web platform tm.tapi host)
OTP_RMN_URL         = API_TM + "/rest-api/pub/api/v2/generate/otp"
LOGIN_URL           = API_TM + "/rest-api/pub/api/v3/login/ott"
SID_LOOKUP_URL      = API_TM + "/rest-api/pub/api/v2/subscriberLookup"
CHANNELS_URL        = API_TS + "/content-detail/pub/api/v1/channels"
CHANNEL_DETAIL_URL  = API_KONG + "/content-detail/pub/api/v1/channels/{cid}"
TOKEN_URL           = API_KONG + "/auth-service/v1/oauth/token-service/token"

# Binge OTT (VOD) API base - discovered from the official Binge web bundle
BINGE_API_BASE      = "https://tb.tapi.videoready.tv/"

# Playback
REFERER           = "https://watch.tataplay.com/"
M3U_PATH          = "special://profile/addon_data/{0}/playlist.m3u".format(ADDON_ID)
M3U_CHANNEL       = '#EXTINF:-1 tvg-id="{1}" tvg-logo="{2}" group-title="{3}",{0}\n{4}'

# Number of channels to request per page while paginating the channel list
CHANNEL_PAGE_SIZE = 100

# Session / cache keys
SESSION_KEY = 'session'
CHANNELS_KEY = 'channels'