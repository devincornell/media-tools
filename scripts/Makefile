server:
	python3 $(SCRIPTS_PATH)/server_v4.py --root-path $(GOPRO_DIR) --template-path $(SCRIPTS_PATH)/templates/gpt_multi_v07_crazy.html --port 8000 -s

montage:
	python3 $(SCRIPTS_PATH)/create_montage_v2.py "$(SAFARI_DIR)/*.mp4" 20 5 "$(SAFARI_COMPILATIONS_DIR)/safari_shared_compilation.mp4" -s 0 -c 1 -v --width 1920 --height 1080
	
