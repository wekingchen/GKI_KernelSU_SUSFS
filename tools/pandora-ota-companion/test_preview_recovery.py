import subprocess
import unittest
from unittest.mock import patch
from capture_feedback_preview import screen

class PreviewDumpRecovery(unittest.TestCase):
    def test_missing_file_after_successful_dump_is_retried(self):
        calls=[]
        def adb(*args):
            calls.append(args)
            if args[0:2]==('shell','cat'):
                if sum(c[0:2]==('shell','cat') for c in calls)==1:
                    raise subprocess.CalledProcessError(1,['adb','shell','cat'])
                return b'<hierarchy><node text="ready" /></hierarchy>'
            return b''
        with patch('capture_feedback_preview.adb',side_effect=adb),patch('capture_feedback_preview.time.sleep'):
            self.assertEqual(screen().tag,'hierarchy')
        self.assertEqual(sum(c[0:2]==('shell','rm') for c in calls),2)
    def test_corrupt_dump_cannot_be_consumed_as_a_valid_screen(self):
        with patch('capture_feedback_preview.adb',return_value=b'not xml'),patch('capture_feedback_preview.time.sleep'):
            with self.assertRaisesRegex(RuntimeError,'four bounded attempts'):screen()
    def test_repeated_adb_timeout_stops(self):
        with patch('capture_feedback_preview.adb',side_effect=subprocess.TimeoutExpired('adb',35)),patch('capture_feedback_preview.time.sleep'):
            with self.assertRaises(RuntimeError):screen()

    def test_launcher_anr_is_closed_before_returning_app_hierarchy(self):
        dialog=b'''<hierarchy><node text="Pixel Launcher isn't responding"/><node resource-id="android:id/aerr_close" text="Close app" bounds="[10,20][110,60]"/></hierarchy>'''
        captures=iter([dialog,b'<hierarchy><node text="OTA"/></hierarchy>']);calls=[]
        def adb(*args):
            calls.append(args)
            return next(captures) if args[:2]==('shell','cat') else b''
        with patch('capture_feedback_preview.adb',side_effect=adb),patch('capture_feedback_preview.time.sleep'):
            self.assertEqual(screen().find('node').get('text'),'OTA')
        self.assertIn(('shell','input','tap','60','40'),calls)
        self.assertIn(('shell','am','force-stop','com.google.android.apps.nexuslauncher'),calls)
        self.assertNotIn(('shell','am','force-stop','com.wekingchen.pandoraota'),calls)

    def test_app_anr_is_not_dismissed_or_retried_as_launcher(self):
        dialog=b'''<hierarchy><node text="Pandora OTA isn't responding"/><node resource-id="android:id/aerr_close" bounds="[10,20][110,60]"/></hierarchy>'''
        calls=[]
        def adb(*args):
            calls.append(args);return dialog if args[:2]==('shell','cat') else b''
        with patch('capture_feedback_preview.adb',side_effect=adb),patch('capture_feedback_preview.time.sleep'):
            with self.assertRaisesRegex(RuntimeError,'Unexpected application error'):screen()
        self.assertFalse(any('tap' in c or 'force-stop' in c for c in calls))

    def test_persistent_launcher_anr_still_fails_after_bounded_attempts(self):
        dialog=b'''<hierarchy><node text="Pixel Launcher isn't responding"/><node resource-id="android:id/aerr_close" bounds="[10,20][110,60]"/></hierarchy>'''
        with patch('capture_feedback_preview.adb',return_value=dialog),patch('capture_feedback_preview.time.sleep'):
            with self.assertRaisesRegex(RuntimeError,'four bounded attempts'):screen()

    def test_navigation_waits_for_destination_instead_of_returning_after_tap(self):
        import xml.etree.ElementTree as ET
        from capture_feedback_preview import tap_text
        source=ET.fromstring('<hierarchy><node text="open" bounds="[10,20][110,60]"/></hierarchy>')
        dest=ET.fromstring('<hierarchy><node text="destination"/></hierarchy>')
        with patch('capture_feedback_preview.screen',side_effect=[source,source,dest]),patch('capture_feedback_preview.adb'),patch('capture_feedback_preview.time.sleep'):
            tap_text('open','destination')

    def test_screenshot_detection_rejects_black_and_accepts_real_rgb_rgba_filters(self):
        import struct,zlib
        from capture_feedback_preview import screenshot_visible
        def png(bright,mode=0,channels=4):
            w=h=32; rows=[];prev=bytearray(w*channels)
            for y in range(h):
                row=bytearray([bright]*3+([255] if channels==4 else []))*w;encoded=bytearray(len(row))
                for i in range(len(row)):
                    left=row[i-channels] if i>=channels else 0;up=prev[i];corner=prev[i-channels] if i>=channels else 0
                    predictors=[0,left,up,(left+up)//2]
                    value=left+up-corner;distances=[abs(value-left),abs(value-up),abs(value-corner)]
                    predictors.append([left,up,corner][distances.index(min(distances))])
                    encoded[i]=(row[i]-predictors[mode])&255
                rows.append(bytes([mode])+encoded);prev=row
            def chunk(name,data):return struct.pack('>I',len(data))+name+data+b'\0'*4
            return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6 if channels==4 else 2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')
        for channels in (3,4):
            for mode in range(5):
                self.assertTrue(screenshot_visible(png(240,mode,channels)))
                self.assertFalse(screenshot_visible(png(0,mode,channels)))

    def test_black_capture_is_not_saved_as_valid_preview(self):
        from capture_feedback_preview import capture
        from pathlib import Path
        with patch('capture_feedback_preview.screen'),patch('capture_feedback_preview.adb',return_value=b'png'),patch('capture_feedback_preview.screenshot_visible',return_value=False),patch('capture_feedback_preview.time.sleep'),patch.object(Path,'write_bytes') as save:
            with self.assertRaisesRegex(RuntimeError,'remained black'):capture(Path('unused.png'))
            save.assert_not_called()
