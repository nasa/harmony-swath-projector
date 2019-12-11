#
# Data Services Reprojection service for Harmony
#

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import gdal
import json
import logging
import mimetypes
import re
import shutil
import subprocess


from tempfile import mkdtemp

import harmony

print(sys.path)
from Mergers import NetCDF4Merger

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
            if not hasattr(msg, 'granules') or not msg.granules:
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
            root_ext = os.path.splitext(os.path.basename(input_file))
            output_file = temp_dir + os.sep + root_ext[0] + '_repr' + root_ext[1]
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
                    logger.info("reprojected output '%s'" % output)
                    result_str = subprocess.check_output(['gdalwarp', '-geoloc', '-t_srs', crs, dataset, output], stderr=subprocess.STDOUT).decode("utf-8")
                    outputs.append(name)
                except Exception as e:
                    logger.info("Cannot reproject " + name)

            # Now merge outputs (unless we only have one)

            if not outputs:
                raise Exception("No subdatasets could be reprojected")

            else:
                NetCDF4Merger.create_output(input_file, output_file, temp_dir)

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

