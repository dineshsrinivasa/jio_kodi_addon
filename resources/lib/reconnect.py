# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import time
from urllib.parse import urlencode

import xbmc
import xbmcgui
from codequick import Script


class PlayerWatcher(xbmc.Player):
    """Watches the current playback session and signals when it ends/stalls."""

    def __init__(self):
        xbmc.Player.__init__(self)
        self.stopped = False
        self.want_retry = False
        self.on_stop = None
        self._restarting = False

    def _handle_stop(self, event):
        if self._restarting:
            Script.log(
                "WATCHDOG: %s ignored (self-restart in progress)" % event,
                lvl=Script.DEBUG,
            )
            return
        Script.log("WATCHDOG: %s" % event, lvl=Script.INFO)
        self.stopped = True
        if self.on_stop:
            try:
                self.on_stop()
            except Exception:
                pass

    def _handle_failure(self, event):
        if self._restarting:
            Script.log(
                "WATCHDOG: %s ignored (self-restart in progress)" % event,
                lvl=Script.DEBUG,
            )
            return
        Script.log("WATCHDOG: %s (stream failure) -> scheduling retry" % event, lvl=Script.WARNING)
        self.want_retry = True

    def onPlayBackStopped(self):
        self._handle_stop("onPlayBackStopped")

    def onPlayBackEnded(self):
        self._handle_failure("onPlayBackEnded")

    def onPlayBackError(self):
        self._handle_failure("onPlayBackError")


def _make_listitem(info):
    item = xbmcgui.ListItem(path=info.get("url", ""))
    item.setProperty("IsPlayable", "true")
    item.setProperty("inputstream", "inputstream.adaptive")
    item.setProperty(
        "inputstream.adaptive.manifest_type", "mpd" if info.get("isMpd") else "hls"
    )
    if info.get("mode") == "direct":
        dh = info.get("direct_headers")
        if dh:
            enc = urlencode(dh)
            item.setProperty("inputstream.adaptive.stream_headers", enc)
            item.setProperty("inputstream.adaptive.manifest_headers", enc)
        item.setMimeType("application/vnd.apple.mpegurl")
    else:
        item.setProperty(
            "inputstream.adaptive.stream_selection_type",
            info.get("select_type", "adaptive"),
        )
        item.setProperty("inputstream.adaptive.chooser_resolution_secure_max", "4k")
        if info.get("headers"):
            enc = urlencode(info["headers"])
            item.setProperty("inputstream.adaptive.stream_headers", enc)
            item.setProperty("inputstream.adaptive.manifest_headers", enc)
        if info.get("isMpd") and info.get("license_key"):
            item.setProperty("inputstream.adaptive.license_type", "drm")
            item.setProperty(
                "inputstream.adaptive.license_key", info["license_key"]
            )
    return item


def _reconnect(watch, refresh):
    try:
        info = refresh()
    except Exception as e:
        Script.log("WATCHDOG: refresh() raised: %s" % e, lvl=Script.ERROR)
        return False
    if not info or not info.get("url"):
        Script.log("WATCHDOG: refresh returned no usable stream", lvl=Script.ERROR)
        return False
    try:
        watch._restarting = True
        item = _make_listitem(info)
        Script.log(
            "WATCHDOG: restarting playback: %s" % info.get("url"), lvl=Script.INFO
        )
        watch.play(info["url"], item)
        time.sleep(2)
        watch._restarting = False
        return True
    except Exception as e:
        watch._restarting = False
        Script.log("WATCHDOG: play error: %s" % e, lvl=Script.ERROR)
        return False


def _retry(watch, channel_id, refresh, max_attempts, attempt, reason="failure"):
    """Perform one reconnect attempt, respecting the maximum attempts limit."""
    if attempt >= max_attempts:
        Script.log(
            "WATCHDOG: %s but max attempts (%d) reached; giving up on channel %s"
            % (reason, max_attempts, channel_id),
            lvl=Script.ERROR,
        )
        try:
            xbmcgui.Dialog().notification(
                "JioTV", "Stream failed and could not auto-recover"
            )
        except Exception:
            pass
        return False
    Script.log(
        "WATCHDOG: reconnect needed (%s) on channel %s. Attempt %d/%d"
        % (reason, channel_id, attempt + 1, max_attempts),
        lvl=Script.WARNING,
    )
    if _reconnect(watch, refresh):
        Script.log(
            "WATCHDOG: reconnect attempt %d SUCCESS channel %s"
            % (attempt + 1, channel_id),
            lvl=Script.WARNING,
        )
        return True
    else:
        Script.log(
            "WATCHDOG: reconnect attempt %d FAILED channel %s"
            % (attempt + 1, channel_id),
            lvl=Script.ERROR,
        )
        return False


def watchdog(channel_id, refresh, max_attempts=3, stall_window=8, enable=True):
    """Background monitor for a playback session.

    If the stream stalls (buffers forever without recovering), it re-resolves a
    fresh URL via `refresh()` and restarts playback, up to `max_attempts` times.
    Exits automatically when playback ends/stops or Kodi is shutting down.
    """
    if not enable:
        Script.log("WATCHDOG: reconnect disabled by settings, not starting", lvl=Script.DEBUG)
        return

    watch = PlayerWatcher()
    mon = xbmc.Monitor()

    start_wait = time.time()
    while not watch.isPlaying() and not watch.stopped and not mon.abortRequested():
        if time.time() - start_wait > 35:
            Script.log(
                "WATCHDOG: playback never started within 35s; watchdog exiting",
                lvl=Script.DEBUG,
            )
            return
        xbmc.sleep(500)

    if watch.stopped or mon.abortRequested():
        return

    Script.log(
        "WATCHDOG: monitoring playback for channel %s (attempts=%d stall_window=%ss)"
        % (channel_id, max_attempts, stall_window),
        lvl=Script.INFO,
    )

    never_started = 40
    attempt = 0
    first_seen = time.time()
    last_time = None
    last_moved = None
    armed = False

    while not watch.stopped and not mon.abortRequested():
        if not watch.isPlaying():
            if watch.want_retry:
                watch.want_retry = False
                xbmc.sleep(500)
                if _retry(watch, channel_id, refresh, max_attempts, attempt, reason="failure"):
                    attempt += 1
                    first_seen = time.time()
                    last_time = None
                    last_moved = None
                    armed = False
                else:
                    return
            xbmc.sleep(500)
            continue

        paused = False
        try:
            paused = xbmc.getCondVisibility("Player.Paused")
        except Exception:
            paused = False

        try:
            cur = float(watch.getTime())
        except Exception:
            cur = 0.0

        if paused:
            last_moved = time.time()
            xbmc.sleep(1000)
            continue

        if last_time is None:
            last_time = cur
            last_moved = time.time()
            if cur > 0:
                armed = True
            xbmc.sleep(1000)
            continue

        if cur > last_time:
            last_time = cur
            last_moved = time.time()
            if not armed and cur > 0:
                armed = True
            xbmc.sleep(1000)
            continue

        stalled = False
        if armed:
            if cur == last_time and (time.time() - last_moved) >= stall_window:
                stalled = True
        else:
            if (time.time() - first_seen) >= never_started:
                stalled = True

        if stalled:
            if not _retry(watch, channel_id, refresh, max_attempts, attempt, reason="stall"):
                return
            attempt += 1
            first_seen = time.time()
            last_time = None
            last_moved = None
            armed = False

        xbmc.sleep(1000)

    Script.log(
        "WATCHDOG: stopping watchdog for channel %s (stopped=%s abort=%s)"
        % (channel_id, watch.stopped, mon.abortRequested()),
        lvl=Script.DEBUG,
    )
