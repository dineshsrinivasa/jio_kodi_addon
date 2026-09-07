# -*- coding: utf-8 -*-
# Tata Play Binge Kodi addon entry point.
# Forwards control to resources.lib.main (codequick) and, if anything crashes,
# shows the full Python traceback on screen and saves it to the addon profile
# folder (widgets/binge_error.txt) so the developer can read it.

import sys
import traceback


def _report(tb):
    try:
        import xbmcvfs
        from xbmcaddon import Addon
        profile = xbmcvfs.translatePath(Addon().getAddonInfo("profile"))
        with xbmcvfs.File(profile + "binge_error.txt", "w") as f:
            f.write(tb)
    except Exception:
        pass
    try:
        from xbmcgui import Dialog
        Dialog().textviewer(
            "Tata Play Binge - ERROR",
            "The addon hit an error. Please screenshot this for the developer (or open "
            "the addon profile folder and send binge_error.txt):\n\n" + (tb or "")[-2500:],
        )
    except Exception:
        pass


if __name__ == '__main__':
    try:
        from resources.lib import main
        main.run()
    except SystemExit:
        pass
    except Exception:
        tb = traceback.format_exc()
        _report(tb)
        try:
            import xbmc
            xbmc.log("TATAPLAY-BINGE-ERROR: " + tb, xbmc.LOGERROR)
        except Exception:
            pass