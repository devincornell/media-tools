REINDEX = "media.reindex.v1"
THUMBNAILS = "media.thumbnails.v1"
CLEANUP = "media.cleanup.v1"
CONVERT_MP4 = "media.convert_mp4.v1"
MOVE = "media.move_rescan.v1"

KIND_BY_TYPE = {
    REINDEX: "reindex",
    THUMBNAILS: "thumbnails",
    CLEANUP: "cleanup",
    CONVERT_MP4: "convert_mp4",
    MOVE: "move",
}
TYPE_BY_KIND = {kind: job_type for job_type, kind in KIND_BY_TYPE.items()}
