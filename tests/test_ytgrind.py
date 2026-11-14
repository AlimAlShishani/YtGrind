import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ytgrind import library, shorts, silence, subtitles  # noqa: E402
from ytgrind.common import ToolError, parse_timecode, slugify  # noqa: E402


class TimecodeTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(parse_timecode("90"), 90)
        self.assertEqual(parse_timecode("1:30"), 90)
        self.assertEqual(parse_timecode("01:02:03"), 3723)
        self.assertAlmostEqual(parse_timecode("1:30.5"), 90.5)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            parse_timecode("abc")

    def test_slug(self):
        self.assertEqual(slugify("Ranking EVERY Mob?!"), "ranking-every-mob")


class SilenceTests(unittest.TestCase):
    def test_keep_segments_leave_padding(self):
        segs = silence.keep_segments([(2.0, 3.5), (5.5, 7.0)], 9.0, pad=0.12)
        self.assertEqual([(round(a, 2), round(b, 2)) for a, b in segs], [(0.0, 2.12), (3.38, 5.62), (6.88, 9.0)])

    def test_short_silence_is_kept(self):
        # 0.2 s Pause mit pad 0.12 -> nichts zu entfernen
        self.assertEqual(silence.keep_segments([(1.0, 1.2)], 5.0, pad=0.12), [(0.0, 5.0)])

    def test_trailing_silence(self):
        segs = silence.keep_segments([(3.0, float("inf"))], 10.0, pad=0.1)
        self.assertEqual(len(segs), 1)
        self.assertAlmostEqual(segs[0][1], 3.1)

    def test_frame_snapping(self):
        segs = silence.keep_segments([(1.0, 2.0)], 4.0, pad=0.1, fps=30)
        for a, b in segs:
            self.assertAlmostEqual(a * 30, round(a * 30), places=6)
            self.assertAlmostEqual(b * 30, round(b * 30), places=6)

    def test_graph_single_segment_has_no_split(self):
        g = silence.build_filter_script([(0, 5)], has_video=True, audio_tracks=[0])
        self.assertNotIn("split", g)
        self.assertIn("concat=n=1:v=1:a=1[vout][aout0]", g)

    def test_graph_many_segments(self):
        g = silence.build_filter_script([(0, 1), (2, 3), (4, 5)], has_video=True, audio_tracks=[0, 1])
        self.assertIn("[0:v]split=3", g)
        self.assertIn("[0:a:1]asplit=3", g)
        self.assertIn("concat=n=3:v=1:a=2[vout][aout0][aout1]", g)


class SubtitleTests(unittest.TestCase):
    WORDS = [{"w": w, "s": i * 0.4, "e": i * 0.4 + 0.3} for i, w in enumerate("so this is the worst take. Fight me!".split())]

    def test_slice_shifts_to_zero(self):
        out = subtitles.slice_words(self.WORDS, 1.2, 2.4)
        self.assertTrue(out and out[0]["s"] >= 0)
        self.assertLess(out[-1]["e"], 1.3)

    def test_chunking_breaks_on_sentence_end(self):
        chunks = subtitles.chunk_words(self.WORDS, per_chunk=4)
        flat = [[w["w"] for w in c] for c in chunks]
        self.assertTrue(any(c[-1] == "take." for c in flat))

    def test_ass_contains_highlight_and_hook(self):
        ass = subtitles.build_ass(self.WORDS, hook_text="Hot take")
        self.assertIn("[Events]", ass)
        self.assertIn("HOT TAKE", ass)
        self.assertIn("{\\c&H00FFFF&}", ass)
        self.assertNotIn("take.", ass.replace("TAKE.", ""))  # Satzzeichen am Ende entfernt


class SpecTests(unittest.TestCase):
    def test_parse(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "s.txt"
            f.write_text("# c\n0:10 - 0:50 | Title here | mode=crop x=0.3\n1:00 - 1:30\n", encoding="utf-8")
            specs = shorts.parse_spec_file(f)
        self.assertEqual(len(specs), 2)
        self.assertEqual(specs[0].options, {"mode": "crop", "x": "0.3"})
        self.assertEqual(specs[1].title, "")

    def test_end_before_start(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "s.txt"
            f.write_text("0:50 - 0:10 | x\n", encoding="utf-8")
            with self.assertRaises(ToolError):
                shorts.parse_spec_file(f)

    def test_filters(self):
        self.assertTrue(shorts.video_filter("blur", 0.5).endswith("[v]"))
        self.assertIn("crop=1080:1920", shorts.video_filter("crop", 0.2))
        with self.assertRaises(ToolError):
            shorts.video_filter("zoom", 0.5)


class LibraryTests(unittest.TestCase):
    def test_init_tag_find(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "lib"
            library.init(root)
            (root / "memes/shock/shocked-pikachu.png").write_bytes(b"x")
            (root / "sfx/impact/boom.wav").write_bytes(b"x")
            res = library.scan(root)
            self.assertEqual(len(res["added"]), 2)
            self.assertEqual(library.scan(root)["added"], [])  # idempotent
            library.tag(root, "pikachu", ["+pokemon", "+funny"])
            hits = library.find(root, ["pokemon", "shock"])
            self.assertEqual([h["file"] for h in hits], ["memes/shock/shocked-pikachu.png"])
            self.assertEqual(len(library.find(root, ["pokemon", "boom"], any_tag=True)), 2)
            problems = library.check(root)
            self.assertTrue(any("QUELLE" in p for p in problems))
            # CSV ist mit ';' lesbar
            with (root / "index.csv").open(encoding="utf-8-sig") as fh:
                self.assertEqual(len(list(csv.DictReader(fh, delimiter=";"))), 2)


if __name__ == "__main__":
    unittest.main()
