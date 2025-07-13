import pathlib
import jinja2
import PIL

import sys
sys.path.append('../src')
import mediatools



def make_site(root: pathlib.Path, template_path: pathlib.Path, thumb_folder: str = '_thumbs', page_name: str = 'web3.html'):
    '''Make the site from the root directory and template.'''

    mdir = mediatools.MediaDir.from_path(root, use_absolute=True, ingore_folder_names=(thumb_folder,))

    print(f'reading template {template_path}')
    template_path = pathlib.Path(template_path)
    with template_path.open('r') as f:
        template_html = f.read()
    environment = jinja2.Environment()
    template = environment.from_string(template_html)

    make_pages(root, mdir, template, thumbs_path=root / thumb_folder, page_name=page_name)

def make_pages(root: pathlib.Path, mdir: mediatools.MediaDir, template: jinja2.Template, thumbs_path: pathlib.Path, page_name: str):
    '''Make pages for the media directory and its subdirectories.'''
    rel_path = mdir.fpath.relative_to(root)

    child_paths = list()
    for sdir in mdir.subdirs:
        if len(sdir.all_media_files()) > 0 or len(sdir.subdirs) > 0:
            child_paths.append(make_pages(root=root, mdir=sdir, template=template, thumbs_path=thumbs_path, page_name=page_name))

    clips = list()
    vids = list()
    best_thumb, best_aspect = None, None
    for vfile in mdir.videos:
        rp = vfile.fpath.relative_to(root)
        thumb_fp = thumbs_path / str(rp.with_suffix('.gif')).replace('/', '.')
        rel_thumb_fp = thumb_fp.relative_to(root)

        info = vfile.get_info()
        
        info_dict = {
            'vid_web': mediatools.parse_url(vfile.fpath.name),
            'vid_title': info.title(),
            'thumb_web': mediatools.parse_url('/'+str(rel_thumb_fp)),
            'vid_size': info.size,
            'vid_size_str': info.size_str(),
            'duration': info.probe.duration,
            'duration_str': info.duration_str(),
            'res_str': info.resolution_str(),
            'aspect': info.aspect_ratio(),
            'idx': info.id(),
        }
        if info.probe.duration < 60:
            clips.append(info_dict)
        else:
            vids.append(info_dict)

        # select a good thumb
        if best_aspect is None or info.aspect_ratio() > best_aspect:
            best_aspect = info.aspect_ratio()
            best_thumb =  mediatools.parse_url('/'+str(rel_thumb_fp))#str(rel_thumb_fp.with_suffix('.gif')).replace('/', '.')


    images = list()
    for ifile in mdir.images:
        rp = ifile.fpath.relative_to(root)
        try:
            info = ifile.get_info()
        except PIL.UnidentifiedImageError:
            print(f'Error: {ifile.fpath} is not a valid image file.')
            continue
        else:
            images.append({
                'path': mediatools.parse_url(rp.name),
                'title': info.title(),
                'aspect': info.aspect_ratio(),
            })
            if best_thumb is None or info.aspect_ratio() > best_aspect:
                best_aspect = info.aspect_ratio()
                best_thumb = f'/{mediatools.parse_url(str(rp))}'#ifile.fpath.with_suffix('.gif')


    
    #print(images)
    #for im in images:
    #    print('-->', im)
    #imgs = list(sorted(images, key=lambda i: -i['aspect']))

    html_str = template.render(
        vids = list(sorted(vids, key=lambda vi: (-vi['aspect'], -vi['duration']))),
        clips = list(sorted(clips, key=lambda vi: (-vi['aspect'], -vi['duration']))),
        imgs = list(sorted(images, key=lambda i: -i['aspect'])),
        child_paths = list(sorted(child_paths, key=lambda i: -i['subfolder_aspect'])), 
        page_name = page_name,
    )

    with (mdir.fpath / page_name).open('w') as f:
        f.write(html_str)
    print('wrote', mdir.fpath / page_name)
    #print(f'saved {pp} with {len(pinfo.img_infos)} images, {len(pinfo.vid_infos)} vids, and {len(pinfo.subpages)} subfolders')

    #thumb_fp = thumbs_path / str(rp.with_suffix('.gif')).replace('/', '.')
    #if best_thumb is not None:
    #    thumb_path = best_thumb.relative_to(root).with_suffix('.gif')
    #    thumb_fp = thumb_path / str().replace('/', '.')
    #else:
    #    thumb_fp = None
    
    return {
        'path': f'/{str(rel_path)}/{page_name}', 
        'path_rel': f'{str(rel_path)}/{page_name}', 
        'name': mediatools.fname_to_title(rel_path.name), 
        'subfolder_thumb': best_thumb if best_thumb is not None else '',
        'subfolder_aspect': best_aspect if best_aspect is not None else 1.0,
        'num_vids': len(vids),
        'num_imgs': len(images),
        'num_subfolders': len(child_paths),
        'files_size_str': mediatools.format_memory(sum([p.stat().st_size for p in mdir.all_files()])),
        'idx': mediatools.fname_to_id(mdir.fpath.name),
    }

if __name__ == '__main__':

    # Example usage
    root = pathlib.Path('/AddStorage/personal/dwhelper/')
    make_site(
        root=root,
        template_path='templates/gpt_multi_v2.2.html',
    )
    


