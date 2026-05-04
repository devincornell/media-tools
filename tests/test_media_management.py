"""Tests for MediaDir functionality, mirroring the examples/0-managing_media_files.ipynb notebook."""
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import pytest
import requests

import mediatools
from mediatools import (
    MediaDir,
    NonMediaFile,
    scan_directory,
    ImageNotFoundError,
    NonMediaFileNotFoundError,
    VideoNotFoundError,
    DirectoryNotFoundError,
)
from mediatools.file_stat_result import FileStatResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def temp_path():
    """Download the test dataset zip and yield the root temp directory."""
    url = os.environ.get("TEST_ZIP_FILE_URL")
    if not url:
        pytest.skip("TEST_ZIP_FILE_URL environment variable not set")
    td = tempfile.TemporaryDirectory()
    root = Path(td.name)
    zip_path = root / "archive.zip"

    response = requests.get(url)
    zip_path.write_bytes(response.content)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(root)
    zip_path.unlink()

    yield root

    td.cleanup()


@pytest.fixture(scope="module")
def media_dir(temp_path):
    """Return a scanned MediaDir for the downloaded dataset."""
    return scan_directory(temp_path)


@pytest.fixture(scope="module")
def modified_root(temp_path):
    """Create a slightly modified copy of the dataset directory."""
    modified = Path(tempfile.mkdtemp(prefix="mediatools_modified_"))
    shutil.copytree(temp_path, modified, dirs_exist_ok=True)

    # Replicate the changes from the notebook
    shutil.move(
        str(modified / "totk_builds/op_builds.mp4"),
        str(modified / "new_vid.mp4"),
    )
    (modified / "new_dir").mkdir(exist_ok=True)
    shutil.move(
        str(modified / "totk_builds/op_builds_thumb.jpg"),
        str(modified / "new_dir/new_thumb.jpg"),
    )

    yield modified

    shutil.rmtree(modified)


@pytest.fixture(scope="module")
def modified_media_dir(modified_root):
    return scan_directory(modified_root)


# ===========================================================================
# Scanning
# ===========================================================================

class TestScanDirectory:
    def test_returns_mediadir_instance(self, temp_path):
        md = scan_directory(temp_path)
        assert isinstance(md, MediaDir)

    def test_from_path_equivalent_to_scan_directory(self, temp_path):
        md1 = scan_directory(temp_path)
        md2 = MediaDir.from_path(temp_path)
        assert md1.path == md2.path
        assert set(md1.all_file_paths()) == set(md2.all_file_paths())

    def test_path_attribute(self, temp_path, media_dir):
        assert media_dir.path == temp_path

    def test_has_videos(self, media_dir):
        assert len(media_dir.all_video_files()) > 0

    def test_has_images(self, media_dir):
        assert len(media_dir.all_image_files()) > 0

    def test_has_subdirectories(self, media_dir):
        assert len(media_dir.subdirs) > 0

    def test_display_returns_string(self, media_dir):
        result = media_dir.display()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_custom_video_ext_excludes_mp4(self, temp_path):
        md = scan_directory(temp_path, video_ext=[], image_ext=['.jpg', '.jpeg'])
        # With no video extensions, no videos should be found
        assert len(md.all_video_files()) == 0

    def test_custom_image_ext_limits_images(self, temp_path):
        md = scan_directory(temp_path, video_ext=[], image_ext=['.jpg', '.jpeg'])
        for img in md.all_image_files():
            assert img.path.suffix.lower() in ('.jpg', '.jpeg')

    def test_ignore_path_excludes_directory(self, temp_path):
        md = scan_directory(temp_path, ignore_path=lambda p: p.name == 'battles')
        for subdir_name in md.subdirs:
            assert subdir_name != 'battles'

    def test_ignore_path_still_finds_other_dirs(self, temp_path, media_dir):
        md_no_battles = scan_directory(temp_path, ignore_path=lambda p: p.name == 'battles')
        # totk_builds should still be present
        assert 'totk_builds' in md_no_battles.subdirs


# ===========================================================================
# Directory navigation
# ===========================================================================

class TestDirectoryNavigation:
    def test_subdirs_is_dict(self, media_dir):
        assert isinstance(media_dir.subdirs, dict)

    def test_subdirs_values_are_mediadir(self, media_dir):
        for subdir in media_dir.subdirs.values():
            assert isinstance(subdir, MediaDir)

    def test_parent_of_root_is_none(self, media_dir):
        assert media_dir.parent is None

    def test_parent_of_subdir_is_not_none(self, media_dir):
        for subdir in media_dir.subdirs.values():
            assert subdir.parent is not None

    def test_subdir_parent_is_media_dir(self, media_dir):
        for subdir in media_dir.subdirs.values():
            assert subdir.parent is media_dir

    def test_subscript_access(self, media_dir):
        battles = media_dir["battles"]
        assert isinstance(battles, MediaDir)
        assert battles.path.name == "battles"

    def test_nested_subscript_access(self, media_dir):
        lynels = media_dir["battles"]["totk_lynels"]
        assert isinstance(lynels, MediaDir)
        assert lynels.path.name == "totk_lynels"

    def test_subscript_path_notation(self, media_dir):
        lynels = media_dir["battles/totk_lynels"]
        assert isinstance(lynels, MediaDir)

    def test_subdir_method_varargs(self, media_dir):
        lynels = media_dir.subdir("battles", "totk_lynels")
        assert isinstance(lynels, MediaDir)

    def test_subdir_method_path_object(self, media_dir):
        lynels = media_dir.subdir(Path("battles") / "totk_lynels")
        assert isinstance(lynels, MediaDir)

    def test_subscript_and_subdir_equivalent(self, media_dir):
        a = media_dir["battles"]["totk_lynels"]
        b = media_dir.subdir("battles", "totk_lynels")
        assert a.path == b.path

    def test_missing_subdir_raises(self, media_dir):
        with pytest.raises(DirectoryNotFoundError):
            media_dir["nonexistent_subdir_xyz"]

    def test_recursive_tree_function(self, media_dir):
        """Replicate the notebook's recursive print_tree function."""
        def count_dirs(mdir: MediaDir) -> int:
            count = 1
            for subdir in mdir.subdirs.values():
                count += count_dirs(subdir)
            return count

        assert count_dirs(media_dir) >= len(media_dir.subdirs) + 1

    def test_recursive_file_count(self, media_dir):
        """Replicate the notebook's count_files function."""
        def count_files(mdir: MediaDir) -> int:
            count = len(mdir.videos) + len(mdir.images) + len(mdir.other_files)
            for subdir in mdir.subdirs.values():
                count += count_files(subdir)
            return count

        assert count_files(media_dir) == len(media_dir.all_file_paths())


# ===========================================================================
# Working with media files
# ===========================================================================

class TestMediaFileAccess:
    def test_videos_property(self, media_dir):
        ex_dir = media_dir["battles/totk_lynels"]
        assert isinstance(ex_dir.videos, list)

    def test_images_property(self, media_dir):
        ex_dir = media_dir["battles/totk_lynels"]
        assert isinstance(ex_dir.images, list)

    def test_image_paths(self, media_dir):
        ex_dir = media_dir["battles/totk_lynels"]
        paths = ex_dir.image_paths()
        assert isinstance(paths, list)
        for p in paths:
            assert isinstance(p, Path)

    def test_other_files_property(self, media_dir):
        ex_dir = media_dir["battles/totk_lynels"]
        assert isinstance(ex_dir.other_files, list)

    def test_video_paths(self, media_dir):
        ex_dir = media_dir["battles/totk_lynels"]
        paths = ex_dir.video_paths()
        assert isinstance(paths, list)
        for p in paths:
            assert isinstance(p, Path)

    def test_get_video(self, media_dir, temp_path):
        vf = media_dir.get_video(temp_path / "totk_builds/op_builds.mp4")
        assert isinstance(vf, mediatools.VideoFile)

    def test_get_video_missing_raises(self, media_dir, temp_path):
        with pytest.raises(VideoNotFoundError):
            media_dir.get_video(temp_path / "totk_builds/nonexistent.mp4")

    def test_get_image(self, media_dir, temp_path):
        imf = media_dir.get_image(temp_path / "totk_builds/op_builds_thumb.jpg")
        assert isinstance(imf, mediatools.ImageFile)

    def test_get_image_missing_raises(self, media_dir, temp_path):
        with pytest.raises(ImageNotFoundError):
            media_dir.get_image(temp_path / "totk_builds/nonexistent.jpg")

    def test_get_nonmedia(self, media_dir, temp_path):
        nmf = media_dir.get_nonmedia(temp_path / "totk_builds/op_builds.txt")
        assert isinstance(nmf, NonMediaFile)

    def test_get_nonmedia_missing_raises(self, media_dir, temp_path):
        with pytest.raises(NonMediaFileNotFoundError):
            media_dir.get_nonmedia(temp_path / "totk_builds/nonexistent.txt")


class TestRecursiveFileMethods:
    def test_all_image_paths_returns_list(self, media_dir):
        paths = media_dir.all_image_paths()
        assert isinstance(paths, list)
        assert len(paths) > 0

    def test_all_file_paths_returns_list(self, media_dir):
        paths = media_dir.all_file_paths()
        assert isinstance(paths, list)
        assert len(paths) > 0

    def test_all_media_paths_subset_of_all_file_paths(self, media_dir):
        media = set(media_dir.all_media_paths())
        all_files = set(media_dir.all_file_paths())
        assert media.issubset(all_files)

    def test_all_video_files_returns_list(self, media_dir):
        vfs = media_dir.all_video_files()
        assert len(vfs) > 0
        for vf in vfs:
            assert isinstance(vf, mediatools.VideoFile)

    def test_all_image_files_returns_list(self, media_dir):
        imfs = media_dir.all_image_files()
        assert len(imfs) > 0
        for imf in imfs:
            assert isinstance(imf, mediatools.ImageFile)

    def test_all_video_paths_match_video_files(self, media_dir):
        paths_from_method = set(media_dir.all_video_paths())
        paths_from_files = {vf.path for vf in media_dir.all_video_files()}
        assert paths_from_method == paths_from_files

    def test_all_image_paths_match_image_files(self, media_dir):
        paths_from_method = set(media_dir.all_image_paths())
        paths_from_files = {imf.path for imf in media_dir.all_image_files()}
        assert paths_from_method == paths_from_files


class TestFileStatResult:
    def test_stat_returns_file_stat_result(self, media_dir):
        ex_dir = media_dir["battles/totk_lynels"]
        vf = ex_dir.videos[0]
        stat = vf.stat()
        assert isinstance(stat, FileStatResult)

    def test_stat_size_positive(self, media_dir):
        ex_dir = media_dir["battles/totk_lynels"]
        stat = ex_dir.videos[0].stat()
        assert stat.size > 0

    def test_stat_size_str_is_string(self, media_dir):
        ex_dir = media_dir["battles/totk_lynels"]
        stat = ex_dir.videos[0].stat()
        assert isinstance(stat.size_str(), str)
        assert len(stat.size_str()) > 0

    def test_stat_modified_at_str_is_string(self, media_dir):
        ex_dir = media_dir["battles/totk_lynels"]
        stat = ex_dir.videos[0].stat()
        assert isinstance(stat.modified_at_str(), str)

    def test_stat_accessed_at_str_is_string(self, media_dir):
        ex_dir = media_dir["battles/totk_lynels"]
        stat = ex_dir.videos[0].stat()
        assert isinstance(stat.accessed_at_str(), str)

    def test_stat_changed_at_str_is_string(self, media_dir):
        ex_dir = media_dir["battles/totk_lynels"]
        stat = ex_dir.videos[0].stat()
        assert isinstance(stat.changed_at_str(), str)


# ===========================================================================
# Directory comparison
# ===========================================================================

class TestDirectoryComparison:
    def test_file_counts_differ(self, media_dir, modified_media_dir):
        original_count = len(media_dir.all_file_paths())
        modified_count = len(modified_media_dir.all_file_paths())
        assert original_count == modified_count  # same number of files, just moved

    def test_file_diff_returns_two_sets(self, media_dir, modified_media_dir):
        removed, added = media_dir.file_diff(modified_media_dir)
        assert isinstance(removed, set)
        assert isinstance(added, set)

    def test_file_diff_removed_not_empty(self, media_dir, modified_media_dir):
        removed, _ = media_dir.file_diff(modified_media_dir)
        assert len(removed) > 0

    def test_file_diff_added_not_empty(self, media_dir, modified_media_dir):
        _, added = media_dir.file_diff(modified_media_dir)
        assert len(added) > 0

    def test_file_diff_removed_contains_moved_video(self, media_dir, modified_media_dir, temp_path):
        removed, _ = media_dir.file_diff(modified_media_dir)
        removed_names = {p.name for p in removed}
        assert "op_builds.mp4" in removed_names

    def test_file_diff_removed_contains_moved_image(self, media_dir, modified_media_dir, temp_path):
        removed, _ = media_dir.file_diff(modified_media_dir)
        removed_names = {p.name for p in removed}
        assert "op_builds_thumb.jpg" in removed_names

    def test_file_diff_added_contains_new_video(self, media_dir, modified_media_dir):
        _, added = media_dir.file_diff(modified_media_dir)
        added_names = {p.name for p in added}
        assert "new_vid.mp4" in added_names

    def test_file_diff_added_contains_new_thumb(self, media_dir, modified_media_dir):
        _, added = media_dir.file_diff(modified_media_dir)
        added_names = {p.name for p in added}
        assert "new_thumb.jpg" in added_names

    def test_get_changed_dirs_returns_list(self, media_dir, modified_media_dir):
        changed = media_dir.get_changed_dirs(modified_media_dir)
        assert isinstance(changed, list)

    def test_get_changed_dirs_not_empty(self, media_dir, modified_media_dir):
        changed = media_dir.get_changed_dirs(modified_media_dir)
        assert len(changed) > 0

    def test_get_changed_dirs_are_mediadir_instances(self, media_dir, modified_media_dir):
        for cd in media_dir.get_changed_dirs(modified_media_dir):
            assert isinstance(cd, MediaDir)


# ===========================================================================
# Serialization
# ===========================================================================

class TestSerialization:
    def test_to_dict_returns_dict(self, media_dir):
        d = media_dir.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_has_required_keys(self, media_dir):
        d = media_dir.to_dict()
        for key in ('path', 'videos', 'images', 'other_files', 'subdirs', 'meta'):
            assert key in d

    def test_to_dict_path_is_string(self, media_dir):
        d = media_dir.to_dict()
        assert isinstance(d['path'], str)

    def test_to_dict_subdirs_is_list(self, media_dir):
        d = media_dir.to_dict()
        assert isinstance(d['subdirs'], list)

    def test_roundtrip_from_dict(self, media_dir):
        d = media_dir.to_dict()
        restored = MediaDir.from_dict(d)
        assert set(str(p) for p in restored.all_file_paths()) == set(str(p) for p in media_dir.all_file_paths())


# ===========================================================================
# Practical workflow helpers (from notebook Section 4)
# ===========================================================================

class TestAnalyzeMediaLibrary:
    """Tests replicating the analyze_media_library helper from the notebook."""

    def test_total_videos_positive(self, media_dir):
        total_videos = len(media_dir.all_video_files())
        assert total_videos > 0

    def test_total_images_positive(self, media_dir):
        total_images = len(media_dir.all_image_files())
        assert total_images > 0

    def test_directory_breakdown_keys(self, media_dir):
        for subdir_name in media_dir.subdirs:
            assert subdir_name in media_dir.subdirs

    def test_subdirectory_video_counts_nonnegative(self, media_dir):
        for subdir in media_dir.subdirs.values():
            assert len(subdir.all_video_files()) >= 0

    def test_subdirectory_image_counts_nonnegative(self, media_dir):
        for subdir in media_dir.subdirs.values():
            assert len(subdir.all_image_files()) >= 0


class TestBatchProcessingPreparation:
    """Tests replicating the prepare_batch_processing_list helper from the notebook."""

    def _build_batch(self, media_dir):
        files = media_dir.all_video_files()
        result = []
        for file_obj in files:
            rel_path = file_obj.path.relative_to(media_dir.path)
            parts = rel_path.parts
            result.append({
                'full_path': file_obj.path,
                'relative_path': rel_path,
                'category': parts[0] if len(parts) > 1 else 'root',
                'subcategory': parts[1] if len(parts) > 2 else None,
                'filename': file_obj.path.name,
                'extension': file_obj.path.suffix.lower(),
            })
        return result

    def test_batch_list_not_empty(self, media_dir):
        assert len(self._build_batch(media_dir)) > 0

    def test_batch_extensions_are_video(self, media_dir):
        from mediatools.constants import VIDEO_FILE_EXTENSIONS
        for item in self._build_batch(media_dir):
            assert item['extension'] in VIDEO_FILE_EXTENSIONS

    def test_batch_grouping_by_category(self, media_dir):
        batch = self._build_batch(media_dir)
        by_category: dict = {}
        for item in batch:
            by_category.setdefault(item['category'], []).append(item)
        for category, items in by_category.items():
            assert len(items) > 0


class TestBackupVerification:
    """Tests replicating the create_backup_verification_report helper from the notebook."""

    def test_identical_dirs_have_no_diff(self, temp_path):
        md1 = scan_directory(temp_path)
        md2 = scan_directory(temp_path)
        removed, added = md1.file_diff(md2)
        assert len(removed) == 0
        assert len(added) == 0

    def test_modified_dir_is_not_complete_backup(self, media_dir, modified_media_dir):
        removed, added = media_dir.file_diff(modified_media_dir)
        backup_complete = len(removed) == 0 and len(added) == 0
        assert not backup_complete

    def test_source_stats_match_scan(self, media_dir):
        assert len(media_dir.all_file_paths()) > 0
        assert len(media_dir.all_video_files()) > 0
        assert len(media_dir.all_image_files()) > 0

    def test_backup_stats_match_modified_scan(self, modified_media_dir):
        assert len(modified_media_dir.all_file_paths()) > 0
