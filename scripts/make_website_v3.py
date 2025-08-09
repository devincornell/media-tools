import pathlib
import jinja2
import PIL
import dataclasses

import sys
sys.path.append('../src')
sys.path.append('src')
import mediatools



def make_site(root: pathlib.Path, template_path: pathlib.Path, thumb_folder: str = '_thumbs', page_name: str = 'web3.html'):
    '''Make the site from the root directory and template.'''
    pathlib.Path(thumb_folder).mkdir(exist_ok=True)
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

    best_subpage_thumb, best_local_thumb = BestThumbTracker(), BestThumbTracker()
    
    child_paths = list()
    for sdir in sorted(mdir.subdirs, key=lambda sd: sd.fpath):
        if len(sdir.all_media_files()) > 0 or len(sdir.subdirs) > 0:
            subpage_data = make_pages(root=root, mdir=sdir, template=template, thumbs_path=thumbs_path, page_name=page_name)
            child_paths.append(subpage_data)

            best_subpage_thumb.update(
                new_path=subpage_data['subfolder_thumb'],
                new_aspect=subpage_data['subfolder_aspect'],
            )

    clips = list()
    vids = list()
    for vfile in mdir.videos:
        rp = vfile.fpath.relative_to(root)
        thumb_fp = thumbs_path / str(rp.with_suffix('.gif')).replace('/', '.')
        rel_thumb_fp = thumb_fp.relative_to(root)

        try:
            info = vfile.get_info()
        except (mediatools.ffmpeg.ProbeError, mediatools.ffmpeg.FFMPEGExecutionError) as e:
            print(f'Error: {vfile.fpath} could not be probed. Skipping.')
            continue
        else:
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

            best_local_thumb.update(
                new_path=mediatools.parse_url('/'+str(rel_thumb_fp)),
                new_aspect=info.aspect_ratio(),
            )

            # select a good thumb
            #if best_aspect is None or info.aspect_ratio() > best_aspect:
            #    best_aspect = info.aspect_ratio()
            #    best_thumb =  mediatools.parse_url('/'+str(rel_thumb_fp))#str(rel_thumb_fp.with_suffix('.gif')).replace('/', '.')

            if not thumb_fp.is_file():
                try:
                    #mediatools.ffmpeg.make_thumb(vfile.fpath, thumb_fp, width=400)
                    import random
                    rnum = random.uniform(-0.2, 0.2)
                    mediatools.ffmpeg.make_animated_thumb(vfile.fpath, thumb_fp, framerate=2+rnum, sample_period=120, width=400)
                    #vfile.ffmpeg.make_thumb(str(thumb_fp), width=400)
                except mediatools.ffmpeg.FFMPEGExecutionError as e:
                    print(f'FFMPEG ERROR: \n{e.stderr}\n\n')
            

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
            #if best_thumb is None or info.aspect_ratio() > best_aspect:
            #    best_aspect = info.aspect_ratio()
            #    best_thumb = f'/{mediatools.parse_url(str(rp))}'#ifile.fpath.with_suffix('.gif')
            best_local_thumb.update(
                new_path=f'/{mediatools.parse_url(str(rp))}',
                new_aspect=info.aspect_ratio(),
            )


    html_str = template.render(
        vids = list(sorted(vids, key=lambda vi: (-vi['aspect'], -vi['duration']))),
        #vids = list(sorted(vids, key=lambda vi: vi['vid_title'])),
        clips = list(sorted(clips, key=lambda vi: (-vi['aspect'], -vi['duration']))),
        imgs = list(sorted(images, key=lambda i: -i['aspect'])),
        #child_paths = list(sorted(child_paths, key=lambda i: -i['subfolder_aspect'])), 
        child_paths = list(sorted(child_paths, key=lambda i: i['path_rel'])), 
        page_name = page_name,
    )

    with (mdir.fpath / page_name).open('w') as f:
        f.write(html_str)
    print('wrote', mdir.fpath / page_name)

    best_local_thumb.update_from_other(best_subpage_thumb)
    
    return {
        'path': f'/{str(rel_path)}/{page_name}', 
        'path_rel': f'{str(rel_path)}/{page_name}',
        'name': mediatools.fname_to_title(rel_path.name), 
        'subfolder_thumb': best_local_thumb.get_final_path(),
        'subfolder_aspect': best_local_thumb.get_final_aspect(),
        'num_vids': len(vids),
        'num_imgs': len(images),
        'num_subfolders': len(child_paths),
        'files_size_str': mediatools.format_memory(sum([p.stat().st_size for p in mdir.all_files()])),
        'idx': mediatools.fname_to_id(mdir.fpath.name),
    }

@dataclasses.dataclass
class BestThumbTracker:
    path: pathlib.Path|None = None
    aspect: float|None = None

    def update(self, new_path: pathlib.Path, new_aspect: float):
        '''Update the best thumb if the new one is better.'''
        if new_path is None or new_aspect is None:
            return
        if self.path is None or new_path == '' or new_aspect > self.aspect:
            self.path = pathlib.Path(new_path)
            self.aspect = new_aspect
    
    def update_from_other(self, other: 'BestThumbTracker'):
        '''Update from another BestThumbTracker.'''
        return self.update(new_path=other.path, new_aspect=other.aspect)
    
    def get_final_path(self) -> str:
        '''Get the path as a string.'''
        return str(self.path) if self.path is not None else ''

    def get_final_aspect(self) -> float:
        '''Get the aspect ratio.'''
        return self.aspect if self.aspect is not None else 1.0


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Generate a media website from a directory.')
    parser.add_argument('root', type=pathlib.Path, help='Root directory containing media files')
    args = parser.parse_args()

    make_site(
        #root=args.root,
        root=pathlib.Path(args.root).resolve(),
        template_path='templates/gpt_multi_v2.2.html',
        thumb_folder='_thumbs',
        page_name='web3.html',
    )
    


