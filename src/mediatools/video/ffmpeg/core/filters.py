import typing

# TypeAlias is the standard way to create readable aliases (Python 3.10+)
# If you are on an older version, you can just do: LinkLabel = str
if hasattr(typing, 'TypeAlias'):
    LinkLabel: typing.TypeAlias = str
else:
    LinkLabel = str


def filtergraph(*complex_links: str) -> str:
    '''Combine multiple complex filter links into a complete filtergraph using semicolons.
    
    Example:
        link1 = filtergraph_link('scale', input='0:v', output='bg', w=1920, h=1080)
        link2 = filtergraph_link('gblur', input='bg', output='out', sigma=5)
        filtergraph(link1, link2) -> '[0:v]scale=w=1920:h=1080[bg];[bg]gblur=sigma=5[out]'
    '''
    valid_links = [str(link) for link in complex_links if link]
    return ';'.join(valid_links)

def filtergraph_link(
    filter_spec: str,
    *filter_args,
    input: LinkLabel | None = None,
    output: LinkLabel | None = None,
    inputs: typing.Sequence[LinkLabel] | None = None,
    outputs: typing.Sequence[LinkLabel] | None = None,
    **filter_kwargs,
) -> str:
    '''Build a filter link for FFMPEG command. Each call is one filter link, so it will be used in sequence.
    Example:
        filtergraph_link('scale', input='in', output='out', w=480, h=640) -> '[in]scale=w=480:h=640[out]'
    '''    
    in_labels = _parse_stream_labels(name='input', single_input=input, multi_inputs=inputs)
    out_labels = _parse_stream_labels(name='output', single_input=output, multi_inputs=outputs)
    
    # Notice we removed the extra colons that were in the docstring example
    return f'{in_labels}{filter_link(filter_spec, *filter_args, **filter_kwargs)}{out_labels}'
    

def _parse_stream_labels(
    name: str,
    single_input: LinkLabel | None = None,
    multi_inputs: typing.Sequence[LinkLabel] | None = None
) -> str:
    '''Parse stream labels for filtergraph links. Allows for zero labels (source/sink filters).'''
    if single_input is not None and multi_inputs is not None:
        raise ValueError(f'Cannot specify both {name} and multiple {name}s.')
    
    if single_input is not None:
        return f'[{single_input}]'
    
    if multi_inputs is not None:
        return ''.join(f'[{s}]' for s in multi_inputs)
        
    # If both are None, this might be a source or sink filter (e.g., generating a solid color)
    return ''

def filterchain(*links: str) -> str:
    '''Chain multiple simple filter links together sequentially using commas.
    Used when passing multiple filters to a single input stream.
    
    Example:
        step1 = filter_link('scale', w=480, h=640)
        step2 = filter_link('fps', fps=30)
        filter_chain(step1, step2) -> 'scale=w=480:h=640,fps=fps=30'
    '''
    # Filter out any empty strings or None values just to be safe
    valid_links = [str(link) for link in links if link]
    return ','.join(valid_links)

def filter_link(
    filter_spec: str,
    *filter_args,
    **filter_kwargs,
) -> str:
    '''Build a simple filter link for FFMPEG command. Each call is one filter link.
    Example:
        filter_link('scale', w=480, h=640) -> 'scale=w=480:h=640'
        filter_link('split') -> 'split'
    '''    
    all_args = [str(a) for a in filter_args]
    all_args.extend(f"{k}={v}" for k, v in filter_kwargs.items())
    
    if not all_args:
        # Prevent the trailing "=" if no arguments are passed
        return filter_spec
        
    args_str = ':'.join(all_args)
    return f'{filter_spec}={args_str}'