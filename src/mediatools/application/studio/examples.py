'''Built-in example graphs for the studio, written as the ffmpeg commands they correspond to.'''
from __future__ import annotations

import dataclasses

from ...video.ffmpeg import filtergraph_blurred_padding


@dataclasses.dataclass(frozen=True)
class Example:
    id: str
    title: str
    category: str
    summary: str
    explanation: str
    command: str


_BLURRED = filtergraph_blurred_padding(1080, 1920, input="0:v", output="v")

EXAMPLES: list[Example] = [
    Example(
        "downscale-half", "Downscale to half size", "Resize",
        "Make a video half as wide and half as tall (a quarter of the pixels).",
        "One `scale` filter. `iw`/`ih` are the input width/height, so `w=iw/2` halves the width. "
        "`h=-2` means: pick the height that keeps the aspect ratio, rounded to an even number (most encoders need even sizes). "
        "Audio is copied untouched with `-c:a copy`.",
        'ffmpeg -i in.mp4 -vf "scale=w=iw/2:h=-2" -c:a copy {stem}-half.mp4',
    ),
    Example(
        "resize-720p", "Resize to 720p", "Resize",
        "Resize any video to 720 pixels tall, keeping its shape.",
        "`scale=w=-2:h=720` fixes the height and computes the width from the aspect ratio. "
        "`flags=lanczos` picks a sharper resampling algorithm than the default (bicubic).",
        'ffmpeg -i in.mp4 -vf "scale=w=-2:h=720:flags=lanczos" -c:v libx264 -crf 20 -preset medium -c:a copy {stem}-720p.mp4',
    ),
    Example(
        "fit-letterbox", "Fit into 1920x1080 with black bars", "Resize",
        "Make every video exactly 1920x1080 without stretching it: add bars where needed.",
        "`scale` with `force_original_aspect_ratio=decrease` shrinks the picture until it fits inside 1920x1080. "
        "`pad` then places it on a 1920x1080 canvas; `x=(ow-iw)/2` centers it (`ow` = output width, `iw` = input width). "
        "`setsar=1` marks pixels as square so players don't stretch the result.",
        'ffmpeg -i in.mp4 -vf "scale=w=1920:h=1080:force_original_aspect_ratio=decrease,'
        'pad=w=1920:h=1080:x=(ow-iw)/2:y=(oh-ih)/2:color=black,setsar=1" -c:a copy {stem}-1080p.mp4',
    ),
    Example(
        "blurred-background", "Vertical video with blurred background", "Resize",
        "Turn a landscape video into a 1080x1920 vertical video, filling the empty space with a blurred copy.",
        "`split` makes two copies of the picture (an output pad can only feed one filter). "
        "One copy is scaled to *cover* the frame, cropped and blurred (`gblur`); the other is scaled to *fit*. "
        "`overlay` puts the sharp copy on top, centered with `x=(W-w)/2` (`W` = background width, `w` = foreground width). "
        "This is mediatools' `filtergraph_blurred_padding`.",
        f'ffmpeg -i in.mp4 -filter_complex "{_BLURRED}" -map "[v]" -map 0:a? -c:v libx264 -crf 21 {{stem}}-vertical.mp4',
    ),
    Example(
        "crop-square", "Crop to a centered square", "Resize",
        "Cut the largest possible square out of the middle of the video.",
        "`crop` takes the output size and the top-left corner. `min(iw,ih)` is the shorter side; "
        "when `x`/`y` are left out, crop centers the area.",
        "ffmpeg -i in.mp4 -vf \"crop=w='min(iw,ih)':h='min(iw,ih)'\" -c:a copy {stem}-square.mp4",
    ),
    Example(
        "gaussian-blur", "Blur the whole video", "Blur & sharpen",
        "Apply a soft gaussian blur.",
        "`gblur` blurs with a gaussian kernel; `sigma` is the strength (try 2 for subtle, 20 for heavy). "
        "`boxblur` is a faster alternative.",
        'ffmpeg -i in.mp4 -vf "gblur=sigma=10" -c:a copy {stem}-blur.mp4',
    ),
    Example(
        "blur-region", "Blur only a part of the frame", "Blur & sharpen",
        "Blur a rectangle (e.g. a face or a license plate) and leave the rest sharp.",
        "`split` copies the picture; one copy is `crop`ped to the region and blurred with `boxblur`, then "
        "`overlay` puts the blurred patch back at the same position. Change x/y/w/h in both crop and overlay to move it.",
        'ffmpeg -i in.mp4 -filter_complex "[0:v]split[base][tmp];[tmp]crop=w=320:h=240:x=100:y=80,boxblur=luma_radius=20:luma_power=2[blurred];'
        '[base][blurred]overlay=x=100:y=80[v]" -map "[v]" -map 0:a? {stem}-redacted.mp4',
    ),
    Example(
        "denoise-sharpen", "Denoise and sharpen", "Blur & sharpen",
        "Clean up grainy footage, then restore some crispness.",
        "`hqdn3d` is a fast 3D denoiser (spatial + temporal). `unsharp` sharpens: "
        "`luma_msize_x/y` is the matrix size, `luma_amount` the strength (negative values blur).",
        'ffmpeg -i in.mp4 -vf "hqdn3d=luma_spatial=4,unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=0.8" -c:a copy {stem}-clean.mp4',
    ),
    Example(
        "black-white", "Black and white", "Color",
        "Remove all color.",
        "`hue=s=0` sets the saturation to zero. (`format=gray` would also work, but changes the pixel format.)",
        'ffmpeg -i in.mp4 -vf "hue=s=0" -c:a copy {stem}-bw.mp4',
    ),
    Example(
        "brightness-contrast", "Brightness, contrast, saturation", "Color",
        "Make the image a bit brighter, punchier and more colorful.",
        "`eq` adjusts brightness (-1..1, 0 = unchanged), contrast (1 = unchanged), saturation (1 = unchanged) and gamma.",
        'ffmpeg -i in.mp4 -vf "eq=brightness=0.05:contrast=1.15:saturation=1.3" -c:a copy {stem}-graded.mp4',
    ),
    Example(
        "rotate-90", "Rotate 90° clockwise", "Rotate & flip",
        "Turn a sideways phone video upright.",
        "`transpose` rotates by 90°: `dir=clock` is clockwise, `cclock` counter-clockwise. "
        "For a mirror image use `hflip` (horizontal) or `vflip` (vertical).",
        'ffmpeg -i in.mp4 -vf "transpose=dir=clock" -c:a copy {stem}-rotated.mp4',
    ),
    Example(
        "speed-2x", "Play twice as fast (with audio)", "Time",
        "Speed up video and audio together.",
        "Video speed is changed by rewriting timestamps: `setpts=PTS/2` halves each frame's presentation time. "
        "Audio uses `atempo=2`, which changes speed without changing pitch. "
        "Video and audio are separate streams, so they are two separate chains: `[0:v]...[v]` and `[0:a]...[a]`.",
        'ffmpeg -i in.mp4 -filter_complex "[0:v]setpts=PTS/2[v];[0:a]atempo=2[a]" -map "[v]" -map "[a]" {stem}-2x.mp4',
    ),
    Example(
        "timelapse", "Timelapse (10x, no audio)", "Time",
        "Compress long footage into a timelapse.",
        "`setpts=PTS/10` makes it 10x faster; `fps=30` then drops the extra frames so the file stays small. `-an` removes audio.",
        'ffmpeg -i in.mp4 -vf "setpts=PTS/10,fps=30" -an {stem}-timelapse.mp4',
    ),
    Example(
        "trim-fade", "Trim a clip and fade in", "Time",
        "Keep 10 seconds starting at 0:05, fading picture and sound in over the first second.",
        "The input options `-ss 5 -t 10` (on the input node) select the time range before decoding, which is fast. "
        "`fade=type=in:duration=1` fades the picture from black, `afade` does the same for audio.",
        'ffmpeg -ss 5 -t 10 -i in.mp4 -filter_complex "[0:v]fade=type=in:duration=1[v];[0:a]afade=type=in:duration=1[a]" '
        '-map "[v]" -map "[a]" {stem}-clip.mp4',
    ),
    Example(
        "gif", "High-quality GIF", "Formats",
        "Make a small looping GIF with good colors.",
        "GIFs only have 256 colors. `palettegen` computes the best palette for this clip and `paletteuse` applies it. "
        "Because the frames are needed twice (to compute the palette and to draw with it), `split` duplicates them. "
        "`paletteuse` has two input pads: the frames and the palette.",
        'ffmpeg -t 5 -i in.mp4 -filter_complex "[0:v]fps=12,scale=w=480:h=-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse[v]" '
        '-map "[v]" {stem}.gif',
    ),
    Example(
        "thumbnail", "Thumbnail image", "Formats",
        "Save one representative frame as a JPEG.",
        "`thumbnail` looks at batches of frames and picks the most representative one; `scale` resizes it. "
        "`-frames:v 1` stops after one frame.",
        'ffmpeg -i in.mp4 -vf "thumbnail,scale=w=640:h=-2" -frames:v 1 {stem}-thumb.jpg',
    ),
    Example(
        "two-outputs", "Full size and a small preview at once", "Multiple inputs & outputs",
        "Write two files in one pass: the original quality, and a small 480p preview.",
        "`split` duplicates the stream. Each output node maps its own pads: `big` gets the first copy plus the original audio, "
        "`small` gets the scaled copy. One ffmpeg run, one decode, two outputs.",
        'ffmpeg -i in.mp4 -filter_complex "[0:v]split=outputs=2[full][tmp];[tmp]scale=w=-2:h=480[small]" '
        '-map "[full]" -map 0:a? -c:v libx264 -crf 20 {stem}-full.mp4 -map "[small]" -map 0:a? -c:v libx264 -crf 28 {stem}-preview.mp4',
    ),
    Example(
        "side-by-side", "Two videos side by side", "Multiple inputs & outputs",
        "Put two videos next to each other, e.g. for a before/after comparison.",
        "Both inputs are scaled to the same height (hstack requires it), then `hstack` joins them. "
        "Its `inputs` option sets how many input pads it has. Audio comes from the left video.",
        'ffmpeg -i left.mp4 -i right.mp4 -filter_complex "[0:v]scale=w=-2:h=720[l];[1:v]scale=w=-2:h=720[r];[l][r]hstack=inputs=2:shortest=1[v]" '
        '-map "[v]" -map 0:a? {stem}-side-by-side.mp4',
    ),
    Example(
        "picture-in-picture", "Picture in picture", "Multiple inputs & outputs",
        "Show a second video small in the bottom-right corner of the first.",
        "The second input is scaled to a quarter of its width, then `overlay` draws it on the first. "
        "`overlay` has two input pads: `main` (background) and `overlay` (foreground). "
        "`W`/`H` are the main video's size and `w`/`h` the overlay's, so `x=W-w-20` is 20 px from the right edge.",
        'ffmpeg -i main.mp4 -i inset.mp4 -filter_complex "[1:v]scale=w=iw/4:h=-2[pip];[0:v][pip]overlay=x=W-w-20:y=H-h-20:shortest=1[v]" '
        '-map "[v]" -map 0:a? {stem}-pip.mp4',
    ),
    Example(
        "concat", "Join two clips", "Multiple inputs & outputs",
        "Play one clip after the other (both need the same size and frame rate).",
        "`concat` takes `n` segments, each with `v` video and `a` audio pads, in the order segment 1 video, segment 1 audio, "
        "segment 2 video, ... and has `v` + `a` output pads.",
        'ffmpeg -i first.mp4 -i second.mp4 -filter_complex "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]" -map "[v]" -map "[a]" {stem}-joined.mp4',
    ),
    Example(
        "caption", "Burn in a caption", "Text",
        "Write a line of text at the bottom of the picture.",
        "`drawtext` draws text with a system font (`font=Sans`). `x=(w-text_w)/2` centers it; `box=1` adds a background box "
        "whose color `black@0.5` is black at 50% opacity.",
        "ffmpeg -i in.mp4 -vf \"drawtext=text='Hello from the studio':font=Sans:fontsize=48:fontcolor=white:"
        "x=(w-text_w)/2:y=h-th-60:box=1:boxcolor=black@0.5:boxborderw=16\" -c:a copy {stem}-caption.mp4",
    ),
    Example(
        "loudness", "Normalize loudness", "Audio",
        "Make quiet or loud recordings play at a standard volume.",
        "`loudnorm` implements EBU R128: `I` is the target loudness (-16 LUFS suits online video), `TP` the true-peak ceiling. "
        "The video is copied untouched with `-c:v copy` (allowed because only audio is filtered).",
        'ffmpeg -i in.mp4 -af "loudnorm=I=-16:TP=-1.5:LRA=11" -c:v copy -c:a aac -b:a 192k {stem}-loud.mp4',
    ),
    Example(
        "extract-audio", "Extract the audio as MP3", "Audio",
        "Save just the soundtrack.",
        "No filters needed: the output node maps only the input's audio pad, and `-c:a libmp3lame` encodes MP3.",
        "ffmpeg -i in.mp4 -map 0:a -c:a libmp3lame -q:a 2 {stem}.mp3",
    ),
]
