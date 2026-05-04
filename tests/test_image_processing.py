"""Tests for image processing functionality, mirroring the examples/1-image_processing.ipynb notebook."""
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest
import requests

import mediatools
from mediatools import ImageFile, ImageFiles, scan_directory
from mediatools.images import Image, ImageMeta
from mediatools.file_stat_result import FileStatResult


# ---------------------------------------------------------------------------
# Sample image URL (same as used in the notebook)
# ---------------------------------------------------------------------------

SAMPLE_IMAGE_URL = (
    "https://storage.googleapis.com/public_data_09324832787/"
    "blogpost_filecol_select_payload_time.png"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def temp_dir():
    """Create a temp directory with the same structure as the notebook helper."""
    td = tempfile.TemporaryDirectory(prefix="mediatools_images_")
    root = Path(td.name)
    (root / "nature").mkdir()
    (root / "processed").mkdir()
    (root / "comparisons").mkdir()

    raw = requests.get(SAMPLE_IMAGE_URL)
    raw.raise_for_status()
    data = raw.content

    (root / "sample_chart.png").write_bytes(data)
    (root / "nature" / "landscape.png").write_bytes(data)
    (root / "nature" / "mountains.png").write_bytes(data)

    yield root

    td.cleanup()


@pytest.fixture(scope="module")
def image_file(temp_dir):
    return mediatools.ImageFile.from_path(temp_dir / "sample_chart.png")


@pytest.fixture(scope="module")
def image_collection(temp_dir):
    return mediatools.ImageFiles.from_rglob(temp_dir)


@pytest.fixture(scope="module")
def loaded_image(image_file):
    return image_file.read()


# ===========================================================================
# ImageFile
# ===========================================================================

class TestImageFile:
    def test_from_path_returns_imagefile(self, temp_dir):
        imf = mediatools.ImageFile.from_path(temp_dir / "sample_chart.png")
        assert isinstance(imf, mediatools.ImageFile)

    def test_path_attribute(self, image_file, temp_dir):
        assert image_file.path == temp_dir / "sample_chart.png"

    def test_stat_returns_file_stat_result(self, image_file):
        stat = image_file.stat()
        assert isinstance(stat, FileStatResult)

    def test_stat_size_positive(self, image_file):
        assert image_file.stat().size > 0

    def test_read_meta_returns_image_meta(self, image_file):
        meta = image_file.read_meta()
        assert isinstance(meta, ImageMeta)

    def test_read_meta_has_resolution(self, image_file):
        meta = image_file.read_meta()
        width, height = meta.res
        assert width > 0
        assert height > 0

    def test_read_meta_has_stat(self, image_file):
        meta = image_file.read_meta()
        assert isinstance(meta.stat, FileStatResult)

    def test_missing_file_raises(self, temp_dir):
        with pytest.raises(FileNotFoundError):
            mediatools.ImageFile.from_path(temp_dir / "nonexistent.png")


# ===========================================================================
# ImageFiles collection
# ===========================================================================

class TestImageFiles:
    def test_from_rglob_returns_image_files(self, temp_dir):
        collection = mediatools.ImageFiles.from_rglob(temp_dir)
        assert isinstance(collection, mediatools.ImageFiles)

    def test_from_rglob_finds_all_images(self, image_collection):
        # notebook creates 3 images (root + 2 in nature/)
        assert len(image_collection) == 3

    def test_from_glob_finds_only_direct_children(self, temp_dir):
        nature_images = mediatools.ImageFiles.from_glob(temp_dir / "nature")
        assert len(nature_images) == 2
        names = [img.path.name for img in nature_images]
        assert "landscape.png" in names
        assert "mountains.png" in names

    def test_scan_directory_all_image_files(self, temp_dir):
        image_files = scan_directory(temp_dir).all_image_files()
        assert len(image_files) == 3
        for imf in image_files:
            assert isinstance(imf, mediatools.ImageFile)

    def test_all_items_are_image_file_instances(self, image_collection):
        for imf in image_collection:
            assert isinstance(imf, mediatools.ImageFile)


# ===========================================================================
# Image (in-memory)
# ===========================================================================

class TestImageRead:
    def test_read_returns_image_instance(self, image_file):
        img = image_file.read()
        assert isinstance(img, Image)

    def test_image_has_numpy_array(self, loaded_image):
        assert isinstance(loaded_image.im, np.ndarray)

    def test_image_shape_has_at_least_two_dims(self, loaded_image):
        assert len(loaded_image.shape) >= 2

    def test_image_size_property(self, loaded_image):
        h, w = loaded_image.size
        assert h > 0 and w > 0

    def test_image_write_creates_file(self, loaded_image, temp_dir):
        out = temp_dir / "processed" / "sample_chart_copy.png"
        loaded_image.write(out)
        assert out.exists()
        assert out.stat().st_size > 0


class TestImageDtypeConversions:
    def test_as_float_dtype(self, loaded_image):
        float_img = loaded_image.as_float()
        assert np.issubdtype(float_img.im.dtype, np.floating)

    def test_as_ubyte_dtype(self, loaded_image):
        ubyte_img = loaded_image.as_ubyte()
        assert ubyte_img.im.dtype == np.uint8

    def test_to_rgb_has_three_channels(self, loaded_image):
        rgb = loaded_image.to_rgb()
        assert rgb.shape[2] == 3

    def test_to_rgb_same_spatial_dims(self, loaded_image):
        rgb = loaded_image.to_rgb()
        assert rgb.shape[0] == loaded_image.shape[0]
        assert rgb.shape[1] == loaded_image.shape[1]

    def test_as_float_returns_new_image(self, loaded_image):
        float_img = loaded_image.as_float()
        assert float_img is not loaded_image

    def test_as_ubyte_returns_new_image(self, loaded_image):
        ubyte_img = loaded_image.as_ubyte()
        assert ubyte_img is not loaded_image


class TestImageArrayOperations:
    def test_getitem_slice_returns_image(self, loaded_image):
        h, w = loaded_image.shape[:2]
        crop_size = min(h, w) // 3
        start_h = (h - crop_size) // 2
        start_w = (w - crop_size) // 2
        cropped = loaded_image[start_h:start_h + crop_size, start_w:start_w + crop_size]
        assert isinstance(cropped, Image)

    def test_getitem_crop_correct_shape(self, loaded_image):
        h, w = loaded_image.shape[:2]
        crop_size = min(h, w) // 3
        start_h = (h - crop_size) // 2
        start_w = (w - crop_size) // 2
        cropped = loaded_image[start_h:start_h + crop_size, start_w:start_w + crop_size]
        assert cropped.shape[0] == crop_size
        assert cropped.shape[1] == crop_size

    def test_getitem_smaller_than_original(self, loaded_image):
        h, w = loaded_image.shape[:2]
        crop_size = min(h, w) // 3
        start_h = (h - crop_size) // 2
        start_w = (w - crop_size) // 2
        cropped = loaded_image[start_h:start_h + crop_size, start_w:start_w + crop_size]
        assert cropped.shape[0] < h
        assert cropped.shape[1] < w


# ===========================================================================
# TransformCalculator
# ===========================================================================

class TestTransformCalculator:
    def test_resize_explicit_dims(self, loaded_image):
        resized = loaded_image.transform.resize((400, 600))
        assert isinstance(resized, Image)
        assert resized.size == (400, 600)

    def test_resize_small(self, loaded_image):
        resized = loaded_image.transform.resize((100, 150))
        assert resized.size == (100, 150)

    def test_resize_auto_height(self, loaded_image):
        """Pass -1 for height; width is fixed, height is auto-calculated."""
        resized = loaded_image.transform.resize((-1, 200))
        assert isinstance(resized, Image)
        assert resized.size[1] == 200

    def test_resize_auto_width(self, loaded_image):
        """Pass -1 for width; height is fixed, width is auto-calculated."""
        resized = loaded_image.transform.resize((200, -1))
        assert isinstance(resized, Image)
        assert resized.size[0] == 200

    def test_resize_preserves_image_type(self, loaded_image):
        resized = loaded_image.transform.resize((50, 50))
        assert type(resized) is Image

    def test_resize_both_minus_one_raises(self, loaded_image):
        with pytest.raises(ValueError):
            loaded_image.transform.resize((-1, -1))

    def test_resize_output_has_same_channels(self, loaded_image):
        original_channels = loaded_image.shape[2] if len(loaded_image.shape) == 3 else 1
        resized = loaded_image.transform.resize((100, 100))
        resized_channels = resized.shape[2] if len(resized.shape) == 3 else 1
        assert resized_channels == original_channels


# ===========================================================================
# FilterCalculator
# ===========================================================================

class TestFilterCalculator:
    def test_sobel_returns_image(self, loaded_image):
        filtered = loaded_image.filter.sobel()
        assert isinstance(filtered, Image)

    def test_sobel_same_spatial_shape(self, loaded_image):
        filtered = loaded_image.filter.sobel()
        assert filtered.shape[0] == loaded_image.shape[0]
        assert filtered.shape[1] == loaded_image.shape[1]

    def test_sobel_returns_new_image(self, loaded_image):
        filtered = loaded_image.filter.sobel()
        assert filtered is not loaded_image


# ===========================================================================
# DistanceCalculator
# ===========================================================================

class TestDistanceCalculator:
    def test_euclid_returns_float(self, loaded_image):
        sobel = loaded_image.filter.sobel()
        dist = loaded_image.dist.euclid(sobel)
        assert isinstance(dist, float)

    def test_euclid_nonnegative(self, loaded_image):
        sobel = loaded_image.filter.sobel()
        assert loaded_image.dist.euclid(sobel) >= 0

    def test_euclid_self_is_zero(self, loaded_image):
        assert loaded_image.dist.euclid(loaded_image) == pytest.approx(0.0)

    def test_composit_returns_float(self, loaded_image):
        sobel = loaded_image.filter.sobel()
        dist = loaded_image.dist.composit(sobel)
        assert isinstance(dist, float)

    def test_composit_nonnegative(self, loaded_image):
        sobel = loaded_image.filter.sobel()
        assert loaded_image.dist.composit(sobel) >= 0

    def test_sobel_dist_returns_float(self, loaded_image):
        sobel = loaded_image.filter.sobel()
        dist = loaded_image.dist.sobel(sobel)
        assert isinstance(dist, float)

    def test_composit_equals_euclid_plus_sobel(self, loaded_image):
        other = loaded_image.transform.resize((100, 100))
        # composit = euclid + sobel (on resized pair so sizes match)
        # Use the resized image against itself for a clean comparison
        a = other.dist.euclid(other) + other.dist.sobel(other)
        b = other.dist.composit(other)
        assert a == pytest.approx(b, rel=1e-5)


# ===========================================================================
# Advanced workflows (from notebook Section 3)
# ===========================================================================

class TestImageSimilarityAnalysis:
    """Replicate the analyze_image_similarities workflow from the notebook."""

    def test_distance_matrix_shape(self, image_collection):
        comparison_size = (50, 50)
        images = [imf.read().transform.resize(comparison_size) for imf in image_collection]
        n = len(images)
        distances = np.zeros((n, n))
        for i, img_i in enumerate(images):
            for j, img_j in enumerate(images):
                if i != j:
                    distances[i, j] = img_i.dist.composit(img_j)
        assert distances.shape == (n, n)

    def test_distance_matrix_diagonal_is_zero(self, image_collection):
        comparison_size = (50, 50)
        images = [imf.read().transform.resize(comparison_size) for imf in image_collection]
        n = len(images)
        distances = np.zeros((n, n))
        for i in range(n):
            distances[i, i] = images[i].dist.composit(images[i])
        assert np.all(distances == 0.0)

    def test_off_diagonal_distances_positive(self, image_collection):
        comparison_size = (50, 50)
        images = [imf.read().transform.resize(comparison_size) for imf in image_collection]
        n = len(images)
        for i in range(n):
            for j in range(n):
                if i != j:
                    d = images[i].dist.composit(images[j])
                    assert d >= 0.0


class TestImageQualityAssessment:
    """Replicate the assess_image_quality workflow from the notebook."""

    def _assess(self, image_files):
        results = []
        for img_file in image_files:
            meta = img_file.read_meta()
            stat = img_file.stat()
            image = img_file.read()
            edges = image.filter.sobel()
            edge_density = float(np.mean(edges.im))
            gray = np.mean(image.im, axis=2) if len(image.shape) == 3 else image.im
            dynamic_range = float(np.max(gray) - np.min(gray))
            results.append({
                'filename': img_file.path.name,
                'resolution': meta.res,
                'file_size_mb': stat.size / (1024 * 1024),
                'edge_density': edge_density,
                'dynamic_range': dynamic_range,
            })
        return results

    def test_returns_one_result_per_image(self, image_collection):
        results = self._assess(image_collection)
        assert len(results) == len(image_collection)

    def test_result_has_required_keys(self, image_collection):
        results = self._assess(image_collection)
        for r in results:
            for key in ('filename', 'resolution', 'file_size_mb', 'edge_density', 'dynamic_range'):
                assert key in r

    def test_edge_density_nonnegative(self, image_collection):
        results = self._assess(image_collection)
        for r in results:
            assert r['edge_density'] >= 0.0

    def test_dynamic_range_nonnegative(self, image_collection):
        results = self._assess(image_collection)
        for r in results:
            assert r['dynamic_range'] >= 0.0

    def test_file_size_mb_positive(self, image_collection):
        results = self._assess(image_collection)
        for r in results:
            assert r['file_size_mb'] > 0.0

    def test_resolution_is_tuple_of_two_positive_ints(self, image_collection):
        results = self._assess(image_collection)
        for r in results:
            w, h = r['resolution']
            assert w > 0 and h > 0


class TestOrganizationStats:
    """Replicate the organize_images_by_properties workflow from the notebook."""

    def _organize(self, image_files):
        stats = {'by_resolution': {}}
        for img_file in image_files:
            meta = img_file.read_meta()
            width, height = meta.res
            if width >= 1920 and height >= 1080:
                cat = "high_res"
            elif width >= 800 and height >= 600:
                cat = "medium_res"
            else:
                cat = "low_res"
            stats['by_resolution'][cat] = stats['by_resolution'].get(cat, 0) + 1
        return stats

    def test_returns_dict_with_by_resolution(self, image_collection):
        stats = self._organize(image_collection)
        assert 'by_resolution' in stats

    def test_total_count_equals_collection_size(self, image_collection):
        stats = self._organize(image_collection)
        total = sum(stats['by_resolution'].values())
        assert total == len(image_collection)

    def test_all_categories_are_valid(self, image_collection):
        valid = {"high_res", "medium_res", "low_res"}
        stats = self._organize(image_collection)
        for cat in stats['by_resolution']:
            assert cat in valid
