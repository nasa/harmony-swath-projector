"""
 Data Services Reprojection service for Harmony
"""

import argparse
import functools
import mimetypes
import os
import re
import subprocess
import sys
from tempfile import mkdtemp

import numpy as np
import rasterio
# from affine import Affine
from rasterio.transform import Affine
import xarray
from pyproj import Proj
from pyresample import geometry, kd_tree, bilinear
from pyresample.ewa import ll2cr, fornav

import harmony
from Mergers import NetCDF4Merger

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RADIUS_EARTH_METRES = 6.378137e6  # nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html
crs_default = '+proj=longlat +ellps=WGS84 +units=m'

RADIUS_EARTH_METRES = 6.378137e6  # http://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html
crs_default = '+proj=longlat +ellps=WGS84'
#crs_default ='EPSG:4327'
#crs_default = '+proj=eqc'

# https://pyresample.readthedocs.io/en/latest/swath.html
rows_per_scan = 8  # the number of rows in the entire swath (need for EWA)
repr_mode = 'pyresampl'


def rgetattr(obj, attr, *args):
    """
        return attribute if it exists
    """

    def _getattr(obj, attr):
        return getattr(obj, attr, *args)

    # accepts a function and a sequence and returns a single value calculated
    # function is applied cumulatively to arguments in the sequence
    # from left to right until the list is exhausted
    return functools.reduce(_getattr, [obj] + attr.split('.'))


def write_netcdf(file_name, data, crs, transform):
    """Write the results of the transformation to a new NetCDF file.

    :param file_name: String name of the output file.
    :param data: The numpy.ndarray containing the transformed data.
    :param crs: Coordinate Reference System of the transformed data,
        currently: {'proj': 'eqc'}
    :param transform: Transformation matrix from Affine.

    """
    with rasterio.open(file_name,
                       'w',
                       driver='NetCDF',
                       height=data.shape[0],
                       width=data.shape[1],
                       count=1,
                       dtype=data.dtype,
                       crs=crs,
                       transform=transform) as netcdf_container:
        netcdf_container.write(data, 1)  # first (and only) band


def convert_resolution_degrees_to_metres(degrees):
    """Take an input value of latitude of longitude resolution in decimal
    degrees and convert that to a value in metres. This formula relies on the
    average radius of the Earth at the equator.

    :param degrees: Decimal degrees input (either latitude or longitude)
    :type degrees: float
    :return: Resolution in metres.
    :rtype: float

    """
    return degrees * 2.0 * pi * RADIUS_EARTH_METRES / 360.0


def get_input_file_data(file_name):
    """Get the input dataset (sea surface temperature) and coordinate
    information. Using the coordinate information derive a swath
    definition.

    :rtype: dictionary

    """
    with xarray.open_dataset(file_name, decode_cf=True) as dataset:
        latitudes = dataset.coords.variables.get('lat').values
        longitudes = dataset.coords.variables.get('lon').values
        metadata = dataset.attrs
        if dataset.attrs.get('geospatial_lat_resolution') != None:
            lat_res = dataset.attrs.get('geospatial_lat_resolution')
        if dataset.attrs.get('geospatial_lon_resolution') != None:
            lon_res = dataset.attrs.get('geospatial_lon_resolution')

    swath_definition = geometry.SwathDefinition(lons=longitudes,
                                                lats=latitudes)
    return {'latitudes': latitudes,
            'longitudes': longitudes,
            'metadata': metadata,
            'swath_definition': swath_definition,
            'lat_res':lat_res,
            'lon_res':lon_res
            }


def get_resolution_from_minimum_difference(latitudes, longitudes):
    """Take the differences in latitude and longitudes between adjacent pixels
    (in both the i and j directions), and find the minimum combined difference:

    Minimum(((lat_2 - lat_1)^2 + (lon_2 - lon_1)^2)^0.5)

    Then return the resolution in metres.

    NOTE: Is the median value more appropriate than the minimum? If so:

    `np.ndarray.min()` becomes `np.median(np.ndarray)`

    :param latitudes: Input array of latitudes
    :param longitudes: Input array of longitudes, where the points at indices:
        longitudes[i, j] and latitudes[i, j] are the same data point.
    :type: numpy.ndarray
    :type: numpy.ndarray
    :return: The minimum of the differences, cast as a float for compatibility
        with later functions (internally one of the pyresample functions can't
        handle a numpy.float64.
    :rtype: float

    """
    lats_diff_i = np.diff(latitudes, n=1, axis=0)
    lons_diff_i = np.diff(longitudes, n=1, axis=0)
    lats_diff_j = np.diff(latitudes, n=1, axis=1)
    lons_diff_j = np.diff(longitudes, n=1, axis=1)

    diffs_i = np.sqrt(np.add(np.square(lats_diff_i), np.square(lons_diff_i)))
    diffs_j = np.sqrt(np.add(np.square(lats_diff_j), np.square(lons_diff_j)))
    min_diff = min(diffs_i.min(), diffs_j.min())
    # Alternative if using the median:
    # min_diff = min(np.median(diffs_i), np.median(diffs_j))
    return min_diff

def get_extents_from_walking_perimeter(projection, latitudes, longitudes):
    """Find the extents of the projected coordinates in the x and y directions
    of the output. This is achieved by projecting only the points along the
    perimeters of the latitude and longitude arrays.

    :param projection: An object that will convert from latitude and
        longitude to the user specified (or default) output projection.
    :type projection: pyproj.proj.Proj
    :param latitudes: The latitudes from the input file.
    :type latitudes: np.ndarray
    :param longitudes: The longitudes from the input file.
    :type longitudes: np.adarray
    :return: x_min, x_max, y_min, y_max
    :rtype: tuple(float, float, float, float)

    """
    n_elements_x, n_elements_y = latitudes.shape
    bottom_points = [projection(longitudes[0, ind], latitudes[0, ind])
                     for ind in range(n_elements_y)]

    top_points = [projection(longitudes[-1, ind], latitudes[-1, ind])
                  for ind in range(n_elements_y)]

    left_points = [projection(longitudes[ind, 0], latitudes[ind, 0])
                   for ind in range(n_elements_x)]

    right_points = [projection(longitudes[ind, -1], latitudes[ind, -1])
                    for ind in range(n_elements_x)]

    all_points = left_points + top_points + right_points + bottom_points
    x_values, y_values = zip(*all_points)

    return min(x_values), max(x_values), min(y_values), max(y_values)

def gdal_resample(message, dataset, output_file, logger):
    prms = get_params_from_msg(message)

    gdal_cmd = ['gdalwarp', '-geoloc', '-t_srs', prms.get('crs')]
    if prms.get('interpolation') and prms.get('interpolation') is not 'ewa':
        gdal_cmd.extend(['-r', prms.get('interpolation')])
        logger.info('Selected interpolation: %s' % prms.get('interpolation'))
    if prms.get('x_extent') and prms.get('y_extent'):
        gdal_cmd.extend(['-te', str(prms.get('x_min')), str(prms.get('y_min')), str(prms.get('x_max')), str(prms.get('y_max'))])
        logger.info('Selected scale extent: %f %f %f %f' % (prms.get('x_min'), prms.get('y_min'), prms.get('x_max'), prms.get('y_max')))
    if prms.get('xres') and prms.get('yres'):
        gdal_cmd.extend(['-tr', str(prms.get('xres')), str(prms.get('yres'))])
        logger.info('Selected scale size: %d %d' % prms.get('xres', prms.get('yres')))
    if prms.get('width') and prms.get('height'):
        gdal_cmd.extend(['-ts', str(prms.get('width')), str(prms.get('height'))])
        logger.info('Selected width: %d' % prms.get('width'))
        logger.info('Selected height: %d' % prms.get('height'))
    gdal_cmd.extend([dataset, output_file])
    result_str = subprocess.check_output(gdal_cmd, stderr=subprocess.STDOUT).decode("utf-8")

def py_resample(message, name, output_file, target_area, cols, rows, t_params, s_params, input_idxs, idx_ref):
    prms = get_params_from_msg(message)
    # Suppress known pyresamle warnings
    if not sys.warnoptions:
        warnings.simplefilter("ignore")
    # Get parameters for pyresample
    data_set = xarray.open_dataset(prms.get('input_file'))
    swath_area = prms.get('file_data').get("swath_definition")
    radius_of_influence = 50000

    # Exclude time
    if data_set.variables.get('time').size != 0:
        data_arr = data_set.variables.get(name)[0].values
    else :
        data_arr = data_set.variables.get(name).values

    if prms.get('interpolation') == 'near' :
        fill_value = 9999
        epsilon = 0.5
        result_data = kd_tree.resample_nearest(swath_area, data_arr, target_area,
                                               radius_of_influence,
                                               fill_value, epsilon)
    if prms.get('interpolation') =='bilinear':
        # # -------------- BILINEAR 1 --------------
        # fill_value = 9999
        # epsilon = 0.5
        # neighbours = 32
        # reduce_data = True
        # segments = None
        # result_data = bilinear.resample_bilinear(data_arr, swath_area, target_area, radius_of_influence,
        #                                     neighbours,
        #                                     fill_value, reduce_data, segments, epsilon)
        # # -------------- BILINEAR 1 --------------

        # -------------- BILINEAR 2 --------------
        result_data = bilinear.get_sample_from_bil_info(data_arr.ravel(), t_params, s_params,
                                                        input_idxs,
                                                        idx_ref, output_shape=target_area.shape)
    if prms.get('interpolation') =='ewa' :
        # fornav resamples the swath data to the gridded area
        num_valid_points, result_data = fornav(cols, rows, target_area, data_arr,
                                               rows_per_scan=rows_per_scan)

    write_netcdf(output_file, result_data, prms.get('crs'), prms.get('grid_transform'))

def get_params_from_msg(message) :
    crs = rgetattr(message, 'format.crs', crs_default)
    interpolation = rgetattr(message, 'format.interpolation', 'near')  # near, bilinear, ewa
    x_extent = rgetattr(message, 'format.scaleExtent.x', None)
    y_extent = rgetattr(message, 'format.scaleExtent.y', None)
    width = rgetattr(message, 'format.width', 0)
    height = rgetattr(message, 'format.height', 0)
    xres = rgetattr(message, 'format.scaleSize.x', 0)
    yres = rgetattr(message, 'format.scaleSize.y', 0)
    granule = message.granules[0]

    input_file = granule.local_filename
    file_data = get_input_file_data(input_file)
    latitudes = file_data.get("latitudes")
    longitudes = file_data.get("longitudes")
    lon_res = file_data.get('lon_res')
    lat_res = file_data.get('lat_res')
    projection = pyproj.proj.Proj(crs)

    # Verify message and assign values

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

    if not x_extent and not y_extent:
        x_min, x_max, y_min, y_max = get_extents_from_walking_perimeter(projection, latitudes, longitudes)
    if not xres and not yres:
        xres = get_resolution_from_minimum_difference(latitudes, longitudes)
        yres = -1.0 * get_resolution_from_minimum_difference(latitudes, longitudes)

    if not width and not height:
        width, height = abs(round((x_min - x_max) / xres)), abs(round((y_min - y_max) / yres))

    geotransform = (x_min, xres, 0.0, y_max, 0.0, yres)  # GDAL Standard geo-transform tuple
    grid_transform = Affine.from_gdal(*geotransform)

    return locals()


def convert_to_meters(x_min, y_min, x_max, y_max):
    #https://stackoverflow.com/questions/23875030/python-get-the-ratios-between-degrees-and-meters-depending-on-coordinates-on
    y_mn = 110540 * y_min # meters
    y_mx = 110540 * y_max
    x_mn = 111320 * np.cos(y_min) * x_min
    x_mx = 111320 * np.cos(y_max) * x_max
    return x_mn, y_mn, x_mx, y_mx


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

            # Verify a granule URL has been provided and make a local copy of the granule file

            # message schema
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
                raise Exception(
                    "'scaleSize', 'width' or/and 'height' cannot be used at the same time in the message.")

            granule = msg.granules[0]
            self.download_granules()
            logger.info("Granule data copied")

            # Get reprojection options

            crs = rgetattr(msg, 'format.crs', None)
            interpolation = rgetattr(msg, 'format.interpolation', None)
            x_extent = rgetattr(msg, 'format.scaleExtent.x', [])
            y_extent = rgetattr(msg, 'format.scaleExtent.y', [])
            width = rgetattr(msg, 'format.width', 0)
            height = rgetattr(msg, 'format.height', 0)
            xres = rgetattr(msg, 'format.scaleSize.x', 0)
            yres = rgetattr(msg, 'format.scaleSize.y', 0)

            # Set up source and destination files
            param_list = get_params_from_msg(msg)
            if not os.path.isfile(param_list.get('input_file')):
                raise Exception("Input file does not exist")
            temp_dir = mkdtemp()
            root_ext = os.path.splitext(os.path.basename(param_list.get('input_file')))
            output_file = temp_dir + os.sep + root_ext[0] + '_repr' + root_ext[1]
            extension = os.path.splitext(output_file)[-1][1:]
            file_data = get_input_file_data(param_list.get('input_file'))
            latitudes = file_data.get("latitudes")
            longitudes = file_data.get("longitudes")

            # Verify message

            crs = crs or crs_default

            if not x_extent and y_extent:
                raise Exception("Missing x extent")
            if x_extent and not y_extent:
                raise Exception("Missing y extent")
            if width and not height:
                raise Exception("Missing cell height")
            if height and not width:
                raise Exception("Missing cell width")

            if x_extent and y_extent:
                if len(x_extent) != 2 or len(y_extent) != 2:
                    raise Exception("Invalid XExtent or YExtent")
                x_min, x_max = x_extent[0], x_extent[1]
                y_min, y_max = y_extent[0], y_extent[1]
            else :
                projection_eqc = Proj(crs)
                x_min, y_min = projection_eqc(longitudes.min(), latitudes.min())
                x_max, y_max = projection_eqc(longitudes.max(), latitudes.max())
                x_min, y_min, x_max, y_max = convert_to_meters(x_min, y_min, x_max, y_max)

            logger.info("Reprojecting file " + param_list.get('input_file') + " as " + output_file)
            logger.info("Selected CRS: " + param_list.get('crs') + "\tInterpolation: " + param_list.get('interpolation'))

            # Get parameters for pyresample

            x_res = get_resolution_from_minimum_difference(latitudes, longitudes)
            y_res = -1.0 * get_resolution_from_minimum_difference(latitudes, longitudes)
            if not width and not height:
                width, height = abs(round((x_min - x_max) / x_res)), abs(round((y_min - y_max) / y_res))
            grid_extent = (x_min, y_min, x_max, y_max)
            target_area = geometry.AreaDefinition('grid_area', 'target_grid', 'proj', crs, width, height, grid_extent)
            swath_area = file_data.get("swath_definition")

            # Use gdalinfo to get the sub-datasets in the input file as well as the file type.

            try:
                info = subprocess.check_output(['gdalinfo', param_list.get('input_file')], stderr=subprocess.STDOUT).decode("utf-8")
                input_format = re.search(r"Driver:\s*([^/]+)", info).group(1)
            except Exception as err:
                logger.error("Unable to determine input file format: " + str(err))
                raise Exception("Cannot determine input file format")

            logger.info("Input file format: " + input_format)
            datasets = [line.split('=')[-1] for line in info.split("\n") if
                        re.match(r"^\s*SUBDATASET_\d+_NAME=", line)]

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
                    logger.info("Reprojected output '%s'" % output)

                    if repr_mode =='gdal':
                        gdal_resample(msg, dataset, output, logger)
                    else:
                        if name == "lat" or name == "lon": continue
                        py_resample(msg, name, output, target_area, cols, rows, t_params, s_params, input_idxs, idx_ref)
                    outputs.append(name)
                except Exception as err:
                    # Assume for now dataset cannot be reprojected. TBD add checks for other error
                    # conditions.
                    logger.info("Cannot reproject " + name)

            # Now merge outputs (unless we only have one)

            if not outputs:
                raise Exception("No subdatasets could be reprojected")

            NetCDF4Merger.create_output(param_list.get('input_file'), output_file, temp_dir)

            # Return the output file back to Harmony

            logger.info("Reprojection complete")
            mimetype = mimetypes.guess_type(param_list.get('input_file'), False) or ('application/octet-stream', None)
            self.completed_with_local_file(
                output_file,
                source_granule=granule,
                is_regridded=True,
                mime=mimetype[0])

        except Exception as err:
            logger.error("Reprojection failed: " + str(err))
            self.completed_with_error("Reprojection failed with error: " + str(err))

        finally:
            self.cleanup()

# Main program start
#
if __name__ == "__main__":
    PARSER = argparse.ArgumentParser(prog='Reproject',
                                     description='Run the Data Services Reprojection Tool')
    PARSER.add_argument('--harmony-action',
                        choices=['invoke'],
                        help='The action Harmony needs to perform (currently only "invoke")')
    PARSER.add_argument('--harmony-input',
                        help='The input data for the action provided by Harmony')

    ARGS = PARSER.parse_args()
    harmony.run_cli(PARSER, ARGS, HarmonyAdapter)
