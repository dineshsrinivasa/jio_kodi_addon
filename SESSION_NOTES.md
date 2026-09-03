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

### Root cause #2: WRONG resolver format for NORMAL channels -> 400 (corrected 2026 session)
IMPORTANT CORRECTION: an earlier note claimed the JSON resolver
`urlquick.post(GET_CHANNEL_URL, json=rjson, headers=getChannelHeaders()/getChannelHeadersWithHost())`
was "the working resolver" to RESTORE. That was WRONG. User's kodi.log (v2.3.19) showed EVERY normal
channel (619, 626, 370, 3240) failing with:
`WATCHDOG: _resolve_stream FAILED for channel X: 400 Client Error for url: .../geturl`
Jio's geturl API now REJECTS the `json=rjson` payload. The WORKING current format (confirmed by
reading Kiran's CURRENT main.py on branch kiran/main) for NORMAL channels is the SAME form-encoded
Sony-style call used for the special channels:
    urlquick.post("https://jiotvapi.media.jio.com/playback/apis/v1/geturl?langId=6",
                  data="stream_type=Seek&channel_id="+chan, verify=False,
                  headers=getSonyHeaders(), max_age=-1)
So the form-encoded + sony_headers approach is what makes channels PLAY (they previously played but
buffered). My "restore json" change broke playback entirely (400). FIXED in v2.3.20.
- The user's ORIGINAL bug (buffering forever) is exactly what the watchdog solves: the form-encoded
  working resolver returns a stream with an expiring __hdnea__ token; when it stalls, the watchdog
  re-resolves a FRESH token.

### FIX IMPLEMENTED (v2.3.18 / watchdog, committed this session)
- New file `resources/lib/reconnect.py`: `PlayerWatcher(xbmc.Player)` + `watchdog(...)` daemon
  thread that polls playback progress, detects stalls (time frozen while playing, or never starts
  progressing), and restarts playback on the SAME channel with a FRESH stream (new `__hdnea__`
  token) via a `refresh()` callback. Honors max attempts; pauses don't trigger it; self-stops when
  playback ends or Kodi shuts down.
- `main.py`: refactored `play` -> `_resolve_stream(...)` (returns normalized info dict) +
  `_start_watchdog(...)`. Zee/Sony special handling preserved as-is (user ignored Zee/Sony).
- New settings: `reconnect` (bool, default true), `reconnect_attempts` (int 1-10, default 3),
  `reconnect_stall` (int 3-30s, default 8). Strings #33050/#33051/#33052.
- Added `WATCHDOG` debug logging (Script.log DEBUG) throughout -- enables diagnosing playback via
  Kodi debug log.

### v2.3.20 - FIXED normal channels (400) by matching working geturl request
- 2.3.18 had the watchdog; 2.3.19 fixed the settings-crash; but 2.3.19 broke PLAYBACK: my
  `_resolve_stream` used `json=rjson` + `getChannelHeaders()` for NORMAL channels -> Jio returned
  400. User log confirmed.
- v2.3.20 changed the normal-channel branch to the CURRENTLY-WORKING form-encoded request:
  `GET_CHANNEL_URL + "?langId=6"` with `data="stream_type=Seek&channel_id="+chan` and
  `headers=sony_headers` (getSonyHeaders()). Exactly Kiran's current main.py.
- Version 2.3.20 rebuilt: `Zips/plugin.video.jiotv-2.3.20.zip` (17 files, forward-slash entries),
  root & repository.dineshrepo `addons.xml` + md5 (`fd9a80fa991c350ef16490e8e186f09f`), added
  news/changelog.

### v2.3.20 CONFIRMED WORKING on device (2026-09-03)
- User confirmed on 2.3.20: "channel works fine with 2.3.20 but main issue not fixed yet, it stuck
  again in buffer after some time". => The 400 is FIXED; playback now starts but after some time
  sticks in buffering (the ORIGINAL stall bug the watchdog is meant to recover). We need a 2.3.20+
  kodi.log captured DURING a stall to see whether the watchdog fires and why reconnect may fail.

## v2.3.21 - diagnostics tooling (this session)
- Confirmed 2.3.20 works on device; remaining = mid-playback stall. To diagnose, added:
  1. **`Upload log for remote debugging`** settings button (route `resources/lib/main/uploadlog`):
     reads `kodi.log` at `special://logpath/kodi.log`, POSTs raw body to `https://paste.rs`
     (returns the paste URL in the response body), shows it in a textviewer and copies it to
     clipboard. String #33054. `paste.rs` verified reachable: POST -> 201 + `https://paste.rs/...`.
  2. **`Low quality test`** setting (`lowq`, string #33053): when ON, `_resolve_stream` forces
     `qltyopt="Lowest"` (quality_to_enum -> index 0) and logs
     `WATCHDOG: LOW-Q TEST active, forcing lowest bitrate` at INFO. Helps isolate whether the stall
     is bandwidth-related vs token-expiry (expect: it's token expiry, low quality won't fix it).
- Bumped watchdog start + "monitoring playback" log lines from DEBUG -> INFO so they appear in a
  NORMAL (non-debug) kodi.log. The STALL/reconnect events were already WARNING/ERROR.
- Version 2.3.21 rebuilt: `Zips/plugin.video.jiotv-2.3.21.zip` (17 forward-slash entries), root &
  repository.dineshrepo `addons.xml` + md5 (`49ee3582a3107651791d58eeaf82ea65`), added
  news/changelog, removed 2.3.20 zip.
- LESSON: `System.IO.Compression.ZipArchive` requires `Add-Type -AssemblyName
  System.IO.Compression.FileSystem` to be loaded in each fresh PowerShell process (Rediscovered:
  type is not available across separate bash invocations).

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

## v2.3.19 - Settings-page crash on Android (fixed this session)
- After 2.3.18 was installed on the user's ANDROID TAB, opening the addon's Settings page (via
  Add-ons > JioTV > Configure) hard-crashed Kodi (force close), twice.
- ROOT CAUSE: my two new number settings (`reconnect_attempts`, `reconnect_stall`) used:
      <setting id="..." type="number"> + <control type="spinner" format="integer">
          <minimum>/<step>/<maximum> INSIDE the <control> tag.
  On Kodi Nexus 20 / Omega 21 this deprecated control nesting hard-crashes the settings renderer.
- FIX: converted both to the standard Kodi structure:
      <setting id="..." type="integer"> + <constraints><minimum>/<step>/<maximum></constraints>
      + minimal <control type="spinner" format="integer" />
  Verified settings.xml parses. Type was changed from "number" to "integer" (correct Kodi type).
- Version bumped 2.3.18 -> 2.3.19 (crash fix = new version so repo distributes corrected file).
  Rebuilt Zips/plugin.video.jiotv-2.3.19.zip (forward-slash entries, 17 files), updated both
  addons.xml (version+news) + md5 (now f9345a3b8bd29f0304c94df4d2de3a83), removed 2.3.18 zip.
- LESSON: when adding number/integer settings to settings.xml for a Kodi addon, ALWAYS put
  minimum/step/maximum in <constraints> and keep <control> minimal. Avoid <type="number"> (use
  "integer" for spinners).

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

## v2.3.22 - Watchdog startup crash (root cause of non-recovery) + reconnect on stream death
- On-device log `https://paste.rs/hKE1L` (CloudWalker CloudTV518, Kodi 21.3 32-bit) revealed the
  real reason the watchdog NEVER ran: it crashed immediately at thread start:
      AttributeError: module 'xbmc' has no attribute 'abortRequested'
  at reconnect.py:117 in the loop `while not watch.isPlaying() ... and not xbmc.abortRequested()`.
- `xbmc.abortRequested` is a BOOLEAN PROPERTY, not a method. Correct: `xbmc.Monitor().abortRequested()`
  (the idiom already used in service.py:36). Fixed all 4 usages (reconnect.py) by adding
  `mon = xbmc.Monitor()` and calling `mon.abortRequested()`.
- Stall sequence (channel 626 Suvarna News): plays ~2min, then HTTP 403 on CDN segment + master
  re-request (expired `__hdnea__` token), retries ~9s, then `eof reading from demuxer` -> playback
  actually ENDS (`onPlayBackEnded`), not hangs.
- Because the stream DIES (Ended/Error) rather than only freezing, the frozen-time stall detector
  alone would not reconnect. v2.3.22 also reconnects on `onPlayBackEnded`/`onPlayBackError`
  (`_handle_failure` sets `want_retry=True`) while still NOT reconnecting on `onPlayBackStopped`
  (manual/TV channel switch). Refactored the reconnect into shared `_retry(...)` honoring
  `max_attempts` (both stall and failure paths).
- Default `stall_window=8` can race the ~9s EOF; kept for now, may lower to 5s if needed on-device.
- Version bumped to 2.3.22; rebuilt zip (17 forward-slash entries, 39433 bytes), updated both
  addons.xml (version+news, LF-only news block) + md5 (now c7ee1e0e676bc63e0d01a5b18492018b),
  removed 2.3.21 zip. Commit c5847d1, pushed to origin/main. Live verified: zip HTTP 200 len=39433,
  addons.xml lists 2.3.22, md5 matches.
- PENDING on-device validation: does the watchdog (1) not crash now, and (2) successfully
  auto-reconnect via `watch.play()` under a PVR IPTV Simple session when the 403/EOF occurs.

## v2.3.23 - On-device result: watchdog was NOT running (still no recovery) - setting was OFF
- Post-2.3.22 on-device log `https://paste.rs/Wf1t5` (incar KT1001, Kodi 21.2, 64-bit): device booted
  2.3.20, repo auto-updated to 2.3.22 at 11:46:04, user used the new Upload-Log button (proves
  process is >=2.3.21), DID the 403->EOF stall AGAIN (channel DD_India, 403 from 11:49:56, EOF+OnExit
  11:50:08, ~12s) and playback ENDED with NO recovery.
- CRITICAL: there are ZERO `WATCHDOG:` lines in the whole log - not even the INFO "watchdog thread
  started" / "monitoring playback" lines. That means the watchdog never started. Since `play` calls
  `_start_watchdog` (main.py:692) unconditionally after successful `_resolve_stream`, the only code
  path that produces NO INFO log is `Settings.get_boolean("reconnect")` returning False
  (main.py:636) -> returns early with a DEBUG-only message invisible at INFO log level.
- So the "Auto-recover stalled streams" toggle was OFF on this device (the thing we had been
  treating as automatically-on). User then ENABLED it and will restart Kodi + retest.
- NOTE: no AttributeError in this log (crash fix held up); the remaining blocker was simply that the
  feature was disabled. Also, Kodi does NOT hot-reload addon modules on repo auto-update - an
  already-running plugin process keeps its loaded code until Kodi restarts, so always restart Kodi
  after an auto-update before testing.
- v2.3.23 (shipped to make status unambiguous): changed the "auto-recover disabled" message in
  `_start_watchdog` (main.py) and reconnect.py's `enable=False` path from DEBUG to WARNING, so a
  normal kodi.log will ALWAYS show whether the watchdog was skipped. Rebuilt zip
  (17 entries, 39543 bytes), addons.xml+md5 = a7d9da8c5d35cd4a1627ab5862e07b18, commit eea576c
  pushed to origin/main.
- PENDING: user toggled setting ON + restart Kodi + reproduce stall + fresh Upload-Log capture. We
  expect to now see `WATCHDOG: watchdog thread started for channel X` then, on the 403->EOF,
  `WATCHDOG: onPlayBackEnded/Error (stream failure) -> scheduling retry` and reconnect attempts.
