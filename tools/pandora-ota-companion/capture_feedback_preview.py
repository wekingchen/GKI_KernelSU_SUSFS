#!/usr/bin/env python3
"""CI emulator UI preview after instrumentation cleanup; does not run inside the APK."""
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


def adb(*args):
    return subprocess.run(['adb', *args], capture_output=True, check=True).stdout


def screen():
    adb('shell', 'uiautomator', 'dump', '/sdcard/pandora-feedback-ui.xml')
    return ET.fromstring(adb('shell', 'cat', '/sdcard/pandora-feedback-ui.xml'))


def main():
    adb('shell', 'am', 'force-stop', 'com.wekingchen.pandoraota')
    adb('shell', 'am', 'start', '-n', 'com.wekingchen.pandoraota/.MainActivity')
    time.sleep(2)
    for _ in range(5):
        root = screen()
        button = next((n for n in root.iter('node') if n.get('text', '').startswith('填写测试结果')), None)
        if button is not None:
            bounds = list(map(int, re.findall(r'\d+', button.get('bounds', ''))))
            if len(bounds) != 4:
                raise RuntimeError('invalid feedback button bounds')
            x1, y1, x2, y2 = bounds
            adb('shell', 'input', 'tap', str((x1+x2)//2), str((y1+y2)//2))
            time.sleep(2)
            root = screen()
            if not any(n.get('text') == '01  测试对象' for n in root.iter('node')):
                raise RuntimeError('native feedback form did not open')
            Path(sys.argv[1]).write_bytes(adb('exec-out', 'screencap', '-p'))
            print('Native feedback form preview captured')
            return
        adb('shell', 'input', 'swipe', '720', '2500', '720', '900', '400')
        time.sleep(1)
    raise RuntimeError('feedback entry not found on workbench')


if __name__ == '__main__':
    main()
