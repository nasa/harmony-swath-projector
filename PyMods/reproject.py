"""
 Data Services Reprojection service for Harmony
"""
import argparse
import functools
import os
import re
from tempfile import mkdtemp
import logging
import json

import numpy as np
import rasterio
from rasterio.transform import Affine
import xarray
from pyproj import Proj
from pyresample import geometry

from PyMods import nc_merge
from PyMods.nc_info import NCInfo
from PyMods.interpolation_gdal import gdal_resample_all_variables
from PyMods.interpolation_pyresample import resample_all_variables

RADIUS_EARTH_METRES = 6_378_137  # http://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html
CRS_DEFAULT = '+proj=longlat +ellps=WGS84'

# The REPR_MODE should probably become a parameter in the call to reproject,
# with a default value to fall back on.
REPR_MODE = 'pyresample'
# REPR_MODE = 'gdal'

''' TODO: Refactor so that we either first determine groups, or we cache PyResample
    setup results to avoid recomputing.

    Also: Refactor to not use gdalinfo for list of datasets

    Also: Resolve issues re. get_resolution and get_extents and various data architectures
'''

def reproject(msg, logger):
    # Set up source and destination files
    param_list = get_params_from_msg(msg, logger)
    temp_dir = mkdtemp()
    root_ext = os.path.splitext(os.path.basename(param_list.get('input_file')))
    output_file = temp_dir + os.sep + root_ext[0] + '_repr' + root_ext[1]

    logger.info(f'Reprojecting file {param_list.get("input_file")} as {output_file}')
    logger.info(f'Selected CRS: {param_list.get("crs")}\t'
                f'Interpolation: {param_list.get("interpolation")}')

    try:
        info = NCInfo(param_list['input_file'])
    except Exception as err:
        logger.error(f'Unable to parse input file variables: {str(err)}')
        raise Exception('Unable to parse input file varialbes')

    science_variables = info.get_science_variables()

    if len(science_variables) == 0:
        raise Exception('No science variables found in input file')

    logger.info(f'Input file has {len(science_variables)} science variables')

    # Loop through each dataset and reproject
    if REPR_MODE == 'gdal':
        logger.debug('Using gdal for reprojection.')
        outputs = gdal_resample_all_variables(param_list, science_variables,
                                              temp_dir, logger)
    elif REPR_MODE == 'pyresample':
        logger.debug('Using pyresample for reprojection.')
        outputs = resample_all_variables(param_list, science_variables,
                                         temp_dir, logger)
    else:
        raise Exception(f'Invalid reprojection mode: {REPR_MODE}')

    if not outputs:
        raise Exception("No subdatasets could be reprojected")

    # Now merge outputs (unless we only have one)
    metadata_variables = info.get_metadata_variables()
    nc_merge.create_output(param_list.get('input_file'), output_file, temp_dir,
                           metadata_variables, logger)

    # Return the output file back to Harmony
    return param_list.get('granule'), output_file


def get_params_from_msg(message, logger):
    # TODO: test for incomplete message, consider defaults as None or undefined
    crs = rgetattr(message, 'format.crs', CRS_DEFAULT)
    interpolation = rgetattr(message, 'format.interpolation', 'near')  # near, bilinear, ewa
    x_extent = rgetattr(message, 'format.scaleExtent.x', None)
    y_extent = rgetattr(message, 'format.scaleExtent.y', None)
    width = rgetattr(message, 'format.width', None)
    height = rgetattr(message, 'format.height', None)
    xres = rgetattr(message, 'format.scaleSize.x', 0)
    yres = rgetattr(message, 'format.scaleSize.y', 0)
    granule = rgetattr(message, 'granules', [None])[0]

    # ERROR 5: -tr and -ts options cannot be used at the same time.
    if (
            (x_extent is not None or y_extent is not None) and
            (height is not None or width is not None)
    ):
        raise Exception("'scaleSize', 'width' or/and 'height' cannot "
                        "be used at the same time in the message.")

    input_file = rgetattr(granule, 'local_filename', None)
    if input_file is None:
        raise Exception('Invalid local_filename attribute for granule.')
    elif not os.path.isfile(input_file):
        raise Exception("Input file does not exist")

    # refactor to get groups and datasets together (first?)
    try:
        latlon_group, data_group = get_group(input_file)
        file_data = get_input_file_data(input_file, latlon_group)
        latitudes = file_data.get("latitudes")
        longitudes = file_data.get("longitudes")
        lon_res = file_data.get('lon_res')
        lat_res = file_data.get('lat_res')
    except Exception as err:
        logger.error(f'Unable to determine input file format: {str(err)}')
        raise Exception('Cannot determine input file format')

    projection = Proj(crs)

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
        x_min = rgetattr(x_extent, 'min', None)
        x_max = rgetattr(x_extent, 'max', None)
    if y_extent:
        y_min = rgetattr(y_extent, 'min', None)
        y_max = rgetattr(y_extent, 'max', None)

    if REPR_MODE == 'pyresample':
        if x_extent is None and y_extent is None:
            x_min, x_max, y_min, y_max = get_extents_from_walking_perimeter(projection, latitudes, longitudes)
        if xres is not None and yres is not None:
            xres = get_resolution_from_minimum_difference(latitudes, longitudes, projection)
    #        yres = -1.0 * get_resolution_from_minimum_difference(latitudes, longitudes)
            yres = -1.0 * xres

        if not width and not height and REPR_MODE == 'pyresample':
            width, height = abs(round((x_min - x_max) / xres)), abs(round((y_min - y_max) / yres))

        geotransform = (x_min, xres, 0.0, y_max, 0.0, yres)  # GDAL Standard geo-transform tuple
        grid_transform = Affine.from_gdal(*geotransform)

    return locals()


def get_group(file_name):
    dataset = rasterio.open(file_name)
    latlon_group = None
    data_group = None

    for subdataset in dataset.subdatasets:
        dataset_path = re.sub(r'.*\.nc:(.*)', r'\1', subdataset)
        dataset_path_arr = dataset_path.split('/')
        dataset_name = dataset_path_arr[-1]
        prefix = dataset_path_arr[0:-1] # if dataset_path.len > 1 else ""

        if 'lat' in dataset_path or 'lon' in dataset_path:
            latlon_group = "/".join(prefix)
        else:
            data_group = "/".join(prefix)

        if latlon_group != None and data_group != None:
            # early exit from loop
            break

    return latlon_group, data_group


def get_input_file_data(file_name, group):
    """Get the input dataset (sea surface temperature) and coordinate
    information. Using the coordinate information derive a swath
    definition.

    :rtype: dictionary

    """
    with xarray.open_dataset(file_name, decode_cf=True, group=group) as dataset:
        try:
            latitudes = dataset.coords.variables.get('lat').values
            longitudes = dataset.coords.variables.get('lon').values
        except:
            variables = dataset.variables
            for variable in dataset.variables:
                if "lat" in variable:
                    latitudes = variables[variable].values
                elif "lon" in variable:
                    longitudes = variables[variable].values

        metadata = dataset.attrs
        lat_res = dataset.attrs.get('geospatial_lat_resolution')
        lon_res = dataset.attrs.get('geospatial_lon_resolution')

    swath_definition = geometry.SwathDefinition(lons=longitudes,
                                                lats=latitudes)
    return {'latitudes': latitudes,
            'longitudes': longitudes,
            'metadata': metadata,
            'swath_definition': swath_definition,
            'lat_res':lat_res,
            'lon_res':lon_res}


def get_resolution_from_minimum_difference(latitudes, longitudes, projection):
    """Take the differences in latitude and longitudes between adjacent pixels
    (in both the i and j directions), and find the minimum combined difference:

    Minimum(((lat_2 - lat_1)^2 + (lon_2 - lon_1)^2)^0.5)

    Then return the resolution in metres or degrees depending on projection.

    NOTE: Is the median value more appropriate than the minimum? If so:

    `np.ndarray.min()` becomes `np.median(np.ndarray)`

    :param latitudes: Input array of latitudes
    :param longitudes: Input array of longitudes, where the points at indices:
        longitudes[i, j] and latitudes[i, j] are the same data point.
    :param projection: target projection of output grid
    :type: numpy.ndarray
    :type: numpy.ndarray
    :type: PyProj.proj.Proj projection object, converting degrees to meters, forward projection
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
    # min_diff = min(diffs_i.min(), diffs_j.min()) # * 2 ?
    # TODO: Resolve issues, use min? median? meta-data? total-cell-count?
    # Alternative if using the median:
    min_diff = min(np.median(diffs_i), np.median(diffs_j))

    if not projection.crs.is_geographic: # convert resolution to meters
        # generic conversion based upon distance of degrees at equator
        min_diff = min_diff * (2 * np.pi * RADIUS_EARTH_METRES / 360)
        # should we use center of grid?  determine point of true-scale?
    return float(min_diff)


def get_extents_from_walking_perimeter(projection, latitudes, longitudes):
    """Find the extents of the projected coordinates in the x and y directions
    of the output. This is achieved by projecting only the points along the
    perimeters of the latitude and longitude arrays.

    :param projection: An object that will convert from latitude and
        longitude to the user specified (or default) output projection.
    :type projection: PyProj.proj.Proj projection object
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


def rgetattr(obj, attr, *args):
    """ Recursive get attribute
        Returns attribute from an attribute hierarchy, e.g. a.b.c, if it exists
    """

    # functools.reduce will apply _getattr with previous result (obj)
    #   and item from sequence (attr)
    def _getattr(obj, attr):
        return getattr(obj, attr, *args)

    # First call takes first two items, thus need [obj] as first item in sequence
    return functools.reduce(_getattr, [obj] + attr.split('.'))


'''
class to_object(data):  # treats data as a dictionary
    def __init__(self, data):
        self.__dict__ = data
'''

def to_object(item):
    """ Recursively converts item into object with attributes
        E.g., a dictionary becomes an object with "." access attributes
        Useful for e.g., converting json objects into "full" objects
    """
    if isinstance(item, dict):
        # return a new object with the dictionary items as attributes
        return type('obj', (), {k: to_object(v) for k, v in item.items()})
    if isinstance(item, list):
        def yield_convert(item):
            """ Acts as a generator (iterator) returning one item for successive calls """
            for index, value in enumerate(item):
                yield to_object(value)
        # list will iterate on generator (yield_convert) and combine the results into a list
        return list(yield_convert(item))
    else:
        return item


# Main program start for testing
#
if __name__ == "__main__":
    PARSER = argparse.ArgumentParser(prog='Reproject', description='Run the Data Services Reprojection Tool')
    PARSER.add_argument('--message',
                        help='The input data for the action provided by Harmony')

    ARGS = PARSER.parse_args()
    # Note it is hard to get properly quoted json string through shell invocation,
    # It is easier if single and double quoting is inverted
    quoted_msg = re.sub("'", '"', ARGS.message)
    msg_dictionary = json.loads(quoted_msg)
    msg = to_object(msg_dictionary)

    logger = logging.getLogger("SwotRepr")
    syslog = logging.StreamHandler()
    formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s")
    #       "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] [%(user)s] %(message)s")
    syslog.setFormatter(formatter)
    logger.addHandler(syslog)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    reproject(msg, logger)
