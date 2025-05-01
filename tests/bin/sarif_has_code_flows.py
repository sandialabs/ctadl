#!/usr/bin/env python3

import json
import sys

def main():
    with open(sys.argv[1], 'r') as fd:
        sarif = json.loads(fd.read())
        try:
            for run in sarif.get('runs', []):
                for result in run.get('results', []):
                    if result.get('ruleId') == 'C0001':
                        return 0
        except:
            pass
        return 1

if __name__ == '__main__':
    exit(main())
