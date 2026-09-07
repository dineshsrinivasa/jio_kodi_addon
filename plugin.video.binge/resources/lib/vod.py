# -*- coding: utf-8 -*-
# Tata Play Binge OTT (VOD) catalogue browsing layer.
#
# Endpoint shapes discovered from the official Binge web bundle (tb.tapi.videoready.tv).
# NOTE: these are undocumented and require an authenticated session (bearer access token).
# Every call is guarded so a failure degrades gracefully instead of crashing the addon.
import requests

from resources.lib import utils
from resources.lib.constants import BINGE_API_BASE
from codequick import Script

TIMEOUT = 25


def _session_headers(extra=None):
    session = utils.getSession()
    h = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "platform": "BINGE_ANYWHERE",
        "locale": "IND",
        "devicetype": "WEB",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    }
    if session and session.get("accessToken"):
        h["authorization"] = "bearer " + session["accessToken"]
        if session.get("sid"):
            h["x-subscriber-id"] = str(session["sid"])
        if session.get("sName"):
            h["x-subscriber-name"] = str(session["sName"])
        if session.get("profileId"):
            h["profileid"] = str(session["profileId"])
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
    items = d.get("items") or d.get("contentList") or d.get("list") or d.get("content") or []
    if isinstance(items, dict):
        items = items.get("items") or items.get("list") or []
    return items or []


def getBrowsePage(page):
    """Fetch a browse-by page config (rails: language/genre/provider/category)."""
    return _get_logged("homescreen-client/pub/api/v1/page/{0}/BINGE_ANYWHERE".format(page))


def getRail(rail_id, limit=100):
    """Fetch rail content by rail id."""
    return _get("homescreen-client/pub/api/v3/rail",
                params={"id": rail_id, "limit": limit, "allowBingeRepositioning": "true"})


def getSeeAll(rail_id, offset=0, limit=100):
    return _get("homescreen-client/pub/api/v4/rail/seeAll",
                params={"id": rail_id, "limit": limit, "Offset": offset})


def search(query, offset=0, limit=100):
    return _get_logged("search-connector/binge/anywhere/search",
                       params={"queryString": query, "limit": limit, "offset": offset})


def getSeasons(content_id):
    return _get("content-subscriber-detail/api/series/list/" + str(content_id))


def getContentInfo(content_id):
    return _get("content-subscriber-detail/api/content/info/" + str(content_id))


def getContentPackage(offset=0, maxn=100):
    """Subscribed partner OTT apps (like Jio-Hotstar style provider list)."""
    d = _data(_get("homescreen-client/pub/api/v1/page/HOME/BINGE_ANYWHERE"))
    return d


# ------------------------------------------------------------ discovery ------
def collect_rails(pages=("HOME", "BROWSE", "LANGUAGE")):
    """Collect (title, rail_id, kind) rails across the known browse pages.

    kind is best-effort: 'language' if title hints a language, 'provider' if it
    hints a known partner app, else 'category'. Duplicates are dropped.
    """
    langs = {"kannada", "hindi", "tamil", "telugu", "malayalam", "marathi",
             "bengali", "punjabi", "gujarati", "english", "odia", "bhojpuri"}
    providers = {"zee5", "jiohotstar", "sonyliv", "amazon", "prime", "apple",
                 "discovery", "aha", "netflix", "sunnxt", "hungama", "mx",
                 "lionsgate", "shemaroo", "fancode", "bbc", "ultra", "epic",
                 "chaupal", "namma", "playflix", "manorama", "waves", "stage"}
    found = {}
    for page in pages:
        data = _get_logged("homescreen-client/pub/api/v1/page/{0}/BINGE_ANYWHERE".format(page))
        for it in _items(data):
            title = (it.get("title") or it.get("name") or "").strip()
            rid = it.get("id") or it.get("railId")
            if not title or rid is None or str(rid) in found:
                continue
            lw = title.lower()
            kind = "category"
            for l in langs:
                if l in lw:
                    kind = "language"
                    break
            if kind == "category":
                for p in providers:
                    if p in lw.replace(" ", ""):
                        kind = "provider"
                        break
            found[str(rid)] = {"title": title, "rail": str(rid), "kind": kind}
    return list(found.values())


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
               or it.get("imageUrl") or it.get("image") or "")
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