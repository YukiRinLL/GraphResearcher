#!/usr/bin/env python3
"""
Markdown Preprocessing Script

Normalizes markdown files to a standard format:
- Converts various heading formats to standard Markdown
- Normalizes reference format to [n] url
- Removes duplicate entries
- Cleans up whitespace

Usage:
    # Process single file
    python scripts/preprocess_md.py -i input.md -o output.md
    
    # Process directory in place
    python scripts/preprocess_md.py -i data/md_data/ --in-place
    
    # Process directory to new location
    python scripts/preprocess_md.py -i data/raw_md/ -o data/md_data/
    
    # Detect format only (no modification)
    python scripts/preprocess_md.py -i input.md --detect-only
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.md_normalizer import MDNormalizer


def main():
    parser = argparse.ArgumentParser(
        description='Preprocess and normalize markdown files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '-i', '--input',
        type=str,
        required=True,
        help='Input file or directory'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        default=None,
        help='Output file or directory (default: print to stdout for single file)'
    )
    
    parser.add_argument(
        '--in-place',
        action='store_true',
        help='Modify files in place (for directory processing)'
    )
    
    parser.add_argument(
        '--detect-only',
        action='store_true',
        help='Only detect format, do not normalize'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else None
    
    normalizer = MDNormalizer()
    
    if input_path.is_file():
        # Single file processing
        content = input_path.read_text(encoding='utf-8')
        
        if args.detect_only:
            fmt = normalizer.detect_format(content)
            print(f"Detected format: {fmt}")
            return
        
        normalized = normalizer.normalize(content)
        
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(normalized, encoding='utf-8')
            print(f"Normalized: {input_path} -> {output_path}")
        elif args.in_place:
            input_path.write_text(normalized, encoding='utf-8')
            print(f"Normalized in place: {input_path}")
        else:
            print(normalized)
    
    elif input_path.is_dir():
        # Directory processing
        md_files = list(input_path.glob('*.md'))
        
        if not md_files:
            print(f"No .md files found in {input_path}")
            return
        
        print(f"Found {len(md_files)} markdown files")
        
        if args.detect_only:
            # Detect formats
            formats = {}
            for md_file in md_files:
                content = md_file.read_text(encoding='utf-8')
                fmt = normalizer.detect_format(content)
                formats[fmt] = formats.get(fmt, 0) + 1
            
            print("\nFormat distribution:")
            for fmt, count in sorted(formats.items(), key=lambda x: -x[1]):
                print(f"  {fmt}: {count}")
            return
        
        # Normalize files
        stats = normalizer.process_directory(
            input_path,
            output_dir=output_path,
            in_place=args.in_place
        )
        
        print(f"\nProcessed: {stats['processed']}")
        print(f"Errors: {stats['errors']}")
        
        if output_path:
            print(f"Output: {output_path}")
    
    else:
        print(f"Error: {input_path} does not exist")
        sys.exit(1)


if __name__ == '__main__':
    main()
