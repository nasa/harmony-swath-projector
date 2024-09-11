""" Data Services Swath Projector service for Harmony """

import functools
import logging
import os
from tempfile import mkdtemp
from typing import Dict

from harmony.message import Message
from harmony.message_utility import has_self_consistent_grid
from pyproj import Proj
from varinfo import VarInfoFromNetCDF4

from swath_projector import nc_merge
from swath_projector.exceptions import InvalidTargetGrid
from swath_projector.interpolation import resample_all_variables

RADIUS_EARTH_METRES = (
    6_378_137  # http://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html
)
CRS_DEFAULT = '+proj=longlat +ellps=WGS84'
INTERPOLATION_DEFAULT = 'ewa-nn'
CF_CONFIG_FILE = 'swath_projector/cf_config.json'


def reproject(
    message: Message,
    collection_short_name: str,
    granule_url: str,
    local_filename: str,
    temp_dir: str,
    logger: logging.Logger,
) -> str:
    """Derive reprojection parameters from the input Harmony message. Then
    extract listing of science variables and coordinate variables from the
    source granule. Then reproject all science variables. Finally merge all
    individual output bands back into a single NetCDF-4 file.

    """
    parameters = get_parameters_from_message(message, granule_url, local_filename)

    # Set up source and destination files
    temp_dir = mkdtemp()
    root_ext = os.path.splitext(os.path.basename(parameters.get('input_file')))
    output_file = temp_dir + os.sep + root_ext[0] + '_repr' + root_ext[1]

    logger.info(f'Reprojecting file {parameters.get("input_file")} as {output_file}')
    logger.info(
        f'Selected CRS: {parameters.get("crs")}\t'
        f'Interpolation: {parameters.get("interpolation")}'
    )

    try:
        var_info = VarInfoFromNetCDF4(
            parameters['input_file'],
            short_name=collection_short_name,
            config_file=CF_CONFIG_FILE,
        )
    except Exception as err:
        logger.error(f'Unable to parse input file variables: {str(err)}')
        raise Exception('Unable to parse input file variables') from err

    science_variables = var_info.get_science_variables()

    if len(science_variables) == 0:
        raise Exception('No science variables found in input file')

    logger.info(f'Input file has {len(science_variables)} science variables')

    # Loop through each dataset and reproject
    logger.debug('Using pyresample for reprojection.')
    outputs = resample_all_variables(
        parameters, science_variables, temp_dir, logger, var_info
    )

    if not outputs:
        raise Exception('No variables could be reprojected')

    # Now merge outputs (unless we only have one)
    metadata_variables = var_info.get_metadata_variables()
    nc_merge.create_output(
        parameters,
        output_file,
        temp_dir,
        science_variables,
        metadata_variables,
        logger,
        var_info,
    )

    # Return the output file back to Harmony
    return output_file


def get_parameters_from_message(
    message: Message, granule_url: str, input_file: str
) -> Dict:
    """A helper function to parse the input Harmony message and extract
    required information. If the message is missing parameters, then
    default values will be used. The `granule_url` is taken from the
    inbound STAC `Item.asset.href`, denoting a URL to the original source
    of the input granule. The `input_file` is the local path of that input
    granule, as downloaded by `harmony-service-lib-py` utility functions
    for transformation by this service.

    """
    parameters = {
        'crs': rgetattr(message, 'format.crs', CRS_DEFAULT),
        'granule_url': granule_url,
        'input_file': input_file,
        'interpolation': rgetattr(
            message, 'format.interpolation', INTERPOLATION_DEFAULT
        ),
        'x_extent': rgetattr(message, 'format.scaleExtent.x', None),
        'y_extent': rgetattr(message, 'format.scaleExtent.y', None),
        'width': rgetattr(message, 'format.width', None),
        'height': rgetattr(message, 'format.height', None),
        'xres': rgetattr(message, 'format.scaleSize.x', None),
        'yres': rgetattr(message, 'format.scaleSize.y', None),
    }

    parameters['projection'] = Proj(parameters['crs'])

    if parameters['interpolation'] in [None, '', 'None']:
        parameters['interpolation'] = INTERPOLATION_DEFAULT

    # when a user requests both a resolution and dimensions, then ensure the
    # extents are consistent.
    if (parameters['xres'] is not None or parameters['yres'] is not None) and (
        parameters['height'] is not None or parameters['width'] is not None
    ):
        if not has_self_consistent_grid(message):
            raise InvalidTargetGrid()

    if not os.path.isfile(parameters['input_file']):
        raise Exception('Input file does not exist')

    # Verify message and assign values for minimum and maximum x and y.

    if not parameters['x_extent'] and parameters['y_extent']:
        raise Exception('Missing x extent')
    if parameters['x_extent'] and not parameters['y_extent']:
        raise Exception('Missing y extent')
    if parameters['width'] and not parameters['height']:
        raise Exception('Missing cell height')
    if parameters['height'] and not parameters['width']:
        raise Exception('Missing cell width')

    parameters['x_min'] = rgetattr(message, 'format.scaleExtent.x.min', None)
    parameters['x_max'] = rgetattr(message, 'format.scaleExtent.x.max', None)
    parameters['y_min'] = rgetattr(message, 'format.scaleExtent.y.min', None)
    parameters['y_max'] = rgetattr(message, 'format.scaleExtent.y.max', None)

    # Mark the properties that this service will use, so that downstream
    # services will not re-use them.
    message.format.process(
        'crs', 'interpolation', 'scaleExtent', 'scaleSize', 'height', 'width'
    )

    return parameters


def rgetattr(obj, attr: str, *args):
    """Recursive get attribute. Returns attribute from an attribute hierarchy,
    e.g. a.b.c, if it exists. If it doesn't exist, the default value will
    be assigned. Even though the `args` is often optional, in this case the
    default value *must* be defined.

    """

    # functools.reduce will apply _getattr with previous result (obj)
    #   and item from sequence (attr)
    def _getattr(obj, attr):
        return getattr(obj, attr, *args)

    # First call takes first two items, thus need [obj] as first item in sequence
    attribute_value = functools.reduce(_getattr, [obj] + attr.split('.'))

    # Check if the message value is `None` but a non-None default was defined
    if attribute_value is None and args[0] is not None:
        attribute_value = args[0]

    return attribute_value
