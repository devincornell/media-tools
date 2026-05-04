
from .core.filters import filtergraph_link, filter_link, filterchain, filtergraph


def filtergraph_animated_thumb(
    target_w: int, 
    target_h: int, 
    fps: int = 10, 
    pts: float = 1.0, 
    use_blurred_padding: bool = False,
    blur_sigma: int = 25, 
    input: str|None = None, 
    output: str|None = None,
    inputs: list[str]|None = None,
    outputs: list[str]|None = None,
    **scale_filter_kwargs,
) -> str:
    '''Create a filterchain that generates an animated thumbnail from a video.
    '''
    sample_chain = filterchain(
        filter_link('setpts', f'PTS/{pts}'),
        filter_link('fps', fps=fps),
    )

    if not use_blurred_padding:
        return filtergraph_link(
            filterchain(
                sample_chain,
                filter_link('scale', w=target_w, h=target_h, **scale_filter_kwargs),
            ),
            input=input,
            output=output,
            inputs=inputs,
            outputs=outputs,
        )
    else:
        connector_name = "sampled"
        return filtergraph(
            filtergraph_link( # does the animated thumb
                sample_chain,
                input=input,
                inputs=inputs,
                output=connector_name,
            ),
            filtergraph_blurred_padding( # does the resize with padding
                target_w=target_w, 
                target_h=target_h, 
                blur_sigma=blur_sigma, 
                input=connector_name, 
                output=output,
                outputs=outputs,
            ),
        )



def filtergraph_blurred_padding(
    target_w: int, 
    target_h: int, 
    blur_sigma: int = 25, 
    input: str|None = None, 
    output: str|None = None,
    inputs: list[str]|None = None,
    outputs: list[str]|None = None,
) -> str:
    '''Create a filtergraph that applies a blurred padding effect to a video. 
    The input video is scaled to fit within the target dimensions while preserving aspect ratio, 
        and the background is filled with a blurred version of the video.
    Args:
        target_w: Target width for the output video.
        target_h: Target height for the output video.
        blur_sigma: Sigma value for the gaussian blur applied to the background (default: 25).
        input: Optional name for the input stream (used in filtergraph linking).
        output: Optional name for the output stream (used in filtergraph linking).
    Returns:
        A filtergraph string that can be used in an FFmpeg command to achieve the blurred padding effect.
    '''
    return filtergraph(

        # 1. Split the input video stream into two parts: `bg_raw` and `fg_raw`.
        filtergraph_link(filter_spec='split', input=input, inputs=inputs, outputs=['bg_raw', 'fg_raw']), 

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
            y="(H-h)/2",
            output=output,
            outputs=outputs,
        )
    )

