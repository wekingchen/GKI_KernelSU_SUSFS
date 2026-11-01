#!/usr/bin/env python3
"""Reject duplicate mobile request IDs before any failure Issue or baseline mutation."""
import json
import os
import re
import sys

WORKFLOW = '.github/workflows/xiaomi-sm8850-os4-ota-test-feedback.yml'


def previous_run(pages, request, current):
    if not re.fullmatch(r'[a-f0-9]{32}', request):
        raise ValueError('invalid client request ID')
    matches = [r['id'] for page in pages for r in page.get('workflow_runs', [])
               if isinstance(r.get('id'), int) and r['id'] < current
               and r.get('head_branch') == 'dev' and r.get('event') == 'workflow_dispatch'
               and r.get('path') == WORKFLOW and r.get('display_title') == 'Pandora OTA feedback / ' + request]
    return min(matches) if matches else None


if __name__ == '__main__':
    previous = previous_run(json.load(sys.stdin), os.environ['CLIENT_REQUEST_ID'], int(os.environ['GITHUB_RUN_ID']))
    if previous:
        raise SystemExit(f'Duplicate mobile feedback; follow original Run {previous}. No new Issue or baseline mutation.')
