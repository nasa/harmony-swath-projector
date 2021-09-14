#
# Using Conda within ENTRYPOINT was taken from:
# https://pythonspeed.com/articles/activate-conda-dockerfile/
#
# This Dockerfile will create a base image containing all the Conda and Pip
# requirements for SwotRepr.
#
# This Dockerfile does not copy the pymods or the test directory, these will
# be copied when the image is run as a container, to allow more rapid
# development iteration.
#

FROM continuumio/miniconda3

WORKDIR "/home"

# Copy requirements files
COPY pip_requirements.txt .
COPY test/pip_test_requirements.txt .

# Create Conda environment
RUN conda create -y --name swotrepr python=3.7 -q \
	--channel conda-forge \
	--channel defaults

# Install additional Pip dependencies
RUN conda run --name swotrepr pip install -r pip_requirements.txt

# Install additional Pip requirements (for testing)
RUN conda run --name swotrepr pip install --no-input -r pip_test_requirements.txt

# Set conda environment to subsetter, as `conda run` will not stream logging.
# Setting these environment variables is the equivalent of `conda activate`.
ENV _CE_CONDA='' \
    _CE_M='' \
    CONDA_DEFAULT_ENV=swotrepr \
    CONDA_EXE=/opt/conda/bin/conda \
    CONDA_PREFIX=/opt/conda/envs/swotrepr \
    CONDA_PREFIX_1=/opt/conda \
    CONDA_PROMPT_MODIFIER=(swotrepr) \
    CONDA_PYTHON_EXE=/opt/conda/bin/python \
    CONDA_ROOT=/opt/conda \
    CONDA_SHLVL=2 \
    PATH="/opt/conda/envs/swotrepr/bin:${PATH}" \
    SHLVL=1
