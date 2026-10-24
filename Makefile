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
	uv run --group api --extra client pytest tests/test_api.py tests/test_fileops.py

# Job tests need a disposable MongoDB (never point this at a real database).
TEST_MONGODB_URL ?= mongodb://127.0.0.1:27099

test_jobs:
	TEST_MONGODB_URL=$(TEST_MONGODB_URL) uv run --group api --extra client pytest tests/test_jobs.py tests/test_media_jobs.py

# mongo:8 refuses to start on Linux >= 6.19; apparmor=unconfined is needed on this host's Docker.
test_mongo_up:
	docker run -d --rm --name mt-test-mongo --security-opt apparmor=unconfined -p 127.0.0.1:27099:27017 mongo:7

test_mongo_down:
	docker rm -f mt-test-mongo


################################## API Server ##################################
.PHONY: serve_dwhost serve_gopro worker

serve_dwhost: SERVE_ROOT = /mnt/hdd-b/.sys/
serve_dwhost: SERVE_THUMBS = /mnt/hdd-b/.dwhelper_thumbs/
serve_dwhost: SERVE_DB = dwhost
serve_dwhost: SERVE_TEMPLATE = scripts/templates/gpt_multi_v09.html
serve_dwhost: SERVE_PORT = 6969
serve_dwhost: SERVE_COPY_ROOTS = /mnt/hdd-b/

serve_gopro: SERVE_ROOT = /mnt/hdd-a/gopro/gopro_raw_organized
serve_gopro: SERVE_THUMBS = /mnt/hdd-a/gopro/gopro_raw_organized_thumbs
serve_gopro: SERVE_DB = gopro
serve_gopro: SERVE_TEMPLATE = scripts/templates/gpt_multi_v07_crazy.html
serve_gopro: SERVE_PORT = 8000
serve_gopro: SERVE_COPY_ROOTS =

# SERVE_COPY_ROOTS: space-separated dirs that move jobs may read from (empty disables move jobs).
# SERVE_WORKERS: jobs run at once (default 4).
serve_dwhost serve_gopro:
	sudo uv run --group api python -m apps.api \
		--root-path "$(SERVE_ROOT)" \
		--thumb-path "$(SERVE_THUMBS)" \
		--database-name $(SERVE_DB) \
		--template-path $(SERVE_TEMPLATE) \
		--reels-template-path scripts/templates/reels.html \
		$(foreach r,$(SERVE_COPY_ROOTS),--copy-source-root "$(r)") \
		$(if $(SERVE_WORKERS),--worker-concurrency $(SERVE_WORKERS)) \
		--port $(SERVE_PORT)

worker:
	uv run --group api python -m apps.worker

api_serve:
	uv run --group api uvicorn apps.api.main:app --reload

docker_build:
	docker build -t mediatools-api .

docker_up:
	docker compose up -d --build


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
