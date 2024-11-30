from __future__ import annotations
import jinja2
import typing
import pathlib
import dataclasses
import pprint
import subprocess
import os
import tqdm
import ffmpeg
import sys
#import videotools
import html
import urllib.parse

import sys
sys.path.append('..')
import pydevin
#import pydevin.videotools
#import pydevin.mediasite

def make_pages(
        fpath: pathlib.Path, 
        config: pydevin.mediasite.SiteConfig, 
        make_thumbs: bool = True
    ) -> pydevin.mediasite.PageInfo:
    page_tree = pydevin.mediasite.PageInfo.from_fpath(fpath, config, verbose=True)
    return make_files_recursive(page_tree, config=config, make_thumbs=make_thumbs)

def make_files_recursive(
        pinfo: pydevin.mediasite.PageInfo, 
        config: pydevin.mediasite.SiteConfig, 
        make_thumbs: bool
    ):
    print(f'starting in {str(pinfo.folder_fpath)}')

    print(f'making thumbnails')
    if make_thumbs:
        #try:
        pinfo.make_thumbs(verbose=True)
        #except Exception as e:
        #    print(e)

    for sp in pinfo.subpages:
        make_files_recursive(sp, config, make_thumbs=make_thumbs)

    #sp_infos = list(sorted(pinfo.subpage_info_dicts(), key=lambda pi: pi['name']))
    #vid_infos = list(sorted(pinfo.vid_info_dicts(), key=lambda vi: vi['vid_title']))
    #vid_thumb_infos = list(sorted(pinfo.vid_info_dicts(), key=lambda vi: -vi['aspect']))
    #img_infos = list(sorted(pinfo.img_info_dicts(), key=lambda ii: ii['aspect']))

    #vids = [vi for vi in vid_infos if not vi['is_clip']]
    #vid_thumbs = [vi for vi in vid_thumb_infos if not vi['is_clip']]
    #clips = [vi for vi in vid_infos if vi['is_clip']]

    subpages = pinfo.get_subpages_dicts(
        sort_key=lambda sp: sp.title,
    )
    vid_thumbs = pinfo.get_vid_info_dicts(
        filter_cond=lambda vi: not vi.is_clip,
        sort_key=lambda vi: (-vi.aspect(), -vi.probe.duration),
    )
    clips = pinfo.get_vid_info_dicts(
        filter_cond=lambda vi: vi.is_clip,
        sort_key=lambda vi: (-vi.aspect(), -vi.probe.duration),
    )
    vids = pinfo.get_vid_info_dicts(
        filter_cond=lambda vi: not vi.is_clip,
        #sort_key=lambda vi: (-vi.aspect(), -vi.probe.duration),
        sort_key=lambda vi: vi.vid_title,
    )
    imgs = pinfo.get_img_info_dicts(
        sort_key=lambda vi: -vi.aspect(),
    )

    html_str = config.template.render(
        vid_thumbs = vid_thumbs,
        vids = vids, 
        clips = clips,
        imgs = imgs,
        child_paths = subpages, 
        video_width = config.video_width, 
        clip_width = config.clip_width,
        name = pinfo.folder_fpath_rel,
    )

    # write the template
    pp = pinfo.page_path()
    print(f'saving {pp} with {len(pinfo.img_infos)} images, {len(pinfo.vid_infos)} vids, and {len(pinfo.subpages)} subfolders')
    with pp.open('w') as f:
        f.write(html_str)


if __name__ == '__main__':

    base_path = pathlib.Path('/AddStorage/personal/dwhelper/')
    #base_path = pathlib.Path('/StorageDrive/raw_videos/gopro_videos')

    thumb_path = base_path.joinpath('_thumbs/')

    print('reading template')
    #template_path = pathlib.Path('templates/band1_template.html')
    template_path = pydevin.TEMPLATES['gpt_multi_v2.2']
    with template_path.open('r') as f:
        template_html = f.read()
    environment = jinja2.Environment()
    template = environment.from_string(template_html)


    config = pydevin.mediasite.SiteConfig(
        base_path = base_path,
        thumb_base_path = thumb_path,
        template = template,
        page_fname = 'web.html',
        vid_extensions = ('mp4', 'MOV', 'mov', 'MP4', 'flv', 'ts', 'webm'),
        img_extensions = ('png', 'gif', 'jpg', 'jpeg'),
        thumb_extension = '.gif',
        video_width = '85%',
        clip_width = '100%',
        ideal_aspect = 1.8,
        clip_duration = 60,
        do_clip_autoplay = False,
    )
    
    print(f'making pages')
    make_pages(
        fpath=base_path,#.joinpath('z_photos/'),
        config=config,
        make_thumbs=True,
    )


