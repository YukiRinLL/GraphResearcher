#!/usr/bin/env python3
"""
Clean wiki JSON files by removing specified fields.
Fields to remove:
- extract_with_citations_and_tables
- citation_map  
- sections_with_statements
- all_statements
- markdown
- In parse sections: byteoffset, statements
"""

import json
import os
import sys
from pathlib import Path
from copy import deepcopy


def clean_wiki_json(data: dict) -> dict:
    """Clean wiki JSON by removing specified fields."""
    cleaned = deepcopy(data)
    
    # Remove fields from query.pages.*
    if "query" in cleaned and "pages" in cleaned["query"]:
        pages = cleaned["query"]["pages"]
        if isinstance(pages, dict):
            for page_id, page_data in pages.items():
                # Remove top-level fields
                fields_to_remove = [
                    "extract_with_citations_and_tables",
                    "citation_map",
                    "sections_with_statements",
                    "all_statements",
                    "markdown",
                    "lead"
                ]
                for field in fields_to_remove:
                    if field in page_data:
                        del page_data[field]
    
    # Remove fields from parse sections
    if "parse" in cleaned and "sections" in cleaned["parse"]:
        for section in cleaned["parse"]["sections"]:
            if "byteoffset" in section:
                del section["byteoffset"]
            if "statements" in section:
                del section["statements"]
    
    return cleaned


def process_single_file(input_path: str, output_path: str) -> bool:
    """Process a single JSON file."""
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        cleaned = clean_wiki_json(data)
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        print(f"Error processing {input_path}: {e}")
        return False


def process_batch(input_dir: str, output_dir: str) -> tuple:
    """Process all JSON files in a directory."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    success = 0
    failed = 0
    
    json_files = list(input_path.glob("*.json"))
    total = len(json_files)
    
    for i, json_file in enumerate(json_files, 1):
        output_file = output_path / json_file.name
        print(f"[{i}/{total}] Processing: {json_file.name}")
        
        if process_single_file(str(json_file), str(output_file)):
            success += 1
        else:
            failed += 1
    
    return success, failed


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python clean_wiki_json.py <input_path> <output_path> [--batch]")
        print("  Single file: python clean_wiki_json.py input.json output.json")
        print("  Batch mode:  python clean_wiki_json.py input_dir output_dir --batch")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    batch_mode = len(sys.argv) > 3 and sys.argv[3] == "--batch"
    
    if batch_mode:
        success, failed = process_batch(input_path, output_path)
        print(f"\nCompleted: {success} succeeded, {failed} failed")
    else:
        if process_single_file(input_path, output_path):
            print(f"Successfully cleaned: {output_path}")
        else:
            print("Failed to process file")
            sys.exit(1)

