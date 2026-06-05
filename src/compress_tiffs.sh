#!/bin/bash
# Script assuring TIF/TIFF files in a given directory tree
# (derived from PROTOCOL_DIR/PROTOCOL_ID environment variables)
# are LZW-compressed.
# copied from https://github.com/acdh-oeaw/arche-curationTools/blob/master/tif_lzw.sh
#
# Uses gdal_translate for the LZW compression and then copies
# image metadata using the exiftool

if [ -z "${PROTOCOL_DIR:-}" ] || [ -z "${PROTOCOL_ID:-}" ]; then
    echo "Error: PROTOCOL_DIR and PROTOCOL_ID must be set in the environment."
    echo "Hint: source ./set_protocol_id.sh"
    exit 1
fi

TARGET_DIR="${PROTOCOL_DIR%/}/${PROTOCOL_ID}"
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