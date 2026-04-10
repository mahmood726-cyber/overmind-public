from overmind.parsing.loop_detector import LoopDetector


def test_fingerprint_detects_rephrased_loops():
    detector = LoopDetector()
    lines = [
        "Running test at 10:30:15...",
        "Test failed with error code 42",
        "Running test at 10:30:20...",
        "Test failed with error code 43",
        "Running test at 10:30:25...",
        "Test failed with error code 44",
    ]
    # The lines differ in timestamps and error codes but the structure repeats
    assert detector.detect(lines) is True


def test_fingerprint_ignores_genuinely_different_content():
    detector = LoopDetector()
    lines = [
        "Building module A...",
        "Testing module A...",
        "Building module B...",
        "Testing module B...",
        "Building module C...",
        "Testing module C...",
    ]
    assert detector.detect(lines) is False


def test_fingerprint_catches_timestamp_only_differences():
    detector = LoopDetector()
    lines = [
        "[2026-04-07 10:00:01] Retrying connection to database",
        "[2026-04-07 10:00:05] Retrying connection to database",
        "[2026-04-07 10:00:09] Retrying connection to database",
    ]
    assert detector.detect(lines) is True


def test_existing_exact_match_still_works():
    detector = LoopDetector()
    lines = ["same line", "same line", "same line"]
    assert detector.detect(lines) is True


def test_normalize_strips_numbers_and_timestamps():
    detector = LoopDetector()
    a = detector._normalize_for_fingerprint("Error at 10:30:15 with code 42")
    b = detector._normalize_for_fingerprint("Error at 11:45:20 with code 99")
    assert a == b
