"""
Agency registry for Wiki Live Challenge.

Manages registered agencies for evaluation testing.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any


class AgencyRegistry:
    """
    Registry for managing evaluation agencies.
    
    Agencies must be registered in the agencies.json file before
    they can be processed by the evaluation scripts.
    """
    
    DEFAULT_REGISTRY_NAME = "agencies.json"
    
    def __init__(self, registry_path: Optional[Path] = None):
        """
        Initialize the agency registry.
        
        Args:
            registry_path: Path to agencies.json file.
        """
        self.registry_path = registry_path
        self.data = {}
        self.agencies = {}
        
        if registry_path and registry_path.exists():
            self.load()
    
    def load(self, path: Optional[Path] = None) -> None:
        """
        Load registry from JSON file.
        
        Args:
            path: Optional path to registry file.
        """
        if path:
            self.registry_path = path
        
        if not self.registry_path or not self.registry_path.exists():
            raise FileNotFoundError(f"Registry file not found: {self.registry_path}")
        
        with open(self.registry_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
        
        self.agencies = self.data.get('agencies', {})
    
    def save(self) -> None:
        """Save registry to JSON file."""
        if not self.registry_path:
            raise ValueError("Registry path not set")
        
        self.data['agencies'] = self.agencies
        
        with open(self.registry_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def register(
        self,
        agency_id: str,
        name: str,
        description: str = "",
        has_citations: bool = True,
        enabled: bool = True
    ) -> None:
        """
        Register a new agency.
        
        Args:
            agency_id: Unique identifier (folder name).
            name: Display name.
            description: Description of the agency.
            has_citations: Whether outputs have citation references.
            enabled: Whether agency is enabled for processing.
        """
        self.agencies[agency_id] = {
            "name": name,
            "description": description,
            "has_citations": has_citations,
            "enabled": enabled
        }
    
    def unregister(self, agency_id: str) -> bool:
        """
        Remove an agency from registry.
        
        Args:
            agency_id: Agency identifier to remove.
        
        Returns:
            True if removed, False if not found.
        """
        if agency_id in self.agencies:
            del self.agencies[agency_id]
            return True
        return False
    
    def is_registered(self, agency_id: str) -> bool:
        """Check if an agency is registered."""
        return agency_id in self.agencies
    
    def is_enabled(self, agency_id: str) -> bool:
        """Check if an agency is enabled."""
        agency = self.agencies.get(agency_id, {})
        return agency.get('enabled', False)
    
    def has_citations(self, agency_id: str) -> bool:
        """Check if an agency has citation references."""
        agency = self.agencies.get(agency_id, {})
        return agency.get('has_citations', True)
    
    def get(self, agency_id: str) -> Optional[Dict[str, Any]]:
        """Get agency configuration."""
        return self.agencies.get(agency_id)
    
    def get_all(self, enabled_only: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        Get all registered agencies.
        
        Args:
            enabled_only: If True, only return enabled agencies.
        
        Returns:
            Dictionary of agency configurations.
        """
        if enabled_only:
            return {k: v for k, v in self.agencies.items() if v.get('enabled', True)}
        return self.agencies
    
    def list_ids(self, enabled_only: bool = False) -> List[str]:
        """
        Get list of agency IDs.
        
        Args:
            enabled_only: If True, only return enabled agency IDs.
        
        Returns:
            List of agency identifiers.
        """
        if enabled_only:
            return [k for k, v in self.agencies.items() if v.get('enabled', True)]
        return list(self.agencies.keys())
    
    def validate_directory(self, base_dir: Path) -> Dict[str, Any]:
        """
        Validate that all registered agencies have corresponding directories.
        
        Args:
            base_dir: Base directory containing agency folders.
        
        Returns:
            Validation results with found/missing agencies.
        """
        found = []
        missing = []
        unregistered = []
        
        # Check registered agencies
        for agency_id in self.agencies:
            agency_dir = base_dir / agency_id
            if agency_dir.exists() and agency_dir.is_dir():
                found.append(agency_id)
            else:
                missing.append(agency_id)
        
        # Check for unregistered directories
        if base_dir.exists():
            for item in base_dir.iterdir():
                if item.is_dir() and item.name not in self.agencies:
                    if not item.name.startswith('.') and item.name != '__pycache__':
                        unregistered.append(item.name)
        
        return {
            'found': found,
            'missing': missing,
            'unregistered': unregistered,
            'valid': len(missing) == 0
        }
    
    @classmethod
    def find_registry(cls, start_dir: Path) -> Optional[Path]:
        """
        Find agencies.json file starting from a directory.
        
        Args:
            start_dir: Directory to start searching from.
        
        Returns:
            Path to agencies.json if found, None otherwise.
        """
        current = start_dir
        for _ in range(10):  # Max 10 levels up
            candidate = current / cls.DEFAULT_REGISTRY_NAME
            if candidate.exists():
                return candidate
            
            if current.parent == current:
                break
            current = current.parent
        
        return None
    
    @classmethod
    def load_from_directory(cls, base_dir: Path) -> 'AgencyRegistry':
        """
        Load registry from a directory containing agencies.json.
        
        Args:
            base_dir: Directory containing agencies.json.
        
        Returns:
            Loaded AgencyRegistry instance.
        """
        registry_path = base_dir / cls.DEFAULT_REGISTRY_NAME
        return cls(registry_path)
