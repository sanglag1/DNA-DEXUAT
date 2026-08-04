"""
Unified Pattern Cache Utility for Steel Cutting Optimization.

Provides atomic read/write operations for pickle files with metadata support.
All optimization modules should use this class for consistent cache management.
"""

import hashlib
import json
import os
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class PatternCache:
    """
    Unified cache manager for optimization patterns.
    
    Features:
    - Atomic writes (temp file + rename) to prevent corruption
    - Metadata JSON for debugging and cache validation
    - Consistent folder structure across all modules
    - Cache versioning for compatibility checks
    """
    
    VERSION = "1.0"  # Bump this when format changes to invalidate old caches
    DEFAULT_CACHE_DIR = "patterns_cache"
    
    def __init__(self, cache_dir: Optional[str] = None, base_dir: Optional[Path] = None):
        """
        Initialize cache manager.
        
        Args:
            cache_dir: Name of cache directory (default: 'patterns_cache')
            base_dir: Base directory for cache (default: project root)
        """
        if base_dir is None:
            base_dir = Path(__file__).resolve().parents[1]  # Project root
        
        self.cache_dir = base_dir / (cache_dir or self.DEFAULT_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def generate_cache_key(params: Dict[str, Any], use_md5: bool = False) -> str:
        """
        Generate a unique cache key from parameters.
        
        Args:
            params: Dictionary of parameters to hash
            use_md5: Use MD5 instead of SHA256 (shorter key, for compatibility)
        
        Returns:
            Hex digest of hash
        """
        # Sort keys for consistent ordering
        params_string = json.dumps(params, sort_keys=True, ensure_ascii=False)
        
        if use_md5:
            return hashlib.md5(params_string.encode('utf-8')).hexdigest()
        else:
            return hashlib.sha256(params_string.encode('utf-8')).hexdigest()[:16]
    
    def _get_paths(self, cache_key: str) -> Tuple[Path, Path]:
        """Get pickle and metadata file paths for a cache key."""
        pkl_path = self.cache_dir / f"patterns_{cache_key}.pkl"
        meta_path = self.cache_dir / f"patterns_{cache_key}_metadata.json"
        return pkl_path, meta_path
    
    def exists(self, cache_key: str) -> bool:
        """Check if cache exists for given key."""
        pkl_path, _ = self._get_paths(cache_key)
        return pkl_path.exists()
    
    def save(
        self,
        cache_key: str,
        data: Any,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Save data to cache with atomic write.
        
        Args:
            cache_key: Unique key for this cache entry
            data: Data to pickle (patterns, solutions, etc.)
            metadata: Optional metadata dict to save alongside
        
        Returns:
            True if successful, False otherwise
        """
        pkl_path, meta_path = self._get_paths(cache_key)
        tmp_path = pkl_path.with_suffix('.pkl.tmp')
        
        try:
            # Atomic write: write to temp file first, then rename
            with open(tmp_path, 'wb') as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
            
            # Atomic rename (safe on POSIX systems)
            os.replace(tmp_path, pkl_path)
            
            # Save metadata
            meta = {
                'cache_version': self.VERSION,
                'cache_key': cache_key,
                'created_at': datetime.now().isoformat(),
                'data_type': type(data).__name__,
                **(metadata or {})
            }
            
            # Count items if possible
            if hasattr(data, '__len__'):
                meta['item_count'] = len(data)
            
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            print(f"⚠️ Cache save error: {e}<br>")
            # Cleanup temp file if exists
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except:
                    pass
            return False
    
    def load(
        self,
        cache_key: str,
        validate_version: bool = True
    ) -> Optional[Any]:
        """
        Load data from cache.
        
        Args:
            cache_key: Unique key for this cache entry
            validate_version: Check cache version compatibility
        
        Returns:
            Cached data or None if not found/invalid
        """
        pkl_path, meta_path = self._get_paths(cache_key)
        
        if not pkl_path.exists():
            return None
        
        try:
            # Check version compatibility if metadata exists
            if validate_version and meta_path.exists():
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                
                cached_version = meta.get('cache_version', '0.0')
                if cached_version != self.VERSION:
                    print(f"⚠️ Cache version mismatch ({cached_version} != {self.VERSION}), regenerating...<br>")
                    return None
            
            # Load pickle data
            with open(pkl_path, 'rb') as f:
                data = pickle.load(f)
            
            return data
            
        except (pickle.PickleError, EOFError, IOError) as e:
            print(f"⚠️ Cache load error (will regenerate): {e}<br>")
            return None
    
    def get_metadata(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a cache entry."""
        _, meta_path = self._get_paths(cache_key)
        
        if not meta_path.exists():
            return None
        
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    
    def delete(self, cache_key: str) -> bool:
        """Delete a cache entry."""
        pkl_path, meta_path = self._get_paths(cache_key)
        
        try:
            if pkl_path.exists():
                pkl_path.unlink()
            if meta_path.exists():
                meta_path.unlink()
            return True
        except Exception as e:
            print(f"⚠️ Cache delete error: {e}<br>")
            return False
    
    def clear_all(self) -> int:
        """Delete all cache files. Returns count of files deleted."""
        count = 0
        for f in self.cache_dir.glob("patterns_*.pkl"):
            try:
                f.unlink()
                count += 1
            except:
                pass
        for f in self.cache_dir.glob("patterns_*_metadata.json"):
            try:
                f.unlink()
                count += 1
            except:
                pass
        return count
    
    def list_entries(self) -> list:
        """List all cache entries with metadata."""
        entries = []
        for pkl_file in sorted(self.cache_dir.glob("patterns_*.pkl")):
            if pkl_file.name.endswith('_metadata.json'):
                continue
            
            cache_key = pkl_file.stem.replace('patterns_', '')
            meta = self.get_metadata(cache_key)
            
            entries.append({
                'cache_key': cache_key,
                'file_path': str(pkl_file),
                'size_bytes': pkl_file.stat().st_size,
                'metadata': meta
            })
        
        return entries


# Convenience function for quick access
_default_cache: Optional[PatternCache] = None

def get_pattern_cache() -> PatternCache:
    """Get the default pattern cache instance."""
    global _default_cache
    if _default_cache is None:
        _default_cache = PatternCache()
    return _default_cache
