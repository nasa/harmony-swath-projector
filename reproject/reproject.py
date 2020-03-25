"""
 Data Services Reprojection service for Harmony
"""

import argparse
import mimetypes
import os
import re
import sys
import subprocess
import functools

from tempfile import mkdtemp

import harmony

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Mergers import NetCDF4Merger


def rgetattr(obj, attr, *args):
    """
        return attribute if it exists
    """

    def _getattr(obj, attr):
        return getattr(obj, attr, *args)

    # accepts a function and a sequence and returns a single value calculated
    # function is applied cumulatively to arguments in the sequence from left to right until the list is exhausted
    return functools.reduce(_getattr, [obj] + attr.split('.'))


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

            # message schema
            # {'granules': [{'local_filename': '/home/test/data/VNL2_oneBand.nc'}],
            # 'format': {'crs': 'CRS:84',  'interpolation': 'bilinear',
            #            # 'width': 1000, 'height': 500,
            #            'scaleExtent': {'x': [-160, -30], 'y': [10, 25]},
            #            'scaleSize': {'x': 1, 'y': 1}
            #            }}
            # New message format:
            # {'granules': [{'local_filename': '/home/test/data/VNL2_oneBand.nc'}],
            #     'format': {
            #         'crs': 'CRS:84', 'interpolation': 'bilinear',
            #         'width': 1000, 'height': 500,
            #         'scaleExtent': {
            #             'x': {'min': -160, 'max': -30},
            #             'y': {'min': 10, 'max': 25}
            #         },
            #         'scaleSize': {'x': 1, 'y': 1}
            #     }
            # }
            msg = self.message
            if not hasattr(msg, 'granules') or not msg.granules:
                raise Exception("No granules specified for reprojection")
            if not isinstance(msg.granules, list):
                raise Exception("Invalid granule list")
            if len(msg.granules) > 1:
                raise Exception("Too many granules")
            # ERROR 5: -tr and -ts options cannot be used at the same time.
            if hasattr(msg, 'format') and hasattr(msg.format, 'scaleSize') and (
                    hasattr(msg.format, 'width') or hasattr(msg.format, 'height')):
                raise Exception("'scaleSize', 'width' or/and 'height' cannot be used at the same time in the message.")

            self.download_granules()
            logger.info("Granule data copied")

            # Get reprojection options

            crs = rgetattr(msg, 'format.crs', None)
            interpolation = rgetattr(msg, 'format.interpolation', None)
            x_extent = rgetattr(msg, 'format.scaleExtent.x', None)
            y_extent = rgetattr(msg, 'format.scaleExtent.y', None)
            width = rgetattr(msg, 'format.width', 0)
            height = rgetattr(msg, 'format.height', 0)
            xres = rgetattr(msg, 'format.scaleSize.x', 0)
            yres = rgetattr(msg, 'format.scaleSize.y', 0)

            crs = crs or '+proj=longlat +ellps=WGS84 +units=m'

            if not x_extent and y_extent:
                raise Exception("Missing x extent")
            if x_extent and not y_extent:
                raise Exception("Missing y extent")
            if width and not height:
                raise Exception("Missing cell height")
            if height and not width:
                raise Exception("Missing cell width")
            if x_extent:
                x_min = x_extent.min
                x_max = x_extent.max
            if y_extent:
                y_min = y_extent.min
                y_max = y_extent.max

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
                    gdal_cmd = ['gdalwarp', '-geoloc', '-t_srs', crs]
                    if interpolation:
                        gdal_cmd.extend(['-r', interpolation])
                        logger.info('Selected interpolation: %s' % interpolation)
                    if x_extent and y_extent:
                        gdal_cmd.extend(['-te', str(x_min), str(y_min), str(x_max), str(y_max)])
                        logger.info('Selected scale extent: %f %f %f %f' % (x_min, y_min, x_max, y_max))
                    if xres and yres:
                        gdal_cmd.extend(['-tr', str(xres), str(yres)])
                        logger.info('Selected scale size: %d %d' % (xres, yres))
                    if width and height:
                        gdal_cmd.extend(['-ts', str(width), str(height)])
                        logger.info('Selected width: %d' % width)
                        logger.info('Selected height: %d' % height)
                    gdal_cmd.extend([dataset, output])

                    logger.info("GDAL command: " + " ".join(gdal_cmd))

                    result_str = subprocess.check_output(gdal_cmd, stderr=subprocess.STDOUT).decode("utf-8")
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
