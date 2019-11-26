#
# Data Services Reprojection service for Harmony
#

import argparse
import gdal
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import sys

from tempfile import mkdtemp

import harmony


# Data Services Reprojection service for Harmony
#
# This class uses the Harmony utility library for processing the
# service input options.
#
class HarmonyAdapter(harmony.BaseHarmonyAdapter):

    # Callback used by BaseHarmonyAdapter to invoke the service
    #
    def invoke(self):
        logger = self.logger
        logger.info("Starting Data Services Reprojection Service")

        try:
            if not hasattr(self, 'message'):
                raise Exception("No message request")


            # Verify a granule URL has been provided andmake a local copy of the granule file

            msg = self.message
            if not hasattr(msg, 'granules') or not msg.granules :
                raise Exception("No granules specified for reprojection")
            if not isinstance(msg.granules, list):
                raise Exception("Invalid granule list")
            if len(msg.granules) > 1:
                raise Exception("Too many granules")

            self.download_granules()
            logger.info("Granule data copied")


            # Get the reprojection crs

            crs = None
            if hasattr(msg, 'format') and hasattr(msg.format, 'crs'):
                crs = msg.format.crs
            crs = crs or '+proj=longlat +ellps=WGS84 +units=m'


            # Set up source and destination files

            granule = msg.granules[0]
            input_file = granule.local_filename
            if not os.path.isfile(input_file):
                raise Exception("Input file does not exist")
            temp_dir = mkdtemp()
            output_file = temp_dir + os.sep + os.path.basename(input_file)
            extension = os.path.splitext(output_file)[-1][1:]

            logger.info("Reprojecting file " + input_file + " as " + output_file)
            logger.info("Selected CRS: " + crs)


            # Use gdalinfo to get the sub-datasets in the input file as well as the file type.
            #
            # gdal.Warp(output_file, input_file, options=['geoloc', 't_srs', '+proj=longlat +ellps=WGS84 +units=m'], tps=False)
            # gdalwarp -geoloc -tps -t_srs '+proj=longlat +ellps=WGS84' NETCDF:<input_file>:sea_surface_temperature output_file

            try:
                info = subprocess.check_output(['gdalinfo', input_file], stderr=subprocess.STDOUT).decode("utf-8")
                input_format = re.search("Driver:\s*([^/]+)", info).group(1)
            except Exception as e:
                logger.error("Unable to determine input file format: " + str(e))
                raise Exception("Cannot determine input file format")

            logger.info("Input file format: " + input_format)
            datasets = [line.split('=')[-1] for line in info.split("\n") if re.match(r"^\s*SUBDATASET_\d+_NAME=", line)]

            if not datasets:
                raise Exception("No subdatasets found in input file")
            logger.info("Input file has " + str(len(datasets)) + " datasets")


            # Loop through each dataset and reproject

            outputs = []
            for dataset in datasets:
                try:
                    name = dataset.split(':')[-1]
                    output = temp_dir + os.sep + name + '.' + extension
                    logger.info("Reprojecting subdataset '%s'" % name)
                    result_str = subprocess.check_output(['gdalwarp', '-geoloc', '-t_srs', crs, dataset, output], stderr=subprocess.STDOUT).decode("utf-8")
                    outputs.append(name)
                except Exception as e:
                    logger.info("Cannot reproject " + name)

            # Now merge outputs (unless we only have one)

            if not outputs:
                raise Exception("No subdatasets could be reprojected")

            elif len(outputs) == 1:
                # Just rename a single band output

                shutil.move(temp_dir + os.sep + outputs[0] + '.' + extension, output_file)
            else:
                # Merge multiple bands back into one file
                args = ['gdal_merge.py', '-o', output_file, '-separate', '-of', input_format]
                args.extend([temp_dir + os.sep + name + '.' + extension for name in outputs])
                logger.info("Merging output files")

                subprocess.check_output(args, stderr=subprocess.STDOUT)


            # Return the output file back to Harmony

            logger.info("Reprojection complete")
            mimetype = mimetypes.guess_type(input_file, False) or ('application/octet-stream', None)
            self.completed_with_local_file(output_file, os.path.basename(input_file), mimetype[0])

        except Exception as e:
            logger.error("Reprojection failed: " + str(e))
            self.completed_with_error("Reprojection failed with error: " + str(e))

        finally:
            self.cleanup()



# Main program start
#
if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='Reproject', description='Run the Data Services Reprojection Tool')
    parser.add_argument('--harmony-action',
                        choices=['invoke'],
                        help='The action Harmony needs to perform (currently only "invoke")')
    parser.add_argument('--harmony-input',
                        help='The input data for the action provided by Harmony')

    args = parser.parse_args()
    harmony.run_cli(parser, args, HarmonyAdapter)

