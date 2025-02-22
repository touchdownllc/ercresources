# ERC Resources Python Scripts
 for the Confluence ERC Resources site

Python scripts to publish and manage ERC publications on Confluence.

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Create a `.env` file in the root directory with your Confluence credentials (see `.env.example`)

## Set up a virtual environment
#... on a Mac
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```


# ERC Publications Publisher

## Environment Variables

Create a `.env` file with the following variables:

- `CONFLUENCE_URL`: URL of your Confluence instance
- `CONFLUENCE_USERNAME`: Username/email for Confluence
- `CONFLUENCE_API_TOKEN`: API token for authentication
- `CONFLUENCE_SPACE_KEY`: Confluence space key
- `CONFLUENCE_PARENT_PAGE_ID`: Parent page ID where publications will be created

## Usage

### Publishing Pages

Run the script to publish/update pages:

```
python erc_publish_publications.py --csv-file your_file.csv
```

### Deleting Pages

To see what pages would be deleted (dry run):

```
python erc_publish_publications.py --delete --dry-run
```

To actually delete all pages:

```
python erc_publish_publications.py --delete
```

