PACKAGE_NAME = mediatools
PACKAGE_SRC = src/$(PACKAGE_NAME)



################################## building ##################################
install:
	uv pip install -e . --native-tls


uninstall:
	pip uninstall $(PACKAGE_NAME)


################################## Compiling Examples ##################################
EXAMPLE_NOTEBOOK_FOLDER = examples

examples:
	-jupyter nbconvert --to markdown $(EXAMPLE_NOTEBOOK_FOLDER)/*.ipynb
	-mv $(EXAMPLE_NOTEBOOK_FOLDER)/*.md $(MKDOCS_FOLDER)

################################## Testing ##################################

test:
	#uv run pytest tests/test_ffmpeg_clean.py
	uv run pytest tests/test_ffmpeg_interface.py
	uv run pytest tests/test_image_processing.py
	uv run pytest tests/test_media_management.py
	


################################## MKDocs-Material Documentation Website Generation ##################################
# https://squidfunk.github.io/mkdocs-material/
MKDOCS_FOLDER = docs

# https://squidfunk.github.io/mkdocs-material/publishing-your-site/
mkdocs_deploy:
	mkdocs gh-deploy --force

# https://squidfunk.github.io/mkdocs-material/creating-your-site/
mkdocs_serve:
	mkdocs serve -a localhost:8080

mkdocs_build:
	mkdocs build

# https://squidfunk.github.io/mkdocs-material/getting-started/
mkdocs_setup:
	-pip install mkdocs
	-pip install mkdocs-material
	mkdocs new .
