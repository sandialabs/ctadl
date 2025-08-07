#!/usr/bin/env python3
import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Generator, Optional


@dataclass(frozen=True)
class TInfo:
    insn: str
    uri: str
    uriBaseId: str
    fileUri: str
    byteOffset: int
    byteLength: int
    startLine: Optional[int]
    startColumn: Optional[int]
    endLine: Optional[int]
    endColumn: Optional[int]


TAINTED_INSTRUCTION_RULE = "C0002"


def get_tainted_instruction_info(cur: sqlite3.Cursor) -> Generator[TInfo, None, None]:
    for (
        insn,
        uri,
        uriBaseId,
        fileUri,
        byteOffset,
        byteLength,
        startLine,
        startColumn,
        endLine,
        endColumn,
    ) in cur.execute(
        """
        SELECT
            insn, ibl.artifactUri, ibl.artifactUriBaseId, cf.uri, ibl.byteOffset, ibl.byteLength,
            startLine, startColumn, endLine, endColumn
        FROM "natural_flow.ReachableEdge"
        JOIN "_InsnBytecodeLocation" ibl USING (insn)
        JOIN "CSourceInfo_Location" csil ON (csil.element = insn)
        JOIN CSourceInfo_File cf ON (csil.file_id = cf.id)
        JOIN CSourceInfo_LineRegion lr ON lr."id" = "region_id"
        LEFT OUTER JOIN CLineRegion_StartColumn sc ON sc."id" = "region_id"
        LEFT OUTER JOIN CLineRegion_EndLine el ON el."id" = "region_id"
        LEFT OUTER JOIN CLineRegion_EndColumn ec ON ec."id" = "region_id"
        """,
    ):
        yield TInfo(
            insn=insn,
            uri=uri,
            uriBaseId=uriBaseId,
            fileUri=fileUri,
            byteOffset=byteOffset,
            byteLength=byteLength,
            startLine=startLine,
            startColumn=startColumn,
            endLine=endLine,
            endColumn=endColumn,
        )


def do_db_files(output, processed_file_names, db_files):
    # [filename][line] = byte_offsets
    file_info = defaultdict(lambda: defaultdict(set))
    for db_file in db_files:
        with sqlite3.connect(db_file) as conn:
            for info in get_tainted_instruction_info(conn.cursor()):
                file_info[info.fileUri][info.startLine].add(info.byteOffset)
        for file_name in processed_file_names:
            output_idx = processed_file_names[file_name]
            byte_offsets = []
            for line_no in output[output_idx]['lineNumbers']:
                try:
                    byte_offsets_entry = file_info[file_name][line_no]
                except (KeyError, IndexError):
                    byte_offsets_entry = []
                byte_offsets.append(sorted(byte_offsets_entry))
            output[output_idx]['byteOffsets'] = byte_offsets
    return output


def do_sarif_files(sarif_files):
    output = []
    # a map indicating what files have been processed and their array index
    processed_file_names = {}
    for sarif_file in sarif_files:
        # file_names[fileName][lineNumber] = ['comments'...]
        file_names = defaultdict(lambda: defaultdict(set))
        with open(sarif_file, 'r') as f:
            sarif_data = json.load(f)
        for run in sarif_data['runs']:
            for result in run['results']:
                if result['ruleId'] == TAINTED_INSTRUCTION_RULE:
                    try:
                        fileName = result['locations'][0]['physicalLocation']['artifactLocation']['uri']
                        lineNumber = result['locations'][0]['physicalLocation']['region']['startLine']
                        comments = set()
                    except (KeyError, IndexError):
                        # result is malformed or no physical location; we expect results with no physical location, so
                        # don't print a warning
                        continue
                    try:
                        comments = set(result['properties']['additionalProperties']['taintLabels'])
                    except (KeyError, IndexError):
                        print('Warning: result had no taint labels', file=sys.stderr)
                        pass
                    file_names[fileName][lineNumber].update(comments)
        for file_name in file_names:
            if file_name in processed_file_names:
                print(f'Warning: ignoring duplicate lines for file {file_name}', file=sys.stderr)
                continue
            processed_file_names[file_name] = len(output)
            obj = {'fileName': file_name, 'lineNumbers': [], 'comments': []}
            for line_number in sorted(file_names[file_name]):
                comments = ', '.join(file_names[file_name][line_number])
                obj['lineNumbers'].append(line_number)
                obj['comments'].append(comments)
            output.append(obj)
    return output, processed_file_names


def main():
    parser = argparse.ArgumentParser(description='''Outputs a .json file that indicates tainted file/byte offsets to
                                     highlight, sent to stdout. Takes in one or more sarif files with
                                     sarif+instructions or ctadlir.db files (needed for byte offsets).''')
    parser.add_argument('-d', '--db', action='store_true',
                        help='''Take in ctadlir.db files in addition to sarif; required for byte offset info for jadx.
                        In this case, the .db files come after the sarif files, with one expected for each, e.g.:
                        "a.sarif b.sarif a/ctadlir.db b/ctadlir.db"''')
    parser.add_argument('filenames', nargs="+")
    # {entries: ['fileName': file_name, 'lineNumbers': [], 'comments': [], 'byteOffsets': [[]]]}
    # line numbers are sorted; comments and byte offsets indices correspond to line number indices (and have same size)
    # byteOffsets is optional and may be empty; each sub-entry is also sorted
    args = parser.parse_args()
    input_files = args.filenames
    if args.db:
        mid_point = len(input_files) // 2
        sarif_files = input_files[:mid_point]
        db_files = input_files[mid_point:]
        if len(sarif_files) != len(db_files):
            raise RuntimeError('Need to give same number of sarif and db files')
        output, processed_file_names = do_sarif_files(sarif_files)
        output = do_db_files(output, processed_file_names, db_files)
    else:
        output, _ = do_sarif_files(input_files)
    print(json.dumps({'entries': output}))


if __name__ == '__main__':
    main()
