#
# Using Conda within ENTRYPOINT was taken from:
# https://pythonspeed.com/articles/activate-conda-dockerfile/
#

FROM continuumio/miniconda3

ARG EDL_USERNAME
ARG EDL_PASSWORD

WORKDIR "/home"

# Bundle app source
COPY ./PyMods PyMods
COPY swotrepr.py .
COPY conda_requirements.txt .
COPY pip_requirements.txt .

# Create Conda environment
RUN conda create --name swotrepr --file conda_requirements.txt python=3.7 \
	--channel conda-forge \
	--channel defaults

# Make RUN commands use the Conda environment
SHELL ["conda", "run", "--name", "swotrepr", "/bin/bash", "-c"]

# Install additional Pip dependencies
RUN pip install -r pip_requirements.txt

# Install Harmony
# Note GIT credentials could have issue if password contains certain characters.
# URL encoding additional characters besides '@' may be required
RUN pip install "git+https://${EDL_USERNAME}:${EDL_PASSWORD}@git.earthdata.nasa.gov/scm/harmony/harmony-service-lib-py.git"

ENTRYPOINT ["conda", "run", "--name", "swotrepr", "PYTHONPATH=.", "python", "swotrepr.py"]
