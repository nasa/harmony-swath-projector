""" Reprojection support for merging single-dataset NetCDF-4 files, produced by
    `pyresample`, back into a single output file with all the necessary
    attributes.
"""
from typing import Dict, Optional, Set, Tuple
import argparse
import logging
import os
import re
import warnings

import netCDF4
import numpy as np

from pymods.exceptions import MissingReprojectedDataError
from pymods.utilities import get_variable_file_path

GDAL_DATASET_NAME = 'Band1'

STD_COOR_ATTRS = {  # only for non-geographic projection case, i.e. not lat/lon
    'x': {'long_name': 'x coordinate of projection',
          'units': 'm',
          'standard_name': 'projection_x_coordinate'},
    'y': {'long_name': 'y coordinate of projection',
          'units': 'm',
          'standard_name': 'projection_y_coordinate'}
}


def create_output(input_file: str, output_file: str, temp_dir: str,
                  science_variables: Set[str],
                  metadata_variables: Set[str] = set(),
                  logger: Optional[logging.Logger] = None) -> None:
    """ Merging the reprojected single-dataset netCDF4 files from `pyresample`
        into a NETCDF-4 file, copying global attributes and metadata
        variables (those without coordinates, which therefore can't be
        reprojected) from the original input file. Then for each listed science
        variable, retrieve the single-band file and copy the reprojected
        variables, and any accompanying CRS and coordinate datasets. Note, the
        coordinate datasets will only be copied once.

    """

    if not logger:
        logger = logging.getLogger(__name__)

    logger.info(f'Creating output file "{output_file}"')

    with netCDF4.Dataset(input_file) as input_dataset, \
         netCDF4.Dataset(output_file, 'w', format='NETCDF4') as output_dataset:

        logger.info('Copying input file attributes to output file.')
        output_dataset.setncatts(read_attrs(input_dataset))

        if has_time_dimension(input_dataset):
            copy_time_dimension(input_dataset, output_dataset, logger)

        for metadata_variable in metadata_variables:
            copy_metadata_variable(input_dataset, output_dataset,
                                   metadata_variable, logger)

        output_extension = os.path.splitext(input_file)[1]

        for variable_name in science_variables:
            dataset_file = get_variable_file_path(temp_dir, variable_name,
                                                  output_extension)

            if os.path.isfile(dataset_file):
                data = netCDF4.Dataset(dataset_file) # pylint: disable=E1101
                set_dimension(data, output_dataset)

                copy_variable(input_dataset, output_dataset, data,
                              variable_name, logger)


                # Note: This assumes single band output files contain
                # coordinates and CRS information in the root of the dataset.
                for variable_key in data.variables: # pylint: disable=E1133
                    existing_keys = list(output_dataset.variables.keys())
                    existing_keys += [GDAL_DATASET_NAME, variable_name]
                    if variable_key not in existing_keys:
                        copy_variable(input_dataset, output_dataset, data,
                                      variable_key, logger)

                data.close()
            else:
                logger.error(f'Cannot find "{dataset_file}".')
                raise MissingReprojectedDataError(variable_name)

        # if 'crs' exists in output, rename it to the grid_mapping_name
        # and update grid_mapping attributes
        if 'crs' in output_dataset.variables.keys():
            new_crs_name = output_dataset['crs'].grid_mapping_name
            output_dataset.renameVariable('crs', new_crs_name)
            for name, var in output_dataset.variables.items():
                # avoid the new crs var itself, replace grid_mapping attribute
                if name != new_crs_name \
                        and hasattr(var, 'grid_mapping'):
                    var.grid_mapping = new_crs_name


def read_attrs(inf):
    """read attribute from a file/dataset"""
    return inf.__dict__


def has_time_dimension(inf):
    """check if time dimension exists"""
    return 'time' in list(inf.dimensions.keys())


def copy_time_dimension(input_dataset: netCDF4.Dataset,
                        output_dataset: netCDF4.Dataset,
                        logger: logging.Logger) -> None:
    """add time dimension to the output file"""
    logger.info('Adding "time" dimension.')
    time_variable = input_dataset['time']
    output_dataset.createDimension('time', len(time_variable))
    copy_metadata_variable(input_dataset, output_dataset, 'time', logger)


def set_dimension(inf, out):
    """set dimension in the output"""
    for name, dimension in inf.dimensions.items():
        if not (dimension.isunlimited()
                or name in list(out.dimensions.keys())):
            out.createDimension(name, len(dimension))


def copy_metadata_variable(input_dataset: netCDF4.Dataset,
                           output_dataset: netCDF4.Dataset, variable_name: str,
                           logger: logging.Logger) -> None:
    """ Write a metadata variable directly from the input dataset. These
        variables have not been reprojected as they contain no references to
        dimensions or coordinate datasets.

    """
    # TODO: Account for dimensions - potential conflicts between original and
    # reprojected dimension names.
    logger.info(f'Adding input file variable "{variable_name}" to the output.')
    variable = input_dataset[variable_name]
    data_type = input_dataset[variable_name].datatype
    attributes = read_attrs(variable)
    fill_value = get_fill_value_from_attributes(attributes)

    output_dataset.createVariable(variable_name, data_type,
                                  fill_value=fill_value, zlib=True,
                                  complevel=6)

    output_dataset[variable_name][:] = variable[:]
    output_dataset[variable_name].setncatts(attributes)


def copy_variable(input_dataset: netCDF4.Dataset,
                  output_dataset: netCDF4.Dataset,
                  single_band_output: netCDF4.Dataset,
                  dataset_name: str, logger: logging.Logger) -> None:
    """ Write a reprojected dataset from a single-band output file to the
        merged output file. This will first obtain metadata (dimensions,
        data type and  attributes) from either the single-band output, or from
        the original input file dataset. Then the variable values from the
        single-band output are copied into the data arrays. If the dataset
        attributes include a scale and offset, the output values are adjusted
        accordingly.

    """
    logger.info(f'Adding reprojected "{dataset_name}" to the output')

    # set data type, dimensions, and attributes
    dims, data_type, attrs = get_dataset_meta(input_dataset,
                                              single_band_output,
                                              dataset_name)
    fill_value = get_fill_value_from_attributes(attrs)

    if dataset_name not in single_band_output.variables.keys():
        ori_dataset_name = GDAL_DATASET_NAME
    else:
        ori_dataset_name = dataset_name

    if dims:
        output_dataset.createVariable(dataset_name, data_type, dimensions=dims,
                                      fill_value=fill_value, zlib=True,
                                      complevel=6)
    else:
        output_dataset.createVariable(dataset_name, data_type,
                                      fill_value=fill_value, zlib=True,
                                      complevel=6)

    output_dataset[dataset_name].setncatts(attrs)

    # Manually compute the data value if offset and scale_factor exist for
    # integers. This is necessary so that the netCDF4 library can recompute the
    # integer value from the science value. The library does not support
    # directly providing the integer value when offset and scale_factor are
    # defined.

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', category=UserWarning)
        if (
                single_band_output[ori_dataset_name].shape !=
                output_dataset[dataset_name].shape
        ):
            reshaped = single_band_output[ori_dataset_name][:].reshape(
                output_dataset[dataset_name].shape
            )
            if 'add_offset' in attrs and 'scale_factor' in attrs:
                reshaped = (
                    (reshaped * output_dataset[dataset_name].scale_factor)
                    + output_dataset[dataset_name].add_offset
                )

            output_dataset[dataset_name][:] = reshaped
        else:
            output_dataset[dataset_name][:] = single_band_output[ori_dataset_name][:]


def get_dataset_meta(inf: netCDF4.Dataset,
                     single_band_output: netCDF4.Dataset,
                     dataset_name: str) -> Tuple[Tuple, np.dtype, Dict]:
    """get dataset data type, dimensions, and attributes from reprojection or input"""
    if GDAL_DATASET_NAME in single_band_output.variables:
        single_band_name = GDAL_DATASET_NAME
    else:
        single_band_name = dataset_name

    # TODO: refactor to properly address merging dimensions and reprojected dimensions ?
    # TODO: at least add commentary
    if dataset_name in single_band_output.variables.keys():  # when is this true?
        data_type = single_band_output[dataset_name].datatype
        dims = get_dimensions(single_band_output, dataset_name)
        attrs = read_attrs(inf[dataset_name]) \
            if dataset_name in inf.variables.keys() \
            else read_attrs(single_band_output[dataset_name])
        if dataset_name in STD_COOR_ATTRS:
            attrs.update(STD_COOR_ATTRS[dataset_name])
    else:
        data_type = inf[dataset_name].datatype
        dims = get_dimensions(single_band_output, dataset_name, inf)
        attrs = read_attrs(inf[dataset_name])

        if single_band_output[single_band_name].grid_mapping:
            attrs['grid_mapping'] = single_band_output[single_band_name].grid_mapping

    # remove coordinates attribute if it is no longer valid
    if 'coordinates' in attrs and not check_coor_valid(attrs, inf,
                                                       single_band_output):
        del attrs['coordinates']

    return dims, data_type, attrs


def get_dimensions(single_band_dataset: netCDF4.Dataset, dataset_name: str,
                   inf: netCDF4.Dataset = None) -> Tuple[str]:
    """get dimensions from input"""
    # TODO: refactor to properly address merging dimensions and reprojected dimensions ?
    if inf:
        if 'time' in list(inf.dimensions.keys()):
            return ('time',) + single_band_dataset[GDAL_DATASET_NAME].dimensions
        else:
            return single_band_dataset[GDAL_DATASET_NAME].dimensions
#       return inf[dataset_name].dimensions  # when is this the right answer?

    if single_band_dataset[dataset_name].size > 1:
        return (dataset_name,)

    return None


def check_coor_valid(attrs: Dict, inf: netCDF4.Dataset,
                     single_band_dataset: netCDF4.Dataset) -> bool:
    """ Check if coordinates attributes is still valid after reprojection
        Invalid coordinate reference cases:

          1) Coordinate variable listed in attribute does not exist in single
             band output dataset.
          2) Coordinate variable array shape in the reprojected, single-band
             dataset does not match the input coordinate array shape.

    """
    coordinates_attribute = attrs.get('coordinates')

    if coordinates_attribute is not None:
        coors = re.split(' |,', coordinates_attribute)
    else:
        coors = []

    valid = True

    for coor in coors:
        if coor not in single_band_dataset.variables:
            valid = False
            break
        elif coor in single_band_dataset.variables and coor in inf.variables:
            if single_band_dataset[coor].shape != inf[coor].shape:
                valid = False
                break

    return valid


def get_fill_value_from_attributes(variable_attributes: Dict) -> Optional:
    """ Check attributes for _FillValue. If present return this and remove the
        _FillValue attribute from the input dictionary. Otherwise return None.

    """
    return variable_attributes.pop('_FillValue', None)


# main program
if __name__ == "__main__":
    PARSER = argparse.ArgumentParser(prog='nc_merge',
                                     description='Merged reprojected netcdf4 files into one')
    PARSER.add_argument('--ori-inputfile', dest='ori_inputfile',
                        help='Original input netcdf4 file(before reprojection)')
    PARSER.add_argument('--output-filename', dest='output_filename',
                        help='Merged netcdf4 output file')
    PARSER.add_argument('--proj-dir', dest='proj_dir',
                        help='Output directory where projected netcdf4 files are')
    PARSER.add_argument('--science-variables', dest='science_variables',
                        help='Variables to include in the merged output file')
    ARGS = PARSER.parse_args()

    logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')

    create_output(ARGS.ori_inputfile, ARGS.output_filename, ARGS.proj_dir,
                  ARGS.science_variables)
