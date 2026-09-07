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

# device_details body sent with auth requests
DEVICE_DETAILS = ('{"app":"11.0","lo":"en_IN","os":"10","device_id":"YVJNVFZWVlZ7S01UZmRZTWNNQ3lHe0RvS0VYS0NHSwA",'
                  '"ip":"","dn":"ONEPLUS A6003","device_type":"ANDROID","device_category":"open","manufacturer":"OnePlus",'
                  '"ma":"","car":"","sname":"","device_platform":"MOBILE","location":"","model":"ONEPLUS A6003",'
                  '"pl":"Android","net":"Wifi"}')

# Endpoints (auth/login via the Binge-mobile platform for RMN-only non-DTH accounts)
CHANNELS_URL        = API_TS + "/content-detail/pub/api/v1/channels"
CHANNEL_DETAIL_URL  = API_KONG + "/content-detail/pub/api/v1/channels/{cid}"
TOKEN_URL           = API_KONG + "/auth-service/v1/oauth/token-service/token"

# Binge OTT (VOD) API base - discovered from the official Binge web bundle
BINGE_API_BASE      = "https://tb.tapi.videoready.tv/"

# Binge-mobile (www.tataplaybinge.com) platform - works for NON-DTH (RMN-only) accounts.
# Flow: guest/register -> anonymousId + deviceId -> generateOTP -> validateOTP -> create user -> session.
BINGE_MOBILE_UA        = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
BINGE_ORIGIN           = "https://www.tataplaybinge.com"
BINGE_REGISTER_URL     = BINGE_API_BASE + "binge-mobile-services/pub/api/v1/user/guest/register"
BINGE_OTP_URL          = BINGE_API_BASE + "binge-mobile-services/pub/api/v1/user/authentication/generateOTP"
BINGE_VALIDATE_OTP_URL = BINGE_API_BASE + "binge-mobile-services/pub/api/v1/user/authentication/validateOTP"
BINGE_SUBSCRIBER_URL   = BINGE_API_BASE + "binge-mobile-services/api/v4/subscriber/details"
BINGE_CREATE_USER_URL  = BINGE_API_BASE + "binge-mobile-services/api/v3/create/new/user"
BINGE_UPDATE_USER_URL  = BINGE_API_BASE + "binge-mobile-services/api/v3/update/exist/user"

# Playback
REFERER           = "https://watch.tataplay.com/"
M3U_PATH          = "special://profile/addon_data/{0}/playlist.m3u".format(ADDON_ID)
M3U_CHANNEL       = '#EXTINF:-1 tvg-id="{1}" tvg-logo="{2}" group-title="{3}",{0}\n{4}'

# Number of channels to request per page while paginating the channel list
CHANNEL_PAGE_SIZE = 100

# Session / cache keys
SESSION_KEY = 'session'
CHANNELS_KEY = 'channels'