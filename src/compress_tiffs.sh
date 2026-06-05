#!/bin/bash
# Script assuring TIF/TIFF files in a given directory tree
# (passed as a first parameter or a current working dir otherwise)
# are LZW-compressed.
# copied from https://github.com/acdh-oeaw/arche-curationTools/blob/master/tif_lzw.sh
#
# Uses gdal_translate for the LZW compression and then copies
# image metadata using the exiftool

TARGET_DIR="${1:-.}"
cd "$TARGET_DIR" || exit 1

echo "Processing directory $(pwd) recursively"

find . -type f \( -iname '*.tif' -o -iname '*.tiff' \) -print0 |
while IFS= read -r -d '' F ; do
    gdalinfo "$F" | grep -q 'COMPRESSION=LZW'
    FLAG_NC="$?"
    FLAG_T=$(gdalinfo "$F" | grep -E 'Block=[0-9]+x1 ' | wc -l)
    if [ "$FLAG_NC" != "0" ] || [ "$FLAG_T" != "0" ] ; then
        echo "  Compressing $F"
        FTMP="$(dirname "$F")/__tmp__$(basename "$F")"
        gdal_translate -co "COMPRESS=LZW" -co "PREDICTOR=2" -co "TILED=YES" "$F" "$FTMP" >/dev/null 2>&1 &&
        exiftool -m -overwrite_original_in_place -tagsFromFile "$F" "$FTMP" >/dev/null 2>&1 &&
        mv "$FTMP" "$F"
        if [ "$?" != "0" ] ; then
            echo "    failed"
        fi
	rm -f "$FTMP"
    fi
done