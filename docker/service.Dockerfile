#
# Service image for ghcr.io/nasa/harmony-swath-projector, a Harmony backend
# service that projects Earth Observation, L2 swath files of a NetCDF-4 format.
# The output from this service is a NetCDF-4 file containing the data projected
# on to a grid of the specified projection.
#
# This image instantiates a conda environment, with required packages, before
# Installing additional dependencies via Pip. The service code is then copied
# into the Docker image, before environment variables are set to activate the
# created conda environment.
#
# 2021-07-15: Change Python version from 3.7 to 3.9
# 2023-07-20: Update Python version to 3.11.
# 2023-11-16: Update conda environment name to "swathprojector"
#
FROM continuumio/miniconda3

WORKDIR "/home"

# Add dependencies
COPY pip_requirements.txt .

# Create Conda environment
RUN conda create -y --name swathprojector python=3.11 -q \
    --channel conda-forge --channel defaults && conda clean --all --quiet --yes

# Install additional Pip dependencies
RUN conda run --name swathprojector pip install --no-input -r pip_requirements.txt

# Bundle app source
COPY ./swath_projector swath_projector

# Set conda environment to subsetter, as `conda run` will not stream logging.
# Setting these environment variables is the equivalent of `conda activate`.
ENV _CE_CONDA='' \
    _CE_M='' \
    CONDA_DEFAULT_ENV=swathprojector \
    CONDA_EXE=/opt/conda/bin/conda \
    CONDA_PREFIX=/opt/conda/envs/swathprojector \
    CONDA_PREFIX_1=/opt/conda \
    CONDA_PROMPT_MODIFIER=(swathprojector) \
    CONDA_PYTHON_EXE=/opt/conda/bin/python \
    CONDA_ROOT=/opt/conda \
    CONDA_SHLVL=2 \
    PATH="/opt/conda/envs/swathprojector/bin:${PATH}" \
    SHLVL=1

# Configure a container to be executable via the `docker run` command.
ENTRYPOINT ["python", "-m", "swath_projector"]
