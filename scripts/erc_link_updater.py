import sys
import argparse
import os
from atlassian import Confluence
from bs4 import BeautifulSoup
from urllib.parse import quote
import re
from difflib import SequenceMatcher
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Confluence connection details from environment variables
CONFLUENCE_URL = os.getenv('CONFLUENCE_URL')
USERNAME = os.getenv('CONFLUENCE_USERNAME')
API_TOKEN = os.getenv('CONFLUENCE_API_TOKEN')

# Space key
space_key = os.getenv('CONFLUENCE_SPACE')

def parse_arguments():
    parser = argparse.ArgumentParser(description="Update Confluence page links")
    parser.add_argument("source_page_id", help="ID of the source (data set page) Confluence page")
    parser.add_argument("target_page_id", help="ID of the target (report page) Confluence page")
    parser.add_argument("--reset", action="store_true", help="Reset hyperlinks to plain text")
    return parser.parse_args()

def reset_hyperlinks(source_content):
    soup = BeautifulSoup(source_content, 'html.parser')

    table = find_variables_table(soup)
    
    if not table:
        print("Table not found in source content")
        return source_content

    rows = table.find_all('tr')
    
    for row in rows[1:]:
        cells = row.find_all('td')
        if len(cells) >= 3:
            item_name = cells[2].get_text(strip=True)
            cells[2].clear()
            cells[2].append(item_name)
    return str(soup)

def get_page_url(confluence, page_id):
    page_info = confluence.get_page_by_id(page_id, expand='space')
    
    space_key = page_info['space']['key']
    page_title = page_info['title']
    
    encoded_title = quote(page_title.replace(' ', '+'))
    
    base_url = confluence.url.rstrip('/')
    page_url = f"{base_url}/display/{space_key}/{encoded_title}"
    
    return page_url

def find_heading_for_item_name(content, item_name, score_threshold=0.60):
    soup = BeautifulSoup(content, 'html.parser')
    headings = soup.find_all(['h1', 'h2'])
    print(item_name)
    
    def normalize(text):
        return re.sub(r'\s+', ' ', text.strip().lower())
    
    def similarity_ratio(a, b):
        return SequenceMatcher(None, a, b).ratio()
    
    def tokenize(text):
        return set(re.findall(r'\b\w+\b', text.lower()))
    
    normalized_item_name = normalize(item_name)
    item_tokens = tokenize(item_name)
    best_match = None
    best_score = 0
    
    for heading in headings:
        heading_text = heading.text.strip()
        normalized_heading = normalize(heading_text)
        
        # Check for exact match first
        if normalized_heading == normalized_item_name:
            return heading_text
        
        heading_tokens = tokenize(heading_text)
        
        # Calculate token overlap
        overlap = len(item_tokens.intersection(heading_tokens)) / len(item_tokens)
        
        # Calculate similarity ratio
        ratio = similarity_ratio(normalized_item_name, normalized_heading)
        
        # Combine scores (you can adjust the weights)
        score = (overlap * 0.6) + (ratio * 0.4)
        
        # Update best match if this is better
        if score > best_score:
            best_score = score
            best_match = heading_text
    
    if best_match and best_score >= score_threshold:
        return best_match
    else:
        print(f"No match found for '{item_name}' with score >= {score_threshold}")
        return None

def find_variables_table(soup):
    tables = soup.find_all('table')
    for table in tables:
        headers = table.find_all('th')
        if len(headers) >= 3:
            header_texts = [h.get_text(strip=True).lower() for h in headers]
            if ('utd-erc variable' in header_texts and 'item name' in header_texts) or ('Variables' in header_texts and 'item name' in header_texts):
                return table
    return None

def create_links_thecb(source_content, target_content, target_page_url):
    soup = BeautifulSoup(source_content, 'html.parser')

    table = find_variables_table(soup)
    
    if not table:
        print("Table not found in source content: " + target_page_url)
        print(source_content)
        return source_content

    rows = table.find_all('tr')
    
    for row in rows[1:]:
        cells = row.find_all('td')
        if len(cells) >= 3:
            item_name = cells[2].get_text(strip=True)
            heading = find_heading_for_item_name(target_content, item_name)
            
            if heading:
                encoded_heading = quote(heading.replace(' ', '-').replace('#', ''))               
                link = f'<a href="{target_page_url}#{encoded_heading}">{item_name}</a>'                
                cells[2].clear()
                cells[2].append(BeautifulSoup(link, 'html.parser'))
            else:
                # write the text string back -- to undo prior runs
                cells[2].clear()
                cells[2].append(item_name)

    return str(soup)

def create_links_sbec(source_content, target_content, target_page_url):
    soup = BeautifulSoup(source_content, 'html.parser')

    table = find_variables_table(soup)
    
    if not table:
        print("Table not found in source content: " + target_page_url)
        print(source_content)
        return source_content

    rows = table.find_all('tr')
    
    for row in rows[1:]:
        cells = row.find_all('td')
        if len(cells) >= 3:
            item_name = cells[1].get_text(strip=True)
            heading = find_heading_for_item_name(target_content, item_name)
            
            if heading:
                encoded_heading = quote(heading.replace(' ', '-').replace('#', ''))               
                link = f'<a href="{target_page_url}#{encoded_heading}">{item_name}</a>'                
                cells[1].clear()
                cells[1].append(BeautifulSoup(link, 'html.parser'))
            else:
                # write the text string back -- to undo prior runs
                cells[1].clear()
                cells[1].append(item_name)

    return str(soup)

def validate_page_titles(source_title, target_title):
    expected_target_title = source_title[len("Datasets: "):].strip()

    if target_title != expected_target_title:
        print(f"Warning: Page titles do not match the expected pattern.")
        print(f"Source title: {source_title}")
        print(f"Target title: {target_title}")
        print(f"Expected target title: {expected_target_title}")
        return False
    return True

def main():
    args = parse_arguments()

    # Check if environment variables are set
    if not all([CONFLUENCE_URL, USERNAME, API_TOKEN, space_key]):
        print("Error: Missing environment variables. Please check your .env file.")
        sys.exit(1)

    confluence = Confluence(
        url=CONFLUENCE_URL,
        username=USERNAME,
        password=API_TOKEN
    )

    source_page = confluence.get_page_by_id(args.source_page_id, expand='body.storage,version,space')
    target_page = confluence.get_page_by_id(args.target_page_id, expand='body.storage')

    # Validate page titles
    if not validate_page_titles(source_page['title'], target_page['title']):
        print("Operation aborted.")
        sys.exit(1)

    source_content = source_page['body']['storage']['value']
    
    if args.reset:
        updated_content = reset_hyperlinks(source_content)
        version_comment = "Reset hyperlinks to plain text"
    else:
        target_content = target_page['body']['storage']['value']
        target_page_url = get_page_url(confluence, args.target_page_id)
        updated_content = create_links_sbec(source_content, target_content, target_page_url)
        version_comment = "Updated links"

    # Update the page
    confluence.update_page(
        page_id=args.source_page_id,
        title=source_page['title'],
        body=updated_content,
        minor_edit=True,
        version_comment=version_comment,
        full_width=True )

    print(f"The page '{source_page['title']}' has been updated in Confluence.")

if __name__ == "__main__":
    main()