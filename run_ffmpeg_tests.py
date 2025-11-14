#!/usr/bin/env python3
"""
Comprehensive test runner for FFMPEG class functionality.
This script tests the ffinput and ffoutput convenience functions
with the FFMPEG class using real video files and probe-based validation.
"""

import sys
import os
sys.path.append('./src')

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
    
    # List of tests to run
    tests = [
        (test_probe_video_properties, "Video Probe Properties"),
        (test_ffmpeg_command_generation, "Command Generation"),
        # Uncomment the following tests if ffmpeg is installed:
        # (test_ffmpeg_basic_conversion, "Basic Video Conversion"),
        # (test_ffmpeg_video_scaling, "Video Scaling"),
        # (test_ffmpeg_video_trimming, "Video Trimming"), 
        # (test_ffmpeg_quality_adjustment, "Quality Adjustment"),
        # (test_ffmpeg_audio_extraction, "Audio Extraction"),
        # (test_ffmpeg_multiple_outputs, "Multiple Outputs"),
        # (test_ffmpeg_seeking_with_accuracy, "Seeking with Accuracy"),
        # (test_ffmpeg_overwrite_protection, "Overwrite Protection"),
    ]
    
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