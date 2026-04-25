gopro:
	python3 $(SCRIPTS_PATH)/server_v2.py $(GOPRO_DIR) $(SCRIPTS_PATH)/templates/gpt_multi_v07_crazy.html --port 8000 -s

montage:
	python3 $(SCRIPTS_PATH)/create_montage_v2.py "$(SAFARI_DIR)/*.mp4" 20 5 "$(SAFARI_COMPILATIONS_DIR)/safari_shared_compilation.mp4" -s 0 -c 1 -v --width 1920 --height 1080
	
#python3 $(SCRIPTS_PATH)/create_montage_v2.py "$(GOPRO_DIR)/GoPro 2025-10-**/GX*.mp4" 120 3 "$(GOPRO_COMPILATIONS_DIR)/safari_and_kuwait2.mp4" -s 2 -c 1 -v --width 3840 --height 2160
#copymontage:
old_host:
	python3 $(SCRIPTS_PATH)/server_v2.py $(MEDIA_DIR) $(SCRIPTS_PATH)/templates/gpt_multi_v07.html --port 8000 -s -w

host:
	python3 $(SCRIPTS_PATH)/server_v3.py $(MEDIA_DIR)/ $(SCRIPTS_PATH)/templates/gpt_multi_v07.html --port 8000 -s

make_host:
	python3 $(SCRIPTS_PATH)/server_v3.py $(MEDIA_DIR)/ $(SCRIPTS_PATH)/templates/gpt_multi_v07.html --port 8000 -s -w


thumbs:
	python3 $(SCRIPTS_PATH)/scan_videos_v1.py "$(MEDIA_DIR)" --make-thumbs
