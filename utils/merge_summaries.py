import json
import sys

if len(sys.argv) < 2:
    print(f'Usage {sys.argv[0]} <out_file> <in_file1> <in_file2> ...')
    sys.exit(1)
out_file = sys.argv[1]
in_files = sys.argv[2:]
if len(in_files) < 2:
    print('You need to merge at least two files')
    sys.exit(1)

mega_json_file = None
for fname in in_files:
    with open(fname) as f:
        jdata = json.load(f)
        if mega_json_file is None:
            mega_json_file = jdata
        else:
            mega_json_file['model_generators'].extend(jdata['model_generators'])
with open(out_file, 'w') as f:
    json.dump(mega_json_file, f)
