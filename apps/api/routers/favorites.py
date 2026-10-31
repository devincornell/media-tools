from __future__ import annotations

from fastapi import APIRouter

from mediatools.contracts import ErrorResponse, FavoriteState, PathList

from ..dependencies import FavoritesDep

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


@router.get("")
async def list_favorites(favorites: FavoritesDep) -> PathList:
    '''Favorite file paths, most recently starred first.'''
    return PathList(paths=await favorites.list_all())


@router.put("/{file_path:path}", responses={404: {"model": ErrorResponse}})
async def add_favorite(file_path: str, favorites: FavoritesDep) -> FavoriteState:
    return await favorites.add(file_path)


@router.delete("/{file_path:path}")
async def remove_favorite(file_path: str, favorites: FavoritesDep) -> FavoriteState:
    return await favorites.remove(file_path)
