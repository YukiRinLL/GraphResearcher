#!/usr/bin/env python3
"""
Clean markdown tables by removing empty columns and fixing Source rows.
"""

import re
import sys
from pathlib import Path


def clean_markdown_tables(content: str) -> str:
    """Clean all tables in markdown content."""
    lines = content.split('\n')
    result = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check if this is a table (starts with |)
        if line.strip().startswith('|'):
            # Collect all table lines
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1
            
            # Process table
            cleaned_table = clean_table(table_lines)
            result.extend(cleaned_table)
        else:
            result.append(line)
            i += 1
    
    return '\n'.join(result)


def clean_table(table_lines: list) -> list:
    """Clean a table by removing empty columns."""
    if not table_lines:
        return table_lines
    
    # Parse table into cells
    rows = []
    for line in table_lines:
        # Clean colspan="99" pattern
        line = re.sub(r'colspan="?\d+"?\s*', '', line)
        
        # Split by | and remove first/last empty
        cells = line.split('|')
        if cells and cells[0].strip() == '':
            cells = cells[1:]
        if cells and cells[-1].strip() == '':
            cells = cells[:-1]
        rows.append([c.strip() for c in cells])
    
    if not rows:
        return table_lines
    
    # Check if this is a Source-only row
    cleaned_rows = []
    for row in rows:
        non_empty = [c for c in row if c]
        # If all non-empty cells are "Source:", keep just one
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
    
    # Find columns that have actual content (excluding separator row)
    cols_with_content = set()
    for row_idx, row in enumerate(rows):
        for col_idx, cell in enumerate(row):
            # Skip separator row check
            if row_idx == 1 and all(c in '- ' for c in cell):
                continue
            if cell and cell != '':
                cols_with_content.add(col_idx)
    
    # Keep only columns with content
    cols_to_keep = sorted(cols_with_content)
    
    # If no columns found, keep first few
    if not cols_to_keep:
        cols_to_keep = list(range(min(4, num_cols)))
    
    # Rebuild rows with only content columns
    final_rows = []
    for row in rows:
        if len(row) == 1 and row[0] == 'Source:':
            # Source row - just keep as is
            final_rows.append(['Source:'])
        else:
            new_row = [row[i] if i < len(row) else '' for i in cols_to_keep]
            final_rows.append(new_row)
    
    # Fix separator row to match header
    if len(final_rows) > 1:
        header_len = len(final_rows[0])
        final_rows[1] = ['---'] * header_len
    
    # Rebuild table lines
    result = []
    for row in final_rows:
        result.append('| ' + ' | '.join(row) + ' |')
    
    return result


def process_file(input_path: str, output_path: str = None) -> bool:
    """Process a single markdown file."""
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        cleaned = clean_markdown_tables(content)
        
        out_path = output_path or input_path
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(cleaned)
        
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


def process_batch(input_dir: str) -> tuple:
    """Process all markdown files in a directory."""
    path = Path(input_dir)
    success = 0
    failed = 0
    
    md_files = list(path.glob("*.md"))
    total = len(md_files)
    
    for i, md_file in enumerate(md_files, 1):
        print(f"[{i}/{total}] Processing: {md_file.name}")
        if process_file(str(md_file)):
            success += 1
        else:
            failed += 1
    
    return success, failed


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python clean_markdown_tables.py <file.md> [output.md]")
        print("       python clean_markdown_tables.py <dir> --batch")
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
