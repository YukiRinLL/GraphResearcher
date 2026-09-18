#!/usr/bin/env python3
"""
JSON Generation Script

Generates JSON data from markdown files with:
- Statement extraction using LLM
- Citation URL parsing
- Web content fetching via Jina API

Supports incremental processing - only processes what's missing.

Usage:
    # Full pipeline for single file
    python scripts/generate_json.py -i data/md_data/Article.md -o data/json_data/Article.json
    
    # Full pipeline for directory
    python scripts/generate_json.py -i data/gemini/md_data/ -o data/gemini/json_data/
    
    # Only extract statements (skip fetching)
    python scripts/generate_json.py -i data/md_data/ -o data/json_data/ --steps extract
    
    # Only fetch citations (for existing JSON)
    python scripts/generate_json.py -i data/md_data/ -o data/json_data/ --steps fetch
    
    # Both steps (default)
    python scripts/generate_json.py -i data/md_data/ -o data/json_data/ --steps extract,fetch

Environment Variables (or .env file):
    JINA_API_KEY        - Jina Reader API key (required for fetching)
    EXTRACT_MODEL       - Model for statement extraction (default: gemini-2.5-flash)
    EXTRACT_API_KEY     - API key for extraction model
    EXTRACT_BASE_URL    - Base URL for extraction API
    CONCURRENCY         - Number of concurrent workers (default: 10)
"""

import argparse
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Config
from src.citation_parser import CitationParser
from src.statement_extractor import StatementExtractor
from src.jina_scraper import JinaScraper
from src.json_builder import JSONBuilder


def process_single_file(
    md_path: Path,
    json_path: Path,
    config: Config,
    steps: set,
    citation_parser: CitationParser,
    json_builder: JSONBuilder,
    extractor: StatementExtractor = None,
    scraper: JinaScraper = None,
    base_dir: Path = None,
    verbose: bool = False,
    print_lock: Lock = None
) -> dict:
    """
    Process a single markdown file.
    
    Returns:
        Statistics dict.
    """
    stats = {'status': 'success', 'statements': 0, 'fetched': 0, 'failed': 0}
    
    try:
        # Read markdown
        md_content = md_path.read_text(encoding='utf-8')
        
        # Parse citations
        citation_urls = citation_parser.extract_citation_urls(md_content)
        clean_text = citation_parser.extract_clean_text(md_content)
        
        # Extract title
        import re
        title_match = re.search(r'^#\s+(.+)$', md_content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else md_path.stem
        
        # Load existing JSON if exists
        existing_data = None
        existing_statements = []
        existing_contents = {}
        
        if json_path.exists():
            existing_data = json_builder.load(json_path)
            page = json_builder.get_page(existing_data)
            existing_statements = page.get('statements', [])
            existing_contents = page.get('citation_contents', {})
        
        # Step 1: Extract statements
        statements = existing_statements
        if 'extract' in steps:
            if not existing_statements and extractor:
                statements = extractor.extract(
                    md_content,
                    has_citations=True,
                    citation_urls=citation_urls
                )
                stats['statements'] = len(statements)
                
                if verbose and print_lock:
                    with print_lock:
                        print(f"  Extracted {len(statements)} statements from {md_path.name}")
            elif existing_statements:
                stats['statements'] = len(existing_statements)
        
        # Step 2: Fetch citation contents
        citation_contents = existing_contents
        if 'fetch' in steps and scraper and citation_urls:
            # Find URLs that need fetching
            to_fetch = {}
            for cite_num, url in citation_urls.items():
                if cite_num not in existing_contents:
                    to_fetch[cite_num] = url
                elif existing_contents[cite_num].get('error'):
                    to_fetch[cite_num] = url
            
            if to_fetch:
                new_contents = scraper.fetch_urls(to_fetch, concurrency=3)
                citation_contents.update(new_contents)
                
                for content in new_contents.values():
                    if content.get('error'):
                        stats['failed'] += 1
                    else:
                        stats['fetched'] += 1
                
                if verbose and print_lock:
                    with print_lock:
                        print(f"  Fetched {stats['fetched']}/{len(to_fetch)} URLs for {md_path.name}")
        
        # Compute relative source path
        if base_dir:
            try:
                source_file = str(md_path.relative_to(base_dir))
            except ValueError:
                source_file = md_path.name
        else:
            source_file = md_path.name
        
        # Build JSON
        json_data = json_builder.build(
            title=title,
            extract=clean_text,
            citation_urls=citation_urls,
            statements=statements,
            citation_contents=citation_contents if citation_contents else None,
            source_file=source_file
        )
        
        # Save
        json_builder.save(json_data, json_path)
        
    except Exception as e:
        stats['status'] = 'error'
        stats['error'] = str(e)[:200]
        if verbose and print_lock:
            with print_lock:
                print(f"  Error processing {md_path.name}: {e}")
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description='Generate JSON data from markdown files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '-i', '--input',
        type=str,
        required=True,
        help='Input markdown file or directory'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        required=True,
        help='Output JSON file or directory'
    )
    
    parser.add_argument(
        '--steps',
        type=str,
        default='extract,fetch',
        help='Processing steps: extract, fetch, or both (default: extract,fetch)'
    )
    
    parser.add_argument(
        '-c', '--concurrency',
        type=int,
        default=None,
        help='Number of concurrent workers (default: from config or 10)'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force reprocessing even if output exists'
    )
    
    parser.add_argument(
        '--skip-existing',
        action='store_true',
        help='Skip files that already have complete output'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    parser.add_argument(
        '--env',
        type=str,
        default=None,
        help='Path to .env file'
    )
    
    args = parser.parse_args()
    
    # Parse steps
    steps = set(s.strip() for s in args.steps.split(','))
    valid_steps = {'extract', 'fetch'}
    invalid = steps - valid_steps
    if invalid:
        print(f"Invalid steps: {invalid}. Valid steps: {valid_steps}")
        sys.exit(1)
    
    # Load config
    env_path = Path(args.env) if args.env else PROJECT_ROOT / '.env'
    config = Config(env_path)
    
    if args.verbose:
        print(f"Config: {config}")
    
    # Validate config for required steps
    if 'extract' in steps:
        if not config.extract_api_key or not config.extract_base_url:
            print("Error: EXTRACT_API_KEY and EXTRACT_BASE_URL required for extraction")
            print("Set them in .env file or environment")
            sys.exit(1)
    
    if 'fetch' in steps:
        if not config.jina_api_key:
            print("Error: JINA_API_KEY required for fetching")
            print("Set it in .env file or environment")
            sys.exit(1)
    
    # Initialize components
    citation_parser = CitationParser()
    json_builder = JSONBuilder()
    
    extractor = None
    if 'extract' in steps:
        extractor = StatementExtractor(
            model=config.extract_model,
            api_key=config.extract_api_key,
            base_url=config.extract_base_url,
            timeout=config.api_timeout
        )
        print(f"Statement extractor: {config.extract_model}")
    
    scraper = None
    if 'fetch' in steps:
        scraper = JinaScraper(
            api_key=config.jina_api_key,
            max_retries=config.max_retries
        )
        print("Jina scraper initialized")
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    concurrency = args.concurrency or config.concurrency
    
    if input_path.is_file():
        # Single file processing
        print(f"Processing: {input_path}")
        
        stats = process_single_file(
            md_path=input_path,
            json_path=output_path,
            config=config,
            steps=steps,
            citation_parser=citation_parser,
            json_builder=json_builder,
            extractor=extractor,
            scraper=scraper,
            verbose=args.verbose,
            print_lock=Lock()
        )
        
        print(f"\nResult: {stats['status']}")
        print(f"  Statements: {stats['statements']}")
        print(f"  Fetched: {stats['fetched']}")
        print(f"  Failed: {stats['failed']}")
        
    elif input_path.is_dir():
        # Directory processing
        md_files = list(input_path.glob('*.md'))
        
        if not md_files:
            print(f"No .md files found in {input_path}")
            return
        
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Filter files if skip_existing
        if args.skip_existing:
            md_files = [
                f for f in md_files
                if not (output_path / f"{f.stem}.json").exists()
            ]
        
        print(f"Processing {len(md_files)} files with {concurrency} workers")
        print(f"Steps: {steps}")
        
        total_stats = {
            'success': 0, 'error': 0,
            'statements': 0, 'fetched': 0, 'failed': 0
        }
        print_lock = Lock()
        
        def process_file(md_file):
            json_file = output_path / f"{md_file.stem}.json"
            return md_file.name, process_single_file(
                md_path=md_file,
                json_path=json_file,
                config=config,
                steps=steps,
                citation_parser=citation_parser,
                json_builder=json_builder,
                extractor=extractor,
                scraper=scraper,
                base_dir=input_path.parent,
                verbose=args.verbose,
                print_lock=print_lock
            )
        
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {executor.submit(process_file, f): f for f in md_files}
            
            completed = 0
            for future in as_completed(futures):
                name, stats = future.result()
                completed += 1
                
                if stats['status'] == 'success':
                    total_stats['success'] += 1
                else:
                    total_stats['error'] += 1
                
                total_stats['statements'] += stats.get('statements', 0)
                total_stats['fetched'] += stats.get('fetched', 0)
                total_stats['failed'] += stats.get('failed', 0)
                
                if not args.verbose:
                    print(f"\rProgress: {completed}/{len(md_files)}", end='', flush=True)
        
        print(f"\n\nCompleted:")
        print(f"  Success: {total_stats['success']}")
        print(f"  Errors: {total_stats['error']}")
        print(f"  Total statements: {total_stats['statements']}")
        print(f"  URLs fetched: {total_stats['fetched']}")
        print(f"  URLs failed: {total_stats['failed']}")
    
    else:
        print(f"Error: {input_path} does not exist")
        sys.exit(1)


if __name__ == '__main__':
    main()
