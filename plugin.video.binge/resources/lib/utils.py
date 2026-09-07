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
# Binge-mobile (www.tataplaybinge.com) OTP login for NON-DTH (RMN-only) accounts.
# Source of truth: reverse-engineered from the official www.tataplaybinge.com web app
# (see drmlive/tataplay send_otp.php / verify_otp.php).


def _bm_headers(extra=None, content_type=None):
    """Base headers for binge-mobile-services requests."""
    headers = {
        "accept": "application/json, text/plain, */*",
        "origin": constants.BINGE_ORIGIN,
        "referer": constants.BINGE_ORIGIN + "/",
        "user-agent": constants.BINGE_MOBILE_UA,
    }
    if content_type:
        headers["Content-Type"] = content_type
    if extra:
        headers.update(extra)
    return headers


def _device_cred():
    """Return (deviceId, anonymousId), registering a guest device on first use."""
    with PersistentDict(constants.SESSION_KEY) as db:
        cred = db.get("bm_device")
        if cred and cred.get("deviceId") and cred.get("anonymousId"):
            return cred["deviceId"], cred["anonymousId"]

    import random
    device_id = "%03d%d%d" % (random.randint(100, 999), int(time.time()), random.randint(10, 99))
    try:
        resp = urlquick.post(constants.BINGE_REGISTER_URL,
                             data="",
                             headers=_bm_headers({"deviceid": device_id, "authorization": "bearer undefined"}),
                             verify=False, max_age=-1, raise_for_status=False)
        data = resp.json()
    except Exception:
        log_exc("guest register request")
        return device_id, None
    anon = (data.get("data") or {}).get("anonymousId")
    log("guest register: status=%s anonymousId=%s" % (getattr(resp, "status_code", "?"), bool(anon)))
    if anon:
        with PersistentDict(constants.SESSION_KEY) as db:
            db["bm_device"] = {"deviceId": device_id, "anonymousId": anon}
    return device_id, anon


def generateOTP(rmn, sid=None):
    """Send OTP for a NON-DTH (RMN-only) account via the Binge-mobile flow.
    sid is ignored/accepted for API compatibility with the older DTH flow."""
    device_id, anon = _device_cred()
    if not anon:
        return {"code": -1, "message": "Device registration failed (see log)."}
    try:
        resp = urlquick.post(constants.BINGE_OTP_URL,
                             data="",
                             headers=_bm_headers({
                                 "anonymousid": anon,
                                 "deviceid": device_id,
                                 "mobilenumber": str(rmn).strip(),
                                 "newotpflow": "4DOTP",
                                 "platform": "BINGE_ANYWHERE",
                             }),
                             verify=False, max_age=-1, raise_for_status=False)
        data = resp.json()
    except Exception:
        log_exc("generateOTP request")
        return {"code": -1, "message": "network/parse error (see log)"}
    log("generateOTP: status=%s body=%s" % (getattr(resp, "status_code", "?"), _safe(data)))
    return data


def lookupSid(rmn):
    """Binge-mobile has no 10-digit DTH SID for RMN-only accounts; always returns None
    so the caller proceeds with the non-DTH OTP flow."""
    return None


def login_otp(rmn, sid=None, otp=None):
    """Validate OTP and create/update the Binge subscriber, storing the session.

    Returns None on success, else an error string."""
    try:
        rmn = str(rmn).strip()
        otp = str(otp).strip()
    except Exception:
        return "invalid input"
    device_id, anon = _device_cred()
    if not anon:
        return "Device registration failed (see log)."

    # 1) validate OTP -> userAuthenticateToken + deviceAuthenticateToken
    try:
        resp = urlquick.post(constants.BINGE_VALIDATE_OTP_URL,
                             json={"mobileNumber": rmn, "otp": otp},
                             headers=_bm_headers({"anonymousid": anon, "deviceid": device_id, "platform": "BINGE_ANYWHERE"}, content_type="application/json"),
                             verify=False, max_age=-1, raise_for_status=False)
        data = resp.json()
    except Exception:
        log_exc("validateOTP request")
        return "network/parse error (see log)"
    log("validateOTP: status=%s body=%s" % (getattr(resp, "status_code", "?"), _safe(data)))
    tok = (data.get("data") or {}).get("userAuthenticateToken")
    devtok = (data.get("data") or {}).get("deviceAuthenticateToken") or ""
    first_login = (data.get("data") or {}).get("firstTimeLogin") is True
    if not tok:
        return (data.get("message") or "OTP validation failed") if data.get("message") else "OTP validation failed"
    log("validateOTP: OK userToken(len=%s) firstTimeLogin=%s" % (len(tok), first_login))

    # 2) fetch subscriber account details -> pick create vs update
    account = {}
    try:
        resp = urlquick.get(constants.BINGE_SUBSCRIBER_URL,
                            headers=_bm_headers({
                                "anonymousid": anon,
                                "authorization": "bearer " + tok,
                                "devicetype": "WEB",
                                "mobilenumber": rmn,
                            }),
                            verify=False, max_age=-1, raise_for_status=False)
        acc_data = resp.json()
    except Exception:
        log_exc("subscriber details request")
        acc_data = {}
    log("subscriber/details: status=%s body=%s" % (getattr(resp, "status_code", "?"), _safe(acc_data)))
    ads = ((acc_data.get("data") or {}).get("accountDetails") or [{}])
    account = ads[0] if isinstance(ads, list) and ads else {}
    dth_status = account.get("dthStatus") or ""
    log("subscriber/details: dthStatus=%r subscriberId=%r bingeSubscriberId=%r firstTimeLogin=%s" %
        (dth_status, account.get("subscriberId"), account.get("bingeSubscriberId"), first_login))

    # 3) create (new user) or update (existing) via the login endpoint
    if first_login:
        login_url = constants.BINGE_CREATE_USER_URL
        if dth_status == "DTH Without Binge":
            login_body = {
                "dthStatus": "DTH Without Binge",
                "subscriberId": account.get("subscriberId") or rmn,
                "login": "OTP",
                "mobileNumber": rmn,
                "baId": None,
                "isPastBingeUser": False,
                "eulaChecked": True,
                "packageId": "",
                "referenceId": None,
            }
        else:
            login_body = {
                "dthStatus": "Non DTH User",
                "subscriberId": rmn,
                "login": "OTP",
                "mobileNumber": rmn,
                "isPastBingeUser": False,
                "eulaChecked": True,
                "packageId": "",
            }
    else:
        login_url = constants.BINGE_UPDATE_USER_URL
        login_body = {
            "dthStatus": dth_status or "Non DTH User",
            "subscriberId": account.get("subscriberId") or rmn,
            "bingeSubscriberId": account.get("bingeSubscriberId") or "",
            "baId": account.get("baId") or "",
            "login": "OTP",
            "mobileNumber": rmn,
            "payment_return_url": "https://www.tataplaybinge.com/subscription-transaction/status",
            "eulaChecked": True,
            "packageId": "",
        }

    try:
        resp = urlquick.post(login_url,
                             json=login_body,
                             headers=_bm_headers({
                                 "anonymousid": anon,
                                 "authorization": "bearer " + tok,
                                 "device": "WEB",
                                 "deviceid": device_id,
                                 "devicename": "Web",
                                 "devicetoken": devtok,
                                 "platform": "WEB",
                             }, content_type="application/json"),
                             verify=False, max_age=-1, raise_for_status=False)
        ldata = resp.json()
    except Exception:
        log_exc("login create/update request")
        return "network/parse error (see log)"
    log("login create/update: status=%s body=%s" % (getattr(resp, "status_code", "?"), _safe(ldata)))

    session = _bm_session_from(ldata, rmn)
    if session and session.get("accessToken"):
        saveSession(session)
        return None
    msg = ldata.get("message") or (acc_data.get("message") if acc_data else None) or "Login failed"
    return msg


def _deep(data, *keys):
    """Walk data (dicts/lists) collecting the first non-empty value for any of keys."""
    if isinstance(data, dict):
        for k, v in data.items():
            if k.lower() in keys and v not in (None, "", []):
                return v
        for v in data.values():
            found = _deep(v, *keys)
            if found not in (None, "", []):
                return found
    elif isinstance(data, list):
        for v in data:
            found = _deep(v, *keys)
            if found not in (None, "", []):
                return found
    return None


def _bm_session_from(data, rmn):
    """Extract a usable session dict from the create/update login response."""
    token = _deep(data, "accessToken", "access_token", "token", "ssoToken", "authToken")
    if not token:
        return None
    entitlements = _deep(data, "entitlements", "packages", "pkgIds") or []
    if isinstance(entitlements, dict):
        entitlements = [v for v in entitlements.values()]
    if not isinstance(entitlements, list):
        entitlements = [entitlements]
    profile = _deep(data, "profileId")
    return {
        "accessToken": token,
        "entitlements": entitlements,
        "sid": _deep(data, "sid", "subscriberId"),
        "sName": _deep(data, "sName", "subscriberName", "subscriberName_inner"),
        "acStatus": _deep(data, "acStatus"),
        "profileId": profile,
        "rmn": rmn,
        "anonymousId": _deep(data, "anonymousId"),
    }


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