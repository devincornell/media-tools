from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from fastapi.responses import FileResponse

from mediatools.contracts import ErrorResponse, MediaJobPage
from mediatools.contracts.studio import (
    CompileRequest,
    CompileView,
    ExampleList,
    FilterCatalogView,
    GraphList,
    GraphSaveRequest,
    ImportRequest,
    ImportResult,
    IoOptionsView,
    MediaListing,
    SavedGraphView,
    StudioRunAccepted,
    StudioRunRequest,
)
from mediatools.jobs import JobStatus
from mediatools.video.ffmpeg.filtergraph import FilterGraphDoc, FilterSpec

from ..dependencies import StudioDep
from ..settings import TEMPLATES_DIR

router = APIRouter(tags=["studio"])
api = "/api/studio"

_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse}}
_SAVE_ERRORS: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}


@router.get("/studio", include_in_schema=False)
async def studio_page() -> FileResponse:
    return FileResponse(TEMPLATES_DIR / "studio.html", media_type="text/html")


@router.get(f"{api}/filters", responses={503: {"model": ErrorResponse}})
async def list_filters(studio: StudioDep) -> FilterCatalogView:
    '''Every filter of the server's ffmpeg build.'''
    return await studio.filters()


@router.get(f"{api}/filters/{{name}}", responses=_NOT_FOUND)
async def filter_spec(name: str, studio: StudioDep) -> FilterSpec:
    '''Pads and options of one filter, as reported by `ffmpeg -h filter=NAME`.'''
    return await studio.filter_spec(name)


@router.get(f"{api}/io-options")
async def io_options(studio: StudioDep) -> IoOptionsView:
    '''Options input and output nodes may set.'''
    return studio.io_options()


@router.get(f"{api}/examples")
async def examples(studio: StudioDep) -> ExampleList:
    return await studio.examples()


@router.post(f"{api}/compile")
async def compile_graph(request: CompileRequest, studio: StudioDep) -> CompileView:
    '''Check a graph and show the filtergraph and command it produces. Problems are returned, not raised.'''
    return await studio.compile(request.graph, request.params)


@router.post(f"{api}/import")
async def import_text(request: ImportRequest, studio: StudioDep) -> ImportResult:
    '''Turn an ffmpeg command line or filtergraph text into a graph.'''
    return await studio.import_text(request.text)


@router.get(f"{api}/graphs")
async def list_graphs(studio: StudioDep) -> GraphList:
    return await studio.list_graphs()


@router.post(f"{api}/graphs", status_code=201, responses=_SAVE_ERRORS)
async def create_graph(request: GraphSaveRequest, studio: StudioDep) -> SavedGraphView:
    return await studio.create_graph(request)


@router.get(f"{api}/graphs/{{graph_id}}", responses=_NOT_FOUND)
async def get_graph(graph_id: str, studio: StudioDep) -> SavedGraphView:
    return await studio.get_graph(graph_id)


@router.put(f"{api}/graphs/{{graph_id}}", responses=_SAVE_ERRORS)
async def update_graph(graph_id: str, request: GraphSaveRequest, studio: StudioDep) -> SavedGraphView:
    '''Replace a saved graph; pass the `revision` you loaded to avoid overwriting someone else's change.'''
    return await studio.update_graph(graph_id, request)


@router.delete(f"{api}/graphs/{{graph_id}}", status_code=204, responses=_SAVE_ERRORS)
async def delete_graph(graph_id: str, studio: StudioDep) -> Response:
    '''Delete a saved graph (refused while other saved graphs embed it).'''
    await studio.delete_graph(graph_id)
    return Response(status_code=204)


@router.post(f"{api}/run", status_code=202, responses={422: {"model": ErrorResponse}})
async def run_graph(request: StudioRunRequest, studio: StudioDep) -> StudioRunAccepted:
    '''Queue one render job per item.'''
    return await studio.run(request)


@router.get(f"{api}/jobs")
async def list_jobs(
    studio: StudioDep,
    status: JobStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MediaJobPage:
    '''Studio render jobs only. Cancel and logs use the generic `/v1/jobs/{id}` endpoints.'''
    return await studio.list_jobs(status=status, limit=limit, offset=offset)


@router.get(f"{api}/jobs/{{job_id}}/graph", responses=_NOT_FOUND)
async def job_graph(job_id: str, studio: StudioDep) -> FilterGraphDoc:
    '''The graph a render job ran, to reopen it in the editor.'''
    return await studio.job_graph(job_id)


@router.get(f"{api}/media", responses={404: {"model": ErrorResponse}})
async def media(studio: StudioDep, path: str = ".") -> MediaListing:
    '''Folders and media files in a gallery folder, for choosing inputs.'''
    return await studio.media(path)
