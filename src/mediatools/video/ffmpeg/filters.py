import typing


LinkLabel = typing.TypeVar('LinkLabel', bound=str)


def filtergraph_link(
    filter_name: str,
    *filter_args,
    input: LinkLabel|None = None,
    output: LinkLabel|None = None,
    inputs: typing.Sequence[LinkLabel]|None = None,
    outputs: typing.Sequence[LinkLabel]|None = None,
    **filter_kwargs,
) -> str:
    '''Build a filter link for FFMPEG command. Each call is one filter link, so it will be used in sequence.
    Example:
        filtergraph_link('scale', input='in', output='out', w=480, h=640) -> '[in]:scale=w=480:h=640[out]'
    '''    
    in_labels = _parse_stream_labels(name='input', single_input=input, multi_inputs=inputs)
    out_labels = _parse_stream_labels(name='output', single_input=output, multi_inputs=outputs)
    return f'{in_labels}{filter_link(filter_name, *filter_args, **filter_kwargs)}{out_labels}'
    

def _parse_stream_labels(
    name: str,
    single_input: LinkLabel|None = None,
    multi_inputs: typing.Sequence[LinkLabel]|None = None
) -> str:
    '''Parse stream labels for filtergraph links.'''
    if single_input is not None:
        if multi_inputs is not None:
            raise ValueError(f'Cannot specify both {name} and multiple {name}s.')
        return f'[{single_input}]'
    else:
        if multi_inputs is None:
            return ''
        else:
            return ''.join(f'[{s}]' for s in multi_inputs)


def filter_link(
    filter_name: str,
    *filter_args,
    **filter_kwargs,
) -> str:
    '''Build a simple filter link for FFMPEG command. Each call is one filter link, so it will be used in sequence.
    Example:
        filter_link('scale', w=480, h=640) -> ':scale=w=480:h=640'
    '''    
    all_args = [str(a) for a in filter_args]
    all_args.extend(f"{k}={v}" for k, v in filter_kwargs.items())
    
    if len(all_args):
        return f':{filter_name}={":".join(all_args)}'
    else:
    
    return f':{filter_name}'


