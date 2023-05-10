#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2021 Vincent Mallet <vmallet@gmail.com>
# SPDX-License-Identifier: MIT

import argparse
import sys
import textwrap
from pathlib import Path
from zipfile import ZipFile, is_zipfile

from . import PAK, __version__, check_crc, is_pak_file, replace_section

EPILOG_MARKER = "##MYEPILOG##"


class EpilogizerHelpFormatter(argparse.HelpFormatter):
    """
    Help message formatter which injects a pre-formatted epilog text if the text to be formatted is the EPILOG_MARKER.
    """

    def __init__(self, prog, indent_increment=2, max_help_position=24, width=None) -> None:
        super().__init__(prog, indent_increment, max_help_position, width)
        self._my_prog = prog
        self._my_indent = ' ' * indent_increment

    def _fill_text(self, text, width, indent):
        if text == EPILOG_MARKER:
            return make_epilogue_text(self._my_prog, self._my_indent, width)
        return super()._fill_text(text, width, indent)


def make_epilogue_text(prog, indent, width):
    lines = [
        f'{prog} ~/fw/CAM_FW.pak',
        'List the content of CAM_FW.pak, auto-detecting the number of sections',
        '',
        f'{prog} ~/fw/CAM_FW.pak -e -d /tmp/extracted/',
        'Extract all sections of CAM_FW.pak into /tmp/extracted',
        '',
        f'{prog} ~/fw/CAM_FW.pak -r -n 4 -f ~/fw/new_fs.cramfs -o ~/fw/CAM_FW_PATCHED.pak',
        'From firmware file ~/fw/CAM_FW.pak, replace the 4th section with new file ~/fw/new_fs.cramfs, writing'
        ' the output to ~/fw/CAM_FW_PATCHED.pak'
    ]

    wrapper = textwrap.TextWrapper(width, initial_indent=indent, subsequent_indent=indent)

    return "\n".join(["examples:"] + [wrapper.fill(line) for line in lines])


def find_new_name(base: Path):
    name = base
    suffix = 0
    while name.exists():
        suffix += 1
        if suffix == 1000:
            raise Exception(f"Could not find a non-existing file/directory for base: {base}")
        name = base.with_name(f"{base.name}.{suffix:03}")

    return name


def make_output_file_name(filename: Path):
    base = filename.with_name(filename.name + ".replaced")
    return find_new_name(base)


def make_output_dir_name(filename: Path):
    base = filename.with_name(filename.name + ".extracted")
    return find_new_name(base)


def parse_args():
    parser = argparse.ArgumentParser(
        description=f'%(prog)s {__version__} (by Vincent Mallet 2021) - manipulate Swann / Reolink PAK firmware files',
        formatter_class=EpilogizerHelpFormatter,
        epilog=EPILOG_MARKER)

    parser.add_argument('-v', '--version', action='version', version=f"%(prog)s {__version__}")

    pgroup = parser.add_mutually_exclusive_group()
    pgroup.add_argument('-l', '--list', dest='list', action='store_true',
                        help='List contents of PAK firmware file (default)')
    pgroup.add_argument('-r', '--replace', dest='replace', action='store_true',
                        help='Replace a section into a new PAK file')
    pgroup.add_argument('-e', '--extract', dest='extract', action='store_true',
                        help='Extract sections to a directory')
    parser.add_argument('-f', '--section-file', dest='section_file', type=Path, help='Input binary file for section replacement')
    parser.add_argument('-n', '--section-num', dest='section_num', type=int, help='Section number of replaced section')
    parser.add_argument('-o', '--output', dest='output_pak', type=Path, help='Name of output PAK file when replacing a section')
    parser.add_argument('-d', '--output-dir', dest='output_dir', type=Path,
                        help='Name of output directory when extracting sections')
    parser.add_argument('--empty', dest='include_empty', action='store_true',
                        help='Include empty sections when extracting')
    parser.add_argument('filename', type=Path, help='Name of PAK firmware file')

    args = parser.parse_args()

    # Set default action as "list"
    if not (args.list or args.replace or args.extract):
        args.list = True

    return args


def main():
    args = parse_args()
    filename = args.filename

    if not is_pak_file(filename) and not is_zipfile(filename):
        sys.exit("error: file is not a PAK or a ZIP, or doesn't exist")

    if args.list:
        if is_pak_file(filename):
            with PAK.from_file(filename) as pak:
                pak.header.print_debug()
                check_crc(filename)
        else:
            with ZipFile(filename) as myzip:
                for name in myzip.namelist():
                    with myzip.open(name) as file:
                        if is_pak_file(file):
                            with PAK.from_fd(file, closefd=False) as pak:
                                pak.header.print_debug()
                            check_crc(file)

    elif args.extract:
        output_dir = args.output_dir or make_output_dir_name(filename)
        print(f"output: {output_dir}")
        if is_pak_file(filename):
            with PAK.from_file(filename) as pak:
                pak.extract(output_dir, args.include_empty, quiet=False)
        else:
            with ZipFile(filename) as myzip:
                for name in myzip.namelist():
                    with myzip.open(name) as file:
                        if is_pak_file(file):
                            with PAK.from_fd(file) as pak:
                                pak.extract(output_dir, args.include_empty, quiet=False)
                            # If the ZIP has multiple PAKs, generate a new directory name.
                            output_dir = make_output_dir_name(output_dir)

    elif args.replace:
        if not args.section_file or not args.section_num:
            raise Exception("replace error: need both section binary file and section number to do a replacement;"
                            " see help")
        output_file = args.output_pak or make_output_file_name(filename)
        replace_section(filename, args.section_file, args.section_num, output_file)


if __name__ == "__main__":
    main()
