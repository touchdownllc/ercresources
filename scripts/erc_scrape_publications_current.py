from abc import ABC, abstractmethod
import logging
import requests
from bs4 import BeautifulSoup
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import re

@dataclass
class PageConfig:
    url: str
    title: str
    publishing_erc: str
    csv_file: str
    type: str = "Publication"  # Default type

class BaseERCScraper(ABC):
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

    def _clean_title(self, title: str) -> str:
        """Clean up publication title by removing trailing periods and extra whitespace."""
        if not title:
            return ""
        
        # Remove trailing periods, but keep periods that are part of abbreviations
        # e.g., "Ph.D." or "U.S." should keep their periods
        title = title.strip()
        while title.endswith('.'):
            title = title[:-1].strip()
            
        # Handle common abbreviations - add them back if removed
        common_abbrev = ['Ph.D', 'U.S', 'M.S', 'B.A', 'M.A', 'Ed.D']
        for abbrev in common_abbrev:
            if title.endswith(abbrev):
                title = title + '.'
                
        return title.strip()

    def _make_absolute_url(self, url: str) -> str:
        if not url:
            return ''
            
        # If it's already an absolute URL, return it
        if url.startswith(('http://', 'https://')):
            return url
            
        # If it ends with .pdf, it's likely a document that needs the full path
        if url.lower().endswith('.pdf'):
            # For University of Houston
            if 'uh.edu' in self.base_url:
                return f"https://uh.edu/education/research/institutes-centers/erc/reports-publications/{url}"
            # For UT Dallas
            elif 'utdallas.edu' in self.base_url:
                return f"https://tsp.utdallas.edu/publications/{url}"
            # For UT Austin
            elif 'utexas.edu' in self.base_url:
                return f"https://texaserc.utexas.edu/about-us/publications/{url}"
                
        # Default case: just append to base_url if it starts with /
        return f"{self.base_url}{url}" if url.startswith('/') else url

    def _make_absolute_url(self, url: str) -> str:
        if not url:
            return ''
        return f"{self.base_url}{url}" if url.startswith('/') else url

    def _extract_link(self, cell: BeautifulSoup) -> str:
        try:
            link = cell.find('a')
            if link and link.get('href'):
                return self._make_absolute_url(link.get('href'))
            return ''
        except Exception as e:
            logging.warning(f"Error extracting link: {e}")
            return ''

    def _split_title_authors(self, text: str) -> Tuple[str, str]:
        text = text.strip()
        
        # Look for "by" pattern
        pattern = r'(.*?)(?:\s+by\s+|\s+By\s+|\s+BY\s+)([^\.]+)(?:\..*)?$'
        match = re.search(pattern, text, re.IGNORECASE)
        
        if match:
            title = match.group(1).strip().rstrip('.')
            authors = match.group(2).strip().rstrip('.')
            return title, authors
            
        # Try citation format
        match = re.match(r'^([^\.]+?)\s*\((\d{4})\)\s*(.+?)(?:\s*\.\s*|$)', text)
        if match:
            authors = match.group(1).strip()
            title = match.group(3).strip()
            return title, authors
            
        # Default case
        return text.rstrip('.'), ''

    @abstractmethod
    def scrape_page(self, config: PageConfig) -> Optional[pd.DataFrame]:
        pass

class UTAustinScraper(BaseERCScraper):
    def _process_ut_austin_row(self, row: BeautifulSoup, is_policy_brief: bool) -> Optional[Dict]:
        try:
            cells = row.find_all('td')
            if not cells:
                return None

            result = {}
            
            if is_policy_brief:
                # Policy Brief format
                if len(cells) >= 5:
                    result["ERCProj #"] = cells[0].get_text(strip=True)
                    result["THECB #"] = cells[1].get_text(strip=True)
                    
                    # Process title/authors cell
                    title_cell = cells[2]
                    title_text = title_cell.get_text(strip=True)
                    link = title_cell.find('a')
                    if link and link.get('href'):
                        result["URL"] = self._make_absolute_url(link.get('href'))
                    
                    # Extract title and authors
                    result.update(self._extract_title_authors(title_text))
                    
                    result["Project Abbreviated Name"] = cells[3].get_text(strip=True)
                    result["Date"] = cells[4].get_text(strip=True)
            else:
                # Other publications format
                if len(cells) >= 2:
                    title_cell = cells[0]
                    title_text = title_cell.get_text(strip=True)
                    link = title_cell.find('a')
                    if link and link.get('href'):
                        result["URL"] = self._make_absolute_url(link.get('href'))
                    
                    # Extract title and authors
                    result.update(self._extract_title_authors(title_text))
                    result["Year"] = cells[1].get_text(strip=True)

            return result if result.get("Title") else None

        except Exception as e:
            logging.warning(f"Error processing UT Austin row: {e}")
            return None
    
    def _extract_title_authors(self, text: str) -> Dict[str, str]:
        """Extract title and authors from combined text."""
        text = text.strip()
        result = {"Title": text, "Authors": ""}
        
        # Try different variations of "by"
        for separator in ["by", "By", "BY"]:
            if separator in text:
                parts = text.rsplit(separator, 1)
                if len(parts) == 2:
                    title = self._clean_title(parts[0].strip())  # Clean the title
                    authors = parts[1].strip().strip('.: ')
                    # Handle all-caps titles
                    if title.isupper():
                        title = title.title()
                    result["Title"] = title
                    result["Authors"] = authors
                    break
        
        # Always clean the title, even if no "by" separator was found
        result["Title"] = self._clean_title(result["Title"])
        
        return result

    def scrape_page(self, config: PageConfig) -> Optional[pd.DataFrame]:
        try:
            response = requests.get(config.url, headers=self.headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            all_rows = []
            table = soup.find('table', id='tablepress-20') or soup.find('table', id='tablepress-21')
            
            if table:
                tbody = table.find('tbody')
                if tbody:
                    for tr in tbody.find_all('tr'):
                        row_data = self._process_ut_austin_row(tr, 'tablepress-20' in str(table))
                        if row_data:
                            row_data['Type'] = config.type
                            all_rows.append(row_data)

            if not all_rows:
                return None

            df = pd.DataFrame(all_rows)
            df['Publishing ERC'] = config.publishing_erc
            df['Source URL'] = config.url
            return df

        except Exception as e:
            logging.error(f"Error scraping content from {config.url}: {e}")
            return None

class UTDallasScraper(BaseERCScraper):
    def scrape_page(self, config: PageConfig) -> Optional[pd.DataFrame]:
        try:
            response = requests.get(config.url, headers=self.headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            content_well = soup.find('main', {'class': 'site-main'})
            if not content_well:
                content_well = soup
                
            all_rows = []
            
            if 'research-areas' in config.url:
                # Process by sections for research areas
                headings = content_well.find_all('h2')
                for heading in headings:
                    section_rows = self._process_section(heading, config.type)
                    if section_rows:
                        all_rows.extend(section_rows)
            else:
                # Process paragraphs for published work and working papers
                paragraphs = content_well.find_all('p')
                for para in paragraphs:
                    if not para.get_text(strip=True) or para.find_parent('nav'):
                        continue
                    # Skip "To the top" links
                    if "To the top" in para.get_text():
                        continue
                    row_data = self._process_content(para, config.type, "General")
                    if row_data:
                        all_rows.append(row_data)

            if not all_rows:
                return None

            df = pd.DataFrame(all_rows)
            df['Publishing ERC'] = config.publishing_erc
            df['Source URL'] = config.url
            return df

        except Exception as e:
            logging.error(f"Error scraping content from {config.url}: {e}")
            return None

    def _process_section(self, heading: BeautifulSoup, pub_type: str) -> List[Dict]:
        results = []
        section_title = heading.get_text(strip=True)
        
        next_element = heading.find_next_sibling()
        while next_element and next_element.name != 'h2':
            if next_element.name == 'ul':
                for li in next_element.find_all('li', recursive=False):
                    entry = self._process_content(li, pub_type, section_title)
                    if entry:
                        results.append(entry)
            elif next_element.name == 'p' and next_element.get_text(strip=True):
                entry = self._process_content(next_element, pub_type, section_title)
                if entry:
                    results.append(entry)
            next_element = next_element.find_next_sibling()
            
        return results

    def _process_content(self, element: BeautifulSoup, pub_type: str, section_title: str) -> Optional[Dict]:
        try:
            text = element.get_text(strip=True)
            if not text or "To the top" in text:
                return None

            result = {
                'Type': pub_type,
                'Research Area': section_title,
                'URL': '',
                'Year': '',
                'Title': '',
                'Authors': ''
            }

            # Extract URL if present
            link = element.find('a')
            if link and link.get('href'):
                result['URL'] = self._make_absolute_url(link.get('href'))

            # Clean up text
            text = self._clean_special_chars(text)
            text = text.replace('..', '.').replace('()', '').strip()
            text = re.sub(r'\.+', '.', text)
            text = re.sub(r'\s+', ' ', text)

            # Pattern 1: NBER working paper format
            nber_pattern = r'^([^,]+),\s*([^\.]+?)\.\s*(?:\d{4}\.)?\s*["\u201c\u201d]([^"]+)["\u201c\u201d].*?(?:NBER working paper|$)'
            match = re.match(nber_pattern, text)
            if match:
                main_author = match.group(1).strip()
                other_authors = match.group(2).strip()
                # Clean up authors list
                if other_authors.startswith('and '):
                    other_authors = other_authors[4:]
                authors = [main_author]
                if other_authors:
                    more_authors = re.split(r',\s*(?:and\s+)?|\s+and\s+', other_authors)
                    authors.extend([a.strip() for a in more_authors if a.strip()])
                result['Authors'] = ', '.join(authors)
                result['Title'] = match.group(3).strip()
                # Extract year from text
                year_match = re.search(r'\b(19|20)\d{2}\b', text)
                if year_match:
                    result['Year'] = year_match.group(0)
                return result

            # Pattern 2: Journal article with embedded authors
            journal_match = re.match(r'^([^\.]+)\.\s*(?:\d{4}\.)?\s*["\u201c\u201d]([^"]+)["\u201c\u201d].*?(?:[A-Za-z\s]+,\s*\d+\(\d+\))', text)
            if journal_match:
                result['Authors'] = journal_match.group(1).strip()
                result['Title'] = journal_match.group(2).strip()
                # Extract year if present
                year_match = re.search(r'\b(19|20)\d{2}\b', text)
                if year_match:
                    result['Year'] = year_match.group(0)
                return result

            # Pattern 3: Journal reference only (look for volume/issue pattern)
            journal_only = re.match(r'^([^,]+),\s*(\d+)\((\d+)\)', text)
            if journal_only:
                # This is just journal info, try to find title in previous entries
                return None

            # Pattern 4: Standard academic format
            academic_pattern = r'^([^\.]+)\.\s*(?:\d{4}\.)?\s*["\u201c\u201d]([^"]+)["\u201c\u201d]'
            match = re.match(academic_pattern, text)
            if match:
                result['Authors'] = match.group(1).strip()
                result['Title'] = match.group(2).strip()
                # Extract year if present
                year_match = re.search(r'\b(19|20)\d{2}\b', text)
                if year_match:
                    result['Year'] = year_match.group(0)
                return result

            # Pattern 5: "In Progress" papers
            if 'In Progress' in text:
                match = re.match(r'^([^\.]+)\.\s*In Progress\.\s*["\u201c\u201d]?([^"]+)["\u201c\u201d]?', text)
                if match:
                    result['Authors'] = match.group(1).strip()
                    result['Title'] = match.group(2).strip()
                    result['Year'] = 'In Progress'
                    return result

            # Pattern 6: Author list cleanup (fix reversed author order)
            author_pattern = r'^([^,]+),\s*([^\.]+?)\s*\.'
            match = re.match(author_pattern, text)
            if match:
                first_part = match.group(1).strip()
                second_part = match.group(2).strip()
                if ',' in second_part:  # Likely a list of additional authors
                    result['Authors'] = f"{first_part}, {second_part}"
                else:  # Might be reversed name order
                    result['Authors'] = f"{second_part} {first_part}"
                    
            # Extract any year present
            year_match = re.search(r'\b(19|20)\d{2}\b', text)
            if year_match:
                result['Year'] = year_match.group(0)

            # If we haven't found a title yet, look for quoted text
            if not result['Title']:
                title_match = re.search(r'["\u201c\u201d]([^"]+)["\u201c\u201d]', text)
                if title_match:
                    result['Title'] = title_match.group(1).strip()

            # If we still don't have a title, use the remaining text
            if not result['Title']:
                # Remove any identified parts (authors, year) and use what's left
                cleaned_text = text
                if result['Authors']:
                    cleaned_text = cleaned_text.replace(result['Authors'], '')
                if result['Year']:
                    cleaned_text = cleaned_text.replace(result['Year'], '')
                cleaned_text = cleaned_text.strip(' .,')
                if cleaned_text:
                    result['Title'] = cleaned_text

            # Clean the title before returning
            if result['Title']:
                result['Title'] = self._clean_title(result['Title'])

            return result if (result['Title'] or result['Authors']) else None

        except Exception as e:
            logging.warning(f"Error processing UTD content: {e}")
            return None

    def _clean_special_chars(self, text: str) -> str:
        replacements = {
            'È': 'e',
            '¸': 'u',
            'é': 'e',
            'í': 'i',
            'ó': 'o',
            'ñ': 'n',
            '"': '"',
            '"': '"',
            ''': "'",
            ''': "'",
            '\u201c': '"',
            '\u201d': '"',
            '‚Äì': '-',
            '‚Äî': '-',
            '‚Äú': '"',
            '‚Äù': '"',
            '\u2013': '-',
            '\u2014': '-',
            'ì': 'i',
            'î': '-',
            'i': 'i'
        }
        text = text.strip()
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

class UHoustonScraper(BaseERCScraper):
    def scrape_page(self, config: PageConfig) -> Optional[pd.DataFrame]:
        try:
            response = requests.get(config.url, headers=self.headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            content_well = soup.find('section', id='content-well')
            if not content_well:
                content_well = soup
                
            all_rows = []
            
            if 'policy-briefs' in config.url:
                table = content_well.find('table')
                if table:
                    rows = self._process_uh_table(table)
                    all_rows.extend(rows)
            else:
                # Existing publication processing logic remains the same
                sections = content_well.find_all('h2')
                for heading in sections:
                    section_rows = self._process_uh_sections(heading)
                    if section_rows:
                        all_rows.extend(section_rows)

            if not all_rows:
                return None

            df = pd.DataFrame(all_rows)
            df['Publishing ERC'] = config.publishing_erc
            df['Source URL'] = config.url
            return df

        except Exception as e:
            logging.error(f"Error scraping content from {config.url}: {e}")
            return None

    def _process_uh_table(self, table: BeautifulSoup) -> List[Dict]:
        results = []
        rows = table.find_all('tr')
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                text = cells[1].get_text(strip=True)
                if not text or text == 'Policy Brief':
                    continue
                    
                url = self._extract_link(cells[1])
                text = re.sub(r'https?://[^\s]+(?=\s|$)', '', text)
                text = re.sub(r'\s+', ' ', text).strip()
                
                proj_num = cells[0].get_text(strip=True) if cells[0] else ''
                
                parts = text.split('.', 1)
                title = self._clean_title(parts[0]) if parts else text
                rest = parts[1].strip() if len(parts) > 1 else ''
                
                # Process authors and institution
                authors = ''
                institution = ''
                year = ''
                
                if rest:
                    # Split on institution identifier
                    auth_parts = re.split(r'\s+[-–]\s+(?:Rice|University|Urban|Texas)', rest)
                    if len(auth_parts) > 0:
                        authors = auth_parts[0].strip()
                        # Get institution from the rest
                        if len(auth_parts) > 1:
                            institution = 'Rice University' if 'Rice' in rest else \
                                        'Urban Institute' if 'Urban' in rest else \
                                        'University of Houston' if 'University of Houston' in rest else \
                                        'Texas State University' if 'Texas State' in rest else \
                                        ''
                
                # Extract year if present
                year_match = re.search(r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})', text)
                if year_match:
                    year = year_match.group(1)
                    # Remove month/year from title
                    title = re.sub(r',\s*(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}', '', title)
                
                # Clean up authors
                if authors:
                    # Fix spacing around periods in initials
                    authors = re.sub(r'(?<=\w)\.(?=\w)', '. ', authors)
                    # Fix spacing after commas
                    authors = re.sub(r',(\S)', ', \1', authors)
                    # Remove any trailing periods
                    authors = authors.strip('.')
                    # Fix "and" spacing
                    authors = re.sub(r'\s+and\s+', ' and ', authors)
                    # Clean up multiple spaces
                    authors = re.sub(r'\s+', ' ', authors).strip()

                result = {
                    'Project Number': proj_num,
                    'Title': title,  # Already cleaned above
                    'URL': url,
                    'Authors': authors,
                    'Year': year,
                    'Institution': institution,
                    'Type': 'Policy Brief'
                }
                
                # Special case fix for UH015
                if proj_num == 'UH015':
                    result['Title'] = "The Texas Top Ten Percent Plan's Effect on Historically Marginalized Students Attaining Professional School Degrees"
                    result['Authors'] = "Toni Templeton, Chaunté White, and Catherine L Horn"
                    result['Institution'] = "University of Houston"

                if result['Title']:
                    results.append(result)
                    
        return results

    def _process_uh_sections(self, heading: BeautifulSoup) -> List[Dict]:
        results = []
        section_title = heading.get_text(strip=True)
        
        next_element = heading.find_next_sibling()
        while next_element and next_element.name != 'h2':
            if next_element.name == 'ul':
                for li in next_element.find_all('li', recursive=False):
                    entry = self._process_uh_publication(li, section_title)
                    if entry:
                        original_text = entry.pop('_original_text', '')
                        supp_docs = self._process_uh_supplemental(li)
                        entry.update(supp_docs)
                        results.append(entry)
            elif next_element.name == 'p' and next_element.get_text(strip=True):
                entry = self._process_uh_publication(next_element, section_title)
                if entry:
                    results.append(entry)
                        
            next_element = next_element.find_next_sibling()
                
        return results

    def _process_uh_publication(self, element: BeautifulSoup, section_title: str) -> Optional[Dict]:
        try:
            text = element.get_text(strip=True)
            if not text:
                return None

            result = {
                'Research Area': section_title,
                'Type': 'Publication',
                'Is Supporting Document': False
            }

            # Extract URL - First try to find an anchor tag
            link = element.find('a')
            if link and link.get('href'):
                result['URL'] = self._make_absolute_url(link.get('href'))
            else:
                # If no anchor tag, look for PDF references in the text
                pdf_match = re.search(r'(?:https?://[^\s]+\.pdf|[^"\s]+\.pdf)', text)
                if pdf_match:
                    result['URL'] = self._make_absolute_url(pdf_match.group(0))

            # Handle specific known publications that need exact formats
            known_pubs = {
                "Lacking Accountability and Effectiveness Measures": {
                    'Authors': "Mairaj, Fiza",
                    'Title': "Lacking Accountability and Effectiveness Measures: Exploring the Implementation of Mentoring Programs for Refugee Youth",
                    'Year': "2024"
                },
                "Colorado": {
                    'Authors': "Templeton, T",
                    'Title': "Colorado",
                    'Year': "2024"
                },
                "From Theory to Practice": {
                    'Authors': "Sands, S. and Maira, F.",
                    'Title': "From Theory to Practice: Introducing Logic Models for Evaluating PMMs",
                    'Year': "2024"
                },
                "Feast or Famine": {
                    'Authors': "Templeton, T., Selsberg, B., Abdelmalak, M., & Abdelhamid, M.",
                    'Title': "Feast or Famine: Inequity within the Texas School Finance System",
                    'Year': "2023"
                },
                "The Far Reach": {
                    'Authors': "Templeton, T., White, C.L., & Horn, C.L.",
                    'Title': "The Far Reach of the Texas Top Ten Percent Plan: Consideration of Professional School Degrees",
                    'Year': "2023"
                },
                "Understanding the role": {
                    'Authors': "Mairaj, F. and Callahan, R.M.",
                    'Title': "Understanding the role of the hollow state in educating refugees: A review of the literature",
                    'Year': "2022"
                },
                "Review of Texas Educator": {
                    'Authors': "Templeton, T. & Horn, C.L.",
                    'Title': "A Review of Texas Educator Preparation Program Policy",
                    'Year': "2020"
                },
                "Contracting for Success": {
                    'Authors': "Sands, S.R., & Mairaj, F.",
                    'Title': "Contracting for Success? The Evolution of Governance in Texas Portfolio School Districts",
                    'Year': "2024"
                },
                "QuantCrit Analysis": {
                    'Authors': "Templeton, T., White, C.L., Peters, A.L., & Horn, C.L.",
                    'Title': "A QuantCrit Analysis of the Black Teacher to Principal Pipeline",
                    'Year': "2021"
                },
                "STEM Teachers": {
                    'Authors': "Templeton, T., White, C.L., Tran, M., Lowrey, S.L., & Horn, C.L.",
                    'Title': "STEM Teachers in Highest-Need Schools: An Analysis of the Effects of the Robert Noyce Teacher Scholarship Program on STEM Teacher Placement and Retention",
                    'Year': "2021"
                }
            }

            # Check for known publications first
            for key, pub in known_pubs.items():
                if key in text:
                    result.update(pub)
                    return result

            # For reports section, handle differently
            if 'Reports' in section_title:
                title = text
                if 'Charter Authorizer' in text:
                    year_match = re.search(r'(\d{4})-(\d{4})', text)
                    result['Year'] = year_match.group(2) if year_match else ''
                    title = re.sub(r'(?:Appendix [A-Z]|Executive Summary).*$', '', title)
                elif 'Teacher Workforce' in text:
                    year_match = re.search(r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})', text)
                    result['Year'] = year_match.group(1) if year_match else ''
                
                result['Title'] = title.strip(' ."')
                return result

            # Standard processing for other entries
            year_match = re.search(r'\((\d{4})\)', text)
            if year_match:
                result['Year'] = year_match.group(1)
                text = text.replace(f"({year_match.group(1)})", "")

            # Try to split authors and title
            if '. ' in text:
                authors, rest = text.split('. ', 1)
                if ',' in authors or '&' in authors:
                    result['Authors'] = authors.strip()
                    result['Title'] = rest.strip(' ."')
                else:
                    result['Title'] = text.strip(' ."')
            else:
                result['Title'] = text.strip(' ."')

            return result

        except Exception as e:
            logging.warning(f"Error processing UH publication: {e}")
            return None

    def _preprocess_text(self, text: str) -> str:
        """Clean and standardize text before processing."""
        # Remove multiple spaces
        text = re.sub(r'\s+', ' ', text)
        # Fix common issues
        text = text.replace('.,', '.')
        text = text.replace('..', '.')
        text = text.replace(':"', ': "')
        # Remove trailing periods and spaces
        text = text.strip(' .')
        return text

    def _clean_title(self, title: str) -> str:
        """Clean up publication title."""
        # Remove various suffixes
        patterns = [
            r'Executive\s*Summary$',
            r'Appendix\s+[A-Z]$',
            r',\s*(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}$',
            r'\s*\(\d{4}\)$',
            r'(?:Vol\.|Volume)\s*\d+.*$',
            r'Manuscript submitted for publication$'
        ]
        
        for pattern in patterns:
            title = re.sub(pattern, '', title)
        
        return title.strip(' ".')

    def _clean_authors(self, authors: str) -> str:
        """Clean up author names."""
        # Remove any trailing periods
        authors = authors.rstrip('.')
        # Standardize separators
        authors = re.sub(r'\s+and\s+', ' & ', authors)
        authors = re.sub(r'\s*,\s*', ', ', authors)
        # Remove extra spaces around ampersands
        authors = re.sub(r'\s*&\s*', ' & ', authors)
        return authors.strip()

    def _process_report(self, text: str, result: Dict) -> Dict:
        """Handle reports like Charter Authorizer reports."""
        # Extract year if present
        year_match = re.search(r'(\d{4})-(\d{4})|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})', text)
        if year_match:
            year = year_match.group(3) if year_match.group(3) else year_match.group(1)
            result['Year'] = year
        
        # Clean up title
        title = re.sub(r'(?:Appendix [A-Z]|Executive Summary).*$', '', text)
        title = title.replace('TexasCharter', 'Texas Charter')
        result['Title'] = title.strip()
        
        return result

    def _check_known_problematic_entries(self, text: str) -> Optional[Dict]:
        """Handle known problematic entries with specific fixes."""
        known_entries = {
            "Lacking Accountability and Effectiveness Measures": {
                'Authors': "Mairaj, Fiza",
                'Title': "Lacking Accountability and Effectiveness Measures: Exploring the Implementation of Mentoring Programs for Refugee Youth",
                'Year': "2024",
                'Type': "Publication",
                'URL': "https://doi.org/10.3390/socsci13110586"
            },
            "Feast or Famine": {
                'Authors': "Templeton, T., Selsberg, B., Abdelmalak, M., & Abdelhamid, M.",
                'Title': "Feast or Famine: Inequity within the Texas School Finance System",
                'Year': "2023",
                'Type': "Publication"
            },
            "The Far Reach of the Texas Top Ten Percent Plan": {
                'Authors': "Templeton, T., White, C.L., & Horn, C.L.",
                'Title': "The Far Reach of the Texas Top Ten Percent Plan: Consideration of Professional School Degrees",
                'Year': "2023",
                'Type': "Publication",
                'URL': "https://doi.org/10.1080/00221546.2023.2171216"
            },
            "Understanding the role of the hollow state": {
                'Authors': "Mairaj, F. and Callahan, R.M.",
                'Title': "Understanding the role of the hollow state in educating refugees: A review of the literature",
                'Year': "2022",
                'Type': "Publication"
            },
            "Review of Texas Educator Preparation Program Policy": {
                'Authors': "Templeton, T. & Horn, C.L.",
                'Title': "A Review of Texas Educator Preparation Program Policy",
                'Year': "2020",
                'Type': "Publication"
            }
        }

        # Check if any of the known entries are in the text
        for key, entry in known_entries.items():
            if key in text:
                result = entry.copy()
                result['Is Supporting Document'] = False
                return result

        return None

    def _process_uh_supplemental(self, li_element: BeautifulSoup) -> Dict:
        supp_info = {}
        nested_ul = li_element.find('ul')
        
        if nested_ul:
            for i, supp_li in enumerate(nested_ul.find_all('li', recursive=False), 1):
                if i > 2:  # Only process up to 2 supplemental items
                    break
                    
                supp_link = supp_li.find('a')
                supp_em = supp_li.find('em')
                
                if supp_em:
                    supp_title = supp_em.get_text(strip=True)
                elif supp_link:
                    supp_title = supp_link.get_text(strip=True)
                else:
                    supp_title = supp_li.get_text(strip=True)
                
                # Handle both href and text content as potential URLs
                url_text = ''
                if supp_link and supp_link.get('href'):
                    url_text = supp_link.get('href')
                else:
                    # Look for potential file references in the text
                    text_content = supp_li.get_text(strip=True)
                    url_match = re.search(r'(?:https?://\S+|\S+\.(?:pdf|doc|docx|xls|xlsx))', text_content)
                    if url_match:
                        url_text = url_match.group(0)
                
                # Always make URLs absolute
                supp_url = self._make_absolute_url(url_text) if url_text else ''
                
                supp_info[f'supp{i}_Title'] = supp_title.strip(' .')
                supp_info[f'supp{i}_URL'] = supp_url

        # Ensure both supplemental entries exist
        for i in range(1, 3):
            if f'supp{i}_Title' not in supp_info:
                supp_info[f'supp{i}_Title'] = ''
                supp_info[f'supp{i}_URL'] = ''
                
        return supp_info

def get_scraper(erc_name: str) -> BaseERCScraper:
    scrapers = {
        'UT Austin': UTAustinScraper('https://texaserc.utexas.edu'),
        'UT Dallas': UTDallasScraper('https://tsp.utdallas.edu'),
        'University of Houston': UHoustonScraper('https://uh.edu')
    }
    return scrapers.get(erc_name)

def clean_publications_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean the publications DataFrame."""
    # Drop rows that are navigation links
    nav_patterns = [
        'history-and-background',
        'proposal-preparation-and-submission',
        'for-researchers-of-approved-projects',
        'data-warehouse',
        'index.php',
        'project-policy-briefs',
        'faculty-staff'
    ]
    
    keep_mask = ~df['URL'].str.contains('|'.join(nav_patterns), case=False, na=False)
    cleaned_df = df[keep_mask].copy()
    
    # Fill NaN values
    cleaned_df['Title'] = cleaned_df['Title'].fillna('')
    cleaned_df['Authors'] = cleaned_df['Authors'].fillna('')
    
    # Clean up titles and remove empty rows
    cleaned_df['Title'] = cleaned_df['Title'].str.strip()
    cleaned_df = cleaned_df[cleaned_df['Title'].str.strip() != '']
    
    # Convert empty strings to NA
    replace_dict = {col: {'': pd.NA} for col in cleaned_df.columns if cleaned_df[col].dtype == 'object'}
    cleaned_df = cleaned_df.replace(replace_dict)
    
    # Ensure proper data types
    cleaned_df = cleaned_df.infer_objects()
    
    return cleaned_df

def main():
    logging.basicConfig(level=logging.INFO)
    
    configs = [
        # UT Austin
        PageConfig(
            url="https://texaserc.utexas.edu/about-us/publications/policy-briefs/",
            title="UT Austin ERC - Policy Briefs",
            publishing_erc="UT Austin",
            csv_file="ut_austin_policy_briefs.csv",
            type="Policy Brief"
        ),
        PageConfig(
            url="https://texaserc.utexas.edu/about-us/publications/other-publications/",
            title="UT Austin ERC - Other Publications",
            publishing_erc="UT Austin",
            csv_file="ut_austin_other_publications.csv",
            type="Publication"
        ),
        # UT Dallas
        PageConfig(
            url="https://tsp.utdallas.edu/publications/research-areas/",
            title="UTD TSP - Research Areas",
            publishing_erc="UT Dallas",
            csv_file="ut_dallas_research_areas.csv",
            type="Research Publication"
        ),
        PageConfig(
            url="https://tsp.utdallas.edu/publications/published-work/",
            title="UTD TSP - Published Work",
            publishing_erc="UT Dallas",
            csv_file="ut_dallas_published_work.csv",
            type="Published Work"
        ),
        PageConfig(
            url="https://tsp.utdallas.edu/publications/working-papers/",
            title="UTD TSP - Working Papers",
            publishing_erc="UT Dallas",
            csv_file="ut_dallas_working_papers.csv",
            type="Working Paper"
        ),
        # UH
        PageConfig(
            url="https://uh.edu/education/research/institutes-centers/erc/project-policy-briefs/",
            title="UH ERC - Project Policy Briefs",
            publishing_erc="University of Houston",
            csv_file="u_houston_project_policy_briefs.csv",
            type="Policy Brief"
        ),
        PageConfig(
            url="https://uh.edu/education/research/institutes-centers/erc/reports-publications/",
            title="UH ERC - Reports and Publications",
            publishing_erc="University of Houston",
            csv_file="u_houston_reports_publications.csv",
            type="Publication"
        )
    ]
    
    all_data = []
    all_columns = set()
    
    for config in configs:
        scraper = get_scraper(config.publishing_erc)
        if scraper:
            logging.info(f"Scraping data from {config.url}")
            df = scraper.scrape_page(config)
            if df is not None:
                # Track all columns
                all_columns.update(df.columns)
                
                all_data.append(df)
                logging.info(f"Successfully scraped {len(df)} rows from {config.url}")
                # Save individual file for debugging
                df.to_csv(config.csv_file, index=False)
                logging.info(f"Saved data to {config.csv_file}")
            else:
                logging.warning(f"No data scraped from {config.url}")
        else:
            logging.error(f"No scraper found for {config.publishing_erc}")

    if all_data:
        # Ensure all DataFrames have the same columns
        for df in all_data:
            for col in all_columns:
                if col not in df.columns:
                    df[col] = ''
        
        # Concatenate with all columns
        merged_df = pd.concat(all_data, ignore_index=True)
        
        # Clean up the data
        merged_df = clean_publications_data(merged_df)
        
        # Remove duplicates
        merged_df = merged_df.drop_duplicates(subset=['Title', 'Authors', 'URL'], keep='first')
        
        # Ensure consistent column order
        desired_columns = [
            'Title', 'Authors', 'Year', 'URL', 'Research Area', 'Type', 
            'Is Supporting Document', 'Publishing ERC', 'Source URL',
            'supp1_Title', 'supp1_URL', 'supp2_Title', 'supp2_URL'
        ]
        
        # Include only existing columns
        final_columns = [col for col in desired_columns if col in merged_df.columns]
        # Add any additional columns
        final_columns.extend(col for col in merged_df.columns if col not in desired_columns)
        
        merged_df = merged_df[final_columns]
        
        # Save final output
        merged_df.to_csv("erc_publications.csv", index=False)
        logging.info(f"Saved {len(merged_df)} rows to erc_publications.csv")
    else:
        logging.error("No data was scraped from any source")

if __name__ == "__main__":
    main()
                                       
