
#!/usr/bin/env python3
"""
Alias for the refactored AIAPIClient in src/shared/ai_client/.
This maintains backward compatibility for imports.
"""

from shared.ai_client import AIAPIClient

# Create a singleton instance for backward compatibility
ai_client = AIAPIClient()

# Expose both the class and the instance
__all__ = ['AIAPIClient', 'ai_client']
