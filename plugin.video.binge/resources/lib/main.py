# -*- coding: utf-8 -*-
# Tata Play Binge addon: routing + playback
import traceback
from urllib.parse import urlencode

import xbmcgui
from codequick import Route, Resolver, Listitem, Script, run
from codequick.script import Settings
from codequick.utils import keyboard

from resources.lib import utils, vod
from resources.lib.constants import ADDON_ID, REFERER, USER_AGENT

ICON = Script.get_info("icon")


def _default_art():
    return {"thumb": "", "icon": ICON, "fanart": ""}


# ------------------------------------------------------------------ root ---
@Route.register
def root(plugin):
    if not utils.isLoggedIn():
        yield Listitem.from_dict(
            **{
                "label": "Login with RMN + OTP",
                "art": _default_art(),
                "callback": Route.ref("/resources/lib/main:login_flow"),
            }
        )
        yield Listitem.from_dict(
            **{
                "label": "Login (OTP) via add-on settings",
                "art": _default_art(),
                "callback": "plugin://plugin.video.binge/resources/lib/main/login/",
            }
        )
    else:
        yield Listitem.from_dict(
            **{
                "label": "Zee TV (via Binge)",
                "art": _default_art(),
                "callback": Route.ref("/resources/lib/main:zee"),
            }
        )
        yield Listitem.from_dict(
            **{
                "label": "All Channels",
                "art": _default_art(),
                "callback": Route.ref("/resources/lib/main:channels"),
            }
        )
        yield Listitem.from_dict(
            **{
                "label": "OTT  (Series / Movies)",
                "art": _default_art(),
                "callback": Route.ref("/resources/lib/main:ott"),
            }
        )
        yield Listitem.from_dict(
            **{
                "label": "Reload channel list",
                "art": _default_art(),
                "callback": Route.ref("/resources/lib/main:reload"),
            }
        )
        yield Listitem.from_dict(
            **{
                "label": "Logout",
                "art": _default_art(),
                "callback": Route.ref("/resources/lib/main:logout"),
            }
        )
    yield Listitem.from_dict(
        **{
            "label": "Upload kodi.log for debugging",
            "art": _default_art(),
            "callback": Route.ref("/resources/lib/main:uploadlog"),
        }
    )


@Route.register
def login_flow(plugin):
    """In-add-on OTP login: RMN -> auto SID -> send OTP -> verify."""
    try:
        rmn = keyboard("Enter your Tata Play Binge registered mobile number")
        if not rmn:
            return False
        rmn = str(rmn).strip()
        Settings.set_string("rmn", rmn)
        sid = (Settings.get_string("sid") or "").strip()
        if not sid:
            sid = utils.lookupSid(rmn)
            if not sid:
                Script.notify(ADDON_ID, "No Binge subscriber found for this number.")
                return False
            Settings.set_string("sid", str(sid))
        resp = utils.generateOTP(rmn, sid)
        if resp.get("code") != 0:
            Script.notify(ADDON_ID, "OTP failed: %s" % (resp.get("message") or resp.get("msg")))
            return False
        otp = keyboard("Enter the OTP sent to +91 %s" % rmn)
        if not otp:
            return False
        error = utils.login_otp(rmn, sid, str(otp).strip())
        if error:
            Script.notify(ADDON_ID, "Login failed: %s" % error)
            return False
        Script.notify(ADDON_ID, Script.localize(32007))
        return False
    except Exception:
        utils.log_exc("login_flow")
        Script.notify(ADDON_ID, "Login failed - see kodi.log for details.")
        return False


# ---------------------------------------------- channel list helpers -------
def _channel_item(ch):
    cid = ch.get("id") or ch.get("channel_id") or ch.get("dvbTriplet")
    if cid is None:
        return None
    title = utils._channelTitle(ch) or str(cid)
    logo = utils._channelLogo(ch)
    info = {
        "label": title,
        "art": {"thumb": logo, "icon": logo or ICON, "fanart": logo},
        "info": {"title": title, "mediatype": "video"},
        "callback": play,
        "params": {"channel_id": str(cid)},
    }
    genre = utils._channelGenre(ch)
    if genre:
        info["info"]["genre"] = genre
    return Listitem.from_dict(**info)


def _catalog(plugin, channels):
    items = [_channel_item(ch) for ch in channels]
    items = [i for i in items if i]
    if not items:
        Script.notify(ADDON_ID, Script.localize(32012))
    for it in items:
        yield it


# -------------------------------------------------------------- sections ----
@Route.register
def zee(plugin):
    """Zee Network channels delivered through the Binge entitlement."""
    channels = [c for c in utils.getUserChannels()
                if "zee" in utils._channelTitle(c).lower()
                or "zee" in utils._channelGenre(c).lower()]
    yield from _catalog(plugin, channels)


@Route.register
def channels(plugin):
    yield from _catalog(plugin, utils.getUserChannels())


# ================================================================== OTT ====
def _ott_img(item):
    return item.get("image") or ""


@Route.register
def ott(plugin):
    """OTT (series/movies) browse menu: vendors, search, and curated browse."""
    yield Listitem.from_dict(**{
        "label": "Search OTT  /  Series",
        "art": _default_art(),
        "callback": Route.ref("/resources/lib/main:ott_search"),
    })
    yield Listitem.from_dict(**{
        "label": "Browse-by (Genres / Languages / Providers)",
        "art": _default_art(),
        "callback": Route.ref("/resources/lib/main:ott_browse", params={"page": "BROWSE"}),
    })
    yield Listitem.from_dict(**{
        "label": "Movies",
        "art": _default_art(),
        "callback": Route.ref("/resources/lib/main:ott_rail", params={"rail": "MOVIES"}),
    })
    yield Listitem.from_dict(**{
        "label": "TV Shows",
        "art": _default_art(),
        "callback": Route.ref("/resources/lib/main:ott_rail", params={"rail": "TV_SHOWS"}),
    })


@Route.register
def ott_search(plugin):
    query = keyboard("Search Tata Play Binge OTT")
    if not query:
        return False
    items = vod.normalize_items(vod._items(vod.search(query)))
    if not items:
        Script.notify(ADDON_ID, "No OTT results (check login / network).")
    yield from _ott_items(plugin, items, seasons=True)


@Route.register
def ott_browse(plugin, page):
    """Fetch a browse-by page and list its rails (genre/language/provider)."""
    data = vod.getBrowsePage(page)
    items = vod._items(data)
    if not items:
        Script.notify(ADDON_ID, "Browse page unavailable (session may be required).")
        return
    for it in items:
        title = it.get("title") or it.get("name") or ""
        rid = it.get("id") or it.get("railId")
        if not title or rid is None:
            continue
        yield Listitem.from_dict(**{
            "label": title,
            "art": _default_art(),
            "callback": Route.ref("/resources/lib/main:ott_rail", params={"rail": str(rid)}),
        })


@Route.register
def ott_rail(plugin, rail):
    """List a rail's content (by id or a known section key)."""
    items = vod.normalize_items(vod._items(vod.getRail(rail)))
    if not items:
        Script.notify(ADDON_ID, "Rail empty/unavailable.")
        return
    yield from _ott_items(plugin, items, seasons=True)


def _ott_items(plugin, items, seasons=False):
    seen = set()
    for it in items:
        cid = it.get("contentId")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        li = {
            "label": it.get("title") or cid,
            "art": {"thumb": _ott_img(it), "icon": _ott_img(it) or ICON,
                    "fanart": _ott_img(it)},
            "info": {"title": it.get("title") or cid, "mediatype": "video"},
        }
        if it.get("provider"):
            li["info"]["studio"] = it["provider"]
        if seasons:
            li["callback"] = Route.ref("/resources/lib/main:ott_item",
                                       params={"contentId": cid})
        else:
            li["callback"] = Route.ref("/resources/lib/main:ott_notice",
                                       params={"title": li["label"]})
        yield Listitem.from_dict(**li)


@Script.register
def ott_notice(plugin=None, title=""):
    Script.notify(ADDON_ID,
                  "OTT playback requires the partner DRM API which is not public; "
                  "this build delivers OTT catalogue browsing. "
                  "Live channels play via All Channels / Zee TV.")


@Route.register
def ott_item(plugin, contentId):
    """Item details -> seasons -> episodes. Best-effort playback at leaf."""
    seasons = vod._items(vod.getSeasons(contentId))
    if not seasons:
        # not a series / detail not found; try direct info
        info = vod._data(vod.getContentInfo(contentId))
        fig = vod.normalize_items([info]) if info else []
        if fig:
            yield from _ott_items(plugin, fig)
        else:
            yield Listitem.from_dict(**{
                "label": "No seasons found - title may still be live-stream TBD",
                "art": _default_art(),
                "callback": Route.ref("/resources/lib/main:ott_notice"),
            })
        return
    for s in seasons:
        sid = s.get("id") or s.get("seasonId") or s.get("contentId")
        title = s.get("title") or s.get("name") or ("Season " + str(s.get("seasonNum", "")))
        yield Listitem.from_dict(**{
            "label": title,
            "art": _default_art(),
            "callback": Route.ref("/resources/lib/main:ott_season",
                                  params={"seasonId": str(sid)}),
        })


@Route.register
def ott_season(plugin, seasonId):
    episodes = vod.normalize_items(vod._items(vod.getContentInfo(seasonId)))
    if episodes:
        yield from _ott_items(plugin, episodes, seasons=False)
    else:
        # try series list for episodes of this season obj
        ep = vod.normalize_items(vod._items(vod.getSeasons(seasonId)))
        yield from _ott_items(plugin, ep, seasons=False)


# The catalogue/browse layer is delivered through this addon. Actual streaming of
# OTT-partner titles (Zee5/SonyLIV/JioHotstar etc.) requires each partner's
# proprietary DRM/playback API, which is not part of the public VideoReady surface.
# Selecting a title therefore surfaces this notice rather than a dead item.


# ================================================================ playback ===
@Resolver.register
def play(plugin, channel_id):
    if not utils.isLoggedIn():
        Script.notify(ADDON_ID, "Login required. Add your RMN/SID and verify OTP in add-on settings.")
        return False

    try:
        mpd, lic = utils.resolvePlayback(channel_id)
    except Exception:
        utils.log_exc("play resolve cid=%s" % channel_id)
        Script.notify(ADDON_ID, "Playback error - see kodi.log for details.")
        return False
    if not mpd or not lic:
        Script.notify(ADDON_ID, "No stream available for this channel/title.")
        return False

    headers = {
        "Referer": REFERER,
        "User-Agent": USER_AGENT,
        "Content-Type": "application/octet-stream",
    }
    license_key = lic + "|" + urlencode(headers) + "|R{SSM}|"

    return Listitem.from_dict(
        **{
            "label": plugin._title if plugin._title else channel_id,
            "art": _default_art(),
            "callback": mpd + "|verifypeer=false",
            "properties": {
                "IsPlayable": True,
                "inputstream": "inputstream.adaptive",
                "inputstream.adaptive.stream_selection_type": "adaptive",
                "inputstream.adaptive.chooser_resolution_secure_max": "4k",
                "inputstream.adaptive.stream_headers": urlencode(headers),
                "inputstream.adaptive.manifest_headers": urlencode(headers),
                "inputstream.adaptive.manifest_type": "mpd",
                "inputstream.adaptive.license_type": "com.widevine.alpha",
                "inputstream.adaptive.license_key": license_key,
            },
        }
    )


# ------------------------------------------------------ settings actions ----
@Script.register
def login(plugin):
    Script.open_settings()


@Script.register
def sendotp(plugin):
    try:
        rmn = Settings.get_string("rmn") or ""
        if not rmn:
            Script.notify(ADDON_ID, "Enter your registered mobile number first.")
            return
        sid = Settings.get_string("sid") or ""
        if not sid:
            sid = utils.lookupSid(rmn)
            if sid:
                Settings.set_string("sid", sid)
        resp = utils.generateOTP(rmn, sid)
        if resp.get("code") == 0:
            Script.notify(ADDON_ID, "OTP sent. Enter it below and tap Verify.")
        else:
            utils.log("sendotp: API rejected: %s" % utils._safe(resp), lvl=Script.ERROR)
            Script.notify(ADDON_ID, "OTP failed: %s" % (resp.get("message") or resp.get("msg")))
    except Exception:
        utils.log_exc("sendotp")
        xbmcgui.Dialog().textviewer(
            "Tata Play Binge - Send OTP failed",
            "Please screenshot this for the developer:\n\n" + (traceback.format_exc() or "")[-1500:])


@Script.register
def dologin(plugin):
    try:
        rmn = Settings.get_string("rmn") or ""
        sid = Settings.get_string("sid") or ""
        otp = Settings.get_string("otp") or ""
        if not (rmn and otp):
            Script.notify(ADDON_ID, "Missing RMN or OTP.")
            return
        if not sid:
            sid = utils.lookupSid(rmn)
            if sid:
                Settings.set_string("sid", sid)
        error = utils.login_otp(rmn, sid, otp)
        if error:
            Script.notify(ADDON_ID, "Login failed: %s" % error)
        else:
            Script.notify(ADDON_ID, Script.localize(32007))
    except Exception:
        utils.log_exc("dologin")
        xbmcgui.Dialog().textviewer(
            "Tata Play Binge - Login failed",
            "Please screenshot this for the developer:\n\n" + (traceback.format_exc() or "")[-1500:])


@Script.register
def logout(plugin):
    utils.logout()
    Script.notify(ADDON_ID, Script.localize(32011))


@Script.register
def reload(plugin):
    utils.getChannelList(refresh=True)
    Script.notify(ADDON_ID, Script.localize(32014))


@Script.register
def m3ugen(plugin):
    utils.exportM3U()


@Script.register
def uploadlog(plugin):
    """Read kodi.log and post it to paste.rs for remote debugging."""
    try:
        import xbmcvfs
        import xbmc
        import requests
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
            data=content if isinstance(content, bytes) else content.encode("utf-8", "replace"),
            headers={"Content-Type": "text/plain"},
            timeout=60,
        )
        url = resp.text.strip()
        if not url.startswith("http"):
            raise IOError("paste.rs returned HTTP %s" % resp.status_code)
        utils.log("UPLOADLOG: shared log at %s" % url)
        xbmcgui.Dialog().textviewer("Tata Play Binge - Log shared",
                                    "Share this link:\n\n%s\n\n" % url)
        try:
            xbmc.executebuiltin("Clipboard(%s)" % url)
        except Exception:
            pass
        Script.notify("Upload Log", "Log URL copied")
    except Exception:
        tb = (traceback.format_exc() or "")[-1500:]
        utils.log_exc("uploadlog")
        xbmcgui.Dialog().textviewer(
            "Tata Play Binge - Upload failed",
            "The log could not be uploaded (network/paste.rs may be blocked). "
            "Please screenshot this for the developer:\n\n" + tb)