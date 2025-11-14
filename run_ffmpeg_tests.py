#!/usr/bin/env python3
"""
Comprehensive test runner for FFMPEG class functionality.
This script tests the ffinput and ffoutput convenience functions
with the FFMPEG class using real video files and probe-based validation.

Usage:
    python run_ffmpeg_tests.py           # Auto-detect FFmpeg and run appropriate tests
    python run_ffmpeg_tests.py --basic   # Run only basic tests (no FFmpeg required)
    python run_ffmpeg_tests.py --full    # Run all tests (requires FFmpeg)
    python run_ffmpeg_tests.py --force   # Force run all tests even if FFmpeg not detected
"""

import sys
import os
import argparse
sys.path.append('./src')

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='FFMPEG Class Test Runner')
    parser.add_argument('--basic', action='store_true', 
                       help='Run only basic tests (probe + command generation)')
    parser.add_argument('--full', action='store_true',
                       help='Run all tests including video processing (requires FFmpeg)')
    parser.add_argument('--force', action='store_true',
                       help='Force run all tests even if FFmpeg not detected')
    return parser.parse_args()

def run_test(test_func, test_name):
    """Run a single test with error handling"""
    print(f"\n{'='*60}")
    print(f"Running: {test_name}")
    print(f"{'='*60}")
    try:
        test_func()
        print(f"✅ {test_name} PASSED")
        return True
    except Exception as e:
        print(f"❌ {test_name} FAILED: {str(e)}")
        return False

def main():
    """Run all FFMPEG tests"""
    import shutil
    
    from tests.test_ffmpeg_tools import (
        test_probe_video_properties,
        test_ffmpeg_command_generation,
        test_ffmpeg_basic_conversion,
        test_ffmpeg_video_scaling,
        test_ffmpeg_video_trimming,
        test_ffmpeg_quality_adjustment,
        test_ffmpeg_audio_extraction,
        test_ffmpeg_multiple_outputs,
        test_ffmpeg_seeking_with_accuracy,
        test_ffmpeg_overwrite_protection
    )
    
    # Check if FFmpeg is available
    ffmpeg_available = shutil.which('ffmpeg') is not None
    
    # Tests that don't require FFmpeg binary
    basic_tests = [
        (test_probe_video_properties, "Video Probe Properties"),
        (test_ffmpeg_command_generation, "Command Generation"),
    ]
    
    # Tests that require FFmpeg binary for actual video processing
    ffmpeg_tests = [
        (test_ffmpeg_basic_conversion, "Basic Video Conversion"),
        (test_ffmpeg_video_scaling, "Video Scaling"),
        (test_ffmpeg_video_trimming, "Video Trimming"), 
        (test_ffmpeg_quality_adjustment, "Quality Adjustment"),
        (test_ffmpeg_audio_extraction, "Audio Extraction"),
        (test_ffmpeg_multiple_outputs, "Multiple Outputs"),
        (test_ffmpeg_seeking_with_accuracy, "Seeking with Accuracy"),
        (test_ffmpeg_overwrite_protection, "Overwrite Protection"),
    ]
    
def main():
    """Run all FFMPEG tests"""
    import shutil
    
    # Parse command line arguments
    args = parse_args()
    
    from tests.test_ffmpeg_tools import (
        test_probe_video_properties,
        test_ffmpeg_command_generation,
        test_ffmpeg_basic_conversion,
        test_ffmpeg_video_scaling,
        test_ffmpeg_video_trimming,
        test_ffmpeg_quality_adjustment,
        test_ffmpeg_audio_extraction,
        test_ffmpeg_multiple_outputs,
        test_ffmpeg_seeking_with_accuracy,
        test_ffmpeg_overwrite_protection
    )
    
    # Check if FFmpeg is available
    ffmpeg_available = shutil.which('ffmpeg') is not None
    
    # Tests that don't require FFmpeg binary
    basic_tests = [
        (test_probe_video_properties, "Video Probe Properties"),
        (test_ffmpeg_command_generation, "Command Generation"),
    ]
    
    # Tests that require FFmpeg binary for actual video processing
    ffmpeg_tests = [
        (test_ffmpeg_basic_conversion, "Basic Video Conversion"),
        (test_ffmpeg_video_scaling, "Video Scaling"),
        (test_ffmpeg_video_trimming, "Video Trimming"), 
        (test_ffmpeg_quality_adjustment, "Quality Adjustment"),
        (test_ffmpeg_audio_extraction, "Audio Extraction"),
        (test_ffmpeg_multiple_outputs, "Multiple Outputs"),
        (test_ffmpeg_seeking_with_accuracy, "Seeking with Accuracy"),
        (test_ffmpeg_overwrite_protection, "Overwrite Protection"),
    ]
    
    # Determine which tests to run based on arguments and FFmpeg availability
    if args.basic:
        tests = basic_tests
        print("🔧 Running BASIC tests only (by request)")
    elif args.full or args.force:
        tests = basic_tests + ffmpeg_tests
        if args.force and not ffmpeg_available:
            print("⚠️  WARNING: FFmpeg not detected but running all tests anyway (--force)")
        else:
            print("🚀 Running ALL tests (basic + video processing)")
    elif ffmpeg_available:
        tests = basic_tests + ffmpeg_tests
        print("✅ FFmpeg detected - running ALL tests (basic + video processing)")
    else:
        tests = basic_tests
        print("⚠️  FFmpeg not detected - running BASIC tests only (probe + command generation)")
        print("   Install FFmpeg to run the full video processing test suite")
        print("   Or use --force to run all tests anyway")
    
    # Run all tests
    passed = 0
    failed = 0
    
    print("🚀 Starting FFMPEG Class Tests")
    print("Using ffinput() and ffoutput() convenience functions")
    print("Testing with Big Buck Bunny video sample")
    
    for test_func, test_name in tests:
        if run_test(test_func, test_name):
            passed += 1
        else:
            failed += 1
    
    # Summary
    print(f"\n{'='*60}")
    print(f"TEST SUMMARY")
    print(f"{'='*60}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Total:  {passed + failed}")
    
    if failed == 0:
        print(f"\n🎉 All tests passed! FFMPEG class is working correctly.")
        print(f"✨ The ffinput() and ffoutput() convenience functions are ready for production use.")
    else:
        print(f"\n⚠️  Some tests failed. Check the output above for details.")
        
    return failed == 0

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)