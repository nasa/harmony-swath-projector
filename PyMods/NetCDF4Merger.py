"""
    Reprojection support for merging single-dataset NetCDF 4 files produced by gdalwarp back
    into a single output file with all the necessary attributes.
"""
import argparse
import logging
import os
import re
import netCDF4
import warnings

GDAL_DATASET_NAME = 'Band1'

STD_COOR_ATTRS = {  # only for non-geographic projection case, i.e. not lat/lon
    'x': {'long_name': 'x coordinate of projection',
          'units': 'm',
          'standard_name': 'projection_x_coordinate'},
    'y': {'long_name': 'y coordinate of projection',
          'units': 'm',
          'standard_name': 'projection_y_coordinate'}
}


def create_output(inputfile, outputfile, temp_dir, logger=None):
    """
        Merging the reprojected single-dataset netCDF4 files from GDAL into one, and copy attributes
        from the original input file
    """

    if not logger:
        logger = logging.getLogger(__name__)
    logger.info("Creating output file '%s'", outputfile)

    with netCDF4.Dataset(inputfile) as inf, netCDF4.Dataset(outputfile, 'w',
                                                            format='NETCDF4') as out:

        out.setncatts(read_attrs(inf))

        files = [f for f in os.listdir(temp_dir)
                 if f != os.path.basename(outputfile)
                 and not f.startswith('.')]  # macos "hidden" files
        if has_time_dimension(inf):
            copy_time_dimension(inf, out)

        for file in files:
            logger.info("Adding '%s' to the output", file)
            data = netCDF4.Dataset(temp_dir + '/' + file)
            set_dimension(data, out)

            for name, var in data.variables.items():
                if name not in list(out.variables.keys()):
                    if name != GDAL_DATASET_NAME:
                        copy_variable(inf, out, data, name, logger)
                    else:
                        dataset_name = find_dataset_name(inf, os.path.splitext(file)[0])
                        copy_variable(inf, out, data, dataset_name, logger)

        # if 'crs' exists in output, rename it to the grid_mapping_name
        # and update grid_mapping attributes
        if 'crs' in out.variables.keys():
            new_crs_name = out['crs'].grid_mapping_name
            out.renameVariable('crs', new_crs_name)
            for name, var in out.variables.items():
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

def copy_time_dimension(inf, out):
    """add time dimension to the output file"""
    out.createDimension('time', len(inf.dimensions['time']))

def set_dimension(inf, out):
    """set dimension in the output"""
    for name, dimension in inf.dimensions.items():
        if not (dimension.isunlimited()
                or name in list(out.dimensions.keys())):
            out.createDimension(name, len(dimension))


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


def copy_variable(inf, out, repr, dataset_name, logger):
    """write dataset value to the output"""

    # set data type, dimensions, and attributes
    dims, data_type, attrs = get_dataset_meta(inf, repr, dataset_name)

    if dataset_name not in repr.variables.keys():
        ori_dataset_name = GDAL_DATASET_NAME
    else:
        ori_dataset_name = dataset_name

    new_dataset_name = dataset_name.split('/')[-1]  # just basename at end of path

    fill_value = None
    if '_FillValue' in attrs:
        fill_value = attrs['_FillValue']
        del attrs['_FillValue']

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
                reshaped = (reshaped * out[new_dataset_name].scale_factor)
                    + out[new_dataset_name].add_offset

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


# main program
if __name__ == "__main__":
    print('Main')
    PARSER = argparse.ArgumentParser(prog='NetCDF4Merger',
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
