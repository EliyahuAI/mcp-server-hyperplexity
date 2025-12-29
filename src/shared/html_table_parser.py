#!/usr/bin/env python3
"""
HTML Table Parser for extracting structured table data from HTML content.
Handles various table structures including standard HTML tables, lists, and divs.
"""

import logging
import re
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import aiohttp
import asyncio

logger = logging.getLogger(__name__)

# Jina AI Reader endpoint for clean content extraction
JINA_READER_BASE = "https://r.jina.ai/"


class HTMLTableParser:
    """Parser for extracting tables from HTML content."""

    def __init__(self, timeout: int = 30):
        """
        Initialize HTML table parser.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        logger.info("Initialized HTMLTableParser")

    async def fetch_html(self, url: str) -> Dict[str, Any]:
        """
        Fetch HTML content from a URL.

        Args:
            url: URL to fetch

        Returns:
            Dictionary with:
            {
                'success': bool,
                'html': str,  # Raw HTML content
                'status_code': int,
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'html': '',
            'status_code': 0,
            'error': None
        }

        try:
            logger.info(f"Fetching HTML from {url}")

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=self.timeout) as response:
                    result['status_code'] = response.status

                    if response.status == 200:
                        html_content = await response.text()
                        result['success'] = True
                        result['html'] = html_content
                        logger.info(f"  [SUCCESS] Fetched {len(html_content)} characters from {url}")
                    else:
                        result['error'] = f"HTTP {response.status}"
                        logger.warning(f"  [FAILED] HTTP {response.status} for {url}")

        except asyncio.TimeoutError:
            result['error'] = f"Timeout after {self.timeout}s"
            logger.error(f"  [TIMEOUT] Failed to fetch {url}")
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"  [ERROR] Failed to fetch {url}: {str(e)}")

        return result

    def parse_html_tables(self, html: str, table_name: str = None) -> Dict[str, Any]:
        """
        Parse HTML content to extract table structures.

        Args:
            html: HTML content as string
            table_name: Optional table name to search for (helps identify specific table)

        Returns:
            Dictionary with:
            {
                'success': bool,
                'tables_found': int,
                'tables': List[Dict],  # Each with 'headers', 'rows', 'table_index'
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'tables_found': 0,
            'tables': [],
            'error': None
        }

        try:
            soup = BeautifulSoup(html, 'lxml')  # Faster C-based parser

            # Find all table elements
            html_tables = soup.find_all('table')

            if not html_tables:
                result['error'] = 'No HTML tables found'
                logger.warning("  [NO TABLES] No <table> elements found in HTML")
                return result

            logger.info(f"  Found {len(html_tables)} HTML table(s)")

            # Parse each table
            for idx, html_table in enumerate(html_tables):
                parsed_table = self._parse_single_table(html_table, idx)

                if parsed_table['rows_count'] > 0:
                    result['tables'].append(parsed_table)
                    logger.info(
                        f"    Table {idx + 1}: {parsed_table['rows_count']} rows, "
                        f"{len(parsed_table['headers'])} columns"
                    )

            result['success'] = len(result['tables']) > 0
            result['tables_found'] = len(result['tables'])

            if result['tables_found'] == 0:
                result['error'] = 'No parseable tables found'

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"  [ERROR] Failed to parse HTML tables: {str(e)}")

        return result

    def _parse_single_table(self, table_element, table_index: int) -> Dict[str, Any]:
        """
        Parse a single HTML table element.

        Args:
            table_element: BeautifulSoup table element
            table_index: Index of this table in the document

        Returns:
            Dictionary with:
            {
                'table_index': int,
                'headers': List[str],
                'rows': List[Dict],  # Each row is dict with column names as keys
                'rows_count': int,
                'raw_rows': List[List[str]]  # Raw row data as 2D array
            }
        """
        parsed = {
            'table_index': table_index,
            'headers': [],
            'rows': [],
            'rows_count': 0,
            'raw_rows': []
        }

        try:
            # Extract headers (try <thead>, then first <tr>)
            headers = []

            thead = table_element.find('thead')
            if thead:
                header_row = thead.find('tr')
                if header_row:
                    headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]

            # If no thead, try first row
            if not headers:
                first_row = table_element.find('tr')
                if first_row:
                    # Check if first row contains <th> elements
                    ths = first_row.find_all('th')
                    if ths:
                        headers = [th.get_text(strip=True) for th in ths]
                    else:
                        # Use first row as headers if it looks like headers
                        tds = first_row.find_all('td')
                        headers = [td.get_text(strip=True) for td in tds]

            # If still no headers, generate generic ones
            if not headers:
                # Count columns from first data row
                tbody = table_element.find('tbody')
                if tbody:
                    first_data_row = tbody.find('tr')
                    if first_data_row:
                        col_count = len(first_data_row.find_all(['td', 'th']))
                        headers = [f'Column_{i+1}' for i in range(col_count)]

            parsed['headers'] = headers

            # Extract data rows
            tbody = table_element.find('tbody')
            if not tbody:
                # If no tbody, get all rows except the header row
                tbody = table_element

            rows = tbody.find_all('tr')

            # Skip first row if it was used as headers
            start_idx = 0
            if not table_element.find('thead'):
                first_row = table_element.find('tr')
                if first_row and first_row.find('th'):
                    start_idx = 1

            for row in rows[start_idx:]:
                cells = row.find_all(['td', 'th'])
                if not cells:
                    continue

                # Extract cell values
                cell_values = [cell.get_text(strip=True) for cell in cells]

                # Skip empty rows
                if not any(cell_values):
                    continue

                parsed['raw_rows'].append(cell_values)

                # Create row dict with headers
                if len(headers) > 0:
                    row_dict = {}
                    for i, header in enumerate(headers):
                        value = cell_values[i] if i < len(cell_values) else ''
                        row_dict[header] = value
                    parsed['rows'].append(row_dict)

            parsed['rows_count'] = len(parsed['rows'])

        except Exception as e:
            logger.error(f"Error parsing table {table_index}: {str(e)}")

        return parsed

    def parse_lists(self, html: str) -> Dict[str, Any]:
        """
        Parse HTML lists (ul, ol) as potential table data.
        Useful for sites that structure tabular data as lists.

        Args:
            html: HTML content as string

        Returns:
            Dictionary with:
            {
                'success': bool,
                'lists_found': int,
                'lists': List[Dict],  # Each with 'items', 'list_type'
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'lists_found': 0,
            'lists': [],
            'error': None
        }

        try:
            soup = BeautifulSoup(html, 'lxml')  # Faster C-based parser

            # Find all list elements
            lists = soup.find_all(['ul', 'ol'])

            if not lists:
                result['error'] = 'No lists found'
                return result

            logger.info(f"  Found {len(lists)} list(s)")

            for idx, list_element in enumerate(lists):
                items = [li.get_text(strip=True) for li in list_element.find_all('li')]

                if len(items) > 0:
                    list_data = {
                        'list_index': idx,
                        'list_type': list_element.name,  # 'ul' or 'ol'
                        'items': items,
                        'items_count': len(items)
                    }
                    result['lists'].append(list_data)
                    logger.info(f"    List {idx + 1}: {len(items)} items")

            result['success'] = len(result['lists']) > 0
            result['lists_found'] = len(result['lists'])

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"  [ERROR] Failed to parse lists: {str(e)}")

        return result

    def detect_pagination(self, html: str) -> Dict[str, Any]:
        """
        Detect if the page has pagination (indicating more data available).

        Args:
            html: HTML content as string

        Returns:
            Dictionary with:
            {
                'pagination_detected': bool,
                'next_page_url': Optional[str],
                'total_pages': Optional[int],
                'current_page': Optional[int]
            }
        """
        result = {
            'pagination_detected': False,
            'next_page_url': None,
            'total_pages': None,
            'current_page': None
        }

        try:
            soup = BeautifulSoup(html, 'lxml')  # Faster C-based parser

            # Look for common pagination indicators
            pagination_keywords = ['next', 'pagination', 'page', 'pager', 'nav']

            # Search for elements with pagination-related classes or IDs
            for keyword in pagination_keywords:
                elements = soup.find_all(class_=re.compile(keyword, re.I))
                elements.extend(soup.find_all(id=re.compile(keyword, re.I)))

                if elements:
                    result['pagination_detected'] = True

                    # Try to find "next" link
                    for elem in elements:
                        next_link = elem.find('a', text=re.compile(r'next|>|→', re.I))
                        if next_link and next_link.get('href'):
                            result['next_page_url'] = next_link['href']
                            break

                    break

            # Try to detect page numbers
            if result['pagination_detected']:
                # Look for patterns like "Page 1 of 10" or "1 / 10"
                text = soup.get_text()
                page_match = re.search(r'Page\s+(\d+)\s+of\s+(\d+)', text, re.I)
                if page_match:
                    result['current_page'] = int(page_match.group(1))
                    result['total_pages'] = int(page_match.group(2))

        except Exception as e:
            logger.error(f"Error detecting pagination: {str(e)}")

        return result

    async def fetch_via_jina(self, url: str) -> Dict[str, Any]:
        """
        Fetch content via Jina AI Reader (handles JS-rendered content).

        Args:
            url: URL to fetch

        Returns:
            Dictionary with:
            {
                'success': bool,
                'markdown': str,  # Clean markdown content
                'title': str,
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'markdown': '',
            'title': '',
            'error': None
        }

        try:
            jina_url = f"{JINA_READER_BASE}{url}"
            logger.info(f"Fetching via Jina AI Reader: {url}")

            headers = {
                'Accept': 'text/markdown',
                'X-Return-Format': 'markdown'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(jina_url, headers=headers, timeout=self.timeout) as response:
                    if response.status == 200:
                        content = await response.text()

                        # Extract title from first line if it's a heading
                        lines = content.split('\n')
                        title = ''
                        if lines and lines[0].startswith('#'):
                            title = lines[0].lstrip('#').strip()

                        result['success'] = True
                        result['markdown'] = content
                        result['title'] = title

                        logger.info(f"  [SUCCESS] Jina returned {len(content)} chars")
                    else:
                        result['error'] = f"Jina API returned HTTP {response.status}"
                        logger.warning(f"  [FAILED] Jina HTTP {response.status}")

        except asyncio.TimeoutError:
            result['error'] = f"Jina timeout after {self.timeout}s"
            logger.error(f"  [TIMEOUT] Jina request timed out")
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"  [ERROR] Jina fetch failed: {str(e)}")

        return result

    def parse_markdown_tables(self, markdown: str) -> Dict[str, Any]:
        """
        Parse markdown tables from Jina AI Reader output.

        Args:
            markdown: Markdown content from Jina

        Returns:
            Dictionary with tables found in markdown format
        """
        result = {
            'success': False,
            'tables_found': 0,
            'tables': [],
            'error': None
        }

        try:
            # Find markdown tables (format: | col1 | col2 |)
            table_pattern = r'\|[^\n]+\|\n\|[-:\s|]+\|\n(\|[^\n]+\|\n)+'
            table_matches = re.finditer(table_pattern, markdown, re.MULTILINE)

            tables = []
            for idx, match in enumerate(table_matches):
                table_text = match.group(0)
                parsed = self._parse_markdown_table(table_text, idx)
                if parsed['rows_count'] > 0:
                    tables.append(parsed)

            result['success'] = len(tables) > 0
            result['tables_found'] = len(tables)
            result['tables'] = tables

            if len(tables) == 0:
                result['error'] = 'No markdown tables found'
            else:
                logger.info(f"  Parsed {len(tables)} markdown table(s)")

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"  [ERROR] Markdown table parsing failed: {str(e)}")

        return result

    def _parse_markdown_table(self, table_text: str, table_index: int) -> Dict[str, Any]:
        """
        Parse a single markdown table.

        Args:
            table_text: Markdown table text
            table_index: Index of this table

        Returns:
            Dictionary with headers and rows
        """
        parsed = {
            'table_index': table_index,
            'headers': [],
            'rows': [],
            'rows_count': 0
        }

        try:
            lines = [line.strip() for line in table_text.strip().split('\n') if line.strip()]

            if len(lines) < 3:  # Need header, separator, and at least one row
                return parsed

            # Extract headers from first line
            header_line = lines[0]
            headers = [h.strip() for h in header_line.split('|')[1:-1]]  # Skip empty start/end
            parsed['headers'] = headers

            # Skip separator line (line 1)
            # Parse data rows (lines 2+)
            for row_line in lines[2:]:
                cells = [c.strip() for c in row_line.split('|')[1:-1]]

                if len(cells) > 0:
                    # Create row dict
                    row_dict = {}
                    for i, header in enumerate(headers):
                        value = cells[i] if i < len(cells) else ''
                        row_dict[header] = value

                    parsed['rows'].append(row_dict)

            parsed['rows_count'] = len(parsed['rows'])
            logger.info(f"    Markdown table {table_index}: {parsed['rows_count']} rows")

        except Exception as e:
            logger.error(f"Error parsing markdown table {table_index}: {str(e)}")

        return parsed

    async def fetch_and_parse(self, url: str, table_name: str = None) -> Dict[str, Any]:
        """
        Fetch HTML from URL and parse tables in one call.

        Args:
            url: URL to fetch
            table_name: Optional table name for better identification

        Returns:
            Dictionary with:
            {
                'success': bool,
                'url': str,
                'html_fetched': bool,
                'tables': List[Dict],
                'tables_found': int,
                'pagination': Dict,
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'url': url,
            'html_fetched': False,
            'tables': [],
            'tables_found': 0,
            'pagination': {},
            'error': None
        }

        # Fetch HTML
        fetch_result = await self.fetch_html(url)

        if not fetch_result['success']:
            result['error'] = f"Failed to fetch HTML: {fetch_result['error']}"
            return result

        result['html_fetched'] = True
        html = fetch_result['html']

        # Parse tables
        parse_result = self.parse_html_tables(html, table_name)

        if parse_result['success']:
            result['success'] = True
            result['tables'] = parse_result['tables']
            result['tables_found'] = parse_result['tables_found']
        else:
            result['error'] = parse_result['error']

        # Detect pagination
        result['pagination'] = self.detect_pagination(html)

        return result
