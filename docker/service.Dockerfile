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
FROM python:3.13-slim-bookworm

WORKDIR "/home"

RUN apt-get update

# Add dependencies
COPY pip_requirements.txt .

RUN pip install --no-input --no-cache-dir \
    -r pip_requirements.txt

# Bundle app source
COPY ./swath_projector swath_projector

# Configure a container to be executable via the `docker run` command.
ENTRYPOINT ["python", "-m", "swath_projector"]
