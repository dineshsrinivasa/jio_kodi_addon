# Session Notes - JioTV Kodi Addon

## Repo context
- This addon `plugin.video.jiotv` is maintained by `dineshsrinivasa` (origin + upstream = github.com/dineshsrinivasa/jio_kodi_addon).
- It is a fork of Kiran Reddy's original addon: https://github.com/kiranreddyrebel/plugin.video.jiotv (credited in README.md line 55).
- The repo was recently restructured to match "Kiran's working Kodi repository format" (dir wrapper, root URLs, Zips datadir). See git log eaefc45 / 3e956fb.
- Yes, we are aware of Kiran Reddy's repo. It is the upstream source. EPG fallback URL still points to `https://kiranreddyrebel.github.io/epg.xml.gz` (main.py:886) and EPG_SRC default is `testingweb624/jioEpg` (constants.py:36).

## Architecture / key files
- `addon.py` -> `resources/lib/main.py` (entry).
- `resources/lib/main.py`: routing + the `play` resolver (core playback logic).
- `resources/lib/utils.py`: login, headers, caching, Monitor, helpers.
- `resources/lib/proxy.py`: local HTTP server for web login.
- `resources/lib/constants.py`: URLs, image config, M3U template.
- `resources/settings.xml`: settings incl. quality, usempd, enablehost, epgsource.

## Playback flow (main.py `play`)
1. `@Resolver.register @isLoggedIn play(...)`.
2. For Zee channels (hardcoded id map 5000-5026): build ~m3u8 URL from `zee_channels` dict + zee cookie; use `getZeeHeaders(host)`.
3. For Sony channels (154/471 etc.) and all others: POST to
   `https://jiotvapi.media.jio.com/playback/apis/v1/geturl?langId=6`
   with `data="stream_type=Seek&channel_id=X"`, headers from `getSonyHeaders()`.
   Response contains `result` (m3u8 URL) with a `__hdnea__` Akamai stream token.
4. If not MPD: fetch the variant m3u8, optionally pick a quality band with `quality_to_enum`, and, if catchup, patch the URL from the variant playlist.
5. For a hardcoded Sony/Zee subset (ids in lines 670-695) it does `xbmc.Player().play(...)`.
6. Otherwise it returns a codequick Listitem (which codequick sets up for inputstream.adaptive).

## Known bug being worked on (IMPORTANT)
**Symptom:** When a JioTV channel buffers, playback gets stuck forever and never recovers/plays.
Switching to another channel also buffers/sticks — even that channel won't recover after buffering.
(Reported by user, 2026-09-03.)

### Root cause #1: NO recovery/watchdog (confirmed)
There is no recovery/watchdog mechanism anywhere. The stream is resolved once and handed to
inputstream.adaptive; if it stalls (expired `__hdnea__` token, CDN hiccup, stuck manifest) the
player buffers forever and nothing restarts it.

### Root cause #2: Upstream regression in Kiran's repo (confirmed via git logs)
Added kiran remote: `git remote add kiran https://github.com/kiranreddyrebel/plugin.video.jiotv.git`
Fetched. Kiran's `main` = commit `67a35ab` (identical hashes to our early history — our repo
dineshsrinivasa/jio_kodi_addon is a fork of kiranreddyrebel).
- Kiran's commit `23322b0` (Oct 1 2025, "Update main.py") changed the **normal (non-special)
  channel** resolution in `play` from:
    `urlquick.post(GET_CHANNEL_URL, json=rjson, headers=getChannelHeadersWithHost()/getChannelHeaders())`
  to the Sony-style form-encoded call:
    `urlquick.post(..., data="stream_type=Seek&channel_id="+chan, headers=sony_headers)`
  This is the likely regression that destabilized buffering on normal channels.
- Local commit `13f67fa` (Dinesh, "stability improvements") is benign (removed prints, added guards).
- The `resp`/`cookie`/`onlyUrl` logic in the current `main.py` is also convoluted with
  `ZEE_RANGE`/`ZEE_MAP` gating that has dead/broken paths.

### FIX IMPLEMENTED (v2.3.18, committed this session)
- New file `resources/lib/reconnect.py`: `PlayerWatcher(xbmc.Player)` + `watchdog(...)` daemon
  thread that polls playback progress, detects stalls (time frozen while playing, or never starts
  progressing), and restarts playback on the SAME channel with a FRESH stream (new `__hdnea__`
  token) via a `refresh()` callback. Honors max attempts; pauses don't trigger it; self-stops when
  playback ends or Kodi shuts down.
- `main.py`: refactored `play` -> `_resolve_stream(...)` (returns normalized info dict) +
  `_start_watchdog(...)`. RESTORED the working JSON resolver (`GET_CHANNEL_URL`, `json=rjson`,
  `getChannelHeadersWithHost()/getChannelHeaders()`) for NORMAL channels (ignoring Zee/Sony as user
  requested). Zee/Sony special handling preserved as-is (not the focus).
- New settings: `reconnect` (bool, default true), `reconnect_attempts` (int 1-10, default 3),
  `reconnect_stall` (int 3-30s, default 8). Strings #33050/#33051/#33052.
- Added `WATCHDOG` debug logging (Script.log DEBUG) throughout -- enables diagnosing playback via
  Kodi debug log.
- Version bumped 2.3.17 -> 2.3.18. Rebuilt `Zips/plugin.video.jiotv-2.3.18.zip`, regenerated root
  & repository.dineshrepo `addons.xml` + md5 (both = 436a9e03f9f4d26aabfcf6e19047060a).

## How to collect debug logs from users (to review)
1. In Kodi: Settings > System > Logging > enable "Enable debug logging".
2. Reproduce the buffer-stall on a normal channel, wait ~10s, then switch channels.
3. Grab the `kodi.log` (Kodi Settings > System > Logging > "Show log folder" / or
   `%APPDATA%\Kodi\kodi.log` on Windows).
4. Search the log for `WATCHDOG:` entries — they show stall detection + reconnect attempts
   (channel id, cur/last time, attempt N/M, success/failure).

## Installation / update troubleshooting (IMPORTANT - session continuation)
- The GitHub Pages repo is LIVE and correct as of the 2.3.18 push:
  - `https://dineshsrinivasa.github.io/jio_kodi_addon/addons.xml` -> contains version 2.3.18.
  - Served `addons.xml.md5` = `14d2ad21ddaf6d4127724e1a809ef55a` (matches local copy => not stale CDN).
  - `https://dineshsrinivasa.github.io/jio_kodi_addon/Zips/plugin.video.jiotv/plugin.video.jiotv-2.3.18.zip` -> HTTP 200.
  => Server side is fine; any "still 2.3.17" is Kodi's LOCAL cache, NOT the repo.
- HOWEVER the user reported: installing `plugin.video.jiotv-2.3.18.zip` manually fails with
  "invalid structure". ROOT CAUSE FOUND (this session):
  - The zip built earlier via PowerShell/`Compress-Archive` produced zip entries with **backslash
    path separators** (`plugin.video.jiotv\addon.py`). Kodi (non-Windows unzip logic) expects
    **forward slashes** (`plugin.video.jiotv/addon.py`) and rejects backslash entries as
    "invalid structure".
  - FIX: rebuilt the zip with .NET `System.IO.Compression.ZipArchive`, writing each entry with an
    explicit forward-slash name under the top folder `plugin.video.jiotv/`. Rebuilt
    `Zips/plugin.video.jiotv/plugin.video.jiotv-2.3.18.zip` has 17 entries, all forward-slash,
    embedded addon.xml is version 2.3.18. COMMITTED + PUSHED (re-push 2.3.18 zip).
  - LESSON: NEVER build Kodi addon zips with PowerShell `Compress-Archive` (backslashes).
    Always build with .NET ZipArchive + forward-slash entry names.
- User's install method = UNKNOWN (asked; not yet answered as of this writing). If they installed
  manually via zip originally, the repository auto-update will NEVER touch it -> they MUST reinstall
  manually with the corrected zip. Reconfirm with the user which method they used.
- Next step for user: retry "Install from zip file" with the corrected zip (download from the URL
  above), OR if repo-installed, do Add-ons > Check for updates / disable+enable the Dinesh repo /
  delete `%APPDATA%\Kodi\userdata\Database\addons33.db` (Kodi closed) to clear the cached addons.xml.
- To actually validate the watchdog fix end-to-end: enable Kodi debug logging, reproduce a
  buffer-stall on a normal channel, grab `kodi.log`, and check `WATCHDOG:` lines.

## Future / known remaining issues
- The convoluted `_resolve_stream` still mirrors upstream Zee/Sony quirks; a full cleanup of the
  `ZEE_RANGE`/`ZEE_MAP`/`DIRECT_IDS` gating is desirable later. Zee/Sony were intentionally left
  unchanged per user request.
- Watchdog cannot be unit-tested here (no Python/Kodi runtime in this environment); must be
  validated on a real Kodi device.

## Notes / gotchas
- Code uses codequick framework (Route/Resolver/Listitem/Script).
- Several hardcoded channel-id lists (Zee 5000-5026, Sony, etc.) are duplicated across
  if/elif checks in `play` and repeated literal tuples in m3ugen — beware inconsistencies.
- `getSonyHeaders()` builds a broad header dict incl. `Channel_id: 471`.
- Don't commit secrets/tokens (some Zee tokens are hardcoded in utils.zeeCookie).
