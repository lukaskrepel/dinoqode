#!/usr/bin/env python3
# zbarcam replacement using picamera2 + pyzbar
# Outputs in the same format as zbarcam: QR-Code:<content>
import sys
import time

import cv2
from picamera2 import Picamera2
from pyzbar import pyzbar

while True:
    cam = None
    try:
        cam = Picamera2()
        cfg = cam.create_preview_configuration(
            main={"size": (640, 480), "format": "RGB888"}
        )
        cam.configure(cfg)
        cam.start()
        time.sleep(1)

        last_code = None
        last_time = 0

        while True:
            frame = cam.capture_array()
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            codes = pyzbar.decode(gray)
            now = time.time()
            for code in codes:
                data = code.data.decode("utf-8")
                if data != last_code or (now - last_time) > 3:
                    print("QR-Code:" + data, flush=True)
                    last_code = data
                    last_time = now
            time.sleep(0.2)

    except Exception as e:
        print(
            f"Camera error: {e}, restarting in 5 seconds...",
            flush=True,
            file=sys.stderr,
        )
        try:
            if cam:
                cam.stop()
                cam.close()
        except Exception:
            pass
        time.sleep(5)
