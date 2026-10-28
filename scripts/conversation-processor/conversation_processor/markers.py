"""Generic loader marker recognition; hashes are provenance, never identities."""
import re

# Also accept the loader's character-count footer before the closing bracket.
PERSONA_MARKER = r'\[persona sha256=([0-9a-f]{8})(?: 字数=\d+)?\]'


def hashes(text, source):
    pattern = source.get('persona_marker_pattern', PERSONA_MARKER)
    return re.findall(pattern, text)
