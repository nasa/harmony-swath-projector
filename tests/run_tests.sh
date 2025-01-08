#!/bin/sh

# Exit status used to report back to caller
#
STATUS=0

export HDF5_DISABLE_VERSION_CHECK=1

# Run the standard set of unittests, producing JUnit compatible output
#
coverage run -m xmlrunner discover tests -o tests/reports

RESULT=$?
if [ "$RESULT" -ne "0" ]; then
    STATUS=1
    echo "ERROR: unittest generated errors"
fi


echo "Test Coverage Estimates"
coverage report --omit="tests/*"
coverage html --omit="tests/*" -d /home/tests/coverage


# Run pylint
#
pylint swath_projector --disable=E0401 --extension-pkg-whitelist=netCDF4
RESULT=$?
RESULT=$((3 & $RESULT))
if [ "$RESULT" -ne "0" ]; then
    STATUS=1
    echo "ERROR: pylint generated errors"
fi

exit $STATUS
