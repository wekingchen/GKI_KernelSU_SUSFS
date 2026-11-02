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
