# -*- coding: utf-8 -*-
# Tata Play Binge OTT (VOD) catalogue browsing layer.
#
# Endpoint shapes discovered from the official Binge web bundle (tb.tapi.videoready.tv).
# The hierarchy endpoint (DONGLE_HOMEPAGE) is the primary entry point for OTT browse.
# Every call is guarded so a failure degrades gracefully instead of crashing the addon.
import requests

from codequick.storage import PersistentDict

from resources.lib import utils
from resources.lib.constants import BINGE_API_BASE, SESSION_KEY
from codequick import Script

TIMEOUT = 25


def _bm_cred():
    """Registered device credentials (anonymousid + deviceid) as used by the Binge web app."""
    with PersistentDict(SESSION_KEY) as db:
        cred = db.get("bm_device") or {}
    return cred or {}


def _session_headers(extra=None):
    session = utils.getSession()
    h = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "platform": "BINGE_ANYWHERE",
        "locale": "IND",
        "deviceName": "Web",
        "deviceType": "WEB",
        "apiVersion": "v3",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    }
    cred = _bm_cred()
    if cred.get("deviceId"):
        h["deviceid"] = str(cred["deviceId"])
        h["deviceId"] = str(cred["deviceId"])
    if cred.get("anonymousId"):
        h["anonymousid"] = str(cred["anonymousId"])
        h["anonymousId"] = str(cred["anonymousId"])
    if session:
        if session.get("accessToken"):
            h["authorization"] = "bearer " + session["accessToken"]
        if session.get("sid"):
            h["x-subscriber-id"] = str(session["sid"])
            h["x-authenticated-userid"] = str(session["sid"])
            h["subscriberId"] = str(session["sid"])
        if session.get("sName"):
            h["x-subscriber-name"] = str(session["sName"])
        if session.get("profileId"):
            h["profileid"] = str(session["profileId"])
            h["profileId"] = str(session["profileId"])
        if session.get("baId"):
            h["baId"] = str(session["baId"])
        if session.get("deviceToken"):
            h["devicetoken"] = str(session["deviceToken"])
            h["deviceToken"] = str(session["deviceToken"])
        if session.get("dthStatus"):
            h["dthStatus"] = str(session["dthStatus"])
    if extra:
        h.update(extra)
    return h


def _get(path, params=None, extra_headers=None, timeout=TIMEOUT):
    """GET against the Binge API base. Returns parsed json or None."""
    url = BINGE_API_BASE.rstrip("/") + "/" + path.lstrip("/")
    try:
        resp = requests.get(url, params=params, headers=_session_headers(extra_headers),
                            verify=False, timeout=timeout)
        data = resp.json()
        if data.get("code") not in (0, 200, None):
            utils.log("vod %s: code=%s %s" % (path, data.get("code"), utils._safe(data)), lvl=Script.ERROR)
        return data
    except Exception:
        utils.log_exc("vod _get " + path)
        return None


def _get_logged(path, params=None):
    data = _get(path, params)
    if data is None:
        utils.log("vod %s => no response (timeout/network)" % path, lvl=Script.ERROR)
    elif not _data(data):
        utils.log("vod %s => code not 0/200: %s" % (path, utils._safe(data)), lvl=Script.ERROR)
    return data


def _data(data):
    if not data or data.get("code") not in (0, 200):
        return None
    return data.get("data")


def _items(data):
    d = _data(data)
    if not d:
        return []
    if isinstance(d, list):
        return d
    items = (d.get("items") or d.get("contentList") or d.get("list") or d.get("content")
             or d.get("rails") or d.get("railList"))
    if isinstance(items, dict):
        items = items.get("items") or items.get("list") or items.get("rails") or []
    return items or []


# ------------------------------------------------------------------ hierarchy ---
def getHierarchy(page="DONGLE_HOMEPAGE"):
    """Fetch the full hierarchy for a browse page. Returns raw data (list of rails)."""
    return _get_logged("homescreen-client/pub/api/v2/hierarchy/{0}".format(page))


def _hierarchy_rails(page="DONGLE_HOMEPAGE"):
    """Extract rail dicts from a hierarchy response."""
    data = getHierarchy(page)
    d = _data(data)
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        return d.get("rails") or d.get("railList") or []
    return []


_SKIP_SOURCES = ("HERO_BANNER", "MID_SCROLL_BANNER", "LIVE_EVENT_BANNER", "SPECIAL_BANNER_RAIL",
                 "CONTINUE_WATCHING", "WATCHLIST")


def list_rails(page="DONGLE_HOMEPAGE", skip_banners=True):
    """List the rails of a browse page as [(rail_id, title), ...]."""
    out = []
    seen = set()
    for it in _hierarchy_rails(page):
        rid = it.get("railId") or it.get("id")
        title = (it.get("railTitle") or it.get("title") or it.get("name") or "").strip()
        src = it.get("sectionSource") or ""
        if rid is None or not title or str(rid) in seen:
            continue
        if skip_banners and src and any(src.startswith(s) or src == s for s in _SKIP_SOURCES):
            continue
        seen.add(str(rid))
        out.append((str(rid), title))
    return out


def find_rail_on_page(page, subtitle):
    """Find a rail on a browse page whose title contains subtitle (case-insensitive)."""
    sub = subtitle.lower()
    for rid, title in list_rails(page, skip_banners=False):
        if sub in title.lower():
            return rid
    return None


def provider_page(provider):
    """Map a partner-app name to its DONGLE_* hierarchy page."""
    key = provider.lower().replace(" ", "").replace("_", "")
    if key in ("jiohotstar", "hotstar"):
        return "DONGLE_HOTSTAR"
    if key == "zee5":
        return "DONGLE_ZEE5"
    return "DONGLE_" + key.upper()


def getRail(rail_id, limit=100):
    """Fetch rail content by rail id. VRNNRAILFILTER + userSelectedApps=All are required."""
    params = {
        "id": rail_id,
        "limit": limit,
        "userSelectedApps": "All",
        "allowBingeRepositioning": "true",
    }
    return _get("homescreen-client/api/v3/rail", params=params, extra_headers={"rule": "VRNNRAILFILTER"})


def getSeeAll(rail_id, offset=0, limit=100):
    """Fetch seeAll content. Note: endpoint may be broken server-side (startsWith TypeError)."""
    return _get("homescreen-client/pub/api/v4/rail/seeAll",
                params={"id": rail_id, "limit": limit, "Offset": offset})


def search(query, offset=0, limit=100):
    """Search OTT content. Tries multiple endpoints; returns None if all fail."""
    for path in ("search-connector/binge/anywhere/search",
                 "binge-media-search/pub/freemium/search/results",
                 "search-connector/freemium/search/results"):
        data = _get(path, params={"queryString": query, "limit": limit, "offset": offset})
        if data and _data(data) is not None:
            return data
    return None


def getSeasons(content_id):
    return _get("content-subscriber-detail/api/series/list/" + str(content_id))


def getContentInfo(content_id):
    return _get("content-subscriber-detail/api/content/info/" + str(content_id))


# ---------------------------------------------------------------- items ------
def _langs(it):
    """Collect language info from a raw item across the shapes Binge uses."""
    langs = []
    for key in ("language", "languages", "lang", "subTitles", "subtitle",
                "audioLanguages", "audio_languages", "availLanguages"):
        v = it.get(key)
        if isinstance(v, list):
            for x in v:
                if isinstance(x, dict):
                    if x.get("name") or x.get("value"):
                        langs.append(str(x.get("name") or x.get("value")))
                elif x:
                    langs.append(str(x))
        elif v:
            langs.append(str(v))
    return langs


def filter_items(items, provider=None, lang=None):
    """Client-side filter of normalised items by provider and/or language (case-insensitive)."""
    out = []
    for it in items:
        if provider:
            prov = (it.get("provider") or "").lower()
            if provider.lower() not in prov:
                continue
        if lang:
            langs = " ".join(it.get("langs") or [])
            if lang.lower() not in langs.lower():
                continue
        out.append(it)
    return out


def normalize_items(items):
    """Normalise raw rail items into a common dict for the Kodi listing."""
    out = []
    for it in items or []:
        content = it.get("content") or it
        cid = content.get("contentId") or it.get("id")
        title = (content.get("title") or content.get("name")
                 or it.get("title") or it.get("name") or "")
        img = (content.get("imageUrl") or content.get("image")
               or content.get("posterImage") or content.get("boxCoverImage")
               or it.get("imageUrl") or it.get("image")
               or it.get("posterImage") or it.get("boxCoverImage") or "")
        provider = content.get("provider") or it.get("provider") or ""
        ctype = it.get("railType") or content.get("contentType") or it.get("contentType") or ""
        providerContentId = content.get("providerContentId") or it.get("providerContentId")
        langs = _langs(it) or _langs(content)
        out.append({
            "contentId": str(cid) if cid is not None else None,
            "title": title,
            "image": img,
            "provider": provider,
            "providerContentId": str(providerContentId) if providerContentId else None,
            "contentType": ctype,
            "langs": langs,
            "raw": it,
        })
    return out
