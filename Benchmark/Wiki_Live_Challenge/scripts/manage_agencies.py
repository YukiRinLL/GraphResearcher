#!/usr/bin/env python3
"""
Agency Management Script

Manage registered agencies for Wiki Live Challenge evaluation.

Usage:
    # List all registered agencies
    python scripts/manage_agencies.py list
    
    # Register a new agency
    python scripts/manage_agencies.py register my_agency --name "My Agency" --desc "Description"
    
    # Unregister an agency
    python scripts/manage_agencies.py unregister my_agency
    
    # Validate registry against directory
    python scripts/manage_agencies.py validate
    
    # Enable/disable an agency
    python scripts/manage_agencies.py enable my_agency
    python scripts/manage_agencies.py disable my_agency
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agency_registry import AgencyRegistry


def cmd_list(args, registry: AgencyRegistry):
    """List all registered agencies."""
    agencies = registry.get_all()
    
    if not agencies:
        print("No agencies registered.")
        return
    
    print(f"Registered agencies ({len(agencies)}):\n")
    
    for agency_id, info in sorted(agencies.items()):
        status = "✓" if info.get('enabled', True) else "✗"
        citations = "has_citations" if info.get('has_citations', True) else "no_citations"
        print(f"  [{status}] {agency_id}")
        print(f"      Name: {info.get('name', agency_id)}")
        print(f"      Description: {info.get('description', 'N/A')}")
        print(f"      Citations: {citations}")
        print()


def cmd_register(args, registry: AgencyRegistry):
    """Register a new agency."""
    if registry.is_registered(args.agency_id):
        print(f"Agency '{args.agency_id}' is already registered.")
        if not args.force:
            print("Use --force to update.")
            return
    
    registry.register(
        agency_id=args.agency_id,
        name=args.name or args.agency_id,
        description=args.desc or "",
        has_citations=not args.no_citations,
        enabled=True
    )
    registry.save()
    
    print(f"Registered agency: {args.agency_id}")
    print(f"  Name: {args.name or args.agency_id}")
    print(f"  Description: {args.desc or 'N/A'}")
    print(f"  Has citations: {not args.no_citations}")


def cmd_unregister(args, registry: AgencyRegistry):
    """Unregister an agency."""
    if not registry.is_registered(args.agency_id):
        print(f"Agency '{args.agency_id}' is not registered.")
        return
    
    registry.unregister(args.agency_id)
    registry.save()
    
    print(f"Unregistered agency: {args.agency_id}")


def cmd_validate(args, registry: AgencyRegistry):
    """Validate registry against directory."""
    base_dir = registry.registry_path.parent
    result = registry.validate_directory(base_dir)
    
    print(f"Validation results for: {base_dir}\n")
    
    if result['found']:
        print(f"Found ({len(result['found'])}):")
        for agency_id in sorted(result['found']):
            print(f"  ✓ {agency_id}")
    
    if result['missing']:
        print(f"\nMissing directories ({len(result['missing'])}):")
        for agency_id in sorted(result['missing']):
            print(f"  ✗ {agency_id}")
    
    if result['unregistered']:
        print(f"\nUnregistered directories ({len(result['unregistered'])}):")
        for name in sorted(result['unregistered']):
            print(f"  ? {name}")
    
    print(f"\nValid: {result['valid']}")


def cmd_enable(args, registry: AgencyRegistry):
    """Enable an agency."""
    if not registry.is_registered(args.agency_id):
        print(f"Agency '{args.agency_id}' is not registered.")
        return
    
    agency = registry.get(args.agency_id)
    agency['enabled'] = True
    registry.save()
    
    print(f"Enabled agency: {args.agency_id}")


def cmd_disable(args, registry: AgencyRegistry):
    """Disable an agency."""
    if not registry.is_registered(args.agency_id):
        print(f"Agency '{args.agency_id}' is not registered.")
        return
    
    agency = registry.get(args.agency_id)
    agency['enabled'] = False
    registry.save()
    
    print(f"Disabled agency: {args.agency_id}")


def main():
    parser = argparse.ArgumentParser(
        description='Manage registered agencies for Wiki Live Challenge',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--registry', '-r',
        type=str,
        default=str(PROJECT_ROOT / 'data/2025_Mar_Nov/test_data/agencies.json'),
        help='Path to agencies.json file'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # list command
    list_parser = subparsers.add_parser('list', help='List all registered agencies')
    
    # register command
    reg_parser = subparsers.add_parser('register', help='Register a new agency')
    reg_parser.add_argument('agency_id', help='Agency identifier (folder name)')
    reg_parser.add_argument('--name', '-n', help='Display name')
    reg_parser.add_argument('--desc', '-d', help='Description')
    reg_parser.add_argument('--no-citations', action='store_true', help='Agency has no citation references')
    reg_parser.add_argument('--force', '-f', action='store_true', help='Force update if exists')
    
    # unregister command
    unreg_parser = subparsers.add_parser('unregister', help='Unregister an agency')
    unreg_parser.add_argument('agency_id', help='Agency identifier to remove')
    
    # validate command
    val_parser = subparsers.add_parser('validate', help='Validate registry against directory')
    
    # enable command
    en_parser = subparsers.add_parser('enable', help='Enable an agency')
    en_parser.add_argument('agency_id', help='Agency identifier')
    
    # disable command
    dis_parser = subparsers.add_parser('disable', help='Disable an agency')
    dis_parser.add_argument('agency_id', help='Agency identifier')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Load registry
    registry_path = Path(args.registry)
    if not registry_path.exists():
        print(f"Registry file not found: {registry_path}")
        sys.exit(1)
    
    registry = AgencyRegistry(registry_path)
    
    # Execute command
    commands = {
        'list': cmd_list,
        'register': cmd_register,
        'unregister': cmd_unregister,
        'validate': cmd_validate,
        'enable': cmd_enable,
        'disable': cmd_disable,
    }
    
    commands[args.command](args, registry)


if __name__ == '__main__':
    main()
