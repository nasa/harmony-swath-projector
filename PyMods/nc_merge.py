""" Reprojection support for merging single-dataset NetCDF-4 files, produced by
    either gdalwarp or pyresample, back into a single output file with all the
    necessary attributes.
"""
from typing import Dict, Optional, Set
import argparse
import logging
import os
import re
import warnings

import netCDF4

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
                  metadata_variables: Set[str] = set(),
                  logger: Optional[logging.Logger] = None) -> None:
    """ Merging the reprojected single-dataset netCDF4 files from GDAL into
        one, and copy attributes from the original input file

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

        files = [f for f in os.listdir(temp_dir)
                 if f != os.path.basename(output_file)
                 and not f.startswith('.')]  # macos "hidden" files

        for dataset_file in files:
            logger.info(f'Adding "{dataset_file}" to the output')
            data = netCDF4.Dataset(os.sep.join([temp_dir, dataset_file]))
            set_dimension(data, output_dataset)

            for name, var in data.variables.items():
                if name not in list(output_dataset.variables.keys()):
                    if name != GDAL_DATASET_NAME:
                        copy_variable(input_dataset, output_dataset, data,
                                      name, logger)
                    else:
                        dataset_name = find_dataset_name(
                            input_dataset, os.path.splitext(dataset_file)[0]
                        )
                        copy_variable(input_dataset, output_dataset, data,
                                      dataset_name, logger)

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


def find_dataset_name(inf, name):
    # TODO: refactor reproject.py and this module to rename intermediate .nc4 files
    # to include group names, and then decode these file names to establish
    # dataset name with group path.  Then this method is not needed.
    dataset_name = None

    def find_dataset_in_group(inf, group, name):
        for variable in inf[group].variables:
            if name == variable:
                return f"{group}/{variable}"
            for subgroup in inf[group].groups:
                dataset_name = find_dataset_in_group(inf, subgroup, name)
                if dataset_name:
                    return dataset_name

    for variable in inf.variables:
        if name == variable:
            return variable
    for group in inf.groups:
        dataset_name = find_dataset_in_group(inf, group, name)
        if dataset_name:
            return dataset_name
    return dataset_name


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
    data_type = get_data_type(input_dataset, variable_name)
    attributes = read_attrs(variable)
    fill_value = get_fill_value_from_attributes(attributes)

    output_dataset.createVariable(variable_name, data_type,
                                  fill_value=fill_value, zlib=True,
                                  complevel=6)

    output_dataset[variable_name][:] = variable[:]
    output_dataset[variable_name].setncatts(attributes)


def copy_variable(inf, out, repr, dataset_name, logger):
    """write dataset value to the output"""

    # set data type, dimensions, and attributes
    dims, data_type, attrs = get_dataset_meta(inf, repr, dataset_name)
    fill_value = get_fill_value_from_attributes(attrs)

    if dataset_name not in repr.variables.keys():
        ori_dataset_name = GDAL_DATASET_NAME
    else:
        ori_dataset_name = dataset_name

    new_dataset_name = dataset_name.split('/')[-1]  # just basename at end of path

    if dims:
        out.createVariable(new_dataset_name, data_type, dims,
                           fill_value=fill_value, zlib=True, complevel=6)
    else:
        out.createVariable(new_dataset_name, data_type,
                           fill_value=fill_value, zlib=True, complevel=6)

    out[new_dataset_name].setncatts(attrs)

    # manually compute the data value if offset and scale_factor exist for integers

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        if repr[ori_dataset_name][:].shape != out[new_dataset_name].shape:
            reshaped = repr[ori_dataset_name][:].reshape(out[new_dataset_name].shape)
            if 'add_offset' in attrs and 'scale_factor' in attrs:
                reshaped = ((reshaped * out[new_dataset_name].scale_factor)
                            + out[new_dataset_name].add_offset)

            out[new_dataset_name][:] = reshaped
        else:
            out[new_dataset_name][:] = repr[ori_dataset_name][:]


def get_dataset_meta(inf, repr, dataset_name):
    """get dataset data type, dimensions, and attributes from reprojection or input"""
    # TODO: refactor to properly address merging dimensions and reprojected dimensions ?
    # TODO: at least add commentary
    if dataset_name in repr.variables.keys():  # when is this true?
        data_type = get_data_type(repr, dataset_name)
        dims = get_dimensions(repr, dataset_name)
        attrs = read_attrs(inf[dataset_name]) \
            if dataset_name in inf.variables.keys() \
            else read_attrs(repr[dataset_name])
        if dataset_name in STD_COOR_ATTRS:
            attrs.update(STD_COOR_ATTRS[dataset_name])
    else:
        data_type = get_data_type(inf, dataset_name)
        dims = get_dimensions(repr, dataset_name, inf)
        attrs = read_attrs(inf[dataset_name])
        if repr[GDAL_DATASET_NAME].grid_mapping:
            attrs['grid_mapping'] = repr[GDAL_DATASET_NAME].grid_mapping

    # remove coordinates attribute if it is no longer valid
    if 'coordinates' in attrs and not check_coor_valid(attrs, inf, repr):
        del attrs['coordinates']

    return dims, data_type, attrs

def get_data_type(inf, dataset_name):
    """get data type"""
    return inf[dataset_name].datatype

def get_dimensions(repr, dataset_name, inf=None):
    """get dimensions from input"""
    # TODO: refactor to properly address merging dimensions and reprojected dimensions ?
    if inf:
        if 'time' in list(inf.dimensions.keys()):
            return ('time',) + repr[GDAL_DATASET_NAME].dimensions
        else:
            return repr[GDAL_DATASET_NAME].dimensions
#       return inf[dataset_name].dimensions  # when is this the right answer?

    if repr[dataset_name].size > 1:
        return (dataset_name,)
    return None


def check_coor_valid(attrs, inf, repr):
    """
        Check if coordinates attributes is still valid after reprojection
        Invalid coordinate reference cases:
          1) coordinate reference no longer exists
          2) coordinate size does not match after reprojection
    """
    coors = re.split(' |,', attrs['coordinates'])
    valid = True

    for coor in coors:
        if coor not in repr.variables.keys():
            valid = False
            break
        elif coor in repr.variables.keys() and coor in inf.variables.keys():
            if repr[coor].shape != inf[coor].shape:
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
    print('Main')
    PARSER = argparse.ArgumentParser(prog='nc_merge',
                                     description='Merged reprojected netcdf4 files into one')
    PARSER.add_argument('--ori-inputfile', dest='ori_inputfile',
                        help='Original input netcdf4 file(before reprojection)')
    PARSER.add_argument('--output-filename', dest='output_filename',
                        help='Merged netcdf4 output file')
    PARSER.add_argument('--proj-dir', dest='proj_dir',
                        help='Output directory where projected netcdf4 files are')
    ARGS = PARSER.parse_args()

    logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')

    create_output(ARGS.ori_inputfile, ARGS.output_filename, ARGS.proj_dir)
