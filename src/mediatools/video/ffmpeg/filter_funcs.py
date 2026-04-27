
from .filters import filtergraph_link, filter_link, filterchain, filtergraph


def blurred_padding_filter(target_w: int, target_h: int, blur_sigma: int = 25):
    return filtergraph(

        # 1. Split the input video stream into two parts: `bg_raw` and `fg_raw`.
        filtergraph_link(filter_spec='split', input='0:v', outputs=['bg_raw', 'fg_raw']), 

        # 2. Fill the frame completely without stretching or leaving black bars
        filtergraph_link(
            filter_spec = filterchain(
                
                # 2a. Scale `bg_raw` to fill the frame while preserving aspect ratio, which may cause some cropping.
                filter_link(
                    "scale", 
                    w=target_w, 
                    h=target_h, 
                    force_original_aspect_ratio="increase"
                ),
                
                # 2b. Crop the scaled `bg_raw` to the target dimensions.
                filter_link("crop", w=target_w, h=target_h),
                
                # 2c. Apply a gaussian blur to the cropped background.
                filter_link("gblur", sigma=blur_sigma)
            ), 
            input="bg_raw", 
            output="bg_ready"
        ), 
        
        # 3. Scale `fg_raw` to fit within the target dimensions while preserving aspect ratio, which may cause letterboxing/pillarboxing.
        filtergraph_link(
            filter_spec = "scale", 
            w=target_w, 
            h=target_h, 
            force_original_aspect_ratio="decrease",
            input="fg_raw",
            output="fg_ready"
        ),

        # 4. Overlay `fg_ready` on top of `bg_ready` according to the centering math: `x="(W-w)/2", y="(H-h)/2"`.
        #    - `x` and `y` are the starting coordinates of the overlay.
        #    - `W` and `H` are the width and height of the main/background video
        #    - `w` and `h`  are the width and height of the foreground video.
        filtergraph_link(
            filter_spec="overlay", 
            inputs=["bg_ready", "fg_ready"], 
            x="(W-w)/2", 
            y="(H-h)/2"
        )
    )