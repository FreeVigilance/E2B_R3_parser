"""
E2B R3 ICSR Import/Export Module
=================================
Модуль импорта и экспорта данных по безопасности лекарственных препаратов
в формате E2B R3 (ICH E2B(R3) Individual Case Safety Report).

Поддерживаемые форматы конвертации:
    XML (E2B R3) → JSON
    XML (E2B R3) → HTML
    XML (E2B R3) → SQL
    XML (E2B R3) → CIOMS (форма CIOMS I)
    JSON          → XML (E2B R3)

Использование:
    from e2b_converter import E2BConverter

    with open('report.xml', encoding='utf-8') as f:
        xml_data = f.read()

    json_out  = E2BConverter.xml_to_json(xml_data)
    html_out  = E2BConverter.xml_to_html(xml_data)
    sql_out   = E2BConverter.xml_to_sql(xml_data)
    cioms_out = E2BConverter.xml_to_cioms(xml_data)

Стандарт: ICH E2B(R3)
Лицензия: GNU GPL v3
"""

import json
from typing import Any, Dict, List, Optional

from _constants import __version__, __author__, __license__
from _xml_parser import _parse_xml
from _json_converter import _to_json
from _html_converter import _to_html
from _sql_converter import _to_sql
from _xml_generator import _to_xml
from _cioms_converter import _to_cioms
from _attachments import extract_attachments as _extract_attachments


class E2BConverter:
    """
    Converter for E2B R3 Individual Case Safety Report (ICSR) data.

    Supported conversions:
        XML  → JSON  (xml_to_json)
        XML  → HTML  (xml_to_html)
        XML  → SQL   (xml_to_sql)
        XML  → CIOMS (xml_to_cioms)
        JSON → XML   (json_to_xml)

    Attachment extraction:
        extract_attachments(xml_string, output_dir)

    File helpers:
        save_as_json, save_as_html, save_as_sql, save_as_cioms
        load_xml_file, load_json_file
    """

    @staticmethod
    def xml_to_dict(xml_string: str) -> Dict[str, Any]:
        """Parse E2B R3 XML to a Python dict."""
        _, data = _parse_xml(xml_string)
        return data

    @staticmethod
    def xml_to_json(xml_string: str, indent: int = 2,
                    include_empty: bool = False) -> str:
        """
        Convert E2B R3 XML to a clean JSON string.

        Args:
            xml_string:    Raw XML text.
            indent:        JSON indentation level (default 2).
            include_empty: If True, include null/empty fields in output.

        Returns:
            JSON string.
        """
        root_tag, data = _parse_xml(xml_string)
        return _to_json(data, root_tag, indent=indent, include_empty=include_empty)

    @staticmethod
    def xml_to_html(xml_string: str) -> str:
        """
        Convert E2B R3 XML to a styled HTML report.

        Args:
            xml_string: Raw XML text.

        Returns:
            Complete HTML document as string.
        """
        root_tag, data = _parse_xml(xml_string)
        return _to_html(data, root_tag)

    @staticmethod
    def xml_to_sql(xml_string: str, dialect: str = 'sqlite',
                   include_ddl: bool = True) -> str:
        """
        Convert E2B R3 XML to SQL statements.

        Args:
            xml_string:  Raw XML text.
            dialect:     'sqlite' (default) or 'postgresql'.
            include_ddl: Prepend CREATE TABLE statements (default True).

        Returns:
            SQL text with DDL and INSERT statements.
        """
        root_tag, data = _parse_xml(xml_string)
        return _to_sql(data, root_tag, dialect=dialect, include_ddl=include_ddl)

    @staticmethod
    def xml_to_cioms(xml_string: str) -> str:
        """
        Convert E2B R3 XML to a printable CIOMS I form (HTML).

        Args:
            xml_string: Raw XML text.

        Returns:
            Standalone HTML document with the filled CIOMS form.
        """
        root_tag, data = _parse_xml(xml_string)
        return _to_cioms(data)

    @staticmethod
    def extract_attachments(xml_string: str, output_dir: str) -> List[str]:
        """
        Decode and save all base64-encoded ED attachments from F.r.3.4 fields.

        Args:
            xml_string: Raw XML text.
            output_dir: Directory where decoded files will be written.

        Returns:
            List of absolute paths of the files that were written.
        """
        _, data = _parse_xml(xml_string)
        return _extract_attachments(data, output_dir)

    @staticmethod
    def json_to_xml(json_string: str) -> str:
        """
        Convert a JSON string (previously exported by xml_to_json) back to
        E2B R3 application XML.

        Args:
            json_string: JSON text produced by xml_to_json.

        Returns:
            XML string.
        """
        obj = json.loads(json_string)
        if not isinstance(obj, dict) or len(obj) != 1:
            raise ValueError('JSON must be a single-key object {root_tag: {...}}')
        root_tag, data = next(iter(obj.items()))
        return _to_xml(data, root_tag)

    @staticmethod
    def load_xml_file(path: str) -> Dict[str, Any]:
        """Load and parse an E2B R3 XML file, returning a Python dict."""
        with open(path, encoding='utf-8') as f:
            return E2BConverter.xml_to_dict(f.read())

    @staticmethod
    def load_json_file(path: str) -> Dict[str, Any]:
        """Load an exported JSON file, returning a Python dict."""
        with open(path, encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def save_as_json(xml_string: str, output_path: str,
                     indent: int = 2, include_empty: bool = False) -> None:
        """Convert XML and write JSON to *output_path*."""
        result = E2BConverter.xml_to_json(xml_string, indent=indent,
                                          include_empty=include_empty)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result)

    @staticmethod
    def save_as_html(xml_string: str, output_path: str) -> None:
        """Convert XML and write HTML report to *output_path*."""
        result = E2BConverter.xml_to_html(xml_string)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result)

    @staticmethod
    def save_as_sql(xml_string: str, output_path: str,
                    dialect: str = 'sqlite', include_ddl: bool = True) -> None:
        """Convert XML and write SQL to *output_path*."""
        result = E2BConverter.xml_to_sql(xml_string, dialect=dialect,
                                         include_ddl=include_ddl)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result)

    @staticmethod
    def save_as_cioms(xml_string: str, output_path: str) -> None:
        """Convert XML and write CIOMS form HTML to *output_path*."""
        result = E2BConverter.xml_to_cioms(xml_string)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result)

    @staticmethod
    def convert_file(input_path: str, output_format: str,
                     output_path: Optional[str] = None, **kwargs) -> str:
        """
        Convenience: read *input_path* (XML or JSON) and convert.

        Args:
            input_path:    Path to source file (.xml or .json).
            output_format: One of 'json', 'html', 'sql', 'cioms', 'xml'.
            output_path:   If given, write result to this file as well.
            **kwargs:      Forwarded to the specific converter.

        Returns:
            Converted string.
        """
        with open(input_path, encoding='utf-8') as f:
            content = f.read()

        ext = input_path.rsplit('.', 1)[-1].lower()
        if ext == 'json' and output_format == 'xml':
            result = E2BConverter.json_to_xml(content)
        elif ext in ('xml', 'txt'):
            fmt = output_format.lower()
            if fmt == 'json':
                result = E2BConverter.xml_to_json(content, **kwargs)
            elif fmt == 'html':
                result = E2BConverter.xml_to_html(content)
            elif fmt == 'sql':
                result = E2BConverter.xml_to_sql(content, **kwargs)
            elif fmt == 'cioms':
                result = E2BConverter.xml_to_cioms(content)
            else:
                raise ValueError(f'Unknown output format: {output_format}')
        else:
            raise ValueError(f'Cannot determine conversion for input extension: {ext}')

        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(result)

        return result


# Module-level convenience functions
def xml_to_json(xml_string: str, indent: int = 2) -> str:
    """Convert E2B R3 XML to JSON string."""
    return E2BConverter.xml_to_json(xml_string, indent=indent)


def xml_to_html(xml_string: str) -> str:
    """Convert E2B R3 XML to HTML report."""
    return E2BConverter.xml_to_html(xml_string)


def xml_to_sql(xml_string: str, dialect: str = 'sqlite') -> str:
    """Convert E2B R3 XML to SQL statements."""
    return E2BConverter.xml_to_sql(xml_string, dialect=dialect)


def xml_to_cioms(xml_string: str) -> str:
    """Convert E2B R3 XML to CIOMS I form HTML."""
    return E2BConverter.xml_to_cioms(xml_string)


def json_to_xml(json_string: str) -> str:
    """Convert JSON (from xml_to_json) back to E2B R3 XML."""
    return E2BConverter.json_to_xml(json_string)


def extract_attachments(xml_string: str, output_dir: str) -> List[str]:
    """Decode and save ED attachments from F.r.3.4 fields."""
    return E2BConverter.extract_attachments(xml_string, output_dir)


def _cli_main() -> None:
    import argparse
    import sys
    import os

    parser = argparse.ArgumentParser(
        prog='e2b_converter',
        description='E2B R3 ICSR Import/Export Tool — converts XML ↔ JSON/HTML/SQL/CIOMS',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python e2b_converter.py report.xml --format json  -o report.json
  python e2b_converter.py report.xml --format html  -o report.html
  python e2b_converter.py report.xml --format sql   -o report.sql
  python e2b_converter.py report.xml --format cioms -o cioms.html
  python e2b_converter.py report.xml --format sql   --dialect postgresql -o report.sql
  python e2b_converter.py report.json --format xml  -o report_out.xml
  python e2b_converter.py report.xml --attach ./attachments/
        """
    )
    parser.add_argument('input', help='Input file path (.xml or .json)')
    parser.add_argument('-f', '--format', default=None,
                        choices=['json', 'html', 'sql', 'cioms', 'xml'],
                        help='Output format')
    parser.add_argument('-o', '--output', default=None,
                        help='Output file path (stdout if omitted)')
    parser.add_argument('--dialect', default='sqlite',
                        choices=['sqlite', 'postgresql'],
                        help='SQL dialect (only for --format sql, default: sqlite)')
    parser.add_argument('--include-empty', action='store_true',
                        help='Include empty/null fields in JSON output')
    parser.add_argument('--no-ddl', action='store_true',
                        help='Omit CREATE TABLE statements from SQL output')
    parser.add_argument('--attach', metavar='DIR', default=None,
                        help='Decode and save ED attachments (F.r.3.4) to DIR')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')

    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f'Error: file not found: {args.input}', file=sys.stderr)
        sys.exit(1)

    with open(args.input, encoding='utf-8') as f:
        content = f.read()

    ext = args.input.rsplit('.', 1)[-1].lower()

    # Parse once; reused by both --attach and --format to avoid double work
    parsed: Optional[tuple] = None

    def _get_parsed():
        nonlocal parsed
        if parsed is None:
            parsed = _parse_xml(content)
        return parsed

    # Handle --attach (independent of --format)
    if args.attach:
        try:
            _, data = _get_parsed()
            saved = _extract_attachments(data, args.attach)
            if saved:
                print(f'Extracted {len(saved)} attachment(s):')
                for p in saved:
                    print(f'  {p}')
            else:
                print('No attachments found in this report.')
        except Exception as exc:
            print(f'Attachment extraction error: {exc}', file=sys.stderr)
            sys.exit(2)
        if not args.format:
            return

    if not args.format:
        print('Error: --format is required (unless using --attach only)', file=sys.stderr)
        sys.exit(1)

    try:
        if args.format == 'xml':
            if ext != 'json':
                print('Error: --format xml expects a JSON input file', file=sys.stderr)
                sys.exit(1)
            result = E2BConverter.json_to_xml(content)
        else:
            root_tag, data = _get_parsed()
            if args.format == 'json':
                result = _to_json(data, root_tag, include_empty=args.include_empty)
            elif args.format == 'html':
                result = _to_html(data, root_tag)
            elif args.format == 'sql':
                result = _to_sql(data, root_tag, dialect=args.dialect,
                                 include_ddl=not args.no_ddl)
            elif args.format == 'cioms':
                result = _to_cioms(data)
            else:
                print(f'Error: unknown format {args.format}', file=sys.stderr)
                sys.exit(1)
    except Exception as exc:
        print(f'Conversion error: {exc}', file=sys.stderr)
        sys.exit(2)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f'Saved to {args.output}')
    else:
        sys.stdout.buffer.write(result.encode('utf-8'))
        sys.stdout.buffer.write(b'\n')


if __name__ == '__main__':
    _cli_main()
