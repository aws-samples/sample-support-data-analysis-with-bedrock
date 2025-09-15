#!/bin/bash

# Script to create a tar.gz archive of all files in the current directory
# Use this script to package generated support cases or other data for the workshop
# Usage: ./create_archive.sh

# Get the current directory name to use as the archive name
DIR_NAME=$(basename "$(pwd)")

# Create timestamp for unique archive name
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Archive filename
ARCHIVE_NAME="${DIR_NAME}_${TIMESTAMP}.tar.gz"

echo "Creating tar.gz archive: $ARCHIVE_NAME"
echo "Archiving all files in: $(pwd)"

# Create the tar.gz archive
# -c: create archive
# -z: compress with gzip
# -f: specify filename
# --exclude: exclude the script itself and any existing .tar.gz files
tar -czf "$ARCHIVE_NAME" --exclude="*.tar.gz" --exclude="create_archive.sh" *

if [ $? -eq 0 ]; then
    echo "Archive created successfully: $ARCHIVE_NAME"
    echo "Archive size: $(du -h "$ARCHIVE_NAME" | cut -f1)"
    echo "Files archived: $(tar -tzf "$ARCHIVE_NAME" | wc -l)"
else
    echo "Error: Failed to create archive"
    exit 1
fi
