"""
Attachment extraction from E2B R3 ED-type (Encapsulated Data) fields.

The ICH E2B(R3) standard allows base64-encoded binary files in F.r.3.4
(result of tests — unstructured data). This module decodes and saves them.
"""

import base64
import os
from typing import Any, Dict, List


_MEDIA_EXT: Dict[str, str] = {
    'application/pdf':  '.pdf',
    'image/jpeg':       '.jpg',
    'image/png':        '.png',
    'image/gif':        '.gif',
    'text/plain':       '.txt',
    'text/html':        '.html',
    'application/xml':  '.xml',
    'text/xml':         '.xml',
}


def _safe_name(text: str) -> str:
    return ''.join(c if c.isalnum() or c in '-_.' else '_' for c in str(text))


def extract_attachments(data: Dict[str, Any], output_dir: str) -> List[str]:
    """
    Decode all base64-encoded ED attachments and write them to *output_dir*.

    Scans F.r.3.4 fields in the parsed ICSR dict.  Each attachment is saved as
    ``<report_id>_<test_name_or_index><ext>``.

    Args:
        data:       Parsed E2B R3 dict (from _parse_xml).
        output_dir: Directory where files will be written (created if absent).

    Returns:
        List of absolute paths of the files that were written.
    """
    os.makedirs(output_dir, exist_ok=True)

    c1 = data.get('c_1_identification_case_safety_report') or {}
    report_id = _safe_name(
        c1.get('c_1_1_sender_safety_report_unique_id') or 'report')

    tests = data.get('f_r_results_tests_procedures_investigation_patient') or []
    saved: List[str] = []

    for i, test in enumerate(tests):
        b64 = test.get('f_r_3_4_result_unstructured_data', '')
        if not b64:
            continue

        media_type = test.get('f_r_3_4_result_media_type', '')
        ext = _MEDIA_EXT.get(media_type, '.bin')

        try:
            raw = base64.b64decode(b64)
        except Exception:
            continue

        test_name = test.get('f_r_2_1_test_name') or f'attachment_{i + 1}'
        filename = f"{report_id}_{_safe_name(test_name)}{ext}"
        path = os.path.join(output_dir, filename)

        with open(path, 'wb') as fh:
            fh.write(raw)

        saved.append(os.path.abspath(path))

    return saved
