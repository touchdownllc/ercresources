# ERC Resources Python Scripts
 
Python scripts to publish and manage ERC publications on Confluence.

## Setup

1. Clone the repository or download as a .zip file
2. Create a virtual environment:
   ```
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Create a `.env` file in the root directory with your Confluence credentials (see `.env.example`)


# Python Scripts Documentation

## ERC Publish Publications

A Python utility for automatically creating and organizing research publication pages in Confluence based on CSV data.

Code: https://github.com/touchdownllc/ercresources/blob/main/scripts/erc_publish_publications.py

### Overview

This script reads research publication information from a CSV file and creates hierarchically organized pages in Confluence. It creates type-based parent pages (e.g., "Published Research") and publication detail pages under them.

### Requirements

- Python 3.6+
- Required Python packages (install via `pip`):
  - `atlassian-python-api`
  - `pandas`
  - `requests`
  - `python-dotenv`

### Setup

1. **Install dependencies**:
   ```
   pip install -r requirements.txt
   ```

2. **Create a `.env` file** in the same directory as the script with the following variables:
   ```
   CONFLUENCE_URL=https://your-instance.atlassian.net
   CONFLUENCE_USERNAME=your_email@example.com
   CONFLUENCE_API_TOKEN=your_api_token
   CONFLUENCE_SPACE_KEY=SPACENAME
   CONFLUENCE_PARENT_PAGE_ID=123456789
   ```

   To create an API token:
   - Go to [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
   - Click "Create API token"
   - Give it a name and copy the token to your `.env` file

### CSV Format

Your CSV file should contain the following columns:
- `Title` (required): Publication title
- `Authors` (required): Publication authors
- `Type` (required): Publication type (e.g., "Research Publication")
- `URL` (optional): Link to the publication
- `Source URL` (optional): Publishing source URL
- `Date` (optional): Publication date
- `Abstract` (optional): Publication abstract
- `Key Terms` (optional): Related key terms
- `Topic` (optional): Research topic
- `THECB #` (optional): THECB Project ID
- `Publishing ERC` (optional): Publishing ERC name
- `Project Abbreviated Name` (optional): Short project name
- `Research Area` (optional): Research field or area

### Usage

#### Creating/Updating Publication Pages

```
python erc_publish_publications.py --csv-file your_publications.csv
```

By default, the script looks for a file named `erc_publications.csv` if no file is specified.

#### Deleting All Pages (with confirmation)

```
python erc_publish_publications.py --delete
```

This requires typing "yes" to confirm deletion.

#### Preview Deletion (dry run)

```
python erc_publish_publications.py --delete --dry-run
```

This shows what would be deleted without actually removing any pages.

### How It Works

1. The script connects to Confluence using your API credentials
2. It creates or updates parent pages for each unique publication type in your CSV
3. For each publication in the CSV:
   - Creates or updates a page with formatted details
   - Organizes it under the appropriate type page
   - Adds labels for filtering/categorization
4. Invalid URLs are logged as warnings but pages are still created

### Troubleshooting

- Check the logs for detailed error messages
- Ensure your Confluence API token has read/write permissions
- Verify the CSV format matches the expected column names
- If pages aren't appearing, check that the parent page ID is correct

## ERC Link Updater

A Python utility for automatically creating hyperlinks between data set pages and report pages in Confluence.

code: https://github.com/touchdownllc/ercresources/blob/main/scripts/erc_link_updater.py 

### Overview

This script searches for variable names in a source Confluence page (data set page) and links them to corresponding headings in a target Confluence page (report page). It's designed to work with TEA, THECB, and SBEC variable tables.

### Requirements

- Python 3.6+
- Required Python packages (install via `pip`):
  - `atlassian-python-api`
  - `beautifulsoup4`
  - `python-dotenv`

### Setup

1. **Install dependencies**:
   ```
   pip install -r requirements.txt
   ```

2. **Create a `.env` file** in the same directory as the script with the following variables:
   ```
   CONFLUENCE_URL=https://your-instance.atlassian.net
   CONFLUENCE_USERNAME=your_email@example.com
   CONFLUENCE_API_TOKEN=your_api_token
   CONFLUENCE_SPACE=SPACENAME
   ```

   To create an API token:
   - Go to [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
   - Click "Create API token"
   - Give it a name and copy the token to your `.env` file

### Usage

```
python erc_link_updater.py --dataset-page-id DATASET_PAGE_ID --report-page-id REPORT_PAGE_ID --link-type LINK_TYPE
```

Where:
- `DATASET_PAGE_ID`: The ID of the Confluence page containing the variables table
- `REPORT_PAGE_ID`: The ID of the Confluence page containing headings to link to
- 'LINK_TYPE' can be
  - `thecb`: Texas Higher Education Coordinating Board (default)
  - `sbec`: State Board for Educator Certification
  - `tea`: Texas Education Agency

#### Reset Links

To remove all hyperlinks in the variables table and reset to plain text:

```
python erc_link_updater.py --dataset-page-id DATASET_PAGE_ID --report-page-id REPORT_PAGE_ID --reset
```

#### Finding Page IDs

To find a Confluence page ID:
1. Open the page in your browser
2. Look at the URL, which will be in a format like:
   `https://your-instance.atlassian.net/wiki/spaces/SPACE/pages/123456789/Page+Title`
3. The number (e.g., `123456789`) is the page ID

### How It Works

1. The script connects to Confluence using your API credentials
2. It locates the variables table in the source page
3. For each variable name in the table, it searches for a matching heading in the target page
4. When a match is found, it creates a hyperlink to that specific heading
5. The script has built-in matching logic to handle different variable naming patterns

### Troubleshooting

- If no table is found, the script will output "Table not found in source content"
- If variables aren't matching to headings, try adjusting the `score_threshold` parameter in the `find_heading_for_item_name` function
- Check Confluence permissions to ensure your API token has read/write access to the pages
