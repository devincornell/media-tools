server:
	cd $(SCRIPTS_PATH)/.. && uv run --group api python -m apps.api --root-path $(GOPRO_DIR) --port 8000

montage:
	python3 $(SCRIPTS_PATH)/create_montage_v2.py "$(SAFARI_DIR)/*.mp4" 20 5 "$(SAFARI_COMPILATIONS_DIR)/safari_shared_compilation.mp4" -s 0 -c 1 -v --width 1920 --height 1080
	
