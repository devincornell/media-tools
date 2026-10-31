from __future__ import annotations

from fastapi import APIRouter

from mediatools.contracts import ErrorResponse, FavoriteState, FolderFavoriteState, PathList

from ..dependencies import FavoritesDep, FolderFavoritesDep

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


@router.get("/folders")
async def list_favorite_folders(folders: FolderFavoritesDep) -> PathList:
    '''Favorite folder paths relative to the gallery root, most recently starred first.'''
    return PathList(paths=await folders.list_all())


@router.put("/folders/{folder_path:path}", responses={404: {"model": ErrorResponse}})
async def add_favorite_folder(folder_path: str, folders: FolderFavoritesDep) -> FolderFavoriteState:
    return await folders.add(folder_path)


@router.delete("/folders/{folder_path:path}")
async def remove_favorite_folder(folder_path: str, folders: FolderFavoritesDep) -> FolderFavoriteState:
    return await folders.remove(folder_path)


@router.get("")
async def list_favorites(favorites: FavoritesDep) -> PathList:
    '''Favorite video hashes, most recently starred first.'''
    return PathList(paths=await favorites.list_all())


@router.put("/{file_hash}", responses={404: {"model": ErrorResponse}})
async def add_favorite(file_hash: str, favorites: FavoritesDep) -> FavoriteState:
    return await favorites.add(file_hash)


@router.delete("/{file_hash}")
async def remove_favorite(file_hash: str, favorites: FavoritesDep) -> FavoriteState:
    return await favorites.remove(file_hash)
