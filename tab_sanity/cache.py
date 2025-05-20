import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import hashlib
import logging
import time
import glob

class PerplexityCache:
    def __init__(self, cache_dir: str = ".perplexity_cache", max_age_days: int = 7):
        self.cache_dir = cache_dir
        self.max_age_days = max_age_days
        self.max_age_seconds = max_age_days * 24 * 60 * 60
        os.makedirs(cache_dir, exist_ok=True)
        print(f"Cache initialized: {cache_dir} (max age: {max_age_days} days)")

    def _get_cache_key(self, api_name: str, model: str, prompt: str, context_url: Optional[str] = None) -> str:
        """Generate a cache key based on API call parameters."""
        # Create a string representation of the API call
        key_parts = [
            f"api={api_name}",
            f"model={model}",
            # Use just a hash of the prompt to keep keys manageable
            f"prompt_hash={hashlib.md5(prompt.encode()).hexdigest()[:16]}"
        ]
        
        # Add context URL if provided
        if context_url:
            key_parts.append(f"url_hash={hashlib.md5(context_url.encode()).hexdigest()[:8]}")
        
        # Create a simpler cache key
        return hashlib.md5("||".join(key_parts).encode()).hexdigest()

    def _get_cache_path(self, key: str) -> str:
        """Generate a cache file path from a key."""
        return os.path.join(self.cache_dir, f"{key}.json")

    def _is_cache_valid(self, cache_data: Dict[str, Any]) -> bool:
        """Check if cache entry is still valid."""
        cache_time = datetime.fromisoformat(cache_data["timestamp"])
        return datetime.now() - cache_time < timedelta(days=self.max_age_days)

    def get(self, api_name: str, model: str, prompt: str, context_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a value from the cache if it exists and is valid."""
        cache_key = self._get_cache_key(api_name, model, prompt, context_url)
        cache_path = self._get_cache_path(cache_key)
        
        print(f"Cache lookup: {cache_key[:8]}... for prompt hash: {hashlib.md5(prompt.encode()).hexdigest()[:8]}...")
        
        if not os.path.exists(cache_path):
            print(f"Cache MISS: file {cache_key[:8]}... not found")
            return None

        try:
            # Check if the file is too old
            file_age = time.time() - os.path.getmtime(cache_path)
            if file_age > self.max_age_seconds:
                print(f"Cache MISS: file {cache_key[:8]}... too old ({file_age/86400:.1f} days)")
                return None
            
            with open(cache_path, 'r') as f:
                cache_data = json.load(f)
            
            if not self._is_cache_valid(cache_data):
                print(f"Cache EXPIRED: file {cache_key[:8]}... too old, removing")
                os.remove(cache_path)
                return None
            
            print(f"Cache HIT: using cached result from {cache_key[:8]}...")
            return cache_data["data"]
        except Exception as e:
            print(f"Cache ERROR: {str(e)}")
            return None

    def set(self, api_name: str, model: str, prompt: str, value: Dict[str, Any], context_url: Optional[str] = None) -> None:
        """Store a value in the cache."""
        cache_key = self._get_cache_key(api_name, model, prompt, context_url)
        cache_path = self._get_cache_path(cache_key)
        cache_data = {
            "timestamp": datetime.now().isoformat(),
            "data": value
        }
        
        print(f"Caching result: {cache_key[:8]}... for prompt hash: {hashlib.md5(prompt.encode()).hexdigest()[:8]}...")
        
        try:
            with open(cache_path, 'w') as f:
                json.dump(cache_data, f)
            
            # Only save the prompt text to a file if it doesn't already exist
            prompt_file_path = os.path.join(self.cache_dir, f"{cache_key}_prompt.txt")
            if not os.path.exists(prompt_file_path):
                with open(prompt_file_path, 'w', encoding='utf-8') as f:
                    f.write(prompt)
                    if context_url:
                        f.write(f"\n\nContext URL: {context_url}")
                print(f"Prompt saved to {os.path.basename(prompt_file_path)}")
            
            print(f"Cache STORED: {cache_key[:8]}...")
        except Exception as e:
            print(f"Cache ERROR storing {cache_key[:8]}: {e}")

    def clear_old_entries(self) -> int:
        """Clear cache entries that are older than max_age_seconds."""
        count = 0
        current_time = time.time()
        
        for file_path in glob.glob(os.path.join(self.cache_dir, "*.json")):
            try:
                file_age = current_time - os.path.getmtime(file_path)
                if file_age > self.max_age_seconds:
                    os.remove(file_path)
                    # Also remove the prompt file if it exists
                    prompt_file = file_path.replace(".json", "_prompt.txt")
                    if os.path.exists(prompt_file):
                        os.remove(prompt_file)
                    count += 1
            except Exception as e:
                print(f"Error clearing cache entry {file_path}: {e}")
        
        if count > 0:
            print(f"Cleared {count} old cache entries")
        
        return count 