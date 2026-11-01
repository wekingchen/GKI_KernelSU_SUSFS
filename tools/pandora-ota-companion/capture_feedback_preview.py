#!/usr/bin/env python3
"""CI emulator UI preview after instrumentation cleanup; does not run inside the APK."""
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


def adb(*args):
    return subprocess.run(['adb', *args], capture_output=True, check=True, timeout=35).stdout


def screen():
    # uiautomator may exit 0 before a hierarchy file exists (for example while
    # the activity is settling). Never consume an old file or treat exit 0 alone
    # as a successful dump. /data/local/tmp avoids emulated-storage timing.
    path = '/data/local/tmp/pandora-feedback-ui.xml'
    last = None
    for attempt in range(4):
        try:
            adb('shell', 'rm', '-f', path)
            adb('shell', 'uiautomator', 'dump', path)
            root = ET.fromstring(adb('shell', 'cat', path))
            if root.tag != 'hierarchy':
                raise ValueError('unexpected UI root')
            return root
        except (subprocess.SubprocessError, ET.ParseError, ValueError) as error:
            last = error
            if attempt < 3:
                time.sleep(1)
    raise RuntimeError('UI hierarchy unavailable after four bounded attempts') from last


def tap_text(prefix):
    for _ in range(5):
        root = screen()
        button = next((n for n in root.iter('node') if n.get('text', '').startswith(prefix)), None)
        if button is not None:
            bounds = list(map(int, re.findall(r'\d+', button.get('bounds', ''))))
            if len(bounds) != 4:
                raise RuntimeError('invalid UI button bounds')
            x1, y1, x2, y2 = bounds
            adb('shell', 'input', 'tap', str((x1+x2)//2), str((y1+y2)//2))
            time.sleep(2)
            return
        adb('shell', 'input', 'swipe', '720', '2500', '720', '900', '400')
        time.sleep(1)
    raise RuntimeError('UI entry not found: ' + prefix)


def main():
    adb('shell', 'am', 'force-stop', 'com.wekingchen.pandoraota')
    adb('shell', 'am', 'start', '-n', 'com.wekingchen.pandoraota/.MainActivity')
    time.sleep(2)
    tap_text('填写测试结果')
    root = screen()
    if not any(n.get('text') == '01  测试对象' for n in root.iter('node')):
        raise RuntimeError('native feedback form did not open')
    output = Path(sys.argv[1])
    output.write_bytes(adb('exec-out', 'screencap', '-p'))
    print('Native feedback form preview captured')
    adb('shell', 'input', 'keyevent', '4')
    time.sleep(1)
    tap_text('设置')
    tap_text('使用指南')
    root = screen()
    if not any(n.get('text') == '从新 OTA 到稳定内核，一条链路看懂' for n in root.iter('node')):
        raise RuntimeError('native help guide did not open')
    output.with_name('help-guide.png').write_bytes(adb('exec-out', 'screencap', '-p'))
    print('Native help guide preview captured')


if __name__ == '__main__':
    main()
