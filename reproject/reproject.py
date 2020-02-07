"""
 Data Services Reprojection service for Harmony
"""

import argparse
import mimetypes
import os
import re
import sys
import subprocess

from tempfile import mkdtemp

import harmony

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Mergers import NetCDF4Merger



class HarmonyAdapter(harmony.BaseHarmonyAdapter):
    """
        Data Services Reprojection service for Harmony

        This class uses the Harmony utility library for processing the
        service input options.
    """


    def invoke(self):
        """
            Callback used by BaseHarmonyAdapter to invoke the service
        """
        logger = self.logger
        logger.info("Starting Data Services Reprojection Service")
        os.environ['HDF5_DISABLE_VERSION_CHECK'] = '1'

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


            # Get reprojection options

            crs = None
            interpolation = None
            x_extent = []
            y_extent = []
            width, height = 0, 0
            x_min, x_max, y_min, y_max = 0.0, 0.0, 0.0, 0.0

            if hasattr(msg, 'format'):
                if hasattr(msg.format, 'crs'):
                    crs = msg.format.crs
                if hasattr(msg.format, 'interpolation'):
                    interpolation = msg.format.interpolation
                if hasattr(msg.format, 'XExtent'):
                    x_extent = msg.format.XExtent
                if hasattr(msg.format, 'YExtent'):
                    y_extent = msg.format.YExtent
                if hasattr(msg.format, 'width'):
                    width = msg.format.width
                if hasattr(msg.format, 'height'):
                    height = msg.format.height

            crs = crs or '+proj=longlat +ellps=WGS84 +units=m'

            if not x_extent and y_extent:
                raise Exception("Missing x extent")
            if x_extent and not y_extent:
                raise Exception("Missing y extent")
            if len(x_extent) != 2 or len(y_extent) != 2:
                raise Exception("Invalid XExtent or YExtent")
            if x_extent and y_extent:
                x_min, x_max = x_extent[0], x_extent[1]
                y_min, y_max = y_extent[0], y_extent[1]

            if width and not height:
                raise Exception("Missing cell height")
            if height and not width:
                raise Exception("Missing cell width")

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

            try:
                info = subprocess.check_output(['gdalinfo', input_file], stderr=subprocess.STDOUT).decode("utf-8")
                input_format = re.search(r"Driver:\s*([^/]+)", info).group(1)
            except Exception as err:
                logger.error("Unable to determine input file format: " + str(err))
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
                    result_str = subprocess.check_output( \
                        ['gdalwarp', '-geoloc', '-t_srs', crs, dataset, output], \
                        stderr=subprocess.STDOUT).decode("utf-8")
                    outputs.append(name)
                except Exception as err:
                    # Assume for now dataset cannot be reprojected. TBD add checks for other error
                    # conditions.
                    logger.info("Cannot reproject " + name)

            # Now merge outputs (unless we only have one)

            if not outputs:
                raise Exception("No subdatasets could be reprojected")

            NetCDF4Merger.create_output(input_file, output_file, temp_dir)

            # Return the output file back to Harmony

            logger.info("Reprojection complete")
            mimetype = mimetypes.guess_type(input_file, False) or ('application/octet-stream', None)
            self.completed_with_local_file(output_file, os.path.basename(input_file), mimetype[0])

        except Exception as err:
            logger.error("Reprojection failed: " + str(err))
            self.completed_with_error("Reprojection failed with error: " + str(err))

        finally:
            self.cleanup()



# Main program start
#
if __name__ == "__main__":
    PARSER = argparse.ArgumentParser(prog='Reproject', description='Run the Data Services Reprojection Tool')
    PARSER.add_argument('--harmony-action',
                        choices=['invoke'],
                        help='The action Harmony needs to perform (currently only "invoke")')
    PARSER.add_argument('--harmony-input',
                        help='The input data for the action provided by Harmony')

    ARGS = PARSER.parse_args()
    harmony.run_cli(PARSER, ARGS, HarmonyAdapter)
