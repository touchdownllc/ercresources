import requests
from bs4 import BeautifulSoup
import pandas as pd
from atlassian import Confluence
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# List of URLs to scrape and their corresponding page names
target_pages = [
    {
        "url": "https://texaserc.utexas.edu/projects/current-research-projects/",
        "title": "UT Austin ERC - Current Research Projects",
        "csv_file": "current_research_projects.csv"
    },
    {
        "url": "https://texaserc.utexas.edu/projects/past-research-projects/",
        "title": "UT Austin ERC - Past Research Projects",
        "csv_file": "past_research_projects.csv"
    },
]

def scrape_table_from_url(url):
    response = requests.get(url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table')
        if table:
            # Extract table headers
            headers = [th.text.strip() for th in table.find_all('th')]
            #Rename 'ERCProjNo.' or 'ERCProj #' to 'ERC Project Number'
            headers = ['ERC Proj No' if h in ['ERCProjNo.', 'ERCProj #'] else h for h in headers]
            #Rename 'Original Approval Date' to 'Approval Date'
            headers = ['Approval Date' if h in ['Original Approval Date'] else h for h in headers]
            # Rename 'THECB #' or 'THECBNo.' to 'THECB Number'
            headers = ['THECB Number' if h in ['THECB #', 'THECBNo.'] else h for h in headers]
            # Rename 'Texas ERC Project Name (Click Project Name to see available policy brief)' or 
            # 'Texas ERC Project Full Name(Click Project Name to see available policy brief)' to 'Texas ERC Project Name'
            headers = ['Texas ERC Project Name' if 'Texas ERC Project' in h and 'Click Project Name to see available policy brief' in h else h for h in headers]
            # Rename 'Project  Abbreviated Name' to 'Project Abbreviated Name'
            headers = ['Project Abbreviated Name' if h in ['Project  Abbreviated Name'] else h for h in headers]

            # Add 'Publication Links' to headers
            headers.append('Publications Associated with Project')

            # Extract table rows
            rows = []
            hyperlink_rows = []
            for tr in table.find_all('tr')[1:]:
                cells = [td.text.strip() for td in tr.find_all('td')]
                # Standardize 'Approval Date' to add 4 digit year if only 2 digits are present
                for i, header in enumerate(headers):
                    if header == 'Approval Date' and i < len(cells):
                        date_parts = cells[i].split('.')
                        if len(date_parts) == 3 and len(date_parts[2]) == 2:
                            cells[i] = f"{date_parts[0]}.{date_parts[1]}.20{date_parts[2]}"
                # Remove the row where the first column is '149'
                if len(cells) > 0 and cells[0] == '149' and url == 'https://texaserc.utexas.edu/projects/past-research-projects/':
                    continue
                # Process the 'Texas ERC Project Name' column
                publication_links = 'N'
                for i, cell in enumerate(cells):
                    if i < len(headers) and headers[i] == 'Texas ERC Project Name':
                        if '\nBrief 1' in cell:
                            cells[i] = cell.split('\nBrief 1')[0].strip()
                            publication_links = 'Y'
                        # Check for hyperlinks in 'Texas ERC Project Name'
                        link_elements = tr.find_all('td')[i].find_all('a')
                        if link_elements:
                            thecb_number = cells[headers.index('THECB Number')].strip() if 'THECB Number' in headers else ''
                            for link in link_elements:
                                hyperlink_rows.append({
                                    'THECB Number': thecb_number,
                                    'Texas ERC Project Name': cells[i],
                                    'Hyperlink': link.get('href')
                                })
                            #print(f"Found hyperlink in 'Texas ERC Project Name': {link.get('href')}")

                # Add Confluence macro for publication links
                thecb_number_index = headers.index('THECB Number') if 'THECB Number' in headers else -1
                if thecb_number_index != -1 and len(cells) > thecb_number_index:
                    thecb_number = cells[thecb_number_index].strip()
                    if thecb_number and thecb_number != '---':
                        filter_label = f"thecb-id-{thecb_number}"
                        publication_links = f"<ac:structured-macro ac:name=\"contentbylabel\" ac:schema-version=\"1\"><ac:parameter ac:name=\"label\">{filter_label}</ac:parameter><ac:parameter ac:name=\"max\">10</ac:parameter><ac:parameter ac:name=\"showSpace\">false</ac:parameter><ac:parameter ac:name=\"showLabels\">false</ac:parameter></ac:structured-macro>"
                    else:
                        publication_links = '---'
                cells.append(publication_links)
                rows.append(cells)

            # Create DataFrames
            main_df = pd.DataFrame(rows, columns=headers)
            hyperlink_df = pd.DataFrame(hyperlink_rows)
            return main_df, hyperlink_df
    return None, None

def save_dataframe_to_csv(dataframe, csv_path):
    dataframe.to_csv(csv_path, mode='w', index=False, header=True)

def load_dataframe_from_csv(csv_path):
    if os.path.exists(csv_path):
        return pd.read_csv(csv_path)
    return None

def publish_to_confluence(confluence, title, dataframe, projects_parent_page_id, space_key):
    # Convert the DataFrame to a Confluence table format
    confluence_table = '<table class="confluenceTable">'
    confluence_table += '<thead><tr>'
    for col in dataframe.columns:
        confluence_table += f'<th class="confluenceTh">{col}</th>'
    confluence_table += '</tr></thead>'
    confluence_table += '<tbody>'
    for _, row in dataframe.iterrows():
        confluence_table += '<tr>'
        for i, cell in enumerate(row):
            cell_value = '---' if pd.isna(cell) else cell
            confluence_table += f'<td class="confluenceTd">{cell_value}</td>'
        confluence_table += '</tr>'
    confluence_table += '</tbody></table>'

    # Define the page content
    page_content = f"""
    <h2>{title}</h2>
    {confluence_table}
    """

    print("Title: " + title)  
    try:
        existing_page = confluence.get_page_by_title(space=space_key, title=title, expand='body.storage')
    except requests.exceptions.HTTPError as e:
        print(f"Error finding '{title}': {e}")
        existing_page = None

    if existing_page:
        try:
            confluence.update_page(
                page_id=existing_page['id'],
                title=title,
                body=page_content,
                type='page',
                representation='storage',
                full_width=True 
            )
            print(f"Updated page: {title}")
        except Exception as e:
            print(f"Error updating page '{title}': {e}")
    else:
        try:
            new_page = confluence.create_page(
                space=space_key,
                title=title,
                body=page_content,
                parent_id=projects_parent_page_id,
                type='page',
                representation='storage',
                full_width=True 
            )
            page_id = new_page['id']
            print(f"Created page: {title} with ID: {page_id}")
        except requests.exceptions.HTTPError as e:
            print(f"Error creating page '{title}': {e}")

def initialize_confluence(username, api_token, site_url):
    return Confluence(
        url=site_url,
        username=username,
        password=api_token,
        cloud=True
    )

def main():
    # Get Confluence credentials from environment variables
    api_token = os.getenv('CONFLUENCE_API_TOKEN')
    site_url = os.getenv('CONFLUENCE_URL')
    username = os.getenv('CONFLUENCE_USERNAME')
    space_key = os.getenv('CONFLUENCE_SPACE_KEY')
    projects_parent_page_id = os.getenv('PROJECTS_PARENT_PAGE_ID')
    
    if not all([api_token, site_url, username, space_key, projects_parent_page_id]):
        print("Error: Missing required environment variables. Please check your .env file.")
        return

    confluence = initialize_confluence(username, api_token, site_url)
    combined_hyperlink_df = pd.DataFrame()

    # Loop through each URL and scrape the table, saving to individual CSVs
    for page in target_pages:
        url = page["url"]
        csv_file = page["csv_file"]
        main_df, hyperlink_df = scrape_table_from_url(url)
        if main_df is not None:
            save_dataframe_to_csv(main_df, csv_file)
            print(f"Saved data from {url} to CSV: {csv_file}.")
            if hyperlink_df is not None and not hyperlink_df.empty:
                combined_hyperlink_df = pd.concat([combined_hyperlink_df, hyperlink_df], ignore_index=True)
        else:
            print(f"No table found at {url}.")

    # Save combined hyperlinks to a single CSV
    if not combined_hyperlink_df.empty:
        save_dataframe_to_csv(combined_hyperlink_df, "combined_hyperlinks.csv")
        print("Saved all hyperlinks to combined_hyperlinks.csv.")

    # Prompt the user to continue with updating Confluence
    proceed = input("Do you want to continue with reading from the CSVs and updating Confluence? (y/n): ")
    if proceed.lower() == 'y':
        for page in target_pages:
            title = page["title"]
            csv_file = page["csv_file"]
            df = load_dataframe_from_csv(csv_file)
            if df is not None:
                publish_to_confluence(confluence, title, df, projects_parent_page_id, space_key)
                print(f"Published data to Confluence with title '{title}'.")
            else:
                print(f"No data found in CSV: {csv_file} to publish.")

if __name__ == "__main__":
    main()