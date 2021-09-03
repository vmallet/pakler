# pakfwtool

Pakfwtool is a command-line tool used to manipulate `.pak` firmware files
used by Swann and Reolink. You can list, extract, and replace their content.
It makes it easy to explore and patch firmwares used by various NVRs, DVRs
and IP cameras.


## Installing / Getting Started

Stuff to install and get started

## Usage

The main commands are:
 * get help: `pakfwtool -h`
 * [list contents](#Viewing-content): `pakfwtool file.pak` (or `pakfwtool -l file.pak`)
 * [extract contents](#Extracting-content): `pakfwtool file.pak -e -d <directory>`
 * replace contents: `pakfwtool file.pak -r -n ... -f ... -o newfile.pak`

Help can be had with:
```shell
pakfwtool -h
```

### Viewing content

```shell
pakfwtool ./NT98312_NVR_8IP_REOLINK_L300_130_21060706.pak
```

### Extracting content
Contents of a `.pak` file can be extracted using the `-e` command. If no output
directory is specified using the `-d` parameter, a default unique output
directory will be created by appending `.extracted` to the name of the `.pak`
file.

example:
```shell
pakfwtool ./NT98312_NVR_8IP_REOLINK_L300_130_21060706.pak -e -d newdir
```
```
Attempting to guess number of sections... guessed: 11
output: newdir
Extracting section 0 (131072 bytes) into newdir/00_header.bin
Extracting section 1 (18096 bytes) into newdir/01_loader.bin
Extracting section 2 (26404 bytes) into newdir/02_fdt.bin
Extracting section 3 (414552 bytes) into newdir/03_uboot.bin
Extracting section 4 (3022896 bytes) into newdir/04_kernel.bin
Extracting section 5 (12210176 bytes) into newdir/05_fs.bin
Extracting section 6 (17113088 bytes) into newdir/06_app.bin
Skipping empty section 7
Extracting section 8 (122036 bytes) into newdir/08_logo.bin
Skipping empty section 9
Skipping empty section 10
```

list example
replace example

## Naming

4Pakfwtool is a mouthful and I don't quite know how to even pronounce it.. but
'paktool' was already used by many projects and I wanted to stick with something
short. Suggestions are welcome :)

## Licensing

Pakfwtool is licensed under MIT license. See [LICENSE](LICENSE)
