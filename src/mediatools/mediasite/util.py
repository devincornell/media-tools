import urllib


def fname_to_title(fname: str, max_char: int = 150) -> str:
    replaced = fname.replace('_', ' ').replace('-', ' ')
    return ' '.join(replaced.strip().split()).title()[:max_char]

def fname_to_id(fname: str) -> str:
    return '-'.join(fname.strip().split())

def parse_url(urlstr: str) -> str:
    try:
        return urllib.parse.quote(urlstr)
    except TypeError as e:
        return ''

