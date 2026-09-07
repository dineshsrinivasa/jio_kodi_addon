# Tata Play Binge Kodi Addon

Stream your **Tata Play Binge** subscribed channels — including the full **Zee TV** network lineup — directly in Kodi.

This addon authenticates to the Tata Play Binge (VideoReady) OTT service using your
**registered mobile number (RMN)** and **subscriber ID (SID)** via a one-time password (OTP),
then lets you watch every channel your subscription entitles (DASH + Widevine DRM).

## Why this addon?
- **Zee TV via Binge** — the Zee channels you expect come from Binge's own OTT entitlement
  (Zee TV, Zee News, Zee Telugu, Zee Kannada HD, and many more), no third-party hack needed.
- OTT login foundation that the VOD side will also share.

## Login
1. Open add-on **Settings** → enter your registered mobile number (RMN).
2. SID is auto-detected from your RMN if left blank (or enter it manually).
3. Tap **Send OTP**, enter the OTP received on your phone, then tap **Verify OTP and login**.

## Channels
- **Zee TV (via Binge)** — curated Zee-network channels.
- **All Channels** — every channel your subscription entitles.

## Playback
Channels play as MPEG-DASH with **Widevine** DRM via `inputstream.adaptive`.
A fresh `ls_session` license token is generated per channel at playback time
(the per-channel JWT expires after ~1 day).

## PVR
Generate a `playlist.m3u` from Settings → **PVR → Generate playlist.m3u** and point
`PVR IPTV Simple Client` at the generated file for live EPG-style viewing.

> **Note on VOD/OTT content:** the public VideoReady API surface that is openly
> documented/reused covers **live TV channels** (login, channel list, license tokens).
> Movies / shows browsing via in-app catalog endpoints is not part of any public
> reverse-engineering at this time, so this build ships the OTT authentication +
> all live Binge channels (incl. Zee TV networks). A logged-in session also returns
> your full entitlement/package list which future catalog browse can build on.

## Disclaimer
Not affiliated with or endorsed by Tata Play. Built from reverse-engineered public
APIs of the Tata Play Binge service. An active Tata Play Binge subscription is required.