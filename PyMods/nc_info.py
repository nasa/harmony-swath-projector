import argparse
import logging
from netCDF4 import Dataset


# walk the group tree.
def walktree(top):
    values = top.groups.values()
    yield values
    for value in top.groups.values():
        for children in walktree(value):
            yield children


class NC4Info:
    def __init__(self, ncfile):
        self.rootgroup = Dataset(ncfile)
        self.vars_coord = set()
        self.vars_meta = set()
        self.dims = set()
        self.coords = set()
        self.auxs = set()  # TODO:auxiliary Information

        for children in walktree(self.rootgroup):
            if self.rootgroup.variables:
                for nvar, var in self.rootgroup.variables.items():
                    if 'coordinates' in var.ncattrs():
                        self.vars_coord.add("/" + nvar)
                    else:
                        self.vars_meta.add("/" + nvar)
                for dim in self.rootgroup.dimensions:
                    self.dims.add("/" + dim)
            for child in children:
                if child.variables:
                    for varn, var in child.variables.items():
                        if 'coordinates' in var.ncattrs():
                            self.vars_coord.add(child.path + "/" + varn)
                            vcoords = getattr(var, 'coordinates')
                            if "," not in vcoords:
                                self.coords.add(child.path + "/" + getattr(var, 'coordinates'))
                            else:
                                nvc = vcoords.split(", ")
                                for idx, value in enumerate(nvc):
                                    self.coords.add(child.path + "/" + value)
                        else:
                            self.vars_meta.add(child.path + "/" + varn)
                    for dim in child.dimensions:
                        self.dims.add(child.path + "/" + dim)

    def get_science_variables(self):
        return self.vars_coord - self.vars_meta - self.dims - self.coords

    def get_metadata_variables(self):
        return self.vars_meta - self.dims - self.coords


# Main program start for testing with any input file
#
if __name__ == "__main__":
    PARSER = argparse.ArgumentParser(prog='scan', description='Run NetCDF scaning tool')
    PARSER.add_argument('--file',
                        help='The input file for scanning variables.')
    ARGS = PARSER.parse_args()

    logger = logging.getLogger("SwotRepr")
    syslog = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s")
    #       "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] [%(user)s] %(message)s")
    syslog.setFormatter(formatter)
    logger.addHandler(syslog)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    input_file = ARGS.file

    # ----------------------------------------
    info4 = NC4Info(input_file)
    print(info4.rootgroup.data_model)
    sciVars = info4.get_science_variables()
    print("--------- science_variables ----------")
    print(*(sorted(sciVars)), sep="\n")
    metaVars = info4.get_metadata_variables()
    print("--------- metadata ----------")
    print(*(sorted(metaVars)), sep="\n")
