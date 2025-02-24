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
        print
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

def find_heading_for_item_name(content, item_name, score_threshold=0.45):
    """
    Find a heading in the content that matches the item name.
    
    Args:
        content: HTML content to search in
        item_name: Name of the item to find a heading for
        score_threshold: Minimum score to consider a match
        
    Returns:
        The matching heading text, or None if no match found
    """
    soup = BeautifulSoup(content, 'html.parser')
    headings = soup.find_all(['h1', 'h2', 'h3'])  # Include h3 headings too
    print(f"Looking for heading matching '{item_name}'")
    
    def normalize(text):
        """Normalize text for comparison by removing extra spaces and converting to lowercase."""
        return re.sub(r'\s+', ' ', text.strip().lower())
    
    def similarity_ratio(a, b):
        """Calculate string similarity ratio using SequenceMatcher."""
        return SequenceMatcher(None, a, b).ratio()
    
    def tokenize(text):
        """Tokenize text into words, removing non-alphanumeric characters."""
        return set(re.findall(r'\b\w+\b', text.lower()))
    
    normalized_item_name = normalize(item_name)
    
    # Check for exact matches in headings first (case-insensitive)
    for heading in headings:
        heading_text = heading.get_text().strip()
        normalized_heading = normalize(heading_text)
        
        # If item name appears exactly in the heading
        if normalized_item_name in normalized_heading:
            return heading_text
    
    # Look for E-number patterns (like E0123) that might match
    e_number_match = re.search(r'E\d+', item_name)
    if e_number_match:
        e_number = e_number_match.group(0)
        for heading in headings:
            heading_text = heading.get_text().strip()
            if e_number in heading_text:
                return heading_text
    
    # For variables with underscores, try matching individual parts
    if '_' in item_name:
        parts = item_name.split('_')
        for heading in headings:
            heading_text = heading.get_text().strip()
            normalized_heading = normalize(heading_text)
            # If any significant part appears in the heading
            for part in parts:
                if len(part) >= 4 and normalize(part) in normalized_heading:
                    return heading_text
    
    # Tokenize the item name for more sophisticated matching
    item_tokens = tokenize(item_name)
    
    # If no tokens (very short or only symbols), skip token-based matching
    if not item_tokens:
        return None
    
    best_match = None
    best_score = 0
    
    for heading in headings:
        heading_text = heading.get_text().strip()
        normalized_heading = normalize(heading_text)
        
        # Skip extremely short headings as they're likely not what we want
        if len(normalized_heading) < 5:
            continue
            
        heading_tokens = tokenize(heading_text)
        
        # Skip if no tokens in heading
        if not heading_tokens:
            continue
        
        # Calculate token overlap (how many item tokens appear in heading)
        if len(item_tokens) > 0:
            overlap = len(item_tokens.intersection(heading_tokens)) / len(item_tokens)
        else:
            overlap = 0
        
        # Calculate similarity ratio
        ratio = similarity_ratio(normalized_item_name, normalized_heading)
        
        # Special bonus for headings that contain the full item name
        contains_bonus = 0.3 if normalized_item_name in normalized_heading else 0
        
        # Combine scores with weighted approach
        score = (overlap * 0.4) + (ratio * 0.4) + contains_bonus
        
        # Update best match if this is better
        if score > best_score:
            best_score = score
            best_match = heading_text
    
    if best_match and best_score >= score_threshold:
        print(f"Found match: '{best_match}' with score {best_score:.2f}")
        return best_match
    else:
        print(f"No match found for '{item_name}' with score >= {score_threshold}")
        return None

def find_variables_table(soup):
    """
    Find the table that contains variable information in a Confluence page.
    Uses multiple detection methods to be more robust.
    
    Args:
        soup: BeautifulSoup object of the page content
        
    Returns:
        The table element, or None if not found
    """
    # Method 1: Look for tables with specific header text
    tables = soup.find_all('table')
    for table in tables:
        headers = table.find_all('th')
        if len(headers) >= 3:
            header_texts = [h.get_text(strip=True).lower() for h in headers]
            
            # Check for known variable table headers
            if (('erc variable' in header_texts and 'item name' in header_texts) or 
                ('utd-erc variable' in header_texts) or
                ('variables' in header_texts)):
                print(f"Found variables table with headers: {header_texts}")
                return table
    
    # Method 2: Look for tables under a Variables heading
    variables_heading = None
    for heading in soup.find_all(['h1', 'h2']):
        if heading.get_text(strip=True).lower() == 'variables':
            variables_heading = heading
            break
    
    if variables_heading:
        # Find the next table after the Variables heading
        next_element = variables_heading.next_sibling
        while next_element:
            if next_element.name == 'table':
                print("Found table after 'Variables' heading")
                return next_element
            next_element = next_element.next_sibling
    
    # Method 3: Try to find the largest table that might contain variables
    tables = soup.find_all('table')
    if tables:
        # Sort tables by number of rows
        tables_by_size = sorted(tables, key=lambda t: len(t.find_all('tr')), reverse=True)
        
        # Check if the largest table has variable-like headers
        largest_table = tables_by_size[0]
        headers = largest_table.find_all('th')
        if len(headers) >= 3:
            header_texts = [h.get_text(strip=True).lower() for h in headers]
            print(f"Using largest table with headers: {header_texts}")
            
            # Print the first row of data for debugging
            first_data_row = largest_table.find_all('tr')[1] if len(largest_table.find_all('tr')) > 1 else None
            if first_data_row:
                cells = first_data_row.find_all(['td', 'th'])
                cell_texts = [c.get_text(strip=True) for c in cells]
                print(f"First data row: {cell_texts}")
            
            return largest_table
    
    # Try to dump the HTML for debugging
    try:
        print("No suitable table found. Page structure:")
        tables = soup.find_all('table')
        print(f"Found {len(tables)} tables on the page")
        
        for i, table in enumerate(tables):
            headers = table.find_all('th')
            print(f"Table {i+1} has {len(headers)} header cells and {len(table.find_all('tr'))} rows")
            if headers:
                header_texts = [h.get_text(strip=True) for h in headers]
                print(f"  Headers: {header_texts[:5]}...")
    except Exception as e:
        print(f"Error during debug dump: {e}")
    
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

def create_links_tea(source_content, target_content, target_page_url):
    """
    Create links from ERC variables in the source page to corresponding
    headings in the target page. Also adds the matched heading to the table.
    If the 'Item name' column doesn't exist, it will be created.
    
    Args:
        source_content: HTML content of the source page
        target_content: HTML content of the target page
        target_page_url: URL of the target page
        
    Returns:
        Updated HTML content of the source page
    """
    soup = BeautifulSoup(source_content, 'html.parser')

    table = find_variables_table(soup)
    
    if not table:
        print("Table not found in source content: " + target_page_url)
        return source_content

    # Check table headers
    header_row = table.find('tr')
    headers = header_row.find_all('th')
    header_texts = [th.get_text(strip=True).lower() for th in headers]
    print(f"Headers in order: {header_texts}")
    
    # Look for the Item name column
    item_name_col_index = None
    for i, header_text in enumerate(header_texts):
        if "item name" in header_text:
            item_name_col_index = i
            print(f"Found 'Item name' at index {i}")
            break
    
    # If Item name column doesn't exist, create it after the UTD-ERC Variable column
    if item_name_col_index is None:
        print("'Item name' column not found, creating it")
        
        # Find the UTD-ERC Variable column (usually the second column)
        utd_erc_col_index = None
        for i, header_text in enumerate(header_texts):
            if "utd-erc" in header_text or "utd erc" in header_text:
                utd_erc_col_index = i
                print(f"Found 'UTD-ERC Variable' at index {i}")
                break
        
        # Default to adding after the second column if UTD-ERC not found
        if utd_erc_col_index is None:
            utd_erc_col_index = 1  # Default to second column (index 1)
        
        # Create the new Item name header
        new_header = soup.new_tag('th')
        new_header.string = "Item name"
        headers[utd_erc_col_index].insert_after(new_header)
        
        # Update the header list after insertion
        headers = header_row.find_all('th')
        header_texts = [th.get_text(strip=True).lower() for th in headers]
        
        # Find the new index of Item name column
        for i, header_text in enumerate(header_texts):
            if "item name" in header_text:
                item_name_col_index = i
                print(f"New 'Item name' column created at index {i}")
                break
        
        # Add a new cell to each row for the Item name column
        rows = table.find_all('tr')[1:]  # Skip header row
        for row in rows:
            cells = row.find_all('td')
            th_cells = row.find_all('th')
            
            # Calculate the insertion position based on utd_erc_col_index
            insert_after_cell = None
            if utd_erc_col_index - len(th_cells) >= 0:
                # If utd_erc is a td cell
                td_index = utd_erc_col_index - len(th_cells)
                if td_index < len(cells):
                    insert_after_cell = cells[td_index]
            else:
                # If utd_erc is the last th cell
                insert_after_cell = th_cells[-1]
            
            if insert_after_cell:
                new_cell = soup.new_tag('td')
                insert_after_cell.insert_after(new_cell)
    
    # Check for the Matched Heading column too
    heading_col_index = None
    header_texts = [th.get_text(strip=True).lower() for th in header_row.find_all('th')]
    
    # Look for a "Matched Heading" column
    for i, header_text in enumerate(header_texts):
        if "matched heading" in header_text:
            heading_col_index = i
            break
    
    # If Matched Heading column doesn't exist, add it
    if heading_col_index is None:
        # Add a new header cell
        new_header = soup.new_tag('th')
        new_header.string = "Matched Heading"
        headers[-1].insert_after(new_header)
        
        # Update the header list again
        headers = header_row.find_all('th')
        header_texts = [th.get_text(strip=True).lower() for th in headers]
        
        # Find the new Matched Heading column index
        for i, header_text in enumerate(header_texts):
            if "matched heading" in header_text:
                heading_col_index = i
                break
        
        # Add a new cell to each row
        rows = table.find_all('tr')[1:]  # Skip header row
        for row in rows:
            cells = row.find_all('td')
            if cells:  # Make sure the row has cells
                new_cell = soup.new_tag('td')
                cells[-1].insert_after(new_cell)
    
    rows = table.find_all('tr')[1:]  # Skip header row
    
    # Create patterns to match headings that look like "E#### - Name" or similar patterns
    e_number_pattern = re.compile(r'E\d+')
    
    for row in rows:
        cells = row.find_all('td')
        erc_variable_cell = row.find('th')
        
        if not erc_variable_cell:
            continue
            
        # Get ERC variable from first column (in th)
        erc_variable = erc_variable_cell.get_text(strip=True)
        print(f"Looking for match for '{erc_variable}'")
        
        # Skip empty variables
        if not erc_variable:
            continue
            
        # Try to find a matching heading
        heading = find_heading_for_item_name(target_content, erc_variable, score_threshold=0.45)
        
        # If not found, try some fallback matching patterns:
        if not heading:
            # 1. Search for E-numbers in the heading if the ERC variable has one
            e_match = e_number_pattern.search(erc_variable)
            if e_match:
                e_number = e_match.group(0)
                # Try to find a heading with this E-number
                soup_target = BeautifulSoup(target_content, 'html.parser')
                for h in soup_target.find_all(['h1', 'h2', 'h3']):
                    if e_number in h.get_text():
                        heading = h.get_text().strip()
                        break
            
            # 2. Try without special characters and underscores
            if not heading:
                clean_erc = re.sub(r'[_\-]', ' ', erc_variable.lower())
                # Try to find headings that contain words from the cleaned ERC variable
                soup_target = BeautifulSoup(target_content, 'html.parser')
                for h in soup_target.find_all(['h1', 'h2', 'h3']):
                    heading_text = h.get_text().lower()
                    if any(word in heading_text for word in clean_erc.split() if len(word) > 3):
                        heading = h.get_text().strip()
                        break
        
        # Calculate the item name cell index within the row
        # Subtract the number of th cells since the item_name_col_index is based on all cells
        th_count = len(row.find_all('th'))
        td_item_name_index = item_name_col_index - th_count
        
        # Make sure we have enough td cells
        while len(cells) <= td_item_name_index:
            # Add placeholder cells if needed
            new_cell = soup.new_tag('td')
            if cells:
                cells[-1].insert_after(new_cell)
            else:
                # If no cells, add after the last th
                row.find_all('th')[-1].insert_after(new_cell)
            cells = row.find_all('td')  # Update the cells list
        
        if heading:
            # Format the heading for a URL anchor
            encoded_heading = quote(heading.replace(' ', '-').replace('#', ''))
            
            # Create a clean version of the heading for display (remove E#### and other prefixes)
            display_heading = heading
            # Try to extract a cleaner version from the heading (remove E numbers, etc.)
            heading_parts = re.split(r'[–—\-]\s*', heading, 1)  # Split on different dash types
            if len(heading_parts) > 1:
                # Use the part after the dash
                display_heading = heading_parts[1].strip()
            
            # Create the link with the heading text
            link = f'<a href="{target_page_url}#{encoded_heading}">{display_heading}</a>'
            
            # Update the Item Name cell with the link
            cells[td_item_name_index].clear()
            cells[td_item_name_index].append(BeautifulSoup(link, 'html.parser'))
            print(f"Added link in column index {td_item_name_index}")
            
            # Calculate the heading cell index
            td_heading_index = heading_col_index - th_count
            
            # Make sure we have enough cells for the heading too
            while len(cells) <= td_heading_index:
                new_cell = soup.new_tag('td')
                cells[-1].insert_after(new_cell)
                cells = row.find_all('td')
            
            # Add the matched heading to our new column
            cells[td_heading_index].string = heading
            
            print(f"Added link for '{erc_variable}' to heading '{heading}'")
        else:
            print(f"No matching heading found for '{erc_variable}'")
            
            # Calculate the heading cell index
            td_heading_index = heading_col_index - th_count
            
            # Make sure we have enough cells for the heading
            while len(cells) <= td_heading_index:
                new_cell = soup.new_tag('td')
                cells[-1].insert_after(new_cell)
                cells = row.find_all('td')
            
            # Clear the heading cell
            cells[td_heading_index].string = "No match found"

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

def parse_arguments():
    import argparse
    parser = argparse.ArgumentParser(description='Update links in Confluence pages')
    parser.add_argument('--dataset-page-id', required=True, help='Dataset page ID')
    parser.add_argument('--report-page-id', required=True, help='Report page ID')
    parser.add_argument('--reset', action='store_true', help='Reset hyperlinks to plain text')
    parser.add_argument('--link-type', choices=['thecb', 'sbec', 'tea'], default='thecb', 
                        help='Type of link creation function to use (default: thecb)')
    return parser.parse_args()

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

    source_page = confluence.get_page_by_id(args.dataset_page_id, expand='body.storage,version,space')
    target_page = confluence.get_page_by_id(args.report_page_id, expand='body.storage')

    # print (source_page)
    # print ('target')
    # print(target_page)

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
        target_page_url = get_page_url(confluence, args.report_page_id)
        
        # Select the appropriate link creation function based on the link-type argument
        if args.link_type == 'thecb':
            updated_content = create_links_thecb(source_content, target_content, target_page_url)
            version_comment = "Updated THECB links"
        elif args.link_type == 'sbec':
            updated_content = create_links_sbec(source_content, target_content, target_page_url)
            version_comment = "Updated SBEC links"
        elif args.link_type == 'tea':
            updated_content = create_links_tea(source_content, target_content, target_page_url)
            version_comment = "Updated TEA links"
        else:
            # This should never happen due to the choices parameter in argparse
            print(f"Error: Unknown link type '{args.link_type}'")
            sys.exit(1)

    # Update the page
    confluence.update_page(
        page_id=args.dataset_page_id,
        title=source_page['title'],
        body=updated_content,
        minor_edit=True,
        version_comment=version_comment,
        full_width=True )

    print(f"The page '{source_page['title']}' has been updated in Confluence using {args.link_type.upper()} link creation.")

if __name__ == "__main__":
    main()