#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

echo "Başlangıç: ffmpeg kurulumu"

# Create a directory to download and extract ffmpeg
mkdir -p /tmp/ffmpeg
cd /tmp/ffmpeg

# Download a static build of ffmpeg
# Using a known static build from johnvansickle.com
echo "ffmpeg indiriliyor..."
curl -L "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz" -o ffmpeg.tar.xz

# Extract the archive
echo "ffmpeg çıkarılıyor..."
tar -xf ffmpeg.tar.xz

# Find the ffmpeg binary and move it to a directory in the PATH
# The extracted folder is named something like ffmpeg-4.4-amd64-static
echo "ffmpeg /usr/local/bin/ dizinine taşınıyor..."
mv ffmpeg-*-amd64-static/ffmpeg /usr/local/bin/

# Clean up the downloaded files
cd /
rm -rf /tmp/ffmpeg

# Verify that ffmpeg is installed and accessible
echo "ffmpeg kurulumu doğrulanyor..."
ffmpeg -version

echo "Bitiş: ffmpeg başarıyla kuruldu."
