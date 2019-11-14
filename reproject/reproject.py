#
# Data Services Reprojection service for Harmony
#

import argparse
import json
import logging
import os
import re
import subprocess

from tempfile import mkdtemp
from shutil import copyfile

import harmony


# Data Services Reprojection service for Harmony
#
class HarmonyAdapter(harmony.BaseHarmonyAdapter):

    # Callback used by BaseHarmonyAdapter to invoke the service
    #
    def invoke(self):
        logger = self.logger
        message = self.message

        temp_dir = mkdtemp()

        logger.info("Starting Data Services Reprojection Service")
        try:
            # Make a local copy of the granule file we need to reproject

            if not message.granules:
                raise Exception("No granules specified for reprojection")
            if len(message.granules) > 1:
                raise Exception("Only one granule may be reprojected at a time")

            self.download_granules()
            logger.info("Granule data copied")


            # Loop through each file proforming the reprojection

            granule = message.granules[0]
            input_file = granule.local_filename
            output_file = temp_dir + os.sep + os.path.basename(input_file)
            extension = os.path.splitext(output_file)[-1][1:]
            logger.info("Reprojecting file " + input_file + " as " + output_file)


            # TBD reproject. Just copy to output for now

            copyfile(input_file, output_file)


            # Return the output file back to Harmony

            logger.info("Reprojection complete")
            self.completed_with_local_file(output_file)

        except Exception as e:
            logger.exception("Reprojection failed", e)
            self.completed_with_error("Reprojection failed with error: " + str(e))

        finally:
            self.cleanup()



# Main program start
#
parser = argparse.ArgumentParser(prog='Reproject', description='Run the Data Services Reprojection Tool')
parser.add_argument('--harmony-action',
                    choices=['invoke'],
                    help='The action Harmony needs to perform (currently only "invoke")')
parser.add_argument('--harmony-input',
                    help='The input data for the action provided by Harmony')

print("Starting")
args = parser.parse_args()
harmony.run_cli(parser, args, HarmonyAdapter)

