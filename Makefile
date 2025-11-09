PACKAGE_NAME = mediatools
PACKAGE_SRC = src/$(PACKAGE_NAME)

SCRIPTS_PATH = ~/code/media-tools/scripts

gopro:
	python3 $(SCRIPTS_PATH)/server_v2.py /mnt/MoStorage/gopro $(SCRIPTS_PATH)/templates/gpt_multi_v07.html --port 8000 -s -w

montage:
	python3 $(SCRIPTS_PATH)/create_montage_v2.py "/mnt/MoStorage/gopro/GoPro 2024-05-31" 30 1 $(SCRIPTS_PATH)/test_montage_05-31.mp4 -s 1 -c 1 -v --width 3840 --height 2160
	python3 $(SCRIPTS_PATH)/create_montage_v2.py "/mnt/MoStorage/gopro/GoPro 2024-09-05" 30 1 $(SCRIPTS_PATH)/test_montage_09-05.mp4 -s 1 -c 1 -v --width 3840 --height 2160
	python3 $(SCRIPTS_PATH)/create_montage_v2.py "/mnt/MoStorage/gopro/GoPro 2024-10-05" 30 1 $(SCRIPTS_PATH)/test_montage_10-05.mp4 -s 1 -c 1 -v --width 3840 --height 2160

	cp $(SCRIPTS_PATH)/test_montage_05-31.mp4 /mnt/MoStorage/gopro/
	cp $(SCRIPTS_PATH)/test_montage_09-05.mp4 /mnt/MoStorage/gopro/
	cp $(SCRIPTS_PATH)/test_montage_10-05.mp4 /mnt/MoStorage/gopro/

#copymontage:


thumbs:
	python3 $(SCRIPTS_PATH)/scan_videos_v1.py "/mnt/MoStorage/gopro/" -t _thumbs


################################## building ##################################
install:
	pip install .

uninstall:
	pip uninstall $(PACKAGE_NAME)


clean_build:
	-rm -r $(PACKAGE_NAME).egg-info
	-rm -r dist
	-rm -r build


################################## testing ##################################
pytest:
	cd tests; pytest *.py

################################## linting ##################################
mypy:
	python -m mypy $(PACKAGE_SRC) --python-version=3.11



################################## Virtual Environments ##################################
activate:
	source $(VIRTUAL_ENV_NAME)/bin/activate

VIRTUAL_ENV_NAME = myenv

venv_new: 
	python -m venv $(VIRTUAL_ENV_NAME)

venv_activate:
	source $(VIRTUAL_ENV_NAME)/bin/activate

venv_deactivate:
	deactivate


################################## Compiling Examples ##################################
EXAMPLE_NOTEBOOK_FOLDER = examples

examples_compile:
	-jupyter nbconvert --to markdown $(EXAMPLE_NOTEBOOK_FOLDER)/*.ipynb
	-mv $(EXAMPLE_NOTEBOOK_FOLDER)/*.md $(MKDOCS_FOLDER)


################################## Make requirements.txt ##################################
REQUIREMENTS_FOLDER = requirements

requirements:
	-mkdir $(REQUIREMENTS_FOLDER)
	pip freeze > $(REQUIREMENTS_FOLDER)/requirements.txt	
	pip list > $(REQUIREMENTS_FOLDER)/packages.txt
	-pip install pipreqs
	pipreqs --force $(PACKAGE_NAME)/ --savepath $(REQUIREMENTS_FOLDER)/used_packages.txt




################################## MKDocs-Material Documentation Website Generation ##################################
# https://squidfunk.github.io/mkdocs-material/
MKDOCS_FOLDER = docs

# https://squidfunk.github.io/mkdocs-material/publishing-your-site/
mkdocs_deploy:
	mkdocs gh-deploy --force

# https://squidfunk.github.io/mkdocs-material/creating-your-site/
mkdocs_serve:
	mkdocs serve

mkdocs_build:
	mkdocs build

# https://squidfunk.github.io/mkdocs-material/getting-started/
mkdocs_setup:
	-pip install mkdocs
	-pip install mkdocs-material
	mkdocs new .
