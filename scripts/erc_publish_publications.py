from dataclasses import dataclass
from typing import Dict, List, Optional
import logging
import html
import pandas as pd
import requests
from atlassian import Confluence
import argparse
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class ConfluenceConfig:
    url: str
    username: str
    api_token: str
    space_key: str
    parent_page_id: str

@dataclass
class PageContent:
    title: str
    body: str 
    type_name: str
    labels: List[str]
    url: str

class ConfluencePageManager:
    def __init__(self, config: ConfluenceConfig):
        self.config = config
        self.confluence = Confluence(
            url=config.url,
            username=config.username,
            password=config.api_token,
            cloud=True
        )
        self.logger = logging.getLogger(__name__)
        self.type_to_page_id = {}

    def create_type_pages(self, unique_types: List[str]) -> None:
        """Creates or updates parent pages for each content type."""
        for type_name in sorted(unique_types):
            page_title = f"{type_name}s"
            if page_title == "Research Publications":
                page_title = "Published Research"
            try:
                type_page = self.confluence.get_page_by_title(
                    space=self.config.space_key, 
                    title=page_title
                )

                if not type_page:
                    type_page = self.confluence.create_page(
                        space=self.config.space_key,
                        title=page_title,
                        body=f"<h1>{page_title}</h1>",
                        parent_id=self.config.parent_page_id,
                        representation='storage',
                        full_width=True
                    )

                page_id = type_page['id']
                
                # Add page tree
                page_tree_macro = f"""
                    <ac:structured-macro ac:name="pagetree">
                    <ac:parameter ac:name="root"><ac:link><ri:page ri:content-title="{page_title}" /></ac:link></ac:parameter>
                    <ac:parameter ac:name="spaceKey">{self.config.space_key}</ac:parameter>
                    <ac:parameter ac:name="startDepth">1</ac:parameter>
                    </ac:structured-macro>
                """
                page_body = f"<h2>Contents</h2>{page_tree_macro}"

                #print (page_body)
                
                self.confluence.update_page(
                    page_id=page_id,
                    title=page_title,
                    body=page_body,
                    parent_id=self.config.parent_page_id,
                    representation='storage',
                    full_width=True
                )
                
                self.type_to_page_id[type_name] = page_id

            except requests.exceptions.HTTPError as e:
                self.logger.error(f"Error handling type page '{type_name}': {e}")
                raise

    def delete_all_pages(self, dry_run: bool = False) -> None:
        """
        Deletes all pages under the configured parent page.
        
        Args:
            dry_run (bool): If True, only simulates deletion and prints what would be deleted
        """
        self.logger.info(f"{'[DRY RUN] ' if dry_run else ''}Starting deletion of all pages under parent page {self.config.parent_page_id}")
        
        try:
            # Get all child pages recursively with their hierarchy
            pages_to_delete = self.get_all_child_pages_with_hierarchy(self.config.parent_page_id)
            
            if not pages_to_delete:
                self.logger.info("No pages found to delete")
                return

            # Print deletion preview
            self.print_deletion_preview(pages_to_delete)
            
            if dry_run:
                self.logger.info("[DRY RUN] No pages were actually deleted")
                return
                
            # Delete pages from bottom up (children first)
            for page in reversed(pages_to_delete):
                try:
                    self.confluence.remove_page(page['id'])
                    self.logger.info(f"Deleted page: {page['title']} (ID: {page['id']})")
                except Exception as e:
                    self.logger.error(f"Failed to delete page {page['title']}: {str(e)}")
                    
            self.logger.info(f"Completed deletion of {len(pages_to_delete)} pages")
            
        except Exception as e:
            self.logger.error(f"Error during page deletion: {str(e)}")
            raise

    def get_all_child_pages_with_hierarchy(self, parent_id: str, level: int = 0) -> List[dict]:
        """
        Recursively gets all child pages under a parent page, including their hierarchy level.
        
        Args:
            parent_id (str): ID of the parent page
            level (int): Current hierarchy level (for indentation)
            
        Returns:
            List[dict]: List of pages with hierarchy information
        """
        all_pages = []
        
        try:
            # Get immediate children
            children = self.confluence.get_page_child_by_type(parent_id, type='page')
            
            for child in children:
                # Add hierarchy level to page info
                child['level'] = level
                all_pages.append(child)
                
                # Recursively get children
                child_pages = self.get_all_child_pages_with_hierarchy(child['id'], level + 1)
                all_pages.extend(child_pages)
                
        except Exception as e:
            self.logger.error(f"Error getting child pages for {parent_id}: {str(e)}")
            raise
            
        return all_pages

    def print_deletion_preview(self, pages: List[dict]) -> None:
        """
        Prints a formatted preview of pages that will be deleted.
        
        Args:
            pages (List[dict]): List of pages with hierarchy information
        """
        print("\nPages to be deleted (in reverse order):")
        print("=" * 80)
        
        # Group pages by type for summary
        type_counts = {}
        
        # Print detailed hierarchy
        for page in reversed(pages):
            indent = "  " * page['level']
            print(f"{indent}• {page['title']}")
            
            # Count page types for summary
            page_type = page.get('type', 'Unknown')
            type_counts[page_type] = type_counts.get(page_type, 0) + 1
        
        # Print summary
        print("\nSummary:")
        print("=" * 80)
        print(f"Total pages to delete: {len(pages)}")
        for page_type, count in type_counts.items():
            print(f"- {page_type}: {count} pages")
        print("=" * 80 + "\n")


class ContentProcessor:
    @staticmethod
    def validate_url(url: str) -> bool:
        """Validates if a URL is accessible."""
        if pd.isna(url) or not url:
            return False
        try:
            response = requests.head(url, allow_redirects=True, timeout=5)
            return 200 <= response.status_code < 400
        except:
            return False

    @staticmethod
    def create_page_content(row: pd.Series) -> PageContent:
        """Creates page content from a row in the simplified CSV format."""
        # Build the body content parts
        body_parts = [
            f"<p><b>Title:</b> {html.escape(str(row['Title']), quote=True)}</p>",
            f"<p><b>Authors:</b> {html.escape(str(row['Authors']), quote=True)}</p>",
            f"<p><b>Type:</b> {html.escape(str(row['Type']), quote=True)}</p>"
        ]
        
        # Add optional fields if present
        if pd.notna(row['THECB #']):
            body_parts.append(f"<p><b>THECB Project ID:</b> {html.escape(str(row['THECB #']), quote=True)}</p>")
            
        if pd.notna(row['Publishing ERC']):
            body_parts.append(f"<p><b>Publishing ERC:</b> {html.escape(str(row['Publishing ERC']), quote=True)}</p>")
          
        if pd.notna(row['Project Abbreviated Name']):
            body_parts.append(f"<p><b>Project Abbreviated Name:</b> {html.escape(str(row['Project Abbreviated Name']), quote=True)}</p>")
            
        if pd.notna(row['Date']):
            body_parts.append(f"<p><b>Publication Date:</b> {row['Date']}</p>")

        if pd.notna(row['Abstract']):
            try:
                body_parts.append(f"<p><b>Abstract: </b></p>")
                # Convert to string and handle potential None values
                abstract_text = str(row['Abstract']) if row['Abstract'] is not None else ""
                # Only proceed if we have actual content
                if abstract_text.strip():
                    escaped_abstract = html.escape(abstract_text, quote=True)
                    abstract_content = f"""<ac:structured-macro ac:name="expand">
                        <ac:parameter ac:name="title">Expand for abstract</ac:parameter>
                        <ac:rich-text-body>
                            <p>{escaped_abstract}</p>
                        </ac:rich-text-body>
                    </ac:structured-macro>"""
                    body_parts.append(abstract_content)
            except Exception as e:
                logger.warning(f"Error processing abstract for '{row['Title']}': {str(e)}")
                # Continue without the abstract rather than failing
                pass
            
        if pd.notna(row['Key Terms']):
            body_parts.append(f"<p><b>Key Terms:</b> {html.escape(str(row['Key Terms']), quote=True)}</p>")
            
        if pd.notna(row['Topic']):
            body_parts.append(f"<p><b>Topic:</b> {html.escape(str(row['Topic']), quote=True)}</p>")
                       
        if pd.notna(row['Source URL']):
            body_parts.append(f'<p><b>Publishing Source:</b> <a href="{row["Source URL"]}">{row["Source URL"]}</a></p>')

        if pd.notna(row['URL']):
            body_parts.append(f'<p><b><a href="{row["URL"]}">Link to Publication</a></b></p>')
        else:
            body_parts.append(f'<p><b>Link to Publication</b> (not provided)</p>')

        # Create labels
        labels = ['erc-publication']
        
        
            
        if pd.notna(row['THECB #']):
            labels.append(f"thecb-id-{str(row['THECB #']).replace(' ', '-').replace(',', '').replace('.','')}")
            
        if pd.notna(row['Publishing ERC']):
            labels.append(f"pub-erc-{row['Publishing ERC'].replace(' ', '-').replace(',', '').replace('.','')}")

        if pd.notna(row['Topic']):
            labels.append(f"topic-{row['Topic'].replace(' ', '-').replace(',', '').replace('.','')}")

        if pd.notna(row['Research Area']):
            labels.append(f"topic-{row['Research Area'].replace(' ', '-').replace(',', '').replace('.','')}")

        if pd.notna(row['Type']):
            labels.append(f"type-{row['Type'].replace(' ', '-').replace(',', '').replace('.','')}")

        return PageContent(
            title=row['Title'],
            body='\n'.join(body_parts),
            type_name=row['Type'],
            labels=labels,
            url=row['URL'] if pd.notna(row['URL']) else ''
        )

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Confluence Page Manager')
    parser.add_argument('--delete', action='store_true', help='Delete all pages under parent page')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without actually deleting')
    parser.add_argument('--csv-file', type=str, default='erc_publications.csv', 
                      help='Path to the CSV file with publication data')
    args = parser.parse_args()

    # Configuration from environment variables
    config = ConfluenceConfig(
        url=os.getenv('CONFLUENCE_URL'),
        username=os.getenv('CONFLUENCE_USERNAME'),
        api_token=os.getenv('CONFLUENCE_API_TOKEN'),
        space_key=os.getenv('CONFLUENCE_SPACE_KEY'),
        parent_page_id=os.getenv('CONFLUENCE_PARENT_PAGE_ID')
    )

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Initialize page manager
    page_manager = ConfluencePageManager(config)

    if args.delete:
        if args.dry_run:
            # Dry run mode - just show what would be deleted
            try:
                page_manager.delete_all_pages(dry_run=True)
            except Exception as e:
                logger.error(f"Error during dry run: {str(e)}")
            return
            
        # Actual deletion mode
        proceed = input("Are you sure you want to delete all pages? This cannot be undone! (yes/no): ")
        if proceed.lower() == 'yes':
            try:
                page_manager.delete_all_pages(dry_run=False)
                logger.info("Page deletion completed successfully")
            except Exception as e:
                logger.error(f"Failed to delete pages: {str(e)}")
        else:
            logger.info("Deletion cancelled")
        return

    # Normal page creation/update flow
    try:

        # Check if args.csv_file is provided
        if args.csv_file is None:
            raise FileNotFoundError("CSV file path not provided. Please specify a CSV file using the --csv-file argument.")
    
        # Load data
        df = pd.read_csv(args.csv_file)
        
        # Create type pages
        unique_types = sorted(df['Type'].unique())
        page_manager.create_type_pages(unique_types)
        
        # Process each row
        for _, row in df.iterrows():
            try:
                content = ContentProcessor.create_page_content(row)
                
                if content.url and not ContentProcessor.validate_url(content.url):
                    logger.warning(f"This publication has an invalid URL: {content.title} - {content.url}")
                #     continue

                # Create or update page
                existing_page = page_manager.confluence.get_page_by_title(
                    space=config.space_key,
                    title=content.title,
                    expand='body.storage'
                )
                
                parent_id = page_manager.type_to_page_id[content.type_name]
                
                if existing_page:
                    page_manager.confluence.update_page(
                        page_id=existing_page['id'],
                        title=content.title,
                        body=content.body,
                        type='page',
                        representation='storage',
                        full_width=True
                    )
                    logger.info(f"Updated page: {content.title}")
                else:
                    new_page = page_manager.confluence.create_page(
                        space=config.space_key,
                        title=content.title,
                        body=content.body,
                        parent_id=parent_id,
                        type='page',
                        representation='storage',
                        full_width=True
                    )
                    
                    # Add labels
                    for label in content.labels:
                        page_manager.confluence.set_page_label(new_page['id'], label)
                        
                    logger.info(f"Created page: {content.title}")

            except Exception as e:
                logger.error(f"Error processing row: {str(e)}")
                continue

    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")

if __name__ == "__main__":
    main()