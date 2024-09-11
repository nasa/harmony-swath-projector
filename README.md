# Data Services Swath Projector

To download source code:

```bash
git clone https://github.com/nasa/harmony-swath-projector
```

To build the Docker image:

```bash
cd harmony-swath-projector
./bin/build-image
```

### Directory contents:

* .snyk - A file used by the Snyk webhook to ensure the correct version of
  Python is used when installing the full dependency tree for the Swath
  Projector. This file should be updated when the version of Python is updated
  in the service Docker image.
* bin - A directory containing scripts to build and run Docker images. This
  includes the service and test Docker images.
* docs - A directory containing documentations, primarily in Jupyter notebooks.
* docker - A directory containing the service and test Dockerfiles.
* pip_requirements.txt - A file containing third party packages to be installed
  via Pip.
* swath_projector - A directory containing the source code for the service.
* tests - A directory containing a Python unit-test suite.

### Running the Swath Projector:

The Swath Projector can be run and tested as part of a local installation of
Harmony. See <https://github.com/nasa/harmony/blob/main/README.md> for more
details.

### To run the service locally, by invoking the Python module directly.

First ensure you are in a conda environment, with the conda and Pip dependencies
installed, as specified in their requirements files.

```
conda create --name=swathprojector python=3.11 -q \
    --channel conda-forge --channel defaults -y
conda activate swathprojector
pip install -r pip_requirements.txt
```

For simple invocations, you can then use the `bin.project_local_granule` Python
module:

```
$ cd harmony-swath-projector
$ python
>>> from bin.project_local_granule import project_granule
>>> project_granule('<full path to local granule, including: file:///>')
```

The `project_granule` function allows a user to specify the target
Coordinate Reference System (CRS) and interpolation method. For more
complicated requests a user can mimic the behavior of the `project_granule`
script, but defining a custom input Harmony message with more parameters
defined. When manually constructing and invoking a Harmony message, the
environment variables `ENV`, `OAUTH_CLIENT_ID`, `OAUTH_PASSWORD`,
`OAUTH_REDIRECT_URI`, `STAGING_BUCKET` and `STAGING_PATH` will need to be
manually set. If `ENV=dev` or `ENV=test`, then the other environment variables
can be set to anything. Be careful not to update these variables in the same
environment as a locally running instance of Harmony.

### Message schema:

The Swath Projector can specify several options for reprojection in the
`format` property of the Harmony message:

```
{
  ...,
  "format": {
    "crs": "CRS:84",
    "interpolation": "bilinear",
    "width": 1000,
    "height": 500,
    "scaleExtent": {
      "x": {"min": -180, "max": 180},
	  "y": {"min": -90, "max": 90}
    },
    "scaleSize": {"x": 1, "y": 1}
  },
  ...
}
```

* `crs`: Either an EPSG code, or a Proj4 string. Default to geographic coordinates.
* `interpolation`: `near`, `bilinear`, `ewa` or `ewa-nn`. Currently defaults to
  `ewa-nn`, which uses elliptically weighted averaging to pick the value of the
  highest weighted pixel in relation to the output grid pixel.
* `width`: The number of output grid pixels in the `x` dimension. Should be used
  with `height`. The default value is the `x` `scaleExtent` divided by the `x`
  resolution.
* `height`: The number of output grid pixels in the `y` dimension. Should be used
  with `width`. The default value is the `y` `scaleExtent` divided by the `y`
  resolution.
* `scaleExtent`: An object for each of the `x` and `y` dimension of the image,
  specifying the minimum and maximum extent of that dimension in the reprojected
  CRS. If the `scaleExtent` is not specified, it is derived from the walking the
  perimeter of the input grid, reprojected those points to the target CRS, and
  finding the extreme values in each reprojected dimension.
* `scaleSize`: The resolution of each output pixel in the reprojected CRS.  The
  default values are derived from finding the total area of the swath via
  Gauss' Area formula, and assuming the pixels are square. This should not
  normally be specified if the `height` and `width` are also supplied, in this
  case the grid definition must be internally consistent with itself.  Where
  consistency is determined by the equation `scaleSize = (scaleExtent.max -
  scaleExtent.min) / dimension`


All the attributes in the `format` property are optional, and have defaults as
described.

### Development notes:

The Swath Projector runs within a Docker container (both the project itself,
and the tests that are run for CI/CD). If you add a new Python package to be
used within the Swath Projector (or remove a third party package), the change
in dependencies will need to be recorded in the relevant requirements file:

* `harmony-swath-projector/pip_requirements.txt`: Additional requirements
	installed within the container's conda environment via Pip. These are also
	required for the source code of the Swath Projector to run.
* `harmony-swath-projector/tests/pip_test_requirements.txt`: Requirements only
	used while running tests, such as `pylint` or `coverage`. These are kept
	separate to reduce the dependencies in the delivered software.

### Running tests:

The Swath Projector has Python tests that use the `unittest` package. These can
be run within a Docker container using the following two scripts:

```bash
# Build a Docker image with all test files and dependencies
./bin/build-test

# Execute the `unittest` suite within a Docker container
./bin/run-test /full/path/to/swath-projector-coverage
```
Coverage reports are being generate for each build in GitHub, and saved as
artifacts.

The tests can also be run outside of the Docker container, for faster checks
during development. To do so, first activate the requisite conda environment,
which will need requirements (including the test Pip requirements). Then run:

```
export ENV=test
python -m unittest discover tests
```

Note - before opening a pull request, all tests should be run in the Docker
container environment, to be sure that there isn't something different between
the local development environment and the environment in which the Swath
Projector will actually run. Additionally, the Docker container invocation will
provide pylint checking, to ensure linting errors have not been added during
development.

### Versioning

As a Harmony service, the Swath Projector is meant to follow semantic version
numbers (e.g., `major.minor.patch`). This version is included in the
`docker/service_version.txt` file. When updating the Swath Projector, the
version number contained in that file should be incremented before creating a
pull request.

The general rules for which version number to increment are:

* Major: When API changes are made to the service that are not backwards
  compatible.
* Minor: When functionality is added in a backwards compatible way.
* Patch: Used for backwards compatible bug fixes or performance improvements.

When the Docker image is built, it will be tagged with the semantic version
number as stored in `docker/service_version.txt`.

## CI/CD:

The CI/CD for the Swath Projector is contained in GitHub workflows in the
`.github/workflows` directory:

* `run_tests.yml` - A reusable workflow that builds the service and test Docker
  images, then runs the Python unit test suite in an instance of the test
  Docker container.
* `run_tests_on_pull_request.yml` - Triggered for all PRs against the `main`
  branch. It runs the workflow in `run_tests.yml` to ensure all tests pass for
  the new code.
* `publish_docker_image.yml` - Triggered either manually or for commits to the
  `main` branch that contain changes to the `docker/service_version.txt` file.

The `publish_docker_image.yml` workflow will:

* Run the full unit tests suite, to prevent publication of broken code.
* Extract the semantic version number from `docker/service_version.txt`.
* Extract the release notes for the most recent version from `CHANGELOG.md`.
* Create a GitHub release that will also tag the related git commit with the
  semantic version number.

Before triggering a release, ensure both the `docker/service_version.txt` and
`CHANGELOG.md` files are updated. The `CHANGELOG.md` file requires a specific
format for a new release, as it looks for the following string to define the
newest release of the code (starting at the top of the file).

```
## vX.Y.Z
```

### pre-commit hooks:

This repository uses [pre-commit](https://pre-commit.com/) to enable pre-commit
checking the repository for some coding standard best practices. These include:

* Removing trailing whitespaces.
* Removing blank lines at the end of a file.
* JSON files have valid formats.
* [ruff](https://github.com/astral-sh/ruff) Python linting checks.
* [black](https://black.readthedocs.io/en/stable/index.html) Python code
  formatting checks.

To enable these checks:

```bash
# Install pre-commit Python package as part of test requirements:
pip install -r tests/pip_test_requirements.txt

# Install the git hook scripts:
pre-commit install

# (Optional) Run against all files:
pre-commit run --all-files
```

When you try to make a new commit locally, `pre-commit` will automatically run.
If any of the hooks detect non-compliance (e.g., trailing whitespace), that
hook will state it failed, and also try to fix the issue. You will need to
review and `git add` the changes before you can make a commit.

It is planned to implement additional hooks, possibly including tools such as
`mypy`.

[pre-commit.ci](pre-commit.ci) is configured such that these same hooks will be
automatically run for every pull request.

## Get in touch:

You can reach out to the maintainers of this repository via email:

* david.p.auty@nasa.gov
* owen.m.littlejohns@nasa.gov
