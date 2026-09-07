# -*- coding: utf-8 -*-
# Tata Play Binge Kodi addon entry point
# Simply forwards control to resources.lib.main which handles routing via codequick.

import sys

if __name__ == '__main__':
    from resources.lib import main
    main.run()