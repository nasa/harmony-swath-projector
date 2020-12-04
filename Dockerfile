#
# Using Conda within ENTRYPOINT was taken from:
# https://pythonspeed.com/articles/activate-conda-dockerfile/
#

FROM continuumio/miniconda3

WORKDIR "/home"

# Add dependencies
COPY conda_requirements.txt .
COPY pip_requirements.txt .

# Create Conda environment
RUN conda create -y --name swotrepr --file conda_requirements.txt python=3.7 -q \
	--channel conda-forge \
	--channel defaults

# Install additional Pip dependencies
RUN conda run --name swotrepr pip install --no-input -r pip_requirements.txt

# Bundle app source
COPY ./pymods pymods
COPY swotrepr.py .

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

# Configure a container to be executable via the `docker run` command.
ENTRYPOINT ["python", "swotrepr.py"]
