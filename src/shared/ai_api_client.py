
#!/usr/bin/env python3
"""
Alias for the refactored AIAPIClient in src/shared/ai_client/.
This maintains backward compatibility for imports.
"""

from shared.ai_client import AIAPIClient

# Expose the class directly
__all__ = ['AIAPIClient']
