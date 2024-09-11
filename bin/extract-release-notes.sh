#!/bin/bash
###############################################################################
#
# A bash script to extract only the notes related to the most recent version of
# the Swath Projector from CHANGELOG.md
#
# 2023-06-16: Created.
# 2023-10-10: Copied from earthdata-varinfo repository to HOSS.
# 2024-01-03: Copied from HOSS repository to the Swath Projector.
# 2024-09-01: Copied and modified from HyBIG repository to handle new format.
#
###############################################################################

CHANGELOG_FILE="CHANGELOG.md"

## captures versions
## >## v1.0.0
## >## [v1.0.0]
VERSION_PATTERN="^## [\[]v"

## captures url links
#[v1.0.0]:(https://github.com/nasa/harmony-swath-projector/releases/tag/1.0.0)
LINK_PATTERN="^\[.*\].*/tag/.*"

# Read the file and extract text between the first two occurrences of the
# VERSION_PATTERN
result=$(awk "/$VERSION_PATTERN/{c++; if(c==2) exit;} c==1" "$CHANGELOG_FILE")

# Print the result
echo "$result" |  grep -v "$VERSION_PATTERN" | grep -v "$LINK_PATTERN"
