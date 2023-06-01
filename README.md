# pakler

Pakler is a command-line tool and library used to manipulate `.pak` firmware files
used by Swann and Reolink devices. You can list, extract, and replace their
content. It makes it easy to explore and patch firmwares used by various
NVRs, DVRs and IP cameras.

## Installing

Note: pakler requires Python 3.6+

### Recommended

```shell
pip install pakler
```

### Manual

```shell
git clone https://github.com/vmallet/pakler
cd pakler
pip install .
```

## Usage

The main commands are:
 * get help: `pakler -h`
 * [list content](#viewing-content-of-pak-files): `pakler file.pak` (or `pakler -l file.pak`)
 * [extract content](#extracting-content-of-pak-files): `pakler file.pak -e -d <directory>`
 * [replace content](#replacing-content-of-pak-files): `pakler file.pak -r -n ... -f ... -o newfile.pak`

Help can be had with:
```shell
pakler -h
```

Note: list and extract also work with ZIPs that contain `.pak` files.

### Viewing content of `.pak` files

Listing the contents of a `.pak` file is pretty straightforward: invoke the
tool with the name of the firmware file on the command line.

```shell
pakler NVR8-7400_1705_3438_1103.pak
```

```
Header  magic=32725913  crc32=0250e72d  type=00002302  sections=<10>  mtd_parts=<10>
    Section  0 name="uboot1"         version="v1.0.0.1"       start=0x00000584  len=0x000437d0  (start=    1412 len=  276432)
    Section  1 name=""               version=""               start=0x00043d54  len=0x00000000  (start=  277844 len=       0)
    Section  2 name="bootargs"       version="v1.0.0.1"       start=0x00043d54  len=0x00020000  (start=  277844 len=  131072)
    Section  3 name="kernel"         version="v1.0.0.1"       start=0x00063d54  len=0x0023fdc8  (start=  408916 len= 2358728)
    Section  4 name="fs"             version="v1.0.0.442"     start=0x002a3b1c  len=0x00402000  (start= 2767644 len= 4202496)
    Section  5 name="app"            version="v1.0.0.421"     start=0x006a5b1c  len=0x00947000  (start= 6970140 len= 9728000)
    Section  6 name=""               version=""               start=0x00fecb1c  len=0x00000000  (start=16698140 len=       0)
    Section  7 name="logo"           version="v1.0.0.1"       start=0x00fecb1c  len=0x0000f1fd  (start=16698140 len=   61949)
    Section  8 name=""               version=""               start=0x00ffbd19  len=0x00000000  (start=16760089 len=       0)
    Section  9 name=""               version=""               start=0x00ffbd19  len=0x00000000  (start=16760089 len=       0)
    Mtd_part name="uboot1"         mtd="/dev/mtd9"       a=0x00000000  start=0x00000000  len=0x00080000
    Mtd_part name="uboot2"         mtd="/dev/mtd9"       a=0x00080000  start=0x00080000  len=0x001e0000
    Mtd_part name="bootargs"       mtd="/dev/mtd9"       a=0x00260000  start=0x00260000  len=0x00020000
    Mtd_part name="kernel"         mtd="/dev/mtd9"       a=0x00280000  start=0x00280000  len=0x00440000
    Mtd_part name="fs"             mtd="/dev/mtd9"       a=0x006c0000  start=0x006c0000  len=0x00c00000
    Mtd_part name="app"            mtd="/dev/mtd9"       a=0x012c0000  start=0x012c0000  len=0x02000000
    Mtd_part name="para"           mtd="/dev/mtd9"       a=0x032c0000  start=0x032c0000  len=0x00800000
    Mtd_part name="logo"           mtd="/dev/mtd9"       a=0x03ac0000  start=0x03ac0000  len=0x00200000
    Mtd_part name="ipc_img"        mtd="/dev/mtd9"       a=0x03cc0000  start=0x03cc0000  len=0x00b00000
    Mtd_part name="version"        mtd="/dev/mtd9"       a=0xffffffff  start=0xffffffff  len=0x00000000
File passes CRC check: NVR8-7400_1705_3438_1103.pak
```

### Extracting content of `.pak` files

Contents of a `.pak` file can be extracted using the `-e` command. If no
output directory is specified using the `-d` parameter, a default unique
output directory will be created by appending `.extracted` to the name of
the `.pak` file.

example:
```shell
pakler ./NT98312_NVR_8IP_REOLINK_L300_130_21060706.pak -e -d newdir
```
```
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

### Replacing content of `.pak` files

A `.pak` file is made up of multiple sections, and at the moment you can
replace only one section at a time. To replace a section you need to 
use the `-r` command, specify the number of the section to replace with `-n`,
the file to use as a replacement with `-f`, and the output file to write
the resulting patched file with `-o`.

Here is an example where we replace the `.pak` file's section #5 with the
file `patched_fs.bin`

```shell
pakler NT98312_NVR_8IP_REOLINK_L300_130_21060706.pak -r -n 5 -f patched_fs.bin -o patched_fw.pak
````

```
Input            : NT98312_NVR_8IP_REOLINK_L300_130_21060706.pak
Output           : patched_fw.pak
Replacing section: 5
Replacement file : new_fs.bin
Copying section 0 (131072 bytes)
Copying section 1 (18096 bytes)
Copying section 2 (26404 bytes)
Copying section 3 (414552 bytes)
Copying section 4 (3022896 bytes)
Replacing section 5 (12210176 bytes) with 12211578 bytes
Copying section 6 (17113088 bytes)
Copying section 7 (0 bytes)
Copying section 8 (122036 bytes)
Copying section 9 (0 bytes)
Copying section 10 (0 bytes)
Writing header... (1552 bytes)
Updating CRC...
Replacement completed. New header:
Header  magic=32725913  crc32=41ee801c  type=00006202  sections=<11>  mtd_parts=<11>
    Section  0 name="header"         version="v1.0.0.0"       start=0x00000610  len=0x00020000  (start=    1552 len=  131072)
    Section  1 name="loader"         version="v1.0.0.0"       start=0x00020610  len=0x000046b0  (start=  132624 len=   18096)
    Section  2 name="fdt"            version="v1.0.0.0"       start=0x00024cc0  len=0x00006724  (start=  150720 len=   26404)
    Section  3 name="uboot"          version="v1.0.0.0"       start=0x0002b3e4  len=0x00065358  (start=  177124 len=  414552)
    Section  4 name="kernel"         version="v1.0.0.0"       start=0x0009073c  len=0x002e2030  (start=  591676 len= 3022896)
    Section  5 name="fs"             version="v1.0.0.0"       start=0x0037276c  len=0x00ba557a  (start= 3614572 len=12211578)
    Section  6 name="app"            version="v1.0.0.0"       start=0x00f17ce6  len=0x01052000  (start=15826150 len=17113088)
    Section  7 name=""               version=""               start=0x01f69ce6  len=0x00000000  (start=32939238 len=       0)
    Section  8 name="logo"           version="v1.0.0.0"       start=0x01f69ce6  len=0x0001dcb4  (start=32939238 len=  122036)
    Section  9 name=""               version=""               start=0x01f8799a  len=0x00000000  (start=33061274 len=       0)
    Section 10 name=""               version=""               start=0x01f8799a  len=0x00000000  (start=33061274 len=       0)
    Mtd_part name="header"         mtd="/dev/mtd9"       a=0x00000000  start=0x00000000  len=0x00020000
    Mtd_part name="loader"         mtd="/dev/mtd9"       a=0x00020000  start=0x00020000  len=0x00080000
    Mtd_part name="fdt"            mtd="/dev/mtd9"       a=0x000a0000  start=0x000a0000  len=0x00080000
    Mtd_part name="uboot"          mtd="/dev/mtd9"       a=0x00120000  start=0x00120000  len=0x000e0000
    Mtd_part name="kernel"         mtd="/dev/mtd9"       a=0x00200000  start=0x00200000  len=0x00500000
    Mtd_part name="fs"             mtd="/dev/mtd9"       a=0x00700000  start=0x00700000  len=0x00f00000
    Mtd_part name="app"            mtd="/dev/mtd9"       a=0x01600000  start=0x01600000  len=0x02000000
    Mtd_part name="para"           mtd="/dev/mtd9"       a=0x03600000  start=0x03600000  len=0x00800000
    Mtd_part name="logo"           mtd="/dev/mtd9"       a=0x03e00000  start=0x03e00000  len=0x00100000
    Mtd_part name="uid"            mtd="/dev/mtd9"       a=0x03f00000  start=0x03f00000  len=0x00100000
    Mtd_part name="version"        mtd="/dev/mtd9"       a=0xffffffff  start=0xffffffff  len=0x00000000
```

### As a library

Here are a few things you can do with pakler's API:

```py
from pakler import PAK

with PAK.from_file("firmware.pak") as pak:  # Also from_bytes() and from_fd()
    assert pak.crc == pak.calc_crc()
    pak.extract("firmware_extracted")
    print(pak.partitions)
    section = pak.sections[0]
    pak.save_section(section, f"{section.name}.bin")
    section_bytes = pak.extract_section(section)
```

## Naming

Why pakler? Take a **pak** and **L**ist it, **E**xtract it, or **R**eplace 
parts of it... pakler? Makes sense! (Naming suggestions are welcome :) )

## Version history

* v0.2.0 - 2023/05/31 - The [AT0myks](https://github.com/AT0myks) release
  
  A big thanks to AT0myks for all the changes brought in this release.
  - Make Pakler usable as a library (author: AT0myks)
  - Support for 64-bit PAK files (author: AT0myks)
  - Support for handling PAK files directly from ZIP archives (author: AT0myks)
  - Several code layout and packaging improvements (author: AT0myks)

* v0.1.0 - 2021/09/03 - Initial release

## Licensing

pakler is licensed under MIT license. See [LICENSE](LICENSE)
