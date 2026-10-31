#!/usr/bin/env python3
"""Hygiene check: fail if personal paths appear in tracked files."""

import re
import sys
import glob

# Patterns that should never appear in committed files
FORBIDDEN_PATTERNS = [
    r'C:\\\\Users',
    r'\\.minimax',
    r'[CDE]:\\\\',  # C:\, D:\, E:\
]

# Files to check (tracked files that should be clean)
INCLUDE_GLOBS = [
    'docs/*.txt',
    'scripts/*.py',
    'crates/**/*.rs',
    'README*.md',
    'paper/*.tex',
    'paper/*.bib',
    'CHANGELOG.md',
    'CITATION.cff',
]

def main():
    violations = []
    
    for glob_pattern in INCLUDE_GLOBS:
        for filepath in glob.glob(glob_pattern, recursive=True):
            # Skip the hygiene check script itself
            if filepath.endswith('check_hygiene.py'):
                continue
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                for pattern in FORBIDDEN_PATTERNS:
                    matches = list(re.finditer(pattern, content))
                    if matches:
                        for m in matches:
                            line_no = content[:m.start()].count('\n') + 1
                            violations.append(f"{filepath}:{line_no}: forbidden pattern '{pattern}' matched '{m.group()}'")
            except Exception as e:
                print(f"Warning: could not read {filepath}: {e}", file=sys.stderr)
    
    if violations:
        print("HYGIENE CHECK FAILED:", file=sys.stderr)
        for v in violations:
            print(v, file=sys.stderr)
        return 1
    
    print("HYGIENE CHECK PASSED: no personal paths found in tracked files")
    return 0

if __name__ == '__main__':
    sys.exit(main())