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
