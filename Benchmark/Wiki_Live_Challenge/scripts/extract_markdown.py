#!/usr/bin/env python3
"""
Extract markdown content from wiki JSON files and save as .md files.
"""

import json
import os
import sys
from pathlib import Path


def extract_markdown(data: dict) -> tuple:
    """Extract markdown content and title from wiki JSON."""
    title = None
    markdown = None
    
    if "query" in data and "pages" in data["query"]:
        pages = data["query"]["pages"]
        if isinstance(pages, dict):
            for page_id, page_data in pages.items():
                title = page_data.get("title", None)
                markdown = page_data.get("markdown", None)
                break
    
    return title, markdown


def process_single_file(input_path: str, output_path: str) -> bool:
    """Process a single JSON file and extract markdown."""
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        title, markdown = extract_markdown(data)
        
        if markdown is None:
            print(f"Warning: No markdown found in {input_path}")
            return False
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Add title as H1 header
        content = f"# {title}\n\n{markdown}" if title else markdown
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
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
        # Change extension from .json to .md
        md_filename = json_file.stem + ".md"
        output_file = output_path / md_filename
        print(f"[{i}/{total}] Processing: {json_file.name}")
        
        if process_single_file(str(json_file), str(output_file)):
            success += 1
        else:
            failed += 1
    
    return success, failed


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python extract_markdown.py <input_path> <output_path> [--batch]")
        print("  Single file: python extract_markdown.py input.json output.md")
        print("  Batch mode:  python extract_markdown.py input_dir output_dir --batch")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    batch_mode = len(sys.argv) > 3 and sys.argv[3] == "--batch"
    
    if batch_mode:
        success, failed = process_batch(input_path, output_path)
        print(f"\nCompleted: {success} succeeded, {failed} failed")
    else:
        if process_single_file(input_path, output_path):
            print(f"Successfully extracted: {output_path}")
        else:
            print("Failed to process file")
            sys.exit(1)

