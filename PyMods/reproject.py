"""
 Data Services Reprojection service for Harmony
"""
import argparse
import functools
import os
import re
import subprocess
import sys
from tempfile import mkdtemp
import logging
import json
import warnings

import numpy as np
import rasterio
# from affine import Affine
from rasterio.transform import Affine
import xarray
from pyproj import Proj
from pyresample import geometry, kd_tree, bilinear
from pyresample.ewa import ll2cr, fornav

from PyMods import NetCDF4Merger

RADIUS_EARTH_METRES = 6_378_137  # http://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html
CRS_DEFAULT = '+proj=longlat +ellps=WGS84'
#CRS_DEFAULT ='EPSG:4979' # WGS84 Datum + Elipsoid for coordinate reference (CRS), similar to 4326
#CRS_DEFAULT = '+proj=eqc'

# https://pyresample.readthedocs.io/en/latest/swath.html
ROWS_PER_SCAN = 8  # the number of overlapping rows in the swath (need for EWA)
REPR_MODE = 'pyresample' # 'gdal'

''' TODO: Refactor so that we either first determine groups, or we cache PyResample
    setup results to avoid recomputing.
    
    Also: Refactor to not use gdalinfo for list of datasets
    
    Also: Resolve issues re. get_resolution and get_extents and various data architectures
'''

def reproject(msg, logger):
    # Set up source and destination files
    param_list = get_params_from_msg(msg)
    if not os.path.isfile(param_list.get('input_file')):
        raise Exception("Input file does not exist")
    temp_dir = mkdtemp()
    root_ext = os.path.splitext(os.path.basename(param_list.get('input_file')))
    output_file = temp_dir + os.sep + root_ext[0] + '_repr' + root_ext[1]
    extension = os.path.splitext(output_file)[-1][1:]

    logger.info("Reprojecting file " + param_list.get('input_file') + " as " + output_file)
    logger.info("Selected CRS: " + param_list.get('crs') + "\tInterpolation: " + param_list.get('interpolation'))

    # TODO: refactor to better handle parameters, and to consider e.g. EWA and Nearest setup
    if REPR_MODE == 'pyresample':
        target_area, cols, rows, t_params, s_params, input_idxs, idx_ref \
          = get_pyresample_params(param_list)

    # Use gdalinfo to get the sub-datasets in the input file as well as the file type.
    try:
        info = subprocess.check_output(['gdalinfo', param_list.get('input_file')], stderr=subprocess.STDOUT).decode("utf-8")
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
            if "lat" in name or "lon" in name:
                continue # skip processing
            output = temp_dir + os.sep + name.split('/')[-1] + '.' + extension
            logger.info("Reprojecting subdataset '%s'" % name)
            logger.info("Reprojected output '%s'" % output)
            if REPR_MODE == 'gdal':
                gdal_resample(msg, dataset, output, logger)
            else:
                # if name == "lat" or name == "lon": continue
                py_resample(msg, name, output, target_area, cols, rows, t_params, s_params, input_idxs, idx_ref)
            outputs.append(name)
        except Exception as err:
            # Assume for now dataset cannot be reprojected. TBD add checks for other error
            # conditions.
            logger.info("Cannot reproject " + name)
            logger.info(err)

    # Now merge outputs (unless we only have one)

    if not outputs:
        raise Exception("No subdatasets could be reprojected")

    NetCDF4Merger.create_output(param_list.get('input_file'), output_file, temp_dir)

    # Return the output file back to Harmony
    return param_list.get('granule'), output_file


def gdal_resample(message, dataset, output_file, logger):
    prms = get_params_from_msg(message)

    #TODO: rework to accomodate new parameter handling re. undefined or None
    gdal_cmd = ['gdalwarp', '-geoloc', '-t_srs', prms.get('crs')]
    if prms.get('interpolation') and prms.get('interpolation') is not 'ewa':
        gdal_cmd.extend(['-r', prms.get('interpolation')])
        logger.info('Selected interpolation: %s' % prms.get('interpolation'))
    if prms.get('x_extent') and prms.get('y_extent'):
        gdal_cmd.extend(['-te', str(prms.get('x_min')), str(prms.get('y_min')), str(prms.get('x_max')), str(prms.get('y_max'))])
        logger.info('Selected scale extent: %f %f %f %f' % (prms.get('x_min'), prms.get('y_min'), prms.get('x_max'), prms.get('y_max')))
    if prms.get('xres') and prms.get('yres'):
        gdal_cmd.extend(['-tr', str(prms.get('xres')), str(prms.get('yres'))])
        logger.info('Selected scale size: %d %d' % (prms.get('xres'), prms.get('yres')))
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
    data_set = xarray.open_dataset(prms.get('input_file'), decode_cf=True, group=prms.get('data_group'))
    swath_area = prms.get('file_data').get("swath_definition")
    radius_of_influence = 50000

    name = name.split('/')[-1]

    # Get data, exclude time
    if not data_set.variables:
        data_arr = data_set.values
    elif data_set.variables.get('time') is not None: # .size != 0:
        data_arr = data_set.variables.get(name)[0].values
    else:
        data_arr = data_set.variables.get(name).values

    if prms.get('interpolation') == 'near':
        fill_value = 9999
        epsilon = 0.5
        result_data = kd_tree.resample_nearest(swath_area, data_arr, target_area,
                                               radius_of_influence,
                                               fill_value, epsilon)
    if prms.get('interpolation') == 'bilinear':
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
                                                        input_idxs, idx_ref,
                                                        output_shape=target_area.shape)
    if prms.get('interpolation') == 'ewa':
        # fornav resamples the swath data to the gridded area
        if np.issubdtype(data_arr.dtype, np.integer):
            data_arr = data_arr.astype(float)
        num_valid_points, result_data = fornav(cols, rows, target_area, data_arr,
                                               rows_per_scan=ROWS_PER_SCAN)

    write_netcdf(output_file, result_data, prms.get('crs'), prms.get('grid_transform'))


def get_pyresample_params(param_list):
    # TODO: refactor to better handle parameters, and to consider e.g. EWA and Nearest setup
    # Get parameters for pyresample
    # data_set = xarray.open_dataset(param_list.get('input_file'))
    grid_extent = param_list.get('x_min'), param_list.get('y_min'), param_list.get('x_max'), param_list.get('y_max')
    target_area = geometry.AreaDefinition('grid_area', 'target_grid', 'proj', param_list.get('crs'),
                                          param_list.get('width'), param_list.get('height'), grid_extent)
    swath_area = param_list.get('file_data').get("swath_definition")
    # ll2cr converts swath longitudes and latitudes to grid columns and rows
    swath_points_in_grid, cols, rows = ll2cr(swath_area, target_area)
    # Calculate interpolation coefficients, input data reduction matrix and mapping matrix for 2 step bilinear
    radius_of_influence = 50000
    t_params = s_params = input_idxs = idx_ref = None
    if param_list.get('interpolation') == 'bilinear':
        t_params, s_params, input_idxs, idx_ref = bilinear.get_bil_info(swath_area, target_area,
                                                                        radius_of_influence, neighbours=4)
    return target_area, cols, rows, t_params, s_params, input_idxs, idx_ref


def get_params_from_msg(message):
    # TODO: test for incomplete message, consider defaults as None or undefined
    crs = rgetattr(message, 'format.crs', CRS_DEFAULT)
    interpolation = rgetattr(message, 'format.interpolation', 'near')  # near, bilinear, ewa
    x_extent = rgetattr(message, 'format.scaleExtent.x', None)
    y_extent = rgetattr(message, 'format.scaleExtent.y', None)
    width = rgetattr(message, 'format.width', 0)
    height = rgetattr(message, 'format.height', 0)
    xres = rgetattr(message, 'format.scaleSize.x', 0)
    yres = rgetattr(message, 'format.scaleSize.y', 0)
    granule = rgetattr(message, 'granules', [None])[0]

    input_file = rgetattr(granule, 'local_filename', None)
    # TODO: test for no local_filename
    # refactor to get groups and datasets together (first?)
    latlon_group, data_group = get_group(input_file)
    file_data = get_input_file_data(input_file, latlon_group)
    latitudes = file_data.get("latitudes")
    longitudes = file_data.get("longitudes")
    lon_res = file_data.get('lon_res')
    lat_res = file_data.get('lat_res')
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
            'lon_res':lon_res
            }


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
