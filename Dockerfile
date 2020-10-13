#
# Using Conda within ENTRYPOINT was taken from:
# https://pythonspeed.com/articles/activate-conda-dockerfile/
#

FROM continuumio/miniconda3

WORKDIR "/home"

# Bundle app source
COPY ./pymods pymods
COPY swotrepr.py .
COPY conda_requirements.txt .
COPY pip_requirements.txt .

# Create Conda environment
RUN conda create --name swotrepr --file conda_requirements.txt python=3.7 -q \
	--channel conda-forge \
	--channel defaults

# Install additional Pip dependencies
RUN conda run --name swotrepr pip install -r pip_requirements.txt

# Set conda environment to subsetter, as `conda run` will not stream logging.
# Setting these environment variables is the equivalent of `conda activate`.
ENV _CE_CONDA ''
ENV _CE_M ''
ENV CONDA_DEFAULT_ENV swotrepr
ENV CONDA_EXE /opt/conda/bin/conda
ENV CONDA_PREFIX /opt/conda/envs/swotrepr
ENV CONDA_PREFIX_1 /opt/conda
ENV CONDA_PROMPT_MODIFIER (swotrepr)
ENV CONDA_PYTHON_EXE /opt/conda/bin/python
ENV CONDA_ROOT /opt/conda
ENV CONDA_SHLVL 2
ENV PATH "/opt/conda/envs/swotrepr/bin:${PATH}"
ENV SHLVL 1

# Configure a container to be executable via the `docker run` command.
ENTRYPOINT ["python", "swotrepr.py"]
