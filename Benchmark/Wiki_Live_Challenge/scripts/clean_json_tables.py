#!/usr/bin/env python3
"""
Clean markdown tables in JSON files (extract_with_tables and tables[].markdown).
"""

import json
import sys
from pathlib import Path
from copy import deepcopy


def clean_table(table_lines: list) -> list:
    """Clean a table by removing empty columns."""
    if not table_lines:
        return table_lines
    
    # Parse table into cells
    rows = []
    for line in table_lines:
        # Clean colspan="99" pattern
        import re
        line = re.sub(r'colspan="?\d+"?\s*', '', line)
        
        cells = line.split('|')
        if cells and cells[0].strip() == '':
            cells = cells[1:]
        if cells and cells[-1].strip() == '':
            cells = cells[:-1]
        rows.append([c.strip() for c in cells])
    
    if not rows:
        return table_lines
    
    # Handle Source-only rows
    cleaned_rows = []
    for row in rows:
        non_empty = [c for c in row if c]
        if non_empty and all(c == 'Source:' for c in non_empty):
            cleaned_rows.append(['Source:'])
        else:
            cleaned_rows.append(row)
    rows = cleaned_rows
    
    # Find max columns
    num_cols = max(len(row) for row in rows)
    
    # Normalize row lengths
    for row in rows:
        while len(row) < num_cols:
            row.append('')
    
    # Find columns with content
    cols_with_content = set()
    for row_idx, row in enumerate(rows):
        for col_idx, cell in enumerate(row):
            if row_idx == 1 and all(c in '- ' for c in cell):
                continue
            if cell:
                cols_with_content.add(col_idx)
    
    cols_to_keep = sorted(cols_with_content)
    if not cols_to_keep:
        cols_to_keep = list(range(min(4, num_cols)))
    
    # Rebuild rows
    final_rows = []
    for row in rows:
        if len(row) == 1 and row[0] == 'Source:':
            final_rows.append(['Source:'])
        else:
            new_row = [row[i] if i < len(row) else '' for i in cols_to_keep]
            final_rows.append(new_row)
    
    # Fix separator row
    if len(final_rows) > 1:
        header_len = len(final_rows[0])
        final_rows[1] = ['---'] * header_len
    
    # Rebuild lines
    result = []
    for row in final_rows:
        result.append('| ' + ' | '.join(row) + ' |')
    
    return result


def clean_markdown_text(text: str) -> str:
    """Clean all tables in a markdown text."""
    lines = text.split('\n')
    result = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        if line.strip().startswith('|'):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1
            
            cleaned = clean_table(table_lines)
            result.extend(cleaned)
        else:
            result.append(line)
            i += 1
    
    return '\n'.join(result)


def clean_table_markdown(md: str) -> str:
    """Clean a single table markdown string."""
    lines = md.split('\n')
    cleaned = clean_table(lines)
    return '\n'.join(cleaned)


def clean_wiki_json(data: dict) -> dict:
    """Clean tables in wiki JSON."""
    cleaned = deepcopy(data)
    
    if "query" in cleaned and "pages" in cleaned["query"]:
        pages = cleaned["query"]["pages"]
        if isinstance(pages, dict):
            for page_id, page_data in pages.items():
                # Clean extract_with_tables
                if "extract_with_tables" in page_data:
                    page_data["extract_with_tables"] = clean_markdown_text(
                        page_data["extract_with_tables"]
                    )
                
                # Clean tables[].markdown
                if "tables" in page_data:
                    for table in page_data["tables"]:
                        if "markdown" in table:
                            table["markdown"] = clean_table_markdown(table["markdown"])
    
    return cleaned


def process_file(input_path: str, output_path: str = None) -> bool:
    """Process a single JSON file."""
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        cleaned = clean_wiki_json(data)
        
        out_path = output_path or input_path
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


def process_batch(input_dir: str) -> tuple:
    """Process all JSON files in a directory."""
    path = Path(input_dir)
    success = 0
    failed = 0
    
    json_files = list(path.glob("*.json"))
    total = len(json_files)
    
    for i, json_file in enumerate(json_files, 1):
        print(f"[{i}/{total}] Processing: {json_file.name}")
        if process_file(str(json_file)):
            success += 1
        else:
            failed += 1
    
    return success, failed


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python clean_json_tables.py <file.json> [output.json]")
        print("       python clean_json_tables.py <dir> --batch")
        sys.exit(1)
    
    if len(sys.argv) > 2 and sys.argv[2] == "--batch":
        success, failed = process_batch(sys.argv[1])
        print(f"\nCompleted: {success} succeeded, {failed} failed")
    else:
        output = sys.argv[2] if len(sys.argv) > 2 else None
        if process_file(sys.argv[1], output):
            print(f"Cleaned: {output or sys.argv[1]}")
        else:
            sys.exit(1)
