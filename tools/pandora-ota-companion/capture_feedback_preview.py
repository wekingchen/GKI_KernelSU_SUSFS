#!/usr/bin/env python3
"""CI emulator UI preview after instrumentation cleanup; does not run inside the APK."""
from pathlib import Path
import re
import struct
import zlib
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
            adb('shell', 'input', 'keyevent', 'KEYCODE_WAKEUP')
            adb('shell', 'wm', 'dismiss-keyguard')
            adb('shell', 'rm', '-f', path)
            adb('shell', 'uiautomator', 'dump', path)
            root = ET.fromstring(adb('shell', 'cat', path))
            if root.tag != 'hierarchy':
                raise ValueError('unexpected UI root')
            messages = ' '.join(n.get('text', '') for n in root.iter('node'))
            close = next((n for n in root.iter('node') if n.get('resource-id') == 'android:id/aerr_close'), None)
            if close is not None:
                if "Pixel Launcher isn't responding" not in messages:
                    raise RuntimeError('Unexpected application error dialog: ' + messages)
                # Only the emulator launcher is disposable. Never hide an OTA App ANR.
                tap_node(close)
                adb('shell', 'am', 'force-stop', 'com.google.android.apps.nexuslauncher')
                time.sleep(1)
                continue
            return root
        except (subprocess.SubprocessError, ET.ParseError, ValueError) as error:
            last = error
            if attempt < 3:
                time.sleep(1)
    raise RuntimeError('UI hierarchy unavailable after four bounded attempts') from last


def tap_node(node):
    bounds = list(map(int, re.findall(r'\d+', node.get('bounds', ''))))
    if len(bounds) != 4 or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        raise RuntimeError('invalid UI button bounds')
    x1, y1, x2, y2 = bounds
    adb('shell', 'input', 'tap', str((x1+x2)//2), str((y1+y2)//2))


def tap_text(prefix, expected=None):
    for _ in range(5):
        root = screen()
        button = next((n for n in root.iter('node') if n.get('text', '').startswith(prefix)), None)
        if button is not None:
            tap_node(button)
            time.sleep(2)
            if expected is not None:
                for check in range(4):
                    if any(n.get('text', '').startswith(expected) for n in screen().iter('node')):
                        return
                    time.sleep(1)
                # Retrying a navigation tap is safe; never retry a write action here.
                continue
            return
        adb('shell', 'input', 'swipe', '720', '2500', '720', '900', '400')
        time.sleep(1)
    raise RuntimeError('UI entry not found: ' + prefix)


def screenshot_visible(data):
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('invalid screenshot PNG')
    pos = 8; compressed = bytearray(); width = height = channels = 0
    while pos < len(data):
        length = struct.unpack('>I', data[pos:pos+4])[0]
        kind = data[pos+4:pos+8]; chunk = data[pos+8:pos+8+length]; pos += length+12
        if kind == b'IHDR':
            width,height,depth,color,_,_,interlace = struct.unpack('>IIBBBBB',chunk)
            if depth != 8 or color not in (2,6) or interlace or not (0 < width <= 4096 and 0 < height <= 8192):
                raise ValueError('unsupported screenshot PNG')
            channels = 3 if color == 2 else 4
        elif kind == b'IDAT': compressed.extend(chunk)
    stride = width*channels
    raw = zlib.decompress(compressed)
    if not stride or len(raw) != height*(stride+1): raise ValueError('incomplete screenshot PNG')
    previous = bytearray(stride); visible = total = 0
    target_samples = ((width+15)//16)*(height*9//10)
    for y in range(height*9//10):
        at=y*(stride+1); mode=raw[at]; row=bytearray(raw[at+1:at+1+stride])
        for i in range(stride):
            left=row[i-channels] if i >= channels else 0; up=previous[i]; corner=previous[i-channels] if i >= channels else 0
            if mode == 1: predictor=left
            elif mode == 2: predictor=up
            elif mode == 3: predictor=(left+up)//2
            elif mode == 4:
                value=left+up-corner; distances=(abs(value-left),abs(value-up),abs(value-corner))
                predictor=(left,up,corner)[distances.index(min(distances))]
            elif mode == 0: predictor=0
            else: raise ValueError('invalid PNG filter')
            row[i]=(row[i]+predictor)&255
        if y < height*9//10:
            for x in range(0,width,16):
                total += 1
                visible += max(row[x*channels:x*channels+3]) > 40
        if visible > target_samples*.05:
            return True
        previous=row
    return total > 0 and visible/total > .05


def capture(path):
    for attempt in range(4):
        screen()
        data=adb('exec-out','screencap','-p')
        if screenshot_visible(data):
            path.write_bytes(data)
            return
        time.sleep(1)
    raise RuntimeError('emulator display remained black after bounded wake/render checks')


def main():
    output = Path(sys.argv[1])
    adb('shell', 'svc', 'power', 'stayon', 'true')
    adb('shell', 'settings', 'put', 'system', 'screen_off_timeout', '2147483647')
    adb('shell', 'input', 'keyevent', 'KEYCODE_WAKEUP')
    adb('shell', 'wm', 'dismiss-keyguard')
    adb('shell', 'am', 'force-stop', 'com.wekingchen.pandoraota')
    adb('shell', 'am', 'start', '-W', '-n', 'com.wekingchen.pandoraota/.MainActivity')
    time.sleep(2)
    screen()
    capture(output.with_name('workbench.png'))
    tap_text('记录')
    screen()
    capture(output.with_name('records.png'))
    tap_text('设置')
    screen()
    capture(output.with_name('settings.png'))
    tap_text('工作台')
    tap_text('填写测试结果', '01  测试对象')
    root = screen()
    if not any(n.get('text') == '01  测试对象' for n in root.iter('node')):
        raise RuntimeError('native feedback form did not open')
    capture(output)
    print('Native feedback form preview captured')
    adb('shell', 'input', 'keyevent', '4')
    time.sleep(1)
    tap_text('刷新可信状态')
    root = screen()
    if not any('OTA 全链路状态' in n.get('text', '') for n in root.iter('node')):
        raise RuntimeError('stage card did not appear')
    capture(output.with_name('stage-status.png'))
    print('Native stage status card preview captured')
    tap_text('设置')
    tap_text('使用指南', '从新 OTA 到稳定内核，一条链路看懂')
    root = screen()
    if not any(n.get('text') == '从新 OTA 到稳定内核，一条链路看懂' for n in root.iter('node')):
        raise RuntimeError('native help guide did not open')
    capture(output.with_name('help-guide.png'))
    print('Native help guide preview captured')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Keep the actual blocked screen/hierarchy without changing test outcome.
        output = Path(sys.argv[1])
        for name, command in (
            ('preview-failure.png', ('exec-out', 'screencap', '-p')),
            ('preview-failure.xml', ('shell', 'cat', '/data/local/tmp/pandora-feedback-ui.xml')),
            ('preview-power.txt', ('shell', 'dumpsys', 'power')),
            ('preview-window.txt', ('shell', 'dumpsys', 'window')),
            ('preview-activity.txt', ('shell', 'dumpsys', 'activity', 'activities')),
            ('preview-logcat.txt', ('logcat', '-d', '-t', '400')),
        ):
            try:
                output.with_name(name).write_bytes(adb(*command))
            except Exception as diagnostic_error:
                print('Diagnostic capture failed:', diagnostic_error, file=sys.stderr)
        raise
