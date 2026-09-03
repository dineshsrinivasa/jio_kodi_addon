# -*- coding: utf-8 -*-
from __future__ import unicode_literals

# xbmc imports
from xbmcaddon import Addon
from xbmc import executebuiltin, log, LOGINFO
from xbmcgui import Dialog, DialogProgress

# codequick imports
from codequick import Route, run, Listitem, Resolver, Script
from codequick.utils import keyboard
from codequick.script import Settings
from codequick.storage import PersistentDict
import xbmc
import time
import xbmcplugin
import xbmcgui
import xbmcvfs
import sys

# add-on imports
from resources.lib.utils import (
    getTokenParams,
    getHeaders,
    isLoggedIn,
    login as ULogin,
    logout as ULogout,
    check_addon,
    sendOTPV2,
    get_local_ip,
    getChannelHeaders,
    getSonyHeaders,
    getZeeHeaders,
    zeeCookie,
    getChannelHeadersWithHost,
    quality_to_enum,
    _setup,
    kodi_rpc,
    Monitor,
    getCachedChannels,
    getCachedDictionary,
    cleanLocalCache,
    getFeatured,
    cleanup_signals,
)
from resources.lib.constants import (
    GET_CHANNEL_URL,
    IMG_CATCHUP,
    PLAY_URL,
    IMG_CATCHUP_SHOWS,
    CATCHUP_SRC,
    M3U_SRC,
    EPG_SRC,
    M3U_CHANNEL,
    IMG_CONFIG,
    EPG_PATH,
    ADDON,
    ADDON_ID,
)
from resources.lib.reconnect import watchdog

# additional imports
import urlquick
from uuid import uuid4
from urllib.parse import urlencode
import inputstreamhelper
from time import time, sleep
from datetime import datetime, timedelta, date
import m3u8
import requests
import gzip
import xml.etree.ElementTree as ET
import os
import json
import threading

# Root path of plugin

monitor = Monitor()

# Channel id groups used by the playback resolver.
ZEE_RANGE = [
    "5000", "5001", "5002", "5003", "5004", "5005", "5006", "5007", "5008", "5009",
    "5010", "5011", "5012", "5013", "5014", "5015", "5016", "5017", "5018", "5019",
    "5020", "5021", "5022", "5023", "5024", "5025", "5026",
]
DIRECT_IDS = ["154", "181", "182", "183", "289", "291", "471", "483"] + ZEE_RANGE
ZEE_MAP = ["5016", "5017", "5023", "5024", "5025", "5026"]


@Route.register
def root(plugin):
    yield Listitem.from_dict(
        **{
            "label": "Featured",
            "art": {
                "thumb": IMG_CATCHUP_SHOWS + "cms/TKSS_Carousal1.jpg",
                "icon": IMG_CATCHUP_SHOWS + "cms/TKSS_Carousal1.jpg",
                "fanart": IMG_CATCHUP_SHOWS + "cms/TKSS_Carousal1.jpg",
            },
            "callback": Route.ref("/resources/lib/main:show_featured"),
        }
    )
    for e in ["Genres", "Languages"]:
        yield Listitem.from_dict(
            **{
                "label": e,
                # "art": {
                #     "thumb": CONFIG[e][0].get("tvImg"),
                #     "icon": CONFIG[e][0].get("tvImg"),
                #     "fanart": CONFIG[e][0].get("promoImg"),
                # },
                "callback": Route.ref("/resources/lib/main:show_listby"),
                "params": {"by": e},
            }
        )


# Shows Featured Content
@Route.register
def show_featured(plugin, id=None):
    for each in getFeatured():
        if id:
            if int(each.get("id", 0)) == int(id):
                data = each.get("data", [])
                for child in data:
                    info_dict = {
                        "art": {
                            "thumb": IMG_CATCHUP_SHOWS + child.get("episodePoster", ""),
                            "icon": IMG_CATCHUP_SHOWS + child.get("episodePoster", ""),
                            "fanart": IMG_CATCHUP_SHOWS
                            + child.get("episodePoster", ""),
                            "clearart": IMG_CATCHUP + child.get("logoUrl", ""),
                            "clearlogo": IMG_CATCHUP + child.get("logoUrl", ""),
                        },
                        "info": {
                            "originaltitle": child.get("showname"),
                            "tvshowtitle": child.get("showname"),
                            "genre": child.get("showGenre"),
                            "plot": child.get("description"),
                            "episodeguide": child.get("episode_desc"),
                            "episode": 0
                            if child.get("episode_num") == -1
                            else child.get("episode_num"),
                            "cast": child.get("starCast", "").split(", "),
                            "director": child.get("director"),
                            "duration": child.get("duration") * 60,
                            "tag": child.get("keywords"),
                            "mediatype": "movie"
                            if child.get("channel_category_name") == "Movies"
                            else "episode",
                        },
                    }
                    if child.get("showStatus") == "Now":
                        info_dict["label"] = info_dict["info"]["title"] = (
                            child.get("showname", "") + " [COLOR red] [ LIVE ] [/COLOR]"
                        )
                        info_dict["callback"] = play
                        info_dict["params"] = {"channel_id": child.get("channel_id")}
                        yield Listitem.from_dict(**info_dict)
                    elif child.get("showStatus") == "future":
                        timetext = datetime.fromtimestamp(
                            int(child.get("startEpoch", 0) * 0.001)
                        ).strftime("    [ %I:%M %p -") + datetime.fromtimestamp(
                            int(child.get("endEpoch", 0) * 0.001)
                        ).strftime(
                            " %I:%M %p ]   %a"
                        )
                        info_dict["label"] = info_dict["info"]["title"] = child.get(
                            "showname", ""
                        ) + (" [COLOR green]%s[/COLOR]" % timetext)
                        info_dict["callback"] = ""
                        yield Listitem.from_dict(**info_dict)
                    elif child.get("showStatus") == "catchup":
                        timetext = datetime.fromtimestamp(
                            int(child.get("startEpoch", 0) * 0.001)
                        ).strftime("    [ %I:%M %p -") + datetime.fromtimestamp(
                            int(child.get("endEpoch", 0) * 0.001)
                        ).strftime(
                            " %I:%M %p ]   %a"
                        )
                        info_dict["label"] = info_dict["info"]["title"] = child.get(
                            "showname", ""
                        ) + (" [COLOR yellow]%s[/COLOR]" % timetext)
                        info_dict["callback"] = play
                        info_dict["params"] = {
                            "channel_id": child.get("channel_id"),
                            "showtime": child.get("showtime", "").replace(":", ""),
                            "srno": datetime.fromtimestamp(
                                int(child.get("startEpoch", 0) * 0.001)
                            ).strftime("%Y%m%d"),
                            "programId": child.get("srno", ""),
                            "begin": datetime.utcfromtimestamp(
                                int(child.get("startEpoch", 0) * 0.001)
                            ).strftime("%Y%m%dT%H%M%S"),
                            "end": datetime.utcfromtimestamp(
                                int(child.get("endEpoch", 0) * 0.001)
                            ).strftime("%Y%m%dT%H%M%S"),
                        }
                        yield Listitem.from_dict(**info_dict)
        else:
            yield Listitem.from_dict(
                **{
                    "label": each.get("name"),
                    "art": {
                        "thumb": IMG_CATCHUP_SHOWS
                        + each.get("data", [{}])[0].get("episodePoster"),
                        "icon": IMG_CATCHUP_SHOWS
                        + each.get("data", [{}])[0].get("episodePoster"),
                        "fanart": IMG_CATCHUP_SHOWS
                        + each.get("data", [{}])[0].get("episodePoster"),
                    },
                    "callback": Route.ref("/resources/lib/main:show_featured"),
                    "params": {"id": each.get("id")},
                }
            )


# Shows Filter options
@Route.register
def show_listby(plugin, by):
    dictionary = getCachedDictionary()
    GENRE_MAP = dictionary.get("channelCategoryMapping")
    LANG_MAP = dictionary.get("languageIdMapping")
    langValues = list(LANG_MAP.values())
    langValues.append("Extra")
    CONFIG = {
        "Genres": GENRE_MAP.values(),
        "Languages": langValues,
    }
    for each in CONFIG[by]:
        tvImg = IMG_CONFIG[by].get(each, {}).get("tvImg", "")
        promoImg = IMG_CONFIG[by].get(each, {}).get("promoImg", "")
        yield Listitem.from_dict(
            **{
                "label": each,
                "art": {"thumb": tvImg, "icon": tvImg, "fanart": promoImg},
                "callback": Route.ref("/resources/lib/main:show_category"),
                "params": {"categoryOrLang": each, "by": by},
            }
        )


def is_lang_allowed(langId, langMap):
    if langId in langMap.keys():
        return Settings.get_boolean(langMap[langId])
    else:
        return Settings.get_boolean("Extra")


def is_genre_allowed(id, map):
    if id in map.keys():
        return Settings.get_boolean(map[id])
    else:
        return False


def isPlayAbleLang(each, LANG_MAP):
    return not each.get("channelIdForRedirect") and is_lang_allowed(
        str(each.get("channelLanguageId")), LANG_MAP
    )


def isPlayAbleGenre(each, GENRE_MAP):
    return not each.get("channelIdForRedirect") and is_genre_allowed(
        str(each.get("channelCategoryId")), GENRE_MAP
    )


# Shows channels by selected filter/category


@Route.register
def show_category(plugin, categoryOrLang, by):
    resp = getCachedChannels()
    dictionary = getCachedDictionary()
    GENRE_MAP = dictionary.get("channelCategoryMapping")
    LANG_MAP = dictionary.get("languageIdMapping")

    def fltr(x):
        fby = by.lower()[:-1]
        if fby == "genre":
            return GENRE_MAP[
                str(x.get("channelCategoryId"))
            ] == categoryOrLang and isPlayAbleLang(x, LANG_MAP)
        else:
            if categoryOrLang == "Extra":
                return str(
                    x.get("channelLanguageId")
                ) not in LANG_MAP.keys() and isPlayAbleGenre(x, GENRE_MAP)
            else:
                if str(x.get("channelLanguageId")) not in LANG_MAP.keys():
                    return False
                return LANG_MAP[
                    str(x.get("channelLanguageId"))
                ] == categoryOrLang and isPlayAbleGenre(x, GENRE_MAP)

    try:
        flist = list(filter(fltr, resp))
        if len(flist) < 1:
            yield Listitem.from_dict(
                **{
                    "label": "No Results Found, Go Back",
                    "callback": show_listby,
                    "params": {"by": by},
                }
            )
        else:
            for each in flist:
                if Settings.get_boolean("number_toggle"):
                    channel_number = int(each.get("channel_order")) + 1
                    channel_name = str(channel_number) + " " + each.get("channel_name")
                else:
                    channel_name = each.get("channel_name")
                litm = Listitem.from_dict(
                    **{
                        "label": channel_name,
                        "art": {
                            "thumb": IMG_CATCHUP + each.get("logoUrl"),
                            "icon": IMG_CATCHUP + each.get("logoUrl"),
                            "fanart": IMG_CATCHUP + each.get("logoUrl"),
                            "clearlogo": IMG_CATCHUP + each.get("logoUrl"),
                            "clearart": IMG_CATCHUP + each.get("logoUrl"),
                        },
                        "callback": play,
                        "params": {"channel_id": each.get("channel_id")},
                    }
                )
                if each.get("isCatchupAvailable"):
                    litm.context.container(
                        show_epg, "Catchup", 0, each.get("channel_id")
                    )
                yield litm
    except Exception as e:
        Script.notify("Error", e)
        monitor.waitForAbort(1)
        return False


# Shows EPG container from Context menu


@Route.register
def show_epg(plugin, day, channel_id):
    resp = urlquick.get(
        CATCHUP_SRC.format(day, channel_id), max_age=-1
    ).json()
    epg = sorted(resp["epg"], key=lambda show: show["startEpoch"], reverse=False)
    livetext = "[COLOR red] [ LIVE ] [/COLOR]"
    for each in epg:
        current_epoch = int(time() * 1000)
        if not each["stbCatchupAvailable"] or each["startEpoch"] > current_epoch:
            continue
        islive = each["startEpoch"] < current_epoch and each["endEpoch"] > current_epoch
        showtime = (
            "   " + livetext
            if islive
            else datetime.fromtimestamp(int(each["startEpoch"] * 0.001)).strftime(
                "    [ %I:%M %p -"
            )
            + datetime.fromtimestamp(int(each["endEpoch"] * 0.001)).strftime(
                " %I:%M %p ]   %a"
            )
        )
        yield Listitem.from_dict(
            **{
                "label": each["showname"] + showtime,
                "art": {
                    "thumb": IMG_CATCHUP_SHOWS + each["episodePoster"],
                    "icon": IMG_CATCHUP_SHOWS + each["episodePoster"],
                    "fanart": IMG_CATCHUP_SHOWS + each["episodePoster"],
                },
                "callback": play,
                "info": {
                    "title": each["showname"] + showtime,
                    "originaltitle": each["showname"],
                    "tvshowtitle": each["showname"],
                    "genre": each["showGenre"],
                    "plot": each["description"],
                    "episodeguide": each.get("episode_desc"),
                    "episode": 0 if each["episode_num"] == -1 else each["episode_num"],
                    "cast": each["starCast"].split(", "),
                    "director": each["director"],
                    "duration": each["duration"] * 60,
                    "tag": each["keywords"],
                    "mediatype": "episode",
                },
                "params": {
                    "channel_id": each.get("channel_id"),
                    "showtime": each.get("showtime", "").replace(":", ""),
                    "srno": datetime.fromtimestamp(
                        int(each.get("startEpoch", 0) * 0.001)
                    ).strftime("%Y%m%d"),
                    "programId": each.get("srno", ""),
                    "begin": datetime.utcfromtimestamp(
                        int(each.get("startEpoch", 0) * 0.001)
                    ).strftime("%Y%m%dT%H%M%S"),
                    "end": datetime.utcfromtimestamp(
                        int(each.get("endEpoch", 0) * 0.001)
                    ).strftime("%Y%m%dT%H%M%S"),
                },
            }
        )
    if int(day) == 0:
        for i in range(-1, -7, -1):
            label = (
                "Yesterday"
                if i == -1
                else (date.today() + timedelta(days=i)).strftime("%A %d %B")
            )
            yield Listitem.from_dict(
                **{
                    "label": label,
                    "callback": Route.ref("/resources/lib/main:show_epg"),
                    "params": {"day": i, "channel_id": channel_id},
                }
            )


def _resolve_stream(channel_id, showtime=None, srno=None, programId=None, begin=None, end=None):
    """Build and return a normalized stream info dict for a channel.

    This mirrors the URL/header construction previously done inline in play()
    so that the stall-recovery watchdog can re-resolve a fresh stream (with a
    fresh __hdnea__ token) on demand.
    """
    sony_headers = getSonyHeaders()
    try:
        rjson = {"channel_id": int(channel_id), "stream_type": "Seek"}
        isCatchup = False
        if showtime and srno:
            isCatchup = True
            rjson["showtime"] = showtime
            rjson["srno"] = srno
            rjson["stream_type"] = "Catchup"
            rjson["programId"] = programId
            rjson["begin"] = begin
            rjson["end"] = end
            Script.log(str(rjson), lvl=Script.INFO)

        headers = getHeaders()
        if not headers:
            return None
        headers["channelid"] = str(channel_id)
        headers["srno"] = str(uuid4()) if "srno" not in rjson else rjson["srno"]

        zee_channels = {
            "5016": "https://z5ak-cmaflive.zee5.com/cmaf/live/2105525/ZeeAnmolCinemaELE/master.m3u8",
            "5017": "https://z5ak-cmaflive.zee5.com/cmaf/live/2105527/ZeeActionELE/master.m3u8",
            "5023": "https://z5ak-cmaflive.zee5.com/cmaf/live/2105261/ZEECHITRAMANDIRELE/master.m3u8",
            "5024": "https://z5ak-cmaflive.zee5.com/cmaf/live/2105526/ZeeAnmolELE/master.m3u8",
            "5025": "https://z5live-cf.zee5.com/out/v1/ZEE5_Live_Channels/Zee-Ganga-Zee-Anmol-Cinema-2-SD/master/master.m3u8",
            "5026": "https://z5ak-cmaflive.zee5.com/cmaf/live/2105176/BigMagicELE/master.m3u8",
        }

        host_map = {
            "5016": "z5ak-cmaflive.zee5.com",
            "5017": "z5ak-cmaflive.zee5.com",
            "5023": "z5ak-cmaflive.zee5.com",
            "5024": "z5ak-cmaflive.zee5.com",
            "5025": "z5live-cf.zee5.com",
            "5026": "z5ak-cmaflive.zee5.com",
        }
        zee_id_map = {
            "5016": "0-9-zeeanmolcinema",
            "5017": "0-9-zeeaction",
            "5023": "0-9-394",
            "5024": "0-9-zeeanmol",
            "5025": "0-9-bigganga",
            "5026": "0-9-bigmagic_1786965389",
        }

        resp = None
        url = None
        headerszee = None
        m3u8Headers = None
        onlyUrl = None
        uriToUse = None

        if channel_id in DIRECT_IDS:
            if channel_id in zee_channels:
                zee_channelid = zee_id_map.get(channel_id)
                host = host_map.get(channel_id)
                cook = zeeCookie(zee_channelid)
                if not cook:
                    Script.notify("Zee Error", "Failed to get Zee channel cookie")
                    return None
                headerszee = getZeeHeaders(host)
                base_url = zee_channels[channel_id]
                onlyUrl = url = "{0}{1}".format(base_url, cook)
                cookie = url.split("?")[1] if "?hdntl=" in url else ""
                uriToUse = onlyUrl
                headers["cookie"] = cookie
            else:
                if not sony_headers:
                    Script.notify("Error", "getSonyHeaders() returned None")
                    return None
                if "user-agent" not in sony_headers:
                    Script.notify("Error", "'user-agent' missing in Sony headers")
                    return None
                chan = "471" if channel_id in ["154", "471"] else str(channel_id)
                res = urlquick.post(
                    "https://jiotvapi.media.jio.com/playback/apis/v1/geturl?langId=6",
                    data="stream_type=Seek&channel_id={0}".format(chan),
                    verify=False,
                    headers=sony_headers,
                    max_age=-1,
                )
                sonyheaders = sony_headers
                sonyheaders["cookie"] = "__hdnea__" + res.json().get("result", "").split("__hdnea__")[-1]
                sonyheaders.setdefault("user-agent", "jiotv")
                sonyheaders = {k: str(v) for k, v in sonyheaders.items() if v}
                resp = res.json()
                onlyUrl = resp.get("result", "").split("?")[0].split("/")[-1]
                cookie = "__hdnea__" + resp.get("result", "").split("__hdnea__")[-1]
                headers["cookie"] = cookie
                uriToUse = resp.get("result", "")
        else:
            chan = str(channel_id)
            res = urlquick.post(
                GET_CHANNEL_URL + "?langId=6",
                data="stream_type=Seek&channel_id=" + chan,
                verify=False,
                headers=sony_headers,
                max_age=-1,
            )
            resp = res.json()
            onlyUrl = resp.get("result", "").split("?")[0].split("/")[-1]
            cookie = "__hdnea__" + resp.get("result", "").split("__hdnea__")[-1]
            headers["cookie"] = cookie
            uriToUse = resp.get("result", "")

        art = {
            "thumb": IMG_CATCHUP + onlyUrl.replace(".m3u8", ".png"),
            "icon": IMG_CATCHUP + onlyUrl.replace(".m3u8", ".png"),
        }

        qltyopt = Settings.get_string("quality")
        lowq_test = Settings.get_boolean("lowq")
        if lowq_test:
            qltyopt = "Lowest"
            Script.log("WATCHDOG: LOW-Q TEST active, forcing lowest bitrate", lvl=Script.INFO)
        selectionType = "adaptive"
        isMpd = Settings.get_boolean("usempd") and bool(resp) and bool(resp.get("mpd", False))
        if isMpd:
            license_headers = headers
            license_headers["Content-type"] = urlencode("application/octet-stream")
            if Settings.get_boolean("mpdnotice"):
                Script.notify(
                    "Notice!", "Using the Experimental MPD URL", icon=Script.NOTIFY_INFO
                )
            uriToUse = resp.get("mpd", "").get("result", "")
        if qltyopt == "Ask-me":
            selectionType = "ask-quality"
        if qltyopt == "Manual":
            selectionType = "manual-osd"
        if not isMpd and not qltyopt == "Manual":
            m3u8Headers = {
                "user-agent": "jiotv",
                "cookie": headers["cookie"],
                "content-type": "application/vnd.apple.mpegurl",
                "Accesstoken": sony_headers["Accesstoken"],
            }
            if channel_id in ZEE_RANGE:
                m3u8Res = urlquick.get(
                    uriToUse,
                    headers=headerszee,
                    verify=False,
                    max_age=-1,
                    raise_for_status=True,
                )
            else:
                m3u8Res = urlquick.get(
                    uriToUse,
                    headers=m3u8Headers,
                    verify=False,
                    max_age=-1,
                    raise_for_status=True,
                )
            m3u8Headers = {k: str(v) for k, v in m3u8Headers.items() if v}
            m3u8String = m3u8Res.text
            variant_m3u8 = m3u8.loads(m3u8String)
            if variant_m3u8.is_variant and (
                variant_m3u8.version is None or variant_m3u8.version < 7
            ):
                quality = quality_to_enum(qltyopt, len(variant_m3u8.playlists))
                tmpurl = variant_m3u8.playlists[quality].uri
                if isCatchup:
                    tmpurl = variant_m3u8.playlists[quality].uri
                    if "?" in tmpurl:
                        uriToUse = uriToUse.split("?")[0].replace(onlyUrl, tmpurl)
                    else:
                        uriToUse = uriToUse.replace(onlyUrl, tmpurl.split("?")[0])

        if isMpd:
            license_key = (
                "?" + urlencode("Content-type=application/octet-stream")
                + "|" + urlencode(headers) + "|R{SSM}|"
            )
        else:
            license_key = "|" + urlencode(headers) + "|R{SSM}|"

        if channel_id in zee_channels:
            direct_headers = headerszee
        else:
            direct_headers = m3u8Headers

        info = {
            "mode": "direct" if channel_id in DIRECT_IDS else "codequick",
            "channel_id": str(channel_id),
            "url": uriToUse,
            "art": art,
            "headers": headers,
            "direct_headers": direct_headers,
            "select_type": selectionType,
            "isMpd": bool(isMpd),
            "license_key": license_key,
        }
        Script.log(
            "WATCHDOG: _resolve_stream OK channel=%s mode=%s url=%s"
            % (channel_id, info["mode"], uriToUse),
            lvl=Script.DEBUG,
        )
        return info
    except Exception as e:
        Script.log(
            "WATCHDOG: _resolve_stream FAILED for channel %s: %s" % (channel_id, e),
            lvl=Script.ERROR,
        )
        return None


def _start_watchdog(channel_id, showtime=None, srno=None, programId=None, begin=None, end=None):
    """Start the stall-recovery watchdog thread for the current playback session."""
    try:
        enable = Settings.get_boolean("reconnect")
        if not enable:
            Script.log(
                "WATCHDOG: auto-recover disabled by settings; NOT starting watchdog",
                lvl=Script.WARNING,
            )
            return
        try:
            attempts = int(Settings.get_string("reconnect_attempts"))
        except Exception:
            attempts = 3
        try:
            stall = int(Settings.get_string("reconnect_stall"))
        except Exception:
            stall = 8
        if attempts < 1:
            attempts = 1
        if stall < 3:
            stall = 3

        def refresh():
            return _resolve_stream(channel_id, showtime, srno, programId, begin, end)

        t = threading.Thread(
            target=watchdog,
            args=(str(channel_id), refresh, attempts, stall, True),
            name="JioTV-Watchdog",
        )
        t.setDaemon(True)
        t.start()
        Script.log(
            "WATCHDOG: watchdog thread started for channel %s"
            % channel_id,
            lvl=Script.INFO,
        )
    except Exception as e:
        Script.log(
            "WATCHDOG: failed to start watchdog: %s" % e,
            lvl=Script.ERROR,
        )


# Play live stream/ catchup according to params.
# Also insures that user is logged in.
@Resolver.register
@isLoggedIn
def play(
    plugin, channel_id, showtime=None, srno=None, programId=None, begin=None, end=None
):
    try:
        is_helper = inputstreamhelper.Helper("mpd", drm="com.widevine.alpha")
        hasIs = is_helper.check_inputstream()
        if not hasIs:
            return

        info = _resolve_stream(channel_id, showtime, srno, programId, begin, end)
        if not info:
            return False

        _start_watchdog(channel_id, showtime, srno, programId, begin, end)

        if info["mode"] == "direct":
            dialog = xbmcgui.DialogProgress()
            dialog.create("Loading Stream", "Please wait... buffering...")
            xbmc.sleep(1500)
            dialog.close()

            listitem = xbmcgui.ListItem(path=info["url"])
            listitem.setProperty("IsPlayable", "true")
            listitem.setProperty("inputstream", "inputstream.adaptive")
            listitem.setProperty("inputstream.adaptive.manifest_type", "hls")
            dh = info.get("direct_headers")
            if dh:
                enc = urlencode(dh)
                listitem.setProperty("inputstream.adaptive.stream_headers", enc)
                listitem.setProperty("inputstream.adaptive.manifest_headers", enc)
            listitem.setMimeType("application/vnd.apple.mpegurl")
            xbmcplugin.setResolvedUrl(
                handle=int(sys.argv[1]), succeeded=True, listitem=listitem
            )
            listitem.setContentLookup(False)
            sony_channels = [
                "154", "289", "291",
                "5001", "5002", "5003", "5004", "5005", "5006", "5007", "5008", "5009",
                "5010", "5011", "5012", "5013", "5014", "5015", "5016", "5017", "5018",
                "5019", "5020", "5021", "5022", "5023", "5024", "5025", "5026",
            ]
            callback_value = info["url"] if channel_id in sony_channels else None
            xbmc.Player().play(info["url"], listitem)

            # Return dummy ListItem to avoid error popup
            return Listitem().from_dict(
                **{
                    "label": "Sony",
                    "art": info["art"],
                    "callback": callback_value,
                    "properties": {},
                }
            )
        else:
            return Listitem().from_dict(
                **{
                    "label": plugin._title,
                    "art": info["art"],
                    "callback": info["url"] + "|verifypeer=false",
                    "properties": {
                        "IsPlayable": True,
                        "inputstream": "inputstream.adaptive",
                        "inputstream.adaptive.stream_selection_type": info["select_type"],
                        "inputstream.adaptive.chooser_resolution_secure_max": "4k",
                        "inputstream.adaptive.stream_headers": urlencode(info["headers"]),
                        "inputstream.adaptive.manifest_headers": urlencode(info["headers"]),
                        "inputstream.adaptive.manifest_type": "mpd" if info["isMpd"] else "hls",
                        "inputstream.adaptive.license_type": "drm",
                        "inputstream.adaptive.license_key": info["license_key"],
                    },
                }
            )
    except Exception as e:
        Script.notify("headers - Error while playback , Check connection", e)
        return False


# Login `route` to access from Settings


@Script.register
def login(plugin):
    method = Dialog().yesno(
        "Login", "Select Login Method", yeslabel="Keyboard", nolabel="WEB"
    )
    if method == 1:
        login_type = Dialog().yesno(
            "Login", "Select Login Type", yeslabel="OTP", nolabel="Password"
        )
        if login_type == 1:
            mobile = Settings.get_string("mobile")
            if not mobile or (len(mobile) != 10):
                mobile = Dialog().numeric(0, "Enter your Jio mobile number")
                ADDON.setSetting("mobile", mobile)
            error = sendOTPV2(mobile)
            if error:
                Script.notify("Login Error", error)
                return
            otp = Dialog().numeric(0, "Enter OTP")
            ULogin(mobile, otp, mode="otp")
        elif login_type == 0:
            username = keyboard("Enter your Jio mobile number or email")
            password = keyboard("Enter your password", hidden=True)
            ULogin(username, password)
    elif method == 0:
        pDialog = DialogProgress()
        pDialog.create(
            "JioTV", "Visit [B]http://%s:48996/[/B] to login" % get_local_ip()
        )
        for i in range(120):
            sleep(1)
            with PersistentDict("headers") as db:
                headers = db.get("headers")
            if headers or pDialog.iscanceled():
                break
            pDialog.update(i)
        pDialog.close()


@Script.register
def setmobile(plugin):
    prevMobile = Settings.get_string("mobile")
    mobile = Dialog().numeric(0, "Update Jio mobile number", prevMobile)
    kodi_rpc("Addons.SetAddonEnabled", {"addonid": ADDON_ID, "enabled": False})
    ADDON.setSetting("mobile", mobile)
    kodi_rpc("Addons.SetAddonEnabled", {"addonid": ADDON_ID, "enabled": True})
    monitor.waitForAbort(1)
    Script.notify("Jio number set", "")


@Script.register
def applyall(plugin):
    kodi_rpc("Addons.SetAddonEnabled", {"addonid": ADDON_ID, "enabled": False})
    monitor.waitForAbort(1)
    kodi_rpc("Addons.SetAddonEnabled", {"addonid": ADDON_ID, "enabled": True})
    monitor.waitForAbort(1)
    Script.notify("All settings applied", "")


# Logout `route` to access from Settings


@Script.register
def logout(plugin):
    ULogout()


# M3u Generate `route`
@Script.register
def m3ugen(plugin, notify="yes"):
    channels = getCachedChannels()
    dictionary = getCachedDictionary()
    GENRE_MAP = dictionary.get("channelCategoryMapping")
    LANG_MAP = dictionary.get("languageIdMapping")

    m3ustr = '#EXTM3U x-tvg-url="%s"\n' % EPG_SRC

    for i, channel in enumerate(channels):
        channel_id = int(channel.get("channel_id"))
        
        if 5000 <= channel_id <= 5022:
            continue  # 💡 Skip ZEE range from default block, handle separately below

        if str(channel.get("channelLanguageId")) not in LANG_MAP.keys():
            lang = "Extra"
        else:
            lang = LANG_MAP[str(channel.get("channelLanguageId"))]

        if str(channel.get("channelCategoryId")) not in GENRE_MAP.keys():
            genre = "Extragenre"
        else:
            genre = GENRE_MAP[str(channel.get("channelCategoryId"))]

        if not Settings.get_boolean(lang):
            continue

        group = lang + ";" + genre
        _play_url = PLAY_URL + "channel_id={0}".format(channel_id)

        catchup = ""
        if channel.get("isCatchupAvailable"):
            catchup = ' catchup="vod" catchup-source="{0}channel_id={1}&showtime={{H}}{{M}}{{S}}&srno={{Y}}{{m}}{{d}}&programId={{catchup-id}}" catchup-days="7"'.format(
                PLAY_URL, channel_id
            )

        m3ustr += M3U_CHANNEL.format(
            tvg_id=channel_id,
            channel_name=channel.get("channel_name"),
            group_title=group,
            tvg_chno=int(channel.get("channel_order", i)) + 1,
            tvg_logo=IMG_CATCHUP + channel.get("logoUrl", ""),
            catchup=catchup,
            play_url=_play_url,
        )

    # ✅ Hardcoded ZEE channels JSON (you can import or load from file as needed)
    zee_channels = [
            {"@id": "5016", "display-name": "Zee Anmol Cinema", "icon": {"@src": "https://akamaividz2.zee5.com/image/upload/w_396,h_224,c_scale,f_webp,q_auto:eco/resources/0-9-zeeanmol/cover/1920x77021724318"}},
            {"@id": "5017", "display-name": "Zee Action", "icon": {"@src": "https://akamaividz2.zee5.com/image/upload/w_396,h_224,c_scale,f_webp,q_auto:eco/resources/0-9-zeeaction/cover/1920x770126103899"}},
            {"@id": "5023", "display-name": "Zee Chitramandir", "icon": {"@src": "https://akamaividz2.zee5.com/image/upload/w_1755,h_987,c_scale,f_webp,q_auto:eco/resources/0-9-394/list_clean/1920x1080liste8fe4dcfd539403d973018b5d3e16309.png"}},
            {"@id": "5024", "display-name": "Zee Anmol TV", "icon": {"@src": "https://akamaividz2.zee5.com/image/upload/w_1755,h_987,c_scale,f_webp,q_auto:eco/resources/0-9-zeeanmol/list_clean/1920x1080list0481942c331940e0a2356355bcdec8bb.png"}},
            {"@id": "5025", "display-name": "Zee Anmol Cinema_2", "icon": {"@src": "https://akamaividz2.zee5.com/image/upload/w_396,h_224,c_scale,f_webp,q_auto:eco/resources/0-9-zeeanmol/cover/1920x77021724318"}},
            {"@id": "5026", "display-name": "Big Magic", "icon": {"@src": "https://akamaividz2.zee5.com/image/upload/w_396,h_224,c_scale,f_webp,q_auto:eco/resources/0-9-zeeanmol/cover/1920x77021724318"}},

    ]

    for zee in zee_channels:
        cid = zee["@id"]
        name = zee["display-name"]
        logo = zee["icon"]["@src"]

        m3ustr += (
            f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{name}" group-title="ZEE" tvg-logo="{logo}",{name}\n'
            f'plugin://plugin.video.jiotv/resources/lib/main/play/?channel_id={cid}\n'
        )

    with open(M3U_SRC, "w+", encoding="utf-8") as f:
        f.write(m3ustr.replace("\xa0", " "))

    if notify == "yes":
        Script.notify("JioTV", "Playlist updated.")



# EPG Generate `route`
@Script.register
def epg_setup(plugin):
    Script.notify("Please wait", "Epg setup in progress")
    pDialog = DialogProgress()
    pDialog.create("Epg setup in progress")
    # Download EPG XML file
    url = Settings.get_string("epgurl")
    if not url or (len(url) < 5):
        url = "https://kiranreddyrebel.github.io/epg.xml.gz"
    payload = {}
    headers = {}
    response = requests.request("GET", url, headers=headers, data=payload)
    # source_tree = ET.parse(CHANNELS_XML)
    # source_root = source_tree.getroot()
    with open(EPG_PATH, "wb") as f:
        f.write(response.content)
        # for chunk in response.iter_content(chunk_size=1024):
        #     if chunk:
        #         f.write(chunk)
    # Extract and parse the XML file
    pDialog.update(20)
    with gzip.open(EPG_PATH, "rb") as f:
        data = f.read()
        xml_content = data.decode("utf-8")
        root = ET.fromstring(xml_content)
    # Modify all the programs in the EPG
    # programs = root.findall('./programme')
    pDialog.update(30)
    # for channel in root.iterfind("channel"):
    #     root.remove(channel)
    pDialog.update(35)
    # Example: Modify the program and add catchupid
    # for channel in source_root.iterfind('channel'):
    #     new_channel = ET.Element(channel.tag, channel.attrib)
    #     for child in channel:
    #         new_child = ET.Element(child.tag, child.attrib)
    #         new_child.text = child.text
    #         new_channel.append(new_child)
    #     root.append(new_channel)
    pDialog.update(45)
    for program in root.iterfind(".//programme"):
        # Example: Modify the program and add catchupid
        icon = program.find("icon")
        icon_src = icon.get("src")
        jpg_name = icon_src.rsplit("/", 1)[-1]
        catchup_id = os.path.splitext(jpg_name)[0]
        program.set("catchup-id", catchup_id)
        title = program.find("title")
        title.text = title.text.strip()
    pDialog.update(60)
    # create the XML declaration and add it to the top of the file
    xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'

    # create the doctype declaration
    doctype_declaration = '<!DOCTYPE tv SYSTEM "xmltv.dtd">\n'
    full_xml_bytes = (
        xml_declaration.encode("UTF-8")
        + doctype_declaration.encode("UTF-8")
        + ET.tostring(root, encoding="UTF-8")
    )
    gzip_bytes = gzip.compress(full_xml_bytes)
    pDialog.update(80)
    with open(EPG_PATH, "wb") as f:
        f.write(gzip_bytes)
    pDialog.update(100)
    pDialog.close()
    Script.notify("JioTV", "Epg generated")


# PVR Setup `route` to access from Settings
@Script.register
def pvrsetup(plugin):
    executebuiltin("RunPlugin(plugin://plugin.video.jiotv/resources/lib/main/m3ugen/)")
    IDdoADDON = "pvr.iptvsimple"

    def set_setting(id, value):
        if Addon(IDdoADDON).getSetting(id) != value:
            Addon(IDdoADDON).setSetting(id, value)

    if check_addon(IDdoADDON):
        set_setting("m3uPathType", "0")
        set_setting("m3uPath", M3U_SRC)
        set_setting("epgPathType", "1")
        set_setting("epgUrl", EPG_SRC)
        set_setting("epgCache", "false")
        set_setting("useInputstreamAdaptiveforHls", "true")
        set_setting("catchupEnabled", "true")
        set_setting("catchupWatchEpgBeginBufferMins", "0")
        set_setting("catchupWatchEpgEndBufferMins", "0")
    _setup(M3U_SRC, EPG_SRC)


# Cache cleanup
@Script.register
def cleanup(plugin):
    urlquick.cache_cleanup(-1)
    cleanLocalCache()
    cleanup_signals()
    Script.notify("Cache Cleaned", "")


# Upload Kodi log to a paste service for remote debugging
@Script.register
def uploadlog(plugin):
    try:
        log_path = xbmcvfs.translatePath("special://logpath/kodi.log")
        if not xbmcvfs.exists(log_path):
            Script.notify("Upload Log", "kodi.log not found")
            return
        content = ""
        with xbmcvfs.File(log_path, "r") as f:
            content = f.read()
        if not content:
            Script.notify("Upload Log", "log is empty")
            return
        Script.notify("Upload Log", "Uploading kodi.log...")
        resp = requests.post(
            "https://paste.rs",
            data=content.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            timeout=60,
        )
        url = resp.text.strip()
        if not url.startswith("http"):
            Script.notify("Upload Log", "Upload failed: %s" % resp.status_code)
            return
        Script.log("UPLOADLOG: shared log at %s" % url, lvl=Script.INFO)
        Dialog().textviewer("JioTV - Log shared", "Share this link:\n\n%s\n\n" % url)
        try:
            xbmc.executebuiltin("Clipboard(%s)" % url)
        except Exception:
            pass
        Script.notify("Upload Log", "Log URL copied")
    except Exception as e:
        Script.log("UPLOADLOG: error: %s" % e, lvl=Script.ERROR)
        Script.notify("Upload Log", "Error: %s" % e)