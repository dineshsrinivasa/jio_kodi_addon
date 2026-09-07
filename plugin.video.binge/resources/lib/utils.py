# -*- coding: utf-8 -*-
import json
import time
import traceback
from urllib.parse import quote

import requests
import urlquick
from codequick import Script
from codequick.script import Settings
from codequick.storage import PersistentDict

from resources.lib import constants


def log(msg, lvl=Script.INFO):
    try:
        Script.log("BINGE: " + msg, lvl=lvl)
    except Exception:
        pass


def log_exc(where):
    try:
        log("%s failed: %s" % (where, traceback.format_exc()[-1200:]), lvl=Script.ERROR)
    except Exception:
        pass


def _safe(data):
    """Return a small diagnostic preview of a response body with secrets masked."""
    if data is None:
        return "None"
    if isinstance(data, dict):
        out = {}
        for k, v in list(data.items())[:8]:
            vv = v
            if isinstance(vv, str) and len(vv) > 60:
                vv = vv[:20] + "...(%d chars)" % len(vv)
            if k.lower() in ("authorization", "accessToken", "token", "otp", "jwt"):
                vv = "<masked>"
            out[k] = vv
        return json.dumps(out)[:900]
    s = str(data)
    return s[:900]


def get_opt_quality():
    q = Settings.get_string("quality") or "HD"
    return {
        "SD": 0,
        "HD": 1,
        "Full HD": 2,
        "4K": 3,
    }.get(q, 1)


def get_headers(auth=False, token=None):
    headers = {
        "x-app-id": constants.X_APP_ID,
        "x-app-key": constants.X_APP_KEY,
        "x-api-key": constants.X_API_KEY,
        "Content-Type": "application/json",
        "User-Agent": constants.USER_AGENT,
        "Referer": constants.REFERER,
    }
    if auth:
        headers["device_details"] = constants.DEVICE_DETAILS
        headers["x-device-id"] = constants.X_DEVICE_ID
        headers["x-device-platform"] = constants.X_DEVICE_PLATFORM
        headers["x-device-type"] = constants.X_DEVICE_TYPE
    if token:
        headers["x-app-token"] = token
    return headers


# ------------------------------------------------------------------ session ---
def saveSession(session):
    now = int(time.time())
    session["saved"] = now
    session["exp"] = session.get("exp") or (now + 3600 * 24)
    with PersistentDict(constants.SESSION_KEY) as db:
        db[constants.SESSION_KEY] = session


def getSession():
    with PersistentDict(constants.SESSION_KEY) as db:
        return db.get(constants.SESSION_KEY)


def getAccessToken():
    session = getSession()
    if not session:
        return None
    if session.get("exp", 0) - int(time.time()) < 60:
        return None
    return session.get("accessToken")


def getUserEntitlements():
    """All package ids the subscription declares (from userDetails.entitlements)."""
    session = getSession()
    if not session:
        return []
    entitlements = session.get("entitlements") or []
    pkg_ids = []
    for e in entitlements:
        if isinstance(e, dict):
            val = e.get("pkgId")
        else:
            val = e
        if val:
            pkg_ids.append(str(val).strip())
    return pkg_ids


def getUserDetails():
    session = getSession()
    if not session:
        return None
    tok = session.get("accessToken")
    sid = session.get("sid") or (tok.get("sid") if isinstance(tok, dict) else None)
    sname = session.get("sName") or (tok.get("sName") if isinstance(tok, dict) else None)
    return {
        "sid": sid,
        "sName": sname,
        "rmn": session.get("rmn"),
        "profileId": session.get("profileId"),
        "entitlements": getUserEntitlements(),
    }


def logout():
    with PersistentDict(constants.SESSION_KEY) as db:
        if constants.SESSION_KEY in db:
            del db[constants.SESSION_KEY]
        db.flush()


def isLoggedIn():
    """Plain predicate - call inside routes (codequick inspects decorated signatures)."""
    return bool(getAccessToken())


# -------------------------------------------------------------------- login ---
def _web_headers():
    """Headers for the watch.tataplay.com web login endpoints (tm.tapi host)."""
    return {
        "Content-Type": "application/json",
        "User-Agent": constants.WEB_USER_AGENT,
        "device_details": constants.WEB_DEVICE_DETAILS,
        "origin": "https://watch.tataplay.com",
        "referer": "https://watch.tataplay.com/",
    }


def generateOTP(rmn, sid):
    try:
        resp = urlquick.post(constants.OTP_RMN_URL,
                             json={"sid": str(sid).strip(), "rmn": str(rmn).strip()},
                             headers=_web_headers(),
                             verify=False, max_age=-1, raise_for_status=False)
        data = resp.json()
        log("generateOTP: status=%s code=%s msg=%s" %
            (resp.status_code, data.get("code"), (data.get("message") or data.get("msg"))))
        return data
    except Exception:
        log_exc("generateOTP")
        return {}


def lookupSid(rmn):
    try:
        resp = urlquick.post(constants.SID_LOOKUP_URL,
                             json={"rmn": str(rmn).strip()},
                             verify=False, max_age=-1, raise_for_status=False)
        data = resp.json()
        log("lookupSid: status=%s code=%s msg=%s" %
            (resp.status_code, data.get("code"), (data.get("message") or data.get("msg"))))
        sidList = (data.get("data") or {}).get("sidList") or []
        if isinstance(sidList, list) and sidList:
            sid = sidList[0].get("sid") if isinstance(sidList[0], dict) else sidList[0]
            return str(sid)
        return None
    except Exception:
        log_exc("lookupSid")
        return None


def login_otp(rmn, sid, otp):
    payload = {
        "authorization": otp,
        "rmn": rmn,
        "sid": sid,
        "loginOption": "OTP",
    }
    try:
        resp = urlquick.post(constants.LOGIN_URL, json=payload,
                             headers=_web_headers(),
                             verify=False, max_age=-1, raise_for_status=False)
        data = resp.json()
    except Exception:
        log_exc("login_otp request")
        return "network/parse error (see log)"
    log("login_otp: status=%s code=%s msg=%s" %
        (resp.status_code, data.get("code"), (data.get("message") or data.get("msg"))))
    if data.get("code") == 0:
        d = data.get("data") or {}
        token = d.get("accessToken")
        if token:
            ud = d.get("userDetails") or {}
            up = d.get("userProfile") or {}
            entitlements = ud.get("entitlements") or []
            log("login_otp: OK token(len=%s) sid=%s prof=%s entitlements=%s" %
                (len(token), ud.get("sid"), up.get("id"), len(entitlements)))
            saveSession({
                "accessToken": token,
                "entitlements": entitlements,
                "sid": ud.get("sid"),
                "sName": ud.get("sName"),
                "acStatus": ud.get("acStatus"),
                "profileId": up.get("id"),
                "rmn": rmn,
            })
            return None
        log("login_otp: code=0 but missing accessToken: %s" % _safe(d), lvl=Script.ERROR)
    if data.get("message"):
        return data.get("message")
    return json.dumps(data.get("msg") or data.get("code"), ensure_ascii=False)


# ------------------------------------------------------------ channel list ---
def _rawChannels():
    """Paginate the public channel catalogue. Response: data.list."""
    channels, offset, total = [], 0, 0
    while True:
        try:
            resp = urlquick.get(constants.CHANNELS_URL,
                                params={"limit": constants.CHANNEL_PAGE_SIZE, "offset": offset},
                                headers=get_headers(),
                                verify=False, max_age=-1, raise_for_status=False)
            data = resp.json().get("data") or {}
            items = data.get("list") or data.get("channels") or []
            total = int(data.get("total") or 0)
            if not items:
                break
            channels.extend(items)
            offset = int(data.get("offset") or (offset + len(items)))
        except Exception as e:
            log("channel list fetch failed at offset %s: %s" % (offset, e), lvl=Script.ERROR)
            break
        if total and offset >= total:
            break
    log("channels: fetched %s (total reported %s)" % (len(channels), total))
    return channels


def getChannelList(refresh=False):
    with PersistentDict(constants.CHANNELS_KEY) as db:
        cached = db.get(constants.CHANNELS_KEY)
        if cached and not refresh and time.time() - cached.get("saved", 0) < 3600 * 24:
            return cached.get("channels", [])

    channels = _rawChannels()
    with PersistentDict(constants.CHANNELS_KEY) as db:
        db[constants.CHANNELS_KEY] = {"saved": int(time.time()), "channels": channels}
    return channels


def _channelTitle(ch):
    return ch.get("title") or ch.get("channel_name") or ""


def _channelLogo(ch):
    return ch.get("image") or ch.get("channel_logo") or ""


def _channelEntitlements(ch):
    ents = ch.get("entitlements") or ch.get("channel_entitlements") or []
    offer = ch.get("offerId") or {}
    for e in (offer.get("epids") or []):
        bid = e.get("bid")
        if bid:
            ents.append(bid)
    return [str(e).strip() for e in ents if str(e).strip()]


def _channelGenre(ch):
    return ch.get("genre") or ch.get("channel_genre") or ""


def getUserChannels():
    """Channels the current subscription actually entitles."""
    sub = set(getUserEntitlements())
    result = []
    for ch in getChannelList():
        if sub and not (sub & set(_channelEntitlements(ch))):
            continue
        result.append(ch)
    return result


def getChannelsById():
    lookup = {}
    for ch in getChannelList():
        cid = ch.get("id") or ch.get("channel_id") or ch.get("dvbTriplet")
        if cid is not None:
            lookup[str(cid)] = ch
    return lookup


def getChannelById(cid):
    return getChannelsById().get(str(cid))


# ------------------------------------------------------------------ license ---
def fetchChannelDetail(cid):
    try:
        resp = urlquick.get(constants.CHANNEL_DETAIL_URL.format(cid=cid),
                            headers=get_headers(),
                            verify=False, max_age=-1, raise_for_status=False)
        data = resp.json()
        if data.get("code") == 0:
            d = data.get("data") or {}
            log("channel detail cid=%s: mpd=%s lic=%s" %
                (cid, bool(d.get("dashWidewinePlayUrl")), bool(d.get("dashWidewineLicenseUrl"))))
            return d
        log("channel detail cid=%s code=%s %s" % (cid, data.get("code"), _safe(data)), lvl=Script.ERROR)
    except Exception as e:
        log("channel detail fetch failed cid=%s: %s" % (cid, e), lvl=Script.ERROR)
    return {}


def getEpids(channel):
    """Build the epid list used for the stream JWT."""
    offered = set()
    if channel.get("offerId"):
        for e in (channel["offerId"].get("epids") or []):
            if e.get("epid") and e.get("bid"):
                offered.add((str(e["epid"]), str(e["bid"])))
    if offered:
        return [{"epid": e, "bid": b} for e, b in sorted(offered)]

    # fallback: intersect with the subscription package ids
    sub = set(getUserEntitlements())
    bids = set(_channelEntitlements(channel)) & sub
    return [{"epid": "Subscription", "bid": b} for b in sorted(bids)]


def getStreamToken(channel):
    """Fetch a per-channel Widevine ls_session JWT (expires ~1 day)."""
    epids = getEpids(channel)
    if not epids:
        return None
    session = getSession()
    if not session:
        return None
    headers = get_headers(auth=True)
    headers["authorization"] = "bearer " + session.get("accessToken", "")
    if session.get("sid"):
        headers["x-subscriber-id"] = str(session["sid"])
    if session.get("sName"):
        headers["x-subscriber-name"] = str(session["sName"])
    if session.get("profileId"):
        headers["profileid"] = str(session["profileId"])

    payload = {"action": "stream", "epids": epids}
    try:
        resp = requests.post(constants.TOKEN_URL, json=payload,
                             headers=headers,
                             verify=False, timeout=30)
        data = resp.json()
    except Exception as e:
        log("token-service request failed: %s" % e, lvl=Script.ERROR)
        return None
    if data.get("code") == 0:
        tok = (data.get("data") or {}).get("token")
        log("token-service: OK token len=%s" % (len(tok) if tok else 0))
        return tok
    log("token-service error: %s %s" % (resp.status_code, _safe(data)), lvl=Script.ERROR)
    return None


def resolvePlayback(channel_id, channel=None):
    """Returns (mpd_url, license_url). Fetches live manifest + license URLs."""
    if channel is None:
        channel = getChannelById(channel_id) or {}
    detail = fetchChannelDetail(channel_id) or {}
    d = detail.get("detail") or detail or {}

    mpd = d.get("dashWidewinePlayUrl") or detail.get("dashWidewinePlayUrl") or channel.get("channel_url")
    lic = d.get("dashWidewineLicenseUrl") or detail.get("dashWidewineLicenseUrl") or channel.get("channel_license_url")
    if not mpd:
        return None, None

    sch = channel or {}
    offer = sch.get("offerId") or d.get("offerId") or detail.get("offerId")
    if offer and not sch.get("offerId"):
        sch = dict(sch, offerId=offer)

    jwt = getStreamToken(sch)
    if not jwt:
        log("resolvePlayback cid=%s: no stream JWT "
            "(epids=%s, mpd=%s)" % (channel_id, bool(getEpids(sch)), bool(mpd)), lvl=Script.ERROR)
        return None, None

    manifest = mpd
    if "?" not in manifest:
        manifest += "?"
    else:
        manifest += "&"
    manifest += "ls_session=" + jwt

    license_url = lic + "&ls_session=" + jwt if lic else None
    log("resolvePlayback cid=%s: manifest=%s license=%s" % (channel_id, bool(manifest), bool(license_url)))
    return manifest, license_url


# --------------------------------------------------------------------- m3u ----
def exportM3U():
    if not getAccessToken():
        return False
    lines = ['#EXTM3U', '#EXT-X-VERSION:3', '']
    ref_raw = quote(constants.REFERER, safe='')
    ua_raw = quote(constants.USER_AGENT, safe='')
    for ch in getUserChannels():
        cid = ch.get("id") or ch.get("channel_id") or ch.get("dvbTriplet")
        title = _channelTitle(ch)
        logo = _channelLogo(ch)
        genre = _channelGenre(ch) or "Others"
        mpd, lic = resolvePlayback(cid, ch)
        if not mpd or not lic:
            continue
        lines.append('#KODIPROP:inputstream=inputstream.adaptive')
        lines.append('#KODIPROP:inputstream.adaptive.manifest_type=mpd')
        lines.append('#KODIPROP:inputstream.adaptive.license_type=com.widevine.alpha')
        lines.append('#KODIPROP:inputstream.adaptive.stream_headers=referer={0}&user-agent={1}'.format(ref_raw, ua_raw))
        lines.append('#KODIPROP:inputstream.adaptive.license_key={0}|Content-Type=application%2Foctet-stream&referer={1}&user-agent={2}|R{{SSM}}|'.format(lic, ref_raw, ua_raw))
        lines.append(constants.M3U_CHANNEL.format(title, cid, logo, genre, mpd))
    try:
        write_m3u('\n'.join(lines))
    except Exception as e:
        Script.log("M3U write failed: %s" % e, lvl=Script.ERROR)
        return False
    Script.notify(constants.ADDON_ID, Script.localize(32013))
    return True


def write_m3u(contents):
    from xbmcvfs import File
    path = Script.get_info('profile') + 'playlist.m3u'
    with File(path, 'w') as f:
        f.write(contents)
        f.write('\n')
    return path